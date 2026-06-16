"""Analytics and dashboard schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class DashboardStats(BaseModel):
    site_id: Optional[int] = None
    timestamp: datetime
    # Live counts
    people_present: int = 0
    employees_present: int = 0
    visitors_present: int = 0
    vehicles_present: int = 0
    # Occupancy
    occupancy_pct: float = Field(0.0, ge=0, le=100)
    # Today totals
    today_entries: int = 0
    today_exits: int = 0
    # Alert summary
    active_alerts: int = 0
    critical_alerts: int = 0
    # Camera health
    cameras_online: int = 0
    cameras_offline: int = 0
    # Cached flag
    from_cache: bool = False


class OccupancyDataPoint(BaseModel):
    timestamp: datetime
    zone_id: Optional[int] = None
    zone_name: Optional[str] = None
    count: int = Field(..., ge=0)
    pct: float = Field(..., ge=0, le=100)


class HeatmapPoint(BaseModel):
    x: float
    y: float
    intensity: float = Field(..., ge=0, le=1)


class HeatmapData(BaseModel):
    floor_id: int
    width: int
    height: int
    grid_size: int = 50
    date_from: str
    date_to: str
    points: List[HeatmapPoint] = []
    total_detections: int = 0


class BehaviorEventResponse(BaseModel):
    event_id: int
    camera_id: Optional[int] = None
    zone_id: Optional[int] = None
    event_type: str
    person_id: Optional[int] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    snapshot_path: Optional[str] = None
    alert_generated: bool

    model_config = {"from_attributes": True}


class CameraTimelineEntry(BaseModel):
    camera_id: int
    camera_name: Optional[str] = None
    zone_id: Optional[int] = None
    zone_name: Optional[str] = None
    seen_at: datetime
    confidence: Optional[float] = None


class CrossCameraJourney(BaseModel):
    person_id: int
    person_type: str  # employee / visitor / unknown
    date: str         # ISO date
    cameras: List[int] = []
    timeline: List[CameraTimelineEntry] = []
    total_zones_visited: int = 0
    journey_start: Optional[datetime] = None
    journey_end: Optional[datetime] = None
