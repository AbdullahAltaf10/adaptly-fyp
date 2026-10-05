"""A learner's own history steering Module 4 (scope 6.1).

The property that matters is one-directional: **history can make support
gentler and can never make it pushier.** Every evidence tier in policy.py
exists because rewriting what someone is reading is the most intrusive thing
this system does; a learner for whom rewriting has worked must not be rewritten
to on weaker evidence. So most of these tests are about what does NOT change.
"""

import pytest

from app.intervention import preferences
from app.intervention.decider import (
    ASSISTANT_HELP_PROMPT,
    BREAK_SUGGESTION,
    BULLET_SUMMARY,
    SIMPLIFY_CONTENT,
    Signals,
)
from app.intervention.policy import (
    DEFAULT_DWELL_LONG,
    DEFAULT_DWELL_SHORT,
    DefaultPolicy,
)

policy = DefaultPolicy()


def signals(**over):
    base = dict(
        state="struggling",
        source="lstm",
        confidence=0.5,
        raw_struggling=True,
        brow_struggling=True,
        chunk_id="c1",
        content_id="d1",
        dwell_seconds=DEFAULT_DWELL_LONG + 10,
    )
    base.update(over)
    return Signals(**base)


def effectiveness(kind, effective, ineffective, unknown=0):
    total = effective + ineffective + unknown
    evaluable = effective + ineffective
    return {
        "intervention_type": kind,
        "total_count": total,
        "effective_count": effective,
        "ineffective_count": ineffective,
        "unknown_outcome_count": unknown,
        "effectiveness_rate": (effective / evaluable) if evaluable else None,
    }


def profile(*items):
    return {"intervention_effectiveness_by_type": list(items)}


# ------------------------------------------------- reading the profile

def test_a_clearly_poor_record_discourages_a_type():
    p = profile(effectiveness(SIMPLIFY_CONTENT, effective=0, ineffective=5))
    assert preferences.discouraged_from_profile(p) == {SIMPLIFY_CONTENT}


def test_too_few_outcomes_is_not_a_pattern():
    # Three unlucky tries is noise, not a learner who cannot use simplification.
    p = profile(effectiveness(SIMPLIFY_CONTENT, effective=0, ineffective=3))
    assert preferences.discouraged_from_profile(p) == frozenset()


def test_unknown_outcomes_are_not_evidence_either_way():
    # Most interventions have an unknown outcome. Counting them as failures would
    # discourage every type for every learner.
    p = profile(effectiveness(SIMPLIFY_CONTENT, effective=0, ineffective=1, unknown=20))
    assert preferences.discouraged_from_profile(p) == frozenset()


def test_a_type_that_mostly_helps_is_never_discouraged():
    p = profile(effectiveness(SIMPLIFY_CONTENT, effective=4, ineffective=2))
    assert preferences.discouraged_from_profile(p) == frozenset()


def test_the_threshold_is_strict_at_the_boundary():
    at = preferences.DISCOURAGE_AT_OR_BELOW
    n = 8
    just_under = profile(effectiveness(SIMPLIFY_CONTENT, effective=int(n * at), ineffective=n - int(n * at)))
    above = profile(effectiveness(SIMPLIFY_CONTENT, effective=int(n * at) + 1, ineffective=n - int(n * at) - 1))
    assert preferences.discouraged_from_profile(just_under) == {SIMPLIFY_CONTENT}
    assert preferences.discouraged_from_profile(above) == frozenset()


@pytest.mark.parametrize("kind", [BREAK_SUGGESTION, ASSISTANT_HELP_PROMPT, "other"])
def test_a_break_and_the_assistant_are_never_withheld_on_history(kind):
    # A break for tiredness and an offer of help are not things to hold back
    # because an earlier one went unnoticed.
    p = profile(effectiveness(kind, effective=0, ineffective=9))
    assert preferences.discouraged_from_profile(p) == frozenset()


@pytest.mark.parametrize("bad", [None, {}, [], "x", {"intervention_effectiveness_by_type": None},
                                 {"intervention_effectiveness_by_type": [{"nonsense": 1}]},
                                 {"intervention_effectiveness_by_type": ["str"]}])
