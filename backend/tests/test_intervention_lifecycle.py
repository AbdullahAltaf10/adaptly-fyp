"""
Module 4 P2 - the wiring, the lifecycle, and what actually gets stored.

P1's tests cover the decision, which is a pure function. These cover the part
that is not pure and where the expensive mistakes live: an intervention that is
recorded but never reaches a status anything measures, a stored timestamp that
points at the wrong moment, or a delivery report a client can forge.

The three that would otherwise have failed silently
---------------------------------------------------
**An intervention left at `offered` is invisible.** Module 8 begins measuring
recovery from `displayed` for automatic types and `accepted` for
learner-initiated ones, and from `offered` for neither. Fire-and-forget gives a
full event collection and an empty dashboard, with nothing raising anywhere.

**`delivered_at` is the whole measurement.** Module 8 reads exactly one field
to decide when to start measuring, and there is no fallback - an intervention
without `delivered_at` is invisible to every recovery metric. This module is
the only thing that sets it, so a lifecycle that never advances produces events
that look complete and count for nothing.

It is written once and must never move. `delivery_status` carries on to
`dismissed` or `completed` afterwards, and an intervention that helped and was
later dismissed has to keep its measurement - that was #46.

**Delivery is reported by the browser.** Without a transition graph a client
could post `completed` against something that was never rendered and
manufacture a measurement for it.

No network and no model load: the model is stubbed at the route's own seam, and
the database is a fake collection that behaves like the two pymongo calls this
module makes.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth.dependencies import get_current_user  # noqa: E402
from app.engagement import furrow, routes as engagement_routes  # noqa: E402
from app.intervention import content, contracts, cooldown, service, store  # noqa: E402
from app.intervention.decider import (  # noqa: E402
    ASSISTANT_HELP_PROMPT,
    BREAK_SUGGESTION,
    BULLET_SUMMARY,
    SIMPLIFY_CONTENT,
    TIER_BROAD,
    Decision,
    Signals,
)
from app.main import app  # noqa: E402

client = TestClient(app)


# --------------------------------------------------------------------------
# A database that behaves like the two calls store.py makes, and no more
# --------------------------------------------------------------------------

class FakeCollection:
    def __init__(self):
        self.docs = {}
        self.fail = False

    def replace_one(self, query, document, upsert=False):
        if self.fail:
            raise RuntimeError("no connection")
        self.docs[query["_id"]] = dict(document)

        class R:
            upserted_id = query["_id"]

        return R()

    def find_one(self, query):
        if self.fail:
            raise RuntimeError("no connection")
        found = self.docs.get(query["_id"])
        return dict(found) if found else None

    def find(self, query):
        if self.fail:
            raise RuntimeError("no connection")
        matched = [dict(d) for d in self.docs.values()
                   if all(d.get(k) == v for k, v in query.items())]

        class Cursor:
            def __init__(self, items):
                self.items = items

            def sort(self, field, direction=1):
                self.items.sort(key=lambda d: d.get(field, ""), reverse=direction < 0)
                return self.items

            def __iter__(self):
                return iter(self.items)

        return Cursor(matched)


class FakeDB:
    def __init__(self):
        self.collection = FakeCollection()

    def __getitem__(self, name):
        return self.collection

    def __getattr__(self, name):
        return self.collection


@pytest.fixture
def fake_store(monkeypatch):
    database = FakeDB()
    monkeypatch.setattr(store, "db", database)
    return database.collection


@pytest.fixture(autouse=True)
def clean_state():
    cooldown.reset("u1", "s1")
    cooldown.reset("u2", "s1")
    original = service.get_decider()
    yield
    service.set_decider(original)
    cooldown.reset("u1", "s1")
    cooldown.reset("u2", "s1")
    app.dependency_overrides.clear()


def as_user(uid="u1"):
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": f"{uid}@t.com"}


def an_event(intervention_type=SIMPLIFY_CONTENT, uid="u1", session="s1", timestamp="t0"):
    decision = Decision(
        intervention_type=intervention_type,
        reason_code="struggling",
        reason="Signs of difficulty.",
        tier=TIER_BROAD,
        chunk_id="3",
        content_id="c1",
    )
    return contracts.build_intervention_event(
        decision=decision, user_id=uid, session_id=session,
        triggering_engagement_state="struggling", timestamp=timestamp,
        policy_version="v1-tiered",
    )


def signals(**overrides):
    base = dict(
        state="struggling", source="lstm", confidence=0.4,
        raw_struggling=False, brow_struggling=False,
        chunk_id="3", content_id="c1", is_critical=False,
        dwell_seconds=0.0, engagement_event_id="e1",
    )
    base.update(overrides)
    return Signals(**base)


# --------------------------------------------------------------------------
# The transition graph - delivery is an untrusted report
# --------------------------------------------------------------------------

def test_a_client_cannot_jump_straight_to_a_measured_status():
    """
    The attack this closes: `completed` posted against something never
    rendered would anchor a recovery measurement for an intervention nobody
    saw, and every number computed from it would be fiction.
    """
    event = an_event()
    with pytest.raises(contracts.InvalidTransition):
        contracts.advance(event, "completed")
    with pytest.raises(contracts.InvalidTransition):
        contracts.advance(event, "accepted")


def test_offered_can_only_be_displayed_or_fail():
    event = an_event()
    assert contracts.advance(event, "displayed")["delivery_status"] == "displayed"
    assert contracts.advance(event, "failed")["delivery_status"] == "failed"


@pytest.mark.parametrize("terminal", ["dismissed", "completed", "failed"])
def test_a_finished_intervention_cannot_move_again(terminal):
    event = an_event()
    event = contracts.advance(event, "displayed")
    if terminal != "dismissed":
        event = contracts.advance(event, terminal)
    else:
        event = contracts.advance(event, "dismissed")
    for status in contracts.DELIVERY_STATUSES:
        with pytest.raises(contracts.InvalidTransition):
            contracts.advance(event, status)


def test_a_status_that_is_not_a_status_is_rejected_before_anything_else():
    with pytest.raises(ValueError):
        contracts.advance(an_event(), "probably")


# --------------------------------------------------------------------------
# The timestamp is the recovery anchor, and stops moving once it is one
# --------------------------------------------------------------------------

def test_an_automatic_type_is_delivered_when_it_is_displayed():
    """`displayed` is where a simplification reaches the learner."""
    event = an_event(SIMPLIFY_CONTENT, timestamp="t0")
    assert event.get("delivered_at") is None, "an offer has not been delivered"

    displayed = contracts.advance(event, "displayed", timestamp="t1")
    assert displayed["delivered_at"] == "t1"

    accepted = contracts.advance(displayed, "accepted", timestamp="t2")
    assert accepted["delivered_at"] == "t1", "delivery moved"
    completed = contracts.advance(accepted, "completed", timestamp="t3")
    assert completed["delivered_at"] == "t1"


def test_a_learner_initiated_type_is_delivered_when_it_is_accepted():
    """
    A break suggestion shown and ignored was never experienced, so `displayed`
    does not count for it - the measurement waits until the learner takes it up.
    """
    event = an_event(BREAK_SUGGESTION, timestamp="t0")

    displayed = contracts.advance(event, "displayed", timestamp="t1")
    assert displayed.get("delivered_at") is None, "showing it is not delivering it"

    accepted = contracts.advance(displayed, "accepted", timestamp="t2")
    assert accepted["delivered_at"] == "t2"
    completed = contracts.advance(accepted, "completed", timestamp="t3")
    assert completed["delivered_at"] == "t2"


def test_the_offer_timestamp_never_moves():
    """
    It used to. `timestamp` was dragged along as a stand-in anchor because the
    contract had nowhere else to put one, which made the time between detecting
    difficulty and actually helping impossible to compute. #54 added
    `delivered_at`, so `timestamp` means what it says again.
    """
    event = an_event(SIMPLIFY_CONTENT, timestamp="t0")
    for status, moment in (("displayed", "t1"), ("accepted", "t2"), ("completed", "t3")):
        event = contracts.advance(event, status, timestamp=moment)
        assert event["timestamp"] == "t0"


def test_a_dismissal_does_not_take_the_measurement_with_it():
    """
    The #46 regression, on Module 4's side. An intervention that was shown,
    helped, and then closed by the learner keeps its `delivered_at`, so it is
    still measured. Recording the dismissal must never cost the measurement.
    """
    event = contracts.advance(an_event(SIMPLIFY_CONTENT), "displayed", timestamp="t1")
    dismissed = contracts.advance(event, "dismissed", timestamp="t2")
    assert dismissed["delivered_at"] == "t1"


LEGAL_PATHS = [
    ("displayed", "accepted", "completed"),
    ("displayed", "accepted", "dismissed"),
    ("displayed", "accepted", "failed"),
    ("displayed", "completed"),
    ("displayed", "dismissed"),
    ("displayed", "failed"),
    ("failed",),
]


@pytest.mark.parametrize("intervention_type", [
    SIMPLIFY_CONTENT, BULLET_SUMMARY, BREAK_SUGGESTION, ASSISTANT_HELP_PROMPT,
])
@pytest.mark.parametrize("path", LEGAL_PATHS)
def test_delivery_is_recorded_once_at_the_first_moment_that_counts(intervention_type, path):
    """
    The general form, over every type and every legal path: `delivered_at` is
    the first moment that counted for that type, it never moves afterwards, and
    the offer time is left alone throughout.
    """
    event = an_event(intervention_type, timestamp="t0")
    expected = None
    for index, status in enumerate(path, start=1):
        event = contracts.advance(event, status, timestamp=f"t{index}")
        if expected is None and contracts.starts_recovery_measurement(intervention_type, status):
            expected = f"t{index}"

    assert event["timestamp"] == "t0"
    assert event.get("delivered_at") == expected

    if expected is None:
        # Never reached a status that counts, so Module 8 measures nothing -
        # which is correct, not a gap.
        assert not any(
            contracts.starts_recovery_measurement(intervention_type, s) for s in path
        )


def test_a_retrying_client_cannot_move_the_delivery_moment():
    """
    Delivery reports come over an unreliable connection. A client that retries
    must not rewrite when the intervention reached the learner.
    """
    event = contracts.advance(an_event(SIMPLIFY_CONTENT), "displayed", timestamp="t1")
    again = contracts.advance(event, "accepted", timestamp="t9")
    assert again["delivered_at"] == "t1"


def test_every_emitted_field_is_one_the_real_contract_accepts():
    """
    Read against the actual schema file rather than a list copied into this
    test, so the two cannot drift.
    """
    import json
    import pathlib

    schema_path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "shared" / "contracts" / "intervention-event.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    allowed = set(schema["properties"])

    if "delivered_at" not in allowed:
        pytest.skip(
            "waiting on #54 to add delivered_at to the contract; Module 8's "
            "allowlist drops unknown fields, so emitting it early is harmless"
        )

    event = an_event(SIMPLIFY_CONTENT)
    event = contracts.advance(event, "displayed")
    event = contracts.advance(event, "completed")
    assert set(event) <= allowed, f"not in contract: {set(event) - allowed}"


def test_dismissal_is_recorded_as_an_outcome_but_claims_nothing_about_helping():
    """
    Dismissal is a delivery fact. It is not evidence the intervention would
    not have worked, and Module 8 reads outcome "dismissed" as unknown rather
    than ineffective, so `helped` must stay None.
    """
    event = contracts.advance(an_event(), "displayed")
    dismissed = contracts.advance(event, "dismissed")
    assert dismissed["outcome"] == "dismissed"
    assert dismissed["helped"] is None


# --------------------------------------------------------------------------
# Storage - written exactly as Module 8's repository would have written it
# --------------------------------------------------------------------------

def test_the_document_is_keyed_on_the_intervention_id(fake_store):
    event = an_event()
    assert store.save(event) is True
    assert list(fake_store.docs) == [event["intervention_id"]]


def test_a_lifecycle_transition_replaces_the_document_rather_than_adding_one(fake_store):
    """
    Module 8 reads one document per intervention and takes its timestamp as
    the anchor. A second row for the same intervention would double-count it
    in every intervention metric.
    """
    event = an_event()
    store.save(event)
    store.save(contracts.advance(event, "displayed"))
    assert len(fake_store.docs) == 1
    assert store.get(event["intervention_id"])["delivery_status"] == "displayed"


def test_anything_outside_the_allowlist_is_dropped_before_the_write(fake_store):
    """
    Defence in depth, mirroring Module 8's own filtering: the contract sets
    additionalProperties false, but nothing enforces that on a direct write.
    """
    event = an_event()
    event["landmarks"] = [[0.1, 0.2]] * 478
    event["tier"] = "strong"
    store.save(event)
    stored = store.get(event["intervention_id"])
    assert "landmarks" not in stored
    assert "tier" not in stored
    assert set(stored) <= store.ALLOWED_FIELDS


def test_the_allowlist_matches_module_8s(fake_store):
    """
    store.py is a stand-in for Module 8's repository and must write identical
    documents. If this drifts, events written before Module 8 merges become
    subtly different from the ones written after.
    """
    module_8_fields = {
        "schema_version", "intervention_id", "session_id", "user_id",
        "content_id", "chunk_id", "timestamp", "intervention_type", "reason",
        "reason_code", "triggering_engagement_state",
        "triggering_engagement_event_id", "delivery_status", "outcome",
        "recovery_timestamp", "recovery_duration_seconds", "helped",
        "policy_version", "model_version",
        # Added by #54: delivered_at is what recovery is measured from, the
        # other two are reserved for Module 6's sequencing.
        "delivered_at", "sequence_id", "step_index",
    }
    assert store.ALLOWED_FIELDS == module_8_fields
    assert store.COLLECTION == "analytics_intervention_events"


def test_an_unreachable_database_is_reported_not_raised(fake_store):
    """Module 4 must never take the analyze endpoint down with it."""
    fake_store.fail = True
    assert store.save(an_event()) is False
    assert store.get("anything") is None
    assert store.list_for_session("s1") == []


# --------------------------------------------------------------------------
# The service - deciding, recording, and reporting delivery
# --------------------------------------------------------------------------

def test_an_offered_intervention_is_stored_before_it_is_returned(fake_store):
    result = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False, engagement_event_id="e1",
    )
    assert result["intervention"] is not None
    stored = store.get(result["intervention"]["intervention_id"])
    assert stored["delivery_status"] == "offered"
    assert stored["policy_version"] == "v1-tiered"


def test_nothing_is_offered_if_it_could_not_be_stored(fake_store):
    """
    An intervention the server has no record of is one the browser cannot
    report delivery for, so it would sit at `offered` forever and count for
    nothing. Staying silent is the safe direction.
    """
    fake_store.fail = True
    result = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=True, engagement_event_id="e1",
    )
    assert result["intervention"] is None
    assert "stored" in result["note"]
    assert cooldown.fired_count("u1", "s1") == 0, "a quiet period was spent on nothing"


def test_the_second_window_is_silent_while_the_first_is_still_being_measured(fake_store):
    first = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )
    second = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )
    assert first["intervention"] is not None
    assert second["intervention"] is None
    assert second["note"] == "cooling down"


def test_the_browser_is_not_told_which_tier_fired(fake_store):
    """
    Scope 6.8 - no scores or indicators during an active session. The tier is
    how much the decider trusted itself, which is one however it is labelled.
    """
    result = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=True, dwell_seconds=90.0,
    )
    payload = result["intervention"]
    assert "tier" not in payload
    assert "confidence" not in payload
    assert "user_id" not in payload
    assert payload["reason"], "the learner-facing sentence is missing"


def test_dwell_from_the_browser_is_bounded_not_trusted(fake_store):
    result = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=True, dwell_seconds=10 ** 9,
    )
    assert result["intervention"]["intervention_type"] == SIMPLIFY_CONTENT

    cooldown.reset("u1", "s1")
    negative = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=True, dwell_seconds=-500.0,
    )
    assert negative["intervention"]["intervention_type"] == ASSISTANT_HELP_PROMPT


def test_a_failed_delivery_gives_the_quiet_period_back(fake_store):
    """
    A renderer that breaks must not silently starve somebody of support for
    two minutes at a time - nothing reached them.
    """
    offered = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )["intervention"]
    service.update_status("u1", "s1", offered["intervention_id"], "failed")
    assert cooldown.is_cooling("u1", "s1") is False


def test_a_dismissal_does_not(fake_store):
    """They saw it and said no. Asking again at once is what cooldown is for."""
    offered = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )["intervention"]
    service.update_status("u1", "s1", offered["intervention_id"], "displayed")
    service.update_status("u1", "s1", offered["intervention_id"], "dismissed")
    assert cooldown.is_cooling("u1", "s1") is True


def test_repeating_the_current_status_is_not_an_error(fake_store):
    """A client retrying after a dropped response is behaving correctly."""
    offered = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )["intervention"]
    once = service.update_status("u1", "s1", offered["intervention_id"], "displayed")
    twice = service.update_status("u1", "s1", offered["intervention_id"], "displayed")
    assert once["timestamp"] == twice["timestamp"], "a retry moved the recovery anchor"


def test_one_learner_cannot_report_delivery_for_another(fake_store):
    offered = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )["intervention"]
    with pytest.raises(LookupError):
        service.update_status("u2", "s1", offered["intervention_id"], "displayed")


def test_ending_a_session_clears_its_quiet_period(fake_store):
    service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )
    assert cooldown.is_cooling("u1", "s1") is True
    service.on_session_end("u1", "s1")
    assert cooldown.is_cooling("u1", "s1") is False


def test_module_6_can_replace_the_policy_without_touching_delivery(fake_store):
    """
    The reason decide() is behind an interface. A different decider changes
    what is offered and nothing else - no change to storage, lifecycle, or the
    route the browser talks to.
    """
    class AlwaysBreak:
        policy_version = "test-stub"

        def decide(self, signals, *, history=None, recovery=None):
            return Decision(
                intervention_type=BREAK_SUGGESTION, reason_code="other",
                reason="Stub.", tier=TIER_BROAD,
            )

    service.set_decider(AlwaysBreak())
    result = service.evaluate(
        "u1", "s1", state="focused", source="lstm", confidence=0.9,
        raw_struggling=False, brow_struggling=False,
    )
    assert result["intervention"]["intervention_type"] == BREAK_SUGGESTION
    stored = store.get(result["intervention"]["intervention_id"])
    assert stored["policy_version"] == "test-stub"


def test_the_default_policy_stays_quiet_while_somebody_is_recovering(fake_store):
    """
    Interrupting a learner who has just come back up is wrong on its face, and
    it would also put a second intervention inside the first one's recovery
    window - the ambiguity Module 8 needs `competing_start` to cope with.
    """
    result = service.evaluate(
        "u1", "s1", state="recovered", source="rule", confidence=0.6,
        raw_struggling=True, brow_struggling=True, dwell_seconds=90.0,
    )
    assert result["intervention"] is None


# --------------------------------------------------------------------------
# The endpoints
# --------------------------------------------------------------------------

def test_reporting_delivery_says_whether_it_is_measured(fake_store):
    """
    Returned because it is the only way a client author can find out that a
    delivery path they built contributes to nothing, without reading Module 8.
    """
    as_user()
    offered = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=True, dwell_seconds=90.0,
    )["intervention"]
    assert offered["intervention_type"] == SIMPLIFY_CONTENT

    response = client.post(
        f"/intervention/{offered['intervention_id']}/status",
        json={"session_id": "s1", "delivery_status": "displayed"},
    )
    assert response.status_code == 200
    assert response.json()["starts_recovery_measurement"] is True


def test_a_learner_initiated_type_reports_false_until_it_is_accepted(fake_store):
    as_user()
    offered = service.evaluate(
        "u1", "s1", state="fatigued", source="rule", confidence=0.7,
        raw_struggling=False, brow_struggling=False,
    )["intervention"]
    assert offered["intervention_type"] == BREAK_SUGGESTION

    url = f"/intervention/{offered['intervention_id']}/status"
    shown = client.post(url, json={"session_id": "s1", "delivery_status": "displayed"})
    assert shown.json()["starts_recovery_measurement"] is False
    taken = client.post(url, json={"session_id": "s1", "delivery_status": "accepted"})
    assert taken.json()["starts_recovery_measurement"] is True


def test_an_illegal_move_is_a_conflict_not_a_retry(fake_store):
    as_user()
    offered = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )["intervention"]
    response = client.post(
        f"/intervention/{offered['intervention_id']}/status",
        json={"session_id": "s1", "delivery_status": "completed"},
    )
    assert response.status_code == 409


def test_an_unknown_intervention_is_a_404(fake_store):
    as_user()
    response = client.post(
        "/intervention/does-not-exist/status",
        json={"session_id": "s1", "delivery_status": "displayed"},
    )
    assert response.status_code == 404


def test_somebody_elses_intervention_is_also_a_404(fake_store):
    """
    Same answer as "does not exist", so this cannot be used to discover which
    intervention ids are real.
    """
    offered = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )["intervention"]
    as_user("u2")
    response = client.post(
        f"/intervention/{offered['intervention_id']}/status",
        json={"session_id": "s1", "delivery_status": "displayed"},
    )
    assert response.status_code == 404


def test_a_status_that_is_not_a_status_is_unprocessable(fake_store):
    as_user()
    offered = service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )["intervention"]
    response = client.post(
        f"/intervention/{offered['intervention_id']}/status",
        json={"session_id": "s1", "delivery_status": "maybe"},
    )
    assert response.status_code == 422


def test_the_session_list_shows_only_your_own(fake_store):
    service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )
    service.evaluate(
        "u2", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )
    as_user("u1")
    body = client.get("/intervention/session/s1").json()
    assert body["count"] == 1


def test_the_session_list_carries_no_scores(fake_store):
    service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )
    as_user()
    item = client.get("/intervention/session/s1").json()["interventions"][0]
    assert not {"tier", "confidence", "user_id", "policy_version"} & set(item)


def test_delivery_reports_need_authentication(fake_store):
    app.dependency_overrides.clear()
    response = client.post(
        "/intervention/anything/status",
        json={"session_id": "s1", "delivery_status": "displayed"},
    )
    assert response.status_code == 401


# --------------------------------------------------------------------------
# The wiring itself: one analyze call, end to end
# --------------------------------------------------------------------------

@pytest.fixture
def stubbed_window(monkeypatch, fake_store):
    """
    An analyze request with the model and the calibration lookup stubbed at
    the route's own seams, so this exercises the real handler without
    TensorFlow or MongoDB.
    """
    monkeypatch.setattr(
        engagement_routes, "extract_feature_sequence", lambda frames: [[0.0] * 9] * 10
    )
    monkeypatch.setattr(
        engagement_routes, "predict",
        lambda sequence: {"state": "struggling", "confidence": 0.71},
    )
    monkeypatch.setattr(engagement_routes.head_pose, "mean_pose", lambda raw: None)

    class NoCalibration:
        def find_one(self, query):
            return None

    class DB:
        calibration = NoCalibration()

    monkeypatch.setattr(engagement_routes, "db", DB())
    return {"frames": [{"landmarks": None} for _ in range(10)], "session_id": "s1"}


def _furrowed(monkeypatch, value):
    monkeypatch.setattr(
        furrow, "update",
        lambda *a, **k: {
            "furrowed": value, "furrow_available": True, "furrow_ratio": 1.2,
            "furrow_brow_ratio": 1.0, "furrow_off_pose": False,
        },
    )


def test_analyze_offers_an_intervention_and_it_can_be_delivered(monkeypatch, stubbed_window):
    """
    The whole point of P2, in one test: a struggling window produces an
    intervention on the analyze response, and delivery can be reported until it
    reaches a status Module 8 measures recovery from.

    This one is worth reading carefully, because writing it is what showed the
    obvious client is wrong. With no dwell the offer is an
    assistant_help_prompt, which is learner-initiated - so a frontend that
    renders it, reports `displayed` and stops has done everything it looks like
    it should and contributed nothing. The measurement only starts when the
    learner takes it up.
    """
    as_user()
    _furrowed(monkeypatch, True)
    engagement_routes.session_state.start("u1", "s1")

    body = client.post("/engagement/analyze", json=stubbed_window).json()
    offered = body["intervention"]
    assert offered is not None, body["diagnostics"]["intervention"]
    assert offered["intervention_type"] == ASSISTANT_HELP_PROMPT

    url = f"/intervention/{offered['intervention_id']}/status"
    shown = client.post(url, json={"session_id": "s1", "delivery_status": "displayed"}).json()
    assert shown["starts_recovery_measurement"] is False, (
        "rendering it is not enough for a learner-initiated type"
    )

    taken = client.post(url, json={"session_id": "s1", "delivery_status": "accepted"}).json()
    assert taken["starts_recovery_measurement"] is True


@pytest.mark.parametrize("dwell, expected, measured_at", [
    (0.0, ASSISTANT_HELP_PROMPT, "accepted"),
    (30.0, BULLET_SUMMARY, "displayed"),
    (90.0, SIMPLIFY_CONTENT, "displayed"),
])
def test_every_delivery_path_reaches_something_measurable(
    monkeypatch, stubbed_window, dwell, expected, measured_at
):
    """
    The general form. Whatever the policy offers, there is a delivery path
    through the real endpoints that ends in a status Module 8 measures, and
    the status differs by type - which is the part a frontend gets wrong.
    """
    as_user()
    _furrowed(monkeypatch, True)
    engagement_routes.session_state.start("u1", "s1")

    body = client.post(
        "/engagement/analyze", json={**stubbed_window, "dwell_seconds": dwell}
    ).json()
    offered = body["intervention"]
    assert offered["intervention_type"] == expected

    url = f"/intervention/{offered['intervention_id']}/status"
    last = None
    for status in ("displayed", "accepted"):
        last = client.post(url, json={"session_id": "s1", "delivery_status": status}).json()
        if last["starts_recovery_measurement"]:
            assert last["delivery_status"] == measured_at
            break
    else:
        raise AssertionError(f"{expected} never reached a measurable status")


def test_the_engagement_event_is_unchanged_by_any_of_this(monkeypatch, stubbed_window):
    """
    The intervention rides alongside the contract event, never inside it.
    The engagement contract sets additionalProperties false.
    """
    as_user()
    _furrowed(monkeypatch, False)
    engagement_routes.session_state.start("u1", "s1")

    body = client.post("/engagement/analyze", json=stubbed_window).json()
    assert "intervention" not in body["event"]
    assert "intervention_id" not in body["event"]


def test_analyze_still_works_when_the_intervention_path_is_broken(monkeypatch, stubbed_window):
    """
    Engagement detection works today and this is new. A fault here must be
    reported, not propagated.
    """
    as_user()
    _furrowed(monkeypatch, True)
    engagement_routes.session_state.start("u1", "s1")

    def explode(*args, **kwargs):
        raise RuntimeError("policy blew up")

    monkeypatch.setattr(engagement_routes.intervention, "evaluate", explode)

    response = client.post("/engagement/analyze", json=stubbed_window)
    assert response.status_code == 200
    body = response.json()
    assert body["state"]
    assert body["intervention"] is None
    assert "policy blew up" in body["diagnostics"]["intervention"]


def test_a_window_with_no_difficulty_offers_nothing(monkeypatch, stubbed_window):
    as_user()
    _furrowed(monkeypatch, False)
    monkeypatch.setattr(
        engagement_routes, "predict",
        lambda sequence: {"state": "focused", "confidence": 0.9},
    )
    engagement_routes.session_state.start("u1", "s1")

    body = client.post("/engagement/analyze", json=stubbed_window).json()
    assert body["intervention"] is None
    assert body["diagnostics"]["intervention"] == "no intervention warranted"


def test_without_dwell_the_intrusive_responses_never_fire(monkeypatch, stubbed_window):
    """
    Nothing sends dwell until the content viewer exists (issue #12), so it is
    0 and the dwell-gated responses stay out of reach. That is the right
    failure: no dwell evidence, no dwell-based intervention.
    """
    as_user()
    _furrowed(monkeypatch, True)
    engagement_routes.session_state.start("u1", "s1")

    body = client.post("/engagement/analyze", json=stubbed_window).json()
    assert body["intervention"]["intervention_type"] == ASSISTANT_HELP_PROMPT


def test_dwell_from_the_viewer_unlocks_them(monkeypatch, stubbed_window):
    """The same window with dwell reported gets the strongest response."""
    as_user()
    _furrowed(monkeypatch, True)
    engagement_routes.session_state.start("u1", "s1")

    body = client.post(
        "/engagement/analyze", json={**stubbed_window, "dwell_seconds": 90.0}
    ).json()
    assert body["intervention"]["intervention_type"] == SIMPLIFY_CONTENT


def _tagged_chunks(monkeypatch, critical):
    """
    Stand in for Module 2's content collection.

    `is_critical` is a field on a chunk in Module 2's contract, so this is the
    shape Module 9 will eventually write to - not something invented here.
    """
    doc = {
        "chunks": [
            {"chunk_id": "7", "order": 7, "text": "A passage.", "is_critical": critical}
        ]
    }

    class Content:
        def find_one(self, query, projection=None):
            return dict(doc)

    class DB:
        content = Content()

    monkeypatch.setattr(content, "db", DB())
    monkeypatch.setattr(content, "_object_id", lambda cid: cid)
    content.reset_cache()


def test_a_critical_section_is_helped_sooner(monkeypatch, stubbed_window):
    """Scope 6.9 - respond earlier where comprehension matters most."""
    as_user()
    _furrowed(monkeypatch, True)
    engagement_routes.session_state.start("u1", "s1")
    window = {**stubbed_window, "dwell_seconds": 30.0, "content_id": "c1", "chunk_id": "7"}

    _tagged_chunks(monkeypatch, critical=False)
    ordinary = client.post("/engagement/analyze", json=window).json()
    assert ordinary["intervention"]["intervention_type"] == BULLET_SUMMARY

    cooldown.reset("u1", "s1")
    _tagged_chunks(monkeypatch, critical=True)
    critical = client.post("/engagement/analyze", json=window).json()
    assert critical["intervention"]["intervention_type"] == SIMPLIFY_CONTENT


def test_a_client_can_no_longer_claim_its_own_section_is_critical(monkeypatch, stubbed_window):
    """
    In P2 `is_critical` came from the request, so a browser could lower its own
    intervention thresholds by claiming a section mattered. It is read from the
    stored chunk now, and the request field is gone - sending it changes
    nothing.
    """
    as_user()
    _furrowed(monkeypatch, True)
    engagement_routes.session_state.start("u1", "s1")
    _tagged_chunks(monkeypatch, critical=False)

    body = client.post(
        "/engagement/analyze",
        json={
            **stubbed_window,
            "dwell_seconds": 30.0,
            "content_id": "c1",
            "chunk_id": "7",
            "is_critical": True,
        },
    ).json()
    assert body["intervention"]["intervention_type"] == BULLET_SUMMARY


def test_ending_the_session_through_the_endpoint_clears_the_quiet_period(
    monkeypatch, stubbed_window
):
    as_user()
    _furrowed(monkeypatch, True)
    engagement_routes.session_state.start("u1", "s1")
    client.post("/engagement/analyze", json=stubbed_window)
    assert cooldown.is_cooling("u1", "s1") is True

    client.post("/engagement/session/end", json={"session_id": "s1"})
    assert cooldown.is_cooling("u1", "s1") is False
