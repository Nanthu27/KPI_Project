"""
ReverseSolver - deterministic math behind the Goal-Seeking Agent (spec
section 2). NO LLM involved here; the agent only narrates this output.

Approach: since CalculationEngine's formula is piecewise-linear in each
intervention's percentage (L2_new is linear in intervention%, L1_new and
BusinessOutcome_new are linear combinations of L2/L1 values), we solve
for the intervention percentages via a bounded line-search / scaling
approach rather than a full LP solver, which keeps this dependency-free
(no scipy/numpy requirement) and easy to audit:

1. Find every intervention that has a path (via the link tables) to the
   target metric.
2. Compute each such intervention's "sensitivity" - how much the target
   metric moves per 1 percentage-point of that intervention, holding all
   other interventions at their CURRENT value (a first-order partial
   derivative, computed by perturbing the live calculation engine by a
   small epsilon - cheap and always consistent with whatever formula
   CalculationEngine.compute_l2/l1/business_outcomes happens to use, so
   ReverseSolver never has its own duplicate copy of the math).
3. Distribute the required total change proportionally across the
   contributing interventions' current values (locked interventions are
   excluded and held fixed), then scale up iteratively until the target
   is hit or every contributing intervention is clamped at its max_value.
4. If even maxing out every contributing intervention can't reach the
   target, return feasible=False with max_achievable_value set.
"""
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from ..models import Intervention, L1Metric, L2Metric, BusinessOutcome
from ..schemas.agent_schemas import ReverseSolveResult

EPSILON_PCT = 1.0  # perturbation size (percentage points) used for the sensitivity probe
MAX_ITERATIONS = 25
CONVERGENCE_TOLERANCE = 0.01  # accept within 1% of target


