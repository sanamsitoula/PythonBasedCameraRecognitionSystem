"""
Visitor models — aligned with cctv_analytics Phase 3 schema.
EVAP extension columns are added by sql/005_evap_web_tables.sql via ALTER TABLE.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime,
    ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class VisitorMaster(Base):
    """Reflects cctv_analytics.visitor_master (Phase 3).
    PK is VARCHAR(50). EVAP adds full_name, phone, email, etc. via ALTER TABLE.
    """
    __tablename__ = "visitor_master"

    visitor_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    face_snapshot_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_visits: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # EVAP extension columns
    full_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    id_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    id_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    photo_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    tracking_records: Mapped[list["VisitorTracking"]] = relationship(
        "VisitorTracking", back_populates="visitor", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<VisitorMaster visitor_id={self.visitor_id!r} name={self.full_name!r}>"


class VisitorTracking(Base):
    """Reflects cctv_analytics.visitor_tracking (Phase 3).
    check_in_time → entered_at, check_out_time → exited_at (DB column aliases).
    """
    __tablename__ = "visitor_tracking"

    tracking_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    visitor_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("visitor_master.visitor_id", ondelete="CASCADE"),
        nullable=False,
    )
    camera_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    track_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zone_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    check_in_time: Mapped[Optional[datetime]] = mapped_column(
        "entered_at", DateTime(timezone=True), nullable=True
    )
    check_out_time: Mapped[Optional[datetime]] = mapped_column(
        "exited_at", DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # EVAP extension columns
    host_employee_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    purpose: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    badge_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    visitor: Mapped["VisitorMaster"] = relationship(
        "VisitorMaster", back_populates="tracking_records"
    )

    def __repr__(self) -> str:
        return f"<VisitorTracking tracking_id={self.tracking_id} visitor_id={self.visitor_id!r}>"
