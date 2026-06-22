"""
Goal-Seeking Agent (spec section 2). User states a target metric value;
ReverseSolver (deterministic) computes the recommended intervention
levels; this agent only narrates that solved plan.

FR-2.1: intent extraction must map natural-language metric names to the
canonical metric schema using a maintained synonym table, NOT rely on
the LLM alone for ID resolution in production. The synonym table below
is intentionally simple/extendable rather than ML-based, per that
requirement.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from ..models import L1Metric, BusinessOutcome
from ..services.calculation_engine import calculation_engine, FORMULA_PENDING_CONFIRMATION, FORMULA_DISCLOSURE_TEXT
from ..schemas.agent_schemas import GoalSeekingRequest, GoalSeekingResponse, GoalSeekingPlanItem
from .anthropic_client import call_anthropic_json, AnthropicNotConfiguredError
from .hallucination_guard import validate_no_hallucinated_numbers

# FR-2.1: synonym lookup table, maintained in code (not LLM-resolved).
# Extend this whenever a new metric is added to the KPI hierarchy.
METRIC_SYNONYMS = {
    "dso": "Days Sales Outstanding",
    "days sales outstanding": "Days Sales Outstanding",
    "collections cycle": "Days Sales Outstanding",
    "collection cycle": "Days Sales Outstanding",
    "bad debt": "Bad Debt Ratio",
    "bad debt ratio": "Bad Debt Ratio",
    "collection efficiency": "Collection Efficiency",
    "cash conversion cycle": "Cash Conversion Cycle",
    "ccc": "Cash Conversion Cycle",
    "working capital": "Working Capital Efficiency",
    "working capital efficiency": "Working Capital Efficiency",
}

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _resolve_canonical_metric_name(raw_text: str, db: Session) -> Optional[str]:
    lower = raw_text.lower()
    for synonym, canonical in METRIC_SYNONYMS.items():
        if synonym in lower:
            return canonical
    # Fall back to direct substring match against actual metric names in the DB,
    # so newly-created metrics work even before someone adds a synonym entry.
    all_names = [m.name for m in db.query(L1Metric).all()] + [m.name for m in db.query(BusinessOutcome).all()]
    for name in all_names:
        if name.lower() in lower:
            return name
    return None


def _extract_target_value(raw_text: str) -> Optional[float]:
    matches = _NUMBER_RE.findall(raw_text)
    if not matches:
        return None
    return float(matches[0])


def _parse_goal(user_question: str, db: Session) -> Tuple[Optional[str], Optional[float]]:
    """Lightweight prior step (FR-2.1) — resolves metric name + target value before calling the solver."""
    metric_name = _resolve_canonical_metric_name(user_question, db)
    target_value = _extract_target_value(user_question)
    return metric_name, target_value


SYSTEM_PROMPT = """You are the Goal-Seeking Agent. The user states a target value for a metric. A deterministic
solver (NOT you) has already computed the recommended intervention levels to reach that
target. Your job is to PRESENT that solved plan clearly, not to invent or adjust it.

STRICT RULES:
1. Never alter the numbers in solver_result. Present them exactly as given.
2. Always state: the goal as understood, the recommended plan (each intervention + level),
   the projected outcome, and the confidence score.
3. If solver_result.feasible is false, say so plainly and explain (using only data given)
   what the maximum achievable value is -- do not pretend a solution exists.
4. Confidence score interpretation for the user:
   - 85-100%: "high confidence -- this combination is well within tested ranges"
   - 60-84%: "moderate confidence -- this extrapolates beyond your typical intervention range"
   - below 60%: "low confidence -- treat this as directional, validate before committing budget"
   Always state the band, not just the raw number. Also explicitly mention that the
   confidence methodology is PROVISIONAL pending Finance/Analytics sign-off if
   solver_result.confidence_basis says so.
5. If parsed_goal seems ambiguous or low-confidence (e.g., metric name not clearly matched),
   ask ONE clarifying question before presenting a plan. Do not guess silently.
6. End every response by inviting the user to either "Apply this plan to sliders" or ask
   for an alternative (e.g. lower-cost option) -- but do not generate the alternative
   yourself; flag it as a new solver request.
7. Tone: advisory, confident, but explicit that this is a recommendation requiring human
   sign-off, not an automatic action.

OUTPUT FORMAT: Respond with ONLY a valid JSON object, no markdown fences, no text before
or after:
{
  "response_text": "...",
  "plan": [{"intervention": "...", "recommended_value": 0}],
  "projected_outcome": {},
  "confidence_score": 0.0,
  "confidence_band": "high|moderate|low",
  "action_available": "apply_to_sliders",
  "feasible": true,
  "clarifying_question": null
}
"""


def _confidence_band(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.60:
        return "moderate"
    return "low"


def handle_goal_seeking(db: Session, request: GoalSeekingRequest) -> GoalSeekingResponse:
    metric_name, target_value = _parse_goal(request.user_question, db)

    if metric_name is None or target_value is None:
        return GoalSeekingResponse(
            response_text=(
                "I couldn't confidently identify which metric and target value you mean. "
                "Could you specify it like: \"I want DSO to reach 30 days\"?"
            ),
            plan=[],
            feasible=False,
            clarifying_question="Which metric and target value would you like to solve for?",
            action_available=None,
        )

    solver_result = calculation_engine.reverse_solve(
        db, metric_name, target_value, request.locked_interventions
    )

    payload = {
        "parsed_goal": {
            "target_metric": metric_name,
            "target_value": target_value,
        },
        "solver_result": solver_result.model_dump(),
        "user_question": request.user_question,
    }

    try:
        raw = call_anthropic_json(SYSTEM_PROMPT, payload)
    except AnthropicNotConfiguredError as exc:
        return GoalSeekingResponse(
            response_text=f"[Goal-Seeking Agent unavailable: {exc}]",
            plan=[GoalSeekingPlanItem(intervention=r["name"], recommended_value=r["recommended"]) for r in solver_result.recommended_interventions],
            projected_outcome=solver_result.projected_outcome,
            confidence_score=solver_result.confidence_score,
            confidence_band=_confidence_band(solver_result.confidence_score),
            feasible=solver_result.feasible,
        )

    response_text = raw.get("response_text", "")
    violations = validate_no_hallucinated_numbers(response_text, payload)
    if violations:
        response_text += f"\n\n[Note: hallucination guard flagged unverified numbers: {violations}]"
    if FORMULA_PENDING_CONFIRMATION:
        response_text += f"\n\n{FORMULA_DISCLOSURE_TEXT}"

    plan = [
        GoalSeekingPlanItem(intervention=item.get("intervention", ""), recommended_value=item.get("recommended_value", 0))
        for item in raw.get("plan", [])
    ] or [
        GoalSeekingPlanItem(intervention=r["name"], recommended_value=r["recommended"])
        for r in solver_result.recommended_interventions
    ]

    return GoalSeekingResponse(
        response_text=response_text,
        plan=plan,
        projected_outcome=raw.get("projected_outcome") or solver_result.projected_outcome,
        confidence_score=raw.get("confidence_score", solver_result.confidence_score),
        confidence_band=raw.get("confidence_band") or _confidence_band(solver_result.confidence_score),
        action_available=raw.get("action_available", "apply_to_sliders"),
        feasible=raw.get("feasible", solver_result.feasible),
        clarifying_question=raw.get("clarifying_question"),
    )
