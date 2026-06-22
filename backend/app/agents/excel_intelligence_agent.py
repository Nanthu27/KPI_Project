"""
Excel Intelligence Agent (spec section 3). Traces and narrates the EXACT
formula chain behind a metric, using TraceEngine's real sheet/row/formula
data. Never invents a formula or cell reference (FR-3.1, FR-3.4).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..services.calculation_engine import calculation_engine
from ..schemas.agent_schemas import (
    ExcelIntelligenceRequest, ExcelIntelligenceResponse, ExcelTraceStepOut,
)
from .anthropic_client import call_anthropic_json, AnthropicNotConfiguredError
from .hallucination_guard import validate_no_hallucinated_numbers

SYSTEM_PROMPT = """You are the Excel Intelligence Agent. You explain EXACTLY how a number was calculated by
tracing the real formula chain from the uploaded Excel workbook. You are the audit/trust
layer of this platform -- accuracy and source citation matter more than fluency here.

STRICT RULES:
1. You will receive a pre-built calculation_trace object containing the real formula
   chain, sheet names, row numbers, and values used. NEVER invent a formula, cell
   reference, or sheet name not present in this object.
2. Always cite the source: sheet name + row number + filename, for every formula step
   you mention. If a question can't be answered from calculation_trace, say so and
   suggest the user check the Knowledge Agent for definitional (non-formula) questions.
3. Present the chain step by step (intervention -> L2 -> L1 -> outcome), showing the
   formula and the actual numbers plugged in at each step.
4. If the user asks a hypothetical ("what if IDP were 50%?"), you may recompute using
   the SAME formula structure given in calculation_trace, showing your substitution
   explicitly -- but flag clearly that this is a simulated/unapplied projection, not
   the current live state. Do not silently update the dashboard.
5. Never editorialize about whether the formula is "correct" or "good practice" -- you
   report what the workbook contains, you do not audit business logic.
6. Tone: precise, technical-but-readable, like a knowledgeable analyst walking through
   a spreadsheet with a colleague.

OUTPUT FORMAT: Respond with ONLY a valid JSON object, no markdown fences, no text before
or after:
{
  "response_text": "...",
  "trace_steps": [{"step": 1, "description": "...", "formula": "...", "result": "..."}],
  "source_citation": "...",
  "is_hypothetical": false
}
"""

NO_TRACE_RESPONSE = ExcelIntelligenceResponse(
    response_text="I can't trace this specific calculation -- I couldn't find a matching formula chain in the indexed workbook for that metric.",
    trace_steps=[],
    source_citation="",
    is_hypothetical=False,
)


def handle_excel_intelligence(db: Session, request: ExcelIntelligenceRequest) -> ExcelIntelligenceResponse:
    trace = calculation_engine.trace_calculation(db, request.metric_name, request.metric_level)

    if trace is None:
        return NO_TRACE_RESPONSE

    payload = {
        "metric_queried": request.metric_name,
        "calculation_trace": trace.model_dump(by_alias=True),
        "source_file": "FA_V2.1.xlsx",
        "user_question": request.user_question,
        "is_hypothetical": request.hypothetical_overrides is not None,
    }
    if request.hypothetical_overrides:
        payload["hypothetical_overrides"] = request.hypothetical_overrides

    try:
        raw = call_anthropic_json(SYSTEM_PROMPT, payload)
    except AnthropicNotConfiguredError as exc:
        # Fall back to a literal, deterministic rendering of the trace with no LLM narration.
        fallback_steps = [
            ExcelTraceStepOut(
                step=s.step,
                description=f"{s.from_} -> {s.to}",
                formula=s.formula,
                result=str(s.weight) if s.weight is not None else "",
            )
            for s in trace.formula_path
        ]
        citation = "; ".join(sorted({f"{s.sheet} row {s.row}" for s in trace.formula_path if s.sheet}))
        return ExcelIntelligenceResponse(
            response_text=f"[Excel Intelligence Agent narration unavailable: {exc}] Raw trace below.",
            trace_steps=fallback_steps,
            source_citation=f"FA_V2.1.xlsx, {citation}",
            is_hypothetical=False,
        )

    response_text = raw.get("response_text", "")
    violations = validate_no_hallucinated_numbers(response_text, payload)
    if violations:
        response_text += f"\n\n[Note: hallucination guard flagged unverified numbers: {violations}]"

    trace_steps = [
        ExcelTraceStepOut(
            step=s.get("step", i + 1), description=s.get("description", ""),
            formula=s.get("formula", ""), result=s.get("result", ""),
        )
        for i, s in enumerate(raw.get("trace_steps", []))
    ]

    return ExcelIntelligenceResponse(
        response_text=response_text,
        trace_steps=trace_steps,
        source_citation=raw.get("source_citation", "FA_V2.1.xlsx"),
        is_hypothetical=raw.get("is_hypothetical", False),
    )
