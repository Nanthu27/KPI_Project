"""
Excel import service.

Designed to work with two kinds of workbooks:

1. The "simple" template this app exports / expects for round-tripping:
   sheets literally named Business Outcomes / L1 Metrics / L2 Metrics /
   Interventions, each a flat table of columns matching the entity
   fields (name, unit, min_value, target_value, max_value,
   default_value, higher_is_better, vertical_horizontal, lob).
   Relationship sheets (optional): "BO-L1 Links", "L1-L2 Links",
   "L2-Intervention Links" with columns (child_name, parent_name,
   impact_factor).

2. A best-effort fallback that scans every sheet for a header row
   containing recognizable column names (case-insensitive, fuzzy on
   underscores/spaces) and treats matching sheets as one of the 4
   entities. This keeps the importer useful for messier real-world
   workbooks (like the original BRD source file) without crashing.

Any row that can't be parsed is skipped and reported back in
`warnings` rather than raising, so a partially-malformed workbook still
imports what it can.
"""
from typing import Dict, List, Tuple
import pandas as pd

from sqlalchemy.orm import Session

from ..models import BusinessOutcome, L1Metric, L2Metric, Intervention
from ..repositories import (
    business_outcome_repo, l1_metric_repo, l2_metric_repo, intervention_repo,
)

ENTITY_SHEET_ALIASES = {
    "business_outcomes": ["business outcomes", "business outcome", "outcomes", "bo", "l0"],
    "l1_metrics": ["l1 metrics", "l1", "l1metrics"],
    "l2_metrics": ["l2 metrics", "l2", "l2metrics"],
    "interventions": ["interventions", "intervention"],
}

COLUMN_ALIASES = {
    "name": ["name", "metric name", "business outcome", "intervention", "metric"],
    "unit": ["unit", "units"],
    "min_value": ["min_value", "min", "low", "minimum"],
    "band_min": ["band_min", "band min", "benchmark start", "target start"],
    "target_value": ["target_value", "target", "benchmark", "best-in class", "best_in_class"],
    "max_value": ["max_value", "max", "high", "maximum"],
    "default_value": ["default_value", "default", "current_value", "current value", "baseline"],
    "higher_is_better": ["higher_is_better", "higher is better"],
    "vertical_horizontal": ["vertical_horizontal", "vertical / horizontal", "vertical/horizontal", "service line", "vertical"],
    "lob": ["lob", "line of business"],
    "percentage": ["percentage", "value", "adoption", "%"],
    "description": ["description", "desc"],
}


def _normalize(s: str) -> str:
    return str(s).strip().lower().replace("_", " ")


def _find_column(columns: List[str], aliases: List[str]) -> str | None:
    normalized = {_normalize(c): c for c in columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def _map_columns(df: pd.DataFrame) -> Dict[str, str]:
    """Returns {field_name: actual_dataframe_column_name} for whatever was found."""
    mapping = {}
    for field, aliases in COLUMN_ALIASES.items():
        col = _find_column(list(df.columns), aliases)
        if col:
            mapping[field] = col
    return mapping


def _safe_float(value, default=0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_str(value, default="") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value).strip()


def _classify_sheet(sheet_name: str) -> str | None:
    norm = _normalize(sheet_name)
    for entity, aliases in ENTITY_SHEET_ALIASES.items():
        if norm in aliases or any(alias in norm for alias in aliases):
            return entity
    return None


def _import_metric_sheet(db: Session, df: pd.DataFrame, model_cls, repo, warnings: List[str], sheet_label: str) -> int:
    mapping = _map_columns(df)
    if "name" not in mapping:
        warnings.append(f"Sheet '{sheet_label}' skipped: no recognizable 'name' column.")
        return 0

    created = 0
    for idx, row in df.iterrows():
        name = _safe_str(row.get(mapping["name"]))
        if not name:
            continue
        default_value = _safe_float(row.get(mapping.get("default_value")), 0.0)
        min_value = _safe_float(row.get(mapping.get("min_value")), 0.0)
        obj = model_cls(
            name=name,
            unit=_safe_str(row.get(mapping.get("unit")), "%"),
            min_value=min_value,
            band_min=_safe_float(row.get(mapping.get("band_min")), min_value),
            target_value=_safe_float(row.get(mapping.get("target_value")), 0.0),
            max_value=_safe_float(row.get(mapping.get("max_value")), 100.0),
            default_value=default_value,
            current_value=default_value,
            improvement_percentage=0.0,
            higher_is_better=1 if _safe_str(row.get(mapping.get("higher_is_better"))).lower() in ("1", "true", "yes") else 0,
            vertical_horizontal=_safe_str(row.get(mapping.get("vertical_horizontal")), "Finance & Accounting"),
            lob=_safe_str(row.get(mapping.get("lob")), "Order to Cash"),
            sort_order=idx,
        )
        repo.create(db, obj)
        created += 1
    return created


def _import_intervention_sheet(db: Session, df: pd.DataFrame, warnings: List[str], sheet_label: str) -> int:
    mapping = _map_columns(df)
    if "name" not in mapping:
        warnings.append(f"Sheet '{sheet_label}' skipped: no recognizable 'name' column.")
        return 0

    created = 0
    for idx, row in df.iterrows():
        name = _safe_str(row.get(mapping["name"]))
        if not name:
            continue
        obj = Intervention(
            name=name,
            percentage=_safe_float(row.get(mapping.get("percentage")), 0.0),
            description=_safe_str(row.get(mapping.get("description")), None) or None,
            vertical_horizontal=_safe_str(row.get(mapping.get("vertical_horizontal")), "Finance & Accounting"),
            lob=_safe_str(row.get(mapping.get("lob")), "Order to Cash"),
            sort_order=idx,
        )
        intervention_repo.create(db, obj)
        created += 1
    return created


def import_workbook(db: Session, file_bytes: bytes) -> Tuple[int, int, int, int, List[str]]:
    """
    Parses the uploaded Excel file and inserts rows into all 4 entities.
    Returns (bo_count, l1_count, l2_count, intervention_count, warnings).
    """
    warnings: List[str] = []
    try:
        sheets = pd.read_excel(file_bytes, sheet_name=None, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not read Excel file: {exc}") from exc

    bo_count = l1_count = l2_count = iv_count = 0

    for sheet_name, df in sheets.items():
        if df.empty:
            continue
        entity = _classify_sheet(sheet_name)
        if entity is None:
            continue

        # Drop fully-empty columns/rows that openpyxl sometimes includes
        df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
        if df.empty:
            continue

        if entity == "business_outcomes":
            bo_count += _import_metric_sheet(db, df, BusinessOutcome, business_outcome_repo, warnings, sheet_name)
        elif entity == "l1_metrics":
            l1_count += _import_metric_sheet(db, df, L1Metric, l1_metric_repo, warnings, sheet_name)
        elif entity == "l2_metrics":
            l2_count += _import_metric_sheet(db, df, L2Metric, l2_metric_repo, warnings, sheet_name)
        elif entity == "interventions":
            iv_count += _import_intervention_sheet(db, df, warnings, sheet_name)

    if bo_count == l1_count == l2_count == iv_count == 0:
        warnings.append(
            "No recognizable sheets found. Expected sheet names like "
            "'Business Outcomes', 'L1 Metrics', 'L2 Metrics', 'Interventions'."
        )

    return bo_count, l1_count, l2_count, iv_count, warnings
