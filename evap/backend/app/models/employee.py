"""
Employee models — aligned with cctv_analytics Phase 3 schema.
EVAP extension columns are added by sql/005_evap_web_tables.sql via ALTER TABLE.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime,
    ForeignKey, Integer, Numeric, String, Text, Time,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .attendance import AttendanceLog, EmployeeZoneHistory, MovementHistory


class EmployeeMaster(Base):
    """Reflects cctv_analytics.employee_master (Phase 3).
    'full_name' Python attr maps to 'employee_name' DB column.
    Extension cols (email, phone, is_active, employee_code) added by ALTER TABLE.
    """
    __tablename__ = "employee_master"

    employee_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    full_name: Mapped[str] = mapped_column("employee_name", String(200), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    designation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    work_start_time: Mapped[Optional[object]] = mapped_column(Time, nullable=True)
    work_end_time: Mapped[Optional[object]] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    # EVAP extension columns
    employee_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Enrollment tracking columns (added by sql/006_employee_enrollment_fields.sql)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enrollment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_started"
    )
    enrollment_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    photo_paths: Mapped[object] = mapped_column(
        JSONB, nullable=False, default=list, server_default="'[]'::jsonb"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','inactive','deleted')", name="ck_em_status"
        ),
        CheckConstraint(
            "enrollment_status IN ('not_started','pending','enrolled','failed')",
            name="ck_em_enrollment_status",
        ),
    )

    face_masters: Mapped[list["EmployeeFaceMaster"]] = relationship(
        "EmployeeFaceMaster", back_populates="employee", cascade="all, delete-orphan"
    )
    phase4_faces: Mapped[list["FaceMaster"]] = relationship(
        "FaceMaster", back_populates="employee", cascade="all, delete-orphan"
    )
    attendance_logs: Mapped[list["AttendanceLog"]] = relationship(
        "AttendanceLog", back_populates="employee"
    )
    zone_histories: Mapped[list["EmployeeZoneHistory"]] = relationship(
        "EmployeeZoneHistory", back_populates="employee"
    )

    def __repr__(self) -> str:
        return f"<EmployeeMaster employee_id={self.employee_id!r} name={self.full_name!r}>"


class EmployeeFaceMaster(Base):
    """Reflects cctv_analytics.employee_face_master (Phase 3).
    'face_id' Python attr maps to 'face_master_id' DB column.
    """
    __tablename__ = "employee_face_master"

    face_id: Mapped[int] = mapped_column(
        "face_master_id", Integer, primary_key=True, autoincrement=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("employee_master.employee_id", ondelete="CASCADE"),
        nullable=False,
    )
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_enrolled: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    enrolled_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # EVAP extension columns
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quality_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)

    employee: Mapped["EmployeeMaster"] = relationship(
        "EmployeeMaster", back_populates="face_masters"
    )
    embeddings: Mapped[list["FaceEmbedding"]] = relationship(
        "FaceEmbedding", back_populates="face_master_obj", cascade="all, delete-orphan",
        primaryjoin="EmployeeFaceMaster.employee_id == foreign(FaceEmbedding.employee_id)",
        foreign_keys="[EmployeeFaceMaster.employee_id]",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<EmployeeFaceMaster face_id={self.face_id} employee_id={self.employee_id!r}>"


class FaceEmbedding(Base):
    """Reflects cctv_analytics.face_embeddings (Phase 3).
    PK is employee_id (VARCHAR) referencing employee_master.
    """
    __tablename__ = "face_embeddings"

    embedding_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("employee_master.employee_id", ondelete="CASCADE"),
        nullable=False,
    )
    embedding_vector: Mapped[Optional[bytes]] = mapped_column(nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_angle: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    model_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    face_master_obj: Mapped[Optional["EmployeeFaceMaster"]] = relationship(
        "EmployeeFaceMaster",
        primaryjoin="FaceEmbedding.employee_id == foreign(EmployeeFaceMaster.employee_id)",
        foreign_keys="[FaceEmbedding.employee_id]",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<FaceEmbedding embedding_id={self.embedding_id} employee_id={self.employee_id!r}>"


class FaceMaster(Base):
    """Phase 4 extended face records — new table created in cctv_analytics."""
    __tablename__ = "face_master"

    face_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("employee_master.employee_id", ondelete="CASCADE"),
        nullable=True,
    )
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    quality_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "quality_score >= 0 AND quality_score <= 1", name="ck_face_master_quality"
        ),
    )

    employee: Mapped[Optional["EmployeeMaster"]] = relationship(
        "EmployeeMaster", back_populates="phase4_faces"
    )

    def __repr__(self) -> str:
        return f"<FaceMaster face_id={self.face_id} employee_id={self.employee_id!r}>"
