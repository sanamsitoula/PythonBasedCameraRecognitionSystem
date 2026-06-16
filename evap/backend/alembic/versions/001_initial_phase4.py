"""Initial Phase 4 EVAP schema

Creates all Phase 4 tables: visitors, canteen entries, cross-camera re-ID
tracks, reports, audit logs, zones, zone events, and supporting lookup tables.
Phase 3 tables (cameras, employees, attendance, alerts, persons) are expected
to already exist (created by Phase 3 migrations or SQL scripts).

Revision ID: 001
Revises: None (first Phase 4 migration)
Create Date: 2026-06-15 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "001_initial_phase4"
down_revision = None          # Set to Phase 3 final revision ID if chaining
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # ── Enum types ─────────────────────────────────────────────────────────────
    visitor_status = postgresql.ENUM(
        "pre_registered", "checked_in", "checked_out", "denied", "overstay",
        name="visitor_status_enum",
        create_type=False
    )
    visitor_status.create(op.get_bind(), checkfirst=True)

    report_status = postgresql.ENUM(
        "pending", "generating", "ready", "failed", "expired",
        name="report_status_enum",
        create_type=False
    )
    report_status.create(op.get_bind(), checkfirst=True)

    report_type = postgresql.ENUM(
        "attendance_daily", "attendance_monthly", "visitor_log",
        "alert_summary", "crowd_analytics", "canteen_usage",
        "employee_presence", "custom",
        name="report_type_enum",
        create_type=False
    )
    report_type.create(op.get_bind(), checkfirst=True)

    zone_event_type = postgresql.ENUM(
        "entry", "exit", "dwell", "loitering", "overcrowding",
        name="zone_event_type_enum",
        create_type=False
    )
    zone_event_type.create(op.get_bind(), checkfirst=True)

    # ── Zones ──────────────────────────────────────────────────────────────────
    op.create_table(
        "zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True),
        sa.Column("polygon", postgresql.JSONB, nullable=True,
                  comment="List of [x,y] pixel coordinates defining zone boundary"),
        sa.Column("max_capacity", sa.Integer, nullable=True),
        sa.Column("alert_on_overcrowd", sa.Boolean, server_default="true"),
        sa.Column("dwell_alert_seconds", sa.Integer, nullable=True,
                  comment="Alert if person dwells longer than this"),
        sa.Column("restricted", sa.Boolean, server_default="false",
                  comment="Restricted zone — alert on any entry"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_zones_camera_id", "zones", ["camera_id"])
    op.create_index("ix_zones_is_active", "zones", ["is_active"])

    # ── Zone Events ────────────────────────────────────────────────────────────
    op.create_table(
        "zone_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("persons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.Enum(name="zone_event_type_enum"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("dwell_seconds", sa.Float, nullable=True),
        sa.Column("snapshot_path", sa.String(500), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("metadata", postgresql.JSONB, server_default="'{}'"),
    )
    op.create_index("ix_zone_events_zone_id", "zone_events", ["zone_id"])
    op.create_index("ix_zone_events_occurred_at", "zone_events", ["occurred_at"])
    op.create_index("ix_zone_events_person_id", "zone_events", ["person_id"])

    # ── Visitors ───────────────────────────────────────────────────────────────
    op.create_table(
        "visitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("id_type", sa.String(50), nullable=True,
                  comment="passport | national_id | driver_license"),
        sa.Column("id_number", sa.String(100), nullable=True),
        sa.Column("company", sa.String(200), nullable=True),
        sa.Column("face_encoding", postgresql.ARRAY(sa.Float), nullable=True,
                  comment="128-d face encoding vector"),
        sa.Column("photo_path", sa.String(500), nullable=True),
        sa.Column("blacklisted", sa.Boolean, server_default="false"),
        sa.Column("blacklist_reason", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_visitors_email", "visitors", ["email"])
    op.create_index("ix_visitors_phone", "visitors", ["phone"])
    op.create_index("ix_visitors_blacklisted", "visitors", ["blacklisted"])
    op.create_index("ix_visitors_full_name_trgm", "visitors",
                    ["full_name"], postgresql_using="gin",
                    postgresql_ops={"full_name": "gin_trgm_ops"})

    # ── Visitor Sessions ───────────────────────────────────────────────────────
    op.create_table(
        "visitor_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("visitor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("visitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("host_employee_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.Enum(name="visitor_status_enum"),
                  nullable=False, server_default="'pre_registered'"),
        sa.Column("purpose", sa.String(300), nullable=True),
        sa.Column("badge_number", sa.String(50), nullable=True),
        sa.Column("otp_code", sa.String(10), nullable=True),
        sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_camera_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True),
        sa.Column("exit_camera_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entry_snapshot_path", sa.String(500), nullable=True),
        sa.Column("exit_snapshot_path", sa.String(500), nullable=True),
        sa.Column("areas_visited", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_visitor_sessions_visitor_id", "visitor_sessions", ["visitor_id"])
    op.create_index("ix_visitor_sessions_status", "visitor_sessions", ["status"])
    op.create_index("ix_visitor_sessions_scheduled_at", "visitor_sessions", ["scheduled_at"])
    op.create_index("ix_visitor_sessions_checked_in_at", "visitor_sessions", ["checked_in_at"])

    # ── Canteen Entries ────────────────────────────────────────────────────────
    op.create_table(
        "canteen_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("persons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("visitor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("visitors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True),
        sa.Column("meal_type", sa.String(50), nullable=True,
                  comment="breakfast | lunch | dinner | snack"),
        sa.Column("entered_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("snapshot_path", sa.String(500), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("face_match", sa.Boolean, server_default="false"),
        sa.Column("metadata", postgresql.JSONB, server_default="'{}'"),
    )
    op.create_index("ix_canteen_entries_employee_id", "canteen_entries", ["employee_id"])
    op.create_index("ix_canteen_entries_entered_at", "canteen_entries", ["entered_at"])
    op.create_index("ix_canteen_entries_meal_type", "canteen_entries", ["meal_type"])

    # ── Cross-Camera Re-ID Tracks ──────────────────────────────────────────────
    op.create_table(
        "reid_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("persons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("track_id", sa.String(100), nullable=False,
                  comment="Internal short-term track ID from detection pipeline"),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True),
        sa.Column("appearance_embedding", postgresql.ARRAY(sa.Float), nullable=True,
                  comment="Re-ID embedding vector (e.g. 512-d OSNet)"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("frame_count", sa.Integer, server_default="1"),
        sa.Column("trajectory", postgresql.JSONB, nullable=True,
                  comment="List of {camera_id, bbox, timestamp} waypoints"),
        sa.Column("snapshot_path", sa.String(500), nullable=True),
        sa.Column("similarity_score", sa.Float, nullable=True),
        sa.Column("linked_track_ids", postgresql.ARRAY(sa.String), nullable=True,
                  comment="Track IDs from other cameras this was matched to"),
        sa.Column("metadata", postgresql.JSONB, server_default="'{}'"),
    )
    op.create_index("ix_reid_tracks_track_id", "reid_tracks", ["track_id"])
    op.create_index("ix_reid_tracks_person_id", "reid_tracks", ["person_id"])
    op.create_index("ix_reid_tracks_first_seen_at", "reid_tracks", ["first_seen_at"])
    op.create_index("ix_reid_tracks_last_seen_at", "reid_tracks", ["last_seen_at"])

    # ── Reports ────────────────────────────────────────────────────────────────
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("report_type", sa.Enum(name="report_type_enum"), nullable=False),
        sa.Column("status", sa.Enum(name="report_status_enum"),
                  nullable=False, server_default="'pending'"),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True,
                  comment="User ID who requested the report"),
        sa.Column("parameters", postgresql.JSONB, server_default="'{}'",
                  comment="Report generation parameters (date range, filters, etc.)"),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_reports_report_type", "reports", ["report_type"])
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index("ix_reports_created_at", "reports", ["created_at"])
    op.create_index("ix_reports_expires_at", "reports", ["expires_at"])

    # ── Audit Log ─────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("actor_id", sa.String(200), nullable=True,
                  comment="User/service that performed the action"),
        sa.Column("actor_type", sa.String(50), nullable=True,
                  comment="user | service | system"),
        sa.Column("action", sa.String(100), nullable=False,
                  comment="e.g. create_employee, delete_camera, export_report"),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(200), nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("before_state", postgresql.JSONB, nullable=True),
        sa.Column("after_state", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(20), server_default="'success'",
                  comment="success | failure"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource_type_id", "audit_logs",
                    ["resource_type", "resource_id"])
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])

    # ── Updated-at triggers ────────────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION evap_set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    for table in ("zones", "visitors", "visitor_sessions"):
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION evap_set_updated_at();
        """)


def downgrade() -> None:
    # Drop triggers
    for table in ("zones", "visitors", "visitor_sessions"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")
    op.execute("DROP FUNCTION IF EXISTS evap_set_updated_at()")

    # Drop tables in reverse dependency order
    for table in (
        "audit_logs",
        "reports",
        "reid_tracks",
        "canteen_entries",
        "visitor_sessions",
        "visitors",
        "zone_events",
        "zones",
    ):
        op.drop_table(table)

    # Drop enums
    for enum_name in (
        "zone_event_type_enum",
        "report_type_enum",
        "report_status_enum",
        "visitor_status_enum",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
