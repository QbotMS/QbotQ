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
from typing import Mapping

sys.path.insert(0, "/opt/qbot/app")

from qbot3.routes.route_precompute_orchestrator import ensure_route_precompute
from qbot3.routes.route_precompute_orchestrator import active_precompute_job_types
from qbot3.routes.route_base_store import ensure_route_base
import psycopg
from psycopg.rows import dict_row
import os


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


def _route_import_state(conn, route_id_text: str) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT
            a.id AS route_artifact_id,
            pr.id AS route_parse_result_id
        FROM qbot_v2.route_artifacts a
        LEFT JOIN qbot_v2.route_parse_results pr
            ON pr.route_artifact_id = a.id
        WHERE a.route_id::text = %s
        ORDER BY a.updated_at DESC NULLS LAST, a.created_at DESC NULLS LAST, a.id DESC
        LIMIT 1
        """,
        (route_id_text,),
    ).fetchone()
    if not row:
        return {
            "has_artifact": False,
            "has_parse_result": False,
            "route_artifact_id": None,
            "route_parse_result_id": None,
        }
    return {
        "has_artifact": bool(row.get("route_artifact_id")),
        "has_parse_result": bool(row.get("route_parse_result_id")),
        "route_artifact_id": row.get("route_artifact_id"),
        "route_parse_result_id": row.get("route_parse_result_id"),
    }


def _route_surface_profile_state(conn, route_artifact_id: int | None) -> dict[str, object]:
    if route_artifact_id is None:
        return {
            "has_profile": False,
            "surface_profile_id": None,
        }
    row = conn.execute(
        """
        SELECT id AS surface_profile_id
        FROM qbot_v2.route_surface_profiles
        WHERE route_artifact_id = %s
        ORDER BY enriched_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        (route_artifact_id,),
    ).fetchone()
    if not row:
        return {
            "has_profile": False,
            "surface_profile_id": None,
        }
    return {
        "has_profile": True,
        "surface_profile_id": row.get("surface_profile_id"),
    }


def _route_frames_state(conn, route_artifact_id: int | None) -> dict[str, object]:
    if route_artifact_id is None:
        return {
            "has_frames": False,
            "frame_count": 0,
        }
    row = conn.execute(
        """
        SELECT count(*)::int AS frame_count
        FROM qbot_v2.route_frames
        WHERE route_artifact_id = %s
          AND frame_size_m = 80
        """,
        (route_artifact_id,),
    ).fetchone()
    frame_count = int(row.get("frame_count") or 0) if row else 0
    return {
        "has_frames": frame_count > 0,
        "frame_count": frame_count,
    }


def _route_artifact_path(conn, route_artifact_id: int | None) -> str | None:
    if route_artifact_id is None:
        return None
    row = conn.execute(
        """
        SELECT artifact_path
        FROM qbot_v2.route_artifacts
        WHERE id = %s
        LIMIT 1
        """,
        (route_artifact_id,),
    ).fetchone()
    return str(row.get("artifact_path")) if row and row.get("artifact_path") else None


def _persist_surface_profile_from_enrich_result(
    *,
    route_artifact_id: int,
    artifact_path: str,
    enrich_result: dict[str, object],
) -> dict[str, object] | None:
    import api_db

    with _db_conn() as conn:
        route_artifact_row = conn.execute(
            """
            SELECT id, route_id::text AS route_id, sha256, source_artifact_sha256, created_at, updated_at
            FROM qbot_v2.route_artifacts
            WHERE id = %s
            LIMIT 1
            """,
            (route_artifact_id,),
        ).fetchone()
    if not route_artifact_row:
        return None

    surface_profile = enrich_result.get("surface_profile") if isinstance(enrich_result, dict) else {}
    if not isinstance(surface_profile, dict):
        surface_profile = {}
    surface_summary: dict[str, object] = dict(surface_profile)
    if isinstance(enrich_result, dict):
        surface_summary.update(enrich_result)

    segments = surface_summary.get("segments")
    if not isinstance(segments, list):
        segments = surface_profile.get("segments") if isinstance(surface_profile.get("segments"), list) else []

    record = {
        "route_artifact_id": int(route_artifact_id),
        "enrichment_version": str(surface_summary.get("enrichment_version") or "surface-profile-v1"),
        "source_artifact_sha256": str(route_artifact_row.get("sha256") or route_artifact_row.get("source_artifact_sha256") or "").strip(),
        "surface_source": surface_summary.get("surface_source") or "unknown",
        "sample_every_m": surface_summary.get("sample_every_m") or surface_summary.get("sample_distance_m") or 50,
        "confidence": surface_summary.get("confidence"),
        "coverage_pct": surface_summary.get("coverage_pct"),
        "sampled_points": surface_summary.get("sampled_points"),
        "matched_points": surface_summary.get("matched_points"),
        "unmatched_points": surface_summary.get("unmatched_points"),
        "dominant_surface": surface_summary.get("dominant_surface"),
        "status": surface_summary.get("status") or "ok",
        "surface_summary_json": surface_summary,
        "surface_segments_json": segments,
        "surface_segments_path": surface_summary.get("surface_segments_path"),
    }
    if not record["source_artifact_sha256"]:
        return None
    try:
        profile_row = api_db.upsert_route_surface_profile(record)
        if isinstance(segments, list):
            seg_rows = [seg for seg in segments if isinstance(seg, dict)]
            if seg_rows:
                api_db.replace_route_surface_segments(profile_row["id"], seg_rows)
        return profile_row
    except Exception:
        return None


