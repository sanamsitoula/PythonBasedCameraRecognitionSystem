-- ============================================================
-- CCTV Analytics Phase 2 – PostgreSQL Schema
-- Run once to create all tables and indexes.
-- Safe to re-run: uses CREATE TABLE IF NOT EXISTS.
--
-- PREREQUISITES (run as postgres superuser first):
--   CREATE ROLE cctv_user LOGIN PASSWORD 'Nepal@123';
--   CREATE DATABASE cctv_analytics OWNER cctv_user;
--   \c cctv_analytics
--   GRANT USAGE ON SCHEMA public TO cctv_user;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO cctv_user;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cctv_user;
--
-- Run this file:
--   psql -h localhost -U cctv_user -d cctv_analytics -f sql/schema.sql
--
-- For a full one-step setup, use sql/000_setup.sql instead.
-- ============================================================

-- ----------------------------------------------------------
-- 1. cameras
--    One row per physical camera.
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS cameras (
    id           SERIAL      PRIMARY KEY,
    ip_address   VARCHAR(45) NOT NULL UNIQUE,
    rtsp_url     TEXT        NOT NULL,
    label        VARCHAR(100),
    added_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ
);

-- ----------------------------------------------------------
-- 2. sessions
--    One row per application run (startup → shutdown).
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id         SERIAL      PRIMARY KEY,
    camera_id  INTEGER     NOT NULL REFERENCES cameras(id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at   TIMESTAMPTZ,
    yolo_model VARCHAR(100),
    device     VARCHAR(20),
    notes      TEXT
);

-- ----------------------------------------------------------
-- 3. tracked_objects
--    One row per confirmed track per frame (high-frequency).
--    Written in batches of up to 200 rows for performance.
-- ----------------------------------------------------------
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
CREATE INDEX IF NOT EXISTS idx_to_session  ON tracked_objects(session_id);
CREATE INDEX IF NOT EXISTS idx_to_trackid  ON tracked_objects(track_id, session_id);
CREATE INDEX IF NOT EXISTS idx_to_captured ON tracked_objects(captured_at);

-- ----------------------------------------------------------
-- 4. gender_classifications
--    One row each time gender is determined for a track.
--    (Only once per track per session due to caching.)
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS gender_classifications (
    id            BIGSERIAL   PRIMARY KEY,
    session_id    INTEGER     NOT NULL REFERENCES sessions(id),
    track_id      VARCHAR(10) NOT NULL,
    frame_number  BIGINT      NOT NULL,
    classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    gender        VARCHAR(10) NOT NULL,   -- 'Male', 'Female', 'Unknown'
    confidence    REAL        NOT NULL,
    backend       VARCHAR(20) NOT NULL    -- 'deepface', 'insightface', 'none'
);
CREATE INDEX IF NOT EXISTS idx_gc_session  ON gender_classifications(session_id);
CREATE INDEX IF NOT EXISTS idx_gc_trackid  ON gender_classifications(track_id, session_id);

