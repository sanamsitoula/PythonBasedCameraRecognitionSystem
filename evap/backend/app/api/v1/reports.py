from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db, AsyncSessionLocal
from app.core.dependencies import get_current_active_user
from app.models import AttendanceRecord, Employee, Report, User

router = APIRouter(prefix="/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ReportRequest(BaseModel):
    name: str
    report_type: str  # attendance | occupancy | visitor | vehicle | alert
    format: str = "pdf"  # pdf | xlsx | csv
    parameters: Optional[dict] = None


class ReportOut(BaseModel):
    id: str
    name: str
    report_type: str
    format: str
    status: str
    file_size_bytes: Optional[int]
    generated_by: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------
async def _generate_report(report_id: str) -> None:
    """Run report generation in background. Uses own DB session."""
    async with AsyncSessionLocal() as db:
        report = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
        if not report:
            return
        try:
            report.status = "processing"
            await db.commit()

            params = report.parameters or {}
            date_from_str = params.get("date_from")
            date_to_str = params.get("date_to")
            date_from = datetime.fromisoformat(date_from_str) if date_from_str else None
            date_to = datetime.fromisoformat(date_to_str) if date_to_str else None

            os.makedirs(settings.REPORTS_DIR, exist_ok=True)
            filepath = os.path.join(settings.REPORTS_DIR, f"{report_id}.{report.format}")

            if report.format == "xlsx":
                await _gen_xlsx(report, filepath, db, date_from, date_to)
            elif report.format == "csv":
                await _gen_csv(report, filepath, db, date_from, date_to)
            else:
                await _gen_pdf(report, filepath, db, date_from, date_to)

            report.status = "done"
            report.file_path = filepath
            report.file_size_bytes = os.path.getsize(filepath)
            report.completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            report.status = "failed"
            report.error_message = str(exc)
        finally:
            await db.commit()


async def _gen_pdf(report, filepath, db, date_from, date_to):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(filepath, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 800, f"EVAP Report: {report.name}")
    c.setFont("Helvetica", 12)
    c.drawString(50, 775, f"Type: {report.report_type}")
    c.drawString(50, 755, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    if date_from:
        c.drawString(50, 735, f"Period: {date_from.date()} to {(date_to or datetime.now()).date()}")

    # Sample data rows
    q = select(AttendanceRecord)
    if date_from:
        q = q.where(AttendanceRecord.date >= date_from)
    if date_to:
        q = q.where(AttendanceRecord.date <= date_to)
    q = q.limit(50)
    rows = (await db.execute(q)).scalars().all()

    y = 700
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Employee ID | Date | Status | Duration (min)")
    y -= 15
    c.setFont("Helvetica", 9)
    for r in rows:
        if y < 50:
            c.showPage()
            y = 800
        c.drawString(50, y, f"{r.employee_id} | {r.date.date()} | {r.status} | {r.duration_minutes or '-'}")
        y -= 14

    c.save()


async def _gen_xlsx(report, filepath, db, date_from, date_to):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = report.report_type.title()
    ws.append(["Employee ID", "Date", "Check In", "Check Out", "Status", "Duration (min)", "Manual"])

    q = select(AttendanceRecord)
    if date_from:
        q = q.where(AttendanceRecord.date >= date_from)
    if date_to:
        q = q.where(AttendanceRecord.date <= date_to)
    rows = (await db.execute(q)).scalars().all()
    for r in rows:
        ws.append([
            r.employee_id,
            r.date.date().isoformat() if r.date else "",
            r.check_in.isoformat() if r.check_in else "",
            r.check_out.isoformat() if r.check_out else "",
            r.status,
            r.duration_minutes,
            r.is_manual,
        ])
    wb.save(filepath)


async def _gen_csv(report, filepath, db, date_from, date_to):
    import csv as csvlib

    q = select(AttendanceRecord)
    if date_from:
        q = q.where(AttendanceRecord.date >= date_from)
    if date_to:
        q = q.where(AttendanceRecord.date <= date_to)
    rows = (await db.execute(q)).scalars().all()

    with open(filepath, "w", newline="") as f:
        writer = csvlib.writer(f)
        writer.writerow(["employee_id", "date", "check_in", "check_out", "status", "duration_minutes"])
        for r in rows:
            writer.writerow([r.employee_id, r.date, r.check_in, r.check_out, r.status, r.duration_minutes])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("", response_model=ReportOut, status_code=status.HTTP_202_ACCEPTED)
async def generate_report(
    body: ReportRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    report = Report(
        name=body.name,
        report_type=body.report_type,
        format=body.format,
        parameters=body.parameters,
        status="pending",
        generated_by=current_user.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    background_tasks.add_task(_generate_report, report.id)
    return report


@router.get("", response_model=dict)
async def list_reports(
    report_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(Report).order_by(Report.created_at.desc())
    if report_type:
        q = q.where(Report.report_type == report_type)
    if status:
        q = q.where(Report.status == status)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [ReportOut.model_validate(r) for r in items], "total": total}


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    report = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != "done":
        raise HTTPException(status_code=400, detail=f"Report is not ready (status: {report.status})")
    if not report.file_path or not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail="Report file not found on disk")

    media_type_map = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "text/csv"}
    return FileResponse(
        path=report.file_path,
        media_type=media_type_map.get(report.format, "application/octet-stream"),
        filename=f"{report.name}.{report.format}",
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    report = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    # Delete file if exists
    if report.file_path and os.path.exists(report.file_path):
        os.remove(report.file_path)
    await db.delete(report)
    await db.commit()
