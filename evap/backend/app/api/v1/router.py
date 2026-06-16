from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    analytics,
    attendance,
    auth,
    cameras,
    dashboard,
    employees,
    erp,
    maps,
    notifications,
    reports,
    sites,
    vehicles,
    visitors,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(sites.router)
api_router.include_router(cameras.router)
api_router.include_router(employees.router)
api_router.include_router(visitors.router)
api_router.include_router(vehicles.router)
api_router.include_router(attendance.router)
api_router.include_router(alerts.router)
api_router.include_router(analytics.router)
api_router.include_router(maps.router)
api_router.include_router(reports.router)
api_router.include_router(notifications.router)
api_router.include_router(erp.router)
api_router.include_router(dashboard.router)
