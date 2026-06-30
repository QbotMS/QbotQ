"""Minimal writer for canonical route surface layer.

This module writes qbot_v2.route_surface_layer from the existing
route_surface_profiles surface result. It does not compute surface,
land-cover, POI, weather, WBGT, or analysis runs.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from qbot_route_tools import _fetch_best_route_surface_profile


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


def _route_base_row(conn, *, route_base_id: int | None = None, route_id: str | None = None) -> dict[str, Any] | None:
    if route_base_id is not None:
        row = conn.execute(
            """
            SELECT route_base_id, route_id, route_artifact_id, route_version_key, status
            FROM qbot_v2.route_base
            WHERE route_base_id = %s
            LIMIT 1
            """,
            (route_base_id,),
        ).fetchone()
    else:
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


def _surface_profile_row(conn, profile_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            p.id,
            p.route_artifact_id,
            a.route_id::text AS route_id,
            p.enriched_at,
            p.coverage_pct,
            p.status,
            p.surface_summary_json,
            p.surface_segments_json
        FROM qbot_v2.route_surface_profiles p
        JOIN qbot_v2.route_artifacts a ON a.id = p.route_artifact_id
        WHERE p.id = %s
        LIMIT 1
        """,
        (profile_id,),
    ).fetchone()
    return dict(row) if row else None


def _surface_layers_for_route(route_base: dict[str, Any], profile: dict[str, Any], profile_row: dict[str, Any]) -> list[dict[str, Any]]:
    summary = profile.get("surface_summary_json") or {}
    if not isinstance(summary, dict):
        summary = {}
    segments = profile_row.get("surface_segments_json") or []
    if not isinstance(segments, list) or not segments:
        raise ValueError(f"surface profile {profile.get('id')} has no surface_segments_json")

    coverage_status = str(summary.get("quality_status") or profile.get("status") or "unknown").strip() or "unknown"
    route_version_key = str((profile.get("route_version") or {}).get("route_version_key") or summary.get("route_version_key") or route_base["route_version_key"]).strip()
    if not route_version_key:
        raise ValueError("surface profile missing route_version_key")

    layers: list[dict[str, Any]] = []
    for segment_index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        surface = segment.get("surface_refined") or segment.get("surface_raw") or "unknown"
        layers.append(
            {
                "route_base_id": int(route_base["route_base_id"]),
                "route_version_key": route_version_key,
                "segment_index": segment_index,
                "surface": surface,
                "highway": segment.get("highway"),
                "tracktype": segment.get("tracktype"),
                "source": segment.get("source") or "route_surface_profiles",
                "confidence": segment.get("confidence"),
                "coverage_status": coverage_status,
                "fetched_at": profile.get("enriched_at") or datetime.now(timezone.utc),
                "surface_meta_json": {
                    "surface_profile_id": profile.get("id"),
                    "route_artifact_id": profile.get("route_artifact_id"),
                    "route_id": route_base["route_id"],
                    "route_base_id": int(route_base["route_base_id"]),
                    "route_version_key": route_version_key,
                    "segment_index": segment_index,
                    "km_from": segment.get("km_from"),
                    "km_to": segment.get("km_to"),
                    "distance_m": segment.get("distance_m"),
                    "surface_raw": segment.get("surface_raw"),
                    "surface_inferred": segment.get("surface_inferred"),
                    "surface_refined": segment.get("surface_refined"),
                    "classification_source": segment.get("classification_source"),
                    "classification_sources": segment.get("classification_sources"),
                    "risk_flags": segment.get("risk_flags"),
                    "warnings": segment.get("warnings"),
                    "method": segment.get("method"),
                    "explanation": segment.get("explanation"),
                    "surface_profile_quality_status": summary.get("quality_status"),
                    "surface_profile_coverage_pct": summary.get("coverage_pct"),
                    "surface_profile_sample_every_m": summary.get("sample_every_m"),
                    "surface_profile_route_version_key": route_version_key,
                },
            }
        )
    return layers


def _upsert_route_surface_layer(conn, layers: list[dict[str, Any]]) -> int:
    upserted = 0
    for layer in layers:
        conn.execute(
            """
            INSERT INTO qbot_v2.route_surface_layer (
                route_base_id,
                route_version_key,
                segment_index,
                surface,
                highway,
                tracktype,
                source,
                confidence,
                coverage_status,
                fetched_at,
                surface_meta_json
            )
            VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s::jsonb
            )
            ON CONFLICT (route_base_id, segment_index) DO UPDATE SET
                route_version_key = EXCLUDED.route_version_key,
                surface = EXCLUDED.surface,
                highway = EXCLUDED.highway,
                tracktype = EXCLUDED.tracktype,
                source = EXCLUDED.source,
                confidence = EXCLUDED.confidence,
                coverage_status = EXCLUDED.coverage_status,
                fetched_at = EXCLUDED.fetched_at,
                surface_meta_json = EXCLUDED.surface_meta_json,
                updated_at = now()
            """,
            (
                layer["route_base_id"],
                layer["route_version_key"],
                layer["segment_index"],
                layer["surface"],
                layer["highway"],
                layer["tracktype"],
                layer["source"],
                layer["confidence"],
                layer["coverage_status"],
                layer["fetched_at"],
                json.dumps(layer["surface_meta_json"], ensure_ascii=False),
            ),
        )
        upserted += 1
    return upserted


def ensure_route_surface(*, route_id: str | int | None = None, route_base_id: int | None = None) -> dict[str, Any]:
    if route_id is None and route_base_id is None:
        raise ValueError("route_id or route_base_id required")

    route_id_text = _normalize_route_id(route_id) if route_id is not None else None
    with _db_conn() as conn:
        route_base = _route_base_row(conn, route_base_id=route_base_id, route_id=route_id_text)
        if not route_base:
            raise LookupError(f"No route_base found for route_id={route_id_text or route_base_id!r}")

        profile = _fetch_best_route_surface_profile(
            route_id=str(route_base["route_id"]),
            route_artifact_id=int(route_base["route_artifact_id"]) if route_base.get("route_artifact_id") is not None else None,
        )
        if not profile:
            raise LookupError(f"No suitable surface profile for route_id={route_base['route_id']}")
        route_version = profile.get("route_version") or {}
        route_version_key = str(route_version.get("route_version_key") or "").strip()
        if route_version_key and route_version_key != str(route_base.get("route_version_key") or "").strip():
            raise LookupError(
                f"Surface profile version mismatch for route_id={route_base['route_id']}: "
                f"profile={route_version_key} base={route_base.get('route_version_key')}"
            )

        profile_row = _surface_profile_row(conn, int(profile["id"]))
        if not profile_row:
            raise LookupError(f"Surface profile row {profile['id']} not found")

        layers = _surface_layers_for_route(route_base, profile, profile_row)
        with conn.transaction():
            upserted = _upsert_route_surface_layer(conn, layers)

    return {
        "status": "OK",
        "route_id": route_base["route_id"],
        "route_base_id": int(route_base["route_base_id"]),
        "route_version_key": route_base["route_version_key"],
        "surface_profile_id": profile["id"],
        "surface_profile_route_artifact_id": profile.get("route_artifact_id"),
        "surface_layer_count": upserted,
        "coverage_status": profile.get("quality_status") or profile.get("status") or "unknown",
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write canonical route surface layer from an existing surface profile.")
    parser.add_argument("--route-id", dest="route_id")
    parser.add_argument("--route-base-id", dest="route_base_id", type=int)
    args = parser.parse_args(argv)
    result = ensure_route_surface(route_id=args.route_id, route_base_id=args.route_base_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
