# LangGraph Multi-Agent Layer — What Was Added

This adds a **LangGraph orchestration layer on top of your existing FastAPI Cascade AI**,
exactly per the "wrap, don't rewrite" spec. Nothing in your existing code was removed,
rewritten, or broken. Every new file is additive.

## What already existed (untouched)
- `app/ai/tools/kpi_tools.py` — `insight_tool`, `goal_tool`, `knowledge_tool`,
  `excel_trace_tool`, `decision_advisor_tool`
- `app/ai/cascade/agent.py`, `prompts.py`, `schemas.py` — the original single-agent router
- `app/ai/services/rag_service.py`, `trace_service.py`, `reverse_solver.py`
- The original endpoint `/api/cascade/chat` and `/api/cascade/chat/stream` — still work
  exactly as before (verified with a live test).

## What's new

```
app/ai/graph/
    state.py        ConversationState — the shared TypedDict every node reads/writes
    router_node.py   Classifies intent + which agents are needed (never answers)
    planner_node.py  Turns "needed agents" into an ORDERED execution plan
    edges.py         Conditional routing: skip agents not in the plan
    builder.py       Compiles the StateGraph, exposes run_graph_cascade() / stream_graph_cascade()
    api.py           New router: /api/cascade/graph/chat, /chat/stream, /memory/{id}

app/ai/agents/
    base.py             @node decorator: adds logging + up to 2 retries to every node
    insight_agent.py    Wraps insight_tool (unchanged)
    goal_agent.py        Wraps goal_tool + reuses _extract_goal_params (unchanged)
    knowledge_agent.py   Wraps knowledge_tool / hybrid RAG (unchanged)
    trace_agent.py        Wraps excel_trace_tool + reuses _extract_trace_params (unchanged)
    advisor_agent.py     Wraps decision_advisor_tool (unchanged)
    formatter_agent.py   ONE LLM call that synthesizes whichever agents ran

app/ai/memory/
    memory.py        In-process ConversationMemory keyed by session_id (history,
                      last KPIs, business domain, simulation history)
```

Two small **additive** edits to existing files:
- `app/ai/cascade/schemas.py` — added `session_id` (optional) to `CascadeChatRequest`,
  and new `GraphChatResponse` / `NodeTraceEntry` models. Old fields untouched.
- `app/main.py` — one new import + one new `app.include_router(...)` line.
- `requirements.txt` — added `langgraph>=0.2.20`.

## The graph

```
START -> Router -> Planner -> [Insight] -> [Goal] -> [Knowledge] -> [Trace] -> [Advisor] -> Formatter -> END
```

- **Router** scores the query against the same keyword patterns the old single-agent
  cascade used, but instead of picking ONE tool, it flags every agent whose keywords hit.
  "Why did DSO change and how do I fix it?" → both `insight` and `goal` fire.
- **Planner** takes that unordered set and produces `execution_plan`, a subset of the
  canonical order `[insight, goal, knowledge, trace, advisor]`. Agents not required
  are skipped entirely via conditional edges — no wasted DB/LLM calls.
- **Agents** are 15–40 line wrappers. They call the exact same tool functions as before
  and write only to the state fields they own (no agent ever overwrites another's data).
- Each agent is wrapped with `@node(name)`, which gives it:
  - node-level timing + status pushed into `state["node_trace"]` (observability)
  - up to 2 automatic retries if the tool call raises or returns an `"error"` key
  - errors are captured into `state["errors"]` instead of crashing the graph
- **Formatter** collects whichever `tool_outputs` exist, reuses the existing
  `format_insight_prompt` / `format_goal_prompt` / etc. functions to build one prompt,
  and makes exactly one LLM call for a synthesized, non-repetitive answer.
- **Memory** persists conversation history per `session_id` across turns, in-process.

## New endpoints (old ones untouched)

```
POST /api/cascade/graph/chat          full multi-agent JSON response
POST /api/cascade/graph/chat/stream   SSE: per-node progress events, then the answer
GET    /api/cascade/graph/memory/{session_id}   inspect what's remembered
DELETE /api/cascade/graph/memory/{session_id}   clear a session
```

`GraphChatResponse` is a strict superset of the old `CascadeChatResponse` — it adds
`required_agents`, `execution_plan`, `tool_outputs`, `confidence`, `errors`,
`missing_information`, and `node_trace` for full explainability.

## How to try it

```bash
cd backend
pip install -r requirements.txt --break-system-packages   # adds langgraph
uvicorn app.main:app --reload

curl -X POST http://localhost:8000/api/cascade/graph/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Why did my KPIs change and how do I get DSO below 30?"}'
```

You should see `"execution_plan": ["insight", "goal"]` in the response — proof the
planner dynamically chained two agents for one question, each seeing the previous
agent's output before the Formatter produces one combined answer.

## Verified before delivery
All of the following were run against this exact code (not just written, actually executed):
- Graph compiles (`StateGraph(...).compile()`) with no cycles/dead ends.
- Single-agent query → `execution_plan == ["knowledge"]`.
- Multi-agent query ("why... and how...") → `execution_plan == ["insight", "goal"]`,
  goal agent returned 3 real reverse-solver solutions.
- Advisor query → knowledge + advisor chained, advisor picked a real top strategy
  from the existing `decision_advisor_tool`.
- SSE streaming emits one `progress` event per node, then the final answer, then `[DONE]`.
- A full `TestClient` HTTP request against `/api/cascade/graph/chat` returns `200`.
- The **legacy** `/api/cascade/chat` endpoint was re-tested and still returns `200` with
  the expected shape — zero regressions.

## Fixed during testing (worth knowing about)
Two real bugs were caught by actually running the code, not just reading it:
1. **Deadlock in `memory.py`**: `append_turn()`/`update()` acquired the module lock and
   then called `get()`, which acquired the same lock again. `threading.Lock` isn't
   reentrant, so this hung forever. Fixed with `threading.RLock()`.
2. **DB session silently dropped between nodes**: the SQLAlchemy session was first
   stashed under a private `"__db__"` key not declared in the `ConversationState`
   schema. LangGraph only preserves keys that are part of the declared state schema
   across node hops, so it vanished after the first node. Fixed by declaring `db` as
   a real (if internal-use) field on `ConversationState`.

## Extending it
Adding a new agent (e.g. the Scenario Simulator / KPI Validator / What-If Analyzer
mentioned in the spec) is: write a tool function, wrap it in a `@node("name")` agent
that reads/writes its own state slice, add it to `CANONICAL_ORDER` in
`planner_node.py`, register it in `builder.py`'s `add_node` / conditional-edge loop,
and teach `router_node.py`'s pattern table when it's needed. No existing agent changes.
