"""
Site, Building, Floor, and Zone models for location hierarchy.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .camera import CameraMaster
    from .analytics import OccupancyLog, ZoneHistory, AnalyticsDaily, AnalyticsMonthly
    from .alert import AlertLog
    from .vehicle import LicensePlateLog


class SiteMaster(Base):
    __tablename__ = "site_master"

    site_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    coord_lat: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    coord_lon: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    buildings: Mapped[list["BuildingMaster"]] = relationship(
        "BuildingMaster", back_populates="site", cascade="all, delete-orphan"
    )
    cameras: Mapped[list["CameraMaster"]] = relationship(
        "CameraMaster", back_populates="site"
    )
    alerts: Mapped[list["AlertLog"]] = relationship(
        "AlertLog", back_populates="site"
    )
    plate_logs: Mapped[list["LicensePlateLog"]] = relationship(
        "LicensePlateLog", back_populates="site"
    )
    analytics_daily: Mapped[list["AnalyticsDaily"]] = relationship(
        "AnalyticsDaily", back_populates="site", cascade="all, delete-orphan"
    )
    analytics_monthly: Mapped[list["AnalyticsMonthly"]] = relationship(
        "AnalyticsMonthly", back_populates="site", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SiteMaster site_id={self.site_id} name={self.name!r}>"


class BuildingMaster(Base):
    __tablename__ = "building_master"

    building_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_master.site_id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    floors_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    floor_plan_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("floors_count >= 1", name="ck_building_floors_count"),
    )

    # Relationships
    site: Mapped["SiteMaster"] = relationship("SiteMaster", back_populates="buildings")
    floors: Mapped[list["FloorMaster"]] = relationship(
        "FloorMaster", back_populates="building", cascade="all, delete-orphan"
    )
    cameras: Mapped[list["CameraMaster"]] = relationship(
        "CameraMaster", back_populates="building"
    )

    def __repr__(self) -> str:
        return f"<BuildingMaster building_id={self.building_id} name={self.name!r}>"


class FloorMaster(Base):
    __tablename__ = "floor_master"

    floor_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    building_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("building_master.building_id", ondelete="CASCADE"),
        nullable=False,
    )
    floor_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    map_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    width_meters: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    height_meters: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)

    __table_args__ = (
        UniqueConstraint("building_id", "floor_number", name="uq_floor_building_number"),
    )

    # Relationships
    building: Mapped["BuildingMaster"] = relationship(
        "BuildingMaster", back_populates="floors"
    )
    zones: Mapped[list["ZoneMaster"]] = relationship(
        "ZoneMaster", back_populates="floor", cascade="all, delete-orphan"
    )
    cameras: Mapped[list["CameraMaster"]] = relationship(
        "CameraMaster", back_populates="floor"
    )

    def __repr__(self) -> str:
        return f"<FloorMaster floor_id={self.floor_id} number={self.floor_number}>"


class ZoneMaster(Base):
    __tablename__ = "zone_master"

    zone_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    floor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("floor_master.floor_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    polygon: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    max_capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    color_code: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "zone_type IN ('general','entrance','exit','restricted','parking','canteen',"
            "'office','corridor','stairwell','elevator','lobby','server_room','warehouse')",
            name="ck_zone_type",
        ),
        CheckConstraint("max_capacity > 0", name="ck_zone_max_capacity"),
    )

    # Relationships
    floor: Mapped["FloorMaster"] = relationship("FloorMaster", back_populates="zones")
    cameras: Mapped[list["CameraMaster"]] = relationship(
        "CameraMaster", back_populates="zone"
    )
    occupancy_logs: Mapped[list["OccupancyLog"]] = relationship(
        "OccupancyLog", back_populates="zone"
    )
    zone_histories: Mapped[list["ZoneHistory"]] = relationship(
        "ZoneHistory", back_populates="zone"
    )
    alerts: Mapped[list["AlertLog"]] = relationship("AlertLog", back_populates="zone")
    behavior_events: Mapped[list["BehaviorEvent"]] = relationship(  # type: ignore[name-defined]
        "BehaviorEvent", back_populates="zone"
    )

    def __repr__(self) -> str:
        return f"<ZoneMaster zone_id={self.zone_id} name={self.name!r} type={self.zone_type!r}>"


from .analytics import BehaviorEvent  # noqa: E402, F401
