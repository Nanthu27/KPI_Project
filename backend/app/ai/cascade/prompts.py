"""
Cascade AI Prompts
-------------------
CRITICAL RULE in SYSTEM_PROMPT:
  The LLM must ONLY use metric/intervention names that appear in the
  "Current Page — Live KPI Data" block. It must NEVER invent names like
  DSO, RPA, Collection Efficiency, etc. unless those names actually appear
  in the live data passed to it.
"""

SYSTEM_PROMPT = """You are the Cascade AI — an AI assistant embedded in a KPI simulation platform.

## CRITICAL RULE — Dynamic Data Only
You MUST answer using ONLY the metric names, intervention names, and KPI values that appear in the "Current Page — Live KPI Data" section below. 

NEVER use or invent names that are not in the live data — including "DSO", "RPA", "IDP", "Collection Efficiency", "Days Sales Outstanding", "ROI", "O2C", "P2P", or any other Finance-specific term — unless those exact names appear in the data provided to you.

The user's simulator may contain Health Insurance, Manufacturing, Retail, or any industry. Respond to THEIR actual data.

## Your Role
Help users understand, analyze, and improve their KPI simulation results. You have access to 5 tools:
1. **Insight** — explains WHY KPIs changed (reads live DB data)
2. **Goal** — finds HOW to reach a target value (reverse solver)
3. **Knowledge** — answers definition questions (RAG search)
4. **Trace** — shows FORMULA PATHS through the hierarchy
5. **Advisor** — RECOMMENDS the best intervention strategies

## Rules
- NEVER invent KPI values. All numbers come from the simulation engine.
- NEVER assume what industry or vertical the user is in.
- When the live data block says "Active Interventions: None", tell the user to drag a slider.
- When tool data is provided, base your answer on it exactly.
- Keep responses under 300 words unless asked for detail.

## Evidence & Grounding Rules — READ CAREFULLY
These rules exist because this product makes business decisions. A wrong
number or an invented cause is worse than no answer.

1. **Verified vs. unverified.** Some tool data is split into "verified"
   (backed by a real formula edge / impact factor / Goal Engine solution)
   and "unverified" (metrics that merely changed at the same time, with no
   confirmed link). For verified relationships you may describe A driving
   B. For unverified ones you MUST say they "changed in the same
   simulation run" or "changed together" — NEVER say one "caused",
   "is causing", "led to", "is due to", or "is driving" the other, and
   NEVER use hedged-causal phrasing either ("may be contributing to",
   "is likely due to", "which is contributing to") — that is still an
   unverified causal claim, just softened.
2. **Never do new arithmetic.** If a formula, coefficient, or calculation
   step is not explicitly given to you in the tool data below, do not
   compute it, estimate it, or make one up to "complete the picture".
   Say the calculation isn't available instead.
3. **Never hedge on things the tool already computed.** If tool data gives
   you a definite number (a Goal Engine solution, a ranked strategy's
   measured improvement), state it directly. Do not write "maybe",
   "it's difficult to provide a specific recommendation", "it might be
   helpful to", or similar — the tool already did that work; your job is
   to report it, not to re-guess it.
4. **Knowledge questions answer only from retrieved documents.** If asked
   what something means/is, and the retrieved knowledge doesn't define
   it, say a definition wasn't found in the knowledge base. Do not then
   pivot to explaining it from live simulation data instead — that is a
   different tool with different evidence, and mixing them is exactly
   what makes an answer hard to trust.
5. **Every number you write must appear in the data given to you below**
   (allowing for reasonable rounding/formatting). If you're not looking
   at a number in the data, don't write it.

## Response Structure — Conversational, Progressive
Write like a knowledgeable colleague answering in chat — never like a report.

STRICT RULES:
- NEVER use section labels or headers of any kind — no "Key Takeaway:", no "Insight:", no "Discrepancy:", no "### Analysis", no bold headers used as titles. Just write sentences and paragraphs.
- Split your answer into chunks separated by a line containing only `<!--MORE-->`.
- The FIRST chunk is the preview: the single most important point, in roughly 40-100 words, ending on a complete sentence. Never trail off mid-thought. This is what the user sees immediately, so it must stand alone, answer the question, and give enough context to actually be useful — a single short sentence is NOT enough, even if it's technically true. Include the key number(s) AND a bit of the "why" or "so what" behind them.
- Each chunk after the first should read as a natural continuation of the one before it — like the conversation is still flowing, not restarting under a new heading. Don't repeat anything already said in an earlier chunk.
- Break naturally: one idea or theme per chunk (e.g. what happened → why it happened → what to do next), each still just a short paragraph or two, not a labeled section.
- Use short paragraphs and whitespace. Use bullets only when listing 3+ comparable items (like strategy options), never to restate prose.
- Bold the specific numbers and metric/intervention names that matter (e.g. **Revenue Growth fell 2.3%**) instead of using headers to draw attention.
- Use an occasional relevant emoji (📊 📈 📉 ✅ ⚠️ 💡 🎯) where it genuinely adds clarity — e.g. ⚠️ before a trade-off, 💡 before a suggestion. Don't decorate every line; one or two per response is plenty.
- If nothing more needs saying, it's fine to have only one chunk (no marker at all).

Example (Insight intent) — notice the verified link is stated as driving the outcome, while the co-occurring metric is explicitly flagged as unconfirmed rather than folded into the same causal sentence:
```
**Revenue Growth dropped 2.3%.** The verified path is **TP Simulation → NPS (+3.9%) → Revenue Growth**, with a confirmed impact factor at each step. **AHT also rose 1.8%** in this same run, but there's no confirmed formula link from TP Simulation to AHT in the current data — it changed alongside the drop, not because of it as far as the verified chain shows.
<!--MORE-->
If you want to confirm what's actually driving AHT, 💡 ask me to trace AHT specifically — that'll pull its real upstream relationships instead of guessing from timing alone.
```

## Format
- Use → to show cascade chains inline (e.g. TP Simulation → AHT → CSAT), but ONLY for chains explicitly marked verified in the data below.
- No markdown headers (#, ##, ###) anywhere in the response
"""


