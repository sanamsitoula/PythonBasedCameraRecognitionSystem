"""
db_manager.py – PostgreSQL integration using psycopg2 connection pooling.

Creates all tables on startup (CREATE TABLE IF NOT EXISTS).
Provides typed insert/upsert methods used exclusively by db_writer.py.

If the database is unavailable at startup, is_available = False and all
write methods are silent no-ops.  Background reconnection is attempted
after every failed write.
"""

import json
import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

log = logging.getLogger("database")

_DDL = """
CREATE TABLE IF NOT EXISTS cameras (
    id           SERIAL PRIMARY KEY,
    ip_address   VARCHAR(45)  NOT NULL,
    rtsp_url     TEXT         NOT NULL,
    label        VARCHAR(100),
    added_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sessions (
    id          SERIAL PRIMARY KEY,
    camera_id   INTEGER      NOT NULL REFERENCES cameras(id),
    started_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ,
    yolo_model  VARCHAR(100),
    device      VARCHAR(20),
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS tracked_objects (
    id           BIGSERIAL   PRIMARY KEY,
    session_id   INTEGER     NOT NULL REFERENCES sessions(id),
    track_id     VARCHAR(10) NOT NULL,
    frame_number BIGINT      NOT NULL,
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    class_label  VARCHAR(20) NOT NULL,
    confidence   REAL        NOT NULL,
    bbox_x1      INTEGER     NOT NULL,
    bbox_y1      INTEGER     NOT NULL,
    bbox_x2      INTEGER     NOT NULL,
    bbox_y2      INTEGER     NOT NULL,
    centroid_x   INTEGER     NOT NULL,
    centroid_y   INTEGER     NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_to_session   ON tracked_objects(session_id);
CREATE INDEX IF NOT EXISTS idx_to_track_id  ON tracked_objects(track_id, session_id);
CREATE INDEX IF NOT EXISTS idx_to_captured  ON tracked_objects(captured_at);

CREATE TABLE IF NOT EXISTS gender_classifications (
    id            BIGSERIAL   PRIMARY KEY,
    session_id    INTEGER     NOT NULL REFERENCES sessions(id),
    track_id      VARCHAR(10) NOT NULL,
    frame_number  BIGINT      NOT NULL,
    classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    gender        VARCHAR(10) NOT NULL,
    confidence    REAL        NOT NULL,
    backend       VARCHAR(20) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gc_session  ON gender_classifications(session_id);
CREATE INDEX IF NOT EXISTS idx_gc_track_id ON gender_classifications(track_id, session_id);

CREATE TABLE IF NOT EXISTS direction_events (
    id          BIGSERIAL   PRIMARY KEY,
    session_id  INTEGER     NOT NULL REFERENCES sessions(id),
    track_id    VARCHAR(10) NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    direction   VARCHAR(20) NOT NULL,
    class_label VARCHAR(20) NOT NULL,
    start_x     INTEGER     NOT NULL,
    start_y     INTEGER     NOT NULL,
    end_x       INTEGER     NOT NULL,
    end_y       INTEGER     NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_de_session ON direction_events(session_id);

CREATE TABLE IF NOT EXISTS line_crossings (
    id           BIGSERIAL   PRIMARY KEY,
    session_id   INTEGER     NOT NULL REFERENCES sessions(id),
    track_id     VARCHAR(10) NOT NULL,
    line_label   VARCHAR(100) NOT NULL,
    crossed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    direction    VARCHAR(10) NOT NULL,
    class_label  VARCHAR(20) NOT NULL,
    centroid_x   INTEGER     NOT NULL,
    centroid_y   INTEGER     NOT NULL,
    frame_number BIGINT      NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lc_session    ON line_crossings(session_id);
CREATE INDEX IF NOT EXISTS idx_lc_crossed_at ON line_crossings(crossed_at);
CREATE INDEX IF NOT EXISTS idx_lc_direction  ON line_crossings(direction);

CREATE TABLE IF NOT EXISTS zone_events (
    id           BIGSERIAL   PRIMARY KEY,
    session_id   INTEGER     NOT NULL REFERENCES sessions(id),
    track_id     VARCHAR(10) NOT NULL,
    zone_label   VARCHAR(100) NOT NULL,
    event_type   VARCHAR(10) NOT NULL,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    class_label  VARCHAR(20) NOT NULL,
    frame_number BIGINT      NOT NULL,
    duration_seconds REAL
);
CREATE INDEX IF NOT EXISTS idx_ze_session    ON zone_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ze_zone_label ON zone_events(zone_label);

CREATE TABLE IF NOT EXISTS occupancy_snapshots (
    id                    BIGSERIAL   PRIMARY KEY,
    session_id            INTEGER     NOT NULL REFERENCES sessions(id),
    recorded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    current_people        INTEGER     NOT NULL DEFAULT 0,
    current_vehicles      INTEGER     NOT NULL DEFAULT 0,
    peak_people_session   INTEGER     NOT NULL DEFAULT 0,
    peak_vehicles_session INTEGER     NOT NULL DEFAULT 0,
    avg_people_window     REAL        NOT NULL DEFAULT 0.0,
    avg_vehicles_window   REAL        NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_os_session  ON occupancy_snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_os_recorded ON occupancy_snapshots(recorded_at);

CREATE TABLE IF NOT EXISTS vehicle_counts (
    id          BIGSERIAL   PRIMARY KEY,
    session_id  INTEGER     NOT NULL REFERENCES sessions(id),
    bucket_start TIMESTAMPTZ NOT NULL,
    cars        INTEGER     NOT NULL DEFAULT 0,
    motorcycles INTEGER     NOT NULL DEFAULT 0,
    buses       INTEGER     NOT NULL DEFAULT 0,
    trucks      INTEGER     NOT NULL DEFAULT 0,
    bicycles    INTEGER     NOT NULL DEFAULT 0,
    UNIQUE (session_id, bucket_start)
);
CREATE INDEX IF NOT EXISTS idx_vc_session ON vehicle_counts(session_id);
CREATE INDEX IF NOT EXISTS idx_vc_bucket  ON vehicle_counts(bucket_start);

CREATE TABLE IF NOT EXISTS error_events (
    id          BIGSERIAL   PRIMARY KEY,
    session_id  INTEGER     REFERENCES sessions(id),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    severity    VARCHAR(10) NOT NULL,
    module      VARCHAR(50) NOT NULL,
    message     TEXT        NOT NULL,
    traceback   TEXT
);
CREATE INDEX IF NOT EXISTS idx_ee_session  ON error_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ee_occurred ON error_events(occurred_at);

CREATE TABLE IF NOT EXISTS system_health_snapshots (
    id           BIGSERIAL   PRIMARY KEY,
    session_id   INTEGER     NOT NULL REFERENCES sessions(id),
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cpu_percent  REAL        NOT NULL,
    ram_gb       REAL        NOT NULL,
    device_label VARCHAR(10) NOT NULL,
    actual_fps   REAL        NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sh_session  ON system_health_snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_sh_recorded ON system_health_snapshots(recorded_at);
"""


