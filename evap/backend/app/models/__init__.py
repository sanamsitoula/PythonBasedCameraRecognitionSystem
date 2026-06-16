"""
EVAP models package — re-exports all models so that
`from app.models import XYZ` works from any module.

All Base classes resolve to the same DeclarativeBase from .base.
"""

from .base import Base

# ─── Auth / RBAC ──────────────────────────────────────────────────────────────
from .user import ApiKey, Role, User

# ─── Sites ────────────────────────────────────────────────────────────────────
from .site import BuildingMaster, FloorMaster, SiteMaster, ZoneMaster

# ─── Cameras ──────────────────────────────────────────────────────────────────
from .camera import CameraMaster, CameraStream

# ─── Employees ────────────────────────────────────────────────────────────────
from .employee import EmployeeFaceMaster, EmployeeMaster, FaceEmbedding, FaceMaster

# ─── Visitors ─────────────────────────────────────────────────────────────────
from .visitor import VisitorMaster, VisitorTracking

# ─── Vehicles ─────────────────────────────────────────────────────────────────
from .vehicle import LicensePlateLog, VehicleMaster

# ─── Attendance ───────────────────────────────────────────────────────────────
from .attendance import AttendanceLog, EmployeeZoneHistory, MovementHistory

# ─── Alerts & Notifications ───────────────────────────────────────────────────
from .alert import AlertLog, NotificationLog, Watchlist

# ─── Analytics ────────────────────────────────────────────────────────────────
from .analytics import (
    AnalyticsDaily,
    AnalyticsMonthly,
    BehaviorEvent,
    OccupancyLog,
    ZoneHistory,
)

# ─── System ───────────────────────────────────────────────────────────────────
from .system import ApiLog, AuditLog, ErpSyncLog, Report, SystemHealth

# =============================================================================
# API-layer aliases  (API files use shorter names; models use *Master suffix)
# =============================================================================
Alert            = AlertLog
AlertRule        = Watchlist
Camera           = CameraMaster
StreamHealth     = CameraStream
MovementEvent    = MovementHistory
Visitor          = VisitorMaster
AttendanceRecord = AttendanceLog
Employee         = EmployeeMaster
Floor            = FloorMaster
OccupancySnapshot= OccupancyLog
Zone             = ZoneMaster
Building         = BuildingMaster
Site             = SiteMaster
VehicleLog       = LicensePlateLog
VehicleRegistry  = VehicleMaster
DailyAnalytics   = AnalyticsDaily
SystemMetric     = SystemHealth

# =============================================================================
# Stub models for features not yet fully modelled
# =============================================================================
import sqlalchemy as _sa
from sqlalchemy.dialects.postgresql import JSONB as _JSONB
from sqlalchemy.orm import Mapped as _Mapped, mapped_column as _mc


class Detection(Base):
    """Camera detection event stub."""
    __tablename__ = "detections"
    id:          _Mapped[int]  = _mc(_sa.BigInteger, primary_key=True)
    camera_id:   _Mapped[int]  = _mc(_sa.Integer,   nullable=True)
    class_label: _Mapped[str]  = _mc(_sa.String(50), nullable=True)
    confidence:  _Mapped[float]= _mc(_sa.Float,      nullable=True)
    bbox:        _Mapped[dict] = _mc(_JSONB,          nullable=True)
    detected_at: _Mapped[object]= _mc(_sa.DateTime(timezone=True), server_default=_sa.func.now())


class HeatmapData(Base):
    """Zone heatmap data stub."""
    __tablename__ = "heatmap_data"
    id:          _Mapped[int]  = _mc(_sa.BigInteger, primary_key=True)
    zone_id:     _Mapped[str]  = _mc(_sa.String(100), nullable=True)
    camera_id:   _Mapped[int]  = _mc(_sa.Integer,    nullable=True)
    heat_value:  _Mapped[float]= _mc(_sa.Float,       nullable=True)
    recorded_at: _Mapped[object]= _mc(_sa.DateTime(timezone=True), server_default=_sa.func.now())


class NotificationSetting(Base):
    """Per-user notification preference stub."""
    __tablename__ = "notification_settings"
    id:       _Mapped[int]  = _mc(_sa.Integer, primary_key=True)
    user_id:  _Mapped[int]  = _mc(_sa.Integer, nullable=True)
    channel:  _Mapped[str]  = _mc(_sa.String(50), nullable=True)
    enabled:  _Mapped[bool] = _mc(_sa.Boolean, default=True)
    settings: _Mapped[dict] = _mc(_JSONB, nullable=True)


class ErpConfig(Base):
    """ERP integration configuration stub."""
    __tablename__ = "erp_config"
    id:         _Mapped[int] = _mc(_sa.Integer,    primary_key=True)
    erp_name:   _Mapped[str] = _mc(_sa.String(100), nullable=True)
    api_url:    _Mapped[str] = _mc(_sa.Text,         nullable=True)
    api_key:    _Mapped[str] = _mc(_sa.String(255),  nullable=True)
    is_active:  _Mapped[bool]= _mc(_sa.Boolean,      default=True)
    last_synced:_Mapped[object]= _mc(_sa.DateTime(timezone=True), nullable=True)

__all__ = [
    "Base",
    # Auth
    "Role",
    "User",
    "ApiKey",
    # Sites
    "SiteMaster",
    "BuildingMaster",
    "FloorMaster",
    "ZoneMaster",
    # Cameras
    "CameraMaster",
    "CameraStream",
    # Employees
    "EmployeeMaster",
    "EmployeeFaceMaster",
    "FaceEmbedding",
    "FaceMaster",
    # Visitors
    "VisitorMaster",
    "VisitorTracking",
    # Vehicles
    "VehicleMaster",
    "LicensePlateLog",
    # Attendance
    "AttendanceLog",
    "EmployeeZoneHistory",
    "MovementHistory",
    # Alerts
    "AlertLog",
    "NotificationLog",
    "Watchlist",
    # Analytics
    "OccupancyLog",
    "ZoneHistory",
    "AnalyticsDaily",
    "AnalyticsMonthly",
    "BehaviorEvent",
    # System
    "SystemMetric",
    "Report",
    "ApiLog",
    "AuditLog",
]
