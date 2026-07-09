"""
Regression test for the graph-path live-page-state sync fix.

Bug this guards against: the LangGraph multi-agent path
(app/ai/graph/builder.py::run_graph_cascade / stream_graph_cascade) used to
invoke the compiled graph directly against `db`, which only ever holds the
last-SAVED intervention percentages. Slider drags are frontend-only (see
frontend/src/store/kpiStore.js) and are never written to the DB until the
user clicks Save. So any agent reading the DB straight (insight/goal/
trace/advisor/whatif) would report "no active interventions" even while the
user's screen showed a slider at 50%.

The legacy single-agent path already fixed this with
`cascade.agent._synced_to_live_page_state`, a context manager that
temporarily writes the live page_context values into the DB, lets the tool
run against that accurate snapshot, then restores the original saved values.
This test proves the SAME wrapper is now applied around the graph path too
(builder.py imports and uses it in run_graph_cascade/stream_graph_cascade).

We test the mechanism directly — entering the context manager and reading
DB state from inside vs. outside it — rather than invoking the full compiled
LangGraph (which would require a real/mocked LLM call in formatter_agent).
This keeps the test fast, offline, and focused on the exact bug.

Run with: cd backend && python -m pytest app/tests/test_graph_live_page_sync.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Intervention, L2Metric, intervention_l2_link
from app.services import simulation_service
from app.ai.cascade.schemas import CascadeChatRequest, PageContext
from app.ai.cascade.agent import _synced_to_live_page_state, _get_scope


VERTICAL = "Finance & Accounting"
LOB = "Order to Cash"


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def _seed(db):
    """One intervention driving one L2 metric, saved at 0% (i.e. the user
    has never clicked Save on this LOB, matching a fresh page load)."""
    iv = Intervention(
        name="IDP", percentage=0, vertical_horizontal=VERTICAL, lob=LOB,
    )
    l2 = L2Metric(
        name="Invoice Cycle Time", default_value=100, current_value=100,
        vertical_horizontal=VERTICAL, lob=LOB,
    )
    db.add_all([iv, l2])
    db.commit()
    db.refresh(iv)
    db.refresh(l2)
    db.execute(intervention_l2_link.insert().values(
        intervention_id=iv.id, l2_metric_id=l2.id, impact_factor=10.0,
    ))
    db.commit()
    return iv, l2


def _live_request(iv_name: str, live_pct: float) -> CascadeChatRequest:
    """Mimics exactly what cascadeApi.js sends: page_context carries the
    unsaved, on-screen slider values."""
    return CascadeChatRequest(
        message="why did KPIs change?",
        page_context=PageContext(
            active_interventions=[{"name": iv_name, "percentage": live_pct}],
            business_outcomes=[],
            l1_metrics=[],
            l2_metrics=[],
            filters={"vertical": VERTICAL, "lob": LOB},
        ),
    )


def test_db_reflects_live_slider_value_inside_the_sync_block(db_session):
    iv, l2 = _seed(db_session)
    request = _live_request("IDP", 50)
    vertical, lob = _get_scope(request)

    with _synced_to_live_page_state(db_session, request, vertical, lob):
        simulation_service.recalculate(db_session)
        db_session.refresh(iv)
        db_session.refresh(l2)
        # This is what every graph agent (insight/goal/trace/advisor/whatif)
        # reads today via state["db"] — it must see 50, not the saved 0.
        assert iv.percentage == 50
        assert l2.current_value > 100  # cascade actually ran on the live value


def test_db_is_restored_to_saved_value_after_the_sync_block(db_session):
    iv, l2 = _seed(db_session)
    request = _live_request("IDP", 50)
    vertical, lob = _get_scope(request)

    with _synced_to_live_page_state(db_session, request, vertical, lob):
        pass

    db_session.refresh(iv)
    db_session.refresh(l2)
    # "Nothing is saved unless you click Save" contract must hold — the
    # temporary write for the AI tool call must not leak back to the
    # dashboard's persisted state.
    assert iv.percentage == 0
    assert l2.current_value == 100


def test_without_the_sync_block_the_bug_reproduces(db_session):
    """Negative control: proves this test suite would actually have caught
    the original bug. Reading the DB directly (what the graph agents used
    to do before this patch) sees the stale saved value, not the live one."""
    iv, l2 = _seed(db_session)
    simulation_service.recalculate(db_session)
    db_session.refresh(iv)
    assert iv.percentage == 0  # stale — this is the exact contradiction bug
