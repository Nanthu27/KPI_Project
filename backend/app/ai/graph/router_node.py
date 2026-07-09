"""
Router Node
-----------
Understands the request: intent, business domain entities, and which
specialist agents are *needed* (RAG? calculations? advisor? tracing?).
The Router NEVER generates an answer — it only classifies.

Reuses the SAME deterministic pre-checks the legacy single-agent cascade
uses (`_is_whatif_intent`, `_is_goal_seeking_intent`, `_is_advisor_apply_intent`)
before falling back to plain `INTENT_PATTERNS` keyword scoring, so intent
detection behaves identically to before.

This used to call ONLY `_score_intents` (plain regex table), which has no
WHATIF category at all — so a hypothetical forward-simulation question
("if I set X to 55, what is Y?") could never be routed to a whatif agent
in this graph; it silently scored as KNOWLEDGE (via the "what is" keyword)
every time. That's fixed by running the same pre-checks the legacy path
already relies on.
"""
import time
from typing import Any, Dict

from .state import ConversationState
from ..cascade.agent import (
    INTENT_PATTERNS,
    _real_metric_names_from_context,
    _is_whatif_intent,
    _is_goal_seeking_intent,
    _is_goal_target_intent,
    _is_advisor_apply_intent,
)
from ..cascade.schemas import IntentType

# Map each detectable intent to the LangGraph agent that owns it.
_INTENT_TO_AGENT = {
    IntentType.INSIGHT: "insight",
    IntentType.GOAL: "goal",
    IntentType.KNOWLEDGE: "knowledge",
    IntentType.TRACE: "trace",
    IntentType.ADVISOR: "advisor",
    IntentType.WHATIF: "whatif",
}


def _score_intents(message: str) -> Dict[IntentType, int]:
    msg_lower = message.lower()
    scores = {intent: 0 for intent in INTENT_PATTERNS}
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            import re
            if re.search(pattern, msg_lower):
                scores[intent] += 1
    return scores


def router_node(state: ConversationState) -> Dict[str, Any]:
    started = time.time()
    message = state.get("user_query", "")

    override = state.get("intent_override")
    scores = _score_intents(message)
    total_hits = sum(scores.values())

    if override and override != IntentType.UNKNOWN.value:
        primary = IntentType(override)
    elif _is_advisor_apply_intent(message):
        # Deterministic UI-action phrases ("apply the top recommendation")
        # always mean Advisor, regardless of what the keyword table scores.
        primary = IntentType.ADVISOR
    elif _is_whatif_intent(message):
        # Must be checked before goal-seeking: both can mention numbers and
        # "what", but WHATIF states VALUES and asks for a RESULT, while
        # GOAL states a RESULT and asks which values to change.
        primary = IntentType.WHATIF
    elif _is_goal_seeking_intent(message):
        primary = IntentType.GOAL
    elif _is_goal_target_intent(message):
        primary = IntentType.GOAL
    else:
        primary = max(scores, key=lambda k: scores[k])
        if scores[primary] == 0:
            primary = IntentType.KNOWLEDGE

    # Any intent with at least one keyword hit is treated as a *signal* that
    # its agent is relevant too — this is what turns a single question into
    # a multi-agent plan (e.g. "why did DSO change and how do I fix it?"
    # scores both INSIGHT and GOAL > 0).
    required_agents = [
        _INTENT_TO_AGENT[intent]
        for intent, score in scores.items()
        if score > 0 and intent in _INTENT_TO_AGENT
    ]
    primary_agent = _INTENT_TO_AGENT.get(primary, "knowledge")
    if primary_agent not in required_agents:
        required_agents.append(primary_agent)

    entities = _real_metric_names_from_context(state.get("page_context"))
    confidence = round(scores[primary] / total_hits, 2) if total_hits else 0.5

    finished = time.time()
    log_entry = {
        "node": "router",
        "started_at": started,
        "finished_at": finished,
        "duration_ms": round((finished - started) * 1000, 2),
        "status": "ok",
        "detail": f"intent={primary.value} agents={required_agents}",
    }
    node_trace = list(state.get("node_trace") or [])
    node_trace.append(log_entry)

    return {
        "intent": primary.value,
        "required_agents": required_agents,
        "entities": entities,
        "confidence": confidence,
        "node_trace": node_trace,
    }

