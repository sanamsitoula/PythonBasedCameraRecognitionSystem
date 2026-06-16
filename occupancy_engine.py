"""
occupancy_engine.py – Real-time people and vehicle occupancy tracking.

Maintains:
  current_people    – people inside right now (based on entry/exit events)
  peak_people       – highest count seen since startup (or since last daily reset)
  avg_people        – rolling average over a configurable time window
  current_vehicles  – vehicles present right now
"""

import logging
from collections import deque
from datetime import datetime, date

log = logging.getLogger("analytics")


class OccupancyEngine:
    def __init__(
        self,
        average_window_seconds: int  = 300,
        reset_peak_daily:       bool = True,
        alert_threshold:        int  = 50,
        estimated_fps:          float = 25.0,
    ):
        self._avg_window     = average_window_seconds
        self._reset_daily    = reset_peak_daily
        self._alert_thresh   = alert_threshold

        window_size = max(1, int(average_window_seconds * estimated_fps))
        self._people_history:  deque = deque(maxlen=window_size)
        self._vehicle_history: deque = deque(maxlen=window_size)

        self._current_people   = 0
        self._current_vehicles = 0
        self._peak_people      = 0
        self._peak_vehicles    = 0
        self._total_in         = 0
        self._total_out        = 0
        self._reset_date       = date.today()

    # ─────────────────────────── entry / exit events ─────────────────────────

    def person_entered(self) -> None:
        self._daily_reset_if_needed()
        self._current_people = max(0, self._current_people + 1)
        self._total_in      += 1
        if self._current_people > self._peak_people:
            self._peak_people = self._current_people
            if self._current_people >= self._alert_thresh:
                log.warning("OCCUPANCY ALERT: %d people (threshold=%d)",
                            self._current_people, self._alert_thresh)

    def person_exited(self) -> None:
        self._daily_reset_if_needed()
        self._current_people = max(0, self._current_people - 1)
        self._total_out     += 1

    def vehicle_entered(self) -> None:
        self._current_vehicles = max(0, self._current_vehicles + 1)
        if self._current_vehicles > self._peak_vehicles:
            self._peak_vehicles = self._current_vehicles

    def vehicle_exited(self) -> None:
        self._current_vehicles = max(0, self._current_vehicles - 1)

    def tick(self) -> None:
        """Call once per frame to update rolling averages."""
        self._people_history.append(self._current_people)
        self._vehicle_history.append(self._current_vehicles)

    # ─────────────────────────── properties ──────────────────────────────────

    @property
    def current_people(self) -> int:
        return self._current_people

    @property
    def current_vehicles(self) -> int:
        return self._current_vehicles

    @property
    def peak_people(self) -> int:
        return self._peak_people

    @property
    def peak_vehicles(self) -> int:
        return self._peak_vehicles

    @property
    def avg_people(self) -> float:
        if not self._people_history:
            return 0.0
        return round(sum(self._people_history) / len(self._people_history), 1)

    @property
    def avg_vehicles(self) -> float:
        if not self._vehicle_history:
            return 0.0
        return round(sum(self._vehicle_history) / len(self._vehicle_history), 1)

    @property
    def total_in(self) -> int:
        return self._total_in

    @property
    def total_out(self) -> int:
        return self._total_out

    def snapshot(self) -> dict:
        return {
            "current_people":   self._current_people,
            "current_vehicles": self._current_vehicles,
            "peak_people":      self._peak_people,
            "peak_vehicles":    self._peak_vehicles,
            "avg_people":       self.avg_people,
            "avg_vehicles":     self.avg_vehicles,
        }

    # ─────────────────────────── internal ────────────────────────────────────

    def _daily_reset_if_needed(self) -> None:
        if not self._reset_daily:
            return
        today = date.today()
        if today != self._reset_date:
            self._peak_people   = self._current_people
            self._peak_vehicles = self._current_vehicles
            self._reset_date    = today
