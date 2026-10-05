"""
Suggested questions that are about the paragraph on screen.

They used to be built from the section title alone. Module 2's chunker does not
invent headings, so for most documents every paragraph got the same three
generic questions and the "suggestions" said nothing about what was being read.

Run from backend/:   python -m pytest tests/test_ai_assistant_suggestions.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.ai_assistant.schemas import CurrentChunk  # noqa: E402
from app.ai_assistant.suggestions import (  # noqa: E402
    MAX_TOPIC_LENGTH,
    suggest_for_chunk,
)
from app.auth.dependencies import get_current_user  # noqa: E402
from app.main import app  # noqa: E402

PARAGRAPH_ONE = (
    "Gradient descent is an optimization algorithm that iteratively updates "
    "model parameters in the direction that reduces the loss function."
)
PARAGRAPH_TWO = (
    "Overfitting happens when a model memorises its training examples instead "
    "of learning the pattern behind them, so it fails on data it has not seen."
)


def chunk(text, section_title=None, chunk_id="c1"):
    return CurrentChunk(chunk_id=chunk_id, text=text, section_title=section_title)


def test_a_section_title_is_used_when_the_document_has_one():
    questions = suggest_for_chunk(chunk(PARAGRAPH_ONE, section_title="Model Training"))
    assert questions == [
        "Can you explain Model Training more simply?",
        "Can you give me an example of Model Training?",
        "Why is Model Training important?",
    ]


def test_a_technical_term_from_the_paragraph_is_used_when_there_is_no_title():
    text = (
        "The LSTM reads a sequence one step at a time. An LSTM keeps a memory "
        "cell, and the LSTM decides what to forget."
    )
    questions = suggest_for_chunk(chunk(text))
    assert all("LSTM" in q for q in questions)


def test_two_untitled_paragraphs_get_different_questions():
    one = suggest_for_chunk(chunk(PARAGRAPH_ONE, chunk_id="a"))
    two = suggest_for_chunk(chunk(PARAGRAPH_TWO, chunk_id="b"))
    assert one != two, "the suggestions must change with the paragraph"


def test_with_no_title_and_no_term_it_quotes_the_paragraphs_own_opening():
    questions = suggest_for_chunk(chunk(PARAGRAPH_ONE))
    assert "Gradient descent is an optimization" in questions[0]
    assert questions[0].endswith("more simply?")


def test_it_always_returns_exactly_three_short_questions():
    for text in (PARAGRAPH_ONE, PARAGRAPH_TWO, "Short text here.", "x " * 500):
        questions = suggest_for_chunk(chunk(text))
        assert len(questions) == 3
        assert all(0 < len(q) <= 300 for q in questions)


def test_a_very_long_title_cannot_push_a_question_past_the_contract_limit():
    questions = suggest_for_chunk(chunk(PARAGRAPH_ONE, section_title="T" * 300))
    assert all(len(q) <= 300 for q in questions)
    assert MAX_TOPIC_LENGTH < 300


def test_it_is_deterministic():
    assert suggest_for_chunk(chunk(PARAGRAPH_TWO)) == suggest_for_chunk(chunk(PARAGRAPH_TWO))


# --------------------------------------------------------------------------
# The endpoint
# --------------------------------------------------------------------------

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()


def as_user():
    app.dependency_overrides[get_current_user] = lambda: {"uid": "u1", "email": "u1@test.com"}


def test_the_endpoint_returns_questions_for_the_paragraph_sent():
    as_user()
    r = client.post(
        "/assistant/suggestions",
        json={"current_chunk": {"chunk_id": "c1", "text": PARAGRAPH_TWO}},
    )
    assert r.status_code == 200
    questions = r.json()["suggested_questions"]
    assert len(questions) == 3
    assert "Overfitting happens when" in questions[0]


def test_the_endpoint_requires_sign_in():
    r = client.post(
        "/assistant/suggestions",
        json={"current_chunk": {"chunk_id": "c1", "text": PARAGRAPH_ONE}},
    )
    assert r.status_code == 401


def test_the_endpoint_rejects_a_blank_paragraph():
    as_user()
    r = client.post(
        "/assistant/suggestions",
        json={"current_chunk": {"chunk_id": "c1", "text": "   "}},
    )
    assert r.status_code == 422


def test_the_endpoint_rejects_extra_fields():
    as_user()
    r = client.post(
        "/assistant/suggestions",
        json={"current_chunk": {"chunk_id": "c1", "text": PARAGRAPH_ONE}, "role": "hr_admin"},
    )
    assert r.status_code == 422
