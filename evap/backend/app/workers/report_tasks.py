"""Celery tasks for report generation, daily analytics, and cleanup."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _get_async_db():
    """Async SQLAlchemy session factory for use inside _run_async."""
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
# Report generation
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.workers.report_tasks.generate_report_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="reports",
)
def generate_report_task(self, report_id: int, params: Dict[str, Any]) -> None:
    """
    Async report generation worker.
    Reads report_id from reports table, runs the appropriate generator,
    and updates the record with the file path and 'ready' status.
    """
    from sqlalchemy import text

    async def _generate():
        from ..services.report_service import (  # type: ignore[import]
            generate_attendance_pdf,
            generate_attendance_excel,
            generate_vehicle_report,
            generate_visitor_report,
            generate_executive_summary,
        )
        from ..schemas.report import ReportRequest  # type: ignore[import]

        Session = _get_async_db()
        async with Session() as db:
            # Mark as processing
            await db.execute(
                text("UPDATE reports SET status = 'processing' WHERE report_id = :rid"),
                {"rid": report_id},
            )
            await db.commit()

            try:
                report_type = params.get("report_type", "attendance_daily")
                fmt = params.get("format", "pdf")
                req = ReportRequest(
                    report_type=report_type,
                    format=fmt,
                    date_from=date.fromisoformat(params["date_from"]),
                    date_to=date.fromisoformat(params["date_to"]),
                    site_id=params.get("site_id"),
                    filters=params.get("filters", {}),
                )

                generators = {
                    ("attendance_daily", "pdf"): generate_attendance_pdf,
                    ("attendance_daily", "excel"): generate_attendance_excel,
                    ("attendance_monthly", "pdf"): generate_attendance_pdf,
                    ("attendance_monthly", "excel"): generate_attendance_excel,
                    ("vehicle_log", "pdf"): generate_vehicle_report,
                    ("visitor_summary", "excel"): generate_visitor_report,
                    ("executive_summary", "pdf"): generate_executive_summary,
                }
                generator = generators.get((report_type, fmt), generate_attendance_pdf)
                filepath = await generator(db, req)

                await db.execute(
                    text("""
                        UPDATE reports
                        SET file_path = :fp, generated_at = NOW(), status = 'ready'
                        WHERE report_id = :rid
                    """),
                    {"fp": filepath, "rid": report_id},
                )
                await db.commit()
                logger.info("Report %s ready: %s", report_id, filepath)

            except Exception as exc:
                await db.execute(
                    text("UPDATE reports SET status = 'failed' WHERE report_id = :rid"),
                    {"rid": report_id},
                )
                await db.commit()
                raise exc

    try:
        _run_async(_generate())
    except Exception as exc:
        logger.error("generate_report_task failed for report_id=%s: %s", report_id, exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Daily analytics aggregation
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.workers.report_tasks.generate_daily_analytics",
    queue="reports",
)
def generate_daily_analytics(date_str: Optional[str] = None) -> None:
    """
    Compute end-of-day analytics for all active sites.
    If date_str is None, computes for yesterday.
    """
    async def _compute():
        from ..services.analytics_service import calculate_daily_analytics  # type: ignore[import]
        from ..models.site import SiteMaster  # type: ignore[import]
        from sqlalchemy import select

        target = (
            date.fromisoformat(date_str)
            if date_str
            else (datetime.now(timezone.utc) - timedelta(days=1)).date()
        )

        Session = _get_async_db()
        async with Session() as db:
            stmt = select(SiteMaster.site_id).where(SiteMaster.is_active == True)
            result = await db.execute(stmt)
            site_ids = [r[0] for r in result.all()]

            for site_id in site_ids:
                try:
                    await calculate_daily_analytics(db, target, site_id)
                except Exception as exc:
                    logger.error("Daily analytics failed for site=%s date=%s: %s", site_id, target, exc)

            # Also compute global (site_id=None)
            await calculate_daily_analytics(db, target, None)

    try:
        _run_async(_compute())
        logger.info("Daily analytics complete for %s", date_str or "yesterday")
    except Exception as exc:
        logger.error("generate_daily_analytics failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# ERP sync beat task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.workers.report_tasks.erp_sync_task",
    queue="default",
)
def erp_sync_task() -> None:
    """Hourly ERP employee sync for all configured ERP types."""
    async def _sync():
        from ..services.erp_service import sync_employees_from_erp  # type: ignore[import]
        import os

        erp_types_env = os.getenv("ENABLED_ERP_TYPES", "")
        erp_types = [t.strip() for t in erp_types_env.split(",") if t.strip()]
        if not erp_types:
            return

        Session = _get_async_db()
        async with Session() as db:
            for erp_type in erp_types:
                try:
                    stats = await sync_employees_from_erp(db, erp_type)
                    logger.info("ERP sync %s: %s", erp_type, stats)
                except Exception as exc:
                    logger.error("ERP sync failed for %s: %s", erp_type, exc)

    try:
        _run_async(_sync())
    except Exception as exc:
        logger.error("erp_sync_task failed: %s", exc)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.workers.report_tasks.cleanup_old_reports",
    queue="reports",
)
def cleanup_old_reports(days: int = 30) -> int:
    """
    Delete report files and DB records older than `days` days.
    Returns count of deleted records.
    """
    async def _cleanup() -> int:
        from sqlalchemy import text

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        Session = _get_async_db()
        async with Session() as db:
            # Fetch file paths before deleting
            rows = await db.execute(
                text("SELECT report_id, file_path FROM reports WHERE generated_at < :cutoff"),
                {"cutoff": cutoff},
            )
            to_delete = rows.all()

            deleted_count = 0
            for report_id, filepath in to_delete:
                if filepath:
                    try:
                        Path(filepath).unlink(missing_ok=True)
                    except Exception as exc:
                        logger.warning("Could not delete file %s: %s", filepath, exc)
                try:
                    await db.execute(
                        text("DELETE FROM reports WHERE report_id = :rid"),
                        {"rid": report_id},
                    )
                    deleted_count += 1
                except Exception as exc:
                    logger.error("Could not delete report record %s: %s", report_id, exc)

            await db.commit()
            return deleted_count

    try:
        count = _run_async(_cleanup())
        logger.info("cleanup_old_reports: deleted %d records (older than %d days)", count, days)
        return count
    except Exception as exc:
        logger.error("cleanup_old_reports failed: %s", exc)
        return 0
