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

    Excel first converts slider 50 to 0.50, then:
    L2 change%   = 0.5 * 0.50 / 100 = 0.0025  -> L2 new value = 100.25
    L1 change%   = 1.0 * 0.0025 = 0.0025      -> L1 new value = 100.25
    BO change%   = -0.5 * 0.0025 = -0.00125   -> BO new value = 99.875
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

    assert l2.current_value == pytest.approx(100.25)
    assert l1.current_value == pytest.approx(100.25)
    assert bo.current_value == pytest.approx(99.875)


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

    # change% = (0.1*0.40/100) + (0.2*0.60/100) = 0.0004 + 0.0012 = 0.0016
    simulation_service.recalculate(db)
    db.refresh(l2)
    assert l2.current_value == pytest.approx(100.16)
    assert l2.improvement_percentage == pytest.approx(0.16)


def _build_cascade_scenario(db, bo_default, l2_defaults, l1_defaults,
                             if_iv_l2, if_l2_l1, if_l1_bo, iv_pcts):
    """
    Generic helper: builds a full 3-layer scenario in the given in-memory DB
    and returns (bo, l1_list, l2_list, iv_list) ORM objects.

    Parameters
    ----------
    bo_default  : float  – default value for the single Business Outcome
    l2_defaults : list   – [d1, d2, d3] default values for L2 metrics
    l1_defaults : list   – [d1, d2]     default values for L1 metrics
    if_iv_l2    : list   – [(iv_idx, l2_idx, IF), ...] Intervention->L2 edges
    if_l2_l1    : list   – [(l2_idx, l1_idx, IF), ...] L2->L1 edges
    if_l1_bo    : list   – [(l1_idx, IF), ...]         L1->BO edges
    iv_pcts     : list   – [pct1, pct2, pct3] slider values for interventions
    """
    bo = BusinessOutcome(
        name="BO", unit="%",
        min_value=0, band_min=0, target_value=100, max_value=200,
        default_value=bo_default, current_value=bo_default,
        improvement_percentage=0, higher_is_better=0,
    )
    db.add(bo)
    db.commit()
    db.refresh(bo)

    l1_objs = []
    for d in l1_defaults:
        m = L1Metric(
            name=f"L1_{len(l1_objs)+1}", unit="%",
            min_value=0, band_min=0, target_value=100, max_value=200,
            default_value=d, current_value=d,
            improvement_percentage=0, higher_is_better=0,
        )
        db.add(m); db.commit(); db.refresh(m)
        l1_objs.append(m)

    for l1_idx, if_val in if_l1_bo:
        l1_metric_repo.set_business_outcome_links(
            db, l1_objs[l1_idx].id,
            [{"business_outcome_id": bo.id, "impact_factor": if_val}]
        )

    l2_objs = []
    for d in l2_defaults:
        m = L2Metric(
            name=f"L2_{len(l2_objs)+1}", unit="%",
            min_value=0, band_min=0, target_value=100, max_value=200,
            default_value=d, current_value=d,
            improvement_percentage=0, higher_is_better=0,
        )
        db.add(m); db.commit(); db.refresh(m)
        l2_objs.append(m)

    # Group L2->L1 links by l2_idx so all edges for one L2 are set together
    from collections import defaultdict
    l2_to_l1_links = defaultdict(list)
    for l2_idx, l1_idx, if_val in if_l2_l1:
        l2_to_l1_links[l2_idx].append({"l1_metric_id": l1_objs[l1_idx].id, "impact_factor": if_val})
    for l2_idx, links in l2_to_l1_links.items():
        l2_metric_repo.set_l1_links(db, l2_objs[l2_idx].id, links)

    iv_objs = []
    for pct in iv_pcts:
        iv = Intervention(name=f"IV_{len(iv_objs)+1}", percentage=pct)
        db.add(iv); db.commit(); db.refresh(iv)
        iv_objs.append(iv)

    iv_to_l2_links = defaultdict(list)
    for iv_idx, l2_idx, if_val in if_iv_l2:
        iv_to_l2_links[iv_idx].append({"l2_metric_id": l2_objs[l2_idx].id, "impact_factor": if_val})
    for iv_idx, links in iv_to_l2_links.items():
        intervention_repo.set_l2_links(db, iv_objs[iv_idx].id, links)

    return bo, l1_objs, l2_objs, iv_objs


