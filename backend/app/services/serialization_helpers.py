"""
Serialization helpers.

SQLAlchemy's `relationship(secondary=...)` exposes the *related row*,
not the association row's extra columns (impact_factor). Rather than
switch to a full association-object mapping (more boilerplate for a
single extra column), we fetch the association rows directly and stick
a plain-Python `linked_business_outcomes` / `linked_l1_metrics` /
`linked_l2_metrics` attribute onto each ORM instance before it's handed
to Pydantic (using names that don't collide with the real relationship
attributes, since SQLAlchemy's instrumented collections reject plain
dicts). The schema then reads this transient attribute via a
`validation_alias`.
"""
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import l1_bo_link, l2_l1_link, intervention_l2_link, BusinessOutcome, L1Metric, L2Metric


def attach_l1_business_outcome_links(db: Session, l1_objs: List[L1Metric]) -> None:
    if not l1_objs:
        return
    ids = [m.id for m in l1_objs]
    rows = db.execute(
        select(l1_bo_link.c.l1_metric_id, l1_bo_link.c.business_outcome_id, l1_bo_link.c.impact_factor, BusinessOutcome.name)
        .join(BusinessOutcome, BusinessOutcome.id == l1_bo_link.c.business_outcome_id)
        .where(l1_bo_link.c.l1_metric_id.in_(ids))
    ).all()
    by_l1 = {}
    for l1_id, bo_id, impact_factor, bo_name in rows:
        by_l1.setdefault(l1_id, []).append({"id": bo_id, "name": bo_name, "impact_factor": impact_factor})
    for m in l1_objs:
        m.linked_business_outcomes = by_l1.get(m.id, [])


def attach_l2_l1_links(db: Session, l2_objs: List[L2Metric]) -> None:
    if not l2_objs:
        return
    ids = [m.id for m in l2_objs]
    rows = db.execute(
        select(l2_l1_link.c.l2_metric_id, l2_l1_link.c.l1_metric_id, l2_l1_link.c.impact_factor, L1Metric.name)
        .join(L1Metric, L1Metric.id == l2_l1_link.c.l1_metric_id)
        .where(l2_l1_link.c.l2_metric_id.in_(ids))
    ).all()
    by_l2 = {}
    for l2_id, l1_id, impact_factor, l1_name in rows:
        by_l2.setdefault(l2_id, []).append({"id": l1_id, "name": l1_name, "impact_factor": impact_factor})
    for m in l2_objs:
        m.linked_l1_metrics = by_l2.get(m.id, [])


def attach_intervention_l2_links(db: Session, interventions: List) -> None:
    if not interventions:
        return
    ids = [iv.id for iv in interventions]
    rows = db.execute(
        select(intervention_l2_link.c.intervention_id, intervention_l2_link.c.l2_metric_id, intervention_l2_link.c.impact_factor, L2Metric.name)
        .join(L2Metric, L2Metric.id == intervention_l2_link.c.l2_metric_id)
        .where(intervention_l2_link.c.intervention_id.in_(ids))
    ).all()
    by_iv = {}
    for iv_id, l2_id, impact_factor, l2_name in rows:
        by_iv.setdefault(iv_id, []).append({"id": l2_id, "name": l2_name, "impact_factor": impact_factor})
    for iv in interventions:
        iv.linked_l2_metrics = by_iv.get(iv.id, [])
