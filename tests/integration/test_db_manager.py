"""
Integration tests for db_manager.py.

These tests require a running PostgreSQL instance.
Set the connection details via environment variables:
    CCTV_TEST_HOST     (default: localhost)
    CCTV_TEST_PORT     (default: 5432)
    CCTV_TEST_DBNAME   (default: cctv_test)
    CCTV_TEST_USER     (default: cctv_user)
    CCTV_TEST_PASSWORD (default: cctv_pass)

Skip automatically if psycopg2 is not installed or DB is unreachable.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    import psycopg2  # type: ignore
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not PSYCOPG2_AVAILABLE, reason="psycopg2 not installed"
)

_DB_PARAMS = {
    "host":     os.environ.get("CCTV_TEST_HOST",     "localhost"),
    "port":     int(os.environ.get("CCTV_TEST_PORT", "5432")),
    "dbname":   os.environ.get("CCTV_TEST_DBNAME",   "cctv_test"),
    "user":     os.environ.get("CCTV_TEST_USER",     "cctv_user"),
    "password": os.environ.get("CCTV_TEST_PASSWORD", "cctv_pass"),
}


@pytest.fixture(scope="module")
def db():
    from db_manager import DatabaseManager
    mgr = DatabaseManager(**_DB_PARAMS)
    if not mgr.is_available:
        pytest.skip("PostgreSQL not reachable – skipping integration tests")
    yield mgr
    mgr.close()


def test_db_is_available(db):
    assert db.is_available


def test_schema_tables_exist(db):
    tables = [
        "cameras", "sessions", "tracked_objects", "gender_classifications",
        "direction_events", "line_crossings", "zone_events",
        "occupancy_snapshots", "vehicle_counts", "error_events",
        "system_health_snapshots",
    ]
    with db._get_conn() as conn:
        with conn.cursor() as cur:
            for table in tables:
                cur.execute(
                    "SELECT EXISTS (SELECT FROM information_schema.tables "
                    "WHERE table_name = %s)", (table,)
                )
                exists = cur.fetchone()[0]
                assert exists, f"Table '{table}' does not exist"


def test_ensure_camera_creates_row(db):
    cam_id = db.ensure_camera("192.168.1.1", "rtsp://test", "TestCam")
    assert cam_id is not None
    # calling again returns same id
    cam_id2 = db.ensure_camera("192.168.1.1", "rtsp://test", "TestCam")
    assert cam_id == cam_id2


def test_create_and_close_session(db):
    cam_id     = db.ensure_camera("10.0.0.1", "rtsp://session-test", "SessionTest")
    session_id = db.create_session(cam_id, "yolo11n.pt", "CPU")
    assert session_id is not None
    db.close_session(session_id)


def test_insert_gender(db):
    cam_id     = db.ensure_camera("10.0.0.2", "rtsp://gender-test", "GenderTest")
    session_id = db.create_session(cam_id, "yolo11n.pt", "CPU")
    ok = db.insert_gender(session_id, "P-0001", 1, "Male", 0.92, "deepface")
    assert ok is not False   # None or True counts as success
    db.close_session(session_id)


def test_insert_line_crossing(db):
    cam_id     = db.ensure_camera("10.0.0.3", "rtsp://line-test", "LineTest")
    session_id = db.create_session(cam_id, "yolo11n.pt", "CPU")
    ok = db.insert_line_crossing(session_id, "P-0001", "Gate", "entry", "person", 960, 540, 100)
    assert ok is not False
    db.close_session(session_id)


def test_insert_occupancy_snapshot(db):
    cam_id     = db.ensure_camera("10.0.0.4", "rtsp://occ-test", "OccTest")
    session_id = db.create_session(cam_id, "yolo11n.pt", "CPU")
    ok = db.insert_occupancy_snapshot(session_id, 5, 2, 10, 4, 6.5, 2.1)
    assert ok is not False
    db.close_session(session_id)
