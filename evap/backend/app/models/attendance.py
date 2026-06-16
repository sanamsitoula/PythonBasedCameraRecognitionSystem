"""
Attendance and movement models — aligned with cctv_analytics Phase 3 schema.
Python attribute names used by the API; DB column names match actual schema.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date,
    DateTime, ForeignKey, Integer, Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .employee import EmployeeMaster


class AttendanceLog(Base):
    """Reflects cctv_analytics.attendance_log (Phase 3).
    check_in_time → first_entry, check_out_time → last_exit, date → attendance_date.
    """
    __tablename__ = "attendance_log"

    attendance_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("employee_master.employee_id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[Optional[object]] = mapped_column("attendance_date", Date, nullable=True)
    check_in_time: Mapped[Optional[datetime]] = mapped_column(
        "first_entry", DateTime(timezone=True), nullable=True
    )
    check_out_time: Mapped[Optional[datetime]] = mapped_column(
        "last_exit", DateTime(timezone=True), nullable=True
    )
    working_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    break_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # EVAP extension columns (added by 005_evap_web_tables.sql)
    work_hours: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('present','late','half_day','absent')", name="ck_al_status"
        ),
    )

    employee: Mapped["EmployeeMaster"] = relationship(
        "EmployeeMaster", back_populates="attendance_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<AttendanceLog attendance_id={self.attendance_id} "
            f"employee_id={self.employee_id!r} status={self.status!r}>"
        )


class EmployeeZoneHistory(Base):
    """Reflects cctv_analytics.employee_zone_history (Phase 3).
    camera_id and zone_id are VARCHAR (not FK ints) in the actual table.
    """
    __tablename__ = "employee_zone_history"

    history_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("employee_master.employee_id", ondelete="CASCADE"),
        nullable=False,
    )
    camera_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zone_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    zone_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    entry_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    exit_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    visit_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    employee: Mapped["EmployeeMaster"] = relationship(
        "EmployeeMaster", back_populates="zone_histories"
    )

    def __repr__(self) -> str:
        return (
            f"<EmployeeZoneHistory history_id={self.history_id} "
            f"employee_id={self.employee_id!r} zone_id={self.zone_id!r}>"
        )


class MovementHistory(Base):
    """Reflects cctv_analytics.movement_history (Phase 3).
    person_id / camera_id / zone_id are VARCHAR in the actual table.
    No FK constraint on employee_master (the table stores employees AND visitors).
    """
    __tablename__ = "movement_history"

    movement_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    person_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    person_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    camera_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zone_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    zone_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    entry_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    exit_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    track_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<MovementHistory movement_id={self.movement_id} "
            f"person_id={self.person_id!r} type={self.person_type!r}>"
        )
