"""
smart_alerts.py – Rule-based alert engine for CCTV Phase 3.

Fires alerts for: restricted zone violations, after-hours presence,
loitering, crowd density, and unknown persons in restricted zones.

De-duplication: the same (person_id, alert_type, zone_id) tuple will not
fire again within 5 minutes of its last occurrence.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import threading
import logging
import uuid

log = logging.getLogger("analytics")


# ---------------------------------------------------------------------------
# Alert dataclass
# ---------------------------------------------------------------------------
@dataclass
class Alert:
    alert_id: str
    alert_type: str       # "restricted_zone" | "after_hours" | "loitering" | "crowd" | "unknown_restricted"
    person_id: str        # EMP001 or VISITOR-0001
    camera_id: str
    zone_id: str
    severity: str         # "info" | "warning" | "critical"
    message: str
    snapshot_path: str
    timestamp: datetime
    acknowledged: bool = False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class SmartAlerts:
    # Configurable defaults
    RESTRICTED_ZONES         = ["Warehouse", "Store", "Server Room", "Printing Plant"]
    LOITERING_THRESHOLD_SECONDS = 900    # 15 minutes
    CROWD_THRESHOLD          = 20
    OFFICE_END_HOUR          = 19        # alert if person seen at/after 19:00
    OFFICE_START_HOUR        = 7         # alert if person seen before 07:00

    _MAX_ALERTS   = 500
    _DEDUP_WINDOW = timedelta(minutes=5)

    def __init__(
        self,
        restricted_zones: list = None,
        loitering_seconds: int = 900,
        crowd_threshold: int = 20,
        office_start: int = 7,
        office_end: int = 19,
    ) -> None:
        self._restricted_zones      = restricted_zones if restricted_zones is not None \
                                      else list(self.RESTRICTED_ZONES)
        self._loitering_threshold   = loitering_seconds
        self._crowd_threshold       = crowd_threshold
        self._office_start          = office_start
        self._office_end            = office_end

        self._alerts: list[Alert]   = []
        self._lock                  = threading.Lock()

        # De-dup cache: key=(person_id, alert_type, zone_id) → last_fired datetime
        self._dedup: dict           = {}

    # -----------------------------------------------------------------------
    # Public rule checks
    # -----------------------------------------------------------------------
    def check_restricted_zone(
        self,
        person_id: str,
        camera_id: str,
        zone_label: str,
        is_visitor: bool,
        timestamp: datetime,
    ) -> Optional[Alert]:
        """
        Fire when any person is detected inside a restricted zone.
        - Visitor in restricted zone → warning
        - Unknown / unidentified visitor (person_id starts with "VISITOR") → critical
        """
        if zone_label not in self._restricted_zones:
            return None

        if is_visitor or person_id.upper().startswith("VISITOR"):
            severity = "critical"
            alert_type = "unknown_restricted"
            msg = (
                f"Visitor {person_id} detected in restricted zone '{zone_label}' "
                f"on camera {camera_id}."
            )
        else:
            # Employees generally have access; only raise info-level
            severity = "info"
            alert_type = "restricted_zone"
            msg = (
                f"Employee {person_id} entered restricted zone '{zone_label}' "
                f"on camera {camera_id}."
            )

        return self._create_alert(alert_type, person_id, camera_id, zone_label, severity, msg)

    def check_after_hours(
        self,
        person_id: str,
        camera_id: str,
        zone_label: str,
        timestamp: datetime,
    ) -> Optional[Alert]:
        """Fire when a person is detected outside configured office hours."""
        hour = timestamp.hour
        if self._office_start <= hour < self._office_end:
            return None

        if hour < self._office_start:
            period = f"before office start ({self._office_start:02d}:00)"
        else:
            period = f"after office end ({self._office_end:02d}:00)"

        msg = (
            f"Person {person_id} detected {period} in zone '{zone_label}' "
            f"on camera {camera_id} at {timestamp.strftime('%H:%M:%S')}."
        )
        return self._create_alert(
            "after_hours", person_id, camera_id, zone_label, "warning", msg
        )

    def check_loitering(
        self,
        person_id: str,
        camera_id: str,
        zone_label: str,
        duration_seconds: int,
        timestamp: datetime,
    ) -> Optional[Alert]:
        """Fire when a person has been in the same zone longer than the threshold."""
        if duration_seconds < self._loitering_threshold:
            return None

        minutes = duration_seconds // 60
        msg = (
            f"Loitering detected: {person_id} has been in zone '{zone_label}' "
            f"for {minutes} minute(s) on camera {camera_id}."
        )
        return self._create_alert(
            "loitering", person_id, camera_id, zone_label, "warning", msg
        )

    def check_crowd(
        self,
        zone_label: str,
        camera_id: str,
        count: int,
        timestamp: datetime,
    ) -> Optional[Alert]:
        """Fire when zone headcount exceeds crowd_threshold."""
        if count < self._crowd_threshold:
            return None

        msg = (
            f"Crowd alert: {count} people in zone '{zone_label}' on camera {camera_id} "
            f"(threshold: {self._crowd_threshold})."
        )
        # Use zone_label as person_id for crowd alerts (no single person)
        return self._create_alert(
            "crowd", "CROWD", camera_id, zone_label, "warning", msg
        )

    def check_unknown_in_restricted(
        self,
        person_id: str,
        camera_id: str,
        zone_label: str,
        timestamp: datetime,
    ) -> Optional[Alert]:
        """
        Specifically for VISITOR-prefixed IDs detected inside restricted zones.
        Always critical severity.
        """
        if zone_label not in self._restricted_zones:
            return None

        msg = (
            f"CRITICAL: Unrecognised person '{person_id}' found in restricted zone "
            f"'{zone_label}' on camera {camera_id}."
        )
        return self._create_alert(
            "unknown_restricted", person_id, camera_id, zone_label, "critical", msg
        )

    # -----------------------------------------------------------------------
    # Query methods
    # -----------------------------------------------------------------------
    def get_recent_alerts(self, n: int = 10) -> list:
        """Return the *n* most recent alerts (newest first)."""
        with self._lock:
            return list(reversed(self._alerts[-n:])) if self._alerts else []

    def acknowledge(self, alert_id: str) -> None:
        """Mark an alert as acknowledged by its UUID."""
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.acknowledged = True
                    return

    def get_unacknowledged(self) -> list:
        """Return all alerts that have not been acknowledged yet."""
        with self._lock:
            return [a for a in self._alerts if not a.acknowledged]

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------
    def _create_alert(
        self,
        alert_type: str,
        person_id: str,
        camera_id: str,
        zone: str,
        severity: str,
        message: str,
    ) -> Optional[Alert]:
        """
        Build an Alert, check de-duplication, append to internal list.
        Returns the Alert if it was new, None if suppressed by de-dup.
        """
        now = datetime.now()
        dedup_key = (person_id, alert_type, zone)

        with self._lock:
            last_fired = self._dedup.get(dedup_key)
            if last_fired and (now - last_fired) < self._DEDUP_WINDOW:
                return None

            alert = Alert(
                alert_id=str(uuid.uuid4()),
                alert_type=alert_type,
                person_id=person_id,
                camera_id=camera_id,
                zone_id=zone,
                severity=severity,
                message=message,
                snapshot_path="",
                timestamp=now,
            )

            self._dedup[dedup_key] = now

            # Enforce max capacity (drop oldest)
            if len(self._alerts) >= self._MAX_ALERTS:
                self._alerts.pop(0)
            self._alerts.append(alert)

        log.info("[ALERT][%s] %s – %s", severity.upper(), alert_type, message)
        return alert
