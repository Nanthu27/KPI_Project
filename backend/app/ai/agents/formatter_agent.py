"""
Response Formatter Agent
--------------------------
Collects whatever agents actually ran (per the Planner's execution_plan),
builds one grounded prompt out of their structured tool_outputs (reusing
the existing prompt builders — no new prompt-formatting logic invented),
and makes exactly ONE LLM call to produce the final, explainable answer.

Owns: final_answer, suggested_followups, confidence (final rollup)
"""
import logging
from typing import Any, Dict, List

from ..graph.state import ConversationState
from ..cascade.prompts import (
    SYSTEM_PROMPT,
    format_insight_prompt,
    format_goal_prompt,
    format_whatif_prompt,
    format_knowledge_prompt,
    format_trace_prompt,
    format_advisor_prompt,
    format_page_context,
)
from ..cascade.agent import _call_llm, _generate_followups   # existing helpers, reused
from ..cascade.schemas import IntentType
from ..evidence.grounding import (
    collect_allowed_numbers,
    find_ungrounded_numbers,
    compute_confidence,
    evidence_list,
    evidence_footer,
)
from .base import node

logger = logging.getLogger(__name__)

# Fixed synthesis order, matching the Planner's canonical pipeline.
_FORMATTERS = {
    "insight": format_insight_prompt,
    "goal": format_goal_prompt,
    "whatif": format_whatif_prompt,
    "knowledge": format_knowledge_prompt,
    "trace": format_trace_prompt,
    "advisor": format_advisor_prompt,
}
_ORDER = ["insight", "goal", "whatif", "knowledge", "trace", "advisor"]

_MULTI_AGENT_PREAMBLE = (
    "## Multi-Agent Synthesis\n"
    "Several specialist agents already analyzed this request. Combine their "
    "findings below into ONE coherent, non-repetitive answer. Do not restate "
    "each section separately — synthesize.\n\n"
)


def _build_prompt(state: ConversationState) -> str:
    tool_outputs: Dict[str, Any] = state.get("tool_outputs") or {}
    ran = [name for name in _ORDER if name in tool_outputs]

    blocks = [format_page_context(state.get("page_context"))]
    if len(ran) > 1:
        blocks.append(_MULTI_AGENT_PREAMBLE)

    for name in ran:
        formatter = _FORMATTERS[name]
        blocks.append(formatter(tool_outputs[name], state.get("user_query", "")))

    if not ran:
        # Nothing executed (router misfire) — fall back to a plain knowledge
        # framing so the user still gets a grounded, non-hallucinated answer.
        blocks.append(format_knowledge_prompt({"context": "", "sources": []},
                                                state.get("user_query", "")))
    return "\n\n".join(b for b in blocks if b)


def _agent_sources(name: str, tool_data: Dict[str, Any]) -> List[str]:
    """Same deterministic source-attribution rules as the legacy
    single-agent path's `_sources_used` (cascade/agent.py), but keyed by
    agent name instead of intent so it works when several agents ran in
    the same turn. Only reports a source if the tool actually returned
    usable data for it — never based on what the LLM claims."""
    if not tool_data or (isinstance(tool_data, dict) and tool_data.get("error")):
        return []
    if name == "insight":
        sources = ["live_simulation"]
        if tool_data.get("verified_chains"):
            sources.append("formula_trace")
        return sources
    if name == "goal":
        return ["live_simulation", "goal_engine"]
    if name == "whatif":
        return [] if tool_data.get("needs_clarification") else ["live_simulation", "calculation_engine"]
    if name == "trace":
        return ["formula_trace", "workbook"]
    if name == "advisor":
        return ["live_simulation", "decision_engine"]
    if name == "knowledge":
        return [] if tool_data.get("not_found") else ["knowledge_base"]
    return []


def _finalize_grounding(state: ConversationState, reply: str) -> Dict[str, Any]:
    """Multi-agent equivalent of cascade/agent.py::_finalize_reply.

    Runs the SAME deterministic, no-LLM grounding check the legacy
    single-agent path already runs — but over the UNION of every agent's
    tool output that actually executed this turn, since the graph can run
    several agents (e.g. insight + advisor) before one final answer is
    written. This was flagged as an open gap in AGENT_TRAINING_NOTES.md
    ("backport the grounding layer into the graph agents") and is now
    closed: the multi-agent path can no longer produce an ungrounded
    number without it being flagged, exactly like the single-agent path.
    """
    tool_outputs: Dict[str, Any] = state.get("tool_outputs") or {}

    sources: List[str] = []
    allowed_numbers = set()
    for name in _ORDER:
        data = tool_outputs.get(name)
        if not data:
            continue
        for s in _agent_sources(name, data):
            if s not in sources:
                sources.append(s)
        allowed_numbers |= collect_allowed_numbers(data)

    ungrounded = find_ungrounded_numbers(reply, allowed_numbers) if allowed_numbers else []

    has_error = any(
        isinstance(tool_outputs.get(n), dict) and tool_outputs[n].get("error")
        for n in _ORDER
    ) or bool(state.get("errors"))

    confidence = compute_confidence(
        has_error=has_error,
        ungrounded_count=len(ungrounded),
        sources_used=sources,
    )
    reply_with_footer = reply + evidence_footer(sources, confidence, ungrounded)

    return {
        "final_answer": reply_with_footer,
        "evidence": evidence_list(sources),
        "ungrounded_numbers": ungrounded,
        "confidence": confidence,
    }


def _pick_followup_source(state: ConversationState):
    """Use the most 'downstream' agent's tool_data for follow-up suggestions,
    matching the priority a human analyst would read results in."""
    tool_outputs: Dict[str, Any] = state.get("tool_outputs") or {}
    for name in ["advisor", "goal", "whatif", "trace", "knowledge", "insight"]:
        if name in tool_outputs:
            return name, tool_outputs[name]
    return "knowledge", {}


@node("formatter")
def formatter_agent(state: ConversationState) -> Dict[str, Any]:
    user_prompt = _build_prompt(state)

    history = state.get("history") or []
    # `_call_llm` expects objects with .role/.content; plain dicts work too
    # since it only reads those two attributes-as-keys via ChatMessage model.
    class _H:
        def __init__(self, role, content):
            self.role, self.content = role, content
    hist_objs = [_H(h.get("role", "user"), h.get("content", "")) for h in history[-6:]]

    try:
        reply = _call_llm(SYSTEM_PROMPT, user_prompt, hist_objs)
    except Exception as e:  # noqa: BLE001
        logger.warning("Formatter LLM call failed: %s", e)
        raise  # let the @node retry wrapper handle bounded retries

    followup_name, followup_data = _pick_followup_source(state)
    intent_str = state.get("intent", "unknown")
    try:
        intent_enum = IntentType(intent_str)
    except ValueError:
        intent_enum = IntentType.UNKNOWN

    followups: List[str] = _generate_followups(intent_enum, followup_data, state.get("page_context"))

    tool_outputs = dict(state.get("tool_outputs") or {})
    tool_outputs["formatter"] = {"tool": "formatter", "prompt_chars": len(user_prompt)}

    grounded = _finalize_grounding(state, reply)

    return {
        "tool_outputs": tool_outputs,
        "suggested_followups": followups,
        **grounded,  # final_answer (with evidence footer), evidence, ungrounded_numbers, confidence
    }
