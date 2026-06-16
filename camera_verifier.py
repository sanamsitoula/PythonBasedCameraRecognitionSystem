"""
camera_verifier.py – Pre-flight checks before stream capture begins.

Steps performed:
    1. ICMP ping to camera IP
    2. TCP socket probe on RTSP port 554
    3. RTSP URL authentication test (cv2.VideoCapture probe)
    4. First-frame read + resolution / FPS extraction
"""

import logging
import platform
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

import cv2

from config_manager import AppConfig

log = logging.getLogger("camera")


@dataclass
class VerificationResult:
    success: bool
    ip_reachable: bool = False
    port_open: bool = False
    auth_ok: bool = False
    stream_ok: bool = False
    width: int = 0
    height: int = 0
    fps: float = 0.0
    codec: str = ""
    error_message: str = ""


def _ping(ip: str, timeout: int = 2) -> bool:
    """Returns True if the host responds to ICMP ping."""
    param = "-n" if platform.system().lower() == "windows" else "-c"
    cmd = ["ping", param, "1", "-w" if platform.system().lower() == "windows" else "-W",
           str(timeout * 1000 if platform.system().lower() == "windows" else timeout), ip]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout + 2)
        return result.returncode == 0
    except Exception as exc:
        log.debug("Ping failed: %s", exc)
        return False


def _tcp_probe(ip: str, port: int, timeout: int = 3) -> bool:
    """Returns True if a TCP connection to ip:port succeeds."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _rtsp_probe(rtsp_url: str, timeout_sec: int = 10) -> tuple[bool, bool, int, int, float, str]:
    """
    Attempts to open the RTSP stream.
    Returns (auth_ok, stream_ok, width, height, fps, codec).
    """
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_sec * 1000)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_sec * 1000)

    if not cap.isOpened():
        cap.release()
        return False, False, 0, 0, 0.0, ""

    # Try reading a frame to confirm stream is live
    deadline = time.time() + timeout_sec
    frame_ok = False
    while time.time() < deadline:
        ret, frame = cap.read()
        if ret and frame is not None:
            frame_ok = True
            break
        time.sleep(0.1)

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 0.0
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    codec  = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)]).strip("\x00") or "H264"

    cap.release()
    return True, frame_ok, width, height, fps, codec


def verify_camera(config: AppConfig) -> VerificationResult:
    """
    Run all pre-flight checks. Returns a VerificationResult.
    Logs every step to the camera logger.
    """
    cam = config.camera
    result = VerificationResult(success=False)

    log.info("=== Camera Verification Started ===")
    log.info("Target IP: %s", cam.ip)

    # ── 1. Ping ──────────────────────────────────────────────────────────────
    log.info("Step 1/4 – ICMP ping to %s", cam.ip)
    result.ip_reachable = _ping(cam.ip)
    if not result.ip_reachable:
        result.error_message = f"Camera IP {cam.ip} is not reachable (ping failed). " \
                               "Check network cable / switch / IP address."
        log.error(result.error_message)
        return result
    log.info("Ping OK")

    # ── 2. TCP port probe ────────────────────────────────────────────────────
    log.info("Step 2/4 – TCP probe on port %d", cam.rtsp_port)
    result.port_open = _tcp_probe(cam.ip, cam.rtsp_port)
    if not result.port_open:
        result.error_message = f"RTSP port {cam.rtsp_port} on {cam.ip} is closed. " \
                               "Ensure RTSP is enabled in camera settings."
        log.error(result.error_message)
        return result
    log.info("RTSP port %d is open", cam.rtsp_port)

    # ── 3 & 4. RTSP authentication + stream probe ────────────────────────────
    log.info("Step 3/4 – RTSP authentication check")
    log.info("Step 4/4 – Stream frame verification")
    auth_ok, stream_ok, w, h, fps, codec = _rtsp_probe(cam.rtsp_url)

    result.auth_ok   = auth_ok
    result.stream_ok = stream_ok
    result.width     = w
    result.height    = h
    result.fps       = round(fps, 1)
    result.codec     = codec

    if not auth_ok:
        result.error_message = (
            "RTSP connection failed. Possible causes:\n"
            "  • 401 Unauthorized – wrong username or password\n"
            "  • 403 Forbidden    – account lacks RTSP access\n"
            "  • 404 Not Found    – wrong stream path in rtsp_url\n"
            "  • Timeout          – camera not responding on RTSP\n"
            f"  RTSP URL used: {cam.rtsp_url}"
        )
        log.error(result.error_message)
        return result

    if not stream_ok:
        result.error_message = "RTSP connected but no frames received. " \
                               "Stream may be initialising – retry in a few seconds."
        log.error(result.error_message)
        return result

    result.success = True
    log.info(
        "Camera verification PASSED | %dx%d @ %.1f fps | Codec: %s",
        w, h, fps, codec,
    )
    return result
