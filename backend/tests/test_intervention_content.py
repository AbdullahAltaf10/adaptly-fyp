"""
Module 4 P3 - producing the text an intervention shows.

Nothing here touches a network. The generator is an interface, so a stub is
injected; the cache and the content lookup are fake collections.

What these are actually defending
---------------------------------
**That it refuses rather than pretends.** With no language model there is no
honest way to simplify a passage. Returning the original labelled as simplified
would be undetectable to the learner and Module 8 would record it as a
delivered intervention that may have helped. Several tests exist only to pin
that this fails loudly instead.

**That the cache stays shareable.** Simplifying paragraph 5 is the same work
for everyone who reads it, which is the whole reason the second learner does
not wait. That holds only while a prompt depends on nothing but (task, text).
The moment engagement state enters a prompt the cache stops hitting and starts
storing who was struggling with what.

**That a client cannot tag its own content as critical.** In P2 `is_critical`
came from the request. It is read from the stored chunk now.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth.dependencies import get_current_user  # noqa: E402
from app.intervention import (  # noqa: E402
    cache,
    content,
    contracts,
    cooldown,
    prompts,
    provider,
    simplify,
    store,
)
from app.intervention.decider import (  # noqa: E402
    ASSISTANT_HELP_PROMPT,
    BREAK_SUGGESTION,
    BULLET_SUMMARY,
    SIMPLIFY_CONTENT,
    TIER_BROAD,
    Decision,
)
from app.main import app  # noqa: E402

client = TestClient(app)

PASSAGE = (
    "Amortisation spreads the cost of an intangible asset over the period in "
    "which that asset is expected to generate economic benefit. The charge is "
    "recognised in the income statement each period. Where the useful life "
    "cannot be determined reliably, the asset is not amortised and is instead "
    "tested for impairment annually."
)


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class FakeCollection:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.fail = False
        self.writes = 0

    def replace_one(self, query, document, upsert=False):
        if self.fail:
            raise RuntimeError("no connection")
        self.writes += 1
        self.docs[query["_id"]] = dict(document)

        class R:
            upserted_id = query["_id"]

        return R()

    def find_one(self, query, projection=None):
        if self.fail:
            raise RuntimeError("no connection")
        found = self.docs.get(query["_id"])
        return dict(found) if found else None

    def find(self, query):
        matched = [dict(d) for d in self.docs.values()
                   if all(d.get(k) == v for k, v in query.items())]

        class Cursor:
            def sort(self, field, direction=1):
                return matched

            def __iter__(self):
                return iter(matched)

        return Cursor()


class FakeDB:
    def __init__(self):
        self.collection = FakeCollection()

    def __getitem__(self, name):
        return self.collection

    def __getattr__(self, name):
        return self.collection


@pytest.fixture
def fake_cache(monkeypatch):
    database = FakeDB()
    monkeypatch.setattr(cache, "db", database)
    return database.collection


@pytest.fixture
def fake_store(monkeypatch):
    database = FakeDB()
    monkeypatch.setattr(store, "db", database)
    return database.collection


@pytest.fixture
def fake_content(monkeypatch):
    """Module 2's content collection, in the shape its contract defines."""
    state = {
        "chunks": [
            {"chunk_id": "7", "order": 7, "text": PASSAGE, "is_critical": False},
            {"chunk_id": "8", "order": 8, "text": "Too short.", "is_critical": False},
        ],
        # Two learners with the same material, which is the ordinary case for
        # corporate training and the reason the cache is worth having.
        "owners": {"u1", "u2"},
    }

    class Content:
        def find_one(self, query, projection=None):
            if query.get("uid") not in state["owners"]:
                return None
            return {"chunks": [dict(c) for c in state["chunks"]]}

    class DB:
        content = Content()

    monkeypatch.setattr(content, "db", DB())
    monkeypatch.setattr(content, "_object_id", lambda cid: cid)
    content.reset_cache()
    return state


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv(provider.ENV_API_KEY, raising=False)
    monkeypatch.delenv(provider.ENV_MODE, raising=False)
    cooldown.reset("u1", "s1")
    content.reset_cache()
    yield
    app.dependency_overrides.clear()
    content.reset_cache()


def as_user(uid="u1"):
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": f"{uid}@t.com"}


