"""
Grounding & Evidence
---------------------
This is the enforcement layer the critique was really asking for. The
underlying tools (insight_tool, goal_tool, excel_trace_tool,
decision_advisor_tool) are already deterministic — they read real numbers
from the simulation engine / DB / Excel. The problem was never the data;
it was that nothing checked whether the LLM's PROSE actually stuck to
that data once it started writing.

Two things live here:

1. `find_ungrounded_numbers()` — after the LLM responds, extract every
   number in its text and check each one against the set of numbers that
   actually appeared in the tool output it was given. Any number that
   doesn't match anything (within a small rounding tolerance) is
   "ungrounded" — almost certainly invented mid-generation (this is
   exactly how the Trace Agent's fabricated "-0.55" impact factor for
   CSAT would be caught: it's not in `excel_trace_tool`'s output, so it
   can't be in the allowed set).

2. `compute_confidence()` / `evidence_list()` — a deterministic (no LLM)
   score and checklist of which real data sources backed this specific
   answer, so the UI can show something like:

       Evidence: ✓ Live Simulation  ✓ Formula Trace     Confidence: 92%

No ML "fine-tuning" happens here — there's no dataset or weight update.
This is closer to how a fact-checker works: cheap, deterministic, and
runs on every response, which is more reliable for a numbers-heavy
product than hoping a bigger prompt makes the model behave.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set, Tuple

# Matches ints/decimals, with an optional leading +/- and trailing %.
_NUMBER_RE = re.compile(r"[+-]?\d+(?:\.\d+)?%?")

# Numbers so small/common they appear constantly in ordinary prose
# ("top 3 strategies", "option 1", "step 2") and would otherwise flood
# the ungrounded-number list with false positives.
_IGNORE_NUMBERS = {0, 1, 2, 3, 4, 5, 10, 100}


def _to_float(token: str) -> float:
    return float(token.replace("%", ""))


def extract_numbers(text: str) -> List[float]:
    """Pull every numeric token out of a piece of text."""
    if not text:
        return []
    out = []
    for m in _NUMBER_RE.finditer(text):
        try:
            out.append(_to_float(m.group(0)))
        except ValueError:
            continue
    return out


def _walk_numbers(obj: Any) -> Iterable[float]:
    """Recursively pull every numeric leaf out of a tool_data dict/list."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_numbers(v)
    elif isinstance(obj, str):
        # Some numbers arrive pre-formatted as strings (e.g. "18%").
        for n in extract_numbers(obj):
            yield n


def collect_allowed_numbers(*tool_data_dicts: Dict[str, Any]) -> Set[float]:
    """Build the whitelist of numbers the LLM is allowed to have used,
    from every tool_data dict that was actually fed into its prompt."""
    allowed: Set[float] = set()
    for data in tool_data_dicts:
        if not data:
            continue
        for n in _walk_numbers(data):
            allowed.add(round(n, 2))
            allowed.add(round(n, 1))
            allowed.add(round(n))
    return allowed


def find_ungrounded_numbers(
    text: str, allowed: Set[float], tolerance: float = 0.06
) -> List[float]:
    """Return numbers used in `text` that don't correspond to anything in
    `allowed` (within `tolerance`, to survive rounding-format differences
    like 41.45 vs 41.4 vs 41%)."""
    if not text or not allowed:
        return []
    flagged: List[float] = []
    for n in extract_numbers(text):
        if abs(n) in _IGNORE_NUMBERS:
            continue
        if any(abs(n - a) <= tolerance for a in allowed):
            continue
        # Percent deltas are frequently restated as bare numbers
        # ("a 3.6% gain" -> 3.6, "which is +3.63%" -> 3.63) — already
        # covered by tolerance above. Anything left over here genuinely
        # doesn't correspond to anything in the tool output.
        flagged.append(n)
    return flagged


# ── Evidence / Confidence ───────────────────────────────────────────────────

SOURCE_LABELS = {
    "live_simulation": "Live Simulation",
    "formula_trace": "Formula Trace",
    "workbook": "Workbook / Excel",
    "knowledge_base": "Knowledge Base",
    "goal_engine": "Goal Engine",
    "decision_engine": "Decision Engine",
}


def evidence_list(sources_used: Iterable[str]) -> List[str]:
    return [SOURCE_LABELS.get(s, s) for s in sources_used if s]


def compute_confidence(
    *,
    has_error: bool = False,
    ungrounded_count: int = 0,
    sources_used: Iterable[str] = (),
    data_completeness: float = 1.0,
) -> float:
    """Deterministic confidence score in [0, 1]. No LLM involved — this is
    a simple, auditable rollup of how much of the answer is backed by
    verified data versus how much looks like it might not be."""
    if has_error:
        return 0.2

    score = 0.55 + 0.1 * min(len(list(sources_used)), 3)
    score *= max(0.0, min(1.0, data_completeness))
    score -= 0.15 * min(ungrounded_count, 3)
    return round(max(0.05, min(0.99, score)), 2)


def evidence_footer(sources_used: Iterable[str], confidence: float, ungrounded: List[float] | None = None) -> str:
    """Deterministic markdown footer — never produced by the LLM."""
    labels = evidence_list(sources_used)
    check_line = "  ".join(f"✓ {label}" for label in labels) if labels else "— no verified data source"
    footer = f"\n\n---\n**Evidence:** {check_line}   **Confidence:** {int(round(confidence * 100))}%"
    if ungrounded:
        vals = ", ".join(str(v) for v in ungrounded[:4])
        footer += f"\n⚠️ Could not verify these figures against simulation data: {vals}"
    return footer
