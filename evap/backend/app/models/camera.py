"""
CameraMaster and CameraStream models.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .site import SiteMaster, BuildingMaster, FloorMaster, ZoneMaster
    from .analytics import OccupancyLog, ZoneHistory, BehaviorEvent
    from .alert import AlertLog
    from .vehicle import LicensePlateLog


class CameraMaster(Base):
    __tablename__ = "camera_master"

    camera_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("site_master.site_id", ondelete="SET NULL"), nullable=True
    )
    building_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("building_master.building_id", ondelete="SET NULL"),
        nullable=True,
    )
    floor_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("floor_master.floor_id", ondelete="SET NULL"),
        nullable=True,
    )
    zone_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("zone_master.zone_id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rtsp_url_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    camera_type: Mapped[str] = mapped_column(String(32), nullable=False, default="fixed")
    resolution: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    fps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="offline")
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    installed_at: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    location_x: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    location_y: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    direction_degrees: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "camera_type IN ('fixed','ptz','fisheye','thermal','anpr','360')",
            name="ck_camera_type",
        ),
        CheckConstraint("fps > 0 AND fps <= 120", name="ck_camera_fps"),
        CheckConstraint(
            "status IN ('online','offline','error','maintenance')",
            name="ck_camera_status",
        ),
        CheckConstraint(
            "direction_degrees >= 0 AND direction_degrees < 360",
            name="ck_camera_direction",
        ),
    )

    # Relationships
    site: Mapped[Optional["SiteMaster"]] = relationship(
        "SiteMaster", back_populates="cameras"
    )
    building: Mapped[Optional["BuildingMaster"]] = relationship(
        "BuildingMaster", back_populates="cameras"
    )
    floor: Mapped[Optional["FloorMaster"]] = relationship(
        "FloorMaster", back_populates="cameras"
    )
    zone: Mapped[Optional["ZoneMaster"]] = relationship(
        "ZoneMaster", back_populates="cameras"
    )
    streams: Mapped[list["CameraStream"]] = relationship(
        "CameraStream", back_populates="camera", cascade="all, delete-orphan"
    )
    occupancy_logs: Mapped[list["OccupancyLog"]] = relationship(
        "OccupancyLog", back_populates="camera"
    )
    zone_histories: Mapped[list["ZoneHistory"]] = relationship(
        "ZoneHistory", back_populates="camera"
    )
    alerts: Mapped[list["AlertLog"]] = relationship(
        "AlertLog", back_populates="camera"
    )
    plate_logs: Mapped[list["LicensePlateLog"]] = relationship(
        "LicensePlateLog", back_populates="camera"
    )
    behavior_events: Mapped[list["BehaviorEvent"]] = relationship(
        "BehaviorEvent", back_populates="camera"
    )

    def __repr__(self) -> str:
        return f"<CameraMaster camera_id={self.camera_id} name={self.name!r} status={self.status!r}>"


class CameraStream(Base):
    __tablename__ = "camera_streams"

    stream_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("camera_master.camera_id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    frames_processed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    detections_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    avg_fps: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','stopped','error')", name="ck_stream_status"
        ),
    )

    # Relationships
    camera: Mapped["CameraMaster"] = relationship(
        "CameraMaster", back_populates="streams"
    )

    def __repr__(self) -> str:
        return f"<CameraStream stream_id={self.stream_id} camera_id={self.camera_id} status={self.status!r}>"