class StubGenerator(provider.TextGenerator):
    """A model that is not there. Records what it was asked."""

    name = "stub"
    can_simplify = True
    model = "stub-1"

    def __init__(self, output="Amortisation spreads a cost over time."):
        self.output = output
        self.calls = []

    def generate(self, prompt, *, task, text):
        self.calls.append({"prompt": prompt, "task": task})
        return self.output


def an_event(intervention_type=SIMPLIFY_CONTENT, uid="u1", chunk_id="7", content_id="c1"):
    decision = Decision(
        intervention_type=intervention_type, reason_code="struggling",
        reason="Signs of difficulty.", tier=TIER_BROAD,
        chunk_id=chunk_id, content_id=content_id,
    )
    return contracts.build_intervention_event(
        decision=decision, user_id=uid, session_id="s1",
        triggering_engagement_state="struggling",
    )


# --------------------------------------------------------------------------
# The prompts, and the rule that makes the cache possible
# --------------------------------------------------------------------------

def test_a_prompt_depends_on_nothing_but_the_task_and_the_passage():
    """
    Not a style preference. If a prompt could see the learner, the cache would
    stop hitting and would start holding engagement state in generated text.
    """
    import inspect

    signature = inspect.signature(prompts.build_prompt)
    assert list(signature.parameters) == ["task", "text"]


def test_the_cache_key_has_no_parameter_a_learner_could_enter_through():
    """
    The structural half of the guarantee. There is nowhere to put a user id,
    a session or an engagement state, so none can creep in later by accident.
    """
    import inspect

    assert set(inspect.signature(cache.key_for).parameters) == {
        "task", "text", "prompt_version"
    }


def test_changing_the_prompt_retires_the_old_entries():
    """No migration, and no stale text surviving a rewritten prompt."""
    base = dict(task=prompts.TASK_SIMPLIFY, text=PASSAGE)
    assert cache.key_for(**base, prompt_version="v1") != cache.key_for(**base, prompt_version="v2")


def test_the_two_tasks_do_not_share_an_entry():
    base = dict(text=PASSAGE, prompt_version="v1")
    assert cache.key_for(**base, task=prompts.TASK_SIMPLIFY) != cache.key_for(
        **base, task=prompts.TASK_BULLETS
    )


def test_the_prompt_keeps_the_terms_the_passage_is_teaching():
    """
    Corporate training material. A rewrite of a paragraph about amortisation
    that removes the word `amortisation` has removed the lesson.
    """
    prompt = prompts.build_prompt(prompts.TASK_SIMPLIFY, PASSAGE)
    assert "technical terms" in prompt
    assert PASSAGE in prompt


def test_an_empty_passage_has_no_prompt():
    with pytest.raises(ValueError):
        prompts.build_prompt(prompts.TASK_SIMPLIFY, "   ")


# --------------------------------------------------------------------------
# Refusing rather than pretending
# --------------------------------------------------------------------------

def test_without_a_model_simplification_refuses(fake_cache):
    """
    The single most important test here. Returning the original text labelled
    as simplified would be undetectable to the learner, and Module 8 would
    record it as a delivered intervention that may have helped.
    """
    with pytest.raises(provider.GenerationUnavailable):
        simplify.generate(task=prompts.TASK_SIMPLIFY, text=PASSAGE)


def test_the_fallback_says_it_cannot_simplify():
    assert provider.ExtractiveGenerator().can_simplify is False
    with pytest.raises(provider.GenerationUnavailable):
        provider.ExtractiveGenerator().generate("p", task=prompts.TASK_SIMPLIFY, text=PASSAGE)


def test_bullets_still_work_without_a_model(fake_cache):
    """
    Taking the leading sentences is a real summarisation method, not a
    stand-in, so this one is honest without a model - as long as it says so.
    """
    result = simplify.generate(task=prompts.TASK_BULLETS, text=PASSAGE)
    assert result["generator"] == provider.GENERATOR_EXTRACTIVE
    assert result["generated"].startswith("- ")
    assert len(result["generated"].splitlines()) <= provider.ExtractiveGenerator.MAX_BULLETS


def test_every_result_names_what_produced_it(fake_cache):
    stub = StubGenerator()
    result = simplify.generate(task=prompts.TASK_SIMPLIFY, text=PASSAGE, generator=stub)
    assert result["generator"] == "stub"


