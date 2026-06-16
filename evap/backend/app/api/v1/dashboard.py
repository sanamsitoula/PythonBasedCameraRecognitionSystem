from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models import (
    AlertLog,
    AttendanceLog,
    CameraMaster,
    EmployeeMaster,
    OccupancyLog,
    VisitorMaster,
)
from app.models.vehicle import LicensePlateLog, VehicleMaster

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# /stats — flat structure matching Dashboard.jsx expectations
# ---------------------------------------------------------------------------
@router.get("/stats", response_model=dict)
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── cameras ──────────────────────────────────────────────────────────────
    cams = (await db.execute(
        select(CameraMaster).where(CameraMaster.is_active == True)
    )).scalars().all()

    cameras_list = [
        {
            "id": c.camera_id,
            "name": c.name,
            "status": c.status,
            "ip_address": str(c.ip_address) if c.ip_address else None,
            "site": c.manufacturer,
            "zone": c.model,
            "fps": c.fps,
            "camera_type": c.camera_type,
            "last_heartbeat": c.last_heartbeat.isoformat() if c.last_heartbeat else None,
        }
        for c in cams
    ]

    # ── active alerts ─────────────────────────────────────────────────────────
    active_alerts = (await db.execute(
        select(func.count(AlertLog.alert_id)).where(AlertLog.is_acknowledged == False)
    )).scalar_one() or 0

    # ── people present (latest occupancy per camera) ──────────────────────────
    latest_occ_sq = (
        select(
            OccupancyLog.camera_id,
            func.max(OccupancyLog.snapshot_time).label("latest"),
        )
        .where(OccupancyLog.camera_id.isnot(None))
        .group_by(OccupancyLog.camera_id)
        .subquery()
    )
    people_sum = (await db.execute(
        select(func.coalesce(func.sum(OccupancyLog.people_count), 0))
        .join(
            latest_occ_sq,
            (OccupancyLog.camera_id == latest_occ_sq.c.camera_id)
            & (OccupancyLog.snapshot_time == latest_occ_sq.c.latest),
        )
    )).scalar_one() or 0

    employees_present = (await db.execute(
        select(func.coalesce(func.sum(OccupancyLog.employees_count), 0))
        .join(
            latest_occ_sq,
            (OccupancyLog.camera_id == latest_occ_sq.c.camera_id)
            & (OccupancyLog.snapshot_time == latest_occ_sq.c.latest),
        )
    )).scalar_one() or 0

    visitors_present = (await db.execute(
        select(func.coalesce(func.sum(OccupancyLog.visitors_count), 0))
        .join(
            latest_occ_sq,
            (OccupancyLog.camera_id == latest_occ_sq.c.camera_id)
            & (OccupancyLog.snapshot_time == latest_occ_sq.c.latest),
        )
    )).scalar_one() or 0

    # ── occupancy percent ─────────────────────────────────────────────────────
    occ_pct = (await db.execute(
        select(func.coalesce(func.avg(OccupancyLog.occupancy_pct), 0))
        .join(
            latest_occ_sq,
            (OccupancyLog.camera_id == latest_occ_sq.c.camera_id)
            & (OccupancyLog.snapshot_time == latest_occ_sq.c.latest),
        )
    )).scalar_one() or 0

    # ── today's attendance entries ────────────────────────────────────────────
    today_entries = (await db.execute(
        select(func.count(AttendanceLog.attendance_id)).where(
            AttendanceLog.date >= today_start.date()
        )
    )).scalar_one() or 0

    # ── visitors today (seen today) ───────────────────────────────────────────
    visitors_today = (await db.execute(
        select(func.count(VisitorMaster.visitor_id)).where(
            VisitorMaster.last_seen_at >= today_start,
            VisitorMaster.is_active == True,
        )
    )).scalar_one() or 0

    # ── vehicles currently on-site ────────────────────────────────────────────
    try:
        vehicles_present = (await db.execute(
            select(func.count(VehicleMaster.vehicle_id)).where(
                VehicleMaster.is_active == True
            )
        )).scalar_one() or 0
    except Exception:
        vehicles_present = 0

    # ── department attendance (present today by department) ───────────────────
    try:
        dept_rows = (await db.execute(
            select(EmployeeMaster.department, func.count(AttendanceLog.attendance_id))
            .join(AttendanceLog, EmployeeMaster.employee_id == AttendanceLog.employee_id)
            .where(
                AttendanceLog.date >= today_start.date(),
                AttendanceLog.status == "present",
                EmployeeMaster.department.isnot(None),
            )
            .group_by(EmployeeMaster.department)
        )).all()

        total_by_dept = (await db.execute(
            select(EmployeeMaster.department, func.count(EmployeeMaster.employee_id))
            .where(EmployeeMaster.is_active == True, EmployeeMaster.department.isnot(None))
            .group_by(EmployeeMaster.department)
        )).all()
        total_dept_map = {row[0]: row[1] for row in total_by_dept}

        department_attendance = [
            {
                "dept": row[0],
                "present": row[1],
                "absent": max(0, total_dept_map.get(row[0], row[1]) - row[1]),
            }
            for row in dept_rows
        ]
    except Exception:
        department_attendance = []

    # ── vehicle type breakdown ────────────────────────────────────────────────
    try:
        vtype_rows = (await db.execute(
            select(LicensePlateLog.vehicle_type, func.count(LicensePlateLog.log_id))
            .where(LicensePlateLog.detected_at >= today_start)
            .group_by(LicensePlateLog.vehicle_type)
        )).all()
        vehicle_types = [{"name": row[0] or "Unknown", "value": row[1]} for row in vtype_rows if row[0]]
    except Exception:
        vehicle_types = []

    return {
        "timestamp": now.isoformat(),
        # flat stats for stat cards
        "people_present": int(people_present),
        "employees_present": int(employees_present),
        "visitors_today": int(visitors_today),
        "vehicles_present": int(vehicles_present),
        "occupancy_percent": round(float(occ_pct), 1),
        "today_entries": int(today_entries),
        "active_alerts": int(active_alerts),
        # arrays for charts
        "cameras": cameras_list,
        "department_attendance": department_attendance,
        "vehicle_types": vehicle_types,
    }


