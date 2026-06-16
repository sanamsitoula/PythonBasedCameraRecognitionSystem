from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models import Floor, HeatmapData, MovementEvent, OccupancySnapshot, Zone

router = APIRouter(prefix="/maps", tags=["maps"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ZoneOut(BaseModel):
    id: str
    name: str
    zone_type: str
    capacity: Optional[int]
    polygon_coords: Optional[list]
    is_active: bool

    class Config:
        from_attributes = True


class FloorMapOut(BaseModel):
    id: str
    building_id: str
    name: str
    floor_number: int
    map_image_path: Optional[str]
    map_width: Optional[int]
    map_height: Optional[int]
    zones: list

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/floors/{floor_id}", response_model=dict)
async def get_floor_map(
    floor_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    floor = (await db.execute(select(Floor).where(Floor.id == floor_id))).scalar_one_or_none()
    if not floor:
        raise HTTPException(status_code=404, detail="Floor not found")

    zones = (await db.execute(select(Zone).where(Zone.floor_id == floor_id, Zone.is_active == True))).scalars().all()

    return {
        "id": floor.id,
        "building_id": floor.building_id,
        "name": floor.name,
        "floor_number": floor.floor_number,
        "map_image_path": floor.map_image_path,
        "map_width": floor.map_width,
        "map_height": floor.map_height,
        "zones": [ZoneOut.model_validate(z) for z in zones],
    }


@router.get("/floors/{floor_id}/occupancy", response_model=dict)
async def floor_occupancy(
    floor_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    zones = (
        await db.execute(select(Zone).where(Zone.floor_id == floor_id, Zone.is_active == True))
    ).scalars().all()
    zone_ids = [z.id for z in zones]

    # Latest snapshot per zone
    subq = (
        select(OccupancySnapshot.zone_id, func.max(OccupancySnapshot.recorded_at).label("latest"))
        .where(OccupancySnapshot.zone_id.in_(zone_ids))
        .group_by(OccupancySnapshot.zone_id)
        .subquery()
    )
    snapshots = (
        await db.execute(
            select(OccupancySnapshot)
            .join(subq, (OccupancySnapshot.zone_id == subq.c.zone_id) & (OccupancySnapshot.recorded_at == subq.c.latest))
        )
    ).scalars().all()

    occ_map = {s.zone_id: s.count for s in snapshots}
    zone_data = [
        {
            "zone_id": z.id,
            "zone_name": z.name,
            "capacity": z.capacity,
            "current_count": occ_map.get(z.id, 0),
            "utilization_pct": round(occ_map.get(z.id, 0) / z.capacity * 100, 1) if z.capacity else None,
        }
        for z in zones
    ]
    total = sum(d["current_count"] for d in zone_data)
    return {"floor_id": floor_id, "total_occupancy": total, "zones": zone_data}


@router.get("/floors/{floor_id}/persons", response_model=dict)
async def floor_persons(
    floor_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """Return recently detected persons on this floor (last 5 minutes)."""
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(minutes=5)
    zones = (
        await db.execute(select(Zone.id).where(Zone.floor_id == floor_id))
    ).scalars().all()
    zone_ids = list(zones)

    events = (
        await db.execute(
            select(MovementEvent)
            .where(
                MovementEvent.zone_id.in_(zone_ids),
                MovementEvent.occurred_at >= cutoff,
            )
            .order_by(MovementEvent.occurred_at.desc())
        )
    ).scalars().all()

    # Deduplicate by person/employee to get latest position
    seen: set = set()
    persons = []
    for e in events:
        pid = e.employee_id or e.visitor_id or e.person_id
        if pid and pid not in seen:
            seen.add(pid)
            persons.append(
                {
                    "person_id": e.person_id,
                    "employee_id": e.employee_id,
                    "visitor_id": e.visitor_id,
                    "zone_id": e.zone_id,
                    "last_seen": e.occurred_at,
                    "snapshot_path": e.snapshot_path,
                }
            )

    return {"floor_id": floor_id, "persons": persons, "total": len(persons)}


@router.get("/floors/{floor_id}/heatmap", response_model=dict)
async def floor_heatmap(
    floor_id: str,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(HeatmapData).where(HeatmapData.floor_id == floor_id)
    if date_from:
        q = q.where(HeatmapData.hour_bucket >= date_from)
    if date_to:
        q = q.where(HeatmapData.hour_bucket <= date_to)

    rows = (await db.execute(q)).scalars().all()
    points = [{"x": r.x_coord, "y": r.y_coord, "value": r.intensity, "hour": r.hour_bucket} for r in rows]
    max_intensity = max((r.intensity for r in rows), default=0)
    return {"floor_id": floor_id, "points": points, "max_intensity": max_intensity, "total_points": len(points)}


@router.post("/floors/{floor_id}/upload", status_code=status.HTTP_200_OK)
async def upload_floor_plan(
    floor_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    floor = (await db.execute(select(Floor).where(Floor.id == floor_id))).scalar_one_or_none()
    if not floor:
        raise HTTPException(status_code=404, detail="Floor not found")

    if file.content_type not in ("image/jpeg", "image/png", "image/svg+xml"):
        raise HTTPException(status_code=422, detail="Accepted: JPEG, PNG, SVG")

    maps_dir = os.path.join(settings.MAPS_DIR, floor_id)
    os.makedirs(maps_dir, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1] if file.filename else "png"
    filepath = os.path.join(maps_dir, f"floorplan.{ext}")

    content = await file.read()
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    floor.map_image_path = filepath
    await db.commit()

    return {"floor_id": floor_id, "map_image_path": filepath, "message": "Floor plan uploaded successfully"}
