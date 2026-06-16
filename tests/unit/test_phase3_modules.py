"""
tests/unit/test_phase3_modules.py – Unit tests for Phase 3 analytics modules.

Tests:
  - AttendanceEngine
  - CanteenAnalytics
  - VisitorManager
  - DepartmentAnalytics
  - SmartAlerts
"""

import datetime
import pytest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# AttendanceEngine
# ---------------------------------------------------------------------------
from attendance_engine import AttendanceEngine, AttendanceRecord


class TestAttendanceEngine:
    def setup_method(self):
        self.engine = AttendanceEngine(
            late_threshold="09:15",
            work_start="09:00",
            work_end="18:00",
        )

    def test_first_entry_sets_record(self):
        """record_entry creates a new record with correct first_entry."""
        ts = datetime.datetime(2026, 6, 15, 9, 0, 0)
        record = self.engine.record_entry("EMP001", ts)

        assert record.employee_id == "EMP001"
        assert record.first_entry == ts
        assert record.attendance_date == datetime.date(2026, 6, 15)
        assert record.status in ("present", "late")

    def test_late_detection(self):
        """Entry at 09:20 is marked late (threshold 09:15)."""
        ts = datetime.datetime(2026, 6, 15, 9, 20, 0)
        record = self.engine.record_entry("EMP002", ts)

        assert record.is_late is True
        assert record.status == "late"

    def test_on_time_not_late(self):
        """Entry at 09:00 is not late."""
        ts = datetime.datetime(2026, 6, 15, 9, 0, 0)
        record = self.engine.record_entry("EMP003", ts)

        assert record.is_late is False
        assert record.status == "present"

    def test_exit_updates_record(self):
        """record_exit sets last_exit and calculates working_duration_seconds."""
        entry_ts = datetime.datetime(2026, 6, 15, 9, 0, 0)
        exit_ts  = datetime.datetime(2026, 6, 15, 17, 0, 0)
        self.engine.record_entry("EMP004", entry_ts)
        record = self.engine.record_exit("EMP004", exit_ts)

        assert record.last_exit == exit_ts
        # 8 hours = 28 800 seconds
        assert record.working_duration_seconds == 28_800

    def test_currently_present_list(self):
        """get_currently_present returns employees who entered but haven't exited."""
        ts_entry = datetime.datetime(2026, 6, 15, 9, 5, 0)
        ts_exit  = datetime.datetime(2026, 6, 15, 17, 0, 0)

        self.engine.record_entry("EMP010", ts_entry)
        self.engine.record_entry("EMP011", ts_entry)
        self.engine.record_exit("EMP010", ts_exit)

        present = self.engine.get_currently_present()
        assert "EMP010" not in present
        assert "EMP011" in present

    def test_second_entry_does_not_overwrite_first_entry(self):
        """Calling record_entry twice for the same employee keeps the original first_entry."""
        ts1 = datetime.datetime(2026, 6, 15, 9, 0, 0)
        ts2 = datetime.datetime(2026, 6, 15, 10, 0, 0)
        self.engine.record_entry("EMP020", ts1)
        record = self.engine.record_entry("EMP020", ts2)

        assert record.first_entry == ts1

    def test_get_today_summary(self):
        """get_today_summary returns correct present/late/absent breakdown."""
        today = datetime.date.today()
        ts_present = datetime.datetime.combine(today, datetime.time(9, 0))
        ts_late    = datetime.datetime.combine(today, datetime.time(9, 30))

        self.engine.record_entry("EMP030", ts_present)
        self.engine.record_entry("EMP031", ts_late)

        summary = self.engine.get_today_summary()
        assert summary["present"] >= 1
        assert summary["late"] >= 1


# ---------------------------------------------------------------------------
# CanteenAnalytics
# ---------------------------------------------------------------------------
from canteen_analytics import CanteenAnalytics, CanteenVisit


