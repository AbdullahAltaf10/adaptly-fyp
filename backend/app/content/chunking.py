import re

# Sentence splitting.
#
# The previous version used raw_text.split(". "), which had two defects:
#   1. It DELETED every full stop, because the separator was consumed and only a
#      space was put back when rejoining. Stored text read as one long run-on
#      sentence with no punctuation. This was invisible only because nothing in
#      the application displays content yet.
#   2. It split on abbreviations, so "Dr. Smith" became two sentences.
#
# Fixed in two steps rather than one clever regex: split after any sentence-
# ending punctuation (keeping it), then merge a piece back into the previous one
# when the split turned out to be an abbreviation. A single regex would need a
# variable-width look-behind, which Python does not support.

_SPLIT_AFTER_PUNCTUATION = re.compile(r'(?<=[.!?])["\')\]]*\s+')

# Words that end in a full stop without ending a sentence.
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "a.m", "p.m", "fig", "eq", "no", "vol", "ch",
    "approx", "inc", "ltd", "co", "dept", "est", "al",
}


def _ends_with_abbreviation(text: str) -> bool:
    """True if `text` ends in something like 'Dr.', 'e.g.' or an initial 'A.'."""
    if not text.endswith("."):
        return False
    last = text.split()[-1].rstrip('."\')]').lower()
    if last in _ABBREVIATIONS:
        return True
    # A single letter, i.e. an initial such as the "A." in "A. Gupta"
    return len(last) == 1 and last.isalpha()


def split_sentences(raw_text: str) -> list:
    """Split text into sentences, keeping each sentence's punctuation."""
    flat = re.sub(r"\s+", " ", raw_text.replace("\n", " ")).strip()
    if not flat:
        return []

    pieces = [p for p in _SPLIT_AFTER_PUNCTUATION.split(flat) if p and p.strip()]

    sentences = []
    for piece in pieces:
        piece = piece.strip()
        if sentences and _ends_with_abbreviation(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {piece}"
        else:
            sentences.append(piece)
    return sentences


def chunk_text(raw_text: str, max_words: int = 120) -> list:
    """
    Split long text into readable chunks of about `max_words`, never cutting a
    sentence in half.

    The number of chunks is not chosen by anyone — it falls out of the length of
    the text, roughly (total words / max_words).

    Each chunk carries:
        chunk_id - a STRING identifier. Strings survive a later move to real ids
                   such as UUIDs; integers do not.
        order    - explicit position, so consumers never have to rely on array
                   order surviving storage, filtering or re-sorting.
        text     - the chunk itself, with punctuation intact.
    """
    sentences = split_sentences(raw_text)

    chunks = []
    current = []
    word_count = 0

    for sentence in sentences:
        words = sentence.split()
        if word_count + len(words) > max_words and current:
            chunks.append(" ".join(current).strip())
            current = []
            word_count = 0
        current.append(sentence)
        word_count += len(words)

    if current:
        chunks.append(" ".join(current).strip())

    return [
        {"chunk_id": str(i), "order": i, "text": text}
        for i, text in enumerate(c for c in chunks if c)
    ]
