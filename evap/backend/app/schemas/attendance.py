"""Attendance management schemas."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


AttendanceStatus = Literal["present", "absent", "half_day", "leave", "holiday", "weekend"]
ExceptionType = Literal["late_arrival", "early_departure", "no_checkout", "overtime", "absent"]


class AttendanceRecord(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    date: date
    first_entry: Optional[datetime] = None
    last_exit: Optional[datetime] = None
    working_hours: Optional[float] = Field(None, ge=0, description="Decimal hours worked")
    status: AttendanceStatus = "absent"
    is_late: bool = False
    late_by_minutes: Optional[int] = Field(None, ge=0)
    overtime_hours: Optional[float] = Field(None, ge=0)
    camera_id: Optional[int] = None

    model_config = {"from_attributes": True}


class AttendanceSummary(BaseModel):
    date: date
    site_id: Optional[int] = None
    total_present: int = 0
    total_absent: int = 0
    total_late: int = 0
    total_half_day: int = 0
    total_on_leave: int = 0
    attendance_pct: float = Field(0.0, ge=0, le=100)
    by_department: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description="dept → {present, absent, late}"
    )


class MonthlyAttendance(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000)
    working_days: int = Field(..., ge=0)
    present_days: int = Field(..., ge=0)
    absent_days: int = Field(..., ge=0)
    late_days: int = Field(..., ge=0)
    half_days: int = Field(0, ge=0)
    overtime_hours: float = Field(0.0, ge=0)
    attendance_pct: float = Field(0.0, ge=0, le=100)


class AttendanceException(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    date: date
    exception_type: ExceptionType
    details: Optional[str] = None
    # For late arrival: minutes late; for early_departure: minutes early
    minutes_deviation: Optional[int] = None
    corrected: bool = False
    corrected_by: Optional[str] = None
    corrected_at: Optional[datetime] = None


class AttendanceCorrectionRequest(BaseModel):
    employee_id: str
    date: date
    first_entry: Optional[datetime] = None
    last_exit: Optional[datetime] = None
    status: Optional[AttendanceStatus] = None
    reason: str = Field(..., min_length=5, max_length=512)
