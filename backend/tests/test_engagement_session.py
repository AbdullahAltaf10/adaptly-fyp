"""
Session lifecycle, overlapping-request prevention, and engagement-event shape.

Both behaviours here are new in the migration. The prototype had neither:
windows were sent every second regardless of whether the previous one had
returned, and there was no notion of a session beginning or ending, so rule
state was only ever cleared by a 30-minute timeout.
"""

import threading
import time

from app.engagement import contracts, fatigue, session as session_state, smoothing


def _reset(uid="u1", sid="s1"):
    session_state.end(uid, sid)


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------

def test_start_creates_a_session():
    _reset()
    result = session_state.start("u1", "s1")
    assert result["status"] == "active"
    assert result["window_count"] == 0


def test_start_clears_rule_state_from_a_previous_session():
    """
    A learner who closes the tab and returns must not inherit stale evidence.
    Reusing a session id previously kept whatever the rules had accumulated.
    """
    _reset()
    session_state.start("u1", "s1")
    for _ in range(5):
        smoothing.update("u1", "s1", "drifting", 0.5)
    assert smoothing.update("u1", "s1", "drifting", 0.5)["streak"] > 1

    session_state.start("u1", "s1")          # restart
    assert smoothing.update("u1", "s1", "drifting", 0.5)["streak"] == 1


def test_end_reports_duration_and_window_count():
    _reset()
    session_state.start("u1", "s1")
    session_state.touch("u1", "s1")
    session_state.touch("u1", "s1")
    result = session_state.end("u1", "s1")
    assert result["status"] == "ended"
    assert result["window_count"] == 2
    assert result["duration_seconds"] >= 0


def test_end_releases_rule_state():
    _reset()
    session_state.start("u1", "s1")
    for _ in range(4):
        smoothing.update("u1", "s1", "drifting", 0.5)
    session_state.end("u1", "s1")
    assert smoothing.update("u1", "s1", "drifting", 0.5)["streak"] == 1


def test_ending_an_unknown_session_is_not_an_error():
    assert session_state.end("u1", "never-existed")["status"] == "not_found"


def test_touch_creates_a_session_if_analyze_arrives_first():
    """A client may start sending windows without calling /session/start."""
    _reset()
    session_state.touch("u1", "s1")
    assert session_state.snapshot("u1", "s1")["window_count"] == 1


def test_sessions_are_isolated_between_users():
    session_state.end("a", "shared")
    session_state.end("b", "shared")
    session_state.start("a", "shared")
    session_state.touch("a", "shared")
    session_state.start("b", "shared")
    assert session_state.snapshot("a", "shared")["window_count"] == 1
    assert session_state.snapshot("b", "shared")["window_count"] == 0


# --------------------------------------------------------------------------
# Overlapping requests
# --------------------------------------------------------------------------

def test_windows_for_one_session_do_not_overlap():
    """
    The rules assume windows arrive in order, once each. Two overlapping
    requests could otherwise both advance a streak from the same starting
    point, or append to a fatigue history out of order.
    """
    _reset()
    session_state.start("u1", "s1")
    order = []

    def slow():
        order.append("start")
        time.sleep(0.15)
        order.append("end")

    threads = [threading.Thread(target=session_state.process_exclusively,
                                args=("u1", "s1", slow)) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Serialised correctly, this reads start,end,start,end,start,end.
    assert order == ["start", "end"] * 3


def test_different_sessions_run_concurrently():
    """One learner's slow window must not block another's."""
    started = threading.Event()
    release = threading.Event()

    def blocker():
        started.set()
        release.wait(timeout=2)

    t = threading.Thread(target=session_state.process_exclusively, args=("u1", "sA", blocker))
    t.start()
    started.wait(timeout=2)

    done = []
    session_state.process_exclusively("u1", "sB", lambda: done.append(True))
    assert done == [True], "a different session should not be blocked"

    release.set()
    t.join()


# --------------------------------------------------------------------------
# Engagement event contract shape
# --------------------------------------------------------------------------

def _event(**kw):
    defaults = dict(user_id="u1", session_id="s1", state="focused",
                    confidence=0.42, source=contracts.SOURCE_MODEL)
    defaults.update(kw)
    return contracts.build_engagement_event(**defaults)


def test_event_has_every_required_contract_field():
    event = _event()
    for field in ("schema_version", "event_id", "session_id", "user_id",
                  "timestamp", "state", "confidence"):
        assert field in event, f"missing required field {field}"


def test_event_ids_are_unique():
    assert _event()["event_id"] != _event()["event_id"]


def test_states_are_lowercase_as_the_contract_requires():
    for state in ("focused", "drifting", "struggling", "fatigued", "recovered"):
        assert _event(state=state)["state"] == state


def test_source_distinguishes_model_output_from_rule_output():
    """fatigued and recovered are rules, not model classes."""
    assert _event(source=contracts.SOURCE_MODEL)["source"] == "lstm"
    assert _event(state="fatigued", source=contracts.SOURCE_RULE)["source"] == "rule"


def test_all_nine_features_are_representable():
    """
    brow_raise and inter_brow were added to the contract during review. Without
    them the change that lifted Struggling recall from ~1% to 10-18% could not
    be recorded at all.
    """
    event = _event(features=[0.1] * 9)
    for name in ("gaze_x", "gaze_y", "blink_rate", "head_pitch", "head_yaw",
                 "head_roll", "eye_openness", "brow_raise", "inter_brow"):
        assert name in event, f"missing feature field {name}"


def test_diagnostics_never_leak_into_the_event():
    """additionalProperties is false, so streaks and ratios must stay out."""
    event = _event(features=[0.1] * 9)
    for leaked in ("streak", "raw_state", "fatigue_ratio", "dt_gaze_var",
                   "furrow_ratio", "diagnostics"):
        assert leaked not in event


def test_gaze_regression_is_false_because_it_is_never_measured():
    assert _event()["gaze_regression_detected"] is False


def test_optional_ids_are_omitted_when_absent():
    event = _event()
    assert "content_id" not in event and "chunk_id" not in event
    linked = _event(content_id="c1", chunk_id="3")
    assert linked["content_id"] == "c1" and linked["chunk_id"] == "3"


def test_mean_features_averages_the_window():
    assert contracts.mean_features([[0.0] * 9, [2.0] * 9]) == [1.0] * 9
    assert contracts.mean_features([]) is None
