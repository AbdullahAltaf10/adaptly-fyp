"""
Module 2 endpoints — six ingestion paths, plus listing and detail retrieval.

Every ingestion path runs the same pipeline:

    validate input -> extract text -> check the text is usable
                   -> detect language and warnings -> extract terms
                   -> chunk -> store -> return the contract shape

Keeping that order identical everywhere is deliberate: it means a new input
type cannot accidentally skip validation, and the security checks are not
scattered through six near-copies of the same handler.
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.auth.dependencies import get_current_user
from app.content import extractors
from app.content.chunking import chunk_text
from app.content.contracts import to_contract, to_summary
from app.content.language import build_warnings, detect_language
from app.content.models import build_content_doc, content_fingerprint
from app.content.security import validate_public_url
from app.content.terms import build_glossary, extract_technical_terms
from app.content.validation import (
    validate_extracted_text,
    validate_text_input,
    validate_upload,
)
from app.core.db import db

router = APIRouter(prefix="/content", tags=["content"])


def _store(uid, content_type, title, text, *, source=None, is_transcription=False, extra=None):
    """
    Shared tail of every ingestion path: analyse, chunk, store, return.

    Duplicate detection is a foundation, as the issue asks: an identical upload
    returns the existing document rather than creating a second copy. It does
    not yet detect near-duplicates or partial overlap.
    """
    language = detect_language(text)
    warnings = build_warnings(text, language, is_transcription=is_transcription)
    terms = extract_technical_terms(text)

    fingerprint = content_fingerprint(text)
    existing = db.content.find_one({"uid": uid, "fingerprint": fingerprint})
    if existing:
        existing["content_id"] = str(existing["_id"])
        result = to_contract(existing, include_chunks=False)
        result["duplicate_of_existing"] = True
        return result

    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=422, detail="No readable content could be produced.")

    doc = build_content_doc(
        uid, content_type, title, chunks,
        source=source,
        language=language,
        warnings=warnings,
        technical_terms=terms,
        glossary=build_glossary(terms, text),
        extra=extra,
    )
    inserted = db.content.insert_one(doc)
    doc["content_id"] = str(inserted.inserted_id)
    return to_contract(doc, include_chunks=False)


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------

@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), user=Depends(get_current_user)):
    data = await file.read()
    validate_upload(data, "pdf", file.filename)
    text = validate_extracted_text(extractors.extract_pdf(data), "that PDF")
    return _store(user["uid"], "pdf", file.filename, text, source=file.filename)


@router.post("/upload-research-paper")
async def upload_research_paper(file: UploadFile = File(...), user=Depends(get_current_user)):
    data = await file.read()
    validate_upload(data, "pdf", file.filename)
    result = extractors.extract_research_paper(data)
    text = validate_extracted_text(result["text"], "that paper")
    return _store(
        user["uid"], "research_paper", file.filename, text,
        source=file.filename,
        # Kept internally; not sent in the contract, which forbids extra fields.
        extra={"abstract_detected": result["abstract"] is not None,
               "abstract": result["abstract"]},
    )


@router.post("/paste-text")
async def paste_text(title: str = Form(...), text: str = Form(...), user=Depends(get_current_user)):
    cleaned = validate_text_input(text)
    return _store(user["uid"], "text", title, cleaned)


@router.post("/from-url")
async def from_url(url: str = Form(...), user=Depends(get_current_user)):
    safe_url = validate_public_url(url)          # SSRF check before any fetch
    title, text = extractors.extract_website(safe_url)
    text = validate_extracted_text(text, "that web page")
    return _store(user["uid"], "website", title, text, source=safe_url)


@router.post("/from-youtube")
async def from_youtube(url: str = Form(...), user=Depends(get_current_user)):
    text = extractors.extract_youtube(url)
    text = validate_extracted_text(text, "that video's captions")
    return _store(user["uid"], "youtube", url, text, source=url, is_transcription=True)


@router.post("/upload-video")
async def upload_video(file: UploadFile = File(...), user=Depends(get_current_user)):
    data = await file.read()
    validate_upload(data, "video", file.filename)
    text = extractors.extract_video(data, file.filename)
    text = validate_extracted_text(text, "that video")
    return _store(
        user["uid"], "video", file.filename, text,
        source=file.filename, is_transcription=True,
    )


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------

@router.get("/list")
def list_content(user=Depends(get_current_user)):
    """Metadata only — chunk text is excluded so a long list stays small."""
    items = db.content.find({"uid": user["uid"]}, {"chunks": 0})
    return [to_summary({**doc, "content_id": str(doc["_id"])}) for doc in items]


@router.get("/{content_id}")
def get_content(content_id: str, user=Depends(get_current_user)):
    """
    Full content including chunks, in shared-contract shape.

    This is what lets a study session actually display something to read, and
    what later modules use to address one specific paragraph.

    The query filters on uid as well as id, so one learner cannot read another's
    content by guessing an identifier.
    """
    try:
        object_id = ObjectId(content_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail="Content not found")

    doc = db.content.find_one({"_id": object_id, "uid": user["uid"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Content not found")

    doc["content_id"] = str(doc["_id"])
    return to_contract(doc)
