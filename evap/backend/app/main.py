from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Gauge, make_asgi_app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.rabbitmq import close_rabbitmq, init_rabbitmq
from app.core.redis_client import close_redis, init_redis

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
REQUEST_COUNT = Counter(
    "evap_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Gauge(
    "evap_http_request_latency_seconds",
    "HTTP request latency",
    ["method", "path"],
)
ACTIVE_CONNECTIONS = Gauge("evap_websocket_connections", "Active WebSocket connections")


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        import time

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        REQUEST_COUNT.labels(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            path=request.url.path,
        ).set(duration)
        return response


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active[client_id] = websocket
        ACTIVE_CONNECTIONS.set(len(self.active))

    def disconnect(self, client_id: str):
        self.active.pop(client_id, None)
        ACTIVE_CONNECTIONS.set(len(self.active))

    async def send_to(self, client_id: str, data: dict):
        ws = self.active.get(client_id)
        if ws:
            await ws.send_json(data)

    async def broadcast(self, data: dict):
        dead: list[str] = []
        for cid, ws in self.active.items():
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.disconnect(cid)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=(
            "EVAP – Enterprise Video Analytics Platform REST API. "
            "Provides endpoints for camera management, face recognition, "
            "attendance, visitor management, LPR, analytics, and alerting."
        ),
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus
    app.add_middleware(PrometheusMiddleware)
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # Routers
    app.include_router(api_router, prefix=settings.API_V1_STR)

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #
    @app.get("/health", tags=["system"])
    async def health_check():
        return {
            "status": "healthy",
            "version": settings.VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": settings.PROJECT_NAME,
        }

    # ------------------------------------------------------------------ #
    # WebSocket: per-client channel
    # ------------------------------------------------------------------ #
    @app.websocket("/ws/{client_id}")
    async def websocket_endpoint(websocket: WebSocket, client_id: str):
        await manager.connect(client_id, websocket)
        try:
            while True:
                data = await websocket.receive_text()
                # Echo back with timestamp (clients can send ping)
                await manager.send_to(
                    client_id,
                    {"type": "pong", "client_id": client_id, "echo": data},
                )
        except WebSocketDisconnect:
            manager.disconnect(client_id)

    # ------------------------------------------------------------------ #
    # Startup / Shutdown
    # ------------------------------------------------------------------ #
    @app.on_event("startup")
    async def startup_event():
        await init_db()
        await init_redis()
        try:
            await init_rabbitmq()
        except Exception as exc:
            # Non-fatal: service may start without RabbitMQ in dev
            import logging
            logging.getLogger("evap").warning("RabbitMQ unavailable: %s", exc)

    @app.on_event("shutdown")
    async def shutdown_event():
        await close_db()
        await close_redis()
        await close_rabbitmq()

    return app


app = create_app()
