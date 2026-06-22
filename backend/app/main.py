from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routes import business_outcomes, l1_metrics, l2_metrics, interventions, upload, simulation, structure, users, ai_agents, knowledge_admin
from .seed_data import run_seed

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
app.include_router(ai_agents.router)
app.include_router(knowledge_admin.router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    run_seed()


@app.get("/")
def root():
    return {"status": "ok", "service": "KPI Simulator API"}


@app.get("/health")
def health():
    return {"status": "healthy"}
