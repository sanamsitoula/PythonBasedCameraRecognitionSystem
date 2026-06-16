"""
vehicle_analytics.py – Per-vehicle-type counting and hourly aggregation.

Tracks:
  * Cumulative count per type (cars, motorcycles, buses, trucks, bicycles)
  * Currently active vehicle tracks
  * Hourly bucket counts (for DB flush when the hour rolls over)
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

log = logging.getLogger("vehicle")

VEHICLE_TYPES = ("bicycle", "car", "motorcycle", "bus", "truck")


@dataclass
class VehicleRecord:
    track_id:     str
    vehicle_type: str
    first_seen:   datetime
    last_seen:    datetime
    entry_time:   Optional[datetime] = None
    exit_time:    Optional[datetime] = None
    direction:    Optional[str]      = None
    is_active:    bool               = True


@dataclass
class HourlyBucket:
    hour_start:   datetime
    counts:       dict = field(default_factory=lambda: {t: 0 for t in VEHICLE_TYPES})


class VehicleAnalytics:
    def __init__(self) -> None:
        self._records:  dict[str, VehicleRecord] = {}
        self._active:   set[str]                 = set()
        self._cumulative: dict[str, int]         = defaultdict(int)

        now = datetime.now()
        self._current_bucket = HourlyBucket(
            hour_start = now.replace(minute=0, second=0, microsecond=0)
        )
        self._closed_buckets: list[HourlyBucket] = []

    # ─────────────────────────── public API ──────────────────────────────────

    def update(self, track_id: str, vehicle_type: str, timestamp: datetime) -> VehicleRecord:
        """Call once per frame per vehicle track. Returns the VehicleRecord."""
        if track_id not in self._records:
            self._records[track_id] = VehicleRecord(
                track_id     = track_id,
                vehicle_type = vehicle_type,
                first_seen   = timestamp,
                last_seen    = timestamp,
            )
            self._active.add(track_id)
            self._cumulative[vehicle_type] += 1
            self._bump_bucket(vehicle_type, timestamp)
            log.info("NEW VEHICLE | %s | type=%s", track_id, vehicle_type)
        else:
            self._records[track_id].last_seen = timestamp
        return self._records[track_id]

    def set_direction(self, track_id: str, direction: str) -> None:
        if track_id in self._records:
            self._records[track_id].direction = direction

    def set_entry(self, track_id: str, entry_time: datetime) -> None:
        if track_id in self._records:
            self._records[track_id].entry_time = entry_time

    def set_exit(self, track_id: str, exit_time: datetime) -> None:
        if track_id in self._records:
            rec           = self._records[track_id]
            rec.exit_time = exit_time
            rec.is_active = False
            self._active.discard(track_id)
            log.info("CLOSED VEHICLE | %s | type=%s", track_id, rec.vehicle_type)

    def close_track(self, track_id: str, exit_time: Optional[datetime] = None) -> None:
        self.set_exit(track_id, exit_time or datetime.now())

    def get_active_counts(self) -> dict:
        counts: dict[str, int] = {t: 0 for t in VEHICLE_TYPES}
        for tid in self._active:
            rec = self._records.get(tid)
            if rec:
                counts[rec.vehicle_type] = counts.get(rec.vehicle_type, 0) + 1
        return counts

    def get_cumulative_counts(self) -> dict:
        return dict(self._cumulative)

    def get_record(self, track_id: str) -> Optional[VehicleRecord]:
        return self._records.get(track_id)

    @property
    def active_count(self) -> int:
        return len(self._active)

    def take_closed_buckets(self) -> list:
        """Return and clear any hourly buckets that have completed."""
        buckets = list(self._closed_buckets)
        self._closed_buckets.clear()
        return buckets

    # ─────────────────────────── internal ────────────────────────────────────

    def _bump_bucket(self, vehicle_type: str, now: datetime) -> None:
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        if hour_start != self._current_bucket.hour_start:
            self._closed_buckets.append(self._current_bucket)
            self._current_bucket = HourlyBucket(hour_start=hour_start)
        self._current_bucket.counts[vehicle_type] = \
            self._current_bucket.counts.get(vehicle_type, 0) + 1
