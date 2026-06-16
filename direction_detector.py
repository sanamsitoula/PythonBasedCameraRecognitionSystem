"""
direction_detector.py – Movement direction analysis per track.

Uses an 8-frame rolling history of centroids.  Computes the vector from
the median of the oldest 4 positions to the median of the newest 4.
This is more robust to jitter than using just the first and last point.

Returns one of:  LEFT → RIGHT | RIGHT → LEFT | TOP → BOTTOM | BOTTOM → TOP | STATIONARY
"""

import logging
import statistics
from collections import deque
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

HISTORY_DEPTH = 20    # frames kept in rolling window
MIN_SAMPLES   = 8     # minimum frames before emitting a direction
MIN_MOVEMENT  = 12    # pixels of displacement before declaring non-stationary


@dataclass
class DirectionEvent:
    track_id:    str
    direction:   str    # e.g. "LEFT → RIGHT"
    delta_x:     float
    delta_y:     float


class DirectionDetector:
    def __init__(
        self,
        history_depth: int = HISTORY_DEPTH,
        min_samples:   int = MIN_SAMPLES,
        min_movement:  int = MIN_MOVEMENT,
    ):
        self._depth       = history_depth
        self._min_samples = min_samples
        self._min_move    = min_movement
        self._histories:  dict[str, deque] = {}

    def update(self, track_id: str, center: tuple) -> Optional[DirectionEvent]:
        """Feed one centroid; returns a DirectionEvent once history is sufficient."""
        if track_id not in self._histories:
            self._histories[track_id] = deque(maxlen=self._depth)
        self._histories[track_id].append(center)

        h = self._histories[track_id]
        if len(h) < self._min_samples:
            return None

        return self._compute(track_id, list(h))

    def get_direction(self, track_id: str) -> str:
        h = self._histories.get(track_id)
        if not h or len(h) < self._min_samples:
            return "–"
        event = self._compute(track_id, list(h))
        return event.direction if event else "–"

    def _compute(self, track_id: str, h: list) -> Optional[DirectionEvent]:
        half    = max(1, len(h) // 2)
        older   = h[:half]
        newer   = h[half:]

        median_x = lambda pts: statistics.median(p[0] for p in pts)
        median_y = lambda pts: statistics.median(p[1] for p in pts)

        dx = median_x(newer) - median_x(older)
        dy = median_y(newer) - median_y(older)

        if abs(dx) < self._min_move and abs(dy) < self._min_move:
            direction = "STATIONARY"
        elif abs(dx) >= abs(dy):
            direction = "LEFT → RIGHT" if dx > 0 else "RIGHT → LEFT"
        else:
            direction = "TOP → BOTTOM" if dy > 0 else "BOTTOM → TOP"

        return DirectionEvent(
            track_id  = track_id,
            direction = direction,
            delta_x   = round(dx, 1),
            delta_y   = round(dy, 1),
        )

    def remove(self, track_id: str) -> None:
        self._histories.pop(track_id, None)
