"""
services/reranker.py
─────────────────────
Cross-Encoder Reranking via a lightweight LLM judge.

Why a "Cross-Encoder"?
  Bi-encoder retrieval (vector + BM25) encodes query and document SEPARATELY.
  A cross-encoder sees query AND document TOGETHER, making far better
  relevance decisions — especially for:
    • Negation ("I do NOT want diagnostic centers in Chennai")
    • Specificity ("Chennai" should outscore "Bangalore" for a Chennai query)
    • Cross-lingual pairs ("congé" ↔ "annual leave")

Implementation: LLM-as-judge (gpt-4o-mini via OpenRouter).
  For each (query, chunk) pair we ask the LLM for a relevance score 0-10.
  This is equivalent to a neural cross-encoder but uses the same LLM
  already present in the stack — no extra dependency.

Fallback: if the LLM call fails or returns nonsense, the original
  hybrid score is kept unchanged (graceful degradation).

Speed:
  We batch ALL candidates in a SINGLE LLM call using a JSON response
  format, adding ~1 s overhead but avoiding N sequential API round-trips.
  Only the top `rerank_top_n` candidates are reranked; the rest are pruned
  before calling the LLM (cheaper).
"""
from __future__ import annotations

import json
import re
from typing import List

from openai import OpenAI
from .rag_settings import settings

_rerank_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _rerank_client
    if _rerank_client is None:
        _rerank_client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            timeout=30,
        )
    return _rerank_client


_RERANK_PROMPT = """\
You are a relevance-scoring engine. Given a user query and a list of text passages,
score each passage from 0 to 10 based on how relevant and useful it is for answering the query.

Score meaning:
  0   = completely irrelevant / different topic
  3   = tangentially related
  6   = partially relevant
  8   = clearly relevant
  10  = directly and fully answers the query

Cross-lingual rule: if a passage contains the same information as the query but in a
different language, treat it as fully relevant (score ≥ 8).

Respond with ONLY a valid JSON array of integers, one score per passage in the same
order as provided. No explanation, no text, no markdown. Example:
[8, 2, 9, 4, 7]

USER QUERY:
{query}

PASSAGES:
{passages}
"""


def rerank(
    query:         str,
    candidates:    List[dict],
    rerank_top_n:  int = 10,
    final_top_k:   int | None = None,
) -> List[dict]:
    """
    Cross-encoder rerank a list of retrieval candidates.

    Args:
        query:        The user's original question.
        candidates:   List of dicts with keys: id, score, text, source.
        rerank_top_n: Maximum candidates to send to the LLM (prune first).
        final_top_k:  Return only top-k after reranking (None = return all).

    Returns:
        Candidates sorted by rerank_score descending, each dict gains a
        `rerank_score` key and the `score` key is updated to the LLM score.
    """
    if not candidates:
        return candidates

    # Prune to rerank_top_n before calling LLM
    pool = candidates[:rerank_top_n]

    # Build the passage list for the prompt
    passage_blocks = "\n\n".join(
        f"[{i+1}] {c['text'][:800]}"   # cap at 800 chars per chunk to fit context
        for i, c in enumerate(pool)
    )

    prompt = _RERANK_PROMPT.format(query=query, passages=passage_blocks)

    try:
        resp = _get_client().chat.completions.create(
            model       = settings.CHAT_MODEL,
            messages    = [{"role": "user", "content": prompt}],
            temperature = 0.0,
            max_tokens  = 64,
            extra_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title":      "Teleperformance RAG Reranker",
            },
        )
        raw    = resp.choices[0].message.content or "[]"
        # Strip markdown fences if present
        raw    = re.sub(r"```[^`]*```", "", raw, flags=re.DOTALL).strip()
        scores = json.loads(raw)

        if isinstance(scores, list) and len(scores) == len(pool):
            for i, c in enumerate(pool):
                c["rerank_score"] = float(scores[i]) / 10.0   # normalise to 0-1
            pool.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        # else: fallback — original order kept

    except Exception:
        # Graceful degradation: keep original ordering
        for c in pool:
            c.setdefault("rerank_score", c.get("score", 0.0))

    if final_top_k is not None:
        pool = pool[:final_top_k]

    return pool
