-- =============================================================================
-- schema_p3.sql  –  CCTV Phase 3 PostgreSQL DDL
-- All tables use CREATE TABLE IF NOT EXISTS; all indexes use IF NOT EXISTS.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. employee_master
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 2. employee_face_master
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employee_face_master (
    face_master_id  SERIAL       PRIMARY KEY,
    employee_id     VARCHAR(50)  NOT NULL
                        REFERENCES employee_master(employee_id) ON DELETE CASCADE,
    image_count     INT          NOT NULL DEFAULT 0,
    last_enrolled   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    enrolled_by     VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_efm_employee_id ON employee_face_master(employee_id);

-- ---------------------------------------------------------------------------
-- 3. face_embeddings
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 4. recognized_persons
-- ---------------------------------------------------------------------------
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

CREATE INDEX IF NOT EXISTS idx_rp_session_id   ON recognized_persons(session_id);
CREATE INDEX IF NOT EXISTS idx_rp_camera_id    ON recognized_persons(camera_id);
CREATE INDEX IF NOT EXISTS idx_rp_employee_id  ON recognized_persons(employee_id);
CREATE INDEX IF NOT EXISTS idx_rp_visitor_id   ON recognized_persons(visitor_id);
CREATE INDEX IF NOT EXISTS idx_rp_recognized_at ON recognized_persons(recognized_at);

-- ---------------------------------------------------------------------------
-- 5. visitor_master
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS visitor_master (
    visitor_id           VARCHAR(50)  PRIMARY KEY,
    first_seen_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_seen_at         TIMESTAMPTZ,
    face_snapshot_path   TEXT,
    total_visits         INT          NOT NULL DEFAULT 1,
    embedding_vector     BYTEA
);

CREATE INDEX IF NOT EXISTS idx_vm_first_seen_at ON visitor_master(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_vm_last_seen_at  ON visitor_master(last_seen_at);

-- ---------------------------------------------------------------------------
-- 6. visitor_tracking
-- ---------------------------------------------------------------------------
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

CREATE INDEX IF NOT EXISTS idx_vt_visitor_id  ON visitor_tracking(visitor_id);
CREATE INDEX IF NOT EXISTS idx_vt_camera_id   ON visitor_tracking(camera_id);
CREATE INDEX IF NOT EXISTS idx_vt_entered_at  ON visitor_tracking(entered_at);

-- ---------------------------------------------------------------------------
-- 7. attendance_log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attendance_log (
    attendance_id           BIGSERIAL    PRIMARY KEY,
    employee_id             VARCHAR(50)  NOT NULL
                                REFERENCES employee_master(employee_id) ON DELETE CASCADE,
    attendance_date         DATE         NOT NULL,
    first_entry             TIMESTAMPTZ,
    last_exit               TIMESTAMPTZ,
    working_duration_seconds INT         NOT NULL DEFAULT 0,
    break_duration_seconds   INT         NOT NULL DEFAULT 0,
    status                  VARCHAR(20)  NOT NULL DEFAULT 'present'
                                CHECK (status IN ('present', 'late', 'half_day', 'absent')),
    is_late                 BOOLEAN      NOT NULL DEFAULT FALSE,
    UNIQUE (employee_id, attendance_date)
);

CREATE INDEX IF NOT EXISTS idx_al_employee_id      ON attendance_log(employee_id);
CREATE INDEX IF NOT EXISTS idx_al_attendance_date  ON attendance_log(attendance_date);
CREATE INDEX IF NOT EXISTS idx_al_status           ON attendance_log(status);

-- ---------------------------------------------------------------------------
-- 8. employee_zone_history
-- ---------------------------------------------------------------------------
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
CREATE INDEX IF NOT EXISTS idx_ezh_camera_id   ON employee_zone_history(camera_id);
CREATE INDEX IF NOT EXISTS idx_ezh_zone_id     ON employee_zone_history(zone_id);
CREATE INDEX IF NOT EXISTS idx_ezh_entry_time  ON employee_zone_history(entry_time);

-- ---------------------------------------------------------------------------
-- 9. canteen_visits
-- ---------------------------------------------------------------------------
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

CREATE INDEX IF NOT EXISTS idx_cv_person_id   ON canteen_visits(person_id);
CREATE INDEX IF NOT EXISTS idx_cv_visit_date  ON canteen_visits(visit_date);
CREATE INDEX IF NOT EXISTS idx_cv_entry_time  ON canteen_visits(entry_time);
CREATE INDEX IF NOT EXISTS idx_cv_meal_period ON canteen_visits(meal_period);

-- ---------------------------------------------------------------------------
-- 10. movement_history
-- ---------------------------------------------------------------------------
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
CREATE INDEX IF NOT EXISTS idx_mh_camera_id  ON movement_history(camera_id);
CREATE INDEX IF NOT EXISTS idx_mh_zone_id    ON movement_history(zone_id);
CREATE INDEX IF NOT EXISTS idx_mh_entry_time ON movement_history(entry_time);

-- ---------------------------------------------------------------------------
-- 11. department_analytics
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 12. cross_camera_tracking
-- ---------------------------------------------------------------------------
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
CREATE INDEX IF NOT EXISTS idx_cct_first_seen ON cross_camera_tracking(first_seen);

-- ---------------------------------------------------------------------------
-- 13. smart_alerts
-- ---------------------------------------------------------------------------
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

CREATE INDEX IF NOT EXISTS idx_sa_alert_type   ON smart_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_sa_person_id    ON smart_alerts(person_id);
CREATE INDEX IF NOT EXISTS idx_sa_camera_id    ON smart_alerts(camera_id);
CREATE INDEX IF NOT EXISTS idx_sa_severity     ON smart_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_sa_acknowledged ON smart_alerts(acknowledged);
CREATE INDEX IF NOT EXISTS idx_sa_created_at   ON smart_alerts(created_at);

-- ---------------------------------------------------------------------------
-- 14. audit_log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id    BIGSERIAL    PRIMARY KEY,
    action      VARCHAR(100),
    actor_id    VARCHAR(100),
    target_id   VARCHAR(100),
    details     JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_action     ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_actor_id   ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_target_id  ON audit_log(target_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at);