class TestCanteenAnalytics:
    def setup_method(self):
        self.canteen = CanteenAnalytics()

    def test_person_enter_exit_calculates_duration(self):
        """Duration is correctly calculated on exit."""
        entry = datetime.datetime(2026, 6, 15, 12, 0, 0)
        exit_ = datetime.datetime(2026, 6, 15, 12, 30, 0)

        self.canteen.person_entered("EMP001", "employee", entry)
        visit = self.canteen.person_exited("EMP001", exit_)

        assert visit is not None
        assert visit.duration_seconds == 1800   # 30 minutes

    def test_current_count(self):
        """current_count reflects people inside."""
        ts = datetime.datetime(2026, 6, 15, 12, 0, 0)
        self.canteen.person_entered("EMP001", "employee", ts)
        self.canteen.person_entered("EMP002", "employee", ts)

        assert self.canteen.current_count() == 2

        self.canteen.person_exited("EMP001", ts)
        assert self.canteen.current_count() == 1

    def test_meal_period_detection_lunch(self):
        """12:30 is classified as 'lunch'."""
        ts = datetime.datetime(2026, 6, 15, 12, 30, 0)
        period = self.canteen.determine_meal_period(ts)
        assert period == "lunch"

    def test_meal_period_detection_breakfast(self):
        """08:00 is classified as 'breakfast'."""
        ts = datetime.datetime(2026, 6, 15, 8, 0, 0)
        period = self.canteen.determine_meal_period(ts)
        assert period == "breakfast"

    def test_meal_period_detection_dinner(self):
        """20:00 is classified as 'dinner'."""
        ts = datetime.datetime(2026, 6, 15, 20, 0, 0)
        period = self.canteen.determine_meal_period(ts)
        assert period == "dinner"

    def test_meal_period_detection_other(self):
        """03:00 is classified as 'other'."""
        ts = datetime.datetime(2026, 6, 15, 3, 0, 0)
        period = self.canteen.determine_meal_period(ts)
        assert period == "other"

    def test_open_visit_stored_correctly(self):
        """get_visit returns open visit before exit."""
        ts = datetime.datetime(2026, 6, 15, 13, 0, 0)
        self.canteen.person_entered("EMP050", "employee", ts)

        visit = self.canteen.get_visit("EMP050")
        assert visit is not None
        assert visit.person_id == "EMP050"
        assert visit.exit_time is None

    def test_no_open_visit_returns_none(self):
        """get_visit returns None for person not in canteen."""
        assert self.canteen.get_visit("NOBODY") is None


# ---------------------------------------------------------------------------
# VisitorManager
# ---------------------------------------------------------------------------
from visitor_manager import VisitorManager, VisitorRecord


class TestVisitorManager:
    def setup_method(self):
        self.mgr = VisitorManager()

    def test_get_or_create_returns_visitor_id(self):
        """First call creates a visitor and returns a VISITOR-NNNN string."""
        vid = self.mgr.get_or_create("P-001", "cam1")
        assert vid.startswith("VISITOR-")

    def test_same_track_returns_same_id(self):
        """Calling get_or_create twice for the same (track, camera) pair is idempotent."""
        vid1 = self.mgr.get_or_create("P-001", "cam1")
        vid2 = self.mgr.get_or_create("P-001", "cam1")
        assert vid1 == vid2

    def test_different_tracks_get_different_ids(self):
        """Different track IDs produce different visitor IDs."""
        vid1 = self.mgr.get_or_create("P-001", "cam1")
        vid2 = self.mgr.get_or_create("P-002", "cam1")
        assert vid1 != vid2

    def test_different_cameras_same_track_get_different_ids(self):
        """Same track ID on different cameras is treated as different visitors."""
        vid1 = self.mgr.get_or_create("P-001", "cam1")
        vid2 = self.mgr.get_or_create("P-001", "cam2")
        assert vid1 != vid2

    def test_get_record_returns_record(self):
        """get_record returns a VisitorRecord after get_or_create."""
        vid = self.mgr.get_or_create("P-010", "cam1")
        record = self.mgr.get_record(vid)
        assert isinstance(record, VisitorRecord)
        assert record.visitor_id == vid

    def test_remove_track_deactivates_visitor(self):
        """Removing the only track deactivates the visitor."""
        vid = self.mgr.get_or_create("P-020", "cam1")
        assert vid in {v.visitor_id for v in self.mgr.get_all_active()}

        self.mgr.remove_track("P-020", "cam1")
        active_ids = {v.visitor_id for v in self.mgr.get_all_active()}
        assert vid not in active_ids

    def test_visitor_counter_increments(self):
        """Each new visitor gets an incrementing number."""
        vid1 = self.mgr.get_or_create("P-031", "cam1")
        vid2 = self.mgr.get_or_create("P-032", "cam1")
        n1 = int(vid1.split("-")[1])
        n2 = int(vid2.split("-")[1])
        assert n2 == n1 + 1


# ---------------------------------------------------------------------------
# DepartmentAnalytics
# ---------------------------------------------------------------------------
from department_analytics import DepartmentAnalytics, DepartmentStatus


