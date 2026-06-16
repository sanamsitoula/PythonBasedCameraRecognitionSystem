"""ERP integration service: employee sync and attendance push."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ERP_ADAPTERS = {}  # registered in module body below


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

def register_adapter(erp_type: str):
    """Decorator to register an ERP adapter class."""
    def decorator(cls):
        ERP_ADAPTERS[erp_type] = cls
        return cls
    return decorator


def _get_settings():
    from ..core.config import settings  # type: ignore[import]
    return settings


# ---------------------------------------------------------------------------
# Base adapter
# ---------------------------------------------------------------------------

class BaseERPAdapter:
    erp_type: str = "base"

    def __init__(self):
        self.settings = _get_settings()

    async def fetch_employees(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def push_attendance(self, attendance_records: List[Dict]) -> bool:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Odoo adapter
# ---------------------------------------------------------------------------

@register_adapter("odoo")
class OdooAdapter(BaseERPAdapter):
    erp_type = "odoo"

    def __init__(self):
        super().__init__()
        self.base_url = getattr(self.settings, "ODOO_URL", "http://localhost:8069")
        self.db_name = getattr(self.settings, "ODOO_DB", "odoo")
        self.username = getattr(self.settings, "ODOO_USER", "admin")
        self.password = getattr(self.settings, "ODOO_PASSWORD", "")
        self._uid: Optional[int] = None

    async def _authenticate(self) -> int:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self.base_url}/web/dataset/call_kw",
                json={
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {
                        "model": "res.users",
                        "method": "authenticate",
                        "args": [self.db_name, self.username, self.password, {}],
                        "kwargs": {},
                    },
                },
            )
            data = resp.json()
            uid = data.get("result")
            if not uid:
                raise ConnectionError(f"Odoo authentication failed: {data.get('error')}")
            self._uid = uid
            return uid

    async def fetch_employees(self) -> List[Dict[str, Any]]:
        uid = self._uid or await self._authenticate()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/web/dataset/call_kw",
                json={
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {
                        "model": "hr.employee",
                        "method": "search_read",
                        "args": [[["active", "=", True]]],
                        "kwargs": {
                            "fields": ["id", "name", "job_title", "department_id", "work_email", "mobile_phone"],
                            "limit": 5000,
                        },
                    },
                },
            )
            result = resp.json().get("result", [])
        employees = []
        for emp in result:
            employees.append({
                "employee_id": str(emp["id"]),
                "name": emp.get("name", ""),
                "designation": emp.get("job_title", ""),
                "department": emp.get("department_id", [None, ""])[1] if emp.get("department_id") else "",
                "email": emp.get("work_email", ""),
                "phone": emp.get("mobile_phone", ""),
            })
        return employees

    async def push_attendance(self, attendance_records: List[Dict]) -> bool:
        uid = self._uid or await self._authenticate()
        # Map EVAP attendance records to Odoo hr.attendance format
        odoo_records = []
        for rec in attendance_records:
            if rec.get("first_entry") and rec.get("last_exit"):
                odoo_records.append({
                    "employee_id": int(rec["employee_db_id"]),
                    "check_in": rec["first_entry"],
                    "check_out": rec["last_exit"],
                })

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/web/dataset/call_kw",
                json={
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {
                        "model": "hr.attendance",
                        "method": "create",
                        "args": [odoo_records],
                        "kwargs": {},
                    },
                },
            )
            result = resp.json()
            return "result" in result


# ---------------------------------------------------------------------------
# SAP adapter
# ---------------------------------------------------------------------------

@register_adapter("sap")
class SAPAdapter(BaseERPAdapter):
    erp_type = "sap"

    def __init__(self):
        super().__init__()
        self.base_url = getattr(self.settings, "SAP_ODATA_URL", "")
        self.client_id = getattr(self.settings, "SAP_CLIENT_ID", "")
        self.client_secret = getattr(self.settings, "SAP_CLIENT_SECRET", "")
        self._token: Optional[str] = None

    async def _get_token(self) -> str:
        token_url = getattr(self.settings, "SAP_TOKEN_URL", "")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                token_url,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
            return self._token

    async def fetch_employees(self) -> List[Dict[str, Any]]:
        token = self._token or await self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/EmployeeCollection",
                headers=headers,
                params={"$format": "json", "$top": 5000},
            )
            resp.raise_for_status()
            d = resp.json().get("d", {}).get("results", [])
        return [
            {
                "employee_id": emp.get("EmployeeID", ""),
                "name": emp.get("FormattedName", ""),
                "department": emp.get("DepartmentName", ""),
                "designation": emp.get("JobTitle", ""),
                "email": emp.get("Email", ""),
            }
            for emp in d
        ]

    async def push_attendance(self, attendance_records: List[Dict]) -> bool:
        """SAP CATS (Cross-Application Time Sheet) push."""
        token = self._token or await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "to_TimeRecord": [
                {
                    "EmployeeID": rec.get("employee_id", ""),
                    "Date": rec.get("date", ""),
                    "TimeIn": rec.get("first_entry", ""),
                    "TimeOut": rec.get("last_exit", ""),
                }
                for rec in attendance_records
                if rec.get("first_entry") and rec.get("last_exit")
            ]
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/TimeSheetDataFields",
                headers=headers,
                json=payload,
            )
            return resp.status_code in (200, 201, 204)


# ---------------------------------------------------------------------------
# JEMC ERP adapter (generic REST)
# ---------------------------------------------------------------------------

@register_adapter("jemc")
class JEMCAdapter(BaseERPAdapter):
    erp_type = "jemc"

    def __init__(self):
        super().__init__()
        self.base_url = getattr(self.settings, "JEMC_ERP_URL", "")
        self.api_key = getattr(self.settings, "JEMC_API_KEY", "")

    async def fetch_employees(self) -> List[Dict[str, Any]]:
        headers = {"X-API-Key": self.api_key, "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self.base_url}/api/v1/employees", headers=headers)
            resp.raise_for_status()
            return resp.json().get("employees", [])

    async def push_attendance(self, attendance_records: List[Dict]) -> bool:
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/attendance/bulk",
                headers=headers,
                json={"records": attendance_records},
            )
            return resp.status_code in (200, 201)


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

async def sync_employees_from_erp(db: AsyncSession, erp_type: str) -> Dict[str, int]:
    """Pull employees from ERP and upsert into employee_master. Returns stats."""
    from ..models.employee import EmployeeMaster  # type: ignore[import]
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    AdapterClass = ERP_ADAPTERS.get(erp_type)
    if AdapterClass is None:
        raise ValueError(f"Unsupported ERP type: {erp_type}")

    adapter = AdapterClass()
    employees = await adapter.fetch_employees()

    created = updated = errors = 0
    for emp_data in employees:
        try:
            stmt = pg_insert(EmployeeMaster).values(
                employee_id=emp_data["employee_id"],
                name=emp_data.get("name", ""),
                department=emp_data.get("department"),
                designation=emp_data.get("designation"),
                email=emp_data.get("email"),
                phone=emp_data.get("phone"),
                is_active=True,
            ).on_conflict_do_update(
                index_elements=["employee_id"],
                set_={
                    "name": emp_data.get("name", ""),
                    "department": emp_data.get("department"),
                    "designation": emp_data.get("designation"),
                    "email": emp_data.get("email"),
                },
            )
            result = await db.execute(stmt)
            if result.rowcount > 0:
                updated += 1
            else:
                created += 1
        except Exception as exc:
            logger.error("Employee upsert error: %s", exc)
            errors += 1

    await db.commit()
    stats = {"created": created, "updated": updated, "errors": errors, "total": len(employees)}
    await log_sync(
        db,
        erp_type=erp_type,
        entity_type="employee",
        direction="inbound",
        status="success" if errors == 0 else "partial",
        payload=stats,
        error=None,
    )
    logger.info("ERP employee sync complete: %s", stats)
    return stats


async def push_attendance_to_erp(db: AsyncSession, erp_type: str, target_date: date) -> bool:
    """Send attendance records for target_date to the ERP system."""
    from ..models.attendance import AttendanceLog  # type: ignore[import]
    from ..models.employee import EmployeeMaster
    from sqlalchemy import and_

    AdapterClass = ERP_ADAPTERS.get(erp_type)
    if AdapterClass is None:
        raise ValueError(f"Unsupported ERP type: {erp_type}")

    stmt = (
        select(AttendanceLog, EmployeeMaster.employee_id)
        .join(EmployeeMaster, AttendanceLog.employee_id == EmployeeMaster.id)
        .where(AttendanceLog.date == target_date)
    )
    result = await db.execute(stmt)
    rows = result.all()

    records = [
        {
            "employee_id": emp_id,
            "employee_db_id": log.employee_id,
            "date": str(target_date),
            "first_entry": log.first_entry.isoformat() if log.first_entry else None,
            "last_exit": log.last_exit.isoformat() if log.last_exit else None,
            "status": log.status,
        }
        for log, emp_id in rows
    ]

    adapter = AdapterClass()
    success = await adapter.push_attendance(records)
    await log_sync(
        db,
        erp_type=erp_type,
        entity_type="attendance",
        direction="outbound",
        status="success" if success else "failed",
        payload={"date": str(target_date), "records": len(records)},
    )
    return success


async def get_sync_status(db: AsyncSession, erp_type: str) -> Optional[Dict]:
    from ..models.erp import ERPSyncLog  # type: ignore[import]

    stmt = (
        select(ERPSyncLog)
        .where(ERPSyncLog.erp_type == erp_type)
        .order_by(ERPSyncLog.synced_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return {
        "erp_type": row.erp_type,
        "entity_type": row.entity_type,
        "direction": row.direction,
        "status": row.status,
        "synced_at": row.synced_at.isoformat(),
        "error_message": row.error_message,
    }


async def log_sync(
    db: AsyncSession,
    erp_type: str,
    entity_type: str,
    direction: str,
    status: str,
    payload: Optional[Any] = None,
    error: Optional[str] = None,
) -> None:
    from ..models.erp import ERPSyncLog  # type: ignore[import]

    log = ERPSyncLog(
        erp_type=erp_type,
        entity_type=entity_type,
        entity_id="bulk",
        direction=direction,
        status=status,
        payload=payload,
        error_message=error,
        synced_at=datetime.now(timezone.utc),
    )
    db.add(log)
    await db.commit()
