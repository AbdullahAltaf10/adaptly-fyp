import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.fusion.window import FUSION_WINDOW_SECONDS, FusionWindow  # noqa: E402


def test_a_never_seen_session_is_ready_immediately():
    """A session's first-ever fusion decision must not be blocked by a
    60-second wait that never had a previous decision to measure from."""
    window = FusionWindow()
    assert window.ready("u1", "s1", now=1000.0) is True


def test_not_ready_again_until_the_full_window_has_passed():
    window = FusionWindow()
    window.mark_decided("u1", "s1", now=1000.0)
    assert window.ready("u1", "s1", now=1000.0 + FUSION_WINDOW_SECONDS - 1) is False


def test_ready_again_once_the_window_has_fully_elapsed():
    window = FusionWindow()
    window.mark_decided("u1", "s1", now=1000.0)
    assert window.ready("u1", "s1", now=1000.0 + FUSION_WINDOW_SECONDS) is True


def test_sessions_are_tracked_independently():
    window = FusionWindow()
    window.mark_decided("u1", "s1", now=1000.0)
    assert window.ready("u1", "s2", now=1000.0) is True


def test_users_are_tracked_independently_even_with_the_same_session_id():
    """A defensive-but-real case: uid is part of the key, not just
    session_id, matching the (uid, session_id) keying convention already
    used by engagement/smoothing.py and intervention/cooldown.py."""
    window = FusionWindow()
    window.mark_decided("u1", "s1", now=1000.0)
    assert window.ready("u2", "s1", now=1000.0) is True
