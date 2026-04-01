"""Dense embedding via Ollama and upsert to Qdrant with hybrid vectors."""

import logging
import requests
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from .bm25_vectorizer import sparse_vector
from .config import (
    COLLECTION_COLD,
    COLLECTION_HOT,
    EMBED_DIM,
    EMBED_MODEL,
    OLLAMA_URL,
    QDRANT_URL,
)

log = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 20
UPSERT_BATCH_SIZE = 100


def ensure_collections():
    """Create Qdrant collections if they don't exist."""
    client = QdrantClient(url=QDRANT_URL)
    for name in (COLLECTION_HOT, COLLECTION_COLD):
        if not client.collection_exists(name):
            client.create_collection(
                collection_name=name,
                vectors_config={
                    "dense": VectorParams(
                        size=EMBED_DIM,
                        distance=Distance.COSINE,
                        on_disk=True,
                    )
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams()
                },
                hnsw_config=HnswConfigDiff(on_disk=True),
                on_disk_payload=True,
            )
            log.info(f"Created collection: {name}")


def embed_and_upsert(chunks: list[dict], collection: str):
    """Generate dense + sparse vectors for chunks and upsert to Qdrant.

    Args:
        chunks: list of dicts with 'id', 'text', 'metadata'
        collection: target Qdrant collection name
    """
    client = QdrantClient(url=QDRANT_URL)

    for batch_start in range(0, len(chunks), UPSERT_BATCH_SIZE):
        batch = chunks[batch_start : batch_start + UPSERT_BATCH_SIZE]
        texts = [c["text"] for c in batch]

        # Dense embeddings via Ollama
        dense_vectors = _embed_batch(texts)

        # Sparse vectors via BM25
        sparse_vectors = [sparse_vector(t) for t in texts]

        points = []
        for chunk, dense, sparse in zip(batch, dense_vectors, sparse_vectors):
            point = PointStruct(
                id=chunk["id"],
                vector={
                    "dense": dense,
                    "sparse": SparseVector(
                        indices=sparse["indices"],
                        values=sparse["values"],
                    ),
                },
                payload={
                    "text": chunk["text"],
                    **chunk["metadata"],
                },
            )
            points.append(point)

        client.upsert(collection_name=collection, points=points)
        log.info(f"Upserted {len(points)} points to {collection}")


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Get dense embeddings from Ollama in batches."""
    all_embeddings = []

    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        for text in batch:
            resp = requests.post(
                f"{OLLAMA_URL}/api/embed",
                json={"model": EMBED_MODEL, "input": text},
                timeout=30,
            )
            resp.raise_for_status()
            all_embeddings.append(resp.json()["embeddings"][0])

    return all_embeddings
