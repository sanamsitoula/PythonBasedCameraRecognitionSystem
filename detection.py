"""
detection.py – YOLOv11 person and vehicle detection.

Target classes (COCO indices):
    0  – person
    1  – bicycle
    2  – car
    3  – motorcycle
    5  – bus
    7  – truck

All other COCO classes are ignored.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# COCO class id → friendly label
TARGET_CLASSES: dict[int, str] = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# Friendly label → display label
DISPLAY_LABELS: dict[str, str] = {
    "person":     "People",
    "bicycle":    "Bicycles",
    "car":        "Cars",
    "motorcycle": "Motorcycles",
    "bus":        "Buses",
    "truck":      "Trucks",
}


@dataclass
class DetectionResult:
    people:      int = 0
    bicycles:    int = 0
    cars:        int = 0
    motorcycles: int = 0
    buses:       int = 0
    trucks:      int = 0
    frame_number: int = 0
    has_detection: bool = False


class YOLODetector:
    def __init__(self, model_path: str, confidence: float, iou: float, device: str = "auto"):
        self._model_path  = model_path
        self._confidence  = confidence
        self._iou         = iou
        self._device      = device
        self._model       = None
        self._using_gpu   = False
        self._frame_count = 0

        self._load_model()

    # ──────────────────────────── model loading ──────────────────────────────

    def _load_model(self) -> None:
        """Load YOLO model; fall back to CPU if GPU is unavailable."""
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError:
            raise RuntimeError(
                "ultralytics is not installed. Run: pip install ultralytics"
            )

        if not os.path.exists(self._model_path):
            log.warning(
                "Model not found at '%s'. Ultralytics will download it automatically.",
                self._model_path,
            )

        device = self._resolve_device()
        try:
            self._model = YOLO(self._model_path)
            # Warm-up inference on a blank frame to allocate GPU memory now
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            self._model.predict(dummy, device=device, verbose=False)
            self._using_gpu = (device != "cpu")
            log.info("YOLO model loaded on device='%s'", device)
            self._device = device
        except Exception as exc:
            log.error("GPU/model load failed (%s). Switching to CPU.", exc)
            try:
                self._model = YOLO(self._model_path)
                self._device = "cpu"
                self._using_gpu = False
                log.info("YOLO model loaded on CPU (fallback).")
            except Exception as exc2:
                log.critical("YOLO model could not be loaded at all: %s", exc2)
                raise

    def _resolve_device(self) -> str:
        if self._device.lower() != "auto":
            return self._device.lower()
        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                log.info("CUDA GPU detected: %s", torch.cuda.get_device_name(0))
                return "0"
        except ImportError:
            pass
        return "cpu"

    # ─────────────────────────── inference ──────────────────────────────────

    def detect(self, frame: np.ndarray) -> DetectionResult:
        """Run inference on a single frame and return counts per class."""
        self._frame_count += 1
        result = DetectionResult(frame_number=self._frame_count)

        if self._model is None:
            return result

        try:
            preds = self._model.predict(
                frame,
                device=self._device,
                conf=self._confidence,
                iou=self._iou,
                classes=list(TARGET_CLASSES.keys()),
                verbose=False,
            )
        except Exception as exc:
            log.error("YOLO inference error: %s", exc)
            return result

        if not preds:
            return result

        boxes = preds[0].boxes
        if boxes is None:
            return result

        for cls_id in boxes.cls.tolist():
            cls_id = int(cls_id)
            label = TARGET_CLASSES.get(cls_id)
            if label == "person":
                result.people += 1
            elif label == "bicycle":
                result.bicycles += 1
            elif label == "car":
                result.cars += 1
            elif label == "motorcycle":
                result.motorcycles += 1
            elif label == "bus":
                result.buses += 1
            elif label == "truck":
                result.trucks += 1

        result.has_detection = any([
            result.people, result.bicycles, result.cars,
            result.motorcycles, result.buses, result.trucks,
        ])
        return result

    @property
    def using_gpu(self) -> bool:
        return self._using_gpu

    @property
    def device_label(self) -> str:
        return "GPU" if self._using_gpu else "CPU"
