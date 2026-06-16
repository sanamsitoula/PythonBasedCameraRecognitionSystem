from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models import VehicleLog, VehicleRegistry

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class VehicleCreate(BaseModel):
    plate_number: str
    owner_name: Optional[str] = None
    owner_employee_id: Optional[str] = None
    vehicle_type: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    is_authorized: bool = True


class VehicleUpdate(BaseModel):
    owner_name: Optional[str] = None
    vehicle_type: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    is_authorized: Optional[bool] = None
    is_blacklisted: Optional[bool] = None
    blacklist_reason: Optional[str] = None
    is_active: Optional[bool] = None


class VehicleOut(BaseModel):
    id: str
    plate_number: str
    owner_name: Optional[str]
    vehicle_type: Optional[str]
    make: Optional[str]
    model: Optional[str]
    color: Optional[str]
    is_authorized: bool
    is_blacklisted: bool
    is_active: bool

    class Config:
        from_attributes = True


class VehicleLogOut(BaseModel):
    id: int
    plate_number: str
    camera_id: str
    site_id: Optional[str]
    event_type: str
    confidence: Optional[float]
    snapshot_path: Optional[str]
    direction: Optional[str]
    occurred_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Registry CRUD
# ---------------------------------------------------------------------------
@router.post("", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    body: VehicleCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    existing = (
        await db.execute(
            select(VehicleRegistry).where(VehicleRegistry.plate_number == body.plate_number)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Plate number already registered")
    vehicle = VehicleRegistry(**body.model_dump())
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@router.get("", response_model=dict)
async def list_vehicles(
    is_authorized: Optional[bool] = Query(None),
    is_blacklisted: Optional[bool] = Query(None),
    vehicle_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(VehicleRegistry).where(VehicleRegistry.is_active == True)
    if is_authorized is not None:
        q = q.where(VehicleRegistry.is_authorized == is_authorized)
    if is_blacklisted is not None:
        q = q.where(VehicleRegistry.is_blacklisted == is_blacklisted)
    if vehicle_type:
        q = q.where(VehicleRegistry.vehicle_type == vehicle_type)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [VehicleOut.model_validate(v) for v in items], "total": total}


@router.get("/active", response_model=dict)
async def active_vehicles(
    site_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    # Find plates that have an entry log but no subsequent exit in the same site
    from sqlalchemy import and_, not_, exists

    entry_q = select(VehicleLog.plate_number).where(VehicleLog.event_type == "entry")
    if site_id:
        entry_q = entry_q.where(VehicleLog.site_id == site_id)

    # Simplified: return all plates with last event = "entry"
    subq = (
        select(
            VehicleLog.plate_number,
            func.max(VehicleLog.occurred_at).label("last_event"),
        )
        .group_by(VehicleLog.plate_number)
        .subquery()
    )
    rows = (
        await db.execute(
            select(VehicleLog)
            .join(subq, (VehicleLog.plate_number == subq.c.plate_number) & (VehicleLog.occurred_at == subq.c.last_event))
            .where(VehicleLog.event_type == "entry")
        )
    ).scalars().all()

    return {
        "items": [VehicleLogOut.model_validate(r) for r in rows],
        "total": len(rows),
    }


@router.get("/logs", response_model=dict)
async def vehicle_logs(
    site_id: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    plate_number: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(VehicleLog).order_by(VehicleLog.occurred_at.desc())
    if site_id:
        q = q.where(VehicleLog.site_id == site_id)
    if camera_id:
        q = q.where(VehicleLog.camera_id == camera_id)
    if plate_number:
        q = q.where(VehicleLog.plate_number.ilike(f"%{plate_number}%"))
    if event_type:
        q = q.where(VehicleLog.event_type == event_type)
    if date_from:
        q = q.where(VehicleLog.occurred_at >= date_from)
    if date_to:
        q = q.where(VehicleLog.occurred_at <= date_to)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [VehicleLogOut.model_validate(v) for v in items], "total": total}


@router.get("/analytics/parking", response_model=dict)
async def parking_analytics(
    site_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    # Calculate avg dwell time per plate by pairing entry/exit events
    entry_q = select(
        VehicleLog.plate_number,
        VehicleLog.occurred_at.label("entry_time"),
    ).where(VehicleLog.event_type == "entry")
    exit_q = select(
        VehicleLog.plate_number,
        VehicleLog.occurred_at.label("exit_time"),
    ).where(VehicleLog.event_type == "exit")

    if site_id:
        entry_q = entry_q.where(VehicleLog.site_id == site_id)
        exit_q = exit_q.where(VehicleLog.site_id == site_id)
    if date_from:
        entry_q = entry_q.where(VehicleLog.occurred_at >= date_from)
        exit_q = exit_q.where(VehicleLog.occurred_at >= date_from)
    if date_to:
        entry_q = entry_q.where(VehicleLog.occurred_at <= date_to)
        exit_q = exit_q.where(VehicleLog.occurred_at <= date_to)

    entries = (await db.execute(entry_q)).all()
    exits = (await db.execute(exit_q)).all()

    exit_map: dict = {}
    for row in exits:
        if row.plate_number not in exit_map:
            exit_map[row.plate_number] = row.exit_time

    durations = []
    for row in entries:
        if row.plate_number in exit_map:
            delta = (exit_map[row.plate_number] - row.entry_time).total_seconds() / 60
            if delta > 0:
                durations.append({"plate_number": row.plate_number, "duration_minutes": round(delta, 1)})

    avg_duration = round(sum(d["duration_minutes"] for d in durations) / len(durations), 1) if durations else 0.0
    return {
        "total_vehicles": len(entries),
        "vehicles_with_exit": len(durations),
        "avg_parking_duration_minutes": avg_duration,
        "details": durations[:100],
    }


@router.get("/{plate}/history", response_model=dict)
async def plate_history(
    plate: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = (
        select(VehicleLog)
        .where(VehicleLog.plate_number == plate)
        .order_by(VehicleLog.occurred_at.desc())
    )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [VehicleLogOut.model_validate(v) for v in items], "total": total}


@router.put("/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(
    vehicle_id: str,
    body: VehicleUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    vehicle = (
        await db.execute(select(VehicleRegistry).where(VehicleRegistry.id == vehicle_id))
    ).scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(vehicle, field, value)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    vehicle = (
        await db.execute(select(VehicleRegistry).where(VehicleRegistry.id == vehicle_id))
    ).scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    vehicle.is_active = False
    await db.commit()
