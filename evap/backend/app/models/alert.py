"""
Alert, Notification, and Watchlist models.
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
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User
    from .site import SiteMaster, ZoneMaster
    from .camera import CameraMaster
    from .vehicle import VehicleMaster


class AlertLog(Base):
    __tablename__ = "alert_log"

    alert_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    site_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("site_master.site_id", ondelete="SET NULL"),
        nullable=True,
    )
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("camera_master.camera_id", ondelete="SET NULL"),
        nullable=True,
    )
    person_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vehicle_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("vehicle_master.vehicle_id", ondelete="SET NULL"),
        nullable=True,
    )
    zone_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("zone_master.zone_id", ondelete="SET NULL"),
        nullable=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_acknowledged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    acknowledged_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snapshot_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('info','warning','critical','emergency')",
            name="ck_alert_severity",
        ),
    )

    # Relationships
    site: Mapped[Optional["SiteMaster"]] = relationship(
        "SiteMaster", back_populates="alerts"
    )
    camera: Mapped[Optional["CameraMaster"]] = relationship(
        "CameraMaster", back_populates="alerts"
    )
    vehicle: Mapped[Optional["VehicleMaster"]] = relationship(
        "VehicleMaster", back_populates="alerts"
    )
    zone: Mapped[Optional["ZoneMaster"]] = relationship(
        "ZoneMaster", back_populates="alerts"
    )
    acknowledger: Mapped[Optional["User"]] = relationship(
        "User", back_populates="acknowledged_alerts"
    )
    notifications: Mapped[list["NotificationLog"]] = relationship(
        "NotificationLog", back_populates="alert", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<AlertLog alert_id={self.alert_id} "
            f"type={self.alert_type!r} severity={self.severity!r}>"
        )


class NotificationLog(Base):
    __tablename__ = "notification_log"

    notif_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("alert_log.alert_id", ondelete="CASCADE"),
        nullable=True,
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "channel IN ('email','sms','whatsapp','push','dashboard')",
            name="ck_notification_channel",
        ),
        CheckConstraint(
            "status IN ('pending','sent','failed','delivered')",
            name="ck_notification_status",
        ),
    )

    # Relationships
    alert: Mapped[Optional["AlertLog"]] = relationship(
        "AlertLog", back_populates="notifications"
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationLog notif_id={self.notif_id} "
            f"channel={self.channel!r} status={self.status!r}>"
        )


class Watchlist(Base):
    __tablename__ = "watchlist"

    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_type: Mapped[str] = mapped_column(String(16), nullable=False)
    person_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    added_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "person_type IN ('employee','visitor','unknown')",
            name="ck_watchlist_person_type",
        ),
        CheckConstraint(
            "severity IN ('info','warning','critical','emergency')",
            name="ck_watchlist_severity",
        ),
    )

    # Relationships
    adder: Mapped[Optional["User"]] = relationship(
        "User", back_populates="watchlist_entries"
    )

    def __repr__(self) -> str:
        return (
            f"<Watchlist entry_id={self.entry_id} "
            f"person_type={self.person_type!r} severity={self.severity!r}>"
        )
