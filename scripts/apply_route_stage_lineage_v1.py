#!/usr/bin/env python3
"""Apply the idempotent Planner stage-lineage migration."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
from qbot3.routes.route_poi_store import _db_conn


def main() -> int:
    sql_path = Path(__file__).parents[1] / "sql" / "route_stage_lineage_v1.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn = _db_conn()
    try:
        conn.autocommit = True
        conn.execute(sql)
        row = conn.execute("SELECT to_regclass('qbot_v2.route_stage_lineage') AS table_name").fetchone()
        table_name = row.get("table_name") if isinstance(row, dict) else row[0]
        if not table_name:
            raise RuntimeError("route_stage_lineage migration did not create the table")
        print(table_name)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
