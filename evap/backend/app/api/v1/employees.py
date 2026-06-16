from __future__ import annotations

import asyncio
import re
import sys
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any, List, Optional

import aiofiles
from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, HTTPException,
    Query, UploadFile, status,
)
from pydantic import BaseModel, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.dependencies import get_current_active_user
from app.models import EmployeeMaster

router = APIRouter(prefix="/employees", tags=["employees"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/jpg"}
_CLI = Path(__file__).parents[5] / "enrollment_cli.py"
_ROOT = Path(__file__).parents[5]


def _photo_dir(employee_id: str) -> Path:
    p = Path(settings.SNAP_DIR) / "employees" / employee_id
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class EmployeeCreate(BaseModel):
    employee_id: str
    full_name: str
    department: Optional[str] = None
    designation: Optional[str] = None
    employee_code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    work_start_time: Optional[str] = None
    work_end_time: Optional[str] = None


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    employee_code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    work_start_time: Optional[str] = None
    work_end_time: Optional[str] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None


class EmployeeOut(BaseModel):
    employee_id: str
    full_name: str
    department: Optional[str] = None
    designation: Optional[str] = None
    employee_code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    status: str
    is_active: bool
    enrollment_status: str
    enrollment_error: Optional[str] = None
    photo_count: int = 0
    photo_paths: List[str] = []
    work_start_time: Optional[str] = None
    work_end_time: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @field_validator("work_start_time", "work_end_time", mode="before")
    @classmethod
    def _coerce_time(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, dt_time):
            return v.strftime("%H:%M")
        return str(v)

    @field_validator("photo_paths", mode="before")
    @classmethod
    def _coerce_paths(cls, v: Any) -> List[str]:
        if v is None:
            return []
        return list(v)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_or_404(db: AsyncSession, employee_id: str) -> EmployeeMaster:
    emp = (
        await db.execute(
            select(EmployeeMaster).where(EmployeeMaster.employee_id == employee_id)
        )
    ).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


async def _enrollment_task(employee_id: str, name: str, dept: str, designation: str, image_paths: List[str]) -> None:
    """Background: invoke enrollment_cli.py and write result back to DB."""
    cmd = [
        sys.executable, str(_CLI),
        "add",
        "--id", employee_id,
        "--name", name,
        "--dept", dept or "General",
    ]
    if designation:
        cmd += ["--designation", designation]
    if image_paths:
        cmd += ["--images"] + image_paths

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=300)
        out = stdout_b.decode(errors="replace")
        err = stderr_b.decode(errors="replace")
        success = proc.returncode == 0
        error_text: Optional[str] = None
        if not success:
            error_text = (err or out)[:500]
    except asyncio.TimeoutError:
        success = False
        error_text = "Enrollment timed out after 5 minutes"
    except Exception as exc:
        success = False
        error_text = str(exc)[:500]

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EmployeeMaster).where(EmployeeMaster.employee_id == employee_id)
        )
        emp = result.scalar_one_or_none()
        if emp:
            emp.enrollment_status = "enrolled" if success else "failed"
            emp.enrollment_error = error_text
            emp.updated_at = datetime.utcnow()
            await db.commit()


