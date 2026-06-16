"""Camera CRUD and stream health service."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.camera import (
    CameraCreate,
    CameraResponse,
    CameraStatusSummary,
    CameraStreamStats,
    CameraUpdate,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------
# The Fernet key is read from the application settings at startup.
# Importing here to allow lazy init via _get_fernet().
_fernet_instance: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        try:
            from ..core.config import settings  # type: ignore[import]
            _fernet_instance = Fernet(settings.FERNET_KEY.encode())
        except Exception:
            # Fallback: generate ephemeral key (dev only)
            key = Fernet.generate_key()
            logger.warning("FERNET_KEY not configured – using ephemeral key (dev only)")
            _fernet_instance = Fernet(key)
    return _fernet_instance


def encrypt_rtsp(url: str) -> str:
    return _get_fernet().encrypt(url.encode()).decode()


def decrypt_rtsp(token: str) -> str:
    return _get_fernet().decrypt(token.encode()).decode()


# ---------------------------------------------------------------------------
# DB model helpers  (duck-typed – SQLAlchemy ORM models expected)
# ---------------------------------------------------------------------------

def _row_to_response(row) -> CameraResponse:
    return CameraResponse.model_validate(row, from_attributes=True)


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

async def create_camera(db: AsyncSession, data: CameraCreate) -> CameraResponse:
    """Encrypt RTSP URL and persist camera record."""
    from ..models.camera import CameraMaster  # local import avoids circular dep

    encrypted_url = encrypt_rtsp(data.rtsp_url)
    camera = CameraMaster(
        name=data.name,
        site_id=data.site_id,
        rtsp_url_encrypted=encrypted_url,
        camera_type=data.camera_type,
        resolution=data.resolution,
        fps=data.fps,
        location_x=data.location_x,
        location_y=data.location_y,
        direction_degrees=data.direction_degrees,
        floor_id=data.floor_id,
        zone_id=data.zone_id,
        ip_address=data.ip_address,
        manufacturer=data.manufacturer,
        model=data.model,
        ai_enabled=data.ai_enabled,
        status="offline",
    )
    db.add(camera)
    await db.commit()
    await db.refresh(camera)
    logger.info("Created camera id=%s name=%s", camera.camera_id, camera.name)
    return _row_to_response(camera)


async def get_cameras(
    db: AsyncSession,
    site_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[CameraResponse]:
    from ..models.camera import CameraMaster

    stmt = select(CameraMaster).where(CameraMaster.is_active == True)
    if site_id is not None:
        stmt = stmt.where(CameraMaster.site_id == site_id)
    if status is not None:
        stmt = stmt.where(CameraMaster.status == status)
    stmt = stmt.offset(skip).limit(limit)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_row_to_response(r) for r in rows]


async def get_camera(db: AsyncSession, camera_id: int) -> Optional[CameraResponse]:
    from ..models.camera import CameraMaster

    stmt = select(CameraMaster).where(CameraMaster.camera_id == camera_id)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return None
    response = _row_to_response(row)
    response.stream_stats = await get_stream_health(db, camera_id)
    return response


async def update_camera(
    db: AsyncSession, camera_id: int, data: CameraUpdate
) -> Optional[CameraResponse]:
    from ..models.camera import CameraMaster

    stmt = select(CameraMaster).where(CameraMaster.camera_id == camera_id)
    result = await db.execute(stmt)
    camera = result.scalar_one_or_none()
    if camera is None:
        return None

    update_dict = data.model_dump(exclude_none=True)
    if "rtsp_url" in update_dict:
        update_dict["rtsp_url_encrypted"] = encrypt_rtsp(update_dict.pop("rtsp_url"))

    for key, value in update_dict.items():
        setattr(camera, key, value)

    await db.commit()
    await db.refresh(camera)
    logger.info("Updated camera id=%s", camera_id)
    return _row_to_response(camera)


async def delete_camera(db: AsyncSession, camera_id: int) -> bool:
    """Soft-delete: set is_active=False."""
    from ..models.camera import CameraMaster

    stmt = (
        update(CameraMaster)
        .where(CameraMaster.camera_id == camera_id)
        .values(is_active=False, status="offline")
    )
    result = await db.execute(stmt)
    await db.commit()
    deleted = result.rowcount > 0
    if deleted:
        logger.info("Soft-deleted camera id=%s", camera_id)
    return deleted


async def test_rtsp_connection(camera_id: int, rtsp_url: str) -> dict:
    """
    Attempt to open an RTSP stream via OpenCV and return connectivity result.
    Runs synchronously in a thread pool since cv2 is blocking.
    """
    import asyncio

    def _attempt(url: str) -> dict:
        try:
            import cv2  # type: ignore[import]
        except ImportError:
            return {"success": False, "error": "OpenCV not installed", "camera_id": camera_id}

        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            cap.release()
            return {"success": False, "error": "Cannot open stream", "camera_id": camera_id}
        ret, _ = cap.read()
        cap.release()
        if not ret:
            return {"success": False, "error": "Stream opened but no frames", "camera_id": camera_id}
        return {"success": True, "camera_id": camera_id}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _attempt, rtsp_url)


async def update_heartbeat(db: AsyncSession, camera_id: int) -> None:
    from ..models.camera import CameraMaster

    stmt = (
        update(CameraMaster)
        .where(CameraMaster.camera_id == camera_id)
        .values(last_heartbeat=datetime.now(timezone.utc), status="online")
    )
    await db.execute(stmt)
    await db.commit()


async def get_stream_health(
    db: AsyncSession, camera_id: int
) -> Optional[CameraStreamStats]:
    from ..models.camera import CameraStream

    stmt = (
        select(CameraStream)
        .where(CameraStream.camera_id == camera_id)
        .order_by(CameraStream.started_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return CameraStreamStats.model_validate(row, from_attributes=True)


async def get_status_summary(db: AsyncSession, site_id: Optional[int] = None) -> CameraStatusSummary:
    from sqlalchemy import func
    from ..models.camera import CameraMaster

    stmt = select(CameraMaster.status, func.count().label("cnt")).where(CameraMaster.is_active == True)
    if site_id:
        stmt = stmt.where(CameraMaster.site_id == site_id)
    stmt = stmt.group_by(CameraMaster.status)

    result = await db.execute(stmt)
    rows = result.all()
    counts: dict = {r.status: r.cnt for r in rows}
    total = sum(counts.values())
    return CameraStatusSummary(
        total=total,
        active=counts.get("online", 0),
        offline=counts.get("offline", 0),
        error=counts.get("error", 0),
        maintenance=counts.get("maintenance", 0),
    )
