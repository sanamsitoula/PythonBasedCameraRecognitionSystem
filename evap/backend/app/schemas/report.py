"""Report generation schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


ReportType = Literal[
    "attendance_daily",
    "attendance_monthly",
    "visitor_summary",
    "vehicle_log",
    "alert_summary",
    "occupancy_trend",
    "behavior_events",
    "executive_summary",
]
ReportFormat = Literal["pdf", "excel", "csv"]
ReportStatus = Literal["pending", "processing", "ready", "failed"]


class ReportRequest(BaseModel):
    report_type: ReportType
    format: ReportFormat = "pdf"
    date_from: date
    date_to: date
    site_id: Optional[int] = None
    filters: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def validate_dates(cls, v: date, info) -> date:
        date_from = info.data.get("date_from")
        if date_from and v < date_from:
            raise ValueError("date_to must be >= date_from")
        return v


class ReportResponse(BaseModel):
    id: int
    report_type: ReportType
    title: str
    status: ReportStatus
    format: ReportFormat
    file_url: Optional[str] = None
    generated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    generated_by: Optional[int] = None
    parameters: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}
