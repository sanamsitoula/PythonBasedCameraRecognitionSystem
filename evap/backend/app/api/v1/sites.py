from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models import Building, Camera, Employee, Floor, OccupancySnapshot, Site, Zone

router = APIRouter(prefix="/sites", tags=["sites"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SiteCreate(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    timezone: str = "UTC"
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: Optional[bool] = None


class SiteOut(BaseModel):
    id: str
    name: str
    address: Optional[str]
    city: Optional[str]
    country: Optional[str]
    timezone: str
    latitude: Optional[float]
    longitude: Optional[float]
    is_active: bool

    class Config:
        from_attributes = True


class BuildingCreate(BaseModel):
    name: str
    description: Optional[str] = None


class BuildingOut(BaseModel):
    id: str
    site_id: str
    name: str
    description: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


class FloorCreate(BaseModel):
    name: str
    floor_number: int = 0


class FloorOut(BaseModel):
    id: str
    building_id: str
    name: str
    floor_number: int
    map_image_path: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


class ZoneCreate(BaseModel):
    name: str
    zone_type: str = "general"
    capacity: Optional[int] = None
    polygon_coords: Optional[list] = None
    alert_on_threshold: bool = False
    threshold_count: Optional[int] = None


class ZoneOut(BaseModel):
    id: str
    floor_id: str
    name: str
    zone_type: str
    capacity: Optional[int]
    polygon_coords: Optional[list]
    alert_on_threshold: bool
    is_active: bool

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Sites CRUD
# ---------------------------------------------------------------------------
@router.post("", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
async def create_site(
    body: SiteCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    site = Site(**body.model_dump())
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return site


@router.get("", response_model=dict)
async def list_sites(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(Site)
    if is_active is not None:
        q = q.where(Site.is_active == is_active)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [SiteOut.model_validate(s) for s in items], "total": total}


@router.get("/{site_id}", response_model=SiteOut)
async def get_site(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    site = (await db.execute(select(Site).where(Site.id == site_id))).scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


@router.put("/{site_id}", response_model=SiteOut)
async def update_site(
    site_id: str,
    body: SiteUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    site = (await db.execute(select(Site).where(Site.id == site_id))).scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(site, field, value)
    await db.commit()
    await db.refresh(site)
    return site


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    site = (await db.execute(select(Site).where(Site.id == site_id))).scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    site.is_active = False
    await db.commit()


# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------
@router.post("/{site_id}/buildings", response_model=BuildingOut, status_code=201)
async def create_building(
    site_id: str,
    body: BuildingCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    building = Building(site_id=site_id, **body.model_dump())
    db.add(building)
    await db.commit()
    await db.refresh(building)
    return building


@router.get("/{site_id}/buildings", response_model=dict)
async def list_buildings(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    items = (
        await db.execute(select(Building).where(Building.site_id == site_id))
    ).scalars().all()
    return {"items": [BuildingOut.model_validate(b) for b in items], "total": len(items)}


# ---------------------------------------------------------------------------
# Floors
# ---------------------------------------------------------------------------
@router.post("/buildings/{building_id}/floors", response_model=FloorOut, status_code=201)
async def create_floor(
    building_id: str,
    body: FloorCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    floor = Floor(building_id=building_id, **body.model_dump())
    db.add(floor)
    await db.commit()
    await db.refresh(floor)
    return floor


@router.get("/buildings/{building_id}/floors", response_model=dict)
async def list_floors(
    building_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    items = (
        await db.execute(select(Floor).where(Floor.building_id == building_id))
    ).scalars().all()
    return {"items": [FloorOut.model_validate(f) for f in items], "total": len(items)}


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------
@router.post("/floors/{floor_id}/zones", response_model=ZoneOut, status_code=201)
async def create_zone(
    floor_id: str,
    body: ZoneCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    zone = Zone(floor_id=floor_id, **body.model_dump())
    db.add(zone)
    await db.commit()
    await db.refresh(zone)
    return zone


@router.get("/floors/{floor_id}/zones", response_model=dict)
async def list_zones(
    floor_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    items = (
        await db.execute(select(Zone).where(Zone.floor_id == floor_id))
    ).scalars().all()
    return {"items": [ZoneOut.model_validate(z) for z in items], "total": len(items)}


# ---------------------------------------------------------------------------
# Site cameras + occupancy
# ---------------------------------------------------------------------------
@router.get("/{site_id}/cameras", response_model=dict)
async def site_cameras(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    items = (
        await db.execute(select(Camera).where(Camera.site_id == site_id, Camera.is_active == True))
    ).scalars().all()
    return {
        "items": [
            {"id": c.id, "name": c.name, "status": c.status, "zone_id": c.zone_id}
            for c in items
        ],
        "total": len(items),
    }


@router.get("/{site_id}/occupancy")
async def site_occupancy(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    from sqlalchemy import desc
    # Latest occupancy snapshot per zone in this site
    subq = (
        select(
            OccupancySnapshot.zone_id,
            func.max(OccupancySnapshot.recorded_at).label("latest"),
        )
        .where(OccupancySnapshot.site_id == site_id)
        .group_by(OccupancySnapshot.zone_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(OccupancySnapshot)
            .join(
                subq,
                (OccupancySnapshot.zone_id == subq.c.zone_id)
                & (OccupancySnapshot.recorded_at == subq.c.latest),
            )
        )
    ).scalars().all()
    total = sum(r.count for r in rows)
    zones = [{"zone_id": r.zone_id, "count": r.count, "recorded_at": r.recorded_at} for r in rows]
    return {"site_id": site_id, "total_occupancy": total, "zones": zones}
