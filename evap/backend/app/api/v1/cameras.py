"""
Camera management API — uses camera_master table via CameraMaster model.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
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
        # Tells the frontend whether an RTSP URL is stored (never expose the URL itself)
        "has_rtsp_url": bool(cam.rtsp_url_encrypted),
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

    # ------------------------------------------------------------------ #
    # RTSP URL resolution (priority order):
    #   1. Explicit rtsp_url from the form → use as-is (user is responsible
    #      for encoding special chars like @ in the password as %40)
    #   2. ip + username + password → build URL with RFC-3986 percent-encoding
    #      so passwords like "nepal@123" become "nepal%40123" automatically
    #   3. ip only → bare rtsp://ip:554/stream
    # The result is always AES-encrypted before storage.
    # ------------------------------------------------------------------ #
    from urllib.parse import quote as _quote

    rtsp = getattr(body, 'rtsp_url', None) or ''
    username = getattr(body, 'username', None) or ''
    password = getattr(body, 'password', None) or ''
    ip = getattr(body, 'ip_address', None) or ''

    if rtsp.strip():
        data["rtsp_url_encrypted"] = encrypt_rtsp_url(rtsp.strip())
    elif ip:
        if username and password:
            # Percent-encode credentials so special chars (@ # : /) don't break the URL
            enc_user = _quote(username, safe='')
            enc_pass = _quote(password, safe='')
            built = f"rtsp://{enc_user}:{enc_pass}@{ip}:554/stream"
        elif username:
            enc_user = _quote(username, safe='')
            built = f"rtsp://{enc_user}@{ip}:554/stream"
        else:
            built = f"rtsp://{ip}:554/stream"
        data["rtsp_url_encrypted"] = encrypt_rtsp_url(built)

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


# ---------------------------------------------------------------------------
# Health-check helpers
# ---------------------------------------------------------------------------
async def _tcp_ping(ip: str, port: int = 554, timeout: float = 3.0) -> bool:
    """Return True if a TCP connection to ip:port succeeds within timeout."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def _update_camera_status(camera_id: int, ip: str) -> dict:
    """Ping camera and write online/offline + heartbeat to DB."""
    reachable = await _tcp_ping(ip)
    new_status = "online" if reachable else "offline"
    async with AsyncSessionLocal() as db:
        cam = (await db.execute(
            select(CameraMaster).where(CameraMaster.camera_id == camera_id)
        )).scalar_one_or_none()
        if cam:
            cam.status = new_status
            cam.last_heartbeat = datetime.now(timezone.utc)
            await db.commit()
    return {"camera_id": camera_id, "status": new_status, "reachable": reachable}


