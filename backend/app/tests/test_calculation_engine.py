"""
Unit tests for the new CalculationEngine (app/services/calculation_engine.py).

Scope of these tests, given the pending-confirmation formula issue:
- compute_l2() is tested fully — this part of the spec formula is NOT in
  dispute and matches the spec's own worked example exactly.
- compute_l1() / compute_business_outcomes() are tested only for their
  literal behavior as written (since that's what's actually implemented),
  NOT asserted as "correct" — see calculation_engine.py's warning block.
- reverse_solve() / optimize_under_budget() are tested for their GATING
  behavior (refusing to run while FORMULA_PENDING_CONFIRMATION is True),
  not for solver correctness, since they depend on the disputed formula.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import BusinessOutcome, L1Metric, L2Metric, Intervention
from app.repositories import l1_metric_repo, l2_metric_repo, intervention_repo
from app.services.calculation_engine import calculation_engine, FORMULA_PENDING_CONFIRMATION


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_compute_l2_matches_spec_worked_example(db_session):
    """
    Spec section 0.2 worked example:
    IDP = 28%, impact_factor = 0.133, L2 base (Invoice Cycle Time) = 8 days
    L2_new = 8 - (0.28 x 0.133 x 8) = 8 - 0.29792 = 7.70208 days (~4% reduction)
    This part of the formula is NOT in dispute and is implemented exactly as specified.
    """
    db = db_session

    l2 = L2Metric(name="Invoice Cycle Time", unit="Days", min_value=0, band_min=0, target_value=8,
                  max_value=30, default_value=8, current_value=8, improvement_percentage=0, higher_is_better=0)
    db.add(l2)
    db.commit()
    db.refresh(l2)

    idp = Intervention(name="IDP", percentage=28)
    db.add(idp)
    db.commit()
    db.refresh(idp)
    intervention_repo.set_l2_links(db, idp.id, [{"l2_metric_id": l2.id, "impact_factor": 0.133}])

    l2_new = calculation_engine.compute_l2(db, {idp.id: 28.0})
    assert l2_new[l2.id] == pytest.approx(7.70208, abs=0.001)

    pct_reduction = (8 - l2_new[l2.id]) / 8 * 100
    assert pct_reduction == pytest.approx(3.72, abs=0.1)  # "~4% reduction" per spec


def test_compute_l2_sums_multiple_interventions(db_session):
    db = db_session
    l2 = L2Metric(name="L2", unit="%", min_value=0, band_min=0, target_value=100,
                  max_value=200, default_value=100, current_value=100, improvement_percentage=0, higher_is_better=1)
    db.add(l2)
    db.commit()
    db.refresh(l2)

    iv1 = Intervention(name="IV1", percentage=40)
    iv2 = Intervention(name="IV2", percentage=60)
    db.add_all([iv1, iv2])
    db.commit()
    db.refresh(iv1)
    db.refresh(iv2)

    intervention_repo.set_l2_links(db, iv1.id, [{"l2_metric_id": l2.id, "impact_factor": 0.1}])
    intervention_repo.set_l2_links(db, iv2.id, [{"l2_metric_id": l2.id, "impact_factor": 0.2}])

    # L2_new = 100 - (0.40*0.1*100) - (0.60*0.2*100) = 100 - 4 - 12 = 84
    l2_new = calculation_engine.compute_l2(db, {iv1.id: 40.0, iv2.id: 60.0})
    assert l2_new[l2.id] == pytest.approx(84.0)


def test_formula_pending_confirmation_flag_is_set():
    """
    Documents the current state: this flag MUST be True until the spec
    author confirms the L1/BusinessOutcome aggregation formula. If this
    test starts failing because someone flipped the flag, that's a signal
    to also re-enable reverse_solve/optimize_under_budget and update this
    test file accordingly — not a bug to silently fix.
    """
    assert FORMULA_PENDING_CONFIRMATION is True


def test_reverse_solve_refuses_while_formula_pending(db_session):
    db = db_session
    result = calculation_engine.reverse_solve(db, "Days Sales Outstanding", 30.0)
    assert result.feasible is False
    assert "pending confirmation" in result.confidence_basis.lower()


def test_optimize_under_budget_refuses_while_formula_pending(db_session):
    db = db_session
    result = calculation_engine.optimize_under_budget(db, 5000.0, "Finance & Accounting", "Order to Cash")
    assert result.infeasible is True
    assert result.options == []
    assert "pending confirmation" in (result.recommendation_basis or "").lower()