class TestDepartmentAnalytics:
    def setup_method(self):
        self.dept = DepartmentAnalytics()
        self.dept.set_department_roster("Engineering", ["EMP001", "EMP002", "EMP003"])
        self.dept.set_department_roster("HR", ["EMP101", "EMP102"])

    def test_employee_zone_tracking(self):
        """employee_entered_zone updates the employee's current zone."""
        self.dept.employee_entered_zone("EMP001", "office")
        assert self.dept.get_employee_zone("EMP001") == "office"

    def test_employee_zone_tracking_update(self):
        """Moving to a new zone overwrites the previous zone."""
        self.dept.employee_entered_zone("EMP001", "office")
        self.dept.employee_entered_zone("EMP001", "canteen")
        assert self.dept.get_employee_zone("EMP001") == "canteen"

    def test_department_count(self):
        """present_today counts employees in a non-empty zone."""
        self.dept.employee_entered_zone("EMP001", "office")
        self.dept.employee_entered_zone("EMP002", "canteen")

        status = self.dept.get_department_status("Engineering")
        assert status is not None
        assert status.present_today == 2
        assert status.in_office  == 1
        assert status.in_canteen == 1

    def test_employee_left_camera_clears_zone(self):
        """employee_left_camera marks the employee as outside."""
        self.dept.employee_entered_zone("EMP001", "office")
        self.dept.employee_left_camera("EMP001")
        assert self.dept.get_employee_zone("EMP001") == ""

        status = self.dept.get_department_status("Engineering")
        # EMP001 should no longer be counted as present
        emp_ids = status.employee_ids_present
        assert "EMP001" not in emp_ids

    def test_get_all_departments(self):
        """get_all_departments returns statuses for all registered departments."""
        depts = self.dept.get_all_departments()
        dept_names = {d.department for d in depts}
        assert "Engineering" in dept_names
        assert "HR" in dept_names

    def test_unknown_employee_silently_tracked(self):
        """An employee not in any roster is silently tracked."""
        self.dept.employee_entered_zone("UNKNOWN_EMP", "warehouse")
        zone = self.dept.get_employee_zone("UNKNOWN_EMP")
        assert zone == "warehouse"

    def test_total_enrolled_reflects_roster(self):
        """total_enrolled matches the roster size."""
        status = self.dept.get_department_status("Engineering")
        assert status.total_enrolled == 3


# ---------------------------------------------------------------------------
# SmartAlerts
# ---------------------------------------------------------------------------
from smart_alerts import SmartAlerts, Alert


