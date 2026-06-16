"""
main.py – CCTV Analytics Phase 1 entry point.

Flow:
    1. Load config
    2. Setup logging
    3. Run camera pre-flight verification
    4. Load YOLO model
    5. Start RTSP capture thread
    6. Start health monitor
    7. Start Rich dashboard
    8. Main loop: read → detect → update dashboard → snapshot
    9. Graceful shutdown on Ctrl-C or unrecoverable failure
"""

import logging
import signal
import sys
import time

from config_manager import load_config
from logger import setup_logging, get_camera_logger
from camera_verifier import verify_camera
from rtsp_capture import RTSPCapture
from detection import YOLODetector
from snapshot_manager import (
    save_detection_snapshot,
    save_error_snapshot,
    save_reconnect_snapshot,
)
from health_monitor import HealthMonitor
from ai_analyst import AiAnalyst
from dashboard import (
    Dashboard,
    DashboardState,
    update_camera,
    update_stream_info,
    update_detection,
    update_system,
    update_reconnect,
    update_error,
    update_frame_failures,
    update_ai_insight,
    append_log,
    print_verification_result,
)

# ─────────────────────────── globals ────────────────────────────────────────

_shutdown = False
_reconnect_count = 0
_last_frame = None          # kept for error snapshots


def _handle_signal(signum, frame):
    global _shutdown
    _shutdown = True


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ─────────────────────────── callbacks ──────────────────────────────────────

def _on_reconnect():
    global _reconnect_count, _last_frame
    _reconnect_count += 1
    update_reconnect(_reconnect_count)
    msg = f"Camera reconnected (attempt #{_reconnect_count})"
    append_log(msg)
    log = logging.getLogger("camera")
    log.info(msg)
    if config.system.save_snapshots and config.system.snapshot_on_reconnect and _last_frame is not None:
        save_reconnect_snapshot(_last_frame)


def _on_failure():
    global _shutdown
    msg = "RTSP reconnection failed – all attempts exhausted. Shutting down."
    update_error(msg)
    append_log(msg)
    logging.getLogger("camera").critical(msg)
    _shutdown = True


# ─────────────────────────── main ───────────────────────────────────────────

def main() -> None:
    global config, _last_frame

    # ── 1. Config ─────────────────────────────────────────────────────────
    try:
        config = load_config()
    except FileNotFoundError as exc:
        print(f"[FATAL] {exc}")
        sys.exit(1)

    # ── 2. Logging ────────────────────────────────────────────────────────
    setup_logging(config.system.log_level)
    cam_log = get_camera_logger()
    log = logging.getLogger(__name__)
    log.info("CCTV Analytics Phase 1 starting…")

    # ── 3. Camera verification ────────────────────────────────────────────
    print("\nRunning camera pre-flight verification…\n")
    result = verify_camera(config)
    print_verification_result(result, config)

    if not result.success:
        print("\n[FATAL] Camera verification failed. Please fix the issues above and retry.\n")
        sys.exit(1)

    print("\nVerification passed. Loading YOLO model…\n")
    time.sleep(1)

    # ── 4. YOLO ───────────────────────────────────────────────────────────
    try:
        detector = YOLODetector(
            model_path=config.yolo.model,
            confidence=config.yolo.confidence,
            iou=config.yolo.iou_threshold,
            device=config.yolo.device,
        )
    except Exception as exc:
        log.critical("Could not load YOLO model: %s", exc)
        print(f"\n[FATAL] YOLO model load failed: {exc}\n")
        sys.exit(1)

    # ── 5. RTSP capture ───────────────────────────────────────────────────
    capture = RTSPCapture(config, on_reconnect=_on_reconnect, on_failure=_on_failure)
    if not capture.start():
        log.critical("Failed to start RTSP capture.")
        print("\n[FATAL] Could not start RTSP stream capture.\n")
        sys.exit(1)

    # ── 6. Health monitor ─────────────────────────────────────────────────
    health = HealthMonitor(config)
    health.start()

    # ── 6b. AI analyst ────────────────────────────────────────────────────
    analyst: AiAnalyst | None = None
    if config.ai.enabled:
        if not config.ai.api_key:
            log.warning("AI analyst enabled but no API key set – skipping.")
        else:
            analyst = AiAnalyst(
                api_key=config.ai.api_key,
                model=config.ai.model,
                interval=config.ai.interval_seconds,
                base_url=config.ai.base_url,
            )
            analyst.start()
            append_log("AI analyst started")

    # ── 7. Dashboard ──────────────────────────────────────────────────────
    dashboard = Dashboard(config)
    update_camera(config.camera.ip, "Connected", "Active")
    update_stream_info(
        resolution=f"{result.width}x{result.height}",
        fps=result.fps,
        codec=result.codec,
    )
    update_system(0.0, 0.0, detector.device_label)
    append_log("System started")
    dashboard.start()

    # Track last detection snapshot time to avoid spamming
    _last_det_snapshot: float = 0.0
    _DET_SNAPSHOT_INTERVAL = 10.0   # seconds between detection snapshots

    # ── 8. Main loop ──────────────────────────────────────────────────────
    try:
        while not _shutdown:
            frame = capture.read()

            if frame is None:
                time.sleep(0.005)
                dashboard.tick()
                # Keep system health updated even with no frame
                update_system(health.cpu_pct, health.ram_gb, detector.device_label)
                continue

            _last_frame = frame

            # Detection
            det = detector.detect(frame)

            # Feed AI analyst
            if analyst is not None:
                analyst.push(det)
                update_ai_insight(analyst.insight)

            # Snapshots
            now = time.monotonic()
            if (
                config.system.save_snapshots
                and config.system.snapshot_on_detection
                and det.has_detection
                and (now - _last_det_snapshot) >= _DET_SNAPSHOT_INTERVAL
            ):
                save_detection_snapshot(frame)
                _last_det_snapshot = now

            # Dashboard updates
            update_detection(det, capture.actual_fps)
            update_system(health.cpu_pct, health.ram_gb, detector.device_label)
            update_camera(
                config.camera.ip,
                "Connected" if capture.is_connected else "Reconnecting…",
                "Active"    if capture.is_connected else "Interrupted",
            )

            dashboard.tick()
            time.sleep(0.001)   # yield to other threads

    except Exception as exc:
        log.exception("Unhandled exception in main loop: %s", exc)
        if config.system.save_snapshots and config.system.snapshot_on_error:
            save_error_snapshot(_last_frame)

    finally:
        # ── 9. Shutdown ───────────────────────────────────────────────────
        log.info("Shutting down…")
        dashboard.stop()
        capture.stop()
        health.stop()
        if analyst is not None:
            analyst.stop()
        print("\n[CCTV Phase 1] Shutdown complete.\n")


if __name__ == "__main__":
    main()