class ReverseSolver:
    def __init__(self, engine):
        self.engine = engine  # CalculationEngine instance (avoids circular import at module load)

    def _find_target_metric(self, db: Session, target_metric_name: str):
        """Looks up the target metric by (case-insensitive, substring-tolerant) name across L1 then BusinessOutcome."""
        name_lower = target_metric_name.strip().lower()

        l1_matches = [
            m for m in db.query(L1Metric).all()
            if name_lower in m.name.lower() or m.name.lower() in name_lower
        ]
        if l1_matches:
            return l1_matches[0], "l1"

        bo_matches = [
            m for m in db.query(BusinessOutcome).all()
            if name_lower in m.name.lower() or m.name.lower() in name_lower
        ]
        if bo_matches:
            return bo_matches[0], "business_outcome"

        return None, None

    def _evaluate_target(self, db: Session, intervention_values: Dict[int, float], target_id: int, target_level: str) -> float:
        l2_new = self.engine.compute_l2(db, intervention_values)
        l1_new = self.engine.compute_l1(db, l2_new)
        if target_level == "l1":
            return l1_new.get(target_id, 0.0)
        bo_new = self.engine.compute_business_outcomes(db, l1_new)
        return bo_new.get(target_id, 0.0)

    def solve(
        self, db: Session, target_metric_name: str, target_value: float,
        locked_interventions: Optional[List[int]] = None,
    ) -> ReverseSolveResult:
        locked = set(locked_interventions or [])
        target_metric, target_level = self._find_target_metric(db, target_metric_name)

        if target_metric is None:
            return ReverseSolveResult(
                feasible=False,
                confidence_basis=f"Could not resolve '{target_metric_name}' to a known L1 metric or Business Outcome.",
            )

        all_interventions: List[Intervention] = db.query(Intervention).all()
        intervention_values = {iv.id: iv.percentage for iv in all_interventions}

        current_value = self._evaluate_target(db, intervention_values, target_metric.id, target_level)
        direction = -1 if target_value < current_value else 1  # are we trying to decrease or increase the metric?

        # Step 1: sensitivity probe - perturb each unlocked intervention by
        # +EPSILON_PCT (holding others fixed) and see how much the target moves.
        sensitivities: Dict[int, float] = {}
        for iv in all_interventions:
            if iv.id in locked:
                continue
            probe_values = dict(intervention_values)
            probe_values[iv.id] = min(probe_values[iv.id] + EPSILON_PCT, iv.max_value)
            probed = self._evaluate_target(db, probe_values, target_metric.id, target_level)
            delta = probed - current_value
            if abs(delta) > 1e-9:
                sensitivities[iv.id] = delta / EPSILON_PCT

        contributing_ids = [iv_id for iv_id, s in sensitivities.items() if (s * direction) != 0 and (s < 0) == (direction < 0)]
        # contributing = interventions whose increase actually moves the target in the direction we need
        contributing_ids = [iv_id for iv_id in sensitivities if (sensitivities[iv_id] < 0 and direction < 0) or (sensitivities[iv_id] > 0 and direction > 0)]

        if not contributing_ids:
            return ReverseSolveResult(
                feasible=False,
                confidence_basis="No intervention in this LOB has a measurable effect in the direction needed to reach this target.",
                max_achievable_value=current_value,
            )

        # Step 2: iteratively scale up the contributing interventions
        # proportionally to their sensitivity magnitude, re-checking against
        # max_value clamps, until we hit the target or exhaust headroom.
        working_values = dict(intervention_values)
        iv_by_id = {iv.id: iv for iv in all_interventions}

        for _ in range(MAX_ITERATIONS):
            current = self._evaluate_target(db, working_values, target_metric.id, target_level)
            remaining = target_value - current
            if abs(remaining) <= max(CONVERGENCE_TOLERANCE * abs(target_value), 0.01):
                break

            # Recompute sensitivities at the current working point (formula may be nonlinear
            # across levels even though each compute_* step is linear, so refresh each pass).
            local_sensitivities = {}
            for iv_id in contributing_ids:
                probe_values = dict(working_values)
                probe_values[iv_id] = min(probe_values[iv_id] + EPSILON_PCT, iv_by_id[iv_id].max_value)
                if probe_values[iv_id] == working_values[iv_id]:
                    continue  # already at max, no headroom to probe
                probed = self._evaluate_target(db, probe_values, target_metric.id, target_level)
                local_sensitivities[iv_id] = (probed - current) / EPSILON_PCT

            total_sensitivity = sum(abs(s) for s in local_sensitivities.values())
            if total_sensitivity < 1e-9:
                break  # no more headroom on any contributing intervention

            any_moved = False
            for iv_id, s in local_sensitivities.items():
                if s == 0:
                    continue
                share = abs(s) / total_sensitivity
                desired_delta_pct = (remaining / s) * share if s != 0 else 0
                new_val = working_values[iv_id] + desired_delta_pct
                new_val = max(0.0, min(new_val, iv_by_id[iv_id].max_value))
                if new_val != working_values[iv_id]:
                    any_moved = True
                working_values[iv_id] = new_val
            if not any_moved:
                break

        final_value = self._evaluate_target(db, working_values, target_metric.id, target_level)
        feasible = abs(final_value - target_value) <= max(CONVERGENCE_TOLERANCE * abs(target_value), 0.5)

        recommended = []
        for iv_id in contributing_ids:
            iv = iv_by_id[iv_id]
            recommended.append({
                "name": iv.name,
                "current": _clean(intervention_values[iv_id]),
                "recommended": _clean(working_values[iv_id]),
            })

        # Projected downstream outcome for display
        l2_new = self.engine.compute_l2(db, working_values)
        l1_new = self.engine.compute_l1(db, l2_new)
        bo_new = self.engine.compute_business_outcomes(db, l1_new)
        l1_deltas = {}
        for m in db.query(L1Metric).all():
            if m.default_value:
                l1_deltas[m.id] = round((l1_new.get(m.id, m.default_value) - m.default_value) / m.default_value * 100, 2)
        revenue_impact_pct = self.engine.compute_revenue_impact(db, l1_deltas)

        projected_outcome = {
            target_metric.name: _clean(final_value),
            "revenue_impact_pct": revenue_impact_pct,
        }

        confidence_score, confidence_basis = _estimate_confidence(working_values, intervention_values, iv_by_id, feasible)

        return ReverseSolveResult(
            feasible=feasible,
            recommended_interventions=recommended,
            projected_outcome=projected_outcome,
            confidence_score=confidence_score,
            confidence_basis=confidence_basis,
            max_achievable_value=_clean(final_value) if not feasible else None,
        )


def _clean(value: float) -> float:
    return round(value, 2)


def _estimate_confidence(working_values, original_values, iv_by_id, feasible: bool):
    """
    PROVISIONAL heuristic confidence score, pending Finance/Analytics
    sign-off on a real methodology (spec section 6.4, item 5 - flagged
    open dependency). Computes confidence as a function of how far the
    recommended values are from each intervention's current value,
    relative to its allowed range: small moves -> high confidence,
    moves near the max_value ceiling -> low confidence. This is NOT a
    validated statistical model and must be replaced once Finance
    defines the real methodology (historical variance / backtested
    accuracy / distance-from-tested-range, per the spec).
    """
    if not feasible:
        return 0.45, "PROVISIONAL heuristic (pending Finance sign-off): infeasible solve, capped at low confidence."

    if not working_values:
        return 0.5, "PROVISIONAL heuristic (pending Finance sign-off): no contributing interventions found."

    distances = []
    for iv_id, new_val in working_values.items():
        iv = iv_by_id[iv_id]
        original = original_values.get(iv_id, 0.0)
        move = abs(new_val - original)
        headroom = max(iv.max_value - original, 1e-6)
        distances.append(min(move / headroom, 1.0))

    avg_distance = sum(distances) / len(distances)
    # avg_distance near 0 (small move) -> high confidence; near 1 (maxed out) -> low confidence
    score = round(max(0.3, 1.0 - (avg_distance * 0.65)), 2)
    basis = (
        f"PROVISIONAL heuristic (pending Finance sign-off): based on how close the recommended "
        f"values are to each intervention's tested/default range (avg. headroom used: {round(avg_distance * 100)}%)."
    )
    return score, basis
