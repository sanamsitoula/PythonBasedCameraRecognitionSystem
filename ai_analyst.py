"""
ai_analyst.py – Periodic AI scene analysis with multi-provider fallback.

Providers are tried in order.  If one fails (any HTTP error, network issue,
or 402 quota), the next is tried automatically.  No provider is skipped
permanently — the full chain is retried on every analysis cycle.

Provider order (configured in config.ini [AI] section):
  1. Gemini          – OpenAI-compatible via Google's compatibility endpoint
  2. Anthropic/Claude – native Anthropic Messages API
  3. OpenRouter       – OpenAI-compatible proxy
  4. DeepSeek         – OpenAI-compatible
"""

import json
import logging
import threading
import time
import urllib.request
import urllib.error
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from detection import DetectionResult

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a CCTV security analyst. Given a frame-by-frame detection summary "
    "from a camera feed, reply with ONE concise sentence (max 120 characters) "
    "describing current scene activity or any notable observations. "
    "Be direct, factual, and security-focused. No preamble."
)


# ─────────────────────────── provider descriptor ─────────────────────────────

@dataclass
class ProviderConfig:
    name:         str
    api_key:      str
    model:        str
    endpoint:     str
    is_anthropic: bool = False   # True → use native Anthropic Messages API


# ─────────────────────────── insight result ──────────────────────────────────

@dataclass
class AiInsight:
    text:      str = "Awaiting first analysis…"
    timestamp: str = "–"
    model:     str = ""
    provider:  str = ""
    error:     bool = False


# ─────────────────────────── analyst ─────────────────────────────────────────

class AiAnalyst:
    def __init__(self, providers: List[ProviderConfig], interval: int):
        # drop any provider with no API key
        self._providers = [p for p in providers if p.api_key.strip()]
        self._interval  = interval

        self._lock    = threading.Lock()
        first_model   = self._providers[0].model if self._providers else "–"
        self._insight = AiInsight(model=first_model)
        self._buffer: deque[DetectionResult] = deque(maxlen=300)
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ─────────────────────────── public API ──────────────────────────────────

    def push(self, det: DetectionResult) -> None:
        with self._lock:
            self._buffer.append(det)

    @property
    def insight(self) -> AiInsight:
        with self._lock:
            return self._insight

    def start(self) -> None:
        if not self._providers:
            log.warning("AI analyst: no providers configured — analyst disabled.")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="ai-analyst"
        )
        self._thread.start()
        names = [p.name for p in self._providers]
        log.info("AI analyst started (providers=%s, interval=%ds)", names, self._interval)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    # ─────────────────────────── background loop ─────────────────────────────

    def _loop(self) -> None:
        time.sleep(self._interval)
        while self._running:
            self._analyse()
            time.sleep(self._interval)

    def _analyse(self) -> None:
        with self._lock:
            snapshot = list(self._buffer)
            self._buffer.clear()

        if not snapshot:
            return

        prompt = self._build_prompt(snapshot)
        ts     = datetime.now().strftime("%H:%M:%S")

        for provider in self._providers:
            try:
                if provider.is_anthropic:
                    text = self._call_anthropic(provider, prompt)
                else:
                    text = self._call_openai_compat(provider, prompt)

                with self._lock:
                    self._insight = AiInsight(
                        text      = text,
                        timestamp = ts,
                        model     = provider.model,
                        provider  = provider.name,
                        error     = False,
                    )
                log.debug("AI insight [%s]: %s", provider.name, text)
                return  # success — stop trying further providers

            except urllib.error.HTTPError as exc:
                log.warning(
                    "AI provider '%s' HTTP %s %s — trying next provider.",
                    provider.name, exc.code, exc.reason,
                )
            except urllib.error.URLError as exc:
                log.warning(
                    "AI provider '%s' network error: %s — trying next provider.",
                    provider.name, exc.reason,
                )
            except Exception as exc:
                log.warning(
                    "AI provider '%s' error: %s — trying next provider.",
                    provider.name, exc,
                )

        # all providers failed
        log.warning("AI analyst: all %d provider(s) failed this cycle.", len(self._providers))
        with self._lock:
            self._insight.error = True

    # ─────────────────────────── provider calls ──────────────────────────────

    def _call_openai_compat(self, provider: ProviderConfig, prompt: str) -> str:
        """OpenAI-compatible /chat/completions call (Gemini, OpenRouter, DeepSeek)."""
        payload = json.dumps({
            "model": provider.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            "max_tokens": 80,
        }).encode()

        req = urllib.request.Request(
            provider.endpoint,
            data    = payload,
            headers = {
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {provider.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
        return body["choices"][0]["message"]["content"].strip()

    def _call_anthropic(self, provider: ProviderConfig, prompt: str) -> str:
        """Native Anthropic Messages API call."""
        # Anthropic doesn't use a system role in messages; prepend to user text.
        payload = json.dumps({
            "model":      provider.model,
            "max_tokens": 80,
            "system":     _SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }).encode()

        req = urllib.request.Request(
            provider.endpoint,
            data    = payload,
            headers = {
                "Content-Type":      "application/json",
                "x-api-key":         provider.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
        return body["content"][0]["text"].strip()

    # ─────────────────────────── prompt builder ──────────────────────────────

    @staticmethod
    def _build_prompt(frames: list) -> str:
        total      = len(frames)
        det_frames = sum(1 for f in frames if f.has_detection)

        keys   = ("people", "cars", "motorcycles", "buses", "trucks", "bicycles")
        totals = {k: sum(getattr(f, k) for f in frames) for k in keys}
        peaks  = {k: max((getattr(f, k) for f in frames), default=0) for k in keys}

        cumulative = ", ".join(f"{v} {k}" for k, v in totals.items() if v > 0) or "none"
        peak_str   = ", ".join(f"{v} {k}" for k, v in peaks.items()  if v > 0) or "none"

        return (
            f"Frames analysed: {total} ({det_frames} contained detections)\n"
            f"Cumulative counts: {cumulative}\n"
            f"Peak in a single frame: {peak_str}"
        )
