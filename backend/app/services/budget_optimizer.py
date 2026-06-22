"""
BudgetOptimizer - deterministic math behind the Decision Advisor Agent
(spec section 5). NO LLM involved here; the agent only narrates this
output.

CRITICAL DATA-DEPENDENCY NOTE (spec section 5, "Dependency check before
building"): this optimizer requires `cost_per_unit` per intervention.
That field did not exist anywhere in the original Excel impact matrix or
this app's schema - it has been added to the Intervention model with
PLACEHOLDER/ESTIMATED values (see seed_data.py) pending real cost data
from the BRD/Finance owner. Every option this optimizer returns is only
as trustworthy as that placeholder cost data; the response always carries
a `cost_data_is_placeholder` flag so the UI/agent can disclose this.

Algorithm (per FR-5.1): discretizes each intervention into 10% steps
(0, 10, 20, ..., max_value), enumerates combinations of up to 2
interventions at a time (keeps the search space bounded - same spirit as
the spec's worked example, which shows 2-intervention and 4-intervention
options), filters out anything over budget, scores by ROI%, and returns
the top 3 by ROI among budget-feasible options.
"""
import itertools
from typing import List
from sqlalchemy.orm import Session

from ..models import Intervention, L1Metric
from ..schemas.agent_schemas import OptimizerResult, ScenarioOption

STEP_PCT = 10
MAX_COMBINATION_SIZE = 2  # per FR-5.1: bound the search space
TOP_N_OPTIONS = 3
ASSUMED_ANNUAL_BENEFIT_PER_REVENUE_PCT = 1_000_000  # PLACEHOLDER scaling factor, see note below
ASSUMED_PAYBACK_DIVISOR_GUARD = 1e-6


class BudgetOptimizer:
    def __init__(self, engine):
        self.engine = engine

    def optimize(self, db: Session, budget: float, vertical_horizontal: str, lob: str) -> OptimizerResult:
        interventions: List[Intervention] = (
            db.query(Intervention)
            .filter(Intervention.vertical_horizontal == vertical_horizontal, Intervention.lob == lob)
            .all()
        )
        interventions = [iv for iv in interventions if iv.cost_per_unit > 0]

        if not interventions:
            return OptimizerResult(
                options=[],
                infeasible=True,
                recommendation_basis="No interventions in this LOB have cost_per_unit data configured.",
            )

        candidate_options: List[ScenarioOption] = []

        for combo_size in range(1, min(MAX_COMBINATION_SIZE, len(interventions)) + 1):
            for combo in itertools.combinations(interventions, combo_size):
                option = self._evaluate_combo(db, combo, budget, vertical_horizontal, lob)
                if option is not None:
                    candidate_options.append(option)

        feasible_options = [o for o in candidate_options if o.total_cost <= budget]

        if not feasible_options:
            return OptimizerResult(options=[], infeasible=True, recommendation_basis="No combination of interventions fits within this budget.")

        feasible_options.sort(key=lambda o: o.roi_pct, reverse=True)
        top_options = feasible_options[:TOP_N_OPTIONS]

        recommended = max(top_options, key=lambda o: (o.confidence_score >= 0.85, o.roi_pct))

        return OptimizerResult(
            options=top_options,
            recommended_option_label=recommended.label,
            recommendation_basis="highest ROI per dollar within budget, with confidence above 85% threshold" if recommended.confidence_score >= 0.85 else "highest ROI per dollar within budget",
        )

    def _evaluate_combo(self, db: Session, combo, budget: float, vertical_horizontal: str, lob: str):
        best_option = None
        best_roi = float("-inf")

        # Search discretized intensity levels for this combination of interventions,
        # keep the cheapest-within-budget, highest-ROI configuration found.
        step_ranges = [range(0, int(iv.max_value) + 1, STEP_PCT) for iv in combo]
        for levels in itertools.product(*step_ranges):
            if all(lv == 0 for lv in levels):
                continue
            total_cost = sum(iv.cost_per_unit * (lv / 100.0) for iv, lv in zip(combo, levels))
            if total_cost <= 0 or total_cost > budget:
                continue

            intervention_values = {iv.id: float(lv) for iv, lv in zip(combo, levels)}
            # Hold every OTHER intervention in this LOB at 0 so this option reflects
            # ONLY the combo being evaluated (apples-to-apples comparison across options).
            for iv in db.query(Intervention).filter(
                Intervention.vertical_horizontal == vertical_horizontal, Intervention.lob == lob
            ).all():
                intervention_values.setdefault(iv.id, 0.0)

            l2_new = self.engine.compute_l2(db, intervention_values)
            l1_new = self.engine.compute_l1(db, l2_new)

            l1_metrics = db.query(L1Metric).filter(
                L1Metric.vertical_horizontal == vertical_horizontal, L1Metric.lob == lob
            ).all()
            l1_deltas = {}
            projected_l1_changes = []
            for m in l1_metrics:
                new_val = l1_new.get(m.id, m.default_value)
                delta_pct = round((new_val - m.default_value) / m.default_value * 100, 2) if m.default_value else 0.0
                l1_deltas[m.id] = delta_pct
                if abs(delta_pct) > 0.01:
                    projected_l1_changes.append({"name": m.name, "from": m.default_value, "to": round(new_val, 2)})

            revenue_impact_pct = self.engine.compute_revenue_impact(db, l1_deltas)
            # PLACEHOLDER monetization: converts revenue_impact_pct into a dollar benefit
            # using a flat assumed-revenue scaling factor, since no real revenue baseline
            # is configured per LOB yet. This is clearly a placeholder, not a Finance-
            # approved figure - see module docstring.
            annual_benefit = revenue_impact_pct * (ASSUMED_ANNUAL_BENEFIT_PER_REVENUE_PCT / 100.0)
            roi_pct = round(((annual_benefit - total_cost) / total_cost) * 100, 1) if total_cost > 0 else 0.0
            payback_months = round((total_cost / max(annual_benefit / 12, ASSUMED_PAYBACK_DIVISOR_GUARD)), 1) if annual_benefit > 0 else 999.0

            if roi_pct > best_roi:
                best_roi = roi_pct
                confidence_score = _estimate_confidence(levels, combo)
                label = " + ".join(iv.name for iv in combo)
                best_option = ScenarioOption(
                    label=f"{label} ({', '.join(str(lv) + '%' for lv in levels)})",
                    interventions=[{"name": iv.name, "value": lv} for iv, lv in zip(combo, levels)],
                    total_cost=round(total_cost, 2),
                    roi_pct=roi_pct,
                    payback_months=min(payback_months, 999.0),
                    projected_l1_changes=projected_l1_changes,
                    confidence_score=confidence_score,
                )

        return best_option


def _estimate_confidence(levels, combo) -> float:
    """
    PROVISIONAL heuristic confidence score, pending Finance/Analytics
    sign-off (spec section 6.4, item 5). Same approach as ReverseSolver's
    heuristic: intensity levels close to each intervention's typical/
    default range score higher than levels close to max_value.
    """
    distances = []
    for lv, iv in zip(levels, combo):
        headroom = max(iv.max_value, 1e-6)
        distances.append(lv / headroom)
    avg = sum(distances) / len(distances) if distances else 0.5
    return round(max(0.3, 1.0 - (avg * 0.5)), 2)
