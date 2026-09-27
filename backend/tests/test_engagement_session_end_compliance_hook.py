"""Confirms `/engagement/session/end` stays failure-safe with respect to
Module 10's new auto-generate-report hook (Issue #76).

Mirrors `test_intervention_lifecycle.py`'s own pattern for driving the real
FastAPI app through `TestClient`, since this is specifically testing the
route's wiring (an additive call placed right after Module 8's own
`finalize_session_safely`), not the hook's internal logic -- that's covered
in isolation by `backend/tests/compliance/test_session_hooks.py`.
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth.dependencies import get_current_user  # noqa: E402
from app.engagement import routes as engagement_routes  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    yield
    app.dependency_overrides.clear()


def as_user(uid="hook-user"):
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": f"{uid}@t.com"}


def test_session_end_still_succeeds_when_report_generation_raises():
    """A compliance-generation failure must never prevent a session from
    ending (Issue #76 acceptance criteria).

    Uses the REAL `generate_report_safely` (not mocked away), and instead
    makes what it calls internally blow up -- `_repositories()`, standing in
    for e.g. an unreachable database -- so this actually exercises the
    hook's own try/except through the real route, rather than just
    confirming a raising mock would break things (it would, trivially; see
    the note below on why that isn't the useful test here).
    """

    as_user("hook-user")
    engagement_routes.session_state.start("hook-user", "session-hook-1")

    with patch.object(
        engagement_routes.compliance_session_hooks,
        "_repositories",
        side_effect=RuntimeError("db unreachable"),
    ):
        response = client.post(
            "/engagement/session/end", json={"session_id": "session-hook-1"}
        )

    assert response.status_code == 200


def test_session_end_still_succeeds_when_module_8_finalization_also_raises():
    """Both hooks failing at once (e.g. a shared database outage) must still
    never break the learner-facing session-end response. Same approach as
    above: fail what each safe wrapper calls internally, not the wrapper
    itself, so both real failure-safe functions run for real.
    """

    as_user("hook-user-2")
    engagement_routes.session_state.start("hook-user-2", "session-hook-2")

    with patch.object(
        engagement_routes.session_lifecycle,
        "_repositories",
        side_effect=RuntimeError("db unreachable"),
    ):
        with patch.object(
            engagement_routes.compliance_session_hooks,
            "_repositories",
            side_effect=RuntimeError("db unreachable"),
        ):
            response = client.post(
                "/engagement/session/end", json={"session_id": "session-hook-2"}
            )

    assert response.status_code == 200


def test_session_end_calls_generate_report_safely_with_the_ending_user_and_session():
    as_user("hook-user-3")
    engagement_routes.session_state.start("hook-user-3", "session-hook-3")

    with patch.object(
        engagement_routes.compliance_session_hooks, "generate_report_safely"
    ) as mock_generate:
        response = client.post(
            "/engagement/session/end", json={"session_id": "session-hook-3"}
        )

    assert response.status_code == 200
    mock_generate.assert_called_once_with("hook-user-3", "session-hook-3")
