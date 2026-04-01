"""Stateless BM25-style sparse vector generation."""

import math
import re
from collections import Counter

from .config import BM25_K1, HASH_SPACE


def sparse_vector(text: str) -> dict:
    """Generate a sparse vector from text using BM25-style term weighting.

    Returns dict with 'indices' and 'values' lists for Qdrant SparseVector.
    Uses token hashing (no vocabulary fitting required) so this works
    incrementally without corpus statistics.
    """
    tokens = _tokenize(text)
    if not tokens:
        return {"indices": [], "values": []}

    counts = Counter(tokens)
    indices = []
    values = []

    for token, tf in counts.items():
        idx = hash(token) % HASH_SPACE
        # BM25 TF saturation: diminishing returns for repeated terms
        weight = (BM25_K1 + 1) * tf / (BM25_K1 + tf)
        # Sublinear boost for very frequent terms
        weight = math.log1p(weight)
        indices.append(idx)
        values.append(round(weight, 4))

    return {"indices": indices, "values": values}


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenization with punctuation removal."""
    text = text.lower()
    tokens = re.findall(r"\b[a-z0-9]{2,}\b", text)
    return tokens
