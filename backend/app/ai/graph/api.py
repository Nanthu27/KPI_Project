"""
Multi-Agent Graph API
-----------------------
Mounts at /api/cascade/graph/ — purely additive. Does not modify or
replace the legacy /api/cascade/* endpoints; both can run side by side
so the frontend can migrate at its own pace.

Endpoints:
  POST /api/cascade/graph/chat          — full multi-agent JSON response
  POST /api/cascade/graph/chat/stream   — SSE stream (progress + answer)
  GET  /api/cascade/graph/memory/{sid}  — inspect session memory (debug)
  DELETE /api/cascade/graph/memory/{sid}— clear session memory
"""
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...database import get_db
from ..cascade.schemas import CascadeChatRequest, GraphChatResponse
from ..memory.memory import ConversationMemory
from .builder import run_graph_cascade, stream_graph_cascade

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cascade/graph", tags=["Cascade AI — Multi-Agent (LangGraph)"])


def _resolve_session_id(request: CascadeChatRequest) -> str:
    return request.session_id or str(uuid.uuid4())


@router.post("/chat", response_model=GraphChatResponse)
def graph_chat(request: CascadeChatRequest, db: Session = Depends(get_db)):
    """
    Multi-agent Cascade AI chat (non-streaming).
    Router -> Planner -> [Insight/Goal/Knowledge/Trace/Advisor] -> Formatter.
    Returns the same kind of answer as /cascade/chat, plus full
    explainability (which agents ran, confidence, errors).
    """
    session_id = _resolve_session_id(request)
    try:
        result = run_graph_cascade(db, request, session_id)
        return GraphChatResponse(
            reply=result["reply"],
            intent=result["intent"],
            required_agents=result["required_agents"],
            execution_plan=result["execution_plan"],
            tool_outputs=result["tool_outputs"],
            evidence=result.get("evidence", []),
            ungrounded=result.get("ungrounded", []),
            confidence=result["confidence"],
            errors=result["errors"],
            missing_information=result["missing_information"],
            node_trace=result["node_trace"],
            suggested_followups=result["suggested_followups"],
        )
    except Exception as e:
        logger.error(f"/cascade/graph/chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def graph_chat_stream(request: CascadeChatRequest, db: Session = Depends(get_db)):
    """
    Streaming multi-agent chat via SSE.

    Stream format:
      data: {"progress": {"node": "insight", "status": "ok", ...}}  ← per-node
      data: {"intent": ..., "execution_plan": [...], "followups": [...]}
      data: {"chunk": "final answer text"}
      data: [DONE]
    """
    session_id = _resolve_session_id(request)

    async def generate():
        try:
            async for chunk in stream_graph_cascade(db, request, session_id):
                yield chunk
        except Exception as e:
            logger.error(f"Graph cascade stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/memory/{session_id}")
def get_session_memory(session_id: str):
    """Debug endpoint: inspect what the orchestrator remembers for a session."""
    return ConversationMemory.get(session_id).as_dict()


@router.delete("/memory/{session_id}")
def clear_session_memory(session_id: str):
    ConversationMemory.clear(session_id)
    return {"ok": True, "cleared": session_id}
