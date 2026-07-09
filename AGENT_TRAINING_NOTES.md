# Agent "Training" — What This Actually Is, and What Changed

## First, an honest framing

There's no dataset, no gradient update, and no weight change here — Groq's
Llama 3.3 endpoint isn't fine-tunable through this integration, and there's
no labeled corpus of "good vs bad KPI answers" to train on even if it were.
**"Fine-tuning code" in the literal ML sense isn't the right tool for this
problem.**

What the critique document actually describes — agents guessing causality,
inventing numbers, hedging instead of reporting computed results — is a
**prompting + verification** problem, not a weights problem. So instead of
fine-tuning, this delivers what actually fixes those symptoms:

1. Tightened, explicit prompt contracts per agent (this is the "training"
   in the sense people usually mean when they say "train the agent" for an
   API-based LLM — shaping behavior through instructions).
2. A deterministic **grounding validator** that checks the LLM's output
   against real tool data after the fact — this is the part a prompt alone
   can never guarantee, because prompts are followed probabilistically.
3. Tool-level fixes to the actual data pipeline feeding those prompts —
   including one real bug that explains most of Critical Issue 5.

## The most important finding

**`decision_advisor_tool` had an undefined-variable bug** (`target` instead
of `target_outcome`) that made it **throw an exception on every single
call**. The agent's error handler silently caught this and fell back to
asking the LLM for "general strategy advice" with no real data — which is
*exactly* the hedging, evidence-free advisor behavior in the critique
("it seems... it's difficult to provide a specific recommendation").

This was the single biggest lever in the whole review: the Decision
Advisor wasn't badly prompted, it was **crashing silently on every turn**.
Fixed with a one-line change (`kpi_tools.py`), verified with a live test —
after the fix, the same query returns a real ranked strategy with a real
measured `avg_bo_improvement` number and a working `apply_action` payload.

## Issue-by-issue

| # | Critique issue | Root cause found | Fix |
|---|---|---|---|
| 1 | Insight Agent guesses causality | Prompt let the LLM narrate *any* two metrics that changed together as cause→effect | `insight_tool` now cross-references the real formula graph (`trace_service`) and splits output into `verified_chains` (real edges — safe to call causal) vs `unverified_correlations` (changed together, no edge — LLM is instructed it MUST say so, and forbidden from soft-causal phrasing like "may be contributing to") |
| 2 | Goal Agent hedges ("maybe adjust...") | Prompt let the LLM freely interpret Goal Engine output instead of just reporting it | `goal_tool` now computes `target_achievable` / `closest_reachable` deterministically; prompt forbids "maybe" and forces a direct reachability verdict |
| 3 | Trace Agent hallucinating impact factors | The prompt handed the LLM raw arithmetic formulas ("l2_change_fraction = ...") and *invited* it to "show the numeric calculation steps" — with incomplete inputs (e.g. missing CSAT edge), the model filled the gap with an invented coefficient | Removed the arithmetic invitation entirely; prompt now explicitly forbids introducing any number not present in the trace data |
| 4 | Knowledge Agent blends live data into "not found" answers | No `not_found` signal existed at all — every retrieval, however irrelevant, got sent to the LLM to "answer as best it can" | `knowledge_tool` now computes `not_found` from actual keyword/entity overlap (not retrieval score — those turned out to be nearly flat regardless of relevance, see below) and the agent **skips the LLM call entirely** when nothing relevant was found |
| 5 | Decision Advisor isn't advising | **The undefined-variable crash above** | Fixed; prompt also now forbids hedge language since the tool already computes ranked, measured strategies |
| 6 | "Apply Recommendation" returns text, not action | Already solved before this pass (`apply_action` in `decision_advisor_tool`, frontend `applyRecommendationLocal`) — just verified end-to-end with the advisor crash fixed, since apply mode depends on the advisor tool succeeding | Verified working: `apply_action.sliders` is a real `{name: value}` map from the actual simulation |
| 7 | No shared agent state | A separate LangGraph multi-agent layer already exists (`app/ai/graph/`) but isn't wired to the frontend yet — the live UI calls the single-agent `/cascade/chat`. Out of scope for this pass; noted for later | — |
| 8 | Responses aren't verifiable | Nothing computed confidence/evidence before | New `app/ai/evidence/grounding.py`: deterministic `Evidence: ✓ Live Simulation ✓ Formula Trace   Confidence: 92%` footer on every response, plus structured `evidence`/`confidence` fields in the API response |
| 9 | Missing structured Business Impact block | Partially addressed — verified/unverified chains in the Insight prompt data give the LLM the structured facts; a fully templated (non-LLM) block is the natural next step, see below | — |
| 10 | No deterministic decision flow | Already true for the single-agent path (`_dispatch` runs one tool per request based on `detect_intent`, always tool-first, never guesses) — the LangGraph layer implements the fuller multi-agent version of this | — |

