"""Tests for Module 10 critical-section attestation evidence (Issue #73)."""

from __future__ import annotations

import unittest

from backend.app.compliance.domain.critical_sections import (
    build_critical_section_evidence,
)


def _segment(state: str, chunk_id: str | None, *, start: str, end: str, duration: float):
    return {
        "started_at": start,
        "ended_at": end,
        "duration_seconds": duration,
        "state": state,
        "average_confidence": 0.9 if state != "unknown" else None,
        "chunk_id": chunk_id,
    }


def _chunk(chunk_id: str, *, is_critical: bool = True, completed: bool = True):
    return {"chunk_id": chunk_id, "is_critical": is_critical, "completed": completed}


def _intervention(chunk_id: str):
    return {"chunk_id": chunk_id}


class VerdictTests(unittest.TestCase):
    def test_sustained_engagement(self):
        segments = [
            _segment("focused", "c1", start="t0", end="t10", duration=10),
        ]
        evidence = build_critical_section_evidence(segments, [_chunk("c1")])
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["verdict"], "sustained_engagement")
        self.assertEqual(evidence[0]["focused_seconds"], 10)
        self.assertEqual(evidence[0]["difficulty_seconds"], 0)

    def test_difficulty_then_recovered(self):
        segments = [
            _segment("struggling", "c2", start="t0", end="t5", duration=5),
            _segment("focused", "c2", start="t5", end="t10", duration=5),
        ]
        evidence = build_critical_section_evidence(segments, [_chunk("c2")])
        self.assertEqual(evidence[0]["verdict"], "difficulty_then_recovered")
        self.assertEqual(evidence[0]["focused_seconds"], 5)
        self.assertEqual(evidence[0]["difficulty_seconds"], 5)

    def test_difficulty_not_recovered(self):
        segments = [
            _segment("struggling", "c3", start="t0", end="t5", duration=5),
            _segment("drifting", "c3", start="t5", end="t10", duration=5),
        ]
        evidence = build_critical_section_evidence(segments, [_chunk("c3")])
        self.assertEqual(evidence[0]["verdict"], "difficulty_not_recovered")

    def test_difficulty_after_recovery_is_not_recovered(self):
        # focused -> struggling -> recovered -> struggling: the chunk's last
        # known state is difficulty, so this must NOT read as
        # difficulty_then_recovered just because a positive segment exists
        # somewhere earlier in the chunk's history.
        segments = [
            _segment("focused", "c1", start="t0", end="t5", duration=5),
            _segment("struggling", "c1", start="t5", end="t10", duration=5),
            _segment("recovered", "c1", start="t10", end="t15", duration=5),
            _segment("struggling", "c1", start="t15", end="t20", duration=5),
        ]
        evidence = build_critical_section_evidence(segments, [_chunk("c1")])
        self.assertEqual(evidence[0]["verdict"], "difficulty_not_recovered")

    def test_not_reached(self):
        segments = [
            _segment("focused", "other-chunk", start="t0", end="t10", duration=10),
        ]
        evidence = build_critical_section_evidence(segments, [_chunk("c4")])
        self.assertEqual(evidence[0]["verdict"], "not_reached")
        self.assertIsNone(evidence[0]["first_seen_at"])
        self.assertIsNone(evidence[0]["last_seen_at"])
        self.assertEqual(evidence[0]["focused_seconds"], 0)

    def test_insufficient_data_when_every_segment_is_unknown(self):
        segments = [
            _segment("unknown", "c5", start="t0", end="t10", duration=10),
        ]
        evidence = build_critical_section_evidence(segments, [_chunk("c5")])
        self.assertEqual(evidence[0]["verdict"], "insufficient_data")
        self.assertIsNotNone(evidence[0]["first_seen_at"])

    def test_unknown_segments_are_ignored_not_counted_as_a_break(self):
        # focused -> unknown -> focused on the same chunk must still read as
        # sustained engagement; the unknown gap must not introduce a false
        # "difficulty" reading or otherwise break continuity.
        segments = [
            _segment("focused", "c1", start="t0", end="t5", duration=5),
            _segment("unknown", "c1", start="t5", end="t8", duration=3),
            _segment("focused", "c1", start="t8", end="t12", duration=4),
        ]
        evidence = build_critical_section_evidence(segments, [_chunk("c1")])
        self.assertEqual(evidence[0]["verdict"], "sustained_engagement")
        self.assertEqual(evidence[0]["focused_seconds"], 9)


class MixedAndMultipleChunksTests(unittest.TestCase):
    def test_multiple_critical_chunks_each_get_their_own_correct_verdict(self):
        segments = [
            _segment("focused", "c1", start="t0", end="t10", duration=10),
            _segment("struggling", "c2", start="t10", end="t15", duration=5),
            _segment("focused", "c2", start="t15", end="t20", duration=5),
            _segment("struggling", "c3", start="t20", end="t25", duration=5),
        ]
        chunk_context = [_chunk("c1"), _chunk("c2"), _chunk("c3"), _chunk("c4")]
        evidence = build_critical_section_evidence(segments, chunk_context)
        verdicts = {item["chunk_id"]: item["verdict"] for item in evidence}
        self.assertEqual(
            verdicts,
            {
                "c1": "sustained_engagement",
                "c2": "difficulty_then_recovered",
                "c3": "difficulty_not_recovered",
                "c4": "not_reached",
            },
        )

    def test_non_critical_chunks_are_excluded_entirely(self):
        segments = [_segment("focused", "c1", start="t0", end="t10", duration=10)]
        chunk_context = [_chunk("c1", is_critical=True), _chunk("c2", is_critical=False)]
        evidence = build_critical_section_evidence(segments, chunk_context)
        self.assertEqual([item["chunk_id"] for item in evidence], ["c1"])

    def test_revisited_chunk_combines_all_visits_and_counts_interventions(self):
        # The learner leaves c1 after struggling, comes back later (after a
        # different chunk in between) and recovers. Duration and verdict
        # must reflect the whole history, not just the most recent visit.
        segments = [
            _segment("struggling", "c1", start="t0", end="t5", duration=5),
            _segment("focused", "other", start="t5", end="t10", duration=5),
            _segment("focused", "c1", start="t10", end="t15", duration=5),
        ]
        interventions = [_intervention("c1"), _intervention("c1"), _intervention("other")]
        evidence = build_critical_section_evidence(
            segments, [_chunk("c1")], interventions
        )
        self.assertEqual(evidence[0]["verdict"], "difficulty_then_recovered")
        self.assertEqual(evidence[0]["focused_seconds"], 5)
        self.assertEqual(evidence[0]["difficulty_seconds"], 5)
        self.assertEqual(evidence[0]["intervention_count"], 2)
        self.assertEqual(evidence[0]["first_seen_at"], "t0")
        self.assertEqual(evidence[0]["last_seen_at"], "t15")


class EmptyCriticalListTests(unittest.TestCase):
    def test_no_chunks_marked_critical_returns_empty_list(self):
        segments = [_segment("focused", "c1", start="t0", end="t10", duration=10)]
        evidence = build_critical_section_evidence(
            segments, [_chunk("c1", is_critical=False)]
        )
        self.assertEqual(evidence, [])

    def test_no_chunk_context_at_all_returns_empty_list(self):
        segments = [_segment("focused", "c1", start="t0", end="t10", duration=10)]
        self.assertEqual(build_critical_section_evidence(segments, None), [])
        self.assertEqual(build_critical_section_evidence(segments, []), [])


if __name__ == "__main__":
    unittest.main()
