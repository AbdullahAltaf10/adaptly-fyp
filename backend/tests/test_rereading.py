from app.engagement import rereading


def teardown_function(_fn):
    rereading.reset("u1", "s1")


def test_is_available_now_returns_true():
    assert rereading.is_available() is True


def test_no_revisit_on_purely_forward_reading():
    for order in [0, 1, 2, 3]:
        result = rereading.update("u1", "s1", order, dwell_seconds=10.0)
    assert result["status"] == "available"
    assert result["detected"] is False


def test_detects_a_revisit_to_an_earlier_chunk_with_enough_dwell():
    rereading.update("u1", "s1", 0, dwell_seconds=10.0)
    rereading.update("u1", "s1", 1, dwell_seconds=10.0)
    rereading.update("u1", "s1", 2, dwell_seconds=10.0)
    result = rereading.update("u1", "s1", 0, dwell_seconds=9.0)  # >= REVISIT_MIN_DWELL_SECONDS=8
    assert result["detected"] is True
    assert result["confidence"] is not None and result["confidence"] > 0


def test_does_not_detect_a_revisit_below_the_minimum_dwell():
    rereading.update("u1", "s1", 0, dwell_seconds=10.0)
    rereading.update("u1", "s1", 2, dwell_seconds=10.0)
    result = rereading.update("u1", "s1", 0, dwell_seconds=3.0)  # below REVISIT_MIN_DWELL_SECONDS
    assert result["detected"] is False


def test_a_chunk_never_counts_as_a_revisit_of_itself():
    rereading.update("u1", "s1", 2, dwell_seconds=5.0)
    result = rereading.update("u1", "s1", 2, dwell_seconds=20.0)
    assert result["detected"] is False


def test_none_order_never_crashes_and_is_never_a_revisit():
    result = rereading.update("u1", "s1", None, dwell_seconds=20.0)
    assert result["detected"] is False


def test_sessions_are_independent():
    rereading.update("u1", "s1", 5, dwell_seconds=10.0)
    result = rereading.update("u1", "s2", 0, dwell_seconds=10.0)
    assert result["detected"] is False


def test_reset_clears_history_so_the_next_session_starts_clean():
    rereading.update("u1", "s1", 3, dwell_seconds=10.0)
    rereading.reset("u1", "s1")
    result = rereading.update("u1", "s1", 0, dwell_seconds=10.0)
    assert result["detected"] is False


def test_a_quick_scroll_past_does_not_count_as_having_reached_that_chunk():
    # A learner who skims all the way to chunk 5 in under
    # REVISIT_MIN_DWELL_SECONDS on each window and then reads normally from
    # chunk 0 has not "revisited" anything - they never actually reached 5,
    # they scrolled past it. max_order_seen must only advance on chunks the
    # learner actually dwelled on, or every such skim manufactures a false
    # reading-difficulty flag on every paragraph afterwards.
    for order in [1, 2, 3, 4, 5]:
        rereading.update("u1", "s1", order, dwell_seconds=1.0)  # a quick scroll-past
    result = rereading.update("u1", "s1", 0, dwell_seconds=10.0)
    assert result["detected"] is False
