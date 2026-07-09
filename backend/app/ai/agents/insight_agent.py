"""
Insight Agent
-------------
Thin LangGraph wrapper around the existing `insight_tool`.
Owns: kpis, business_metrics, tool_outputs["insight"]
"""
from typing import Any, Dict

from ..graph.state import ConversationState
from ..tools.kpi_tools import insight_tool  # existing tool — reused, not rewritten
from .base import node


@node("insight")
def insight_agent(state: ConversationState) -> Dict[str, Any]:
    db = state["db"]  # SQLAlchemy session, injected by the graph runner
    tool_data = insight_tool(db, state.get("user_query", ""))

    tool_outputs = dict(state.get("tool_outputs") or {})
    tool_outputs["insight"] = tool_data

    kpis = (
        tool_data.get("changed_l1_metrics", [])
        + tool_data.get("changed_l2_metrics", [])
    )
    business_metrics = tool_data.get("changed_business_outcomes", [])

    return {
        "tool_outputs": tool_outputs,
        "kpis": kpis,
        "business_metrics": business_metrics,
        "entities": {
            **(state.get("entities") or {}),
            "active_interventions": tool_data.get("active_interventions", []),
        },
    }
