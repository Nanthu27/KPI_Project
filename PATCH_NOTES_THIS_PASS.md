# Patch notes — this pass

## 0. New: Decision Intelligence Engine (foundational — addresses the gap-analysis' #1 priority)

**Files (new):** `backend/app/ai/services/decision_engine.py`,
`backend/app/migrations.py`
**Files (changed):** `backend/app/models/models.py`, `backend/app/main.py`,
`backend/app/seed_data.py`, `backend/app/schemas/schemas.py`,
`backend/app/ai/tools/kpi_tools.py` (`goal_tool`, `decision_advisor_tool`),
`backend/app/ai/scripts/eval_harness.py`

Across several design-review conversations, the repeated top finding was:
the simulator has a forward *simulation* model (Intervention → L2 → L1 →
BO) but no *decision* model — nothing that turns "reaches the target" into
"is this a good idea" using risk, cost, and confidence, and Decision
Advisor / Goal Agent were independently guessing at that judgment with no
shared definition of "good."

**What was added:**

- `Intervention` gained four admin-configured columns: `risk_level`,
  `cost_level` (`"Low"|"Medium"|"High"`), `effort_weeks`, `confidence_pct`.
  Per the "AI cannot invent business knowledge" principle from those
  reviews, these are metadata an admin sets — never inferred by an LLM.
  Defaults (`Medium`/`Medium`/4 weeks/90%) keep every existing row and
  caller working unchanged.
- `backend/app/migrations.py` — a tiny additive-column migrator (no
  Alembic in this project) so the *already-seeded* `kpi_simulator.db` gets
  these new columns with real per-row values on next startup, instead of
  silently missing them (`Base.metadata.create_all()` only creates
  brand-new tables, never alters existing ones). Verified against a copy
  of the real shipped `kpi_simulator.db`: schema and all 11 existing
  intervention rows migrated correctly, restored the file afterward so the
  migration runs live as designed.
