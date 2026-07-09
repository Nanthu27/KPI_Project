"""
Trace Formula Agent
--------------------
Thin LangGraph wrapper around the existing `excel_trace_tool`.
Reuses `_extract_trace_params` from the legacy cascade agent for
metric-name resolution against live page data / DB.

Owns: formula_trace, tool_outputs["trace"]
"""
from typing import Any, Dict

from ..graph.state import ConversationState
from ..tools.kpi_tools import excel_trace_tool                  # existing tool
from ..cascade.agent import _extract_trace_params                # existing helper, reused
from ..cascade.schemas import CascadeChatRequest
from .base import node


@node("trace")
def trace_agent(state: ConversationState) -> Dict[str, Any]:
    db = state["db"]

    pseudo_request = CascadeChatRequest(
        message=state.get("user_query", ""),
        trace_metric=state.get("trace_metric"),
        from_intervention=state.get("from_intervention"),
        to_outcome=state.get("to_outcome"),
        page_context=state.get("page_context"),
    )
    metric, from_iv, to_bo = _extract_trace_params(state.get("user_query", ""), pseudo_request)

    tool_data = excel_trace_tool(db, metric, from_iv, to_bo)

    tool_outputs = dict(state.get("tool_outputs") or {})
    tool_outputs["trace"] = tool_data

    return {
        "tool_outputs": tool_outputs,
        "formula_trace": tool_data,
    }
