"""
EVAP Pipeline – bridges Phase 1-3 AI modules with the Phase 4 FastAPI backend.

Wraps the existing detection, face_recognition_engine, and vehicle_analytics
modules from the parent project, processes frames, and publishes results to
RabbitMQ for Phase 4 Celery workers to consume.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Add parent project root to sys.path so we can import Phase 1-3 modules
_PARENT = Path(__file__).resolve().parents[2]
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))


class EVAPPipeline:
    """
    Wraps Phase 1-3 modules (YOLO + ByteTrack + FaceRecognition + VehicleAnalytics)
    and publishes detections to RabbitMQ for Phase 4 processing.

    Usage:
        pipeline = EVAPPipeline(camera_id=1, rtsp_url="rtsp://...", settings=cfg)
        await pipeline.start()
        # runs in background thread
        await pipeline.stop()
    """

    def __init__(self, camera_id: int, rtsp_url: str, settings: Any):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.settings = settings

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_count = 0
        self._detection_count = 0

        # RabbitMQ connection (lazy init in start())
        self._connection = None
        self._channel = None

        # AI modules (lazy init in start())
        self._detector = None
        self._tracker = None
        self._face_engine = None
        self._vehicle_engine = None
        self._behavior_detector = None
        self._anpr_engine = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise AI modules and start the processing thread."""
        logger.info("EVAPPipeline starting for camera_id=%s", self.camera_id)
        self._init_rabbitmq()
        self._init_ai_modules()
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"pipeline-cam-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("EVAPPipeline thread started for camera_id=%s", self.camera_id)

    async def stop(self) -> None:
        """Signal the processing thread to stop and clean up connections."""
        logger.info("EVAPPipeline stopping camera_id=%s", self.camera_id)
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        if self._channel and self._channel.is_open:
            self._channel.close()
        if self._connection and self._connection.is_open:
            self._connection.close()
        logger.info("EVAPPipeline stopped camera_id=%s frames=%d detections=%d",
                    self.camera_id, self._frame_count, self._detection_count)

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_rabbitmq(self) -> None:
        try:
            import pika  # type: ignore[import]

            rabbitmq_url = getattr(self.settings, "RABBITMQ_URL", "amqp://guest:guest@localhost:5672//")
            params = pika.URLParameters(rabbitmq_url)
            params.heartbeat = 60
            self._connection = pika.BlockingConnection(params)
            self._channel = self._connection.channel()
            self._channel.queue_declare(queue="evap.detections", durable=True)
            self._channel.queue_declare(queue="evap.alerts", durable=True)
            logger.info("RabbitMQ connected for camera_id=%s", self.camera_id)
        except Exception as exc:
            logger.error("RabbitMQ init failed: %s — detections will not be published", exc)
            self._channel = None

    def _init_ai_modules(self) -> None:
        """Import and initialise Phase 1-3 AI modules with graceful fallback."""
        # YOLO detector (Phase 1)
        try:
            from detection import YOLODetector  # type: ignore[import]
            model_path = getattr(self.settings, "YOLO_MODEL_PATH", "models/yolov8n.pt")
            self._detector = YOLODetector(model_path=model_path)
            logger.info("YOLO detector loaded")
        except ImportError:
            logger.warning("detection.YOLODetector not found – using stub")
            self._detector = _StubDetector()

        # ByteTrack (Phase 1/2)
        try:
            from tracker import ByteTracker  # type: ignore[import]
            self._tracker = ByteTracker()
        except ImportError:
            logger.warning("tracker.ByteTracker not found – tracking disabled")
            self._tracker = None

        # Face recognition (Phase 3)
        try:
            from face_recognition_engine import FaceRecognitionEngine  # type: ignore[import]
            face_db = getattr(self.settings, "FACE_DB_PATH", "face_embeddings.pkl")
            self._face_engine = FaceRecognitionEngine(db_path=face_db)
            logger.info("FaceRecognitionEngine loaded")
        except ImportError:
            logger.warning("face_recognition_engine not found – face recognition disabled")
            self._face_engine = None

        # Vehicle analytics (Phase 3)
        try:
            from vehicle_analytics import VehicleAnalytics  # type: ignore[import]
            self._vehicle_engine = VehicleAnalytics()
        except ImportError:
            logger.warning("vehicle_analytics not found – vehicle module disabled")
            self._vehicle_engine = None

        # Phase 4 behavior detector and ANPR
        from .behavior_detector import BehaviorDetector
        from .anpr import ANPREngine

        behavior_cfg = {
            "loitering_threshold": getattr(self.settings, "LOITERING_THRESHOLD_SECONDS", 120),
            "crowd_threshold": getattr(self.settings, "CROWD_THRESHOLD", 10),
            "running_speed_threshold": getattr(self.settings, "RUNNING_SPEED_THRESHOLD", 3.0),
        }
        self._behavior_detector = BehaviorDetector(config=behavior_cfg)

        anpr_model = getattr(self.settings, "ANPR_MODEL_PATH", "models/anpr.pt")
        try:
            self._anpr_engine = ANPREngine(model_path=anpr_model)
        except Exception as exc:
            logger.warning("ANPREngine init failed: %s", exc)
            self._anpr_engine = None

    # ------------------------------------------------------------------
    # Capture loop
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        """Main frame capture and processing loop (runs in daemon thread)."""
        try:
            import cv2  # type: ignore[import]
        except ImportError:
            logger.error("OpenCV not available – pipeline cannot run")
            return

        cap = cv2.VideoCapture(self.rtsp_url)
        if not cap.isOpened():
            logger.error("Cannot open RTSP stream: %s", self.rtsp_url)
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_interval = max(1, int(fps / getattr(self.settings, "PROCESS_FPS", 5)))
        logger.info("Camera %s capture loop started @ %s fps (process every %d frames)",
                    self.camera_id, fps, frame_interval)

        frame_idx = 0
        while self._running:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Camera %s: frame read failed – reconnecting", self.camera_id)
                time.sleep(2)
                cap.release()
                cap = cv2.VideoCapture(self.rtsp_url)
                continue

            frame_idx += 1
            self._frame_count += 1

            if frame_idx % frame_interval != 0:
                continue

            try:
                self.process_frame(frame)
            except Exception as exc:
                logger.error("Frame processing error camera=%s: %s", self.camera_id, exc)

        cap.release()
        logger.info("Camera %s capture loop ended", self.camera_id)

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

    def process_frame(self, frame) -> None:
        """Detect, track, recognise and dispatch events for one frame."""
        ts = datetime.now(timezone.utc).isoformat()

        # 1. Object detection
        detections = self._detector.detect(frame) if self._detector else []

        # 2. Tracking
        tracks = []
        if self._tracker and detections:
            tracks = self._tracker.update(detections, frame)
        else:
            tracks = detections  # untracked fallback

        # 3. Separate persons and vehicles
        person_tracks = [t for t in tracks if t.get("class") in ("person", "face")]
        vehicle_tracks = [t for t in tracks if t.get("class") in ("car", "truck", "bus", "motorcycle")]

        # 4. Occupancy update
        h, w = frame.shape[:2] if hasattr(frame, "shape") else (1080, 1920)
        self.publish_detection({
            "type": "occupancy",
            "camera_id": self.camera_id,
            "timestamp": ts,
            "counts": {
                "people": len(person_tracks),
                "vehicles": len(vehicle_tracks),
            },
        })

        # 5. Face recognition
        if self._face_engine and person_tracks:
            for track in person_tracks:
                bbox = track.get("bbox", [])
                if not bbox:
                    continue
                try:
                    recognition = self._face_engine.recognize(frame, bbox)
                    if recognition:
                        self._detection_count += 1
                        self.publish_detection({
                            "type": "face_recognition",
                            "camera_id": self.camera_id,
                            "timestamp": ts,
                            "person_id": track.get("track_id"),
                            "employee_id": recognition.get("employee_id"),
                            "confidence": recognition.get("confidence", 0.0),
                            "bbox": bbox,
                        })
                except Exception as exc:
                    logger.debug("Face recognition error: %s", exc)

        # 6. ANPR
        if self._anpr_engine and vehicle_tracks:
            for track in vehicle_tracks:
                bbox = track.get("bbox", [])
                if not bbox:
                    continue
                try:
                    x1, y1, x2, y2 = [int(c) for c in bbox]
                    crop = frame[y1:y2, x1:x2]
                    if crop.size == 0:
                        continue
                    plates = self._anpr_engine.detect_plates(crop)
                    for plate in plates:
                        if plate.get("confidence", 0) > 0.5:
                            self._detection_count += 1
                            self.publish_detection({
                                "type": "vehicle_detection",
                                "camera_id": self.camera_id,
                                "timestamp": ts,
                                "plate_number": plate["plate_text"],
                                "confidence": plate["confidence"],
                                "vehicle_type": track.get("class", "car"),
                                "direction": "unknown",
                                "bbox": bbox,
                            })
                except Exception as exc:
                    logger.debug("ANPR error: %s", exc)

        # 7. Behavior detection
        if self._behavior_detector and tracks:
            behaviors = self._behavior_detector.update(tracks, (w, h))
            for bev in behaviors:
                self.publish_detection({
                    "type": "behavior",
                    "camera_id": self.camera_id,
                    "timestamp": ts,
                    "behavior_type": bev.get("type"),
                    "person_id": bev.get("track_id"),
                    "confidence": bev.get("confidence", 1.0),
                })
                if bev.get("type") in ("tailgating", "crowding"):
                    self.publish_alert({
                        "alert_type": f"behavior_{bev['type']}",
                        "severity": "warning",
                        "camera_id": self.camera_id,
                        "message": f"{bev['type'].title()} detected at camera {self.camera_id}",
                        "details": bev,
                    })

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish_detection(self, detection_data: Dict[str, Any]) -> None:
        """Publish detection event to RabbitMQ evap.detections queue."""
        if self._channel is None or not self._channel.is_open:
            return
        try:
            import pika
            self._channel.basic_publish(
                exchange="",
                routing_key="evap.detections",
                body=json.dumps(detection_data),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistent
                    content_type="application/json",
                ),
            )
        except Exception as exc:
            logger.warning("Detection publish failed: %s", exc)
            # Attempt reconnect
            try:
                self._init_rabbitmq()
            except Exception:
                pass

    def publish_alert(self, alert_data: Dict[str, Any]) -> None:
        """Publish an alert to RabbitMQ evap.alerts queue."""
        if self._channel is None or not self._channel.is_open:
            return
        try:
            import pika
            self._channel.basic_publish(
                exchange="",
                routing_key="evap.alerts",
                body=json.dumps(alert_data),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )
        except Exception as exc:
            logger.warning("Alert publish failed: %s", exc)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "running": self._running,
            "frames_processed": self._frame_count,
            "detections": self._detection_count,
        }


# ---------------------------------------------------------------------------
# Stub detector for environments without Phase 1-3 modules
# ---------------------------------------------------------------------------

class _StubDetector:
    def detect(self, frame) -> list:
        return []
