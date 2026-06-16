"""Unit tests for occupancy_engine.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from occupancy_engine import OccupancyEngine


def test_initial_state_is_zero():
    eng = OccupancyEngine()
    assert eng.current_people   == 0
    assert eng.current_vehicles == 0
    assert eng.peak_people      == 0


def test_person_entered_increments():
    eng = OccupancyEngine()
    eng.person_entered()
    eng.person_entered()
    assert eng.current_people == 2
    assert eng.total_in       == 2


def test_person_exited_decrements():
    eng = OccupancyEngine()
    eng.person_entered()
    eng.person_entered()
    eng.person_exited()
    assert eng.current_people == 1
    assert eng.total_out      == 1


def test_cannot_go_below_zero():
    eng = OccupancyEngine()
    eng.person_exited()    # no one was ever in
    assert eng.current_people == 0


def test_peak_tracks_maximum():
    eng = OccupancyEngine()
    eng.person_entered()
    eng.person_entered()
    eng.person_entered()
    eng.person_exited()
    assert eng.peak_people == 3
    assert eng.current_people == 2


def test_vehicle_counts_independent():
    eng = OccupancyEngine()
    eng.person_entered()
    eng.vehicle_entered()
    eng.vehicle_entered()
    assert eng.current_people   == 1
    assert eng.current_vehicles == 2


def test_average_is_rolling():
    eng = OccupancyEngine(average_window_seconds=10, estimated_fps=1.0)
    eng.person_entered()    # current = 1
    for _ in range(5):
        eng.tick()
    eng.person_entered()    # current = 2
    for _ in range(5):
        eng.tick()
    # 5 ticks at 1, 5 ticks at 2 → average = 1.5
    assert eng.avg_people == 1.5


def test_snapshot_returns_dict():
    eng = OccupancyEngine()
    eng.person_entered()
    snap = eng.snapshot()
    assert "current_people"   in snap
    assert "peak_people"      in snap
    assert "avg_people"       in snap
    assert snap["current_people"] == 1
