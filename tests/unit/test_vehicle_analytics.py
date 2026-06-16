"""Unit tests for vehicle_analytics.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import datetime
from vehicle_analytics import VehicleAnalytics


def _now():
    return datetime.now()


def test_new_vehicle_creates_record():
    va = VehicleAnalytics()
    rec = va.update("V-0001", "car", _now())
    assert rec.track_id     == "V-0001"
    assert rec.vehicle_type == "car"
    assert rec.is_active


def test_cumulative_count_increments():
    va = VehicleAnalytics()
    va.update("V-0001", "car", _now())
    va.update("V-0002", "car", _now())
    va.update("V-0003", "motorcycle", _now())
    counts = va.get_cumulative_counts()
    assert counts["car"]        == 2
    assert counts["motorcycle"] == 1


def test_active_count():
    va = VehicleAnalytics()
    va.update("V-0001", "car", _now())
    va.update("V-0002", "bus", _now())
    assert va.active_count == 2


def test_close_track_removes_from_active():
    va = VehicleAnalytics()
    va.update("V-0001", "car", _now())
    va.close_track("V-0001")
    assert va.active_count == 0
    rec = va.get_record("V-0001")
    assert not rec.is_active
    assert rec.exit_time is not None


def test_update_existing_track_does_not_double_count():
    va = VehicleAnalytics()
    now = _now()
    va.update("V-0001", "car", now)
    va.update("V-0001", "car", now)   # same track, second frame
    counts = va.get_cumulative_counts()
    assert counts["car"] == 1


def test_set_direction():
    va = VehicleAnalytics()
    va.update("V-0001", "truck", _now())
    va.set_direction("V-0001", "LEFT → RIGHT")
    rec = va.get_record("V-0001")
    assert rec.direction == "LEFT → RIGHT"


def test_get_active_counts_by_type():
    va = VehicleAnalytics()
    va.update("V-0001", "car", _now())
    va.update("V-0002", "car", _now())
    va.update("V-0003", "motorcycle", _now())
    active = va.get_active_counts()
    assert active.get("car", 0)        == 2
    assert active.get("motorcycle", 0) == 1
