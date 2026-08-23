"""
Text extraction for the six supported input types.

Each function takes raw input and returns plain text. Validation happens before
these are called (validation.py, security.py); chunking happens after.

Everything here fails with a clear HTTPException rather than letting a library
error reach the user. A corrupt PDF previously produced a 500 and a stack trace.
"""

import os
import re
import tempfile

import requests
from bs4 import BeautifulSoup
from fastapi import HTTPException

from app.content.security import MAX_DOWNLOAD_BYTES, REQUEST_TIMEOUT_SECONDS

# A browser-like agent. Some sites return an error page or a consent wall to
# unrecognised clients, which would otherwise be stored as the article text.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

def extract_pdf(data: bytes) -> str:
    """Plain PDF extraction, for ordinary single-column documents."""
    from pypdf import PdfReader
    from io import BytesIO

    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise HTTPException(
                status_code=422,
                detail="That PDF is password protected. Remove the password and try again.",
            )
        pages = [page.extract_text() or "" for page in reader.pages]
    except HTTPException:
        raise
    except Exception:
        # Deliberately not surfacing the library's message: it is usually
        # meaningless to a learner and can echo file internals.
        raise HTTPException(
            status_code=422,
            detail="That PDF could not be read. It may be corrupt or in an unsupported format.",
        )

    return "\n".join(pages)


# --------------------------------------------------------------------------
# Research paper — column-aware
# --------------------------------------------------------------------------

def extract_text_with_layout(pdf_bytes: bytes) -> str:
    """
    Column-aware extraction using PyMuPDF.

    A PDF stores "draw this text here" instructions, not reading order. Read in
    raw order, a two-column paper interleaves its columns and the sentences
    become nonsense. Sorting blocks by column and then vertically fixes it.
    """
    import fitz

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="That PDF could not be read. It may be corrupt or in an unsupported format.",
        )

    try:
        full_text = []
        for page in doc:
            blocks = page.get_text("blocks")
            # round(x / 250) buckets blocks into columns; then sort top to bottom
            blocks.sort(key=lambda b: (round(b[0] / 250), b[1]))
            page_text = "\n".join(b[4] for b in blocks if b[4].strip())
            full_text.append(page_text)
        return "\n".join(full_text)
    finally:
        doc.close()


def extract_abstract(text: str):
    match = re.search(
        r"abstract[:\s]*\n?(.*?)(?=\n\s*(introduction|keywords|1\.|i\.)\b)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip()[:2000] if match else None


def remove_references_section(text: str) -> str:
    """
    Cut everything from the References heading onward.

    A 10-page paper can carry 2-3 pages of citations. Left in, they become
    roughly a quarter of the study chunks, and reading a citation list helps
    nobody understand the paper.
    """
    match = re.search(r"\n\s*(references|bibliography)\s*\n", text, re.IGNORECASE)
    return text[:match.start()] if match else text


def extract_research_paper(data: bytes) -> dict:
    raw_text = extract_text_with_layout(data)
    return {
        "text": remove_references_section(raw_text),
        "abstract": extract_abstract(raw_text),
    }


# --------------------------------------------------------------------------
# Website
# --------------------------------------------------------------------------

def extract_website(url: str) -> tuple:
    """
    Fetch a page and pull out its readable text. Returns (title, text).

    The URL must already have passed security.validate_public_url.
    """
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": _USER_AGENT},
            stream=True,          # so the size cap applies before we buffer it all
            allow_redirects=True,
        )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower() and "text" not in content_type.lower():
            raise HTTPException(
                status_code=422,
                detail="That link does not point to a readable web page.",
            )

        # Cap the download rather than trusting Content-Length, which a server
        # can understate or omit entirely.
        chunks, total = [], 0
        for piece in response.iter_content(8192):
            total += len(piece)
            if total > MAX_DOWNLOAD_BYTES:
                raise HTTPException(status_code=413, detail="That page is too large to process.")
            chunks.append(piece)
        html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")

    except HTTPException:
        raise
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="That website took too long to respond.")
    except requests.RequestException:
        raise HTTPException(status_code=422, detail="That website could not be reached.")

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else url
    text = soup.get_text(separator=" ")
    return title[:300], re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------
# YouTube
# --------------------------------------------------------------------------

_YOUTUBE_ID = re.compile(
    r"(?:v=|/videos/|embed/|youtu\.be/|/v/|/e/|watch\?v=|&v=)([A-Za-z0-9_-]{11})"
)


def youtube_video_id(url: str):
    match = _YOUTUBE_ID.search(url or "")
    return match.group(1) if match else None


def extract_youtube(url: str) -> str:
    """
    Fetch a video's existing captions.

    No speech-to-text happens here, which is why this path is free: it reads
    captions the video already has. A video without captions fails clearly
    rather than silently producing nothing.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    video_id = youtube_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="That does not look like a YouTube link.")

    try:
        segments = YouTubeTranscriptApi().fetch(video_id)
        return " ".join(seg.text if hasattr(seg, "text") else seg["text"] for seg in segments)
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="No captions are available for that video. "
                   "Only videos with captions can be used.",
        )


# --------------------------------------------------------------------------
# Uploaded video
# --------------------------------------------------------------------------

def extract_video(data: bytes, filename: str) -> str:
    """
    Transcribe an uploaded video.

    Dormant until OPENAI_API_KEY is configured, returning a clear 503 rather
    than crashing. Unlike YouTube there is no existing transcript, so this
    genuinely needs a speech-to-text service.

    The temporary file is removed in a finally block. The prototype wrote temp
    files and never deleted them, so every upload left a copy of the learner's
    video on disk.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Video transcription is not enabled. "
                   "Set OPENAI_API_KEY in backend/.env to turn it on.",
        )

    suffix = os.path.splitext(filename or "")[1] or ".mp4"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(data)
            temp_path = handle.name

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        with open(temp_path, "rb") as media:
            result = client.audio.transcriptions.create(model="whisper-1", file=media)
        return result.text

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=422, detail="That video could not be transcribed.")
    finally:
        # Always remove the learner's media from disk, including on failure.
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