# ---------------------------------------------------------------------------
# /occupancy-history — time-series for OccupancyChart
# ---------------------------------------------------------------------------
@router.get("/occupancy-history", response_model=dict)
async def occupancy_history(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (await db.execute(
        select(OccupancyLog.snapshot_time, func.sum(OccupancyLog.people_count))
        .where(OccupancyLog.snapshot_time >= cutoff)
        .group_by(OccupancyLog.snapshot_time)
        .order_by(OccupancyLog.snapshot_time.asc())
    )).all()

    # Bucket into 30-min intervals
    from collections import defaultdict
    buckets: dict = defaultdict(int)
    for ts, cnt in rows:
        # round down to nearest 30 min
        minute = (ts.minute // 30) * 30
        key = ts.replace(minute=minute, second=0, microsecond=0).isoformat()
        buckets[key] += cnt or 0

    history = [{"time": k, "count": v} for k, v in sorted(buckets.items())]
    return {"history": history, "hours": hours}


# ---------------------------------------------------------------------------
# /recent-detections — for the Recent Detections panel
# ---------------------------------------------------------------------------
@router.get("/recent-detections", response_model=dict)
async def recent_detections(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    # Pull from alert_log as detection proxy — filter only detection-type alerts
    alerts = (await db.execute(
        select(AlertLog, CameraMaster.name)
        .outerjoin(CameraMaster, AlertLog.camera_id == CameraMaster.camera_id)
        .order_by(AlertLog.created_at.desc())
        .limit(limit)
    )).all()

    detections = []
    for alert, cam_name in alerts:
        detections.append({
            "id": alert.alert_id,
            "type": alert.alert_type,
            "name": (alert.details or {}).get("name") or alert.alert_type.replace("_", " ").title(),
            "camera_name": cam_name or "Unknown Camera",
            "timestamp": alert.created_at.isoformat() if alert.created_at else None,
            "snapshot": alert.snapshot_path,
            "severity": alert.severity,
        })

    return {"detections": detections, "total": len(detections)}


# ---------------------------------------------------------------------------
# /status — legacy endpoint (cameras-status alias)
# ---------------------------------------------------------------------------
@router.get("/cameras-status", response_model=dict)
async def cameras_status(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cams = (await db.execute(
        select(CameraMaster).where(CameraMaster.is_active == True)
    )).scalars().all()

    summary = {"online": 0, "offline": 0, "error": 0, "maintenance": 0}
    items = []
    for c in cams:
        summary[c.status] = summary.get(c.status, 0) + 1
        items.append({
            "id": c.camera_id,
            "name": c.name,
            "status": c.status,
            "ai_enabled": c.ai_enabled,
            "last_heartbeat": c.last_heartbeat.isoformat() if c.last_heartbeat else None,
        })

    return {"cameras": items, "summary": summary, "total": len(items)}
