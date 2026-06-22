"""
Repository layer — thin wrappers around SQLAlchemy queries.
Keeps routes/services free of raw ORM calls so persistence concerns
stay isolated and swappable.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import insert, delete

from ..models import (
    BusinessOutcome, L1Metric, L2Metric, Intervention,
    intervention_l2_link, l2_l1_link, l1_bo_link,
)


# ---------------------------------------------------------------------------
# Business Outcome
# ---------------------------------------------------------------------------

class BusinessOutcomeRepository:
    def list(self, db: Session, vertical_horizontal: Optional[str] = None, lob: Optional[str] = None) -> List[BusinessOutcome]:
        q = db.query(BusinessOutcome)
        if vertical_horizontal:
            q = q.filter(BusinessOutcome.vertical_horizontal == vertical_horizontal)
        if lob:
            q = q.filter(BusinessOutcome.lob == lob)
        return q.order_by(BusinessOutcome.sort_order, BusinessOutcome.id).all()

    def get(self, db: Session, id_: int) -> Optional[BusinessOutcome]:
        return db.query(BusinessOutcome).filter(BusinessOutcome.id == id_).first()

    def create(self, db: Session, obj: BusinessOutcome) -> BusinessOutcome:
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, obj: BusinessOutcome) -> None:
        db.delete(obj)
        db.commit()


# ---------------------------------------------------------------------------
# L1 Metric
# ---------------------------------------------------------------------------

class L1MetricRepository:
    def list(self, db: Session, vertical_horizontal: Optional[str] = None, lob: Optional[str] = None) -> List[L1Metric]:
        q = db.query(L1Metric)
        if vertical_horizontal:
            q = q.filter(L1Metric.vertical_horizontal == vertical_horizontal)
        if lob:
            q = q.filter(L1Metric.lob == lob)
        return q.order_by(L1Metric.sort_order, L1Metric.id).all()

    def get(self, db: Session, id_: int) -> Optional[L1Metric]:
        return db.query(L1Metric).filter(L1Metric.id == id_).first()

    def create(self, db: Session, obj: L1Metric) -> L1Metric:
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, obj: L1Metric) -> None:
        db.delete(obj)
        db.commit()

    def set_business_outcome_links(self, db: Session, l1_id: int, links: List[dict]) -> None:
        db.execute(delete(l1_bo_link).where(l1_bo_link.c.l1_metric_id == l1_id))
        for link in links:
            db.execute(insert(l1_bo_link).values(
                l1_metric_id=l1_id,
                business_outcome_id=link["business_outcome_id"],
                impact_factor=link.get("impact_factor", 0.0),
            ))
        db.commit()


# ---------------------------------------------------------------------------
# L2 Metric
# ---------------------------------------------------------------------------

class L2MetricRepository:
    def list(self, db: Session, vertical_horizontal: Optional[str] = None, lob: Optional[str] = None) -> List[L2Metric]:
        q = db.query(L2Metric)
        if vertical_horizontal:
            q = q.filter(L2Metric.vertical_horizontal == vertical_horizontal)
        if lob:
            q = q.filter(L2Metric.lob == lob)
        return q.order_by(L2Metric.sort_order, L2Metric.id).all()

    def get(self, db: Session, id_: int) -> Optional[L2Metric]:
        return db.query(L2Metric).filter(L2Metric.id == id_).first()

    def create(self, db: Session, obj: L2Metric) -> L2Metric:
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, obj: L2Metric) -> None:
        db.delete(obj)
        db.commit()

    def set_l1_links(self, db: Session, l2_id: int, links: List[dict]) -> None:
        db.execute(delete(l2_l1_link).where(l2_l1_link.c.l2_metric_id == l2_id))
        for link in links:
            db.execute(insert(l2_l1_link).values(
                l2_metric_id=l2_id,
                l1_metric_id=link["l1_metric_id"],
                impact_factor=link.get("impact_factor", 0.0),
            ))
        db.commit()


# ---------------------------------------------------------------------------
# Intervention
# ---------------------------------------------------------------------------

class InterventionRepository:
    def list(self, db: Session, vertical_horizontal: Optional[str] = None, lob: Optional[str] = None) -> List[Intervention]:
        q = db.query(Intervention)
        if vertical_horizontal:
            q = q.filter(Intervention.vertical_horizontal == vertical_horizontal)
        if lob:
            q = q.filter(Intervention.lob == lob)
        return q.order_by(Intervention.sort_order, Intervention.id).all()

    def get(self, db: Session, id_: int) -> Optional[Intervention]:
        return db.query(Intervention).filter(Intervention.id == id_).first()

    def create(self, db: Session, obj: Intervention) -> Intervention:
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, obj: Intervention) -> None:
        db.delete(obj)
        db.commit()

    def set_l2_links(self, db: Session, intervention_id: int, links: List[dict]) -> None:
        db.execute(delete(intervention_l2_link).where(intervention_l2_link.c.intervention_id == intervention_id))
        for link in links:
            db.execute(insert(intervention_l2_link).values(
                intervention_id=intervention_id,
                l2_metric_id=link["l2_metric_id"],
                impact_factor=link.get("impact_factor", 0.0),
            ))
        db.commit()


business_outcome_repo = BusinessOutcomeRepository()
l1_metric_repo = L1MetricRepository()
l2_metric_repo = L2MetricRepository()
intervention_repo = InterventionRepository()


# ---------------------------------------------------------------------------
# Vertical / LOB
# ---------------------------------------------------------------------------

class VerticalRepository:
    def list(self, db: Session) -> List["Vertical"]:
        from ..models import Vertical
        return db.query(Vertical).order_by(Vertical.id).all()

    def get(self, db: Session, id_: int):
        from ..models import Vertical
        return db.query(Vertical).filter(Vertical.id == id_).first()

    def get_by_name(self, db: Session, name: str):
        from ..models import Vertical
        return db.query(Vertical).filter(Vertical.name == name).first()

    def create(self, db: Session, obj):
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, obj) -> None:
        db.delete(obj)
        db.commit()


class LOBRepository:
    def create(self, db: Session, obj):
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def list_for_vertical(self, db: Session, vertical_id: int):
        from ..models import LOB
        return db.query(LOB).filter(LOB.vertical_id == vertical_id).order_by(LOB.id).all()

    def get(self, db: Session, id_: int):
        from ..models import LOB
        return db.query(LOB).filter(LOB.id == id_).first()

    def delete(self, db: Session, obj) -> None:
        db.delete(obj)
        db.commit()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserRepository:
    def list(self, db: Session) -> List["User"]:
        from ..models import User
        return db.query(User).order_by(User.id).all()

    def get(self, db: Session, id_: int):
        from ..models import User
        return db.query(User).filter(User.id == id_).first()

    def create(self, db: Session, obj):
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, obj) -> None:
        db.delete(obj)
        db.commit()


vertical_repo = VerticalRepository()
lob_repo = LOBRepository()
user_repo = UserRepository()