def _ensure_rwgps_route_artifact(route_id_text: str, *, force: bool = False) -> dict[str, object]:
    with _db_conn() as conn:
        state = _route_import_state(conn, route_id_text)
    if state["has_artifact"] and state["has_parse_result"] and not force:
        return {
            "status": "OK",
            "import_status": "skipped",
            "route_id": route_id_text,
            "route_artifact_id": state["route_artifact_id"],
            "route_parse_result_id": state["route_parse_result_id"],
        }

    from tools.rwgps.client import export_route_to_artifact

    export_result = export_route_to_artifact(route_id_text, fmt="gpx", return_mode="metadata")
    if not export_result.get("ok"):
        raise RuntimeError(
            export_result.get("reason")
            or export_result.get("error")
            or f"RWGPS export failed for route_id={route_id_text}"
        )

    with _db_conn() as conn:
        refreshed = _route_import_state(conn, route_id_text)
    return {
        "status": "OK",
        "import_status": "imported",
        "route_id": route_id_text,
        "route_artifact_id": refreshed["route_artifact_id"],
        "route_parse_result_id": refreshed["route_parse_result_id"],
        "export_result": export_result,
    }


def _ensure_rwgps_surface_profile(
    route_id_text: str,
    *,
    route_artifact_id: int | None = None,
    force: bool = False,
) -> dict[str, object]:
    artifact_path: str | None = None
    with _db_conn() as conn:
        import_state = _route_import_state(conn, route_id_text)
        effective_route_artifact_id = route_artifact_id or import_state.get("route_artifact_id")
        surface_state = _route_surface_profile_state(conn, int(effective_route_artifact_id) if effective_route_artifact_id is not None else None)

    if surface_state["has_profile"] and not force:
        return {
            "status": "OK",
            "surface_status": "skipped",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "surface_profile_id": surface_state["surface_profile_id"],
        }

    if not artifact_path:
        with _db_conn() as conn:
            artifact_path = _route_artifact_path(conn, int(effective_route_artifact_id) if effective_route_artifact_id is not None else None)
    if not artifact_path:
        return {
            "status": "ERROR",
            "surface_status": "missing_artifact_path",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "surface_profile_id": None,
            "error": f"missing route artifact path for route_id={route_id_text}",
        }

    from qbot_route_tools import _tool_qbot_route_artifact_enrich

    enrich_result = _tool_qbot_route_artifact_enrich(
        {
            "artifact_path": artifact_path,
            "enrich": ["surface"],
            "surface_source": "auto",
            "sample_every_m": 50,
            "return_mode": "summary",
        }
    )
    if not enrich_result.get("ok"):
        return {
            "status": "ERROR",
            "surface_status": "failed",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "surface_profile_id": None,
            "error": enrich_result.get("reason") or enrich_result.get("error") or "surface enrichment failed",
            "enrich_result": enrich_result,
        }

    with _db_conn() as conn:
        refreshed = _route_surface_profile_state(conn, int(effective_route_artifact_id) if effective_route_artifact_id is not None else None)
    if not refreshed["has_profile"] and effective_route_artifact_id is not None:
        with _db_conn() as conn:
            artifact_path = _route_artifact_path(conn, int(effective_route_artifact_id))
        if artifact_path:
            persisted = _persist_surface_profile_from_enrich_result(
                route_artifact_id=int(effective_route_artifact_id),
                artifact_path=artifact_path,
                enrich_result=enrich_result,
            )
            if persisted:
                with _db_conn() as conn:
                    refreshed = _route_surface_profile_state(conn, int(effective_route_artifact_id))
                try:
                    from tools.rwgps.route_frames import build as _build_route_frames

                    _build_route_frames(route_id=route_id_text, frame_size=80.0, dry_run=False, show=0)
                    frames_status = "built"
                except Exception as exc:
                    return {
                        "status": "ERROR",
                        "surface_status": "frames_failed",
                        "route_id": route_id_text,
                        "route_artifact_id": effective_route_artifact_id,
                        "surface_profile_id": refreshed["surface_profile_id"],
                        "error": f"route_frames build failed: {exc}",
                        "enrich_result": enrich_result,
                    }
    if not refreshed["has_profile"]:
        return {
            "status": "ERROR",
            "surface_status": "not_persisted",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "surface_profile_id": None,
            "error": "surface enrichment completed but no route_surface_profile was persisted",
            "enrich_result": enrich_result,
        }
    return {
        "status": "OK",
        "surface_status": "imported",
        "route_id": route_id_text,
        "route_artifact_id": effective_route_artifact_id,
        "surface_profile_id": refreshed["surface_profile_id"],
        "frames_status": "built" if refreshed["has_profile"] else "unknown",
        "enrich_result": enrich_result,
    }


