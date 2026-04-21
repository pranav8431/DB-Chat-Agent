from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlglot import exp, parse_one
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


def make_engine(db_uri: str) -> Engine:
    return create_engine(db_uri)


def infer_dialect(engine: Engine) -> str:
    name = engine.dialect.name.lower()
    if name.startswith("postgres"):
        return "postgres"
    if name.startswith("mysql"):
        return "mysql"
    if name.startswith("sqlite"):
        return "sqlite"
    return name


def validate_sql(sql: str, dialect: str) -> bool:
    _ = dialect
    if not sql or not sql.strip():
        return False

    normalized = sql.strip().rstrip(";")
    if ";" in normalized:
        return False
    if not is_read_only_sql(normalized):
        return False

    try:
        parsed = parse_one(normalized)
    except Exception:
        return False

    return isinstance(parsed, (exp.Select, exp.With, exp.Union, exp.Intersect, exp.Except))


def is_read_only_sql(sql: str) -> bool:
    if not sql:
        return False
    lowered = sql.strip().lower()
    return lowered.startswith(("select", "with"))


def enforce_rules(sql: str, dialect: str, default_limit: int) -> str:
    _ = (dialect, default_limit)
    return sql


def inspect_schema(engine: Engine) -> dict[str, Any]:
    inspector = inspect(engine)
    schema: dict[str, Any] = {"tables": {}}

    for table in inspector.get_table_names():
        columns = inspector.get_columns(table)
        pks = inspector.get_pk_constraint(table) or {}
        fks = inspector.get_foreign_keys(table)

        schema["tables"][table] = {
            "columns": [
                {
                    "name": c["name"],
                    "type": str(c["type"]),
                    "nullable": c.get("nullable", True),
                }
                for c in columns
            ],
            "primary_key": pks.get("constrained_columns", []),
            "foreign_keys": [
                {
                    "constrained_columns": fk.get("constrained_columns", []),
                    "referred_table": fk.get("referred_table"),
                    "referred_columns": fk.get("referred_columns", []),
                }
                for fk in fks
            ],
        }

    return schema


@lru_cache(maxsize=10)
def get_schema_cached(db_uri: str) -> dict[str, Any]:
    engine = make_engine(db_uri)
    try:
        return inspect_schema(engine)
    finally:
        engine.dispose()


def run_sql(engine: Engine, sql: str, max_rows: int) -> dict[str, Any]:
    _ = max_rows
    if not validate_sql(sql, infer_dialect(engine)):
        raise ValueError("Only single-statement read-only SQL is allowed.")
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = [dict(row._mapping) for row in result]

    return {
        "row_count": len(rows),
        "rows": rows,
    }
