"""Text chunking with recursive character splitting."""

import hashlib

from .config import CHUNK_SIZE, CHUNK_OVERLAP

SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def chunk_sections(sections: list[dict]) -> list[dict]:
    """Split extracted sections into chunks with metadata and deterministic IDs.

    Each returned chunk has:
        - id: SHA-256 hex digest (first 32 chars) for Qdrant point ID
        - text: chunk text
        - metadata: inherited from section + chunk_index
    """
    chunks = []
    for section in sections:
        texts = _split_recursive(section["text"], CHUNK_SIZE, CHUNK_OVERLAP)
        source = section["metadata"].get("source", "unknown")
        context = section["metadata"].get("chapter_title", "")

        for i, text in enumerate(texts):
            raw_id = f"{source}::{context}::chunk_{i}"
            chunk_id = hashlib.sha256(raw_id.encode()).hexdigest()[:32]
            chunks.append({
                "id": chunk_id,
                "text": text,
                "metadata": {**section["metadata"], "chunk_index": i},
            })

    return chunks


def _split_recursive(text: str, size: int, overlap: int) -> list[str]:
    """Split text recursively by paragraph, newline, sentence, then word."""
    if len(text) <= size:
        return [text]

    for sep in SEPARATORS:
        parts = text.split(sep) if sep else list(text)
        if len(parts) > 1:
            return _merge_splits(parts, sep, size, overlap)

    return [text[:size]]


def _merge_splits(parts: list[str], sep: str, size: int, overlap: int) -> list[str]:
    """Merge split parts into chunks respecting size and overlap."""
    chunks = []
    current = []
    current_len = 0

    for part in parts:
        part_len = len(part) + (len(sep) if current else 0)

        if current_len + part_len > size and current:
            chunks.append(sep.join(current))

            # Keep tail parts for overlap
            while current and current_len > overlap:
                dropped = current.pop(0)
                current_len -= len(dropped) + len(sep)

        current.append(part)
        current_len += part_len

    if current:
        chunks.append(sep.join(current))

    return [c for c in chunks if c.strip()]
