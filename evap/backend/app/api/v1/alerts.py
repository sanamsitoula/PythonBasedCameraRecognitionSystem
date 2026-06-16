from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models import Alert, AlertRule, User

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AlertOut(BaseModel):
    id: int
    rule_id: Optional[str]
    alert_type: str
    severity: str
    title: str
    description: Optional[str]
    camera_id: Optional[str]
    zone_id: Optional[str]
    site_id: Optional[str]
    is_acknowledged: bool
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[datetime]
    snapshot_path: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AlertRuleCreate(BaseModel):
    name: str
    rule_type: str
    zone_id: Optional[str] = None
    camera_id: Optional[str] = None
    site_id: Optional[str] = None
    threshold_value: Optional[float] = None
    time_start: Optional[str] = None
    time_end: Optional[str] = None
    days_of_week: Optional[list] = None
    severity: str = "medium"
    notify_email: bool = True
    notify_sms: bool = False
    notify_push: bool = True


class AlertRuleOut(BaseModel):
    id: str
    name: str
    rule_type: str
    zone_id: Optional[str]
    camera_id: Optional[str]
    site_id: Optional[str]
    threshold_value: Optional[float]
    severity: str
    is_active: bool
    notify_email: bool
    notify_sms: bool
    notify_push: bool

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=dict)
async def list_alerts(
    severity: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    is_acknowledged: Optional[bool] = Query(None),
    site_id: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(Alert).order_by(Alert.created_at.desc())
    if severity:
        q = q.where(Alert.severity == severity)
    if alert_type:
        q = q.where(Alert.alert_type == alert_type)
    if is_acknowledged is not None:
        q = q.where(Alert.is_acknowledged == is_acknowledged)
    if site_id:
        q = q.where(Alert.site_id == site_id)
    if camera_id:
        q = q.where(Alert.camera_id == camera_id)
    if date_from:
        q = q.where(Alert.created_at >= date_from)
    if date_to:
        q = q.where(Alert.created_at <= date_to)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [AlertOut.model_validate(a) for a in items], "total": total}


@router.get("/active", response_model=dict)
async def active_alerts(
    severity: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(Alert).where(Alert.is_acknowledged == False).order_by(Alert.created_at.desc())
    if severity:
        q = q.where(Alert.severity == severity)
    if site_id:
        q = q.where(Alert.site_id == site_id)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [AlertOut.model_validate(a) for a in items], "total": total}


@router.put("/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert(
    alert_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_acknowledged = True
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
    await db.commit()


@router.get("/stats", response_model=dict)
async def alert_stats(
    site_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    base_where = []
    if site_id:
        base_where.append(Alert.site_id == site_id)
    if date_from:
        base_where.append(Alert.created_at >= date_from)
    if date_to:
        base_where.append(Alert.created_at <= date_to)

    by_severity = (
        await db.execute(
            select(Alert.severity, func.count(Alert.id).label("count"))
            .where(*base_where)
            .group_by(Alert.severity)
        )
    ).all()

    by_type = (
        await db.execute(
            select(Alert.alert_type, func.count(Alert.id).label("count"))
            .where(*base_where)
            .group_by(Alert.alert_type)
        )
    ).all()

    total = sum(r.count for r in by_severity)
    ack = (
        await db.execute(
            select(func.count(Alert.id)).where(*base_where, Alert.is_acknowledged == True)
        )
    ).scalar_one()

    return {
        "total": total,
        "acknowledged": ack,
        "unacknowledged": total - ack,
        "by_severity": {r.severity: r.count for r in by_severity},
        "by_type": {r.alert_type: r.count for r in by_type},
    }


@router.post("/rules", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    body: AlertRuleCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    rule = AlertRule(**body.model_dump(), created_by=current_user.id)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("/rules", response_model=dict)
async def list_alert_rules(
    is_active: Optional[bool] = Query(None),
    site_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(AlertRule)
    if is_active is not None:
        q = q.where(AlertRule.is_active == is_active)
    if site_id:
        q = q.where(AlertRule.site_id == site_id)
    items = (await db.execute(q)).scalars().all()
    return {"items": [AlertRuleOut.model_validate(r) for r in items], "total": len(items)}
