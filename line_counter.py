"""
line_counter.py – Virtual counting line for entry / exit detection.

Each line is defined by two endpoints (x1,y1) and (x2,y2).
When a track's centroid path crosses the line, a CrossingEvent is emitted.

Crossing detection uses a 2D line-segment intersection test so diagonal
virtual lines work correctly.  A track is counted at most once per crossing
(it must leave the line area before it can cross again).
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

log = logging.getLogger("analytics")


@dataclass
class LineConfig:
    label:           str
    p1:              tuple   # (x1, y1)
    p2:              tuple   # (x2, y2)
    entry_direction: str     # "TOP_TO_BOTTOM" | "BOTTOM_TO_TOP" | "LEFT_TO_RIGHT" | "RIGHT_TO_LEFT"


@dataclass
class CrossingEvent:
    track_id:     str
    class_name:   str
    line_label:   str
    direction:    str    # "entry" or "exit"
    crossed_at:   datetime
    centroid_x:   int
    centroid_y:   int
    frame_number: int


def _segments_intersect(p1, p2, p3, p4) -> bool:
    """Return True if segment p1-p2 intersects segment p3-p4."""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def _which_side(point: tuple, line_p1: tuple, line_p2: tuple) -> int:
    """
    Returns +1 or -1 depending on which side of the directed line (p1→p2)
    the point lies.  Used to determine entry vs exit direction.
    """
    val = (line_p2[0] - line_p1[0]) * (point[1] - line_p1[1]) \
        - (line_p2[1] - line_p1[1]) * (point[0] - line_p1[0])
    return 1 if val >= 0 else -1


class LineCounter:
    def __init__(self, line_configs: list):
        """
        line_configs: List[LineConfig]
        """
        self._lines = line_configs
        # per-line, per-track: last known side
        self._prev_side:  dict[str, dict[str, int]] = {lc.label: {} for lc in self._lines}
        # prevent double-counting: track_id → set of line labels already counted
        self._counted:    dict[str, set] = {}

        self._total_entries: dict[str, int] = {lc.label: 0 for lc in self._lines}
        self._total_exits:   dict[str, int] = {lc.label: 0 for lc in self._lines}

        log.info("LineCounter initialised with %d line(s).", len(self._lines))

    def update(
        self,
        track_id:     str,
        class_name:   str,
        center:       tuple,
        prev_center:  Optional[tuple],
        frame_number: int,
    ) -> list:
        """Returns list of CrossingEvent for any lines crossed this frame."""
        if prev_center is None:
            for lc in self._lines:
                self._prev_side[lc.label][track_id] = _which_side(center, lc.p1, lc.p2)
            return []

        events: list[CrossingEvent] = []
        cx, cy = center

        for lc in self._lines:
            if _segments_intersect(prev_center, center, lc.p1, lc.p2):
                if track_id not in self._counted:
                    self._counted[track_id] = set()
                if lc.label in self._counted[track_id]:
                    continue    # already counted for this crossing session

                self._counted[track_id].add(lc.label)

                # Determine entry vs exit from movement vector
                dy = cy - prev_center[1]
                dx = cx - prev_center[0]

                if lc.entry_direction == "TOP_TO_BOTTOM":
                    direction = "entry" if dy > 0 else "exit"
                elif lc.entry_direction == "BOTTOM_TO_TOP":
                    direction = "entry" if dy < 0 else "exit"
                elif lc.entry_direction == "LEFT_TO_RIGHT":
                    direction = "entry" if dx > 0 else "exit"
                else:  # RIGHT_TO_LEFT
                    direction = "entry" if dx < 0 else "exit"

                if direction == "entry":
                    self._total_entries[lc.label] += 1
                else:
                    self._total_exits[lc.label] += 1

                events.append(CrossingEvent(
                    track_id     = track_id,
                    class_name   = class_name,
                    line_label   = lc.label,
                    direction    = direction,
                    crossed_at   = datetime.now(),
                    centroid_x   = cx,
                    centroid_y   = cy,
                    frame_number = frame_number,
                ))
                log.info(
                    "CROSSING | %s | line=%s | %s | frame=%d",
                    track_id, lc.label, direction.upper(), frame_number,
                )

        # reset counted set when track moves away from any line it has crossed
        # (simple heuristic: allow re-count after 60 frames)
        if track_id in self._counted and frame_number % 60 == 0:
            self._counted[track_id].clear()

        return events

    def remove_track(self, track_id: str) -> None:
        for lc in self._lines:
            self._prev_side[lc.label].pop(track_id, None)
        self._counted.pop(track_id, None)

    def totals(self) -> dict:
        return {
            "entries": sum(self._total_entries.values()),
            "exits":   sum(self._total_exits.values()),
            "by_line": {
                lc.label: {
                    "entries": self._total_entries[lc.label],
                    "exits":   self._total_exits[lc.label],
                }
                for lc in self._lines
            },
        }
