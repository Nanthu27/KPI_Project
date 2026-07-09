"""Cascade API Schemas"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class IntentType(str, Enum):
    INSIGHT   = "insight"
    GOAL      = "goal"
    KNOWLEDGE = "knowledge"
    TRACE     = "trace"
    ADVISOR   = "advisor"
    WHATIF    = "whatif"
    UNKNOWN   = "unknown"


class ChatMessage(BaseModel):
    role: str      # "user" | "assistant"
    content: str


class PageContext(BaseModel):
    """Live KPI data from the current page — sent by the frontend with every message."""
    active_interventions: List[Dict[str, Any]] = []
    business_outcomes: List[Dict[str, Any]] = []
    l1_metrics: List[Dict[str, Any]] = []
    l2_metrics: List[Dict[str, Any]] = []
    filters: Dict[str, Any] = {}


class CascadeChatRequest(BaseModel):
    message: str = Field(..., description="User's question or message")
    history: List[ChatMessage] = Field(default=[], description="Prior conversation turns")

    # Intent override (from UI chips — lets user force a specific tool)
    intent_override: Optional[IntentType] = None

    # Simulation filter context
    vertical_horizontal: Optional[str] = None
    lob: Optional[str] = None

    # Live page data from frontend
    page_context: Optional[PageContext] = None

    # For goal tool
    target_metric: Optional[str] = None
    target_value: Optional[float] = None
    higher_is_better: Optional[bool] = False

    # For trace tool
    trace_metric: Optional[str] = None
    from_intervention: Optional[str] = None
    to_outcome: Optional[str] = None

    # For advisor tool
    target_outcome: Optional[str] = None

    # Optional session id for the LangGraph multi-agent orchestrator
    # (app/ai/graph). Ignored by the legacy single-agent /cascade/chat
    # endpoint — purely additive, does not affect existing behavior.
    session_id: Optional[str] = None


class ToolResult(BaseModel):
    tool_used: str
    data: Dict[str, Any]


class CascadeChatResponse(BaseModel):
    reply: str
    intent: IntentType
    tool_result: Optional[ToolResult] = None
    suggested_followups: List[str] = []
    # Deterministic, non-LLM-generated: which real data sources backed this
    # answer, and a 0-1 confidence score computed from source coverage and
    # whether any numbers in the reply couldn't be matched back to tool data.
    evidence: List[str] = []
    confidence: float = 0.0
    # Structured plan for the frontend's sticky Recommendation Card (Goal /
    # Advisor recommend-mode only). None when this turn has no actionable
    # plan to pin (Insight/Knowledge/Trace/What-If/Advisor-apply-mode).
    card_data: Optional[Dict[str, Any]] = None


class ApplyRecommendationRequest(BaseModel):
    """Apply suggested intervention values to the simulator sliders (explicit user action)."""
    interventions: List[Dict[str, Any]]   # [{"name": "IDP", "value": 65}, ...]


class IngestRequest(BaseModel):
    """Trigger RAG document ingestion into Pinecone."""
    rebuild: bool = False


# ── LangGraph multi-agent orchestrator schemas (additive) ──────────────────

class NodeTraceEntry(BaseModel):
    node: str
    duration_ms: float = 0.0
    status: str = "ok"
    detail: str = ""


class GraphChatResponse(BaseModel):
    """Response for the multi-agent /cascade/graph/chat endpoint. Superset
    of CascadeChatResponse: adds full explainability into which agents ran,
    in what order, and how confident/complete the answer is."""
    reply: str
    intent: IntentType
    required_agents: List[str] = []
    execution_plan: List[str] = []
    tool_outputs: Dict[str, Any] = {}
    # Deterministic (no-LLM) grounding output — see evidence/grounding.py.
    # `evidence` lists which real data sources backed the answer;
    # `ungrounded` lists any numbers in the reply that could not be
    # matched back to real tool output (should be empty in a healthy run).
    evidence: List[str] = []
    ungrounded: List[float] = []
    confidence: float = 0.0
    errors: List[str] = []
    missing_information: List[str] = []
    node_trace: List[NodeTraceEntry] = []
    suggested_followups: List[str] = []