def format_insight_prompt(tool_data: dict, user_query: str) -> str:
    active = tool_data.get("active_interventions", [])
    changed_bos = tool_data.get("changed_business_outcomes", [])
    changed_l1s = tool_data.get("changed_l1_metrics", [])
    changed_l2s = tool_data.get("changed_l2_metrics", [])
    verified_chains = tool_data.get("verified_chains", [])
    unverified = tool_data.get("unverified_correlations", [])

    lines = ["## Live Simulation State (from DB)\n"]

    if active:
        lines.append("**Active Interventions:**")
        for iv in active:
            lines.append(f"  - {iv['name']}: {iv['percentage']}%")
        lines.append("")
    else:
        lines.append("**Active Interventions:** None — all sliders at 0%\n")

    if changed_bos:
        lines.append("**Business Outcomes Changed:**")
        for m in changed_bos:
            lines.append(f"  - **{m['name']}**: {m['default']} → {m['current']} ({m['improvement_pct']:+.2f}%)")
        lines.append("")

    if changed_l1s:
        lines.append("**L1 Metrics Changed:**")
        for m in changed_l1s[:5]:
            lines.append(f"  - {m['name']}: {m['default']} → {m['current']} ({m['improvement_pct']:+.2f}%)")
        lines.append("")

    if changed_l2s:
        lines.append("**L2 Metrics Changed:**")
        for m in changed_l2s[:5]:
            lines.append(f"  - {m['name']}: {m['default']} → {m['current']} ({m['improvement_pct']:+.2f}%)")
        lines.append("")

    if not (changed_bos or changed_l1s or changed_l2s):
        lines.append(
            "**No KPI changes detected.** All metrics are at their baseline (default) values.\n"
            "This means no intervention slider has been moved yet.\n"
        )

    # ── Verified vs. unverified — this is the ONLY source of truth for
    # causal language. See SYSTEM_PROMPT "Evidence & Grounding Rules".
    if verified_chains:
        lines.append("**VERIFIED Cascade Chains (real formula edges — safe to describe as cause → effect):**")
        for c in verified_chains:
            lines.append(f"  - {c['from']} → {c['to']}  (impact factor {c['impact_factor']:+.3f}, {c['level']})")
        lines.append("")
    else:
        lines.append("**VERIFIED Cascade Chains:** none found connecting the active interventions to the changed metrics below.\n")

    if unverified:
        lines.append(
            "**UNVERIFIED Correlations (changed in this same run, but NO confirmed formula "
            "edge links them to an active intervention — you MUST describe these as "
            "'changed together' / 'no confirmed link', never as caused):**"
        )
        for name in unverified:
            lines.append(f"  - {name}")
        lines.append("")

    lines.append(f"## User Question\n{user_query}\n")
    lines.append(
        "Explain what changed. For the VERIFIED chains, you may describe the cascade path as "
        "cause → effect, citing the impact factor. For anything in UNVERIFIED Correlations, "
        "explicitly say there is no confirmed formula link — do not imply causation, even "
        "softly. Only use the metric and intervention names shown above."
    )
    return "\n".join(lines)


