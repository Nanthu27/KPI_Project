"""
What-If (Hypothetical Forward Simulation) Service
---------------------------------------------------
Answers questions like: "If I set TP Gamification to 55, Interaction
Analytics to 65, and QA Automation to 35, what is Revenue Growth?"

This is Scenario 1 from the original architecture proposal ("Decision
Advisor" forward simulation) — it was described in AI_CASCADE_README.md /
the original design doc but never actually implemented as a callable tool.
Without it, a message describing hypothetical intervention values and
asking for the resulting Business Outcome had nowhere correct to go, and
fell through to the Knowledge Agent (which then correctly reported it
couldn't find a definition for "BO" — the tool it needed didn't exist).

Design, reusing the EXACT safe pattern already proven in
`reverse_solver.py` (`_save_interventions` / `_restore_interventions`) and
`cascade/agent.py::_synced_to_live_page_state`:

  1. Snapshot the real (saved) intervention percentages, scoped to the
     current vertical/LOB.
  2. Temporarily write the hypothetical values into the DB.
  3. Call `simulation_service.recalculate()` — the SAME deterministic
     cascade engine used everywhere else. No formula is reimplemented here.
  4. Read the resulting L2/L1/BusinessOutcome values.
  5. Restore the original saved values and recalculate again, in a
     `finally` block, so a hypothetical "what if" question can never
     leave a side effect on the live simulator — exactly like dragging a
     slider and then undoing it.

This never touches anything outside the current vertical/LOB scope other
than the brief global recalculate() pass (same caveat already documented
in reverse_solver.py — safe because of the restore-in-finally guarantee).
"""
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session


def evaluate_hypothetical(
    db: Session,
    intervention_overrides: Dict[int, float],
    vertical: Optional[str] = None,
    lob: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Apply `intervention_overrides` ({intervention_id: hypothetical_percentage}),
    recalculate, capture the resulting metric values scoped to vertical/lob,
    then restore the original saved state. Never commits a lasting change.
    """
    from ...models import Intervention, L2Metric, L1Metric, BusinessOutcome
    from ...services import simulation_service

    def _scope(query, model):
        if vertical:
            query = query.filter(model.vertical_horizontal == vertical)
        if lob:
            query = query.filter(model.lob == lob)
        return query

    scoped_ivs = _scope(db.query(Intervention), Intervention).all()
    original = {iv.id: iv.percentage for iv in scoped_ivs}
    iv_by_id = {iv.id: iv for iv in scoped_ivs}

    # Interventions don't carry their own min_value/max_value columns (see
    # models.py — only BusinessOutcome/L1Metric/L2Metric do); an
    # intervention's adoption slider is always a fixed 0-100% range. Still
    # validate explicitly and report out-of-range requests back to the
    # caller instead of silently clamping (the old behavior): a user asking
    # "what if TP Simulation were 140%?" previously got a silent prediction
    # for 100% with no indication their number was ever changed.
    in_range_overrides: Dict[int, float] = {}
    out_of_range: List[Dict[str, Any]] = []
    IV_MIN, IV_MAX = 0.0, 100.0
    for iv_id, hypothetical_value in intervention_overrides.items():
        iv = iv_by_id.get(iv_id)
        name = iv.name if iv else f"IV-{iv_id}"
        if hypothetical_value > IV_MAX:
            out_of_range.append({
                "name": name, "requested": hypothetical_value,
                "min": IV_MIN, "max": IV_MAX, "direction": "above",
            })
        elif hypothetical_value < IV_MIN:
            out_of_range.append({
                "name": name, "requested": hypothetical_value,
                "min": IV_MIN, "max": IV_MAX, "direction": "below",
            })
        else:
            in_range_overrides[iv_id] = hypothetical_value

    try:
        for iv_id, hypothetical_value in in_range_overrides.items():
            db.query(Intervention).filter(Intervention.id == iv_id).update(
                {Intervention.percentage: hypothetical_value}
            )
        db.commit()
        simulation_service.recalculate(db)

        l2s = _scope(db.query(L2Metric), L2Metric).all()
        l1s = _scope(db.query(L1Metric), L1Metric).all()
        bos = _scope(db.query(BusinessOutcome), BusinessOutcome).all()

        def _serialize(items: List[Any]) -> List[Dict[str, Any]]:
            return [
                {
                    "name": m.name,
                    "unit": m.unit,
                    "default_value": m.default_value,
                    "current_value": m.current_value,
                    "improvement_percentage": m.improvement_percentage,
                    "higher_is_better": bool(m.higher_is_better),
                }
                for m in items
            ]

        result = {
            "applied_overrides": {
                iv.name: in_range_overrides[iv.id]
                for iv in scoped_ivs
                if iv.id in in_range_overrides
            },
            "out_of_range": out_of_range,
            "l2_metrics": _serialize(l2s),
            "l1_metrics": _serialize(l1s),
            "business_outcomes": _serialize(bos),
        }
        return result
    finally:
        for iv_id, pct in original.items():
            db.query(Intervention).filter(Intervention.id == iv_id).update(
                {Intervention.percentage: pct}
            )
        db.commit()
        simulation_service.recalculate(db)
