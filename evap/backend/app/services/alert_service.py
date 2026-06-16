"""Alert creation, retrieval, acknowledgement and rule evaluation."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.alert import AlertAcknowledge, AlertCreate, AlertResponse, AlertStats

logger = logging.getLogger(__name__)

REDIS_CHANNEL = "evap:alerts"


async def create_alert(
    db: AsyncSession,
    redis,  # redis.asyncio.Redis
    alert_data: AlertCreate,
) -> AlertResponse:
    """Persist alert to DB then publish to Redis pub/sub channel."""
    from ..models.alert import AlertLog  # type: ignore[import]

    alert = AlertLog(
        alert_type=alert_data.alert_type,
        severity=alert_data.severity,
        site_id=alert_data.site_id,
        camera_id=alert_data.camera_id,
        person_id=alert_data.person_id,
        vehicle_id=alert_data.vehicle_id,
        zone_id=alert_data.zone_id,
        message=alert_data.message,
        details=alert_data.details,
        snapshot_path=alert_data.snapshot_path,
        is_acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    response = AlertResponse.model_validate(alert, from_attributes=True)

    # Publish to Redis for WebSocket broadcast
    try:
        payload = response.model_dump_json()
        await redis.publish(REDIS_CHANNEL, payload)
    except Exception as exc:
        logger.warning("Redis publish failed for alert %s: %s", alert.alert_id, exc)

    logger.info("Alert created id=%s type=%s severity=%s", alert.alert_id, alert.alert_type, alert.severity)
    return response


async def get_alerts(
    db: AsyncSession,
    site_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    unacknowledged_only: bool = False,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[AlertResponse]:
    from ..models.alert import AlertLog

    stmt = select(AlertLog)

    conditions = []
    if site_id is not None:
        conditions.append(AlertLog.site_id == site_id)
    if camera_id is not None:
        conditions.append(AlertLog.camera_id == camera_id)
    if severity is not None:
        conditions.append(AlertLog.severity == severity)
    if alert_type is not None:
        conditions.append(AlertLog.alert_type == alert_type)
    if unacknowledged_only:
        conditions.append(AlertLog.is_acknowledged == False)
    if date_from is not None:
        conditions.append(AlertLog.created_at >= date_from)
    if date_to is not None:
        conditions.append(AlertLog.created_at <= date_to)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(AlertLog.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [AlertResponse.model_validate(r, from_attributes=True) for r in rows]


async def acknowledge_alert(
    db: AsyncSession,
    alert_id: int,
    user_id: int,
    ack_data: AlertAcknowledge,
) -> Optional[AlertResponse]:
    from ..models.alert import AlertLog, AlertAudit  # type: ignore[import]

    stmt = select(AlertLog).where(AlertLog.alert_id == alert_id)
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    if alert is None:
        return None

    alert.is_acknowledged = True
    alert.acknowledged_by = user_id
    alert.acknowledged_at = datetime.now(timezone.utc)

    # Audit trail
    audit = AlertAudit(
        alert_id=alert_id,
        action="acknowledge",
        performed_by=user_id,
        notes=ack_data.notes,
        performed_at=alert.acknowledged_at,
    )
    db.add(audit)
    await db.commit()
    await db.refresh(alert)
    logger.info("Alert id=%s acknowledged by user=%s", alert_id, user_id)
    return AlertResponse.model_validate(alert, from_attributes=True)


async def get_alert_stats(
    db: AsyncSession,
    site_id: Optional[int] = None,
    target_date: Optional[date] = None,
) -> AlertStats:
    from ..models.alert import AlertLog

    if target_date is None:
        target_date = date.today()

    # by_type
    type_stmt = (
        select(AlertLog.alert_type, func.count().label("cnt"))
        .where(func.date(AlertLog.created_at) == target_date)
    )
    if site_id:
        type_stmt = type_stmt.where(AlertLog.site_id == site_id)
    type_stmt = type_stmt.group_by(AlertLog.alert_type)
    type_result = await db.execute(type_stmt)
    by_type = {r.alert_type: r.cnt for r in type_result.all()}

    # by_severity
    sev_stmt = (
        select(AlertLog.severity, func.count().label("cnt"))
        .where(func.date(AlertLog.created_at) == target_date)
    )
    if site_id:
        sev_stmt = sev_stmt.where(AlertLog.site_id == site_id)
    sev_stmt = sev_stmt.group_by(AlertLog.severity)
    sev_result = await db.execute(sev_stmt)
    by_severity = {r.severity: r.cnt for r in sev_result.all()}

    # unacknowledged
    unack_stmt = select(func.count()).select_from(AlertLog).where(
        AlertLog.is_acknowledged == False
    )
    if site_id:
        unack_stmt = unack_stmt.where(AlertLog.site_id == site_id)
    unack_result = await db.execute(unack_stmt)
    unacknowledged = unack_result.scalar_one_or_none() or 0

    # by hour
    hour_stmt = (
        select(func.extract("hour", AlertLog.created_at).label("hr"), func.count().label("cnt"))
        .where(func.date(AlertLog.created_at) == target_date)
    )
    if site_id:
        hour_stmt = hour_stmt.where(AlertLog.site_id == site_id)
    hour_stmt = hour_stmt.group_by("hr")
    hour_result = await db.execute(hour_stmt)
    by_hour = {int(r.hr): r.cnt for r in hour_result.all()}

    return AlertStats(
        site_id=site_id,
        date=str(target_date),
        total_today=sum(by_type.values()),
        unacknowledged=unacknowledged,
        by_type=by_type,
        by_severity=by_severity,
        by_hour=by_hour,
    )


async def check_alert_rules(
    db: AsyncSession, redis, event_data: Dict[str, Any]
) -> List[AlertResponse]:
    """
    Evaluate configured alert rules against incoming event data.
    Returns list of alerts that were created.

    Rules stored in DB (alert_rules table):
      - rule_type: 'threshold' | 'blacklist' | 'zone_violation' | 'behavior'
      - conditions: JSONB
      - action: severity + message template
    """
    from ..models.alert import AlertRule  # type: ignore[import]

    stmt = select(AlertRule).where(AlertRule.is_active == True)
    result = await db.execute(stmt)
    rules = result.scalars().all()

    triggered: List[AlertResponse] = []
    event_type = event_data.get("type", "")

    for rule in rules:
        try:
            if not _rule_matches(rule, event_data):
                continue

            alert_data = AlertCreate(
                alert_type=rule.rule_type,
                severity=rule.severity,
                site_id=event_data.get("site_id"),
                camera_id=event_data.get("camera_id"),
                person_id=event_data.get("person_id"),
                message=_render_message(rule.message_template, event_data),
                details={"event": event_data, "rule_id": rule.id},
            )
            alert = await create_alert(db, redis, alert_data)
            triggered.append(alert)
        except Exception as exc:
            logger.error("Rule evaluation error rule_id=%s: %s", rule.id, exc)

    return triggered


def _rule_matches(rule, event_data: Dict[str, Any]) -> bool:
    """Simple condition evaluator for alert rules."""
    conditions: dict = rule.conditions or {}
    rule_type = rule.rule_type

    if rule_type == "threshold":
        field = conditions.get("field")
        threshold = conditions.get("value", 0)
        operator = conditions.get("operator", "gt")
        actual = event_data.get(field)
        if actual is None:
            return False
        if operator == "gt":
            return float(actual) > float(threshold)
        elif operator == "lt":
            return float(actual) < float(threshold)
        elif operator == "eq":
            return float(actual) == float(threshold)

    elif rule_type == "blacklist":
        plate = event_data.get("plate_number", "")
        blacklist = conditions.get("plates", [])
        return plate in blacklist

    elif rule_type == "zone_violation":
        zone_id = event_data.get("zone_id")
        restricted_zones = conditions.get("zone_ids", [])
        return zone_id in restricted_zones

    elif rule_type == "behavior":
        event_subtype = event_data.get("behavior_type")
        target_types = conditions.get("behavior_types", [])
        return event_subtype in target_types

    return False


def _render_message(template: str, data: dict) -> str:
    """Naive string interpolation for alert message templates."""
    try:
        return template.format(**data)
    except (KeyError, ValueError):
        return template
