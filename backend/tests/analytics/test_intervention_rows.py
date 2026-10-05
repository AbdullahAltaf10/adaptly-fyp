from app.analytics.api.routes import _intervention_rows


def test_rows_carry_what_the_log_shows_in_time_order():
    events = [
        {"intervention_id": "b", "timestamp": "2026-10-04T10:05:00Z", "intervention_type": "bullet_summary",
         "reason": "Signs of difficulty", "delivery_status": "displayed", "outcome": "helped",
         "helped": True, "user_id": "u1", "session_id": "s1"},
        {"intervention_id": "a", "timestamp": "2026-10-04T10:01:00Z", "intervention_type": "simplify_content",
         "reason": "Both signals", "delivery_status": "accepted", "outcome": "unknown",
         "helped": None, "user_id": "u1", "session_id": "s1"},
    ]
    rows = _intervention_rows(events)
    assert [r["intervention_type"] for r in rows] == ["simplify_content", "bullet_summary"]
    assert rows[1]["reason"] == "Signs of difficulty"
    assert rows[1]["outcome"] == "helped"
    assert "user_id" not in rows[1] and "session_id" not in rows[1]


def test_no_interventions_gives_an_empty_list():
    assert _intervention_rows([]) == []
