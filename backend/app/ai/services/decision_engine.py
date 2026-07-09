"""
Decision Intelligence Engine
-----------------------------
Single, deterministic source of truth for turning a raw simulation result
(a set of intervention percentages + the KPI values they produce) into a
judgment: is this scenario good, risky, expensive, or the best available
option? This does NOT replace `simulation_service` (the cascade math) or
`reverse_solver.py` (the search) — it consumes their output.

Why this exists (see PATCH_NOTES / gap analysis): before this module,
`decision_advisor_tool` ranked strategies purely by aggregate KPI movement
(`avg_bo_improvement`), and `goal_tool` reported reachability with no risk
or cost context. Both agents were making the same kind of judgment
independently, with no shared definition of "good", which is exactly the
inconsistency risk called out in AGENT_TRAINING_NOTES / PATCH_NOTES: two
agents describing the same underlying scenario differently.

Principle (explicitly, per the "AI cannot invent business knowledge"
discussion): this engine NEVER invents risk, cost, or confidence — those
come only from admin-configured `Intervention.risk_level` / `.cost_level` /
`.effort_weeks` / `.confidence_pct` (see models.py). All this module does is
aggregate that already-declared metadata into a single scenario, then apply
one transparent, fixed weighting formula to rank scenarios consistently.
Swap `DEFAULT_WEIGHTS` if the business wants to weight goal-achievement vs.
risk vs. cost vs. confidence differently — that is a business decision too,
so it lives here as one named constant, not scattered across prompts.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

# Ordinal weight for aggregating Low/Medium/High into a 0-1 "badness" score.
_LEVEL_WEIGHT = {"Low": 0.15, "Medium": 0.5, "High": 0.9}
_WEIGHT_LEVEL = sorted(_LEVEL_WEIGHT.items(), key=lambda kv: kv[1])  # for reverse lookup


def _level_to_score(level: Optional[str]) -> float:
    return _LEVEL_WEIGHT.get((level or "Medium").title(), 0.5)


def _score_to_level(score: float) -> str:
    """Inverse of _level_to_score — snaps an aggregated 0-1 score back to a label."""
    if score < 0.33:
        return "Low"
    if score < 0.67:
        return "Medium"
    return "High"


# Default scoring weights. Must sum to 1.0. Mirrors the "40% Goal / 25% Risk
# / 20% Cost / 15% Confidence" pattern requested across the design docs;
# exposed as a parameter so a caller can supply a different mix (e.g. a
# user filter like "Risk: LOW only" should narrow the candidate set FIRST,
# then this default weighting still applies within the remaining options).
DEFAULT_WEIGHTS = {
    "goal": 0.40,
    "risk": 0.25,
    "cost": 0.20,
    "confidence": 0.15,
}


@dataclass
class ScenarioProfile:
    """Risk/cost/confidence rolled up from the interventions used in one scenario."""
    risk_level: str
    cost_level: str
    confidence_pct: float
    effort_weeks: float
    # Per-intervention breakdown, for transparency in the agent's explanation
    # ("High risk because X and Y are pushed above 80%") rather than a bare label.
    contributors: List[Dict] = field(default_factory=list)


@dataclass
class ScenarioScore:
    goal_achievement_pct: float  # 0-100, 100 = target hit exactly / fully reachable
    risk_level: str
    cost_level: str
    confidence_pct: float
    score: float                 # 0-100 weighted composite, higher = better
    recommended: bool
    reason: str


def profile_settings(db: Session, settings_by_name: Dict[str, float], vertical: Optional[str] = None, lob: Optional[str] = None) -> ScenarioProfile:
    """
    Roll up risk/cost/confidence for a scenario, given {intervention_name: pct}.

    Weighting: an intervention only contributes to risk/cost in proportion to
    how hard it's being pushed (pct/100) — pinning a "High risk" intervention
    at 0% shouldn't make the whole scenario read as high-risk, and pushing a
    "Low risk" intervention to 100% shouldn't either. Confidence is a
    pct-weighted average of the interventions actually in play (interventions
    at 0% don't affect the reported confidence, since they're not driving
    anything).
    """
    from ...models import Intervention

    def _scope(q):
        if vertical:
            q = q.filter(Intervention.vertical_horizontal == vertical)
        if lob:
            q = q.filter(Intervention.lob == lob)
        return q

    rows = _scope(db.query(Intervention)).all()
    by_name = {iv.name: iv for iv in rows}

    total_weight = 0.0
    risk_acc = 0.0
    cost_acc = 0.0
    conf_acc = 0.0
    effort_acc = 0.0
    contributors = []

    for name, pct in settings_by_name.items():
        iv = by_name.get(name)
        if iv is None or pct <= 0:
            continue
        w = pct / 100.0
        total_weight += w
        risk_acc += _level_to_score(iv.risk_level) * w
        cost_acc += _level_to_score(iv.cost_level) * w
        conf_acc += (iv.confidence_pct or 90.0) * w
        effort_acc = max(effort_acc, (iv.effort_weeks or 4.0))  # effort = critical path, not summed
        contributors.append({
            "name": name,
            "pct": pct,
            "risk_level": iv.risk_level,
            "cost_level": iv.cost_level,
        })

    if total_weight <= 0:
        # No interventions active at all — nothing to roll up. Treat as
        # low risk/cost (doing nothing is safe) with neutral confidence.
        return ScenarioProfile(risk_level="Low", cost_level="Low", confidence_pct=90.0, effort_weeks=0.0, contributors=[])

    return ScenarioProfile(
        risk_level=_score_to_level(risk_acc / total_weight),
        cost_level=_score_to_level(cost_acc / total_weight),
        confidence_pct=round(conf_acc / total_weight, 1),
        effort_weeks=round(effort_acc, 1),
        contributors=contributors,
    )


def score_scenario(
    goal_achievement_pct: float,
    profile: ScenarioProfile,
    weights: Optional[Dict[str, float]] = None,
) -> ScenarioScore:
    """
    Combine goal achievement + risk + cost + confidence into one 0-100
    composite score. Higher is better. This is the ONE ranking formula both
    Goal Agent and Decision Advisor should use, so the two agents can never
    disagree about which scenario is "best" for reasons that boil down to
    using different math.
    """
    w = weights or DEFAULT_WEIGHTS
    goal_component = max(0.0, min(100.0, goal_achievement_pct))
    risk_component = (1.0 - _level_to_score(profile.risk_level)) * 100.0
    cost_component = (1.0 - _level_to_score(profile.cost_level)) * 100.0
    conf_component = max(0.0, min(100.0, profile.confidence_pct))

    composite = (
        w.get("goal", 0) * goal_component
        + w.get("risk", 0) * risk_component
        + w.get("cost", 0) * cost_component
        + w.get("confidence", 0) * conf_component
    )

    recommended = goal_component >= 80 and profile.risk_level != "High"
    if recommended:
        reason = f"Reaches {goal_component:.0f}% of the goal at {profile.risk_level.lower()} risk and {profile.cost_level.lower()} cost."
    elif goal_component < 80:
        reason = f"Only reaches {goal_component:.0f}% of the goal — not the strongest option toward the target."
    else:
        reason = f"Reaches the goal, but at {profile.risk_level.lower()} risk — a lower-risk option may be preferable."

    return ScenarioScore(
        goal_achievement_pct=round(goal_component, 1),
        risk_level=profile.risk_level,
        cost_level=profile.cost_level,
        confidence_pct=profile.confidence_pct,
        score=round(composite, 1),
        recommended=recommended,
        reason=reason,
    )


def rank_scenarios(scored: List[Dict], weights: Optional[Dict[str, float]] = None) -> List[Dict]:
    """
    Convenience for callers building a list of {"goal_achievement_pct":...,
    "profile": ScenarioProfile, ...extra fields} dicts: attaches a
    ScenarioScore to each and returns the list sorted best-first (mutates
    and returns the same dicts, adding a "decision" key).
    """
    for item in scored:
        item["decision"] = score_scenario(item["goal_achievement_pct"], item["profile"], weights)
    return sorted(scored, key=lambda item: item["decision"].score, reverse=True)
