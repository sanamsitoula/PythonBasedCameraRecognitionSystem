"""
phase3_main.py – CCTV Analytics Phase 3 entry point.

Startup sequence:
  1.  Load config (Phase 2 + Phase 3 sections)
  2.  Setup logging (Phase 2 loggers + Phase 3 category loggers)
  3.  Camera pre-flight verification
  4.  ByteTracker
  5.  GenderClassifier
  6.  Direction / Line / Zone engines
  7.  OccupancyEngine
  8.  VehicleAnalytics
  9.  FaceRecognitionEngine
  10. EmployeeIdentifier
  11. AttendanceEngine
  12. VisitorManager
  13. CanteenAnalytics
  14. DepartmentAnalytics
  15. CrossCameraReID
  16. SmartAlerts
  17. AuditLogger
  18. DatabaseManager + DatabaseManagerP3 (if enabled)
  19. Load employee embeddings from DB into FaceRecognitionEngine
  20. AiAnalyst
  21. RTSPCapture
  22. HealthMonitor
  23. Phase3Dashboard
  24. Main loop
  25. Graceful shutdown
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Optional

# Suppress FFmpeg/OpenCV HEVC codec noise (cosmetic only).
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

# ── Config & logging ──────────────────────────────────────────────────────────
from config_manager import load_config, build_ai_providers
from logger import setup_logging, setup_phase2_loggers, get_camera_logger

# ── Phase 2 engines ───────────────────────────────────────────────────────────
from camera_verifier import verify_camera
from rtsp_capture import RTSPCapture
from health_monitor import HealthMonitor
from tracker import ByteTracker
from gender_classifier import GenderClassifier
from direction_detector import DirectionDetector
from line_counter import LineCounter
from zone_manager import ZoneManager
from occupancy_engine import OccupancyEngine
from vehicle_analytics import VehicleAnalytics
from db_manager import DatabaseManager
from db_writer import DbWriter
from ai_analyst import AiAnalyst
from snapshot_manager_v2 import (
    save_person_snapshot,
    save_vehicle_snapshot,
    save_entry_snapshot,
    save_exit_snapshot,
    save_gender_snapshot,
)

# ── Phase 3 engines ───────────────────────────────────────────────────────────
from face_recognition_engine import FaceRecognitionEngine
from employee_identifier import EmployeeIdentifier, IdentityResult
from attendance_engine import AttendanceEngine
from visitor_manager import VisitorManager
from canteen_analytics import CanteenAnalytics
from department_analytics import DepartmentAnalytics
from cross_camera_reid import CrossCameraReID
from smart_alerts import SmartAlerts, Alert
from audit_logger import AuditLogger
from db_manager_p3 import DatabaseManagerP3

# ── State & dashboard ─────────────────────────────────────────────────────────
import analytics_state as astate
import phase3_state as p3state
from phase3_state import EmployeeSummary, VisitorSummaryP3, DeptSummaryEntry
from phase3_dashboard import Phase3Dashboard, print_preflight_p3

log = logging.getLogger(__name__)

# ─────────────────────────── shutdown flag ───────────────────────────────────

_shutdown        = False
_reconnect_count = 0
config           = None


def _handle_signal(signum, frame):
    global _shutdown
    log.info("Shutdown signal received (%s).", signum)
    _shutdown = True


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ─────────────────────────── throttle timers ─────────────────────────────────

_PERSON_SNAP_INTERVAL    = 15.0
_VEHICLE_SNAP_INTERVAL   = 10.0
_OCCUPANCY_SNAP_INTERVAL = 60.0
_HEALTH_SNAP_INTERVAL    = 30.0
_ANALYTICS_DB_INTERVAL   = 60.0

_last_person_snap    = 0.0
_last_vehicle_snap   = 0.0
_last_occupancy_db   = 0.0
_last_health_db      = 0.0
_last_analytics_db   = 0.0

# per-track bookkeeping
_gender_snapped:     dict = {}
_prev_centers:       dict = {}
_direction_written:  set  = set()
_emp_entry_recorded: set  = set()  # employee_ids already recorded in AttendanceEngine today
_track_in_canteen:   set  = set()  # track_ids currently in canteen zone

CAMERA_ID = "cam1"  # logical camera identifier; extend for multi-camera


# ─────────────────────────── logger setup helper ─────────────────────────────

def setup_phase3_loggers() -> None:
    """Wire up Phase 3 category-specific log files."""
    from logger import _make_file_handler, LOG_DIR
    from logging.handlers import RotatingFileHandler

    _P3_LOGGERS = {
        "recognition": "recognition.log",
        "enrollment":  "enrollment.log",
        "attendance":  "attendance.log",
        "alerts":      "alerts.log",
    }
    for logger_name, filename in _P3_LOGGERS.items():
        cat = logging.getLogger(logger_name)
        if not any(isinstance(h, RotatingFileHandler) for h in cat.handlers):
            cat.addHandler(
                _make_file_handler(os.path.join(LOG_DIR, filename), logging.DEBUG)
            )
        cat.propagate = True


# ─────────────────────────── helpers ─────────────────────────────────────────

def _build_employee_db_from_db(db_p3: Optional[DatabaseManagerP3]) -> dict:
    """
    Load employee metadata from DatabaseManagerP3.
    Returns {employee_id: {"name": str, "department": str, "designation": str}}.
    Falls back to empty dict if DB unavailable.
    """
    if db_p3 is None:
        return {}
    try:
        return db_p3.get_all_employees()
    except Exception as exc:
        log.warning("Could not load employee DB from PostgreSQL: %s", exc)
        return {}


def _load_embeddings(face_engine: FaceRecognitionEngine,
                     db_p3: Optional[DatabaseManagerP3]) -> int:
    """Load stored face embeddings into the recognition engine. Returns count loaded."""
    if db_p3 is None:
        log.info("No DB available – skipping embedding load.")
        return 0
    try:
        embeddings = db_p3.get_all_embeddings()
        for emp_id, embedding in embeddings.items():
            face_engine.register_embedding(emp_id, embedding)
        log.info("Loaded %d face embeddings from DB.", len(embeddings))
        return len(embeddings)
    except Exception as exc:
        log.warning("Could not load embeddings from DB: %s", exc)
        return 0


def _alert_to_dict(alert: Alert) -> dict:
    return {
        "severity":   alert.severity,
        "message":    alert.message,
        "timestamp":  alert.timestamp,
        "alert_type": alert.alert_type,
    }


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
    setup_phase3_loggers()
    cam_log = get_camera_logger()
    rec_log = logging.getLogger("recognition")
    att_log = logging.getLogger("attendance")
    alr_log = logging.getLogger("alerts")
    log.info("CCTV Analytics Phase 3 starting…")

    # ── 3. Camera verification ────────────────────────────────────────────────
    print("\nRunning camera pre-flight verification…\n")
    verify_result = verify_camera(config)

    camera_info = [{
        "ip":            config.camera.ip,
        "success":       verify_result.success,
        "width":         getattr(verify_result, "width", 0),
        "height":        getattr(verify_result, "height", 0),
        "fps":           getattr(verify_result, "fps", 0),
        "codec":         getattr(verify_result, "codec", "–"),
        "error_message": getattr(verify_result, "error_message", ""),
        "status":        "OK" if verify_result.success else "FAILED",
    }]
    print_preflight_p3(camera_info)

    if not verify_result.success:
        print("\n[FATAL] Camera verification failed. Fix the issues above and retry.\n")
        sys.exit(1)

    print("\nVerification passed. Loading ByteTrack model…\n")
    time.sleep(1)

    # ── 4. ByteTracker ────────────────────────────────────────────────────────
    try:
        tracker = ByteTracker(
            model_path = config.yolo.model,
            confidence = config.yolo.confidence,
            iou        = config.yolo.iou_threshold,
            device     = config.yolo.device,
            max_age    = config.tracking.max_age,
            min_hits   = config.tracking.min_hits,
        )
    except Exception as exc:
        log.critical("ByteTracker load failed: %s", exc)
        print(f"\n[FATAL] ByteTracker load failed: {exc}\n")
        sys.exit(1)

    # ── 5. GenderClassifier ───────────────────────────────────────────────────
    gender_clf: Optional[GenderClassifier] = None
    if config.gender.enabled:
        gender_clf = GenderClassifier(
            backend              = config.gender.backend,
            confidence_threshold = config.gender.confidence_threshold,
            min_bbox_height      = config.gender.min_bbox_height,
            max_workers          = config.gender.max_workers,
        )

    # ── 6. Direction / Line / Zone engines ────────────────────────────────────
    direction_det = DirectionDetector()
    line_counter  = LineCounter(config.lines.lines)
    zone_mgr      = ZoneManager(config.zones.zones)

    # ── 7. OccupancyEngine ────────────────────────────────────────────────────
    occupancy = OccupancyEngine(
        average_window_seconds = config.occupancy.average_window_seconds,
        reset_peak_daily       = config.occupancy.reset_peak_daily,
        alert_threshold        = config.occupancy.alert_threshold,
    )

    # ── 8. VehicleAnalytics ───────────────────────────────────────────────────
    vehicle_anlt = VehicleAnalytics()

    # ── 9. FaceRecognitionEngine ──────────────────────────────────────────────
    face_cfg = config.face_recognition
    face_engine = FaceRecognitionEngine(
        backend           = face_cfg.backend,
        model_dir         = face_cfg.model_dir,
        min_confidence    = face_cfg.min_confidence,
        confirmed_threshold = face_cfg.confirmed_threshold,
        possible_threshold  = face_cfg.possible_threshold,
    )

    # ── 10. EmployeeIdentifier ────────────────────────────────────────────────
    emp_identifier = EmployeeIdentifier(
        face_engine  = face_engine,
        employee_db  = {},      # populated after DB connect (step 19)
    )
    emp_identifier.RE_IDENTIFY_INTERVAL = face_cfg.re_identify_interval

    # ── 11. AttendanceEngine ──────────────────────────────────────────────────
    att_cfg = config.attendance
    attendance = AttendanceEngine(
        late_threshold = att_cfg.late_threshold,
        work_start     = att_cfg.work_start,
        work_end       = att_cfg.work_end,
    )

    # ── 12. VisitorManager ────────────────────────────────────────────────────
    visitor_mgr = VisitorManager()

    # ── 13. CanteenAnalytics ──────────────────────────────────────────────────
    canteen = CanteenAnalytics()

    # ── 14. DepartmentAnalytics ───────────────────────────────────────────────
    dept_anlt = DepartmentAnalytics()

    # ── 15. CrossCameraReID ───────────────────────────────────────────────────
    reid = CrossCameraReID()

    # ── 16. SmartAlerts ───────────────────────────────────────────────────────
    alerts_cfg = config.smart_alerts
    smart_alerts = SmartAlerts(
        restricted_zones  = alerts_cfg.restricted_zones,
        loitering_seconds = alerts_cfg.loitering_seconds,
        crowd_threshold   = alerts_cfg.crowd_threshold,
        office_start      = alerts_cfg.office_start_hour,
        office_end        = alerts_cfg.office_end_hour,
    )

    # ── 17. AuditLogger ───────────────────────────────────────────────────────
    audit = AuditLogger()

    # ── 18. Databases ─────────────────────────────────────────────────────────
    db:          Optional[DatabaseManager]   = None
    db_writer:   Optional[DbWriter]          = None
    db_p3:       Optional[DatabaseManagerP3] = None
    session_id:  Optional[int]               = None
    camera_id_db: Optional[int]              = None

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
            camera_id_db = db.ensure_camera(config.camera.ip, config.camera.rtsp_url)
            session_id   = (
                db.create_session(camera_id_db, config.yolo.model, tracker.device_label)
                if camera_id_db else None
            )
            db_writer = DbWriter(db, session_id, config.database.write_queue_max)
            db_writer.start()
            p3state.update(db_available=True)
            astate.update(db_available=True)
            log.info("Phase 2 database session started: session_id=%s", session_id)

            # Phase 3 DB
            try:
                db_p3 = DatabaseManagerP3(
                    host     = config.database.host,
                    port     = config.database.port,
                    dbname   = config.database.dbname,
                    user     = config.database.user,
                    password = config.database.password,
                )
                log.info("Phase 3 DB manager initialised.")
            except Exception as exc:
                log.warning("DatabaseManagerP3 init failed: %s", exc)
                db_p3 = None
        else:
            log.warning("Database unavailable – running without persistence.")

    # ── 19. Load embeddings ───────────────────────────────────────────────────
    emp_db = _build_employee_db_from_db(db_p3)
    emp_identifier.update_employee_db(emp_db)
    n_emb = _load_embeddings(face_engine, db_p3)
    log.info("Employee DB: %d records; embeddings loaded: %d", len(emp_db), n_emb)

    # Load department rosters from emp_db
    dept_map: dict = {}
    for emp_id, info in emp_db.items():
        d = info.get("department", "Unknown")
        dept_map.setdefault(d, []).append(emp_id)
    for dept, roster in dept_map.items():
        dept_anlt.set_department_roster(dept, roster)

    # ── 20. AI analyst ────────────────────────────────────────────────────────
    analyst: Optional[AiAnalyst] = None
    if config.ai.enabled:
        _providers = build_ai_providers(config.ai)
        if _providers:
            analyst = AiAnalyst(providers=_providers, interval=config.ai.interval_seconds)
            analyst.start()
        else:
            log.warning("AI analyst disabled – no API keys configured.")

    # ── 21. RTSP capture ──────────────────────────────────────────────────────
    def _on_reconnect():
        global _reconnect_count
        _reconnect_count += 1
        msg = f"Camera reconnected (attempt #{_reconnect_count})"
        p3state.append_log(msg)
        cam_log.info(msg)

    def _on_failure():
        global _shutdown
        msg = "RTSP reconnection exhausted – shutting down."
        p3state.append_log(msg)
        cam_log.critical(msg)
        _shutdown = True

    capture = RTSPCapture(config, on_reconnect=_on_reconnect, on_failure=_on_failure)
    if not capture.start():
        log.critical("Failed to start RTSP capture.")
        print("\n[FATAL] Could not start RTSP stream capture.\n")
        sys.exit(1)

    # ── 22. HealthMonitor ─────────────────────────────────────────────────────
    health = HealthMonitor(config)
    health.start()

    # ── 23. Phase3Dashboard ───────────────────────────────────────────────────
    dashboard = Phase3Dashboard(config, refresh_rate=config.display.dashboard_refresh_rate)
    dashboard.set_cameras([{
        "ip":     config.camera.ip,
        "status": "Connected",
        "fps":    verify_result.fps,
    }])
    p3state.append_log("Phase 3 started")
    dashboard.start()

    # ── 24. Main loop ─────────────────────────────────────────────────────────
    canteen_zone_label = getattr(config, "canteen", None)
    canteen_zone_label = (
        canteen_zone_label.zone_label if canteen_zone_label else "Canteen"
    )

    try:
        while not _shutdown:
            frame = capture.read()
            now   = time.monotonic()
            now_dt = datetime.now()

            if frame is None:
                occupancy.tick()
                dashboard.tick()
                p3state.update(
                    cpu_pct=health.cpu_pct,
                    ram_gb=health.ram_gb,
                )
                time.sleep(0.005)
                continue

            # ── ByteTrack ────────────────────────────────────────────────────
            try:
                tracking_frame = tracker.track(frame)
            except Exception as exc:
                import traceback as _tb
                err_msg = f"Tracker error: {exc}"
                log.error(err_msg)
                p3state.update(
                    last_error=err_msg,
                    error_count=p3state.get_state().error_count + 1,
                )
                p3state.append_log(f"[ERROR] {err_msg[:55]}")
                continue

            fn = tracking_frame.frame_number

            if fn % 100 == 1:
                log.info(
                    "Frame %d — tracks=%d  persons=%d  vehicles=%d",
                    fn,
                    len(tracking_frame.tracks),
                    len(tracking_frame.persons),
                    len(tracking_frame.vehicles),
                )

            # ── Per-track analytics ───────────────────────────────────────────
            person_summaries_p2  = []
            vehicle_summaries    = []
            gender_counts        = {"Male": 0, "Female": 0, "Unknown": 0}
            active_emps          = []
            active_vis           = []

            for obj in tracking_frame.tracks:
                # Direction
                dir_event = direction_det.update(obj.track_id, obj.center)

                # Line crossing
                prev_c    = _prev_centers.get(obj.track_id)
                crossings = line_counter.update(
                    obj.track_id, obj.class_name, obj.center, prev_c, fn
                )
                _prev_centers[obj.track_id] = obj.center

                # Zone
                zone_label  = zone_mgr.get_current_zone_label(obj.track_id)
                zone_events = zone_mgr.update(
                    obj.track_id, obj.class_name, obj.center, fn
                )

                if obj.is_person:
                    # ── Gender ────────────────────────────────────────────────
                    gender_label = "Unknown"
                    if gender_clf:
                        gender_clf.classify_async(obj.track_id, frame, obj.bbox)
                        cached = gender_clf.get_cached(obj.track_id)
                        if cached:
                            gender_label = cached.gender
                            gender_counts[gender_label] = gender_counts.get(gender_label, 0) + 1
                            if db_writer and cached.gender != "Unknown":
                                db_writer.put_gender(
                                    obj.track_id, fn,
                                    cached.gender, cached.confidence, cached.backend
                                )
                            if (config.system.save_snapshots
                                    and obj.track_id not in _gender_snapped
                                    and cached.gender != "Unknown"):
                                save_gender_snapshot(
                                    frame, obj.track_id,
                                    cached.gender, cached.confidence, obj.bbox
                                )
                                _gender_snapped[obj.track_id] = fn

                    # ── Face identification ───────────────────────────────────
                    try:
                        identity: IdentityResult = emp_identifier.identify(
                            track_id     = obj.track_id,
                            camera_id    = CAMERA_ID,
                            frame        = frame,
                            person_bbox  = obj.bbox,
                            frame_number = fn,
                        )
                    except Exception as exc:
                        log.debug("Face identification failed for track %s: %s",
                                  obj.track_id, exc)
                        identity = None

                    if identity and identity.identity_type == "employee":
                        emp_id = identity.person_id

                        # Attendance (first appearance per employee per day)
                        if emp_id not in _emp_entry_recorded:
                            try:
                                attendance.record_entry(emp_id, now_dt)
                                _emp_entry_recorded.add(emp_id)
                                att_log.info("Entry: %s at %s", emp_id, now_dt)
                                audit.log_event("attendance_entry", emp_id, now_dt)
                                p3state.append_log(f"ENTRY: {emp_id} {identity.employee_name}")
                            except Exception as exc:
                                log.warning("AttendanceEngine.record_entry failed: %s", exc)

                        # Canteen
                        if zone_label == canteen_zone_label:
                            if obj.track_id not in _track_in_canteen:
                                try:
                                    canteen.person_entered(emp_id, "employee", now_dt)
                                    _track_in_canteen.add(obj.track_id)
                                except Exception as exc:
                                    log.debug("canteen.person_entered: %s", exc)

                        # Department zone
                        if zone_label:
                            try:
                                dept_anlt.employee_entered_zone(emp_id, zone_label)
                            except Exception as exc:
                                log.debug("dept_anlt.employee_entered_zone: %s", exc)

                        # Cross-camera ReID
                        try:
                            reid.register_track(emp_id, CAMERA_ID, obj.track_id, fn)
                        except Exception as exc:
                            log.debug("reid.register_track: %s", exc)

                        # Smart alerts for employees
                        if alerts_cfg.enabled:
                            _check_alerts(
                                smart_alerts, identity.person_id, CAMERA_ID,
                                zone_label, False, now_dt, zone_events, alr_log
                            )

                        entry_rec = attendance.get_record(emp_id)
                        entry_dt  = entry_rec.first_entry if entry_rec else None
                        active_emps.append(EmployeeSummary(
                            employee_id      = emp_id,
                            employee_name    = identity.employee_name,
                            department       = identity.department,
                            current_zone     = zone_label or "–",
                            current_camera_id= CAMERA_ID,
                            entry_time       = entry_dt or now_dt,
                            gender           = gender_label,
                        ))
                        rec_log.debug(
                            "Employee %s (conf=%.3f status=%s)",
                            emp_id, identity.confidence, identity.recognition_status
                        )

                    else:
                        # Visitor path
                        vis_id = visitor_mgr.get_or_create(obj.track_id, CAMERA_ID)
                        if zone_label:
                            try:
                                visitor_mgr.update_location(vis_id, zone_label,
                                                             CAMERA_ID, now_dt)
                            except Exception as exc:
                                log.debug("visitor_mgr.update_location: %s", exc)

                        # Canteen
                        if zone_label == canteen_zone_label:
                            if obj.track_id not in _track_in_canteen:
                                try:
                                    canteen.person_entered(vis_id, "visitor", now_dt)
                                    _track_in_canteen.add(obj.track_id)
                                except Exception as exc:
                                    log.debug("canteen.person_entered visitor: %s", exc)

                        # Smart alerts for visitors
                        if alerts_cfg.enabled:
                            _check_alerts(
                                smart_alerts, vis_id, CAMERA_ID,
                                zone_label, True, now_dt, zone_events, alr_log
                            )

                        vis_rec = visitor_mgr.get_record(vis_id)
                        active_vis.append(VisitorSummaryP3(
                            visitor_id        = vis_id,
                            current_zone      = zone_label or "–",
                            current_camera_id = CAMERA_ID,
                            first_seen        = vis_rec.first_seen if vis_rec else now_dt,
                            gender            = gender_label,
                        ))

                    # Phase 2 person summary (for analytics_state)
                    from analytics_state import TrackedPersonSummary
                    person_summaries_p2.append(TrackedPersonSummary(
                        track_id   = obj.track_id,
                        gender     = gender_label,
                        direction  = direction_det.get_direction(obj.track_id),
                        zone       = zone_label or "–",
                        first_seen = obj.first_seen,
                    ))

                    # Person snapshot
                    if (config.system.save_snapshots
                            and (now - _last_person_snap) >= _PERSON_SNAP_INTERVAL):
                        save_person_snapshot(frame, obj.track_id, obj.bbox)
                        globals()["_last_person_snap"] = now

                elif obj.is_vehicle:
                    rec = vehicle_anlt.update(obj.track_id, obj.class_name, obj.last_seen)
                    if dir_event:
                        vehicle_anlt.set_direction(obj.track_id, dir_event.direction)

                    from analytics_state import TrackedVehicleSummary
                    vehicle_summaries.append(TrackedVehicleSummary(
                        track_id     = obj.track_id,
                        vehicle_type = obj.class_name,
                        direction    = dir_event.direction if dir_event else "–",
                        first_seen   = obj.first_seen,
                    ))

                    if (config.system.save_snapshots
                            and (now - _last_vehicle_snap) >= _VEHICLE_SNAP_INTERVAL):
                        save_vehicle_snapshot(frame, obj.track_id, obj.class_name, obj.bbox)
                        globals()["_last_vehicle_snap"] = now

                # Direction DB write (once per track)
                if dir_event and db_writer and obj.track_id not in _direction_written:
                    _direction_written.add(obj.track_id)
                    sx, sy = getattr(dir_event, "start_point", (0, 0))
                    ex, ey = getattr(dir_event, "end_point",   (0, 0))
                    db_writer.put_direction(
                        obj.track_id, dir_event.direction, obj.class_name,
                        sx, sy, ex, ey
                    )

                # Crossing events
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
                        p3state.append_log(f"LINE-IN:  {evt.track_id}")
                    else:
                        if obj.is_person:
                            occupancy.person_exited()
                        else:
                            occupancy.vehicle_exited()
                        save_exit_snapshot(frame, evt.track_id)
                        p3state.append_log(f"LINE-OUT: {evt.track_id}")

                # Zone DB writes
                for zevt in zone_events:
                    if db_writer:
                        db_writer.put_zone_event(
                            zevt.track_id, zevt.zone_label, zevt.event_type,
                            zevt.class_name, zevt.frame_number, zevt.duration_seconds
                        )

            # ── Close stale tracks ────────────────────────────────────────────
            for closed_id in tracking_frame.closed_ids:
                if gender_clf:
                    gender_clf.evict(closed_id)
                direction_det.remove(closed_id)
                line_counter.remove_track(closed_id)
                zone_mgr.remove_track(closed_id)
                vehicle_anlt.close_track(closed_id)
                emp_identifier.evict(closed_id, CAMERA_ID)
                visitor_mgr.remove_track(closed_id, CAMERA_ID)
                _prev_centers.pop(closed_id, None)
                _direction_written.discard(closed_id)
                _gender_snapped.pop(closed_id, None)

                # Canteen exit for departing track
                if closed_id in _track_in_canteen:
                    _track_in_canteen.discard(closed_id)
                    cached_id = emp_identifier.get_cached(closed_id, CAMERA_ID)
                    pid = cached_id.person_id if cached_id else closed_id
                    try:
                        canteen.person_exited(pid, now_dt)
                    except Exception:
                        pass

                # Attendance exit
                cached_id = emp_identifier.get_cached(closed_id, CAMERA_ID)
                if cached_id and cached_id.identity_type == "employee":
                    emp_id_c = cached_id.person_id
                    try:
                        attendance.record_exit(emp_id_c, now_dt)
                        att_log.info("Exit: %s at %s", emp_id_c, now_dt)
                        dept_anlt.employee_left_camera(emp_id_c)
                    except Exception as exc:
                        log.debug("record_exit failed: %s", exc)

            # ── Vehicle bucket flush ──────────────────────────────────────────
            if db_writer:
                for bucket in vehicle_anlt.take_closed_buckets():
                    c = bucket.counts
                    db_writer.put_vehicle_counts(
                        bucket.hour_start,
                        c.get("car", 0), c.get("motorcycle", 0),
                        c.get("bus", 0), c.get("truck", 0), c.get("bicycle", 0),
                    )

            # ── Periodic DB snapshots ─────────────────────────────────────────
            if db_writer:
                if (now - _last_occupancy_db) >= _OCCUPANCY_SNAP_INTERVAL:
                    db_writer.put_occupancy(
                        occupancy.current_people, occupancy.current_vehicles,
                        occupancy.peak_people, occupancy.peak_vehicles,
                        occupancy.avg_people, occupancy.avg_vehicles,
                    )
                    globals()["_last_occupancy_db"] = now

                if (now - _last_health_db) >= _HEALTH_SNAP_INTERVAL:
                    db_writer.put_health(
                        health.cpu_pct, health.ram_gb,
                        tracker.device_label, capture.actual_fps,
                    )
                    globals()["_last_health_db"] = now

            if (db_writer and session_id
                    and fn % config.tracking.persist_every_n >= 0):
                for obj in tracking_frame.tracks:
                    x1, y1, x2, y2 = obj.bbox
                    cx, cy          = obj.center
                    db_writer.put_tracked_object(
                        session_id, obj.track_id, fn,
                        obj.class_name, obj.confidence,
                        x1, y1, x2, y2, cx, cy,
                    )

            # ── Occupancy tick ────────────────────────────────────────────────
            occupancy.tick()

            # ── AI analyst ────────────────────────────────────────────────────
            ai_text = None
            ai_ts   = "–"
            if analyst:
                from detection import DetectionResult as _DR
                counts = tracking_frame.counts_by_class()
                dr = _DR(
                    people       = counts.get("person", 0),
                    cars         = counts.get("car", 0),
                    motorcycles  = counts.get("motorcycle", 0),
                    buses        = counts.get("bus", 0),
                    trucks       = counts.get("truck", 0),
                    bicycles     = counts.get("bicycle", 0),
                    frame_number = fn,
                    has_detection = bool(tracking_frame.tracks),
                )
                analyst.push(dr)
                insight = analyst.insight
                ai_ts_label = (
                    f"{insight.timestamp} [{insight.provider}]"
                    if insight.provider else insight.timestamp
                )
                ai_text = insight.text
                ai_ts   = ai_ts_label
                astate.update(ai_text=insight.text, ai_timestamp=ai_ts_label)

            # ── Build department summaries ────────────────────────────────────
            dept_list = []
            for ds in dept_anlt.get_all_departments():
                dept_list.append(DeptSummaryEntry(
                    department = ds.department,
                    present    = ds.present_today,
                    in_office  = ds.in_office,
                    in_canteen = ds.in_canteen,
                ))

            # ── Attendance summary ────────────────────────────────────────────
            att_summary = attendance.get_today_summary()

            # ── Canteen stats ─────────────────────────────────────────────────
            peak_h, peak_cnt = canteen.peak_hour()

            # ── Phase 3 state update ──────────────────────────────────────────
            gender_live = (gender_clf.live_counts()
                           if gender_clf
                           else {"Male": 0, "Female": 0, "Unknown": 0})
            emp_male    = sum(1 for e in active_emps if e.gender == "Male")
            emp_female  = sum(1 for e in active_emps if e.gender == "Female")
            vis_male    = sum(1 for v in active_vis if v.gender == "Male")
            vis_female  = sum(1 for v in active_vis if v.gender == "Female")

            recent_alerts_list = []
            for a in smart_alerts.get_recent_alerts(5):
                recent_alerts_list.append(a)

            p3state.update(
                actual_fps          = capture.actual_fps,
                frame_number        = fn,
                cpu_pct             = health.cpu_pct,
                ram_gb              = health.ram_gb,
                employees_present   = len(active_emps),
                visitors_present    = len(active_vis),
                male_employees      = emp_male,
                female_employees    = emp_female,
                male_visitors       = vis_male,
                female_visitors     = vis_female,
                present_today       = att_summary.get("present", 0),
                late_today          = att_summary.get("late", 0),
                absent_today        = att_summary.get("absent", 0),
                canteen_current     = canteen.current_count(),
                canteen_today_visits= len(canteen.today_visits()),
                active_employees    = active_emps,
                active_visitors     = active_vis,
                department_summaries= dept_list,
                recent_alerts       = recent_alerts_list,
            )
            if ai_text:
                p3state.update(ai_text=ai_text, ai_timestamp=ai_ts)

            # ── Phase 2 analytics_state update (for Phase 2 compatibility) ────
            line_totals = line_counter.totals()
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
                active_persons    = person_summaries_p2,
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
        p3state.update(
            last_error  = err_msg,
            error_count = p3state.get_state().error_count + 1,
        )
        p3state.append_log(f"[FATAL] {err_msg[:55]}")
        if db_writer:
            db_writer.put_error("CRITICAL", "phase3_main", str(exc),
                                traceback.format_exc())

    finally:
        # ── 25. Graceful shutdown ─────────────────────────────────────────────
        log.info("Phase 3 shutting down…")
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

        print("\n[CCTV Phase 3] Shutdown complete.\n")


# ─────────────────────────── alert helper ────────────────────────────────────

def _check_alerts(
    smart_alerts: SmartAlerts,
    person_id: str,
    camera_id: str,
    zone_label: str,
    is_visitor: bool,
    now_dt: datetime,
    zone_events,
    alr_log: logging.Logger,
) -> None:
    """Run all relevant SmartAlerts checks and push fired alerts to p3state."""
    fired = []

    if zone_label:
        a = smart_alerts.check_restricted_zone(
            person_id, camera_id, zone_label, is_visitor, now_dt
        )
        if a:
            fired.append(a)

        a = smart_alerts.check_after_hours(
            person_id, camera_id, zone_label, now_dt
        )
        if a:
            fired.append(a)

    # Loitering – look for duration in zone_events
    for zevt in zone_events:
        dur = getattr(zevt, "duration_seconds", 0)
        if dur:
            a = smart_alerts.check_loitering(
                person_id, camera_id, zevt.zone_label, int(dur), now_dt
            )
            if a:
                fired.append(a)

    for alert in fired:
        p3state.append_alert(alert)
        alr_log.info("[%s] %s: %s", alert.severity.upper(), alert.alert_type, alert.message)


if __name__ == "__main__":
    main()