def _expected_cascade(bo_default, l2_defaults, l1_defaults,
                      if_iv_l2, if_l2_l1, if_l1_bo, iv_pcts):
    """
    Pure-Python implementation of the cascade formula.
    Returns dicts: l2_chg, l1_chg, bo_chg, l2_new, l1_new, bo_new
    — computed entirely from the inputs, no hardcoded numbers.

    Formula (mirrors simulation_service.recalculate exactly):
      L2 total_change[j] = sum over i: (IF_iv_l2[i,j] * (iv_pct[i] / 100)) / 100
      L1 total_change[k] = sum over j: IF_l2_l1[j,k] * L2_total_change[j]
      BO total_change     = sum over k: IF_l1_bo[k]   * L1_total_change[k]
      new_value           = default * (1 + total_change)
    """
    # Step 1: IV -> L2
    l2_chg = [0.0] * len(l2_defaults)
    for iv_idx, l2_idx, if_val in if_iv_l2:
        l2_chg[l2_idx] += (if_val * (iv_pcts[iv_idx] / 100.0)) / 100.0

    # Step 2: L2 -> L1
    l1_chg = [0.0] * len(l1_defaults)
    for l2_idx, l1_idx, if_val in if_l2_l1:
        l1_chg[l1_idx] += if_val * l2_chg[l2_idx]

    # Step 3: L1 -> BO
    bo_chg = 0.0
    for l1_idx, if_val in if_l1_bo:
        bo_chg += if_val * l1_chg[l1_idx]

    l2_new = [l2_defaults[i] * (1 + l2_chg[i]) for i in range(len(l2_defaults))]
    l1_new = [l1_defaults[i] * (1 + l1_chg[i]) for i in range(len(l1_defaults))]
    bo_new = bo_default * (1 + bo_chg)

    return {
        "l2_chg": l2_chg, "l1_chg": l1_chg, "bo_chg": bo_chg,
        "l2_new": l2_new, "l1_new": l1_new, "bo_new": bo_new,
    }


def _assert_cascade(db, bo, l1_objs, l2_objs, exp):
    """Refresh ORM objects and assert engine output matches expected values.

    improvement_percentage is stored by the engine rounded to 2 decimal
    places (via _round(..., 2)), so we compare against the same rounded
    value rather than the full floating-point precision.
    """
    for obj in [bo] + l1_objs + l2_objs:
        db.refresh(obj)

    for i, m in enumerate(l2_objs):
        assert m.current_value == pytest.approx(exp["l2_new"][i], rel=1e-4), \
            f"L2[{i}] current_value: got {m.current_value}, expected {exp['l2_new'][i]}"
        assert m.improvement_percentage == pytest.approx(round(exp["l2_chg"][i] * 100, 2), abs=1e-6), \
            f"L2[{i}] improvement_percentage: got {m.improvement_percentage}, expected {round(exp['l2_chg'][i]*100,2)}"

    for i, m in enumerate(l1_objs):
        assert m.current_value == pytest.approx(exp["l1_new"][i], rel=1e-4), \
            f"L1[{i}] current_value: got {m.current_value}, expected {exp['l1_new'][i]}"
        assert m.improvement_percentage == pytest.approx(round(exp["l1_chg"][i] * 100, 2), abs=1e-6), \
            f"L1[{i}] improvement_percentage: got {m.improvement_percentage}, expected {round(exp['l1_chg'][i]*100,2)}"

    assert bo.current_value == pytest.approx(exp["bo_new"], rel=1e-4), \
        f"BO current_value: got {bo.current_value}, expected {exp['bo_new']}"
    assert bo.improvement_percentage == pytest.approx(round(exp["bo_chg"] * 100, 2), abs=1e-6), \
        f"BO improvement_percentage: got {bo.improvement_percentage}, expected {round(exp['bo_chg']*100,2)}"


# ---------------------------------------------------------------------------
# Shared topology used across parametrized tests
# Matches the Health Insurance / Insurance scenario in the DB,
# derived from the Excel "Relationships" sheet:
#
#   Topology
#   --------
#   IV_1 -> L2_1 (IF=0.34)   i.e. at 50%: L2_1 changes +17%
#   IV_2 -> L2_2 (IF=0.28)   i.e. at 50%: L2_2 changes +14%
#   IV_3 -> L2_3 (IF=0.25)   i.e. at 50%: L2_3 changes +12.5%
#
#   L2_1 -> L1_1 (IF= 0.7)
#   L2_2 -> L1_1 (IF= 0.8)
#   L2_3 -> L1_1 (IF=-0.5)
#   L2_3 -> L1_2 (IF= 0.6)
#
#   L1_1 -> BO   (IF=-0.35)
#   L1_2 -> BO   (IF=-0.55)
#
#   Defaults: L2=[24,35,45]  L1=[40,80]  BO=100
#
#   Verified at IV=50%:
#     L2_1=28.08 (+17%), L2_2=39.9 (+14%), L2_3=50.625 (+12.5%)
#     L1_1=46.74 (+16.85%), L1_2=86.0 (+7.5%)
#     BO  =89.98 (-10.02%)
# ---------------------------------------------------------------------------
BO_DEFAULT   = 100.0
L2_DEFAULTS  = [24.0, 35.0, 45.0]
L1_DEFAULTS  = [40.0, 80.0]

