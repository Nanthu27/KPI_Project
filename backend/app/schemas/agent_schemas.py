"""
Schemas for the deterministic CalculationEngine outputs and the 5 agent
input/output contracts, matching AI_Agents_Development_Spec.md verbatim
(sections 0-5). These are intentionally separate from schemas.py (the
CRUD schemas) since they represent computation results, not persisted
rows.
"""
from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Section 0: CalculationEngine outputs
# ---------------------------------------------------------------------------

class InterventionChange(BaseModel):
    name: str
    value: float
    impact_factor: float
    affects_l2: Optional[str] = None


class L2Change(BaseModel):
    name: str
    base: float
    new: float
    unit: str
    delta_pct: float


class L1Change(BaseModel):
    name: str
    base: float
    new: float
    unit: str
    delta_pct: float
    target: Optional[float] = None


class BusinessOutcomeChange(BaseModel):
    name: str
    base: float
    new: float
    unit: str
    delta_pct: float


class SimulationResult(BaseModel):
    """Output of CalculationEngine.run_full_simulation() — the ROI Insight Agent's input."""
    lob: str
    vertical: str
    interventions: List[InterventionChange]
    l2_changes: List[L2Change]
    l1_changes: List[L1Change]
    business_outcome_changes: List[BusinessOutcomeChange]
    revenue_impact_pct: float


class CalculationTraceStep(BaseModel):
    step: int
    from_: str = Field(alias="from")
    to: str
    formula: str
    sheet: Optional[str] = None
    row: Optional[int] = None
    weight: Optional[float] = None

    class Config:
        populate_by_name = True


class CalculationTrace(BaseModel):
    """Output of CalculationEngine.trace_calculation() — the Excel Intelligence Agent's input."""
    formula_path: List[CalculationTraceStep]
    values_used: Dict[str, float]
    final_value: float
    final_unit: str


class ReverseSolveResult(BaseModel):
    """Output of CalculationEngine.reverse_solve() — the Goal-Seeking Agent's input."""
    feasible: bool
    recommended_interventions: List[Dict] = Field(default_factory=list)
    projected_outcome: Dict = Field(default_factory=dict)
    confidence_score: float = 0.0
    confidence_basis: str = ""
    max_achievable_value: Optional[float] = None


class ScenarioOption(BaseModel):
    label: str
    interventions: List[Dict]
    total_cost: float
    roi_pct: float
    payback_months: float
    projected_l1_changes: List[Dict] = Field(default_factory=list)
    confidence_score: float = 0.0


class OptimizerResult(BaseModel):
    """Output of CalculationEngine.optimize_under_budget() — the Decision Advisor Agent's input."""
    options: List[ScenarioOption]
    recommended_option_label: Optional[str] = None
    recommendation_basis: Optional[str] = None
    infeasible: bool = False


# ---------------------------------------------------------------------------
# Section 1: ROI Insight Agent
# ---------------------------------------------------------------------------

class ROIInsightRequest(BaseModel):
    vertical_horizontal: str = "Finance & Accounting"
    lob: str = "Order to Cash"
    user_question: Optional[str] = None
    session_id: Optional[str] = None


class ROIInsightResponse(BaseModel):
    response_text: str
    cited_metrics: List[str]
    suggested_followups: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Section 2: Goal-Seeking Agent
# ---------------------------------------------------------------------------

class GoalSeekingRequest(BaseModel):
    vertical_horizontal: str = "Finance & Accounting"
    lob: str = "Order to Cash"
    user_question: str
    locked_interventions: List[int] = Field(default_factory=list)
    session_id: Optional[str] = None


class GoalSeekingPlanItem(BaseModel):
    intervention: str
    recommended_value: float


class GoalSeekingResponse(BaseModel):
    response_text: str
    plan: List[GoalSeekingPlanItem] = Field(default_factory=list)
    projected_outcome: Dict = Field(default_factory=dict)
    confidence_score: float = 0.0
    confidence_band: Literal["high", "moderate", "low"] = "low"
    action_available: Optional[str] = "apply_to_sliders"
    feasible: bool = True
    clarifying_question: Optional[str] = None


# ---------------------------------------------------------------------------
# Section 3: Excel Intelligence Agent
# ---------------------------------------------------------------------------

class ExcelIntelligenceRequest(BaseModel):
    metric_name: str
    metric_level: Literal["intervention", "l2", "l1", "business_outcome"] = "l1"
    user_question: Optional[str] = None
    hypothetical_overrides: Optional[Dict[str, float]] = None


class ExcelTraceStepOut(BaseModel):
    step: int
    description: str
    formula: str
    result: str


class ExcelIntelligenceResponse(BaseModel):
    response_text: str
    trace_steps: List[ExcelTraceStepOut]
    source_citation: str
    is_hypothetical: bool = False


# ---------------------------------------------------------------------------
# Section 4: Knowledge Agent (RAG)
# ---------------------------------------------------------------------------

class KnowledgeRequest(BaseModel):
    user_question: str
    top_k: int = 5
    rerank_top_n: int = 3


class KnowledgeSource(BaseModel):
    doc_type: str
    ref: str


class KnowledgeResponse(BaseModel):
    response_text: str
    sources: List[KnowledgeSource] = Field(default_factory=list)
    redirect_suggested: Optional[str] = None
    not_found: bool = False


# ---------------------------------------------------------------------------
# Section 5: Decision Advisor Agent
# ---------------------------------------------------------------------------

class DecisionAdvisorRequest(BaseModel):
    vertical_horizontal: str = "Finance & Accounting"
    lob: str = "Order to Cash"
    budget: float
    currency: str = "USD"
    user_question: Optional[str] = None


class DecisionAdvisorResponse(BaseModel):
    response_text: str
    recommended_option: Optional[str] = None
    all_options: List[ScenarioOption] = Field(default_factory=list)
    tradeoff_note: Optional[str] = None
    action_available: Optional[str] = "apply_to_sliders"
    infeasible: bool = False


# ---------------------------------------------------------------------------
# Unified chat endpoint (POST /api/agents/chat) + Agent Router
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    vertical_horizontal: str = "Finance & Accounting"
    lob: str = "Order to Cash"
    session_id: Optional[str] = None
    budget: Optional[float] = None


class ChatResponse(BaseModel):
    agent_used: str
    response_text: str
    raw: dict
