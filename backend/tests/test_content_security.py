"""
Security tests for Module 2 content processing.

The prototype trusted its inputs completely: it fetched any URL the user pasted,
believed the browser's claim about file type, and had no size limit. These tests
pin the fixes.

Run from backend/:   python -m pytest tests/ -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.content.security import validate_public_url  # noqa: E402
from app.content.validation import (  # noqa: E402
    MAX_PDF_BYTES,
    validate_extracted_text,
    validate_text_input,
    validate_upload,
)

PDF_HEADER = b"%PDF-1.7\n"
MP4_HEADER = b"\x00\x00\x00\x18ftypmp42"


# --------------------------------------------------------------------------
# SSRF — the server must not be usable as a proxy into private networks
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://localhost:8000/users/directory",   # our own internal API
    "http://127.0.0.1/admin",
    "http://169.254.169.254/latest/meta-data/",  # cloud credentials
    "http://metadata.google.internal/",
    "http://192.168.1.1/",
    "http://10.0.0.5/",
    "http://172.16.0.1/",
    "http://[::1]/",
])
def test_private_and_internal_addresses_are_refused(url):
    with pytest.raises(HTTPException) as exc:
        validate_public_url(url)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "gopher://example.com/",
    "data:text/html,<h1>x</h1>",
])
def test_only_http_and_https_are_allowed(url):
    with pytest.raises(HTTPException):
        validate_public_url(url)


def test_error_message_does_not_leak_network_detail():
    """A precise error would turn this endpoint into a network scanner."""
    with pytest.raises(HTTPException) as exc:
        validate_public_url("http://192.168.1.1/")
    detail = str(exc.value.detail).lower()
    assert "192.168" not in detail and "private" not in detail


def test_empty_url_refused():
    with pytest.raises(HTTPException):
        validate_public_url("")


# --------------------------------------------------------------------------
# File type — the bytes decide, not the browser
# --------------------------------------------------------------------------

def test_real_pdf_is_accepted():
    validate_upload(PDF_HEADER + b"x" * 500, "pdf", "notes.pdf")


def test_file_named_pdf_but_not_a_pdf_is_refused():
    """A .pdf extension and a PDF content-type both come from the client."""
    with pytest.raises(HTTPException) as exc:
        validate_upload(b"<?php system($_GET[0]); ?>", "pdf", "notes.pdf")
    assert exc.value.status_code == 400


def test_real_video_is_accepted():
    validate_upload(MP4_HEADER + b"x" * 500, "video", "lecture.mp4")


def test_pdf_uploaded_as_video_is_refused():
    with pytest.raises(HTTPException):
        validate_upload(PDF_HEADER + b"x" * 500, "video", "lecture.mp4")


def test_empty_file_is_refused():
    with pytest.raises(HTTPException) as exc:
        validate_upload(b"", "pdf", "empty.pdf")
    assert "empty" in str(exc.value.detail).lower()


def test_oversized_file_is_refused():
    oversized = PDF_HEADER + b"x" * (MAX_PDF_BYTES + 1)
    with pytest.raises(HTTPException) as exc:
        validate_upload(oversized, "pdf", "huge.pdf")
    assert exc.value.status_code == 413


# --------------------------------------------------------------------------
# Empty and unusable input
# --------------------------------------------------------------------------

def test_blank_pasted_text_is_refused():
    for value in ("", "   ", "\n\n\t"):
        with pytest.raises(HTTPException):
            validate_text_input(value)


def test_oversized_pasted_text_is_refused():
    with pytest.raises(HTTPException) as exc:
        validate_text_input("a" * 600_000)
    assert exc.value.status_code == 413


def test_scanned_pdf_with_no_text_layer_is_refused():
    """
    A scanned document extracts to almost nothing. Without this check it would
    be stored as an empty document and fail silently later, when a learner
    opened a session and found nothing to read.
    """
    with pytest.raises(HTTPException) as exc:
        validate_extracted_text("  \n ", "that PDF")
    assert exc.value.status_code == 422
    assert "scanned" in str(exc.value.detail).lower()


def test_usable_text_passes():
    text = "This document contains enough readable text to be worth studying properly."
    assert validate_extracted_text(text, "that PDF") == text
