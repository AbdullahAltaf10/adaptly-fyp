"""Tests for the Module 8 analytics persistence layer (Issue #27).

Uses mongomock so the suite never needs a live MongoDB instance. Repositories
only rely on the pymongo-compatible Database/Collection interface, which
mongomock implements, so these tests exercise the same code paths that run
against real Atlas.
"""

from __future__ import annotations

import unittest

import mongomock

from backend.app.analytics.domain.metrics import build_session_summary
from backend.app.analytics.persistence import (
    AssistantEventRepository,
    ChunkProgressRepository,
    EngagementEventRepository,
    InterventionEventRepository,
    LearningProfileRepository,
    SessionAnalyticsRepository,
    SessionRepository,
    collections,
    ensure_indexes,
)
from backend.tests.analytics.fixtures import (
    assistant,
    engagement,
    fixture,
    intervention,
    session,
    timestamp,
)


def _database():
    return mongomock.MongoClient()["adaptly_test"]


class EngagementEventPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = EngagementEventRepository(_database())

    def test_store_and_retrieve_by_session_in_order(self) -> None:
        events = [
            engagement(10, "focused", event_number=2),
            engagement(0, "focused", event_number=1),
            engagement(5, "drifting", event_number=3),
        ]
        self.repo.insert_events(events)

        stored = self.repo.list_by_session("session-1")

        self.assertEqual(
            [item["event_id"] for item in stored],
            ["engagement-1", "engagement-3", "engagement-2"],
        )

    def test_session_and_user_ownership_fields_are_preserved(self) -> None:
        self.repo.insert_events([engagement(0, "focused", event_number=1)])

        stored = self.repo.get("engagement-1")

        self.assertEqual(stored["session_id"], "session-1")
        self.assertEqual(stored["user_id"], "user-1")

    def test_duplicate_event_id_does_not_create_a_second_document(self) -> None:
        first = engagement(0, "focused", event_number=1, confidence=0.5)
        duplicate_resubmission = engagement(0, "focused", event_number=1, confidence=0.5)

        result_a = self.repo.insert_events([first])
        result_b = self.repo.insert_events([duplicate_resubmission])

        self.assertEqual(result_a, {"inserted": 1, "updated": 0})
        self.assertEqual(result_b, {"inserted": 0, "updated": 1})
        self.assertEqual(self.repo.count_for_session("session-1"), 1)

    def test_prohibited_raw_biometric_and_video_fields_are_dropped(self) -> None:
        tainted_event = engagement(0, "focused", event_number=1)
        tainted_event["video_frame"] = b"not-really-a-jpeg"
        tainted_event["facial_landmarks"] = [[0.1, 0.2]] * 468
        tainted_event["raw_frame_bytes"] = b"\x00\x01"

        self.repo.insert_events([tainted_event])
        stored = self.repo.get("engagement-1")

        self.assertNotIn("video_frame", stored)
        self.assertNotIn("facial_landmarks", stored)
        self.assertNotIn("raw_frame_bytes", stored)
        self.assertEqual(stored["state"], "focused")


class InterventionEventPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InterventionEventRepository(_database())

    def test_store_and_retrieve_by_session(self) -> None:
        self.repo.insert_events(
            [intervention(20, intervention_number=1, outcome="recovered", helped=True)]
        )

        stored = self.repo.list_by_session("session-1")

        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["intervention_id"], "intervention-1")
        self.assertEqual(stored[0]["outcome"], "recovered")

    def test_duplicate_intervention_id_is_idempotent(self) -> None:
        event = intervention(20, intervention_number=1)

        self.repo.insert_events([event])
        self.repo.insert_events([event])
        self.repo.insert_events([event])

        self.assertEqual(self.repo.count_for_session("session-1"), 1)


class AssistantEventPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = AssistantEventRepository(_database())

    def test_no_chat_transcript_field_is_persisted(self) -> None:
        tainted_event = assistant(
            5,
            event_number=1,
            direction="learner",
            input_mode="typed",
            response_mode="not_applicable",
        )
        tainted_event["message_text"] = "What does this paragraph mean?"
        tainted_event["chat_transcript"] = ["full", "conversation", "history"]

        self.repo.insert_events([tainted_event])
        stored = self.repo.get("assistant-1")

        self.assertNotIn("message_text", stored)
        self.assertNotIn("chat_transcript", stored)
        self.assertEqual(stored["input_mode"], "typed")

    def test_store_and_retrieve_by_session_in_order(self) -> None:
        self.repo.insert_events(
            [
                assistant(
                    7,
                    event_number=2,
                    direction="assistant",
                    input_mode="not_applicable",
                    response_mode="text",
                ),
                assistant(
                    5,
                    event_number=1,
                    direction="learner",
                    input_mode="typed",
                    response_mode="not_applicable",
                ),
            ]
        )

        stored = self.repo.list_by_session("session-1")

        self.assertEqual([item["event_id"] for item in stored], ["assistant-1", "assistant-2"])


class SessionPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = SessionRepository(_database())

    def test_upsert_then_get_round_trips_session(self) -> None:
        self.repo.upsert_session(session())

        stored = self.repo.get("session-1")

        self.assertEqual(stored["session_id"], "session-1")
        self.assertEqual(stored["status"], "completed")
        self.assertIn("created_at", stored)
        self.assertIn("updated_at", stored)

    def test_repeated_upsert_preserves_created_at_but_refreshes_updated_at(self) -> None:
        self.repo.upsert_session(session(), now="2026-08-17T09:00:00Z")
        self.repo.upsert_session(session(), now="2026-08-17T09:05:00Z")

        stored = self.repo.get("session-1")

        self.assertEqual(stored["created_at"], "2026-08-17T09:00:00Z")
        self.assertEqual(stored["updated_at"], "2026-08-17T09:05:00Z")

    def test_list_by_user(self) -> None:
        self.repo.upsert_session(session())

        stored = self.repo.list_by_user("user-1")

        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["user_id"], "user-1")


class ChunkProgressPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = ChunkProgressRepository(_database())

    def test_entered_then_completed_merge_into_one_document(self) -> None:
        self.repo.upsert_progress(
            {
                "session_id": "session-1",
                "content_id": "content-1",
                "chunk_id": "chunk-1",
                "entered_at": timestamp(0),
                "status": "in_progress",
                "is_critical": True,
            }
        )
        self.repo.upsert_progress(
            {
                "session_id": "session-1",
                "content_id": "content-1",
                "chunk_id": "chunk-1",
                "completed_at": timestamp(30),
                "status": "completed",
            }
        )

        stored = self.repo.get("session-1", "chunk-1")

        self.assertEqual(stored["entered_at"], timestamp(0))
        self.assertEqual(stored["completed_at"], timestamp(30))
        self.assertEqual(stored["status"], "completed")
        self.assertTrue(stored["is_critical"])

    def test_list_by_session(self) -> None:
        self.repo.upsert_progress(
            {
                "session_id": "session-1",
                "content_id": "content-1",
                "chunk_id": "chunk-1",
                "entered_at": timestamp(0),
                "status": "in_progress",
            }
        )

        stored = self.repo.list_by_session("session-1")

        self.assertEqual(len(stored), 1)


class SessionAnalyticsPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = SessionAnalyticsRepository(_database())
        data = fixture("normal_completed_session")
        self.summary = build_session_summary(
            data["session"],
            data["engagement_events"],
            data["intervention_events"],
            data["assistant_events"],
            computed_at=timestamp(120),
            chunk_context=data["chunk_context"],
        )

    def test_save_then_get_round_trips_the_domain_summary(self) -> None:
        self.repo.save(self.summary, now="2026-08-17T09:02:00Z")

        stored = self.repo.get("session-1", "1.0")

        self.assertEqual(stored["session_id"], "session-1")
        self.assertEqual(stored["metric_version"], "1.0")
        self.assertEqual(stored["insight_report_status"], "pending")
        self.assertEqual(stored["summary"], self.summary)

    def test_repeated_generation_does_not_duplicate_the_summary(self) -> None:
        self.repo.save(self.summary, now="2026-08-17T09:02:00Z")
        self.repo.save(self.summary, now="2026-08-17T09:03:00Z")
        self.repo.save(self.summary, now="2026-08-17T09:04:00Z")

        matching_documents = list(
            self.repo._collection.find(
                {"session_id": "session-1", "metric_version": "1.0"}
            )
        )

        self.assertEqual(len(matching_documents), 1)
        self.assertEqual(matching_documents[0]["updated_at"], "2026-08-17T09:04:00Z")

    def test_retrieve_historical_summaries_by_user(self) -> None:
        self.repo.save(self.summary)

        stored = self.repo.list_by_user("user-1")

        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["session_id"], "session-1")

    def test_insight_report_status_can_be_updated_independently(self) -> None:
        self.repo.save(self.summary)

        self.repo.set_insight_report_status("session-1", "1.0", "generated")

        stored = self.repo.get("session-1", "1.0")
        self.assertEqual(stored["insight_report_status"], "generated")


class LearningProfilePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = LearningProfileRepository(_database())
        self.profile = {
            "schema_version": "1.0",
            "metric_version": "1.0",
            "user_id": "user-1",
            "sessions_analyzed": 3,
            "analysis_date_range": {
                "started_at": timestamp(0),
                "ended_at": timestamp(1000),
            },
            "average_session_duration_seconds": 600,
            "average_focus_percentage": 72.5,
            "focus_trend": "stable",
            "recovery_trend": "insufficient_data",
            "intervention_effectiveness_by_type": [],
            "assistant_usage_patterns": {
                "sessions_with_assistant_use": 2,
                "average_learner_messages_per_session": 1.5,
                "typed_input_count": 3,
                "voice_input_count": 0,
                "suggested_question_count": 0,
                "preferred_input_mode": "typed",
            },
            "recurring_difficulty_areas": [],
            "effective_support_methods": [],
            "critical_section_aggregates": {
                "sections_observed": 1,
                "sessions_with_critical_sections": 1,
                "average_engagement_rate": 0.8,
                "average_focus_percentage": 70.0,
            },
            "data_quality": {
                "sessions_with_sufficient_data": 3,
                "average_event_coverage_rate": 0.9,
                "flags": [],
            },
            "computed_at": timestamp(1000),
        }

    def test_save_then_get_round_trips_profile(self) -> None:
        self.repo.save(self.profile)

        stored = self.repo.get("user-1")

        self.assertEqual(stored["sessions_analyzed"], 3)
        self.assertEqual(stored["focus_trend"], "stable")

    def test_recompute_replaces_rather_than_duplicates(self) -> None:
        self.repo.save(self.profile)
        updated_profile = dict(self.profile, sessions_analyzed=5)
        self.repo.save(updated_profile)

        stored = self.repo.get("user-1")
        self.assertEqual(stored["sessions_analyzed"], 5)


class IndexPresenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = _database()
        ensure_indexes(self.database)

    def test_sessions_indexes_exist(self) -> None:
        names = self.database[collections.SESSIONS].index_information()
        self.assertIn("uniq_session_id", names)
        self.assertIn("user_id_started_at", names)
        self.assertIn("status", names)

    def test_engagement_event_indexes_exist(self) -> None:
        names = self.database[collections.ENGAGEMENT_EVENTS].index_information()
        self.assertIn("uniq_event_id", names)
        self.assertIn("session_id_timestamp", names)
        self.assertIn("content_id_chunk_id", names)

    def test_intervention_event_indexes_exist(self) -> None:
        names = self.database[collections.INTERVENTION_EVENTS].index_information()
        self.assertIn("uniq_intervention_id", names)
        self.assertIn("session_id_timestamp", names)

    def test_assistant_event_indexes_exist(self) -> None:
        names = self.database[collections.ASSISTANT_EVENTS].index_information()
        self.assertIn("uniq_event_id", names)
        self.assertIn("session_id_timestamp", names)

    def test_session_analytics_indexes_exist(self) -> None:
        names = self.database[collections.SESSION_ANALYTICS].index_information()
        self.assertIn("uniq_session_metric_version", names)
        self.assertIn("user_id_completed_at", names)

    def test_learning_profile_indexes_exist(self) -> None:
        names = self.database[collections.LEARNING_PROFILES].index_information()
        self.assertIn("uniq_user_id", names)

    def test_ensure_indexes_is_safe_to_call_twice(self) -> None:
        ensure_indexes(self.database)  # must not raise


if __name__ == "__main__":
    unittest.main()
