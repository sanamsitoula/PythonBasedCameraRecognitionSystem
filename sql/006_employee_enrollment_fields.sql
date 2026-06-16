-- Migration 006: add enrollment tracking fields to employee_master
-- Run once against cctv_analytics database

ALTER TABLE employee_master
    ADD COLUMN IF NOT EXISTS notes             TEXT,
    ADD COLUMN IF NOT EXISTS enrollment_status VARCHAR(20) NOT NULL DEFAULT 'not_started',
    ADD COLUMN IF NOT EXISTS enrollment_error  TEXT,
    ADD COLUMN IF NOT EXISTS photo_count       INTEGER     NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS photo_paths       JSONB       NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE employee_master
    DROP CONSTRAINT IF EXISTS ck_em_enrollment_status;

ALTER TABLE employee_master
    ADD CONSTRAINT ck_em_enrollment_status
        CHECK (enrollment_status IN ('not_started', 'pending', 'enrolled', 'failed'));

CREATE INDEX IF NOT EXISTS idx_em_enrollment_status
    ON employee_master (enrollment_status);
