"""
zone_manager.py – Configurable polygon zone analytics.

Zones are convex or concave polygons defined by (x,y) vertex lists.
Uses the ray-casting algorithm for point-in-polygon checks — no external
geometry library required.

Tracks: zone entry time, zone exit time, time spent per zone, visit count.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

log = logging.getLogger("analytics")


@dataclass
class ZoneConfig:
    zone_id:    str
    label:      str
    coords:     list    # [[x,y], [x,y], …] at least 3 points


@dataclass
class ZoneEvent:
    track_id:    str
    zone_id:     str
    zone_label:  str
    event_type:  str           # "enter" or "exit"
    occurred_at: datetime
    class_name:  str
    frame_number: int
    duration_seconds: Optional[float] = None


def _point_in_polygon(px: int, py: int, polygon: list) -> bool:
    n, inside = len(polygon), False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi + 1e-10) + xi):
            inside = not inside
        j = i
    return inside


class ZoneManager:
    def __init__(self, zone_configs: list):
        """zone_configs: List[ZoneConfig]"""
        self._zones = zone_configs
        # per-track state
        self._current_zone:  dict[str, Optional[str]] = {}   # track_id → zone_id | None
        self._entry_times:   dict[str, dict]           = {}   # track_id → {zone_id: datetime}
        self._visit_counts:  dict[str, dict]           = {}   # track_id → {zone_id: int}
        self._path_history:  dict[str, list]           = {}   # track_id → [zone_label, …]

        log.info("ZoneManager initialised with %d zone(s).", len(self._zones))

    def update(
        self,
        track_id:     str,
        class_name:   str,
        center:       tuple,
        frame_number: int,
    ) -> list:
        """Returns List[ZoneEvent] for any enter/exit transitions this frame."""
        cx, cy = center
        if track_id not in self._current_zone:
            self._current_zone[track_id]  = None
            self._entry_times[track_id]   = {}
            self._visit_counts[track_id]  = {}
            self._path_history[track_id]  = []

        prev_zone_id = self._current_zone[track_id]
        new_zone_id  = self._find_zone(cx, cy)

        if new_zone_id == prev_zone_id:
            return []

        events: list[ZoneEvent] = []
        now = datetime.now()

        # Exit old zone
        if prev_zone_id is not None:
            old_zone = self._zone_by_id(prev_zone_id)
            entry_ts = self._entry_times[track_id].get(prev_zone_id)
            duration = (now - entry_ts).total_seconds() if entry_ts else None
            events.append(ZoneEvent(
                track_id         = track_id,
                zone_id          = prev_zone_id,
                zone_label       = old_zone.label if old_zone else prev_zone_id,
                event_type       = "exit",
                occurred_at      = now,
                class_name       = class_name,
                frame_number     = frame_number,
                duration_seconds = duration,
            ))
            label = old_zone.label if old_zone else prev_zone_id
            log.info("ZONE EXIT  | %s → %s (%.1fs)", track_id, label, duration or 0)

        # Enter new zone
        if new_zone_id is not None:
            new_zone = self._zone_by_id(new_zone_id)
            self._entry_times[track_id][new_zone_id] = now
            self._visit_counts[track_id][new_zone_id] = \
                self._visit_counts[track_id].get(new_zone_id, 0) + 1

            zone_label = new_zone.label if new_zone else new_zone_id
            events.append(ZoneEvent(
                track_id     = track_id,
                zone_id      = new_zone_id,
                zone_label   = zone_label,
                event_type   = "enter",
                occurred_at  = now,
                class_name   = class_name,
                frame_number = frame_number,
            ))
            path = self._path_history[track_id]
            if not path or path[-1] != zone_label:
                path.append(zone_label)
            log.info("ZONE ENTER | %s → %s", track_id, zone_label)

        self._current_zone[track_id] = new_zone_id
        return events

    def get_current_zone_label(self, track_id: str) -> str:
        zone_id = self._current_zone.get(track_id)
        if zone_id is None:
            return "–"
        zone = self._zone_by_id(zone_id)
        return zone.label if zone else zone_id

    def get_path(self, track_id: str) -> list:
        return list(self._path_history.get(track_id, []))

    def remove_track(self, track_id: str) -> None:
        self._current_zone.pop(track_id, None)
        self._entry_times.pop(track_id, None)
        self._visit_counts.pop(track_id, None)
        self._path_history.pop(track_id, None)

    def _find_zone(self, cx: int, cy: int) -> Optional[str]:
        for z in self._zones:
            if _point_in_polygon(cx, cy, z.coords):
                return z.zone_id
        return None

    def _zone_by_id(self, zone_id: str) -> Optional[ZoneConfig]:
        for z in self._zones:
            if z.zone_id == zone_id:
                return z
        return None
