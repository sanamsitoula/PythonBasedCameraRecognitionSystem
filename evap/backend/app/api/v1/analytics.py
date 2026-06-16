from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models import (
    Alert,
    BehaviorEvent,
    Camera,
    DailyAnalytics,
    Detection,
    Employee,
    HeatmapData,
    MovementEvent,
    OccupancySnapshot,
    Visitor,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=dict)
async def analytics_dashboard(
    site_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Total persons today
    person_q = select(func.count(Detection.id)).where(
        Detection.detected_at >= today_start,
        Detection.detection_type == "face",
    )

    # Total vehicles today
    vehicle_q = select(func.count(Detection.id)).where(
        Detection.detected_at >= today_start,
        Detection.detection_type == "lpr",
    )

    # Active alerts
    alerts_q = select(func.count(Alert.id)).where(Alert.is_acknowledged == False)

    # Active cameras
    cameras_q = select(func.count(Camera.id)).where(Camera.status == "online", Camera.is_active == True)

    if site_id:
        person_q = person_q.join(Camera, Camera.id == Detection.camera_id).where(Camera.site_id == site_id)
        vehicle_q = vehicle_q.join(Camera, Camera.id == Detection.camera_id).where(Camera.site_id == site_id)
        alerts_q = alerts_q.where(Alert.site_id == site_id)
        cameras_q = cameras_q.where(Camera.site_id == site_id)

    persons = (await db.execute(person_q)).scalar_one()
    vehicles = (await db.execute(vehicle_q)).scalar_one()
    active_alerts = (await db.execute(alerts_q)).scalar_one()
    online_cameras = (await db.execute(cameras_q)).scalar_one()

    # Current occupancy
    occ_subq = (
        select(OccupancySnapshot.zone_id, func.max(OccupancySnapshot.recorded_at).label("latest"))
        .group_by(OccupancySnapshot.zone_id)
        .subquery()
    )
    latest_occ = (
        await db.execute(
            select(func.sum(OccupancySnapshot.count))
            .join(occ_subq, (OccupancySnapshot.zone_id == occ_subq.c.zone_id) & (OccupancySnapshot.recorded_at == occ_subq.c.latest))
        )
    ).scalar_one()

    return {
        "timestamp": now.isoformat(),
        "persons_detected_today": persons,
        "vehicles_detected_today": vehicles,
        "active_alerts": active_alerts,
        "online_cameras": online_cameras,
        "current_occupancy": latest_occ or 0,
    }


@router.get("/occupancy", response_model=dict)
async def occupancy_over_time(
    zone_id: Optional[str] = Query(None),
    floor_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    interval_minutes: int = Query(15, ge=1, le=1440),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(OccupancySnapshot).order_by(OccupancySnapshot.recorded_at.asc())
    if zone_id:
        q = q.where(OccupancySnapshot.zone_id == zone_id)
    if floor_id:
        q = q.where(OccupancySnapshot.floor_id == floor_id)
    if site_id:
        q = q.where(OccupancySnapshot.site_id == site_id)
    if date_from:
        q = q.where(OccupancySnapshot.recorded_at >= date_from)
    if date_to:
        q = q.where(OccupancySnapshot.recorded_at <= date_to)

    rows = (await db.execute(q)).scalars().all()
    data = [{"time": r.recorded_at, "zone_id": r.zone_id, "count": r.count} for r in rows]
    peak = max((r.count for r in rows), default=0)
    avg = round(sum(r.count for r in rows) / len(rows), 1) if rows else 0.0

    return {"data": data, "peak": peak, "average": avg, "total_points": len(data)}


@router.get("/heatmap", response_model=dict)
async def heatmap_data(
    floor_id: str = Query(...),
    zone_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(HeatmapData).where(HeatmapData.floor_id == floor_id)
    if zone_id:
        q = q.where(HeatmapData.zone_id == zone_id)
    if date_from:
        q = q.where(HeatmapData.hour_bucket >= date_from)
    if date_to:
        q = q.where(HeatmapData.hour_bucket <= date_to)

    rows = (await db.execute(q)).scalars().all()
    points = [{"x": r.x_coord, "y": r.y_coord, "value": r.intensity} for r in rows]
    return {"floor_id": floor_id, "points": points, "total_points": len(points)}


@router.get("/daily", response_model=dict)
async def daily_analytics(
    site_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(DailyAnalytics).order_by(DailyAnalytics.date.desc())
    if site_id:
        q = q.where(DailyAnalytics.site_id == site_id)
    if date_from:
        q = q.where(DailyAnalytics.date >= date_from)
    if date_to:
        q = q.where(DailyAnalytics.date <= date_to)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {
        "items": [
            {
                "date": r.date,
                "site_id": r.site_id,
                "total_persons_detected": r.total_persons_detected,
                "total_employees": r.total_employees,
                "total_visitors": r.total_visitors,
                "total_vehicles": r.total_vehicles,
                "peak_occupancy": r.peak_occupancy,
                "total_alerts": r.total_alerts,
                "avg_dwell_time_minutes": r.avg_dwell_time_minutes,
            }
            for r in items
        ],
        "total": total,
    }


@router.get("/monthly", response_model=dict)
async def monthly_analytics(
    site_id: Optional[str] = Query(None),
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    from calendar import monthrange

    _, last_day = monthrange(year, month)
    date_from = datetime(year, month, 1, tzinfo=timezone.utc)
    date_to = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    q = select(DailyAnalytics).where(
        DailyAnalytics.date >= date_from,
        DailyAnalytics.date <= date_to,
    )
    if site_id:
        q = q.where(DailyAnalytics.site_id == site_id)

    rows = (await db.execute(q)).scalars().all()

    return {
        "year": year,
        "month": month,
        "days_with_data": len(rows),
        "total_persons": sum(r.total_persons_detected for r in rows),
        "total_vehicles": sum(r.total_vehicles for r in rows),
        "total_alerts": sum(r.total_alerts for r in rows),
        "peak_occupancy": max((r.peak_occupancy for r in rows), default=0),
        "avg_daily_persons": round(
            sum(r.total_persons_detected for r in rows) / len(rows), 1
        ) if rows else 0,
        "daily_breakdown": [
            {"date": r.date, "persons": r.total_persons_detected, "vehicles": r.total_vehicles, "alerts": r.total_alerts}
            for r in rows
        ],
    }


@router.get("/behavior", response_model=dict)
async def behavior_analytics(
    camera_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(BehaviorEvent).order_by(BehaviorEvent.occurred_at.desc())
    if camera_id:
        q = q.where(BehaviorEvent.camera_id == camera_id)
    if zone_id:
        q = q.where(BehaviorEvent.zone_id == zone_id)
    if event_type:
        q = q.where(BehaviorEvent.event_type == event_type)
    if date_from:
        q = q.where(BehaviorEvent.occurred_at >= date_from)
    if date_to:
        q = q.where(BehaviorEvent.occurred_at <= date_to)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {
        "items": [
            {
                "id": e.id,
                "camera_id": e.camera_id,
                "zone_id": e.zone_id,
                "event_type": e.event_type,
                "confidence": e.confidence,
                "duration_seconds": e.duration_seconds,
                "snapshot_path": e.snapshot_path,
                "occurred_at": e.occurred_at,
            }
            for e in items
        ],
        "total": total,
    }


@router.get("/cross-camera", response_model=dict)
async def cross_camera_journey(
    person_id: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    visitor_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(MovementEvent).order_by(MovementEvent.occurred_at.asc())
    if person_id:
        q = q.where(MovementEvent.person_id == person_id)
    if employee_id:
        q = q.where(MovementEvent.employee_id == employee_id)
    if visitor_id:
        q = q.where(MovementEvent.visitor_id == visitor_id)
    if date_from:
        q = q.where(MovementEvent.occurred_at >= date_from)
    if date_to:
        q = q.where(MovementEvent.occurred_at <= date_to)

    events = (await db.execute(q)).scalars().all()
    cameras_visited = list({e.camera_id for e in events})
    zones_visited = list({e.zone_id for e in events if e.zone_id})

    return {
        "total_events": len(events),
        "cameras_visited": cameras_visited,
        "zones_visited": zones_visited,
        "trajectory": [
            {
                "camera_id": e.camera_id,
                "zone_id": e.zone_id,
                "event_type": e.event_type,
                "occurred_at": e.occurred_at,
                "snapshot_path": e.snapshot_path,
            }
            for e in events
        ],
    }