# ---------------------------------------------------------------------------
# 1. Create employee
# ---------------------------------------------------------------------------
@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    existing = (
        await db.execute(
            select(EmployeeMaster).where(EmployeeMaster.employee_id == body.employee_id)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Employee ID already exists")

    emp = EmployeeMaster(
        employee_id=body.employee_id,
        full_name=body.full_name,
        department=body.department,
        designation=body.designation,
        employee_code=body.employee_code,
        email=body.email,
        phone=body.phone,
        notes=body.notes,
        photo_paths=[],
    )
    db.add(emp)
    await db.commit()
    await db.refresh(emp)
    return EmployeeOut.model_validate(emp)


# ---------------------------------------------------------------------------
# 2. Upload photos
# ---------------------------------------------------------------------------
@router.post("/{employee_id}/photos", status_code=status.HTTP_200_OK)
async def upload_photos(
    employee_id: str,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    emp = await _get_or_404(db, employee_id)

    if not files:
        raise HTTPException(status_code=422, detail="No files provided")

    saved: List[str] = []
    photo_dir = _photo_dir(employee_id)

    for f in files:
        if f.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=422, detail=f"File {f.filename!r} is not JPEG or PNG")
        ext = Path(f.filename or "photo.jpg").suffix or ".jpg"
        filename = f"{employee_id}_{int(datetime.utcnow().timestamp() * 1000)}{ext}"
        filepath = photo_dir / filename
        content = await f.read()
        async with aiofiles.open(filepath, "wb") as out:
            await out.write(content)
        saved.append(str(filepath))

    current_paths: List[str] = list(emp.photo_paths or [])
    current_paths.extend(saved)
    emp.photo_paths = current_paths
    emp.photo_count = len(current_paths)
    emp.updated_at = datetime.utcnow()
    await db.commit()

    return {
        "employee_id": employee_id,
        "uploaded": len(saved),
        "photo_count": emp.photo_count,
        "photo_paths": current_paths,
    }


# ---------------------------------------------------------------------------
# 3. Trigger enrollment
# ---------------------------------------------------------------------------
@router.post("/{employee_id}/enroll", status_code=status.HTTP_202_ACCEPTED)
async def trigger_enrollment(
    employee_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    emp = await _get_or_404(db, employee_id)

    if emp.photo_count == 0:
        raise HTTPException(status_code=400, detail="Upload at least one photo before enrolling")
    if emp.enrollment_status == "pending":
        raise HTTPException(status_code=400, detail="Enrollment already in progress")

    emp.enrollment_status = "pending"
    emp.enrollment_error = None
    emp.updated_at = datetime.utcnow()
    await db.commit()

    background_tasks.add_task(
        _enrollment_task,
        employee_id,
        emp.full_name,
        emp.department or "General",
        emp.designation or "",
        list(emp.photo_paths or []),
    )

    return {
        "employee_id": employee_id,
        "enrollment_status": "pending",
        "message": "Enrollment started in background",
    }


# ---------------------------------------------------------------------------
# 4. List employees
# ---------------------------------------------------------------------------
@router.get("", response_model=dict)
async def list_employees(
    q: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    enrollment_status: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    query = select(EmployeeMaster)
    if q:
        query = query.where(
            or_(
                EmployeeMaster.full_name.ilike(f"%{q}%"),
                EmployeeMaster.employee_id.ilike(f"%{q}%"),
                EmployeeMaster.email.ilike(f"%{q}%"),
            )
        )
    if department:
        query = query.where(EmployeeMaster.department == department)
    if status_filter:
        query = query.where(EmployeeMaster.status == status_filter)
    if enrollment_status:
        query = query.where(EmployeeMaster.enrollment_status == enrollment_status)
    if is_active is not None:
        query = query.where(EmployeeMaster.is_active == is_active)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    items = (await db.execute(query.order_by(EmployeeMaster.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    return {
        "items": [EmployeeOut.model_validate(e) for e in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# 5. Get single employee
# ---------------------------------------------------------------------------
@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    emp = await _get_or_404(db, employee_id)
    return EmployeeOut.model_validate(emp)


# ---------------------------------------------------------------------------
# 6. Poll enrollment status
# ---------------------------------------------------------------------------
@router.get("/{employee_id}/enrollment-status")
async def get_enrollment_status(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    emp = await _get_or_404(db, employee_id)
    return {
        "employee_id": employee_id,
        "enrollment_status": emp.enrollment_status,
        "enrollment_error": emp.enrollment_error,
        "photo_count": emp.photo_count,
    }


# ---------------------------------------------------------------------------
# 7. Update employee
# ---------------------------------------------------------------------------
@router.put("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: str,
    body: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    emp = await _get_or_404(db, employee_id)
    data = body.model_dump(exclude_none=True)
    for field, value in data.items():
        setattr(emp, field, value)
    emp.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(emp)
    return EmployeeOut.model_validate(emp)


# ---------------------------------------------------------------------------
# 8. Delete single photo
# ---------------------------------------------------------------------------
@router.delete("/{employee_id}/photos/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    employee_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    emp = await _get_or_404(db, employee_id)
    current_paths: List[str] = list(emp.photo_paths or [])
    # Match by basename
    updated = [p for p in current_paths if Path(p).name != filename]
    if len(updated) == len(current_paths):
        raise HTTPException(status_code=404, detail="Photo not found")

    # Remove file from disk
    photo_file = _photo_dir(employee_id) / filename
    if photo_file.exists():
        photo_file.unlink(missing_ok=True)

    emp.photo_paths = updated
    emp.photo_count = len(updated)
    emp.updated_at = datetime.utcnow()
    await db.commit()


# ---------------------------------------------------------------------------
# 9. Soft-delete employee
# ---------------------------------------------------------------------------
@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    emp = await _get_or_404(db, employee_id)
    emp.status = "deleted"
    emp.is_active = False
    emp.updated_at = datetime.utcnow()
    await db.commit()
