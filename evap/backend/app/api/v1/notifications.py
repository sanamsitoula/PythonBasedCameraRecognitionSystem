from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models import NotificationLog, NotificationSetting, User

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class NotificationLogOut(BaseModel):
    id: int
    channel: str
    recipient: Optional[str]
    subject: Optional[str]
    message: str
    status: str
    alert_id: Optional[int]
    sent_at: datetime

    class Config:
        from_attributes = True


class NotificationSettingOut(BaseModel):
    user_id: str
    email_enabled: bool
    sms_enabled: bool
    push_enabled: bool
    whatsapp_enabled: bool
    alert_severities: Optional[list]
    quiet_hours_start: Optional[str]
    quiet_hours_end: Optional[str]

    class Config:
        from_attributes = True


class NotificationSettingUpdate(BaseModel):
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    whatsapp_enabled: Optional[bool] = None
    alert_severities: Optional[list] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


class TestNotificationRequest(BaseModel):
    channel: str  # email | sms | push | whatsapp
    recipient: Optional[str] = None
    message: str = "This is a test notification from EVAP."


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=dict)
async def list_notifications(
    channel: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(NotificationLog).where(NotificationLog.user_id == current_user.id)
    if channel:
        q = q.where(NotificationLog.channel == channel)
    if status:
        q = q.where(NotificationLog.status == status)
    if date_from:
        q = q.where(NotificationLog.sent_at >= date_from)
    if date_to:
        q = q.where(NotificationLog.sent_at <= date_to)
    q = q.order_by(NotificationLog.sent_at.desc())

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [NotificationLogOut.model_validate(n) for n in items], "total": total}


@router.post("/test", status_code=status.HTTP_200_OK)
async def send_test_notification(
    body: TestNotificationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # Publish to RabbitMQ queue for the appropriate channel
    try:
        from app.core.rabbitmq import publish_message, QUEUE_NOTIFY_EMAIL, QUEUE_NOTIFY_SMS, QUEUE_NOTIFY_PUSH
        queue_map = {
            "email": QUEUE_NOTIFY_EMAIL,
            "sms": QUEUE_NOTIFY_SMS,
            "push": QUEUE_NOTIFY_PUSH,
        }
        queue = queue_map.get(body.channel, QUEUE_NOTIFY_EMAIL)
        await publish_message(queue, {
            "channel": body.channel,
            "recipient": body.recipient or current_user.email,
            "message": body.message,
            "user_id": current_user.id,
            "test": True,
        })
        delivery_status = "queued"
    except Exception:
        delivery_status = "failed"

    # Log it
    log = NotificationLog(
        user_id=current_user.id,
        channel=body.channel,
        recipient=body.recipient or current_user.email,
        subject="Test Notification",
        message=body.message,
        status=delivery_status,
    )
    db.add(log)
    await db.commit()

    return {"channel": body.channel, "status": delivery_status, "message": "Test notification dispatched"}


@router.get("/settings", response_model=NotificationSettingOut)
async def get_notification_settings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    settings_row = (
        await db.execute(
            select(NotificationSetting).where(NotificationSetting.user_id == current_user.id)
        )
    ).scalar_one_or_none()

    if not settings_row:
        # Create defaults
        settings_row = NotificationSetting(user_id=current_user.id, alert_severities=["high", "critical"])
        db.add(settings_row)
        await db.commit()
        await db.refresh(settings_row)

    return settings_row


@router.put("/settings", response_model=NotificationSettingOut)
async def update_notification_settings(
    body: NotificationSettingUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    settings_row = (
        await db.execute(
            select(NotificationSetting).where(NotificationSetting.user_id == current_user.id)
        )
    ).scalar_one_or_none()

    if not settings_row:
        settings_row = NotificationSetting(user_id=current_user.id)
        db.add(settings_row)

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(settings_row, field, value)

    await db.commit()
    await db.refresh(settings_row)
    return settings_row
