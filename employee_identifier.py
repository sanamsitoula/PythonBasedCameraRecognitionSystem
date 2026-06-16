"""
employee_identifier.py
CCTV Phase 3 — Identity Assignment Engine

Wraps FaceRecognitionEngine to assign and cache stable identities
(employee or visitor) to tracker tracks across cameras.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from face_recognition_engine import FaceRecognitionEngine, FaceMatch

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------
@dataclass
class IdentityResult:
    track_id: str
    camera_id: str
    person_id: str            # "EMP001" or "VISITOR-0001"
    identity_type: str        # "employee" | "visitor"
    employee_name: str        # "" for visitors
    department: str           # "" for visitors
    designation: str          # "" for visitors
    visitor_id: str           # "" for employees
    confidence: float
    recognition_status: str   # "confirmed" | "possible" | "unknown"
    first_seen: datetime
    last_seen: datetime
    _last_identified_frame: int = field(default=0, repr=False, compare=False)


# ---------------------------------------------------------------------------
# Identifier
# ---------------------------------------------------------------------------
class EmployeeIdentifier:
    CONFIRMED = 0.95
    POSSIBLE  = 0.90
    # below POSSIBLE → unknown / visitor

    RE_IDENTIFY_INTERVAL = 30   # frames between re-identification attempts

    # ------------------------------------------------------------------
    def __init__(
        self,
        face_engine: FaceRecognitionEngine,
        employee_db: dict,
    ):
        """
        Parameters
        ----------
        face_engine  : FaceRecognitionEngine instance (already initialised).
        employee_db  : {
              "EMP001": {
                  "name":        "Alice Smith",
                  "department":  "Engineering",
                  "designation": "Software Engineer",
              },
              ...
          }
        """
        self._face_engine   = face_engine
        self._lock          = threading.Lock()
        self._visitor_lock  = threading.Lock()

        # {employee_id: {"name":str, "department":str, "designation":str}}
        self._employee_db: dict = {}
        self._update_employee_db_internal(employee_db)

        # cache key: f"{camera_id}:{track_id}" → IdentityResult
        self._identity_cache: dict[str, IdentityResult] = {}

        # Visitor counter (session-scoped, monotonically increasing)
        self._visitor_counter: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _cache_key(self, track_id: str, camera_id: str) -> str:
        return f"{camera_id}:{track_id}"

    def _next_visitor_id(self) -> str:
        with self._visitor_lock:
            self._visitor_counter += 1
            return f"VISITOR-{self._visitor_counter:04d}"

    def _update_employee_db_internal(self, employee_db: dict) -> None:
        with self._lock:
            self._employee_db = {
                emp_id: {
                    "name":        data.get("name", ""),
                    "department":  data.get("department", ""),
                    "designation": data.get("designation", ""),
                }
                for emp_id, data in employee_db.items()
            }
        logger.info("Employee DB updated: %d records.", len(employee_db))

    def _resolve_status(self, confidence: float) -> str:
        if confidence >= self.CONFIRMED:
            return "confirmed"
        if confidence >= self.POSSIBLE:
            return "possible"
        return "unknown"

    def _build_employee_result(
        self,
        track_id: str,
        camera_id: str,
        match: FaceMatch,
        frame_number: int,
        existing: Optional["IdentityResult"] = None,
    ) -> "IdentityResult":
        with self._lock:
            db_entry = self._employee_db.get(match.employee_id, {})

        now    = datetime.now()
        status = self._resolve_status(match.confidence)

        return IdentityResult(
            track_id=track_id,
            camera_id=camera_id,
            person_id=match.employee_id,
            identity_type="employee",
            employee_name=match.employee_name or db_entry.get("name", ""),
            department=db_entry.get("department", ""),
            designation=db_entry.get("designation", ""),
            visitor_id="",
            confidence=match.confidence,
            recognition_status=status,
            first_seen=existing.first_seen if existing else now,
            last_seen=now,
            _last_identified_frame=frame_number,
        )

    def _build_visitor_result(
        self,
        track_id: str,
        camera_id: str,
        frame_number: int,
        existing: Optional["IdentityResult"] = None,
    ) -> "IdentityResult":
        now = datetime.now()

        # Reuse existing visitor_id if already assigned
        if existing and existing.identity_type == "visitor":
            vis_id = existing.visitor_id
        else:
            vis_id = self._next_visitor_id()

        return IdentityResult(
            track_id=track_id,
            camera_id=camera_id,
            person_id=vis_id,
            identity_type="visitor",
            employee_name="",
            department="",
            designation="",
            visitor_id=vis_id,
            confidence=0.0,
            recognition_status="unknown",
            first_seen=existing.first_seen if existing else now,
            last_seen=now,
            _last_identified_frame=frame_number,
        )

    # ------------------------------------------------------------------
    # Core identify
    # ------------------------------------------------------------------
    def identify(
        self,
        track_id: str,
        camera_id: str,
        frame: np.ndarray,
        person_bbox: tuple,
        frame_number: int = 0,
    ) -> "IdentityResult":
        """Return the best IdentityResult for this track.

        Uses cache and only re-runs face recognition every
        RE_IDENTIFY_INTERVAL frames (or when status is "unknown").
        """
        key = self._cache_key(track_id, camera_id)

        with self._lock:
            existing = self._identity_cache.get(key)

        # Decide whether to run recognition
        should_identify = True
        if existing is not None:
            frames_since = frame_number - existing._last_identified_frame
            already_confirmed = existing.recognition_status in ("confirmed", "possible")
            if already_confirmed and frames_since < self.RE_IDENTIFY_INTERVAL:
                # Update last_seen and return cached
                existing.last_seen = datetime.now()
                return existing
            if existing.recognition_status == "unknown" and frames_since < self.RE_IDENTIFY_INTERVAL:
                # Retry unknown periodically
                should_identify = False  # wait until interval

        if not should_identify and existing is not None:
            existing.last_seen = datetime.now()
            return existing

        # Run face detection + embedding + identification
        result = self._run_recognition(
            track_id=track_id,
            camera_id=camera_id,
            frame=frame,
            person_bbox=person_bbox,
            frame_number=frame_number,
            existing=existing,
        )

        with self._lock:
            self._identity_cache[key] = result

        return result

    def _run_recognition(
        self,
        track_id: str,
        camera_id: str,
        frame: np.ndarray,
        person_bbox: tuple,
        frame_number: int,
        existing: Optional["IdentityResult"],
    ) -> "IdentityResult":
        detection = self._face_engine.detect_and_embed(frame, person_bbox)

        if detection is None or detection.embedding is None:
            logger.debug(
                "track=%s cam=%s: no face/embedding detected — marking visitor.",
                track_id, camera_id,
            )
            return self._build_visitor_result(
                track_id, camera_id, frame_number, existing
            )

        face_match: FaceMatch = self._face_engine.identify(detection.embedding)

        if face_match.matched:
            logger.debug(
                "track=%s cam=%s: matched employee=%s conf=%.3f",
                track_id, camera_id, face_match.employee_id, face_match.confidence,
            )
            return self._build_employee_result(
                track_id, camera_id, face_match, frame_number, existing
            )

        logger.debug(
            "track=%s cam=%s: no employee match (best conf=%.3f) — visitor.",
            track_id, camera_id, face_match.confidence,
        )
        return self._build_visitor_result(
            track_id, camera_id, frame_number, existing
        )

    # ------------------------------------------------------------------
    # Cache accessors
    # ------------------------------------------------------------------
    def get_cached(self, track_id: str, camera_id: str) -> Optional["IdentityResult"]:
        """Return the cached IdentityResult for this track, or None."""
        key = self._cache_key(track_id, camera_id)
        with self._lock:
            return self._identity_cache.get(key)

    def evict(self, track_id: str, camera_id: str) -> None:
        """Remove a track from the cache (call when track closes)."""
        key = self._cache_key(track_id, camera_id)
        with self._lock:
            removed = self._identity_cache.pop(key, None)
        if removed:
            logger.debug(
                "Evicted track=%s cam=%s (was %s).",
                track_id, camera_id, removed.person_id,
            )

    # ------------------------------------------------------------------
    # Hot reload
    # ------------------------------------------------------------------
    def update_employee_db(self, employee_db: dict) -> None:
        """Hot-reload employee metadata (does NOT reload embeddings)."""
        self._update_employee_db_internal(employee_db)

    # ------------------------------------------------------------------
    # Active-entity queries
    # ------------------------------------------------------------------
    def get_active_employees(self) -> list:
        """Return all cached IdentityResults whose identity_type == 'employee'."""
        with self._lock:
            return [
                r for r in self._identity_cache.values()
                if r.identity_type == "employee"
            ]

    def get_active_visitors(self) -> list:
        """Return all cached IdentityResults whose identity_type == 'visitor'."""
        with self._lock:
            return [
                r for r in self._identity_cache.values()
                if r.identity_type == "visitor"
            ]
