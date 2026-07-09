"""
Excel Trace Service
-------------------
Reads the actual KPI relationship graph from the F&A Excel workbook.
Never hallucinating formulas — only reads what is actually in the file.

Provides:
  - trace_kpi(name): full upstream/downstream path for a KPI
  - get_formula_path(metric): Intervention → L2 → L1 → BO chain
  - list_relationships(): all defined impact factors

Falls back to DB-derived relationships if Excel file is not present.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class KpiRelationship:
    parent_name: str
    child_name: str
    impact_factor: float
    level: str   # "IV→L2", "L2→L1", "L1→BO"


@dataclass
class KpiTracePath:
    metric_name: str
    metric_level: str  # "intervention", "l2", "l1", "business_outcome"
    upstream: List[KpiRelationship]    # what drives this metric
    downstream: List[KpiRelationship]  # what this metric drives
    full_chain: str  # human-readable path


class ExcelTraceService:
    """
    Reads F&A Excel impact matrix and exposes relationship data.
    Database-derived fallback if Excel is unavailable.
    """

    def __init__(self, db=None, vertical: Optional[str] = None, lob: Optional[str] = None):
        self.db = db
        self.vertical = vertical
        self.lob = lob
        self._relationships: List[KpiRelationship] = []
        self._loaded = False

        # Possible Excel file locations
        self._excel_candidates = [
            "/mnt/user-data/uploads/ROI_Measurement_Framework_and_Simulation_Model_F_A_V2_1_1__1_.xlsx",
            "/mnt/user-data/uploads/Calculation_Sheet_KPI_Simulator.xlsx",
        ]

    def _ensure_loaded(self):
        if self._loaded:
            return
        loaded = False

        # IMPORTANT: the bundled Excel workbook is a Finance & Accounting
        # specific reference file. If it exists on disk, only use it when the
        # currently selected vertical actually IS Finance & Accounting.
        # Previously this check didn't exist, so ANY vertical's trace request
        # would silently return Finance formulas as soon as that file was
        # present — this was the source of "finance vertical intervention
        # detail" leaking into other verticals' Trace/Insight responses.
        is_finance_vertical = (
            self.vertical is None
            or "finance" in self.vertical.lower()
        )

        if is_finance_vertical:
            for path in self._excel_candidates:
                if os.path.exists(path):
                    try:
                        self._load_from_excel(path)
                        loaded = True
                        break
                    except Exception as e:
                        logger.warning(f"Failed to load Excel from {path}: {e}")

        if not loaded:
            self._load_from_db()

        self._loaded = True

    def _load_from_excel(self, path: str):
        """Parse relationship sheets from the F&A Excel workbook."""
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        logger.info(f"Excel sheets found: {sheet_names}")

        # Try to load from known relationship sheet names
        relation_sheets = {
            "IV→L2": ["Relationships (IV impacting L2)", "IV_L2_Relationships", "Intervention to L2"],
            "L2→L1": ["Relationships (L2 impacting L1)", "L2_L1_Relationships", "L2 to L1"],
            "L1→BO": ["Relationships (L1 impacting BO)", "L1_BO_Relationships", "L1 to BO"],
        }

        for level, candidates in relation_sheets.items():
            for sheet_name in candidates:
                if sheet_name in sheet_names:
                    try:
                        ws = wb[sheet_name]
                        self._parse_relationship_sheet(ws, level)
                        logger.info(f"Loaded {level} relationships from sheet: {sheet_name}")
                        break
                    except Exception as e:
                        logger.warning(f"Failed to parse sheet {sheet_name}: {e}")

        # If no relationships found from named sheets, try to infer from any sheet
        if not self._relationships:
            logger.info("No named relationship sheets found; trying to infer from all sheets")
            self._load_from_db()

    def _parse_relationship_sheet(self, ws, level: str):
        """Parse rows from a relationship sheet. Looks for: parent_name, child_name, impact_factor."""
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return

        # Find header row
        header_row_idx = None
        for i, row in enumerate(rows[:10]):
            row_str = " ".join(str(c).lower() for c in row if c)
            if any(kw in row_str for kw in ["impact factor", "metric", "intervention", "name"]):
                header_row_idx = i
                break

        if header_row_idx is None:
            header_row_idx = 0

        headers = [str(c).lower().strip() if c else "" for c in rows[header_row_idx]]

        # Map column indices
        parent_col = next((i for i, h in enumerate(headers) if "parent" in h or "intervention" in h or "from" in h), 0)
        child_col = next((i for i, h in enumerate(headers) if "child" in h or "metric" in h or "to" in h), 1)
        factor_col = next((i for i, h in enumerate(headers) if "impact" in h or "factor" in h or "weight" in h), 2)

        for row in rows[header_row_idx + 1:]:
            if not row or not any(row):
                continue
            try:
                parent = str(row[parent_col]).strip() if row[parent_col] else None
                child = str(row[child_col]).strip() if row[child_col] else None
                factor = float(row[factor_col]) if row[factor_col] is not None else None

                if parent and child and factor is not None and parent != "None" and child != "None":
                    self._relationships.append(KpiRelationship(
                        parent_name=parent,
                        child_name=child,
                        impact_factor=factor,
                        level=level,
                    ))
            except (ValueError, IndexError, TypeError):
                continue

    def _scoped_ids(self, model):
        """Return the set of row ids for `model` in the current vertical/LOB scope."""
        q = self.db.query(model.id)
        if self.vertical:
            q = q.filter(model.vertical_horizontal == self.vertical)
        if self.lob:
            q = q.filter(model.lob == self.lob)
        return {row[0] for row in q.all()}

    def _scoped_name_map(self, model):
        q = self.db.query(model)
        if self.vertical:
            q = q.filter(model.vertical_horizontal == self.vertical)
        if self.lob:
            q = q.filter(model.lob == self.lob)
        return {row.id: row.name for row in q.all()}

    def _load_from_db(self):
        """Load relationships from the database as fallback.

        Scoped to the current vertical/LOB. Without this, edges and id→name
        maps are built from EVERY vertical's rows, so tracing a metric whose
        name repeats across verticals (the generic "Intervention_1",
        "L1_Metric 1", "BO_1" placeholder names used throughout every
        vertical) would return relationships from the wrong vertical mixed
        in via substring name matching in trace_kpi().
        """
        if self.db is None:
            logger.info("No DB session; using empty relationship graph")
            return

        try:
            from ...models import intervention_l2_link, l2_l1_link, l1_bo_link
            from ...models import Intervention, L2Metric, L1Metric, BusinessOutcome
            from sqlalchemy import select

            iv_map = self._scoped_name_map(Intervention)
            l2_map = self._scoped_name_map(L2Metric)
            l1_map = self._scoped_name_map(L1Metric)
            bo_map = self._scoped_name_map(BusinessOutcome)

            # IV → L2 (keep only edges where BOTH ends belong to this scope)
            edges = self.db.execute(select(
                intervention_l2_link.c.intervention_id,
                intervention_l2_link.c.l2_metric_id,
                intervention_l2_link.c.impact_factor,
            )).fetchall()
            for e in edges:
                if e[0] not in iv_map or e[1] not in l2_map:
                    continue
                self._relationships.append(KpiRelationship(
                    parent_name=iv_map.get(e[0], f"IV-{e[0]}"),
                    child_name=l2_map.get(e[1], f"L2-{e[1]}"),
                    impact_factor=e[2],
                    level="IV→L2",
                ))

            # L2 → L1
            edges = self.db.execute(select(
                l2_l1_link.c.l2_metric_id,
                l2_l1_link.c.l1_metric_id,
                l2_l1_link.c.impact_factor,
            )).fetchall()
            for e in edges:
                if e[0] not in l2_map or e[1] not in l1_map:
                    continue
                self._relationships.append(KpiRelationship(
                    parent_name=l2_map.get(e[0], f"L2-{e[0]}"),
                    child_name=l1_map.get(e[1], f"L1-{e[1]}"),
                    impact_factor=e[2],
                    level="L2→L1",
                ))

            # L1 → BO
            edges = self.db.execute(select(
                l1_bo_link.c.l1_metric_id,
                l1_bo_link.c.business_outcome_id,
                l1_bo_link.c.impact_factor,
            )).fetchall()
            for e in edges:
                if e[0] not in l1_map or e[1] not in bo_map:
                    continue
                self._relationships.append(KpiRelationship(
                    parent_name=l1_map.get(e[0], f"L1-{e[0]}"),
                    child_name=bo_map.get(e[1], f"BO-{e[1]}"),
                    impact_factor=e[2],
                    level="L1→BO",
                ))

            logger.info(f"Loaded {len(self._relationships)} relationships from database")
        except Exception as e:
            logger.error(f"DB relationship load failed: {e}")

    def trace_kpi(self, metric_name: str) -> KpiTracePath:
        """Trace full upstream and downstream paths for a KPI."""
        self._ensure_loaded()

        name_lower = metric_name.lower()

        # Find all relationships involving this metric
        upstream = [
            r for r in self._relationships
            if name_lower in r.child_name.lower()
        ]
        downstream = [
            r for r in self._relationships
            if name_lower in r.parent_name.lower()
        ]

        # Determine metric level
        levels_seen = set()
        for r in upstream:
            levels_seen.add(r.level)
        for r in downstream:
            levels_seen.add(r.level)

        metric_level = "unknown"
        if any("L1→BO" == r.level for r in upstream) or not downstream:
            metric_level = "business_outcome"
        elif any("L2→L1" == r.level for r in upstream):
            metric_level = "l1_metric"
        elif any("IV→L2" == r.level for r in upstream):
            metric_level = "l2_metric"
        elif downstream and all("IV→L2" == r.level for r in downstream):
            metric_level = "intervention"

        # Build human-readable chain
        chain_parts = []
        if upstream:
            drivers = [f"{r.parent_name} (IF={r.impact_factor:+.2f})" for r in upstream[:3]]
            chain_parts.append(f"Driven by: {', '.join(drivers)}")
        if downstream:
            impacts = [f"{r.child_name} (IF={r.impact_factor:+.2f})" for r in downstream[:3]]
            chain_parts.append(f"Impacts: {', '.join(impacts)}")

        full_chain = " → ".join(chain_parts) if chain_parts else f"No traced relationships found for '{metric_name}'"

        return KpiTracePath(
            metric_name=metric_name,
            metric_level=metric_level,
            upstream=upstream,
            downstream=downstream,
            full_chain=full_chain,
        )

    def get_all_relationships(self) -> List[KpiRelationship]:
        self._ensure_loaded()
        return self._relationships

    def find_path_to_outcome(self, intervention_name: str, outcome_name: str) -> str:
        """Trace the specific path from an intervention to a business outcome."""
        self._ensure_loaded()

        # BFS through relationship graph
        iv_lower = intervention_name.lower()
        bo_lower = outcome_name.lower()

        # Find direct IV→L2 connections
        l2_via_iv = [r for r in self._relationships if iv_lower in r.parent_name.lower() and r.level == "IV→L2"]
        if not l2_via_iv:
            return f"No direct relationship found from '{intervention_name}' to any L2 metric."

        chains = []
        for l2_rel in l2_via_iv:
            l2_name = l2_rel.child_name
            l1_rels = [r for r in self._relationships if l2_name.lower() in r.parent_name.lower() and r.level == "L2→L1"]

            for l1_rel in l1_rels:
                l1_name = l1_rel.child_name
                bo_rels = [r for r in self._relationships if l1_name.lower() in r.parent_name.lower() and r.level == "L1→BO"]

                for bo_rel in bo_rels:
                    if bo_lower in bo_rel.child_name.lower() or not bo_lower:
                        chains.append(
                            f"{intervention_name} (slider) "
                            f"→ {l2_name} (IF={l2_rel.impact_factor:+.3f}) "
                            f"→ {l1_name} (IF={l1_rel.impact_factor:+.3f}) "
                            f"→ {bo_rel.child_name} (IF={bo_rel.impact_factor:+.3f})"
                        )

        if not chains:
            return f"Could not trace complete path from '{intervention_name}' to '{outcome_name}'. Partial: {intervention_name} → {', '.join(r.child_name for r in l2_via_iv)}"

        return "\n".join(chains)


# Per (vertical, lob) cache — NOT a single global singleton.
#
# The previous implementation cached one ExcelTraceService for the entire
# process lifetime and only rebuilt it "if db is not None" (which is true on
# almost every call), so in practice it silently reused whatever
# relationships were loaded for the FIRST vertical/LOB ever queried after
# server start, for every subsequent request regardless of which vertical
# the user had actually selected. That is a second, independent cause of
# "wrong vertical" answers, on top of the missing DB filters above.
_trace_service_cache: Dict[tuple, ExcelTraceService] = {}


def get_trace_service(db=None, vertical: Optional[str] = None, lob: Optional[str] = None) -> ExcelTraceService:
    key = (vertical, lob)
    svc = _trace_service_cache.get(key)
    if svc is None:
        svc = ExcelTraceService(db=db, vertical=vertical, lob=lob)
        _trace_service_cache[key] = svc
    elif db is not None:
        # Keep the DB session fresh for this scope's cached service.
        svc.db = db
    return svc
