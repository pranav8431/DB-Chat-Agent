from __future__ import annotations

from typing import Any

from sqlalchemy import MetaData, Table, func, select
from sqlalchemy.engine import Engine

from .db import inspect_schema


def profile_database(engine: Engine, sample_rows: int = 3) -> dict[str, Any]:
    schema = inspect_schema(engine)
    table_profiles: dict[str, Any] = {}
    metadata = MetaData()

    with engine.connect() as conn:
        for table_name in schema["tables"].keys():
            table = Table(table_name, metadata, autoload_with=engine)
            count_query = select(func.count()).select_from(table)
            sample_query = select(table).limit(sample_rows)

            row_count = conn.execute(count_query).scalar_one()
            sample_result = conn.execute(sample_query)
            sample_data = [dict(row._mapping) for row in sample_result]

            table_profiles[table_name] = {
                "row_count": int(row_count),
                "sample_rows": sample_data,
            }

    return {
        "schema": schema,
        "table_profiles": table_profiles,
    }
