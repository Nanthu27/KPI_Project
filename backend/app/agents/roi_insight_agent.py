"""
ROI Insight Agent (spec section 1). Explains WHY a KPI changed, using
ONLY the pre-computed SimulationResult from CalculationEngine. Never
calculates anything itself.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..services.calculation_engine import calculation_engine, FORMULA_PENDING_CONFIRMATION, FORMULA_DISCLOSURE_TEXT
from ..schemas.agent_schemas import ROIInsightRequest, ROIInsightResponse
from .anthropic_client import call_anthropic_json, AnthropicNotConfiguredError
from .hallucination_guard import validate_no_hallucinated_numbers

SYSTEM_PROMPT = """You are the ROI Insight Agent inside an enterprise Finance & Accounting KPI simulation
platform. You explain WHY metrics changed after a user adjusts intervention sliders.

STRICT RULES:
1. You will be given pre-computed numbers in the input JSON. NEVER calculate, estimate,
   or invent any number yourself. Only reference numbers present in the input.
2. If the user asks something requiring a number not present in the input, say you don't
   have that figure and suggest they check the Excel Intelligence Agent for calculation
   detail, or rerun the simulation.
3. Always state the causal chain in this order: Intervention -> L2 metric -> L1 metric ->
   Business Outcome -> Revenue impact. Skip levels only if the input data skips them.
4. Keep responses to 2-4 sentences for the auto-summary. For follow-up questions, you may
   go longer but stay under 120 words.
5. Use plain business language. Never show raw formulas or cell references -- that is the
   Excel Intelligence Agent's job. If the user wants formula-level detail, tell them to
   switch to the Excel tab.
6. Never recommend NEW intervention values or targets -- that is the Goal-Seeking Agent's
   job. You only explain what already happened.
7. If multiple interventions contributed to one metric, name all of them and their
   relative contribution if it's in the input data.
8. Tone: confident, concise, executive-readable. No hedging language like "it seems" or
   "possibly" -- these numbers are deterministic, not probabilistic.

OUTPUT FORMAT: Respond with ONLY a valid JSON object, no markdown fences, no text before
or after:
{
  "response_text": "...",
  "cited_metrics": ["metric name", ...],
  "suggested_followups": ["...", "..."]
}
"""


def handle_roi_insight(db: Session, request: ROIInsightRequest) -> ROIInsightResponse:
    simulation_result = calculation_engine.run_full_simulation(
        db, request.vertical_horizontal, request.lob
    )

    payload = simulation_result.model_dump()
    payload["user_question"] = request.user_question

    no_change = all(abs(c.delta_pct) < 0.01 for c in simulation_result.l1_changes) and \
        all(abs(c.delta_pct) < 0.01 for c in simulation_result.business_outcome_changes)
    if no_change:
        payload["_note_to_agent"] = (
            "All interventions are at their default/baseline values right now -- "
            "explain that this is the baseline state, not an error, per FR-1.2."
        )

    try:
        raw = call_anthropic_json(SYSTEM_PROMPT, payload)
    except AnthropicNotConfiguredError as exc:
        return ROIInsightResponse(
            response_text=f"[ROI Insight Agent unavailable: {exc}]",
            cited_metrics=[],
            suggested_followups=[],
        )

    response_text = raw.get("response_text", "")
    cited_metrics = raw.get("cited_metrics", [])
    suggested_followups = raw.get("suggested_followups", [])

    # Hallucination guard (spec section 6.2) — also enforce the cited_metrics whitelist (FR-1.3).
    violations = validate_no_hallucinated_numbers(response_text, payload)
    known_metric_names = {c.name for c in simulation_result.l1_changes} | \
        {c.name for c in simulation_result.l2_changes} | \
        {c.name for c in simulation_result.business_outcome_changes} | \
        {c.name for c in simulation_result.interventions}
    unknown_cited = [m for m in cited_metrics if m not in known_metric_names]

    if violations or unknown_cited:
        response_text += (
            "\n\n[Note: this response was flagged by the hallucination guard for review - "
            f"unverified numbers: {violations}, unverified metric citations: {unknown_cited}]"
        )

    if FORMULA_PENDING_CONFIRMATION:
        response_text += f"\n\n{FORMULA_DISCLOSURE_TEXT}"

    return ROIInsightResponse(
        response_text=response_text,
        cited_metrics=cited_metrics,
        suggested_followups=suggested_followups,
    )
