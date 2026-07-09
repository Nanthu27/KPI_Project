"""
Page Context Service
--------------------
Fetches the LIVE calculated data for the currently selected vertical/LOB
directly from the simulation engine.

This is the correct approach:
  - Backend calls its OWN simulation_service with the current filters
  - No reliance on frontend passing data (which can be stale or wrong)
  - Always returns real server-calculated values

Called by the agent BEFORE building any prompt.
"""
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def fetch_live_page_data(
    db: Session,
    vertical: Optional[str] = None,
    lob: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch all live KPI data for the given vertical/LOB from the simulation engine.
    This is the single source of truth — always fresh, always calculated.
    """
    try:
        from ...services import simulation_service
        from ...services.serialization_helpers import (
            attach_l1_business_outcome_links,
            attach_l2_l1_links,
            attach_intervention_l2_links,
        )

        # Run recalculation and get everything
        data = simulation_service.recalculate_and_fetch(db)

        def scoped(items):
            """Filter to current vertical/LOB — exactly what the UI dropdown does."""
            result = items
            if vertical:
                result = [i for i in result if i.vertical_horizontal == vertical]
            if lob:
                result = [i for i in result if i.lob == lob]
            return result

        bos  = scoped(data["business_outcomes"])
        l1s  = scoped(data["l1_metrics"])
        l2s  = scoped(data["l2_metrics"])
        ivs  = scoped(data["interventions"])

        # Attach relationship links
        attach_intervention_l2_links(db, ivs)
        attach_l2_l1_links(db, l2s)
        attach_l1_business_outcome_links(db, l1s)

        def serialize(items, include_pct=False):
            result = []
            for m in items:
                entry = {
                    "name": m.name,
                    "default_value": round(m.default_value, 4),
                    "current_value": round(m.current_value, 4),
                    "improvement_pct": round(m.improvement_percentage or 0, 2),
                    "higher_is_better": getattr(m, "higher_is_better", False),
                    "unit": getattr(m, "unit", "%"),
                    "vertical": getattr(m, "vertical_horizontal", vertical or ""),
                    "lob": getattr(m, "lob", lob or ""),
                }
                if include_pct:
                    entry["percentage"] = getattr(m, "percentage", 0)
                result.append(entry)
            return result

        active_ivs = [iv for iv in ivs if (getattr(iv, "percentage", 0) or 0) > 0]

        return {
            "ok": True,
            "vertical": vertical or "All",
            "lob": lob or "All",
            "active_interventions": serialize(active_ivs, include_pct=True),
            "all_interventions": serialize(ivs, include_pct=True),
            "business_outcomes": serialize(bos),
            "l1_metrics": serialize(l1s),
            "l2_metrics": serialize(l2s),
            # Summary stats
            "summary": {
                "total_bos": len(bos),
                "total_l1": len(l1s),
                "total_l2": len(l2s),
                "total_interventions": len(ivs),
                "active_interventions": len(active_ivs),
                "bos_improved": len([b for b in bos if (b.improvement_percentage or 0) > 0]),
                "bos_declined": len([b for b in bos if (b.improvement_percentage or 0) < 0]),
            },
        }

    except Exception as e:
        logger.error(f"fetch_live_page_data failed: {e}", exc_info=True)
        return {
            "ok": False,
            "vertical": vertical or "All",
            "lob": lob or "All",
            "error": str(e),
            "active_interventions": [],
            "all_interventions": [],
            "business_outcomes": [],
            "l1_metrics": [],
            "l2_metrics": [],
            "summary": {},
        }
