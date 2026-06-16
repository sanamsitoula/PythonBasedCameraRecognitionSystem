"""
face_recognition_engine.py
CCTV Phase 3 — Face Detection & Recognition Engine

Backend priority: insightface → deepface → opencv_dnn
Thread-safe, embedding-cached, production-ready.
"""

import logging
import threading
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import cv2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model download URLs
# ---------------------------------------------------------------------------
_PROTOTXT_URL = (
    "https://raw.githubusercontent.com/opencv/opencv/master/"
    "samples/dnn/face_detector/deploy.prototxt"
)
_CAFFEMODEL_URL = (
    "https://github.com/spmallick/learnopencv/raw/master/"
    "FaceDetectionComparison/models/res10_300x300_ssd_iter_140000_fp16.caffemodel"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class FaceDetection:
    bbox: tuple          # (x1, y1, x2, y2)
    confidence: float
    embedding: Optional[np.ndarray]  # 512-d or None


@dataclass
class FaceMatch:
    employee_id: str
    employee_name: str
    confidence: float    # 0.0–1.0 cosine similarity
    matched: bool        # True if above min_threshold


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class FaceRecognitionEngine:
    CONFIRMED_THRESHOLD = 0.95
    POSSIBLE_THRESHOLD  = 0.90
    MIN_THRESHOLD       = 0.85   # below this → no match

    # ------------------------------------------------------------------
    def __init__(
        self,
        backend: str = "insightface",
        min_confidence: float = 0.85,
        model_dir: str = "models/face",
    ):
        self._backend = backend.lower()
        self._min_confidence = min_confidence
        self._model_dir = model_dir
        self._lock = threading.Lock()

        # {employee_id: {"name": str, "mean_embedding": np.ndarray,
        #                "embeddings": [np.ndarray]}}
        self._employee_embeddings: dict = {}

        # Backend handles (lazy-loaded)
        self._insight_app   = None
        self._dnn_detector  = None   # cv2.dnn net for SSD face detector
        self._backend_ready = False

        os.makedirs(self._model_dir, exist_ok=True)
        self._init_backend()

    # ------------------------------------------------------------------
    # Backend initialisation
    # ------------------------------------------------------------------
    def _init_backend(self) -> None:
        if self._backend == "insightface":
            self._backend_ready = self._init_insightface()
            if not self._backend_ready:
                logger.warning("insightface unavailable — falling back to deepface")
                self._backend = "deepface"

        if self._backend == "deepface":
            self._backend_ready = self._init_deepface()
            if not self._backend_ready:
                logger.warning("deepface unavailable — falling back to opencv_dnn")
                self._backend = "opencv_dnn"

        if self._backend == "opencv_dnn":
            self._backend_ready = self._init_opencv_dnn()
            if not self._backend_ready:
                logger.error("All face-recognition backends failed to initialise.")

    def _init_insightface(self) -> bool:
        try:
            from insightface.app import FaceAnalysis  # type: ignore
            logger.info("Initialising InsightFace backend …")
            app = FaceAnalysis(
                name="buffalo_l",
                root=self._model_dir,
                allowed_modules=["detection", "recognition"],
            )
            app.prepare(ctx_id=0, det_size=(640, 640))
            self._insight_app = app
            logger.info("InsightFace backend ready.")
            return True
        except Exception as exc:
            logger.debug("InsightFace init failed: %s", exc)
            return False

    def _init_deepface(self) -> bool:
        try:
            import deepface  # type: ignore  # noqa: F401
            logger.info("DeepFace backend ready (Facenet512).")
            return True
        except Exception as exc:
            logger.debug("DeepFace init failed: %s", exc)
            return False

    def _init_opencv_dnn(self) -> bool:
        prototxt   = os.path.join(self._model_dir, "deploy.prototxt")
        caffemodel = os.path.join(self._model_dir, "res10_300x300_ssd_iter_140000_fp16.caffemodel")
        self._ensure_file(prototxt,   _PROTOTXT_URL,   "SSD prototxt")
        self._ensure_file(caffemodel, _CAFFEMODEL_URL, "SSD caffemodel")
        try:
            net = cv2.dnn.readNetFromCaffe(prototxt, caffemodel)
            self._dnn_detector = net
            logger.info("OpenCV DNN backend ready.")
            return True
        except Exception as exc:
            logger.error("OpenCV DNN init failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def _ensure_file(self, path: str, url: str, label: str) -> None:
        if os.path.exists(path):
            return
        logger.info("Downloading %s from %s …", label, url)
        try:
            urllib.request.urlretrieve(url, path)
            logger.info("Downloaded %s → %s", label, path)
        except Exception as exc:
            logger.error("Failed to download %s: %s", label, exc)

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Return cosine similarity in [0, 1] between two 1-D vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        cos = float(np.dot(a, b) / (norm_a * norm_b))
        # Clamp to [0, 1]; raw cosine is in [-1, 1]
        return max(0.0, min(1.0, (cos + 1.0) / 2.0))

    # ------------------------------------------------------------------
    # Face detection
    # ------------------------------------------------------------------
    def detect_faces(self, frame: np.ndarray) -> list:
        """Detect faces in *frame*; return list[FaceDetection] (no embeddings)."""
        if not self._backend_ready:
            return []

        if self._backend == "insightface":
            return self._detect_insightface(frame)
        if self._backend == "deepface":
            return self._detect_deepface(frame)
        if self._backend == "opencv_dnn":
            return self._detect_opencv_dnn(frame)
        return []

    def _detect_insightface(self, frame: np.ndarray) -> list:
        detections = []
        try:
            faces = self._insight_app.get(frame)
            for face in faces:
                box = face.bbox.astype(int)
                x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
                conf = float(face.det_score)
                emb  = face.embedding.astype(np.float32) if face.embedding is not None else None
                detections.append(FaceDetection(bbox=(x1, y1, x2, y2), confidence=conf, embedding=emb))
        except Exception as exc:
            logger.error("InsightFace detection error: %s", exc)
        return detections

    def _detect_deepface(self, frame: np.ndarray) -> list:
        detections = []
        try:
            from deepface import DeepFace  # type: ignore
            results = DeepFace.extract_faces(
                img_path=frame,
                detector_backend="opencv",
                enforce_detection=False,
            )
            for r in results:
                region = r.get("facial_area", {})
                x = region.get("x", 0)
                y = region.get("y", 0)
                w = region.get("w", 0)
                h = region.get("h", 0)
                conf = float(r.get("confidence", 0.5))
                detections.append(
                    FaceDetection(bbox=(x, y, x + w, y + h), confidence=conf, embedding=None)
                )
        except Exception as exc:
            logger.error("DeepFace detection error: %s", exc)
        return detections

    def _detect_opencv_dnn(self, frame: np.ndarray) -> list:
        detections = []
        if self._dnn_detector is None:
            return detections
        try:
            h, w = frame.shape[:2]
            blob = cv2.dnn.blobFromImage(
                cv2.resize(frame, (300, 300)), 1.0, (300, 300),
                (104.0, 177.0, 123.0), swapRB=False
            )
            self._dnn_detector.setInput(blob)
            out = self._dnn_detector.forward()   # shape (1,1,N,7)
            for i in range(out.shape[2]):
                conf = float(out[0, 0, i, 2])
                if conf < 0.5:
                    continue
                x1 = int(out[0, 0, i, 3] * w)
                y1 = int(out[0, 0, i, 4] * h)
                x2 = int(out[0, 0, i, 5] * w)
                y2 = int(out[0, 0, i, 6] * h)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                detections.append(
                    FaceDetection(bbox=(x1, y1, x2, y2), confidence=conf, embedding=None)
                )
        except Exception as exc:
            logger.error("OpenCV DNN detection error: %s", exc)
        return detections

    # ------------------------------------------------------------------
    # Embedding extraction
    # ------------------------------------------------------------------
    def embed_face(self, face_crop: np.ndarray) -> Optional[np.ndarray]:
        """Extract embedding from a face crop image.

        Returns a float32 numpy array (512-d for insightface/deepface) or None.
        For opencv_dnn fallback: tries deepface first, otherwise returns an
        L2-normalised 9216-d pixel descriptor and marks it via shape.
        """
        if face_crop is None or face_crop.size == 0:
            return None

        if self._backend == "insightface":
            return self._embed_insightface(face_crop)
        if self._backend == "deepface":
            return self._embed_deepface(face_crop)
        if self._backend == "opencv_dnn":
            # Prefer deepface for embeddings even in dnn detection mode
            emb = self._embed_deepface(face_crop)
            if emb is not None:
                return emb
            return self._embed_pixel_fallback(face_crop)
        return None

    def _embed_insightface(self, face_crop: np.ndarray) -> Optional[np.ndarray]:
        try:
            faces = self._insight_app.get(face_crop)
            if faces:
                return faces[0].embedding.astype(np.float32)
            # Fallback: run on padded version
            return None
        except Exception as exc:
            logger.debug("InsightFace embed error: %s", exc)
            return None

    def _embed_deepface(self, face_crop: np.ndarray) -> Optional[np.ndarray]:
        try:
            from deepface import DeepFace  # type: ignore
            result = DeepFace.represent(
                img_path=face_crop,
                model_name="Facenet512",
                enforce_detection=False,
            )
            if isinstance(result, list) and result:
                vec = np.array(result[0]["embedding"], dtype=np.float32)
                return vec
            if isinstance(result, dict):
                vec = np.array(result["embedding"], dtype=np.float32)
                return vec
        except Exception as exc:
            logger.debug("DeepFace embed error: %s", exc)
        return None

    def _embed_pixel_fallback(self, face_crop: np.ndarray) -> Optional[np.ndarray]:
        """96×96 L2-normalised pixel descriptor (9216-d). Functional but limited."""
        try:
            gray  = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (96, 96)).astype(np.float32)
            vec = resized.flatten()
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            logger.debug("Using pixel-fallback embedding (9216-d, not 512-d).")
            return vec
        except Exception as exc:
            logger.debug("Pixel fallback embed error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Combined detect + embed
    # ------------------------------------------------------------------
    def detect_and_embed(
        self,
        frame: np.ndarray,
        person_bbox: tuple = None,
    ) -> Optional[FaceDetection]:
        """Detect the best face and return it with an embedding.

        If *person_bbox* is provided, search only within that ROI.
        Returns the highest-confidence FaceDetection with embedding, or None.
        """
        if frame is None or frame.size == 0:
            return None

        search_frame = frame
        offset_x, offset_y = 0, 0

        if person_bbox is not None:
            x1, y1, x2, y2 = person_bbox
            h, w = frame.shape[:2]
            x1 = max(0, x1); y1 = max(0, y1)
            x2 = min(w, x2); y2 = min(h, y2)
            if x2 > x1 and y2 > y1:
                search_frame = frame[y1:y2, x1:x2]
                offset_x, offset_y = x1, y1
            else:
                return None

        detections = self.detect_faces(search_frame)
        if not detections:
            return None

        # Pick highest-confidence detection
        best = max(detections, key=lambda d: d.confidence)

        # Adjust bbox back to full-frame coordinates
        bx1, by1, bx2, by2 = best.bbox
        best.bbox = (
            bx1 + offset_x,
            by1 + offset_y,
            bx2 + offset_x,
            by2 + offset_y,
        )

        # Extract embedding if not already present (insightface provides it inline)
        if best.embedding is None:
            bx1, by1, bx2, by2 = best.bbox
            face_crop = frame[by1:by2, bx1:bx2]
            if face_crop.size > 0:
                best.embedding = self.embed_face(face_crop)

        return best

    # ------------------------------------------------------------------
    # Identification
    # ------------------------------------------------------------------
    def identify(self, embedding: np.ndarray) -> FaceMatch:
        """Compare *embedding* against loaded employee embeddings.

        Returns the best FaceMatch above MIN_THRESHOLD, or a no-match result.
        """
        no_match = FaceMatch(
            employee_id="",
            employee_name="",
            confidence=0.0,
            matched=False,
        )
        if embedding is None:
            return no_match

        best_score  = -1.0
        best_emp_id = ""
        best_name   = ""

        with self._lock:
            snapshot = dict(self._employee_embeddings)

        for emp_id, data in snapshot.items():
            mean_emb = data.get("mean_embedding")
            if mean_emb is None:
                continue
            # Dimension mismatch guard (pixel fallback vs 512-d)
            if embedding.shape != mean_emb.shape:
                continue
            score = self.cosine_similarity(embedding, mean_emb)
            if score > best_score:
                best_score  = score
                best_emp_id = emp_id
                best_name   = data.get("name", "")

        if best_score >= self._min_confidence:
            return FaceMatch(
                employee_id=best_emp_id,
                employee_name=best_name,
                confidence=best_score,
                matched=True,
            )
        return no_match

    # ------------------------------------------------------------------
    # Embedding database management
    # ------------------------------------------------------------------
    def load_embeddings(self, embeddings_dict: dict) -> None:
        """Load employee embeddings.

        embeddings_dict format:
            {
              "EMP001": {
                "name": "Alice Smith",
                "embeddings": [np.ndarray, ...]
              },
              ...
            }
        """
        processed = {}
        for emp_id, data in embeddings_dict.items():
            name   = data.get("name", "")
            embs   = [e for e in data.get("embeddings", []) if e is not None]
            if not embs:
                logger.warning("Employee %s has no valid embeddings — skipped.", emp_id)
                continue
            stack = np.stack(embs, axis=0).astype(np.float32)
            mean  = np.mean(stack, axis=0)
            norm  = np.linalg.norm(mean)
            if norm > 0:
                mean /= norm
            processed[emp_id] = {
                "name":           name,
                "embeddings":     embs,
                "mean_embedding": mean,
            }
        with self._lock:
            self._employee_embeddings = processed
        logger.info("Loaded embeddings for %d employees.", len(processed))

    def reload_embeddings(self, embeddings_dict: dict) -> None:
        """Thread-safe hot reload of employee embeddings."""
        logger.info("Hot-reloading employee embeddings …")
        self.load_embeddings(embeddings_dict)
