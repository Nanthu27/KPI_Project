"""
Graph Builder
-------------
Assembles the full LangGraph StateGraph:

    START -> Router -> Planner -> [Insight] -> [Goal] -> [What-If]
             -> [Knowledge] -> [Trace] -> [Advisor] -> Formatter -> END

Agents in [] are conditionally skipped when not in `execution_plan`
(see edges.py). The graph is compiled once at import time and reused
for every request — LangGraph graphs are stateless/thread-safe, all
per-request data lives in the state dict passed to `.invoke()`.
"""
import logging
from typing import Any, AsyncGenerator, Dict, Optional

from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session

from .state import ConversationState, new_state
from .router_node import router_node
from .planner_node import planner_node
from .edges import route_from_planner, AGENT_ROUTERS, PATH_MAP
from ..agents.insight_agent import insight_agent
from ..agents.goal_agent import goal_agent
from ..agents.whatif_agent import whatif_agent
from ..agents.knowledge_agent import knowledge_agent
from ..agents.trace_agent import trace_agent
from ..agents.advisor_agent import advisor_agent
from ..agents.formatter_agent import formatter_agent
from ..memory.memory import ConversationMemory
from ..cascade.schemas import CascadeChatRequest
# Reused, not reimplemented: the same live-page-state sync the legacy
# single-agent path uses (see cascade/agent.py::_synced_to_live_page_state
# for the full rationale). Without this, every graph agent
# (insight/goal/trace/advisor/whatif) reads the DB's last-SAVED
# intervention percentages instead of what's actually on the user's
# screen, reproducing the "Active Interventions: None" vs "at 11% each"
# contradiction the legacy path already fixed -- just one layer deeper,
# since here it would show up across several agents' outputs at once.
from ..cascade.agent import _synced_to_live_page_state, _get_scope

logger = logging.getLogger("cascade.graph")


def _build_graph():
    graph = StateGraph(ConversationState)

    graph.add_node("router", router_node)
    graph.add_node("planner", planner_node)
    graph.add_node("insight", insight_agent)
    graph.add_node("goal", goal_agent)
    graph.add_node("whatif", whatif_agent)
    graph.add_node("knowledge", knowledge_agent)
    graph.add_node("trace", trace_agent)
    graph.add_node("advisor", advisor_agent)
    graph.add_node("formatter", formatter_agent)

    graph.add_edge(START, "router")
    graph.add_edge("router", "planner")

    # Planner fans out to whichever agent is first in the execution plan.
    graph.add_conditional_edges("planner", route_from_planner, PATH_MAP)

    # Each agent advances to the next planned agent, or the formatter.
    for name in ["insight", "goal", "whatif", "knowledge", "trace", "advisor"]:
        graph.add_conditional_edges(name, AGENT_ROUTERS[name], PATH_MAP)

    graph.add_edge("formatter", END)

    return graph.compile()


_COMPILED_GRAPH = _build_graph()


def _inject_db(state: ConversationState, db: Session) -> ConversationState:
    """Attach the SQLAlchemy session as a private, non-serialized field.
    Agents pull it out via state["db"] rather than a global/singleton,
    keeping the graph request-scoped and test-friendly."""
    state = dict(state)
    state["db"] = db
    return state  # type: ignore[return-value]


def _build_initial_state(db: Session, request: CascadeChatRequest, session_id: str) -> ConversationState:
    mem = ConversationMemory.get(session_id)
    history = [{"role": h.role, "content": h.content} for h in request.history] or mem.history

    state = new_state(
        session_id=session_id,
        user_query=request.message,
        history=history,
        page_context=request.page_context,
        intent_override=(request.intent_override.value
                         if request.intent_override else None),
        target_metric=request.target_metric,
        target_value=request.target_value,
        higher_is_better=request.higher_is_better or False,
        trace_metric=request.trace_metric,
        from_intervention=request.from_intervention,
        to_outcome=request.to_outcome,
        target_outcome=request.target_outcome,
        memory=mem.as_dict(),
    )
    return _inject_db(state, db)


def run_graph_cascade(db: Session, request: CascadeChatRequest, session_id: str) -> Dict[str, Any]:
    """Synchronous entry point — runs the full multi-agent graph and
    returns a structured, explainable result."""
    state = _build_initial_state(db, request, session_id)
    vertical, lob = _get_scope(request)
    with _synced_to_live_page_state(db, request, vertical, lob):
        result = _COMPILED_GRAPH.invoke(state)

    ConversationMemory.append_turn(session_id, "user", request.message)
    ConversationMemory.append_turn(session_id, "assistant", result.get("final_answer", ""))
    if result.get("business_metrics"):
        ConversationMemory.update(session_id, last_kpis=result.get("business_metrics"))

    return {
        "reply": result.get("final_answer", ""),
        "intent": result.get("intent", "unknown"),
        "required_agents": result.get("required_agents", []),
        "execution_plan": result.get("execution_plan", []),
        "tool_outputs": result.get("tool_outputs", {}),
        "evidence": result.get("evidence", []),
        "ungrounded": result.get("ungrounded_numbers", []),
        "confidence": result.get("confidence", 0.0),
        "errors": result.get("errors", []),
        "missing_information": result.get("missing_information", []),
        "node_trace": result.get("node_trace", []),
        "suggested_followups": result.get("suggested_followups", []),
    }


async def stream_graph_cascade(
    db: Session, request: CascadeChatRequest, session_id: str
) -> AsyncGenerator[str, None]:
    """Streaming entry point (SSE). LangGraph nodes here are synchronous
    tool calls (fast DB/RAG reads), so we stream graph PROGRESS events as
    each node completes, then stream the final answer as one chunk — this
    keeps the UI responsive without needing token-level streaming through
    every intermediate agent."""
    import json

    state = _build_initial_state(db, request, session_id)
    vertical, lob = _get_scope(request)
    seen_nodes = 0
    final_result: Optional[Dict[str, Any]] = None

    with _synced_to_live_page_state(db, request, vertical, lob):
        for event in _COMPILED_GRAPH.stream(state, stream_mode="values"):
            trace = event.get("node_trace", [])
            while seen_nodes < len(trace):
                entry = trace[seen_nodes]
                yield f"data: {json.dumps({'progress': entry})}\n\n"
                seen_nodes += 1
            final_result = event

    final_result = final_result or {}
    meta = {
        "intent": final_result.get("intent", "unknown"),
        "execution_plan": final_result.get("execution_plan", []),
        "followups": final_result.get("suggested_followups", []),
        "evidence": final_result.get("evidence", []),
        "ungrounded": final_result.get("ungrounded_numbers", []),
        "confidence": final_result.get("confidence", 0.0),
    }
    yield f"data: {json.dumps(meta)}\n\n"
    yield f"data: {json.dumps({'chunk': final_result.get('final_answer', '')})}\n\n"

    ConversationMemory.append_turn(session_id, "user", request.message)
    ConversationMemory.append_turn(session_id, "assistant", final_result.get("final_answer", ""))

    yield "data: [DONE]\n\n"
