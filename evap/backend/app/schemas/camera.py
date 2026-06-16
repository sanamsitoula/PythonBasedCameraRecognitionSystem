"""Camera management schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


CameraType = Literal["fixed", "ptz", "fisheye", "thermal", "anpr", "360"]
CameraStatus = Literal["online", "offline", "error", "maintenance"]


class CameraCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    site_id: Optional[int] = None
    rtsp_url: str = Field(..., description="RTSP stream URL (will be encrypted at rest)")
    camera_type: CameraType = "fixed"
    resolution: Optional[str] = Field(None, pattern=r"^\d+x\d+$", examples=["1920x1080"])
    fps: Optional[int] = Field(None, ge=1, le=120)
    # Floor-map placement
    location_x: Optional[float] = Field(None, description="X coordinate on floor map")
    location_y: Optional[float] = Field(None, description="Y coordinate on floor map")
    direction_degrees: Optional[float] = Field(None, ge=0, lt=360)
    floor_id: Optional[int] = None
    zone_id: Optional[int] = None
    # Optional hardware metadata
    ip_address: Optional[str] = None
    manufacturer: Optional[str] = Field(None, max_length=64)
    model: Optional[str] = Field(None, max_length=64)
    installed_at: Optional[str] = None   # ISO date string
    ai_enabled: bool = True

    @field_validator("rtsp_url")
    @classmethod
    def rtsp_url_scheme(cls, v: str) -> str:
        if not (v.startswith("rtsp://") or v.startswith("rtsps://")):
            raise ValueError("RTSP URL must start with rtsp:// or rtsps://")
        return v


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    rtsp_url: Optional[str] = None
    camera_type: Optional[CameraType] = None
    resolution: Optional[str] = Field(None, pattern=r"^\d+x\d+$")
    fps: Optional[int] = Field(None, ge=1, le=120)
    location_x: Optional[float] = None
    location_y: Optional[float] = None
    direction_degrees: Optional[float] = Field(None, ge=0, lt=360)
    floor_id: Optional[int] = None
    zone_id: Optional[int] = None
    ip_address: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    ai_enabled: Optional[bool] = None
    status: Optional[CameraStatus] = None

    @field_validator("rtsp_url")
    @classmethod
    def rtsp_url_scheme(cls, v: Optional[str]) -> Optional[str]:
        if v and not (v.startswith("rtsp://") or v.startswith("rtsps://")):
            raise ValueError("RTSP URL must start with rtsp:// or rtsps://")
        return v


class CameraStreamStats(BaseModel):
    stream_id: int
    camera_id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    frames_processed: int
    detections_count: int
    avg_fps: Optional[float] = None
    status: Literal["active", "stopped", "error"]
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class CameraResponse(BaseModel):
    camera_id: int
    name: str
    site_id: Optional[int] = None
    building_id: Optional[int] = None
    floor_id: Optional[int] = None
    zone_id: Optional[int] = None
    camera_type: CameraType
    resolution: Optional[str] = None
    fps: Optional[int] = None
    is_active: bool
    ai_enabled: bool
    status: CameraStatus
    last_heartbeat: Optional[datetime] = None
    ip_address: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    installed_at: Optional[str] = None
    location_x: Optional[float] = None
    location_y: Optional[float] = None
    direction_degrees: Optional[float] = None
    # Populated separately by get_camera
    stream_stats: Optional[CameraStreamStats] = None

    model_config = {"from_attributes": True}


class CameraStatusSummary(BaseModel):
    total: int
    active: int
    offline: int
    error: int
    maintenance: int