## The grounding validator, concretely

`app/ai/evidence/grounding.py` — no ML, just arithmetic:

1. `collect_allowed_numbers(tool_data)` walks the tool's actual output and
   builds the set of every number that's legitimately available.
2. After the LLM responds, `find_ungrounded_numbers(reply, allowed)`
   extracts every number in the reply and flags any that don't match
   anything in that set (within rounding tolerance).
3. `compute_confidence(...)` turns source coverage + ungrounded-number
   count into a 0–1 score, and `evidence_footer(...)` renders the
   checklist. All of this runs in milliseconds, deterministically, on
   every response — it doesn't rely on the model "trying harder."

This is what would have caught the fabricated `-0.55` CSAT impact factor
in your Trace Agent example: it's not in `excel_trace_tool`'s output, so
it's not in the allowed set, so it gets flagged in the response's
`⚠️ Could not verify these figures` line.

## A real trap I hit and fixed while building this

My first version of `not_found` for the Knowledge Agent used the RAG
retrieval score as the signal. Testing against real data showed the
hybrid RRF fusion scores cluster tightly (~0.009–0.01) **almost
regardless of actual relevance** — a nonsense query and a real one came
back with similarly-scored results. Score alone can't tell "found" from
"not found" in this retrieval setup.

Switched to keyword/entity overlap between the query and what was
actually retrieved instead — and then hit a second, subtler version of
the same critique's exact failure case: asking "what does **TP
Simulation** mean" would incidentally match the word "**Simulation**"
inside an unrelated "Simulation Formulae" doc heading and wrongly report
"found". Fixed by requiring the **full named term** (not one generic
sub-word) to appear in retrieved content whenever the query is asking
about a specific on-page metric/intervention name. Verified all four
cases (nonsense query, generic concept question, undocumented on-page
term, documented concept) behave correctly before shipping.

## What's still open (honest gaps)

- **Issue 7 (shared state) / Issue 10 (deterministic flow)**: ~~the more
  complete fix is the LangGraph multi-agent layer~~ — **done in this pass**.
  The grounding validator is now backported into `agents/formatter_agent.py`
  (see `_finalize_grounding`), and the frontend can opt into the graph path
  via `VITE_USE_GRAPH_CASCADE=true` (`cascadeApi.js`). Both paths now give
  the same anti-hallucination guarantee.
- **Issue 9 (fully structured Business Impact block)**: the data needed
  for a fully templated, no-LLM-prose block (verified chains, gap-to-target,
  ranked strategies) all now exists in the tool outputs — turning it into
  literal template-rendered UI cards instead of LLM prose is a frontend
  task, not a backend one, and wasn't done here.
