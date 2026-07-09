"""
Conditional Edges
------------------
Implements the "Need Goal? / Need RAG? / Need Trace?" branching from the
spec generically: every agent node routes to the NEXT agent named in
`execution_plan`, skipping anything the Planner decided wasn't needed.
When the plan is exhausted, everyone routes to the Formatter.
"""
from typing import Callable

from .state import ConversationState
from .planner_node import CANONICAL_ORDER


def route_from_planner(state: ConversationState) -> str:
    plan = state.get("execution_plan") or []
    return plan[0] if plan else "formatter"


def make_router(current_node: str) -> Callable[[ConversationState], str]:
    """Build a conditional-edge function for `current_node` that advances
    to the next agent in the execution plan, or to 'formatter' if done."""

    def _route(state: ConversationState) -> str:
        plan = state.get("execution_plan") or []
        if current_node not in plan:
            return "formatter"
        idx = plan.index(current_node)
        nxt = idx + 1
        return plan[nxt] if nxt < len(plan) else "formatter"

    _route.__name__ = f"route_after_{current_node}"
    return _route


# Pre-built routers for every agent, keyed by node name — used by builder.py
AGENT_ROUTERS = {name: make_router(name) for name in CANONICAL_ORDER}

# Every possible destination a conditional edge could pick, required by
# LangGraph's `add_conditional_edges(..., path_map=...)` for graph validation.
PATH_MAP = {name: name for name in CANONICAL_ORDER}
PATH_MAP["formatter"] = "formatter"
