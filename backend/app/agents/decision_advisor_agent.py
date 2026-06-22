"""
Decision Advisor Agent (spec section 5). Budget optimization narration.
BudgetOptimizer (deterministic) computes the top-3 scenario options;
this agent only narrates the trade-offs. Never invents an ROI/cost/
payback number.

DATA DEPENDENCY DISCLOSURE (spec section 5 + 6.4): cost_per_unit per
intervention is currently a PLACEHOLDER estimate (see
models/models.py::Intervention.cost_per_unit and seed_data.py). Every
response from this agent must disclose that ROI/payback figures are
provisional until Finance supplies real cost data — enforced below by
always appending a disclosure line, not left to the LLM's discretion.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Intervention
from ..services.calculation_engine import calculation_engine, FORMULA_PENDING_CONFIRMATION, FORMULA_DISCLOSURE_TEXT
from ..schemas.agent_schemas import DecisionAdvisorRequest, DecisionAdvisorResponse
from .anthropic_client import call_anthropic_json, AnthropicNotConfiguredError
from .hallucination_guard import validate_no_hallucinated_numbers

SYSTEM_PROMPT = """You are the Decision Advisor Agent. The user gives a budget; a deterministic optimizer
(NOT you) has already computed the top intervention combinations that fit within it,
each with cost/ROI/payback/confidence already calculated. You ONLY narrate and compare
these options -- you never compute a new number.

STRICT RULES:
1. Never alter any cost, ROI%, payback, or confidence value in optimizer_result. Present
   exactly what's given.
2. If optimizer_result.infeasible is true, say plainly that no combination fits the
   stated budget, using optimizer_result.recommendation_basis if given, and suggest the
   user either raise the budget or ask about a single highest-impact intervention instead.
3. Present each option with: what it includes, total cost, ROI%, payback period, and
   confidence. Use a comparison framing (this option vs. that option) rather than just
   listing them.
4. ALWAYS include this disclosure verbatim (do not paraphrase or omit it), appended after
   your main narration: "Cost and ROI figures use placeholder/estimated cost-per-unit
   data pending confirmation from Finance -- treat these comparisons as directional until
   real cost data is loaded."
5. State which option is recommended and WHY, using only optimizer_result's own
   recommendation_basis field -- do not invent your own justification beyond what's given.
6. Tone: advisory, like a financial analyst presenting options to a budget owner. Avoid
   being falsely precise given the cost-data caveat above.

OUTPUT FORMAT: Respond with ONLY a valid JSON object, no markdown fences, no text before
or after:
{
  "response_text": "...",
  "recommended_option": "...",
  "tradeoff_note": "..."
}
"""

COST_DISCLOSURE = (
    "Cost and ROI figures use placeholder/estimated cost-per-unit data pending "
    "confirmation from Finance — treat these comparisons as directional until real "
    "cost data is loaded."
)


def handle_decision_advisor(db: Session, request: DecisionAdvisorRequest) -> DecisionAdvisorResponse:
    any_cost_data = db.query(Intervention).filter(
        Intervention.vertical_horizontal == request.vertical_horizontal,
        Intervention.lob == request.lob,
        Intervention.cost_per_unit > 0,
    ).first()

    if not any_cost_data:
        return DecisionAdvisorResponse(
            response_text=(
                "No cost data is configured for interventions in this LOB yet, so I can't "
                "compute budget-constrained options. " + COST_DISCLOSURE
            ),
            infeasible=True,
            action_available=None,
        )

    optimizer_result = calculation_engine.optimize_under_budget(
        db, request.budget, request.vertical_horizontal, request.lob
    )

    if optimizer_result.infeasible or not optimizer_result.options:
        return DecisionAdvisorResponse(
            response_text=(
                f"No combination of interventions fits within a budget of "
                f"{request.currency} {request.budget:,.0f}. "
                f"{optimizer_result.recommendation_basis or ''} {COST_DISCLOSURE}"
            ),
            all_options=[],
            infeasible=True,
            action_available=None,
        )

    payload = {
        "budget": request.budget,
        "currency": request.currency,
        "optimizer_result": optimizer_result.model_dump(),
        "user_question": request.user_question,
    }

    try:
        raw = call_anthropic_json(SYSTEM_PROMPT, payload)
    except AnthropicNotConfiguredError as exc:
        return DecisionAdvisorResponse(
            response_text=f"[Decision Advisor Agent unavailable: {exc}] {COST_DISCLOSURE}",
            recommended_option=optimizer_result.recommended_option_label,
            all_options=optimizer_result.options,
            tradeoff_note=optimizer_result.recommendation_basis,
        )

    response_text = raw.get("response_text", "")
    if COST_DISCLOSURE not in response_text:
        response_text += f"\n\n{COST_DISCLOSURE}"
    if FORMULA_PENDING_CONFIRMATION:
        response_text += f"\n\n{FORMULA_DISCLOSURE_TEXT}"

    violations = validate_no_hallucinated_numbers(response_text, payload)
    if violations:
        response_text += f"\n\n[Note: hallucination guard flagged unverified numbers: {violations}]"

    return DecisionAdvisorResponse(
        response_text=response_text,
        recommended_option=raw.get("recommended_option", optimizer_result.recommended_option_label),
        all_options=optimizer_result.options,
        tradeoff_note=raw.get("tradeoff_note", optimizer_result.recommendation_basis),
        infeasible=False,
    )
