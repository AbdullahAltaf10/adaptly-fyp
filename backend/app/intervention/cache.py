"""
Generated text, kept so the same paragraph is never paid for twice.

What it is keyed on, and why that is the whole design
-----------------------------------------------------
The key is a hash of (prompt version, task, passage text). Not the chunk id,
not the learner, and deliberately not the model name.

**Not the chunk id**, because a chunk id only means something inside one
document, and the text behind it can be re-extracted. The text itself is what
the answer depends on.

**Not the learner**, because simplifying paragraph 5 is the same work for
everybody who reads it. That is the point: the first learner to reach a hard
paragraph waits for the model, and everyone after them does not. It only holds
because `prompts.build_prompt` is a pure function of (task, text) - see the
rule in that module. If a prompt ever starts depending on who asked, this cache
becomes both useless and a place engagement state gets stored.

**Including the prompt version** means changing the wording retires the old
entries by itself. No migration, and no chance of a rewritten prompt quietly
serving text produced by the old one.

**Not including the model name** was a correction. It was in the key first,
which read well and was wrong: the key could not be computed without first
choosing a generator, so a passage that a real model had already simplified
became unreachable the moment the API key was removed. A cached rewrite is
perfectly good text; refusing to serve it because the model that wrote it is no
longer configured helps nobody.

The model is stored on the entry instead, and the caller decides whether a hit
is good enough - see `simplify.generate`, which rejects a fallback result when
a real model has since become available. The cost of the change is that
switching GEMINI_MODEL no longer refreshes anything on its own. Bump
PROMPT_VERSION when that is what you want.

Why MongoDB and not memory
--------------------------
Unlike `cooldown.py`, this is worth keeping. It survives a restart, it is
shared between workers, and each miss costs a real API call. It holds published
study material and text derived from it - no learner data - so there is nothing
here that needs to expire with a session.

Every function returns rather than raises. A cache that is down should make
things slower, never broken.
"""

import hashlib
import logging
from datetime import datetime, timezone

from app.core.db import db

log = logging.getLogger(__name__)

COLLECTION = "intervention_content_cache"


def key_for(*, task: str, text: str, prompt_version: str) -> str:
    """
    The cache key. Deliberately takes no user, session or engagement argument -
    there is nowhere to put one - and no model, so it can be computed before a
    generator has been chosen.
    """
    digest = hashlib.sha256()
    for part in (prompt_version, task, text.strip()):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def get(cache_key: str) -> dict | None:
    try:
        document = db[COLLECTION].find_one({"_id": cache_key})
    except Exception:
        log.warning("content cache could not be read", exc_info=True)
        return None
    if not document:
        return None
    return {
        "generated": document["generated"],
        "generator": document["generator"],
        "model": document.get("model"),
    }


def put(cache_key: str, *, generated: str, generator: str, task: str, model: str) -> bool:
    """
    Store one result.

    The passage itself is not stored - only its hash, in the key. The generated
    text has to be kept because that is the thing being reused, and the
    original is already in `db.content`, so storing it again would be a second
    copy of the same study material with its own lifetime.
    """
    document = {
        "_id": cache_key,
        "generated": generated,
        "generator": generator,
        "task": task,
        "model": model,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        db[COLLECTION].replace_one({"_id": cache_key}, document, upsert=True)
        return True
    except Exception:
        log.warning("content cache could not be written", exc_info=True)
        return False
