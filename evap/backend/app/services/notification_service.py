"""Multi-channel notification dispatch service."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config accessor
# ---------------------------------------------------------------------------

def _get_settings():
    from ..core.config import settings  # type: ignore[import]
    return settings


# ---------------------------------------------------------------------------
# Channel implementations
# ---------------------------------------------------------------------------

async def send_email(recipient: str, subject: str, body: str) -> bool:
    """Send HTML email via SMTP. Returns True on success."""
    import asyncio

    def _smtp_send():
        settings = _get_settings()
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = recipient
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_TLS:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, [recipient], msg.as_string())
        return True

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _smtp_send)
    except Exception as exc:
        logger.error("Email send failed to %s: %s", recipient, exc)
        return False


async def send_sms(phone: str, message: str) -> bool:
    """
    Send SMS via configured provider (Twilio / AWS SNS / MSG91).
    Currently implements MSG91 as primary with Twilio fallback.
    """
    import asyncio
    import httpx

    settings = _get_settings()
    provider = getattr(settings, "SMS_PROVIDER", "msg91")

    async def _via_msg91() -> bool:
        url = "https://api.msg91.com/api/v5/flow/"
        payload = {
            "template_id": settings.SMS_TEMPLATE_ID,
            "short_url": "0",
            "mobiles": phone.lstrip("+"),
            "var": message,
        }
        headers = {"authkey": settings.MSG91_AUTH_KEY, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
            return resp.status_code == 200

    async def _via_twilio() -> bool:
        from twilio.rest import Client  # type: ignore[import]

        def _call():
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            client.messages.create(
                body=message,
                from_=settings.TWILIO_FROM_NUMBER,
                to=phone,
            )
            return True

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _call)

    try:
        if provider == "msg91":
            return await _via_msg91()
        else:
            return await _via_twilio()
    except Exception as exc:
        logger.error("SMS send failed to %s: %s", phone, exc)
        return False


async def send_whatsapp(phone: str, message: str) -> bool:
    """
    WhatsApp Business API via Meta Cloud API.
    Stub – replace template_name with actual approved template.
    """
    import httpx

    settings = _get_settings()
    wa_token = getattr(settings, "WHATSAPP_TOKEN", None)
    wa_phone_id = getattr(settings, "WHATSAPP_PHONE_ID", None)

    if not wa_token or not wa_phone_id:
        logger.warning("WhatsApp credentials not configured")
        return False

    url = f"https://graph.facebook.com/v18.0/{wa_phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": phone.lstrip("+"),
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }
    headers = {
        "Authorization": f"Bearer {wa_token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
            return resp.status_code == 200
    except Exception as exc:
        logger.error("WhatsApp send failed to %s: %s", phone, exc)
        return False


async def send_push_notification(device_token: str, title: str, body: str) -> bool:
    """
    Firebase Cloud Messaging (FCM) v1 API push notification.
    Requires GOOGLE_APPLICATION_CREDENTIALS env var or FCM_SERVER_KEY setting.
    """
    import httpx

    settings = _get_settings()
    fcm_key = getattr(settings, "FCM_SERVER_KEY", None)
    if not fcm_key:
        logger.warning("FCM_SERVER_KEY not configured – push notification skipped")
        return False

    url = "https://fcm.googleapis.com/fcm/send"
    payload = {
        "to": device_token,
        "notification": {"title": title, "body": body},
        "priority": "high",
    }
    headers = {
        "Authorization": f"key={fcm_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
            result = resp.json()
            if result.get("failure", 0) > 0:
                logger.warning("FCM send partial failure: %s", result)
                return False
            return True
    except Exception as exc:
        logger.error("Push notification failed to %s: %s", device_token, exc)
        return False


async def log_notification(
    db: AsyncSession,
    alert_id: int,
    channel: str,
    recipient: str,
    status: str,
    error: Optional[str] = None,
) -> None:
    from ..models.notification import NotificationLog  # type: ignore[import]

    log = NotificationLog(
        alert_id=alert_id,
        channel=channel,
        recipient=recipient,
        status=status,
        sent_at=datetime.now(timezone.utc) if status == "sent" else None,
        error_message=error,
    )
    db.add(log)
    await db.commit()


async def send_alert_notifications(db: AsyncSession, alert_id: int) -> None:
    """
    Look up the alert, then dispatch to all configured notification channels
    for users/groups subscribed to that alert severity or type.
    """
    from ..models.alert import AlertLog  # type: ignore[import]
    from ..models.notification import NotificationConfig  # type: ignore[import]

    # Load alert
    alert_stmt = select(AlertLog).where(AlertLog.alert_id == alert_id)
    alert_result = await db.execute(alert_stmt)
    alert = alert_result.scalar_one_or_none()
    if alert is None:
        logger.warning("send_alert_notifications: alert_id=%s not found", alert_id)
        return

    # Load notification configs matching this severity / type
    cfg_stmt = select(NotificationConfig).where(
        NotificationConfig.is_active == True
    )
    cfg_result = await db.execute(cfg_stmt)
    configs = cfg_result.scalars().all()

    for cfg in configs:
        # Filter: if config specifies severities, only match those
        if cfg.severities and alert.severity not in cfg.severities:
            continue
        if cfg.alert_types and alert.alert_type not in cfg.alert_types:
            continue

        message_body = (
            f"<b>[{alert.severity.upper()}] {alert.alert_type}</b><br>"
            f"{alert.message}<br>"
            f"Time: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        plain_body = f"[{alert.severity.upper()}] {alert.alert_type}: {alert.message}"

        channel = cfg.channel
        recipient = cfg.recipient
        success = False
        error_msg = None

        try:
            if channel == "email":
                success = await send_email(
                    recipient,
                    f"EVAP Alert: {alert.alert_type}",
                    message_body,
                )
            elif channel == "sms":
                success = await send_sms(recipient, plain_body)
            elif channel == "whatsapp":
                success = await send_whatsapp(recipient, plain_body)
            elif channel == "push":
                success = await send_push_notification(
                    recipient,
                    f"Alert: {alert.alert_type}",
                    alert.message,
                )
        except Exception as exc:
            error_msg = str(exc)
            logger.error("Notification dispatch error channel=%s: %s", channel, exc)

        await log_notification(
            db,
            alert_id=alert_id,
            channel=channel,
            recipient=recipient,
            status="sent" if success else "failed",
            error=error_msg,
        )
