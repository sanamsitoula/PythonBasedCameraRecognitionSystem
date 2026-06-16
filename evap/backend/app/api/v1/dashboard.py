from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.core.dependencies import get_current_active_user
from app.models import (
    Alert,
    Camera,
    Employee,
    OccupancySnapshot,
    SystemMetric,
    Visitor,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
@router.get("/stats", response_model=dict)
async def dashboard_stats(
    site_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Cameras online
    cam_q = select(func.count(Camera.id)).where(Camera.is_active == True, Camera.status == "online")
    if site_id:
        cam_q = cam_q.where(Camera.site_id == site_id)
    online_cams = (await db.execute(cam_q)).scalar_one()

    total_cam_q = select(func.count(Camera.id)).where(Camera.is_active == True)
    if site_id:
        total_cam_q = total_cam_q.where(Camera.site_id == site_id)
    total_cams = (await db.execute(total_cam_q)).scalar_one()

    # Active alerts
    alert_q = select(func.count(Alert.id)).where(Alert.is_acknowledged == False)
    if site_id:
        alert_q = alert_q.where(Alert.site_id == site_id)
    active_alerts = (await db.execute(alert_q)).scalar_one()

    # Today's critical alerts
    crit_q = select(func.count(Alert.id)).where(
        Alert.severity == "critical",
        Alert.created_at >= today_start,
    )
    if site_id:
        crit_q = crit_q.where(Alert.site_id == site_id)
    critical_alerts = (await db.execute(crit_q)).scalar_one()

    # Current visitors
    vis_q = select(func.count(Visitor.id)).where(Visitor.is_present == True)
    if site_id:
        vis_q = vis_q.where(Visitor.site_id == site_id)
    active_visitors = (await db.execute(vis_q)).scalar_one()

    # Current occupancy (sum of latest snapshot per zone)
    occ_subq = (
        select(OccupancySnapshot.zone_id, func.max(OccupancySnapshot.recorded_at).label("latest"))
        .group_by(OccupancySnapshot.zone_id)
        .subquery()
    )
    occ = (
        await db.execute(
            select(func.sum(OccupancySnapshot.count)).select_from(
                OccupancySnapshot
            ).join(
                occ_subq,
                (OccupancySnapshot.zone_id == occ_subq.c.zone_id) & (OccupancySnapshot.recorded_at == occ_subq.c.latest),
            )
        )
    ).scalar_one()

    # Active employees (check in today, no check out)
    from app.models import AttendanceRecord
    emp_today_q = select(func.count(AttendanceRecord.id)).where(
        AttendanceRecord.date >= today_start,
        AttendanceRecord.check_out.is_(None),
        AttendanceRecord.status == "present",
    )
    active_employees = (await db.execute(emp_today_q)).scalar_one()

    return {
        "timestamp": now.isoformat(),
        "cameras": {"online": online_cams, "total": total_cams, "offline": total_cams - online_cams},
        "alerts": {"active": active_alerts, "critical_today": critical_alerts},
        "occupancy": {"current": occ or 0},
        "persons": {"active_employees": active_employees, "active_visitors": active_visitors},
    }


@router.get("/cameras-status", response_model=dict)
async def cameras_status(
    site_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(Camera).where(Camera.is_active == True)
    if site_id:
        q = q.where(Camera.site_id == site_id)
    cameras = (await db.execute(q)).scalars().all()

    status_summary: dict = {"online": 0, "offline": 0, "error": 0}
    items = []
    for c in cameras:
        status_summary[c.status] = status_summary.get(c.status, 0) + 1
        items.append({
            "id": c.id,
            "name": c.name,
            "site_id": c.site_id,
            "status": c.status,
            "ai_processing_enabled": c.ai_processing_enabled,
            "last_seen": c.last_seen,
        })

    return {"cameras": items, "summary": status_summary, "total": len(items)}


@router.get("/recent-alerts", response_model=dict)
async def recent_alerts(
    site_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if site_id:
        q = q.where(Alert.site_id == site_id)

    alerts = (await db.execute(q)).scalars().all()
    return {
        "items": [
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "title": a.title,
                "is_acknowledged": a.is_acknowledged,
                "camera_id": a.camera_id,
                "created_at": a.created_at,
            }
            for a in alerts
        ],
        "total": len(alerts),
    }


@router.get("/occupancy-trend", response_model=dict)
async def occupancy_trend(
    site_id: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = select(OccupancySnapshot).where(OccupancySnapshot.recorded_at >= cutoff)
    if site_id:
        q = q.where(OccupancySnapshot.site_id == site_id)
    q = q.order_by(OccupancySnapshot.recorded_at.asc())

    rows = (await db.execute(q)).scalars().all()

    # Bucket by hour — sum all zones per hour
    from collections import defaultdict
    hourly: dict = defaultdict(int)
    for r in rows:
        hour_key = r.recorded_at.replace(minute=0, second=0, microsecond=0).isoformat()
        hourly[hour_key] += r.count

    trend = [{"time": k, "count": v} for k, v in sorted(hourly.items())]
    peak = max((v for v in hourly.values()), default=0)

    return {"trend": trend, "peak": peak, "hours": hours}


@router.get("/system-health", response_model=dict)
async def system_health(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    latest = (
        await db.execute(
            select(SystemMetric).order_by(SystemMetric.recorded_at.desc()).limit(1)
        )
    ).scalar_one_or_none()

    if not latest:
        return {
            "cpu_percent": None,
            "memory_percent": None,
            "disk_percent": None,
            "gpu_percent": None,
            "active_streams": 0,
            "detections_per_second": None,
            "queue_depth": None,
            "recorded_at": None,
            "status": "no_data",
        }

    health_status = "healthy"
    if latest.cpu_percent and latest.cpu_percent > 90:
        health_status = "critical"
    elif latest.cpu_percent and latest.cpu_percent > 75:
        health_status = "warning"

    return {
        "cpu_percent": latest.cpu_percent,
        "memory_percent": latest.memory_percent,
        "disk_percent": latest.disk_percent,
        "gpu_percent": latest.gpu_percent,
        "active_streams": latest.active_streams,
        "detections_per_second": latest.detections_per_second,
        "queue_depth": latest.queue_depth,
        "recorded_at": latest.recorded_at,
        "status": health_status,
    }


# ---------------------------------------------------------------------------
# Real-time WebSocket dashboard
# ---------------------------------------------------------------------------
@router.websocket("/realtime")
async def realtime_dashboard(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Push live stats every 5 seconds
            async with AsyncSessionLocal() as db:
                now = datetime.now(timezone.utc)
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

                online_cams = (
                    await db.execute(
                        select(func.count(Camera.id)).where(Camera.status == "online", Camera.is_active == True)
                    )
                ).scalar_one()
                active_alerts = (
                    await db.execute(
                        select(func.count(Alert.id)).where(Alert.is_acknowledged == False)
                    )
                ).scalar_one()
                active_visitors = (
                    await db.execute(
                        select(func.count(Visitor.id)).where(Visitor.is_present == True)
                    )
                ).scalar_one()

            await websocket.send_json({
                "type": "stats",
                "timestamp": now.isoformat(),
                "online_cameras": online_cams,
                "active_alerts": active_alerts,
                "active_visitors": active_visitors,
            })
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
