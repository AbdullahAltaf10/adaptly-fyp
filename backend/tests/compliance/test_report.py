"""Tests for the Module 10 compliance-report builder (Issue #73)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from backend.app.compliance.domain.report import build_compliance_report
from backend.tests.analytics.test_metrics import assert_schema_match
from backend.tests.compliance import fixtures

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _schema() -> dict[str, Any]:
    path = REPOSITORY_ROOT / "shared" / "contracts" / "compliance-report.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _summary_with_timeline() -> dict[str, Any]:
    summary = fixtures.full_summary()
    summary.update(
        {
            "session_id": "session-1",
            "user_id": "user-1",
            "content_id": "content-1",
            "metric_version": "1.0",
            "computed_at": "2026-08-17T09:05:00Z",
            "timeline_segments": [
                {
                    "started_at": "2026-08-17T09:00:00Z",
                    "ended_at": "2026-08-17T09:00:10Z",
                    "duration_seconds": 10,
                    "state": "struggling",
                    "average_confidence": 0.8,
                    "chunk_id": "chunk-1",
                },
                {
                    "started_at": "2026-08-17T09:00:10Z",
                    "ended_at": "2026-08-17T09:00:20Z",
                    "duration_seconds": 10,
                    "state": "focused",
                    "average_confidence": 0.9,
                    "chunk_id": "chunk-1",
                },
            ],
        }
    )
    return summary


class BuildComplianceReportTests(unittest.TestCase):
    def test_combined_report_has_score_and_critical_sections(self):
        report = build_compliance_report(
            _summary_with_timeline(),
            report_id="report-1",
            generated_at="2026-08-17T09:05:00Z",
            chunk_context=[{"chunk_id": "chunk-1", "is_critical": True, "completed": True}],
            intervention_events=[{"chunk_id": "chunk-1"}],
        )
        self.assertEqual(report["status"], "complete")
        self.assertIsInstance(report["engagement_quality_score"], int)
        self.assertEqual(len(report["critical_sections"]), 1)
        self.assertEqual(report["critical_sections"][0]["verdict"], "difficulty_then_recovered")
        self.assertEqual(report["critical_sections"][0]["intervention_count"], 1)
        self.assertEqual(report["source_summary"]["metric_version"], "1.0")
        self.assertEqual(report["session_id"], "session-1")

    def test_no_critical_chunks_produces_empty_list_not_an_error(self):
        report = build_compliance_report(
            _summary_with_timeline(),
            report_id="report-2",
            generated_at="2026-08-17T09:05:00Z",
            chunk_context=[{"chunk_id": "chunk-1", "is_critical": False, "completed": True}],
        )
        self.assertEqual(report["critical_sections"], [])

    def test_combined_report_validates_against_contract(self):
        report = build_compliance_report(
            _summary_with_timeline(),
            report_id="report-3",
            generated_at="2026-08-17T09:05:00Z",
            chunk_context=[{"chunk_id": "chunk-1", "is_critical": True, "completed": True}],
            intervention_events=[{"chunk_id": "chunk-1"}],
        )
        assert_schema_match(report, _schema())

    def test_combined_report_with_no_critical_sections_validates(self):
        report = build_compliance_report(
            _summary_with_timeline(),
            report_id="report-4",
            generated_at="2026-08-17T09:05:00Z",
            chunk_context=None,
        )
        assert_schema_match(report, _schema())


if __name__ == "__main__":
    unittest.main()
