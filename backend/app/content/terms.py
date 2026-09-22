"""
Technical-term extraction and glossary foundation.

Scope section 6.2: "Technical terms are identified at ingestion and a background
glossary is prepared so the agent can explain them instantly."

The work splits cleanly in two:

  * IDENTIFYING candidate terms is free — it is a text-statistics problem, and
    it is implemented here.
  * WRITING definitions needs a language model, which needs an API key. That
    half is deliberately left as a stub, in the same position as video
    transcription: fully specified, switched on by configuration.

So `extract_technical_terms` returns real terms today, and `build_glossary`
returns an empty list until Module 5's language model is wired in. The shared
content contract already reserves `technical_terms` and `glossary`, and both
are optional, so producing the first and not the second is valid.

How terms are identified, and why this way
------------------------------------------
No dependency, and no training data. Three signals that need neither:

  1. Acronyms — runs of capitals such as LSTM, EAR, API.
  2. Capitalised words appearing mid-sentence, which in ordinary prose usually
     means a proper noun or a named concept.
  3. Repeated uncommon words — a word that is rare in general English but
     frequent in THIS document is very likely its subject matter.

This is a heuristic, not a classifier. It will miss multi-word terms
("gradient descent") and will occasionally offer a name as a term. It is a
foundation to build on, which is what the issue asks for.
"""

import re
from collections import Counter

# Words too common to ever be technical terms. Short list on purpose: the
# frequency rule below does most of the work, and a long stop-word list is the
# kind of thing that silently rots.
_COMMON = {
    "the", "and", "for", "that", "this", "with", "from", "have", "has", "been",
    "are", "was", "were", "will", "would", "could", "should", "can", "may",
    "which", "when", "where", "what", "how", "why", "who", "there", "their",
    "these", "those", "than", "then", "them", "they", "some", "such", "into",
    "also", "more", "most", "other", "only", "over", "after", "before", "between",
    "because", "however", "therefore", "while", "during", "each", "both", "all",
    "one", "two", "three", "first", "second", "using", "used", "use", "make",
    "made", "does", "did", "not", "but", "its", "it", "as", "at", "by", "on",
    "in", "of", "to", "is", "be", "an", "a", "or", "if", "we", "you", "he",
    "she", "his", "her", "our", "your", "example", "figure", "table", "section",
}

_ACRONYM = re.compile(r"\b[A-Z]{2,6}\b")
_WORD = re.compile(r"\b[a-zA-Z][a-zA-Z-]{2,}\b")
_MID_SENTENCE_CAP = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{3,})\b")

MAX_TERMS = 40
_MIN_REPEATS = 3


def extract_technical_terms(text: str, limit: int = MAX_TERMS) -> list:
    """
    Candidate technical terms, most significant first.

    Returns a plain list of strings, matching the contract's `technical_terms`.
    """
    if not text or not text.strip():
        return []

    scores = Counter()

    # 1. Acronyms — the strongest signal, so weighted highest.
    for acronym in _ACRONYM.findall(text):
        if acronym.lower() not in _COMMON:
            scores[acronym] += 3

    # 2. Capitalised mid-sentence words.
    for word in _MID_SENTENCE_CAP.findall(text):
        if word.lower() not in _COMMON:
            scores[word] += 2

    # 3. Repeated uncommon words.
    lowered = [w.lower() for w in _WORD.findall(text)]
    for word, count in Counter(lowered).items():
        if count >= _MIN_REPEATS and word not in _COMMON and len(word) > 4:
            scores[word] += min(count, 10)

    # Fold "LSTM" and "lstm" together, preferring the form seen most often.
    merged = {}
    for term, score in scores.items():
        key = term.lower()
        if key not in merged or score > merged[key][1]:
            merged[key] = (term, score)

    ranked = sorted(merged.values(), key=lambda pair: (-pair[1], pair[0].lower()))
    return [term for term, _ in ranked[:limit]]


def build_glossary(terms: list, context: str = "") -> list:
    """
    Definitions for the extracted terms.

    STUB. Returns an empty list until a language model is configured.

    Writing a definition requires understanding the term in context, which is a
    language-model task — the same reason video transcription is dormant. The
    contract makes `glossary` optional precisely so this can arrive later
    without a schema change.

    When implemented, each entry must be {"term": str, "definition": str} to
    match shared/contracts/content.schema.json.
    """
    return []