def test_a_longer_rewrite_is_accepted_because_explaining_a_term_lengthens_it(fake_cache):
    """
    This is a regression test for a guard of mine that was measurably wrong.

    MAX_LENGTH_RATIO started at 1.5, on the reasoning that a rewrite half as
    long again is not a simplification. Running six real passages through
    gemini-3.6-flash gave ratios of 1.16 to 2.29, so that guard would have
    rejected three of five good rewrites. Simplifying training material
    lengthens it - explaining a term inline is longer than the term, and that
    is the whole point.
    """
    rewrite = (
        "Amortisation, which means spreading a cost out over time, applies to "
        "an intangible asset - an asset you cannot touch, such as a patent. "
        "The cost is spread over the period the asset is expected to bring "
        "economic benefit, meaning the time it is expected to make money. Each "
        "period a charge is recorded in the income statement, the document that "
        "tracks income and costs. When the useful life cannot be worked out "
        "reliably, the asset is not amortised at all and is instead checked once "
        "a year for impairment, meaning a drop in value."
    )
    assert len(rewrite) / len(PASSAGE) > 1.5, "this sample no longer tests anything"

    result = simplify.generate(
        task=prompts.TASK_SIMPLIFY, text=PASSAGE, generator=StubGenerator(rewrite)
    )
    assert result["generated"] == rewrite


def test_runaway_output_is_still_rejected(fake_cache):
    """
    What the guard is actually for, now that length is not the signal: a model
    that loops, pads, or hands the whole prompt back.
    """
    stub = StubGenerator(output=PASSAGE * 4)
    with pytest.raises(provider.GenerationFailed):
        simplify.generate(task=prompts.TASK_SIMPLIFY, text=PASSAGE, generator=stub)


def test_runaway_bullets_are_rejected_too(fake_cache):
    """The guard covers both tasks - looping is not specific to one."""
    stub = StubGenerator(output=PASSAGE * 4)
    with pytest.raises(provider.GenerationFailed):
        simplify.generate(task=prompts.TASK_BULLETS, text=PASSAGE, generator=stub)


def test_a_passage_handed_straight_back_is_rejected(fake_cache):
    """The model did nothing. Showing it would spend a real intervention."""
    stub = StubGenerator(output=PASSAGE)
    with pytest.raises(provider.GenerationFailed):
        simplify.generate(task=prompts.TASK_SIMPLIFY, text=PASSAGE, generator=stub)


def test_empty_output_is_rejected(fake_cache):
    stub = StubGenerator(output="   ")
    with pytest.raises(provider.GenerationFailed):
        simplify.generate(task=prompts.TASK_SIMPLIFY, text=PASSAGE, generator=stub)


def test_a_passage_too_short_to_be_worth_rewriting_is_refused(fake_cache):
    with pytest.raises(provider.GenerationUnavailable):
        simplify.generate(task=prompts.TASK_SIMPLIFY, text="Too short.", generator=StubGenerator())


# --------------------------------------------------------------------------
# Cleaning what models add anyway
# --------------------------------------------------------------------------

def test_a_code_fence_around_the_whole_answer_is_removed():
    assert simplify.clean("```\nRewritten text here.\n```") == "Rewritten text here."


def test_a_short_preamble_line_is_removed():
    cleaned = simplify.clean(
        "Here is the simplified version:\n\nAmortisation spreads a cost over its useful life."
    )
    assert cleaned.startswith("Amortisation")


def test_a_real_heading_is_left_alone():
    """
    Only a short first line ending in a colon followed by something
    substantial is stripped, so a passage that legitimately opens with a
    heading keeps it.
    """
    text = "Note:\nshort"
    assert simplify.clean(text) == text


# --------------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------------

def test_the_second_request_for_a_passage_does_not_call_the_model(fake_cache):
    stub = StubGenerator()
    first = simplify.generate(task=prompts.TASK_SIMPLIFY, text=PASSAGE, generator=stub)
    second = simplify.generate(task=prompts.TASK_SIMPLIFY, text=PASSAGE, generator=stub)

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["generated"] == first["generated"]
    assert len(stub.calls) == 1, "the model was called twice for the same passage"


def test_a_cached_result_remembers_which_generator_made_it(fake_cache):
    simplify.generate(task=prompts.TASK_BULLETS, text=PASSAGE)
    again = simplify.generate(task=prompts.TASK_BULLETS, text=PASSAGE)
    assert again["generator"] == provider.GENERATOR_EXTRACTIVE


def test_the_passage_itself_is_not_stored_only_its_hash(fake_cache):
    """
    The original is already in db.content. A second copy with its own lifetime
    is study material sitting somewhere nobody thinks to look.
    """
    simplify.generate(task=prompts.TASK_SIMPLIFY, text=PASSAGE, generator=StubGenerator())
    stored = list(fake_cache.docs.values())[0]
    assert PASSAGE not in str(stored)


