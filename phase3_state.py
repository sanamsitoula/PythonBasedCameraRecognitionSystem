"""
phase3_state.py – Central thread-safe state bus for Phase 3 analytics.

Extends the pattern established in analytics_state.py (Phase 2) but adds
identity-aware fields: employee lists, visitor lists, department summaries,
attendance counters, canteen stats, and recent alert strings.

Usage:
    from phase3_state import get_state, update, append_log, append_alert
"""

import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Sub-dataclasses
# ---------------------------------------------------------------------------
@dataclass
class EmployeeSummary:
    employee_id:     str
    employee_name:   str
    department:      str
    current_zone:    str
    current_camera_id: str
    entry_time:      datetime
    gender:          str          # "Male" | "Female" | "Unknown"


@dataclass
class VisitorSummaryP3:
    visitor_id:       str
    current_zone:     str
    current_camera_id: str
    first_seen:       datetime
    gender:           str          # "Male" | "Female" | "Unknown"


@dataclass
class DeptSummaryEntry:
    department: str
    present:    int
    in_office:  int
    in_canteen: int


# ---------------------------------------------------------------------------
# Main state dataclass
# ---------------------------------------------------------------------------
@dataclass
class Phase3State:
    # ── detection (mirrored from Phase 2 base) ────────────────────────────
    actual_fps:   float = 0.0
    frame_number: int   = 0
    cpu_pct:      float = 0.0
    ram_gb:       float = 0.0

    # ── people counts ─────────────────────────────────────────────────────
    employees_present: int = 0
    visitors_present:  int = 0
    male_employees:    int = 0
    female_employees:  int = 0
    male_visitors:     int = 0
    female_visitors:   int = 0

    # ── attendance today ──────────────────────────────────────────────────
    present_today: int = 0
    absent_today:  int = 0
    late_today:    int = 0

    # ── canteen ───────────────────────────────────────────────────────────
    canteen_current:     int = 0
    canteen_today_visits: int = 0

    # ── active lists ──────────────────────────────────────────────────────
    active_employees:    list = field(default_factory=list)   # List[EmployeeSummary]
    active_visitors:     list = field(default_factory=list)   # List[VisitorSummaryP3]
    department_summaries: list = field(default_factory=list)  # List[DeptSummaryEntry]

    # ── alerts ────────────────────────────────────────────────────────────
    recent_alerts: list = field(default_factory=list)         # last 5 alert message strings

    # ── system ────────────────────────────────────────────────────────────
    start_time:   datetime = field(default_factory=datetime.now)
    db_available: bool     = False
    last_error:   str      = ""
    error_count:  int      = 0
    log_tail:     list     = field(default_factory=list)      # last 10 log lines


# ---------------------------------------------------------------------------
# Module-level singleton + lock
# ---------------------------------------------------------------------------
_STATE3 = Phase3State()
_LOCK3  = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_state() -> Phase3State:
    """Return a shallow copy of the current state (safe for reading)."""
    with _LOCK3:
        return copy.copy(_STATE3)


def update(**kwargs) -> None:
    """
    Atomically update one or more fields on the global Phase3State.

    Example::

        update(employees_present=5, canteen_current=12)
    """
    with _LOCK3:
        for key, value in kwargs.items():
            if hasattr(_STATE3, key):
                setattr(_STATE3, key, value)
            else:
                # Guard against typos; use a warning rather than silently ignoring
                import logging as _log
                _log.getLogger("analytics").warning(
                    "phase3_state.update: unknown field '%s' ignored", key
                )


def append_log(msg: str) -> None:
    """
    Append a timestamped message to log_tail (max 10 entries).
    Oldest entry is dropped when the list is full.
    """
    from datetime import datetime as _dt
    with _LOCK3:
        _STATE3.log_tail.append(f"[{_dt.now().strftime('%H:%M:%S')}] {msg}")
        if len(_STATE3.log_tail) > 10:
            _STATE3.log_tail.pop(0)


def append_alert(msg: str) -> None:
    """
    Append an alert message string to recent_alerts (max 5 entries).
    Oldest entry is dropped when the list is full.
    """
    with _LOCK3:
        _STATE3.recent_alerts.append(msg)
        if len(_STATE3.recent_alerts) > 5:
            _STATE3.recent_alerts.pop(0)
