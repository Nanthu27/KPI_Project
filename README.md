# KPI Simulator + Cascade AI — Production Documentation

> **Version:** 2.0 | **Stack:** React + FastAPI + Google Gemini LLM + Hybrid RAG  
>
> **Note:** this document originally described a Groq/Llama backend from an
> earlier iteration. The codebase now calls Google Gemini exclusively
> (`app/ai/config.py`, `_get_gemini_client()` in `cascade/agent.py`), with an
> automatic fallback model (`gemini-2.5-flash` -> `gemini-2.5-flash-lite`) on
> rate limits. The Groq-specific instructions further down (env vars,
> troubleshooting rows, "LLM Alternatives" table) are stale and kept only for
> history -- use the Gemini setup in `backend/.env` / `app/ai/config.py` as
> the source of truth.
> **Status:** Production-ready | **Last updated:** June 2026

---

## Table of Contents

1. [What This System Does](#1-what-this-system-does)
2. [Architecture Overview](#2-architecture-overview)
3. [All 5 AI Agents — How They Work](#3-all-5-ai-agents)
4. [Hybrid RAG System](#4-hybrid-rag-system)
5. [Calculation Engine & Formulas](#5-calculation-engine--formulas)
6. [Slider Interaction Rules](#6-slider-interaction-rules)
7. [Setup & Installation](#7-setup--installation)
8. [File Structure](#8-file-structure)
9. [API Reference](#9-api-reference)
10. [AI Agent Conditions — Verification](#10-ai-agent-conditions--verification)
11. [Troubleshooting](#11-troubleshooting)
12. [LLM Alternatives (Free)](#12-llm-alternatives-free)

---

## 1. What This System Does

The KPI Simulator is a **real-time business simulation platform** that:

- Lets users drag intervention sliders (0–100%) and instantly see how changes cascade through a 4-level KPI hierarchy
- Includes an **Cascade AI** with 5 specialized agents that explain results, recommend strategies, and trace formulas — using only your **actual live data** (not generic examples)
- Supports any industry vertical (Health Insurance, Finance, Manufacturing, etc.) — all metric names are dynamic
- Generates **PDF snapshots** of the current dashboard state
- Uses **Hybrid RAG** (BM25 keyword + vector search) over your uploaded BRD and Excel files

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      React Frontend                         │
│  KPI Dashboard (sliders, cards) + Cascade AI Panel         │
│  Zustand state | Live cascade (JS) | PDF download          │
└───────────────────┬─────────────────────────────────────────┘
                    │ HTTP / SSE streaming
┌───────────────────▼─────────────────────────────────────────┐
│                   FastAPI Backend                            │
│  /simulation/snapshot  /api/cascade/chat/stream             │
│  /filters  /interventions  /l1-metrics  /l2-metrics  /bos  │
└──────┬─────────────────────┬────────────────────────────────┘
       │                     │
┌──────▼──────┐   ┌──────────▼──────────────────────────────┐
│  SQLite DB  │   │         Cascade AI Engine                │
│  Metrics    │   │  Intent Detection (keyword scoring)      │
│  Relations  │   │       ↓                                  │
│  Impact     │   │  Tool Dispatch (5 agents)                │
│  Factors    │   │       ↓                                  │
└─────────────┘   │  Hybrid RAG (BM25 + LocalVector/Pinecone)│
                  │       ↓                                  │
                  │  Context Builder (live page data)        │
                  │       ↓                                  │
                  │  Google Gemini (gemini-2.5-flash)        │
                  │       ↓                                  │
                  │  SSE Streaming Response                  │
                  └──────────────────────────────────────────┘
```

---

## 3. All 5 AI Agents

### How Intent Detection Works

No extra LLM call. The system scores keyword patterns against the user message:

```python
INSIGHT  → "why", "what happened", "changed", "declined", "cause"
GOAL     → "how to reach", "below N", "target N", "improve to"
TRACE    → "formula", "trace", "path", "how calculated", "cascade"
ADVISOR  → "recommend", "best strategy", "which intervention", "optimal"
KNOWLEDGE→ "what is", "define", "explain", "mean"
```

Highest score wins. If tied → KNOWLEDGE. Zero matches → KNOWLEDGE.

---

### Agent 1: 💡 Insight Agent

**Purpose:** Explain why KPIs changed after slider adjustments.

**What it does:**
1. Calls `simulation_service.recalculate_and_fetch(db)` — reads live DB state
2. Finds all interventions with `percentage > 0` (active sliders)
3. Finds all metrics where `|improvement_percentage| >= 0.1%`
4. Attaches relationship links (which IV drives which L2, etc.)
5. Sends this real data to Groq LLM with the instruction to trace the cascade

**Example trigger:** "Why did my KPIs change?"

**Output guarantees:**
- Uses ONLY metric names from your actual DB
- Shows exact cascade: Intervention → L2 → L1 → Business Outcome
- If nothing changed, says "no sliders are active" and explains how to start

---

### Agent 2: 🎯 Goal Agent (Reverse Solver)

**Purpose:** Find what slider values achieve a target KPI value.

**Algorithm:**
```
1. Extract target metric name from message (reads pageContext for real names)
2. Run ReverseSolver.solve():
   - Strategy A: Grid search over [25, 50, 75, 100]% for each IV (≤3 IVs = exhaustive)
   - Strategy B: Perturb best candidate (±10-20%) — 15 iterations
   - Strategy C: Single-IV focus sweep (10-100% in 10% steps) for each IV
3. Each evaluation: commit trial values to DB → recalculate → read result → restore
4. Rank by |achieved - target|
5. Return top 3 solutions with confidence rating
```

**Confidence:**
- `gap_pct < 5%` → High confidence
- `gap_pct < 15%` → Medium confidence  
- `gap_pct >= 15%` → Low (target may be unreachable with current impact factors)

**IMPORTANT:** The DB is always restored after search. Trial values never persist.

---

### Agent 3: 📚 Knowledge Agent (RAG)

**Purpose:** Answer "what is X?" and formula questions.

**Search order:**
1. BM25 keyword search (40% weight) — exact term matching
2. Local vector search (60% weight) — hash-based semantic similarity
3. Pinecone vector search (if `PINECONE_API_KEY` set) — true semantic search
4. Reciprocal Rank Fusion (RRF) merges results
5. Top 5 chunks sent to LLM

**Knowledge sources (search priority):**
| Priority | Source | How to add |
|----------|---------|------------|
| 1 | Your BRD.docx / Excel | Run `python -m app.ai.scripts.ingest_docs` |
| 2 | `backend/docs/*.txt` files | Drop .txt files in folder, restart server |
| 3 | Built-in generic concepts | Always available, no setup |

**The built-in knowledge is generic (not Finance-specific).** It covers: KPI hierarchy concept, cascade formula, impact factors, slider rules, Excel upload — NOT DSO, RPA, O2C, etc.

---

### Agent 4: 🔍 Trace Agent

**Purpose:** Show the formula path for any metric in your hierarchy.

**What it reads:**
1. First tries your Excel file (if present at `backend/docs/`)
2. Falls back to DB relationships (`intervention_l2_link`, `l2_l1_link`, `l1_bo_link` tables)

**Output includes:**
- Upstream: what drives the metric (with real impact factors)
- Downstream: what the metric drives
- Full chain: `Intervention_1 → L2_Metric_1 → L1_Metric_1 → BO_1`

---

### Agent 5: ⭐ Advisor Agent

**Purpose:** Recommend the best intervention strategy.

**Algorithm:**
```
5 strategy templates tested against your real simulation engine:
  1. Maximum Automation Push — prioritizes IDP/document/automation interventions at 100%
  2. Balanced Digital Transformation — all interventions at 60%
  3. Workflow-First Approach — prioritizes workflow/process at 90%
  4. Analytics-Led Strategy — prioritizes analytics/AI/ML at 90%
  5. Quick Wins Focus — moderate push on IDP/RPA/document at 75%

For each strategy:
  a. Apply settings to DB
  b. Run simulation_service.recalculate()
  c. Read Business Outcome improvement_percentage values
  d. Compute avg improvement
  e. Restore original values

Rank by avg_bo_improvement (highest = best)
```

**The `Apply Top Recommendation` button:**
- Parses intervention names + values from the AI response
- Calls `POST /api/cascade/apply` which persists values to DB
- Triggers `fetchAll()` to update all sliders

---

## 4. Hybrid RAG System

```
User Query
    │
    ├─ BM25 Search (weight: 1 - hybrid_alpha = 0.4)
    │   └─ rank_bm25 → exact keyword matching
    │
    └─ Vector Search (weight: hybrid_alpha = 0.6)
        ├─ Local hash-bucket (zero deps, always available)
        └─ Pinecone (if PINECONE_API_KEY set) — true semantic

Both results → Reciprocal Rank Fusion (RRF, k=60)
    │
Top 5 chunks → Context Builder → Groq LLM
```

### Adding your own documents to RAG

**Option A — Drop files in `backend/docs/`:**
```
backend/docs/
  my_brd.txt          ← plain text from your BRD
  formulas.txt        ← formula documentation
  metric_definitions.txt
```
The RAG service auto-loads all `.txt` files on startup. Restart the server.

**Option B — Ingest into Pinecone (full semantic search):**
```bash
# Set PINECONE_API_KEY in .env first
cd backend
python -m app.ai.scripts.ingest_docs
```
This processes: `backend/docs/*.txt`, BRD.docx (if present), built-in knowledge.

**Option C — Check `/api/cascade/health` to verify what's loaded:**
```json
{
  "rag_documents": 25,
  "bm25": "active",
  "pinecone_connected": false,
  "mode": "BM25 + local vectors"
}
```

---

## 5. Calculation Engine & Formulas

**From BRD Section 9 — implemented exactly in `simulation_service.py`:**

### Intervention → L2 Metric
```
change_fraction = (Impact_Factor × slider_pct) / 100 / 100
# Note: slider_pct is stored as integer (11 = 11%) → divide by 100 twice

Total_Change_Fraction = Σ change_fraction from all linked interventions
New_Value = Default_Value × (1 + Total_Change_Fraction)
improvement_percentage = Total_Change_Fraction × 100
```

### L2 Metric → L1 Metric
```
change_fraction = Impact_Factor × L2_Total_Change_Fraction
Total_Change_Fraction = Σ change_fraction from all linked L2 metrics
New_Value = Default_Value × (1 + Total_Change_Fraction)
```

### L1 Metric → Business Outcome
```
change_fraction = Impact_Factor × L1_Total_Change_Fraction
Total_Change_Fraction = Σ change_fraction from all linked L1 metrics
New_Value = Default_Value × (1 + Total_Change_Fraction)
```

### Example (Intervention_1 = 11%, Impact Factor = 10):
```
L2 change_fraction = (10 × 11) / 100 / 100 = 0.011 = 1.1%
L2 new value = 24 × (1 + 0.011) = 24.264
```

---

## 6. Slider Interaction Rules

| Slider type | What recalculates | Saved to DB? |
|-------------|-------------------|--------------|
| Intervention drag | L2 → L1 → BO (full cascade) | ❌ Never (frontend-only) |
| L2 drag | L1 → BO (partial cascade) | ❌ Never |
| L1 drag | BO only | ❌ Never |
| BO drag | Only that card | ❌ Never |
| "Apply Recommendation" | All linked metrics | ✅ Yes (explicit user action) |
| "Save" / "Create" / "Update" | That record | ✅ Yes |
| Page refresh | Restores DB values | — |

**Cascade runs in JavaScript (frontend) during drag for real-time feel.**  
**Server recalculates on page load via `/simulation/snapshot`.**

---

## 7. Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js 18+
- A free Groq API key: https://console.groq.com

### Step 1: Clone / unzip
```bash
unzip cascade.zip
cd cascade
```

### Step 2: Backend setup
```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Activate (Mac/Linux)
source venv/bin/activate

# if broken
# Set-ExecutionPolicy RemoteSigned -Scope CurrentUser

# .\venv\Scripts\Activate.ps1

# python -m uvicorn app.main:app --reload --port 8000
# or
# .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000



# Install dependencies
pip install -r requirements.txt

# Copy and fill in environment file
copy .env.example .env    # Windows
cp .env.example .env      # Mac/Linux
```

### Step 3: Configure .env
```env
# REQUIRED: Google Gemini (free at https://aistudio.google.com/apikey)
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODEL=gemini-2.5-flash-lite

# OPTIONAL — for full Pinecone vector search
PINECONE_API_KEY=pcsk_your_key_here
PINECONE_INDEX=kpi-cascade-dev
PINECONE_ENV=gcp-starter

# RAG tuning (these defaults work well)
RAG_TOP_K=5
BM25_TOP_K=10
HYBRID_ALPHA=0.6
```

### Step 4: Start backend
```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

Verify: http://localhost:8000/api/cascade/health

### Step 5: Frontend setup
```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:5173

### Step 6: Add your documents (optional)
```bash
# Drop .txt files in:
backend/docs/

# Restart backend — they auto-load into BM25 + local vector search
```

---

## 8. File Structure

```
cascade/
├── backend/
│   ├── .env                          ← API keys (never commit)
│   ├── .env.example                  ← Template
│   ├── requirements.txt
│   ├── docs/                         ← Drop .txt files here for RAG
│   └── app/
│       ├── main.py                   ← FastAPI app, route registration
│       ├── database.py               ← SQLite connection
│       ├── seed_data.py              ← Sample data seeder
│       ├── models/models.py          ← SQLAlchemy models
│       ├── services/
│       │   ├── simulation_service.py ← Core cascade engine (BRD formulas)
│       │   ├── excel_service.py      ← Excel upload parser
│       │   └── serialization_helpers.py
│       ├── routes/                   ← REST endpoints
│       └── ai/
│           ├── config.py             ← AI settings (model, RAG params)
│           ├── cascade/
│           │   ├── agent.py          ← Intent detection + tool dispatch + LLM
│           │   ├── prompts.py        ← System prompt + 5 tool formatters
│           │   ├── router.py         ← /api/cascade/* endpoints
│           │   └── schemas.py        ← Request/response models
│           ├── tools/
│           │   └── kpi_tools.py      ← 5 tool functions
│           └── services/
│               ├── rag_service.py    ← Hybrid BM25 + vector RAG
│               ├── reverse_solver.py ← Goal-seeking oracle
│               ├── trace_service.py  ← Formula path tracer
│               └── page_context_service.py
│
└── frontend/
    └── src/
        ├── App.jsx                   ← Main layout + pageContext wiring
        ├── store/kpiStore.js         ← Zustand: live state, cascade, fetch
        ├── ai/
        │   ├── components/
        │   │   ├── CascadePanel.jsx  ← Chat UI, agents, apply button
        │   │   ├── CascadeButton.jsx ← Floating action button
        │   │   └── MarkdownRenderer.jsx
        │   ├── store/cascadeStore.js ← Chat state, dynamic starters
        │   └── services/cascadeApi.js← SSE streaming fetch
        └── components/
            ├── Header.jsx            ← Download PDF button
            ├── KPICard.jsx           ← Metric card with slider
            ├── MetricSlider.jsx      ← Drag slider, auto-range
            └── InterventionCard.jsx  ← IV slider card
```

---

## 9. API Reference

### Cascade Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/cascade/chat` | Standard JSON chat (non-streaming) |
| POST | `/api/cascade/chat/stream` | SSE streaming chat (recommended) |
| POST | `/api/cascade/apply` | Apply AI recommendation to simulator |
| POST | `/api/cascade/ingest` | Re-trigger RAG document ingestion |
| GET | `/api/cascade/health` | Check LLM, RAG, Pinecone status |

### Stream Response Format
```
data: {"intent":"advisor","tool":"decision_advisor","followups":["..."]}   ← first event
data: {"chunk":"The Rank 1..."}   ← LLM tokens (many of these)
data: [DONE]                       ← stream end
```

### Apply Request Format
```json
POST /api/cascade/apply
{
  "interventions": [
    {"name": "Intervention_1", "value": 60},
    {"name": "Intervention_2", "value": 60}
  ]
}
```

### Simulation Snapshot
```
GET /simulation/snapshot?vertical_horizontal=Health+Insurance&lob=Insurance
```
Returns all interventions, L2/L1 metrics, and business outcomes with cascaded values.

---

## 10. AI Agent Conditions — Verification

| # | Condition | Status | Evidence |
|---|-----------|--------|---------|
| 1 | All 5 agents working | ✅ | Intent routing in agent.py dispatches to correct tool |
| 2 | Readable for new users | ✅ | Structured markdown, numbered options, color-coded metrics |
| 3 | Multiple agents | ✅ | 5 agents, single entry point, keyword intent routing |
| 4 | Hybrid RAG (BM25 + vector) | ✅ | RRF fusion in rag_service.py |
| 5 | docs/ folder for RAG | ✅ | `_load_local_docs()` auto-reads all .txt files on startup |
| 6 | BRD + Excel formulas | ✅ | trace_service.py reads Excel; simulation_service.py implements BRD §9 |
| 7 | Advisor apply button | ✅ | Parses IV names+values from response, calls /apply |
| 8 | All agents use formulas | ✅ | Tools read from DB/simulation engine, never reimplements math |
| 9 | Production-ready | ✅ | Error handling, restore-after-search, DB never left in trial state |
| 10 | Slider cascade correct | ✅ | JS cascade in kpiStore.js mirrors Python simulation_service.py |
| 11 | Free LLM alternatives | ✅ | See section 12 |

---

## 11. Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Optional is not defined` | Missing import in config.py | Add `from typing import Optional` |
| `model llama-3.1-70b-versatile decommissioned` | Old model name | Set `GROQ_MODEL=llama-3.3-70b-versatile` in .env |
| `Cannot reach AI service: Error 400` | Wrong model name | See above |
| `Cannot reach AI service: Error 401` | Bad API key | Check GROQ_API_KEY in .env |
| `No module named 'rank_bm25'` | Missing package | `pip install rank-bm25` |
| `No module named 'groq'` | Missing package (optional) | `pip install groq` (HTTP fallback active without it) |
| Starters show "DSO" / "RPA" | Old hardcoded store | Update cascadeStore.js to dynamic buildStarters() |
| AI uses wrong metric names | pageContext not passed | Verify App.jsx passes liveInterventions/liveBusinessOutcomes |
| Pinecone index not found | Index not created | Run `python -m app.ai.scripts.ingest_docs` |
| PDF download not working | Browser blocks print | Allow print dialog in browser settings |

---

## 12. LLM Alternatives (Free)

All alternatives use the same API format. Change `GROQ_MODEL` in `.env`:

| Provider | Model | Free Tier | Change needed |
|----------|-------|-----------|---------------|
| **Groq** ✅ | `llama-3.3-70b-versatile` | 14,400 req/day | Default — no change |
| **Groq** | `llama-3.1-8b-instant` | 14,400 req/day | `GROQ_MODEL=llama-3.1-8b-instant` |
| **Groq** | `mixtral-8x7b-32768` | 14,400 req/day | `GROQ_MODEL=mixtral-8x7b-32768` |
| **Ollama** (local) | `llama3.2` | Unlimited (local) | Change base URL in agent.py |
| **OpenRouter** | `meta-llama/llama-3.3-70b` | $1 free credit | Change base URL + API key |

### Switch to Ollama (fully local, no API key):
```python
# In backend/app/ai/cascade/agent.py, change base URL:
self.url = "http://localhost:11434/v1/chat/completions"  # Ollama OpenAI-compatible endpoint
```
```bash
# Then run:
ollama pull llama3.2
ollama serve
```

### For Pinecone (free vector DB):
- Sign up at https://app.pinecone.io
- Create an index named `kpi-cascade-dev`, dimension=384, metric=cosine
- Add key to .env → run ingest script

---

## Key Design Decisions

1. **Slider changes never save to DB** — frontend-only state, restored on refresh
2. **Intent detection = keyword scoring** — zero LLM overhead for routing
3. **Reverse solver uses DB as oracle** — never reimplements cascade math
4. **Dynamic starters** — built from live metric names, never hardcoded
5. **System prompt forbids inventing metric names** — LLM must use only pageContext names
6. **DB restore after every advisor/goal search** — guaranteed, runs in `finally` block
7. **RAG built-ins are generic** — no Finance-specific terms that bleed into other verticals

