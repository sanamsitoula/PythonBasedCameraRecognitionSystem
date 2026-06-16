"""
Vehicle and License Plate models for ANPR integration.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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
    from .camera import CameraMaster
    from .site import SiteMaster
    from .alert import AlertLog


class VehicleMaster(Base):
    __tablename__ = "vehicle_master"

    vehicle_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plate_number: Mapped[str] = mapped_column(String(32), nullable=False)
    plate_country: Mapped[str] = mapped_column(String(4), nullable=False, default="IN")
    vehicle_type: Mapped[str] = mapped_column(String(16), nullable=False, default="car")
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    owner_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    make: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_whitelisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "vehicle_type IN ('car','bus','truck','motorcycle','bicycle')",
            name="ck_vehicle_type",
        ),
        CheckConstraint(
            "owner_type IN ('employee','visitor','unknown')",
            name="ck_vehicle_owner_type",
        ),
        CheckConstraint(
            "NOT (is_whitelisted AND is_blacklisted)",
            name="ck_vehicle_not_both_listed",
        ),
    )

    # Relationships
    plate_logs: Mapped[list["LicensePlateLog"]] = relationship(
        "LicensePlateLog", back_populates="vehicle"
    )
    alerts: Mapped[list["AlertLog"]] = relationship(
        "AlertLog", back_populates="vehicle"
    )

    def __repr__(self) -> str:
        return (
            f"<VehicleMaster vehicle_id={self.vehicle_id} "
            f"plate={self.plate_number!r} type={self.vehicle_type!r}>"
        )


class LicensePlateLog(Base):
    __tablename__ = "license_plate_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("camera_master.camera_id", ondelete="SET NULL"),
        nullable=True,
    )
    vehicle_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("vehicle_master.vehicle_id", ondelete="SET NULL"),
        nullable=True,
    )
    plate_number: Mapped[str] = mapped_column(String(32), nullable=False)
    plate_confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    vehicle_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    entry_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    exit_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parking_duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    snapshot_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    site_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("site_master.site_id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "vehicle_type IN ('car','bus','truck','motorcycle','bicycle')",
            name="ck_lp_log_vehicle_type",
        ),
        CheckConstraint(
            "direction IN ('entry','exit','unknown')", name="ck_lp_log_direction"
        ),
        CheckConstraint(
            "plate_confidence >= 0 AND plate_confidence <= 1",
            name="ck_lp_log_confidence",
        ),
        CheckConstraint(
            "parking_duration_seconds >= 0", name="ck_lp_log_duration"
        ),
    )

    # Relationships
    camera: Mapped[Optional["CameraMaster"]] = relationship(
        "CameraMaster", back_populates="plate_logs"
    )
    vehicle: Mapped[Optional["VehicleMaster"]] = relationship(
        "VehicleMaster", back_populates="plate_logs"
    )
    site: Mapped[Optional["SiteMaster"]] = relationship(
        "SiteMaster", back_populates="plate_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<LicensePlateLog log_id={self.log_id} "
            f"plate={self.plate_number!r} direction={self.direction!r}>"
        )