def format_goal_prompt(tool_data: dict, user_query: str) -> str:
    target = tool_data.get("target_metric", "")
    target_val = tool_data.get("target_value", 0)
    solutions = tool_data.get("solutions", [])
    error = tool_data.get("error")
    target_achievable = tool_data.get("target_achievable")
    closest = tool_data.get("closest_reachable")

    if error:
        return (
            f"## Goal Seeking Error\n{error}\n\n"
            f"## User Question\n{user_query}\n\n"
            "Explain the error and suggest the user adjust sliders manually."
        )

    lines = [f"## Goal Seeking Result\n", f"**Target:** {target} = {target_val}\n"]

    if solutions:
        lines.append("**Top Configurations Found (computed by the Goal Engine — state these exactly):**")
        for sol in solutions:
            iv_str = ", ".join(f"{iv['name']} at {iv['value']}%" for iv in sol["interventions"])
            lines.append(
                f"\n**Option {sol['rank']}** ({sol['confidence']} confidence):\n"
                f"  Interventions: {iv_str}\n"
                f"  Achieves **{target} = {sol['achieved_value']}** (gap from target: {sol['gap_pct']:.1f}%)"
            )
        lines.append("")
        if target_achievable:
            lines.append(
                f"**Reachability verdict (already decided by the Goal Engine — state this plainly, "
                f"do not re-evaluate it yourself): Target IS reachable.** Option 1's exact "
                f"configuration gets within {closest['gap_pct']:.1f}% of {target_val} — this is "
                f"THE recommended plan, not merely one candidate among several."
            )
        else:
            lines.append(
                f"**Reachability verdict (already decided by the Goal Engine — state this plainly, "
                f"do not re-evaluate it yourself): Target is NOT exactly reachable with current "
                f"interventions.** The closest achievable value is **{closest['achieved_value']}** "
                f"(gap {closest['gap_pct']:.1f}%) using Option 1's configuration. Present this as the "
                f"maximum reachable outcome, not as a guess."
            )
            limiting_factors = tool_data.get("limiting_factors") or []
            lf_str = (
                ", ".join(f"{lf['name']} is already at its {lf['at']}" for lf in limiting_factors)
                if limiting_factors
                else "no single intervention is pinned at an extreme in this configuration — the "
                     "combination as a whole has already been pushed as far as the model allows"
            )
            lines.append(
                "\n**Structure the reply with these exact sections, in this order, because the "
                "target is NOT reachable (do not skip any of them):**\n"
                f"1. **Definition** — one or two sentences on what {target} measures.\n"
                "2. **Why the target cannot be reached** — state plainly that the Goal Engine has "
                f"already searched the full range of every intervention and the minimum/maximum "
                f"achievable {target} under the current model relationships is "
                f"**{closest['achieved_value']}** (gap {closest['gap_pct']:.1f}% from the requested "
                f"{target_val}), so {target_val} sits outside the feasible solution space with the "
                "levers currently available.\n"
                f"3. **Limiting factors** — name the specific driver(s) preventing further movement: "
                f"{lf_str}. Explain in one sentence that these are constraints imposed by the "
                "prediction model, not something the user forgot to try.\n"
                f"4. **Closest achievable result** — state the requested target ({target_val}), the "
                f"best achievable value ({closest['achieved_value']}), the absolute difference, and "
                f"the percentage gap ({closest['gap_pct']:.1f}%).\n"
                "5. **Recommended action** — list Option 1's exact intervention values (from above) "
                "as the configuration that gets closest to the metric under the current model, and "
                "say this is the best available outcome given current constraints."
            )
        lines.append(
            "\n**IMPORTANT — Option 1 above is the ONLY answer to give.** The other options "
            "(2, 3, ...) are listed purely for your own context about the shape of the search "
            "space; do not present any of them as THE recommendation, even if their gap_pct "
            "looks similar to Option 1's. If the user's follow-up explicitly asks for a "
            "cheaper/alternative option, you may then mention Option 2 by name — but the default "
            "answer to \"what should I change\" is always Option 1's exact intervention values, "
            "matching what the Recommendation Card on screen shows. Never describe Option 2 or 3's "
            "numbers as if they were Option 1's."
        )
    else:
        lines.append("No solutions found. The target may be outside the achievable range with current impact factors.")

    lines.append(f"\n## User Question\n{user_query}\n")
    lines.append(
        "Present the Goal Engine's results exactly as computed — do not say 'maybe' or 'it might be "
        "necessary to adjust' about anything already decided above. State the reachability verdict "
        "directly, then the recommended option's exact intervention values. "
        "Only use the metric and intervention names shown above. "
        "End your reply with one short line pointing the user at the Recommendation Card in the "
        "panel above this chat to actually apply the change — e.g. \"Open the recommendation above "
        "and tap Apply to move your sliders to this plan.\" Do not describe the card as already open "
        "or already applied; it starts collapsed and the user has to tap it."
    )
    return "\n".join(lines)


