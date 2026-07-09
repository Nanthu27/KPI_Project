"""
Lightweight additive-column migrations.

This project has no Alembic setup — `Base.metadata.create_all()` (called on
every startup in `main.py` / `seed_data.py`) only creates tables that don't
exist yet; it silently does nothing to a table that already exists but is
missing a newly-added column. Since `kpi_simulator.db` ships pre-seeded with
real data, adding a new `Column(...)` to a model in `models.py` alone would
make every read of that column return the ORM-side Python default in memory
but crash on any raw SQL path that lists columns explicitly, and would not
actually persist a real per-row value until a full write occurred.

`run_lightweight_migrations()` is a small, dependency-free "add column if
missing" step for SQLite, safe to call on every startup: it inspects the
live schema with `PRAGMA table_info(...)`, and for any column declared in
`MIGRATIONS` that isn't present yet, issues an `ALTER TABLE ... ADD COLUMN`
with that column's default baked in as a SQL literal so existing rows get a
real, queryable value immediately (not just an ORM-side fallback).

If this project moves to Postgres/MySQL in production, replace this with a
real Alembic migration chain — this only works because SQLite's
`ALTER TABLE ADD COLUMN` is simple and the project is single-tenant/dev-scale.
"""
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# table -> [(column_name, sql_type, sql_default_literal), ...]
MIGRATIONS = {
    "interventions": [
        ("risk_level", "VARCHAR", "'Medium'"),
        ("cost_level", "VARCHAR", "'Medium'"),
        ("effort_weeks", "FLOAT", "4.0"),
        ("confidence_pct", "FLOAT", "90.0"),
    ],
}


def run_lightweight_migrations(engine: Engine) -> None:
    with engine.connect() as conn:
        for table, columns in MIGRATIONS.items():
            existing = {
                row[1]  # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
                for row in conn.execute(text(f"PRAGMA table_info({table})"))
            }
            if not existing:
                # Table doesn't exist yet — create_all() will make it with
                # the new columns already included, nothing to migrate.
                continue
            for column, sql_type, default_literal in columns:
                if column in existing:
                    continue
                logger.info("migrations: adding %s.%s (%s)", table, column, sql_type)
                conn.execute(
                    text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {sql_type} "
                        f"DEFAULT {default_literal}"
                    )
                )
        conn.commit()
