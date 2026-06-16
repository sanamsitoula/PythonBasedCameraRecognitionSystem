from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.core.security import decrypt_rtsp_url, encrypt_rtsp_url
from app.models import AttendanceRecord, Employee, ErpConfig, ErpSyncLog

router = APIRouter(prefix="/erp", tags=["erp"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ErpConfigOut(BaseModel):
    id: int
    erp_type: str
    base_url: str
    sync_interval_minutes: int
    last_employee_sync: Optional[datetime]
    last_attendance_push: Optional[datetime]
    is_active: bool

    class Config:
        from_attributes = True


class ErpSyncLogOut(BaseModel):
    id: int
    sync_type: str
    status: str
    records_processed: int
    records_failed: int
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class AttendancePushRequest(BaseModel):
    date_from: datetime
    date_to: datetime
    employee_ids: Optional[list] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_erp_config(db: AsyncSession) -> ErpConfig:
    config = (await db.execute(select(ErpConfig).where(ErpConfig.is_active == True))).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=503, detail="No active ERP configuration found")
    return config


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/config", response_model=ErpConfigOut)
async def get_erp_config(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    config = (await db.execute(select(ErpConfig))).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="ERP not configured")
    return config


@router.get("/employees/sync", response_model=dict)
async def sync_employees_from_erp(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    config = await _get_erp_config(db)
    log = ErpSyncLog(sync_type="pull_employees", status="running", started_at=datetime.now(timezone.utc))
    db.add(log)
    await db.commit()
    await db.refresh(log)

    processed = 0
    failed = 0
    error_msg = None

    try:
        async with httpx.AsyncClient(timeout=settings.ERP_SYNC_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{config.base_url}/employees",
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            erp_employees: list = resp.json().get("data", resp.json() if isinstance(resp.json(), list) else [])

        for emp_data in erp_employees:
            try:
                erp_id = str(emp_data.get("id", ""))
                existing = (
                    await db.execute(select(Employee).where(Employee.erp_id == erp_id))
                ).scalar_one_or_none()
                if existing:
                    existing.full_name = emp_data.get("name", existing.full_name)
                    existing.email = emp_data.get("email", existing.email)
                    existing.phone = emp_data.get("phone", existing.phone)
                else:
                    emp_id_str = emp_data.get("employee_id") or erp_id
                    new_emp = Employee(
                        employee_id=emp_id_str,
                        full_name=emp_data.get("name", "Unknown"),
                        email=emp_data.get("email"),
                        phone=emp_data.get("phone"),
                        erp_id=erp_id,
                    )
                    db.add(new_emp)
                processed += 1
            except Exception:
                failed += 1

        await db.commit()
        config.last_employee_sync = datetime.now(timezone.utc)
        log.status = "success"
    except httpx.HTTPError as exc:
        error_msg = str(exc)
        log.status = "failed"
    except Exception as exc:
        error_msg = str(exc)
        log.status = "partial" if processed > 0 else "failed"

    log.records_processed = processed
    log.records_failed = failed
    log.error_message = error_msg
    log.completed_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "status": log.status,
        "records_processed": processed,
        "records_failed": failed,
        "error": error_msg,
    }


@router.post("/attendance/push", response_model=dict)
async def push_attendance_to_erp(
    body: AttendancePushRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    config = await _get_erp_config(db)
    log = ErpSyncLog(sync_type="push_attendance", status="running", started_at=datetime.now(timezone.utc))
    db.add(log)
    await db.commit()
    await db.refresh(log)

    q = select(AttendanceRecord).where(
        AttendanceRecord.date >= body.date_from,
        AttendanceRecord.date <= body.date_to,
        AttendanceRecord.erp_synced == False,
    )
    if body.employee_ids:
        q = q.where(AttendanceRecord.employee_id.in_(body.employee_ids))
    records = (await db.execute(q)).scalars().all()

    processed = 0
    failed = 0
    error_msg = None

    try:
        payload = [
            {
                "employee_id": r.employee_id,
                "date": r.date.date().isoformat(),
                "check_in": r.check_in.isoformat() if r.check_in else None,
                "check_out": r.check_out.isoformat() if r.check_out else None,
                "status": r.status,
                "duration_minutes": r.duration_minutes,
            }
            for r in records
        ]

        async with httpx.AsyncClient(timeout=settings.ERP_SYNC_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{config.base_url}/attendance",
                json={"records": payload},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()

        for r in records:
            r.erp_synced = True
        await db.commit()
        processed = len(records)

        config.last_attendance_push = datetime.now(timezone.utc)
        log.status = "success"
    except httpx.HTTPError as exc:
        error_msg = str(exc)
        log.status = "failed"
    except Exception as exc:
        error_msg = str(exc)
        log.status = "failed"

    log.records_processed = processed
    log.records_failed = failed
    log.error_message = error_msg
    log.completed_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "status": log.status,
        "records_pushed": processed,
        "error": error_msg,
    }


@router.get("/sync-status", response_model=dict)
async def sync_status(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    config = (await db.execute(select(ErpConfig))).scalar_one_or_none()

    # Last 5 sync logs
    logs = (
        await db.execute(
            select(ErpSyncLog).order_by(ErpSyncLog.started_at.desc()).limit(5)
        )
    ).scalars().all()

    return {
        "last_employee_sync": config.last_employee_sync if config else None,
        "last_attendance_push": config.last_attendance_push if config else None,
        "recent_logs": [ErpSyncLogOut.model_validate(l) for l in logs],
    }


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def erp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive and process ERP webhook payloads."""
    payload: dict = await request.json()
    event_type = payload.get("event")

    if event_type == "employee.updated":
        emp_data = payload.get("data", {})
        erp_id = str(emp_data.get("id", ""))
        existing = (
            await db.execute(select(Employee).where(Employee.erp_id == erp_id))
        ).scalar_one_or_none()
        if existing:
            existing.full_name = emp_data.get("name", existing.full_name)
            existing.email = emp_data.get("email", existing.email)
            await db.commit()
            return {"acknowledged": True, "action": "employee_updated"}

    elif event_type == "employee.terminated":
        emp_data = payload.get("data", {})
        erp_id = str(emp_data.get("id", ""))
        existing = (
            await db.execute(select(Employee).where(Employee.erp_id == erp_id))
        ).scalar_one_or_none()
        if existing:
            existing.is_active = False
            await db.commit()
            return {"acknowledged": True, "action": "employee_deactivated"}

    return {"acknowledged": True, "action": "ignored", "event": event_type}
