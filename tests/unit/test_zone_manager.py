"""Unit tests for zone_manager.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from zone_manager import ZoneManager, ZoneConfig, _point_in_polygon


# ── point-in-polygon tests ────────────────────────────────────────────────────

def test_point_inside_square():
    poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
    assert _point_in_polygon(50, 50, poly) is True


def test_point_outside_square():
    poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
    assert _point_in_polygon(150, 50, poly) is False


def test_point_on_edge_is_inside():
    poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
    # on the right edge — implementation-specific; verify no exception
    _point_in_polygon(100, 50, poly)   # just must not crash


def test_triangle_inside():
    poly = [[0, 0], [200, 0], [100, 200]]
    assert _point_in_polygon(100, 50, poly) is True


def test_triangle_outside():
    poly = [[0, 0], [200, 0], [100, 200]]
    assert _point_in_polygon(0, 200, poly) is False


# ── ZoneManager event tests ───────────────────────────────────────────────────

def _make_manager():
    zones = [
        ZoneConfig(zone_id="z1", label="LeftZone",  coords=[[0,0],[320,0],[320,480],[0,480]]),
        ZoneConfig(zone_id="z2", label="RightZone", coords=[[320,0],[640,0],[640,480],[320,480]]),
    ]
    return ZoneManager(zones)


def test_enter_zone_emits_event():
    mgr    = _make_manager()
    events = mgr.update("P-0001", "person", (100, 100), frame_number=1)
    assert len(events) == 1
    assert events[0].event_type == "enter"
    assert events[0].zone_label == "LeftZone"


def test_exit_and_enter_new_zone():
    mgr = _make_manager()
    mgr.update("P-0001", "person", (100, 100), frame_number=1)   # enter left
    events = mgr.update("P-0001", "person", (400, 100), frame_number=5)   # enter right
    types = {e.event_type for e in events}
    assert "exit"  in types
    assert "enter" in types


def test_no_event_when_staying_in_same_zone():
    mgr = _make_manager()
    mgr.update("P-0001", "person", (100, 100), frame_number=1)
    events = mgr.update("P-0001", "person", (110, 110), frame_number=2)
    assert events == []


def test_get_current_zone_label():
    mgr = _make_manager()
    mgr.update("P-0001", "person", (100, 100), frame_number=1)
    assert mgr.get_current_zone_label("P-0001") == "LeftZone"


def test_path_history_tracked():
    mgr = _make_manager()
    mgr.update("P-0001", "person", (100, 100), frame_number=1)
    mgr.update("P-0001", "person", (400, 100), frame_number=5)
    path = mgr.get_path("P-0001")
    assert "LeftZone"  in path
    assert "RightZone" in path


def test_remove_track_clears_state():
    mgr = _make_manager()
    mgr.update("P-0001", "person", (100, 100), frame_number=1)
    mgr.remove_track("P-0001")
    assert mgr.get_current_zone_label("P-0001") == "–"