class DatabaseManager:
    def __init__(
        self,
        host:            str,
        port:            int,
        dbname:          str,
        user:            str,
        password:        str,
        pool_min:        int = 2,
        pool_max:        int = 10,
        connect_timeout: int = 5,
    ):
        self._dsn = (
            f"host={host} port={port} dbname={dbname} "
            f"user={user} password={password} "
            f"connect_timeout={connect_timeout}"
        )
        self._pool_min = pool_min
        self._pool_max = pool_max
        self._lock     = threading.Lock()
        self._pool_obj = None
        self._available = False
        self._reconnect_lock = threading.Lock()

        self._connect()
        if self._available:
            self._init_schema()

    # ─────────────────────────── connection pool ─────────────────────────────

    def _connect(self) -> None:
        try:
            import psycopg2
            import psycopg2.pool  # type: ignore
            self._pool_obj = psycopg2.pool.ThreadedConnectionPool(
                minconn = self._pool_min,
                maxconn = self._pool_max,
                dsn     = self._dsn,
            )
            self._available = True
            log.info("PostgreSQL connection pool established.")
        except Exception as exc:
            log.error("PostgreSQL connection failed: %s", exc)
            self._available = False

    def _init_schema(self) -> None:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(_DDL)
            log.info("Database schema initialised (CREATE TABLE IF NOT EXISTS).")
        except Exception as exc:
            log.error("Schema init failed: %s", exc)

    @contextmanager
    def _get_conn(self):
        if not self._available or self._pool_obj is None:
            raise RuntimeError("Database not available")
        conn = None
        try:
            conn = self._pool_obj.getconn()
            yield conn
            conn.commit()
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            if conn:
                try:
                    self._pool_obj.putconn(conn)
                except Exception:
                    pass

    def _execute(self, sql: str, params: tuple = ()) -> bool:
        if not self._available:
            return False
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
            return True
        except Exception as exc:
            log.error("DB execute error: %s | SQL: %.80s", exc, sql)
            self._try_reconnect()
            return False

    def _fetchone(self, sql: str, params: tuple = ()):
        if not self._available:
            return None
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.fetchone()
        except Exception as exc:
            log.error("DB fetchone error: %s", exc)
            return None

    def _try_reconnect(self) -> None:
        if not self._reconnect_lock.acquire(blocking=False):
            return
        try:
            log.warning("Attempting DB reconnection…")
            if self._pool_obj:
                try:
                    self._pool_obj.closeall()
                except Exception:
                    pass
            time.sleep(2)
            self._connect()
        finally:
            self._reconnect_lock.release()

    # ─────────────────────────── session management ───────────────────────────

    def ensure_camera(self, ip: str, rtsp_url: str, label: str = "") -> Optional[int]:
        row = self._fetchone(
            "SELECT id FROM cameras WHERE ip_address = %s", (ip,)
        )
        if row:
            self._execute(
                "UPDATE cameras SET last_seen_at = NOW() WHERE ip_address = %s", (ip,)
            )
            return row[0]
        self._execute(
            "INSERT INTO cameras (ip_address, rtsp_url, label) VALUES (%s,%s,%s)",
            (ip, rtsp_url, label),
        )
        row = self._fetchone("SELECT id FROM cameras WHERE ip_address = %s", (ip,))
        return row[0] if row else None

    def create_session(self, camera_id: int, model: str, device: str) -> Optional[int]:
        self._execute(
            "INSERT INTO sessions (camera_id, yolo_model, device) VALUES (%s,%s,%s)",
            (camera_id, model, device),
        )
        row = self._fetchone(
            "SELECT id FROM sessions WHERE camera_id = %s ORDER BY started_at DESC LIMIT 1",
            (camera_id,),
        )
        return row[0] if row else None

    def close_session(self, session_id: int) -> None:
        self._execute(
            "UPDATE sessions SET ended_at = NOW() WHERE id = %s", (session_id,)
        )

    # ─────────────────────────── insert methods ───────────────────────────────

    def insert_tracked_objects_batch(self, session_id: int, records: list) -> None:
        if not records:
            return
        sql = """
            INSERT INTO tracked_objects
                (session_id, track_id, frame_number, class_label, confidence,
                 bbox_x1, bbox_y1, bbox_x2, bbox_y2, centroid_x, centroid_y)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """
        if not self._available:
            return
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    import psycopg2.extras  # type: ignore
                    psycopg2.extras.execute_batch(cur, sql, records)
        except Exception as exc:
            log.error("Batch insert error: %s", exc)

    def insert_gender(
        self, session_id: int, track_id: str, frame_number: int,
        gender: str, confidence: float, backend: str
    ) -> None:
        self._execute(
            """INSERT INTO gender_classifications
               (session_id, track_id, frame_number, gender, confidence, backend)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (session_id, track_id, frame_number, gender, confidence, backend),
        )

    def insert_direction_event(
        self, session_id: int, track_id: str, direction: str, class_label: str,
        sx: int, sy: int, ex: int, ey: int
    ) -> None:
        self._execute(
            """INSERT INTO direction_events
               (session_id, track_id, direction, class_label, start_x, start_y, end_x, end_y)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (session_id, track_id, direction, class_label, sx, sy, ex, ey),
        )

    def insert_line_crossing(
        self, session_id: int, track_id: str, line_label: str, direction: str,
        class_label: str, cx: int, cy: int, frame_number: int
    ) -> None:
        self._execute(
            """INSERT INTO line_crossings
               (session_id, track_id, line_label, direction, class_label,
                centroid_x, centroid_y, frame_number)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (session_id, track_id, line_label, direction, class_label, cx, cy, frame_number),
        )

    def insert_zone_event(
        self, session_id: int, track_id: str, zone_label: str, event_type: str,
        class_label: str, frame_number: int, duration_seconds: Optional[float]
    ) -> None:
        self._execute(
            """INSERT INTO zone_events
               (session_id, track_id, zone_label, event_type, class_label,
                frame_number, duration_seconds)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (session_id, track_id, zone_label, event_type, class_label,
             frame_number, duration_seconds),
        )

    def insert_occupancy_snapshot(
        self, session_id: int, current_p: int, current_v: int,
        peak_p: int, peak_v: int, avg_p: float, avg_v: float
    ) -> None:
        self._execute(
            """INSERT INTO occupancy_snapshots
               (session_id, current_people, current_vehicles,
                peak_people_session, peak_vehicles_session,
                avg_people_window, avg_vehicles_window)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (session_id, current_p, current_v, peak_p, peak_v, avg_p, avg_v),
        )

    def upsert_vehicle_counts(
        self, session_id: int, bucket_start: datetime,
        cars: int, motorcycles: int, buses: int, trucks: int, bicycles: int
    ) -> None:
        self._execute(
            """INSERT INTO vehicle_counts
               (session_id, bucket_start, cars, motorcycles, buses, trucks, bicycles)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (session_id, bucket_start) DO UPDATE SET
                   cars        = EXCLUDED.cars,
                   motorcycles = EXCLUDED.motorcycles,
                   buses       = EXCLUDED.buses,
                   trucks      = EXCLUDED.trucks,
                   bicycles    = EXCLUDED.bicycles""",
            (session_id, bucket_start, cars, motorcycles, buses, trucks, bicycles),
        )

    def insert_error_event(
        self, session_id: Optional[int], severity: str, module: str,
        message: str, traceback: Optional[str] = None
    ) -> None:
        self._execute(
            """INSERT INTO error_events (session_id, severity, module, message, traceback)
               VALUES (%s,%s,%s,%s,%s)""",
            (session_id, severity, module, message, traceback),
        )

    def insert_health_snapshot(
        self, session_id: int, cpu: float, ram_gb: float, device: str, fps: float
    ) -> None:
        self._execute(
            """INSERT INTO system_health_snapshots
               (session_id, cpu_percent, ram_gb, device_label, actual_fps)
               VALUES (%s,%s,%s,%s,%s)""",
            (session_id, cpu, ram_gb, device, fps),
        )

    # ─────────────────────────── shutdown ────────────────────────────────────

    @property
    def is_available(self) -> bool:
        return self._available

    def close(self) -> None:
        if self._pool_obj:
            try:
                self._pool_obj.closeall()
                log.info("DB connection pool closed.")
            except Exception:
                pass
