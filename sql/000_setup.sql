-- =============================================================================
-- CCTV Analytics – Complete Database Setup Script
-- Run this ONCE as the PostgreSQL superuser (postgres).
--
-- Usage (PowerShell):
--   $env:PGPASSWORD = "your_postgres_password"
--   $psql = "C:\Program Files\PostgreSQL\15\bin\psql.exe"
--   & $psql -h localhost -U postgres -d postgres -f sql\000_setup.sql
--
-- What this script does:
--   1. Creates the cctv_user login role
--   2. Creates the cctv_analytics database
--   3. Grants all required privileges to cctv_user
--   4. Runs Phase 2 schema (schema.sql)
--   5. Runs Phase 3 schema (schema_p3.sql)
-- =============================================================================


-- -----------------------------------------------------------------------------
-- STEP 1: Create login role
-- -----------------------------------------------------------------------------
DO
$$
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_catalog.pg_roles WHERE rolname = 'cctv_user'
    ) THEN
        CREATE ROLE cctv_user LOGIN PASSWORD 'Nepal@123';
        RAISE NOTICE 'Role cctv_user created.';
    ELSE
        RAISE NOTICE 'Role cctv_user already exists – skipping.';
    END IF;
END
$$;


-- -----------------------------------------------------------------------------
-- STEP 2: Create database
-- NOTE: CREATE DATABASE cannot run inside a transaction block.
--       If the database already exists this statement will error; ignore it.
-- -----------------------------------------------------------------------------
-- Run manually if needed:
--   CREATE DATABASE cctv_analytics OWNER cctv_user;


-- -----------------------------------------------------------------------------
-- STEP 3: Switch to cctv_analytics and grant privileges
-- (Run the lines below after connecting to cctv_analytics)
-- -----------------------------------------------------------------------------
-- \c cctv_analytics

GRANT CONNECT ON DATABASE cctv_analytics TO cctv_user;
GRANT USAGE  ON SCHEMA public TO cctv_user;
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO cctv_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cctv_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES    TO cctv_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cctv_user;


-- =============================================================================
-- PHASE 2 SCHEMA
-- =============================================================================

-- ----------------------------------------------------------
-- 1. cameras
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
-- ----------------------------------------------------------
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
CREATE INDEX IF NOT EXISTS idx_gc_session ON gender_classifications(session_id);
CREATE INDEX IF NOT EXISTS idx_gc_trackid ON gender_classifications(track_id, session_id);

-- ----------------------------------------------------------
-- 5. direction_events
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS direction_events (
    id          BIGSERIAL   PRIMARY KEY,
    session_id  INTEGER     NOT NULL REFERENCES sessions(id),
    track_id    VARCHAR(10) NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    direction   VARCHAR(25) NOT NULL,
    class_label VARCHAR(20) NOT NULL,
    start_x     INTEGER     NOT NULL,
    start_y     INTEGER     NOT NULL,
    end_x       INTEGER     NOT NULL,
    end_y       INTEGER     NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_de_session ON direction_events(session_id);

-- ----------------------------------------------------------
-- 6. line_crossings
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
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS zone_events (
    id               BIGSERIAL    PRIMARY KEY,
    session_id       INTEGER      NOT NULL REFERENCES sessions(id),
    track_id         VARCHAR(10)  NOT NULL,
    zone_label       VARCHAR(100) NOT NULL,
    event_type       VARCHAR(10)  NOT NULL,
    occurred_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    class_label      VARCHAR(20)  NOT NULL,
    frame_number     BIGINT       NOT NULL,
    duration_seconds REAL
);
CREATE INDEX IF NOT EXISTS idx_ze_session    ON zone_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ze_zone_label ON zone_events(zone_label);

-- ----------------------------------------------------------
-- 8. occupancy_snapshots
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
-- ----------------------------------------------------------
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

-- ----------------------------------------------------------
-- 11. system_health_snapshots
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


-- =============================================================================
-- PHASE 3 SCHEMA
-- =============================================================================

-- ----------------------------------------------------------
-- 12. employee_master
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS employee_master (
    employee_id      VARCHAR(50)  PRIMARY KEY,
    employee_name    VARCHAR(200) NOT NULL,
    department       VARCHAR(100),
    designation      VARCHAR(100),
    status           VARCHAR(20)  NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'inactive', 'deleted')),
    work_start_time  TIME         NOT NULL DEFAULT '09:00:00',
    work_end_time    TIME         NOT NULL DEFAULT '18:00:00',
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_em_department ON employee_master(department);
CREATE INDEX IF NOT EXISTS idx_em_status     ON employee_master(status);

