import fitz  # PyMuPDF
import re


def extract_text_with_layout(pdf_bytes: bytes) -> str:
    """Extracts text from a PDF using column-aware block ordering (PyMuPDF),
    which handles multi-column academic layouts far better than a simple
    top-to-bottom stream read."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = []

    for page in doc:
        blocks = page.get_text("blocks")
        # sort blocks by column (x position) then vertical position within column
        blocks.sort(key=lambda b: (round(b[0] / 250), b[1]))
        page_text = "\n".join(b[4] for b in blocks if b[4].strip())
        full_text.append(page_text)

    doc.close()
    return "\n".join(full_text)


def extract_abstract(text: str) -> str | None:
    match = re.search(r"abstract[:\s]*\n?(.*?)(?=\n\s*(introduction|keywords|1\.|i\.)\b)",
                       text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()[:2000]  # cap length as a safety bound
    return None


def remove_references_section(text: str) -> str:
    """Cuts off everything from the References/Bibliography heading onward,
    since this is not useful study content."""
    match = re.search(r"\n\s*(references|bibliography)\s*\n", text, re.IGNORECASE)
    if match:
        return text[:match.start()]
    return text


def process_research_paper(pdf_bytes: bytes) -> dict:
    raw_text = extract_text_with_layout(pdf_bytes)
    abstract = extract_abstract(raw_text)
    body_text = remove_references_section(raw_text)

    return {
        "abstract": abstract,
        "body_text": body_text,
    }