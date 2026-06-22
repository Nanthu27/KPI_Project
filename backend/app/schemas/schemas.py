"""
Pydantic schemas — request/response contracts for the API.

Naming convention:
  XBase    -> shared fields
  XCreate  -> payload for POST
  XUpdate  -> payload for PUT (all optional, partial update)
  X        -> full response model (includes id + computed fields)
"""
from typing import Optional, List
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

class LinkedParent(BaseModel):
    """A lightweight reference to a parent-level entity + the edge's impact factor."""
    id: int
    name: str
    impact_factor: float

    class Config:
        from_attributes = True


class MetricBase(BaseModel):
    name: str
    unit: str = "%"
    min_value: float = 0
    band_min: float = 0
    target_value: float = 0
    max_value: float = 100
    default_value: float = 0
    higher_is_better: bool = False
    vertical_horizontal: str = "Finance & Accounting"
    lob: str = "Order to Cash"
    sort_order: int = 0


class MetricUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    min_value: Optional[float] = None
    band_min: Optional[float] = None
    target_value: Optional[float] = None
    max_value: Optional[float] = None
    default_value: Optional[float] = None
    higher_is_better: Optional[bool] = None
    vertical_horizontal: Optional[str] = None
    lob: Optional[str] = None
    sort_order: Optional[int] = None


class MetricOut(MetricBase):
    id: int
    current_value: float
    improvement_percentage: float

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Business Outcome
# ---------------------------------------------------------------------------

class BusinessOutcomeCreate(MetricBase):
    benchmark_factor: float = 0.45


class BusinessOutcomeUpdate(MetricUpdate):
    benchmark_factor: Optional[float] = None


class BusinessOutcome(MetricOut):
    benchmark_factor: float = 0.45


# ---------------------------------------------------------------------------
# L1 Metric
# ---------------------------------------------------------------------------

class L1MetricCreate(MetricBase):
    business_outcome_links: List[dict] = Field(
        default_factory=list,
        description='[{"business_outcome_id": 1, "impact_factor": -0.25}, ...]',
    )


class L1MetricUpdate(MetricUpdate):
    business_outcome_links: Optional[List[dict]] = None


class L1Metric(MetricOut):
    business_outcomes: List[LinkedParent] = Field(default_factory=list, validation_alias="linked_business_outcomes")

    class Config:
        from_attributes = True
        populate_by_name = True


# ---------------------------------------------------------------------------
# L2 Metric
# ---------------------------------------------------------------------------

class L2MetricCreate(MetricBase):
    l1_links: List[dict] = Field(
        default_factory=list,
        description='[{"l1_metric_id": 1, "impact_factor": -0.25}, ...]',
    )


class L2MetricUpdate(MetricUpdate):
    l1_links: Optional[List[dict]] = None


class L2Metric(MetricOut):
    l1_metrics: List[LinkedParent] = Field(default_factory=list, validation_alias="linked_l1_metrics")

    class Config:
        from_attributes = True
        populate_by_name = True


# ---------------------------------------------------------------------------
# Intervention
# ---------------------------------------------------------------------------

class InterventionBase(BaseModel):
    name: str
    percentage: float = 0
    description: Optional[str] = None
    vertical_horizontal: str = "Finance & Accounting"
    lob: str = "Order to Cash"
    sort_order: int = 0
    max_value: float = 100
    cost_per_unit: float = 0.0


class InterventionCreate(InterventionBase):
    l2_links: List[dict] = Field(
        default_factory=list,
        description='[{"l2_metric_id": 1, "impact_factor": 0.15}, ...]',
    )


class InterventionUpdate(BaseModel):
    name: Optional[str] = None
    percentage: Optional[float] = None
    description: Optional[str] = None
    vertical_horizontal: Optional[str] = None
    lob: Optional[str] = None
    sort_order: Optional[int] = None
    max_value: Optional[float] = None
    cost_per_unit: Optional[float] = None
    l2_links: Optional[List[dict]] = None


class Intervention(InterventionBase):
    id: int
    l2_metrics: List[LinkedParent] = Field(default_factory=list, validation_alias="linked_l2_metrics")

    class Config:
        from_attributes = True
        populate_by_name = True


# ---------------------------------------------------------------------------
# Aggregate / simulation response
# ---------------------------------------------------------------------------

class SimulationSnapshot(BaseModel):
    """Returned after any mutation that should re-trigger the cascade."""
    business_outcomes: List[BusinessOutcome]
    l1_metrics: List[L1Metric]
    l2_metrics: List[L2Metric]
    interventions: List[Intervention]


class ExcelUploadResult(BaseModel):
    business_outcomes_created: int
    l1_metrics_created: int
    l2_metrics_created: int
    interventions_created: int
    warnings: List[str] = []


# ---------------------------------------------------------------------------
# Vertical / LOB (Structure & Access Control > Mapping)
# ---------------------------------------------------------------------------

class LOBCreate(BaseModel):
    name: str


class LOBOut(BaseModel):
    id: int
    name: str
    vertical_id: int

    class Config:
        from_attributes = True


class VerticalCreate(BaseModel):
    name: str
    lobs: List[str] = Field(default_factory=list)


class VerticalOut(BaseModel):
    id: int
    name: str
    lobs: List[LOBOut] = []

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Users (Structure & Access Control > User Onboarding)
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    name: str
    email: Optional[str] = None
    role: str = "Admin"


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str

    class Config:
        from_attributes = True
