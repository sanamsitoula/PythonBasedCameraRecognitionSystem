"""
ANPR (Automatic Number Plate Recognition) engine.
Uses YOLO for plate detection and EasyOCR / PaddleOCR for text extraction.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class ANPREngine:
    """
    License plate detection and recognition.

    Detection:  Ultralytics YOLO (trained on license plates)
    OCR:        EasyOCR (primary) with PaddleOCR fallback
    """

    # Common plate character substitutions from OCR noise
    _OCR_CORRECTIONS = {
        "O": "0",  # applied only in numeric segments
        "I": "1",
        "S": "5",
        "Z": "2",
        "B": "8",
    }

    def __init__(self, model_path: str):
        self.model_path = str(model_path)
        self._detector = None
        self._ocr = None
        self._ocr_type: Optional[str] = None
        self._load_models()

    def _load_models(self) -> None:
        # YOLO plate detector
        try:
            from ultralytics import YOLO  # type: ignore[import]
            if Path(self.model_path).exists():
                self._detector = YOLO(self.model_path)
                logger.info("ANPR: YOLO model loaded from %s", self.model_path)
            else:
                logger.warning("ANPR: model not found at %s – detection disabled", self.model_path)
        except ImportError:
            logger.warning("ANPR: ultralytics not installed – detection disabled")

        # OCR backend: EasyOCR preferred
        try:
            import easyocr  # type: ignore[import]
            self._ocr = easyocr.Reader(["en"], gpu=False, verbose=False)
            self._ocr_type = "easyocr"
            logger.info("ANPR: EasyOCR loaded")
        except ImportError:
            try:
                from paddleocr import PaddleOCR  # type: ignore[import]
                self._ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
                self._ocr_type = "paddleocr"
                logger.info("ANPR: PaddleOCR loaded as fallback")
            except ImportError:
                logger.warning("ANPR: No OCR engine available – text extraction disabled")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_plates(self, frame: np.ndarray) -> list[dict]:
        """
        Detect license plates in a frame.

        Returns list of:
            {
              "plate_text": str,
              "confidence": float,
              "bbox": [x1, y1, x2, y2],
              "country_estimate": str,
            }
        """
        if self._detector is None or frame is None or frame.size == 0:
            return []

        results = []
        try:
            yolo_results = self._detector(frame, verbose=False, conf=0.4)
            for result in yolo_results:
                for box in result.boxes:
                    conf = float(box.conf[0])
                    if conf < 0.4:
                        continue
                    x1, y1, x2, y2 = [int(c) for c in box.xyxy[0]]
                    # Pad slightly for better OCR
                    h, w = frame.shape[:2]
                    pad = 5
                    x1p = max(0, x1 - pad)
                    y1p = max(0, y1 - pad)
                    x2p = min(w, x2 + pad)
                    y2p = min(h, y2 + pad)
                    plate_crop = frame[y1p:y2p, x1p:x2p]
                    if plate_crop.size == 0:
                        continue

                    plate_text, ocr_conf = self.extract_plate_text(plate_crop)
                    if not plate_text:
                        continue

                    plate_text = self.normalize_plate(plate_text)
                    country = self._estimate_country(plate_text)

                    results.append({
                        "plate_text": plate_text,
                        "confidence": round(min(conf, ocr_conf), 4),
                        "bbox": [x1, y1, x2, y2],
                        "country_estimate": country,
                    })
        except Exception as exc:
            logger.error("ANPR detect_plates error: %s", exc)

        return results

    def extract_plate_text(self, plate_image: np.ndarray) -> tuple[str, float]:
        """
        Run OCR on a cropped plate image.

        Returns (plate_text, confidence) or ("", 0.0) on failure.
        """
        if self._ocr is None or plate_image is None or plate_image.size == 0:
            return "", 0.0

        try:
            if self._ocr_type == "easyocr":
                return self._easyocr_extract(plate_image)
            elif self._ocr_type == "paddleocr":
                return self._paddleocr_extract(plate_image)
        except Exception as exc:
            logger.debug("OCR extraction error: %s", exc)
        return "", 0.0

    def normalize_plate(self, raw_text: str) -> str:
        """
        Clean up OCR noise:
        - Uppercase
        - Remove spaces and special chars except hyphen and digits/letters
        - Apply common character substitutions in numeric segments
        """
        if not raw_text:
            return ""

        text = raw_text.upper().strip()
        # Keep only alphanumeric and hyphen
        text = re.sub(r"[^A-Z0-9\-]", "", text)
        # Remove isolated hyphens at start/end
        text = text.strip("-")
        # Fix O→0 in purely numeric regions (e.g. Indian plates: "MH 01 O1234")
        text = self._fix_numeric_confusion(text)
        return text

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _easyocr_extract(self, image: np.ndarray) -> tuple[str, float]:
        results = self._ocr.readtext(image, detail=1, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- ")
        if not results:
            return "", 0.0
        # Concatenate all detected text segments
        texts = []
        confs = []
        for (_bbox, text, conf) in results:
            texts.append(text.upper().strip())
            confs.append(conf)
        combined = " ".join(texts)
        avg_conf = sum(confs) / len(confs) if confs else 0.0
        return combined, round(avg_conf, 4)

    def _paddleocr_extract(self, image: np.ndarray) -> tuple[str, float]:
        result = self._ocr.ocr(image, cls=True)
        if not result or not result[0]:
            return "", 0.0
        texts = []
        confs = []
        for line in result[0]:
            if line:
                text_info = line[1]
                texts.append(text_info[0].upper())
                confs.append(text_info[1])
        combined = "".join(texts)
        avg_conf = sum(confs) / len(confs) if confs else 0.0
        return combined, round(avg_conf, 4)

    def _fix_numeric_confusion(self, text: str) -> str:
        """
        Apply O→0 substitution only in positions that should be digits.
        Heuristic: if a character is between digits, treat O/I/S/Z/B as digit equivalents.
        """
        result = list(text)
        for i, ch in enumerate(result):
            if ch in self._OCR_CORRECTIONS:
                # Check if surrounded by digits
                prev_digit = i > 0 and result[i - 1].isdigit()
                next_digit = i < len(result) - 1 and result[i + 1].isdigit()
                if prev_digit or next_digit:
                    result[i] = self._OCR_CORRECTIONS[ch]
        return "".join(result)

    def _estimate_country(self, plate_text: str) -> str:
        """
        Rough heuristic to guess plate country from format.
        Returns ISO 2-letter country code or 'UNKNOWN'.
        """
        # Indian plates: XX 00 XX 0000 or XX-00-XX-0000
        if re.match(r"^[A-Z]{2}[\-]?\d{2}[\-]?[A-Z]{1,3}[\-]?\d{4}$", plate_text):
            return "IN"
        # UAE: 1-5 digits + letter + 1-5 digits
        if re.match(r"^\d{1,5}[A-Z]\d{1,5}$", plate_text):
            return "AE"
        # Generic European: 2+ letters + 3-4 digits
        if re.match(r"^[A-Z]{2,3}\d{3,4}[A-Z]{0,3}$", plate_text):
            return "EU"
        return "UNKNOWN"
