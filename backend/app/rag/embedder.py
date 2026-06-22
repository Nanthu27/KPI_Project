"""
services/embedder.py
─────────────────────
Generates embeddings via OpenRouter (no separate OpenAI billing needed).
Model: text-embedding-3-small routed through OpenRouter.
"""

from __future__ import annotations
from typing import List
from openai import OpenAI
from .rag_settings import settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.OPENROUTER_API_KEY:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set in your .env file.\n"
                "Get a key at https://openrouter.ai → Dashboard → API Keys"
            )
        # Use OpenRouter as the base — handles embeddings too
        _client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
    return _client


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of strings, batched in groups of 100."""
    client = _get_client()
    all_vectors: List[List[float]] = []

    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=batch,
            extra_headers={
                "HTTP-Referer": "http://localhost:5000",
                "X-Title": "Teleperformance RAG",
            },
        )
        all_vectors.extend([item.embedding for item in response.data])

    return all_vectors


def embed_query(query: str) -> List[float]:
    """Embed a single query string."""
    return embed_texts([query])[0]