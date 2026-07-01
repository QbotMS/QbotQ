"""Read-only helper for canonical route layers.

This module reads the canonical precompute layers for a route and exposes
explicit source metadata so higher layers can choose canonical vs legacy
fallback without re-computing anything.

Warstwa otoczenia (route_shade_layer, ESA WorldCover) czytana jest ADDITIVELY — nie wchodzi do
bramki canonical/fallback. Pole land_cover_preferred_source mowi konsumentowi: 'worldcover_shade'
gdy jest pokrycie, inaczej 'osm_landcover_legacy'. Dokumentacja: docs/PROJEKT_OTOCZENIE.md
"""

from __future__ import annotations

import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row


_CANONICAL_LAYER_ORDER = (
    "route_base",
    "route_axis_segments",
    "route_surface_layer",
    "route_landcover_layer",
    "route_poi_layer",
    "route_elevation_samples",
    "route_climb_events",
)


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


def _normalize_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _fetch_one(conn, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetch_many(conn, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _route_base_row(
    conn,
    *,
    route_id: str | None = None,
    route_base_id: int | None = None,
) -> dict[str, Any] | None:
    if route_base_id is not None:
        row = _fetch_one(
            conn,
            """
            SELECT
                route_base_id,
                route_id,
                route_artifact_id,
                route_parse_result_id,
                route_version_key,
                route_modified_at,
                route_updated_at,
                geometry_hash,
                sha256,
                distance_m,
                track_points,
                source_provider,
                source_path,
                status,
                source_meta_json,
                created_at,
                updated_at
            FROM qbot_v2.route_base
            WHERE route_base_id = %s
            LIMIT 1
            """,
            (route_base_id,),
        )
    else:
        row = _fetch_one(
            conn,
            """
            SELECT
                route_base_id,
                route_id,
                route_artifact_id,
                route_parse_result_id,
                route_version_key,
                route_modified_at,
                route_updated_at,
                geometry_hash,
                sha256,
                distance_m,
                track_points,
                source_provider,
                source_path,
                status,
                source_meta_json,
                created_at,
                updated_at
            FROM qbot_v2.route_base
            WHERE route_id = %s
            ORDER BY updated_at DESC, route_base_id DESC
            LIMIT 1
            """,
            (route_id,),
        )
    if row:
        row["source_meta_json"] = _normalize_json(row.get("source_meta_json")) or {}
    return row


def _axis_rows(conn, route_base_id: int) -> list[dict[str, Any]]:
    return _fetch_many(
        conn,
        """
        SELECT
            segment_index,
            km_from,
            km_to,
            distance_m,
            segment_geojson,
            elevation_start_m,
            elevation_end_m,
            elevation_gain_m,
            elevation_loss_m,
            avg_grade_pct,
            source_quality,
            created_at,
            updated_at
        FROM qbot_v2.route_axis_segments
        WHERE route_base_id = %s
        ORDER BY segment_index
        """,
        (route_base_id,),
    )


def _surface_rows(conn, route_base_id: int) -> list[dict[str, Any]]:
    return _fetch_many(
        conn,
        """
        SELECT
            segment_index,
            surface,
            highway,
            tracktype,
            source,
            confidence,
            coverage_status,
            fetched_at,
            surface_meta_json,
            created_at,
            updated_at
        FROM qbot_v2.route_surface_layer
        WHERE route_base_id = %s
        ORDER BY segment_index
        """,
        (route_base_id,),
    )


def _landcover_rows(conn, route_base_id: int) -> list[dict[str, Any]]:
    return _fetch_many(
        conn,
        """
        SELECT
            segment_index,
            landuse,
            osm_natural,
            forest_wood_context,
            building_context,
            water_context,
            source,
            confidence,
            coverage_status,
            fetched_at,
            landcover_meta_json,
            created_at,
            updated_at
        FROM qbot_v2.route_landcover_layer
        WHERE route_base_id = %s
        ORDER BY segment_index
        """,
        (route_base_id,),
    )


def _shade_rows(conn, route_base_id: int) -> list[dict[str, Any]]:
    return _fetch_many(
        conn,
        """
        SELECT
            segment_index,
            heading_deg,
            class_center,
            class_left_10,
            class_left_20,
            class_right_10,
            class_right_20,
            n_valid,
            source,
            tile,
            coverage_status,
            meta_json,
            created_at,
            updated_at
        FROM qbot_v2.route_shade_layer
        WHERE route_base_id = %s
        ORDER BY segment_index
        """,
        (route_base_id,),
    )


def _poi_rows(conn, route_base_id: int) -> list[dict[str, Any]]:
    return _fetch_many(
        conn,
        """
        SELECT
            route_poi_layer_id,
            route_base_id,
            route_version_key,
            poi_key,
            poi_id,
            source_place_id,
            provider,
            name,
            category,
            lat,
            lon,
            km_on_route,
            distance_from_route_m,
            opening_hours,
            opening_hours_fetched_at,
            source_updated_at,
            confidence,
            validity_hint,
            stale_after,
            status,
            poi_meta_json,
            created_at,
            updated_at
        FROM qbot_v2.route_poi_layer
        WHERE route_base_id = %s
        ORDER BY km_on_route NULLS LAST, distance_from_route_m NULLS LAST, poi_key
        """,
        (route_base_id,),
    )


def _poi_summary(poi_rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "poi_count": len(poi_rows),
        "by_category": {},
        "field_counts": {
            "km_on_route": 0,
            "distance_from_route_m": 0,
            "opening_hours": 0,
            "town_rows": 0,
        },
        "clusters": [],
    }
    if not poi_rows:
        return summary

    by_category: dict[str, dict[str, Any]] = {}
    field_counts = summary["field_counts"]
    town_rows: list[dict[str, Any]] = []
    supply_rows: list[dict[str, Any]] = []

    for row in poi_rows:
        category = str(row.get("category") or "unknown").strip() or "unknown"
        bucket = by_category.setdefault(category, {"count": 0, "km_count": 0, "distance_count": 0, "opening_hours_count": 0})
        bucket["count"] += 1
        if row.get("km_on_route") is not None:
            bucket["km_count"] += 1
            field_counts["km_on_route"] += 1
        if row.get("distance_from_route_m") is not None:
            bucket["distance_count"] += 1
            field_counts["distance_from_route_m"] += 1
        if str(row.get("opening_hours") or "").strip():
            bucket["opening_hours_count"] += 1
            field_counts["opening_hours"] += 1
        if category == "town":
            field_counts["town_rows"] += 1
            town_rows.append(row)
        elif category in {"hard_resupply", "soft_food_stop", "water"}:
            supply_rows.append(row)

    summary["by_category"] = dict(sorted(by_category.items()))

    def _km_value(row: dict[str, Any]) -> float | None:
        try:
            return float(row.get("km_on_route"))
        except (TypeError, ValueError):
            return None

    def _distance_value(row: dict[str, Any]) -> float | None:
        try:
            return float(row.get("distance_from_route_m"))
        except (TypeError, ValueError):
            return None

    def _sort_metric_value(value: Any) -> float:
        if value is None:
            return 999999.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 999999.0

    town_rows_sorted = [row for row in town_rows if _km_value(row) is not None]
    town_rows_sorted.sort(key=lambda row: (_km_value(row) or 0.0, str(row.get("name") or "")))

    clusters: dict[str, list[dict[str, Any]]] = {}
    for row in supply_rows:
        km = _km_value(row)
        locality = "brak lokalizacji"
        if km is not None and town_rows_sorted:
            nearest_town = min(town_rows_sorted, key=lambda town: abs((_km_value(town) or 0.0) - km))
            locality = str(nearest_town.get("name") or locality).strip() or locality
        clusters.setdefault(locality, []).append(row)

    cluster_rows: list[dict[str, Any]] = []
    for locality, items in sorted(
        clusters.items(),
        key=lambda item: (
            -len(item[1]),
            min((_km_value(row) if _km_value(row) is not None else 999999.0) for row in item[1]),
            item[0],
        ),
    ):
        km_vals = [value for row in items if (value := _km_value(row)) is not None]
        best_items = sorted(
            items,
            key=lambda row: (
                _sort_metric_value(_distance_value(row)),
                _sort_metric_value(_km_value(row)),
                str(row.get("name") or ""),
            ),
        )[:2]
        cluster_rows.append(
            {
                "locality": locality,
                "item_count": len(items),
                "km_min": round(min(km_vals), 3) if km_vals else None,
                "km_max": round(max(km_vals), 3) if km_vals else None,
                "other_count": max(0, len(items) - len(best_items)),
                "best_items": [
                    {
                        "name": item.get("name"),
                        "category": item.get("category"),
                        "km_on_route": item.get("km_on_route"),
                        "distance_from_route_m": item.get("distance_from_route_m"),
                        "opening_hours": item.get("opening_hours"),
                        "provider": item.get("provider"),
                        "confidence": item.get("confidence"),
                        "status": item.get("status"),
                    }
                    for item in best_items
                ],
            }
        )
    summary["clusters"] = cluster_rows
    return summary


def _elevation_rows(conn, route_base_id: int) -> list[dict[str, Any]]:
    return _fetch_many(
        conn,
        """
        SELECT
            sample_index,
            distance_m,
            lat,
            lon,
            elevation_m,
            source,
            smoothing_version,
            elevation_meta_json,
            created_at,
            updated_at
        FROM qbot_v2.route_elevation_samples
        WHERE route_base_id = %s
        ORDER BY sample_index
        """,
        (route_base_id,),
    )


def _climb_rows(conn, route_base_id: int) -> list[dict[str, Any]]:
    return _fetch_many(
        conn,
        """
        SELECT
            event_index,
            start_m,
            end_m,
            length_m,
            elevation_gain_m,
            avg_gradient_pct,
            max_gradient_pct,
            severity,
            segments_json,
            source,
            detection_version,
            climb_meta_json,
            created_at,
            updated_at
        FROM qbot_v2.route_climb_events
        WHERE route_base_id = %s
        ORDER BY event_index
        """,
        (route_base_id,),
    )


def _surface_profile_row(conn, route_artifact_id: int | None) -> dict[str, Any] | None:
    if route_artifact_id is None:
        return None
    row = _fetch_one(
        conn,
        """
        SELECT
            p.id,
            p.route_artifact_id,
            p.enriched_at,
            p.coverage_pct,
            p.status,
            p.enrichment_version AS route_version,
            p.surface_summary_json,
            p.surface_segments_json
        FROM qbot_v2.route_surface_profiles p
        JOIN qbot_v2.route_artifacts a ON a.id = p.route_artifact_id
        WHERE p.route_artifact_id = %s
        ORDER BY p.enriched_at DESC NULLS LAST, p.id DESC
        LIMIT 1
        """,
        (route_artifact_id,),
    )
    return row


def _surface_summary(
    surface_rows: list[dict[str, Any]],
    route_base: dict[str, Any] | None = None,
    surface_profile_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "segment_count": len(surface_rows),
        "total_distance_m": 0.0,
        "coverage_pct": 0.0,
        "route_distance_m": None,
        "missing_distance_count": 0,
        "by_surface": {},
        "by_source": {},
        "by_confidence": {},
        "problem_segments": [],
        "tagged_surface_distance_m": 0.0,
        "tagged_surface_pct": 0.0,
        "tagged_surface_segment_count": 0,
        "inferred_surface_distance_m": 0.0,
        "inferred_surface_pct": 0.0,
        "inferred_surface_segment_count": 0,
        "unknown_provenance_count": 0,
        "overpass_chunks_total": None,
        "overpass_chunks_ok": None,
        "overpass_chunks_failed": None,
        "overpass_timeout_count": None,
        "overpass_http_error_count": None,
    }
    if not surface_rows:
        if route_base and route_base.get("distance_m") is not None:
            try:
                summary["route_distance_m"] = float(route_base.get("distance_m") or 0.0)
            except (TypeError, ValueError):
                summary["route_distance_m"] = None
        return summary

    route_distance_m = None
    if route_base and route_base.get("distance_m") is not None:
        try:
            route_distance_m = float(route_base.get("distance_m") or 0.0)
        except (TypeError, ValueError):
            route_distance_m = None
    summary["route_distance_m"] = route_distance_m

    by_surface: dict[str, dict[str, Any]] = {}
    by_source: dict[str, dict[str, Any]] = {}
    by_confidence: dict[str, dict[str, Any]] = {}
    problem_segments: list[dict[str, Any]] = []
    missing_distance_count = 0
    total_distance_m = 0.0
    tagged_distance_m = 0.0
    inferred_distance_m = 0.0
    tagged_count = 0
    inferred_count = 0
    unknown_provenance_count = 0
    problem_surfaces = {"ground", "grass", "sand", "unknown", "unpaved"}
    ok_statuses = {"GOOD", "GOOD_INFERRED"}
    tagged_sources = {"osm_surface", "osm"}
    inferred_sources = {"osm_contextual", "derived-osm"}

    def _provenance_kind(source: str, classification_source: str) -> str:
        if classification_source == "tagged_surface" or source in tagged_sources:
            return "tagged"
        if classification_source.startswith("inferred_") or source in inferred_sources:
            return "inferred"
        return "unknown"

    for row in surface_rows:
        meta = row.get("surface_meta_json") if isinstance(row.get("surface_meta_json"), dict) else {}
        surface = str(row.get("surface") or meta.get("surface_refined") or meta.get("surface_raw") or "unknown").strip() or "unknown"
        source = str(row.get("source") or "unknown").strip() or "unknown"
        confidence = str(row.get("confidence") or "unknown").strip() or "unknown"
        coverage_status = str(row.get("coverage_status") or "UNKNOWN").strip() or "UNKNOWN"
        classification_source = str(meta.get("classification_source") or "").strip() or "unknown"
        try:
            distance_m = float(meta.get("distance_m"))
        except (TypeError, ValueError):
            distance_m = None

        surface_bucket = by_surface.setdefault(surface, {"segment_count": 0, "distance_m": 0.0, "pct": 0.0})
        surface_bucket["segment_count"] += 1
        if distance_m is None:
            missing_distance_count += 1
        else:
            surface_bucket["distance_m"] += distance_m
            total_distance_m += distance_m

        by_source.setdefault(source, {"segment_count": 0})["segment_count"] += 1
        by_confidence.setdefault(confidence, {"segment_count": 0})["segment_count"] += 1

        provenance_kind = _provenance_kind(source, classification_source)
        if provenance_kind == "tagged":
            tagged_count += 1
            if distance_m is not None:
                tagged_distance_m += distance_m
        elif provenance_kind == "inferred":
            inferred_count += 1
            if distance_m is not None:
                inferred_distance_m += distance_m
        else:
            unknown_provenance_count += 1

        reasons: list[str] = []
        if confidence.lower() == "low":
            reasons.append("low_confidence")
        if surface.lower() in problem_surfaces:
            reasons.append(f"surface={surface.lower()}")
        if coverage_status.upper() not in ok_statuses:
            reasons.append(f"coverage_status={coverage_status}")
        if reasons:
            problem_segments.append(
                {
                    "segment_index": row.get("segment_index"),
                    "surface": surface,
                    "source": source,
                    "confidence": confidence,
                    "coverage_status": coverage_status,
                    "distance_m": distance_m,
                    "reasons": reasons,
                    "missing_distance": distance_m is None,
                }
            )

    if total_distance_m > 0:
        for bucket in by_surface.values():
            bucket["pct"] = round(bucket["distance_m"] / total_distance_m * 100.0, 1)
        summary["tagged_surface_pct"] = round(tagged_distance_m / total_distance_m * 100.0, 1)
        summary["inferred_surface_pct"] = round(inferred_distance_m / total_distance_m * 100.0, 1)
    summary["tagged_surface_distance_m"] = round(tagged_distance_m, 1)
    summary["inferred_surface_distance_m"] = round(inferred_distance_m, 1)
    summary["tagged_surface_segment_count"] = tagged_count
    summary["inferred_surface_segment_count"] = inferred_count
    summary["unknown_provenance_count"] = unknown_provenance_count

    coverage_pct = 0.0
    if route_distance_m and route_distance_m > 0:
        coverage_pct = round(total_distance_m / route_distance_m * 100.0, 1)

    summary.update(
        {
            "total_distance_m": round(total_distance_m, 1),
            "coverage_pct": coverage_pct,
            "missing_distance_count": missing_distance_count,
            "by_surface": by_surface,
            "by_source": by_source,
            "by_confidence": by_confidence,
            "problem_segments": problem_segments,
        }
    )

    profile_overpass = {}
    if isinstance(surface_profile_summary, dict):
        profile_overpass = surface_profile_summary.get("overpass_metrics") if isinstance(surface_profile_summary.get("overpass_metrics"), dict) else {}
    if isinstance(profile_overpass, dict):
        summary["overpass_chunks_total"] = profile_overpass.get("chunks_total")
        summary["overpass_chunks_ok"] = profile_overpass.get("chunks_ok")
        summary["overpass_chunks_failed"] = profile_overpass.get("chunks_failed")
        summary["overpass_timeout_count"] = profile_overpass.get("timeout_count")
        summary["overpass_http_error_count"] = profile_overpass.get("http_error_count")
    return summary


def read_canonical_route(
    *,
    route_id: str | int | None = None,
    route_base_id: int | None = None,
    route_version_key: str | None = None,
) -> dict[str, Any]:
    """Read canonical route layers and mark whether the canonical path is complete."""
    if route_id is None and route_base_id is None:
        raise ValueError("route_id or route_base_id required")

    route_id_text = _normalize_route_id(route_id) if route_id is not None else None
    if route_base_id is not None:
        route_base_id = int(route_base_id)

    with _db_conn() as conn:
        base = _route_base_row(conn, route_id=route_id_text, route_base_id=route_base_id)
        if not base:
            return {
                "route_id": route_id_text,
                "route_base_id": route_base_id,
                "route_version_key": route_version_key,
                "read_path": "legacy_fallback",
                "fallback_reason": "route_base_missing",
                "layer_counts": {name: 0 for name in _CANONICAL_LAYER_ORDER},
                "layers": {},
            }

        if route_id_text and str(base.get("route_id") or "").strip() != route_id_text:
            return {
                "route_id": route_id_text,
                "route_base_id": int(base["route_base_id"]),
                "route_version_key": route_version_key or base.get("route_version_key"),
                "read_path": "legacy_fallback",
                "fallback_reason": "route_id_mismatch",
                "route_base": base,
                "layer_counts": {name: 0 for name in _CANONICAL_LAYER_ORDER},
                "layers": {},
            }

        if route_version_key and str(base.get("route_version_key") or "").strip() != str(route_version_key).strip():
            return {
                "route_id": route_id_text or str(base.get("route_id") or ""),
                "route_base_id": int(base["route_base_id"]),
                "route_version_key": str(base.get("route_version_key") or ""),
                "read_path": "legacy_fallback",
                "fallback_reason": "route_version_key_mismatch",
                "route_base": base,
                "layer_counts": {name: 0 for name in _CANONICAL_LAYER_ORDER},
                "layers": {},
        }

        rb_id = int(base["route_base_id"])
        surface_profile = _surface_profile_row(conn, int(base["route_artifact_id"]) if base.get("route_artifact_id") is not None else None)
        surface_profile_summary = surface_profile.get("surface_summary_json") if isinstance(surface_profile, dict) else None
        if isinstance(surface_profile_summary, str):
            try:
                surface_profile_summary = json.loads(surface_profile_summary)
            except Exception:
                surface_profile_summary = {}
        if not isinstance(surface_profile_summary, dict):
            surface_profile_summary = {}
        layers = {
            "route_base": base,
            "route_axis_segments": _axis_rows(conn, rb_id),
            "route_surface_layer": _surface_rows(conn, rb_id),
            "route_landcover_layer": _landcover_rows(conn, rb_id),
            "route_shade_layer": _shade_rows(conn, rb_id),
            "route_poi_layer": _poi_rows(conn, rb_id),
            "route_elevation_samples": _elevation_rows(conn, rb_id),
            "route_climb_events": _climb_rows(conn, rb_id),
        }
        surface_summary = _surface_summary(layers["route_surface_layer"], base, surface_profile_summary)
        poi_summary = _poi_summary(layers["route_poi_layer"])
        layer_counts = {
            name: (1 if name == "route_base" and layers[name] else len(layers[name]))
            for name in _CANONICAL_LAYER_ORDER
        }
        missing = [name for name in _CANONICAL_LAYER_ORDER if layer_counts.get(name, 0) <= 0]
        shade_rows = layers.get("route_shade_layer", [])
        shade_n = len(shade_rows)
        shade_cov = sum(1 for r in shade_rows if r.get("coverage_status") in ("ok", "partial"))
        # Otoczenie: preferuj WorldCover (route_shade_layer) gdy jest pokrycie; inaczej OSM land-cover (legacy).
        land_cover_preferred_source = "worldcover_shade" if shade_cov > 0 else "osm_landcover_legacy"
        read_path = "canonical" if not missing else "legacy_fallback"
        fallback_reason = None if not missing else f"missing_canonical_layers:{','.join(missing)}"

        return {
            "route_id": str(base.get("route_id") or route_id_text or ""),
            "route_base_id": rb_id,
            "route_version_key": str(base.get("route_version_key") or ""),
            "route_artifact_id": base.get("route_artifact_id"),
            "read_path": read_path,
            "fallback_reason": fallback_reason,
            "route_base": base,
            "layer_counts": layer_counts,
            "route_shade_layer_count": shade_n,
            "shade_coverage_pct": round(shade_cov / shade_n * 100.0, 1) if shade_n else 0.0,
            "land_cover_preferred_source": land_cover_preferred_source,
            "canonical_surface_summary": surface_summary,
            "canonical_poi_summary": poi_summary,
            "surface_profile_overpass_metrics": surface_profile_summary.get("overpass_metrics") if isinstance(surface_profile_summary, dict) else None,
            "layers": layers,
        }
