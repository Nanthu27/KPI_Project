"""
Reverse Solver Service
----------------------
Finds intervention slider configurations that achieve a target KPI value.

Strategy: Gradient-free search using the existing simulation API as an oracle.
We NEVER reimplement cascade math — we call the existing simulation_service.recalculate()
and read current_value from the DB, treating the existing engine as a pure black box.

Algorithm:
  1. Parse target (e.g. "DSO below 25" → find BO named like "DSO", target 25)
  2. Binary search / random hill-climb on intervention sliders
  3. Return top 3 configurations ranked by how close they get to target
"""
import itertools
import logging
import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class InterventionSetting:
    id: int
    name: str
    value: float  # 0-100


@dataclass
class SolverResult:
    interventions: List[InterventionSetting]
    achieved_value: float
    target_value: float
    gap_pct: float           # how far from target
    confidence: str          # "High" / "Medium" / "Low"
    description: str
    # Every intervention's value in this configuration, INCLUDING ones left
    # at 0% — `interventions` above filters those out for display, but a
    # 0% value is exactly as informative as a 100% one when explaining why
    # a target can't be reached further (e.g. "Payable Days extension is
    # already at 0, nothing more to give there"). Keyed by intervention
    # name, not id, so callers in kpi_tools.py don't need DB access again.
    full_settings: Dict[str, float] = field(default_factory=dict)


