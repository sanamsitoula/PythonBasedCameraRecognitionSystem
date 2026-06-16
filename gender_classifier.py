"""
gender_classifier.py – Single-pass, cached gender classification.

Rules:
  * Classify only ONCE per track ID per session (cached after first result).
  * Run in a ThreadPoolExecutor so it never blocks the main loop.

Backend fallback chain (tried in order until one works):
  1. deepface    – pip install deepface
  2. insightface – pip install insightface onnxruntime
  3. opencv_dnn  – built-in; downloads ~27 MB Caffe model on first run
"""

import logging
import os
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

log = logging.getLogger("gender")

BBOX_MIN_HEIGHT = 80    # pixels – skip bboxes shorter than this

# Mean values for the gender Caffe model (BGR order)
_DNN_MEAN  = (78.4263377603, 87.7689143744, 114.895847746)
_DNN_SIZE  = (227, 227)
_DNN_LABELS = ["Male", "Female"]

# Stable URLs for the Levi & Hassner gender Caffe model
_PROTO_URL = (
    "https://raw.githubusercontent.com/spmallick/learnopencv"
    "/master/AgeGender/gender_deploy.prototxt"
)
_MODEL_URL = (
    "https://github.com/spmallick/learnopencv"
    "/raw/master/AgeGender/gender_net.caffemodel"
)


@dataclass
class GenderResult:
    track_id:      str
    gender:        str     # "Male", "Female", or "Unknown"
    confidence:    float   # 0.0–1.0
    backend:       str
    classified_at: datetime


