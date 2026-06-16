"""
health_monitor.py – Periodic system resource monitoring.

Samples CPU and RAM in a background thread and exposes current values.
Also triggers memory protection actions when RAM exceeds the configured limit.
"""

import logging
import threading
import time

import psutil

from config_manager import AppConfig

log = logging.getLogger(__name__)


class HealthMonitor:
    def __init__(self, config: AppConfig):
        self._max_ram_bytes = config.system.max_ram_mb * 1024 * 1024
        self._interval      = 2.0   # sample every 2 seconds

        self._cpu_pct: float = 0.0
        self._ram_gb:  float = 0.0
        self._lock     = threading.Lock()
        self._stop     = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="HealthMonitor"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def cpu_pct(self) -> float:
        with self._lock:
            return self._cpu_pct

    @property
    def ram_gb(self) -> float:
        with self._lock:
            return self._ram_gb

    def _loop(self) -> None:
        while not self._stop.is_set():
            cpu = psutil.cpu_percent(interval=None)
            vm  = psutil.virtual_memory()
            ram_bytes = vm.used

            with self._lock:
                self._cpu_pct = cpu
                self._ram_gb  = ram_bytes / (1024 ** 3)

            if ram_bytes > self._max_ram_bytes:
                log.warning(
                    "RAM usage %.2f GB exceeds limit %.2f GB – consider reducing queue size.",
                    ram_bytes / (1024 ** 3),
                    self._max_ram_bytes / (1024 ** 3),
                )

            time.sleep(self._interval)