# IV_i -> L2_j  (iv_idx, l2_idx, impact_factor)
IF_IV_L2 = [
    (0, 0, 10.0),    # IV_1 -> L2_1
    (1, 0, 24.0),    # Excel U6 references T7 twice: equivalent to IF 12 + 12
    (1, 1, 8.0),     # IV_2 -> L2_2
    (2, 1, 20.0),    # IV_3 -> L2_2
    (2, 2, 25.0),    # IV_3 -> L2_3
]
# L2_j -> L1_k  (l2_idx, l1_idx, impact_factor)
IF_L2_L1 = [
    (0, 0,  0.7),    # L2_1 -> L1_1
    (1, 0,  0.8),    # L2_2 -> L1_1
    (2, 0, -0.5),    # L2_3 -> L1_1
    (2, 1,  0.6),    # L2_3 -> L1_2
]
# L1_k -> BO  (l1_idx, impact_factor)
IF_L1_BO = [
    (0, -0.35),      # L1_1 -> BO
    (1, -0.55),      # L1_2 -> BO
]


@pytest.mark.parametrize("iv_pcts", [
    [0,  0,  0, 0],     # baseline - no change
    [17, 11, 11, 0],    # user-provided Excel verification point
    [50, 50, 50, 0],    # higher adoption
    [100,100,100,0],    # full adoption
    [11,  0,  0, 0],    # only IV_1 active
    [0,  11,  0, 0],    # only IV_2 active
    [0,   0, 11, 0],    # only IV_3 active
    [25, 50, 75, 0],    # mixed values
    [11, 22, 33, 0],    # all different
])
def test_cascade_any_intervention_value(db_session, iv_pcts):
    """
    Parametrized cascade test — works for ANY intervention percentages.

    Expected values are computed purely from the cascade formula
    (same math as simulation_service.recalculate). No result is hardcoded.
    The test proves the engine matches the formula for every combination.
    """
    db = db_session

    bo, l1_objs, l2_objs, _ = _build_cascade_scenario(
        db,
        bo_default=BO_DEFAULT,
        l2_defaults=L2_DEFAULTS,
        l1_defaults=L1_DEFAULTS,
        if_iv_l2=IF_IV_L2,
        if_l2_l1=IF_L2_L1,
        if_l1_bo=IF_L1_BO,
        iv_pcts=iv_pcts,
    )

    simulation_service.recalculate(db)

    exp = _expected_cascade(
        bo_default=BO_DEFAULT,
        l2_defaults=L2_DEFAULTS,
        l1_defaults=L1_DEFAULTS,
        if_iv_l2=IF_IV_L2,
        if_l2_l1=IF_L2_L1,
        if_l1_bo=IF_L1_BO,
        iv_pcts=iv_pcts,
    )

    _assert_cascade(db, bo, l1_objs, l2_objs, exp)


def test_excel_supplied_17_11_11_outputs(db_session):
    """Pinned values from the supplied workbook when Intervention_1/2/3 are 17/11/11."""
    db = db_session

    bo, l1_objs, l2_objs, _ = _build_cascade_scenario(
        db,
        bo_default=BO_DEFAULT,
        l2_defaults=L2_DEFAULTS,
        l1_defaults=L1_DEFAULTS,
        if_iv_l2=IF_IV_L2,
        if_l2_l1=IF_L2_L1,
        if_l1_bo=IF_L1_BO,
        iv_pcts=[17, 11, 11, 0],
    )

    simulation_service.recalculate(db)
    for obj in [bo] + l1_objs + l2_objs:
        db.refresh(obj)

    assert l2_objs[0].current_value == pytest.approx(25.0416)
    assert l2_objs[1].current_value == pytest.approx(36.078)
    assert l2_objs[2].current_value == pytest.approx(46.2375)
    assert l1_objs[0].current_value == pytest.approx(41.6508)
    assert l1_objs[1].current_value == pytest.approx(81.32)
    assert bo.current_value == pytest.approx(97.6481)
