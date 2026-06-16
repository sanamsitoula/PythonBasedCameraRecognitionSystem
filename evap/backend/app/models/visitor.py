"""
Visitor models — wraps Phase 3 visitor_master and visitor_tracking tables.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    pass


class VisitorMaster(Base):
    """Reflects the Phase 3 visitor_master table."""
    __tablename__ = "visitor_master"

    visitor_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    id_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    id_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    photo_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    tracking_records: Mapped[list["VisitorTracking"]] = relationship(
        "VisitorTracking", back_populates="visitor", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<VisitorMaster visitor_id={self.visitor_id} name={self.full_name!r}>"


class VisitorTracking(Base):
    """Reflects the Phase 3 visitor_tracking table."""
    __tablename__ = "visitor_tracking"

    tracking_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visitor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("visitor_master.visitor_id", ondelete="CASCADE"),
        nullable=False,
    )
    host_employee_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("employee_master.employee_id", ondelete="SET NULL"),
        nullable=True,
    )
    purpose: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    check_in_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    check_out_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    badge_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    visitor: Mapped["VisitorMaster"] = relationship(
        "VisitorMaster", back_populates="tracking_records"
    )

    def __repr__(self) -> str:
        return f"<VisitorTracking tracking_id={self.tracking_id} visitor_id={self.visitor_id}>"
