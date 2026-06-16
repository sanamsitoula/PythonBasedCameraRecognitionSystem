"""Alert management schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


AlertSeverity = Literal["info", "warning", "critical", "emergency"]


class AlertCreate(BaseModel):
    alert_type: str = Field(..., min_length=1, max_length=64)
    severity: AlertSeverity = "warning"
    site_id: Optional[int] = None
    camera_id: Optional[int] = None
    person_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    zone_id: Optional[int] = None
    message: str = Field(..., min_length=1, max_length=2048)
    details: Optional[Dict[str, Any]] = None
    snapshot_path: Optional[str] = None


class AlertResponse(BaseModel):
    alert_id: int
    alert_type: str
    severity: AlertSeverity
    site_id: Optional[int] = None
    camera_id: Optional[int] = None
    person_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    zone_id: Optional[int] = None
    message: str
    details: Optional[Dict[str, Any]] = None
    is_acknowledged: bool
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    snapshot_path: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertAcknowledge(BaseModel):
    notes: Optional[str] = Field(None, max_length=1024)


class AlertStats(BaseModel):
    site_id: Optional[int] = None
    date: Optional[str] = None
    total_today: int = 0
    unacknowledged: int = 0
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_severity: Dict[str, int] = Field(default_factory=dict)
    # Hour-of-day distribution for the requested date
    by_hour: Dict[int, int] = Field(default_factory=dict)
