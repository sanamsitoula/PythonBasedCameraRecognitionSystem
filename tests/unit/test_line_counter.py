"""Unit tests for line_counter.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from line_counter import LineCounter, LineConfig


def _make_counter(y=300, entry="TOP_TO_BOTTOM"):
    lc = LineConfig(label="Gate", p1=(0, y), p2=(1920, y), entry_direction=entry)
    return LineCounter([lc])


def test_top_to_bottom_is_entry():
    counter = _make_counter(y=300, entry="TOP_TO_BOTTOM")
    # track moves from y=200 to y=400 (crossing y=300 downward)
    events = counter.update("P-0001", "person", (100, 400), (100, 200), frame_number=10)
    assert len(events) == 1
    assert events[0].direction == "entry"


def test_bottom_to_top_is_exit():
    counter = _make_counter(y=300, entry="TOP_TO_BOTTOM")
    events = counter.update("P-0001", "person", (100, 200), (100, 400), frame_number=10)
    assert len(events) == 1
    assert events[0].direction == "exit"


def test_parallel_motion_no_crossing():
    counter = _make_counter(y=300)
    # track stays above the line
    events = counter.update("P-0001", "person", (150, 100), (100, 100), frame_number=10)
    assert len(events) == 0


def test_totals_accumulate():
    counter = _make_counter(y=300)
    counter.update("P-0001", "person", (100, 400), (100, 200), 1)   # entry
    counter.update("P-0002", "person", (100, 200), (100, 400), 2)   # exit
    totals = counter.totals()
    assert totals["entries"] == 1
    assert totals["exits"]   == 1


def test_same_track_not_double_counted_immediately():
    counter = _make_counter(y=300)
    counter.update("P-0001", "person", (100, 400), (100, 200), 1)   # entry
    # same crossing direction again — should NOT count again
    counter.update("P-0001", "person", (100, 420), (100, 380), 2)
    totals = counter.totals()
    assert totals["entries"] == 1


def test_no_previous_center_returns_no_events():
    counter = _make_counter(y=300)
    events = counter.update("P-0001", "person", (100, 350), None, 1)
    assert events == []


def test_entry_direction_reversed():
    counter = _make_counter(y=300, entry="BOTTOM_TO_TOP")
    # bottom to top should now be entry
    events = counter.update("P-0001", "person", (100, 200), (100, 400), 1)
    assert len(events) == 1
    assert events[0].direction == "entry"
