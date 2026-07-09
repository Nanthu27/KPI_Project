# Cascade AI — AI System Documentation

## Architecture Overview

```
React Frontend
  │
  ├─ CascadeButton.jsx      (floating action button)
  ├─ CascadePanel.jsx       (drawer: chat UI, intent badges, apply button)
  ├─ MarkdownRenderer.jsx   (renders LLM markdown: tables, code, lists)
  │
  └─ cascadeStore.js        (Zustand: messages, streaming state)
       └─ cascadeApi.js     (fetch wrappers: /chat, /chat/stream, /apply)
             │
             ▼ HTTP / SSE
       FastAPI Backend
             │
       /api/cascade/router.py
             │
       agent.py  ←── detect_intent() (keyword scoring, no LLM call)
             │
      ┌──────┼──────────────────────────────────┐
      │      │                                  │
   insight  goal    knowledge   trace    advisor
   _tool   _tool   _tool       _tool    _tool
      │      │         │          │         │
   Live    Reverse   RAG      Trace     Decision
   DB      Solver    Service  Service   Advisor
   (sim)   (oracle)  (BM25+   (DB+      (5 strategy
                     Vector)   Excel)    test loop)
```

## 5 AI Agents (Tools)

| Tool                | Trigger words                                | What it does                                        |
| ------------------- | -------------------------------------------- | --------------------------------------------------- |
| **Insight**   | why, what happened, changed, declined, cause | Reads live simulation state, explains cascade chain |
| **Goal**      | how to reach, target N, below N, reduce to   | Reverse solver: finds IV configs to hit a target    |
| **Knowledge** | what is, define, explain, what are           | Hybrid RAG over KPI definitions, BRD, formulas      |
| **Trace**     | formula, trace, path, hierarchy, cascade     | Maps IV→L2→L1→BO chain with impact factors       |
| **Advisor**   | recommend, best strategy, suggest plan       | Tests 5 strategy configs, ranks by BO improvement   |

## RAG System (Hybrid BM25 + Vector)

```
Query
  │
  ├── BM25 Search (40%)       exact keyword matching
  │   └── rank_bm25 library
  │
  └── Vector Search (60%)     semantic similarity
      ├── LOCAL: deterministic hash-bucket (no keys, no torch)
      └── PINECONE: real sentence embeddings (set PINECONE_API_KEY)
          └── Merged via Reciprocal Rank Fusion (RRF)
                │
           Top 5 chunks
                │
           Prompt builder
                │
           Groq LLM (llama-3.1-70b-versatile)
```

### Knowledge Sources

1. **Built-in** (always available): 14 KPI definitions, formulas, LOB descriptions
2. **docs/\*.txt**: Any .txt files in `backend/docs/` auto-loaded on startup
3. **Pinecone** (optional): BRD.docx + Excel metadata → run `python -m app.ai.scripts.ingest_docs`

## Setup

### Step 1: Get a Groq API Key (Free)

1. Go to https://console.groq.com
2. Create an account → API Keys → Create Key
3. Add to `backend/.env`:
   ```
   GROQ_API_KEY=gsk_your_key_here
   GROQ_MODEL=llama-3.1-70b-versatile
   ```

### Step 2: Install AI Dependencies

```bash
cd backend
pip install groq rank-bm25 python-dotenv python-docx
# Optional for full vector search:
pip install pinecone sentence-transformers
```

### Step 3: Start Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Step 4 (Optional): Ingest Documents into Pinecone

```bash
# Set PINECONE_API_KEY in .env first
cd backend
python -m app.ai.scripts.ingest_docs
```

## API Endpoints

| Endpoint                     | Method | Description                   |
| ---------------------------- | ------ | ----------------------------- |
| `/api/cascade/chat`        | POST   | Standard JSON chat            |
| `/api/cascade/chat/stream` | POST   | Streaming SSE chat            |
| `/api/cascade/apply`       | POST   | Apply AI recommendation to DB |
| `/api/cascade/ingest`      | POST   | Trigger RAG re-ingestion      |
| `/api/cascade/health`      | GET    | Check LLM/RAG status          |

## Key Design Decisions

### Slider changes never save to DB

The frontend maintains `live*` state (liveInterventions, liveL2Metrics, etc.) that is
updated during drag without any API calls. The cascade runs in JavaScript using the same
formula as the Python server. On page refresh, `fetchAll()` calls `/simulation/snapshot`
which restores DB-saved values.

### The `/apply` endpoint is the ONLY way AI writes to DB

When the user clicks "Apply Top Recommendation", `applyRecommendation()` calls `/api/cascade/apply`.
This explicitly persists the AI's suggested values. All other AI operations are read-only.

### Reverse Solver restores DB state after every search

The `ReverseSolver` temporarily commits trial intervention values to the DB (to use the
existing simulation engine as an oracle), then restores the original values in a `finally`
block. This guarantees the DB is never left in a trial state, even if the search crashes.

### Intent detection has no LLM call overhead

Intent is detected by scoring regex patterns against the user message. This is ~0ms vs
~200ms for an extra LLM classification call. The tradeoff: less flexible than LLM routing,
but far faster and free.

## Troubleshooting

| Problem                    | Solution                                                            |
| -------------------------- | ------------------------------------------------------------------- |
| "GROQ_API_KEY is not set"  | Add key to`backend/.env`                                          |
| "unable to reach Groq API" | Check internet access from server; verify key at console.groq.com   |
| BM25 search not working    | `pip install rank-bm25`                                           |
| Pinecone index not found   | Run`python -m app.ai.scripts.ingest_docs`                         |
| Streaming shows no tokens  | Check browser supports EventSource; try`/chat` (non-streaming)    |
| Apply recommendation fails | Check intervention name matches DB (case-insensitive partial match) |
