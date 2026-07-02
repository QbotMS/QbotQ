"""Orchestrator for canonical route precompute jobs.

This module coordinates the existing canonical route writers in order:
route base, surface, land-cover, and POI. It records job state in
qbot_v2.route_precompute_jobs and does not touch elevation/climb,
weather, WBGT, or route_analysis_run.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import psycopg
from psycopg.rows import dict_row

from qbot3.routes.route_base_store import ensure_route_base
from qbot3.routes.route_poi_store import ensure_route_poi
from qbot3.routes.route_surface_store import ensure_route_surface
from qbot3.routes.route_shade_store import ensure_route_shade
# Warstwa otoczenia (route_shade_layer). Dokumentacja: docs/PROJEKT_OTOCZENIE.md
from qbot3.routes.route_elevation_store import ensure_route_elevation
from qbot3.routes.route_surface_context_store import ensure_route_surface_context


JOB_SEQUENCE: tuple[tuple[str, Callable[..., dict[str, Any]], str], ...] = (
    ("route_base", ensure_route_base, "route_axis_segments_count"),
    ("route_surface", ensure_route_surface, "surface_layer_count"),
    ("route_poi", ensure_route_poi, "poi_layer_count"),
)
# route_landcover (OSM land-cover) usuniety 2026-07-02 — zastapiony przez route_shade (WorldCover).


# Faza 2C: punkt rozszerzenia na elevation/climb. DOMYSLNIE WYLACZONY.
# Wlaczany jawnie przez QBOT_ROUTE_ELEVATION_ENABLED=1; przy 0 zachowanie
# orchestratora jest bajt-identyczne (job nie jest dodawany do sekwencji).
ELEVATION_JOB: tuple[str, Callable[..., dict[str, Any]], str] = (
    "route_elevation", ensure_route_elevation, "climb_events_count",
)


# Faza 2D: warstwa oslony (ESA WorldCover), per-wezel osi. DOMYSLNIE WYLACZONA.
# Wlaczana przez QBOT_ROUTE_SHADE_ENABLED=1; przy 0 sekwencja jest bajt-identyczna.
SHADE_JOB: tuple[str, Callable[..., dict[str, Any]], str] = (
    "route_shade", ensure_route_shade, "shade_layer_count",
)


# Faza 2E: warstwa kontekstu/ryzyka nawierzchni (route_surface_context) dla odcinkow BEZ tagu.
# DOMYSLNIE WYLACZONA. Wlaczana przez QBOT_ROUTE_SURFACE_CONTEXT_ENABLED=1. Wymaga route_surface + route_shade.
SURFACE_CONTEXT_JOB: tuple[str, Callable[..., dict[str, Any]], str] = (
    "route_surface_context", ensure_route_surface_context, "context_rows",
)


def _env_get(env: Mapping[str, str] | None, key: str, default: str = "") -> str:
    if env is None:
        return os.getenv(key, default)
    return env.get(key, default)


def _route_elevation_enabled(env: Mapping[str, str] | None = None) -> bool:
    return _env_get(env, "QBOT_ROUTE_ELEVATION_ENABLED", "0") == "1"


def _route_shade_enabled(env: Mapping[str, str] | None = None) -> bool:
    return _env_get(env, "QBOT_ROUTE_SHADE_ENABLED", "0") == "1"


def _route_surface_context_enabled(env: Mapping[str, str] | None = None) -> bool:
    return _env_get(env, "QBOT_ROUTE_SURFACE_CONTEXT_ENABLED", "0") == "1"


def _effective_job_sequence(env: Mapping[str, str] | None = None) -> tuple[tuple[str, Callable[..., dict[str, Any]], str], ...]:
    sequence = JOB_SEQUENCE
    if _route_elevation_enabled(env):
        sequence = sequence + (ELEVATION_JOB,)
    if _route_shade_enabled(env):
        sequence = sequence + (SHADE_JOB,)
    if _route_surface_context_enabled(env):
        sequence = sequence + (SURFACE_CONTEXT_JOB,)
    return sequence


def active_precompute_job_types(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return the currently active canonical precompute job types."""
    return tuple(job_type for job_type, _, _ in _effective_job_sequence(env))


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


def _job_idempotency_key(*, route_id: str, route_version_key: str, job_type: str) -> str:
    return f"route_precompute:{route_id}:{route_version_key}:{job_type}"


