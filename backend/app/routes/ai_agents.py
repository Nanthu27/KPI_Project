"""
API routes for the 5 AI agents (spec section "API ENDPOINTS"):
  POST /api/agents/insight    -> ROI Insight Agent
  POST /api/agents/goal       -> Goal-Seeking Agent
  POST /api/agents/excel      -> Excel Intelligence Agent
  POST /api/agents/knowledge  -> Knowledge Agent
  POST /api/agents/decision   -> Decision Advisor Agent
  POST /api/agents/chat       -> Unified entrypoint, routes via agent_router
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.agent_schemas import (
    ROIInsightRequest, ROIInsightResponse,
    GoalSeekingRequest, GoalSeekingResponse,
    ExcelIntelligenceRequest, ExcelIntelligenceResponse,
    KnowledgeRequest, KnowledgeResponse,
    DecisionAdvisorRequest, DecisionAdvisorResponse,
    ChatRequest, ChatResponse,
)
from ..agents.roi_insight_agent import handle_roi_insight
from ..agents.goal_seeking_agent import handle_goal_seeking
from ..agents.excel_intelligence_agent import handle_excel_intelligence
from ..agents.knowledge_agent import handle_knowledge_query
from ..agents.decision_advisor_agent import handle_decision_advisor
from ..agents.agent_router import route_question

router = APIRouter(prefix="/api/agents", tags=["AI Agents"])


@router.post("/insight", response_model=ROIInsightResponse)
def roi_insight_endpoint(request: ROIInsightRequest, db: Session = Depends(get_db)):
    return handle_roi_insight(db, request)


@router.post("/goal", response_model=GoalSeekingResponse)
def goal_seeking_endpoint(request: GoalSeekingRequest, db: Session = Depends(get_db)):
    return handle_goal_seeking(db, request)


@router.post("/excel", response_model=ExcelIntelligenceResponse)
def excel_intelligence_endpoint(request: ExcelIntelligenceRequest, db: Session = Depends(get_db)):
    return handle_excel_intelligence(db, request)


@router.post("/knowledge", response_model=KnowledgeResponse)
def knowledge_endpoint(request: KnowledgeRequest):
    return handle_knowledge_query(request)


@router.post("/decision", response_model=DecisionAdvisorResponse)
def decision_advisor_endpoint(request: DecisionAdvisorRequest, db: Session = Depends(get_db)):
    return handle_decision_advisor(db, request)


@router.post("/chat", response_model=ChatResponse)
def unified_chat_endpoint(request: ChatRequest, db: Session = Depends(get_db)):
    """
    Single chat-box entrypoint (spec section 6.1): routes the free-text
    message to the correct agent via rule-based keyword matching, calls
    it with sensible defaults filled in from the request's vertical/lob/
    budget context, and returns a uniform envelope plus the agent's full
    raw payload so the frontend can render agent-specific rich UI
    (sliders-apply button, source citations, scenario cards, etc.).
    """
    agent_name = route_question(request.message)

    if agent_name == "roi_insight":
        result = handle_roi_insight(db, ROIInsightRequest(
            vertical_horizontal=request.vertical_horizontal, lob=request.lob,
            user_question=request.message, session_id=request.session_id,
        ))
    elif agent_name == "goal_seeking":
        result = handle_goal_seeking(db, GoalSeekingRequest(
            vertical_horizontal=request.vertical_horizontal, lob=request.lob,
            user_question=request.message, session_id=request.session_id,
        ))
    elif agent_name == "excel_intelligence":
        # Best-effort metric name extraction: the request's free text IS the
        # "metric_name" field here; ExcelIntelligenceAgent's TraceEngine lookup
        # already tolerates substring/partial matches.
        result = handle_excel_intelligence(db, ExcelIntelligenceRequest(
            metric_name=request.message, metric_level="l1", user_question=request.message,
        ))
    elif agent_name == "decision_advisor":
        result = handle_decision_advisor(db, DecisionAdvisorRequest(
            vertical_horizontal=request.vertical_horizontal, lob=request.lob,
            budget=request.budget or 0.0, user_question=request.message,
        ))
    else:
        result = handle_knowledge_query(KnowledgeRequest(user_question=request.message))

    return ChatResponse(
        agent_used=agent_name,
        response_text=result.response_text,
        raw=result.model_dump(),
    )
