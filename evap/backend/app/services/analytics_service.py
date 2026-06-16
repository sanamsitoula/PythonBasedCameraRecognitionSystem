"""Analytics queries: dashboard stats, occupancy, heatmap, behavior events, journeys."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

import numpy as np
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.analytics import (
    BehaviorEventResponse,
    CrossCameraJourney,
    CameraTimelineEntry,
    DashboardStats,
    HeatmapData,
    HeatmapPoint,
    OccupancyDataPoint,
)

logger = logging.getLogger(__name__)

DASHBOARD_CACHE_KEY = "evap:dashboard:{site_id}"
CACHE_TTL = 60  # seconds


async def get_dashboard_stats(
    db: AsyncSession,
    redis,
    site_id: Optional[int] = None,
) -> DashboardStats:
    """Try Redis cache first, fallback to DB query."""
    cache_key = DASHBOARD_CACHE_KEY.format(site_id=site_id or "all")

    try:
        cached = await redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            stats = DashboardStats(**data)
            stats.from_cache = True
            return stats
    except Exception as exc:
        logger.warning("Redis cache read failed: %s", exc)

    stats = await _compute_dashboard_stats(db, site_id)

    try:
        await redis.setex(cache_key, CACHE_TTL, stats.model_dump_json())
    except Exception as exc:
        logger.warning("Redis cache write failed: %s", exc)

    return stats


async def _compute_dashboard_stats(
    db: AsyncSession, site_id: Optional[int]
) -> DashboardStats:
    from ..models.occupancy import OccupancyLog  # type: ignore[import]
    from ..models.alert import AlertLog  # type: ignore[import]
    from ..models.camera import CameraMaster  # type: ignore[import]
    from ..models.zone_history import ZoneHistory  # type: ignore[import]

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Latest occupancy snapshot (last 5 min)
    five_min_ago = now - timedelta(minutes=5)
    occ_stmt = (
        select(
            func.sum(OccupancyLog.people_count).label("people"),
            func.sum(OccupancyLog.employees_count).label("employees"),
            func.sum(OccupancyLog.visitors_count).label("visitors"),
        )
        .where(OccupancyLog.snapshot_time >= five_min_ago)
    )
    occ_result = await db.execute(occ_stmt)
    occ_row = occ_result.one_or_none()
    people_present = int(occ_row.people or 0) if occ_row else 0
    employees_present = int(occ_row.employees or 0) if occ_row else 0
    visitors_present = int(occ_row.visitors or 0) if occ_row else 0

    # Vehicles present (license_plate_log with no exit_time)
    from ..models.vehicle import LicensePlateLog  # type: ignore[import]
    veh_stmt = select(func.count()).select_from(LicensePlateLog).where(
        LicensePlateLog.exit_time.is_(None)
    )
    if site_id:
        veh_stmt = veh_stmt.where(LicensePlateLog.site_id == site_id)
    veh_result = await db.execute(veh_stmt)
    vehicles_present = veh_result.scalar_one_or_none() or 0

    # Occupancy pct – aggregate over all zones with max_capacity
    from ..models.zone_history import ZoneHistory  # noqa: F811
    from ..models.site import ZoneMaster  # type: ignore[import]
    cap_stmt = select(func.sum(ZoneMaster.max_capacity)).where(
        ZoneMaster.max_capacity.isnot(None)
    )
    cap_result = await db.execute(cap_stmt)
    total_capacity = cap_result.scalar_one_or_none() or 0
    occ_pct = min((people_present / total_capacity * 100), 100.0) if total_capacity else 0.0

    # Today entries/exits
    entry_stmt = (
        select(func.count())
        .select_from(LicensePlateLog)
        .where(
            and_(
                LicensePlateLog.entry_time >= today_start,
                LicensePlateLog.direction == "entry",
            )
        )
    )
    exit_stmt = entry_stmt.where(LicensePlateLog.direction == "exit")
    entry_count = (await db.execute(entry_stmt)).scalar_one_or_none() or 0
    exit_count = (await db.execute(exit_stmt)).scalar_one_or_none() or 0

    # Alerts
    alert_stmt = select(AlertLog.severity, func.count().label("cnt")).where(
        AlertLog.is_acknowledged == False
    )
    if site_id:
        alert_stmt = alert_stmt.where(AlertLog.site_id == site_id)
    alert_stmt = alert_stmt.group_by(AlertLog.severity)
    alert_result = await db.execute(alert_stmt)
    alert_rows = {r.severity: r.cnt for r in alert_result.all()}
    active_alerts = sum(alert_rows.values())
    critical_alerts = alert_rows.get("critical", 0) + alert_rows.get("emergency", 0)

    # Camera health
    cam_stmt = select(CameraMaster.status, func.count().label("cnt")).where(
        CameraMaster.is_active == True
    )
    if site_id:
        cam_stmt = cam_stmt.where(CameraMaster.site_id == site_id)
    cam_stmt = cam_stmt.group_by(CameraMaster.status)
    cam_result = await db.execute(cam_stmt)
    cam_rows = {r.status: r.cnt for r in cam_result.all()}
    cameras_online = cam_rows.get("online", 0)
    cameras_offline = cam_rows.get("offline", 0) + cam_rows.get("error", 0)

    return DashboardStats(
        site_id=site_id,
        timestamp=now,
        people_present=people_present,
        employees_present=employees_present,
        visitors_present=visitors_present,
        vehicles_present=vehicles_present,
        occupancy_pct=round(occ_pct, 2),
        today_entries=entry_count,
        today_exits=exit_count,
        active_alerts=active_alerts,
        critical_alerts=critical_alerts,
        cameras_online=cameras_online,
        cameras_offline=cameras_offline,
        from_cache=False,
    )


async def get_occupancy_trend(
    db: AsyncSession,
    zone_id: Optional[int],
    hours: int = 24,
) -> List[OccupancyDataPoint]:
    from ..models.occupancy import OccupancyLog
    from ..models.site import ZoneMaster

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(
            func.date_trunc("hour", OccupancyLog.snapshot_time).label("ts"),
            OccupancyLog.zone_id,
            func.avg(OccupancyLog.people_count).label("avg_count"),
            func.avg(OccupancyLog.occupancy_pct).label("avg_pct"),
        )
        .where(OccupancyLog.snapshot_time >= since)
        .group_by("ts", OccupancyLog.zone_id)
        .order_by("ts")
    )
    if zone_id is not None:
        stmt = stmt.where(OccupancyLog.zone_id == zone_id)

    result = await db.execute(stmt)
    rows = result.all()
    return [
        OccupancyDataPoint(
            timestamp=r.ts,
            zone_id=r.zone_id,
            count=int(r.avg_count or 0),
            pct=round(float(r.avg_pct or 0), 2),
        )
        for r in rows
    ]


async def get_heatmap_data(
    db: AsyncSession,
    floor_id: int,
    date_from: datetime,
    date_to: datetime,
) -> HeatmapData:
    """Aggregate movement detections into a grid and return normalised heatmap points."""
    from ..models.zone_history import ZoneHistory
    from ..models.camera import CameraMaster
    from ..models.site import FloorMaster, ZoneMaster

    # Get floor dimensions
    floor_stmt = select(FloorMaster).where(FloorMaster.floor_id == floor_id)
    floor_result = await db.execute(floor_stmt)
    floor = floor_result.scalar_one_or_none()
    width = int(floor.width_meters * 10) if floor and floor.width_meters else 1000
    height = int(floor.height_meters * 10) if floor and floor.height_meters else 800

    grid_size = 50
    grid_cols = width // grid_size + 1
    grid_rows = height // grid_size + 1
    grid = np.zeros((grid_rows, grid_cols), dtype=np.float32)

    # Get zone centroids on this floor and accumulate dwell times
    zone_stmt = (
        select(ZoneMaster.zone_id, ZoneMaster.polygon)
        .where(ZoneMaster.floor_id == floor_id)
    )
    zone_result = await db.execute(zone_stmt)
    zone_rows = zone_result.all()
    zone_centroids: dict = {}
    for z_id, polygon in zone_rows:
        if polygon:
            xs = [p["x"] for p in polygon]
            ys = [p["y"] for p in polygon]
            zone_centroids[z_id] = (sum(xs) / len(xs), sum(ys) / len(ys))

    # Query dwell events
    dwell_stmt = (
        select(
            ZoneHistory.zone_id,
            func.count().label("events"),
            func.sum(ZoneHistory.duration_seconds).label("total_dwell"),
        )
        .where(
            and_(
                ZoneHistory.entry_time >= date_from,
                ZoneHistory.entry_time <= date_to,
            )
        )
        .group_by(ZoneHistory.zone_id)
    )
    dwell_result = await db.execute(dwell_stmt)
    dwell_rows = dwell_result.all()

    total_detections = 0
    for zone_id, events, total_dwell in dwell_rows:
        total_detections += events
        centroid = zone_centroids.get(zone_id)
        if centroid is None:
            continue
        cx, cy = centroid
        gx = int(cx / grid_size)
        gy = int(cy / grid_size)
        if 0 <= gy < grid_rows and 0 <= gx < grid_cols:
            grid[gy, gx] += float(total_dwell or events)

    # Normalise grid
    max_val = grid.max()
    if max_val > 0:
        grid /= max_val

    points = []
    for gy in range(grid_rows):
        for gx in range(grid_cols):
            intensity = float(grid[gy, gx])
            if intensity > 0.01:
                points.append(HeatmapPoint(
                    x=float(gx * grid_size),
                    y=float(gy * grid_size),
                    intensity=round(intensity, 4),
                ))

    return HeatmapData(
        floor_id=floor_id,
        width=width,
        height=height,
        grid_size=grid_size,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        points=points,
        total_detections=total_detections,
    )


async def get_behavior_events(
    db: AsyncSession,
    camera_id: Optional[int] = None,
    event_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[BehaviorEventResponse]:
    from ..models.behavior import BehaviorEvent  # type: ignore[import]

    stmt = select(BehaviorEvent)
    conditions = []
    if camera_id is not None:
        conditions.append(BehaviorEvent.camera_id == camera_id)
    if event_type is not None:
        conditions.append(BehaviorEvent.event_type == event_type)
    if date_from is not None:
        conditions.append(BehaviorEvent.started_at >= date_from)
    if date_to is not None:
        conditions.append(BehaviorEvent.started_at <= date_to)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(BehaviorEvent.started_at.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    events = []
    for r in rows:
        duration = None
        if r.started_at and r.ended_at:
            duration = int((r.ended_at - r.started_at).total_seconds())
        events.append(BehaviorEventResponse(
            event_id=r.event_id,
            camera_id=r.camera_id,
            zone_id=r.zone_id,
            event_type=r.event_type,
            person_id=r.person_id,
            confidence=r.confidence,
            started_at=r.started_at,
            ended_at=r.ended_at,
            duration_seconds=duration,
            snapshot_path=r.snapshot_path,
            alert_generated=r.alert_generated,
        ))
    return events


async def get_cross_camera_journey(
    db: AsyncSession,
    person_id: int,
    target_date: date,
) -> CrossCameraJourney:
    from ..models.zone_history import ZoneHistory
    from ..models.camera import CameraMaster
    from ..models.site import ZoneMaster

    start_dt = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)

    stmt = (
        select(
            ZoneHistory,
            CameraMaster.name.label("cam_name"),
            ZoneMaster.name.label("zone_name"),
        )
        .outerjoin(CameraMaster, ZoneHistory.camera_id == CameraMaster.camera_id)
        .outerjoin(ZoneMaster, ZoneHistory.zone_id == ZoneMaster.zone_id)
        .where(
            and_(
                ZoneHistory.person_id == person_id,
                ZoneHistory.entry_time >= start_dt,
                ZoneHistory.entry_time < end_dt,
            )
        )
        .order_by(ZoneHistory.entry_time)
    )
    result = await db.execute(stmt)
    rows = result.all()

    timeline = []
    camera_ids = set()
    for zh, cam_name, zone_name in rows:
        if zh.camera_id:
            camera_ids.add(zh.camera_id)
        timeline.append(CameraTimelineEntry(
            camera_id=zh.camera_id or 0,
            camera_name=cam_name,
            zone_id=zh.zone_id,
            zone_name=zone_name,
            seen_at=zh.entry_time,
        ))

    person_type = rows[0][0].person_type if rows else "unknown"
    journey_start = timeline[0].seen_at if timeline else None
    journey_end = timeline[-1].seen_at if timeline else None
    zones_visited = len({e.zone_id for e in timeline if e.zone_id})

    return CrossCameraJourney(
        person_id=person_id,
        person_type=person_type,
        date=str(target_date),
        cameras=list(camera_ids),
        timeline=timeline,
        total_zones_visited=zones_visited,
        journey_start=journey_start,
        journey_end=journey_end,
    )


async def calculate_daily_analytics(
    db: AsyncSession,
    target_date: date,
    site_id: Optional[int] = None,
) -> None:
    """End-of-day aggregation: upsert analytics_daily row."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from ..models.analytics import AnalyticsDaily  # type: ignore[import]
    from ..models.vehicle import LicensePlateLog
    from ..models.zone_history import ZoneHistory

    start_dt = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)

    # Total entries/exits from license_plate_log
    entry_stmt = select(func.count()).select_from(LicensePlateLog).where(
        and_(LicensePlateLog.entry_time >= start_dt, LicensePlateLog.entry_time < end_dt)
    )
    if site_id:
        entry_stmt = entry_stmt.where(LicensePlateLog.site_id == site_id)
    total_entries = (await db.execute(entry_stmt)).scalar_one_or_none() or 0

    # Unique visitors (people with person_type='visitor')
    vis_stmt = select(func.count(ZoneHistory.person_id.distinct())).where(
        and_(
            ZoneHistory.entry_time >= start_dt,
            ZoneHistory.entry_time < end_dt,
            ZoneHistory.person_type == "visitor",
        )
    )
    unique_visitors = (await db.execute(vis_stmt)).scalar_one_or_none() or 0

    # Peak occupancy from occupancy_log
    from ..models.occupancy import OccupancyLog
    peak_stmt = select(func.max(OccupancyLog.people_count)).where(
        and_(OccupancyLog.snapshot_time >= start_dt, OccupancyLog.snapshot_time < end_dt)
    )
    peak_occupancy = (await db.execute(peak_stmt)).scalar_one_or_none() or 0

    avg_stmt = select(func.avg(OccupancyLog.people_count)).where(
        and_(OccupancyLog.snapshot_time >= start_dt, OccupancyLog.snapshot_time < end_dt)
    )
    avg_occupancy = float((await db.execute(avg_stmt)).scalar_one_or_none() or 0)

    # Upsert
    stmt = pg_insert(AnalyticsDaily).values(
        date=target_date,
        site_id=site_id,
        total_entries=total_entries,
        total_exits=total_entries,  # approximate
        peak_occupancy=peak_occupancy,
        avg_occupancy=round(avg_occupancy, 2),
        unique_visitors=unique_visitors,
        calculated_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=["date", "site_id"],
        set_={
            "total_entries": total_entries,
            "peak_occupancy": peak_occupancy,
            "avg_occupancy": round(avg_occupancy, 2),
            "unique_visitors": unique_visitors,
            "calculated_at": datetime.now(timezone.utc),
        },
    )
    await db.execute(stmt)
    await db.commit()
    logger.info("Daily analytics computed for date=%s site=%s", target_date, site_id)
