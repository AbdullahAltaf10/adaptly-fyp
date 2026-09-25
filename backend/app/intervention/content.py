"""
Reading one chunk of study material, for the module that has to act on it.

Module 4 needs two things from Module 2 that nothing else gives it:

  the passage text     - there is nothing to simplify without it
  is_critical          - scope 6.9 asks the intervention engine to respond
                         earlier where comprehension matters most

Both already exist. `content/contracts.py` lists `is_critical` in CHUNK_FIELDS,
so the field has a home on a chunk even though nothing populates it yet -
Module 9 owns that tagging. Reading it from the chunk means the day Module 9
starts writing it, this starts honouring it with no change here.

That matters more than it sounds. In P2 `is_critical` arrived from the browser,
because there was nowhere else to get it. A client could lower its own
intervention thresholds by claiming a section was critical. Reading it from the
stored chunk closes that, and the request field is gone.

Ownership
---------
Every lookup filters on `uid` as well as the content id, exactly as
`content/routes.py:get_content` does, so one learner cannot reach another's
material through an intervention. The check is repeated here rather than
imported because Module 2 exposes it only as a route; it belongs in a shared
function in `app/content/` and should move there.

Caching
-------
A short-lived in-process cache, because this now sits in the engagement hot
path - every analyze window looks up the current chunk. A passage does not
change once stored: `build_content_doc` fingerprints the text and re-uploading
the same document returns the existing one rather than rewriting it.
`is_critical` is the exception; it is expected to be set later by Module 9, so
the cache expires rather than holding forever, and a newly tagged section takes
effect within CACHE_TTL_SECONDS instead of needing a restart.
"""

import logging
import time

from app.core.db import db

log = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300

# (uid, content_id, chunk_id) -> (expires_at, chunk_or_None)
_cache: dict[tuple, tuple] = {}


def _object_id(content_id: str):
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        return ObjectId(content_id)
    except (InvalidId, TypeError):
        return None


def _fetch(uid: str, content_id: str, chunk_id: str) -> dict | None:
    object_id = _object_id(content_id)
    if object_id is None:
        return None
    try:
        document = db.content.find_one(
            {"_id": object_id, "uid": uid}, {"chunks": 1}
        )
    except Exception:
        log.warning("content lookup failed for %s", content_id, exc_info=True)
        return None
    if not document:
        return None
    for chunk in document.get("chunks") or []:
        if str(chunk.get("chunk_id")) == str(chunk_id):
            return {
                "chunk_id": str(chunk.get("chunk_id")),
                "text": chunk.get("text") or "",
                "is_critical": bool(chunk.get("is_critical")),
            }
    return None


def get_chunk(uid: str, content_id: str, chunk_id: str) -> dict | None:
    """
    One chunk of the learner's own content, or None.

    None covers every reason equally - no such content, not theirs, no such
    chunk, database unreachable - because none of them is something the caller
    can act on differently. A missing chunk means the dwell-gated responses
    stay out of reach, which is the same conservative behaviour as having no
    dwell at all.
    """
    if not (uid and content_id and chunk_id is not None):
        return None

    key = (uid, str(content_id), str(chunk_id))
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and cached[0] > now:
        return cached[1]

    chunk = _fetch(uid, str(content_id), str(chunk_id))
    _cache[key] = (now + CACHE_TTL_SECONDS, chunk)
    return chunk


def is_critical(uid: str, content_id: str, chunk_id: str) -> bool:
    """
    Whether HR has marked this section critical. False whenever it cannot be
    established - a section is only treated as critical on evidence.
    """
    chunk = get_chunk(uid, content_id, chunk_id)
    return bool(chunk and chunk["is_critical"])


def reset_cache() -> None:
    """Drop the lookup cache. For tests, and after a content re-import."""
    _cache.clear()
