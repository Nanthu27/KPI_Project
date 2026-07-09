"""
What-If Agent
-------------
Thin LangGraph wrapper around the existing `whatif_tool` (hypothetical
forward simulation). Reuses `_resolve_whatif_overrides` from the legacy
cascade agent so intervention-name resolution logic is never duplicated.

Handles: "If I set TP Gamification to 55, Interaction Analytics to 65, and
QA Automation to 35, what is Revenue Growth?" — states specific values,
asks for a result. This is the counterpart to goal_agent (states a
result, asks which values reach it).

Before this file existed, the graph had no way to reach this behavior at
all: router_node only scored the legacy INTENT_PATTERNS keyword table,
which has no WHATIF category, so a question like this always fell through
to the Knowledge agent and (correctly, but unhelpfully) reported no
definition found for whatever abbreviation appeared in it.

Owns: whatif_output, tool_outputs["whatif"]
"""
from typing import Any, Dict

from ..graph.state import ConversationState
from ..tools.kpi_tools import whatif_tool                       # existing tool
from ..cascade.agent import _resolve_whatif_overrides            # existing helper, reused
from ..cascade.schemas import CascadeChatRequest
from .base import node


@node("whatif")
def whatif_agent(state: ConversationState) -> Dict[str, Any]:
    db = state["db"]

    # Reuse the exact same request-shaped object the legacy single-agent
    # path used, so name resolution (including the "first 3 options"
    # back-reference to the assistant's own prior message) behaves
    # identically regardless of which path handled the turn.
    pseudo_request = CascadeChatRequest(
        message=state.get("user_query", ""),
        page_context=state.get("page_context"),
        history=[
            {"role": h.get("role", "user"), "content": h.get("content", "")}
            for h in (state.get("history") or [])
        ],
    )

    overrides, unresolved_count = _resolve_whatif_overrides(state.get("user_query", ""), pseudo_request)

    if not overrides:
        tool_data = {
            "tool": "whatif",
            "needs_clarification": True,
            "unresolved_count": unresolved_count,
        }
    else:
        tool_data = whatif_tool(db, overrides, unresolved_count=unresolved_count)

    tool_outputs = dict(state.get("tool_outputs") or {})
    tool_outputs["whatif"] = tool_data

    return {
        "tool_outputs": tool_outputs,
        "whatif_output": {
            "applied_overrides": tool_data.get("applied_overrides", {}),
            "business_outcomes": tool_data.get("business_outcomes", []),
        },
    }
