#!/usr/bin/env python3
"""Detached trigger for canonical route precompute jobs.

Called from the RWGPS webhook as an internal worker. It refreshes the
canonical route base, checks whether the current route_version_key is
already fully precomputed, and runs the route precompute orchestrator
only when needed.
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/opt/qbot/app")

from qbot3.routes.route_precompute_orchestrator import ensure_route_precompute
from qbot3.routes.route_base_store import ensure_route_base
import psycopg
from psycopg.rows import dict_row
import os

EXPECTED_JOB_TYPES = ("route_base", "route_surface", "route_landcover", "route_poi")


def _db_conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )


def _normalize_route_id(route_id: str | int) -> str:
    text = str(route_id).strip()
    if not text:
        raise ValueError("route_id required")
    return text


def _route_precompute_rows(conn, route_version_key: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT job_type, status, layer_status_json, idempotency_key
        FROM qbot_v2.route_precompute_jobs
        WHERE route_version_key = %s
        ORDER BY job_type
        """,
        (route_version_key,),
    ).fetchall()
    return [dict(row) for row in rows]


def _precompute_complete(rows: list[dict[str, object]]) -> bool:
    if len(rows) != len(EXPECTED_JOB_TYPES):
        return False
    present = {str(row.get("job_type") or "") for row in rows}
    if set(EXPECTED_JOB_TYPES) != present:
        return False
    return all(str(row.get("status") or "").strip() == "complete" for row in rows)


def ensure_route_precompute_trigger(*, route_id: str | int, trigger_source: str = "rwgps_webhook") -> dict[str, object]:
    route_id_text = _normalize_route_id(route_id)
    base_result = ensure_route_base(route_id_text)
    route_base = base_result["route_base"]
    route_base_id = int(route_base["route_base_id"])
    route_version_key = str(base_result["route_version_key"])
    route_artifact_id = base_result.get("route_artifact_id")

    with _db_conn() as conn:
        rows = _route_precompute_rows(conn, route_version_key)
        if _precompute_complete(rows):
            return {
                "status": "OK",
                "trigger_status": "skipped",
                "route_id": route_id_text,
                "route_base_id": route_base_id,
                "route_artifact_id": route_artifact_id,
                "route_version_key": route_version_key,
                "route_precompute_jobs_count": len(rows),
                "job_types": [row["job_type"] for row in rows],
            }

    result = ensure_route_precompute(route_id=route_id_text, trigger_source=trigger_source)
    return {
        "status": result.get("status", "OK"),
        "trigger_status": "ran",
        "route_id": route_id_text,
        "route_base_id": result.get("route_base_id", route_base_id),
        "route_artifact_id": result.get("route_artifact_id", route_artifact_id),
        "route_version_key": result.get("route_version_key", route_version_key),
        "route_precompute_jobs_count": len(result.get("job_rows") or []),
        "job_types": sorted((row.get("job_type") for row in result.get("job_rows") or [] if isinstance(row, dict))),
        "result": result,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trigger canonical route precompute jobs for a route_id.")
    parser.add_argument("route_id", help="RWGPS route_id")
    parser.add_argument("--trigger-source", dest="trigger_source", default="rwgps_webhook")
    args = parser.parse_args(argv)
    result = ensure_route_precompute_trigger(route_id=args.route_id, trigger_source=args.trigger_source)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
