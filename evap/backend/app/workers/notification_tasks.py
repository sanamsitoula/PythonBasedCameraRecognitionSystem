"""Celery tasks for async notification dispatch."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from .celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _get_async_db():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    import os

    try:
        from ..core.config import settings  # type: ignore[import]
        db_url = settings.DATABASE_URL
    except Exception:
        db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://evap:evap@localhost:5432/evap")

    engine = create_async_engine(db_url)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Single alert dispatch
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.workers.notification_tasks.send_alert_notification_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="notifications",
)
def send_alert_notification_task(self, alert_id: int) -> None:
    """Dispatch notifications for a single alert across all configured channels."""
    async def _dispatch():
        from ..services.notification_service import send_alert_notifications  # type: ignore[import]

        Session = _get_async_db()
        async with Session() as db:
            await send_alert_notifications(db, alert_id)

    try:
        _run_async(_dispatch())
        logger.info("Notifications dispatched for alert_id=%s", alert_id)
    except Exception as exc:
        logger.error("send_alert_notification_task failed for alert_id=%s: %s", alert_id, exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Bulk broadcast
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.workers.notification_tasks.send_bulk_notification",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="notifications",
)
def send_bulk_notification(
    self,
    recipient_list: List[Dict[str, str]],
    message: Dict[str, Any],
) -> Dict[str, int]:
    """
    Send a notification to a list of recipients.

    recipient_list: [{"channel": "email|sms|push|whatsapp", "address": "..."}]
    message:        {"subject": "...", "body": "...", "title": "..."}

    Returns counts: {"sent": N, "failed": M}
    """
    from ..services.notification_service import (  # type: ignore[import]
        send_email, send_sms, send_whatsapp, send_push_notification,
    )

    async def _bulk():
        sent = failed = 0
        for recipient in recipient_list:
            channel = recipient.get("channel", "email")
            address = recipient.get("address", "")
            if not address:
                failed += 1
                continue
            try:
                if channel == "email":
                    ok = await send_email(
                        address,
                        message.get("subject", "EVAP Notification"),
                        message.get("body", ""),
                    )
                elif channel == "sms":
                    ok = await send_sms(address, message.get("body", ""))
                elif channel == "whatsapp":
                    ok = await send_whatsapp(address, message.get("body", ""))
                elif channel == "push":
                    ok = await send_push_notification(
                        address,
                        message.get("title", "EVAP"),
                        message.get("body", ""),
                    )
                else:
                    logger.warning("Unknown channel: %s", channel)
                    ok = False

                if ok:
                    sent += 1
                else:
                    failed += 1
            except Exception as exc:
                logger.error("Bulk send error channel=%s address=%s: %s", channel, address, exc)
                failed += 1

        return {"sent": sent, "failed": failed}

    try:
        result = _run_async(_bulk())
        logger.info(
            "Bulk notification complete: sent=%d failed=%d",
            result["sent"], result["failed"],
        )
        return result
    except Exception as exc:
        logger.error("send_bulk_notification failed: %s", exc)
        raise self.retry(exc=exc)
