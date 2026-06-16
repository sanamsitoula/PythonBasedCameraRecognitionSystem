"""Attendance query and correction service."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.attendance import (
    AttendanceCorrectionRequest,
    AttendanceException,
    AttendanceRecord,
    AttendanceSummary,
    MonthlyAttendance,
)

logger = logging.getLogger(__name__)


async def get_today_attendance(
    db: AsyncSession, site_id: Optional[int] = None
) -> AttendanceSummary:
    """Return today's attendance summary with per-department breakdown."""
    from ..models.attendance import AttendanceLog  # type: ignore[import]
    from ..models.employee import EmployeeMaster  # type: ignore[import]

    today = date.today()
    stmt = (
        select(
            EmployeeMaster.department,
            AttendanceLog.status,
            func.count().label("cnt"),
        )
        .join(EmployeeMaster, AttendanceLog.employee_id == EmployeeMaster.id)
        .where(AttendanceLog.date == today)
    )
    if site_id:
        stmt = stmt.where(EmployeeMaster.site_id == site_id)
    stmt = stmt.group_by(EmployeeMaster.department, AttendanceLog.status)

    result = await db.execute(stmt)
    rows = result.all()

    by_dept: Dict[str, Dict[str, int]] = {}
    totals: Dict[str, int] = {"present": 0, "absent": 0, "late": 0, "half_day": 0, "on_leave": 0}

    for dept, status, cnt in rows:
        dept = dept or "Unknown"
        if dept not in by_dept:
            by_dept[dept] = {"present": 0, "absent": 0, "late": 0}
        if status == "present":
            by_dept[dept]["present"] += cnt
            totals["present"] += cnt
        elif status == "absent":
            by_dept[dept]["absent"] += cnt
            totals["absent"] += cnt
        elif status == "half_day":
            totals["half_day"] += cnt
        # late_arrival exceptions are tracked separately

    # Count late arrivals
    late_stmt = (
        select(func.count())
        .select_from(AttendanceLog)
        .where(and_(AttendanceLog.date == today, AttendanceLog.is_late == True))
    )
    if site_id:
        late_stmt = late_stmt.join(EmployeeMaster, AttendanceLog.employee_id == EmployeeMaster.id).where(
            EmployeeMaster.site_id == site_id
        )
    late_result = await db.execute(late_stmt)
    late_count = late_result.scalar_one_or_none() or 0

    total_employees = sum(totals.values())
    pct = (totals["present"] / total_employees * 100) if total_employees else 0.0

    return AttendanceSummary(
        date=today,
        site_id=site_id,
        total_present=totals["present"],
        total_absent=totals["absent"],
        total_late=late_count,
        total_half_day=totals["half_day"],
        total_on_leave=totals["on_leave"],
        attendance_pct=round(pct, 2),
        by_department=by_dept,
    )


async def get_attendance_range(
    db: AsyncSession,
    employee_id: str,
    date_from: date,
    date_to: date,
) -> List[AttendanceRecord]:
    from ..models.attendance import AttendanceLog
    from ..models.employee import EmployeeMaster

    stmt = (
        select(AttendanceLog, EmployeeMaster.name)
        .join(EmployeeMaster, AttendanceLog.employee_id == EmployeeMaster.id)
        .where(
            and_(
                EmployeeMaster.employee_id == employee_id,
                AttendanceLog.date >= date_from,
                AttendanceLog.date <= date_to,
            )
        )
        .order_by(AttendanceLog.date)
    )
    result = await db.execute(stmt)
    rows = result.all()

    records = []
    for log, emp_name in rows:
        working_hours = None
        if log.first_entry and log.last_exit:
            delta = log.last_exit - log.first_entry
            working_hours = round(delta.total_seconds() / 3600, 2)

        records.append(
            AttendanceRecord(
                employee_id=employee_id,
                employee_name=emp_name,
                date=log.date,
                first_entry=log.first_entry,
                last_exit=log.last_exit,
                working_hours=working_hours,
                status=log.status or "absent",
                is_late=bool(log.is_late),
                late_by_minutes=log.late_by_minutes,
                overtime_hours=log.overtime_hours,
                camera_id=log.camera_id,
            )
        )
    return records


async def get_monthly_report(
    db: AsyncSession,
    year: int,
    month: int,
    site_id: Optional[int] = None,
) -> List[MonthlyAttendance]:
    from ..models.attendance import AttendanceLog
    from ..models.employee import EmployeeMaster

    stmt = (
        select(
            EmployeeMaster.employee_id,
            EmployeeMaster.name,
            func.count().label("total_days"),
            func.sum(
                func.cast(AttendanceLog.status.in_(["present", "half_day"]), func.Integer())
            ).label("present_days"),
            func.sum(
                func.cast(AttendanceLog.status == "absent", func.Integer())
            ).label("absent_days"),
            func.sum(
                func.cast(AttendanceLog.is_late == True, func.Integer())
            ).label("late_days"),
            func.sum(
                func.coalesce(AttendanceLog.overtime_hours, 0)
            ).label("overtime_hours"),
        )
        .join(EmployeeMaster, AttendanceLog.employee_id == EmployeeMaster.id)
        .where(
            and_(
                func.extract("year", AttendanceLog.date) == year,
                func.extract("month", AttendanceLog.date) == month,
            )
        )
        .group_by(EmployeeMaster.employee_id, EmployeeMaster.name)
    )
    if site_id:
        stmt = stmt.where(EmployeeMaster.site_id == site_id)

    result = await db.execute(stmt)
    rows = result.all()

    import calendar
    working_days = sum(
        1
        for d in range(1, calendar.monthrange(year, month)[1] + 1)
        if date(year, month, d).weekday() < 5  # Mon–Fri
    )

    reports = []
    for emp_id, name, total, present, absent, late, overtime in rows:
        present = present or 0
        absent = absent or 0
        late = late or 0
        overtime = float(overtime or 0)
        pct = round((present / working_days * 100), 2) if working_days else 0.0
        reports.append(
            MonthlyAttendance(
                employee_id=emp_id,
                employee_name=name,
                month=month,
                year=year,
                working_days=working_days,
                present_days=present,
                absent_days=absent,
                late_days=late,
                overtime_hours=overtime,
                attendance_pct=pct,
            )
        )
    return reports


