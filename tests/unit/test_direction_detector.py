"""Unit tests for direction_detector.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from direction_detector import DirectionDetector


def _feed(det: DirectionDetector, tid: str, points: list):
    result = None
    for p in points:
        result = det.update(tid, p)
    return result


def test_left_to_right():
    det = DirectionDetector(min_movement=10)
    pts = [(x * 10, 100) for x in range(12)]
    result = _feed(det, "P-0001", pts)
    assert result is not None
    assert result.direction == "LEFT → RIGHT"


def test_right_to_left():
    det = DirectionDetector(min_movement=10)
    pts = [(120 - x * 10, 100) for x in range(12)]
    result = _feed(det, "P-0001", pts)
    assert result is not None
    assert result.direction == "RIGHT → LEFT"


def test_top_to_bottom():
    det = DirectionDetector(min_movement=10)
    pts = [(100, y * 10) for y in range(12)]
    result = _feed(det, "P-0001", pts)
    assert result is not None
    assert result.direction == "TOP → BOTTOM"


def test_bottom_to_top():
    det = DirectionDetector(min_movement=10)
    pts = [(100, 120 - y * 10) for y in range(12)]
    result = _feed(det, "P-0001", pts)
    assert result is not None
    assert result.direction == "BOTTOM → TOP"


def test_stationary():
    det = DirectionDetector(min_movement=15)
    pts = [(100 + i % 3, 100 + i % 2) for i in range(12)]   # tiny jitter
    result = _feed(det, "P-0001", pts)
    assert result is not None
    assert result.direction == "STATIONARY"


def test_insufficient_history_returns_none():
    det = DirectionDetector(min_samples=8)
    result = _feed(det, "P-0001", [(i * 10, 50) for i in range(4)])
    assert result is None


def test_remove_clears_history():
    det = DirectionDetector()
    for i in range(10):
        det.update("P-0001", (i * 10, 50))
    det.remove("P-0001")
    result = det.update("P-0001", (200, 50))
    assert result is None   # history was cleared


def test_multiple_independent_tracks():
    det = DirectionDetector(min_movement=10)
    for i in range(12):
        det.update("P-0001", (i * 10, 100))
        det.update("P-0002", (100, i * 10))
    r1 = det.get_direction("P-0001")
    r2 = det.get_direction("P-0002")
    assert r1 == "LEFT → RIGHT"
    assert r2 == "TOP → BOTTOM"
