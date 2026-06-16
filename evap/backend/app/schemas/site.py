"""Site hierarchy schemas: Site → Building → Floor → Zone."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ZoneType = Literal[
    "general", "entrance", "exit", "restricted", "parking",
    "canteen", "office", "corridor", "stairwell", "elevator",
    "lobby", "server_room", "warehouse",
]


# ── Site ────────────────────────────────────────────────────────────────────

class SiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    timezone: str = Field(default="UTC", max_length=64)
    coord_lat: Optional[float] = Field(None, ge=-90, le=90)
    coord_lon: Optional[float] = Field(None, ge=-180, le=180)


class SiteResponse(BaseModel):
    site_id: int
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    timezone: str
    coord_lat: Optional[float] = None
    coord_lon: Optional[float] = None
    is_active: bool

    model_config = {"from_attributes": True}


# ── Building ─────────────────────────────────────────────────────────────────

class BuildingCreate(BaseModel):
    site_id: int
    name: str = Field(..., min_length=1, max_length=128)
    floors_count: int = Field(default=1, ge=1)
    description: Optional[str] = None
    floor_plan_url: Optional[str] = None


class BuildingResponse(BaseModel):
    building_id: int
    site_id: int
    name: str
    floors_count: int
    description: Optional[str] = None
    floor_plan_url: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Floor ─────────────────────────────────────────────────────────────────────

class FloorCreate(BaseModel):
    building_id: int
    floor_number: int
    name: Optional[str] = Field(None, max_length=128)
    map_image_url: Optional[str] = None
    width_meters: Optional[float] = Field(None, gt=0)
    height_meters: Optional[float] = Field(None, gt=0)


class FloorResponse(BaseModel):
    floor_id: int
    building_id: int
    floor_number: int
    name: Optional[str] = None
    map_image_url: Optional[str] = None
    width_meters: Optional[float] = None
    height_meters: Optional[float] = None

    model_config = {"from_attributes": True}


# ── Zone ──────────────────────────────────────────────────────────────────────

class ZoneCreate(BaseModel):
    floor_id: int
    name: str = Field(..., min_length=1, max_length=128)
    zone_type: ZoneType = "general"
    polygon: Optional[List[Dict[str, float]]] = Field(
        None, description="List of {x, y} points defining the zone boundary"
    )
    max_capacity: Optional[int] = Field(None, gt=0)
    is_restricted: bool = False
    color_code: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class ZoneResponse(BaseModel):
    zone_id: int
    floor_id: int
    name: str
    zone_type: ZoneType
    polygon: Optional[List[Dict[str, float]]] = None
    max_capacity: Optional[int] = None
    is_restricted: bool
    color_code: Optional[str] = None

    model_config = {"from_attributes": True}
