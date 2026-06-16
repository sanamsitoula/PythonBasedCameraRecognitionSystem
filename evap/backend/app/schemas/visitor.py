"""Visitor management schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ZoneVisit(BaseModel):
    camera_id: int
    zone_id: Optional[int] = None
    zone_name: Optional[str] = None
    entered_at: datetime
    exited_at: Optional[datetime] = None
    duration_seconds: Optional[int] = Field(None, ge=0)


class VisitorResponse(BaseModel):
    visitor_id: int
    first_seen_at: datetime
    last_seen_at: datetime
    total_visits: int = Field(..., ge=0)
    face_snapshot_url: Optional[str] = None
    # Derived fields
    current_zone_id: Optional[int] = None
    current_zone_name: Optional[str] = None
    is_currently_present: bool = False

    model_config = {"from_attributes": True}


class VisitorJourney(BaseModel):
    visitor_id: int
    date: str  # ISO date
    visits: List[ZoneVisit] = []
    total_duration_seconds: int = 0
    zones_visited: int = 0