def test_a_cached_rewrite_survives_the_api_key_being_removed(fake_cache, monkeypatch):
    """
    The bug this pins was mine. With the model name in the cache key, the key
    could not be computed before choosing a generator - so a passage a real
    model had already simplified became a 503 the moment GEMINI_API_KEY went
    away. The text was sitting right there.
    """
    monkeypatch.setenv(provider.ENV_API_KEY, "a-key")
    first = simplify.generate(task=prompts.TASK_SIMPLIFY, text=PASSAGE, generator=StubGenerator())
    assert first["cached"] is False

    monkeypatch.delenv(provider.ENV_API_KEY)
    served = simplify.generate(task=prompts.TASK_SIMPLIFY, text=PASSAGE)
    assert served["cached"] is True
    assert served["generated"] == first["generated"]
    assert served["generator"] == "stub", "a cached result must say who really wrote it"


def test_a_fallback_result_is_replaced_once_a_real_model_appears(fake_cache, monkeypatch):
    """
    Somebody who has configured a model should not keep being served leading
    sentences because the first reader of this paragraph arrived before the
    key was set.
    """
    fallback = simplify.generate(task=prompts.TASK_BULLETS, text=PASSAGE)
    assert fallback["generator"] == provider.GENERATOR_EXTRACTIVE

    stub = StubGenerator(output="- A real model wrote this.")
    better = simplify.generate(task=prompts.TASK_BULLETS, text=PASSAGE, generator=stub)
    assert better["cached"] is False
    assert better["generator"] == "stub"
    assert len(stub.calls) == 1


def test_model_output_is_not_replaced_by_a_fallback(fake_cache):
    """The other direction must never happen - that would be a downgrade."""
    simplify.generate(task=prompts.TASK_BULLETS, text=PASSAGE, generator=StubGenerator("- x y z"))
    again = simplify.generate(task=prompts.TASK_BULLETS, text=PASSAGE)
    assert again["cached"] is True
    assert again["generator"] == "stub"


def test_an_unreachable_cache_makes_things_slower_not_broken(fake_cache):
    fake_cache.fail = True
    stub = StubGenerator()
    result = simplify.generate(task=prompts.TASK_SIMPLIFY, text=PASSAGE, generator=stub)
    assert result["generated"]
    assert result["cached"] is False


# --------------------------------------------------------------------------
# Reading the passage, and who is allowed to
# --------------------------------------------------------------------------

def test_a_chunk_is_read_from_the_learners_own_content(fake_content):
    chunk = content.get_chunk("u1", "c1", "7")
    assert chunk["text"] == PASSAGE


def test_another_learners_content_is_not_reachable(fake_content):
    assert content.get_chunk("nobody", "c1", "7") is None


def test_a_missing_chunk_is_not_an_error(fake_content):
    assert content.get_chunk("u1", "c1", "999") is None


def test_is_critical_comes_from_the_stored_chunk(fake_content):
    assert content.is_critical("u1", "c1", "7") is False
    fake_content["chunks"][0]["is_critical"] = True
    content.reset_cache()
    assert content.is_critical("u1", "c1", "7") is True


def test_a_section_is_only_critical_on_evidence(fake_content):
    """Unknown means not critical - never the other way round."""
    assert content.is_critical("u1", "c1", "nope") is False
    assert content.is_critical("u1", None, None) is False


# --------------------------------------------------------------------------
# The endpoint
# --------------------------------------------------------------------------

def test_content_is_returned_with_the_original_beside_it(
    monkeypatch, fake_store, fake_cache, fake_content
):
    """
    Scope 6.4 asks for support delivered inline, not content replaced out from
    under somebody. A learner cannot judge a rewrite they cannot compare.
    """
    monkeypatch.setattr(provider, "choose", lambda task: StubGenerator())
    as_user()
    event = an_event()
    store.save(event)

    body = client.get(f"/intervention/{event['intervention_id']}/content").json()
    assert body["original"] == PASSAGE
    assert body["generated"] and body["generated"] != PASSAGE
    assert body["generator"] == "stub"
    assert body["cached"] is False


