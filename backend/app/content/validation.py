"""
Upload validation — size, real file type, and empty/corrupt input.

The prototype trusted the browser. It checked `file.content_type`, which is
simply a string the client sends and can set to anything, and it had no size
limit at all — so a multi-gigabyte upload would be read straight into memory.

This module checks the bytes themselves. Nothing here needs a new dependency:
file types are identified by their signature ("magic bytes"), which is how
`file(1)` and python-magic work underneath.
"""

from fastapi import HTTPException

# Generous enough for a real textbook chapter or a lecture recording, small
# enough that a single request cannot exhaust memory.
MAX_PDF_BYTES = 25 * 1024 * 1024        # 25 MB
MAX_VIDEO_BYTES = 200 * 1024 * 1024     # 200 MB
MAX_TEXT_CHARS = 500_000                # ~100k words

# Minimum extractable text before we treat a document as unusable. A scanned
# PDF with no text layer typically yields a handful of stray characters.
MIN_EXTRACTED_CHARS = 50

# File signatures. Each entry is (offset, magic bytes).
_SIGNATURES = {
    "pdf": [(0, b"%PDF-")],
    "video": [
        (4, b"ftyp"),          # MP4 / MOV / M4V
        (0, b"\x1a\x45\xdf\xa3"),  # Matroska / WebM
        (0, b"RIFF"),          # AVI
    ],
}


def _matches_signature(head: bytes, kind: str) -> bool:
    for offset, magic in _SIGNATURES[kind]:
        if head[offset:offset + len(magic)] == magic:
            return True
    return False


def validate_upload(data: bytes, kind: str, filename: str = "") -> None:
    """
    Check an uploaded file before any processing touches it.

    kind: "pdf" or "video".
    Raises HTTPException with a message safe to show the user.
    """
    if kind not in _SIGNATURES:
        raise ValueError(f"unknown upload kind: {kind}")

    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    limit = MAX_PDF_BYTES if kind == "pdf" else MAX_VIDEO_BYTES
    if len(data) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large ({len(data) // (1024 * 1024)} MB). "
                   f"The limit is {limit // (1024 * 1024)} MB.",
        )

    # The real check: does the content actually look like what it claims to be?
    # A .pdf extension and a "application/pdf" content-type both come from the
    # client and prove nothing.
    if not _matches_signature(data[:32], kind):
        label = "a PDF" if kind == "pdf" else "a supported video"
        raise HTTPException(
            status_code=400,
            detail=f"That file does not appear to be {label}. "
                   "Check the file and try again.",
        )


def validate_text_input(text: str) -> str:
    """Validate pasted text, returning it stripped."""
    if text is None:
        raise HTTPException(status_code=400, detail="No text was provided.")

    cleaned = text.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="The text is empty.")

    if len(cleaned) > MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"That text is too long ({len(cleaned):,} characters). "
                   f"The limit is {MAX_TEXT_CHARS:,}.",
        )
    return cleaned


def validate_extracted_text(text: str, source_label: str) -> str:
    """
    Check that extraction actually produced something usable.

    Without this a scanned PDF, a paywalled article or a video with no speech
    would be stored as an empty document and silently fail later, when a
    learner opened a study session and found nothing to read.
    """
    cleaned = (text or "").strip()
    if len(cleaned) < MIN_EXTRACTED_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Almost no readable text could be extracted from {source_label}. "
                   "If it is a scanned document, it needs to be converted to text first.",
        )
    return cleaned
