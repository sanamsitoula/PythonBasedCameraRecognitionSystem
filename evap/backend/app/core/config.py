from __future__ import annotations

from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Database / Cache / Queue
    # ------------------------------------------------------------------ #
    DATABASE_URL: str = "postgresql+asyncpg://evap:evap@localhost:5432/evap"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://evap:evap@localhost:5432/evap"
    REDIS_URL: str = "redis://localhost:6379/0"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    # ------------------------------------------------------------------ #
    # JWT / Auth
    # ------------------------------------------------------------------ #
    SECRET_KEY: str = "change-me-in-production-use-32-bytes-minimum"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ------------------------------------------------------------------ #
    # API
    # ------------------------------------------------------------------ #
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "EVAP - Enterprise Video Analytics Platform"
    VERSION: str = "4.0.0"
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # ------------------------------------------------------------------ #
    # SMTP
    # ------------------------------------------------------------------ #
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_TLS: bool = True
    EMAILS_FROM: str = "noreply@evap.local"

    # ------------------------------------------------------------------ #
    # SMS / WhatsApp
    # ------------------------------------------------------------------ #
    SMS_API_KEY: Optional[str] = None
    WHATSAPP_API_KEY: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Push notifications (Firebase)
    # ------------------------------------------------------------------ #
    FIREBASE_CREDENTIALS_PATH: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Encryption
    # ------------------------------------------------------------------ #
    ENCRYPTION_KEY: str = "zW3Xn9k2Lm8pQ4rT6vYhBgFdJcAeNsUi"  # 32-char Fernet key base

    # ------------------------------------------------------------------ #
    # Storage
    # ------------------------------------------------------------------ #
    SNAP_DIR: str = "/snapshots"
    REPORTS_DIR: str = "/reports"
    MAPS_DIR: str = "/maps"

    # ------------------------------------------------------------------ #
    # AI / Face
    # ------------------------------------------------------------------ #
    MAX_FACE_DISTANCE: float = 0.4
    GPU_ENABLED: bool = False
    FACE_DETECTION_MODEL: str = "hog"  # hog | cnn

    # ------------------------------------------------------------------ #
    # Observability
    # ------------------------------------------------------------------ #
    PROMETHEUS_PORT: int = 9090

    # ------------------------------------------------------------------ #
    # MFA
    # ------------------------------------------------------------------ #
    MFA_ISSUER: str = "EVAP"

    # ------------------------------------------------------------------ #
    # ERP
    # ------------------------------------------------------------------ #
    ERP_SYNC_TIMEOUT_SECONDS: int = 30


settings = Settings()
