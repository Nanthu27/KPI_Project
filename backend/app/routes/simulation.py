from typing import Optional, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BusinessOutcome, L1Metric, L2Metric, Intervention
from ..services import simulation_service
from ..services.serialization_helpers import (
    attach_l1_business_outcome_links, attach_l2_l1_links, attach_intervention_l2_links,
)
from ..schemas import schemas as sc

router = APIRouter(tags=["Simulation"])


@router.get("/simulation/snapshot", response_model=sc.SimulationSnapshot)
def get_snapshot(
    vertical_horizontal: Optional[str] = None,
    lob: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Full recalculated snapshot, optionally scoped to a filter combination."""
    data = simulation_service.recalculate_and_fetch(db)

    def scoped(items):
        if vertical_horizontal:
            items = [i for i in items if i.vertical_horizontal == vertical_horizontal]
        if lob:
            items = [i for i in items if i.lob == lob]
        return items

    bo_list = scoped(data["business_outcomes"])
    l1_list = scoped(data["l1_metrics"])
    l2_list = scoped(data["l2_metrics"])
    iv_list = scoped(data["interventions"])

    attach_l1_business_outcome_links(db, l1_list)
    attach_l2_l1_links(db, l2_list)
    attach_intervention_l2_links(db, iv_list)

    return sc.SimulationSnapshot(
        business_outcomes=bo_list,
        l1_metrics=l1_list,
        l2_metrics=l2_list,
        interventions=iv_list,
    )


@router.post("/simulation/reset")
def reset_simulation(db: Session = Depends(get_db)):
    """Resets every Intervention slider to 0 and recalculates the cascade."""
    db.query(Intervention).update({Intervention.percentage: 0})
    db.commit()
    simulation_service.recalculate(db)
    return {"ok": True}


@router.get("/filters/verticals", response_model=List[str])
def list_verticals(db: Session = Depends(get_db)):
    from ..models import Vertical
    rows = db.query(Vertical.name).order_by(Vertical.id).all()
    if rows:
        return [r[0] for r in rows]
    # Fallback: derive from existing metric rows if no Vertical rows exist yet
    # (keeps older databases / Excel-only imports working).
    values = {r[0] for r in db.query(BusinessOutcome.vertical_horizontal).distinct().all()}
    for model in (L1Metric, L2Metric, Intervention):
        values.update(r[0] for r in db.query(model.vertical_horizontal).distinct().all())
    return sorted(values)


@router.get("/filters/lobs", response_model=List[str])
def list_lobs(vertical_horizontal: Optional[str] = None, db: Session = Depends(get_db)):
    from ..models import Vertical, LOB
    if vertical_horizontal:
        vertical = db.query(Vertical).filter(Vertical.name == vertical_horizontal).first()
        if vertical:
            lobs = db.query(LOB.name).filter(LOB.vertical_id == vertical.id).order_by(LOB.id).all()
            if lobs:
                return [l[0] for l in lobs]
    # Fallback: derive from existing metric rows
    values = set()
    for model in (BusinessOutcome, L1Metric, L2Metric, Intervention):
        q = db.query(model.lob)
        if vertical_horizontal:
            q = q.filter(model.vertical_horizontal == vertical_horizontal)
        values.update(r[0] for r in q.distinct().all())
    return sorted(values)
