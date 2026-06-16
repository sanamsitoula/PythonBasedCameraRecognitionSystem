"""
User, Role, and ApiKey models for EVAP RBAC and authentication.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .system import ApiLog, AuditLog
    from .alert import AlertLog
    from .system import Report


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="role_obj")

    def __repr__(self) -> str:
        return f"<Role name={self.name!r}>"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("roles.name", onupdate="CASCADE"),
        nullable=False,
        default="viewer",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    role_obj: Mapped["Role"] = relationship("Role", back_populates="users")
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey", back_populates="user", cascade="all, delete-orphan"
    )
    api_logs: Mapped[list["ApiLog"]] = relationship("ApiLog", back_populates="user")
    acknowledged_alerts: Mapped[list["AlertLog"]] = relationship(
        "AlertLog", back_populates="acknowledger"
    )
    watchlist_entries: Mapped[list["Watchlist"]] = relationship(  # type: ignore[name-defined]
        "Watchlist", back_populates="adder"
    )
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="generator")

    def __repr__(self) -> str:
        return f"<User username={self.username!r} role={self.role!r}>"


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")
    api_logs: Mapped[list["ApiLog"]] = relationship(
        "ApiLog", back_populates="api_key"
    )

    def __repr__(self) -> str:
        return f"<ApiKey id={self.id} name={self.name!r} user_id={self.user_id}>"


# Avoid circular import – import here after all classes are defined
from .alert import Watchlist  # noqa: E402, F401
