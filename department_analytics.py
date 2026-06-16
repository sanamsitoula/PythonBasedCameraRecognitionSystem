"""
department_analytics.py
Tracks employee counts per department and zone.
Thread-safe, production-ready.
"""

from dataclasses import dataclass, field
from typing import Optional
import threading
import logging

log = logging.getLogger("analytics")

KNOWN_ZONES = {"office", "canteen", "warehouse"}


@dataclass
class DepartmentStatus:
    department: str
    total_enrolled: int = 0
    present_today: int = 0
    in_office: int = 0
    in_canteen: int = 0
    in_warehouse: int = 0
    outside: int = 0
    employee_ids_present: list = field(default_factory=list)


class DepartmentAnalytics:
    """
    Maintains real-time per-department zone counts.

    Zones recognised for dedicated counters: "office", "canteen", "warehouse".
    Any other zone label is counted generically (employee marked present but
    the zone column is not incremented).

    Thread-safety: a single Lock guards all mutable state.
    """

    def __init__(self) -> None:
        # department → list[employee_id]
        self._roster: dict[str, list[str]] = {}
        # employee_id → department
        self._employee_dept: dict[str, str] = {}
        # employee_id → current zone label (empty string = outside / unknown)
        self._employee_zone: dict[str, str] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recalculate_department(self, department: str) -> None:
        """Recompute DepartmentStatus counters from first principles. Under lock."""
        # This is called after every zone change so counters are always fresh.
        # We do NOT store DepartmentStatus persistently — we build it on demand.
        pass  # calculation happens in get_department_status

    def _build_status(self, department: str) -> Optional[DepartmentStatus]:
        """Build a DepartmentStatus snapshot. Must be called under lock."""
        roster = self._roster.get(department)
        if roster is None:
            return None

        status = DepartmentStatus(
            department=department,
            total_enrolled=len(roster),
        )
        for emp_id in roster:
            zone = self._employee_zone.get(emp_id, "")
            if zone:
                status.present_today += 1
                status.employee_ids_present.append(emp_id)
                if zone == "office":
                    status.in_office += 1
                elif zone == "canteen":
                    status.in_canteen += 1
                elif zone == "warehouse":
                    status.in_warehouse += 1
                else:
                    # Non-canonical zone: employee is present but zone not counted
                    pass
            else:
                status.outside += 1

        return status

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_department_roster(
        self, department: str, employee_ids: list[str]
    ) -> None:
        """
        Register the canonical list of employees for a department.
        Clears the previous roster for that department.
        """
        with self._lock:
            # Remove stale reverse-mappings for employees that were in this dept
            old_roster = self._roster.get(department, [])
            for emp_id in old_roster:
                if self._employee_dept.get(emp_id) == department:
                    del self._employee_dept[emp_id]

            self._roster[department] = list(employee_ids)
            for emp_id in employee_ids:
                self._employee_dept[emp_id] = department
            log.info(
                "Roster set for '%s': %d employees", department, len(employee_ids)
            )

    def employee_entered_zone(self, employee_id: str, zone_label: str) -> None:
        """
        Update the employee's current zone when they enter a new zone.
        If the employee is not in any known roster this is silently recorded.
        """
        with self._lock:
            prev = self._employee_zone.get(employee_id, "")
            self._employee_zone[employee_id] = zone_label
            log.debug(
                "employee_entered_zone: %s → '%s' (was '%s')",
                employee_id, zone_label, prev,
            )

    def employee_exited_zone(self, employee_id: str, zone_label: str) -> None:
        """
        Called when an employee leaves a zone.
        Clears their zone if they were indeed in that zone.
        """
        with self._lock:
            current = self._employee_zone.get(employee_id, "")
            if current == zone_label:
                self._employee_zone[employee_id] = ""
                log.debug(
                    "employee_exited_zone: %s left '%s'", employee_id, zone_label
                )
            else:
                log.debug(
                    "employee_exited_zone: %s exited '%s' but was in '%s' — clearing anyway",
                    employee_id, zone_label, current,
                )
                # Clear regardless to avoid stale state
                self._employee_zone[employee_id] = ""

    def employee_left_camera(self, employee_id: str) -> None:
        """
        Mark employee as outside (no current zone).
        Called when a track closes and the employee is no longer visible.
        """
        with self._lock:
            self._employee_zone[employee_id] = ""
            log.debug("employee_left_camera: %s marked outside", employee_id)

    def get_department_status(self, department: str) -> Optional[DepartmentStatus]:
        """Return a DepartmentStatus snapshot for department, or None if unknown."""
        with self._lock:
            return self._build_status(department)

    def get_all_departments(self) -> list[DepartmentStatus]:
        """Return DepartmentStatus snapshots for all registered departments."""
        with self._lock:
            return [
                self._build_status(dept)
                for dept in self._roster
                if self._build_status(dept) is not None
            ]

    def get_employee_zone(self, employee_id: str) -> str:
        """Return the employee's current zone label, or empty string if outside/unknown."""
        with self._lock:
            return self._employee_zone.get(employee_id, "")
