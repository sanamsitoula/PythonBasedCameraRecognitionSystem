-- =============================================================================
-- EVAP Phase 4 Schema - 001_schema.sql
-- Enterprise Video Analytics Platform
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- PostGIS for POINT type (optional, falls back to float pair if not available)
-- CREATE EXTENSION IF NOT EXISTS postgis;

-- =============================================================================
-- ROLES
-- =============================================================================
CREATE TABLE IF NOT EXISTS roles (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(64) NOT NULL UNIQUE,
    permissions JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- USERS
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(64) NOT NULL UNIQUE,
    email           VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    role            VARCHAR(64) NOT NULL DEFAULT 'viewer' REFERENCES roles(name) ON UPDATE CASCADE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    mfa_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login      TIMESTAMPTZ
);

-- =============================================================================
-- API KEYS
-- =============================================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id          SERIAL PRIMARY KEY,
    key_hash    VARCHAR(255) NOT NULL UNIQUE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(128) NOT NULL,
    permissions JSONB NOT NULL DEFAULT '{}',
    expires_at  TIMESTAMPTZ,
    last_used   TIMESTAMPTZ,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- SITE MASTER
-- =============================================================================
CREATE TABLE IF NOT EXISTS site_master (
    site_id    SERIAL PRIMARY KEY,
    name       VARCHAR(128) NOT NULL,
    address    TEXT,
    city       VARCHAR(100),
    country    VARCHAR(100),
    timezone   VARCHAR(64) NOT NULL DEFAULT 'UTC',
    -- Stored as (longitude, latitude) decimal degrees
    coord_lat  DOUBLE PRECISION,
    coord_lon  DOUBLE PRECISION,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- BUILDING MASTER
-- =============================================================================
CREATE TABLE IF NOT EXISTS building_master (
    building_id    SERIAL PRIMARY KEY,
    site_id        INTEGER NOT NULL REFERENCES site_master(site_id) ON DELETE CASCADE,
    name           VARCHAR(128) NOT NULL,
    floors_count   INTEGER NOT NULL DEFAULT 1 CHECK (floors_count >= 1),
    description    TEXT,
    floor_plan_url TEXT
);

-- =============================================================================
-- FLOOR MASTER
-- =============================================================================
CREATE TABLE IF NOT EXISTS floor_master (
    floor_id      SERIAL PRIMARY KEY,
    building_id   INTEGER NOT NULL REFERENCES building_master(building_id) ON DELETE CASCADE,
    floor_number  INTEGER NOT NULL,
    name          VARCHAR(128),
    map_image_url TEXT,
    width_meters  NUMERIC(8, 2),
    height_meters NUMERIC(8, 2),
    UNIQUE (building_id, floor_number)
);

-- =============================================================================
-- ZONE MASTER
-- =============================================================================
CREATE TABLE IF NOT EXISTS zone_master (
    zone_id       SERIAL PRIMARY KEY,
    floor_id      INTEGER NOT NULL REFERENCES floor_master(floor_id) ON DELETE CASCADE,
    name          VARCHAR(128) NOT NULL,
    zone_type     VARCHAR(64) NOT NULL DEFAULT 'general'
                  CHECK (zone_type IN ('general','entrance','exit','restricted','parking','canteen','office','corridor','stairwell','elevator','lobby','server_room','warehouse')),
    polygon       JSONB,          -- Array of {x, y} coordinate objects
    max_capacity  INTEGER CHECK (max_capacity > 0),
    is_restricted BOOLEAN NOT NULL DEFAULT FALSE,
    color_code    VARCHAR(7)      -- hex color e.g. #FF5733
);

-- =============================================================================
-- CAMERA MASTER
-- =============================================================================
CREATE TABLE IF NOT EXISTS camera_master (
    camera_id          SERIAL PRIMARY KEY,
    site_id            INTEGER REFERENCES site_master(site_id) ON DELETE SET NULL,
    building_id        INTEGER REFERENCES building_master(building_id) ON DELETE SET NULL,
    floor_id           INTEGER REFERENCES floor_master(floor_id) ON DELETE SET NULL,
    zone_id            INTEGER REFERENCES zone_master(zone_id) ON DELETE SET NULL,
    name               VARCHAR(128) NOT NULL,
    rtsp_url_encrypted TEXT,       -- stored encrypted
    camera_type        VARCHAR(32) NOT NULL DEFAULT 'fixed'
                       CHECK (camera_type IN ('fixed','ptz','fisheye','thermal','anpr','360')),
    resolution         VARCHAR(16),  -- e.g. "1920x1080"
    fps                INTEGER CHECK (fps > 0 AND fps <= 120),
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    ai_enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    status             VARCHAR(32) NOT NULL DEFAULT 'offline'
                       CHECK (status IN ('online','offline','error','maintenance')),
    last_heartbeat     TIMESTAMPTZ,
    ip_address         INET,
    manufacturer       VARCHAR(64),
    model              VARCHAR(64),
    installed_at       DATE,
    location_x         NUMERIC(10, 4),  -- floor map coordinates
    location_y         NUMERIC(10, 4),
    direction_degrees  NUMERIC(5, 2) CHECK (direction_degrees >= 0 AND direction_degrees < 360)
);

-- =============================================================================
-- CAMERA STREAMS
-- =============================================================================
CREATE TABLE IF NOT EXISTS camera_streams (
    stream_id         SERIAL PRIMARY KEY,
    camera_id         INTEGER NOT NULL REFERENCES camera_master(camera_id) ON DELETE CASCADE,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at          TIMESTAMPTZ,
    frames_processed  BIGINT NOT NULL DEFAULT 0,
    detections_count  BIGINT NOT NULL DEFAULT 0,
    avg_fps           NUMERIC(5, 2),
    status            VARCHAR(32) NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','stopped','error')),
    error_message     TEXT
);

-- =============================================================================
-- FACE MASTER (Phase 4 extended face records, complements Phase 3)
-- =============================================================================
CREATE TABLE IF NOT EXISTS face_master (
    face_id     SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employee_master(employee_id) ON DELETE CASCADE,
    image_path  TEXT NOT NULL,
    quality_score NUMERIC(5, 4) CHECK (quality_score >= 0 AND quality_score <= 1),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

-- =============================================================================
-- VEHICLE MASTER
-- =============================================================================
CREATE TABLE IF NOT EXISTS vehicle_master (
    vehicle_id      SERIAL PRIMARY KEY,
    plate_number    VARCHAR(32) NOT NULL,
    plate_country   VARCHAR(4) NOT NULL DEFAULT 'IN',
    vehicle_type    VARCHAR(16) NOT NULL DEFAULT 'car'
                    CHECK (vehicle_type IN ('car','bus','truck','motorcycle','bicycle')),
    owner_id        INTEGER,            -- FK resolved at app level (employee or visitor)
    owner_type      VARCHAR(16)
                    CHECK (owner_type IN ('employee','visitor','unknown')),
    color           VARCHAR(32),
    make            VARCHAR(64),
    model_name      VARCHAR(64),
    is_whitelisted  BOOLEAN NOT NULL DEFAULT FALSE,
    is_blacklisted  BOOLEAN NOT NULL DEFAULT FALSE,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (plate_number, plate_country),
    CHECK (NOT (is_whitelisted AND is_blacklisted))
);

-- =============================================================================
-- LICENSE PLATE LOG
-- =============================================================================
CREATE TABLE IF NOT EXISTS license_plate_log (
    log_id                   BIGSERIAL PRIMARY KEY,
    camera_id                INTEGER REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    vehicle_id               INTEGER REFERENCES vehicle_master(vehicle_id) ON DELETE SET NULL,
    plate_number             VARCHAR(32) NOT NULL,
    plate_confidence         NUMERIC(5, 4) CHECK (plate_confidence >= 0 AND plate_confidence <= 1),
    vehicle_type             VARCHAR(16)
                             CHECK (vehicle_type IN ('car','bus','truck','motorcycle','bicycle')),
    entry_time               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exit_time                TIMESTAMPTZ,
    parking_duration_seconds INTEGER CHECK (parking_duration_seconds >= 0),
    snapshot_path            TEXT,
    direction                VARCHAR(16)
                             CHECK (direction IN ('entry','exit','unknown')),
    site_id                  INTEGER REFERENCES site_master(site_id) ON DELETE SET NULL
);

-- =============================================================================
-- OCCUPANCY LOG
-- =============================================================================
CREATE TABLE IF NOT EXISTS occupancy_log (
    log_id           BIGSERIAL PRIMARY KEY,
    camera_id        INTEGER REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    zone_id          INTEGER REFERENCES zone_master(zone_id) ON DELETE SET NULL,
    snapshot_time    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    people_count     INTEGER NOT NULL DEFAULT 0 CHECK (people_count >= 0),
    employees_count  INTEGER NOT NULL DEFAULT 0 CHECK (employees_count >= 0),
    visitors_count   INTEGER NOT NULL DEFAULT 0 CHECK (visitors_count >= 0),
    max_capacity     INTEGER CHECK (max_capacity > 0),
    occupancy_pct    NUMERIC(5, 2) CHECK (occupancy_pct >= 0 AND occupancy_pct <= 100)
);

-- =============================================================================
-- ZONE HISTORY (person zone transitions)
-- =============================================================================
CREATE TABLE IF NOT EXISTS zone_history (
    history_id       BIGSERIAL PRIMARY KEY,
    person_id        INTEGER NOT NULL,
    person_type      VARCHAR(16) NOT NULL
                     CHECK (person_type IN ('employee','visitor','unknown')),
    zone_id          INTEGER REFERENCES zone_master(zone_id) ON DELETE SET NULL,
    camera_id        INTEGER REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    entry_time       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exit_time        TIMESTAMPTZ,
    duration_seconds INTEGER CHECK (duration_seconds >= 0)
);

-- =============================================================================
-- ALERT LOG
-- =============================================================================
CREATE TABLE IF NOT EXISTS alert_log (
    alert_id          BIGSERIAL PRIMARY KEY,
    alert_type        VARCHAR(64) NOT NULL,
    severity          VARCHAR(16) NOT NULL DEFAULT 'info'
                      CHECK (severity IN ('info','warning','critical','emergency')),
    site_id           INTEGER REFERENCES site_master(site_id) ON DELETE SET NULL,
    camera_id         INTEGER REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    person_id         INTEGER,
    vehicle_id        INTEGER REFERENCES vehicle_master(vehicle_id) ON DELETE SET NULL,
    zone_id           INTEGER REFERENCES zone_master(zone_id) ON DELETE SET NULL,
    message           TEXT NOT NULL,
    details           JSONB,
    is_acknowledged   BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    acknowledged_at   TIMESTAMPTZ,
    snapshot_path     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- NOTIFICATION LOG
-- =============================================================================
CREATE TABLE IF NOT EXISTS notification_log (
    notif_id      BIGSERIAL PRIMARY KEY,
    alert_id      BIGINT REFERENCES alert_log(alert_id) ON DELETE CASCADE,
    channel       VARCHAR(16) NOT NULL
                  CHECK (channel IN ('email','sms','whatsapp','push','dashboard')),
    recipient     VARCHAR(255) NOT NULL,
    status        VARCHAR(16) NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','sent','failed','delivered')),
    sent_at       TIMESTAMPTZ,
    error_message TEXT
);

-- =============================================================================
-- ANALYTICS DAILY
-- =============================================================================
CREATE TABLE IF NOT EXISTS analytics_daily (
    id               SERIAL PRIMARY KEY,
    date             DATE NOT NULL,
    site_id          INTEGER REFERENCES site_master(site_id) ON DELETE CASCADE,
    total_entries    INTEGER NOT NULL DEFAULT 0,
    total_exits      INTEGER NOT NULL DEFAULT 0,
    peak_occupancy   INTEGER NOT NULL DEFAULT 0,
    avg_occupancy    NUMERIC(8, 2) NOT NULL DEFAULT 0,
    total_employees  INTEGER NOT NULL DEFAULT 0,
    total_visitors   INTEGER NOT NULL DEFAULT 0,
    total_vehicles   INTEGER NOT NULL DEFAULT 0,
    unique_visitors  INTEGER NOT NULL DEFAULT 0,
    late_arrivals    INTEGER NOT NULL DEFAULT 0,
    calculated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (date, site_id)
);

-- =============================================================================
-- ANALYTICS MONTHLY
-- =============================================================================
CREATE TABLE IF NOT EXISTS analytics_monthly (
    id                    SERIAL PRIMARY KEY,
    year                  SMALLINT NOT NULL CHECK (year >= 2000 AND year <= 2100),
    month                 SMALLINT NOT NULL CHECK (month >= 1 AND month <= 12),
    site_id               INTEGER REFERENCES site_master(site_id) ON DELETE CASCADE,
    working_days          SMALLINT NOT NULL DEFAULT 0,
    total_attendance      INTEGER NOT NULL DEFAULT 0,
    avg_daily_attendance  NUMERIC(8, 2) NOT NULL DEFAULT 0,
    total_visitors        INTEGER NOT NULL DEFAULT 0,
    total_vehicles        INTEGER NOT NULL DEFAULT 0,
    calculated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (year, month, site_id)
);

-- =============================================================================
-- SYSTEM HEALTH
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_health (
    metric_id          BIGSERIAL PRIMARY KEY,
    timestamp          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cpu_pct            NUMERIC(5, 2) NOT NULL CHECK (cpu_pct >= 0 AND cpu_pct <= 100),
    ram_pct            NUMERIC(5, 2) NOT NULL CHECK (ram_pct >= 0 AND ram_pct <= 100),
    gpu_pct            NUMERIC(5, 2)           CHECK (gpu_pct >= 0 AND gpu_pct <= 100),
    disk_pct           NUMERIC(5, 2) NOT NULL CHECK (disk_pct >= 0 AND disk_pct <= 100),
    active_cameras     INTEGER NOT NULL DEFAULT 0,
    dropped_frames     BIGINT NOT NULL DEFAULT 0,
    queue_depth        INTEGER NOT NULL DEFAULT 0,
    db_connections     INTEGER NOT NULL DEFAULT 0,
    redis_connected    BOOLEAN NOT NULL DEFAULT FALSE,
    rabbitmq_connected BOOLEAN NOT NULL DEFAULT FALSE
);

-- =============================================================================
-- API LOG
-- =============================================================================
CREATE TABLE IF NOT EXISTS api_log (
    log_id       BIGSERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    api_key_id   INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    method       VARCHAR(8) NOT NULL CHECK (method IN ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS')),
    endpoint     TEXT NOT NULL,
    status_code  SMALLINT NOT NULL,
    duration_ms  INTEGER,
    ip_address   INET,
    request_body JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- ERP SYNC LOG
-- =============================================================================
CREATE TABLE IF NOT EXISTS erp_sync_log (
    sync_id       BIGSERIAL PRIMARY KEY,
    erp_type      VARCHAR(64) NOT NULL,    -- e.g. 'SAP','Oracle','Workday'
    entity_type   VARCHAR(64) NOT NULL,    -- e.g. 'employee','attendance'
    entity_id     VARCHAR(128) NOT NULL,
    direction     VARCHAR(8) NOT NULL CHECK (direction IN ('inbound','outbound')),
    status        VARCHAR(16) NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','success','failed','partial')),
    payload       JSONB,
    error_message TEXT,
    synced_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- WATCHLIST
-- =============================================================================
CREATE TABLE IF NOT EXISTS watchlist (
    entry_id    SERIAL PRIMARY KEY,
    person_type VARCHAR(16) NOT NULL
                CHECK (person_type IN ('employee','visitor','unknown')),
    person_id   INTEGER,
    reason      TEXT NOT NULL,
    severity    VARCHAR(16) NOT NULL DEFAULT 'warning'
                CHECK (severity IN ('info','warning','critical','emergency')),
    added_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

-- =============================================================================
-- BEHAVIOR EVENTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS behavior_events (
    event_id         BIGSERIAL PRIMARY KEY,
    camera_id        INTEGER REFERENCES camera_master(camera_id) ON DELETE SET NULL,
    zone_id          INTEGER REFERENCES zone_master(zone_id) ON DELETE SET NULL,
    event_type       VARCHAR(32) NOT NULL
                     CHECK (event_type IN ('loitering','running','abandoned_object','crowding','tailgating')),
    person_id        INTEGER,
    confidence       NUMERIC(5, 4) CHECK (confidence >= 0 AND confidence <= 1),
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at         TIMESTAMPTZ,
    snapshot_path    TEXT,
    alert_generated  BOOLEAN NOT NULL DEFAULT FALSE
);

-- =============================================================================
-- REPORTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS reports (
    report_id    SERIAL PRIMARY KEY,
    report_type  VARCHAR(64) NOT NULL,
    title        VARCHAR(255) NOT NULL,
    format       VARCHAR(8) NOT NULL DEFAULT 'pdf'
                 CHECK (format IN ('pdf','excel','csv')),
    generated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    file_path    TEXT,
    parameters   JSONB,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ
);

-- =============================================================================
-- UPDATED_AT trigger function (reusable)
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
