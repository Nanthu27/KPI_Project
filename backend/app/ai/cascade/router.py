"""
Cascade API Router
------------------
Mounts at /api/cascade/ — additive, never modifies existing routes.

Endpoints:
  POST /api/cascade/chat          — standard JSON chat
  POST /api/cascade/chat/stream   — streaming SSE chat
  POST /api/cascade/apply         — apply AI-recommended slider values to DB
  POST /api/cascade/ingest        — trigger RAG document ingestion (background)
  GET  /api/cascade/health        — health / diagnostics
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...database import get_db
from .schemas import (
    CascadeChatRequest,
    CascadeChatResponse,
    ApplyRecommendationRequest,
    IngestRequest,
    ToolResult,
)
from .agent import run_cascade, stream_cascade

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cascade", tags=["Cascade AI"])


# ── Standard chat ────────────────────────────────────────────────────────────

@router.post("/chat", response_model=CascadeChatResponse)
def cascade_chat(request: CascadeChatRequest, db: Session = Depends(get_db)):
    """
    Main Cascade AI chat endpoint (non-streaming).
    Auto-detects intent and dispatches to the appropriate tool.
    Returns complete JSON response.
    """
    try:
        result = run_cascade(db, request)
        return CascadeChatResponse(
            reply=result["reply"],
            intent=result["intent"],
            tool_result=ToolResult(
                tool_used=result["tool_result"]["tool_used"],
                data=result["tool_result"]["data"],
            ),
            suggested_followups=result["suggested_followups"],
            evidence=result.get("evidence", []),
            confidence=result.get("confidence", 0.0),
            card_data=result.get("card_data"),
        )
    except Exception as e:
        logger.error(f"/cascade/chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Streaming chat ────────────────────────────────────────────────────────────

@router.post("/chat/stream")
async def cascade_chat_stream(request: CascadeChatRequest, db: Session = Depends(get_db)):
    """
    Streaming Cascade AI chat via Server-Sent Events (SSE).

    Stream format:
      data: {"intent": "insight", "tool": "insight", "followups": [...]}  ← first event
      data: {"chunk": "text..."}   ← LLM token chunks
      data: [DONE]                 ← stream end
    """
    async def generate():
        try:
            async for chunk in stream_cascade(db, request):
                yield chunk
        except Exception as e:
            logger.error(f"Cascade stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )


# ── Apply Recommendation (DEPRECATED — kept only to avoid breaking old clients) ─

@router.post("/apply")
def apply_recommendation(request: ApplyRecommendationRequest, db: Session = Depends(get_db)):
    """
    DEPRECATED. Do not call this from the frontend.

    Applying an AI recommendation must behave EXACTLY like a manual slider
    drag: frontend-only, in-memory, never persisted to the database. The
    actual implementation now lives entirely in the frontend —
    `kpiStore.applyRecommendationLocal()` — which updates `liveInterventions`
    and re-runs the local cascade, with zero API calls.

    This endpoint is intentionally a no-op that returns an explanatory error,
    so any stale frontend build calling it fails loudly instead of silently
    writing to the database or leaking changes across Vertical/LOB boundaries
    (the previous bug: `Intervention.name.ilike(...)` matched the first record
    anywhere in the table, regardless of which vertical/LOB was active).
    """
    return {
        "ok": False,
        "applied": [],
        "not_found": [iv.get("name", "") for iv in request.interventions],
        "message": (
            "This endpoint is deprecated. Applying an AI recommendation no longer "
            "writes to the database — it is handled entirely in the frontend via "
            "kpiStore.applyRecommendationLocal(), exactly like a slider drag. "
            "If you are seeing this, your frontend build is out of date."
        ),
    }


# ── (legacy code kept for reference, no longer reachable) ─────────────────────
def _legacy_apply_recommendation_DO_NOT_USE(request: ApplyRecommendationRequest, db: Session):
    from ...models import Intervention
    from ...services import simulation_service

    applied = []
    not_found = []

    for iv_req in request.interventions:
        name = iv_req.get("name", "").strip()
        value = max(0.0, min(100.0, float(iv_req.get("value", 0))))

        iv = db.query(Intervention).filter(
            Intervention.name.ilike(f"%{name}%")
        ).first()

        if iv:
            iv.percentage = value
            applied.append({"name": iv.name, "value": value})
        else:
            not_found.append(name)

    if applied:
        db.commit()
        simulation_service.recalculate(db)

    return {
        "ok": True,
        "applied": applied,
        "not_found": not_found,
        "message": f"Applied {len(applied)} intervention(s). Simulation recalculated.",
    }


# ── RAG Ingestion ─────────────────────────────────────────────────────────────

@router.post("/ingest")
def ingest_documents(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger RAG document ingestion into Pinecone (runs in background).

    Ingests: built-in KPI knowledge, BRD.docx, Excel metadata, docs/*.txt
    After ingestion, restart the backend to activate Pinecone retrieval.
    """
    def _run():
        try:
            from ..services.rag_service import get_rag_service
            rag = get_rag_service()
            rag.reset_for_reingest()
            rag._ensure_initialized()
            logger.info("RAG re-ingestion completed")
        except Exception as e:
            logger.error(f"RAG ingestion error: {e}", exc_info=True)

    background_tasks.add_task(_run)
    return {
        "ok": True,
        "message": "Document ingestion started in background. Check server logs for progress.",
    }


# ── Health Check ──────────────────────────────────────────────────────────────

@router.get("/health")
def cascade_health():
    """Check cascade component status: LLM config, RAG, Pinecone."""
    from ..config import get_ai_config

    cfg = get_ai_config()
    status: dict = {}

    # LLM
    status["llm_provider"] = "Google Gemini"
    status["llm_model"] = cfg.gemini_model
    status["llm_fallback_model"] = cfg.gemini_fallback_model
    status["gemini_key_set"] = bool(cfg.gemini_api_key)

    # RAG
    status["pinecone_key_set"] = bool(cfg.pinecone_api_key)
    status["pinecone_index"] = cfg.pinecone_index_name
    status["hybrid_alpha"] = cfg.hybrid_alpha
    status["rag_top_k"] = cfg.rag_top_k

    try:
        from ..services.rag_service import get_rag_service
        rag = get_rag_service()
        rag._ensure_initialized()
        status["rag_documents"] = len(rag._documents)
        status["bm25"] = "active"
        status["pinecone_connected"] = rag._pinecone_index is not None
    except Exception as e:
        status["rag_error"] = str(e)

    status["ready"] = status["gemini_key_set"]
    status["mode"] = (
        "Full hybrid RAG (BM25 + Pinecone)" if status.get("pinecone_connected")
        else "BM25 + local vectors (set PINECONE_API_KEY for full vector search)"
    )

    return status
