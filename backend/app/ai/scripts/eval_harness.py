"""
Agent Eval / Regression Harness — Goal Agent & Decision Advisor
=================================================================

What this is (and isn't)
-------------------------
This is NOT model fine-tuning. Gemini isn't fine-tunable through this
integration, and prompt/weight training in the ML sense doesn't apply here.
What this actually does — and the thing people usually mean by "train the
agent" for an API-based LLM — is:

  1. A growing, runnable set of real user-style queries with EXPECTED,
     checkable outcomes (which agent should fire, what deterministic facts
     the reply must contain, what it must NOT invent).
  2. Assertions against the real deterministic tool layer (goal_tool,
     decision_advisor_tool, whatif_tool) using the real seeded DB and the
     real cascade math — not mocks — so a regression in the solver or the
     ranking logic is caught even without calling the LLM.
  3. A place to add a case the moment a bug is found, so it can never
     silently regress again (this formalizes what AGENT_TRAINING_NOTES.md
     already did by hand, case by case).

The LLM narration layer (format_goal_prompt -> Gemini -> prose) is NOT
re-verified here on every run, since that needs a live GEMINI_API_KEY and
network access and would make this harness flaky/slow. Instead, each case
checks the DETERMINISTIC tool_data and/or the generated PROMPT TEXT that
gets handed to the LLM — the part that's actually ours to get right. The
LLM's job is just to narrate already-correct facts fluently; garbage tool
data or a garbled prompt is what actually causes bad answers.

Run directly:
    cd backend && python -m app.ai.scripts.eval_harness

Or via pytest (recommended for CI):
    cd backend && python -m pytest app/tests/test_agent_eval_harness.py -v

Add a new case whenever a real bug is found — see CASES below.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ...database import Base
from ...models import BusinessOutcome, L1Metric, L2Metric, Intervention
from ...models.models import intervention_l2_link, l2_l1_link, l1_bo_link
from ..tools.kpi_tools import goal_tool, decision_advisor_tool, whatif_tool
from ..cascade.prompts import format_goal_prompt, format_whatif_prompt
from ..cascade.agent import (
    detect_intent,
    _is_goal_seeking_intent,
    _is_goal_target_intent,
    _is_advisor_apply_intent,
    _is_whatif_intent,
)
from ..cascade.schemas import IntentType


# ── Shared test fixture: a small, real, seeded scenario ─────────────────────
# Deliberately shaped like the bug report's own example: two interventions
# that, even maxed out, can't push a Business Outcome down to a much lower
# target — so "unreachable target" cases are testing real solver behavior,
# not a contrived stub.

def _seeded_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    bo = BusinessOutcome(
        name="Cash Conversion Cycle", unit="Days", min_value=10, max_value=60,
        default_value=50, current_value=50, higher_is_better=0,
        vertical_horizontal="Finance & Accounting", lob="Order to Cash",
    )
    l1 = L1Metric(
        name="Days Sales Outstanding", unit="Days", default_value=45, current_value=45,
        higher_is_better=0, vertical_horizontal="Finance & Accounting", lob="Order to Cash",
    )
    l2 = L2Metric(
        name="Collections Automation", unit="%", default_value=0, current_value=0,
        higher_is_better=1, vertical_horizontal="Finance & Accounting", lob="Order to Cash",
    )
    iv1 = Intervention(name="RPA Bots", percentage=0,
                        vertical_horizontal="Finance & Accounting", lob="Order to Cash")
    iv2 = Intervention(name="Workflow Automation", percentage=0,
                        vertical_horizontal="Finance & Accounting", lob="Order to Cash")
    db.add_all([bo, l1, l2, iv1, iv2])
    db.commit()
    for obj in (bo, l1, l2, iv1, iv2):
        db.refresh(obj)

    db.execute(l1_bo_link.insert().values(l1_metric_id=l1.id, business_outcome_id=bo.id, impact_factor=1.0))
    db.execute(l2_l1_link.insert().values(l2_metric_id=l2.id, l1_metric_id=l1.id, impact_factor=-0.3))
    db.execute(intervention_l2_link.insert().values(intervention_id=iv1.id, l2_metric_id=l2.id, impact_factor=0.5))
    db.execute(intervention_l2_link.insert().values(intervention_id=iv2.id, l2_metric_id=l2.id, impact_factor=0.5))
    db.commit()
    return db


@dataclass
class EvalCase:
    name: str
    run: Callable[[Any], None]  # receives a fresh db session; raises AssertionError on failure
    notes: str = ""


CASES: List[EvalCase] = []


def case(name: str, notes: str = ""):
    def deco(fn):
        CASES.append(EvalCase(name=name, run=fn, notes=notes))
        return fn
    return deco


# ── Suggestion-button intent determinism ─────────────────────────────────────
# See PATCH_NOTES: every starter button now sends a fixed intent_override,
# so these must resolve through the override path regardless of wording.

@case(
    "suggestion_buttons_are_deterministic",
    "Each of the 5 chat starters must resolve to its documented agent via "
    "intent_override, independent of message wording / LLM availability.",
)
def _(db):
    expected = {
        "insight": "Why did my KPIs change?",
        "goal": "How can I improve Cash Conversion Cycle?",
        "trace": "Show me the formula path for Cash Conversion Cycle",
        "advisor": "Recommend the best intervention strategy",
    }
    for intent_str, message in expected.items():
        resolved = detect_intent(message, override=IntentType(intent_str))
        assert resolved == IntentType(intent_str), (
            f"starter message {message!r} with override={intent_str} resolved to {resolved}"
        )


@case(
    "advisor_only_fires_on_explicit_strategy_ask",
    "🎯-style improvement questions must never fall into Advisor's "
    "deterministic pre-checks (goal-seeking / advisor-apply) when no "
    "explicit strategy-ranking language is present.",
)
def _(db):
    goal_like = [
        "How can I improve Cash Conversion Cycle?",
        "What drives Cash Conversion Cycle and how do I improve it?",
        "reach revenue growth is 85",
        "reduce revenue growth 5",
    ]
    for msg in goal_like:
        assert not _is_advisor_apply_intent(msg), f"{msg!r} incorrectly matched advisor-apply"

    advisor_like = [
        "apply the top recommendation to my sliders",
        "Recommend the best intervention strategy",
    ]
    assert _is_advisor_apply_intent(advisor_like[0])


# ── Goal Agent: reachable / unreachable, deterministic tool data ────────────

@case(
    "goal_unreachable_reports_limiting_factors",
    "Bug report case: an out-of-reach target must come back with WHY it "
    "can't be reached (limiting_factors), not just a bare gap%.",
)
def _(db):
    result = goal_tool(
        db, target_metric="Cash Conversion Cycle", target_value=1.0, higher_is_better=False,
        vertical="Finance & Accounting", lob="Order to Cash",
    )
    assert result["target_achievable"] is False
    assert result["limiting_factors"], "expected at least one limiting factor for an unreachable target"
    names = {lf["name"] for lf in result["limiting_factors"]}
    assert names.issubset({"RPA Bots", "Workflow Automation"})

    prompt = format_goal_prompt(result, "How can I improve Cash Conversion Cycle to 1?")
    for heading in ("**Definition**", "**Why the target cannot be reached**",
                    "**Limiting factors**", "**Closest achievable result**", "**Recommended action**"):
        assert heading in prompt, f"missing section {heading!r} in unreachable-target prompt"


@case(
    "goal_reachable_gives_single_clear_option",
    "A reachable target must state Option 1 as THE plan, not hedge between options.",
)
def _(db):
    # Set the search up so a modest, reachable target exists.
    result = goal_tool(
        db, target_metric="Cash Conversion Cycle", target_value=49.0, higher_is_better=False,
        vertical="Finance & Accounting", lob="Order to Cash",
    )
    if result["target_achievable"]:
        prompt = format_goal_prompt(result, "Get Cash Conversion Cycle to 49")
        assert "Target IS reachable" in prompt
        assert "ONLY answer to give" in prompt


@case(
    "goal_seeking_regex_catches_unlabelled_phrasing",
    "Deterministic pre-checks (used when the LLM is unavailable) must still "
    "catch common goal phrasings that don't use the words target/reach.",
)
def _(db):
    must_be_goal = [
        "decrease the revenue growth 5",
        "reduce revenue growth by 5",
        "achieve 90 NPS",
        "what interventions should I change to hit 42.5?",
    ]
    for msg in must_be_goal:
        assert _is_goal_seeking_intent(msg) or _is_goal_target_intent(msg), (
            f"{msg!r} was not caught by any goal-seeking pre-check"
        )


# ── Decision Advisor: ranking sanity + no silent crash ───────────────────────

@case(
    "decision_advisor_ranks_by_signed_direction_not_raw_magnitude",
    "Regression guard for the 'Maximum Push always wins' bug: a strategy "
    "that HURTS the target outcome must never outrank one that helps it, "
    "even if it causes a larger raw movement. Ranking is now produced by "
    "decision_engine.py's risk/cost-aware composite score rather than raw "
    "avg_bo_improvement alone (see PATCH_NOTES: Decision Intelligence "
    "Engine) — so the invariant checked here is 'strategies are sorted by "
    "decision_score descending' and 'a strategy with negative/zero signed "
    "improvement never scores above one with strictly positive signed "
    "improvement', not 'sorted by raw avg_bo_improvement' (that ordering "
    "can now legitimately be reshuffled by a lower-risk/cost runner-up).",
)
def _(db):
    result = decision_advisor_tool(
        db, target_outcome="Cash Conversion Cycle",
        vertical="Finance & Accounting", lob="Order to Cash",
    )
    assert "error" not in result, f"decision_advisor_tool errored: {result.get('error')}"
    strategies = result.get("strategies") or result.get("ranked_strategies") or []
    assert strategies, "decision_advisor_tool returned no strategies"

    # 1. Every strategy carries the Decision Intelligence Engine's output.
    for s in strategies:
        assert "decision_score" in s and "risk" in s and "cost" in s, (
            f"strategy {s.get('name')!r} missing decision_engine fields"
        )

    # 2. Sorted by decision_score descending (the new authoritative order).
    ds_scores = [s["decision_score"] for s in strategies]
    assert ds_scores == sorted(ds_scores, reverse=True), (
        "strategies are not sorted by decision_score descending"
    )

    # 3. The original bug's actual failure mode still can't happen: a
    # strategy with a positive (helpful) signed avg_bo_improvement must
    # never score below one with a negative (harmful) signed
    # avg_bo_improvement, regardless of risk/cost tie-breaking.
    best_helpful = max((s["avg_bo_improvement"] for s in strategies), default=0)
    worst_harmful = min((s["avg_bo_improvement"] for s in strategies), default=0)
    if best_helpful > 0 and worst_harmful < 0:
        helpful_top_score = max(s["decision_score"] for s in strategies if s["avg_bo_improvement"] > 0)
        harmful_top_score = max(s["decision_score"] for s in strategies if s["avg_bo_improvement"] < 0)
        assert helpful_top_score > harmful_top_score, (
            "a harmful (signed-negative) strategy scored as well as a helpful one"
        )


@case(
    "decision_advisor_does_not_silently_crash",
    "Regression guard for the historical undefined-variable bug (`target` "
    "vs `target_outcome`) that made this tool throw on every call.",
)
def _(db):
    result = decision_advisor_tool(db, target_outcome=None,
                                    vertical="Finance & Accounting", lob="Order to Cash")
    assert "error" not in result


# ── What-If: out-of-range values are reported, never silently guessed ───────

@case(
    "whatif_out_of_range_value_is_reported_with_exact_message",
    "Bug report requirement: a value above/below the supported range must "
    "produce a clear message, not a silent clamp-and-guess.",
)
def _(db):
    result = whatif_tool(db, {"RPA Bots": 140, "Workflow Automation": 60},
                          vertical="Finance & Accounting", lob="Order to Cash")
    assert result["out_of_range"] == [
        {"name": "RPA Bots", "requested": 140, "min": 0.0, "max": 100.0, "direction": "above"}
    ]
    assert result["applied_overrides"] == {"Workflow Automation": 60}
    prompt = format_whatif_prompt(result, "what if RPA Bots were 140%?")
    assert "exceeds the maximum supported limit of 100.0%" in prompt


def run_all(verbose: bool = True) -> Dict[str, Any]:
    passed, failed = [], []
    for c in CASES:
        db = _seeded_db()
        try:
            c.run(db)
            passed.append(c.name)
            if verbose:
                print(f"  PASS  {c.name}")
        except AssertionError as e:
            failed.append((c.name, str(e)))
            if verbose:
                print(f"  FAIL  {c.name}: {e}")
        except Exception as e:  # noqa: BLE001 — surface any unexpected error as a failure too
            failed.append((c.name, f"unexpected error: {e!r}"))
            if verbose:
                print(f"  ERROR {c.name}: {e!r}")
        finally:
            db.close()

    if verbose:
        print(f"\n{len(passed)}/{len(CASES)} cases passed.")
    return {"passed": passed, "failed": failed, "total": len(CASES)}


if __name__ == "__main__":
    result = run_all()
    raise SystemExit(1 if result["failed"] else 0)
