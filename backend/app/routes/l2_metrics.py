from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import L2Metric
from ..repositories import l2_metric_repo
from ..schemas import schemas as sc
from ..services import simulation_service
from ..services.serialization_helpers import attach_l2_l1_links

router = APIRouter(prefix="/l2-metrics", tags=["L2 Metrics"])


@router.get("", response_model=List[sc.L2Metric])
def list_l2_metrics(
    vertical_horizontal: Optional[str] = None,
    lob: Optional[str] = None,
    db: Session = Depends(get_db),
):
    items = l2_metric_repo.list(db, vertical_horizontal, lob)
    attach_l2_l1_links(db, items)
    return items


@router.post("", response_model=sc.L2Metric)
def create_l2_metric(payload: sc.L2MetricCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"l1_links"})
    obj = L2Metric(**data, current_value=payload.default_value, improvement_percentage=0.0)
    obj = l2_metric_repo.create(db, obj)
    if payload.l1_links:
        l2_metric_repo.set_l1_links(db, obj.id, payload.l1_links)
    simulation_service.recalculate(db)
    db.refresh(obj)
    attach_l2_l1_links(db, [obj])
    return obj


@router.put("/{metric_id}", response_model=sc.L2Metric)
def update_l2_metric(metric_id: int, payload: sc.L2MetricUpdate, db: Session = Depends(get_db)):
    obj = l2_metric_repo.get(db, metric_id)
    if not obj:
        raise HTTPException(status_code=404, detail="L2 metric not found")
    data = payload.model_dump(exclude_unset=True, exclude={"l1_links"})
    for field, value in data.items():
        setattr(obj, field, value)
    db.commit()
    if payload.l1_links is not None:
        l2_metric_repo.set_l1_links(db, obj.id, payload.l1_links)
    simulation_service.recalculate(db)
    db.refresh(obj)
    attach_l2_l1_links(db, [obj])
    return obj


@router.delete("/{metric_id}")
def delete_l2_metric(metric_id: int, db: Session = Depends(get_db)):
    obj = l2_metric_repo.get(db, metric_id)
    if not obj:
        raise HTTPException(status_code=404, detail="L2 metric not found")
    l2_metric_repo.delete(db, obj)
    return {"ok": True}
