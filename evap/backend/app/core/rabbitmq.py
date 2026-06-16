from __future__ import annotations

import json
from typing import Any, Optional

import aio_pika
from aio_pika import ExchangeType, Message, connect_robust
from aio_pika.abc import AbstractRobustConnection

from app.core.config import settings

# ---------------------------------------------------------------------------
# Queue names
# ---------------------------------------------------------------------------
QUEUE_AI_DETECTIONS = "ai.detections"
QUEUE_AI_ALERTS = "ai.alerts"
QUEUE_NOTIFY_EMAIL = "notifications.email"
QUEUE_NOTIFY_SMS = "notifications.sms"
QUEUE_NOTIFY_PUSH = "notifications.push"

ALL_QUEUES = [
    QUEUE_AI_DETECTIONS,
    QUEUE_AI_ALERTS,
    QUEUE_NOTIFY_EMAIL,
    QUEUE_NOTIFY_SMS,
    QUEUE_NOTIFY_PUSH,
]

# ---------------------------------------------------------------------------
# Connection holder
# ---------------------------------------------------------------------------
_connection: Optional[AbstractRobustConnection] = None


async def get_connection() -> AbstractRobustConnection:
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = await connect_robust(settings.RABBITMQ_URL)
    return _connection


async def init_rabbitmq() -> None:
    """Establish connection and declare all queues."""
    conn = await get_connection()
    async with conn.channel() as channel:
        await channel.set_qos(prefetch_count=10)
        for queue_name in ALL_QUEUES:
            await channel.declare_queue(queue_name, durable=True)


async def close_rabbitmq() -> None:
    global _connection
    if _connection and not _connection.is_closed:
        await _connection.close()
        _connection = None


# ---------------------------------------------------------------------------
# Publish helper
# ---------------------------------------------------------------------------
async def publish_message(queue_name: str, message_dict: Any) -> None:
    """Serialize message_dict to JSON and publish to the named durable queue."""
    conn = await get_connection()
    async with conn.channel() as channel:
        queue = await channel.declare_queue(queue_name, durable=True)
        body = json.dumps(message_dict, default=str).encode()
        await channel.default_exchange.publish(
            Message(
                body=body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=queue_name,
        )


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_rabbitmq():
    conn = await get_connection()
    channel = await conn.channel()
    try:
        yield channel
    finally:
        await channel.close()