def _ensure_rwgps_route_frames(
    route_id_text: str,
    *,
    route_artifact_id: int | None = None,
    force: bool = False,
) -> dict[str, object]:
    with _db_conn() as conn:
        import_state = _route_import_state(conn, route_id_text)
        effective_route_artifact_id = route_artifact_id or import_state.get("route_artifact_id")
        frames_state = _route_frames_state(conn, int(effective_route_artifact_id) if effective_route_artifact_id is not None else None)

    if frames_state["has_frames"] and not force:
        return {
            "status": "OK",
            "frames_status": "skipped",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "frame_count": frames_state["frame_count"],
        }

    if effective_route_artifact_id is None:
        return {
            "status": "ERROR",
            "frames_status": "missing_artifact_id",
            "route_id": route_id_text,
            "route_artifact_id": None,
            "frame_count": 0,
            "error": f"missing route artifact id for route_id={route_id_text}",
        }

    try:
        from tools.rwgps.route_frames import build as _build_route_frames

        rc = _build_route_frames(route_id=route_id_text, frame_size=80.0, dry_run=False, show=0)
    except Exception as exc:
        return {
            "status": "ERROR",
            "frames_status": "failed",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "frame_count": 0,
            "error": f"route_frames build failed: {exc}",
        }

    with _db_conn() as conn:
        refreshed = _route_frames_state(conn, int(effective_route_artifact_id))
    if not refreshed["has_frames"]:
        return {
            "status": "ERROR",
            "frames_status": "not_persisted",
            "route_id": route_id_text,
            "route_artifact_id": effective_route_artifact_id,
            "frame_count": 0,
            "error": "route_frames build completed but no frames were persisted",
            "build_result": rc,
        }
    return {
        "status": "OK",
        "frames_status": "built",
        "route_id": route_id_text,
        "route_artifact_id": effective_route_artifact_id,
        "frame_count": refreshed["frame_count"],
        "build_result": rc,
    }


def _precompute_complete(rows: list[dict[str, object]], env: Mapping[str, str] | None = None) -> bool:
    expected_job_types = active_precompute_job_types(env)
    if len(rows) != len(expected_job_types):
        return False
    present = {str(row.get("job_type") or "") for row in rows}
    if set(expected_job_types) != present:
        return False
    return all(str(row.get("status") or "").strip() == "complete" for row in rows)


def ensure_route_precompute_trigger(
    *,
    route_id: str | int,
    trigger_source: str = "rwgps_webhook",
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    route_id_text = _normalize_route_id(route_id)
    import_result = _ensure_rwgps_route_artifact(route_id_text)
    surface_result = _ensure_rwgps_surface_profile(
        route_id_text,
        route_artifact_id=int(import_result.get("route_artifact_id")) if import_result.get("route_artifact_id") is not None else None,
    )
    if surface_result.get("status") != "OK":
        return {
            "status": "ERROR",
            "trigger_status": "failed",
            "route_id": route_id_text,
            "route_import": import_result,
            "route_surface": surface_result,
        }
    base_result = ensure_route_base(route_id_text)
    route_base = base_result["route_base"]
    route_base_id = int(route_base["route_base_id"])
    route_version_key = str(base_result["route_version_key"])
    route_artifact_id = base_result.get("route_artifact_id")
    frames_result = _ensure_rwgps_route_frames(
        route_id_text,
        route_artifact_id=int(route_artifact_id) if route_artifact_id is not None else None,
    )
    if frames_result.get("status") != "OK":
        return {
            "status": "ERROR",
            "trigger_status": "failed",
            "route_id": route_id_text,
            "route_import": import_result,
            "route_surface": surface_result,
            "route_frames": frames_result,
        }

    with _db_conn() as conn:
        rows = _route_precompute_rows(conn, route_version_key)
        if _precompute_complete(rows, env=env):
            return {
                "status": "OK",
                "trigger_status": "skipped",
                "route_id": route_id_text,
                "route_base_id": route_base_id,
                "route_artifact_id": route_artifact_id,
                "route_version_key": route_version_key,
                "route_precompute_jobs_count": len(rows),
                "job_types": [row["job_type"] for row in rows],
                "route_import": import_result,
                "route_surface": surface_result,
                "route_frames": frames_result,
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
        "route_import": import_result,
        "route_surface": surface_result,
        "route_frames": frames_result,
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
