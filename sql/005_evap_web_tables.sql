-- =============================================================================
-- sql/005_evap_web_tables.sql
-- EVAP Web Platform tables for cctv_analytics database
--
-- PURPOSE:
--   This script extends cctv_analytics with two types of changes:
--   1. ALTER TABLE  – adds EVAP-specific columns to existing Phase 3 tables
--   2. CREATE TABLE – creates new EVAP-only tables (auth, site hierarchy, etc.)
--
-- PREREQUISITES:
--   schema.sql and schema_p3.sql must have been run first.
--   All changes use IF NOT EXISTS / safe DDL, so this is idempotent.
--
-- Run:
--   psql -h localhost -U cctv_user -d cctv_analytics -f sql/005_evap_web_tables.sql
-- =============================================================================

-- ---------------------------------------------------------------------------
-- PART 1: Extend existing Phase 3 tables with EVAP columns
-- ---------------------------------------------------------------------------

-- employee_master
ALTER TABLE employee_master ADD COLUMN IF NOT EXISTS employee_code  VARCHAR(32);
ALTER TABLE employee_master ADD COLUMN IF NOT EXISTS email          VARCHAR(255);
ALTER TABLE employee_master ADD COLUMN IF NOT EXISTS phone          VARCHAR(20);
ALTER TABLE employee_master ADD COLUMN IF NOT EXISTS is_active      BOOLEAN NOT NULL DEFAULT TRUE;

-- employee_face_master
ALTER TABLE employee_face_master ADD COLUMN IF NOT EXISTS is_primary     BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE employee_face_master ADD COLUMN IF NOT EXISTS quality_score  NUMERIC(5,4);

-- face_embeddings
ALTER TABLE face_embeddings ADD COLUMN IF NOT EXISTS model_name  VARCHAR(64);

-- visitor_master
ALTER TABLE visitor_master ADD COLUMN IF NOT EXISTS full_name    VARCHAR(128);
ALTER TABLE visitor_master ADD COLUMN IF NOT EXISTS phone        VARCHAR(20);
ALTER TABLE visitor_master ADD COLUMN IF NOT EXISTS email        VARCHAR(255);
ALTER TABLE visitor_master ADD COLUMN IF NOT EXISTS id_type      VARCHAR(32);
ALTER TABLE visitor_master ADD COLUMN IF NOT EXISTS id_number    VARCHAR(64);
ALTER TABLE visitor_master ADD COLUMN IF NOT EXISTS photo_path   TEXT;
ALTER TABLE visitor_master ADD COLUMN IF NOT EXISTS company      VARCHAR(128);
ALTER TABLE visitor_master ADD COLUMN IF NOT EXISTS is_active    BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE visitor_master ADD COLUMN IF NOT EXISTS created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- visitor_tracking
ALTER TABLE visitor_tracking ADD COLUMN IF NOT EXISTS host_employee_id  VARCHAR(50);
ALTER TABLE visitor_tracking ADD COLUMN IF NOT EXISTS purpose           VARCHAR(255);
ALTER TABLE visitor_tracking ADD COLUMN IF NOT EXISTS badge_number      VARCHAR(32);
ALTER TABLE visitor_tracking ADD COLUMN IF NOT EXISTS status            VARCHAR(16) NOT NULL DEFAULT 'active';
ALTER TABLE visitor_tracking ADD COLUMN IF NOT EXISTS approved_by       VARCHAR(100);

-- attendance_log
ALTER TABLE attendance_log ADD COLUMN IF NOT EXISTS work_hours   NUMERIC(5,2);
ALTER TABLE attendance_log ADD COLUMN IF NOT EXISTS remarks      TEXT;
ALTER TABLE attendance_log ADD COLUMN IF NOT EXISTS created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- ---------------------------------------------------------------------------
-- PART 2: New EVAP-only tables (do not exist in Phase 2/3 schema)
-- ---------------------------------------------------------------------------

