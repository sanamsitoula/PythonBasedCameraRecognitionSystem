"""
phase2_main.py – CCTV Analytics Phase 2 entry point.

Complete flow:
  1.  Load config (all Phase 1 + Phase 2 sections)
  2.  Setup logging (Phase 1 handlers + Phase 2 category logs)
  3.  Camera pre-flight verification
  4.  Initialise ByteTracker (replaces Phase 1 YOLODetector)
  5.  Initialise GenderClassifier
  6.  Initialise DirectionDetector
  7.  Initialise LineCounter
  8.  Initialise ZoneManager
  9.  Initialise OccupancyEngine
  10. Initialise VehicleAnalytics
  11. Initialise DatabaseManager + DbWriter (if enabled)
  12. Initialise AiAnalyst (optional)
  13. Start RTSPCapture
  14. Start HealthMonitor
  15. Start Phase2Dashboard
  16. Main loop
  17. Graceful shutdown
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Optional

# Suppress FFmpeg/OpenCV HEVC codec noise (VPS/SPS warnings are cosmetic).
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

from config_manager import load_config
from logger import setup_logging, setup_phase2_loggers, get_camera_logger
from camera_verifier import verify_camera
from rtsp_capture import RTSPCapture
from health_monitor import HealthMonitor
from ai_analyst import AiAnalyst

from tracker import ByteTracker
from gender_classifier import GenderClassifier
from direction_detector import DirectionDetector
from line_counter import LineCounter
from zone_manager import ZoneManager
from occupancy_engine import OccupancyEngine
from vehicle_analytics import VehicleAnalytics
from db_manager import DatabaseManager
from db_writer import DbWriter
from snapshot_manager_v2 import (
    save_person_snapshot,
    save_vehicle_snapshot,
    save_entry_snapshot,
    save_exit_snapshot,
    save_gender_snapshot,
)

import analytics_state as astate
from phase2_dashboard import Phase2Dashboard, set_camera_info, print_preflight

log = logging.getLogger(__name__)

# ─────────────────────────── shutdown flag ───────────────────────────────────

_shutdown        = False
_reconnect_count = 0
config           = None     # set in main()


def _handle_signal(signum, frame):
    global _shutdown
    _shutdown = True


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ─────────────────────────── snapshot throttle helpers ───────────────────────

_PERSON_SNAP_INTERVAL   = 15.0   # seconds between person snapshots
_VEHICLE_SNAP_INTERVAL  = 10.0   # seconds between vehicle snapshots
_OCCUPANCY_SNAP_INTERVAL = 60.0  # seconds between occupancy DB writes
_HEALTH_SNAP_INTERVAL    = 30.0  # seconds between health DB writes
_ANALYTICS_DB_INTERVAL   = 60.0  # seconds between daily analytics DB writes

_last_person_snap   = 0.0
_last_vehicle_snap  = 0.0
_last_occupancy_db  = 0.0
_last_health_db     = 0.0
_last_analytics_db  = 0.0

# track_id → frame_number of last gender snapshot
_gender_snapped: dict = {}
# track_id → previous centroid for line_counter
_prev_centers:   dict = {}
# track_id → frame of last direction DB write
_direction_written: set = set()


# ─────────────────────────── main ────────────────────────────────────────────

def main() -> None:
    global config, _shutdown

    # ── 1. Config ────────────────────────────────────────────────────────────
    try:
        config = load_config()
    except FileNotFoundError as exc:
        print(f"[FATAL] {exc}")
        sys.exit(1)

    # ── 2. Logging ───────────────────────────────────────────────────────────
    setup_logging(config.system.log_level)
    setup_phase2_loggers()
    cam_log = get_camera_logger()
    log.info("CCTV Analytics Phase 2 starting…")

    # ── 3. Camera verification ────────────────────────────────────────────────
    print("\nRunning camera pre-flight verification…\n")
    verify_result = verify_camera(config)
    print_preflight(verify_result, config)

    if not verify_result.success:
        print("\n[FATAL] Camera verification failed. Fix the issues above and retry.\n")
        sys.exit(1)

    print("\nVerification passed. Loading ByteTrack model…\n")
    time.sleep(1)

    # ── 4. ByteTracker ────────────────────────────────────────────────────────
    try:
        tracker = ByteTracker(
            model_path  = config.yolo.model,
            confidence  = config.yolo.confidence,
            iou         = config.yolo.iou_threshold,
            device      = config.yolo.device,
            max_age     = config.tracking.max_age,
            min_hits    = config.tracking.min_hits,
        )
    except Exception as exc:
        log.critical("ByteTracker load failed: %s", exc)
        print(f"\n[FATAL] ByteTracker load failed: {exc}\n")
        sys.exit(1)

    # ── 5. Gender classifier ──────────────────────────────────────────────────
    gender_clf: Optional[GenderClassifier] = None
    if config.gender.enabled:
        gender_clf = GenderClassifier(
            backend              = config.gender.backend,
            confidence_threshold = config.gender.confidence_threshold,
            min_bbox_height      = config.gender.min_bbox_height,
            max_workers          = config.gender.max_workers,
        )

    # ── 6-8. Direction / line / zone engines ─────────────────────────────────
    direction_det = DirectionDetector()
    line_counter  = LineCounter(config.lines.lines)
    zone_mgr      = ZoneManager(config.zones.zones)

    # ── 9. Occupancy ──────────────────────────────────────────────────────────
    occupancy = OccupancyEngine(
        average_window_seconds = config.occupancy.average_window_seconds,
        reset_peak_daily       = config.occupancy.reset_peak_daily,
        alert_threshold        = config.occupancy.alert_threshold,
    )

    # ── 10. Vehicle analytics ─────────────────────────────────────────────────
    vehicle_anlt = VehicleAnalytics()

    # ── 11. Database ──────────────────────────────────────────────────────────
    db:          Optional[DatabaseManager] = None
    db_writer:   Optional[DbWriter]        = None
    session_id:  Optional[int]             = None
    camera_id:   Optional[int]             = None

    if config.database.enabled:
        db = DatabaseManager(
            host     = config.database.host,
            port     = config.database.port,
            dbname   = config.database.dbname,
            user     = config.database.user,
            password = config.database.password,
            pool_min = config.database.pool_min,
            pool_max = config.database.pool_max,
        )
        if db.is_available:
            camera_id  = db.ensure_camera(config.camera.ip, config.camera.rtsp_url)
            session_id = db.create_session(
                camera_id, config.yolo.model, tracker.device_label
            ) if camera_id else None
            db_writer = DbWriter(db, session_id, config.database.write_queue_max)
            db_writer.start()
            astate.update(db_available=True)
            log.info("Database session started: session_id=%s", session_id)
        else:
            log.warning("Database unavailable – running without persistence.")

    # ── 12. AI analyst ────────────────────────────────────────────────────────
    analyst: Optional[AiAnalyst] = None
    if config.ai.enabled:
        from config_manager import build_ai_providers
        _providers = build_ai_providers(config.ai)
        if _providers:
            analyst = AiAnalyst(providers=_providers, interval=config.ai.interval_seconds)
            analyst.start()
        else:
            log.warning("AI analyst disabled – no API keys configured in [AI] section.")

    # ── 13. RTSP capture ──────────────────────────────────────────────────────
    def _on_reconnect():
        global _reconnect_count
        _reconnect_count += 1
        msg = f"Camera reconnected (attempt #{_reconnect_count})"
        astate.append_log(msg)
        cam_log.info(msg)

    def _on_failure():
        global _shutdown
        msg = "RTSP reconnection exhausted – shutting down."
        astate.append_log(msg)
        cam_log.critical(msg)
        _shutdown = True

    capture = RTSPCapture(config, on_reconnect=_on_reconnect, on_failure=_on_failure)
    if not capture.start():
        log.critical("Failed to start RTSP capture.")
        print("\n[FATAL] Could not start RTSP stream capture.\n")
        sys.exit(1)

    # ── 14. Health monitor ────────────────────────────────────────────────────
    health = HealthMonitor(config)
    health.start()

    # ── 15. Dashboard ─────────────────────────────────────────────────────────
    dashboard = Phase2Dashboard(config)
    set_camera_info(
        ip         = config.camera.ip,
        status     = "Connected",
        rtsp       = "Active",
        resolution = f"{verify_result.width}x{verify_result.height}",
        fps        = verify_result.fps,
        codec      = verify_result.codec,
    )
    astate.append_log("Phase 2 started")
    dashboard.start()

    # ── 16. Main loop ─────────────────────────────────────────────────────────
    last_frame: Optional[object] = None
    try:
        while not _shutdown:
            frame = capture.read()
            now   = time.monotonic()

            if frame is None:
                occupancy.tick()
                dashboard.tick()
                astate.update(cpu_pct=health.cpu_pct, ram_gb=health.ram_gb,
                              device_label=tracker.device_label)
                time.sleep(0.005)
                continue

            last_frame = frame

            # ── ByteTrack ────────────────────────────────────────────────────
            try:
                tracking_frame = tracker.track(frame)
            except Exception as exc:
                import traceback as _tb
                err_msg = f"Tracker error: {exc}"
                log.error(err_msg)
                astate.update(
                    last_error=err_msg,
                    error_count=astate.get_state().error_count + 1,
                )
                astate.append_log(f"[ERROR] {err_msg[:55]}")
                if db_writer:
                    db_writer.put_error("ERROR", "tracker", str(exc), _tb.format_exc())
                continue
            fn = tracking_frame.frame_number

            # periodic debug: log raw detection count so issues are traceable
            if fn % 100 == 1:
                log.info(
                    "Frame %d — tracks=%d  persons=%d  vehicles=%d",
                    fn,
                    len(tracking_frame.tracks),
                    len(tracking_frame.persons),
                    len(tracking_frame.vehicles),
                )

            # ── Per-track analytics ───────────────────────────────────────────
            person_summaries = []
            vehicle_summaries = []
            gender_counts = {"Male": 0, "Female": 0, "Unknown": 0}

            for obj in tracking_frame.tracks:
                # direction
                dir_event = direction_det.update(obj.track_id, obj.center)

                # line crossing
                prev_c = _prev_centers.get(obj.track_id)
                crossings = line_counter.update(
                    obj.track_id, obj.class_name, obj.center, prev_c, fn
                )
                _prev_centers[obj.track_id] = obj.center

                # zone
                zone_events = zone_mgr.update(
                    obj.track_id, obj.class_name, obj.center, fn
                )

                if obj.is_person:
                    # gender
                    gender_label = "Unknown"
                    if gender_clf:
                        gender_clf.classify_async(obj.track_id, frame, obj.bbox)
                        cached = gender_clf.get_cached(obj.track_id)
                        if cached:
                            gender_label = cached.gender
                            gender_counts[gender_label] = gender_counts.get(gender_label, 0) + 1
                            # DB write (once per track)
                            if db_writer and cached.gender != "Unknown":
                                db_writer.put_gender(
                                    obj.track_id, fn,
                                    cached.gender, cached.confidence, cached.backend
                                )
                            # gender snapshot (once per track)
                            if (config.system.save_snapshots
                                    and obj.track_id not in _gender_snapped
                                    and cached.gender != "Unknown"):
                                save_gender_snapshot(frame, obj.track_id,
                                                     cached.gender, cached.confidence,
                                                     obj.bbox)
                                _gender_snapped[obj.track_id] = fn

                    person_summaries.append(astate.TrackedPersonSummary(
                        track_id  = obj.track_id,
                        gender    = gender_label,
                        direction = direction_det.get_direction(obj.track_id),
                        zone      = zone_mgr.get_current_zone_label(obj.track_id),
                        first_seen = obj.first_seen,
                    ))

                    # person snapshot
                    if (config.system.save_snapshots
                            and (now - _last_person_snap) >= _PERSON_SNAP_INTERVAL):
                        save_person_snapshot(frame, obj.track_id, obj.bbox)
                        globals()["_last_person_snap"] = now

                elif obj.is_vehicle:
                    rec = vehicle_anlt.update(obj.track_id, obj.class_name, obj.last_seen)
                    if dir_event:
                        vehicle_anlt.set_direction(obj.track_id, dir_event.direction)

                    vehicle_summaries.append(astate.TrackedVehicleSummary(
                        track_id     = obj.track_id,
                        vehicle_type = obj.class_name,
                        direction    = dir_event.direction if dir_event else "–",
                        first_seen   = obj.first_seen,
                    ))

                    # vehicle snapshot
                    if (config.system.save_snapshots
                            and (now - _last_vehicle_snap) >= _VEHICLE_SNAP_INTERVAL):
                        save_vehicle_snapshot(frame, obj.track_id, obj.class_name, obj.bbox)
                        globals()["_last_vehicle_snap"] = now

                # direction DB write (once per track)
                if dir_event and db_writer and obj.track_id not in _direction_written:
                    _direction_written.add(obj.track_id)
                    sx, sy = dir_event.start_point if hasattr(dir_event, "start_point") else (0, 0)
                    ex_, ey = dir_event.end_point if hasattr(dir_event, "end_point") else (0, 0)
                    db_writer.put_direction(
                        obj.track_id, dir_event.direction, obj.class_name,
                        sx, sy, ex_, ey
                    )

                # crossing DB writes + occupancy + snapshots
                for evt in crossings:
                    if db_writer:
                        db_writer.put_crossing(
                            evt.track_id, evt.line_label, evt.direction,
                            evt.class_name, evt.centroid_x, evt.centroid_y, evt.frame_number
                        )
                    if evt.direction == "entry":
                        if obj.is_person:
                            occupancy.person_entered()
                        else:
                            occupancy.vehicle_entered()
                        save_entry_snapshot(frame, evt.track_id)
                        astate.append_log(f"ENTRY: {evt.track_id}")
                    else:
                        if obj.is_person:
                            occupancy.person_exited()
                        else:
                            occupancy.vehicle_exited()
                        save_exit_snapshot(frame, evt.track_id)
                        astate.append_log(f"EXIT:  {evt.track_id}")

                # zone DB writes
                for zevt in zone_events:
                    if db_writer:
                        db_writer.put_zone_event(
                            zevt.track_id, zevt.zone_label, zevt.event_type,
                            zevt.class_name, zevt.frame_number, zevt.duration_seconds
                        )

            # ── close stale tracks ────────────────────────────────────────────
            for closed_id in tracking_frame.closed_ids:
                if gender_clf:
                    gender_clf.evict(closed_id)
                direction_det.remove(closed_id)
                line_counter.remove_track(closed_id)
                zone_mgr.remove_track(closed_id)
                vehicle_anlt.close_track(closed_id)
                _prev_centers.pop(closed_id, None)
                _direction_written.discard(closed_id)
                _gender_snapped.pop(closed_id, None)

            # ── hourly vehicle bucket flush ───────────────────────────────────
            if db_writer:
                for bucket in vehicle_anlt.take_closed_buckets():
                    c = bucket.counts
                    db_writer.put_vehicle_counts(
                        bucket.hour_start,
                        c.get("car", 0), c.get("motorcycle", 0),
                        c.get("bus", 0),  c.get("truck", 0),
                        c.get("bicycle", 0),
                    )

            # ── periodic DB snapshots ─────────────────────────────────────────
            if db_writer:
                if (now - _last_occupancy_db) >= _OCCUPANCY_SNAP_INTERVAL:
                    db_writer.put_occupancy(
                        occupancy.current_people, occupancy.current_vehicles,
                        occupancy.peak_people,    occupancy.peak_vehicles,
                        occupancy.avg_people,     occupancy.avg_vehicles,
                    )
                    globals()["_last_occupancy_db"] = now

                if (now - _last_health_db) >= _HEALTH_SNAP_INTERVAL:
                    db_writer.put_health(
                        health.cpu_pct, health.ram_gb,
                        tracker.device_label, capture.actual_fps,
                    )
                    globals()["_last_health_db"] = now

            # ── periodic tracked_objects batch write ──────────────────────────
            if db_writer and session_id and fn % config.tracking.persist_every_n >= 0:
                for obj in tracking_frame.tracks:
                    x1, y1, x2, y2 = obj.bbox
                    cx,  cy         = obj.center
                    db_writer.put_tracked_object(
                        session_id, obj.track_id, fn,
                        obj.class_name, obj.confidence,
                        x1, y1, x2, y2, cx, cy,
                    )

            # ── occupancy tick ────────────────────────────────────────────────
            occupancy.tick()

            # ── AI analyst ────────────────────────────────────────────────────
            if analyst:
                from detection import DetectionResult as _DR
                counts = tracking_frame.counts_by_class()
                dr = _DR(
                    people      = counts.get("person", 0),
                    cars        = counts.get("car", 0),
                    motorcycles = counts.get("motorcycle", 0),
                    buses       = counts.get("bus", 0),
                    trucks      = counts.get("truck", 0),
                    bicycles    = counts.get("bicycle", 0),
                    frame_number = fn,
                    has_detection = bool(tracking_frame.tracks),
                )
                analyst.push(dr)
                insight = analyst.insight
                ts_label = (f"{insight.timestamp} [{insight.provider}]"
                            if insight.provider else insight.timestamp)
                astate.update(ai_text=insight.text, ai_timestamp=ts_label)

            # ── analytics state update ────────────────────────────────────────
            line_totals = line_counter.totals()
            gender_live = gender_clf.live_counts() if gender_clf else {"Male": 0, "Female": 0, "Unknown": 0}
            v_counts    = vehicle_anlt.get_active_counts()

            astate.update(
                people_count      = len(tracking_frame.persons),
                car_count         = v_counts.get("car", 0),
                motorcycle_count  = v_counts.get("motorcycle", 0),
                bus_count         = v_counts.get("bus", 0),
                truck_count       = v_counts.get("truck", 0),
                bicycle_count     = v_counts.get("bicycle", 0),
                gender_male       = gender_live.get("Male", 0),
                gender_female     = gender_live.get("Female", 0),
                gender_unknown    = gender_live.get("Unknown", 0),
                total_entries     = line_totals["entries"],
                total_exits       = line_totals["exits"],
                current_occupancy = occupancy.current_people,
                peak_occupancy    = occupancy.peak_people,
                avg_occupancy     = occupancy.avg_people,
                active_persons    = person_summaries,
                active_vehicles   = vehicle_summaries,
                actual_fps        = capture.actual_fps,
                frame_number      = fn,
                cpu_pct           = health.cpu_pct,
                ram_gb            = health.ram_gb,
                device_label      = tracker.device_label,
            )

            dashboard.tick()
            time.sleep(0.001)

    except Exception as exc:
        import traceback
        err_msg = f"Main loop crash: {exc}"
        log.exception(err_msg)
        astate.update(last_error=err_msg, error_count=astate.get_state().error_count + 1)
        astate.append_log(f"[FATAL] {err_msg[:55]}")
        if db_writer:
            db_writer.put_error("CRITICAL", "phase2_main", str(exc),
                                traceback.format_exc())

    finally:
        # ── 17. Shutdown ──────────────────────────────────────────────────────
        log.info("Phase 2 shutting down…")
        dashboard.stop()
        capture.stop()
        health.stop()

        if analyst:
            analyst.stop()
        if gender_clf:
            gender_clf.shutdown()

        if db and session_id:
            db.close_session(session_id)
        if db_writer:
            db_writer.stop()
        if db:
            db.close()

        print("\n[CCTV Phase 2] Shutdown complete.\n")


if __name__ == "__main__":
    main()
