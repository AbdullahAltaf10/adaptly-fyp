"""Validates sample compliance reports against
``shared/contracts/compliance-report.schema.json`` (Issue #72 acceptance
criterion). ``critical_sections`` is reserved but not populated until Issue
#73, so these samples use an empty list -- the schema must still accept
that, since most real sessions have none until Module 9 exists.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from backend.app.compliance.domain.score import build_engagement_quality_score
from backend.tests.analytics.test_metrics import assert_schema_match
from backend.tests.compliance import fixtures

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _schema() -> dict[str, Any]:
    path = REPOSITORY_ROOT / "shared" / "contracts" / "compliance-report.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _envelope(score_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "score_version": score_result["score_version"],
        "report_id": "report-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "content_id": "content-1",
        "generated_at": "2026-08-17T09:05:00Z",
        "source_summary": {
            "metric_version": "1.0",
            "computed_at": "2026-08-17T09:05:00Z",
        },
        "status": score_result["status"],
        "engagement_quality_score": score_result["engagement_quality_score"],
        "components": score_result["components"],
        "excluded_components": score_result["excluded_components"],
        "critical_sections": [],
        "data_quality": {
            "has_sufficient_data": True,
            "event_coverage_rate": 0.9,
            "unknown_duration_seconds": 0,
            "flags": [],
        },
    }


class ComplianceReportSchemaTests(unittest.TestCase):
    def test_complete_report_validates(self):
        score_result = build_engagement_quality_score(fixtures.full_summary())
        assert_schema_match(_envelope(score_result), _schema())

    def test_insufficient_data_report_validates(self):
        score_result = build_engagement_quality_score(fixtures.all_components_missing())
        assert_schema_match(_envelope(score_result), _schema())

    def test_report_with_excluded_components_validates(self):
        score_result = build_engagement_quality_score(fixtures.no_critical_sections())
        assert_schema_match(_envelope(score_result), _schema())


if __name__ == "__main__":
    unittest.main()
