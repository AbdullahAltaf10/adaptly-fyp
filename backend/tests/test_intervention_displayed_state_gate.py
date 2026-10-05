"""Audit 2026-10-04: interventions must not fire while the displayed state is focused,
and the assistant prompt needs the bullet minimum dwell (15 s)."""
from app.intervention.decider import Signals
from app.intervention.policy import DefaultPolicy


def _s(state, raw=True, brow=True, dwell=50.0):
    return Signals(state=state, source="lstm", confidence=0.7, raw_struggling=raw,
                   brow_struggling=brow, dwell_seconds=dwell)


def test_no_struggling_intervention_when_the_displayed_state_is_focused():
    assert DefaultPolicy().decide(_s("focused"), history=[], recovery=None) is None


def test_struggling_intervention_fires_when_the_displayed_state_is_struggling():
    d = DefaultPolicy().decide(_s("struggling"), history=[], recovery=None)
    assert d is not None and d.intervention_type == "simplify_content"


def test_bullets_fire_on_drifting_displayed_state_with_broad_evidence():
    d = DefaultPolicy().decide(_s("drifting", raw=True, brow=False, dwell=20), history=[], recovery=None)
    assert d is not None and d.intervention_type == "bullet_summary"


def test_assistant_prompt_needs_minimum_dwell():
    assert DefaultPolicy().decide(_s("struggling", raw=True, brow=False, dwell=5), history=[], recovery=None) is None
    d = DefaultPolicy().decide(_s("struggling", raw=True, brow=False, dwell=20), history=[], recovery=None)
    assert d is not None and d.intervention_type == "bullet_summary"


def test_paragraph_revisit_path_is_unchanged():
    s = Signals(state="focused", source="lstm", confidence=0.7, raw_struggling=False,
                brow_struggling=False, dwell_seconds=0.0, paragraph_revisit_detected=True)
    d = DefaultPolicy().decide(s, history=[], recovery=None)
    assert d is not None and d.intervention_type == "assistant_help_prompt"
