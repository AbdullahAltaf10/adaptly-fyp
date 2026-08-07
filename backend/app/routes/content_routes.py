from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pypdf import PdfReader
import requests
from bs4 import BeautifulSoup
from app.core.dependencies import get_current_user
from app.core.db import db
from app.models.content_model import build_content_doc
from app.services.text_processing import chunk_text
import io
from openai import OpenAI
import os
import tempfile

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None




router = APIRouter(prefix="/content", tags=["content"])


@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), user=Depends(get_current_user)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    contents = await file.read()
    reader = PdfReader(io.BytesIO(contents))
    raw_text = ""
    for page in reader.pages:
        raw_text += page.extract_text() or ""

    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from PDF")

    chunks = chunk_text(raw_text)
    doc = build_content_doc(user["uid"], "pdf", file.filename, chunks, source=file.filename)
    result = db.content.insert_one(doc)
    return {"content_id": str(result.inserted_id), "chunk_count": len(chunks)}


@router.post("/paste-text")
def paste_text(title: str = Form(...), text: str = Form(...), user=Depends(get_current_user)):
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    chunks = chunk_text(text)
    doc = build_content_doc(user["uid"], "text", title, chunks)
    result = db.content.insert_one(doc)
    return {"content_id": str(result.inserted_id), "chunk_count": len(chunks)}


@router.post("/from-url")
def from_url(url: str = Form(...), user=Depends(get_current_user)):
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception:
        raise HTTPException(status_code=422, detail="Could not fetch URL")

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    raw_text = soup.get_text(separator=" ", strip=True)

    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="No readable content found on page")

    title = soup.title.string if soup.title else url
    chunks = chunk_text(raw_text)
    doc = build_content_doc(user["uid"], "website", title, chunks, source=url)
    result = db.content.insert_one(doc)
    return {"content_id": str(result.inserted_id), "chunk_count": len(chunks)}


@router.get("/list")
def list_content(user=Depends(get_current_user)):
    items = list(db.content.find({"uid": user["uid"]}, {"chunks": 0}))
    for item in items:
        item["_id"] = str(item["_id"])
    return items



from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import re


def extract_youtube_id(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", url)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    return match.group(1)


@router.post("/from-youtube")
def from_youtube(url: str = Form(...), user=Depends(get_current_user)):
    video_id = extract_youtube_id(url)
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.fetch(video_id).to_raw_data()
    except TranscriptsDisabled:
        raise HTTPException(status_code=422, detail="Transcripts are disabled for this video")
    except NoTranscriptFound:
        raise HTTPException(status_code=422, detail="No transcript available for this video")
    except Exception as e:
        print("YOUTUBE ERROR:", repr(e))
        raise HTTPException(status_code=422, detail="Could not fetch YouTube transcript")

    raw_text = " ".join([seg["text"] for seg in transcript_list])
    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="Transcript was empty")

    chunks = chunk_text(raw_text)
    doc = build_content_doc(user["uid"], "youtube", url, chunks, source=url)
    result = db.content.insert_one(doc)
    return {"content_id": str(result.inserted_id), "chunk_count": len(chunks)}







@router.post("/upload-video")
async def upload_video(file: UploadFile = File(...), user=Depends(get_current_user)):
    if not openai_client:
        raise HTTPException(status_code=503, detail="Video transcription is not configured yet")

    allowed_types = ["video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Unsupported video format")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
    except Exception:
        raise HTTPException(status_code=422, detail="Could not transcribe video")
    finally:
        os.remove(tmp_path)

    raw_text = transcript.text
    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="Transcription was empty")

    chunks = chunk_text(raw_text)
    doc = build_content_doc(user["uid"], "video", file.filename, chunks, source=file.filename)
    result = db.content.insert_one(doc)
    return {"content_id": str(result.inserted_id), "chunk_count": len(chunks)}









from app.services.research_paper_processing import process_research_paper


@router.post("/upload-research-paper")
async def upload_research_paper(file: UploadFile = File(...), user=Depends(get_current_user)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    contents = await file.read()
    result = process_research_paper(contents)

    if not result["body_text"].strip():
        raise HTTPException(status_code=422, detail="Could not extract text from research paper")

    full_text = result["body_text"]
    if result["abstract"]:
        full_text = f"Abstract: {result['abstract']}\n\n{full_text}"

    chunks = chunk_text(full_text)
    doc = build_content_doc(user["uid"], "research_paper", file.filename, chunks, source=file.filename)
    result_id = db.content.insert_one(doc)

    return {
        "content_id": str(result_id.inserted_id),
        "chunk_count": len(chunks),
        "abstract_detected": result["abstract"] is not None,
    }