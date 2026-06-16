"""
audit_logger.py – Security audit trail for Phase 3 identity-sensitive operations.

Each event is written as a JSON line to a daily rotating file:
    logs/audit_YYYYMMDD.log

Thread-safe via threading.Lock.
"""

import json
import logging
import os
import threading
from datetime import datetime
from typing import Optional

log = logging.getLogger("audit")


class AuditLogger:
    """
    Writes structured JSON audit events to a date-rotating log file.

    File format:  logs/audit_YYYYMMDD.log
    Line format:  one JSON object per line, always includes ``event_type`` and
                  ``timestamp`` (ISO-8601 UTC).
    """

    def __init__(self, log_dir: str = "logs") -> None:
        self._log_dir = log_dir
        self._lock    = threading.Lock()
        os.makedirs(log_dir, exist_ok=True)

    # -----------------------------------------------------------------------
    # Public logging methods
    # -----------------------------------------------------------------------
    def log_recognition(
        self,
        camera_id: str,
        track_id: str,
        person_id: str,
        confidence: float,
        recognition_status: str,
    ) -> None:
        """Log a face recognition event."""
        self._write({
            "event_type":         "face_recognition",
            "camera_id":          camera_id,
            "track_id":           track_id,
            "person_id":          person_id,
            "confidence":         round(confidence, 4),
            "recognition_status": recognition_status,
        })

    def log_enrollment_add(
        self,
        actor: str,
        employee_id: str,
        employee_name: str,
    ) -> None:
        """Log addition of a new employee to the system."""
        self._write({
            "event_type":    "enrollment_add",
            "actor":         actor,
            "employee_id":   employee_id,
            "employee_name": employee_name,
        })

    def log_enrollment_update(
        self,
        actor: str,
        employee_id: str,
        changes: dict,
    ) -> None:
        """Log modification of an employee's metadata."""
        self._write({
            "event_type":  "enrollment_update",
            "actor":       actor,
            "employee_id": employee_id,
            "changes":     changes,
        })

    def log_enrollment_delete(
        self,
        actor: str,
        employee_id: str,
    ) -> None:
        """Log deletion / deactivation of an employee record."""
        self._write({
            "event_type":  "enrollment_delete",
            "actor":       actor,
            "employee_id": employee_id,
        })

    def log_alert(self, alert) -> None:
        """
        Log a fired smart alert.
        Accepts an Alert dataclass instance (smart_alerts.Alert).
        """
        self._write({
            "event_type":  "smart_alert",
            "alert_id":    alert.alert_id,
            "alert_type":  alert.alert_type,
            "person_id":   alert.person_id,
            "camera_id":   alert.camera_id,
            "zone_id":     alert.zone_id,
            "severity":    alert.severity,
            "message":     alert.message,
            "snapshot_path": alert.snapshot_path,
            "alert_ts":    alert.timestamp.isoformat(),
        })

    def log_attendance_event(
        self,
        employee_id: str,
        event_type: str,
        timestamp: datetime,
    ) -> None:
        """
        Log an attendance entry or exit.
        event_type: "entry" | "exit"
        """
        self._write({
            "event_type":  "attendance_event",
            "employee_id": employee_id,
            "action":      event_type,
            "event_ts":    timestamp.isoformat(),
        })

    def log_system_event(self, event: str, details: dict) -> None:
        """Log a generic system event (startup, shutdown, config reload, etc.)."""
        self._write({
            "event_type": "system_event",
            "event":      event,
            "details":    details,
        })

    # -----------------------------------------------------------------------
    # Internal writer
    # -----------------------------------------------------------------------
    def _write(self, entry: dict) -> None:
        """Append a JSON line to today's audit file."""
        entry["timestamp"] = datetime.utcnow().isoformat() + "Z"
        line = json.dumps(entry, ensure_ascii=False)

        today  = datetime.utcnow().strftime("%Y%m%d")
        path   = os.path.join(self._log_dir, f"audit_{today}.log")

        with self._lock:
            try:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError as exc:
                log.error("AuditLogger: failed to write event '%s': %s",
                          entry.get("event_type", "?"), exc)
