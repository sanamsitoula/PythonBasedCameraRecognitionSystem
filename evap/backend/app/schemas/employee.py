"""Employee management schemas."""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class EmployeeCreate(BaseModel):
    employee_id: str = Field(..., min_length=1, max_length=32, description="Business employee ID")
    name: str = Field(..., min_length=1, max_length=128)
    department: Optional[str] = Field(None, max_length=128)
    designation: Optional[str] = Field(None, max_length=128)
    work_start_time: Optional[time] = Field(None, description="e.g. 09:00")
    work_end_time: Optional[time] = Field(None, description="e.g. 18:00")
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    site_id: Optional[int] = None
    is_active: bool = True

    @field_validator("work_end_time")
    @classmethod
    def end_after_start(cls, v: Optional[time], info) -> Optional[time]:
        start = info.data.get("work_start_time")
        if v and start and v <= start:
            raise ValueError("work_end_time must be after work_start_time")
        return v


class EmployeeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    department: Optional[str] = Field(None, max_length=128)
    designation: Optional[str] = Field(None, max_length=128)
    work_start_time: Optional[time] = None
    work_end_time: Optional[time] = None
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    site_id: Optional[int] = None
    is_active: Optional[bool] = None


class EmployeeResponse(BaseModel):
    id: int
    employee_id: str
    name: str
    department: Optional[str] = None
    designation: Optional[str] = None
    work_start_time: Optional[time] = None
    work_end_time: Optional[time] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    site_id: Optional[int] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class FaceEnrollmentResponse(BaseModel):
    employee_id: str
    enrolled_count: int = Field(..., description="Number of face images enrolled")
    last_enrolled: Optional[datetime] = Field(None, description="Timestamp of last enrollment")
