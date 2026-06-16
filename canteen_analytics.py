"""
canteen_analytics.py
Specialised analytics for the canteen zone.
Thread-safe, production-ready.
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional
import threading
import uuid
import logging

log = logging.getLogger("analytics")


@dataclass
class CanteenVisit:
    visit_id: str
    person_id: str
    person_type: str          # "employee" | "visitor"
    entry_time: datetime
    exit_time: Optional[datetime]
    duration_seconds: int
    meal_period: str          # "breakfast" | "lunch" | "dinner" | "other"


class CanteenAnalytics:
    """
    Tracks canteen occupancy, visit duration, and meal-period breakdowns.

    Thread-safety: a single Lock guards all mutable state.
    """

    BREAKFAST = (7, 10)
    LUNCH = (12, 15)
    DINNER = (19, 22)

    def __init__(self) -> None:
        # person_id → open CanteenVisit (currently inside)
        self._open_visits: dict[str, CanteenVisit] = {}
        # completed visits keyed by date
        self._completed_visits: dict[date, list[CanteenVisit]] = {}
        # occupancy snapshots: list of (datetime, occupant_count) for peak detection
        self._occupancy_log: list[tuple[datetime, int]] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def determine_meal_period(self, timestamp: datetime) -> str:
        """Classify a timestamp into a meal period string."""
        h = timestamp.hour
        if self.BREAKFAST[0] <= h < self.BREAKFAST[1]:
            return "breakfast"
        if self.LUNCH[0] <= h < self.LUNCH[1]:
            return "lunch"
        if self.DINNER[0] <= h < self.DINNER[1]:
            return "dinner"
        return "other"

    def _log_occupancy(self, timestamp: datetime) -> None:
        """Record the current occupant count. Must be called under lock."""
        self._occupancy_log.append((timestamp, len(self._open_visits)))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def person_entered(
        self, person_id: str, person_type: str, timestamp: datetime
    ) -> CanteenVisit:
        """
        Record a person entering the canteen.
        If this person already has an open visit, return the existing one.
        """
        with self._lock:
            if person_id in self._open_visits:
                log.debug("person_entered called again for %s (already inside)", person_id)
                return self._open_visits[person_id]

            visit = CanteenVisit(
                visit_id=str(uuid.uuid4()),
                person_id=person_id,
                person_type=person_type,
                entry_time=timestamp,
                exit_time=None,
                duration_seconds=0,
                meal_period=self.determine_meal_period(timestamp),
            )
            self._open_visits[person_id] = visit
            self._log_occupancy(timestamp)
            log.info("Canteen entry: %s (%s) at %s", person_id, person_type, timestamp)
            return visit

    def person_exited(
        self, person_id: str, timestamp: datetime
    ) -> Optional[CanteenVisit]:
        """
        Complete the open visit for person_id.
        Returns the completed visit, or None if no open visit exists.
        """
        with self._lock:
            visit = self._open_visits.pop(person_id, None)
            if visit is None:
                log.warning("person_exited: no open visit for %s", person_id)
                return None

            visit.exit_time = timestamp
            visit.duration_seconds = max(
                0, int((timestamp - visit.entry_time).total_seconds())
            )
            visit_date = visit.entry_time.date()
            self._completed_visits.setdefault(visit_date, []).append(visit)
            self._log_occupancy(timestamp)
            log.info(
                "Canteen exit: %s after %ds", person_id, visit.duration_seconds
            )
            return visit

    def current_count(self) -> int:
        """Return the number of people currently inside the canteen."""
        with self._lock:
            return len(self._open_visits)

    def today_visits(self) -> list[CanteenVisit]:
        """Return all completed visits for today."""
        today = date.today()
        with self._lock:
            return list(self._completed_visits.get(today, []))

    def get_visit(self, person_id: str) -> Optional[CanteenVisit]:
        """Return the currently open visit for person_id, or None."""
        with self._lock:
            return self._open_visits.get(person_id)

    def peak_hour(self) -> tuple[int, int]:
        """
        Return (hour, count) for the hour of the day with the highest
        simultaneous occupancy recorded in the occupancy log.
        """
        with self._lock:
            if not self._occupancy_log:
                return (0, 0)
            # bucket counts by hour, keep the maximum per hour
            hourly_max: dict[int, int] = {}
            for ts, count in self._occupancy_log:
                h = ts.hour
                if count > hourly_max.get(h, 0):
                    hourly_max[h] = count
            best_hour = max(hourly_max, key=lambda h: hourly_max[h])
            return (best_hour, hourly_max[best_hour])

    def daily_report(self, for_date: Optional[date] = None) -> dict:
        """
        Return a daily summary dict:
        {
            "total_visits": int,
            "employee_visits": int,
            "visitor_visits": int,
            "avg_duration_seconds": int,
            "peak_count": int,
            "peak_time": str,  # "HH:00"
        }
        """
        target = for_date if for_date is not None else date.today()
        with self._lock:
            visits = list(self._completed_visits.get(target, []))
            # also include still-open visits if querying today
            if target == date.today():
                visits = visits + list(self._open_visits.values())

        total = len(visits)
        employee_visits = sum(1 for v in visits if v.person_type == "employee")
        visitor_visits = sum(1 for v in visits if v.person_type == "visitor")
        avg_duration = (
            int(sum(v.duration_seconds for v in visits) / total) if total else 0
        )

        # peak occupancy within target date from occupancy log
        with self._lock:
            day_log = [
                (ts, cnt)
                for ts, cnt in self._occupancy_log
                if ts.date() == target
            ]
        peak_count = max((cnt for _, cnt in day_log), default=0)
        peak_ts = next(
            (ts for ts, cnt in day_log if cnt == peak_count),
            None,
        )
        peak_time = f"{peak_ts.hour:02d}:00" if peak_ts else "N/A"

        return {
            "total_visits": total,
            "employee_visits": employee_visits,
            "visitor_visits": visitor_visits,
            "avg_duration_seconds": avg_duration,
            "peak_count": peak_count,
            "peak_time": peak_time,
        }
