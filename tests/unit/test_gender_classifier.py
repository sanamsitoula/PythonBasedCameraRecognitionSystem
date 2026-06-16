"""Unit tests for gender_classifier.py (no real model needed – uses mocking)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import patch, MagicMock
import numpy as np

from gender_classifier import GenderClassifier, GenderResult


def _small_frame():
    return np.zeros((200, 200, 3), dtype=np.uint8)


def _patch_deepface_unavailable():
    return patch("builtins.__import__", side_effect=ImportError("deepface not installed"))


def test_unavailable_backend_returns_unknown():
    clf = GenderClassifier(backend="none")
    clf._available = False
    clf.classify_async("P-0001", _small_frame(), (0, 0, 100, 100))
    # wait briefly for the async call to complete (it's immediate when unavailable)
    import time; time.sleep(0.05)
    result = clf.get_cached("P-0001")
    assert result is not None
    assert result.gender == "Unknown"
    clf.shutdown()


def test_bbox_too_small_skips_classification():
    clf = GenderClassifier(backend="deepface", min_bbox_height=80)
    clf._available = True
    # bbox height = 50 (< 80 minimum)
    clf.classify_async("P-0001", _small_frame(), (0, 0, 100, 50))
    import time; time.sleep(0.05)
    result = clf.get_cached("P-0001")
    # Should NOT be classified (too small)
    assert result is None
    clf.shutdown()


def test_cache_hit_prevents_rerun():
    clf = GenderClassifier(backend="none")
    clf._available = False
    clf.classify_async("P-0001", _small_frame(), (0, 0, 100, 200))
    import time; time.sleep(0.1)
    first = clf.get_cached("P-0001")
    clf.classify_async("P-0001", _small_frame(), (0, 0, 100, 200))
    second = clf.get_cached("P-0001")
    assert first is second   # same object, not reprocessed
    clf.shutdown()


def test_evict_removes_from_cache():
    clf = GenderClassifier(backend="none")
    clf._available = False
    clf.classify_async("P-0001", _small_frame(), (0, 0, 100, 200))
    import time; time.sleep(0.1)
    assert clf.is_classified("P-0001")
    clf.evict("P-0001")
    assert not clf.is_classified("P-0001")
    clf.shutdown()


def test_live_counts_reflects_cache():
    clf = GenderClassifier(backend="none")
    clf._available = False
    for i in range(3):
        clf.classify_async(f"P-{i:04d}", _small_frame(), (0, 0, 100, 200))
    import time; time.sleep(0.2)
    counts = clf.live_counts()
    assert counts.get("Unknown", 0) == 3
    clf.shutdown()


def test_deepface_mock_result():
    clf = GenderClassifier(backend="deepface", confidence_threshold=0.5)
    clf._available = True
    clf._backend   = "deepface"

    mock_analysis = [{"gender": {"Man": 92, "Woman": 8}}]

    with patch.object(clf, "_run_deepface") as mock_run:
        mock_run.return_value = GenderResult(
            track_id="P-0001", gender="Male", confidence=0.92, backend="deepface",
            classified_at=__import__("datetime").datetime.now(),
        )
        clf.classify_async("P-0001", _small_frame(), (0, 0, 100, 200))
        import time; time.sleep(0.3)

    result = clf.get_cached("P-0001")
    assert result is not None
    assert result.gender == "Male"
    assert result.confidence >= 0.9
    clf.shutdown()
