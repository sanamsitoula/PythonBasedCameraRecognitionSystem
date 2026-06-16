"""
db_writer.py – Background database write thread.

The main loop enqueues events via put_*() methods (non-blocking).
A dedicated daemon thread drains the queue and calls db_manager in batches.
The main loop is never blocked by DB I/O.

If the queue is full (backpressure), events are dropped with a warning.
Enqueue tracked_object rows in batches of `batch_size` for efficiency.
"""

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from db_manager import DatabaseManager

log = logging.getLogger("database")

_FLUSH_INTERVAL = 2.0    # seconds between queue drain cycles
_BATCH_MAX      = 200    # max tracked_objects rows per INSERT batch


@dataclass
class _TrackedObjRow:
    session_id:   int
    track_id:     str
    frame_number: int
    class_label:  str
    confidence:   float
    x1: int; y1: int; x2: int; y2: int
    cx: int; cy: int


class DbWriter:
    def __init__(self, db: "DatabaseManager", session_id: Optional[int], queue_size: int = 2000):
        self._db          = db
        self._session_id  = session_id
        self._queue:      queue.Queue = queue.Queue(maxsize=queue_size)
        self._obj_buffer: list        = []
        self._dropped     = 0
        self._running     = False
        self._thread:     Optional[threading.Thread] = None

    def start(self) -> None:
        self._running = True
        self._thread  = threading.Thread(
            target = self._loop, daemon = True, name = "db-writer"
        )
        self._thread.start()
        log.info("DbWriter started (session_id=%s).", self._session_id)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        self._flush_all()
        log.info("DbWriter stopped. Dropped events: %d", self._dropped)

    # ─────────────────────────── enqueue methods ─────────────────────────────

    def put_tracked_object(
        self, session_id: int, track_id: str, frame_number: int,
        class_label: str, confidence: float,
        x1: int, y1: int, x2: int, y2: int, cx: int, cy: int
    ) -> None:
        self._put(("tracked_obj", session_id, track_id, frame_number,
                   class_label, confidence, x1, y1, x2, y2, cx, cy))

    def put_gender(
        self, track_id: str, frame_number: int,
        gender: str, confidence: float, backend: str
    ) -> None:
        self._put(("gender", track_id, frame_number, gender, confidence, backend))

    def put_direction(
        self, track_id: str, direction: str, class_label: str,
        sx: int, sy: int, ex: int, ey: int
    ) -> None:
        self._put(("direction", track_id, direction, class_label, sx, sy, ex, ey))

    def put_crossing(
        self, track_id: str, line_label: str, direction: str,
        class_label: str, cx: int, cy: int, frame_number: int
    ) -> None:
        self._put(("crossing", track_id, line_label, direction, class_label, cx, cy, frame_number))

    def put_zone_event(
        self, track_id: str, zone_label: str, event_type: str,
        class_label: str, frame_number: int, duration: Optional[float]
    ) -> None:
        self._put(("zone", track_id, zone_label, event_type, class_label, frame_number, duration))

    def put_occupancy(
        self, current_p: int, current_v: int,
        peak_p: int, peak_v: int, avg_p: float, avg_v: float
    ) -> None:
        self._put(("occupancy", current_p, current_v, peak_p, peak_v, avg_p, avg_v))

    def put_vehicle_counts(
        self, bucket_start: datetime,
        cars: int, motorcycles: int, buses: int, trucks: int, bicycles: int
    ) -> None:
        self._put(("vehicle_counts", bucket_start, cars, motorcycles, buses, trucks, bicycles))

    def put_health(self, cpu: float, ram_gb: float, device: str, fps: float) -> None:
        self._put(("health", cpu, ram_gb, device, fps))

    def put_error(
        self, severity: str, module: str, message: str, traceback: Optional[str] = None
    ) -> None:
        self._put(("error", severity, module, message, traceback))

    # ─────────────────────────── internals ───────────────────────────────────

    def _put(self, item: tuple) -> None:
        if not self._db.is_available:
            return
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self._dropped += 1
            if self._dropped % 100 == 0:
                log.warning("DB write queue full — %d events dropped.", self._dropped)

    def _loop(self) -> None:
        while self._running:
            self._flush_all()
            time.sleep(_FLUSH_INTERVAL)

    def _flush_all(self) -> None:
        if not self._db.is_available or self._session_id is None:
            # drain queue to avoid memory leak
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            return

        obj_batch: list = []

        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break

            kind = item[0]

            if kind == "tracked_obj":
                _, sid, tid, fn, cl, cf, x1, y1, x2, y2, cx, cy = item
                obj_batch.append((sid, tid, fn, cl, cf, x1, y1, x2, y2, cx, cy))
                if len(obj_batch) >= _BATCH_MAX:
                    self._db.insert_tracked_objects_batch(self._session_id, obj_batch)
                    obj_batch = []

            elif kind == "gender":
                _, tid, fn, gender, conf, backend = item
                self._db.insert_gender(self._session_id, tid, fn, gender, conf, backend)

            elif kind == "direction":
                _, tid, direction, cl, sx, sy, ex, ey = item
                self._db.insert_direction_event(
                    self._session_id, tid, direction, cl, sx, sy, ex, ey
                )

            elif kind == "crossing":
                _, tid, ll, dir_, cl, cx, cy, fn = item
                self._db.insert_line_crossing(
                    self._session_id, tid, ll, dir_, cl, cx, cy, fn
                )

            elif kind == "zone":
                _, tid, zl, et, cl, fn, dur = item
                self._db.insert_zone_event(
                    self._session_id, tid, zl, et, cl, fn, dur
                )

            elif kind == "occupancy":
                _, cp, cv, pp, pv, ap, av = item
                self._db.insert_occupancy_snapshot(
                    self._session_id, cp, cv, pp, pv, ap, av
                )

            elif kind == "vehicle_counts":
                _, bs, cars, moto, buses, trucks, bikes = item
                self._db.upsert_vehicle_counts(
                    self._session_id, bs, cars, moto, buses, trucks, bikes
                )

            elif kind == "health":
                _, cpu, ram, dev, fps = item
                self._db.insert_health_snapshot(
                    self._session_id, cpu, ram, dev, fps
                )

            elif kind == "error":
                _, sev, mod, msg, tb = item
                self._db.insert_error_event(self._session_id, sev, mod, msg, tb)

        if obj_batch:
            self._db.insert_tracked_objects_batch(self._session_id, obj_batch)