def format_whatif_prompt(tool_data: dict, user_query: str) -> str:
    """Format the result of a hypothetical forward simulation — the user
    stated specific intervention values and asked what a metric/Business
    Outcome would become (as opposed to format_goal_prompt, which searches
    FOR values, or format_insight_prompt, which explains the currently
    SAVED state). See services/whatif_service.py::evaluate_hypothetical."""
    error = tool_data.get("error")
    if error:
        return (
            f"## What-If Simulation Error\n{error}\n\n"
            f"## User Question\n{user_query}\n\n"
            "Explain the error and suggest the user try again with clearer values."
        )

    if tool_data.get("needs_clarification"):
        unresolved = tool_data.get("unresolved_names", [])
        available = tool_data.get("available_interventions", [])
        return (
            "## What-If Simulation — Could Not Resolve Intervention Names\n"
            f"The following names from the question did not match a real intervention: "
            f"{', '.join(unresolved) if unresolved else '(none parsed)'}.\n"
            f"Real interventions available on this page: {', '.join(available[:12])}\n\n"
            f"## User Question\n{user_query}\n\n"
            "Do NOT guess a result. Ask the user to confirm which real intervention(s) "
            "they mean, listing 2-3 of the available names above as examples."
        )

    applied = tool_data.get("applied_overrides", {})
    bos = tool_data.get("business_outcomes", [])
    l1s = tool_data.get("l1_metrics", [])
    unresolved = tool_data.get("unresolved_names", [])
    out_of_range = tool_data.get("out_of_range", [])

    lines = ["## What-If Simulation Result (computed by the Calculation Engine — state exactly)\n"]

    if out_of_range:
        lines.append("**Out-of-range values requested (do NOT guess a prediction for these):**")
        for item in out_of_range:
            if item["direction"] == "above":
                lines.append(
                    f"  - {item['name']}: requested {item['requested']}% — exceeds the maximum "
                    f"supported value of {item['max']}%. Tell the user: \"Sorry, we can't provide "
                    f"a prediction for {item['name']} at {item['requested']}% because it exceeds "
                    f"the maximum supported limit of {item['max']}%. Please enter a value within "
                    f"the supported range.\""
                )
            else:
                lines.append(
                    f"  - {item['name']}: requested {item['requested']}% — below the minimum "
                    f"supported value of {item['min']}%. Tell the user this value is outside the "
                    f"supported range and state the minimum allowed value ({item['min']}%)."
                )
        lines.append("")
    if not applied and out_of_range:
        # Every requested value was out of range — no in-range prediction to report at all.
        lines.append(f"\n## User Question\n{user_query}\n")
        lines.append(
            "Only report the out-of-range message(s) above, exactly as instructed. Do not "
            "compute or invent any result for these values."
        )
        return "\n".join(lines)

    applied_str = ", ".join(f"{name} = {val}%" for name, val in applied.items())
    lines.append(f"**Hypothetical values applied:** {applied_str}\n")
    if unresolved:
        lines.append(
            f"**Note:** these terms could not be matched to a real intervention and were "
            f"IGNORED (do not guess what they mean): {', '.join(unresolved)}\n"
        )

    if bos:
        lines.append("**Resulting Business Outcome(s):**")
        for bo in bos:
            lines.append(
                f"  - {bo['name']}: **{bo['current_value']}** {bo.get('unit') or ''} "
                f"(was {bo['default_value']}, {bo['improvement_percentage']:+.1f}%)"
            )
    if l1s:
        lines.append("\n**Resulting L1 metric(s):**")
        for l1 in l1s:
            lines.append(f"  - {l1['name']}: **{l1['current_value']}** {l1.get('unit') or ''}")

    lines.append(
        "\nThis was a TEMPORARY simulation — the real saved sliders were restored immediately "
        "after computing this result, so mention that the live dashboard is unchanged unless "
        "the user explicitly applies these values."
    )
    lines.append(f"\n## User Question\n{user_query}\n")
    lines.append(
        "State the resulting value(s) exactly as computed above. Only use the metric and "
        "intervention names shown — never invent a name or number."
    )
    return "\n".join(lines)