class TestSmartAlerts:
    def setup_method(self):
        self.sa = SmartAlerts(
            restricted_zones  = ["Warehouse", "Server Room"],
            loitering_seconds = 900,
            crowd_threshold   = 5,
            office_start      = 7,
            office_end        = 19,
        )

    # -- restricted zone --

    def test_restricted_zone_alert_visitor(self):
        """Visitor in a restricted zone triggers a critical alert."""
        ts = datetime.datetime(2026, 6, 15, 10, 0, 0)
        alert = self.sa.check_restricted_zone(
            "VISITOR-0001", "cam1", "Warehouse", True, ts
        )
        assert alert is not None
        assert alert.severity == "critical"
        assert alert.zone_id == "Warehouse"

    def test_restricted_zone_alert_employee_is_info(self):
        """Employee in a restricted zone triggers only an info-level alert."""
        ts = datetime.datetime(2026, 6, 15, 10, 0, 0)
        alert = self.sa.check_restricted_zone(
            "EMP001", "cam1", "Warehouse", False, ts
        )
        assert alert is not None
        assert alert.severity == "info"

    def test_non_restricted_zone_no_alert(self):
        """No alert fired for a non-restricted zone."""
        ts = datetime.datetime(2026, 6, 15, 10, 0, 0)
        alert = self.sa.check_restricted_zone(
            "VISITOR-0002", "cam1", "Reception", True, ts
        )
        assert alert is None

    # -- loitering --

    def test_loitering_alert(self):
        """Duration exceeding threshold fires a loitering alert."""
        ts = datetime.datetime(2026, 6, 15, 10, 0, 0)
        alert = self.sa.check_loitering("EMP002", "cam1", "Lobby", 1000, ts)
        assert alert is not None
        assert alert.alert_type == "loitering"
        assert alert.severity == "warning"

    def test_loitering_below_threshold_no_alert(self):
        """Duration below threshold does not fire an alert."""
        ts = datetime.datetime(2026, 6, 15, 10, 0, 0)
        alert = self.sa.check_loitering("EMP002", "cam1", "Lobby", 300, ts)
        assert alert is None

    # -- after-hours --

    def test_after_hours_alert_before_start(self):
        """Person detected before office_start triggers a warning."""
        ts = datetime.datetime(2026, 6, 15, 5, 30, 0)   # 05:30
        alert = self.sa.check_after_hours("EMP003", "cam1", "Lobby", ts)
        assert alert is not None
        assert alert.alert_type == "after_hours"
        assert alert.severity == "warning"

    def test_after_hours_alert_after_end(self):
        """Person detected after office_end triggers a warning."""
        ts = datetime.datetime(2026, 6, 15, 21, 0, 0)   # 21:00
        alert = self.sa.check_after_hours("EMP003", "cam1", "Lobby", ts)
        assert alert is not None
        assert alert.alert_type == "after_hours"

    def test_during_office_hours_no_alert(self):
        """Person detected during office hours produces no after-hours alert."""
        ts = datetime.datetime(2026, 6, 15, 10, 0, 0)   # 10:00
        alert = self.sa.check_after_hours("EMP004", "cam1", "Office", ts)
        assert alert is None

    # -- crowd --

    def test_crowd_alert(self):
        """Count at/above threshold fires a crowd alert."""
        ts = datetime.datetime(2026, 6, 15, 12, 0, 0)
        alert = self.sa.check_crowd("Cafeteria", "cam1", 10, ts)
        assert alert is not None
        assert alert.alert_type == "crowd"

    def test_crowd_below_threshold_no_alert(self):
        """Count below threshold does not fire a crowd alert."""
        ts = datetime.datetime(2026, 6, 15, 12, 0, 0)
        alert = self.sa.check_crowd("Cafeteria", "cam1", 3, ts)
        assert alert is None

    # -- deduplication --

    def test_deduplication_same_alert_not_fired_within_5_minutes(self):
        """Identical (person, type, zone) fires only once within 5 minutes."""
        ts = datetime.datetime(2026, 6, 15, 10, 0, 0)
        # First call should fire
        alert1 = self.sa.check_restricted_zone(
            "VISITOR-0010", "cam1", "Warehouse", True, ts
        )
        assert alert1 is not None

        # Immediate second call should be suppressed
        ts2 = datetime.datetime(2026, 6, 15, 10, 1, 0)   # 1 minute later
        alert2 = self.sa.check_restricted_zone(
            "VISITOR-0010", "cam1", "Warehouse", True, ts2
        )
        assert alert2 is None

    def test_deduplication_fires_again_after_window(self):
        """Same alert fires again once the 5-minute dedup window expires."""
        ts_first = datetime.datetime(2026, 6, 15, 10, 0, 0)
        ts_after  = datetime.datetime(2026, 6, 15, 10, 6, 0)   # 6 minutes later

        alert1 = self.sa.check_restricted_zone(
            "VISITOR-0011", "cam1", "Server Room", True, ts_first
        )
        assert alert1 is not None

        # Manually advance the dedup cache timestamp to simulate time passing.
        # The SmartAlerts engine checks datetime.now() internally, so we patch
        # the internal dedup entry directly.
        dedup_key = ("VISITOR-0011", "unknown_restricted", "Server Room")
        self.sa._dedup[dedup_key] = ts_first   # set to ts_first (6 min ago relative to ts_after)

        # Patch datetime.now used inside _create_alert
        with patch("smart_alerts.datetime") as mock_dt:
            mock_dt.now.return_value = ts_after
            mock_dt.timedelta = datetime.timedelta
            alert2 = self.sa.check_restricted_zone(
                "VISITOR-0011", "cam1", "Server Room", True, ts_after
            )

        assert alert2 is not None

    def test_get_recent_alerts_ordering(self):
        """get_recent_alerts returns the most recent alerts first."""
        ts = datetime.datetime(2026, 6, 15, 10, 0, 0)
        self.sa.check_crowd("Zone A", "cam1", 10, ts)

        ts2 = datetime.datetime(2026, 6, 15, 10, 5, 0)
        # Use a different zone to avoid dedup
        self.sa.check_crowd("Zone B", "cam1", 10, ts2)

        recent = self.sa.get_recent_alerts(2)
        # Most recent first
        assert recent[0].timestamp >= recent[1].timestamp

    def test_max_alerts_enforced(self):
        """Alert list stays within _MAX_ALERTS capacity."""
        # Inject many alerts by using unique person + zone combos
        ts = datetime.datetime(2026, 6, 15, 10, 0, 0)
        for i in range(self.sa._MAX_ALERTS + 10):
            self.sa._create_alert(
                "test_type", f"P-{i:04d}", "cam1", "Zone", "info", f"msg {i}"
            )
        with self.sa._lock:
            assert len(self.sa._alerts) <= self.sa._MAX_ALERTS
