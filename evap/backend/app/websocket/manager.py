"""WebSocket connection manager."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections, supporting:
    - Per-client personal messaging
    - Global broadcast
    - Site-scoped broadcast
    """

    def __init__(self):
        # client_id → WebSocket
        self._connections: Dict[str, WebSocket] = {}
        # site_id → set of client_ids
        self._site_subscriptions: Dict[int, Set[str]] = {}

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, websocket: WebSocket, client_id: str, site_id: Optional[int] = None) -> None:
        """Accept a new WebSocket connection and register it."""
        await websocket.accept()
        self._connections[client_id] = websocket
        if site_id is not None:
            self._site_subscriptions.setdefault(site_id, set()).add(client_id)
        logger.info("WS connected: client=%s site=%s total=%d", client_id, site_id, len(self._connections))

    def disconnect(self, client_id: str) -> None:
        """Remove a connection and clean up site subscriptions."""
        self._connections.pop(client_id, None)
        for subscribers in self._site_subscriptions.values():
            subscribers.discard(client_id)
        logger.info("WS disconnected: client=%s remaining=%d", client_id, len(self._connections))

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def send_personal_message(self, client_id: str, message: str) -> bool:
        """Send a text message to a specific client. Returns False if not connected."""
        ws = self._connections.get(client_id)
        if ws is None:
            return False
        try:
            await ws.send_text(message)
            return True
        except Exception as exc:
            logger.warning("WS send failed to client=%s: %s", client_id, exc)
            self.disconnect(client_id)
            return False

    async def broadcast(self, message: str) -> int:
        """
        Send a message to ALL connected clients.
        Returns the number of successful deliveries.
        """
        failed: List[str] = []
        sent = 0
        for client_id, ws in list(self._connections.items()):
            try:
                await ws.send_text(message)
                sent += 1
            except Exception as exc:
                logger.warning("Broadcast failed to client=%s: %s", client_id, exc)
                failed.append(client_id)

        for client_id in failed:
            self.disconnect(client_id)

        return sent

    async def broadcast_to_site(self, site_id: int, message: str) -> int:
        """
        Send a message only to clients subscribed to a specific site.
        Returns the number of successful deliveries.
        """
        subscribers = self._site_subscriptions.get(site_id, set()).copy()
        failed: List[str] = []
        sent = 0

        for client_id in subscribers:
            ws = self._connections.get(client_id)
            if ws is None:
                failed.append(client_id)
                continue
            try:
                await ws.send_text(message)
                sent += 1
            except Exception as exc:
                logger.warning("Site broadcast failed to client=%s: %s", client_id, exc)
                failed.append(client_id)

        for client_id in failed:
            self.disconnect(client_id)

        return sent

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def active_connections(self) -> int:
        return len(self._connections)

    def clients_for_site(self, site_id: int) -> int:
        return len(self._site_subscriptions.get(site_id, set()))

    def is_connected(self, client_id: str) -> bool:
        return client_id in self._connections


# Singleton instance used across the application
manager = ConnectionManager()
