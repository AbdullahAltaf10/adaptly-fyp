"""
Definitions for a document's technical terms.

Scope section 6.2: "Technical terms are identified at ingestion and a
background glossary is prepared so the agent can explain them instantly."

Identifying terms was already done (`terms.py`). Writing definitions was not:
`build_glossary` returned `[]` unconditionally, with a docstring saying it
would stay a stub until a language model was wired in. One is wired in now -
Modules 4, 5 and 8 all call Gemini - so the stub was the only thing left
between that sentence in the scope and a glossary that exists.

Three decisions worth stating, because each one is a trade the next person
might otherwise re-litigate:

**One request per document, not one per term.** The free tier allows 20
requests per day per model, shared across Modules 4, 5 and 8. A forty-term
document at one call per term would exhaust two days of quota on a single
upload. Every term goes in one prompt and comes back in one response.

**It runs after the response, not during it.** The scope says "background",
and it means it: a learner who uploads a PDF should not wait on a model call
to see their document. Ingestion stores the document with an empty glossary
and schedules `refresh_glossary_safely`, which fills it in afterwards.

**It never raises, and never invents.** A document with no glossary is a
slightly worse experience; an upload that fails because a model was busy is a
broken one. Anything unparseable is dropped rather than guessed at, and terms
the model answered for that were never asked about are dropped too - the
glossary is shown to a learner as fact, so a hallucinated entry is worse than
a missing one.
"""

import logging

from app.content.terms import MAX_TERMS

log = logging.getLogger(__name__)

TASK_GLOSSARY = "glossary"

# A definition is one sentence a learner can read mid-paragraph without losing
# their place. Anything longer is the model explaining rather than defining,
# and it would crowd the prompt the assistant is given.
MAX_DEFINITION_CHARS = 240

# The model is asked for `term :: definition` per line. `::` rather than `:`
# because definitions contain colons ("LSTM: a network that...") far more
# often than terms do.
SEPARATOR = "::"

_PROMPT = """You are preparing a glossary for a learner studying the document below.

For each term listed, write one plain sentence explaining what it means IN THIS
DOCUMENT'S context. Write for someone meeting the term for the first time.

Rules:
- Output one line per term, in the format: term {separator} definition
- Use exactly the term as given, before the {separator}
- One sentence per term, at most 25 words
- No bullet points, no numbering, no extra commentary before or after
- If a term is too generic to define usefully here, leave it out entirely

Terms:
{terms}

Document (may be truncated):
{context}
"""

# Enough document for the model to place a term in context without spending
# the request budget on a whole book.
MAX_CONTEXT_CHARS = 6000


def _build_prompt(terms: list, context: str) -> str:
    return _PROMPT.format(
        separator=SEPARATOR,
        terms="\n".join(f"- {term}" for term in terms),
        context=(context or "")[:MAX_CONTEXT_CHARS],
    )


def parse_glossary(raw: str, terms: list) -> list:
    """
    Turn a model response into contract-shaped glossary entries.

    Only terms that were asked for come back, matched case-insensitively so
    "lstm" in the reply still answers "LSTM" in the request, and the requested
    spelling is what gets stored. A term answered twice keeps its first
    definition. Malformed lines are skipped in silence: this runs in the
    background, and one bad line is not worth a log entry on every upload.
    """
    if not raw or not terms:
        return []

    wanted = {term.lower(): term for term in terms}
    seen = set()
    entries = []

    for line in raw.splitlines():
        line = line.strip().lstrip("-*").strip()
        if SEPARATOR not in line:
            continue
        left, _, right = line.partition(SEPARATOR)
        key = left.strip().lower()
        definition = " ".join(right.split())
        if key not in wanted or key in seen or not definition:
            continue
        seen.add(key)
        entries.append(
            {"term": wanted[key], "definition": definition[:MAX_DEFINITION_CHARS]}
        )

    return entries


def build_glossary(terms: list, context: str = "", generator=None) -> list:
    """
    Definitions for `terms`, or `[]` when none can be produced.

    `generator` is injectable so tests never reach the network; left as None it
    asks Module 4's provider for whichever model the server has configured, and
    gets None back when that is nothing - mock mode, or no API key.

    Never raises. The caller is an upload path or a background task, and
    neither should fail over a missing glossary.
    """
    if not terms:
        return []

    if generator is None:
        from app.intervention import provider

        generator = provider.model_generator_or_none()
        if generator is None:
            return []

    limited = list(terms)[:MAX_TERMS]
    try:
        raw = generator.generate(
            _build_prompt(limited, context), task=TASK_GLOSSARY, text=context
        )
    except Exception:
        # Logged by type only: the exception text can echo back the learner's
        # own study material, which does not belong in server logs.
        log.warning("Glossary generation failed", exc_info=False)
        return []

    return parse_glossary(raw, limited)


def refresh_glossary_safely(content_id: str, terms: list, context: str, *, database=None) -> None:
    """
    Build the glossary for one stored document and save it. Never raises.

    Runs after the ingestion response has been returned, so a slow or failing
    model costs the learner nothing. A document whose glossary never arrives
    keeps the empty list it was stored with, and the assistant simply has one
    fewer thing in its prompt - it still has the document itself.
    """
    try:
        from bson import ObjectId

        from app.core.db import db as default_db

        entries = build_glossary(terms, context)
        if not entries:
            return

        target = default_db if database is None else database
        target.content.update_one(
            {"_id": ObjectId(content_id)}, {"$set": {"glossary": entries}}
        )
    except Exception:
        log.warning("Could not store glossary for content_id=%s", content_id)


def glossary_for(content_id: str, *, database=None) -> list:
    """
    The stored glossary for one document, or `[]`.

    Read server-side rather than accepted from the request, for the same
    reason the assistant's engagement state is: everything inside the prompt's
    Adaptly-generated sections has to be something the server established, not
    something a client could put there.
    """
    try:
        from bson import ObjectId

        from app.core.db import db as default_db

        target = default_db if database is None else database
        document = target.content.find_one(
            {"_id": ObjectId(content_id)}, {"glossary": 1}
        )
    except Exception:
        return []

    if not document:
        return []
    entries = document.get("glossary") or []
    return [
        {"term": entry["term"], "definition": entry["definition"]}
        for entry in entries
        if isinstance(entry, dict) and entry.get("term") and entry.get("definition")
    ]
