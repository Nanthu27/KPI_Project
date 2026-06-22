from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..repositories import user_repo
from ..schemas import schemas as sc

router = APIRouter(tags=["Structure & Access Control: User Onboarding"])

# Fixed roster of selectable employees, mirroring the company directory shown
# in the screenshots. Picking a name in the UI auto-fills email + role from
# here rather than requiring free-text entry every time.
EMPLOYEE_ROSTER = {
    "Pratheek Basrithaya": {"email": "basrithaya.5@apac.teleperformance.com", "role": "Admin"},
    "Nithesh": {"email": "saini.1569@apac.teleperformance.com", "role": "Admin"},
    "Udit": {"email": "chauhan.1860@teleperformanceusa.com", "role": "Admin"},
    "Himadri Sarkar": {"email": "Himadri.Sarkar@tp.com", "role": "Admin"},
    "Nandha": {"email": "nandha@tp.com", "role": "Admin"},
    "Pooja Majmudar": {"email": "pooja.majmudar@tp.com", "role": "Admin"},
}


@router.get("/users/roster", response_model=List[str])
def get_roster():
    """Selectable employee names for the Employee Name dropdown."""
    return list(EMPLOYEE_ROSTER.keys())


@router.get("/users", response_model=List[sc.UserOut])
def list_users(db: Session = Depends(get_db)):
    return user_repo.list(db)


@router.post("/users", response_model=sc.UserOut)
def create_user(payload: sc.UserCreate, db: Session = Depends(get_db)):
    roster_entry = EMPLOYEE_ROSTER.get(payload.name)
    email = payload.email or (roster_entry["email"] if roster_entry else f"{payload.name.lower().replace(' ', '.')}@tp.com")
    role = payload.role or (roster_entry["role"] if roster_entry else "Admin")

    obj = User(name=payload.name, email=email, role=role)
    return user_repo.create(db, obj)


@router.put("/users/{user_id}", response_model=sc.UserOut)
def update_user(user_id: int, payload: sc.UserUpdate, db: Session = Depends(get_db)):
    obj = user_repo.get(db, user_id)
    if not obj:
        raise HTTPException(status_code=404, detail="User not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    obj = user_repo.get(db, user_id)
    if not obj:
        raise HTTPException(status_code=404, detail="User not found")
    user_repo.delete(db, obj)
    return {"ok": True}
