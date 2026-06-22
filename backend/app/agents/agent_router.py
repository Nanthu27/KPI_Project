"""
Agent Router (spec section 6.1). Rule-based keyword routing for the
single unified /api/agents/chat endpoint — explicitly NOT an LLM call
per the spec ("rule-based is sufficient").

Signal table, copied verbatim from the spec:

| Signal in user question                                    | Route to            |
|--------------------------------------------------------------|----------------------|
| "why did," "what changed," "explain the change"              | ROI Insight          |
| "I want," "target," "reach," "achieve X"                     | Goal-Seeking         |
| "formula," "calculation," "how is X calculated," "which cell"| Excel Intelligence   |
| "what is," "define," "policy," "BRD says"                    | Knowledge Agent      |
| "budget," "$X to spend," "best use of," "which option"       | Decision Advisor     |

Checked in the order below (first match wins) since some phrasings could
plausibly match more than one row (e.g. "what changed the formula" hits
both ROI Insight and Excel Intelligence cues) — formula/calculation
language is checked first since it's the most specific/unambiguous
signal, followed by budget, then goal-seeking, then ROI ("why"), with
Knowledge Agent as the final catch-most-general fallback before the
true default.
"""
import re
from typing import Literal

AgentName = Literal["roi_insight", "goal_seeking", "excel_intelligence", "knowledge", "decision_advisor"]

_EXCEL_PATTERNS = [r"\bformula\b", r"\bcalculation\b", r"how is .* calculated", r"which cell\b", r"\bcell\b"]
_BUDGET_PATTERNS = [r"\bbudget\b", r"\$\s?\d", r"best use of", r"which option\b", r"how (much|many) (should|can) i spend"]
_GOAL_PATTERNS = [r"\bi want\b", r"\btarget\b", r"\breach\b", r"\bachieve\b"]
_ROI_PATTERNS = [r"why did", r"what changed", r"explain the change", r"\bwhy\b.*\bchang"]
_KNOWLEDGE_PATTERNS = [r"\bwhat is\b", r"\bdefine\b", r"\bpolicy\b", r"brd says", r"\bdefinition\b"]


def _matches_any(text: str, patterns) -> bool:
    return any(re.search(p, text) for p in patterns)


def route_question(user_question: str) -> AgentName:
    text = user_question.lower().strip()

    if _matches_any(text, _EXCEL_PATTERNS):
        return "excel_intelligence"
    if _matches_any(text, _BUDGET_PATTERNS):
        return "decision_advisor"
    if _matches_any(text, _GOAL_PATTERNS):
        return "goal_seeking"
    if _matches_any(text, _ROI_PATTERNS):
        return "roi_insight"
    if _matches_any(text, _KNOWLEDGE_PATTERNS):
        return "knowledge"

    # Default fallback: per spec 6.1's framing, Knowledge Agent is the
    # general-purpose "what is this" agent, making it the safest default
    # for ambiguous questions that don't match any specific signal — it
    # will itself say "I couldn't find this" rather than fabricate, which
    # is a safer failure mode than guessing a different agent.
    return "knowledge"
