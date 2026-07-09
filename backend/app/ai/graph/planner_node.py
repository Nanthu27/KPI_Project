"""
Planner Node
------------
Turns the Router's `required_agents` (an unordered set) into
`execution_plan` — an ORDERED list following the canonical reasoning
pipeline:

    Insight -> Goal -> What-If -> Knowledge -> Trace -> Advisor -> Formatter

Only the agents actually required run; everything else is skipped via
conditional edges in `builder.py`. Order is never hardcoded per-query —
it always derives from the fixed canonical order intersected with
whatever the Router flagged as needed, e.g.:

    "What is DSO?"                          -> [knowledge]
    "How is DSO calculated?"                -> [knowledge, trace]
    "How do I get DSO below 30?"            -> [goal]
    "Why did DSO change and how do I fix it?" -> [insight, goal]
    "What's the best ROI strategy for DSO?"  -> [insight, goal, knowledge, advisor]
"""
import time
from typing import Any, Dict

from .state import ConversationState

CANONICAL_ORDER = ["insight", "goal", "whatif", "knowledge", "trace", "advisor"]


def planner_node(state: ConversationState) -> Dict[str, Any]:
    started = time.time()
    required = set(state.get("required_agents") or [])

    execution_plan = [agent for agent in CANONICAL_ORDER if agent in required]
    if not execution_plan:
        execution_plan = ["knowledge"]  # safe default — never run zero agents

    finished = time.time()
    log_entry = {
        "node": "planner",
        "started_at": started,
        "finished_at": finished,
        "duration_ms": round((finished - started) * 1000, 2),
        "status": "ok",
        "detail": f"plan={execution_plan}",
    }
    node_trace = list(state.get("node_trace") or [])
    node_trace.append(log_entry)

    return {
        "execution_plan": execution_plan,
        "plan_index": 0,
        "node_trace": node_trace,
    }
