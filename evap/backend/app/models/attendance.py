"""
Attendance and movement models — reflects Phase 3 tables.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .employee import EmployeeMaster


class AttendanceLog(Base):
    """Reflects the Phase 3 attendance_log table."""
    __tablename__ = "attendance_log"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employee_master.employee_id", ondelete="CASCADE"),
        nullable=False,
    )
    check_in_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    check_out_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    check_in_camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("camera_master.camera_id", ondelete="SET NULL"),
        nullable=True,
    )
    check_out_camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("camera_master.camera_id", ondelete="SET NULL"),
        nullable=True,
    )
    date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    work_hours: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    employee: Mapped["EmployeeMaster"] = relationship(
        "EmployeeMaster", back_populates="attendance_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<AttendanceLog log_id={self.log_id} "
            f"employee_id={self.employee_id} status={self.status!r}>"
        )


class EmployeeZoneHistory(Base):
    """Reflects the Phase 3 employee_zone_history table."""
    __tablename__ = "employee_zone_history"

    history_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employee_master.employee_id", ondelete="CASCADE"),
        nullable=False,
    )
    zone_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("zone_master.zone_id", ondelete="SET NULL"),
        nullable=True,
    )
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("camera_master.camera_id", ondelete="SET NULL"),
        nullable=True,
    )
    entry_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    exit_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    employee: Mapped["EmployeeMaster"] = relationship(
        "EmployeeMaster", back_populates="zone_histories"
    )

    def __repr__(self) -> str:
        return (
            f"<EmployeeZoneHistory history_id={self.history_id} "
            f"employee_id={self.employee_id} zone_id={self.zone_id}>"
        )


class MovementHistory(Base):
    """Reflects the Phase 3 movement_history table."""
    __tablename__ = "movement_history"

    movement_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employee_master.employee_id", ondelete="CASCADE"),
        nullable=False,
    )
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("camera_master.camera_id", ondelete="SET NULL"),
        nullable=True,
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    snapshot_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bbox_x: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    bbox_y: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    bbox_w: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    bbox_h: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)

    # Relationships
    employee: Mapped["EmployeeMaster"] = relationship(
        "EmployeeMaster", back_populates="movement_histories"
    )

    def __repr__(self) -> str:
        return (
            f"<MovementHistory movement_id={self.movement_id} "
            f"employee_id={self.employee_id}>"
        )
