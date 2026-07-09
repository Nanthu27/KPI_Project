"""
Advisor Agent
-------------
Thin LangGraph wrapper around the existing `decision_advisor_tool`.
Runs LAST among the reasoning agents (per the planner's fixed ordering)
so it can see insight / goal / knowledge / trace outputs already sitting
in shared state, exactly as the master spec requires ("Advisor must
receive Insight, Goal calculations, Retrieved docs, Formula trace...").

Owns: advisor_output, tool_outputs["advisor"]
"""
from typing import Any, Dict

from ..graph.state import ConversationState
from ..tools.kpi_tools import decision_advisor_tool  # existing tool
from .base import node


@node("advisor")
def advisor_agent(state: ConversationState) -> Dict[str, Any]:
    db = state["db"]
    target_outcome = state.get("target_outcome")

    tool_data = decision_advisor_tool(db, target_outcome)

    tool_outputs = dict(state.get("tool_outputs") or {})
    tool_outputs["advisor"] = tool_data

    return {
        "tool_outputs": tool_outputs,
        "advisor_output": {
            **tool_data,
            # Carry forward context the advisor "saw" for explainability.
            "informed_by": {
                "insight": bool(state.get("business_metrics")),
                "goal": bool(state.get("goal")),
                "knowledge": bool(state.get("retrieved_documents")),
                "trace": bool(state.get("formula_trace")),
            },
        },
    }
