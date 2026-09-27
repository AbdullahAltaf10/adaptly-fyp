"""
Scope 6.5's second half: confusion and frustration reaching a decision.

`classify_conversational_signal` already ran on every message, and its result
went into the assistant's own prompt and nowhere else - its docstring called
the precedence order "for a future downstream support layer". A learner could
type "I don't understand any of this" and the system watching them took no
notice.

These tests pin what the signal does (shortens how long the system waits), what
it does not do (fire an intervention by itself), and that it cannot leak
between learners or outlast the moment.
"""

import unittest

from app.ai_assistant import latest_signal
from app.intervention.decider import (
    ASSISTANT_HELP_PROMPT,
    BULLET_SUMMARY,
    Signals,
)
from app.intervention.policy import (
    DEFAULT_DWELL_LONG,
    DEFAULT_DWELL_SHORT,
    EXPRESSED_DIFFICULTY_DWELL_FACTOR,
    DefaultPolicy,
)


def a_signal(**overrides):
    payload = {
        "state": "struggling",
        "source": "lstm",
        "confidence": 0.8,
        "raw_struggling": True,
        "brow_struggling": False,
        "chunk_id": "chunk-1",
        "content_id": "content-1",
        "dwell_seconds": 0.0,
    }
    payload.update(overrides)
    return Signals(**payload)


class StoreTests(unittest.TestCase):
    def setUp(self):
        latest_signal.clear("u1", "s1")
        latest_signal.clear("u2", "s1")

    def test_a_recorded_signal_can_be_read_back(self):
        latest_signal.record("u1", "s1", "confusion", now=100.0)

        self.assertEqual(latest_signal.get("u1", "s1", now=110.0), "confusion")

    def test_it_expires(self):
        """A sentence typed twenty minutes ago is not news about right now."""
        latest_signal.record("u1", "s1", "frustration", now=100.0)

        stale = 100.0 + latest_signal.MAX_AGE_SECONDS + 1
        self.assertIsNone(latest_signal.get("u1", "s1", now=stale))

    def test_neutral_does_not_erase_an_earlier_signal(self):
        """Saying "I'm lost" then asking a plain question is still being lost."""
        latest_signal.record("u1", "s1", "confusion", now=100.0)
        latest_signal.record("u1", "s1", "neutral", now=101.0)

        self.assertEqual(latest_signal.get("u1", "s1", now=102.0), "confusion")

    def test_one_learners_words_never_reach_another_learners_session(self):
        latest_signal.record("u1", "s1", "frustration", now=100.0)

        self.assertIsNone(latest_signal.get("u2", "s1", now=101.0))

    def test_clearing_forgets_it(self):
        latest_signal.record("u1", "s1", "confusion", now=100.0)
        latest_signal.clear("u1", "s1")

        self.assertIsNone(latest_signal.get("u1", "s1", now=101.0))

    def test_recording_never_raises_on_bad_input(self):
        latest_signal.record("u1", "s1", None, now=100.0)

        self.assertIsNone(latest_signal.get("u1", "s1", now=101.0))


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = DefaultPolicy()

    def test_expressed_difficulty_shortens_the_wait(self):
        long_gate, short_gate = self.policy.gates_for(
            a_signal(expressed_difficulty="confusion")
        )

        self.assertAlmostEqual(long_gate, DEFAULT_DWELL_LONG * EXPRESSED_DIFFICULTY_DWELL_FACTOR)
        self.assertAlmostEqual(short_gate, DEFAULT_DWELL_SHORT * EXPRESSED_DIFFICULTY_DWELL_FACTOR)

    def test_no_expressed_difficulty_leaves_the_gates_alone(self):
        self.assertEqual(
            self.policy.gates_for(a_signal()), (DEFAULT_DWELL_LONG, DEFAULT_DWELL_SHORT)
        )

    def test_it_compounds_with_a_critical_section(self):
        """Lost on a section HR flagged is where waiting is least defensible."""
        gates = self.policy.gates_for(
            a_signal(is_critical=True, expressed_difficulty="frustration")
        )

        self.assertLess(gates[0], self.policy.gates_for(a_signal(is_critical=True))[0])

    def test_it_never_fires_an_intervention_on_its_own(self):
        """Words say the learner is struggling, not with which paragraph.

        No dwell, no engagement evidence: saying so must not by itself
        interrupt someone who may have worked it out while typing.
        """
        decision = self.policy.decide(
            a_signal(
                state="focused",
                raw_struggling=False,
                brow_struggling=False,
                dwell_seconds=0.0,
                expressed_difficulty="frustration",
            )
        )

        self.assertIsNone(decision)

    def test_it_brings_a_more_useful_response_forward(self):
        """Not a new interruption - the same one, sooner.

        At a dwell between the lowered gate and the normal one, a learner who
        has said nothing gets the gentlest fallback (an offer of the
        assistant). One who has just said they are confused gets the summary
        that the extra seconds of dwell would have earned them anyway.
        """
        dwell = DEFAULT_DWELL_SHORT * EXPRESSED_DIFFICULTY_DWELL_FACTOR + 0.5
        self.assertLess(dwell, DEFAULT_DWELL_SHORT)

        without = self.policy.decide(a_signal(dwell_seconds=dwell))
        with_signal = self.policy.decide(
            a_signal(dwell_seconds=dwell, expressed_difficulty="confusion")
        )

        self.assertEqual(without.intervention_type, ASSISTANT_HELP_PROMPT)
        self.assertEqual(with_signal.intervention_type, BULLET_SUMMARY)


if __name__ == "__main__":
    unittest.main()