def _route_base_row(conn, route_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT route_base_id, route_id, route_artifact_id, route_version_key, status
        FROM qbot_v2.route_base
        WHERE route_id = %s
        ORDER BY updated_at DESC, route_base_id DESC
        LIMIT 1
        """,
        (route_id,),
    ).fetchone()
    return dict(row) if row else None


def _upsert_job(
    conn,
    *,
    route_id: str,
    route_artifact_id: int | None,
    route_version_key: str,
    route_base_id: int,
    trigger_source: str,
    job_type: str,
    schema_status: str,
    started_at: datetime | None,
    finished_at: datetime | None,
    error: str | None,
    layer_status_json: dict[str, Any],
) -> dict[str, Any]:
    idem_key = _job_idempotency_key(route_id=route_id, route_version_key=route_version_key, job_type=job_type)
    row = conn.execute(
        """
        INSERT INTO qbot_v2.route_precompute_jobs (
            route_id,
            route_artifact_id,
            route_version_key,
            route_base_id,
            trigger_source,
            job_type,
            status,
            started_at,
            finished_at,
            error,
            layer_status_json,
            idempotency_key
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s
        )
        ON CONFLICT (idempotency_key) DO UPDATE SET
            route_id = EXCLUDED.route_id,
            route_artifact_id = EXCLUDED.route_artifact_id,
            route_version_key = EXCLUDED.route_version_key,
            route_base_id = EXCLUDED.route_base_id,
            trigger_source = EXCLUDED.trigger_source,
            job_type = EXCLUDED.job_type,
            status = EXCLUDED.status,
            started_at = EXCLUDED.started_at,
            finished_at = EXCLUDED.finished_at,
            error = EXCLUDED.error,
            layer_status_json = EXCLUDED.layer_status_json,
            updated_at = now()
        RETURNING job_id, status, layer_status_json
        """,
        (
            route_id,
            route_artifact_id,
            route_version_key,
            route_base_id,
            trigger_source,
            job_type,
            schema_status,
            started_at,
            finished_at,
            error,
            json.dumps(layer_status_json, ensure_ascii=False),
            idem_key,
        ),
    ).fetchone()
    return dict(row)


def _run_job(
    conn,
    *,
    route_id: str,
    route_artifact_id: int | None,
    route_version_key: str,
    route_base_id: int,
    trigger_source: str,
    job_type: str,
    writer: Callable[..., dict[str, Any]],
    writer_kwargs: dict[str, Any],
    count_key: str,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    base_payload = {
        "status": "running",
        "schema_status": "running",
        "job_type": job_type,
        "route_id": route_id,
        "route_artifact_id": route_artifact_id,
        "route_version_key": route_version_key,
        "route_base_id": route_base_id,
        "trigger_source": trigger_source,
        "started_at": started_at.isoformat(),
    }

    with conn.transaction():
        _upsert_job(
            conn,
            route_id=route_id,
            route_artifact_id=route_artifact_id,
            route_version_key=route_version_key,
            route_base_id=route_base_id,
            trigger_source=trigger_source,
            job_type=job_type,
            schema_status="running",
            started_at=started_at,
            finished_at=None,
            error=None,
            layer_status_json=base_payload,
        )

    try:
        writer_result = writer(**writer_kwargs)
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        failed_payload = {
            **base_payload,
            "status": "failed",
            "schema_status": "failed",
            "finished_at": finished_at.isoformat(),
            "error": str(exc),
        }
        with conn.transaction():
            _upsert_job(
                conn,
                route_id=route_id,
                route_artifact_id=route_artifact_id,
                route_version_key=route_version_key,
                route_base_id=route_base_id,
                trigger_source=trigger_source,
                job_type=job_type,
                schema_status="failed",
                started_at=started_at,
                finished_at=finished_at,
                error=str(exc),
                layer_status_json=failed_payload,
            )
        raise

    finished_at = datetime.now(timezone.utc)
    layer_count = int(writer_result.get(count_key) or 0)
    completed_payload = {
        **base_payload,
        "status": "completed",
        "schema_status": "complete",
        "finished_at": finished_at.isoformat(),
        "writer_result": {count_key: layer_count},
    }
    with conn.transaction():
        _upsert_job(
            conn,
            route_id=route_id,
            route_artifact_id=route_artifact_id,
            route_version_key=route_version_key,
            route_base_id=route_base_id,
            trigger_source=trigger_source,
            job_type=job_type,
            schema_status="complete",
            started_at=started_at,
            finished_at=finished_at,
            error=None,
            layer_status_json=completed_payload,
        )

    return {
        "job_type": job_type,
        "status": "completed",
        "schema_status": "complete",
        "job_result": writer_result,
        "layer_count": layer_count,
    }


def _ensure_route_precompute_poi_only(route_id_text: str, *, trigger_source: str) -> dict[str, Any]:
    """Odswieza WYLACZNIE warstwe POI istniejacej, juz przeliczonej wersji trasy.

    Scenariusz: powrot do policzonej trasy po dluzszym czasie — POI (sklepy/woda/godziny)
    moglo sie zdezaktualizowac, reszta danych (osie, nawierzchnia, wysokosci) nie. NIE
    przebudowuje route_base (nie parsuje GPX od nowa), nie rusza innych warstw, nie przycina
    wersji. Wymaga istniejacego aktywnego route_base (inaczej: pelny przelicz scope='all')."""
    poi_job = next(job for job in JOB_SEQUENCE if job[0] == "route_poi")
    job_type, writer, count_key = poi_job

    with _db_conn() as conn:
        route_base_row = _route_base_row(conn, route_id_text)
        if not route_base_row:
            raise LookupError(
                f"No route_base for route_id={route_id_text!r}; "
                "uruchom najpierw pelny przelicz (scope='all')"
            )
        route_base_id = int(route_base_row["route_base_id"])
        artifact_raw = route_base_row.get("route_artifact_id")
        route_artifact_id = int(artifact_raw) if artifact_raw is not None else None
        route_version_key = str(route_base_row["route_version_key"])

        job_results: dict[str, dict[str, Any]] = {}
        job_results[job_type] = _run_job(
            conn,
            route_id=route_id_text,
            route_artifact_id=route_artifact_id,
            route_version_key=route_version_key,
            route_base_id=route_base_id,
            trigger_source=trigger_source,
            job_type=job_type,
            writer=writer,
            writer_kwargs={"route_base_id": route_base_id},
            count_key=count_key,
        )

        job_rows = conn.execute(
            """
            SELECT job_type, status, layer_status_json, idempotency_key
            FROM qbot_v2.route_precompute_jobs
            WHERE route_version_key = %s AND job_type = %s
            ORDER BY job_type
            """,
            (route_version_key, job_type),
        ).fetchall()

    return {
        "status": "OK",
        "scope": "poi",
        "retention": None,
        "route_id": route_id_text,
        "route_base_id": route_base_id,
        "route_artifact_id": route_artifact_id,
        "route_version_key": route_version_key,
        "jobs": job_results,
        "job_rows": [dict(row) for row in job_rows],
        "job_count": len(job_rows),
        "route_base": route_base_row,
        "trigger_source": trigger_source,
    }


def ensure_route_precompute(*, route_id: str | int, trigger_source: str = "manual", scope: str = "all") -> dict[str, Any]:
    route_id_text = _normalize_route_id(route_id)
    scope_norm = (scope or "all").strip().lower()
    if scope_norm not in {"all", "poi"}:
        raise ValueError(f"unsupported scope={scope!r} (expected 'all' or 'poi')")

    if scope_norm == "poi":
        return _ensure_route_precompute_poi_only(route_id_text, trigger_source=trigger_source)

    base_result = ensure_route_base(route_id_text)
    route_base = base_result["route_base"]
    route_base_id = int(route_base["route_base_id"])
    route_artifact_id = int(base_result["route_artifact_id"])
    route_version_key = str(base_result["route_version_key"])

    with _db_conn() as conn:
        route_base_row = _route_base_row(conn, route_id_text)
        if not route_base_row:
            raise LookupError(f"No route_base found for route_id={route_id_text!r}")

        job_results: dict[str, dict[str, Any]] = {}
        for job_type, writer, count_key in _effective_job_sequence():
            writer_kwargs = {"route_id": route_id_text} if job_type == "route_base" else {"route_base_id": route_base_id}
            job_results[job_type] = _run_job(
                conn,
                route_id=route_id_text,
                route_artifact_id=route_artifact_id,
                route_version_key=route_version_key,
                route_base_id=route_base_id,
                trigger_source=trigger_source,
                job_type=job_type,
                writer=writer,
                writer_kwargs=writer_kwargs,
                count_key=count_key,
            )

        job_rows = conn.execute(
            """
            SELECT job_type, status, layer_status_json, idempotency_key
            FROM qbot_v2.route_precompute_jobs
            WHERE route_version_key = %s
            ORDER BY job_type
            """,
            (route_version_key,),
        ).fetchall()

    retention = None
    try:
        from qbot3.routes.route_versions import prune_route_versions
        retention = prune_route_versions(route_id_text, keep=3, confirm=True)
    except Exception as exc:
        retention = {"status": "ERROR", "error": repr(exc)}

    return {
        "status": "OK",
        "scope": "all",
        "retention": retention,
        "route_id": route_id_text,
        "route_base_id": route_base_id,
        "route_artifact_id": route_artifact_id,
        "route_version_key": route_version_key,
        "jobs": job_results,
        "job_rows": [dict(row) for row in job_rows],
        "job_count": len(job_rows),
        "route_base": route_base_row,
        "trigger_source": trigger_source,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run canonical route precompute jobs for a route_id.")
    parser.add_argument("--route-id", dest="route_id", required=True)
    parser.add_argument("--trigger-source", dest="trigger_source", default="manual")
    args = parser.parse_args(argv)
    result = ensure_route_precompute(route_id=args.route_id, trigger_source=args.trigger_source)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
