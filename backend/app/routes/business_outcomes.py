from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BusinessOutcome
from ..repositories import business_outcome_repo
from ..schemas import schemas as sc
from ..services import simulation_service

router = APIRouter(prefix="/business-outcomes", tags=["Business Outcomes"])


@router.get("", response_model=List[sc.BusinessOutcome])
def list_business_outcomes(
    vertical_horizontal: Optional[str] = None,
    lob: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return business_outcome_repo.list(db, vertical_horizontal, lob)


@router.post("", response_model=sc.BusinessOutcome)
def create_business_outcome(payload: sc.BusinessOutcomeCreate, db: Session = Depends(get_db)):
    obj = BusinessOutcome(
        **payload.model_dump(),
        current_value=payload.default_value,
        improvement_percentage=0.0,
    )
    obj = business_outcome_repo.create(db, obj)
    simulation_service.recalculate(db)
    db.refresh(obj)
    return obj


@router.put("/{outcome_id}", response_model=sc.BusinessOutcome)
def update_business_outcome(outcome_id: int, payload: sc.BusinessOutcomeUpdate, db: Session = Depends(get_db)):
    obj = business_outcome_repo.get(db, outcome_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Business outcome not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    simulation_service.recalculate(db)
    db.refresh(obj)
    return obj


@router.delete("/{outcome_id}")
def delete_business_outcome(outcome_id: int, db: Session = Depends(get_db)):
    obj = business_outcome_repo.get(db, outcome_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Business outcome not found")
    business_outcome_repo.delete(db, obj)
    return {"ok": True}
