-- =============================================================================
-- EVAP Phase 4 Indexes - 002_indexes.sql
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- users
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_users_email       ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role        ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_is_active   ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_users_last_login  ON users(last_login DESC NULLS LAST);

-- ─────────────────────────────────────────────────────────────────────────────
-- api_keys
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_api_keys_user_id     ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash    ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_is_active   ON api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_api_keys_expires_at  ON api_keys(expires_at)
    WHERE expires_at IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- site_master
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_site_master_is_active ON site_master(is_active);
CREATE INDEX IF NOT EXISTS idx_site_master_country   ON site_master(country);

-- ─────────────────────────────────────────────────────────────────────────────
-- building_master
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_building_master_site_id ON building_master(site_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- floor_master
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_floor_master_building_id ON floor_master(building_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- zone_master
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_zone_master_floor_id      ON zone_master(floor_id);
CREATE INDEX IF NOT EXISTS idx_zone_master_zone_type     ON zone_master(zone_type);
CREATE INDEX IF NOT EXISTS idx_zone_master_is_restricted ON zone_master(is_restricted)
    WHERE is_restricted = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- camera_master
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_camera_master_site_id        ON camera_master(site_id);
CREATE INDEX IF NOT EXISTS idx_camera_master_building_id    ON camera_master(building_id);
CREATE INDEX IF NOT EXISTS idx_camera_master_floor_id       ON camera_master(floor_id);
CREATE INDEX IF NOT EXISTS idx_camera_master_zone_id        ON camera_master(zone_id);
CREATE INDEX IF NOT EXISTS idx_camera_master_is_active      ON camera_master(is_active);
CREATE INDEX IF NOT EXISTS idx_camera_master_status         ON camera_master(status);
CREATE INDEX IF NOT EXISTS idx_camera_master_ai_enabled     ON camera_master(ai_enabled)
    WHERE ai_enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_camera_master_last_heartbeat ON camera_master(last_heartbeat DESC NULLS LAST);
-- Composite: active cameras per site
CREATE INDEX IF NOT EXISTS idx_camera_master_site_active
    ON camera_master(site_id, is_active)
    WHERE is_active = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- camera_streams
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_camera_streams_camera_id   ON camera_streams(camera_id);
CREATE INDEX IF NOT EXISTS idx_camera_streams_status      ON camera_streams(status);
CREATE INDEX IF NOT EXISTS idx_camera_streams_started_at  ON camera_streams(started_at DESC);
-- Partial: currently active streams
CREATE INDEX IF NOT EXISTS idx_camera_streams_active
    ON camera_streams(camera_id, started_at)
    WHERE status = 'active';

-- ─────────────────────────────────────────────────────────────────────────────
-- face_master
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_face_master_employee_id ON face_master(employee_id);
CREATE INDEX IF NOT EXISTS idx_face_master_is_active   ON face_master(is_active);
CREATE INDEX IF NOT EXISTS idx_face_master_created_at  ON face_master(created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- vehicle_master
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_vehicle_master_plate_number   ON vehicle_master(plate_number);
CREATE INDEX IF NOT EXISTS idx_vehicle_master_vehicle_type   ON vehicle_master(vehicle_type);
CREATE INDEX IF NOT EXISTS idx_vehicle_master_is_whitelisted ON vehicle_master(is_whitelisted)
    WHERE is_whitelisted = TRUE;
CREATE INDEX IF NOT EXISTS idx_vehicle_master_is_blacklisted ON vehicle_master(is_blacklisted)
    WHERE is_blacklisted = TRUE;
CREATE INDEX IF NOT EXISTS idx_vehicle_master_owner          ON vehicle_master(owner_id, owner_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- license_plate_log
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_lp_log_camera_id    ON license_plate_log(camera_id);
CREATE INDEX IF NOT EXISTS idx_lp_log_vehicle_id   ON license_plate_log(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_lp_log_site_id      ON license_plate_log(site_id);
CREATE INDEX IF NOT EXISTS idx_lp_log_plate_number ON license_plate_log(plate_number);
CREATE INDEX IF NOT EXISTS idx_lp_log_entry_time   ON license_plate_log(entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_lp_log_direction    ON license_plate_log(direction);
-- Composite: site + time range queries
CREATE INDEX IF NOT EXISTS idx_lp_log_site_entry
    ON license_plate_log(site_id, entry_time DESC);
-- Partial: vehicles still inside (no exit recorded)
CREATE INDEX IF NOT EXISTS idx_lp_log_no_exit
    ON license_plate_log(site_id, entry_time)
    WHERE exit_time IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- occupancy_log
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_occupancy_log_camera_id     ON occupancy_log(camera_id);
CREATE INDEX IF NOT EXISTS idx_occupancy_log_zone_id       ON occupancy_log(zone_id);
CREATE INDEX IF NOT EXISTS idx_occupancy_log_snapshot_time ON occupancy_log(snapshot_time DESC);
-- Composite: zone + time for time-series queries
CREATE INDEX IF NOT EXISTS idx_occupancy_log_zone_time
    ON occupancy_log(zone_id, snapshot_time DESC);
-- Partial: over-capacity alerts
CREATE INDEX IF NOT EXISTS idx_occupancy_log_over_capacity
    ON occupancy_log(zone_id, snapshot_time)
    WHERE occupancy_pct >= 100;

-- ─────────────────────────────────────────────────────────────────────────────
-- zone_history
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_zone_history_person      ON zone_history(person_id, person_type);
CREATE INDEX IF NOT EXISTS idx_zone_history_zone_id     ON zone_history(zone_id);
CREATE INDEX IF NOT EXISTS idx_zone_history_camera_id   ON zone_history(camera_id);
CREATE INDEX IF NOT EXISTS idx_zone_history_entry_time  ON zone_history(entry_time DESC);
-- Composite: person + time
CREATE INDEX IF NOT EXISTS idx_zone_history_person_time
    ON zone_history(person_id, entry_time DESC);
-- Partial: still inside (no exit)
CREATE INDEX IF NOT EXISTS idx_zone_history_active
    ON zone_history(zone_id, person_id)
    WHERE exit_time IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- alert_log
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_alert_log_alert_type      ON alert_log(alert_type);
CREATE INDEX IF NOT EXISTS idx_alert_log_severity        ON alert_log(severity);
CREATE INDEX IF NOT EXISTS idx_alert_log_site_id         ON alert_log(site_id);
CREATE INDEX IF NOT EXISTS idx_alert_log_camera_id       ON alert_log(camera_id);
CREATE INDEX IF NOT EXISTS idx_alert_log_zone_id         ON alert_log(zone_id);
CREATE INDEX IF NOT EXISTS idx_alert_log_vehicle_id      ON alert_log(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_alert_log_created_at      ON alert_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_log_acknowledged_by ON alert_log(acknowledged_by);
-- Partial: unacknowledged alerts
CREATE INDEX IF NOT EXISTS idx_alert_log_unacked
    ON alert_log(severity, created_at DESC)
    WHERE is_acknowledged = FALSE;
-- Composite: site + severity + time
CREATE INDEX IF NOT EXISTS idx_alert_log_site_severity_time
    ON alert_log(site_id, severity, created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- notification_log
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_notification_log_alert_id ON notification_log(alert_id);
CREATE INDEX IF NOT EXISTS idx_notification_log_channel  ON notification_log(channel);
CREATE INDEX IF NOT EXISTS idx_notification_log_status   ON notification_log(status);
CREATE INDEX IF NOT EXISTS idx_notification_log_sent_at  ON notification_log(sent_at DESC);
-- Partial: failed notifications for retry
CREATE INDEX IF NOT EXISTS idx_notification_log_failed
    ON notification_log(channel, sent_at)
    WHERE status = 'failed';

-- ─────────────────────────────────────────────────────────────────────────────
-- analytics_daily
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_analytics_daily_date         ON analytics_daily(date DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_daily_site_id      ON analytics_daily(site_id);
CREATE INDEX IF NOT EXISTS idx_analytics_daily_calculated_at ON analytics_daily(calculated_at DESC);
-- Composite: site + date range (primary query pattern)
CREATE INDEX IF NOT EXISTS idx_analytics_daily_site_date
    ON analytics_daily(site_id, date DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- analytics_monthly
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_analytics_monthly_site_id ON analytics_monthly(site_id);
CREATE INDEX IF NOT EXISTS idx_analytics_monthly_year_month
    ON analytics_monthly(year DESC, month DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_monthly_site_period
    ON analytics_monthly(site_id, year DESC, month DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- system_health
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_system_health_timestamp ON system_health(timestamp DESC);
-- Partial: high CPU alerts
CREATE INDEX IF NOT EXISTS idx_system_health_high_cpu
    ON system_health(timestamp DESC)
    WHERE cpu_pct >= 90;
-- Partial: high RAM alerts
CREATE INDEX IF NOT EXISTS idx_system_health_high_ram
    ON system_health(timestamp DESC)
    WHERE ram_pct >= 90;

-- ─────────────────────────────────────────────────────────────────────────────
-- api_log
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_api_log_user_id     ON api_log(user_id);
CREATE INDEX IF NOT EXISTS idx_api_log_api_key_id  ON api_log(api_key_id);
CREATE INDEX IF NOT EXISTS idx_api_log_created_at  ON api_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_log_status_code ON api_log(status_code);
CREATE INDEX IF NOT EXISTS idx_api_log_endpoint    ON api_log(endpoint);
-- Partial: errors only
CREATE INDEX IF NOT EXISTS idx_api_log_errors
    ON api_log(created_at DESC)
    WHERE status_code >= 400;

-- ─────────────────────────────────────────────────────────────────────────────
-- erp_sync_log
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_erp_sync_log_erp_type    ON erp_sync_log(erp_type);
CREATE INDEX IF NOT EXISTS idx_erp_sync_log_entity_type ON erp_sync_log(entity_type);
CREATE INDEX IF NOT EXISTS idx_erp_sync_log_status      ON erp_sync_log(status);
CREATE INDEX IF NOT EXISTS idx_erp_sync_log_synced_at   ON erp_sync_log(synced_at DESC);
CREATE INDEX IF NOT EXISTS idx_erp_sync_log_entity
    ON erp_sync_log(entity_type, entity_id);
-- Partial: failed syncs
CREATE INDEX IF NOT EXISTS idx_erp_sync_log_failed
    ON erp_sync_log(erp_type, synced_at DESC)
    WHERE status = 'failed';

-- ─────────────────────────────────────────────────────────────────────────────
-- watchlist
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_watchlist_person      ON watchlist(person_id, person_type);
CREATE INDEX IF NOT EXISTS idx_watchlist_is_active   ON watchlist(is_active);
CREATE INDEX IF NOT EXISTS idx_watchlist_severity    ON watchlist(severity);
CREATE INDEX IF NOT EXISTS idx_watchlist_added_by    ON watchlist(added_by);
CREATE INDEX IF NOT EXISTS idx_watchlist_expires_at  ON watchlist(expires_at)
    WHERE expires_at IS NOT NULL;
-- Partial: active watchlist entries
CREATE INDEX IF NOT EXISTS idx_watchlist_active_persons
    ON watchlist(person_type, person_id)
    WHERE is_active = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- behavior_events
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_behavior_events_camera_id       ON behavior_events(camera_id);
CREATE INDEX IF NOT EXISTS idx_behavior_events_zone_id         ON behavior_events(zone_id);
CREATE INDEX IF NOT EXISTS idx_behavior_events_event_type      ON behavior_events(event_type);
CREATE INDEX IF NOT EXISTS idx_behavior_events_person_id       ON behavior_events(person_id);
CREATE INDEX IF NOT EXISTS idx_behavior_events_started_at      ON behavior_events(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_behavior_events_alert_generated ON behavior_events(alert_generated)
    WHERE alert_generated = TRUE;
-- Composite: camera + type + time
CREATE INDEX IF NOT EXISTS idx_behavior_events_camera_type_time
    ON behavior_events(camera_id, event_type, started_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- reports
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_reports_generated_by   ON reports(generated_by);
CREATE INDEX IF NOT EXISTS idx_reports_report_type    ON reports(report_type);
CREATE INDEX IF NOT EXISTS idx_reports_generated_at   ON reports(generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_expires_at     ON reports(expires_at)
    WHERE expires_at IS NOT NULL;
