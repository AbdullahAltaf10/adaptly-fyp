def chunk_text(raw_text: str, max_words: int = 120) -> list:
    """Split long text into readable chunks of ~max_words each, breaking on sentence boundaries."""
    sentences = raw_text.replace("\n", " ").split(". ")
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

    return [{"chunk_id": i, "text": c} for i, c in enumerate(chunks) if c]