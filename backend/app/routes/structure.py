from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Vertical, LOB
from ..repositories import vertical_repo, lob_repo
from ..schemas import schemas as sc

router = APIRouter(tags=["Structure & Access Control: Mapping"])


@router.get("/verticals/detailed", response_model=List[sc.VerticalOut])
def list_verticals_detailed(db: Session = Depends(get_db)):
    """Full Vertical objects (with nested LOBs) for the Mapping admin screen."""
    return vertical_repo.list(db)


@router.post("/verticals", response_model=sc.VerticalOut)
def create_vertical(payload: sc.VerticalCreate, db: Session = Depends(get_db)):
    existing = vertical_repo.get_by_name(db, payload.name)
    if existing:
        raise HTTPException(status_code=400, detail="A Vertical/Horizontal Level with this name already exists")

    vertical = Vertical(name=payload.name)
    vertical = vertical_repo.create(db, vertical)

    for lob_name in payload.lobs:
        if lob_name and lob_name.strip():
            lob_repo.create(db, LOB(name=lob_name.strip(), vertical_id=vertical.id))

    db.refresh(vertical)
    return vertical


@router.delete("/verticals/{vertical_id}")
def delete_vertical(vertical_id: int, db: Session = Depends(get_db)):
    obj = vertical_repo.get(db, vertical_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Vertical not found")
    vertical_repo.delete(db, obj)
    return {"ok": True}


@router.post("/verticals/{vertical_id}/lobs", response_model=sc.LOBOut)
def add_lob(vertical_id: int, payload: sc.LOBCreate, db: Session = Depends(get_db)):
    vertical = vertical_repo.get(db, vertical_id)
    if not vertical:
        raise HTTPException(status_code=404, detail="Vertical not found")
    lob = LOB(name=payload.name, vertical_id=vertical_id)
    return lob_repo.create(db, lob)


@router.delete("/lobs/{lob_id}")
def delete_lob(lob_id: int, db: Session = Depends(get_db)):
    obj = lob_repo.get(db, lob_id)
    if not obj:
        raise HTTPException(status_code=404, detail="LOB not found")
    lob_repo.delete(db, obj)
    return {"ok": True}