def test_the_second_fetch_is_served_from_the_cache(
    monkeypatch, fake_store, fake_cache, fake_content
):
    stub = StubGenerator()
    monkeypatch.setattr(provider, "choose", lambda task: stub)
    as_user()
    first, second = an_event(), an_event()
    store.save(first)
    store.save(second)

    client.get(f"/intervention/{first['intervention_id']}/content")
    body = client.get(f"/intervention/{second['intervention_id']}/content").json()
    assert body["cached"] is True
    assert len(stub.calls) == 1


def test_a_second_learner_does_not_wait_for_the_same_passage(
    monkeypatch, fake_store, fake_cache, fake_content
):
    """
    The behavioural half, and the point of the whole cache: the first learner
    to reach a hard paragraph waits for the model and nobody after them does.

    This is the test that would fail if a prompt ever started depending on who
    asked - the second learner would be a miss and the model would run twice.
    """
    stub = StubGenerator()
    monkeypatch.setattr(provider, "choose", lambda task: stub)

    first = an_event(uid="u1")
    second = an_event(uid="u2")
    store.save(first)
    store.save(second)

    as_user("u1")
    one = client.get(f"/intervention/{first['intervention_id']}/content").json()
    as_user("u2")
    two = client.get(f"/intervention/{second['intervention_id']}/content").json()

    assert one["cached"] is False
    assert two["cached"] is True
    assert two["generated"] == one["generated"]
    assert len(stub.calls) == 1, "the model ran twice for one paragraph"


@pytest.mark.parametrize("intervention_type", [BREAK_SUGGESTION, ASSISTANT_HELP_PROMPT])
def test_the_two_fixed_types_have_no_generated_content(
    fake_store, fake_cache, fake_content, intervention_type
):
    """Their whole message is the `reason` already on the offer."""
    as_user()
    event = an_event(intervention_type)
    store.save(event)
    response = client.get(f"/intervention/{event['intervention_id']}/content")
    assert response.status_code == 409


def test_a_missing_model_is_a_503_so_the_client_can_report_failed(
    fake_store, fake_cache, fake_content
):
    """
    Which releases the cooldown - a model outage costs the learner a delay,
    not two minutes of silence.
    """
    as_user()
    event = an_event(SIMPLIFY_CONTENT)
    store.save(event)
    response = client.get(f"/intervention/{event['intervention_id']}/content")
    assert response.status_code == 503


def test_bullets_are_served_without_a_model(fake_store, fake_cache, fake_content):
    as_user()
    event = an_event(BULLET_SUMMARY)
    store.save(event)
    body = client.get(f"/intervention/{event['intervention_id']}/content").json()
    assert body["generator"] == provider.GENERATOR_EXTRACTIVE


def test_an_unreadable_passage_is_a_422(monkeypatch, fake_store, fake_cache, fake_content):
    monkeypatch.setattr(provider, "choose", lambda task: StubGenerator())
    as_user()
    event = an_event(chunk_id="999")
    store.save(event)
    response = client.get(f"/intervention/{event['intervention_id']}/content")
    assert response.status_code == 422


def test_one_learner_cannot_fetch_anothers_intervention_text(
    monkeypatch, fake_store, fake_cache, fake_content
):
    monkeypatch.setattr(provider, "choose", lambda task: StubGenerator())
    event = an_event(uid="u1")
    store.save(event)
    as_user("u2")
    response = client.get(f"/intervention/{event['intervention_id']}/content")
    assert response.status_code == 404


def test_fetching_content_needs_authentication(fake_store, fake_cache, fake_content):
    app.dependency_overrides.clear()
    assert client.get("/intervention/anything/content").status_code == 401


# --------------------------------------------------------------------------
# Choosing a generator
# --------------------------------------------------------------------------

def test_a_configured_key_selects_the_real_model(monkeypatch):
    monkeypatch.setenv(provider.ENV_API_KEY, "not-a-real-key")
    assert isinstance(provider.choose(prompts.TASK_BULLETS), provider.GeminiGenerator)


def test_mock_mode_never_reaches_for_the_model_even_with_a_key(monkeypatch):
    """So a demo can be certain nothing leaves the machine."""
    monkeypatch.setenv(provider.ENV_API_KEY, "not-a-real-key")
    monkeypatch.setenv(provider.ENV_MODE, "mock")
    assert isinstance(provider.choose(prompts.TASK_BULLETS), provider.ExtractiveGenerator)
    with pytest.raises(provider.GenerationUnavailable):
        provider.choose(prompts.TASK_SIMPLIFY)