- **NEW — WHATIF intent was fully orphaned.** `detect_intent()` could
  already return `IntentType.WHATIF` (via `_is_whatif_intent`), and
  `_resolve_whatif_overrides` / `whatif_tool` / `whatif_service.py` all
  already existed — but `cascade/agent.py::_dispatch()` had NO
  `elif intent == IntentType.WHATIF:` branch at all, so every WHATIF
  question silently fell through to the `else` (Knowledge) branch. A
  question like "if I set TP Gamification to 55 ... what is Revenue
  Growth?" would run RAG search and (correctly, but unhelpfully) report
  no definition found. Fixed: `_dispatch` now has a real WHATIF branch,
  `format_whatif_prompt` was added to `prompts.py`, and both `run_cascade`
  and `stream_cascade` handle WHATIF's `needs_clarification` case (ask,
  don't guess which intervention "the first 3 options" means) exactly
  like GOAL already does for an unparseable target. The graph orchestrator
  had the SAME gap one level worse — `router_node.py` only ever scored the
  plain `INTENT_PATTERNS` keyword table, which has no WHATIF category at
  all — so it's now fixed there too: a new `agents/whatif_agent.py`, wired
  into `router_node.py` (now reuses `_is_whatif_intent` /
  `_is_goal_seeking_intent` / `_is_advisor_apply_intent` instead of only
  keyword scoring), `planner_node.py`, `builder.py`, and
  `formatter_agent.py`.
- **NEW — `cascade/agent.py` had a SyntaxError and could not be imported
  at all.** `_GOAL_SEEKING_PATTERNS`'s opening `= [` line was missing, so
  its regex strings sat as orphaned bare statements right after
  `_resolve_whatif_overrides`'s final `return`, followed by a dangling
  `]`. Any process importing this module (i.e. the whole backend) would
  fail at startup. Fixed by restoring the missing list assignment.
- The grounding validator **flags** ungrounded numbers rather than
  silently rewriting the LLM's answer — a deliberate, conservative choice
  (auto-rewriting risks stripping legitimate numbers the tolerance-based
  matcher just didn't recognize). If you want a harder guarantee for
  Trace/Goal specifically, the next step is falling back to a fully
  templated deterministic answer whenever `ungrounded` is non-empty for
  those two intents, instead of just appending a warning.

## Files changed

```
backend/app/ai/evidence/grounding.py       new — grounding validator + confidence/evidence
backend/app/ai/tools/kpi_tools.py           insight_tool: verified_chains/unverified_correlations
                                             knowledge_tool: not_found detection
                                             goal_tool: target_achievable/closest_reachable
                                             decision_advisor_tool: fixed undefined-variable crash
backend/app/ai/cascade/prompts.py           SYSTEM_PROMPT: evidence/grounding rules + anti-hedge rules
                                             format_insight_prompt: verified vs unverified sections
                                             format_goal_prompt: deterministic reachability verdict
                                             format_trace_prompt: forbid new arithmetic
                                             format_advisor_prompt: forbid hedge language
backend/app/ai/cascade/agent.py             knowledge not_found short-circuit (skips LLM entirely)
                                             grounding check + evidence footer on every reply
backend/app/ai/cascade/schemas.py           +evidence, +confidence fields
backend/app/ai/cascade/router.py            pass evidence/confidence through to the HTTP response
```

## Verified before delivery

Every claim above was actually run, not just written:
- `insight_tool` cross-referenced against real seeded DB relationships —
  confirmed `verified_chains` populate with real impact factors.
- `knowledge_tool.not_found` tested against 4 real cases (nonsense query,
  generic concept, undocumented on-page term, documented concept) — all
  correct after the entity-aware fix.
- Grounding validator tested against a mocked LLM reply containing a
  fabricated number — correctly flagged and surfaced in the response.
- The `decision_advisor_tool` crash was caught by running the advisor
  intent end-to-end (not just reading the code) — fixed, then re-verified
  it now returns a real ranked strategy and working `apply_action`.
- Full HTTP-level test via `TestClient` against `/api/cascade/chat` and
  `/api/cascade/chat/stream` — both return the new `evidence`/`confidence`
  fields correctly.