-- ----------------------------------------------------------
-- 5. direction_events
--    Emitted when a track's dominant movement direction is
--    confirmed (after 8+ frames of history).
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS direction_events (
    id          BIGSERIAL   PRIMARY KEY,
    session_id  INTEGER     NOT NULL REFERENCES sessions(id),
    track_id    VARCHAR(10) NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    direction   VARCHAR(25) NOT NULL,   -- e.g. 'LEFT → RIGHT'
    class_label VARCHAR(20) NOT NULL,
    start_x     INTEGER     NOT NULL,
    start_y     INTEGER     NOT NULL,
    end_x       INTEGER     NOT NULL,
    end_y       INTEGER     NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_de_session ON direction_events(session_id);

-- ----------------------------------------------------------
-- 6. line_crossings
--    One row each time a track crosses a virtual counting line.
--    direction = 'entry' or 'exit'
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS line_crossings (
    id           BIGSERIAL    PRIMARY KEY,
    session_id   INTEGER      NOT NULL REFERENCES sessions(id),
    track_id     VARCHAR(10)  NOT NULL,
    line_label   VARCHAR(100) NOT NULL,
    crossed_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    direction    VARCHAR(10)  NOT NULL,
    class_label  VARCHAR(20)  NOT NULL,
    centroid_x   INTEGER      NOT NULL,
    centroid_y   INTEGER      NOT NULL,
    frame_number BIGINT       NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lc_session    ON line_crossings(session_id);
CREATE INDEX IF NOT EXISTS idx_lc_crossed_at ON line_crossings(crossed_at);
CREATE INDEX IF NOT EXISTS idx_lc_direction  ON line_crossings(direction);

-- ----------------------------------------------------------
-- 7. zone_events
--    One row per zone enter or exit event per track.
--    duration_seconds is set on exit events only.
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS zone_events (
    id               BIGSERIAL    PRIMARY KEY,
    session_id       INTEGER      NOT NULL REFERENCES sessions(id),
    track_id         VARCHAR(10)  NOT NULL,
    zone_label       VARCHAR(100) NOT NULL,
    event_type       VARCHAR(10)  NOT NULL,   -- 'enter' or 'exit'
    occurred_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    class_label      VARCHAR(20)  NOT NULL,
    frame_number     BIGINT       NOT NULL,
    duration_seconds REAL
);
CREATE INDEX IF NOT EXISTS idx_ze_session    ON zone_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ze_zone_label ON zone_events(zone_label);

-- ----------------------------------------------------------
-- 8. occupancy_snapshots
--    Periodic snapshot of live occupancy metrics.
--    Written every 60 seconds by default.
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS occupancy_snapshots (
    id                    BIGSERIAL PRIMARY KEY,
    session_id            INTEGER   NOT NULL REFERENCES sessions(id),
    recorded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    current_people        INTEGER   NOT NULL DEFAULT 0,
    current_vehicles      INTEGER   NOT NULL DEFAULT 0,
    peak_people_session   INTEGER   NOT NULL DEFAULT 0,
    peak_vehicles_session INTEGER   NOT NULL DEFAULT 0,
    avg_people_window     REAL      NOT NULL DEFAULT 0.0,
    avg_vehicles_window   REAL      NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_os_session  ON occupancy_snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_os_recorded ON occupancy_snapshots(recorded_at);

-- ----------------------------------------------------------
-- 9. vehicle_counts
--    Hourly vehicle counts by type.
--    bucket_start is truncated to the hour boundary.
--    UPSERT-safe via the UNIQUE constraint.
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS vehicle_counts (
    id           BIGSERIAL   PRIMARY KEY,
    session_id   INTEGER     NOT NULL REFERENCES sessions(id),
    bucket_start TIMESTAMPTZ NOT NULL,
    cars         INTEGER     NOT NULL DEFAULT 0,
    motorcycles  INTEGER     NOT NULL DEFAULT 0,
    buses        INTEGER     NOT NULL DEFAULT 0,
    trucks       INTEGER     NOT NULL DEFAULT 0,
    bicycles     INTEGER     NOT NULL DEFAULT 0,
    UNIQUE (session_id, bucket_start)
);
CREATE INDEX IF NOT EXISTS idx_vc_session ON vehicle_counts(session_id);
CREATE INDEX IF NOT EXISTS idx_vc_bucket  ON vehicle_counts(bucket_start);

-- ----------------------------------------------------------
-- 10. error_events
--     Structured error log written on any module exception.
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS error_events (
    id          BIGSERIAL   PRIMARY KEY,
    session_id  INTEGER     REFERENCES sessions(id),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    severity    VARCHAR(10) NOT NULL,   -- 'WARNING', 'ERROR', 'CRITICAL'
    module      VARCHAR(50) NOT NULL,
    message     TEXT        NOT NULL,
    traceback   TEXT
);
CREATE INDEX IF NOT EXISTS idx_ee_session  ON error_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ee_occurred ON error_events(occurred_at);

-- ----------------------------------------------------------
-- 11. system_health_snapshots
--     Periodic CPU/RAM/FPS snapshot.
--     Written every 30 seconds by default.
-- ----------------------------------------------------------
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
