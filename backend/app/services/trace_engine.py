"""
TraceEngine - deterministic formula tracer behind the Excel Intelligence
Agent (spec section 3). Builds a CalculationTrace by reading the REAL
formulas, sheet names, and row numbers out of the source workbook -
never invents a formula or cell reference (FR-3.1, FR-3.4).

Per spec section 4.1's explicit warning ("do not build separate parsers
for RAG vs. calculation tracing, or they will drift out of sync after a
re-upload"), this engine and the Knowledge Agent's RAG ingestion
(rag/excel_chunker.py) both read from the SAME row-indexed representation
built by _load_workbook_index() below.

The index is built once at import time (re-built by calling
TraceEngine.reload() after a new Excel upload, per FR-3.2) from the
three relationship sheets in the source workbook:
  - "Interventions impacting L2"   (Intervention -> L2, "Impact %" rows)
  - "Relationships (L2 impacting L1)"  (L2 -> L1, "Impact Factor" + "Impact %" rows)
  - "Relationships (L1 impacting BO)"  (L1 -> Business Outcome, same shape)

If a requested metric isn't found in the index, build_trace() returns
None and the route layer responds with "I can't trace this specific
calculation" (FR-3.4) rather than guessing.
"""
import os
import threading
from typing import Dict, List, Optional, Tuple

from openpyxl import load_workbook

from ..schemas.agent_schemas import CalculationTrace, CalculationTraceStep

EXCEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "FA_V2.1.xlsx")

_INDEX_LOCK = threading.Lock()
_INDEX_CACHE: Optional[Dict] = None


def _formula_str(cell) -> str:
    if cell.value is None:
        return ""
    return str(cell.value)


def _load_workbook_index(path: str = EXCEL_PATH) -> Dict:
    """
    Parses the 3 relationship sheets into a flat list of "edges", each
    carrying the real sheet name, row number, and formula string found in
    the workbook. This is intentionally a thin, literal read of the
    sheet's existing layout (the BRD's "Net Impact" pattern: a name column,
    an Impact Factor row, a Change % row, and an Impact % row per metric
    block) rather than a generic formula-chain solver, since the workbook
    is hand-authored and that structure may vary sheet to sheet.
    """
    wb = load_workbook(path, data_only=False)
    edges: List[Dict] = []

    # --- Interventions impacting L2 ------------------------------------
    if "Interventions impacting L2" in wb.sheetnames:
        ws = wb["Interventions impacting L2"]
        l2_col_names = {}
        for col in range(3, ws.max_column + 1):
            header = ws.cell(row=1, column=col).value
            if header:
                l2_col_names[col] = str(header).strip()

        intervention_row_starts = []
        for row in range(6, ws.max_row + 1):
            name = ws.cell(row=row, column=1).value
            if name:
                intervention_row_starts.append((row, str(name).strip()))

        for idx, (start_row, intervention_name) in enumerate(intervention_row_starts):
            impact_row = start_row + 1  # "Impact %" row directly below the boolean flag row
            for col, l2_name in l2_col_names.items():
                cell = ws.cell(row=impact_row, column=col)
                if cell.value is None:
                    continue
                edges.append({
                    "level": "intervention_to_l2",
                    "from": intervention_name,
                    "to": l2_name,
                    "sheet": "Interventions impacting L2",
                    "row": impact_row,
                    "formula": f"Impact% = {cell.value}",
                    "value": cell.value,
                })

    # --- Relationships (L2 impacting L1) -------------------------------
    if "Relationships (L2 impacting L1)" in wb.sheetnames:
        ws = wb["Relationships (L2 impacting L1)"]
        l1_col_names = {}
        for col in range(4, ws.max_column + 1):
            header = ws.cell(row=2, column=col).value
            if header:
                l1_col_names[col] = str(header).strip()

        row = 7
        while row <= ws.max_row:
            l2_name_cell = ws.cell(row=row, column=2).value
            if l2_name_cell:
                l2_name = str(l2_name_cell).strip()
                impact_factor_row = row + 1
                change_pct_row = row + 2
                impact_pct_row = row + 3
                for col, l1_name in l1_col_names.items():
                    impact_factor_cell = ws.cell(row=impact_factor_row, column=col)
                    impact_pct_cell = ws.cell(row=impact_pct_row, column=col)
                    if impact_factor_cell.value is None and impact_pct_cell.value is None:
                        continue
                    edges.append({
                        "level": "l2_to_l1",
                        "from": l2_name,
                        "to": l1_name,
                        "sheet": "Relationships (L2 impacting L1)",
                        "row": impact_pct_row,
                        "formula": _formula_str(impact_pct_cell) or "Impact %",
                        "weight": impact_factor_cell.value if isinstance(impact_factor_cell.value, (int, float)) else None,
                        "weight_formula": _formula_str(impact_factor_cell),
                        "weight_row": impact_factor_row,
                    })
                row += 4
            else:
                row += 1

    # --- Relationships (L1 impacting BO) -------------------------------
    if "Relationships (L1 impacting BO)" in wb.sheetnames:
        ws = wb["Relationships (L1 impacting BO)"]
        bo_col_names = {}
        for col in range(4, ws.max_column + 1):
            header = ws.cell(row=1, column=col).value
            if header:
                bo_col_names[col] = str(header).strip()

        row = 6
        while row <= ws.max_row:
            l1_name_cell = ws.cell(row=row, column=2).value
            if l1_name_cell:
                l1_name = str(l1_name_cell).strip()
                impact_factor_row = row + 1
                change_pct_row = row + 2
                impact_pct_row = row + 3
                for col, bo_name in bo_col_names.items():
                    impact_factor_cell = ws.cell(row=impact_factor_row, column=col)
                    impact_pct_cell = ws.cell(row=impact_pct_row, column=col)
                    if impact_factor_cell.value is None and impact_pct_cell.value is None:
                        continue
                    edges.append({
                        "level": "l1_to_bo",
                        "from": l1_name,
                        "to": bo_name,
                        "sheet": "Relationships (L1 impacting BO)",
                        "row": impact_pct_row,
                        "formula": _formula_str(impact_pct_cell) or "Impact %",
                        "weight": impact_factor_cell.value if isinstance(impact_factor_cell.value, (int, float)) else None,
                        "weight_formula": _formula_str(impact_factor_cell),
                        "weight_row": impact_factor_row,
                    })
                row += 4
            else:
                row += 1

    return {
        "edges": edges,
        "source_file": os.path.basename(path),
    }


