from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Suppress the LangChainPendingDeprecationWarning from langgraph's internal
# JsonPlusSerializer about the future change to 'allowed_objects'. This fires
# at import time and cannot be addressed by passing constructor arguments from
# application code — it is an internal library warning that does not affect
# runtime behaviour of this application.
import warnings
warnings.filterwarnings(
    "ignore",
    message=".*allowed_objects.*",
    category=DeprecationWarning,
)

from .database import Base, engine
from .routes import business_outcomes, l1_metrics, l2_metrics, interventions, upload, simulation, structure, users
from .ai.cascade.router import router as cascade_router
from .ai.graph.api import router as cascade_graph_router
from .seed_data import run_seed
from .migrations import run_lightweight_migrations

app = FastAPI(
    title="KPI Simulator API",
    description="Backend for the KPI Simulator: cascading Intervention -> L2 -> L1 -> Business Outcome calculation engine.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(business_outcomes.router)
app.include_router(l1_metrics.router)
app.include_router(l2_metrics.router)
app.include_router(interventions.router)
app.include_router(upload.router)
app.include_router(simulation.router)
app.include_router(structure.router)
app.include_router(users.router)
app.include_router(cascade_router, prefix="/api")        # → /api/cascade/chat etc.
app.include_router(cascade_graph_router, prefix="/api")   # → /api/cascade/graph/chat etc.


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations(engine)
    run_seed()


@app.get("/")
def root():
    return {"status": "ok", "service": "KPI Simulator API"}


@app.get("/health")
def health():
    return {"status": "healthy"}
