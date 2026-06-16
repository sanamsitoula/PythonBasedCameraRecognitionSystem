"""Vehicle and ANPR schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


VehicleType = Literal["car", "bus", "truck", "motorcycle", "bicycle"]
OwnerType = Literal["employee", "visitor", "unknown"]


class VehicleCreate(BaseModel):
    plate_number: str = Field(..., min_length=1, max_length=32)
    plate_country: str = Field(default="IN", max_length=4)
    vehicle_type: VehicleType = "car"
    # Owner linkage
    owner_id: Optional[int] = None
    owner_type: OwnerType = "unknown"
    owner_name: Optional[str] = Field(None, max_length=128)
    owner_phone: Optional[str] = Field(None, max_length=20)
    # Physical details
    color: Optional[str] = Field(None, max_length=32)
    make: Optional[str] = Field(None, max_length=64)
    model_name: Optional[str] = Field(None, max_length=64)
    is_whitelisted: bool = False
    is_blacklisted: bool = False

    @field_validator("plate_number")
    @classmethod
    def uppercase_plate(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("is_blacklisted")
    @classmethod
    def not_both_lists(cls, v: bool, info) -> bool:
        if v and info.data.get("is_whitelisted"):
            raise ValueError("Vehicle cannot be both whitelisted and blacklisted")
        return v


class VehicleUpdate(BaseModel):
    vehicle_type: Optional[VehicleType] = None
    owner_id: Optional[int] = None
    owner_type: Optional[OwnerType] = None
    owner_name: Optional[str] = Field(None, max_length=128)
    owner_phone: Optional[str] = Field(None, max_length=20)
    color: Optional[str] = Field(None, max_length=32)
    make: Optional[str] = Field(None, max_length=64)
    model_name: Optional[str] = Field(None, max_length=64)
    is_whitelisted: Optional[bool] = None
    is_blacklisted: Optional[bool] = None


class VehicleResponse(BaseModel):
    vehicle_id: int
    plate_number: str
    plate_country: str
    vehicle_type: VehicleType
    owner_id: Optional[int] = None
    owner_type: OwnerType
    owner_name: Optional[str] = None
    color: Optional[str] = None
    make: Optional[str] = None
    model_name: Optional[str] = None
    is_whitelisted: bool
    is_blacklisted: bool
    registered_at: datetime

    model_config = {"from_attributes": True}


class LicensePlateEvent(BaseModel):
    log_id: int
    plate_number: str
    plate_confidence: Optional[float] = Field(None, ge=0, le=1)
    vehicle_type: Optional[VehicleType] = None
    vehicle_id: Optional[int] = None
    camera_id: Optional[int] = None
    site_id: Optional[int] = None
    direction: Literal["entry", "exit", "unknown"]
    entry_time: datetime
    exit_time: Optional[datetime] = None
    parking_duration_seconds: Optional[int] = None
    snapshot_url: Optional[str] = None

    model_config = {"from_attributes": True}


class ParkingAnalytics(BaseModel):
    site_id: Optional[int] = None
    date: str  # ISO date
    total_today: int
    avg_duration_seconds: Optional[float] = None
    peak_hour: Optional[int] = Field(None, ge=0, le=23)
    current_occupancy: int = 0
    vehicles_by_type: dict[str, int] = {}