class TraceEngine:
    def __init__(self):
        global _INDEX_CACHE
        with _INDEX_LOCK:
            if _INDEX_CACHE is None:
                try:
                    _INDEX_CACHE = _load_workbook_index()
                except FileNotFoundError:
                    _INDEX_CACHE = {"edges": [], "source_file": None}
        self.index = _INDEX_CACHE

    @classmethod
    def reload(cls, path: str = EXCEL_PATH) -> None:
        """Re-indexes from a freshly uploaded workbook. Call after every Excel upload (FR-3.2)."""
        global _INDEX_CACHE
        with _INDEX_LOCK:
            _INDEX_CACHE = _load_workbook_index(path)

    def _find_edges_to(self, metric_name: str, level: str) -> List[Dict]:
        name_lower = metric_name.strip().lower()
        return [
            e for e in self.index["edges"]
            if e["level"] == level and (name_lower in e["to"].lower() or e["to"].lower() in name_lower)
        ]

    def build_trace(self, db, metric_name: str, metric_level: str) -> Optional[CalculationTrace]:
        """
        Walks backward from the requested metric to find the real edges
        that feed it, in the order Intervention -> L2 -> L1 -> Business
        Outcome (matching the spec's example output exactly). Returns None
        if no matching edges exist in the indexed workbook (caller should
        surface "I can't trace this specific calculation" per FR-3.4).
        """
        steps: List[CalculationTraceStep] = []
        values_used: Dict[str, float] = {}
        step_num = 1

        if metric_level in ("business_outcome",):
            l1_edges = self._find_edges_to(metric_name, "l1_to_bo")
            for edge in l1_edges:
                steps.append(CalculationTraceStep(
                    step=step_num, **{"from": edge["from"]}, to=edge["to"],
                    formula=edge["formula"], sheet=edge["sheet"], row=edge["row"], weight=edge.get("weight"),
                ))
                if edge.get("weight") is not None:
                    values_used[f"weight_{edge['from']}_to_{edge['to']}"] = edge["weight"]
                step_num += 1

        elif metric_level in ("l1",):
            l2_edges = self._find_edges_to(metric_name, "l2_to_l1")
            for edge in l2_edges:
                steps.append(CalculationTraceStep(
                    step=step_num, **{"from": edge["from"]}, to=edge["to"],
                    formula=edge["formula"], sheet=edge["sheet"], row=edge["row"], weight=edge.get("weight"),
                ))
                if edge.get("weight") is not None:
                    values_used[f"weight_{edge['from']}_to_{edge['to']}"] = edge["weight"]
                step_num += 1
                # Also walk one more level back: which interventions feed this L2?
                iv_edges = self._find_edges_to(edge["from"], "intervention_to_l2")
                for iv_edge in iv_edges:
                    steps.insert(len(steps) - 1, CalculationTraceStep(
                        step=step_num, **{"from": iv_edge["from"]}, to=iv_edge["to"],
                        formula=iv_edge["formula"], sheet=iv_edge["sheet"], row=iv_edge["row"],
                    ))
                    step_num += 1

        elif metric_level in ("l2",):
            iv_edges = self._find_edges_to(metric_name, "intervention_to_l2")
            for edge in iv_edges:
                steps.append(CalculationTraceStep(
                    step=step_num, **{"from": edge["from"]}, to=edge["to"],
                    formula=edge["formula"], sheet=edge["sheet"], row=edge["row"],
                ))
                step_num += 1

        if not steps:
            return None

        # Renumber steps sequentially after the insert-based reordering above.
        for i, step in enumerate(steps, start=1):
            step.step = i

        final_value = values_used.get(list(values_used.keys())[-1]) if values_used else 0.0

        return CalculationTrace(
            formula_path=steps,
            values_used=values_used,
            final_value=final_value or 0.0,
            final_unit="",
        )
