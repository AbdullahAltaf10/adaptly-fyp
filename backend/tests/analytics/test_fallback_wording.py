"""Audit 2026-10-04: the fallback report must not say 'on track' when nothing was measured."""
from app.analytics.insights.fallback import build_fallback_report


def _summary(has_sufficient_data: bool) -> dict:
    return {
        "duration_seconds": 63,
        "data_quality": {"has_sufficient_data": has_sufficient_data},
        "longest_focused_period": None,
        "intervention_metrics": {"total_count": 0},
    }


def test_on_track_is_said_only_when_engagement_was_measured():
    report = build_fallback_report(_summary(has_sufficient_data=True))
    assert "on track throughout" in report


def test_no_on_track_claim_when_data_was_insufficient():
    report = build_fallback_report(_summary(has_sufficient_data=False))
    assert "on track" not in report
    assert "No extra support was offered during this session." in report
