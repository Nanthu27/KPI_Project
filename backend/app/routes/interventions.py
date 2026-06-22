from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Intervention
from ..repositories import intervention_repo
from ..schemas import schemas as sc
from ..services import simulation_service
from ..services.serialization_helpers import attach_intervention_l2_links

router = APIRouter(prefix="/interventions", tags=["Interventions"])


@router.get("", response_model=List[sc.Intervention])
def list_interventions(
    vertical_horizontal: Optional[str] = None,
    lob: Optional[str] = None,
    db: Session = Depends(get_db),
):
    items = intervention_repo.list(db, vertical_horizontal, lob)
    attach_intervention_l2_links(db, items)
    return items


@router.post("", response_model=sc.Intervention)
def create_intervention(payload: sc.InterventionCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"l2_links"})
    obj = Intervention(**data)
    obj = intervention_repo.create(db, obj)
    if payload.l2_links:
        intervention_repo.set_l2_links(db, obj.id, payload.l2_links)
    simulation_service.recalculate(db)
    db.refresh(obj)
    attach_intervention_l2_links(db, [obj])
    return obj


@router.put("/{intervention_id}", response_model=sc.Intervention)
def update_intervention(intervention_id: int, payload: sc.InterventionUpdate, db: Session = Depends(get_db)):
    obj = intervention_repo.get(db, intervention_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Intervention not found")
    data = payload.model_dump(exclude_unset=True, exclude={"l2_links"})
    for field, value in data.items():
        setattr(obj, field, value)
    db.commit()
    if payload.l2_links is not None:
        intervention_repo.set_l2_links(db, obj.id, payload.l2_links)
    simulation_service.recalculate(db)
    db.refresh(obj)
    attach_intervention_l2_links(db, [obj])
    return obj


@router.delete("/{intervention_id}")
def delete_intervention(intervention_id: int, db: Session = Depends(get_db)):
    obj = intervention_repo.get(db, intervention_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Intervention not found")
    intervention_repo.delete(db, obj)
    simulation_service.recalculate(db)
    return {"ok": True}
