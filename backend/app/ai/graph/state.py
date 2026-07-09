"""
ConversationState
------------------
Single shared state object threaded through every node in the LangGraph.

Design rule (per master spec): every agent reads the full state but only
WRITES to the fields it owns. LangGraph merges each node's returned dict
into the running state (shallow merge on top-level keys), so as long as
two agents never return the same key, nothing is ever overwritten.

Field ownership:
    router_node        -> intent, required_agents, entities, confidence
    planner_node        -> execution_plan
    insight_agent       -> kpis, business_metrics, tool_outputs["insight"]
    goal_agent           -> goal, calculations, tool_outputs["goal"]
    knowledge_agent      -> retrieved_documents, retrieved_chunks, tool_outputs["knowledge"]
    trace_agent           -> formula_trace, tool_outputs["trace"]
    advisor_agent        -> advisor_output, tool_outputs["advisor"]
    whatif_agent          -> whatif_output, tool_outputs["whatif"]
    formatter_agent      -> final_answer, confidence (final), suggested_followups
    every node            -> node_trace (append-only observability log), errors,
                             missing_information (append-only)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class NodeLogEntry(TypedDict, total=False):
    node: str
    started_at: float
    finished_at: float
    duration_ms: float
    status: str            # "ok" | "error" | "skipped" | "retried"
    detail: str


class ConversationState(TypedDict, total=False):
    # ── Identity / input ────────────────────────────────────────────────
    session_id: str
    user_query: str
    history: List[Dict[str, str]]          # [{"role": "user"/"assistant", "content": ...}]
    page_context: Optional[Any]            # schemas.PageContext (live simulator data)

    # Internal-only: SQLAlchemy session for this request. Must be declared
    # as a real schema field — LangGraph only preserves keys that are part
    # of the state schema across node hops; anything else is silently
    # dropped between nodes.
    db: Optional[Any]

    # ── Optional explicit parameters (mirrors CascadeChatRequest) ───────
    intent_override: Optional[str]
    target_metric: Optional[str]
    target_value: Optional[float]
    higher_is_better: Optional[bool]
    trace_metric: Optional[str]
    from_intervention: Optional[str]
    to_outcome: Optional[str]
    target_outcome: Optional[str]

    # ── Router / Planner output ──────────────────────────────────────────
    intent: str
    entities: Dict[str, Any]
    required_agents: List[str]             # e.g. ["insight", "goal"]
    execution_plan: List[str]              # ordered subset of required_agents
    plan_index: int                        # pointer into execution_plan (internal)

    # ── Per-agent structured outputs ─────────────────────────────────────
    kpis: List[Dict[str, Any]]
    business_metrics: List[Dict[str, Any]]
    goal: Dict[str, Any]
    calculations: Dict[str, Any]
    retrieved_documents: List[Dict[str, Any]]
    retrieved_chunks: List[Dict[str, Any]]
    formula_trace: Dict[str, Any]
    advisor_output: Dict[str, Any]
    whatif_output: Dict[str, Any]
    tool_outputs: Dict[str, Any]           # raw output of every tool, keyed by agent name

    # ── Final response ───────────────────────────────────────────────────
    final_answer: str
    suggested_followups: List[str]

    # ── Grounding / anti-hallucination (deterministic, no LLM) ───────────
    # Which real, verifiable data sources actually backed the final answer
    # (e.g. "live_simulation", "formula_trace") and any numbers the LLM's
    # prose used that could NOT be matched back to real tool output.
    # Computed once, in the formatter, over the UNION of every agent that
    # ran this turn — see agents/formatter_agent.py::_finalize_grounding.
    evidence: List[str]
    ungrounded_numbers: List[float]

    # ── Cross-cutting / observability ────────────────────────────────────
    confidence: float

    errors: List[str]
    missing_information: List[str]
    retries: Dict[str, int]                # per-agent retry counters
    node_trace: List[NodeLogEntry]
    memory: Dict[str, Any]                 # snapshot of persisted ConversationMemory


def new_state(
    session_id: str,
    user_query: str,
    history: Optional[List[Dict[str, str]]] = None,
    page_context: Optional[Any] = None,
    **overrides: Any,
) -> ConversationState:
    """Build an initial state dict with safe defaults for every field."""
    state: ConversationState = {
        "session_id": session_id,
        "user_query": user_query,
        "history": history or [],
        "page_context": page_context,
        "db": None,
        "intent_override": None,
        "target_metric": None,
        "target_value": None,
        "higher_is_better": False,
        "trace_metric": None,
        "from_intervention": None,
        "to_outcome": None,
        "target_outcome": None,
        "intent": "unknown",
        "entities": {},
        "required_agents": [],
        "execution_plan": [],
        "plan_index": 0,
        "kpis": [],
        "business_metrics": [],
        "goal": {},
        "calculations": {},
        "retrieved_documents": [],
        "retrieved_chunks": [],
        "formula_trace": {},
        "advisor_output": {},
        "whatif_output": {},
        "tool_outputs": {},
        "final_answer": "",
        "suggested_followups": [],
        "evidence": [],
        "ungrounded_numbers": [],
        "confidence": 0.0,
        "errors": [],
        "missing_information": [],
        "retries": {},
        "node_trace": [],
        "memory": {},
    }
    state.update(overrides)
    return state
