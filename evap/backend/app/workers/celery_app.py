"""Celery application factory with RabbitMQ broker and Redis backend."""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def _get_broker_url() -> str:
    try:
        from ..core.config import settings  # type: ignore[import]
        return settings.RABBITMQ_URL
    except Exception:
        return os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672//")


def _get_backend_url() -> str:
    try:
        from ..core.config import settings  # type: ignore[import]
        return settings.REDIS_URL
    except Exception:
        return os.getenv("REDIS_URL", "redis://localhost:6379/0")


# ---------------------------------------------------------------------------
# Celery app
# ---------------------------------------------------------------------------

celery_app = Celery(
    "evap",
    broker=_get_broker_url(),
    backend=_get_backend_url(),
    include=[
        "app.workers.ai_tasks",
        "app.workers.report_tasks",
        "app.workers.notification_tasks",
    ],
)

# ---------------------------------------------------------------------------
# Queue definitions
# ---------------------------------------------------------------------------

default_exchange = Exchange("default", type="direct")
reports_exchange = Exchange("reports", type="direct")
notifications_exchange = Exchange("notifications", type="direct")
ai_exchange = Exchange("ai", type="direct")

celery_app.conf.task_queues = (
    Queue("default", default_exchange, routing_key="default"),
    Queue("ai", ai_exchange, routing_key="ai"),
    Queue("reports", reports_exchange, routing_key="reports"),
    Queue("notifications", notifications_exchange, routing_key="notifications"),
)

celery_app.conf.task_default_queue = "default"
celery_app.conf.task_default_exchange = "default"
celery_app.conf.task_default_routing_key = "default"

celery_app.conf.task_routes = {
    # AI tasks → ai queue
    "app.workers.ai_tasks.*": {"queue": "ai", "routing_key": "ai"},
    # Report tasks → reports queue
    "app.workers.report_tasks.*": {"queue": "reports", "routing_key": "reports"},
    # Notification tasks → notifications queue
    "app.workers.notification_tasks.*": {"queue": "notifications", "routing_key": "notifications"},
}

# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"
celery_app.conf.enable_utc = True

# ---------------------------------------------------------------------------
# Task behaviour
# ---------------------------------------------------------------------------

celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.task_track_started = True
celery_app.conf.worker_prefetch_multiplier = 1   # fair dispatch for long tasks
celery_app.conf.task_time_limit = 3600           # 1 hour hard limit
celery_app.conf.task_soft_time_limit = 3300      # 55 min soft limit

# ---------------------------------------------------------------------------
# Beat schedule
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    # Nightly analytics at 00:05 UTC
    "daily-analytics-midnight": {
        "task": "app.workers.report_tasks.generate_daily_analytics",
        "schedule": crontab(hour=0, minute=5),
        "args": [],
        "options": {"queue": "reports"},
    },
    # ERP employee sync every hour
    "erp-employee-sync-hourly": {
        "task": "app.workers.report_tasks.erp_sync_task",
        "schedule": crontab(minute=0),
        "args": [],
        "options": {"queue": "default"},
    },
    # Camera health check every minute
    "camera-health-check-minute": {
        "task": "app.workers.ai_tasks.camera_health_check",
        "schedule": crontab(),   # every minute
        "args": [],
        "options": {"queue": "ai"},
    },
    # Cleanup expired reports daily at 03:00
    "cleanup-old-reports-daily": {
        "task": "app.workers.report_tasks.cleanup_old_reports",
        "schedule": crontab(hour=3, minute=0),
        "args": [30],
        "options": {"queue": "reports"},
    },
}

# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    pass   # beat_schedule handles this declaratively
