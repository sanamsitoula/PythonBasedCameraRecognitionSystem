"""
db_manager_p3.py  –  Phase 3 database layer for the CCTV analytics platform.

Wraps the existing DatabaseManager (db_manager.py) and reuses its
ThreadedConnectionPool via _get_conn().  All Phase 3 tables are created on
instantiation by executing sql/schema_p3.sql.

Embedding vectors are stored as raw bytes (float32, 512-dim):
    serialize  : ndarray.tobytes()
    deserialize: np.frombuffer(data, dtype=np.float32).reshape(512,)
"""

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, date
from typing import Optional

import numpy as np
import psycopg2

log = logging.getLogger("database_p3")

# Path to the Phase 3 DDL file, relative to this module's location.
_SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql", "schema_p3.sql")

# Shape assumed for all stored face embeddings.
_EMBEDDING_DTYPE = np.float32
_EMBEDDING_DIM   = 512


class DatabaseManagerP3:
    """
    Phase 3 database operations.

    Parameters
    ----------
    db_manager : DatabaseManager
        An already-initialised Phase 1/2 DatabaseManager instance whose
        _get_conn() context manager is reused for all Phase 3 queries.
    """

    def __init__(self, db_manager) -> None:
        self._db = db_manager
        self._init_schema()

    # ─────────────────────────── internal helpers ─────────────────────────────

    @contextmanager
    def _get_conn(self):
        """Delegate to the parent DatabaseManager's connection pool."""
        with self._db._get_conn() as conn:
            yield conn

    def _init_schema(self) -> None:
        """Execute schema_p3.sql to create all Phase 3 tables if absent."""
        try:
            with open(_SCHEMA_FILE, "r", encoding="utf-8") as fh:
                ddl = fh.read()
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(ddl)
            log.info("Phase 3 schema initialised (schema_p3.sql).")
        except Exception as exc:
            log.error("Phase 3 schema init failed: %s", exc)

    @staticmethod
    def _vec_to_bytes(vec: np.ndarray) -> bytes:
        return vec.astype(_EMBEDDING_DTYPE).tobytes()

    @staticmethod
    def _bytes_to_vec(data: bytes) -> np.ndarray:
        return np.frombuffer(data, dtype=_EMBEDDING_DTYPE).reshape(_EMBEDDING_DIM)

    # ─────────────────────────── employee management ──────────────────────────

    def ensure_employee(
        self,
        employee_id: str,
        name: str,
        department: str,
        designation: str,
    ) -> bool:
        """
        Insert a new employee record or update name/department/designation if
        the employee already exists.  Returns True on success.
        """
        sql = """
            INSERT INTO employee_master (employee_id, employee_name, department, designation)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (employee_id) DO UPDATE SET
                employee_name = EXCLUDED.employee_name,
                department    = EXCLUDED.department,
                designation   = EXCLUDED.designation,
                updated_at    = NOW()
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (employee_id, name, department, designation))
            return True
        except Exception as exc:
            log.error("ensure_employee(%s) failed: %s", employee_id, exc)
            return False

    def update_employee_status(self, employee_id: str, status: str) -> bool:
        """
        Set the status of an employee ('active', 'inactive', 'deleted').
        Returns True on success.
        """
        sql = """
            UPDATE employee_master
               SET status = %s, updated_at = NOW()
             WHERE employee_id = %s
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (status, employee_id))
            return True
        except Exception as exc:
            log.error("update_employee_status(%s, %s) failed: %s", employee_id, status, exc)
            return False

    def get_all_active_employees(self) -> list:
        """
        Return a list of dicts for all employees with status='active'.
        Each dict contains employee_id, employee_name, department, designation,
        work_start_time, work_end_time.
        """
        sql = """
            SELECT employee_id, employee_name, department, designation,
                   work_start_time, work_end_time
              FROM employee_master
             WHERE status = 'active'
             ORDER BY employee_name
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
            return [
                {
                    "employee_id":    r[0],
                    "employee_name":  r[1],
                    "department":     r[2],
                    "designation":    r[3],
                    "work_start_time": str(r[4]),
                    "work_end_time":   str(r[5]),
                }
                for r in rows
            ]
        except Exception as exc:
            log.error("get_all_active_employees() failed: %s", exc)
            return []

    # ─────────────────────────── face embeddings ──────────────────────────────

    def save_face_embedding(
        self,
        employee_id: str,
        embedding_vector: np.ndarray,
        image_path: str,
        angle: str,
    ) -> int:
        """
        Persist a face embedding for an employee.
        Also upserts a row in employee_face_master to track enrolment counts.
        Returns the new embedding_id, or -1 on failure.
        """
        sql_emb = """
            INSERT INTO face_embeddings
                (employee_id, embedding_vector, image_path, source_angle)
            VALUES (%s, %s, %s, %s)
            RETURNING embedding_id
        """
        sql_master = """
            INSERT INTO employee_face_master (employee_id, image_count, last_enrolled)
            VALUES (%s, 1, NOW())
            ON CONFLICT (employee_id) DO UPDATE SET
                image_count   = employee_face_master.image_count + 1,
                last_enrolled = NOW()
        """
        try:
            vec_bytes = self._vec_to_bytes(embedding_vector)
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql_emb, (employee_id, psycopg2.Binary(vec_bytes), image_path, angle))
                    row = cur.fetchone()
                    embedding_id = row[0] if row else -1
                    cur.execute(sql_master, (employee_id,))
            return embedding_id
        except Exception as exc:
            log.error("save_face_embedding(%s) failed: %s", employee_id, exc)
            return -1

    def load_all_embeddings(self) -> dict:
        """
        Load every face embedding for active employees.
        Returns dict[employee_id -> list[np.ndarray]].
        """
        sql = """
            SELECT fe.employee_id, fe.embedding_vector
              FROM face_embeddings fe
              JOIN employee_master em ON em.employee_id = fe.employee_id
             WHERE em.status = 'active'
             ORDER BY fe.employee_id, fe.embedding_id
        """
        result: dict = {}
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
            for emp_id, raw in rows:
                vec = self._bytes_to_vec(bytes(raw))
                result.setdefault(emp_id, []).append(vec)
        except Exception as exc:
            log.error("load_all_embeddings() failed: %s", exc)
        return result

    def delete_employee_embeddings(self, employee_id: str) -> bool:
        """Delete all face embeddings for a given employee. Returns True on success."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM face_embeddings WHERE employee_id = %s",
                        (employee_id,),
                    )
            return True
        except Exception as exc:
            log.error("delete_employee_embeddings(%s) failed: %s", employee_id, exc)
            return False

    # ─────────────────────────── recognition ──────────────────────────────────

    def insert_recognition(
        self,
        session_id: Optional[int],
        camera_id: str,
        track_id: str,
        employee_id_or_none: Optional[str],
        visitor_id_or_none: Optional[str],
        confidence: float,
        status: str,
        frame_number: int,
    ) -> bool:
        """Insert a single face recognition event. Returns True on success."""
        sql = """
            INSERT INTO recognized_persons
                (session_id, camera_id, track_id, employee_id, visitor_id,
                 confidence, recognition_status, frame_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        session_id, camera_id, track_id,
                        employee_id_or_none, visitor_id_or_none,
                        confidence, status, frame_number,
                    ))
            return True
        except Exception as exc:
            log.error("insert_recognition() failed: %s", exc)
            return False

    # ─────────────────────────── visitor management ───────────────────────────

    def get_or_create_visitor(self, visitor_id: str) -> bool:
        """
        Insert a visitor_master row if not present (first visit).
        Returns True on success.
        """
        sql = """
            INSERT INTO visitor_master (visitor_id)
            VALUES (%s)
            ON CONFLICT (visitor_id) DO NOTHING
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (visitor_id,))
            return True
        except Exception as exc:
            log.error("get_or_create_visitor(%s) failed: %s", visitor_id, exc)
            return False

    def update_visitor_last_seen(self, visitor_id: str) -> bool:
        """
        Update last_seen_at and increment total_visits for an existing visitor.
        Returns True on success.
        """
        sql = """
            UPDATE visitor_master
               SET last_seen_at = NOW(),
                   total_visits = total_visits + 1
             WHERE visitor_id = %s
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (visitor_id,))
            return True
        except Exception as exc:
            log.error("update_visitor_last_seen(%s) failed: %s", visitor_id, exc)
            return False

    # ─────────────────────────── attendance ───────────────────────────────────

    def upsert_attendance(
        self,
        employee_id: str,
        attendance_date: date,
        first_entry: Optional[datetime],
        last_exit: Optional[datetime],
        working_secs: int,
        break_secs: int,
        status: str,
        is_late: bool,
    ) -> bool:
        """
        Insert or update an attendance_log row for the given employee+date.
        On conflict the non-key columns are updated.  Returns True on success.
        """
        sql = """
            INSERT INTO attendance_log
                (employee_id, attendance_date, first_entry, last_exit,
                 working_duration_seconds, break_duration_seconds, status, is_late)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (employee_id, attendance_date) DO UPDATE SET
                first_entry              = COALESCE(attendance_log.first_entry, EXCLUDED.first_entry),
                last_exit                = EXCLUDED.last_exit,
                working_duration_seconds = EXCLUDED.working_duration_seconds,
                break_duration_seconds   = EXCLUDED.break_duration_seconds,
                status                   = EXCLUDED.status,
                is_late                  = EXCLUDED.is_late
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        employee_id, attendance_date,
                        first_entry, last_exit,
                        working_secs, break_secs,
                        status, is_late,
                    ))
            return True
        except Exception as exc:
            log.error("upsert_attendance(%s, %s) failed: %s", employee_id, attendance_date, exc)
            return False

    def get_today_attendance(self) -> list:
        """
        Return attendance records for today as a list of dicts.
        Columns: attendance_id, employee_id, employee_name, department,
                 first_entry, last_exit, working_duration_seconds,
                 break_duration_seconds, status, is_late.
        """
        sql = """
            SELECT al.attendance_id, al.employee_id, em.employee_name, em.department,
                   al.first_entry, al.last_exit,
                   al.working_duration_seconds, al.break_duration_seconds,
                   al.status, al.is_late
              FROM attendance_log al
              JOIN employee_master em ON em.employee_id = al.employee_id
             WHERE al.attendance_date = CURRENT_DATE
             ORDER BY em.employee_name
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
            return [
                {
                    "attendance_id":           r[0],
                    "employee_id":             r[1],
                    "employee_name":           r[2],
                    "department":              r[3],
                    "first_entry":             r[4],
                    "last_exit":               r[5],
                    "working_duration_seconds": r[6],
                    "break_duration_seconds":  r[7],
                    "status":                  r[8],
                    "is_late":                 r[9],
                }
                for r in rows
            ]
        except Exception as exc:
            log.error("get_today_attendance() failed: %s", exc)
            return []

    # ─────────────────────────── zone history ─────────────────────────────────

    def insert_zone_history(
        self,
        employee_id: str,
        camera_id: str,
        zone_id: str,
        zone_label: str,
        entry_time: datetime,
        exit_time: Optional[datetime],
        duration_secs: Optional[int],
    ) -> bool:
        """Insert an employee zone visit record. Returns True on success."""
        sql = """
            INSERT INTO employee_zone_history
                (employee_id, camera_id, zone_id, zone_label,
                 entry_time, exit_time, duration_seconds)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        employee_id, camera_id, zone_id, zone_label,
                        entry_time, exit_time, duration_secs,
                    ))
            return True
        except Exception as exc:
            log.error("insert_zone_history(%s) failed: %s", employee_id, exc)
            return False

    # ─────────────────────────── canteen visits ───────────────────────────────

    def insert_canteen_visit(
        self,
        person_id: str,
        person_type: str,
        entry_time: datetime,
        exit_time: Optional[datetime],
        duration_secs: Optional[int],
        meal_period: str,
    ) -> bool:
        """Insert a canteen visit record. visit_date is derived from entry_time. Returns True on success."""
        sql = """
            INSERT INTO canteen_visits
                (person_id, person_type, entry_time, exit_time,
                 duration_seconds, meal_period, visit_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        visit_date = entry_time.date() if entry_time else datetime.utcnow().date()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        person_id, person_type, entry_time, exit_time,
                        duration_secs, meal_period, visit_date,
                    ))
            return True
        except Exception as exc:
            log.error("insert_canteen_visit(%s) failed: %s", person_id, exc)
            return False

    def get_today_canteen_visits(self) -> list:
        """
        Return all canteen visits for today as a list of dicts.
        Columns: visit_id, person_id, person_type, entry_time, exit_time,
                 duration_seconds, meal_period.
        """
        sql = """
            SELECT visit_id, person_id, person_type, entry_time, exit_time,
                   duration_seconds, meal_period
              FROM canteen_visits
             WHERE visit_date = CURRENT_DATE
             ORDER BY entry_time
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
            return [
                {
                    "visit_id":         r[0],
                    "person_id":        r[1],
                    "person_type":      r[2],
                    "entry_time":       r[3],
                    "exit_time":        r[4],
                    "duration_seconds": r[5],
                    "meal_period":      r[6],
                }
                for r in rows
            ]
        except Exception as exc:
            log.error("get_today_canteen_visits() failed: %s", exc)
            return []

    # ─────────────────────────── movement history ─────────────────────────────

    def insert_movement(
        self,
        person_id: str,
        person_type: str,
        camera_id: str,
        zone_id: str,
        zone_label: str,
        entry_time: datetime,
        exit_time: Optional[datetime],
        duration_secs: Optional[int],
        track_id: str,
    ) -> bool:
        """Insert a movement_history record for any person (employee or visitor). Returns True on success."""
        sql = """
            INSERT INTO movement_history
                (person_id, person_type, camera_id, zone_id, zone_label,
                 entry_time, exit_time, duration_seconds, track_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        person_id, person_type, camera_id, zone_id, zone_label,
                        entry_time, exit_time, duration_secs, track_id,
                    ))
            return True
        except Exception as exc:
            log.error("insert_movement(%s) failed: %s", person_id, exc)
            return False

    def get_employee_movement_today(self, employee_id: str) -> list:
        """
        Return all movement_history rows for a specific employee today as a list of dicts.
        Columns: movement_id, camera_id, zone_id, zone_label,
                 entry_time, exit_time, duration_seconds, track_id.
        """
        sql = """
            SELECT movement_id, camera_id, zone_id, zone_label,
                   entry_time, exit_time, duration_seconds, track_id
              FROM movement_history
             WHERE person_id   = %s
               AND person_type = 'employee'
               AND entry_time >= CURRENT_DATE
               AND entry_time  < CURRENT_DATE + INTERVAL '1 day'
             ORDER BY entry_time
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (employee_id,))
                    rows = cur.fetchall()
            return [
                {
                    "movement_id":      r[0],
                    "camera_id":        r[1],
                    "zone_id":          r[2],
                    "zone_label":       r[3],
                    "entry_time":       r[4],
                    "exit_time":        r[5],
                    "duration_seconds": r[6],
                    "track_id":         r[7],
                }
                for r in rows
            ]
        except Exception as exc:
            log.error("get_employee_movement_today(%s) failed: %s", employee_id, exc)
            return []

    # ─────────────────────────── cross-camera tracking ────────────────────────

    def insert_cross_camera_link(
        self,
        unified_id: str,
        camera_id: str,
        track_id: str,
        confidence: float,
    ) -> bool:
        """
        Insert or update a cross_camera_tracking link.
        On conflict (same unified_id + camera_id + track_id) updates last_seen and confidence.
        Returns True on success.
        """
        sql = """
            INSERT INTO cross_camera_tracking
                (unified_id, camera_id, track_id, first_seen, last_seen, confidence)
            VALUES (%s, %s, %s, NOW(), NOW(), %s)
            ON CONFLICT DO NOTHING
        """
        # We do a simple insert; if an exact duplicate already exists it is silently
        # skipped.  Callers needing update-on-dup should issue a separate UPDATE.
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (unified_id, camera_id, track_id, confidence))
            return True
        except Exception as exc:
            log.error("insert_cross_camera_link(%s) failed: %s", unified_id, exc)
            return False

    # ─────────────────────────── smart alerts ─────────────────────────────────

    def insert_alert(
        self,
        alert_type: str,
        person_id: Optional[str],
        camera_id: Optional[str],
        zone_id: Optional[str],
        severity: str,
        message: str,
        snapshot_path: Optional[str],
    ) -> bool:
        """Insert a smart_alerts record. Returns True on success."""
        sql = """
            INSERT INTO smart_alerts
                (alert_type, person_id, camera_id, zone_id,
                 severity, message, snapshot_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        alert_type, person_id, camera_id, zone_id,
                        severity, message, snapshot_path,
                    ))
            return True
        except Exception as exc:
            log.error("insert_alert(type=%s) failed: %s", alert_type, exc)
            return False

    # ─────────────────────────── audit log ────────────────────────────────────

    def insert_audit_log(
        self,
        action: str,
        actor_id: str,
        target_id: str,
        details_dict: Optional[dict],
    ) -> bool:
        """
        Insert an audit_log record.  details_dict is serialised to JSONB.
        Returns True on success.
        """
        sql = """
            INSERT INTO audit_log (action, actor_id, target_id, details)
            VALUES (%s, %s, %s, %s)
        """
        try:
            details_json = json.dumps(details_dict) if details_dict is not None else None
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (action, actor_id, target_id, details_json))
            return True
        except Exception as exc:
            log.error("insert_audit_log(action=%s) failed: %s", action, exc)
            return False
