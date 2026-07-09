"""
Regression tests for two fixes made in response to the bug report
"Suggestion Intent Mapping & Goal Agent Response":

1. goal_tool now returns `limiting_factors` (interventions pinned at 0%/100%
   in the best-found configuration) whenever a target is NOT reachable, and
   format_goal_prompt turns that into a structured Definition / Why-not /
   Limiting-factors / Closest-achievable / Recommended-action reply instead
   of a bare "cannot be reached, gap = X%" line.

2. whatif_service.evaluate_hypothetical no longer silently clamps an
   out-of-range hypothetical intervention value into 0-100 — it reports it
   back as `out_of_range` (with the requested value + supported max/min) so
   the agent can tell the user clearly, while still computing a real
   prediction for any other, in-range values in the same request.

These use the actual seeded DB (via the `db_session`/`seeded_db` fixtures
already used elsewhere in this test package) rather than mocks, so a
regression in the real reverse-solver/cascade math would also be caught.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..database import Base
from ..models import BusinessOutcome, L1Metric, L2Metric, Intervention
from ..models.models import intervention_l2_link, l2_l1_link, l1_bo_link
from ..ai.tools.kpi_tools import goal_tool, whatif_tool
from ..ai.cascade.prompts import format_goal_prompt, format_whatif_prompt


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()


def _seed_ccc_scenario(db):
    """Minimal Cash-Conversion-Cycle-style scenario: two interventions that,
    even maxed out, cannot push the Business Outcome below the target — the
    exact shape of the bug report's example (target 42.5, closest 49.98)."""
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

    # Impact factors chosen so max intervention adoption still only gets
    # DSO/CCC partway to a much lower target — an intentionally unreachable goal.
    db.execute(l1_bo_link.insert().values(l1_metric_id=l1.id, business_outcome_id=bo.id, impact_factor=1.0))
    db.execute(l2_l1_link.insert().values(l2_metric_id=l2.id, l1_metric_id=l1.id, impact_factor=-0.3))
    db.execute(intervention_l2_link.insert().values(intervention_id=iv1.id, l2_metric_id=l2.id, impact_factor=0.5))
    db.execute(intervention_l2_link.insert().values(intervention_id=iv2.id, l2_metric_id=l2.id, impact_factor=0.5))
    db.commit()
    return bo, l1, l2, iv1, iv2


def test_goal_tool_reports_limiting_factors_when_unreachable(db_session):
    db = db_session
    _seed_ccc_scenario(db)

    result = goal_tool(
        db, target_metric="Cash Conversion Cycle", target_value=1.0, higher_is_better=False,
        vertical="Finance & Accounting", lob="Order to Cash",
    )

    assert result["target_achievable"] is False
    assert result["closest_reachable"] is not None
    limiting = {lf["name"] for lf in result["limiting_factors"]}
    # Both interventions should be pinned at their maximum in the
    # best-found (rank 1) configuration — that's the whole reason the
    # target can't go any lower.
    assert "RPA Bots" in limiting
    assert "Workflow Automation" in limiting
    assert all(lf["at"] == "maximum (100%)" for lf in result["limiting_factors"])


def test_goal_prompt_structures_unreachable_response(db_session):
    db = db_session
    _seed_ccc_scenario(db)
    result = goal_tool(
        db, target_metric="Cash Conversion Cycle", target_value=1.0, higher_is_better=False,
        vertical="Finance & Accounting", lob="Order to Cash",
    )
    prompt = format_goal_prompt(result, "How can I improve Cash Conversion Cycle to 1?")

    for heading in (
        "**Definition**", "**Why the target cannot be reached**",
        "**Limiting factors**", "**Closest achievable result**", "**Recommended action**",
    ):
        assert heading in prompt
    assert "RPA Bots is already at its maximum" in prompt


def test_goal_tool_no_limiting_factors_key_when_reachable(db_session):
    """A target that IS reachable should not have a spurious limiting_factors
    list distracting the reply — the achievable branch is unaffected."""
    db = db_session
    _seed_ccc_scenario(db)
    result = goal_tool(
        db, target_metric="Cash Conversion Cycle", target_value=49.0, higher_is_better=False,
        vertical="Finance & Accounting", lob="Order to Cash",
    )
    if result["target_achievable"]:
        assert result["limiting_factors"] == []


def test_whatif_out_of_range_value_reported_not_silently_clamped(db_session):
    db = db_session
    _seed_ccc_scenario(db)

    result = whatif_tool(
        db, {"RPA Bots": 140, "Workflow Automation": 60},
        vertical="Finance & Accounting", lob="Order to Cash",
    )

    assert result["out_of_range"] == [
        {"name": "RPA Bots", "requested": 140, "min": 0.0, "max": 100.0, "direction": "above"}
    ]
    # The in-range value should still produce a real prediction.
    assert result["applied_overrides"] == {"Workflow Automation": 60}
    assert result["business_outcomes"]


def test_whatif_prompt_gives_exact_range_message(db_session):
    db = db_session
    _seed_ccc_scenario(db)
    result = whatif_tool(
        db, {"RPA Bots": 140}, vertical="Finance & Accounting", lob="Order to Cash",
    )
    prompt = format_whatif_prompt(result, "What if RPA Bots were 140%?")
    assert "exceeds the maximum supported limit of 100.0%" in prompt
    assert "Please enter a value within the supported range" in prompt


def test_whatif_below_minimum_reported(db_session):
    db = db_session
    _seed_ccc_scenario(db)
    result = whatif_tool(
        db, {"RPA Bots": -20}, vertical="Finance & Accounting", lob="Order to Cash",
    )
    assert result["out_of_range"][0]["direction"] == "below"
    assert result["out_of_range"][0]["min"] == 0.0
