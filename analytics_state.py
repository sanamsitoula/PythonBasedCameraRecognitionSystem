"""
analytics_state.py – Central live-state dataclass for Phase 2.

All analytics modules write here; the dashboard reads from here.
Uses a threading.Lock so any thread can safely update any field.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TrackedPersonSummary:
    track_id:   str
    gender:     str = "Unknown"
    direction:  str = "–"
    zone:       str = "–"
    first_seen: Optional[datetime] = None


@dataclass
class TrackedVehicleSummary:
    track_id:     str
    vehicle_type: str
    direction:    str = "–"
    first_seen:   Optional[datetime] = None


@dataclass
class AnalyticsState:
    # ── detection counts ─────────────────────────────────────────────
    people_count:      int = 0
    car_count:         int = 0
    motorcycle_count:  int = 0
    bus_count:         int = 0
    truck_count:       int = 0
    bicycle_count:     int = 0

    # ── gender breakdown ─────────────────────────────────────────────
    gender_male:       int = 0
    gender_female:     int = 0
    gender_unknown:    int = 0

    # ── entry / exit ─────────────────────────────────────────────────
    total_entries:     int = 0
    total_exits:       int = 0

    # ── occupancy ────────────────────────────────────────────────────
    current_occupancy: int = 0
    peak_occupancy:    int = 0
    avg_occupancy:     float = 0.0

    # ── active tracks ────────────────────────────────────────────────
    active_persons:   list = field(default_factory=list)   # List[TrackedPersonSummary]
    active_vehicles:  list = field(default_factory=list)   # List[TrackedVehicleSummary]

    # ── stream ───────────────────────────────────────────────────────
    actual_fps:        float = 0.0
    frame_number:      int   = 0

    # ── system ───────────────────────────────────────────────────────
    cpu_pct:           float = 0.0
    ram_gb:            float = 0.0
    device_label:      str   = "CPU"

    # ── AI insight ───────────────────────────────────────────────────
    ai_text:           str = "Awaiting first analysis…"
    ai_timestamp:      str = "–"

    # ── operational ──────────────────────────────────────────────────
    start_time:        datetime = field(default_factory=datetime.now)
    db_available:      bool = False
    log_tail:          list = field(default_factory=list)   # last 8 messages
    last_error:        str = ""
    error_count:       int = 0


# ── module-level singleton + lock ────────────────────────────────────────────

_STATE = AnalyticsState()
_LOCK  = threading.Lock()


def get_state() -> AnalyticsState:
    """Return a shallow copy of the current state (safe to read without the lock)."""
    with _LOCK:
        import copy
        return copy.copy(_STATE)


def update(**kwargs) -> None:
    """Update one or more fields atomically."""
    with _LOCK:
        for k, v in kwargs.items():
            setattr(_STATE, k, v)


def append_log(msg: str) -> None:
    from datetime import datetime as _dt
    with _LOCK:
        _STATE.log_tail.append(f"[{_dt.now().strftime('%H:%M:%S')}] {msg}")
        if len(_STATE.log_tail) > 8:
            _STATE.log_tail.pop(0)