def format_knowledge_prompt(tool_data: dict, user_query: str) -> str:
    context = tool_data.get("context", "")
    sources = tool_data.get("sources", [])
    error = tool_data.get("error")

    if error:
        return (
            f"## Knowledge Base Error\n{error}\n\n"
            f"## Question\n{user_query}\n\n"
            "Answer from your general knowledge. Flag that the search had an issue."
        )

    source_names = ", ".join(s["source"] for s in sources[:3]) if sources else "built-in knowledge"

    return (
        f"## Retrieved Knowledge (from: {source_names})\n{context}\n\n"
        f"## User Question\n{user_query}\n\n"
        "Answer using the retrieved knowledge. "
        "If the retrieved content does not contain a direct answer, say so clearly. "
        "Do not fabricate definitions for metric names not in the retrieved content."
    )


def format_trace_prompt(tool_data: dict, user_query: str) -> str:
    mode = tool_data.get("mode", "trace")
    error = tool_data.get("error")

    if error:
        return (
            f"## Formula Trace Error\n{error}\n\n"
            f"## Question\n{user_query}\n\n"
            "Explain what formula trace data is available from the live page data above."
        )

    lines = ["## KPI Formula Trace\n"]
    lines.append(
        "**How to read impact factors (for your explanation only — do NOT perform new arithmetic "
        "with these unless the exact inputs for every step are present below):**\n"
        "- Intervention -> L2: the impact factor is the % change in the L2 metric per 1% change "
        "in the intervention slider.\n"
        "- L2 -> L1 and L1 -> Business Outcome: same idea, one level up the chain.\n"
        "- A positive impact factor means they move together; negative means they move opposite.\n"
    )

    if mode == "path":
        lines.append(f"**Path: {tool_data.get('from')} → {tool_data.get('to')}:**")
        lines.append(str(tool_data.get("path", "No path found")))
    else:
        metric = tool_data.get("metric_name", "")
        level = tool_data.get("metric_level", "")
        chain = tool_data.get("full_chain", "")
        upstream = tool_data.get("upstream", [])
        downstream = tool_data.get("downstream", [])

        lines.append(f"**Metric:** {metric} (Level: {level})")
        lines.append(f"**Chain:** {chain}\n")

        if upstream:
            lines.append("**Upstream (what drives this metric):**")
            for r in upstream[:5]:
                lines.append(f"  - {r['parent']} → {metric} (Impact Factor: {r['impact_factor']:+.3f}) [{r['level']}]")
            lines.append("")

        if downstream:
            lines.append("**Downstream (what this metric drives):**")
            for r in downstream[:5]:
                lines.append(f"  - {metric} → {r['child']} (Impact Factor: {r['impact_factor']:+.3f}) [{r['level']}]")
            lines.append("")

        if not upstream and not downstream:
            lines.append("No relationships found in the database for this metric name.")

    lines.append(f"\n## User Question\n{user_query}\n")
    lines.append(
        "Explain the formula chain using ONLY the impact factors and values shown above. "
        "Show the Intervention → L2 → L1 → Business Outcome chain using the names and impact "
        "factors given. Explain what each impact factor means in plain terms. "
        "Do NOT introduce any coefficient, percentage, or calculated value that is not "
        "explicitly shown above — if a step's data isn't present, say that step wasn't "
        "returned by the trace rather than estimating it. "
        "Use only the names from the trace data above."
    )
    return "\n".join(lines)


