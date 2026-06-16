"""
logger.py – Centralised logging configuration for CCTV Phase 1 & 2.

Phase 1 log files:
    logs/application.log  – general INFO+ messages
    logs/error.log        – ERROR+ messages only
    logs/camera.log       – camera-specific events

Phase 2 category log files (added by setup_phase2_loggers()):
    logs/tracking.log     – track open/update/close events
    logs/analytics.log    – entry/exit/zone/direction events
    logs/database.log     – DB writes and connection events
    logs/gender.log       – gender classification results
    logs/vehicle.log      – vehicle detection events
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

_LOG_FORMAT = "%(asctime)s\n%(levelname)s\n%(message)s\n"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 10 * 1024 * 1024   # 10 MB per file
_BACKUP_COUNT = 5


def _make_file_handler(path: str, level: int) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def setup_logging(log_level: str = "INFO") -> None:
    """Call once at startup to wire up all handlers."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)          # capture everything; handlers filter

    if root.handlers:                     # avoid duplicate handlers on reload
        return

    # Console handler – only WARNING and above to keep Rich dashboard clean
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(console)

    # application.log
    root.addHandler(
        _make_file_handler(os.path.join(LOG_DIR, "application.log"), numeric_level)
    )
    # error.log
    root.addHandler(
        _make_file_handler(os.path.join(LOG_DIR, "error.log"), logging.ERROR)
    )


_PHASE2_LOGGERS = {
    "tracking":  "tracking.log",
    "analytics": "analytics.log",
    "database":  "database.log",
    "gender":    "gender.log",
    "vehicle":   "vehicle.log",
}


def setup_phase2_loggers() -> None:
    """Wire up Phase 2 category-specific log files. Call after setup_logging()."""
    for logger_name, filename in _PHASE2_LOGGERS.items():
        cat = logging.getLogger(logger_name)
        if not any(isinstance(h, RotatingFileHandler) for h in cat.handlers):
            cat.addHandler(
                _make_file_handler(os.path.join(LOG_DIR, filename), logging.DEBUG)
            )
        cat.propagate = True   # also goes to application.log


_PHASE3_LOGGERS = {
    "recognition": "recognition.log",
    "enrollment":  "enrollment.log",
    "attendance":  "attendance.log",
    "alerts":      "alerts.log",
}


def setup_phase3_loggers() -> None:
    """Wire up Phase 3 category-specific log files. Call after setup_logging()."""
    for logger_name, filename in _PHASE3_LOGGERS.items():
        cat = logging.getLogger(logger_name)
        if not any(isinstance(h, RotatingFileHandler) for h in cat.handlers):
            cat.addHandler(
                _make_file_handler(os.path.join(LOG_DIR, filename), logging.DEBUG)
            )
        cat.propagate = True   # also goes to application.log


def get_camera_logger() -> logging.Logger:
    """Returns a logger that additionally writes to logs/camera.log."""
    cam_logger = logging.getLogger("camera")
    if not any(
        isinstance(h, RotatingFileHandler)
        and "camera.log" in getattr(h, "baseFilename", "")
        for h in cam_logger.handlers
    ):
        cam_logger.addHandler(
            _make_file_handler(os.path.join(LOG_DIR, "camera.log"), logging.DEBUG)
        )
    return cam_logger