class GenderClassifier:
    def __init__(
        self,
        backend:              str   = "deepface",
        confidence_threshold: float = 0.65,
        min_bbox_height:      int   = BBOX_MIN_HEIGHT,
        max_workers:          int   = 2,
    ):
        self._backend    = backend.lower()
        self._threshold  = confidence_threshold
        self._min_height = min_bbox_height
        self._executor   = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="gender")
        self._lock       = threading.Lock()

        self._cache:   dict[str, GenderResult] = {}
        self._pending: dict[str, Future]        = {}

        # set by _probe_opencv_dnn
        self._gender_net = None

        self._available = False
        self._load()

    # ─────────────────────────── init / probes ───────────────────────────────

    def _load(self) -> None:
        """Try each backend in priority order; stop at the first that works."""
        _ORDER = {
            "deepface":    ["deepface", "insightface", "opencv_dnn"],
            "insightface": ["insightface", "opencv_dnn"],
            "opencv_dnn":  ["opencv_dnn"],
        }
        to_try = _ORDER.get(self._backend, ["deepface", "insightface", "opencv_dnn"])

        for backend in to_try:
            if backend == "deepface" and self._probe_deepface():
                self._backend   = "deepface"
                self._available = True
                return
            if backend == "insightface" and self._probe_insightface():
                self._backend   = "insightface"
                self._available = True
                return
            if backend == "opencv_dnn" and self._probe_opencv_dnn():
                self._backend   = "opencv_dnn"
                self._available = True
                return

        log.warning("Gender classification unavailable – results will be 'Unknown'.")

    def _probe_deepface(self) -> bool:
        try:
            import deepface  # type: ignore   # noqa: F401
            log.info("DeepFace ready for gender classification.")
            return True
        except Exception as exc:
            log.warning("DeepFace not available (%s). Trying InsightFace…", exc)
            return False

    def _probe_insightface(self) -> bool:
        try:
            import insightface  # type: ignore
            self._if_app = insightface.app.FaceAnalysis(
                allowed_modules=["detection", "genderage"]
            )
            self._if_app.prepare(ctx_id=0, det_size=(320, 320))
            log.info("InsightFace ready for gender classification.")
            return True
        except Exception as exc:
            log.warning("InsightFace not available (%s). Trying OpenCV DNN…", exc)
            return False

    def _probe_opencv_dnn(self) -> bool:
        """Download the Caffe gender model if needed, then load via cv2.dnn."""
        import cv2

        model_dir  = os.path.join("models", "gender")
        os.makedirs(model_dir, exist_ok=True)
        proto_path = os.path.join(model_dir, "gender_deploy.prototxt")
        model_path = os.path.join(model_dir, "gender_net.caffemodel")

        for url, path, label in [
            (_PROTO_URL, proto_path, "prototxt (~3 KB)"),
            (_MODEL_URL, model_path, "caffemodel (~27 MB)"),
        ]:
            if not os.path.exists(path):
                log.info("Gender: downloading %s — please wait…", label)
                try:
                    urllib.request.urlretrieve(url, path)
                    log.info("Gender: %s downloaded.", label)
                except Exception as exc:
                    log.warning("Gender: download failed for %s: %s", label, exc)
                    return False

        try:
            self._gender_net = cv2.dnn.readNet(proto_path, model_path)
            log.info("OpenCV DNN gender model ready (no extra pip packages needed).")
            return True
        except Exception as exc:
            log.warning("OpenCV DNN gender model load failed: %s", exc)
            return False

    # ─────────────────────────── public API ──────────────────────────────────

    def classify_async(self, track_id: str, frame: np.ndarray, bbox: tuple) -> None:
        """
        Submit a non-blocking classification.
        Result stored in cache when done; read with get_cached().
        """
        with self._lock:
            if track_id in self._cache or track_id in self._pending:
                return
            if not self._available:
                self._cache[track_id] = self._unknown(track_id)
                return

        x1, y1, x2, y2 = bbox
        if (y2 - y1) < self._min_height:
            return

        crop = self._crop(frame, bbox)
        if crop is None:
            return

        future = self._executor.submit(self._classify_sync, track_id, crop)
        with self._lock:
            self._pending[track_id] = future

        future.add_done_callback(lambda f: self._store_result(track_id, f))

    def get_cached(self, track_id: str) -> Optional[GenderResult]:
        with self._lock:
            return self._cache.get(track_id)

    def is_classified(self, track_id: str) -> bool:
        with self._lock:
            return track_id in self._cache

    def evict(self, track_id: str) -> None:
        with self._lock:
            self._cache.pop(track_id, None)
            self._pending.pop(track_id, None)

    def live_counts(self) -> dict:
        with self._lock:
            counts = {"Male": 0, "Female": 0, "Unknown": 0}
            for r in self._cache.values():
                counts[r.gender] = counts.get(r.gender, 0) + 1
        return counts

    @property
    def cache_size(self) -> int:
        with self._lock:
            return len(self._cache)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)

    # ─────────────────────────── internals ───────────────────────────────────

    def _store_result(self, track_id: str, future: "Future") -> None:
        try:
            result = future.result()
        except Exception as exc:
            log.debug("Gender future error for %s: %s", track_id, exc)
            result = self._unknown(track_id)
        with self._lock:
            self._cache[track_id] = result
            self._pending.pop(track_id, None)
        if result.gender != "Unknown":
            log.info(
                "%s → gender=%s conf=%.1f%% [%s]",
                track_id, result.gender, result.confidence * 100, result.backend,
            )

    def _classify_sync(self, track_id: str, crop: np.ndarray) -> GenderResult:
        if self._backend == "deepface":
            return self._run_deepface(track_id, crop)
        if self._backend == "insightface":
            return self._run_insightface(track_id, crop)
        if self._backend == "opencv_dnn":
            return self._run_opencv_dnn(track_id, crop)
        return self._unknown(track_id)

    # ─────────────────────────── backend runners ─────────────────────────────

    def _run_deepface(self, track_id: str, crop: np.ndarray) -> GenderResult:
        try:
            from deepface import DeepFace  # type: ignore
            analysis = DeepFace.analyze(
                crop,
                actions           = ["gender"],
                enforce_detection = False,
                silent            = True,
            )
            if isinstance(analysis, list):
                analysis = analysis[0]
            gender_data = analysis.get("gender", {})
            if isinstance(gender_data, str):
                gender, conf = gender_data, 0.80
            else:
                m = gender_data.get("Man", 0)
                w = gender_data.get("Woman", 0)
                gender, conf = ("Male", m / 100.0) if m >= w else ("Female", w / 100.0)
            if conf < self._threshold:
                return self._unknown(track_id)
            return GenderResult(
                track_id=track_id, gender=gender,
                confidence=round(conf, 3), backend="deepface",
                classified_at=datetime.now(),
            )
        except Exception as exc:
            log.debug("DeepFace error for %s: %s", track_id, exc)
            return self._unknown(track_id)

    def _run_insightface(self, track_id: str, crop: np.ndarray) -> GenderResult:
        try:
            faces = self._if_app.get(crop)
            if not faces:
                return self._unknown(track_id)
            face   = faces[0]
            gender = "Male" if face.gender == 1 else "Female"
            conf   = float(face.det_score) if hasattr(face, "det_score") else 0.80
            if conf < self._threshold:
                return self._unknown(track_id)
            return GenderResult(
                track_id=track_id, gender=gender,
                confidence=round(conf, 3), backend="insightface",
                classified_at=datetime.now(),
            )
        except Exception as exc:
            log.debug("InsightFace error for %s: %s", track_id, exc)
            return self._unknown(track_id)

    def _run_opencv_dnn(self, track_id: str, crop: np.ndarray) -> GenderResult:
        import cv2
        try:
            blob = cv2.dnn.blobFromImage(crop, 1.0, _DNN_SIZE, _DNN_MEAN, swapRB=False)
            self._gender_net.setInput(blob)
            preds  = self._gender_net.forward()
            idx    = int(preds[0].argmax())
            gender = _DNN_LABELS[idx]
            conf   = float(preds[0][idx])
            if conf < self._threshold:
                return self._unknown(track_id)
            return GenderResult(
                track_id=track_id, gender=gender,
                confidence=round(conf, 3), backend="opencv_dnn",
                classified_at=datetime.now(),
            )
        except Exception as exc:
            log.debug("OpenCV DNN gender error for %s: %s", track_id, exc)
            return self._unknown(track_id)

    # ─────────────────────────── static helpers ──────────────────────────────

    @staticmethod
    def _unknown(track_id: str) -> GenderResult:
        return GenderResult(
            track_id=track_id, gender="Unknown",
            confidence=0.0, backend="none",
            classified_at=datetime.now(),
        )

    @staticmethod
    def _crop(frame: np.ndarray, bbox: tuple) -> Optional[np.ndarray]:
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        pad_x = max(0, int((x2 - x1) * 0.08))
        pad_y = max(0, int((y2 - y1) * 0.08))
        crop = frame[max(0, y1 - pad_y):min(h, y2 + pad_y),
                     max(0, x1 - pad_x):min(w, x2 + pad_x)]
        return crop if crop.size > 0 else None
