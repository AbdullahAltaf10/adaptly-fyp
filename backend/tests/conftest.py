"""
Shared pytest setup.

Puts both `backend/` (for `app`) and the repo root (for `ml`) on the import
path, so tests can be run from `backend/` without any environment setup.
`ml/` lives beside `backend/` rather than inside it because training code,
saved models and evaluation belong with the machine-learning work.

It also keeps the suite off the network. See `no_live_model_calls` below.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)

for path in (BACKEND_DIR, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(autouse=True)
def no_live_model_calls(monkeypatch):
    """Run the suite in mock mode unless a test deliberately says otherwise.

    A developer machine has a real `GEMINI_API_KEY` in `backend/.env`, and
    several code paths reach for a model whenever one is configured. Without
    this, running the tests quietly spends the shared free-tier quota - 20
    requests per day per model, across Modules 2, 4, 5 and 8 - and makes those
    tests depend on a network call answering.

    That is not hypothetical: Module 2's glossary went from a stub to a real
    generator, and the existing content test immediately started returning a
    genuine Gemini-written definition.

    Tests that want the real path inject their own generator or client, which
    this does not affect. A test that truly needs the environment variable can
    still set it with its own `monkeypatch.setenv`, because that runs after
    this fixture.
    """
    monkeypatch.setenv("INTERVENTION_CONTENT_MODE", "mock")
    monkeypatch.setenv("ASSISTANT_MODE", "mock")