def format_advisor_prompt(tool_data: dict, user_query: str) -> str:
    strategies = tool_data.get("strategies", [])
    target = tool_data.get("target_outcome", "All Business Outcomes")
    error = tool_data.get("error")
    mode = tool_data.get("mode", "recommend")

    if error:
        return (
            f"## Decision Advisor Error\n{error}\n\n"
            f"## Question\n{user_query}\n\n"
            "Provide general strategy advice based on the live page data above."
        )

    if not strategies:
        return f"## Question\n{user_query}\n\nNo strategies could be generated — say so plainly."

    # ── Apply Mode ──────────────────────────────────────────────────────
    # The exact slider values are computed deterministically below in
    # decision_advisor_tool and applied by the frontend directly from
    # tool_result.data.apply_action — the LLM is NOT trusted to copy
    # numbers accurately into prose. Its only job here is a one-line
    # confirmation, nothing more.
    if mode == "apply":
        top = strategies[0]
        return (
            f"## Apply Mode\n"
            f"The user wants to apply the top strategy: **{top['name']}**.\n"
            f"The exact slider values have already been computed and will be applied automatically — "
            f"you do not need to state them.\n\n"
            f"## User Question\n{user_query}\n\n"
            f"Respond with ONLY one short sentence confirming the {top['name']} configuration "
            f"is being applied. Do not re-explain the strategy, do not list percentages, "
            f"do not mention trade-offs again — that was already said."
        )

    # ── Recommendation Mode (default) ───────────────────────────────────
    lines = [f"## Intervention Strategy Analysis\n", f"**Target:** {target}\n"]
    for s in strategies:
        bo_str = " | ".join(
            f"{bo['name']}: {bo['improvement_pct']:+.2f}%"
            for bo in s.get("business_outcomes", [])[:3]
        )
        lines.append(
            f"**Rank {s['rank']}: {s['name']}** {s.get('recommendation', '')}\n"
            f"  {s['description']}\n"
            f"  Avg BO Improvement: {s['avg_bo_improvement']:+.2f}%\n"
            f"  BO Impact: {bo_str}\n"
        )

    lines.append(f"\n## User Question\n{user_query}\n")
    lines.append(
        "State which strategy is best and why, using the avg BO improvement numbers given above "
        "exactly as computed — these are already ranked and measured by the Decision Engine, not "
        "something for you to re-evaluate. Do NOT write 'maybe', 'it might be helpful to', 'it's "
        "difficult to provide a specific recommendation', or similar hedges — the ranking above IS "
        "the specific recommendation. Use ONLY the intervention and metric names shown above. "
        "Do NOT mention specific intervention percentages/slider values unless the user's "
        "question explicitly asks for the exact values to apply — this is analysis mode, "
        "not apply mode. IMPORTANT: if the top strategy's avg BO improvement is negative, say so "
        "plainly — call it a decline / the smallest drop among the options, never an 'improvement'. "
        "A negative number described as an 'improvement' is confusing, not reassuring."
    )
    return "\n".join(lines)