- `decision_engine.py` — the single shared scoring formula:
  `score_scenario(goal_achievement_pct, risk/cost/confidence profile)` →
  one 0–100 composite (default weights 40% goal / 25% risk / 20% cost /
  15% confidence, named constants, not buried in a prompt).
  `profile_settings()` rolls up an intervention mix's risk/cost/confidence
  weighted by how hard each lever is pushed (an intervention pinned at 0%
  doesn't count against the scenario; one at 100% counts fully).
- `decision_advisor_tool` now profiles every strategy through this engine
  and re-ranks by the composite `decision_score` instead of raw
  `avg_bo_improvement` alone, so a strategy that narrowly out-improves
  another using High-risk/High-cost interventions no longer automatically
  outranks a Low-risk near-tie. `risk`, `cost`, `implementation_confidence`,
  `effort_weeks`, `decision_score`, and `recommendation_reason` are now on
  every strategy in the response.
- `goal_tool` now attaches the same profile to every candidate solution
  (`risk`, `cost`, `implementation_confidence`, `decision_score`,
  `recommended`, `recommendation_reason`) without changing which option is
  ranked #1 — Option 1 is still, as before, the reverse solver's closest
  match by gap%, now just with a risk/cost verdict attached rather than a
  bare number.
- `eval_harness.py`'s `decision_advisor_ranks_by_signed_direction_not_raw_magnitude`
  regression guard was updated for the new ranking key: it now asserts
  strategies are sorted by `decision_score` (not raw `avg_bo_improvement`),
  and that a strategy which measurably *hurts* the target outcome can never
  out-score one that helps it, regardless of risk/cost tie-breaking. Full
  suite re-run: **8/8 eval-harness cases pass**, **32/32 relevant pytest
  cases pass** (4 pre-existing, unrelated failures — see below — were
  present before this change too).

**Verified in this sandbox** (network access to PyPI was available, unlike
the previous pass): installed `sqlalchemy`, `fastapi`, `pydantic`, `pytest`,
`python-dotenv`, ran `python -m app.ai.scripts.eval_harness` and
`python -m pytest app/tests/ -q` directly against the real code — not just
`py_compile`. Pre-existing, unrelated failures (present before this change,
not caused by it): `test_rag_service.py` (missing optional `rank-bm25`
dependency in this sandbox) and one floating-point rounding assertion in
`test_simulation.py::test_excel_supplied_17_11_11_outputs` (expects
`97.6481`, gets `97.648` — a `pytest.approx` precision issue unrelated to
interventions/decision logic).

**Explicitly out of scope for this pass** (see the chat-side gap analysis
for the full prioritized backlog): a true LP/constrained optimizer to
replace grid search, AI request/token logging, response caching, prompt
versioning, and a formal dependency-graph module. These are each
substantial, separately-scoped efforts and are listed with recommended
next steps rather than partially bolted on.

---



**Files:** `backend/app/ai/graph/builder.py`

The legacy single-agent path (`cascade/agent.py::run_cascade`) already wraps
every tool call in `_synced_to_live_page_state()` — a context manager that
temporarily writes the frontend's live, unsaved slider values into the DB,
recalculates, lets the tool run against that accurate snapshot, then
restores the original saved values in a `finally` block. This exists
because slider drags never write to the DB until the user clicks Save
(`frontend/src/store/kpiStore.js`), so the DB alone is stale.

That wrapper was never applied to the newer LangGraph multi-agent path
(`run_graph_cascade` / `stream_graph_cascade`). Every agent in
`app/ai/agents/*.py` reads `state["db"]` directly, so switching the
frontend flag `VITE_USE_GRAPH_CASCADE=true` would reproduce the exact
"Active Interventions: None" vs "TP Simulation at 11% each" contradiction
that was already found and fixed in the legacy path — just across every
agent instead of one.

**Fix:** both `run_graph_cascade()` and `stream_graph_cascade()` now wrap
the compiled graph's `.invoke()` / `.stream()` call in the same
`_synced_to_live_page_state(db, request, vertical, lob)` context manager,
imported directly from `cascade.agent` (no logic duplicated).

**New test:** `backend/app/tests/test_graph_live_page_sync.py` — three
tests: (1) DB reflects the live slider value *inside* the sync block, (2)
DB is restored to the saved value *after* the block (the "nothing saves
without clicking Save" contract), (3) a negative control proving the
original bug would actually have failed this suite (reading the DB
directly outside the sync block returns the stale value). Run with:

```bash
cd backend && python -m pytest app/tests/test_graph_live_page_sync.py -v
```

I could not execute this myself in this sandbox (no network access to
install `sqlalchemy`/`fastapi`/etc.) — syntax-checked with `py_compile`
only. Please run it and let me know if anything fails.

## 2. Fixed: frontend tests had no runner

**Files:** `frontend/package.json`, `frontend/vite.config.js`

`frontend/src/__tests__/*.test.js` use Jest-style `describe`/`test`/`expect`
but no test runner was installed and no `test` script existed. Added
`vitest` as a devDependency, a `"test": "vitest run"` script, and a
`test: { globals: true, environment: 'node' }` block in `vite.config.js` so
the existing test files run unmodified (vitest's `globals: true` provides
Jest-compatible globals). Run with:

```bash
cd frontend && npm install && npm test
```

## 3. Fixed: README described the wrong LLM provider

**Files:** `README.md`

The doc described Groq/Llama (`GROQ_API_KEY`, `llama-3.3-70b-versatile`),
but the actual code (`app/ai/config.py`, `_get_gemini_client()` in
`cascade/agent.py`) uses Google Gemini exclusively, with automatic
fallback-model retry on rate limits. Fixed the header note, the
architecture diagram line, and the copy-pasteable Step 3 env block to
match the real Gemini setup. Left a note pointing out that the
troubleshooting table and "LLM Alternatives" table further down are stale
history rather than rewriting every mention.

## 4. Fixed: suggestion buttons could resolve to the wrong agent

**Files:** `frontend/src/ai/store/cascadeStore.js`, `frontend/src/ai/components/CascadePanel.jsx`

Bug report: clicking 🎯 "How can I improve Cash Conversion Cycle?" could
answer with ⭐ Decision Advisor instead of the Goal/Improvement agent.
Root cause: starter buttons sent plain message text with no
`intent_override`, so which agent answered depended entirely on the
LLM/regex classifier's read of that exact wording — which could drift.

**Fix:** every starter now carries a fixed `intent` field, sent through as
`intent_override` (already a first-class, highest-precedence field in
`detect_intent()` / `router_node.py` — just never wired up from the
starters). Mapping now matches the bug report exactly:

| Emoji | Starter | Agent |
|---|---|---|
| 💡 | Why did my KPIs change? | insight |
| 🎯 | How can I improve `<BO>`? | **goal** |
| 🔍 | Trace formula for `<BO>` | trace |
| 📊 | Why did `<intervention>` change things? | insight |
| ⭐ | Recommend the best intervention strategy | advisor |

Free-typed natural-language questions are unaffected — they still go
through the existing LLM/regex classifier, which already had its own
(separately reasoned) insight-vs-advisor split for "how can I improve X"
phrasing.

## 5. Fixed: Goal Agent's unreachable-target reply gave no explanation

**Files:** `backend/app/ai/services/reverse_solver.py`,
`backend/app/ai/tools/kpi_tools.py`, `backend/app/ai/cascade/prompts.py`,
`backend/app/ai/cascade/agent.py`

Bug report: "Target 42.5 cannot be reached. Closest achievable value is
49.98. Gap = 15%." told the user nothing about *why*, which KPI was
limiting it, or what to do next.

**Fix:** `SolverResult` now carries `full_settings` (every intervention's
value in the best-found configuration, including ones left at 0% — the
old `interventions` list filtered those out). `goal_tool` uses this to
compute `limiting_factors`: any intervention pinned at 0% or 100% in the
best-found configuration when the target isn't reachable — a real,
deterministic signal, not a guess. `format_goal_prompt` now requires a
5-section structured reply in the unreachable case: **Definition → Why the
target cannot be reached → Limiting factors → Closest achievable result →
Recommended action**, matching the bug report's spec exactly. The no-LLM
deterministic fallback (`_deterministic_reply_fallback`) got the same
upgrade so the explanation still shows up even if Gemini is unreachable.
Both the legacy single-agent path and the LangGraph multi-agent path share
`goal_tool`/`format_goal_prompt`, so this fix applies to both.

Verified against the real seeded DB with a scenario shaped like the bug
report's own example (target unreachable, closest = 49.98) — see
`backend/app/tests/test_goal_and_whatif_range.py` and the eval harness
below.

## 6. Fixed: out-of-range What-If values were silently clamped

**Files:** `backend/app/ai/services/whatif_service.py`,
`backend/app/ai/cascade/prompts.py`

`evaluate_hypothetical()` used to do
`max(0.0, min(100.0, hypothetical_value))` with no feedback at all — a
user asking "what if RPA Bots were 140%?" silently got a prediction for
100% with no indication their number was ever changed.

**Fix:** out-of-range values are now separated out and reported back as
`out_of_range` (name, requested value, supported min/max, direction)
instead of being silently rewritten; in-range values in the same request
still get a real prediction. `format_whatif_prompt` turns this into the
exact message format requested in the bug report ("Sorry, we can't
provide a prediction for `<name>` at `<value>`% because it exceeds the
maximum supported limit of `<max>`%..."). Note: `Intervention` has no
per-row `min_value`/`max_value` columns (only `BusinessOutcome`/
`L1Metric`/`L2Metric` do — confirmed in `models.py`), so an intervention's
valid range is always 0-100; this is what's now validated against
explicitly instead of implicitly.

Also confirmed (no bug found): the Business Outcome/L1/L2 slider
(`MetricSlider.jsx`) already correctly drags across each metric's real
`min_value`/`max_value`. `InterventionSlider.jsx` was hardcoded to 0-100,
which is actually correct for interventions (no per-row range exists) —
updated it to accept `minValue`/`maxValue` props defaulting to 0/100
anyway, purely for symmetry/forward-compatibility with `MetricSlider`.

## 7. New: Goal Agent / Decision Advisor eval harness

**Files:** `backend/app/ai/scripts/eval_harness.py`,
`backend/app/tests/test_agent_eval_harness.py`

Per the request to "train" the Goal and Decision Advisor agents: since
Gemini isn't fine-tunable through this integration, this formalizes what
`AGENT_TRAINING_NOTES.md` already did by hand — a growing, runnable set of
real queries with checkable expected outcomes, run against the real
deterministic tool layer (`goal_tool`, `decision_advisor_tool`,
`whatif_tool`) and real seeded data, not mocks. Covers: suggestion-button
determinism, the advisor-only-on-explicit-ask boundary, unreachable vs.
reachable goal replies, goal-seeking regex coverage, the historical
Decision Advisor crash (regression guard), the historical "Maximum Push
always wins" ranking bug (regression guard), and What-If range validation.
8/8 cases pass. Run with:

```bash
cd backend && python -m app.ai.scripts.eval_harness      # quick manual run
cd backend && python -m pytest app/tests/test_agent_eval_harness.py -v   # CI
```

Add a new case to `CASES` in `eval_harness.py` the moment a new bug is
found — that's the actual "training loop" available for a hosted,
non-fine-tunable model: tighten the prompt/tool, add the case, make sure
it never regresses silently again.



- **Concurrency**: `_synced_to_live_page_state`, `reverse_solver.py`, and
  `whatif_service.py` all mutate real DB rows and restore them in a
  `finally` block. This is safe for one user at a time but not for two
  concurrent requests against the same LOB (no per-request isolation/lock).
  Fine for a demo; worth a real fix (e.g. a request-scoped in-memory
  recalculation that never touches persisted rows) before multi-user use.
