"""
snapshot_manager.py – Saves JPEG snapshots triggered by detection / error / reconnect events.

Folder layout:
    snapshots/detection/   – frames where person or vehicle is detected
    snapshots/error/       – frames captured at the moment of an error
    snapshots/reconnect/   – first frame after a successful reconnection
"""

import logging
import os
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

SNAPSHOT_ROOT = "snapshots"
_SUBDIRS = ("detection", "error", "reconnect")


def _ensure_dirs() -> None:
    for sub in _SUBDIRS:
        os.makedirs(os.path.join(SNAPSHOT_ROOT, sub), exist_ok=True)


_ensure_dirs()


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:21]


def _save(frame: np.ndarray, subfolder: str, prefix: str) -> Optional[str]:
    path = os.path.join(SNAPSHOT_ROOT, subfolder, f"{prefix}_{_ts()}.jpg")
    try:
        cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        log.info("Snapshot saved: %s", path)
        return path
    except Exception as exc:
        log.error("Failed to save snapshot to %s: %s", path, exc)
        return None


def save_detection_snapshot(frame: np.ndarray) -> Optional[str]:
    return _save(frame, "detection", "det")


def save_error_snapshot(frame: Optional[np.ndarray]) -> Optional[str]:
    if frame is None:
        # Save a black placeholder
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
    return _save(frame, "error", "err")


def save_reconnect_snapshot(frame: np.ndarray) -> Optional[str]:
    return _save(frame, "reconnect", "rec")
