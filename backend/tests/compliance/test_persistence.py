"""Tests for Module 10's compliance-report repository (Issue #74)."""

from __future__ import annotations

import unittest

import mongomock

from backend.app.compliance.persistence.reports import ComplianceReportRepository
from backend.tests.compliance import fixtures


def _report(session_id: str = "session-1", user_id: str = "user-1", *, score: int = 80) -> dict:
    score_result = {
        "score_version": "1.0",
        "status": "complete",
        "engagement_quality_score": score,
        "components": [],
        "excluded_components": [],
    }
    return {
        "schema_version": "1.0",
        "score_version": score_result["score_version"],
        "report_id": f"report-{session_id}",
        "session_id": session_id,
        "user_id": user_id,
        "content_id": "content-1",
        "generated_at": "2026-08-17T09:05:00Z",
        "source_summary": {"metric_version": "1.0", "computed_at": "2026-08-17T09:05:00Z"},
        "status": score_result["status"],
        "engagement_quality_score": score_result["engagement_quality_score"],
        "components": score_result["components"],
        "excluded_components": score_result["excluded_components"],
        "critical_sections": [],
        "data_quality": fixtures.full_summary()["data_quality"],
    }


class ComplianceReportRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database = mongomock.MongoClient()["adaptly_test"]
        self.repository = ComplianceReportRepository(self.database)

    def test_save_then_get_round_trips_the_contract_shaped_report(self):
        report = _report()
        self.repository.save(report)
        stored = self.repository.get("session-1")
        self.assertEqual(stored["report"], report)
        self.assertEqual(stored["session_id"], "session-1")
        self.assertIn("created_at", stored)

    def test_get_missing_session_returns_none(self):
        self.assertIsNone(self.repository.get("does-not-exist"))

    def test_save_is_upsert_keyed_by_session_id_not_duplicated(self):
        self.repository.save(_report())
        self.repository.save(_report())
        self.assertEqual(self.database["compliance_reports"].count_documents({}), 1)

    def test_save_is_insert_only_first_report_wins_a_race(self):
        # Two "concurrent" generate calls building different reports for the
        # same session (Issue #74 review finding): whichever save reaches
        # the database first must be the one that sticks -- a second,
        # different report must never silently overwrite it.
        first_report = _report(score=80)
        second_report = _report(score=40)

        self.repository.save(first_report)
        self.repository.save(second_report)

        stored = self.repository.get("session-1")
        self.assertEqual(stored["report"]["engagement_quality_score"], 80)
        self.assertEqual(stored["report"], first_report)
        self.assertEqual(self.database["compliance_reports"].count_documents({}), 1)

    def test_list_filters_by_user_id_and_content_id(self):
        self.repository.save(_report("session-1", "user-1"))
        self.repository.save(_report("session-2", "user-2"))
        results = self.repository.list(user_id="user-1")
        self.assertEqual([item["session_id"] for item in results], ["session-1"])

    def test_list_with_no_filters_returns_everything(self):
        self.repository.save(_report("session-1", "user-1"))
        self.repository.save(_report("session-2", "user-2"))
        results = self.repository.list()
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
