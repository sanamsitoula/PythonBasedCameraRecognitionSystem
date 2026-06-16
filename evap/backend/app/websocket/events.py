"""WebSocket event types, models, and Redis pub/sub bridge."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel

from .manager import ConnectionManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

ALERT_NEW = "ALERT_NEW"
OCCUPANCY_UPDATE = "OCCUPANCY_UPDATE"
CAMERA_STATUS = "CAMERA_STATUS"
PERSON_DETECTED = "PERSON_DETECTED"
VEHICLE_DETECTED = "VEHICLE_DETECTED"
BEHAVIOR_EVENT = "BEHAVIOR_EVENT"
SYSTEM_HEALTH = "SYSTEM_HEALTH"
HEARTBEAT = "HEARTBEAT"

# Redis channels → WS event type mapping
REDIS_CHANNEL_MAP: Dict[str, str] = {
    "evap:alerts": ALERT_NEW,
    "evap:ws:broadcast": "__passthrough__",   # already formatted
}


# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------

class WebSocketEvent(BaseModel):
    type: str
    data: Dict[str, Any] = {}
    timestamp: datetime = None  # type: ignore[assignment]
    site_id: Optional[int] = None

    def model_post_init(self, __context: Any) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now(timezone.utc))

    def to_json(self) -> str:
        return self.model_dump_json()


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def make_alert_event(alert_data: dict, site_id: Optional[int] = None) -> WebSocketEvent:
    return WebSocketEvent(type=ALERT_NEW, data=alert_data, site_id=site_id)


def make_occupancy_event(camera_id: int, zone_id: Optional[int], count: int, pct: float) -> WebSocketEvent:
    return WebSocketEvent(
        type=OCCUPANCY_UPDATE,
        data={"camera_id": camera_id, "zone_id": zone_id, "count": count, "pct": pct},
    )


def make_camera_status_event(camera_id: int, status: str, site_id: Optional[int] = None) -> WebSocketEvent:
    return WebSocketEvent(
        type=CAMERA_STATUS,
        data={"camera_id": camera_id, "status": status},
        site_id=site_id,
    )


def make_heartbeat() -> WebSocketEvent:
    return WebSocketEvent(type=HEARTBEAT, data={"status": "ok"})


# ---------------------------------------------------------------------------
# Redis → WebSocket bridge
# ---------------------------------------------------------------------------

async def handle_redis_subscription(
    redis_client,
    ws_manager: ConnectionManager,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """
    Subscribe to Redis pub/sub channels and forward messages to connected
    WebSocket clients.

    redis_client: redis.asyncio.Redis
    ws_manager:   ConnectionManager singleton
    stop_event:   optional asyncio.Event; set it to gracefully stop the loop
    """
    channels = list(REDIS_CHANNEL_MAP.keys())
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(*channels)
    logger.info("Redis pub/sub subscribed to: %s", channels)

    try:
        while True:
            if stop_event and stop_event.is_set():
                break

            try:
                message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=1.0)
            except asyncio.TimeoutError:
                # Send periodic heartbeat to all clients
                hb = make_heartbeat().to_json()
                if ws_manager.active_connections > 0:
                    await ws_manager.broadcast(hb)
                continue

            if message is None:
                continue

            channel = message.get("channel", b"").decode() if isinstance(message.get("channel"), bytes) else message.get("channel", "")
            raw_data = message.get("data", b"")
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode()

            try:
                payload = json.loads(raw_data)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Non-JSON message on channel %s: %s", channel, raw_data[:200])
                continue

            event_type_override = REDIS_CHANNEL_MAP.get(channel)

            if event_type_override == "__passthrough__":
                # Message is already a WebSocketEvent-shaped dict
                try:
                    event = WebSocketEvent(**payload)
                except Exception:
                    event = WebSocketEvent(type=payload.get("type", "UNKNOWN"), data=payload)
            else:
                event = WebSocketEvent(
                    type=event_type_override or "UNKNOWN",
                    data=payload,
                    site_id=payload.get("site_id"),
                )

            json_msg = event.to_json()
            site_id = event.site_id

            if site_id is not None:
                await ws_manager.broadcast_to_site(site_id, json_msg)
            else:
                await ws_manager.broadcast(json_msg)

    except asyncio.CancelledError:
        logger.info("Redis subscription task cancelled")
    except Exception as exc:
        logger.error("Redis subscription error: %s", exc)
        raise
    finally:
        await pubsub.unsubscribe(*channels)
        logger.info("Redis pub/sub unsubscribed")


# ---------------------------------------------------------------------------
# WebSocket endpoint helper
# ---------------------------------------------------------------------------

async def ws_lifecycle(
    websocket,
    client_id: str,
    ws_manager: ConnectionManager,
    site_id: Optional[int] = None,
) -> None:
    """
    Standard WebSocket lifecycle: connect → receive loop → disconnect.
    Import and call this from FastAPI WebSocket route handlers.
    """
    from fastapi import WebSocketDisconnect

    await ws_manager.connect(websocket, client_id, site_id=site_id)
    # Send welcome event
    welcome = WebSocketEvent(
        type="CONNECTED",
        data={"client_id": client_id, "site_id": site_id},
    ).to_json()
    await ws_manager.send_personal_message(client_id, welcome)

    try:
        while True:
            # Receive (keeps connection alive; clients may send pings)
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    pong = WebSocketEvent(type="pong", data={}).to_json()
                    await ws_manager.send_personal_message(client_id, pong)
            except Exception:
                pass  # ignore malformed client messages
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)
    except Exception as exc:
        logger.error("WS error client=%s: %s", client_id, exc)
        ws_manager.disconnect(client_id)
