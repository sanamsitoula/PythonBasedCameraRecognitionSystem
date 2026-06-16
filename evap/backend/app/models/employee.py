"""
Employee models — wraps Phase 3 tables plus Phase 4 FaceMaster extension.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, FLOAT as PG_FLOAT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .attendance import AttendanceLog, EmployeeZoneHistory, MovementHistory


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 tables (reflected; defined here for relationship wiring)
# ─────────────────────────────────────────────────────────────────────────────

class EmployeeMaster(Base):
    """Reflects the Phase 3 employee_master table."""
    __tablename__ = "employee_master"

    employee_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    designation: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
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
    movement_histories: Mapped[list["MovementHistory"]] = relationship(
        "MovementHistory", back_populates="employee"
    )

    def __repr__(self) -> str:
        return f"<EmployeeMaster employee_id={self.employee_id} code={self.employee_code!r}>"


class EmployeeFaceMaster(Base):
    """Reflects the Phase 3 employee_face_master table."""
    __tablename__ = "employee_face_master"

    face_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employee_master.employee_id", ondelete="CASCADE"),
        nullable=False,
    )
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quality_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    employee: Mapped["EmployeeMaster"] = relationship(
        "EmployeeMaster", back_populates="face_masters"
    )
    embeddings: Mapped[list["FaceEmbedding"]] = relationship(
        "FaceEmbedding", back_populates="face_master_obj", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<EmployeeFaceMaster face_id={self.face_id} employee_id={self.employee_id}>"


class FaceEmbedding(Base):
    """Reflects the Phase 3 face_embeddings table."""
    __tablename__ = "face_embeddings"

    embedding_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    face_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employee_face_master.face_id", ondelete="CASCADE"),
        nullable=False,
    )
    # pgvector stores as vector(512) — use ARRAY(FLOAT) as fallback
    embedding: Mapped[Optional[list]] = mapped_column(
        ARRAY(PG_FLOAT), nullable=True
    )
    model_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    face_master_obj: Mapped["EmployeeFaceMaster"] = relationship(
        "EmployeeFaceMaster", back_populates="embeddings"
    )

    def __repr__(self) -> str:
        return f"<FaceEmbedding embedding_id={self.embedding_id} face_id={self.face_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 extension
# ─────────────────────────────────────────────────────────────────────────────

class FaceMaster(Base):
    """Phase 4 extended face records."""
    __tablename__ = "face_master"

    face_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[Optional[int]] = mapped_column(
        Integer,
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

    # Relationships
    employee: Mapped[Optional["EmployeeMaster"]] = relationship(
        "EmployeeMaster", back_populates="phase4_faces"
    )

    def __repr__(self) -> str:
        return f"<FaceMaster face_id={self.face_id} employee_id={self.employee_id}>"
