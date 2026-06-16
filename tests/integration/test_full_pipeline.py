"""
Integration test: synthetic frames through tracker analytics pipeline.

Tests the analytics modules together without needing a real camera or GPU.
ByteTracker is mocked to return synthetic TrackedObject data.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tracker import TrackedObject, TrackingFrame
from direction_detector import DirectionDetector
from line_counter import LineCounter, LineConfig
from zone_manager import ZoneManager, ZoneConfig
from occupancy_engine import OccupancyEngine
from vehicle_analytics import VehicleAnalytics


def _make_track(tid, is_person, cx, cy, class_name="person"):
    return TrackedObject(
        track_id   = tid,
        raw_id     = int(tid.split("-")[1]),
        class_name = class_name,
        confidence = 0.90,
        bbox       = (cx - 30, cy - 60, cx + 30, cy + 60),
        center     = (cx, cy),
        is_person  = is_person,
        is_vehicle = not is_person,
        first_seen = datetime.now(),
        last_seen  = datetime.now(),
        age_frames = 5,
    )


def test_person_crosses_line_and_occupancy_increments():
    line    = LineConfig(label="Gate", p1=(0, 300), p2=(640, 300), entry_direction="TOP_TO_BOTTOM")
    counter = LineCounter([line])
    occ     = OccupancyEngine()

    # simulate track moving from y=200 to y=400
    events = counter.update("P-0001", "person", (320, 400), (320, 200), frame_number=10)
    assert len(events) == 1
    assert events[0].direction == "entry"
    occ.person_entered()
    assert occ.current_people == 1


def test_person_zone_path_tracking():
    zones = [
        ZoneConfig(zone_id="z1", label="Lobby",  coords=[[0,0],[320,0],[320,600],[0,600]]),
        ZoneConfig(zone_id="z2", label="Office", coords=[[320,0],[640,0],[640,600],[320,600]]),
    ]
    mgr = ZoneManager(zones)

    # person starts in Lobby
    events = mgr.update("P-0001", "person", (100, 100), frame_number=1)
    assert any(e.zone_label == "Lobby" and e.event_type == "enter" for e in events)

    # person moves to Office
    events = mgr.update("P-0001", "person", (400, 100), frame_number=20)
    labels = [(e.zone_label, e.event_type) for e in events]
    assert ("Lobby",  "exit")  in labels
    assert ("Office", "enter") in labels

    path = mgr.get_path("P-0001")
    assert path == ["Lobby", "Office"]


def test_direction_detected_after_consistent_movement():
    det  = DirectionDetector(min_movement=10)
    for i in range(15):
        det.update("P-0001", (i * 12, 200))
    direction = det.get_direction("P-0001")
    assert direction == "LEFT → RIGHT"


def test_vehicle_analytics_cumulative():
    va = VehicleAnalytics()
    now = datetime.now()
    for i in range(5):
        va.update(f"V-{i:04d}", "car", now)
    va.update("V-0100", "motorcycle", now)
    counts = va.get_cumulative_counts()
    assert counts["car"]        == 5
    assert counts["motorcycle"] == 1
    assert va.active_count      == 6


def test_pipeline_multiple_tracks():
    """Simulate 5 people walking through a zone and crossing a line."""
    line  = LineConfig(label="Gate", p1=(0, 300), p2=(640, 300), entry_direction="TOP_TO_BOTTOM")
    counter = LineCounter([line])
    occ     = OccupancyEngine()
    det     = DirectionDetector()

    for i in range(1, 6):
        tid = f"P-{i:04d}"
        # Move from y=100 (above line) to y=500 (below line)
        for y in range(100, 501, 40):
            det.update(tid, (320, y))
        # Final crossing
        counter.update(tid, "person", (320, 500), (320, 100), frame_number=i * 10)
        occ.person_entered()

    assert occ.current_people == 5
    assert occ.total_in       == 5
    assert counter.totals()["entries"] == 5

    # all move left→right in direction
    direction = det.get_direction("P-0001")
    assert direction == "TOP → BOTTOM"
