"""Retrying a transient Gemini failure in the assistant.

What has to be right is the *boundary*: retry what asking again can fix, and
nothing else. A retry that fires on a bad key just delays the same error, and
one that fires on timeouts makes a learner watch a spinner for three minutes.
"""

import pytest

from app.ai_assistant import service


class ApiError(Exception):
    def __init__(self, code):
        super().__init__(f"error {code}")
        self.code = code


class FakeClient:
    """A Gemini client that raises the queued errors, then answers."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.models = self

    def generate_content(self, model, contents):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def run(outcomes):
    client = FakeClient(outcomes)
    sleeps = []
    try:
        result = service._generate_with_retry(client, "m", "p", sleep=sleeps.append)
    except Exception as error:  # noqa: BLE001 - the tests inspect it
        return client, sleeps, error
    return client, sleeps, result


@pytest.mark.parametrize("code", [429, 500, 502, 503])
def test_a_transient_failure_is_retried_and_can_succeed(code):
    client, sleeps, result = run([ApiError(code), "answer"])
    assert result == "answer"
    assert client.calls == 2
    assert sleeps == [1.0]


def test_two_transient_failures_in_a_row_still_recover():
    client, sleeps, result = run([ApiError(503), ApiError(503), "answer"])
    assert result == "answer"
    assert client.calls == 3
    assert sleeps == [1.0, 2.0]


def test_a_persistent_failure_stops_after_three_attempts():
    # Bounded, because the free tier is 20 requests a day per model, shared with
    # Modules 4 and 8. Unbounded retry would spend it on a service that is down.
    client, sleeps, result = run([ApiError(503)] * 10)
    assert isinstance(result, ApiError)
    assert client.calls == service.MAX_ATTEMPTS == 3


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
def test_a_failure_asking_again_cannot_fix_is_not_retried(code):
    # A bad key or a rejected prompt gives the same answer every time.
    client, sleeps, result = run([ApiError(code), "answer"])
    assert isinstance(result, ApiError)
    assert client.calls == 1
    assert sleeps == []


def test_a_timeout_is_never_retried():
    # A timeout is 60 seconds. Three of them is three minutes of spinner, which
    # is worse than the error.
    client, sleeps, result = run([ApiError(504), "answer"])
    assert isinstance(result, ApiError)
    assert client.calls == 1

    client, sleeps, result = run([TimeoutError("slow"), "answer"])
    assert client.calls == 1


def test_an_error_with_no_code_is_not_retried():
    # Not knowing what went wrong is not a licence to keep asking.
    client, sleeps, result = run([RuntimeError("???"), "answer"])
    assert isinstance(result, RuntimeError)
    assert client.calls == 1


def test_success_first_time_makes_exactly_one_call():
    client, sleeps, result = run(["answer"])
    assert result == "answer"
    assert client.calls == 1
    assert sleeps == []


def test_the_retry_is_wired_into_the_real_path():
    # The helper being correct is worthless if create_gemini_response does not
    # call it.
    import inspect

    assert "_generate_with_retry" in inspect.getsource(service.create_gemini_response)


def test_a_timeout_class_error_is_not_retried_even_when_it_carries_a_retryable_code():
    # The timeout guard is not redundant. `_is_timeout_error` also recognises
    # transport timeouts by class name, and one of those can arrive with a
    # response whose status happens to be retryable. The code check alone would
    # retry it, and three 60-second waits is the failure this guard exists to
    # prevent.
    class ReadTimeout(Exception):
        code = 503

    client, sleeps, result = run([ReadTimeout("slow"), "answer"])
    assert isinstance(result, ReadTimeout)
    assert client.calls == 1