-- ----------------------------------------------------------
-- 13. employee_face_master
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS employee_face_master (
    face_master_id  SERIAL       PRIMARY KEY,
    employee_id     VARCHAR(50)  NOT NULL
                        REFERENCES employee_master(employee_id) ON DELETE CASCADE,
    image_count     INT          NOT NULL DEFAULT 0,
    last_enrolled   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    enrolled_by     VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_efm_employee_id ON employee_face_master(employee_id);

-- ----------------------------------------------------------
-- 14. face_embeddings
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS face_embeddings (
    embedding_id     BIGSERIAL    PRIMARY KEY,
    employee_id      VARCHAR(50)  NOT NULL
                         REFERENCES employee_master(employee_id) ON DELETE CASCADE,
    embedding_vector BYTEA        NOT NULL,
    image_path       TEXT,
    source_angle     VARCHAR(50),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fe_employee_id ON face_embeddings(employee_id);
CREATE INDEX IF NOT EXISTS idx_fe_created_at  ON face_embeddings(created_at);

-- ----------------------------------------------------------
-- 15. recognized_persons
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS recognized_persons (
    recognition_id      BIGSERIAL    PRIMARY KEY,
    session_id          INT,
    camera_id           VARCHAR(50),
    track_id            VARCHAR(50),
    employee_id         VARCHAR(50),
    visitor_id          VARCHAR(50),
    confidence          FLOAT,
    recognition_status  VARCHAR(20),
    recognized_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    frame_number        INT
);
CREATE INDEX IF NOT EXISTS idx_rp_session_id    ON recognized_persons(session_id);
CREATE INDEX IF NOT EXISTS idx_rp_employee_id   ON recognized_persons(employee_id);
CREATE INDEX IF NOT EXISTS idx_rp_recognized_at ON recognized_persons(recognized_at);

-- ----------------------------------------------------------
-- 16. visitor_master
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS visitor_master (
    visitor_id           VARCHAR(50)  PRIMARY KEY,
    first_seen_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_seen_at         TIMESTAMPTZ,
    face_snapshot_path   TEXT,
    total_visits         INT          NOT NULL DEFAULT 1,
    embedding_vector     BYTEA
);
CREATE INDEX IF NOT EXISTS idx_vm_first_seen_at ON visitor_master(first_seen_at);

-- ----------------------------------------------------------
-- 17. visitor_tracking
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS visitor_tracking (
    tracking_id       BIGSERIAL    PRIMARY KEY,
    visitor_id        VARCHAR(50)  NOT NULL
                          REFERENCES visitor_master(visitor_id) ON DELETE CASCADE,
    camera_id         VARCHAR(50),
    track_id          VARCHAR(50),
    zone_id           VARCHAR(100),
    entered_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    exited_at         TIMESTAMPTZ,
    duration_seconds  INT
);
CREATE INDEX IF NOT EXISTS idx_vt_visitor_id ON visitor_tracking(visitor_id);
CREATE INDEX IF NOT EXISTS idx_vt_entered_at ON visitor_tracking(entered_at);

-- ----------------------------------------------------------
-- 18. attendance_log
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS attendance_log (
    attendance_id            BIGSERIAL    PRIMARY KEY,
    employee_id              VARCHAR(50)  NOT NULL
                                 REFERENCES employee_master(employee_id) ON DELETE CASCADE,
    attendance_date          DATE         NOT NULL,
    first_entry              TIMESTAMPTZ,
    last_exit                TIMESTAMPTZ,
    working_duration_seconds INT          NOT NULL DEFAULT 0,
    break_duration_seconds   INT          NOT NULL DEFAULT 0,
    status                   VARCHAR(20)  NOT NULL DEFAULT 'present'
                                 CHECK (status IN ('present', 'late', 'half_day', 'absent')),
    is_late                  BOOLEAN      NOT NULL DEFAULT FALSE,
    UNIQUE (employee_id, attendance_date)
);
CREATE INDEX IF NOT EXISTS idx_al_employee_id     ON attendance_log(employee_id);
CREATE INDEX IF NOT EXISTS idx_al_attendance_date ON attendance_log(attendance_date);

-- ----------------------------------------------------------
-- 19. employee_zone_history
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS employee_zone_history (
    history_id        BIGSERIAL    PRIMARY KEY,
    employee_id       VARCHAR(50)  NOT NULL,
    camera_id         VARCHAR(50),
    zone_id           VARCHAR(100),
    zone_label        VARCHAR(200),
    entry_time        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    exit_time         TIMESTAMPTZ,
    duration_seconds  INT,
    visit_number      INT          NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_ezh_employee_id ON employee_zone_history(employee_id);
CREATE INDEX IF NOT EXISTS idx_ezh_entry_time  ON employee_zone_history(entry_time);

-- ----------------------------------------------------------
-- 20. canteen_visits
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS canteen_visits (
    visit_id          BIGSERIAL    PRIMARY KEY,
    person_id         VARCHAR(50),
    person_type       VARCHAR(20),
    entry_time        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    exit_time         TIMESTAMPTZ,
    duration_seconds  INT,
    meal_period       VARCHAR(20)  NOT NULL DEFAULT 'lunch',
    visit_date        DATE         NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cv_person_id  ON canteen_visits(person_id);
CREATE INDEX IF NOT EXISTS idx_cv_visit_date ON canteen_visits(visit_date);

-- ----------------------------------------------------------
-- 21. movement_history
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS movement_history (
    movement_id       BIGSERIAL    PRIMARY KEY,
    person_id         VARCHAR(50),
    person_type       VARCHAR(20),
    camera_id         VARCHAR(50),
    zone_id           VARCHAR(100),
    zone_label        VARCHAR(200),
    entry_time        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    exit_time         TIMESTAMPTZ,
    duration_seconds  INT,
    track_id          VARCHAR(50)
);
CREATE INDEX IF NOT EXISTS idx_mh_person_id  ON movement_history(person_id);
CREATE INDEX IF NOT EXISTS idx_mh_entry_time ON movement_history(entry_time);

-- ----------------------------------------------------------
-- 22. department_analytics
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS department_analytics (
    analytics_id       BIGSERIAL    PRIMARY KEY,
    department         VARCHAR(100),
    snapshot_time      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    employees_present  INT          NOT NULL DEFAULT 0,
    in_office          INT          NOT NULL DEFAULT 0,
    in_canteen         INT          NOT NULL DEFAULT 0,
    outside            INT          NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_da_department    ON department_analytics(department);
CREATE INDEX IF NOT EXISTS idx_da_snapshot_time ON department_analytics(snapshot_time);

-- ----------------------------------------------------------
-- 23. cross_camera_tracking
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS cross_camera_tracking (
    link_id     BIGSERIAL    PRIMARY KEY,
    unified_id  VARCHAR(50),
    camera_id   VARCHAR(50),
    track_id    VARCHAR(50),
    first_seen  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_seen   TIMESTAMPTZ,
    confidence  FLOAT
);
CREATE INDEX IF NOT EXISTS idx_cct_unified_id ON cross_camera_tracking(unified_id);
CREATE INDEX IF NOT EXISTS idx_cct_camera_id  ON cross_camera_tracking(camera_id);

-- ----------------------------------------------------------
-- 24. smart_alerts
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS smart_alerts (
    alert_id       BIGSERIAL    PRIMARY KEY,
    alert_type     VARCHAR(100),
    person_id      VARCHAR(50),
    camera_id      VARCHAR(50),
    zone_id        VARCHAR(100),
    severity       VARCHAR(20)  NOT NULL DEFAULT 'warning',
    message        TEXT,
    acknowledged   BOOLEAN      NOT NULL DEFAULT FALSE,
    snapshot_path  TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sa_severity   ON smart_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_sa_created_at ON smart_alerts(created_at);

-- ----------------------------------------------------------
-- 25. audit_log
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id    BIGSERIAL    PRIMARY KEY,
    action      VARCHAR(100),
    actor_id    VARCHAR(100),
    target_id   VARCHAR(100),
    details     JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_action     ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at);


-- =============================================================================
-- VERIFY
-- =============================================================================
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
