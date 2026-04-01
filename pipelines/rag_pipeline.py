"""
title: RAG Retrieval
author: ChuckAI
version: 0.1.0
description: Hybrid BM25 + semantic retrieval from Qdrant with RRF fusion. Queries docs_hot first, falls back to docs_cold.
"""

import logging
import math
import re
import time
from collections import Counter
from typing import List, Optional

log = logging.getLogger("rag_pipeline")

import requests
from pydantic import BaseModel, Field


class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = ["*"]
        qdrant_url: str = Field(default="http://localhost:6333")
        ollama_url: str = Field(default="http://localhost:11434")
        embed_model: str = Field(default="nomic-embed-text:v1.5")
        collection_hot: str = Field(default="docs_hot")
        collection_cold: str = Field(default="docs_cold")
        top_k: int = Field(default=10)
        min_hot_results: int = Field(default=3)
        score_threshold: float = Field(default=0.5)
        priority: int = Field(default=0)
        enabled: bool = Field(default=True)

    def __init__(self):
        self.type = "filter"
        self.name = "RAG Retrieval"
        self.valves = self.Valves()
        self._last_sources = []
        self._web_search = False

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

        # Skip Open WebUI internal tasks (title generation, tag generation, etc.)
        if query.lstrip().startswith("### Task:"):
            return body

        # Detect web search — Open WebUI injects search results into messages
        self._web_search = any(
            "search results" in str(m.get("content", "")).lower()
            or "web_search" in str(m.get("metadata", {}))
            for m in messages
        )

        # Only use the last user turn for RAG — Open WebUI may pack conversation
        # history into a single message, causing irrelevant matches against
        # previous assistant responses
        if len(query) > 500:
            lines = [l.strip() for l in query.split("\n") if l.strip()]
            if lines:
                query = lines[-1]
            if len(query) > 500:
                query = query[:500]

        t0 = time.perf_counter()
        chunks = self._retrieve(query)
        retrieval_ms = (time.perf_counter() - t0) * 1000
        log.info(
            "inlet: query=%d chars, %d chunks retrieved in %.0f ms",
            len(query), len(chunks), retrieval_ms,
        )
        if not chunks:
            self._last_sources = []
            return body

        # Build context block and track sources for outlet
        context_parts = []
        seen_sources = []
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

            # Deduplicate sources for citation footer
            source_key = (source, book, chapter)
            if source_key not in seen_sources:
                seen_sources.append(source_key)

        self._last_sources = seen_sources

        context = "\n\n".join(context_parts)

        rag_system = {
            "role": "system",
            "content": (
                "The following document excerpts were retrieved from the user's "
                "personal knowledge base. Use them to inform your answer when relevant. "
                "Cite sources by name when you use them. If the excerpts are not "
                "relevant to the question, ignore them entirely and answer using your "
                "own knowledge. Do not mention or describe the excerpts.\n\n"
                f"--- Retrieved Context ---\n{context}\n--- End Context ---"
            ),
        }

        # Insert after any existing system message
        insert_idx = 0
        if messages and messages[0].get("role") == "system":
            insert_idx = 1
        body["messages"].insert(insert_idx, rag_system)

        return body

    async def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        messages = body.get("messages", [])
        if not messages:
            self._last_sources = []
            self._web_search = False
            return body

        # Find the last assistant message
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                # Determine response mode and build footer
                has_rag = bool(self._last_sources)
                has_web = self._web_search

                # Check if model actually used RAG context
                rag_used = False
                if has_rag:
                    content = msg["content"].lower()
                    skip_phrases = [
                        "do not contain",
                        "don't contain",
                        "no information",
                        "not relevant",
                        "not related",
                        "rely on my own",
                        "own knowledge",
                        "no relevant",
                    ]
                    rag_used = not any(phrase in content for phrase in skip_phrases)

                # Build mode tag
                modes = []
                if rag_used:
                    modes.append("RAG")
                if has_web:
                    modes.append("Web")
                if not modes:
                    modes.append("LLM")
                mode_tag = " + ".join(modes)

                # Build footer
                footer = f"\n\n---\n`{mode_tag}`"

                # Append RAG sources if used
                if rag_used:
                    lines = ["\n**Sources:**"]
                    for source, book, chapter in self._last_sources:
                        parts = [f"*{source}*"]
                        if book:
                            parts = [f"*{book}*"]
                        if chapter:
                            parts.append(chapter)
                        lines.append(f"- {' — '.join(parts)}")
                    footer += "\n".join(lines)

                msg["content"] += footer
                break

        self._last_sources = []
        self._web_search = False
        return body

    def _retrieve(self, query: str) -> list[dict]:
        """Query docs_hot first, fall back to docs_cold if < min_hot_results."""
        t0 = time.perf_counter()
        dense = self._embed(query)
        embed_ms = (time.perf_counter() - t0) * 1000
        sparse = self._sparse_vector(query)
        if not dense:
            log.warning("embed failed after %.0f ms", embed_ms)
            return []

        t1 = time.perf_counter()
        results = self._search(self.valves.collection_hot, dense, sparse)
        hot_ms = (time.perf_counter() - t1) * 1000
        log.info("search hot: %d results in %.0f ms", len(results), hot_ms)

        if len(results) < self.valves.min_hot_results:
            t2 = time.perf_counter()
            cold = self._search(self.valves.collection_cold, dense, sparse)
            cold_ms = (time.perf_counter() - t2) * 1000
            log.info("search cold (fallback): %d results in %.0f ms", len(cold), cold_ms)
            results.extend(cold)

        scores = [r.get("_score", 0) for r in results] or [0]
        log.info(
            "retrieve total: embed=%.0f ms, %d results above threshold %.2f (scores: %.3f–%.3f)",
            embed_ms, len(results), self.valves.score_threshold,
            min(scores), max(scores),
        )
        return results[: self.valves.top_k]

    def _search(self, collection: str, dense: list, sparse: dict) -> list[dict]:
        """Hybrid search: dense similarity for scoring + sparse BM25 for boosting.

        Uses dense search with score_threshold to filter by actual cosine
        similarity (not RRF rank scores which are always 0.5/0.333/etc).
        Then re-ranks using RRF fusion with sparse results for better ordering.
        """
        try:
            # Dense search with real cosine similarity scores
            dense_resp = requests.post(
                f"{self.valves.qdrant_url}/collections/{collection}/points/query",
                json={
                    "query": dense,
                    "using": "dense",
                    "limit": self.valves.top_k,
                    "score_threshold": self.valves.score_threshold,
                    "with_payload": True,
                },
                timeout=10,
            )
            dense_resp.raise_for_status()
            dense_points = dense_resp.json().get("result", {}).get("points", [])

            if not dense_points:
                return []

            # Also run sparse search for RRF re-ranking
            sparse_resp = requests.post(
                f"{self.valves.qdrant_url}/collections/{collection}/points/query",
                json={
                    "query": {
                        "indices": sparse["indices"],
                        "values": sparse["values"],
                    },
                    "using": "sparse",
                    "limit": 20,
                    "with_payload": True,
                },
                timeout=10,
            )
            sparse_resp.raise_for_status()
            sparse_points = sparse_resp.json().get("result", {}).get("points", [])

            # RRF fusion: combine rankings from dense + sparse
            rrf_k = 60
            scores = {}
            payloads = {}
            for rank, pt in enumerate(dense_points):
                pid = pt["id"]
                scores[pid] = scores.get(pid, 0) + 1.0 / (rrf_k + rank + 1)
                payloads[pid] = pt.get("payload", {})
                payloads[pid]["_dense_score"] = pt.get("score", 0)
            for rank, pt in enumerate(sparse_points):
                pid = pt["id"]
                scores[pid] = scores.get(pid, 0) + 1.0 / (rrf_k + rank + 1)
                if pid not in payloads:
                    payloads[pid] = pt.get("payload", {})

            # Only return points that passed the dense threshold
            ranked = sorted(
                [(pid, s) for pid, s in scores.items() if pid in {p["id"] for p in dense_points}],
                key=lambda x: x[1],
                reverse=True,
            )
            return [
                {**payloads[pid], "_score": payloads[pid].get("_dense_score", 0)}
                for pid, _ in ranked
            ]
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
        except Exception as e:
            log.error("embed error: %s (query len=%d)", e, len(query))
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
