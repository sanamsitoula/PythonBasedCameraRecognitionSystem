from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models import MovementEvent, Visitor

router = APIRouter(prefix="/visitors", tags=["visitors"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class WatchlistRequest(BaseModel):
    reason: str


class VisitorOut(BaseModel):
    id: str
    person_id: Optional[str]
    name: Optional[str]
    phone: Optional[str]
    purpose: Optional[str]
    host_employee_id: Optional[str]
    site_id: Optional[str]
    first_seen: datetime
    last_seen: Optional[datetime]
    is_present: bool
    is_watchlisted: bool
    face_image_path: Optional[str]

    class Config:
        from_attributes = True


class MovementOut(BaseModel):
    id: int
    camera_id: str
    zone_id: Optional[str]
    event_type: str
    confidence: Optional[float]
    snapshot_path: Optional[str]
    occurred_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=dict)
async def list_visitors(
    site_id: Optional[str] = Query(None),
    is_present: Optional[bool] = Query(None),
    is_watchlisted: Optional[bool] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(Visitor)
    if site_id:
        q = q.where(Visitor.site_id == site_id)
    if is_present is not None:
        q = q.where(Visitor.is_present == is_present)
    if is_watchlisted is not None:
        q = q.where(Visitor.is_watchlisted == is_watchlisted)
    if date_from:
        q = q.where(Visitor.first_seen >= date_from)
    if date_to:
        q = q.where(Visitor.first_seen <= date_to)
    q = q.order_by(Visitor.first_seen.desc())

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [VisitorOut.model_validate(v) for v in items], "total": total}


@router.get("/active", response_model=dict)
async def active_visitors(
    site_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(Visitor).where(Visitor.is_present == True)
    if site_id:
        q = q.where(Visitor.site_id == site_id)
    q = q.order_by(Visitor.first_seen.desc())
    items = (await db.execute(q)).scalars().all()
    return {"items": [VisitorOut.model_validate(v) for v in items], "total": len(items)}


@router.get("/{visitor_id}", response_model=VisitorOut)
async def get_visitor(
    visitor_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    visitor = (
        await db.execute(select(Visitor).where(Visitor.id == visitor_id))
    ).scalar_one_or_none()
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")
    return visitor


@router.get("/{visitor_id}/journey", response_model=dict)
async def visitor_journey(
    visitor_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    visitor = (
        await db.execute(select(Visitor).where(Visitor.id == visitor_id))
    ).scalar_one_or_none()
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")

    events = (
        await db.execute(
            select(MovementEvent)
            .where(MovementEvent.visitor_id == visitor_id)
            .order_by(MovementEvent.occurred_at.asc())
        )
    ).scalars().all()

    timeline = [
        {
            "sequence": idx + 1,
            "camera_id": e.camera_id,
            "zone_id": e.zone_id,
            "event_type": e.event_type,
            "snapshot_path": e.snapshot_path,
            "occurred_at": e.occurred_at,
        }
        for idx, e in enumerate(events)
    ]
    duration_minutes = None
    if events:
        delta = events[-1].occurred_at - events[0].occurred_at
        duration_minutes = round(delta.total_seconds() / 60, 1)

    return {
        "visitor_id": visitor_id,
        "first_seen": visitor.first_seen,
        "last_seen": visitor.last_seen,
        "duration_minutes": duration_minutes,
        "zones_visited": len({e.zone_id for e in events if e.zone_id}),
        "timeline": timeline,
    }


@router.post("/{visitor_id}/watchlist", status_code=status.HTTP_200_OK)
async def add_to_watchlist(
    visitor_id: str,
    body: WatchlistRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    visitor = (
        await db.execute(select(Visitor).where(Visitor.id == visitor_id))
    ).scalar_one_or_none()
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")
    visitor.is_watchlisted = True
    visitor.watchlist_reason = body.reason
    await db.commit()
    return {"visitor_id": visitor_id, "is_watchlisted": True, "reason": body.reason}
