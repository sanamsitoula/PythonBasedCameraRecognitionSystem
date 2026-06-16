"""
rtsp_capture.py – Threaded RTSP frame capture with automatic reconnection.

Spawns a daemon thread that continuously reads frames from the camera and
places them into a bounded queue.  The main thread consumes frames from the
queue without blocking the capture loop.

Public interface:
    RTSPCapture.start()
    RTSPCapture.read() → Optional[np.ndarray]
    RTSPCapture.stop()
    RTSPCapture.is_connected → bool
    RTSPCapture.actual_fps   → float
"""

import logging
import queue
import threading
import time
from typing import Optional

import cv2
import numpy as np

from config_manager import AppConfig

log = logging.getLogger("camera")


class RTSPCapture:
    def __init__(self, config: AppConfig, on_reconnect=None, on_failure=None):
        self._config         = config
        self._url            = config.camera.rtsp_url
        self._q_size         = config.system.frame_queue_size
        self._fail_threshold = config.system.frame_failure_threshold
        self._reconnect_max  = config.system.reconnect_attempts
        self._reconnect_wait = config.system.reconnect_delay

        self._on_reconnect = on_reconnect   # callable() invoked after successful reconnect
        self._on_failure   = on_failure     # callable() invoked on unrecoverable failure

        self._queue: queue.Queue = queue.Queue(maxsize=self._q_size)
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event   = threading.Event()
        self._connected    = threading.Event()

        # FPS tracking
        self._fps_lock       = threading.Lock()
        self._frame_times: list = []
        self._actual_fps: float = 0.0

        # Failure counter
        self._fail_count = 0

    # ─────────────────────────── public API ─────────────────────────────────

    def start(self) -> bool:
        """Open the RTSP stream and start the capture thread. Returns True on success."""
        if not self._open_capture():
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="RTSPCapture")
        self._thread.start()
        return True

    def read(self) -> Optional[np.ndarray]:
        """Return the latest frame from the queue, or None if no frame available."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self) -> None:
        """Signal the capture thread to stop and release the capture object."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._release()
        log.info("RTSPCapture stopped.")

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def actual_fps(self) -> float:
        with self._fps_lock:
            return round(self._actual_fps, 1)

    # ─────────────────────────── internals ──────────────────────────────────

    def _open_capture(self) -> bool:
        """Try to open cv2.VideoCapture with RTSP transport options."""
        self._release()
        cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        # Low-latency transport settings
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8_000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5_000)

        if cap.isOpened():
            self._cap = cap
            self._connected.set()
            self._fail_count = 0
            log.info("RTSP stream opened: %s", self._url)
            return True

        cap.release()
        log.error("Failed to open RTSP stream: %s", self._url)
        self._connected.clear()
        return False

    def _release(self) -> None:
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _capture_loop(self) -> None:
        """Main capture loop – runs in daemon thread."""
        while not self._stop_event.is_set():
            if not self._cap or not self._cap.isOpened():
                self._reconnect()
                continue

            ret, frame = self._cap.read()

            if not ret or frame is None:
                self._fail_count += 1
                log.warning("Frame read failure #%d", self._fail_count)

                if self._fail_count >= self._fail_threshold:
                    log.error(
                        "Frame failure threshold reached (%d). Initiating reconnection.",
                        self._fail_threshold,
                    )
                    self._reconnect()
                continue

            # Frame OK – reset failure counter
            self._fail_count = 0
            self._update_fps()

            # Keep queue size bounded (drop oldest frame if full)
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
            try:
                self._queue.put_nowait(frame)
            except queue.Full:
                pass

    def _update_fps(self) -> None:
        now = time.monotonic()
        with self._fps_lock:
            self._frame_times.append(now)
            # Keep only the last 30 timestamps
            if len(self._frame_times) > 30:
                self._frame_times.pop(0)
            if len(self._frame_times) >= 2:
                elapsed = self._frame_times[-1] - self._frame_times[0]
                if elapsed > 0:
                    self._actual_fps = (len(self._frame_times) - 1) / elapsed

    def _reconnect(self) -> None:
        """Attempt to re-open the stream up to reconnect_attempts times."""
        self._connected.clear()
        self._release()
        # Drain the frame queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        for attempt in range(1, self._reconnect_max + 1):
            if self._stop_event.is_set():
                return
            log.warning("Reconnect attempt %d/%d …", attempt, self._reconnect_max)
            time.sleep(self._reconnect_wait)
            if self._open_capture():
                log.info("Reconnected successfully on attempt %d", attempt)
                if callable(self._on_reconnect):
                    self._on_reconnect()
                return

        log.critical("All %d reconnect attempts exhausted. Giving up.", self._reconnect_max)
        if callable(self._on_failure):
            self._on_failure()
        self._stop_event.set()
