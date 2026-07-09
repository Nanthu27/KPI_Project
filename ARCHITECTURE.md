# KPI Simulator — Production AI Architecture

This describes the system **as it actually exists in this codebase** after
this pass — not a proposed redesign. Where I changed something, it's called
out explicitly with the file touched.

## 0. The core principle: nothing about a metric is hardcoded, anywhere

There is no `RevenueGrowthFormula` class, no `if metric_name == "NPS"` branch,
and no metric/intervention name baked into backend or agent code. Every KPI,
intervention, Vertical, and LOB is a **row in the database**
(`app/models/models.py`): `BusinessOutcome`, `L1Metric`, `L2Metric`,
`Intervention`, connected by association tables that carry the
**impact_factor** for that specific edge:

```
Intervention --(impact_factor)--> L2Metric --(impact_factor)--> L1Metric --(impact_factor)--> BusinessOutcome
```

Adding a brand-new KPI, a new intervention, or a whole new Vertical/LOB
requires **zero code changes** — it's a row insert via the
`Structure & Access Control` UI / `/structure` API. The calculation engine,
the RAG ingestion, and every AI agent all read names and values live from
this schema. This is the dynamic architecture; it was already true in the
uploaded project and this pass verified/hardened it rather than rebuilding it.

## 1. Two engines, cleanly separated

| Engine | Lives in | Does |
|---|---|---|
| **Calculation Engine** | `app/services/simulation_service.py` | One generic cascade function (`recalculate()`) that walks Intervention→L2→L1→BusinessOutcome using only the DB's `impact_factor` edges. No AI, no RAG, 100% deterministic, runs in milliseconds. |
| **Reverse Solver (Goal Seek)** | `app/ai/services/reverse_solver.py` | Given a target value for any metric, searches the same live graph to find intervention combinations that reach it — the "Excel Goal Seek / Solver" pattern, over real edges, not invented ones. |

Neither engine calls an LLM. This is what makes every number in the app
**reproducible and auditable** — the same inputs always produce the same
outputs, and any AI agent that reports a number is reporting *this* engine's
output, never its own arithmetic.

## 2. RAG is scoped to knowledge, never to formulas

`app/ai/services/rag_service.py` (hybrid BM25 + Pinecone) only ever indexes
the BRD and business-concept text (`docs/BRD.docx`,
`docs/kpi_formula_knowledge.txt`) for the **Knowledge Agent** to explain
*what a metric means* or *why a relationship exists*. It never supplies the
number a metric currently holds, and it never supplies an impact factor —
those always come from the DB via the Calculation Engine. This is the
"don't RAG the formulas" principle, and it's already how the code is wired.

## 3. The multi-agent orchestrator (LangGraph)

```
      USER
        │
        ▼
    Router (keyword/intent detection, no LLM)
        │
        ▼
    Planner (builds an execution_plan: which agents actually need to run)
        │
   ┌────┼──────────┬───────────┬────────────┬─────────────┐
   ▼    ▼          ▼           ▼            ▼             │
Insight Goal   Knowledge     Trace       Advisor           │
(live   (Goal  (BRD RAG —    (dependency  (ranked           │
 sim)    Seek   knowledge     path from    strategy from    │
         engine) only)        real edges)  live sim)        │
   └────┴──────────┴───────────┴────────────┴───────────────┘
                        │
                        ▼
                   Formatter Agent
        (ONE LLM call: synthesizes only the agents
         that ran, into one coherent explanation)
                        │
                        ▼
              Grounding Validator (deterministic, no LLM)
        - collect_allowed_numbers(): every real number the
          agents actually returned
        - find_ungrounded_numbers(): flag anything in the
          LLM's prose that doesn't match a real number
        - compute_confidence() + evidence_footer()
                        │
                        ▼
              Final answer + Evidence + Confidence
```

Every agent (`app/ai/agents/*.py`) is a thin wrapper around a pre-existing,
deterministic tool in `app/ai/tools/kpi_tools.py` — the agent's job is to
call the tool, not to compute anything itself. The LLM only ever narrates
structured data it was handed; it's never the source of a number.

### What changed in this pass

The multi-agent graph (`app/ai/graph/`) already existed but its Formatter
only computed a rough confidence rollup — it did **not** run the same
grounding validator the older single-agent path (`/api/cascade/chat`) used.
That gap is closed:

- `app/ai/agents/formatter_agent.py` — now runs the identical
  `collect_allowed_numbers` / `find_ungrounded_numbers` / `compute_confidence`
  / `evidence_footer` pipeline as the legacy path, generalized to the union
  of every agent that ran in a turn (not just one intent).
- `app/ai/graph/state.py` — added `evidence` / `ungrounded_numbers` as
  first-class state fields (LangGraph only preserves declared fields).
- `app/ai/cascade/schemas.py` — `GraphChatResponse` now also returns
  `evidence` and `ungrounded`, matching what `/cascade/chat` already returns.
- `app/ai/graph/api.py`, `app/ai/graph/builder.py` — pass those fields
  through to the HTTP/SSE response.
- `frontend/src/ai/services/cascadeApi.js` — added a
  `VITE_USE_GRAPH_CASCADE=true` build flag so the UI can point at
  `/api/cascade/graph/chat` (full multi-agent, full explainability) instead
  of the legacy single-tool `/api/cascade/chat`, without any other frontend
  code changes (the response shape is a superset).

Both endpoints now give the **same anti-hallucination guarantee**: any
number in a reply that isn't backed by a real tool call is flagged with
`⚠️ Could not verify these figures against simulation data`, never silently
presented as fact.

## 4. Why this satisfies "no static data, everything dynamic, no hallucination"

- **No static data**: every metric/intervention name, value, and
  relationship is a live DB row; RAG only carries prose explanations, never
  numbers used in an answer.
- **No hallucination path**: the LLM is structurally prevented from being
  the source of a number — it only narrates tool output — and the grounding
  validator catches anything that slips through in phrasing, deterministically,
  after every single response.
- **Production-ready**: deterministic core (calculation + goal-seek) is
  separated from the explanatory layer (LLM), so scaling/repricing/switching
  LLM providers never risks the correctness of a single simulated number.

## 5. Request flow, end to end

1. User drags an intervention slider (or types a chat question).
2. `simulation_service.recalculate()` (or the goal-seek engine) updates every
   downstream metric from live DB edges — this happens whether or not the
   user ever opens the chat panel.
3. If the user asks the AI a question, the Router/Planner picks the minimal
   set of agents needed; each agent calls its tool, which reads the *same*
   live DB state (never a cached or hardcoded snapshot).
4. The Formatter makes exactly one LLM call to turn that structured data
   into prose, then the grounding validator checks the prose against the
   data before it's returned.
5. The response carries `evidence` + `confidence` so the UI (and the user)
   can see exactly what was verified, not just what was said.
