from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import L1Metric
from ..repositories import l1_metric_repo
from ..schemas import schemas as sc
from ..services import simulation_service
from ..services.serialization_helpers import attach_l1_business_outcome_links

router = APIRouter(prefix="/l1-metrics", tags=["L1 Metrics"])


@router.get("", response_model=List[sc.L1Metric])
def list_l1_metrics(
    vertical_horizontal: Optional[str] = None,
    lob: Optional[str] = None,
    db: Session = Depends(get_db),
):
    items = l1_metric_repo.list(db, vertical_horizontal, lob)
    attach_l1_business_outcome_links(db, items)
    return items


@router.post("", response_model=sc.L1Metric)
def create_l1_metric(payload: sc.L1MetricCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"business_outcome_links"})
    obj = L1Metric(**data, current_value=payload.default_value, improvement_percentage=0.0)
    obj = l1_metric_repo.create(db, obj)
    if payload.business_outcome_links:
        l1_metric_repo.set_business_outcome_links(db, obj.id, payload.business_outcome_links)
    simulation_service.recalculate(db)
    db.refresh(obj)
    attach_l1_business_outcome_links(db, [obj])
    return obj


@router.put("/{metric_id}", response_model=sc.L1Metric)
def update_l1_metric(metric_id: int, payload: sc.L1MetricUpdate, db: Session = Depends(get_db)):
    obj = l1_metric_repo.get(db, metric_id)
    if not obj:
        raise HTTPException(status_code=404, detail="L1 metric not found")
    data = payload.model_dump(exclude_unset=True, exclude={"business_outcome_links"})
    for field, value in data.items():
        setattr(obj, field, value)
    db.commit()
    if payload.business_outcome_links is not None:
        l1_metric_repo.set_business_outcome_links(db, obj.id, payload.business_outcome_links)
    simulation_service.recalculate(db)
    db.refresh(obj)
    attach_l1_business_outcome_links(db, [obj])
    return obj


@router.delete("/{metric_id}")
def delete_l1_metric(metric_id: int, db: Session = Depends(get_db)):
    obj = l1_metric_repo.get(db, metric_id)
    if not obj:
        raise HTTPException(status_code=404, detail="L1 metric not found")
    l1_metric_repo.delete(db, obj)
    return {"ok": True}
