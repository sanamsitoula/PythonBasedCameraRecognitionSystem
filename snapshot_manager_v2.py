"""
snapshot_manager_v2.py – Extended snapshot storage for Phase 2.

Saves annotated frames to category-specific subdirectories:
    snapshots/people/
    snapshots/vehicles/
    snapshots/entry/
    snapshots/exit/
    snapshots/gender/

Filenames encode the track ID and timestamp so they sort chronologically.
"""

import logging
import os
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

_DIRS = {
    "people":   os.path.join("snapshots", "people"),
    "vehicles": os.path.join("snapshots", "vehicles"),
    "entry":    os.path.join("snapshots", "entry"),
    "exit":     os.path.join("snapshots", "exit"),
    "gender":   os.path.join("snapshots", "gender"),
}


def _ensure_dirs() -> None:
    for d in _DIRS.values():
        os.makedirs(d, exist_ok=True)


_ensure_dirs()


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]


def _save(category: str, image: np.ndarray, name: str) -> Optional[str]:
    path = os.path.join(_DIRS[category], name)
    try:
        cv2.imwrite(path, image)
        return path
    except Exception as exc:
        log.warning("Snapshot write failed (%s): %s", path, exc)
        return None


def _crop_bbox(frame: np.ndarray, bbox: tuple, pad: float = 0.06) -> Optional[np.ndarray]:
    x1, y1, x2, y2 = bbox
    h, w = frame.shape[:2]
    px = max(0, int((x2 - x1) * pad))
    py = max(0, int((y2 - y1) * pad))
    c = frame[max(0, y1 - py): min(h, y2 + py), max(0, x1 - px): min(w, x2 + px)]
    return c if c.size > 0 else None


# ─────────────────────────── public API ──────────────────────────────────────

def save_person_snapshot(
    frame: np.ndarray, track_id: str, bbox: tuple
) -> Optional[str]:
    crop = _crop_bbox(frame, bbox)
    if crop is None:
        return None
    return _save("people", crop, f"{track_id}_{_ts()}.jpg")


def save_vehicle_snapshot(
    frame: np.ndarray, track_id: str, vehicle_type: str, bbox: tuple
) -> Optional[str]:
    crop = _crop_bbox(frame, bbox)
    if crop is None:
        return None
    return _save("vehicles", crop, f"{track_id}_{vehicle_type}_{_ts()}.jpg")


def save_entry_snapshot(
    frame: np.ndarray, track_id: str, draw_text: bool = True
) -> Optional[str]:
    img = frame.copy() if draw_text else frame
    if draw_text:
        cv2.putText(img, f"ENTRY {track_id}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    return _save("entry", img, f"{track_id}_entry_{_ts()}.jpg")


def save_exit_snapshot(
    frame: np.ndarray, track_id: str, draw_text: bool = True
) -> Optional[str]:
    img = frame.copy() if draw_text else frame
    if draw_text:
        cv2.putText(img, f"EXIT {track_id}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    return _save("exit", img, f"{track_id}_exit_{_ts()}.jpg")


def save_gender_snapshot(
    frame: np.ndarray, track_id: str, gender: str, confidence: float, bbox: tuple
) -> Optional[str]:
    crop = _crop_bbox(frame, bbox)
    if crop is None:
        return None
    crop = crop.copy()
    label = f"{gender} {confidence * 100:.0f}%"
    colour = (255, 180, 0) if gender == "Male" else (200, 0, 255)
    cv2.putText(crop, label, (5, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.65, colour, 2)
    return _save("gender", crop, f"{track_id}_{gender}_{_ts()}.jpg")
