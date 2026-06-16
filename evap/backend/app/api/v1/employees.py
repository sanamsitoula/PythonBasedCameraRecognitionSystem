from __future__ import annotations

import os
from datetime import date, datetime
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models import AttendanceRecord, Employee, MovementEvent

router = APIRouter(prefix="/employees", tags=["employees"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class EmployeeCreate(BaseModel):
    employee_id: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    department_id: Optional[str] = None
    designation: Optional[str] = None
    site_id: Optional[str] = None
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None
    erp_id: Optional[str] = None
    join_date: Optional[datetime] = None


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    department_id: Optional[str] = None
    designation: Optional[str] = None
    site_id: Optional[str] = None
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None
    is_active: Optional[bool] = None


class EmployeeOut(BaseModel):
    id: str
    employee_id: str
    full_name: str
    email: Optional[str]
    phone: Optional[str]
    department_id: Optional[str]
    designation: Optional[str]
    site_id: Optional[str]
    shift_start: Optional[str]
    shift_end: Optional[str]
    face_enrolled: bool
    is_active: bool
    join_date: Optional[datetime]

    class Config:
        from_attributes = True


class AttendanceOut(BaseModel):
    id: int
    date: datetime
    check_in: Optional[datetime]
    check_out: Optional[datetime]
    status: str
    duration_minutes: Optional[int]
    is_manual: bool

    class Config:
        from_attributes = True


class MovementOut(BaseModel):
    id: int
    camera_id: str
    zone_id: Optional[str]
    event_type: str
    confidence: Optional[float]
    snapshot_path: Optional[str]
    occurred_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    existing = (
        await db.execute(select(Employee).where(Employee.employee_id == body.employee_id))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Employee ID already exists")
    employee = Employee(**body.model_dump())
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    return employee


@router.get("/search", response_model=dict)
async def search_employees(
    q: str = Query(..., min_length=1),
    department_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    query = select(Employee).where(
        Employee.is_active == True,
        or_(
            Employee.full_name.ilike(f"%{q}%"),
            Employee.employee_id.ilike(f"%{q}%"),
            Employee.email.ilike(f"%{q}%"),
        ),
    )
    if department_id:
        query = query.where(Employee.department_id == department_id)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    items = (await db.execute(query.offset(skip).limit(limit))).scalars().all()
    return {"items": [EmployeeOut.model_validate(e) for e in items], "total": total}


@router.get("", response_model=dict)
async def list_employees(
    site_id: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    face_enrolled: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(Employee)
    if site_id:
        q = q.where(Employee.site_id == site_id)
    if department_id:
        q = q.where(Employee.department_id == department_id)
    if is_active is not None:
        q = q.where(Employee.is_active == is_active)
    if face_enrolled is not None:
        q = q.where(Employee.face_enrolled == face_enrolled)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [EmployeeOut.model_validate(e) for e in items], "total": total}


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    emp = (await db.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@router.put("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: str,
    body: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    emp = (await db.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(emp, field, value)
    await db.commit()
    await db.refresh(emp)
    return emp


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    emp = (await db.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp.is_active = False
    await db.commit()


# ---------------------------------------------------------------------------
# Face enrollment
# ---------------------------------------------------------------------------
@router.post("/{employee_id}/enroll-face", status_code=status.HTTP_200_OK)
async def enroll_face(
    employee_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    emp = (await db.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if file.content_type not in ("image/jpeg", "image/png", "image/jpg"):
        raise HTTPException(status_code=422, detail="Only JPEG/PNG images accepted")

    snap_dir = os.path.join(settings.SNAP_DIR, "faces")
    os.makedirs(snap_dir, exist_ok=True)
    filename = f"{employee_id}_{int(datetime.now().timestamp())}.jpg"
    filepath = os.path.join(snap_dir, filename)

    content = await file.read()
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    # Store image path; face encoding would be generated by AI worker
    emp.face_image_path = filepath
    emp.face_enrolled = True
    await db.commit()

    return {
        "employee_id": employee_id,
        "face_enrolled": True,
        "image_path": filepath,
        "message": "Face image uploaded. Encoding will be processed by AI worker.",
    }


# ---------------------------------------------------------------------------
# History endpoints
# ---------------------------------------------------------------------------
@router.get("/{employee_id}/attendance", response_model=dict)
async def employee_attendance(
    employee_id: str,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(AttendanceRecord).where(AttendanceRecord.employee_id == employee_id)
    if date_from:
        q = q.where(AttendanceRecord.date >= date_from)
    if date_to:
        q = q.where(AttendanceRecord.date <= date_to)
    q = q.order_by(AttendanceRecord.date.desc())

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [AttendanceOut.model_validate(a) for a in items], "total": total}


@router.get("/{employee_id}/movement", response_model=dict)
async def employee_movement(
    employee_id: str,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(MovementEvent).where(MovementEvent.employee_id == employee_id)
    if date_from:
        q = q.where(MovementEvent.occurred_at >= date_from)
    if date_to:
        q = q.where(MovementEvent.occurred_at <= date_to)
    q = q.order_by(MovementEvent.occurred_at.desc())

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [MovementOut.model_validate(m) for m in items], "total": total}


@router.get("/{employee_id}/zone-history", response_model=dict)
async def employee_zone_history(
    employee_id: str,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = (
        select(MovementEvent)
        .where(MovementEvent.employee_id == employee_id, MovementEvent.zone_id.isnot(None))
    )
    if date_from:
        q = q.where(MovementEvent.occurred_at >= date_from)
    if date_to:
        q = q.where(MovementEvent.occurred_at <= date_to)
    q = q.order_by(MovementEvent.occurred_at.desc())

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [MovementOut.model_validate(m) for m in items], "total": total}
