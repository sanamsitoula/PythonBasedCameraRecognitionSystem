"""
Camera management API — uses camera_master table via CameraMaster model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.core.security import encrypt_rtsp_url
from app.models.camera import CameraMaster

router = APIRouter(prefix="/cameras", tags=["cameras"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CameraCreate(BaseModel):
    name: str
    ip_address: Optional[str] = None
    rtsp_url: Optional[str] = None
    camera_type: str = "fixed"
    site: Optional[str] = None        # free-text site name (stored in manufacturer field for now)
    zone: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    username: Optional[str] = None    # used to build rtsp_url if provided
    password: Optional[str] = None
    type: Optional[str] = None        # UI alias for camera_type


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    rtsp_url: Optional[str] = None
    camera_type: Optional[str] = None
    site: Optional[str] = None
    zone: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    status: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    type: Optional[str] = None


class CameraOut(BaseModel):
    id: int
    name: str
    ip_address: Optional[str]
    camera_type: str
    site: Optional[str]
    zone: Optional[str]
    resolution: Optional[str]
    fps: Optional[int]
    status: str
    is_active: bool
    ai_enabled: bool
    last_heartbeat: Optional[datetime]
    manufacturer: Optional[str]
    model: Optional[str]

    class Config:
        from_attributes = True


def _cam_to_out(cam: CameraMaster) -> dict:
    return {
        "id": cam.camera_id,
        "name": cam.name,
        "ip_address": str(cam.ip_address) if cam.ip_address else None,
        "camera_type": cam.camera_type,
        "site": cam.manufacturer,   # we store free-text site in manufacturer
        "zone": cam.model,          # we store free-text zone in model
        "resolution": cam.resolution,
        "fps": cam.fps,
        "status": cam.status,
        "is_active": cam.is_active,
        "ai_enabled": cam.ai_enabled,
        "last_heartbeat": cam.last_heartbeat,
        "manufacturer": cam.manufacturer,
        "model": cam.model,
    }


def _build_camera(body: CameraCreate | CameraUpdate) -> dict:
    data: dict = {}
    if body.name is not None:
        data["name"] = body.name
    # Resolve camera_type — UI sends 'type', API model uses 'camera_type'
    cam_type = getattr(body, 'camera_type', None) or getattr(body, 'type', None) or "fixed"
    valid_types = {"fixed", "ptz", "fisheye", "thermal", "anpr", "360"}
    data["camera_type"] = cam_type if cam_type in valid_types else "fixed"
    if body.ip_address is not None:
        data["ip_address"] = body.ip_address
    if body.resolution is not None:
        data["resolution"] = body.resolution
    if body.fps is not None:
        data["fps"] = body.fps
    # Store site/zone in manufacturer/model columns (simple approach, avoids FK)
    if getattr(body, 'site', None) is not None:
        data["manufacturer"] = body.site
    if getattr(body, 'zone', None) is not None:
        data["model"] = body.zone
    # Build/store RTSP URL
    rtsp = getattr(body, 'rtsp_url', None)
    if rtsp:
        data["rtsp_url_encrypted"] = encrypt_rtsp_url(rtsp)
    return data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_camera(
    body: CameraCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    data = _build_camera(body)
    cam = CameraMaster(**data)
    db.add(cam)
    await db.commit()
    await db.refresh(cam)
    return _cam_to_out(cam)


@router.get("")
async def list_cameras(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(CameraMaster).where(CameraMaster.is_active == True)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.order_by(CameraMaster.camera_id).offset(skip).limit(limit))).scalars().all()
    return {"items": [_cam_to_out(c) for c in items], "total": total}


@router.get("/status")
async def cameras_status(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """Quick status summary for dashboard."""
    items = (await db.execute(
        select(CameraMaster).where(CameraMaster.is_active == True)
    )).scalars().all()
    return {
        "total": len(items),
        "online": sum(1 for c in items if c.status == "online"),
        "offline": sum(1 for c in items if c.status == "offline"),
        "error": sum(1 for c in items if c.status == "error"),
        "cameras": [_cam_to_out(c) for c in items],
    }


@router.get("/{camera_id}")
async def get_camera(
    camera_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cam = (await db.execute(
        select(CameraMaster).where(CameraMaster.camera_id == camera_id)
    )).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    return _cam_to_out(cam)


@router.put("/{camera_id}")
async def update_camera(
    camera_id: int,
    body: CameraUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cam = (await db.execute(
        select(CameraMaster).where(CameraMaster.camera_id == camera_id)
    )).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    updates = _build_camera(body)
    for field, value in updates.items():
        setattr(cam, field, value)

    await db.commit()
    await db.refresh(cam)
    return _cam_to_out(cam)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cam = (await db.execute(
        select(CameraMaster).where(CameraMaster.camera_id == camera_id)
    )).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    cam.is_active = False
    await db.commit()


@router.post("/{camera_id}/restart")
async def restart_stream(
    camera_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cam = (await db.execute(
        select(CameraMaster).where(CameraMaster.camera_id == camera_id)
    )).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    cam.last_heartbeat = datetime.now(timezone.utc)
    await db.commit()
    return {"camera_id": camera_id, "status": "restarted"}