class ReverseSolver:
    """
    Goal-seeking engine that uses the existing simulation_service as oracle.
    Never reimplements cascade formulas.
    """

    def __init__(self, db: Session, vertical: Optional[str] = None, lob: Optional[str] = None):
        self.db = db
        # Vertical/LOB scope — every query below MUST be filtered by these,
        # otherwise the solver mixes interventions/metrics from other
        # verticals into its search and goal-seeking oracle.
        self.vertical = vertical
        self.lob = lob
        # Import here to avoid circular imports
        from ...services import simulation_service
        from ...models import BusinessOutcome, L1Metric, Intervention
        self._sim = simulation_service
        self._BO = BusinessOutcome
        self._L1 = L1Metric
        self._IV = Intervention

    def _scope(self, query, model):
        """Apply the current vertical/LOB filter to a query, if set."""
        if self.vertical:
            query = query.filter(model.vertical_horizontal == self.vertical)
        if self.lob:
            query = query.filter(model.lob == self.lob)
        return query

    def _current_interventions(self) -> List[Dict]:
        rows = self._scope(self.db.query(self._IV), self._IV).all()
        return [{"id": iv.id, "name": iv.name, "percentage": iv.percentage} for iv in rows]

    def _save_interventions(self, settings: Dict[int, float]):
        """Temporarily set intervention values and recalculate.

        NOTE: recalculate() cascades the WHOLE table (all verticals) because
        the underlying cascade engine is global. That is fine mathematically
        (each row's total_change only sums its own linked edges), but it does
        mean every recalculate() call briefly perturbs other verticals' live
        current_value too. Since we always restore in a `finally` block this
        is safe, but it does mean concurrent requests across verticals should
        not share a solver run — acceptable for this single-user simulator.
        """
        for iv_id, value in settings.items():
            self.db.query(self._IV).filter(self._IV.id == iv_id).update(
                {self._IV.percentage: max(0, min(100, value))}
            )
        self.db.commit()
        self._sim.recalculate(self.db)

    def _restore_interventions(self, original: List[Dict]):
        """Restore intervention values after search."""
        for iv in original:
            self.db.query(self._IV).filter(self._IV.id == iv["id"]).update(
                {self._IV.percentage: iv["percentage"]}
            )
        self.db.commit()
        self._sim.recalculate(self.db)

    def _read_kpi_value(self, metric_name: str) -> Optional[float]:
        """Read current_value from DB after recalculation.

        Scoped to the current vertical/LOB. Without this, a metric name that
        repeats across verticals (e.g. "BO_1", "Intervention_1" — the
        generic placeholder names used across every vertical) would silently
        resolve to whichever row happens to match first in the whole table,
        which is exactly how a Finance vertical's value could leak into a
        different vertical's response.
        """
        # Try Business Outcomes first
        bo = self._scope(
            self.db.query(self._BO).filter(self._BO.name.ilike(f"%{metric_name}%")),
            self._BO,
        ).first()
        if bo:
            return bo.current_value

        # Try L1 Metrics
        l1 = self._scope(
            self.db.query(self._L1).filter(self._L1.name.ilike(f"%{metric_name}%")),
            self._L1,
        ).first()
        if l1:
            return l1.current_value

        return None

    def _evaluate(self, settings: Dict[int, float], target_metric: str) -> Optional[float]:
        """Apply settings, recalculate, read result."""
        self._save_interventions(settings)
        return self._read_kpi_value(target_metric)

    def _score(self, achieved: Optional[float], target: float, higher_is_better: bool) -> float:
        """Lower score = closer to target.

        This is always the absolute distance to the target — never a
        one-sided "did we clear the threshold" check. The old version
        returned `max(0, achieved - target)` (or the mirror image for
        higher_is_better), which scores EVERY candidate that satisfies the
        inequality as a perfect 0 — a config landing dead-on the target and
        one undershooting it by 50 points tied exactly. Ties were then
        broken by search insertion order, not by which one a person would
        actually call "closest" — so the ranked #1 solution (what the
        Recommendation Card shows) and the prose the Goal Agent wrote while
        looking at each option's own gap_pct could end up naming two
        different configurations as the answer. Absolute distance can't
        produce that disagreement: whichever config is genuinely nearest
        the target is unambiguously rank #1 everywhere it's used.

        `higher_is_better` is kept as a parameter (some callers still pass
        it, and it still steers which extreme the search explores first)
        but no longer changes the ranking formula itself.
        """
        if achieved is None:
            return float("inf")
        return abs(achieved - target)

    def solve(
        self,
        target_metric: str,
        target_value: float,
        higher_is_better: bool = False,
        max_iterations: int = 60,
        n_results: int = 3,
        allowed_interventions: Optional[List[str]] = None,
    ) -> List[SolverResult]:
        """
        Find top N intervention configurations that approach the target.
        Returns results sorted by proximity to target.

        allowed_interventions: if provided, only intervention names in this
        list are varied during the search. All others are pinned at their
        current DB value (not forced to 0). This respects user constraints
        like "achieve 85% using only TP Simulation and Interaction Analytics".
        """
        original = self._current_interventions()
        iv_ids = [iv["id"] for iv in original]
        iv_names = {iv["id"]: iv["name"] for iv in original}

        if not iv_ids:
            return []

        # Partition into search IDs (varied) and pinned IDs (held constant).
        # Case-insensitive name match to handle minor user typos.
        if allowed_interventions:
            allowed_lower = {n.lower() for n in allowed_interventions}
            search_iv_ids = [
                iv_id for iv_id in iv_ids
                if iv_names.get(iv_id, "").lower() in allowed_lower
            ]
            pinned_settings = {
                iv["id"]: iv["percentage"]
                for iv in original
                if iv["id"] not in search_iv_ids
            }
            # If none of the named interventions matched (e.g. typo), fall
            # back to searching all — better to over-answer than silently
            # return nothing.
            if not search_iv_ids:
                search_iv_ids = iv_ids
                pinned_settings = {}
        else:
            search_iv_ids = iv_ids
            pinned_settings = {}

        # Deterministic, request-scoped RNG. Previously this used the
        # global, unseeded `random` module, so the SAME goal (same metric,
        # same target, same direction) could return a DIFFERENT "closest
        # achievable" answer on every call — e.g. one run says 87.65, the
        # next says 96.7, for the identical question. That's indistinguishable
        # from hallucination even though every individual number was really
        # simulated. Seeding on the actual inputs makes identical questions
        # reproducible while still varying naturally across different goals.
        seed_key = (target_metric, round(target_value, 4), higher_is_better, tuple(sorted(iv_ids)))
        # Python's built-in hash() is randomized per-process for strings
        # (PYTHONHASHSEED) by design, so it would only be stable within a
        # single running server. Use a stable digest instead so the same
        # goal reproduces the same answer even across restarts/deploys.
        import hashlib
        seed_int = int(hashlib.md5(repr(seed_key).encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed_int)

        def _rank_key(candidate):
            score, settings, _achieved = candidate
            # Round the score so float noise (e.g. 0.11999999999) doesn't
            # masquerade as a real difference from another candidate's
            # 0.12 — genuine ties need to actually tie for the second key
            # (simplicity) to kick in.
            total_change = sum(settings.values())
            return (round(score, 4), total_change)

        candidates: List[tuple] = []  # (score, settings_dict, achieved_value)

        try:
            # Strategy 0: always test the two natural extremes explicitly.
            # Without this, a "reduce X below N" goal could report an
            # implausibly high "closest achievable" floor simply because the
            # grid/perturbation search below never happened to try turning
            # every intervention all the way down to 0 — even though that
            # all-zero configuration is exactly what a real user would try
            # first, and is very often the actual best-achievable minimum.
            for extreme in (0, 100):
                settings = {**pinned_settings, **{iv_id: extreme for iv_id in search_iv_ids}}
                achieved = self._evaluate(settings, target_metric)
                score = self._score(achieved, target_value, higher_is_better)
                if achieved is not None:
                    candidates.append((score, dict(settings), achieved))

            # Strategy 1: Test combinations with finer granularity.
            # search_iv_ids is the set of interventions we're allowed to vary;
            # pinned_settings holds all others at their current values.
            if len(search_iv_ids) <= 2:
                # Fine-grained exhaustive grid: every 5% step — 21² = 441 evals
                test_values = list(range(0, 101, 5))
                for combo in itertools.product(test_values, repeat=len(search_iv_ids)):
                    settings = {**pinned_settings, **dict(zip(search_iv_ids, combo))}
                    achieved = self._evaluate(settings, target_metric)
                    score = self._score(achieved, target_value, higher_is_better)
                    if achieved is not None:
                        candidates.append((score, dict(settings), achieved))
            elif len(search_iv_ids) <= 4:
                # Medium exhaustive grid: every 10% step — 11⁴ = 14,641 evals max,
                # capped at max_iterations*4 to stay within reasonable time.
                test_values = list(range(0, 101, 10))
                for combo in itertools.product(test_values, repeat=len(search_iv_ids)):
                    settings = {**pinned_settings, **dict(zip(search_iv_ids, combo))}
                    achieved = self._evaluate(settings, target_metric)
                    score = self._score(achieved, target_value, higher_is_better)
                    if achieved is not None:
                        candidates.append((score, dict(settings), achieved))
                    if len(candidates) >= max_iterations * 4:
                        break
            else:
                # Random sampling with 10% step granularity for larger intervention sets
                test_values = list(range(0, 101, 10))
                for _ in range(max_iterations * 2):
                    settings = {**pinned_settings, **{iv_id: rng.choice(test_values) for iv_id in search_iv_ids}}
                    achieved = self._evaluate(settings, target_metric)
                    score = self._score(achieved, target_value, higher_is_better)
                    if achieved is not None:
                        candidates.append((score, dict(settings), achieved))

            # Strategy 2: Focus search around best candidate with fine-grained perturbations.
            # Uses ±5 and ±1 steps (in addition to ±10 and ±20) so the solver can
            # home in on precise values instead of bouncing between round multiples of 10.
            if candidates:
                candidates.sort(key=_rank_key)
                best_settings = candidates[0][1]

                for _ in range(25):
                    # Perturb only the search IDs; pinned IDs stay at their fixed values.
                    perturbed = dict(pinned_settings)
                    for iv_id in search_iv_ids:
                        val = best_settings.get(iv_id, 0)
                        delta = rng.choice([-20, -10, -5, -1, 0, 1, 5, 10, 20])
                        perturbed[iv_id] = max(0, min(100, val + delta))
                    achieved = self._evaluate(perturbed, target_metric)
                    score = self._score(achieved, target_value, higher_is_better)
                    if achieved is not None:
                        candidates.append((score, perturbed, achieved))

            # Strategy 3: Incremental single-IV optimization with 5% granularity.
            # Baseline is the "neutral direction" extreme (0 when searching for a lower
            # value, 50 otherwise) so this strategy explores the low end of
            # the space too, instead of only ever starting from 50.
            baseline = 0 if not higher_is_better else 50
            for focus_id in search_iv_ids[:4]:  # top 4 search interventions
                for val in range(0, 101, 5):  # 0, 5, 10, 15, ..., 95, 100
                    settings = {**pinned_settings, **{iv_id: baseline for iv_id in search_iv_ids}}
                    settings[focus_id] = val
                    achieved = self._evaluate(settings, target_metric)
                    score = self._score(achieved, target_value, higher_is_better)
                    if achieved is not None:
                        candidates.append((score, dict(settings), achieved))

        finally:
            self._restore_interventions(original)

        # Deduplicate and rank
        candidates.sort(key=_rank_key)
        seen = set()
        unique_candidates = []
        for score, settings, achieved in candidates:
            key = tuple(sorted(settings.items()))
            if key not in seen:
                seen.add(key)
                unique_candidates.append((score, settings, achieved))

        # Build results
        results = []
        for score, settings, achieved in unique_candidates[:n_results]:
            gap = abs(achieved - target_value)
            # Relative to whichever of target/achieved is larger, not just
            # the target — dividing by a small target alone (e.g. target=10
            # while sitting at 76.89) produces triple-digit percentages that
            # read as far more alarming/confusing than the actual gap is.
            # Using the larger side gives a stable, interpretable "how far
            # off, as a fraction of the bigger number" in both directions,
            # and doesn't change near-miss cases where target and achieved
            # are already close together.
            denominator = max(abs(target_value), abs(achieved), 1)
            gap_pct = min((gap / denominator) * 100, 999.9)  # cap so UI never shows e.g. 8053.6%

            if gap_pct < 5:
                confidence = "High"
            elif gap_pct < 15:
                confidence = "Medium"
            else:
                confidence = "Low"

            iv_settings = [
                InterventionSetting(id=iv_id, name=iv_names.get(iv_id, f"IV-{iv_id}"), value=round(val))
                for iv_id, val in sorted(settings.items(), key=lambda x: x[1], reverse=True)
                if val > 0
            ]

            # Human-readable description — values shown as whole numbers since
            # sliders snap to integers on the UI.
            iv_desc = ", ".join([f"{iv.name} at {iv.value}%" for iv in iv_settings[:3]])
            direction = "above" if higher_is_better else "below"
            results.append(SolverResult(
                interventions=iv_settings,
                achieved_value=round(achieved, 2),
                target_value=target_value,
                gap_pct=round(gap_pct, 1),
                confidence=confidence,
                description=f"Set {iv_desc}. Achieves {target_metric} of {achieved:.2f} (target: {direction} {target_value}).",
                full_settings={iv_names.get(iv_id, f"IV-{iv_id}"): round(val) for iv_id, val in settings.items()},
            ))

        return results


def run_reverse_solver(
    db: Session,
    target_metric: str,
    target_value: float,
    higher_is_better: bool = False,
    vertical: Optional[str] = None,
    lob: Optional[str] = None,
    allowed_interventions: Optional[List[str]] = None,
) -> List[SolverResult]:
    solver = ReverseSolver(db, vertical=vertical, lob=lob)
    return solver.solve(target_metric, target_value, higher_is_better,
                        allowed_interventions=allowed_interventions)
