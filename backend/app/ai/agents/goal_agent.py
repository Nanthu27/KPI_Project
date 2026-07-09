"""
Goal Agent
----------
Thin LangGraph wrapper around the existing `goal_tool` (reverse solver).
Reuses the existing `_extract_goal_params` helper from the legacy cascade
agent so metric/value parsing logic is never duplicated.

Owns: goal, calculations, tool_outputs["goal"]

FIX: _extract_goal_params now returns a 5-tuple
  (metric, value, higher, ambiguous, current_value)
  This agent previously unpacked only 3 values and would throw ValueError.
  Also now passes vertical/lob scope from page_context filters so the
  reverse solver doesn't query across all verticals.
"""
from typing import Any, Dict

from ..graph.state import ConversationState
from ..tools.kpi_tools import goal_tool                       # existing tool
from ..cascade.agent import _extract_goal_params, _business_outcome_context  # existing helpers, reused
from ..cascade.schemas import CascadeChatRequest
from .base import node


@node("goal")
def goal_agent(state: ConversationState) -> Dict[str, Any]:
    db = state["db"]

    page_context = state.get("page_context")

    # Resolve vertical/lob from page_context filters (same logic as _get_scope)
    vertical = state.get("vertical_horizontal")
    lob = state.get("lob")
    if page_context and hasattr(page_context, "filters") and page_context.filters:
        filters = page_context.filters
        vertical = vertical or filters.get("vertical") or filters.get("vertical_horizontal")
        lob = lob or filters.get("lob")

    # Reuse the exact same request-shaped object the legacy single-agent
    # router used, so the target metric/value parsing behaves identically.
    pseudo_request = CascadeChatRequest(
        message=state.get("user_query", ""),
        target_metric=state.get("target_metric"),
        target_value=state.get("target_value"),
        higher_is_better=state.get("higher_is_better") or False,
        page_context=page_context,
        vertical_horizontal=vertical,
        lob=lob,
    )

    # _extract_goal_params returns a 6-tuple:
    #   (metric, value, higher, ambiguous, current_value, allowed_interventions)
    # A previous version of this file unpacked only 5 values here, which
    # raised "too many values to unpack" on every single call — the
    # @node() retry wrapper swallowed that exception silently, so this
    # node always fell through to its retry-exhausted/empty-result path
    # instead of ever actually running the solver or asking a real
    # clarifying question.
    metric, value, higher, ambiguous, current_value, allowed_interventions = _extract_goal_params(
        state.get("user_query", ""), pseudo_request
    )

    tool_outputs = dict(state.get("tool_outputs") or {})

    if ambiguous or value is None:
        # No parseable target — ask instead of guessing. The cascade agent
        # run_cascade/stream_cascade paths do the same check on this flag.
        bo_ctx = _business_outcome_context(db, metric, vertical, lob)
        tool_data = {
            "tool": "goal",
            "needs_clarification": True,
            "metric": metric,
            "current_value": current_value,
            "min_value": bo_ctx["min_value"],
            "max_value": bo_ctx["max_value"],
            "matches": bo_ctx["matches"],
        }
        tool_outputs["goal"] = tool_data
        return {
            "tool_outputs": tool_outputs,
            "goal": {
                "target_metric": metric,
                "target_value": None,
                "higher_is_better": higher,
                "needs_clarification": True,
                "current_value": current_value,
                "solutions": [],
            },
            "calculations": {
                **(state.get("calculations") or {}),
                "goal_solutions": [],
            },
        }

    # Pass vertical/lob so the reverse solver only touches this scope's
    # interventions and metrics — prevents cross-vertical data leaks.
    tool_data = goal_tool(db, metric, value, higher, vertical=vertical, lob=lob)

    tool_outputs["goal"] = tool_data

    return {
        "tool_outputs": tool_outputs,
        "goal": {
            "target_metric": metric,
            "target_value": value,
            "higher_is_better": higher,
            "solutions": tool_data.get("solutions", []),
        },
        "calculations": {
            **(state.get("calculations") or {}),
            "goal_solutions": tool_data.get("solutions", []),
        },
    }
