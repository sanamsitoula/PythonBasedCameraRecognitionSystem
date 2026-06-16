"""
attendance_engine.py
Tracks employee attendance automatically from camera events.
Thread-safe, production-ready.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional
import threading
import logging

log = logging.getLogger("analytics")


@dataclass
class AttendanceRecord:
    employee_id: str
    attendance_date: date
    first_entry: Optional[datetime] = None
    last_exit: Optional[datetime] = None
    working_duration_seconds: int = 0
    break_duration_seconds: int = 0
    status: str = "present"   # present / late / absent
    is_late: bool = False


class AttendanceEngine:
    """
    Records employee entries and exits from camera events.

    Thread-safety: a single Lock guards all mutable state.
    """

    def __init__(
        self,
        late_threshold: str = "09:15",
        work_start: str = "09:00",
        work_end: str = "18:00",
    ) -> None:
        self.late_threshold = late_threshold
        self.work_start = work_start
        self.work_end = work_end

        # employee_id → date → AttendanceRecord
        self._records: dict[str, dict[date, AttendanceRecord]] = {}
        # employees who have entered today but have not yet exited
        self._currently_inside: set[str] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_hhmm(hhmm: str) -> tuple[int, int]:
        """Parse 'HH:MM' into (hour, minute)."""
        parts = hhmm.split(":")
        return int(parts[0]), int(parts[1])

    def _is_late(self, entry_time: datetime) -> bool:
        th, tm = self._parse_hhmm(self.late_threshold)
        threshold = entry_time.replace(hour=th, minute=tm, second=0, microsecond=0)
        return entry_time > threshold

    def _get_or_create_record(
        self, employee_id: str, for_date: date
    ) -> AttendanceRecord:
        """Return existing record or create a new one. Must be called under lock."""
        emp_map = self._records.setdefault(employee_id, {})
        if for_date not in emp_map:
            emp_map[for_date] = AttendanceRecord(
                employee_id=employee_id,
                attendance_date=for_date,
                status="absent",
            )
        return emp_map[for_date]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_entry(self, employee_id: str, timestamp: datetime) -> AttendanceRecord:
        """
        Called when a camera recognises an employee entering.
        Sets first_entry if this is the first event today; marks is_late.
        """
        today = timestamp.date()
        with self._lock:
            record = self._get_or_create_record(employee_id, today)
            if record.first_entry is None:
                record.first_entry = timestamp
                record.is_late = self._is_late(timestamp)
                record.status = "late" if record.is_late else "present"
                log.info(
                    "Entry recorded: %s at %s (late=%s)",
                    employee_id,
                    timestamp,
                    record.is_late,
                )
            self._currently_inside.add(employee_id)
            return record

    def record_exit(self, employee_id: str, timestamp: datetime) -> AttendanceRecord:
        """
        Called when a camera recognises an employee exiting.
        Updates last_exit and refreshes working_duration_seconds.
        """
        today = timestamp.date()
        with self._lock:
            record = self._get_or_create_record(employee_id, today)
            record.last_exit = timestamp
            record.working_duration_seconds = self.calculate_working_hours(record)
            self._currently_inside.discard(employee_id)
            log.info("Exit recorded: %s at %s", employee_id, timestamp)
            return record

    def get_record(
        self, employee_id: str, for_date: Optional[date] = None
    ) -> Optional[AttendanceRecord]:
        """Return the AttendanceRecord for the given employee and date (default today)."""
        target = for_date if for_date is not None else date.today()
        with self._lock:
            return self._records.get(employee_id, {}).get(target)

    def get_today_summary(self) -> dict:
        """
        Return a summary dict for today:
        {"present": int, "late": int, "absent": int, "records": list[AttendanceRecord]}
        """
        today = date.today()
        with self._lock:
            records_today = [
                emp_map[today]
                for emp_map in self._records.values()
                if today in emp_map
            ]
        present = sum(1 for r in records_today if r.status == "present")
        late = sum(1 for r in records_today if r.status == "late")
        absent = sum(1 for r in records_today if r.status == "absent")
        return {
            "present": present,
            "late": late,
            "absent": absent,
            "records": list(records_today),
        }

    def calculate_working_hours(self, record: AttendanceRecord) -> int:
        """
        Returns net working seconds: (last_exit - first_entry) - break_duration_seconds.
        Returns 0 if either timestamp is missing.
        """
        if record.first_entry is None or record.last_exit is None:
            return 0
        total = int((record.last_exit - record.first_entry).total_seconds())
        net = max(0, total - record.break_duration_seconds)
        return net

    def get_currently_present(self) -> list[str]:
        """Return employee_ids that have entered today but not yet exited."""
        with self._lock:
            return list(self._currently_inside)

    def mark_absent(self, employee_ids: list[str], for_date: date) -> None:
        """
        Mark the given employees as absent for for_date.
        Typically called at end-of-day for employees never seen.
        """
        with self._lock:
            for emp_id in employee_ids:
                record = self._get_or_create_record(emp_id, for_date)
                if record.first_entry is None:
                    record.status = "absent"
                    log.info("Marked absent: %s on %s", emp_id, for_date)
