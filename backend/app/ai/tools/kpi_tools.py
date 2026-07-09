"""
Cascade AI Tools
-----------------
Five internal tools used by the single Cascade AI agent:

  1. insight_tool      — explain why KPIs changed
  2. goal_tool         — reverse-solve to reach a target
  3. knowledge_tool    — RAG-based Q&A (BRD, definitions, formulas)
  4. excel_trace_tool  — trace KPI hierarchy paths
  5. decision_advisor  — recommend top intervention strategies

Each tool returns a structured dict consumed by the agent's prompt builder.
NONE of these tools reimplement cascade math — they read from existing APIs/DB.
"""
import logging
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 1 — INSIGHT TOOL
# ──────────────────────────────────────────────────────────────────────────────

def insight_tool(db: Session, query: str = "", vertical: Optional[str] = None, lob: Optional[str] = None) -> Dict[str, Any]:
    """
    Explain current simulation state: which interventions moved, which KPIs
    changed, and why. Reads ONLY from the existing simulation snapshot,
    scoped to the currently selected vertical/LOB.

    IMPORTANT: without the vertical/lob filter below, this tool used to read
    EVERY intervention and metric in the database across ALL verticals, so a
    user viewing e.g. "Health Insurance" would see active sliders and KPI
    changes that actually belonged to "Finance & Accounting" (or whichever
    vertical happened to have active sliders at the time).
    """
    try:
        from ...services import simulation_service
        from ...services.serialization_helpers import (
            attach_l1_business_outcome_links,
            attach_l2_l1_links,
            attach_intervention_l2_links,
        )

        data = simulation_service.recalculate_and_fetch(db)

        def scoped(items):
            result = items
            if vertical:
                result = [i for i in result if i.vertical_horizontal == vertical]
            if lob:
                result = [i for i in result if i.lob == lob]
            return result

        ivs = scoped(data["interventions"])
        l2s = scoped(data["l2_metrics"])
        l1s = scoped(data["l1_metrics"])
        bos = scoped(data["business_outcomes"])

        attach_intervention_l2_links(db, ivs)
        attach_l2_l1_links(db, l2s)
        attach_l1_business_outcome_links(db, l1s)

        # Active interventions (slider > 0)
        active_ivs = [iv for iv in ivs if (iv.percentage or 0) > 0]

        # Significant KPI changes
        def changed(items, threshold=0.5):
            return [
                {
                    "name": m.name,
                    "default": round(m.default_value, 2),
                    "current": round(m.current_value, 2),
                    "improvement_pct": round(m.improvement_percentage or 0, 2),
                    "higher_is_better": m.higher_is_better,
                }
                for m in items
                if abs(m.improvement_percentage or 0) >= threshold
            ]

        changed_bos = changed(bos, threshold=0.1)
        changed_l1s = changed(l1s, threshold=0.1)
        changed_l2s = changed(l2s, threshold=0.1)

        # ── Verified causal chains vs. unverified correlations ──────────
        # This is the fix for "the Insight Agent is guessing causality"
        # (it was inferring cause from metrics that merely changed in the
        # same simulation tick). Instead: cross-reference the REAL
        # relationship graph (trace_service — same data the Trace Agent
        # uses, read from the Excel workbook / DB impact-factor tables)
        # and only call something a "cascade path" if there is an actual
        # edge connecting the two metrics. Anything that changed but isn't
        # reachable from an active intervention through a real edge goes
        # into `unverified_correlations` — the LLM is instructed to never
        # use causal language for those.
        verified_chains: List[Dict[str, Any]] = []
        explained_names = set()
        active_names = {iv.name for iv in active_ivs}
        changed_l2_names = {m["name"] for m in changed_l2s}
        changed_l1_names = {m["name"] for m in changed_l1s}
        changed_bo_names = {m["name"] for m in changed_bos}
        try:
            from ..services.trace_service import get_trace_service

            svc = get_trace_service(db=db, vertical=vertical, lob=lob)
            relationships = svc.get_all_relationships()

            # IV -> L2 (only edges from an active slider to an L2 that
            # actually changed)
            frontier = set(active_names)
            for r in relationships:
                if r.level == "IV→L2" and r.parent_name in frontier and r.child_name in changed_l2_names:
                    verified_chains.append({
                        "from": r.parent_name, "to": r.child_name,
                        "impact_factor": r.impact_factor, "level": r.level,
                    })
                    explained_names.add(r.child_name)

            # L2 -> L1 (only from an L2 we just verified as explained)
            for r in relationships:
                if r.level == "L2→L1" and r.parent_name in explained_names and r.child_name in changed_l1_names:
                    verified_chains.append({
                        "from": r.parent_name, "to": r.child_name,
                        "impact_factor": r.impact_factor, "level": r.level,
                    })
                    explained_names.add(r.child_name)

            # L1 -> BO
            for r in relationships:
                if r.level == "L1→BO" and r.parent_name in explained_names and r.child_name in changed_bo_names:
                    verified_chains.append({
                        "from": r.parent_name, "to": r.child_name,
                        "impact_factor": r.impact_factor, "level": r.level,
                    })
                    explained_names.add(r.child_name)
        except Exception as e:  # noqa: BLE001 — insight must still work without trace data
            logger.warning(f"insight_tool: could not cross-reference trace graph: {e}")

        all_changed_names = {
            m["name"] for m in (changed_bos + changed_l1s + changed_l2s)
        }
        unverified_correlations = sorted(all_changed_names - explained_names - active_names)

        return {
            "tool": "insight",
            "active_interventions": [
                {"name": iv.name, "percentage": iv.percentage}
                for iv in active_ivs
            ],
            "changed_business_outcomes": changed_bos,
            "changed_l1_metrics": changed_l1s,
            "changed_l2_metrics": changed_l2s,
            "all_interventions": [
                {"name": iv.name, "percentage": iv.percentage or 0}
                for iv in ivs
            ],
            # Verified: a real edge (with a real impact factor) connects
            # these two metrics — the LLM MAY describe this as cause/effect.
            "verified_chains": verified_chains,
            # Unverified: these metrics changed in the same tick but no
            # edge connects them to an active intervention — the LLM MUST
            # describe these as "changed together", never as caused.
            "unverified_correlations": unverified_correlations,
            "vertical": vertical or "All",
            "lob": lob or "All",
            "query": query,
        }
    except Exception as e:
        logger.error(f"insight_tool error: {e}", exc_info=True)
        return {"tool": "insight", "error": str(e), "query": query}


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 2 — GOAL TOOL
# ──────────────────────────────────────────────────────────────────────────────

