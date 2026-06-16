"""
System health, API logging, audit log, ERP sync, and report models.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User, ApiKey


class SystemHealth(Base):
    __tablename__ = "system_health"

    metric_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    cpu_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    ram_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    gpu_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    disk_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    active_cameras: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dropped_frames: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    queue_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    db_connections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    redis_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rabbitmq_connected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    __table_args__ = (
        CheckConstraint("cpu_pct >= 0 AND cpu_pct <= 100", name="ck_health_cpu"),
        CheckConstraint("ram_pct >= 0 AND ram_pct <= 100", name="ck_health_ram"),
        CheckConstraint("gpu_pct >= 0 AND gpu_pct <= 100", name="ck_health_gpu"),
        CheckConstraint("disk_pct >= 0 AND disk_pct <= 100", name="ck_health_disk"),
    )

    def __repr__(self) -> str:
        return (
            f"<SystemHealth metric_id={self.metric_id} "
            f"cpu={self.cpu_pct} ram={self.ram_pct} ts={self.timestamp}>"
        )


class ApiLog(Base):
    __tablename__ = "api_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    api_key_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
    )
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    request_body: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "method IN ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS')",
            name="ck_api_log_method",
        ),
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="api_logs")
    api_key: Mapped[Optional["ApiKey"]] = relationship(
        "ApiKey", back_populates="api_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<ApiLog log_id={self.log_id} "
            f"method={self.method!r} endpoint={self.endpoint!r} "
            f"status={self.status_code}>"
        )


class AuditLog(Base):
    """Reflects Phase 3 audit_log table."""
    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    old_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog audit_id={self.audit_id} "
            f"action={self.action!r} entity={self.entity_type!r}>"
        )


class ErpSyncLog(Base):
    __tablename__ = "erp_sync_log"

    sync_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    erp_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "direction IN ('inbound','outbound')", name="ck_erp_direction"
        ),
        CheckConstraint(
            "status IN ('pending','success','failed','partial')",
            name="ck_erp_status",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ErpSyncLog sync_id={self.sync_id} "
            f"erp={self.erp_type!r} entity={self.entity_type!r} "
            f"status={self.status!r}>"
        )


class Report(Base):
    __tablename__ = "reports"

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False, default="pdf")
    generated_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parameters: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "format IN ('pdf','excel','csv')", name="ck_report_format"
        ),
    )

    # Relationships
    generator: Mapped[Optional["User"]] = relationship(
        "User", back_populates="reports"
    )

    def __repr__(self) -> str:
        return (
            f"<Report report_id={self.report_id} "
            f"type={self.report_type!r} format={self.format!r}>"
        )