-- 1. roles  (RBAC)
CREATE TABLE IF NOT EXISTS roles (
    id          SERIAL      PRIMARY KEY,
    name        VARCHAR(64) NOT NULL UNIQUE,
    permissions JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO roles (name, permissions) VALUES
    ('admin',    '{"all": true}'),
    ('operator', '{"view": true, "alerts": true}'),
    ('viewer',   '{"view": true}')
ON CONFLICT (name) DO NOTHING;

-- 2. users  (web platform accounts)
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL      PRIMARY KEY,
    username        VARCHAR(64) NOT NULL UNIQUE,
    email           VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    role            VARCHAR(64) NOT NULL DEFAULT 'viewer'
                        REFERENCES roles(name) ON UPDATE CASCADE,
    full_name       VARCHAR(128),
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    mfa_enabled     BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login      TIMESTAMPTZ
);
-- Default admin user (password: admin123 — CHANGE IMMEDIATELY after first login)
INSERT INTO users (username, email, hashed_password, role, full_name)
VALUES (
    'admin',
    'admin@evap.local',
    '$2b$12$LKghShvIWaEMWlR3dEMoNuVixpKBBxQb/pkrxAW3ZYqGxv/saMiCC',  -- bcrypt of 'admin123'
    'admin',
    'System Administrator'
) ON CONFLICT (username) DO NOTHING;