def goal_tool(
    db: Session,
    target_metric: str,
    target_value: float,
    higher_is_better: bool = False,
    vertical: Optional[str] = None,
    lob: Optional[str] = None,
    allowed_interventions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Find intervention configurations that achieve a target KPI value.
    Uses the existing simulation engine as oracle (ReverseSolver), scoped to
    the current vertical/LOB so the solver only touches this vertical's
    interventions and metrics.

    allowed_interventions: if provided, only these intervention names are
    adjusted; all others are pinned at their current value. This respects
    the user's explicit constraint ("only change TP Simulation and IA").
    """
    try:
        from ..services.reverse_solver import run_reverse_solver

        results = run_reverse_solver(
            db=db,
            target_metric=target_metric,
            target_value=target_value,
            higher_is_better=higher_is_better,
            vertical=vertical,
            lob=lob,
            allowed_interventions=allowed_interventions,
        )

        # Attach a risk/cost/confidence profile to every candidate using the
        # same Decision Intelligence Engine decision_advisor_tool uses (see
        # decision_engine.py), so "reach 79% with Simulation 90%" also comes
        # with a risk/cost verdict instead of just a bare gap%. Per the gap
        # analysis: previously the Goal Agent's "confidence" was only a
        # gap-based High/Medium/Low label with no risk or cost context at
        # all — the agent could recommend a High-risk/High-cost combination
        # with the same confidence label as a Low-risk one achieving the
        # same target.
        from ..services.decision_engine import profile_settings, score_scenario

        solutions = []
        for i, sol in enumerate(results):
            settings_by_name = {iv.name: iv.value for iv in sol.interventions}
            profile = profile_settings(db, settings_by_name, vertical=vertical, lob=lob)
            goal_pct = max(0.0, 100.0 - min(100.0, sol.gap_pct))
            decision = score_scenario(goal_pct, profile)
            solutions.append({
                "rank": i + 1,
                "interventions": [
                    {"name": iv.name, "value": iv.value}
                    for iv in sol.interventions
                ],
                "achieved_value": sol.achieved_value,
                "gap_pct": sol.gap_pct,
                "confidence": sol.confidence,  # gap-based reachability confidence (unchanged, existing meaning)
                "description": sol.description,
                "risk": profile.risk_level,
                "cost": profile.cost_level,
                "implementation_confidence": profile.confidence_pct,  # admin-declared confidence, distinct meaning from `confidence` above
                "effort_weeks": profile.effort_weeks,
                "decision_score": decision.score,
                "recommended": decision.recommended,
                "recommendation_reason": decision.reason,
            })

        # Deterministic reachability verdict — computed here, not left for
        # the LLM to hedge about. "Achievable" means the best candidate the
        # solver found lands within 5% of the target; otherwise we report
        # the closest reachable value plainly instead of writing "maybe".
        best = solutions[0] if solutions else None
        target_achievable = bool(best) and best["gap_pct"] <= 5.0

        # When the target is NOT reachable, the user's next question is
        # always "why not / which KPI is limiting it" (see bug report
        # "Goal Agent Response When Target Cannot Be Reached" — the old
        # reply just said "cannot be reached, gap = 15%" with no
        # explanation). Every intervention the solver's own best-found
        # configuration pushed to 0% or 100% is, by construction, a
        # "no more room to give" lever: the search already tried harder
        # values on either side and this was still the closest result.
        # That's a real, deterministic signal — not a guess — so it's safe
        # to hand the LLM as fact instead of letting it invent a reason.
        limiting_factors = []
        if not target_achievable and results:
            for name, value in results[0].full_settings.items():
                if value <= 0:
                    limiting_factors.append({"name": name, "value": value, "at": "minimum (0%)"})
                elif value >= 100:
                    limiting_factors.append({"name": name, "value": value, "at": "maximum (100%)"})

        return {
            "tool": "goal",
            "target_metric": target_metric,
            "target_value": target_value,
            "higher_is_better": higher_is_better,
            "solutions": solutions,
            "target_achievable": target_achievable,
            "closest_reachable": best,
            "limiting_factors": limiting_factors,
        }
    except Exception as e:
        logger.error(f"goal_tool error: {e}", exc_info=True)
        return {
            "tool": "goal",
            "target_metric": target_metric,
            "target_value": target_value,
            "error": str(e),
        }


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 2b — WHAT-IF TOOL (hypothetical forward simulation)
# ──────────────────────────────────────────────────────────────────────────────

def whatif_tool(
    db: Session,
    intervention_values: Dict[str, float],
    unresolved_count: int = 0,
    vertical: Optional[str] = None,
    lob: Optional[str] = None,
) -> Dict[str, Any]:
    """
    "If I set TP Gamification to 55, Interaction Analytics to 65, and QA
    Automation to 35, what is Revenue Growth?" — forward simulation given
    EXPLICIT hypothetical intervention values, as opposed to goal_tool
    (which searches for values that hit a target) or insight_tool (which
    explains the CURRENT saved state).

    `intervention_values` must already be resolved to real intervention
    names that exist in this vertical/LOB (see `_resolve_whatif_overrides`
    in cascade/agent.py) — this tool never guesses a name, it only runs
    the cascade for names it's given.

    Never reimplements cascade math — delegates to
    `whatif_service.evaluate_hypothetical`, which uses the same
    deterministic simulation_service the rest of the app uses, and always
    restores the DB to its prior saved state afterward.
    """
    try:
        from ...models import Intervention
        from ..services.whatif_service import evaluate_hypothetical

        def _scope(query):
            if vertical:
                query = query.filter(Intervention.vertical_horizontal == vertical)
            if lob:
                query = query.filter(Intervention.lob == lob)
            return query

        scoped_ivs = _scope(db.query(Intervention)).all()
        name_to_id = {iv.name: iv.id for iv in scoped_ivs}

        overrides_by_id: Dict[int, float] = {}
        unresolved_names: List[str] = []
        for name, value in intervention_values.items():
            iv_id = name_to_id.get(name)
            if iv_id is None:
                unresolved_names.append(name)
            else:
                overrides_by_id[iv_id] = value

        if not overrides_by_id:
            return {
                "tool": "whatif",
                "needs_clarification": True,
                "unresolved_names": unresolved_names,
                "available_interventions": sorted(name_to_id.keys()),
            }

        result = evaluate_hypothetical(db, overrides_by_id, vertical=vertical, lob=lob)
        result["tool"] = "whatif"
        result["unresolved_names"] = unresolved_names
        return result
    except Exception as e:
        logger.error(f"whatif_tool error: {e}", exc_info=True)
        return {"tool": "whatif", "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 3 — KNOWLEDGE TOOL (RAG)
# ──────────────────────────────────────────────────────────────────────────────

def knowledge_tool(query: str, allowed_terms: Optional[list] = None) -> Dict[str, Any]:
    """
    Answer domain questions using RAG over BRD, formula docs,
    KPI definitions, and Excel metadata. Never hallucinate — only return
    what was retrieved.

    allowed_terms: the real BO/L1/L2/Intervention names on the CURRENT
    page (from page_context), passed straight to RagService.search() so
    Finance-specific doc chunks (DSO, RPA, Collection Efficiency Rate...)
    never leak into answers for a different vertical (e.g. Customer
    Support / TP Simulation). Generic conceptual docs (source=
    "generic_fallback") are always kept regardless.
    """
    try:
        from ..services.rag_service import get_rag_service

        rag = get_rag_service()
        results = rag.search(query, allowed_terms=allowed_terms)
        context = rag.format_context(results)

        # Nothing retrieved (or only noise) → the Knowledge Agent must say
        # so and stop, never fall back to explaining from live simulation
        # data (that's the Insight Agent's job, a different responsibility
        # with different evidence). `not_found=True` tells the caller to
        # skip the LLM entirely for this turn.
        #
        # NOTE: this deliberately does NOT use the retrieval score to
        # decide relevance. RRF fusion scores here cluster tightly
        # (~0.009-0.01) almost regardless of actual relevance — a
        # nonsense query and a real one can both come back with a
        # non-empty, similarly-scored result set. Instead we check for
        # actual keyword overlap between the query and what was
        # retrieved, which is what a human would call "did this even
        # touch the topic asked about".
        _STOPWORDS = {
            "what", "does", "is", "are", "the", "a", "an", "mean", "means",
            "meaning", "of", "for", "in", "on", "to", "and", "or", "define",
            "explain", "how", "why", "which", "this", "that",
        }
        retrieved_text = context.lower()

        # If the query is asking about one of the real names on the current
        # page (e.g. "what does TP Simulation mean?"), a single generic
        # sub-word incidentally appearing somewhere else in the knowledge
        # base ("simulation" inside an unrelated "Simulation Formulae"
        # heading) must NOT count as finding a definition. Require the
        # FULL named term to appear, not just one of its words.
        matched_entity = None
        if allowed_terms:
            q_lower = query.lower()
            for term in allowed_terms:
                if term and len(term) >= 3 and term.lower() in q_lower:
                    matched_entity = term.lower()
                    break

        if matched_entity:
            has_overlap = matched_entity in retrieved_text
        else:
            query_tokens = {
                w for w in re.findall(r"[a-z0-9]+", query.lower())
                if len(w) >= 3 and w not in _STOPWORDS
            }
            has_overlap = any(tok in retrieved_text for tok in query_tokens) if query_tokens else bool(results)

        not_found = (not results) or (not context.strip()) or (not has_overlap)

        return {
            "tool": "knowledge",
            "query": query,
            "context": context,
            "not_found": not_found,
            "sources": [
                {
                    "source": r.metadata.get("source", "docs"),
                    "score": round(r.score, 4),
                    "snippet": r.content[:200],
                }
                for r in results
            ],
        }
    except Exception as e:
        logger.error(f"knowledge_tool error: {e}", exc_info=True)
        return {"tool": "knowledge", "query": query, "error": str(e), "context": ""}


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 4 — EXCEL TRACE TOOL
# ──────────────────────────────────────────────────────────────────────────────

def excel_trace_tool(
    db: Session,
    metric_name: str,
    from_intervention: Optional[str] = None,
    to_outcome: Optional[str] = None,
    vertical: Optional[str] = None,
    lob: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Trace KPI formula paths from the real Excel impact matrix.
    Shows: Intervention → L2 → L1 → Business Outcome chain.
    Never hallucinating — reads actual impact factors from file or DB.
    Scoped to the current vertical/LOB (see trace_service.get_trace_service).
    """
    try:
        from ..services.trace_service import get_trace_service

        svc = get_trace_service(db=db, vertical=vertical, lob=lob)

        if from_intervention and to_outcome:
            path = svc.find_path_to_outcome(from_intervention, to_outcome)
            return {
                "tool": "excel_trace",
                "mode": "path",
                "from": from_intervention,
                "to": to_outcome,
                "path": path,
            }
        else:
            trace = svc.trace_kpi(metric_name)
            return {
                "tool": "excel_trace",
                "mode": "trace",
                "metric_name": trace.metric_name,
                "metric_level": trace.metric_level,
                "full_chain": trace.full_chain,
                "upstream": [
                    {
                        "parent": r.parent_name,
                        "impact_factor": r.impact_factor,
                        "level": r.level,
                    }
                    for r in trace.upstream
                ],
                "downstream": [
                    {
                        "child": r.child_name,
                        "impact_factor": r.impact_factor,
                        "level": r.level,
                    }
                    for r in trace.downstream
                ],
            }
    except Exception as e:
        logger.error(f"excel_trace_tool error: {e}", exc_info=True)
        return {"tool": "excel_trace", "metric_name": metric_name, "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# TOOL 5 — DECISION ADVISOR
# ──────────────────────────────────────────────────────────────────────────────

def decision_advisor_tool(
    db: Session,
    target_outcome: Optional[str] = None,
    budget_constraint: Optional[str] = None,
    vertical: Optional[str] = None,
    lob: Optional[str] = None,
    apply_intent: bool = False,
) -> Dict[str, Any]:
    """
    Recommend the best intervention strategies ranked by ROI impact.
    Tests different intervention mixes and ranks by aggregate improvement.
    Reads from existing simulation engine — never reimplements math.

    Scoped to the current vertical/LOB. Previously this queried
    `Intervention.all()` / `BusinessOutcome.all()` with no filter, so the
    5 strategy simulations mixed every vertical's interventions together,
    and the ranked business-outcome improvements reported back to the user
    could belong to a completely different vertical than the one they were
    looking at.
    """
    try:
        from ...services import simulation_service
        from ...models import Intervention, BusinessOutcome

        def scoped_query(model):
            q = db.query(model)
            if vertical:
                q = q.filter(model.vertical_horizontal == vertical)
            if lob:
                q = q.filter(model.lob == lob)
            return q

        # Get only this vertical/LOB's interventions and business outcomes
        ivs = scoped_query(Intervention).all()
        bos = scoped_query(BusinessOutcome).all()

        if not ivs:
            return {
                "tool": "decision_advisor",
                "error": "No interventions configured in the simulator.",
            }

        # Save original state
        original_pcts = {iv.id: iv.percentage for iv in ivs}

        def _target_bos(all_bos):
            return (
                [b for b in all_bos if target_outcome.lower() in b.name.lower()]
                if target_outcome else all_bos
            )

        def _goodness(bo) -> float:
            """Signed 'how good is this change' score for one business
            outcome: positive means it moved in the DESIRABLE direction,
            negative means it moved the wrong way — regardless of how big
            the raw movement is.

            This replaces `sum(abs(improvement_percentage))`, which is the
            bug that made "Maximum Push" (100% on every slider) win every
            single time: abs() can't tell a KPI crashing by 23% from a KPI
            improving by 23% — both just look like "a big number" to it. A
            strategy that tanks Revenue Growth was scoring exactly as well
            as one that grew it, so the ranking always favored whichever
            strategy caused the largest raw cascade movement, good or bad.
            """
            pct = bo.improvement_percentage or 0
            return pct if bo.higher_is_better else -pct

        # ── Rank interventions by MEASURED impact, not by keyword guessing ──
        # Previously this matched intervention names against hardcoded terms
        # like "idp", "rpa", "workflow", "analytics", "bpm" — vocabulary from
        # one specific (Finance/automation) vertical. For any other vertical
        # (e.g. "TP Simulation", "TP Gamification", "Interaction Analytics"),
        # those buckets mostly missed, so strategies were built on
        # coincidence rather than this vertical's actual data. Instead: test
        # each intervention alone at 100%, measure its real effect on the
        # target business outcome(s), and rank by that.
        impact_scores = {}
        try:
            for probe in ivs:
                for other in ivs:
                    db.query(Intervention).filter(Intervention.id == other.id).update(
                        {Intervention.percentage: 100 if other.id == probe.id else 0}
                    )
                db.commit()
                simulation_service.recalculate(db)
                probed_bos = _target_bos(scoped_query(BusinessOutcome).all())
                impact_scores[probe.id] = sum(_goodness(b) for b in probed_bos)
        finally:
            for iv in ivs:
                db.query(Intervention).filter(Intervention.id == iv.id).update(
                    {Intervention.percentage: original_pcts[iv.id]}
                )
            db.commit()
            simulation_service.recalculate(db)

        ranked = sorted(ivs, key=lambda iv: impact_scores.get(iv.id, 0), reverse=True)
        top1 = ranked[:1]
        top2 = ranked[:2] if len(ranked) >= 2 else ranked
        top1_names = ", ".join(iv.name for iv in top1) or "the top intervention"
        top2_names = ", ".join(iv.name for iv in top2)

        strategies = []

        # Strategy templates — built purely from this vertical's own
        # interventions and their measured impact, no hardcoded vocabulary.
        strategy_configs = [
            {
                "name": "Balanced Approach",
                "desc": "Even push across every intervention on this page",
                "settings": {iv.id: 60 for iv in ivs},
            },
            {
                "name": "High-Impact Focus",
                "desc": f"Concentrate on {top2_names} — the interventions with the largest measured effect on {target_outcome or 'the business outcomes'}",
                "settings": {iv.id: (90 if iv in top2 else 20) for iv in ivs},
            },
            {
                "name": "Conservative Rollout",
                "desc": "A modest, lower-risk increase across all interventions",
                "settings": {iv.id: 30 for iv in ivs},
            },
            {
                # Without a low/no-op option in this list, the ranking can
                # only ever choose among "push harder" variants — so if the
                # data-driven truth is that these interventions net HURT the
                # target outcome (e.g. they drive up a metric that has a
                # negative downstream impact factor), every option scores
                # badly and the "least bad" push still gets recommended as
                # if it were good. Including a near-zero baseline lets the
                # ranking honestly surface "pull back" as the best answer
                # when that's what the data actually shows.
                "name": "Minimal Intervention",
                "desc": "Pull back to near-zero and let the KPIs settle",
                "settings": {iv.id: 5 for iv in ivs},
            },
            {
                "name": "Top Priority Push",
                "desc": f"Max out {top1_names} alone, keep everything else minimal",
                "settings": {iv.id: (100 if iv in top1 else 10) for iv in ivs},
            },
            {
                "name": "Maximum Push",
                "desc": "Push every intervention to its ceiling",
                "settings": {iv.id: 100 for iv in ivs},
            },
        ]

        try:
            for strategy in strategy_configs:
                # Apply settings
                for iv in ivs:
                    new_pct = strategy["settings"].get(iv.id, 0)
                    db.query(Intervention).filter(Intervention.id == iv.id).update(
                        {Intervention.percentage: new_pct}
                    )
                db.commit()
                simulation_service.recalculate(db)

                # Measure aggregate BO improvement
                current_bos = scoped_query(BusinessOutcome).all()
                target_bos = (
                    [b for b in current_bos if target_outcome.lower() in b.name.lower()]
                    if target_outcome else current_bos
                )

                total_improvement = sum(_goodness(bo) for bo in target_bos)
                avg_improvement = total_improvement / max(len(target_bos), 1)

                bo_details = [
                    {
                        "name": bo.name,
                        "default": round(bo.default_value, 2),
                        "current": round(bo.current_value, 2),
                        "improvement_pct": round(bo.improvement_percentage or 0, 2),
                    }
                    for bo in target_bos
                ]

                active_ivs = [
                    {"name": iv.name, "pct": strategy["settings"].get(iv.id, 0)}
                    for iv in ivs
                    if strategy["settings"].get(iv.id, 0) > 0
                ]

                strategies.append({
                    "name": strategy["name"],
                    "description": strategy["desc"],
                    "avg_bo_improvement": round(avg_improvement, 2),
                    "interventions": active_ivs,
                    "business_outcomes": bo_details,
                    # Raw settings kept (not just active_ivs, which drops
                    # 0% entries) so decision_engine.profile_settings can
                    # weigh "pinned at 0%" correctly below.
                    "_settings_by_name": {iv.name: strategy["settings"].get(iv.id, 0) for iv in ivs},
                })

        finally:
            # Restore original state
            for iv in ivs:
                db.query(Intervention).filter(Intervention.id == iv.id).update(
                    {Intervention.percentage: original_pcts[iv.id]}
                )
            db.commit()
            simulation_service.recalculate(db)

        # ── Decision Intelligence scoring ──────────────────────────────────
        # Previously ranked purely by avg_bo_improvement (raw KPI movement).
        # That let a strategy that only barely out-improves another win
        # outright even if it relies on High-risk/High-cost interventions
        # while the runner-up used Low-risk ones for nearly the same gain —
        # exactly the "highest revenue isn't automatically best" problem.
        # decision_engine.py is the single shared scoring formula (also used
        # by goal_tool) so the two agents can't disagree about what "best"
        # means. goal_achievement_pct here is relative to the best strategy
        # found (100% = the top raw improvement among the tested options),
        # since decision_advisor_tool has no single numeric target the way
        # goal_tool does.
        from ..services.decision_engine import profile_settings, rank_scenarios

        best_raw = max((s["avg_bo_improvement"] for s in strategies), default=0)
        scoring_input = []
        for s in strategies:
            settings_by_name = s.pop("_settings_by_name")
            profile = profile_settings(db, settings_by_name, vertical=vertical, lob=lob)
            goal_pct = (
                max(0.0, s["avg_bo_improvement"] / best_raw * 100.0) if best_raw > 0 else 0.0
            )
            s["risk"] = profile.risk_level
            s["cost"] = profile.cost_level
            s["implementation_confidence"] = profile.confidence_pct
            s["effort_weeks"] = profile.effort_weeks
            scoring_input.append({**s, "goal_achievement_pct": goal_pct, "profile": profile})

        strategies = rank_scenarios(scoring_input)

        # Add rank + a human label derived from the decision engine's own
        # verdict rather than a second, separately-reasoned "confidence"
        # guess — avoids the Goal-Agent-says-X / Advisor-says-Y
        # contradiction risk called out in the gap analysis.
        for i, s in enumerate(strategies):
            s["rank"] = i + 1
            s["decision_score"] = s["decision"].score
            s["confidence"] = "High" if s["decision"].confidence_pct >= 90 else (
                "Medium" if s["decision"].confidence_pct >= 75 else "Low"
            )
            if i == 0 and s["decision"].recommended:
                s["recommendation"] = "⭐ Top Pick"
            elif i == 0:
                s["recommendation"] = "Best Available (see risk note)"
            elif i == 1:
                s["recommendation"] = "Strong Alternative"
            else:
                s["recommendation"] = None
            s["recommendation_reason"] = s["decision"].reason
            del s["decision"]
            del s["profile"]
            del s["goal_achievement_pct"]

        return {
            "tool": "decision_advisor",
            "target_outcome": target_outcome or "All Business Outcomes",
            "strategies": strategies[:3],  # Top 3
            "total_strategies_tested": len(strategies),
            "mode": "apply" if apply_intent else "recommend",
            # Computed here — deterministically, from the actual simulation
            # engine — rather than asking the LLM to copy numbers into prose
            # and having the frontend regex-scrape them back out of chat
            # text. That regex-scraping approach (matching "**Name**: NN%"
            # patterns, with a hardcoded list of strategy-name cutoffs) was
            # fragile and broke as soon as the response wording changed.
            "apply_action": (
                {
                    "strategy_name": strategies[0]["name"],
                    "sliders": {iv["name"]: iv["pct"] for iv in strategies[0]["interventions"]},
                }
                if apply_intent and strategies else None
            ),
        }

    except Exception as e:
        logger.error(f"decision_advisor_tool error: {e}", exc_info=True)
        return {"tool": "decision_advisor", "error": str(e)}
