"""Celery tasks for AI event processing."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_sync_db():
    """Return a synchronous SQLAlchemy session for use in Celery tasks."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import os

    try:
        from ..core.config import settings  # type: ignore[import]
        db_url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
    except Exception:
        db_url = os.getenv("DATABASE_URL", "postgresql://evap:evap@localhost:5432/evap").replace(
            "postgresql+asyncpg", "postgresql"
        )

    engine = create_engine(db_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session()


def _get_redis_sync():
    """Synchronous Redis client for Celery tasks."""
    import redis
    import os

    try:
        from ..core.config import settings  # type: ignore[import]
        url = settings.REDIS_URL
    except Exception:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(url, decode_responses=True)


# ---------------------------------------------------------------------------
# Routing task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.workers.ai_tasks.process_detection_event",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def process_detection_event(self, detection_data: Dict[str, Any]) -> None:
    """Route incoming detection events to the appropriate handler task."""
    event_type = detection_data.get("type", "")
    try:
        if event_type == "face_recognition":
            process_face_recognition.apply_async(args=[detection_data], queue="ai")
        elif event_type == "vehicle_detection":
            process_vehicle_detection.apply_async(args=[detection_data], queue="ai")
        elif event_type == "behavior":
            process_behavior_event.apply_async(args=[detection_data], queue="ai")
        elif event_type == "occupancy":
            update_occupancy_snapshot.apply_async(
                args=[detection_data.get("camera_id"), detection_data.get("counts", {})],
                queue="ai",
            )
        else:
            logger.warning("Unknown detection event type: %s", event_type)
    except Exception as exc:
        logger.error("Error routing detection event: %s", exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Face recognition
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.workers.ai_tasks.process_face_recognition",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def process_face_recognition(self, event_data: Dict[str, Any]) -> None:
    """
    Process a face recognition event:
    - Identify employee or mark as visitor
    - Create/update attendance record
    - Update zone_history (movement)
    - Publish to Redis for WebSocket broadcast
    """
    db = None
    try:
        db = _get_sync_db()
        redis_client = _get_redis_sync()

        person_id: Optional[int] = event_data.get("person_id")
        employee_id: Optional[str] = event_data.get("employee_id")
        camera_id: int = event_data.get("camera_id", 0)
        zone_id: Optional[int] = event_data.get("zone_id")
        confidence: float = event_data.get("confidence", 0.0)
        ts_str: str = event_data.get("timestamp", datetime.now(timezone.utc).isoformat())
        event_ts = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else ts_str

        if employee_id:
            # Update attendance: first entry of the day
            from sqlalchemy import text
            db.execute(
                text("""
                    INSERT INTO attendance_log (employee_id, date, first_entry, status, camera_id)
                    SELECT em.id, :today, :ts, 'present', :cam_id
                    FROM employee_master em WHERE em.employee_id = :emp_id
                    ON CONFLICT (employee_id, date) DO UPDATE
                      SET last_exit = EXCLUDED.first_entry,
                          status    = 'present'
                      WHERE attendance_log.last_exit IS NULL
                         OR attendance_log.last_exit < EXCLUDED.first_entry
                """),
                {
                    "today": event_ts.date(),
                    "ts": event_ts,
                    "cam_id": camera_id,
                    "emp_id": employee_id,
                },
            )
            db.commit()

        # Zone history
        if zone_id and person_id:
            db.execute(
                text("""
                    INSERT INTO zone_history (person_id, person_type, zone_id, camera_id, entry_time)
                    VALUES (:pid, :ptype, :zid, :cid, :ts)
                """),
                {
                    "pid": person_id,
                    "ptype": "employee" if employee_id else "visitor",
                    "zid": zone_id,
                    "cid": camera_id,
                    "ts": event_ts,
                },
            )
            db.commit()

        # Publish WebSocket event
        import json
        ws_event = {
            "type": "PERSON_DETECTED",
            "data": {
                "person_id": person_id,
                "employee_id": employee_id,
                "camera_id": camera_id,
                "zone_id": zone_id,
                "confidence": confidence,
                "timestamp": event_ts.isoformat(),
            },
        }
        redis_client.publish("evap:ws:broadcast", json.dumps(ws_event))

    except Exception as exc:
        logger.error("process_face_recognition error: %s", exc)
        if db:
            db.rollback()
        raise self.retry(exc=exc)
    finally:
        if db:
            db.close()


# ---------------------------------------------------------------------------
# Vehicle detection
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.workers.ai_tasks.process_vehicle_detection",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def process_vehicle_detection(self, event_data: Dict[str, Any]) -> None:
    """
    Process a vehicle detection event:
    - Upsert license_plate_log (entry or exit)
    - Check against blacklist → trigger alert if needed
    - Publish to Redis
    """
    db = None
    try:
        db = _get_sync_db()
        redis_client = _get_redis_sync()

        plate: str = event_data.get("plate_number", "").upper().strip()
        camera_id: int = event_data.get("camera_id", 0)
        site_id: Optional[int] = event_data.get("site_id")
        direction: str = event_data.get("direction", "unknown")
        confidence: float = event_data.get("confidence", 0.0)
        vehicle_type: str = event_data.get("vehicle_type", "car")
        snapshot: Optional[str] = event_data.get("snapshot_path")
        ts_str = event_data.get("timestamp", datetime.now(timezone.utc).isoformat())
        event_ts = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else ts_str

        from sqlalchemy import text
        if direction == "entry":
            db.execute(
                text("""
                    INSERT INTO license_plate_log
                      (camera_id, plate_number, plate_confidence, vehicle_type, entry_time, direction, site_id, snapshot_path)
                    VALUES (:cam, :plate, :conf, :vtype, :ts, 'entry', :site, :snap)
                """),
                {
                    "cam": camera_id, "plate": plate, "conf": confidence,
                    "vtype": vehicle_type, "ts": event_ts, "site": site_id, "snap": snapshot,
                },
            )
        elif direction == "exit":
            # Update most recent open entry for this plate
            db.execute(
                text("""
                    UPDATE license_plate_log
                    SET exit_time = :ts,
                        direction = 'exit',
                        parking_duration_seconds = EXTRACT(EPOCH FROM (:ts - entry_time))::INTEGER
                    WHERE log_id = (
                        SELECT log_id FROM license_plate_log
                        WHERE plate_number = :plate AND exit_time IS NULL
                        ORDER BY entry_time DESC LIMIT 1
                    )
                """),
                {"ts": event_ts, "plate": plate},
            )
        db.commit()

        # Check blacklist
        row = db.execute(
            text("SELECT is_blacklisted FROM vehicle_master WHERE plate_number = :p"),
            {"p": plate},
        ).fetchone()
        if row and row.is_blacklisted:
            import json
            alert_event = {
                "type": "alert",
                "data": {
                    "alert_type": "blacklisted_vehicle",
                    "severity": "critical",
                    "camera_id": camera_id,
                    "site_id": site_id,
                    "plate_number": plate,
                    "message": f"Blacklisted vehicle detected: {plate}",
                },
            }
            redis_client.publish("evap:alerts:trigger", json.dumps(alert_event))

        # Publish vehicle event
        import json
        ws_event = {
            "type": "VEHICLE_DETECTED",
            "data": {"plate": plate, "camera_id": camera_id, "direction": direction, "timestamp": event_ts.isoformat()},
        }
        redis_client.publish("evap:ws:broadcast", json.dumps(ws_event))

    except Exception as exc:
        logger.error("process_vehicle_detection error: %s", exc)
        if db:
            db.rollback()
        raise self.retry(exc=exc)
    finally:
        if db:
            db.close()


# ---------------------------------------------------------------------------
# Behavior event
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.workers.ai_tasks.process_behavior_event",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def process_behavior_event(self, event_data: Dict[str, Any]) -> None:
    """Save behavior event; trigger alert if event warrants one."""
    db = None
    try:
        db = _get_sync_db()
        redis_client = _get_redis_sync()

        behavior_type: str = event_data.get("behavior_type", "")
        camera_id: int = event_data.get("camera_id", 0)
        zone_id: Optional[int] = event_data.get("zone_id")
        person_id: Optional[int] = event_data.get("person_id")
        confidence: float = event_data.get("confidence", 0.0)
        snapshot: Optional[str] = event_data.get("snapshot_path")
        ts_str = event_data.get("timestamp", datetime.now(timezone.utc).isoformat())
        event_ts = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else ts_str

        from sqlalchemy import text
        result = db.execute(
            text("""
                INSERT INTO behavior_events
                  (camera_id, zone_id, event_type, person_id, confidence, started_at, snapshot_path)
                VALUES (:cam, :zone, :etype, :pid, :conf, :ts, :snap)
                RETURNING event_id
            """),
            {
                "cam": camera_id, "zone": zone_id, "etype": behavior_type,
                "pid": person_id, "conf": confidence, "ts": event_ts, "snap": snapshot,
            },
        )
        event_id = result.scalar()
        db.commit()

        # Auto-alert for high-risk behaviors
        alert_behaviors = {"loitering", "tailgating", "crowding"}
        if behavior_type in alert_behaviors:
            import json
            alert = {
                "type": "alert",
                "data": {
                    "alert_type": f"behavior_{behavior_type}",
                    "severity": "warning" if behavior_type != "tailgating" else "critical",
                    "camera_id": camera_id,
                    "zone_id": zone_id,
                    "message": f"Behavior detected: {behavior_type} at camera {camera_id}",
                    "details": {"event_id": event_id, "confidence": confidence},
                },
            }
            redis_client.publish("evap:alerts:trigger", json.dumps(alert))

            # Mark event as alert_generated
            db.execute(
                text("UPDATE behavior_events SET alert_generated = TRUE WHERE event_id = :eid"),
                {"eid": event_id},
            )
            db.commit()

    except Exception as exc:
        logger.error("process_behavior_event error: %s", exc)
        if db:
            db.rollback()
        raise self.retry(exc=exc)
    finally:
        if db:
            db.close()


# ---------------------------------------------------------------------------
# Occupancy snapshot
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.workers.ai_tasks.update_occupancy_snapshot",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def update_occupancy_snapshot(self, camera_id: int, counts: Dict[str, Any]) -> None:
    """Save an occupancy snapshot row and publish to Redis."""
    db = None
    try:
        db = _get_sync_db()
        redis_client = _get_redis_sync()

        people = counts.get("people", 0)
        employees = counts.get("employees", 0)
        visitors = counts.get("visitors", 0)
        zone_id = counts.get("zone_id")
        max_cap = counts.get("max_capacity")
        occ_pct = round((people / max_cap * 100), 2) if max_cap and max_cap > 0 else None

        from sqlalchemy import text
        db.execute(
            text("""
                INSERT INTO occupancy_log
                  (camera_id, zone_id, snapshot_time, people_count, employees_count, visitors_count, max_capacity, occupancy_pct)
                VALUES (:cam, :zone, NOW(), :people, :emp, :vis, :cap, :pct)
            """),
            {
                "cam": camera_id, "zone": zone_id,
                "people": people, "emp": employees, "vis": visitors,
                "cap": max_cap, "pct": occ_pct,
            },
        )
        db.commit()

        import json
        ws_event = {
            "type": "OCCUPANCY_UPDATE",
            "data": {
                "camera_id": camera_id,
                "zone_id": zone_id,
                "people_count": people,
                "occupancy_pct": occ_pct,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        redis_client.publish("evap:ws:broadcast", json.dumps(ws_event))

        # Invalidate dashboard cache
        redis_client.delete("evap:dashboard:all")

    except Exception as exc:
        logger.error("update_occupancy_snapshot error: %s", exc)
        if db:
            db.rollback()
        raise self.retry(exc=exc)
    finally:
        if db:
            db.close()


# ---------------------------------------------------------------------------
# Camera health check (beat task)
# ---------------------------------------------------------------------------

@celery_app.task(name="app.workers.ai_tasks.camera_health_check")
def camera_health_check() -> None:
    """Mark cameras as offline if no heartbeat in last 2 minutes."""
    db = None
    try:
        db = _get_sync_db()
        from sqlalchemy import text
        db.execute(
            text("""
                UPDATE camera_master
                SET status = 'offline'
                WHERE is_active = TRUE
                  AND status = 'online'
                  AND last_heartbeat < NOW() - INTERVAL '2 minutes'
            """)
        )
        db.commit()
    except Exception as exc:
        logger.error("camera_health_check error: %s", exc)
        if db:
            db.rollback()
    finally:
        if db:
            db.close()
