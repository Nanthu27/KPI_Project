"""
Unit tests for the agent-layer infrastructure that doesn't depend on a
live LLM/Pinecone connection: the hallucination guard, the keyword-based
agent router, and TraceEngine's real-workbook indexing.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agents.hallucination_guard import validate_no_hallucinated_numbers
from app.agents.agent_router import route_question
from app.services.trace_engine import TraceEngine


# --- Hallucination guard ----------------------------------------------------

def test_guard_passes_when_all_numbers_present():
    structured_input = {"l1_changes": [{"name": "DSO", "base": 45, "new": 41, "delta_pct": -8.9}]}
    text = "DSO dropped from 45 to 41 days, an 8.9% improvement."
    assert validate_no_hallucinated_numbers(text, structured_input) == []


def test_guard_flags_invented_number():
    structured_input = {"l1_changes": [{"name": "DSO", "base": 45, "new": 41, "delta_pct": -8.9}]}
    text = "DSO dropped from 45 to 41 days, lifting revenue by 15.7%."
    violations = validate_no_hallucinated_numbers(text, structured_input)
    assert "15.7" in violations


def test_guard_exempts_small_counting_numbers():
    structured_input = {"x": 1}
    text = "Three interventions contributed to this change."
    assert validate_no_hallucinated_numbers(text, structured_input) == []


def test_guard_is_sign_agnostic():
    structured_input = {"delta_pct": -8.9}
    text = "a drop of 8.9 percent"
    assert validate_no_hallucinated_numbers(text, structured_input) == []


# --- Agent router -------------------------------------------------------------

def test_router_roi_insight():
    assert route_question("Why did DSO improve this month?") == "roi_insight"


def test_router_goal_seeking():
    assert route_question("I want DSO to reach 30 days") == "goal_seeking"


def test_router_excel_intelligence():
    assert route_question("How is collection efficiency calculated?") == "excel_intelligence"


def test_router_decision_advisor():
    assert route_question("I have a budget of $50000, what should I spend it on?") == "decision_advisor"


def test_router_knowledge_fallback():
    assert route_question("What is Cash Conversion Cycle?") == "knowledge"


def test_router_ambiguous_ROI_phrasing():
    assert route_question("What changed in the simulation?") == "roi_insight"


# --- TraceEngine real-workbook indexing -----------------------------------

def test_trace_engine_finds_real_dso_chain():
    engine = TraceEngine()
    trace = engine.build_trace(None, "Days Sales Outstanding", "l1")
    assert trace is not None
    assert len(trace.formula_path) > 0
    # Every step must cite a real sheet name from the workbook, never a fabricated one.
    for step in trace.formula_path:
        assert step.sheet in (
            "Interventions impacting L2",
            "Relationships (L2 impacting L1)",
            "Relationships (L1 impacting BO)",
        )


def test_trace_engine_returns_none_for_unknown_metric():
    engine = TraceEngine()
    trace = engine.build_trace(None, "Completely Made Up Metric Name XYZ123", "l1")
    assert trace is None
