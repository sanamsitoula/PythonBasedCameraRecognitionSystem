"""
visitor_manager.py
Manages unknown persons who are not recognised as employees.
Thread-safe, production-ready.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional
import threading
import logging

log = logging.getLogger("analytics")


@dataclass
class VisitorRecord:
    visitor_id: str                # VISITOR-0001
    track_camera_key: str          # "camera1:P-0001"
    first_seen: datetime
    last_seen: datetime
    current_zone: str
    current_camera_id: str
    movement_history: list = field(default_factory=list)
    # list of {"zone": str, "entry": datetime, "exit": Optional[datetime]}
    face_snapshot_path: str = ""


class VisitorManager:
    """
    Creates and tracks visitor records keyed by (camera_id, track_id) pairs.

    Visitor IDs are formatted as VISITOR-NNNN. The counter resets each session
    (on instantiation). A new day detected at get_or_create time also resets
    the counter so IDs remain meaningful per day.

    Thread-safety: a single Lock guards all mutable state.
    """

    def __init__(self) -> None:
        self._counter: int = 0
        self._counter_date: date = date.today()

        # "camera_id:track_id" → visitor_id
        self._track_map: dict[str, str] = {}
        # visitor_id → VisitorRecord
        self._records: dict[str, VisitorRecord] = {}
        # visitor_id → bool  (True while at least one track is active)
        self._active: set[str] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_key(self, track_id: str, camera_id: str) -> str:
        return f"{camera_id}:{track_id}"

    def _next_visitor_id(self) -> str:
        """Increment counter, reset on new day. Must be called under lock."""
        today = date.today()
        if today != self._counter_date:
            self._counter = 0
            self._counter_date = today
        self._counter += 1
        return f"VISITOR-{self._counter:04d}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create(self, track_id: str, camera_id: str) -> str:
        """
        Return the visitor_id for this (camera_id, track_id) combo.
        Creates a new VisitorRecord on first encounter.
        """
        key = self._make_key(track_id, camera_id)
        with self._lock:
            if key in self._track_map:
                return self._track_map[key]

            visitor_id = self._next_visitor_id()
            now = datetime.now()
            record = VisitorRecord(
                visitor_id=visitor_id,
                track_camera_key=key,
                first_seen=now,
                last_seen=now,
                current_zone="",
                current_camera_id=camera_id,
            )
            self._records[visitor_id] = record
            self._track_map[key] = visitor_id
            self._active.add(visitor_id)
            log.info(
                "New visitor created: %s (camera=%s track=%s)",
                visitor_id, camera_id, track_id,
            )
            return visitor_id

    def update_location(
        self,
        visitor_id: str,
        zone: str,
        camera_id: str,
        timestamp: datetime,
    ) -> None:
        """
        Update the visitor's current zone and camera.
        Opens a new movement_history entry if the zone changed.
        """
        with self._lock:
            record = self._records.get(visitor_id)
            if record is None:
                log.warning("update_location: unknown visitor_id %s", visitor_id)
                return

            record.last_seen = timestamp
            record.current_camera_id = camera_id

            if record.current_zone != zone:
                # Close the last open movement entry if any
                for entry in reversed(record.movement_history):
                    if entry.get("exit") is None and entry.get("zone") == record.current_zone:
                        entry["exit"] = timestamp
                        break
                # Open a new entry
                record.movement_history.append(
                    {"zone": zone, "entry": timestamp, "exit": None}
                )
                record.current_zone = zone
                log.debug("Visitor %s moved to zone '%s'", visitor_id, zone)

    def record_exit_zone(
        self, visitor_id: str, zone: str, exit_time: datetime
    ) -> None:
        """
        Close the open movement_history entry for the given zone.
        """
        with self._lock:
            record = self._records.get(visitor_id)
            if record is None:
                log.warning("record_exit_zone: unknown visitor_id %s", visitor_id)
                return

            for entry in reversed(record.movement_history):
                if entry.get("zone") == zone and entry.get("exit") is None:
                    entry["exit"] = exit_time
                    break

            record.last_seen = exit_time
            if record.current_zone == zone:
                record.current_zone = ""

    def set_snapshot(self, visitor_id: str, path: str) -> None:
        """Attach a face snapshot file path to a visitor record."""
        with self._lock:
            record = self._records.get(visitor_id)
            if record is None:
                log.warning("set_snapshot: unknown visitor_id %s", visitor_id)
                return
            record.face_snapshot_path = path

    def get_record(self, visitor_id: str) -> Optional[VisitorRecord]:
        """Return the VisitorRecord for visitor_id, or None."""
        with self._lock:
            return self._records.get(visitor_id)

    def get_all_active(self) -> list[VisitorRecord]:
        """Return all visitors that still have at least one active (open) track."""
        with self._lock:
            return [
                self._records[vid]
                for vid in self._active
                if vid in self._records
            ]

    def get_today_count(self) -> int:
        """Return the total number of unique visitors created today."""
        today = date.today()
        with self._lock:
            return sum(
                1
                for record in self._records.values()
                if record.first_seen.date() == today
            )

    def remove_track(self, track_id: str, camera_id: str) -> None:
        """
        Called when a camera track closes.
        Removes the track mapping. If no other tracks reference the same
        visitor_id, marks the visitor as inactive.
        """
        key = self._make_key(track_id, camera_id)
        with self._lock:
            visitor_id = self._track_map.pop(key, None)
            if visitor_id is None:
                return

            # Check whether any other tracks still reference this visitor
            still_active = any(vid == visitor_id for vid in self._track_map.values())
            if not still_active:
                self._active.discard(visitor_id)
                log.info(
                    "Visitor %s deactivated (track %s on %s closed)",
                    visitor_id, track_id, camera_id,
                )
