from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.core.security import decrypt_rtsp_url, encrypt_rtsp_url
from app.models import Camera, Detection, StreamHealth

router = APIRouter(prefix="/cameras", tags=["cameras"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CameraCreate(BaseModel):
    site_id: str
    floor_id: Optional[str] = None
    zone_id: Optional[str] = None
    name: str
    rtsp_url: str  # plaintext — encrypted on write
    camera_type: str = "fixed"
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    ai_processing_enabled: bool = True
    face_detection: bool = True
    lpr_enabled: bool = False
    crowd_detection: bool = True
    behavior_detection: bool = True


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    floor_id: Optional[str] = None
    zone_id: Optional[str] = None
    camera_type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    ip_address: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    rtsp_url: Optional[str] = None


class CameraOut(BaseModel):
    id: str
    site_id: str
    floor_id: Optional[str]
    zone_id: Optional[str]
    name: str
    camera_type: str
    manufacturer: Optional[str]
    model: Optional[str]
    ip_address: Optional[str]
    resolution: Optional[str]
    fps: Optional[int]
    status: str
    ai_processing_enabled: bool
    face_detection: bool
    lpr_enabled: bool
    crowd_detection: bool
    behavior_detection: bool
    is_active: bool
    last_seen: Optional[datetime]

    class Config:
        from_attributes = True


class StreamHealthOut(BaseModel):
    camera_id: str
    fps_actual: Optional[float]
    bitrate_kbps: Optional[int]
    frame_drops: int
    latency_ms: Optional[int]
    status: str
    error_message: Optional[str]
    recorded_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
async def register_camera(
    body: CameraCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    data = body.model_dump(exclude={"rtsp_url"})
    data["rtsp_url_encrypted"] = encrypt_rtsp_url(body.rtsp_url)
    camera = Camera(**data)
    db.add(camera)
    await db.commit()
    await db.refresh(camera)
    return camera


@router.get("", response_model=dict)
async def list_cameras(
    site_id: Optional[str] = Query(None),
    floor_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(Camera)
    if site_id:
        q = q.where(Camera.site_id == site_id)
    if floor_id:
        q = q.where(Camera.floor_id == floor_id)
    if zone_id:
        q = q.where(Camera.zone_id == zone_id)
    if status:
        q = q.where(Camera.status == status)
    if is_active is not None:
        q = q.where(Camera.is_active == is_active)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {"items": [CameraOut.model_validate(c) for c in items], "total": total}


@router.get("/{camera_id}", response_model=CameraOut)
async def get_camera(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cam = (await db.execute(select(Camera).where(Camera.id == camera_id))).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    return cam


@router.put("/{camera_id}", response_model=CameraOut)
async def update_camera(
    camera_id: str,
    body: CameraUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cam = (await db.execute(select(Camera).where(Camera.id == camera_id))).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    updates = body.model_dump(exclude_none=True)
    if "rtsp_url" in updates:
        cam.rtsp_url_encrypted = encrypt_rtsp_url(updates.pop("rtsp_url"))
    for field, value in updates.items():
        setattr(cam, field, value)

    await db.commit()
    await db.refresh(cam)
    return cam


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cam = (await db.execute(select(Camera).where(Camera.id == camera_id))).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    cam.is_active = False
    await db.commit()


@router.post("/{camera_id}/test")
async def test_camera(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cam = (await db.execute(select(Camera).where(Camera.id == camera_id))).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    rtsp_url = decrypt_rtsp_url(cam.rtsp_url_encrypted)
    # In production, attempt OpenCV/GStreamer connection test here.
    # We mark the camera as online and update last_seen optimistically.
    cam.status = "online"
    cam.last_seen = datetime.now(timezone.utc)
    await db.commit()
    return {"camera_id": camera_id, "rtsp_url_prefix": rtsp_url[:20] + "...", "status": "online"}


@router.get("/{camera_id}/stream-health", response_model=dict)
async def stream_health(
    camera_id: str,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    items = (
        await db.execute(
            select(StreamHealth)
            .where(StreamHealth.camera_id == camera_id)
            .order_by(StreamHealth.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {"items": [StreamHealthOut.model_validate(s) for s in items], "total": len(items)}


@router.get("/{camera_id}/snapshots", response_model=dict)
async def camera_snapshots(
    camera_id: str,
    detection_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    q = select(Detection).where(
        Detection.camera_id == camera_id,
        Detection.snapshot_path.isnot(None),
    )
    if detection_type:
        q = q.where(Detection.detection_type == detection_type)
    q = q.order_by(Detection.detected_at.desc())

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return {
        "items": [
            {
                "id": d.id,
                "detection_type": d.detection_type,
                "snapshot_path": d.snapshot_path,
                "confidence": d.confidence,
                "detected_at": d.detected_at,
            }
            for d in items
        ],
        "total": total,
    }


@router.put("/{camera_id}/toggle", response_model=CameraOut)
async def toggle_ai_processing(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    cam = (await db.execute(select(Camera).where(Camera.id == camera_id))).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    cam.ai_processing_enabled = not cam.ai_processing_enabled
    await db.commit()
    await db.refresh(cam)
    return cam
