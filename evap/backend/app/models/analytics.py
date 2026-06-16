"""
Analytics and behaviour detection models.
"""
from __future__ import annotations

from datetime import date as dt_date, datetime
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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .camera import CameraMaster
    from .site import SiteMaster, ZoneMaster


class OccupancyLog(Base):
    __tablename__ = "occupancy_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("camera_master.camera_id", ondelete="SET NULL"),
        nullable=True,
    )
    zone_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("zone_master.zone_id", ondelete="SET NULL"),
        nullable=True,
    )
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    people_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    employees_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visitors_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    occupancy_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)

    __table_args__ = (
        CheckConstraint("people_count >= 0", name="ck_occupancy_people_count"),
        CheckConstraint("employees_count >= 0", name="ck_occupancy_employees_count"),
        CheckConstraint("visitors_count >= 0", name="ck_occupancy_visitors_count"),
        CheckConstraint("max_capacity > 0", name="ck_occupancy_max_capacity"),
        CheckConstraint(
            "occupancy_pct >= 0 AND occupancy_pct <= 100",
            name="ck_occupancy_pct",
        ),
    )

    # Relationships
    camera: Mapped[Optional["CameraMaster"]] = relationship(
        "CameraMaster", back_populates="occupancy_logs"
    )
    zone: Mapped[Optional["ZoneMaster"]] = relationship(
        "ZoneMaster", back_populates="occupancy_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<OccupancyLog log_id={self.log_id} zone_id={self.zone_id} "
            f"people={self.people_count} pct={self.occupancy_pct}>"
        )


class ZoneHistory(Base):
    __tablename__ = "zone_history"

    history_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(Integer, nullable=False)
    person_type: Mapped[str] = mapped_column(String(16), nullable=False)
    zone_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("zone_master.zone_id", ondelete="SET NULL"),
        nullable=True,
    )
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("camera_master.camera_id", ondelete="SET NULL"),
        nullable=True,
    )
    entry_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    exit_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "person_type IN ('employee','visitor','unknown')",
            name="ck_zone_history_person_type",
        ),
        CheckConstraint(
            "duration_seconds >= 0", name="ck_zone_history_duration"
        ),
    )

    # Relationships
    zone: Mapped[Optional["ZoneMaster"]] = relationship(
        "ZoneMaster", back_populates="zone_histories"
    )
    camera: Mapped[Optional["CameraMaster"]] = relationship(
        "CameraMaster", back_populates="zone_histories"
    )

    def __repr__(self) -> str:
        return (
            f"<ZoneHistory history_id={self.history_id} "
            f"person_id={self.person_id} type={self.person_type!r}>"
        )


class AnalyticsDaily(Base):
    __tablename__ = "analytics_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt_date] = mapped_column(Date, nullable=False)
    site_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("site_master.site_id", ondelete="CASCADE"),
        nullable=True,
    )
    total_entries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_exits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    peak_occupancy: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_occupancy: Mapped[float] = mapped_column(
        Numeric(8, 2), nullable=False, default=0
    )
    total_employees: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_visitors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_vehicles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_visitors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    late_arrivals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("date", "site_id", name="uq_analytics_daily_date_site"),
    )

    # Relationships
    site: Mapped[Optional["SiteMaster"]] = relationship(
        "SiteMaster", back_populates="analytics_daily"
    )

    def __repr__(self) -> str:
        return f"<AnalyticsDaily id={self.id} date={self.date} site_id={self.site_id}>"


class AnalyticsMonthly(Base):
    __tablename__ = "analytics_monthly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    site_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("site_master.site_id", ondelete="CASCADE"),
        nullable=True,
    )
    working_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    total_attendance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_daily_attendance: Mapped[float] = mapped_column(
        Numeric(8, 2), nullable=False, default=0
    )
    total_visitors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_vehicles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("year", "month", "site_id", name="uq_analytics_monthly_period_site"),
        CheckConstraint("year >= 2000 AND year <= 2100", name="ck_analytics_year"),
        CheckConstraint("month >= 1 AND month <= 12", name="ck_analytics_month"),
    )

    # Relationships
    site: Mapped[Optional["SiteMaster"]] = relationship(
        "SiteMaster", back_populates="analytics_monthly"
    )

    def __repr__(self) -> str:
        return f"<AnalyticsMonthly id={self.id} year={self.year} month={self.month} site_id={self.site_id}>"


class BehaviorEvent(Base):
    __tablename__ = "behavior_events"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("camera_master.camera_id", ondelete="SET NULL"),
        nullable=True,
    )
    zone_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("zone_master.zone_id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    person_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snapshot_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alert_generated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('loitering','running','abandoned_object','crowding','tailgating')",
            name="ck_behavior_event_type",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_behavior_confidence"
        ),
    )

    # Relationships
    camera: Mapped[Optional["CameraMaster"]] = relationship(
        "CameraMaster", back_populates="behavior_events"
    )
    zone: Mapped[Optional["ZoneMaster"]] = relationship(
        "ZoneMaster", back_populates="behavior_events"
    )

    def __repr__(self) -> str:
        return (
            f"<BehaviorEvent event_id={self.event_id} "
            f"type={self.event_type!r} camera_id={self.camera_id}>"
        )
