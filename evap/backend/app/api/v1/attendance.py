from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models import AttendanceRecord, Employee, User

router = APIRouter(prefix="/attendance", tags=["attendance"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AttendanceOut(BaseModel):
    id: int
    employee_id: str
    date: datetime
    check_in: Optional[datetime]
    check_out: Optional[datetime]
    status: str
    duration_minutes: Optional[int]
    is_manual: bool
    correction_reason: Optional[str]

    class Config:
        from_attributes = True


class ManualCorrectionRequest(BaseModel):
    employee_id: str
    date: datetime
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    status: str = "present"
    reason: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=dict)
async def list_attendance(
    employee_id: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(AttendanceRecord)
    if employee_id:
        q = q.where(AttendanceRecord.employee_id == employee_id)
    if status:
        q = q.where(AttendanceRecord.status == status)
    if date_from:
        q = q.where(AttendanceRecord.date >= date_from)
    if date_to:
        q = q.where(AttendanceRecord.date <= date_to)
    if department_id:
        q = q.join(Employee, Employee.id == AttendanceRecord.employee_id).where(
            Employee.department_id == department_id
        )
    q = q.order_by(AttendanceRecord.date.desc())

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [AttendanceOut.model_validate(a) for a in items], "total": total}


@router.get("/today", response_model=dict)
async def today_attendance(
    site_id: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    q = select(AttendanceRecord).where(AttendanceRecord.date >= today_start)

    if department_id or site_id:
        q = q.join(Employee, Employee.id == AttendanceRecord.employee_id)
        if department_id:
            q = q.where(Employee.department_id == department_id)
        if site_id:
            q = q.where(Employee.site_id == site_id)

    records = (await db.execute(q)).scalars().all()

    # Summary counts
    status_counts: dict = {}
    for r in records:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1

    total_active_employees = (
        await db.execute(
            select(func.count(Employee.id)).where(Employee.is_active == True)
        )
    ).scalar_one()

    return {
        "date": today_start.date().isoformat(),
        "total_active_employees": total_active_employees,
        "total_records": len(records),
        "present": status_counts.get("present", 0),
        "absent": total_active_employees - len(records),
        "late": status_counts.get("late", 0),
        "early_leave": status_counts.get("early_leave", 0),
        "half_day": status_counts.get("half_day", 0),
        "status_breakdown": status_counts,
    }


@router.get("/department/{dept_id}", response_model=dict)
async def department_attendance(
    dept_id: str,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = (
        select(AttendanceRecord)
        .join(Employee, Employee.id == AttendanceRecord.employee_id)
        .where(Employee.department_id == dept_id)
    )
    if date_from:
        q = q.where(AttendanceRecord.date >= date_from)
    if date_to:
        q = q.where(AttendanceRecord.date <= date_to)
    q = q.order_by(AttendanceRecord.date.desc())

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [AttendanceOut.model_validate(a) for a in items], "total": total}


@router.get("/monthly-report", response_model=dict)
async def monthly_report(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    department_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    from calendar import monthrange
    from datetime import timedelta

    _, last_day = monthrange(year, month)
    date_from = datetime(year, month, 1, tzinfo=timezone.utc)
    date_to = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    q = select(
        AttendanceRecord.status,
        func.count(AttendanceRecord.id).label("count"),
    ).where(
        AttendanceRecord.date >= date_from,
        AttendanceRecord.date <= date_to,
    )
    if department_id or site_id:
        q = q.join(Employee, Employee.id == AttendanceRecord.employee_id)
        if department_id:
            q = q.where(Employee.department_id == department_id)
        if site_id:
            q = q.where(Employee.site_id == site_id)
    q = q.group_by(AttendanceRecord.status)

    rows = (await db.execute(q)).all()
    summary = {row.status: row.count for row in rows}

    avg_duration = (
        await db.execute(
            select(func.avg(AttendanceRecord.duration_minutes)).where(
                AttendanceRecord.date >= date_from,
                AttendanceRecord.date <= date_to,
            )
        )
    ).scalar_one()

    return {
        "year": year,
        "month": month,
        "working_days": last_day,
        "summary": summary,
        "avg_duration_minutes": round(avg_duration or 0, 1),
    }


@router.post("/manual-correction", response_model=AttendanceOut, status_code=status.HTTP_201_CREATED)
async def manual_correction(
    body: ManualCorrectionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # Upsert: update existing record for that day or create new
    existing = (
        await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.employee_id == body.employee_id,
                func.date(AttendanceRecord.date) == body.date.date(),
            )
        )
    ).scalar_one_or_none()

    if existing:
        if body.check_in is not None:
            existing.check_in = body.check_in
        if body.check_out is not None:
            existing.check_out = body.check_out
        existing.status = body.status
        existing.is_manual = True
        existing.correction_reason = body.reason
        existing.corrected_by = current_user.id
        if existing.check_in and existing.check_out:
            delta = (existing.check_out - existing.check_in).total_seconds() / 60
            existing.duration_minutes = int(delta)
        await db.commit()
        await db.refresh(existing)
        return existing
    else:
        duration = None
        if body.check_in and body.check_out:
            duration = int((body.check_out - body.check_in).total_seconds() / 60)
        record = AttendanceRecord(
            employee_id=body.employee_id,
            date=body.date,
            check_in=body.check_in,
            check_out=body.check_out,
            status=body.status,
            duration_minutes=duration,
            is_manual=True,
            correction_reason=body.reason,
            corrected_by=current_user.id,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record


@router.get("/exceptions", response_model=dict)
async def attendance_exceptions(
    exception_type: Optional[str] = Query(None, description="late | absent | early_leave"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    exception_statuses = ["late", "absent", "early_leave"]
    if exception_type:
        exception_statuses = [exception_type]

    q = select(AttendanceRecord).where(AttendanceRecord.status.in_(exception_statuses))
    if date_from:
        q = q.where(AttendanceRecord.date >= date_from)
    if date_to:
        q = q.where(AttendanceRecord.date <= date_to)
    q = q.order_by(AttendanceRecord.date.desc())

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [AttendanceOut.model_validate(a) for a in items], "total": total}