@router.get("/{camera_id}/health")
async def check_camera_health(
    camera_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """Ping the camera's IP:554 and update status in DB. Returns immediately with result."""
    cam = (await db.execute(
        select(CameraMaster).where(CameraMaster.camera_id == camera_id)
    )).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not cam.ip_address:
        return {"camera_id": camera_id, "status": cam.status, "reachable": False, "error": "No IP configured"}

    result = await _update_camera_status(camera_id, str(cam.ip_address))
    return result


@router.post("/health-check-all", status_code=status.HTTP_202_ACCEPTED)
async def health_check_all(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """Ping all active cameras in background and update their status."""
    cams = (await db.execute(
        select(CameraMaster).where(CameraMaster.is_active == True, CameraMaster.ip_address.isnot(None))
    )).scalars().all()

    async def _check_all():
        tasks = [_update_camera_status(c.camera_id, str(c.ip_address)) for c in cams]
        await asyncio.gather(*tasks, return_exceptions=True)

    background_tasks.add_task(_check_all)
    return {"queued": len(cams), "message": "Health check started for all cameras"}


# ---------------------------------------------------------------------------
# RTSP connectivity test (diagnostic — does NOT stream, just checks open)
# ---------------------------------------------------------------------------
@router.get("/{camera_id}/rtsp-test")
async def rtsp_test(
    camera_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """Try to open the RTSP URL stored for this camera and report success/failure.
    Useful for diagnosing stream issues without reloading the full UI."""
    import cv2 as _cv2

    cam = (await db.execute(
        select(CameraMaster).where(CameraMaster.camera_id == camera_id)
    )).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    rtsp_url: Optional[str] = None
    if cam.rtsp_url_encrypted:
        try:
            from app.core.security import decrypt_rtsp_url
            rtsp_url = decrypt_rtsp_url(cam.rtsp_url_encrypted)
        except Exception:
            pass
    if not rtsp_url and cam.ip_address:
        rtsp_url = f"rtsp://{cam.ip_address}:554/stream"

    if not rtsp_url:
        return {"camera_id": camera_id, "success": False, "error": "No RTSP URL configured"}

    # Mask password in the returned URL for security
    import re as _re
    safe_url = _re.sub(r':[^:@]+@', ':***@', rtsp_url)

    loop = asyncio.get_event_loop()

    def _try_open():
        import os as _os
        _os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
        c = _cv2.VideoCapture(rtsp_url, _cv2.CAP_FFMPEG)
        opened = c.isOpened()
        c.release()
        return opened

    try:
        opened = await asyncio.wait_for(loop.run_in_executor(None, _try_open), timeout=8)
        return {
            "camera_id": camera_id,
            "success": opened,
            "rtsp_url_masked": safe_url,
            "has_rtsp_url": bool(cam.rtsp_url_encrypted),
            "error": None if opened else "cv2 could not open the RTSP stream — check credentials and stream path",
        }
    except asyncio.TimeoutError:
        return {
            "camera_id": camera_id,
            "success": False,
            "rtsp_url_masked": safe_url,
            "has_rtsp_url": bool(cam.rtsp_url_encrypted),
            "error": "Timed out after 8 s — camera unreachable or stream path incorrect",
        }


# ---------------------------------------------------------------------------
# MJPEG live stream proxy
# ---------------------------------------------------------------------------
@router.get("/{camera_id}/stream")
async def stream_camera(
    camera_id: int,
    token: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Proxy RTSP → MJPEG for browser display.

    The VideoCapture is opened BEFORE the StreamingResponse so that failures
    return a proper HTTP 503 (which triggers img.onError in the browser).
    All steps are logged to the evap.stream logger — visible in the backend
    console window started by start_evap.bat.
    """
    import logging
    import os
    import re
    import cv2 as _cv2
    from fastapi.responses import StreamingResponse

    log = logging.getLogger("evap.stream")

    cam = (await db.execute(
        select(CameraMaster).where(CameraMaster.camera_id == camera_id)
    )).scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    # ── Resolve RTSP URL ────────────────────────────────────────────────
    rtsp_url: Optional[str] = None
    if cam.rtsp_url_encrypted:
        try:
            from app.core.security import decrypt_rtsp_url
            rtsp_url = decrypt_rtsp_url(cam.rtsp_url_encrypted)
        except Exception as dec_err:
            log.error("[STREAM] cam=%d decryption failed: %s", camera_id, dec_err)

    if not rtsp_url and cam.ip_address:
        rtsp_url = f"rtsp://{cam.ip_address}:554/stream"
        log.warning("[STREAM] cam=%d no stored URL — using IP fallback: %s", camera_id, rtsp_url)

    if not rtsp_url:
        log.error("[STREAM] cam=%d no RTSP URL and no IP — aborting", camera_id)
        raise HTTPException(status_code=503, detail="No RTSP URL configured for this camera")

    # Mask password in all log output
    safe_url = re.sub(r'(rtsp://[^:]+:)[^@]+(@)', r'\1***\2', rtsp_url)
    log.info("[STREAM] cam=%d  url=%s  has_encrypted=%s",
             camera_id, safe_url, bool(cam.rtsp_url_encrypted))

    # ── Open VideoCapture BEFORE starting the response ───────────────────
    # This is critical: if we open inside the generator, a failure sends
    # HTTP 200 with an empty body and the browser never fires img.onError.
    loop = asyncio.get_event_loop()

    def _open_capture() -> _cv2.VideoCapture:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "rtsp_transport;tcp|stimeout;5000000"   # 5 s connect timeout (µs)
        )
        c = _cv2.VideoCapture(rtsp_url, _cv2.CAP_FFMPEG)
        c.set(_cv2.CAP_PROP_BUFFERSIZE, 1)
        return c

    try:
        cap = await asyncio.wait_for(
            loop.run_in_executor(None, _open_capture), timeout=12
        )
    except asyncio.TimeoutError:
        log.error("[STREAM] cam=%d TIMEOUT (>12 s) connecting to %s", camera_id, safe_url)
        raise HTTPException(
            status_code=503,
            detail=f"Timeout connecting to RTSP stream after 12 s — url={safe_url}",
        )
    except Exception as open_err:
        log.error("[STREAM] cam=%d OPEN EXCEPTION %s url=%s", camera_id, open_err, safe_url)
        raise HTTPException(status_code=503, detail=str(open_err))

    if not cap.isOpened():
        cap.release()
        log.error(
            "[STREAM] cam=%d cv2.VideoCapture.isOpened()=False url=%s  "
            "→ wrong credentials, unreachable host, or incorrect stream path",
            camera_id, safe_url,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Cannot open RTSP stream: {safe_url}  "
                f"Possible causes: wrong password, wrong stream path (/Streaming/Channels/102 "
                f"vs /stream1 etc.), or camera firewall blocking this server's IP."
            ),
        )

    log.info("[STREAM] cam=%d OPENED OK — starting MJPEG relay", camera_id)

    # ── Frame relay generator ────────────────────────────────────────────
    async def _mjpeg_generator():
        try:
            consecutive_failures = 0
            frame_count = 0
            # H.265/HEVC cameras drop the first ~3 frames while the decoder
            # initialises VPS/SPS/PPS — allow up to 20 before giving up.
            while consecutive_failures < 20:
                ret, frame = await loop.run_in_executor(None, cap.read)
                if not ret:
                    consecutive_failures += 1
                    if consecutive_failures == 1:
                        log.debug("[STREAM] cam=%d frame decode skip (HEVC init?)", camera_id)
                    await asyncio.sleep(0.05)
                    continue
                consecutive_failures = 0
                frame_count += 1
                if frame_count == 1:
                    log.info("[STREAM] cam=%d first frame OK shape=%s", camera_id, frame.shape)

                h, w = frame.shape[:2]
                if w > 1280:
                    scale = 1280 / w
                    frame = _cv2.resize(frame, (1280, int(h * scale)))
                _, buf = _cv2.imencode(".jpg", frame, [_cv2.IMWRITE_JPEG_QUALITY, 75])
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buf.tobytes()
                    + b"\r\n"
                )
                await asyncio.sleep(0.033)   # ~30 fps cap
        except Exception as stream_err:
            log.error("[STREAM] cam=%d stream error after %d frames: %s",
                      camera_id, frame_count, stream_err)
        finally:
            cap.release()
            log.info("[STREAM] cam=%d VideoCapture released", camera_id)

    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