def test_a_missing_or_malformed_profile_changes_nothing(bad):
    assert preferences.discouraged_from_profile(bad) == frozenset()


# ----------------------------------------------- what the policy does

def test_with_no_history_the_policy_is_exactly_what_it_was():
    assert policy.decide(signals()).intervention_type == SIMPLIFY_CONTENT


def test_a_discouraged_rewrite_becomes_a_summary_and_says_why():
    decision = policy.decide(signals(discouraged_types=frozenset({SIMPLIFY_CONTENT})))
    assert decision.intervention_type == BULLET_SUMMARY
    assert "has not helped you before" in decision.reason
    assert "simplified text" in decision.reason


def test_a_discouraged_summary_becomes_the_assistant_offer_and_says_why():
    decision = policy.decide(
        signals(dwell_seconds=DEFAULT_DWELL_SHORT + 5, discouraged_types=frozenset({BULLET_SUMMARY}))
    )
    assert decision.intervention_type == ASSISTANT_HELP_PROMPT
    assert "a summary has not helped you before" in decision.reason


def test_both_discouraged_falls_all_the_way_to_the_gentlest_offer():
    decision = policy.decide(
        signals(discouraged_types=frozenset({SIMPLIFY_CONTENT, BULLET_SUMMARY}))
    )
    assert decision.intervention_type == ASSISTANT_HELP_PROMPT


def test_the_reason_is_not_changed_when_history_had_nothing_to_do_with_it():
    # Discouraging a type the evidence would never have earned must not put a
    # false explanation in Module 8's log.
    weak = signals(raw_struggling=True, brow_struggling=False,
                   dwell_seconds=DEFAULT_DWELL_SHORT + 5,
                   discouraged_types=frozenset({SIMPLIFY_CONTENT}))
    decision = policy.decide(weak)
    assert decision.intervention_type == BULLET_SUMMARY
    assert "has not helped" not in decision.reason


def test_history_can_never_promote_a_learner_to_a_more_intrusive_response():
    # THE property. Whatever is discouraged, the response is never more
    # intrusive than the evidence alone would have chosen.
    order = {ASSISTANT_HELP_PROMPT: 0, BULLET_SUMMARY: 1, SIMPLIFY_CONTENT: 2}
    for strong in (True, False):
        for dwell in (DEFAULT_DWELL_SHORT, DEFAULT_DWELL_SHORT + 1, DEFAULT_DWELL_LONG + 1):
            for discouraged in (frozenset(), {SIMPLIFY_CONTENT}, {BULLET_SUMMARY},
                                {SIMPLIFY_CONTENT, BULLET_SUMMARY}):
                base = policy.decide(signals(brow_struggling=strong, dwell_seconds=dwell))
                personal = policy.decide(signals(brow_struggling=strong, dwell_seconds=dwell,
                                                 discouraged_types=frozenset(discouraged)))
                assert order[personal.intervention_type] <= order[base.intervention_type], (
                    strong, dwell, discouraged)


def test_fatigue_still_gets_a_break_whatever_the_history_says():
    decision = policy.decide(
        signals(state="fatigued", discouraged_types=frozenset({SIMPLIFY_CONTENT, BULLET_SUMMARY}))
    )
    assert decision.intervention_type == BREAK_SUGGESTION


def test_a_recovering_learner_is_still_left_alone():
    assert policy.decide(signals(state="recovered", discouraged_types=frozenset({SIMPLIFY_CONTENT}))) is None


# --------------------------------------------- reading it safely

def test_a_database_failure_means_no_personalisation_not_a_failed_intervention():
    preferences._cache.clear()

    def boom(uid):
        raise RuntimeError("db unreachable")

    assert preferences.discouraged_for("u1", load=boom) == frozenset()


