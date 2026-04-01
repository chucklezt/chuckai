"""
title: RAG Retrieval
author: ChuckAI
version: 0.1.0
description: Hybrid BM25 + semantic retrieval from Qdrant with RRF fusion. Queries docs_hot first, falls back to docs_cold.
"""

import math
import re
from collections import Counter
from typing import List, Optional

import requests
from pydantic import BaseModel, Field


class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = ["*"]
        qdrant_url: str = Field(default="http://localhost:6333")
        ollama_url: str = Field(default="http://localhost:11434")
        embed_model: str = Field(default="nomic-embed-text")
        collection_hot: str = Field(default="docs_hot")
        collection_cold: str = Field(default="docs_cold")
        top_k: int = Field(default=5)
        min_hot_results: int = Field(default=3)
        priority: int = Field(default=0)
        enabled: bool = Field(default=True)

    def __init__(self):
        self.type = "filter"
        self.name = "RAG Retrieval"
        self.valves = self.Valves()

    async def on_startup(self):
        pass

    async def on_shutdown(self):
        pass

    async def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.enabled:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        # Get the last user message
        user_msg = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg
                break

        if not user_msg:
            return body

        query = user_msg.get("content", "")
        if not query or len(query) < 3:
            return body

        chunks = self._retrieve(query)
        if not chunks:
            return body

        # Build context block
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source", "unknown")
            book = chunk.get("book_title", "")
            chapter = chunk.get("chapter_title", "")

            label = f"[{i}] {source}"
            if book:
                label += f" — {book}"
            if chapter:
                label += f", {chapter}"

            context_parts.append(f"{label}\n{chunk['text']}")

        context = "\n\n".join(context_parts)

        rag_system = {
            "role": "system",
            "content": (
                "The following document excerpts were retrieved from the user's "
                "personal knowledge base. Use them to inform your answer when relevant. "
                "Cite sources by name when you use them. If the excerpts don't help "
                "answer the question, rely on your own knowledge and say so.\n\n"
                f"--- Retrieved Context ---\n{context}\n--- End Context ---"
            ),
        }

        # Insert after any existing system message
        insert_idx = 0
        if messages and messages[0].get("role") == "system":
            insert_idx = 1
        body["messages"].insert(insert_idx, rag_system)

        return body

    def _retrieve(self, query: str) -> list[dict]:
        """Query docs_hot first, fall back to docs_cold if < min_hot_results."""
        dense = self._embed(query)
        sparse = self._sparse_vector(query)
        if not dense:
            return []

        results = self._search(self.valves.collection_hot, dense, sparse)

        if len(results) < self.valves.min_hot_results:
            cold = self._search(self.valves.collection_cold, dense, sparse)
            results.extend(cold)

        return results[: self.valves.top_k]

    def _search(self, collection: str, dense: list, sparse: dict) -> list[dict]:
        """Hybrid search with RRF fusion via Qdrant REST API."""
        try:
            resp = requests.post(
                f"{self.valves.qdrant_url}/collections/{collection}/points/query",
                json={
                    "prefetch": [
                        {"query": dense, "using": "dense", "limit": 20},
                        {
                            "query": {
                                "indices": sparse["indices"],
                                "values": sparse["values"],
                            },
                            "using": "sparse",
                            "limit": 20,
                        },
                    ],
                    "query": {"fusion": "rrf"},
                    "limit": self.valves.top_k,
                    "with_payload": True,
                },
                timeout=10,
            )
            resp.raise_for_status()
            points = resp.json().get("result", {}).get("points", [])
            return [pt["payload"] for pt in points if pt.get("payload")]
        except Exception:
            return []

    def _embed(self, query: str) -> list[float]:
        """Dense embedding via Ollama."""
        try:
            resp = requests.post(
                f"{self.valves.ollama_url}/api/embed",
                json={"model": self.valves.embed_model, "input": query},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["embeddings"][0]
        except Exception:
            return []

    @staticmethod
    def _sparse_vector(text: str) -> dict:
        """BM25-style sparse vector — matches ingest/bm25_vectorizer.py."""
        tokens = re.findall(r"\b[a-z0-9]{2,}\b", text.lower())
        if not tokens:
            return {"indices": [], "values": []}

        counts = Counter(tokens)
        k1 = 1.2
        hash_space = 2**24
        indices, values = [], []

        for token, tf in counts.items():
            idx = hash(token) % hash_space
            weight = math.log1p((k1 + 1) * tf / (k1 + tf))
            indices.append(idx)
            values.append(round(weight, 4))

        return {"indices": indices, "values": values}
