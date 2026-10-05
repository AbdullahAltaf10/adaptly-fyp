"""Deterministic, context-grounded follow-up questions for the assistant API."""

from app.ai_assistant.schemas import CurrentChunk
from app.content.terms import extract_technical_terms

# Suggested questions are capped at 300 characters by the response contract, and
# the topic is spliced into a sentence, so it is bounded here rather than
# trusted to be short.
MAX_TOPIC_LENGTH = 80
SNIPPET_WORDS = 6


def _snippet(text: str) -> str:
    words = text.split()[:SNIPPET_WORDS]
    snippet = " ".join(words).rstrip(".,;:!?")
    return snippet + ("..." if len(text.split()) > SNIPPET_WORDS else "")


def _topic(chunk: CurrentChunk) -> str | None:
    """What this paragraph is about, from the best evidence available.

    In order of trust: the section title the document itself gave it, then the
    most significant technical term in the paragraph (Module 2's own
    identification, the same one that fills the glossary), and only then nothing
    - the caller falls back to quoting the paragraph's opening words, which is
    always available and always specific to this paragraph.
    """
    if chunk.section_title:
        return chunk.section_title[:MAX_TOPIC_LENGTH]
    terms = extract_technical_terms(chunk.text, limit=1)
    return terms[0][:MAX_TOPIC_LENGTH] if terms else None


def suggest_for_chunk(chunk: CurrentChunk) -> list[str]:
    """Three short questions a learner might want to ask about THIS paragraph.

    Deterministic and local: no provider call, so it costs no Gemini quota and
    can run every time the learner scrolls to a new paragraph. Before this, a
    document whose chunks have no title (which is most of them - Module 2's
    chunker does not invent headings) got the same three generic questions for
    every paragraph, so the "suggested questions" said nothing about what was
    actually on screen.
    """
    topic = _topic(chunk)
    if topic:
        return [
            f"Can you explain {topic} more simply?",
            f"Can you give me an example of {topic}?",
            f"Why is {topic} important?",
        ]
    return [
        f"Can you explain the part starting “{_snippet(chunk.text)}” more simply?",
        "Can you give me an example from this paragraph?",
        "What is the main point of this paragraph?",
    ]


def generate_suggested_questions(request) -> list[str]:
    """Follow-ups for the active section, for both mock and Gemini responses.

    Generated locally from the current chunk so both modes return the same
    stable response contract without another provider request.
    """
    return suggest_for_chunk(request.current_chunk)