def test_the_answer_is_cached_so_analyze_does_not_read_the_database_every_ten_seconds():
    preferences._cache.clear()
    calls = []

    def load(uid):
        calls.append(uid)
        return profile(effectiveness(SIMPLIFY_CONTENT, 0, 6))

    first = preferences.discouraged_for("u1", now=100.0, load=load)
    second = preferences.discouraged_for("u1", now=150.0, load=load)
    assert first == second == {SIMPLIFY_CONTENT}
    assert calls == ["u1"]
    # ...but not forever: a profile changes at session end.
    preferences.discouraged_for("u1", now=100.0 + preferences.CACHE_TTL_SECONDS + 1, load=load)
    assert calls == ["u1", "u1"]


def test_one_learners_history_never_reaches_another():
    preferences._cache.clear()

    def load(uid):
        return profile(effectiveness(SIMPLIFY_CONTENT, 0, 6)) if uid == "u1" else None

    assert preferences.discouraged_for("u1", load=load) == {SIMPLIFY_CONTENT}
    assert preferences.discouraged_for("u2", load=load) == frozenset()


def test_the_decision_is_taken_from_the_server_not_the_request():
    # Signals is built inside the service from the stored profile; the analyze
    # request model has no field that could carry it.
    from app.engagement.routes import AnalyzeRequest

    assert "discouraged_types" not in AnalyzeRequest.model_fields


# ------------------------------------------- through the real service

def _evaluate_strongly(uid="u1", session="s1", **over):
    from app.intervention import service

    args = dict(
        state="struggling", source="lstm", confidence=0.5,
        raw_struggling=True, brow_struggling=True,
        content_id="d1", chunk_id="c1", dwell_seconds=DEFAULT_DWELL_LONG + 10,
    )
    args.update(over)
    return service.evaluate(uid, session, **args)


@pytest.fixture
def isolated(monkeypatch):
    """The service with storage, chunk lookup and cooldown out of the way."""
    from app.intervention import content, cooldown, service, store

    saved = {}
    monkeypatch.setattr(store, "save", lambda event: saved.__setitem__(event["intervention_id"], event) or True)
    monkeypatch.setattr(store, "list_for_session", lambda sid: [])
    monkeypatch.setattr(content, "is_critical", lambda *a, **k: False)
    monkeypatch.setattr(cooldown, "is_cooling", lambda *a, **k: False)
    monkeypatch.setattr(cooldown, "start", lambda *a, **k: None, raising=False)
    preferences._cache.clear()
    yield monkeypatch
    preferences._cache.clear()


def test_a_new_learner_with_no_profile_gets_the_ordinary_decision(isolated):
    isolated.setattr(preferences, "_load_profile", lambda uid: None)
    result = _evaluate_strongly()
    assert result["intervention"]["intervention_type"] == SIMPLIFY_CONTENT


def test_a_learner_for_whom_rewriting_failed_is_offered_a_summary_end_to_end(isolated):
    isolated.setattr(
        preferences, "_load_profile",
        lambda uid: profile(effectiveness(SIMPLIFY_CONTENT, effective=0, ineffective=6)),
    )
    result = _evaluate_strongly()
    payload = result["intervention"]
    assert payload["intervention_type"] == BULLET_SUMMARY
    # The reason a learner may see must be the true one.
    assert "has not helped you before" in payload["reason"]


def test_another_learner_is_not_affected_by_this_learners_history(isolated):
    isolated.setattr(
        preferences, "_load_profile",
        lambda uid: profile(effectiveness(SIMPLIFY_CONTENT, 0, 6)) if uid == "u1" else None,
    )
    assert _evaluate_strongly(uid="u1")["intervention"]["intervention_type"] == BULLET_SUMMARY
    assert _evaluate_strongly(uid="u2", session="s2")["intervention"]["intervention_type"] == SIMPLIFY_CONTENT


def test_the_event_records_which_policy_made_the_decision(isolated):
    # Module 8 records policy_version on every event, and personalisation means
    # the same signals can now yield a different decision, so the version has to
    # say which behaviour produced it.
    from app.intervention import store
    from app.intervention.policy import POLICY_VERSION

    seen = []
    isolated.setattr(store, "save", lambda event: seen.append(event) or True)
    isolated.setattr(preferences, "_load_profile", lambda uid: None)

    _evaluate_strongly()

    assert seen and seen[0]["policy_version"] == POLICY_VERSION
    assert POLICY_VERSION != "v1-tiered"
