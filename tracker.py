"""
tracker.py – ByteTrack-based multi-object tracker using ultralytics.

Calling model.track(persist=True, tracker="bytetrack.yaml") gives us
persistent integer track IDs across frames.  This module:
  * Formats them as P-0001 (persons) / V-0001 (vehicles)
  * Detects stale tracks (not seen for max_age frames) and closes them
  * Returns a TrackingFrame with all active TrackedObject entries
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

PERSON_CLASSES:  dict[int, str] = {0: "person"}
VEHICLE_CLASSES: dict[int, str] = {
    1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"
}
ALL_CLASSES: dict[int, str] = {**PERSON_CLASSES, **VEHICLE_CLASSES}


@dataclass
class TrackedObject:
    track_id:    str            # P-0001 or V-0001
    raw_id:      int            # internal ByteTrack integer ID
    class_name:  str            # "person", "car", etc.
    confidence:  float
    bbox:        tuple          # (x1, y1, x2, y2) pixels
    center:      tuple          # (cx, cy)
    is_person:   bool
    is_vehicle:  bool
    first_seen:  datetime = field(default_factory=datetime.now)
    last_seen:   datetime = field(default_factory=datetime.now)
    age_frames:  int = 0        # consecutive frames this track has been alive


@dataclass
class TrackingFrame:
    tracks:       list          # List[TrackedObject]
    frame_number: int
    timestamp:    datetime
    closed_ids:   list          # track_ids closed this frame (stale)

    @property
    def persons(self) -> list:
        return [t for t in self.tracks if t.is_person]

    @property
    def vehicles(self) -> list:
        return [t for t in self.tracks if t.is_vehicle]

    @property
    def people_count(self) -> int:
        return sum(1 for t in self.tracks if t.is_person)

    def counts_by_class(self) -> dict:
        counts: dict[str, int] = {}
        for t in self.tracks:
            counts[t.class_name] = counts.get(t.class_name, 0) + 1
        return counts


class ByteTracker:
    def __init__(
        self,
        model_path:  str,
        confidence:  float,
        iou:         float,
        device:      str = "auto",
        max_age:     int = 30,
        min_hits:    int = 1,
    ):
        self._model_path  = model_path
        self._confidence  = confidence
        self._iou         = iou
        self._device      = device
        self._max_age     = max_age
        self._min_hits    = min_hits
        self._model       = None
        self._using_gpu   = False
        self._frame_count = 0

        # track registries
        self._person_registry:  dict[int, str] = {}
        self._vehicle_registry: dict[int, str] = {}
        self._person_counter  = 0
        self._vehicle_counter = 0

        # live track objects keyed by track_id string
        self._active: dict[str, TrackedObject] = {}
        # frame number when each track was last seen
        self._last_seen_frame: dict[str, int] = {}

        self._tracker_yaml = self._resolve_tracker_yaml()
        self._load_model()

    # ─────────────────────────── model loading ───────────────────────────────

    def _resolve_tracker_yaml(self) -> str:
        """Find bytetrack.yaml bundled with ultralytics; fall back to botsort.yaml."""
        try:
            import ultralytics
            pkg = os.path.dirname(ultralytics.__file__)
            for name in ("bytetrack.yaml", "botsort.yaml"):
                candidate = os.path.join(pkg, "cfg", "trackers", name)
                if os.path.exists(candidate):
                    log.info("Using tracker config: %s", candidate)
                    return candidate
        except Exception as exc:
            log.warning("Could not resolve tracker yaml path: %s", exc)
        return "bytetrack.yaml"

    def _load_model(self) -> None:
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError:
            raise RuntimeError("ultralytics is not installed. Run: pip install ultralytics")

        if not os.path.exists(self._model_path):
            log.warning("Model not found at '%s'. Will be auto-downloaded.", self._model_path)

        device = self._resolve_device()
        try:
            self._model = YOLO(self._model_path)
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            self._model.predict(dummy, device=device, verbose=False)
            self._using_gpu = (device != "cpu")
            self._device = device
            log.info("ByteTracker model loaded on device='%s'", device)
        except Exception as exc:
            log.error("GPU load failed (%s). Falling back to CPU.", exc)
            self._model = YOLO(self._model_path)
            self._device = "cpu"
            self._using_gpu = False
            log.info("ByteTracker model loaded on CPU (fallback).")

    def _resolve_device(self) -> str:
        if self._device.lower() != "auto":
            return self._device.lower()
        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                log.info("CUDA GPU detected: %s", torch.cuda.get_device_name(0))
                return "0"
        except ImportError:
            pass
        return "cpu"

    # ─────────────────────────── ID helpers ──────────────────────────────────

    def _person_id(self, raw_id: int) -> str:
        if raw_id not in self._person_registry:
            self._person_counter += 1
            self._person_registry[raw_id] = f"P-{self._person_counter:04d}"
        return self._person_registry[raw_id]

    def _vehicle_id(self, raw_id: int) -> str:
        if raw_id not in self._vehicle_registry:
            self._vehicle_counter += 1
            self._vehicle_registry[raw_id] = f"V-{self._vehicle_counter:04d}"
        return self._vehicle_registry[raw_id]

    # ─────────────────────────── public track() ──────────────────────────────

    def track(self, frame: np.ndarray) -> TrackingFrame:
        self._frame_count += 1
        now = datetime.now()

        raw_tracks: list[TrackedObject] = []

        if self._model is not None:
            try:
                results = self._model.track(
                    frame,
                    tracker   = self._tracker_yaml,
                    persist   = True,
                    device    = self._device,
                    conf      = self._confidence,
                    iou       = self._iou,
                    classes   = list(ALL_CLASSES.keys()),
                    verbose   = False,
                )
                raw_tracks = self._parse_results(results, now)
            except Exception as exc:
                log.error("ByteTrack inference error on frame %d: %s", self._frame_count, exc)

        # update active track table
        seen_ids: set[str] = set()
        for obj in raw_tracks:
            seen_ids.add(obj.track_id)
            if obj.track_id in self._active:
                existing = self._active[obj.track_id]
                existing.last_seen  = now
                existing.confidence = obj.confidence
                existing.bbox       = obj.bbox
                existing.center     = obj.center
                existing.age_frames += 1
                obj = existing
            else:
                self._active[obj.track_id] = obj
                log.debug("New track: %s (%s)", obj.track_id, obj.class_name)
            self._last_seen_frame[obj.track_id] = self._frame_count

        # detect stale tracks
        closed: list[str] = []
        for tid, last_f in list(self._last_seen_frame.items()):
            if (self._frame_count - last_f) > self._max_age:
                closed.append(tid)
                self._active.pop(tid, None)
                self._last_seen_frame.pop(tid, None)
                log.debug("Track closed (stale): %s", tid)

        # min_hits=1 → show from first confirmed frame (age_frames >= 0)
        # min_hits=N → require N-1 increments before showing
        _threshold = max(0, self._min_hits - 1)
        current_tracks = [
            self._active[tid]
            for tid in self._active
            if self._active[tid].age_frames >= _threshold
        ]

        return TrackingFrame(
            tracks       = current_tracks,
            frame_number = self._frame_count,
            timestamp    = now,
            closed_ids   = closed,
        )

    def _parse_results(self, results, now: datetime) -> list:
        if not results or results[0].boxes is None:
            return []
        boxes = results[0].boxes
        if len(boxes) == 0:
            return []

        # ByteTrack may not assign IDs on the very first frame(s).
        # Fall back to index-based temp IDs so detections appear immediately.
        if boxes.id is not None:
            raw_ids = [int(x) for x in boxes.id.tolist()]
        else:
            raw_ids = list(range(len(boxes.xyxy)))
            log.debug("boxes.id is None on frame %d — using temp IDs", self._frame_count)

        tracks = []
        for box, cls_id, raw_id, conf in zip(
            boxes.xyxy.tolist(),
            boxes.cls.tolist(),
            raw_ids,
            boxes.conf.tolist(),
        ):
            cls_id     = int(cls_id)
            raw_id     = int(raw_id)
            class_name = ALL_CLASSES.get(cls_id, "unknown")
            is_person  = cls_id in PERSON_CLASSES
            is_vehicle = cls_id in VEHICLE_CLASSES

            track_id = self._person_id(raw_id) if is_person else self._vehicle_id(raw_id)
            x1, y1, x2, y2 = (int(v) for v in box)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            tracks.append(TrackedObject(
                track_id   = track_id,
                raw_id     = raw_id,
                class_name = class_name,
                confidence = round(float(conf), 3),
                bbox       = (x1, y1, x2, y2),
                center     = (cx, cy),
                is_person  = is_person,
                is_vehicle = is_vehicle,
                first_seen = now,
                last_seen  = now,
            ))
        return tracks

    # ─────────────────────────── properties ──────────────────────────────────

    @property
    def using_gpu(self) -> bool:
        return self._using_gpu

    @property
    def device_label(self) -> str:
        return "GPU" if self._using_gpu else "CPU"

    @property
    def total_persons_seen(self) -> int:
        return self._person_counter

    @property
    def total_vehicles_seen(self) -> int:
        return self._vehicle_counter