def test_module_4_uses_the_same_environment_variables_as_module_5():
    """One API key on the server, not two. See app/ai_assistant/../config.py."""
    assert provider.ENV_API_KEY == "GEMINI_API_KEY"
    assert provider.ENV_MODEL == "GEMINI_MODEL"
    assert provider.ENV_TIMEOUT_MS == "GEMINI_TIMEOUT_MS"


def _fake_sdk(monkeypatch, failures, error_class="ServerError", code=503):
    """
    Stand in for google.genai, failing the first `failures` calls.

    Returns a counter so a test can assert how many attempts were made.
    """
    import sys
    import types as pytypes

    calls = {"n": 0}

    class APIError(Exception):
        pass

    class ServerError(APIError):
        pass

    class ClientError(APIError):
        pass

    raised = {"ServerError": ServerError, "ClientError": ClientError}[error_class]

    class Models:
        def generate_content(self, *, model, contents):
            calls["n"] += 1
            if calls["n"] <= failures:
                error = raised("overloaded")
                error.code = code
                raise error
            return pytypes.SimpleNamespace(text="Rewritten plainly.")

    class Client:
        def __init__(self, **kwargs):
            self.models = Models()

    genai = pytypes.ModuleType("google.genai")
    genai.Client = Client
    errors = pytypes.ModuleType("google.genai.errors")
    errors.APIError, errors.ServerError, errors.ClientError = APIError, ServerError, ClientError
    sdk_types = pytypes.ModuleType("google.genai.types")
    sdk_types.HttpOptions = lambda **kwargs: kwargs
    genai.errors, genai.types = errors, sdk_types
    google = pytypes.ModuleType("google")
    google.genai = genai

    for name, module in (
        ("google", google), ("google.genai", genai),
        ("google.genai.errors", errors), ("google.genai.types", sdk_types),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    monkeypatch.setattr(provider.time, "sleep", lambda seconds: None)
    return calls


def test_a_transient_outage_is_retried(monkeypatch):
    """
    Not theoretical. Two of about fifteen calls came back 503 "currently
    experiencing high load" while measuring prompt output. Without this a
    learner loses the intervention over a few seconds of load.
    """
    calls = _fake_sdk(monkeypatch, failures=2)
    output = provider.GeminiGenerator("key").generate(
        "p", task=prompts.TASK_SIMPLIFY, text=PASSAGE
    )
    assert output == "Rewritten plainly."
    assert calls["n"] == 3


def test_it_gives_up_rather_than_retrying_forever(monkeypatch):
    calls = _fake_sdk(monkeypatch, failures=99)
    with pytest.raises(provider.GenerationFailed):
        provider.GeminiGenerator("key").generate("p", task=prompts.TASK_SIMPLIFY, text=PASSAGE)
    assert calls["n"] == provider.MAX_ATTEMPTS


def test_being_rate_limited_is_retried(monkeypatch):
    """
    429 is a 4xx but it is not a mistake. I hit it myself running a dozen
    calls in a row on the free tier, and a burst of interventions across a few
    learners would reach the per-minute limit just as easily.
    """
    calls = _fake_sdk(monkeypatch, failures=2, error_class="ClientError", code=429)
    output = provider.GeminiGenerator("key").generate(
        "p", task=prompts.TASK_SIMPLIFY, text=PASSAGE
    )
    assert output == "Rewritten plainly."
    assert calls["n"] == 3


def test_a_bad_key_is_not_retried(monkeypatch):
    """
    Every other 4xx is a bad key or a bad model name. Retrying only makes a
    misconfiguration slower to diagnose.
    """
    calls = _fake_sdk(monkeypatch, failures=99, error_class="ClientError", code=401)
    with pytest.raises(provider.GenerationFailed):
        provider.GeminiGenerator("key").generate("p", task=prompts.TASK_SIMPLIFY, text=PASSAGE)
    assert calls["n"] == 1


def test_a_missing_sdk_is_reported_not_crashed(monkeypatch):
    """
    google-genai arrives with PR #43 and is not installed everywhere yet.
    Module 4 has to degrade rather than fail to import.
    """
    import builtins

    real_import = builtins.__import__

    def no_genai(name, *args, **kwargs):
        if name == "google" or name.startswith("google.genai"):
            raise ImportError("no genai")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_genai)
    with pytest.raises(provider.GenerationUnavailable):
        provider.GeminiGenerator("key").generate("p", task=prompts.TASK_SIMPLIFY, text=PASSAGE)