-- 3. api_keys
CREATE TABLE IF NOT EXISTS api_keys (
    id          SERIAL      PRIMARY KEY,
    key_hash    VARCHAR(255) NOT NULL UNIQUE,
    user_id     INT         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(128) NOT NULL,
    permissions JSONB       NOT NULL DEFAULT '{}',
    expires_at  TIMESTAMPTZ,
    last_used   TIMESTAMPTZ,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. site_master
CREATE TABLE IF NOT EXISTS site_master (
    site_id    SERIAL      PRIMARY KEY,
    name       VARCHAR(128) NOT NULL,
    address    TEXT,
    city       VARCHAR(100),
    country    VARCHAR(100),
    timezone   VARCHAR(64) NOT NULL DEFAULT 'Asia/Kathmandu',
    coord_lat  DOUBLE PRECISION,
    coord_lon  DOUBLE PRECISION,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO site_master (name, city, country, timezone)
VALUES ('Main Site', 'Kathmandu', 'Nepal', 'Asia/Kathmandu')
ON CONFLICT DO NOTHING;

-- 5. building_master
CREATE TABLE IF NOT EXISTS building_master (
    building_id  SERIAL      PRIMARY KEY,
    site_id      INT         NOT NULL REFERENCES site_master(site_id) ON DELETE CASCADE,
    name         VARCHAR(128) NOT NULL,
    floors_count INT         NOT NULL DEFAULT 1,
    description  TEXT,
    floor_plan_url TEXT,
    CONSTRAINT ck_building_floors CHECK (floors_count >= 1)
);

-- 6. floor_master
CREATE TABLE IF NOT EXISTS floor_master (
    floor_id       SERIAL      PRIMARY KEY,
    building_id    INT         NOT NULL REFERENCES building_master(building_id) ON DELETE CASCADE,
    floor_number   INT         NOT NULL,
    name           VARCHAR(128),
    map_image_url  TEXT,
    width_meters   NUMERIC(8,2),
    height_meters  NUMERIC(8,2),
    UNIQUE (building_id, floor_number)
);

-- 7. zone_master  (structured zones with capacity; different from the VARCHAR zone_id in CCTV tables)
CREATE TABLE IF NOT EXISTS zone_master (
    zone_id       SERIAL      PRIMARY KEY,
    floor_id      INT         NOT NULL REFERENCES floor_master(floor_id) ON DELETE CASCADE,
    name          VARCHAR(128) NOT NULL,
    zone_type     VARCHAR(64) NOT NULL DEFAULT 'general',
    polygon       JSONB,
    max_capacity  INT,
    is_restricted BOOLEAN     NOT NULL DEFAULT FALSE,
    color_code    VARCHAR(7),
    CONSTRAINT ck_zone_type CHECK (
        zone_type IN ('general','entrance','exit','restricted','parking','canteen',
                      'office','corridor','stairwell','elevator','lobby','server_room','warehouse')
    ),
    CONSTRAINT ck_zone_capacity CHECK (max_capacity IS NULL OR max_capacity > 0)
);

-- 8. camera_master  (structured camera registry; different from cctv_analytics.cameras)
CREATE TABLE IF NOT EXISTS camera_master (
    camera_id         SERIAL      PRIMARY KEY,
    site_id           INT         REFERENCES site_master(site_id) ON DELETE SET NULL,
    building_id       INT         REFERENCES building_master(building_id) ON DELETE SET NULL,
    floor_id          INT         REFERENCES floor_master(floor_id) ON DELETE SET NULL,
    zone_id           INT         REFERENCES zone_master(zone_id) ON DELETE SET NULL,
    name              VARCHAR(128) NOT NULL,
    rtsp_url_encrypted TEXT,
    camera_type       VARCHAR(32) NOT NULL DEFAULT 'fixed',
    resolution        VARCHAR(16),
    fps               INT,
    is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
    ai_enabled        BOOLEAN     NOT NULL DEFAULT TRUE,
    status            VARCHAR(32) NOT NULL DEFAULT 'offline',
    last_heartbeat    TIMESTAMPTZ,
    ip_address        VARCHAR(45),
    manufacturer      VARCHAR(64),
    model             VARCHAR(64),
    installed_at      DATE,
    CONSTRAINT ck_camera_type   CHECK (camera_type IN ('fixed','ptz','fisheye','thermal','anpr','360')),
    CONSTRAINT ck_camera_status CHECK (status IN ('online','offline','error','maintenance')),
    CONSTRAINT ck_camera_fps    CHECK (fps IS NULL OR (fps > 0 AND fps <= 120))
);

-- 9. camera_streams
CREATE TABLE IF NOT EXISTS camera_streams (
    stream_id         SERIAL      PRIMARY KEY,
    camera_id         INT         NOT NULL REFERENCES camera_master(camera_id) ON DELETE CASCADE,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at          TIMESTAMPTZ,
    frames_processed  BIGINT      NOT NULL DEFAULT 0,
    detections_count  BIGINT      NOT NULL DEFAULT 0,
    avg_fps           NUMERIC(5,2),
    status            VARCHAR(32) NOT NULL DEFAULT 'active',
    error_message     TEXT,
    CONSTRAINT ck_stream_status CHECK (status IN ('active','stopped','error'))
);

-- 10. face_master  (Phase 4 extended face records)
CREATE TABLE IF NOT EXISTS face_master (
    face_id       SERIAL      PRIMARY KEY,
    employee_id   VARCHAR(50) REFERENCES employee_master(employee_id) ON DELETE CASCADE,
    image_path    TEXT        NOT NULL,
    quality_score NUMERIC(5,4),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_face_master_quality CHECK (
        quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)
    )
);

-- 11. alert_log  (EVAP web-platform alert store; different from cctv_analytics.smart_alerts)
CREATE TABLE IF NOT EXISTS alert_log (
    alert_id        BIGSERIAL   PRIMARY KEY,
    alert_type      VARCHAR(64) NOT NULL,
    severity        VARCHAR(16) NOT NULL DEFAULT 'info',
    site_id         INT         REFERENCES site_master(site_id) ON DELETE SET NULL,
    camera_id       INT         REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    person_id       INT,
    vehicle_id      INT,
    zone_id         INT         REFERENCES zone_master(zone_id) ON DELETE SET NULL,
    message         TEXT        NOT NULL,
    details         JSONB,
    is_acknowledged BOOLEAN     NOT NULL DEFAULT FALSE,
    acknowledged_by INT         REFERENCES users(id) ON DELETE SET NULL,
    acknowledged_at TIMESTAMPTZ,
    snapshot_path   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_alert_severity CHECK (severity IN ('info','warning','critical','emergency'))
);

-- 12. notification_log
CREATE TABLE IF NOT EXISTS notification_log (
    notif_id      BIGSERIAL   PRIMARY KEY,
    alert_id      BIGINT      REFERENCES alert_log(alert_id) ON DELETE CASCADE,
    channel       VARCHAR(16) NOT NULL,
    recipient     VARCHAR(255) NOT NULL,
    status        VARCHAR(16) NOT NULL DEFAULT 'pending',
    sent_at       TIMESTAMPTZ,
    error_message TEXT,
    CONSTRAINT ck_notif_channel CHECK (channel IN ('email','sms','whatsapp','push','dashboard')),
    CONSTRAINT ck_notif_status  CHECK (status IN ('pending','sent','failed','delivered'))
);

-- 13. watchlist
CREATE TABLE IF NOT EXISTS watchlist (
    entry_id    SERIAL      PRIMARY KEY,
    person_type VARCHAR(16) NOT NULL,
    person_id   INT,
    reason      TEXT        NOT NULL,
    severity    VARCHAR(16) NOT NULL DEFAULT 'warning',
    added_by    INT         REFERENCES users(id) ON DELETE SET NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_watchlist_person_type CHECK (person_type IN ('employee','visitor','unknown')),
    CONSTRAINT ck_watchlist_severity    CHECK (severity IN ('info','warning','critical','emergency'))
);

-- 14. occupancy_log  (EVAP structured occupancy; different from cctv_analytics.occupancy_snapshots)
CREATE TABLE IF NOT EXISTS occupancy_log (
    log_id          BIGSERIAL   PRIMARY KEY,
    camera_id       INT         REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    zone_id         INT         REFERENCES zone_master(zone_id) ON DELETE SET NULL,
    snapshot_time   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    people_count    INT         NOT NULL DEFAULT 0,
    employees_count INT         NOT NULL DEFAULT 0,
    visitors_count  INT         NOT NULL DEFAULT 0,
    max_capacity    INT,
    occupancy_pct   NUMERIC(5,2),
    CONSTRAINT ck_occ_people    CHECK (people_count >= 0),
    CONSTRAINT ck_occ_employees CHECK (employees_count >= 0),
    CONSTRAINT ck_occ_visitors  CHECK (visitors_count >= 0),
    CONSTRAINT ck_occ_capacity  CHECK (max_capacity IS NULL OR max_capacity > 0),
    CONSTRAINT ck_occ_pct       CHECK (occupancy_pct IS NULL OR (occupancy_pct >= 0 AND occupancy_pct <= 100))
);

-- 15. zone_history  (general movement log per zone_master zone)
CREATE TABLE IF NOT EXISTS zone_history (
    history_id       BIGSERIAL   PRIMARY KEY,
    person_id        INT         NOT NULL,
    person_type      VARCHAR(16) NOT NULL,
    zone_id          INT         REFERENCES zone_master(zone_id) ON DELETE SET NULL,
    camera_id        INT         REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    entry_time       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exit_time        TIMESTAMPTZ,
    duration_seconds INT,
    CONSTRAINT ck_zh_person_type CHECK (person_type IN ('employee','visitor','unknown')),
    CONSTRAINT ck_zh_duration    CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
);

-- 16. analytics_daily
CREATE TABLE IF NOT EXISTS analytics_daily (
    id               SERIAL  PRIMARY KEY,
    date             DATE    NOT NULL,
    site_id          INT     REFERENCES site_master(site_id) ON DELETE CASCADE,
    total_entries    INT     NOT NULL DEFAULT 0,
    total_exits      INT     NOT NULL DEFAULT 0,
    peak_occupancy   INT     NOT NULL DEFAULT 0,
    avg_occupancy    NUMERIC(8,2) NOT NULL DEFAULT 0,
    total_employees  INT     NOT NULL DEFAULT 0,
    total_visitors   INT     NOT NULL DEFAULT 0,
    total_vehicles   INT     NOT NULL DEFAULT 0,
    unique_visitors  INT     NOT NULL DEFAULT 0,
    late_arrivals    INT     NOT NULL DEFAULT 0,
    calculated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (date, site_id)
);

-- 17. analytics_monthly
CREATE TABLE IF NOT EXISTS analytics_monthly (
    id                    SERIAL       PRIMARY KEY,
    year                  SMALLINT     NOT NULL,
    month                 SMALLINT     NOT NULL,
    site_id               INT          REFERENCES site_master(site_id) ON DELETE CASCADE,
    working_days          SMALLINT     NOT NULL DEFAULT 0,
    total_attendance      INT          NOT NULL DEFAULT 0,
    avg_daily_attendance  NUMERIC(8,2) NOT NULL DEFAULT 0,
    total_visitors        INT          NOT NULL DEFAULT 0,
    total_vehicles        INT          NOT NULL DEFAULT 0,
    calculated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (year, month, site_id),
    CONSTRAINT ck_am_year  CHECK (year >= 2000 AND year <= 2100),
    CONSTRAINT ck_am_month CHECK (month >= 1 AND month <= 12)
);

-- 18. behavior_events
CREATE TABLE IF NOT EXISTS behavior_events (
    event_id        BIGSERIAL   PRIMARY KEY,
    camera_id       INT         REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    zone_id         INT         REFERENCES zone_master(zone_id) ON DELETE SET NULL,
    event_type      VARCHAR(32) NOT NULL,
    person_id       INT,
    confidence      NUMERIC(5,4),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    snapshot_path   TEXT,
    alert_generated BOOLEAN     NOT NULL DEFAULT FALSE,
    CONSTRAINT ck_be_event_type CHECK (
        event_type IN ('loitering','running','abandoned_object','crowding','tailgating')
    ),
    CONSTRAINT ck_be_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

-- 19. system_health  (EVAP detailed health metrics; different from cctv_analytics.system_health_snapshots)
CREATE TABLE IF NOT EXISTS system_health (
    metric_id          BIGSERIAL   PRIMARY KEY,
    timestamp          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cpu_pct            NUMERIC(5,2) NOT NULL,
    ram_pct            NUMERIC(5,2) NOT NULL,
    gpu_pct            NUMERIC(5,2),
    disk_pct           NUMERIC(5,2) NOT NULL,
    active_cameras     INT         NOT NULL DEFAULT 0,
    dropped_frames     BIGINT      NOT NULL DEFAULT 0,
    queue_depth        INT         NOT NULL DEFAULT 0,
    db_connections     INT         NOT NULL DEFAULT 0,
    redis_connected    BOOLEAN     NOT NULL DEFAULT FALSE,
    rabbitmq_connected BOOLEAN     NOT NULL DEFAULT FALSE,
    CONSTRAINT ck_sh_cpu  CHECK (cpu_pct  >= 0 AND cpu_pct  <= 100),
    CONSTRAINT ck_sh_ram  CHECK (ram_pct  >= 0 AND ram_pct  <= 100),
    CONSTRAINT ck_sh_gpu  CHECK (gpu_pct  IS NULL OR (gpu_pct  >= 0 AND gpu_pct  <= 100)),
    CONSTRAINT ck_sh_disk CHECK (disk_pct >= 0 AND disk_pct <= 100)
);

-- 20. api_log
CREATE TABLE IF NOT EXISTS api_log (
    log_id       BIGSERIAL    PRIMARY KEY,
    user_id      INT          REFERENCES users(id) ON DELETE SET NULL,
    api_key_id   INT          REFERENCES api_keys(id) ON DELETE SET NULL,
    method       VARCHAR(8)   NOT NULL,
    endpoint     TEXT         NOT NULL,
    status_code  SMALLINT     NOT NULL,
    duration_ms  INT,
    ip_address   VARCHAR(45),
    request_body JSONB,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_api_method CHECK (
        method IN ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS')
    )
);

-- 21. evap_audit_log  (separate from cctv_analytics.audit_log which the CCTV engine uses)
CREATE TABLE IF NOT EXISTS evap_audit_log (
    audit_id    SERIAL       PRIMARY KEY,
    user_id     INT          REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(64)  NOT NULL,
    entity_type VARCHAR(64),
    entity_id   VARCHAR(128),
    old_value   JSONB,
    new_value   JSONB,
    ip_address  VARCHAR(45),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 22. erp_sync_log
CREATE TABLE IF NOT EXISTS erp_sync_log (
    sync_id       BIGSERIAL   PRIMARY KEY,
    erp_type      VARCHAR(64) NOT NULL,
    entity_type   VARCHAR(64) NOT NULL,
    entity_id     VARCHAR(128) NOT NULL,
    direction     VARCHAR(8)  NOT NULL,
    status        VARCHAR(16) NOT NULL DEFAULT 'pending',
    payload       JSONB,
    error_message TEXT,
    synced_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_erp_dir    CHECK (direction IN ('inbound','outbound')),
    CONSTRAINT ck_erp_status CHECK (status IN ('pending','success','failed','partial'))
);

-- 23. reports
CREATE TABLE IF NOT EXISTS reports (
    report_id    SERIAL       PRIMARY KEY,
    report_type  VARCHAR(64)  NOT NULL,
    title        VARCHAR(255) NOT NULL,
    format       VARCHAR(8)   NOT NULL DEFAULT 'pdf',
    generated_by INT          REFERENCES users(id) ON DELETE SET NULL,
    file_path    TEXT,
    parameters   JSONB,
    generated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ,
    CONSTRAINT ck_report_format CHECK (format IN ('pdf','excel','csv'))
);

-- 24. vehicle_master
CREATE TABLE IF NOT EXISTS vehicle_master (
    vehicle_id      SERIAL      PRIMARY KEY,
    plate_number    VARCHAR(32) NOT NULL,
    plate_country   VARCHAR(4)  NOT NULL DEFAULT 'NP',
    vehicle_type    VARCHAR(16) NOT NULL DEFAULT 'car',
    owner_id        INT,
    owner_type      VARCHAR(16),
    color           VARCHAR(32),
    make            VARCHAR(64),
    model_name      VARCHAR(64),
    is_whitelisted  BOOLEAN     NOT NULL DEFAULT FALSE,
    is_blacklisted  BOOLEAN     NOT NULL DEFAULT FALSE,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_vm_vehicle_type  CHECK (vehicle_type IN ('car','bus','truck','motorcycle','bicycle')),
    CONSTRAINT ck_vm_owner_type    CHECK (owner_type IS NULL OR owner_type IN ('employee','visitor','unknown')),
    CONSTRAINT ck_vm_not_both      CHECK (NOT (is_whitelisted AND is_blacklisted))
);

-- 25. license_plate_log
CREATE TABLE IF NOT EXISTS license_plate_log (
    log_id                  BIGSERIAL   PRIMARY KEY,
    camera_id               INT         REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    vehicle_id              INT         REFERENCES vehicle_master(vehicle_id) ON DELETE SET NULL,
    plate_number            VARCHAR(32) NOT NULL,
    plate_confidence        NUMERIC(5,4),
    vehicle_type            VARCHAR(16),
    entry_time              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exit_time               TIMESTAMPTZ,
    parking_duration_seconds INT,
    snapshot_path           TEXT,
    direction               VARCHAR(16),
    site_id                 INT         REFERENCES site_master(site_id) ON DELETE SET NULL,
    CONSTRAINT ck_lpl_vehicle_type CHECK (
        vehicle_type IS NULL OR vehicle_type IN ('car','bus','truck','motorcycle','bicycle')
    ),
    CONSTRAINT ck_lpl_direction    CHECK (direction IS NULL OR direction IN ('entry','exit','unknown')),
    CONSTRAINT ck_lpl_confidence   CHECK (plate_confidence IS NULL OR (plate_confidence >= 0 AND plate_confidence <= 1)),
    CONSTRAINT ck_lpl_duration     CHECK (parking_duration_seconds IS NULL OR parking_duration_seconds >= 0)
);

-- 26. detections  (raw YOLO detections linked to camera_master)
CREATE TABLE IF NOT EXISTS detections (
    id          BIGSERIAL   PRIMARY KEY,
    camera_id   INT         REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    class_label VARCHAR(50),
    confidence  FLOAT,
    bbox        JSONB,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 27. heatmap_data
CREATE TABLE IF NOT EXISTS heatmap_data (
    id          BIGSERIAL   PRIMARY KEY,
    zone_id     INT         REFERENCES zone_master(zone_id) ON DELETE SET NULL,
    camera_id   INT         REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    heat_value  FLOAT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 28. notification_settings
CREATE TABLE IF NOT EXISTS notification_settings (
    id       SERIAL  PRIMARY KEY,
    user_id  INT     REFERENCES users(id) ON DELETE CASCADE,
    channel  VARCHAR(50),
    enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    settings JSONB
);

-- 29. erp_config
CREATE TABLE IF NOT EXISTS erp_config (
    id          SERIAL       PRIMARY KEY,
    erp_name    VARCHAR(100),
    api_url     TEXT,
    api_key     VARCHAR(255),
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    last_synced TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- Indexes for new tables
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_users_username    ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email       ON users(email);
CREATE INDEX IF NOT EXISTS idx_api_keys_user_id  ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_camera_master_status ON camera_master(status);
CREATE INDEX IF NOT EXISTS idx_camera_master_site   ON camera_master(site_id);
CREATE INDEX IF NOT EXISTS idx_alert_log_severity   ON alert_log(severity);
CREATE INDEX IF NOT EXISTS idx_alert_log_acked       ON alert_log(is_acknowledged);
CREATE INDEX IF NOT EXISTS idx_alert_log_created     ON alert_log(created_at);
CREATE INDEX IF NOT EXISTS idx_occupancy_log_time    ON occupancy_log(snapshot_time);
CREATE INDEX IF NOT EXISTS idx_system_health_time    ON system_health(timestamp);
CREATE INDEX IF NOT EXISTS idx_api_log_user          ON api_log(user_id);
CREATE INDEX IF NOT EXISTS idx_api_log_created       ON api_log(created_at);
CREATE INDEX IF NOT EXISTS idx_evap_audit_user       ON evap_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_evap_audit_created    ON evap_audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_daily_date  ON analytics_daily(date);
CREATE INDEX IF NOT EXISTS idx_vehicle_master_plate  ON vehicle_master(plate_number);
CREATE INDEX IF NOT EXISTS idx_lpl_plate             ON license_plate_log(plate_number);
CREATE INDEX IF NOT EXISTS idx_lpl_entry_time        ON license_plate_log(entry_time);
CREATE INDEX IF NOT EXISTS idx_watchlist_active      ON watchlist(is_active);

-- ---------------------------------------------------------------------------
-- Verification
-- ---------------------------------------------------------------------------
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(quote_ident(tablename))) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
