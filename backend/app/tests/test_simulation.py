"""
Minimal unit tests for the cascade calculation engine.
Run with:  cd backend && python -m pytest app/tests/test_simulation.py -v
(requires pytest: pip install pytest)
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
from app.services import simulation_service


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_single_chain_cascade(db_session):
    """
    Intervention (50%) --impact 0.5--> L2 (default 100)
    L2 --impact 1.0--> L1 (default 100)
    L1 --impact -0.5--> BO (default 100)

    L2 change%   = 0.5 * 50 / 100 = 0.25       -> L2 new value = 125
    L1 change%   = 1.0 * 0.25 = 0.25           -> L1 new value = 125
    BO change%   = -0.5 * 0.25 = -0.125        -> BO new value = 87.5
    """
    db = db_session

    bo = BusinessOutcome(name="BO", unit="%", min_value=0, band_min=0, target_value=100,
                          max_value=200, default_value=100, current_value=100,
                          improvement_percentage=0, higher_is_better=0)
    db.add(bo)
    db.commit()
    db.refresh(bo)

    l1 = L1Metric(name="L1", unit="%", min_value=0, band_min=0, target_value=100,
                  max_value=200, default_value=100, current_value=100,
                  improvement_percentage=0, higher_is_better=1)
    db.add(l1)
    db.commit()
    db.refresh(l1)
    l1_metric_repo.set_business_outcome_links(db, l1.id, [{"business_outcome_id": bo.id, "impact_factor": -0.5}])

    l2 = L2Metric(name="L2", unit="%", min_value=0, band_min=0, target_value=100,
                  max_value=200, default_value=100, current_value=100,
                  improvement_percentage=0, higher_is_better=1)
    db.add(l2)
    db.commit()
    db.refresh(l2)
    l2_metric_repo.set_l1_links(db, l2.id, [{"l1_metric_id": l1.id, "impact_factor": 1.0}])

    iv = Intervention(name="IV", percentage=50)
    db.add(iv)
    db.commit()
    db.refresh(iv)
    intervention_repo.set_l2_links(db, iv.id, [{"l2_metric_id": l2.id, "impact_factor": 0.5}])

    simulation_service.recalculate(db)

    db.refresh(l2)
    db.refresh(l1)
    db.refresh(bo)

    assert l2.current_value == pytest.approx(125.0)
    assert l1.current_value == pytest.approx(125.0)
    assert bo.current_value == pytest.approx(87.5)


def test_zero_intervention_means_no_change(db_session):
    db = db_session
    bo = BusinessOutcome(name="BO", unit="%", min_value=0, band_min=0, target_value=100,
                          max_value=200, default_value=50, current_value=50,
                          improvement_percentage=0, higher_is_better=0)
    db.add(bo)
    db.commit()
    simulation_service.recalculate(db)
    db.refresh(bo)
    assert bo.current_value == 50.0
    assert bo.improvement_percentage == 0.0


def test_multiple_edges_sum_correctly(db_session):
    """Two interventions both feeding the same L2 metric should sum their change%."""
    db = db_session

    l2 = L2Metric(name="L2", unit="%", min_value=0, band_min=0, target_value=100,
                  max_value=200, default_value=100, current_value=100,
                  improvement_percentage=0, higher_is_better=1)
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

    # change% = (0.1*40/100) + (0.2*60/100) = 0.04 + 0.12 = 0.16
    simulation_service.recalculate(db)
    db.refresh(l2)
    assert l2.current_value == pytest.approx(116.0)
    assert l2.improvement_percentage == pytest.approx(16.0)
