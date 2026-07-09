"""
Simulation engine.

Implements BRD section 9 "Calculation Logic" exactly:

  Intervention -> L2 Metrics
    Intervention % = Slider Value / 100
    Change %       = (Impact Factor x Intervention %) / 100
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

Each level's "Total Change %" computed above becomes the upstream input
for the next level, so the three blocks chain together into a single
top-to-bottom recalculation triggered any time an intervention slider
(or a manual override) changes.

`improvement_percentage` on every metric is simply Total Change % * 100,
signed so that the UI can color it green/red depending on whether the
metric's "higher_is_better" flag agrees with the direction of travel.
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
    # edge rows: (intervention_id, l2_metric_id, impact_factor)
    iv_l2_edges = db.execute(select(
        intervention_l2_link.c.intervention_id,
        intervention_l2_link.c.l2_metric_id,
        intervention_l2_link.c.impact_factor,
    )).all()

    intervention_value_by_id: Dict[int, float] = {iv.id: iv.percentage for iv in interventions}

    l2_total_change: Dict[int, float] = {m.id: 0.0 for m in l2_metrics}
    for intervention_id, l2_id, impact_factor in iv_l2_edges:
        # Excel stores a slider value like 17% as 0.17 before applying
        # T = Impact Factor * Intervention New Value % / 100.
        slider_pct = intervention_value_by_id.get(intervention_id, 0.0)
        intervention_fraction = slider_pct / 100.0
        change_pct = (impact_factor * intervention_fraction) / 100.0
        if l2_id in l2_total_change:
            l2_total_change[l2_id] += change_pct

    for metric in l2_metrics:
        total_change = l2_total_change.get(metric.id, 0.0)
        if metric.manual_override and metric.manual_value is not None:
            metric.current_value = metric.manual_value
            # Effective change% from manual value — used as upstream for L1 cascade
            effective_change = (
                (metric.manual_value - metric.default_value) / metric.default_value
                if metric.default_value != 0 else 0.0
            )
            l2_total_change[metric.id] = effective_change
            metric.improvement_percentage = _round(effective_change * 100, 2)
        else:
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
        if metric.manual_override and metric.manual_value is not None:
            metric.current_value = metric.manual_value
            effective_change = (
                (metric.manual_value - metric.default_value) / metric.default_value
                if metric.default_value != 0 else 0.0
            )
            l1_total_change[metric.id] = effective_change
            metric.improvement_percentage = _round(effective_change * 100, 2)
        else:
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
        if outcome.manual_override and outcome.manual_value is not None:
            outcome.current_value = outcome.manual_value
            effective_change = (
                (outcome.manual_value - outcome.default_value) / outcome.default_value
                if outcome.default_value != 0 else 0.0
            )
            outcome.improvement_percentage = _round(effective_change * 100, 2)
        else:
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
