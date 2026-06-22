"""
Knowledge Agent (spec section 4). RAG-based Q&A over the BRD, Excel
metadata, and User Guide corpus, reusing the existing OpenRouter-based
pipeline (vector_store -> reranker) AS-IS per product decision. This is
the only one of the 3 narration-style spots in this file set that does
NOT call Anthropic — it calls OpenRouter via app/rag/rag_settings.py,
exactly like the original standalone RAG backend did.
"""
from __future__ import annotations

import json
from typing import List

from openai import OpenAI

from ..schemas.agent_schemas import KnowledgeRequest, KnowledgeResponse, KnowledgeSource
from ..rag.vector_store import query_similar
from ..rag.reranker import rerank
from ..rag.rag_settings import settings
from .hallucination_guard import validate_no_hallucinated_numbers


class KnowledgeAgentNotConfiguredError(RuntimeError):
    pass


def _get_openrouter_client() -> OpenAI:
    if not settings.OPENROUTER_API_KEY:
        raise KnowledgeAgentNotConfiguredError(
            "OPENROUTER_API_KEY is not set. The Knowledge Agent's RAG pipeline "
            "(embeddings + chat) cannot run without it. See .env.example."
        )
    return OpenAI(api_key=settings.OPENROUTER_API_KEY, base_url=settings.OPENROUTER_BASE_URL)


def _format_source_ref(metadata: dict, source: str) -> KnowledgeSource:
    doc_type = metadata.get("doc_type", "unknown")
    if doc_type == "brd":
        section_number = metadata.get("section_number") or ""
        section_title = metadata.get("section_title") or ""
        ref = f"BRD Section {section_number} {section_title}".strip()
    elif doc_type == "excel":
        ref = f"Excel sheet '{metadata.get('sheet_name', '?')}', row {metadata.get('row_number', '?')}"
    elif doc_type == "user_guide":
        ref = f"User Guide — {metadata.get('section_title', 'Overview')}"
    else:
        ref = source
    return KnowledgeSource(doc_type=doc_type, ref=ref)


def handle_knowledge_query(request: KnowledgeRequest) -> KnowledgeResponse:
    try:
        candidates = query_similar(request.user_question, top_k=request.top_k)
    except Exception as exc:  # noqa: BLE001 — surface as a clean "unavailable" response, not a 500
        return KnowledgeResponse(
            response_text=f"[Knowledge Agent unavailable: retrieval failed — {exc}]",
            sources=[], not_found=True,
        )

    if not candidates:
        return KnowledgeResponse(
            response_text="I couldn't find this in the BRD, Excel, or User Guide.",
            sources=[], not_found=True,
        )

    reranked = rerank(request.user_question, candidates, rerank_top_n=settings.RERANK_TOP_N, final_top_k=request.rerank_top_n)

    relevant = [c for c in reranked if c.get("score", 0) >= settings.RELEVANCE_THRESHOLD]
    if not relevant:
        return KnowledgeResponse(
            response_text="I couldn't find this in the BRD, Excel, or User Guide.",
            sources=[], not_found=True,
        )

    context_blocks = "\n\n---\n\n".join(
        f"[Source: {c.get('metadata', {}).get('doc_type', 'unknown')}]\n{c['text']}"
        for c in relevant
    )

    try:
        client = _get_openrouter_client()
    except KnowledgeAgentNotConfiguredError as exc:
        return KnowledgeResponse(response_text=f"[{exc}]", sources=[], not_found=True)

    completion = client.chat.completions.create(
        model=settings.CHAT_MODEL,
        temperature=settings.CHAT_TEMPERATURE,
        max_tokens=settings.CHAT_MAX_TOKENS,
        messages=[
            {"role": "system", "content": settings.SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context_blocks}\n\nQuestion: {request.user_question}"},
        ],
    )
    raw_text = completion.choices[0].message.content or "{}"

    try:
        parsed = json.loads(raw_text.strip().strip("`").lstrip("json").strip())
    except (json.JSONDecodeError, ValueError):
        parsed = {"response_text": raw_text, "sources": [], "redirect_suggested": None}

    response_text = parsed.get("response_text", raw_text)

    sources: List[KnowledgeSource] = []
    if parsed.get("sources"):
        for s in parsed["sources"]:
            sources.append(KnowledgeSource(doc_type=s.get("doc_type", "unknown"), ref=s.get("ref", "")))
    else:
        # Fall back to deriving citations directly from the retrieved chunks if the
        # model didn't echo them back in its JSON (keeps citations honest either way).
        for c in relevant[:3]:
            sources.append(_format_source_ref(c.get("metadata", {}), c.get("source", "unknown")))

    payload_for_guard = {"retrieved_chunks": [c["text"] for c in relevant]}
    violations = validate_no_hallucinated_numbers(response_text, payload_for_guard)
    if violations:
        response_text += f"\n\n[Note: hallucination guard flagged unverified numbers: {violations}]"

    return KnowledgeResponse(
        response_text=response_text,
        sources=sources,
        redirect_suggested=parsed.get("redirect_suggested"),
        not_found=False,
    )
