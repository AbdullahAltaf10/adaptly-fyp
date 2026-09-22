"""
Processing tests for Module 2 — chunking, language warnings, terms, contract shape.

Run from backend/:   python -m pytest tests/ -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.content.chunking import chunk_text, split_sentences  # noqa: E402
from app.content.contracts import to_contract, to_summary  # noqa: E402
from app.content.language import (  # noqa: E402
    WARNING_LOW_CONFIDENCE_TRANSCRIPTION,
    WARNING_URDU,
    build_warnings,
    detect_language,
)
from app.content.models import build_content_doc, content_fingerprint  # noqa: E402
from app.content.terms import build_glossary, extract_technical_terms  # noqa: E402


# --------------------------------------------------------------------------
# Chunking — punctuation was previously destroyed
# --------------------------------------------------------------------------

def test_full_stops_survive_chunking():
    text = "The cat sat on the mat. The dog barked loudly. It was fine."
    joined = " ".join(c["text"] for c in chunk_text(text))
    assert joined.count(".") == text.count(".")


def test_abbreviations_do_not_split_sentences():
    assert len(split_sentences("Dr. Smith arrived at 5 p.m. today.")) == 1


def test_chunk_shape_matches_contract():
    for chunk in chunk_text("One sentence. Another sentence."):
        assert set(chunk.keys()) == {"chunk_id", "order", "text"}
        assert isinstance(chunk["chunk_id"], str)
        assert isinstance(chunk["order"], int)


def test_chunk_count_follows_length_not_a_setting():
    short = chunk_text(" ".join(["Some words here."] * 20))
    long = chunk_text(" ".join(["Some words here."] * 200))
    assert len(long) > len(short)


# --------------------------------------------------------------------------
# Language detection and warnings
# --------------------------------------------------------------------------

def test_english_detected():
    assert detect_language("This is an ordinary English sentence about studying.") == "en"


def test_urdu_script_detected_and_warned():
    urdu = "یہ ایک اردو جملہ ہے جو تعلیم کے بارے میں ہے۔"
    assert detect_language(urdu) == "ur"
    assert WARNING_URDU in build_warnings(urdu, "ur")


def test_empty_text_is_unknown_not_a_crash():
    assert detect_language("") == "unknown"
    assert detect_language("   ") == "unknown"


def test_warnings_is_always_a_list():
    """The contract requires `warnings`, with [] as the agreed empty value."""
    assert build_warnings("Plain English text here.", "en") == []
    assert isinstance(build_warnings("", "unknown"), list)


def test_transcription_is_flagged_as_lower_confidence():
    warnings = build_warnings("Some transcribed speech.", "en", is_transcription=True)
    assert WARNING_LOW_CONFIDENCE_TRANSCRIPTION in warnings


# --------------------------------------------------------------------------
# Technical terms
# --------------------------------------------------------------------------

def test_acronyms_are_picked_up():
    text = ("The LSTM model processes sequences. LSTM networks handle temporal "
            "data well. We compared LSTM against CNN approaches.")
    assert "LSTM" in extract_technical_terms(text)


def test_common_words_are_not_offered_as_terms():
    terms = [t.lower() for t in extract_technical_terms(
        "This is the thing that we have been using for a while and it works.")]
    assert "this" not in terms and "that" not in terms


def test_empty_text_gives_no_terms():
    assert extract_technical_terms("") == []


def test_glossary_is_an_empty_stub_until_an_llm_is_configured():
    assert build_glossary(["LSTM"], "context") == []


# --------------------------------------------------------------------------
# Duplicate detection
# --------------------------------------------------------------------------

def test_identical_text_gives_the_same_fingerprint():
    assert content_fingerprint("Hello world.") == content_fingerprint("Hello world.")


def test_fingerprint_ignores_whitespace_and_case():
    assert content_fingerprint("Hello   World.") == content_fingerprint("hello world.")


def test_different_text_gives_a_different_fingerprint():
    assert content_fingerprint("One thing.") != content_fingerprint("Another thing.")


# --------------------------------------------------------------------------
# Contract conversion
# --------------------------------------------------------------------------

def _doc(content_type="text"):
    d = build_content_doc(
        "u1", content_type, "My Notes", chunk_text("First one. Second one."),
        source="notes.txt", language="en", warnings=[], technical_terms=["LSTM"],
        extra={"abstract_detected": True},
    )
    d["content_id"] = "abc123"
    return d


def test_internal_names_are_renamed_at_the_boundary():
    out = to_contract(_doc())
    assert out["user_id"] == "u1" and "uid" not in out
    assert out["content_type"] == "plain_text" and "type" not in out


def test_video_type_is_renamed():
    assert to_contract(_doc("video"))["content_type"] == "uploaded_video"


def test_types_that_already_match_are_unchanged():
    for internal in ("pdf", "research_paper", "website", "youtube"):
        assert to_contract(_doc(internal))["content_type"] == internal


def test_internal_extra_is_not_sent_in_the_contract():
    """additionalProperties is false, so abstract_detected must stay internal."""
    out = to_contract(_doc())
    assert "extra" not in out and "abstract_detected" not in out and "fingerprint" not in out


def test_required_contract_fields_are_present():
    out = to_contract(_doc())
    for field in ("schema_version", "content_id", "user_id", "content_type",
                  "title", "status", "language", "warnings", "chunks", "created_at"):
        assert field in out, f"missing required field {field}"


def test_summary_excludes_chunk_text():
    summary = to_summary(_doc())
    assert "chunks" not in summary
    assert summary["chunk_count"] == 1