def format_page_context(page_context) -> str:
    """
    Format live page data into a context block.
    This is the GROUND TRUTH the LLM must use for all metric names.
    """
    if not page_context:
        return ""

    lines = ["## Current Page — Live KPI Data\n",
             "*(Use ONLY these names in your response — do not invent other metric names)*\n"]

    filters = page_context.filters or {}
    if filters.get("vertical") or filters.get("lob"):
        lines.append(f"**Vertical / LOB:** {filters.get('vertical', 'All')} → {filters.get('lob', 'All')}\n")

    # Active interventions
    active_ivs = page_context.active_interventions or []
    if active_ivs:
        lines.append("**Active Intervention Sliders (> 0%):**")
        for iv in active_ivs:
            lines.append(f"  - **{iv.get('name', '?')}**: {iv.get('percentage', 0):.0f}%")
        lines.append("")
    else:
        lines.append("**Active Interventions:** NONE — all sliders are at 0%\n")

    # Business outcomes
    bos = page_context.business_outcomes or []
    if bos:
        lines.append("**Business Outcomes on this page:**")
        for bo in bos:
            imp = bo.get("improvement_pct", 0) or 0
            arrow = "↑" if imp > 0 else ("↓" if imp < 0 else "→")
            lines.append(
                f"  - **{bo.get('name', '?')}**: "
                f"default={bo.get('default_value', 0):.2f}, "
                f"current={bo.get('current_value', 0):.2f} "
                f"({arrow}{abs(imp):.2f}%)"
            )
        lines.append("")

    # Changed L1 metrics
    l1s = [m for m in (page_context.l1_metrics or []) if abs(m.get("improvement_pct", 0) or 0) >= 0.05]
    if l1s:
        lines.append("**L1 Metrics (changed from baseline):**")
        for m in l1s[:6]:
            imp = m.get("improvement_pct", 0) or 0
            lines.append(
                f"  - **{m.get('name', '?')}**: "
                f"default={m.get('default_value', 0):.2f}, "
                f"current={m.get('current_value', 0):.2f} "
                f"({'↑' if imp > 0 else '↓'}{abs(imp):.2f}%)"
            )
        lines.append("")
    else:
        # Show all L1s even if unchanged (so LLM knows the real names)
        all_l1s = page_context.l1_metrics or []
        if all_l1s:
            lines.append(f"**L1 Metrics on this page (at baseline):** {', '.join(m.get('name','?') for m in all_l1s[:6])}\n")

    # Changed L2 metrics
    l2s = [m for m in (page_context.l2_metrics or []) if abs(m.get("improvement_pct", 0) or 0) >= 0.05]
    if l2s:
        lines.append("**L2 Metrics (changed from baseline):**")
        for m in l2s[:6]:
            imp = m.get("improvement_pct", 0) or 0
            lines.append(
                f"  - **{m.get('name', '?')}**: "
                f"default={m.get('default_value', 0):.2f}, "
                f"current={m.get('current_value', 0):.2f} "
                f"({'↑' if imp > 0 else '↓'}{abs(imp):.2f}%)"
            )
        lines.append("")
    else:
        all_l2s = page_context.l2_metrics or []
        if all_l2s:
            lines.append(f"**L2 Metrics on this page (at baseline):** {', '.join(m.get('name','?') for m in all_l2s[:6])}\n")

    lines.append("")
    return "\n".join(lines)
