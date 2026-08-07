from datetime import datetime

def build_content_doc(uid: str, content_type: str, title: str, chunks: list, source: str = None):
    return {
        "uid": uid,
        "type": content_type,  # "pdf" | "text" | "website" | "youtube" | "video"
        "title": title,
        "source": source,       # filename or URL, if applicable
        "chunks": chunks,       # list of { "chunk_id": int, "text": str }
        "status": "ready",
        "created_at": datetime.utcnow(),
    }