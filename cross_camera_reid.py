"""
cross_camera_reid.py
Links the same person (employee or visitor) across multiple cameras
using cosine similarity of face embeddings.
Thread-safe, production-ready.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import threading
import logging

import numpy as np

log = logging.getLogger("analytics")


@dataclass
class UnifiedTrack:
    unified_id: str                # EMP001 or VISITOR-0001
    camera_tracks: dict            # {camera_id: track_id}
    last_embedding: Optional[np.ndarray]  # most recent face embedding
    last_seen: datetime
    confidence: float              # similarity score of the last re-id link


class CrossCameraReID:
    """
    Maintains a registry of unified tracks (one per person) and resolves
    new camera observations to existing identities via embedding similarity.

    Thread-safety: a single Lock guards all mutable state.
    """

    REID_THRESHOLD = 0.88  # cosine similarity required to link tracks

    def __init__(self, reid_threshold: float = 0.88) -> None:
        self.reid_threshold = reid_threshold

        # "camera_id:track_id" → unified_id
        self._track_map: dict[str, str] = {}
        # unified_id → UnifiedTrack
        self._unified_tracks: dict[str, UnifiedTrack] = {}
        # unified_id → list of {"camera_id": str, "track_id": str, "timestamp": datetime}
        self._journey: dict[str, list] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(camera_id: str, track_id: str) -> str:
        return f"{camera_id}:{track_id}"

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """
        Compute cosine similarity between two 1-D float arrays.
        Returns 0.0 if either vector has zero norm.
        """
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_track(
        self,
        camera_id: str,
        track_id: str,
        unified_id: str,
        embedding: Optional[np.ndarray],
        timestamp: datetime,
    ) -> None:
        """
        Register a confirmed camera→track→unified_id mapping.
        Updates the UnifiedTrack's embedding and journey log.
        Creates the UnifiedTrack if it does not yet exist.
        """
        key = self._make_key(camera_id, track_id)
        with self._lock:
            # Create unified track if needed
            if unified_id not in self._unified_tracks:
                self._unified_tracks[unified_id] = UnifiedTrack(
                    unified_id=unified_id,
                    camera_tracks={},
                    last_embedding=None,
                    last_seen=timestamp,
                    confidence=1.0,
                )
                self._journey[unified_id] = []
                log.info("New unified track: %s", unified_id)

            track = self._unified_tracks[unified_id]
            track.camera_tracks[camera_id] = track_id
            track.last_seen = timestamp
            if embedding is not None:
                track.last_embedding = embedding

            # Map the camera+track key to unified_id
            self._track_map[key] = unified_id

            # Append to journey
            self._journey[unified_id].append(
                {"camera_id": camera_id, "track_id": track_id, "timestamp": timestamp}
            )
            log.debug(
                "register_track: %s → %s at %s", key, unified_id, timestamp
            )

    def find_match(
        self,
        camera_id: str,
        track_id: str,
        embedding: np.ndarray,
    ) -> Optional[str]:
        """
        Given an embedding from a new/unknown camera track, search all
        registered unified tracks for a cosine-similarity match above
        the configured threshold.

        Returns the unified_id of the best match, or None.
        Does NOT register the track — call register_track afterwards.
        """
        key = self._make_key(camera_id, track_id)
        with self._lock:
            # If already registered, return immediately
            if key in self._track_map:
                return self._track_map[key]

            best_id: Optional[str] = None
            best_score = -1.0

            for uid, track in self._unified_tracks.items():
                if track.last_embedding is None:
                    continue
                score = self._cosine_similarity(embedding, track.last_embedding)
                if score > best_score:
                    best_score = score
                    best_id = uid

            if best_id is not None and best_score >= self.reid_threshold:
                log.info(
                    "find_match: %s matched to %s (score=%.4f)",
                    key, best_id, best_score,
                )
                return best_id

            log.debug(
                "find_match: no match for %s (best score=%.4f, threshold=%.4f)",
                key, best_score, self.reid_threshold,
            )
            return None

    def get_unified_id(self, camera_id: str, track_id: str) -> Optional[str]:
        """
        Return the unified_id already registered for this camera+track, or None.
        """
        key = self._make_key(camera_id, track_id)
        with self._lock:
            return self._track_map.get(key)

    def remove_track(self, camera_id: str, track_id: str) -> None:
        """
        Remove a camera+track mapping when the track closes.
        Also removes the track from the corresponding UnifiedTrack.camera_tracks.
        """
        key = self._make_key(camera_id, track_id)
        with self._lock:
            unified_id = self._track_map.pop(key, None)
            if unified_id is None:
                return
            track = self._unified_tracks.get(unified_id)
            if track and camera_id in track.camera_tracks:
                del track.camera_tracks[camera_id]
            log.debug("remove_track: removed %s (unified=%s)", key, unified_id)

    def get_active_tracks(self) -> list[UnifiedTrack]:
        """
        Return all UnifiedTrack objects that still have at least one
        active camera+track mapping.
        """
        with self._lock:
            active_ids = set(self._track_map.values())
            return [
                self._unified_tracks[uid]
                for uid in active_ids
                if uid in self._unified_tracks
            ]

    def get_journey(self, unified_id: str) -> list[dict]:
        """
        Return the sorted list of camera appearances for unified_id.
        Each entry: {"camera_id": str, "track_id": str, "timestamp": datetime}
        """
        with self._lock:
            entries = self._journey.get(unified_id, [])
            return sorted(entries, key=lambda e: e["timestamp"])
