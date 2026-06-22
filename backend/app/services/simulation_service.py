"""
Simulation service — LIVE DASHBOARD FORMULA (validated, chained-%).

This module is the calculation path actually used by the KPI Simulator
dashboard (every CRUD route calls simulation_service.recalculate(db)
after a mutation). It intentionally does NOT use the new
CalculationEngine's weighted-sum formula from
AI_Agents_Development_Spec.md section 0.2, because that formula's own
worked example doesn't reconcile with the formula as written (see the
big warning block at the top of services/calculation_engine.py) and
produces nonsensical numbers (negative DSO, negative Bad Debt Ratio)
with the current seed weights. Product decision: keep the dashboard on
this validated formula until the spec author confirms the correct
interpretation of the new one.

Implements the BRD's original "Calculation Logic" (chained percentage
cascade):

  Intervention -> L2 Metrics
    Change %       = (Impact Factor x Intervention New Value %) / 100
    Total Change % = sum(Change % from all related interventions)
    New Value      = Default Value + (Default Value x Total Change %)

  L2 Metrics -> L1 Metrics
    Change %       = Impact Factor x Total Change % of related L2 metric
    Total Change % = sum(Change % from all related L2 metrics)
    New Value      = Default Value + (Default Value x Total Change %)

  L1 Metrics -> Business Outcomes
    Change %       = Impact Factor x Total Change % of related L1 metric
    Total Change % = sum(Change % from all related L1 metrics)
    New Value      = Default Value + (Default Value x Total Change %)

`improvement_percentage` on every metric is simply Total Change% * 100,
signed so the UI can color it green/red depending on whether the
metric's "higher_is_better" flag agrees with the direction of travel.

NOTE for the AI agents: CalculationEngine.run_full_simulation(),
.reverse_solve(), .trace_calculation(), and .optimize_under_budget()
(in calculation_engine.py) are SEPARATE from this module and use the
new spec formula for their own internal math — that's an intentional,
isolated area pending confirmation, not a bug. Once the formula
ambiguity is resolved, this module and that one should be reconciled
into a single engine again.
"""
from typing import Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import (
    BusinessOutcome, L1Metric, L2Metric, Intervention,
    intervention_l2_link, l2_l1_link, l1_bo_link,
)


def _round(value: float, digits: int = 4) -> float:
    return round(value, digits)


def recalculate(db: Session) -> None:
    """
    Recomputes current_value + improvement_percentage for every
    L2Metric, L1Metric, and BusinessOutcome row, cascading up from
    whatever the Intervention.percentage values currently are.
    Mutates ORM objects in place and commits once at the end.
    """
    interventions: List[Intervention] = db.query(Intervention).all()
    l2_metrics: List[L2Metric] = db.query(L2Metric).all()
    l1_metrics: List[L1Metric] = db.query(L1Metric).all()
    business_outcomes: List[BusinessOutcome] = db.query(BusinessOutcome).all()

    # ---- Step 1: Intervention -> L2 ------------------------------------
    iv_l2_edges = db.execute(select(
        intervention_l2_link.c.intervention_id,
        intervention_l2_link.c.l2_metric_id,
        intervention_l2_link.c.impact_factor,
    )).all()

    intervention_value_by_id: Dict[int, float] = {iv.id: iv.percentage for iv in interventions}

    l2_total_change: Dict[int, float] = {m.id: 0.0 for m in l2_metrics}
    for intervention_id, l2_id, impact_factor in iv_l2_edges:
        new_value_pct = intervention_value_by_id.get(intervention_id, 0.0)
        change_pct = (impact_factor * new_value_pct) / 100.0
        if l2_id in l2_total_change:
            l2_total_change[l2_id] += change_pct

    for metric in l2_metrics:
        total_change = l2_total_change.get(metric.id, 0.0)
        metric.current_value = _round(metric.default_value + (metric.default_value * total_change))
        metric.improvement_percentage = _round(total_change * 100, 2)

    # ---- Step 2: L2 -> L1 ------------------------------------------------
    l2_l1_edges = db.execute(select(
        l2_l1_link.c.l2_metric_id,
        l2_l1_link.c.l1_metric_id,
        l2_l1_link.c.impact_factor,
    )).all()

    l1_total_change: Dict[int, float] = {m.id: 0.0 for m in l1_metrics}
    for l2_id, l1_id, impact_factor in l2_l1_edges:
        l2_change_pct = l2_total_change.get(l2_id, 0.0)
        change_pct = impact_factor * l2_change_pct
        if l1_id in l1_total_change:
            l1_total_change[l1_id] += change_pct

    for metric in l1_metrics:
        total_change = l1_total_change.get(metric.id, 0.0)
        metric.current_value = _round(metric.default_value + (metric.default_value * total_change))
        metric.improvement_percentage = _round(total_change * 100, 2)

    # ---- Step 3: L1 -> Business Outcome ----------------------------------
    l1_bo_edges = db.execute(select(
        l1_bo_link.c.l1_metric_id,
        l1_bo_link.c.business_outcome_id,
        l1_bo_link.c.impact_factor,
    )).all()

    bo_total_change: Dict[int, float] = {b.id: 0.0 for b in business_outcomes}
    for l1_id, bo_id, impact_factor in l1_bo_edges:
        l1_change_pct = l1_total_change.get(l1_id, 0.0)
        change_pct = impact_factor * l1_change_pct
        if bo_id in bo_total_change:
            bo_total_change[bo_id] += change_pct

    for outcome in business_outcomes:
        total_change = bo_total_change.get(outcome.id, 0.0)
        outcome.current_value = _round(outcome.default_value + (outcome.default_value * total_change))
        outcome.improvement_percentage = _round(total_change * 100, 2)

    db.commit()


def recalculate_and_fetch(db: Session):
    """Runs the cascade then returns fresh ORM objects for the response."""
    recalculate(db)
    return {
        "business_outcomes": db.query(BusinessOutcome).order_by(BusinessOutcome.sort_order, BusinessOutcome.id).all(),
        "l1_metrics": db.query(L1Metric).order_by(L1Metric.sort_order, L1Metric.id).all(),
        "l2_metrics": db.query(L2Metric).order_by(L2Metric.sort_order, L2Metric.id).all(),
        "interventions": db.query(Intervention).order_by(Intervention.sort_order, Intervention.id).all(),
    }