async def get_exceptions(
    db: AsyncSession, target_date: date, site_id: Optional[int] = None
) -> List[AttendanceException]:
    from ..models.attendance import AttendanceLog
    from ..models.employee import EmployeeMaster

    stmt = (
        select(AttendanceLog, EmployeeMaster.employee_id, EmployeeMaster.name)
        .join(EmployeeMaster, AttendanceLog.employee_id == EmployeeMaster.id)
        .where(
            and_(
                AttendanceLog.date == target_date,
                AttendanceLog.status.in_(["absent", "half_day"]) | (AttendanceLog.is_late == True),
            )
        )
    )
    if site_id:
        stmt = stmt.where(EmployeeMaster.site_id == site_id)

    result = await db.execute(stmt)
    rows = result.all()

    exceptions = []
    for log, emp_id, emp_name in rows:
        if log.status == "absent":
            exceptions.append(
                AttendanceException(
                    employee_id=emp_id,
                    employee_name=emp_name,
                    date=target_date,
                    exception_type="absent",
                )
            )
        if log.is_late:
            exceptions.append(
                AttendanceException(
                    employee_id=emp_id,
                    employee_name=emp_name,
                    date=target_date,
                    exception_type="late_arrival",
                    minutes_deviation=log.late_by_minutes,
                )
            )
        if log.last_exit is None and log.first_entry is not None:
            exceptions.append(
                AttendanceException(
                    employee_id=emp_id,
                    employee_name=emp_name,
                    date=target_date,
                    exception_type="no_checkout",
                )
            )
    return exceptions


async def manual_correction(
    db: AsyncSession,
    employee_id: str,
    correction: AttendanceCorrectionRequest,
    corrected_by: int,
) -> Optional[AttendanceRecord]:
    """Apply manual correction to an attendance record and write audit entry."""
    from ..models.attendance import AttendanceLog, AttendanceCorrectionAudit
    from ..models.employee import EmployeeMaster

    # Resolve employee DB pk
    emp_stmt = select(EmployeeMaster).where(EmployeeMaster.employee_id == employee_id)
    emp_result = await db.execute(emp_stmt)
    employee = emp_result.scalar_one_or_none()
    if employee is None:
        return None

    log_stmt = select(AttendanceLog).where(
        and_(AttendanceLog.employee_id == employee.id, AttendanceLog.date == correction.date)
    )
    log_result = await db.execute(log_stmt)
    log = log_result.scalar_one_or_none()

    if log is None:
        # Create new record
        log = AttendanceLog(
            employee_id=employee.id,
            date=correction.date,
            first_entry=correction.first_entry,
            last_exit=correction.last_exit,
            status=correction.status or "present",
        )
        db.add(log)
    else:
        # Save old values for audit
        old_vals = {
            "first_entry": str(log.first_entry),
            "last_exit": str(log.last_exit),
            "status": log.status,
        }
        if correction.first_entry is not None:
            log.first_entry = correction.first_entry
        if correction.last_exit is not None:
            log.last_exit = correction.last_exit
        if correction.status is not None:
            log.status = correction.status

        audit = AttendanceCorrectionAudit(
            attendance_id=log.id,
            corrected_by=corrected_by,
            old_values=old_vals,
            new_values={
                "first_entry": str(log.first_entry),
                "last_exit": str(log.last_exit),
                "status": log.status,
            },
            reason=correction.reason,
        )
        db.add(audit)

    await db.commit()
    await db.refresh(log)

    working_hours = None
    if log.first_entry and log.last_exit:
        delta = log.last_exit - log.first_entry
        working_hours = round(delta.total_seconds() / 3600, 2)

    return AttendanceRecord(
        employee_id=employee_id,
        date=log.date,
        first_entry=log.first_entry,
        last_exit=log.last_exit,
        working_hours=working_hours,
        status=log.status or "present",
        is_late=bool(log.is_late),
    )


def calculate_overtime(employee, attendance_record: AttendanceRecord) -> float:
    """
    Return hours beyond scheduled work_end_time.
    employee must have work_end_time attribute.
    Returns 0.0 if no overtime.
    """
    if attendance_record.last_exit is None or employee.work_end_time is None:
        return 0.0

    scheduled_end = datetime.combine(attendance_record.date, employee.work_end_time)
    # Make timezone-aware if needed
    if attendance_record.last_exit.tzinfo is not None:
        scheduled_end = scheduled_end.replace(tzinfo=timezone.utc)

    delta = attendance_record.last_exit - scheduled_end
    if delta.total_seconds() > 0:
        return round(delta.total_seconds() / 3600, 2)
    return 0.0
