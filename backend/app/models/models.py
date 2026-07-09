"""
ORM models.

Hierarchy (bottom-up, per BRD section 9 "Calculation Logic"):

    Intervention --(impact_factor)--> L2Metric
    L2Metric     --(impact_factor)--> L1Metric
    L1Metric     --(impact_factor)--> BusinessOutcome

Every "child" row above is connected to its parent through a small
association table that also stores the impact_factor for that specific
edge, because the same L2 metric can feed multiple L1 metrics (and vice
versa) with different weights. This mirrors the "Net Impact" /
"Relationships" sheets in the source workbook.

Vertical/Horizontal + LOB act as a simple scoping/filter dimension so
the simulator can show a different metric tree per filter combination,
matching the "Vertical / Horizontal Level" and "LOB" dropdowns in the UI.
"""
from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, Table
)
from sqlalchemy.orm import relationship
from ..database import Base


# ---------------------------------------------------------------------------
# Association tables (store the per-edge impact factor)
# ---------------------------------------------------------------------------

intervention_l2_link = Table(
    "intervention_l2_link",
    Base.metadata,
    Column("intervention_id", Integer, ForeignKey("interventions.id"), primary_key=True),
    Column("l2_metric_id", Integer, ForeignKey("l2_metrics.id"), primary_key=True),
    Column("impact_factor", Float, nullable=False, default=0.0),
)

l2_l1_link = Table(
    "l2_l1_link",
    Base.metadata,
    Column("l2_metric_id", Integer, ForeignKey("l2_metrics.id"), primary_key=True),
    Column("l1_metric_id", Integer, ForeignKey("l1_metrics.id"), primary_key=True),
    Column("impact_factor", Float, nullable=False, default=0.0),
)

l1_bo_link = Table(
    "l1_bo_link",
    Base.metadata,
    Column("l1_metric_id", Integer, ForeignKey("l1_metrics.id"), primary_key=True),
    Column("business_outcome_id", Integer, ForeignKey("business_outcomes.id"), primary_key=True),
    Column("impact_factor", Float, nullable=False, default=0.0),
)


class FilterScope:
    """Mixin: every entity is scoped to a Vertical/Horizontal + LOB filter pair."""
    vertical_horizontal = Column(String, nullable=False, default="Finance & Accounting", index=True)
    lob = Column(String, nullable=False, default="Order to Cash", index=True)
    sort_order = Column(Integer, nullable=False, default=0)


class BusinessOutcome(FilterScope, Base):
    __tablename__ = "business_outcomes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    unit = Column(String, nullable=False, default="%")  # "Days" | "%" | "$"
    min_value = Column(Float, nullable=False, default=0)
    band_min = Column(Float, nullable=False, default=0)  # left edge of the purple "benchmark zone"
    target_value = Column(Float, nullable=False, default=0)  # right edge of the purple "benchmark zone"
    max_value = Column(Float, nullable=False, default=100)
    default_value = Column(Float, nullable=False, default=0)  # baseline before simulation
    current_value = Column(Float, nullable=False, default=0)  # live simulated value
    improvement_percentage = Column(Float, nullable=False, default=0)
    higher_is_better = Column(Integer, nullable=False, default=0)  # 0/1 bool: does up=green?
    manual_override = Column(Integer, default=0)
    manual_value = Column(Float, nullable=True)

    l1_links = relationship(
        "L1Metric", secondary=l1_bo_link, back_populates="business_outcomes"
    )


class L1Metric(FilterScope, Base):
    __tablename__ = "l1_metrics"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    unit = Column(String, nullable=False, default="%")
    min_value = Column(Float, nullable=False, default=0)
    band_min = Column(Float, nullable=False, default=0)
    target_value = Column(Float, nullable=False, default=0)
    max_value = Column(Float, nullable=False, default=100)
    default_value = Column(Float, nullable=False, default=0)
    current_value = Column(Float, nullable=False, default=0)
    improvement_percentage = Column(Float, nullable=False, default=0)
    higher_is_better = Column(Integer, nullable=False, default=0)
    manual_override = Column(Integer, default=0)
    manual_value = Column(Float, nullable=True)

    business_outcomes = relationship(
        "BusinessOutcome", secondary=l1_bo_link, back_populates="l1_links"
    )
    l2_links = relationship(
        "L2Metric", secondary=l2_l1_link, back_populates="l1_metrics"
    )


class L2Metric(FilterScope, Base):
    __tablename__ = "l2_metrics"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    unit = Column(String, nullable=False, default="%")
    min_value = Column(Float, nullable=False, default=0)
    band_min = Column(Float, nullable=False, default=0)
    target_value = Column(Float, nullable=False, default=0)
    max_value = Column(Float, nullable=False, default=100)
    default_value = Column(Float, nullable=False, default=0)
    current_value = Column(Float, nullable=False, default=0)
    improvement_percentage = Column(Float, nullable=False, default=0)
    higher_is_better = Column(Integer, nullable=False, default=0)
    manual_override = Column(Integer, default=0)
    manual_value = Column(Float, nullable=True)

    l1_metrics = relationship(
        "L1Metric", secondary=l2_l1_link, back_populates="l2_links"
    )
    interventions = relationship(
        "Intervention", secondary=intervention_l2_link, back_populates="l2_metrics"
    )


class Intervention(FilterScope, Base):
    __tablename__ = "interventions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    percentage = Column(Float, nullable=False, default=0)  # 0-100 slider value (adoption %)
    description = Column(String, nullable=True)

    # --- Decision-intelligence metadata -----------------------------------
    # Per the "an AI cannot invent business knowledge" principle: risk/cost/
    # effort/confidence are business judgments that must come from admin
    # configuration, not from an LLM guessing at run time. These feed
    # decision_engine.py's scenario scoring (goal achievement + risk + cost
    # + confidence) so Decision Advisor / Goal Agent can rank scenarios by
    # more than raw KPI movement. Defaults ("Medium"/90%) keep existing rows
    # and callers working unchanged.
    risk_level = Column(String, nullable=False, default="Medium")   # "Low" | "Medium" | "High"
    cost_level = Column(String, nullable=False, default="Medium")   # "Low" | "Medium" | "High"
    effort_weeks = Column(Float, nullable=False, default=4.0)       # rough implementation time
    confidence_pct = Column(Float, nullable=False, default=90.0)    # admin's confidence in the impact factors above

    l2_metrics = relationship(
        "L2Metric", secondary=intervention_l2_link, back_populates="interventions"
    )


class Vertical(Base):
    """
    A first-class, manageable 'Vertical / Horizontal Level' instance
    (e.g. 'Finance & Accounting', 'TCO Estimator', 'Sales'). Created via
    the Structure & Access Control > Mapping tab. Each Vertical owns a
    list of LOBs.
    """
    __tablename__ = "verticals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)

    lobs = relationship("LOB", back_populates="vertical", cascade="all, delete-orphan")


class LOB(Base):
    """A Line of Business / sub-instance scoped under a Vertical (e.g. 'Order to Cash')."""
    __tablename__ = "lobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    vertical_id = Column(Integer, ForeignKey("verticals.id"), nullable=False)

    vertical = relationship("Vertical", back_populates="lobs")


class User(Base):
    """An onboarded user with access to the simulator (Structure & Access Control > User Onboarding)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    role = Column(String, nullable=False, default="Admin")
