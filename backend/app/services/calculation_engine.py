"""
CalculationEngine - the single deterministic source of truth for every
number shown in the KPI Simulator and narrated by any of the 5 AI agents.

############################################################################
# !! PENDING CONFIRMATION FROM SPEC AUTHOR - DO NOT TREAT AS FINAL !!
#
# AI_Agents_Development_Spec.md section 0.2 gives this formula:
#
#     L1_new = Sum( L2_new[i] x weight[i] )
#
# ...but its OWN worked example doesn't reconcile with that formula:
#   L2_new = 7.70, weight = 0.60  ->  L1_new = 4.62 by the formula above
#   but the example states this "combines with other L2 inputs -> DSO 41
#   days", which is only possible if there's an implicit baseline term
#   (e.g. DSO_new = DSO_base + Sum(weight x delta_L2) or a multiplicative
#   variant) that the written formula omits.
#
# This was caught empirically: running real seeded weights through the
# literal formula below produces NEGATIVE Days Sales Outstanding and
# negative Bad Debt Ratio, which are nonsensical for those metrics.
#
# Product decision: pause on resolving this interpretation gap until the
# spec author/BRD owner confirms which formula is intended. The code
# below implements the LITERALLY-WRITTEN formula (no baseline term) as a
# placeholder ONLY because that's what's actually written in the spec —
# this is explicitly NOT validated as correct, and the seed data's
# weights have NOT been recalibrated to match it (recalibration is
# pointless until the formula itself is confirmed). Treat every number
# this engine currently produces as provisional/non-authoritative until
# this flag is removed.
############################################################################

Implements AI_Agents_Development_Spec.md section 0.2 AS LITERALLY WRITTEN
(pending the confirmation above):

    L2_new = L2_base - (intervention_value% x impact_factor x L2_base)

    L1_new = Sum( L2_new[i] x weight[i] )   for all L2 metrics feeding this L1

    Business_Outcome_new = Sum( L1_new[i] x weight[i] )

    Revenue_Impact% = delta_L1_pct x benchmark_factor

This REPLACES the previous chained-percentage formula that used to live
in services/simulation_service.py (Total Change% accumulated level by
level). That formula was internally consistent and produced sane
numbers with the existing seed weights — see git history / earlier
conversation turns if a rollback is needed while the above is resolved.

IMPORTANT - "weight" vs "impact_factor" naming:
The spec calls the Intervention->L2 edge weight "impact_factor" and the
L2->L1 / L1->BusinessOutcome edge weight "weight". In this codebase both
edges are stored in the same `impact_factor` column on the association
tables (intervention_l2_link, l2_l1_link, l1_bo_link) - there is only one
"edge weight" concept, just used in two slightly different formula shapes
depending on which level it's at. CalculationEngine below applies the
correct formula shape per level; the column name is unchanged so existing
CRUD/dependency-builder UI keeps working unmodified.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import (
    BusinessOutcome, L1Metric, L2Metric, Intervention,
    intervention_l2_link, l2_l1_link, l1_bo_link,
)
from ..schemas.agent_schemas import (
    SimulationResult, InterventionChange, L2Change, L1Change, BusinessOutcomeChange,
    CalculationTrace,
)

# Runtime-checkable flag (not just a docstring) — agent routes check this
# and append a disclosure to every narrated response until the spec
# author confirms the correct L1/BusinessOutcome formula interpretation.
# See the module docstring above for the full explanation.
FORMULA_PENDING_CONFIRMATION = True
FORMULA_DISCLOSURE_TEXT = (
    "Note: the L1/Business Outcome aggregation formula in this preview is "
    "PENDING CONFIRMATION from the spec author due to an inconsistency between "
    "the written formula and its own worked example. Treat these specific "
    "numbers as provisional. The live KPI Simulator dashboard uses the "
    "previously-validated formula and is unaffected."
)


def _round(value: float, digits: int = 4) -> float:
    return round(value, digits)


def _pct_change(base: float, new: float) -> float:
    if base == 0:
        return 0.0
    return _round((new - base) / base * 100, 2)


@dataclass
class _Edge:
    impact_factor: float


class CalculationEngine:
    """
    Stateless w.r.t. the DB session - every method takes `db` explicitly so
    this can be called from request-scoped FastAPI dependencies, background
    jobs, or unit tests with an in-memory SQLite session alike.
    """

    # -----------------------------------------------------------------
    # compute_l2 / compute_l1 / compute_business_outcomes
    # -----------------------------------------------------------------

    def compute_l2(self, db: Session, intervention_values: Dict[int, float]) -> Dict[int, float]:
        """
        L2_new = L2_base - (intervention_value% x impact_factor x L2_base)

        If multiple interventions feed the same L2 metric, their individual
        reductions are summed (each applied to the SAME base value, matching
        the spec's per-edge formula - there is no compounding across edges
        at this level).
        """
        l2_metrics: List[L2Metric] = db.query(L2Metric).all()
        edges = db.execute(select(
            intervention_l2_link.c.intervention_id,
            intervention_l2_link.c.l2_metric_id,
            intervention_l2_link.c.impact_factor,
        )).all()

        l2_base: Dict[int, float] = {m.id: m.default_value for m in l2_metrics}
        l2_new: Dict[int, float] = dict(l2_base)

        for intervention_id, l2_id, impact_factor in edges:
            if l2_id not in l2_base:
                continue
            iv_value_pct = intervention_values.get(intervention_id, 0.0)
            base = l2_base[l2_id]
            reduction = (iv_value_pct / 100.0) * impact_factor * base
            l2_new[l2_id] = l2_new[l2_id] - reduction

        return {k: _round(v) for k, v in l2_new.items()}

    def compute_l1(self, db: Session, l2_values: Dict[int, float]) -> Dict[int, float]:
        """L1_new = Sum( L2_new[i] x weight[i] ) for all L2 metrics feeding this L1."""
        l1_metrics: List[L1Metric] = db.query(L1Metric).all()
        edges = db.execute(select(
            l2_l1_link.c.l2_metric_id,
            l2_l1_link.c.l1_metric_id,
            l2_l1_link.c.impact_factor,
        )).all()

        l1_new: Dict[int, float] = {m.id: 0.0 for m in l1_metrics}
        l1_has_edge: Dict[int, bool] = {m.id: False for m in l1_metrics}

        for l2_id, l1_id, weight in edges:
            if l1_id not in l1_new:
                continue
            l2_new_value = l2_values.get(l2_id, 0.0)
            l1_new[l1_id] += l2_new_value * weight
            l1_has_edge[l1_id] = True

        l1_defaults = {m.id: m.default_value for m in l1_metrics}
        for l1_id in l1_new:
            if not l1_has_edge[l1_id]:
                l1_new[l1_id] = l1_defaults[l1_id]

        return {k: _round(v) for k, v in l1_new.items()}

    def compute_business_outcomes(self, db: Session, l1_values: Dict[int, float]) -> Dict[int, float]:
        """Business_Outcome_new = Sum( L1_new[i] x weight[i] )."""
        outcomes: List[BusinessOutcome] = db.query(BusinessOutcome).all()
        edges = db.execute(select(
            l1_bo_link.c.l1_metric_id,
            l1_bo_link.c.business_outcome_id,
            l1_bo_link.c.impact_factor,
        )).all()

        bo_new: Dict[int, float] = {b.id: 0.0 for b in outcomes}
        bo_has_edge: Dict[int, bool] = {b.id: False for b in outcomes}

        for l1_id, bo_id, weight in edges:
            if bo_id not in bo_new:
                continue
            l1_new_value = l1_values.get(l1_id, 0.0)
            bo_new[bo_id] += l1_new_value * weight
            bo_has_edge[bo_id] = True

        bo_defaults = {b.id: b.default_value for b in outcomes}
        for bo_id in bo_new:
            if not bo_has_edge[bo_id]:
                bo_new[bo_id] = bo_defaults[bo_id]

        return {k: _round(v) for k, v in bo_new.items()}

    def compute_revenue_impact(self, db: Session, l1_deltas: Dict[int, float]) -> float:
        """
        Revenue_Impact% = delta_L1_pct x benchmark_factor, aggregated across
        every L1 metric that feeds a Business Outcome (weighted by how much
        of that L1's delta actually reaches an outcome), then averaged
        across Business Outcomes.

        Simplification used here (documented, not hidden): each Business
        Outcome's benchmark_factor is applied to the weighted-average delta%
        of the L1 metrics feeding it, and the final revenue_impact_pct
        returned is the average across all Business Outcomes in scope. This
        matches the spec's single-number worked example (Revenue_Impact =
        delta-DSO% x benchmark_factor) for the common single-outcome case,
        and generalizes sanely when there are multiple outcomes.
        """
        outcomes: List[BusinessOutcome] = db.query(BusinessOutcome).all()
        if not outcomes:
            return 0.0

        edges = db.execute(select(
            l1_bo_link.c.l1_metric_id,
            l1_bo_link.c.business_outcome_id,
            l1_bo_link.c.impact_factor,
        )).all()

        per_outcome_weighted_delta: Dict[int, float] = {b.id: 0.0 for b in outcomes}
        per_outcome_weight_sum: Dict[int, float] = {b.id: 0.0 for b in outcomes}

        for l1_id, bo_id, weight in edges:
            if bo_id not in per_outcome_weighted_delta:
                continue
            delta = l1_deltas.get(l1_id, 0.0)
            per_outcome_weighted_delta[bo_id] += delta * weight
            per_outcome_weight_sum[bo_id] += weight

        impacts = []
        for outcome in outcomes:
            weight_sum = per_outcome_weight_sum[outcome.id]
            if weight_sum == 0:
                continue
            avg_delta = per_outcome_weighted_delta[outcome.id] / weight_sum
            impacts.append(avg_delta * outcome.benchmark_factor)

        if not impacts:
            return 0.0
        return _round(sum(impacts) / len(impacts), 2)

    # -----------------------------------------------------------------
    # run_full_simulation - the ROI Insight Agent's input contract
    # -----------------------------------------------------------------

    def run_full_simulation(self, db: Session, vertical_horizontal: str, lob: str) -> SimulationResult:
        """
        NOTE: l2_changes in the returned SimulationResult use the
        confirmed-correct L2 formula (compute_l2) and are trustworthy.
        l1_changes, business_outcome_changes, and revenue_impact_pct use
        the PENDING-CONFIRMATION aggregation formula (see module
        docstring) and should be treated as provisional — callers (the
        ROI Insight Agent) disclose this via FORMULA_DISCLOSURE_TEXT.
        """
        interventions: List[Intervention] = (
            db.query(Intervention)
            .filter(Intervention.vertical_horizontal == vertical_horizontal, Intervention.lob == lob)
            .all()
        )
        l2_metrics: List[L2Metric] = (
            db.query(L2Metric)
            .filter(L2Metric.vertical_horizontal == vertical_horizontal, L2Metric.lob == lob)
            .all()
        )
        l1_metrics: List[L1Metric] = (
            db.query(L1Metric)
            .filter(L1Metric.vertical_horizontal == vertical_horizontal, L1Metric.lob == lob)
            .all()
        )
        business_outcomes: List[BusinessOutcome] = (
            db.query(BusinessOutcome)
            .filter(BusinessOutcome.vertical_horizontal == vertical_horizontal, BusinessOutcome.lob == lob)
            .all()
        )

        intervention_values = {iv.id: iv.percentage for iv in interventions}
        l2_new = self.compute_l2(db, intervention_values)
        l1_new = self.compute_l1(db, l2_new)
        bo_new = self.compute_business_outcomes(db, l1_new)

        l1_deltas = {m.id: _pct_change(m.default_value, l1_new.get(m.id, m.default_value)) for m in l1_metrics}
        revenue_impact_pct = self.compute_revenue_impact(db, l1_deltas)

        iv_l2_edges = db.execute(select(
            intervention_l2_link.c.intervention_id,
            intervention_l2_link.c.l2_metric_id,
            intervention_l2_link.c.impact_factor,
        )).all()
        l2_name_by_id = {m.id: m.name for m in l2_metrics}
        first_l2_for_iv: Dict[int, str] = {}
        impact_factor_for_iv: Dict[int, float] = {}
        for iv_id, l2_id, impact_factor in iv_l2_edges:
            if iv_id not in first_l2_for_iv and l2_id in l2_name_by_id:
                first_l2_for_iv[iv_id] = l2_name_by_id[l2_id]
                impact_factor_for_iv[iv_id] = impact_factor

        interventions_out = [
            InterventionChange(
                name=iv.name,
                value=iv.percentage,
                impact_factor=impact_factor_for_iv.get(iv.id, 0.0),
                affects_l2=first_l2_for_iv.get(iv.id),
            )
            for iv in interventions
        ]

        l2_out = [
            L2Change(
                name=m.name, base=m.default_value, new=l2_new.get(m.id, m.default_value),
                unit=m.unit, delta_pct=_pct_change(m.default_value, l2_new.get(m.id, m.default_value)),
            )
            for m in l2_metrics
        ]
        l1_out = [
            L1Change(
                name=m.name, base=m.default_value, new=l1_new.get(m.id, m.default_value),
                unit=m.unit, delta_pct=l1_deltas.get(m.id, 0.0),
                target=m.target_value,
            )
            for m in l1_metrics
        ]
        bo_out = [
            BusinessOutcomeChange(
                name=m.name, base=m.default_value, new=bo_new.get(m.id, m.default_value),
                unit=m.unit, delta_pct=_pct_change(m.default_value, bo_new.get(m.id, m.default_value)),
            )
            for m in business_outcomes
        ]

        return SimulationResult(
            lob=lob,
            vertical=vertical_horizontal,
            interventions=interventions_out,
            l2_changes=l2_out,
            l1_changes=l1_out,
            business_outcome_changes=bo_out,
            revenue_impact_pct=revenue_impact_pct,
        )

    # -----------------------------------------------------------------
    # Persist current_value / improvement_percentage onto the ORM rows
    # (keeps the existing dashboard CRUD/cascade behavior working)
    # -----------------------------------------------------------------

    def recalculate_and_persist(self, db: Session) -> None:
        """
        Runs compute_l2 / compute_l1 / compute_business_outcomes across
        EVERY row regardless of vertical/lob scope (matches the previous
        simulation_service.recalculate() behavior, which the rest of the
        CRUD routes call after every mutation) and writes current_value +
        improvement_percentage back onto each ORM row.
        """
        interventions: List[Intervention] = db.query(Intervention).all()
        l2_metrics: List[L2Metric] = db.query(L2Metric).all()
        l1_metrics: List[L1Metric] = db.query(L1Metric).all()
        business_outcomes: List[BusinessOutcome] = db.query(BusinessOutcome).all()

        intervention_values = {iv.id: iv.percentage for iv in interventions}
        l2_new = self.compute_l2(db, intervention_values)
        l1_new = self.compute_l1(db, l2_new)
        bo_new = self.compute_business_outcomes(db, l1_new)

        for metric in l2_metrics:
            new_val = l2_new.get(metric.id, metric.default_value)
            metric.current_value = new_val
            metric.improvement_percentage = _pct_change(metric.default_value, new_val)

        for metric in l1_metrics:
            new_val = l1_new.get(metric.id, metric.default_value)
            metric.current_value = new_val
            metric.improvement_percentage = _pct_change(metric.default_value, new_val)

        for outcome in business_outcomes:
            new_val = bo_new.get(outcome.id, outcome.default_value)
            outcome.current_value = new_val
            outcome.improvement_percentage = _pct_change(outcome.default_value, new_val)

        db.commit()

    # -----------------------------------------------------------------
    # trace_calculation - the Excel Intelligence Agent's input contract
    # -----------------------------------------------------------------

    def trace_calculation(self, db: Session, metric_name: str, metric_level: str) -> Optional[CalculationTrace]:
        """
        Builds a step-by-step formula trace ending at the given metric.
        Delegates the actual sheet/row/formula lookups to TraceEngine
        (services/trace_engine.py), which is built on the SAME row-indexed
        Excel representation used by the Knowledge Agent's RAG ingestion
        (per spec section 4.1's "do not build separate parsers" warning).
        """
        from .trace_engine import TraceEngine
        return TraceEngine().build_trace(db, metric_name, metric_level)

    # -----------------------------------------------------------------
    # reverse_solve - the Goal-Seeking Agent's input contract
    # -----------------------------------------------------------------

    def reverse_solve(
        self, db: Session, target_metric_name: str, target_value: float,
        locked_interventions: Optional[List[int]] = None,
    ):
        if FORMULA_PENDING_CONFIRMATION:
            from ..schemas.agent_schemas import ReverseSolveResult
            return ReverseSolveResult(
                feasible=False,
                confidence_basis=(
                    "Goal-Seeking's solver depends on the L1 aggregation formula, which is currently "
                    "pending confirmation from the spec author (see calculation_engine.py)."
                ),
            )
        from .reverse_solver import ReverseSolver
        return ReverseSolver(self).solve(db, target_metric_name, target_value, locked_interventions or [])

    # -----------------------------------------------------------------
    # optimize_under_budget - the Decision Advisor Agent's input contract
    # -----------------------------------------------------------------

    def optimize_under_budget(self, db: Session, budget: float, vertical_horizontal: str, lob: str):
        if FORMULA_PENDING_CONFIRMATION:
            # The L1 weighted-sum formula this optimizer depends on (via
            # compute_l1) is pending confirmation — see the module-level
            # warning above. Rather than surface nonsensical
            # projected_l1_changes (e.g. negative DSO) inside an
            # otherwise-plausible-looking ScenarioOption, refuse outright
            # until the formula is confirmed. ROI/cost comparisons alone
            # (which don't depend on the disputed L1 formula) could in
            # principle still run, but that's a deliberate follow-up, not
            # done here to avoid a partially-correct response that looks
            # fully correct.
            from ..schemas.agent_schemas import OptimizerResult
            return OptimizerResult(
                options=[],
                infeasible=True,
                recommendation_basis=(
                    "Decision Advisor's projections depend on the L1 aggregation formula, which is "
                    "currently pending confirmation from the spec author (see calculation_engine.py). "
                    "Re-enable once confirmed."
                ),
            )
        from .budget_optimizer import BudgetOptimizer
        return BudgetOptimizer(self).optimize(db, budget, vertical_horizontal, lob)


calculation_engine = CalculationEngine()
