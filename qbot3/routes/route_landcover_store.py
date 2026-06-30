"""Minimal writer for canonical route land-cover layer.

This module writes qbot_v2.route_landcover_layer from the existing
RWGPS land-cover pipeline. It does not compute surface, POI, weather,
WBGT, or analysis runs.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from tools.rwgps.surface_landcover import _fetch_landuse, landcover_for_point


def _db_conn():
    conn = psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )
    conn.autocommit = True
    return conn


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


def _landcover_context(label: str | None) -> tuple[str | None, str | None, str | None, str | None, str | None, str]:
    normalized = str(label or "").strip().lower()
    if normalized == "las":
        return "forest", "wood", "forest/wood", None, None, "inferred"
    if normalized == "woda":
        return None, "water", None, None, "water", "inferred"
    if normalized == "pola":
        return "farmland", None, None, None, None, "inferred"
    if normalized == "laki/zielen":
        return "meadow", "grassland", "green/open", None, None, "inferred"
    if normalized == "zabudowa":
        return "residential", None, None, "built-up", None, "inferred"
    if normalized == "surowa":
        return "brownfield", "bare_rock", "raw/open", None, None, "inferred"
    return None, None, None, None, None, "unknown"


def _route_frame_rows(conn, route_artifact_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT frame_index, dist_start_m, dist_end_m, surface, mid_lat, mid_lon
        FROM qbot_v2.route_frames
        WHERE route_artifact_id = %s AND frame_size_m = 80
        ORDER BY frame_index
        """,
        (route_artifact_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _bbox_from_frames(frames: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    lats: list[float] = []
    lons: list[float] = []
    for frame in frames:
        mid_lat = frame.get("mid_lat")
        mid_lon = frame.get("mid_lon")
        if mid_lat is None or mid_lon is None:
            continue
        try:
            lats.append(float(mid_lat))
            lons.append(float(mid_lon))
        except (TypeError, ValueError):
            continue
    if not lats or not lons:
        return None
    pad = 0.01
    return (min(lats) - pad, min(lons) - pad, max(lats) + pad, max(lons) + pad)


def _landcover_layers_for_route(route_base: dict[str, Any], frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not frames:
        raise LookupError(f"No route_frames for route_id={route_base['route_id']}")

    bbox = _bbox_from_frames(frames)
    polygons: list[dict[str, Any]] = []
    if bbox is not None:
        try:
            polygons = _fetch_landuse(bbox)
        except Exception:
            polygons = []

    coverage_status = "active" if polygons else "unknown"
    coverage_pct = 100.0 if polygons else 0.0
    fetched_at = datetime.now(timezone.utc)

    layers: list[dict[str, Any]] = []
    for frame in frames:
        mid_lat = frame.get("mid_lat")
        mid_lon = frame.get("mid_lon")
        if mid_lat is not None and mid_lon is not None and polygons:
            try:
                label = landcover_for_point(float(mid_lat), float(mid_lon), polygons)
            except Exception:
                label = "teren otwarty"
        else:
            label = "teren otwarty"
        landuse, osm_natural, forest_wood_context, building_context, water_context, confidence = _landcover_context(label)
        segment_index = int(frame["frame_index"])
        layers.append(
            {
                "route_base_id": int(route_base["route_base_id"]),
                "route_version_key": str(route_base["route_version_key"]),
                "segment_index": segment_index,
                "landuse": landuse,
                "osm_natural": osm_natural,
                "forest_wood_context": forest_wood_context,
                "building_context": building_context,
                "water_context": water_context,
                "source": "route_frames+surface_landcover.landcover_for_point",
                "confidence": confidence,
                "coverage_status": coverage_status,
                "fetched_at": fetched_at,
                "landcover_meta_json": {
                    "route_base_id": int(route_base["route_base_id"]),
                    "route_id": str(route_base["route_id"]),
                    "route_artifact_id": int(route_base["route_artifact_id"]),
                    "route_version_key": str(route_base["route_version_key"]),
                    "segment_index": segment_index,
                    "dist_start_m": frame.get("dist_start_m"),
                    "dist_end_m": frame.get("dist_end_m"),
                    "mid_lat": mid_lat,
                    "mid_lon": mid_lon,
                    "surface": frame.get("surface"),
                    "land_cover": label,
                    "frame_size_m": 80,
                    "source_pipeline": "tools.rwgps.surface_landcover",
                    "coverage_pct": coverage_pct,
                },
            }
        )
    return layers


def _upsert_route_landcover_layer(conn, layers: list[dict[str, Any]]) -> int:
    upserted = 0
    for layer in layers:
        conn.execute(
            """
            INSERT INTO qbot_v2.route_landcover_layer (
                route_base_id,
                route_version_key,
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
                landcover_meta_json
            )
            VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s::jsonb
            )
            ON CONFLICT (route_base_id, segment_index) DO UPDATE SET
                route_version_key = EXCLUDED.route_version_key,
                landuse = EXCLUDED.landuse,
                osm_natural = EXCLUDED.osm_natural,
                forest_wood_context = EXCLUDED.forest_wood_context,
                building_context = EXCLUDED.building_context,
                water_context = EXCLUDED.water_context,
                source = EXCLUDED.source,
                confidence = EXCLUDED.confidence,
                coverage_status = EXCLUDED.coverage_status,
                fetched_at = EXCLUDED.fetched_at,
                landcover_meta_json = EXCLUDED.landcover_meta_json,
                updated_at = now()
            """,
            (
                layer["route_base_id"],
                layer["route_version_key"],
                layer["segment_index"],
                layer["landuse"],
                layer["osm_natural"],
                layer["forest_wood_context"],
                layer["building_context"],
                layer["water_context"],
                layer["source"],
                layer["confidence"],
                layer["coverage_status"],
                layer["fetched_at"],
                json.dumps(layer["landcover_meta_json"], ensure_ascii=False),
            ),
        )
        upserted += 1
    return upserted


def ensure_route_landcover(*, route_id: str | int | None = None, route_base_id: int | None = None) -> dict[str, Any]:
    if route_id is None and route_base_id is None:
        raise ValueError("route_id or route_base_id required")

    route_id_text = _normalize_route_id(route_id) if route_id is not None else None
    conn = _db_conn()
    try:
        route_base = _route_base_row(conn, route_base_id=route_base_id, route_id=route_id_text)
        if not route_base:
            raise LookupError(f"No route_base found for route_id={route_id_text or route_base_id!r}")

        frames = _route_frame_rows(conn, int(route_base["route_artifact_id"]))
        layers = _landcover_layers_for_route(route_base, frames)
        with conn.transaction():
            upserted = _upsert_route_landcover_layer(conn, layers)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    covered = sum(1 for layer in layers if layer.get("confidence") != "unknown")
    coverage_pct = round(covered / len(layers) * 100.0, 2) if layers else 0.0
    return {
        "status": "OK",
        "route_id": route_base["route_id"],
        "route_base_id": int(route_base["route_base_id"]),
        "route_version_key": route_base["route_version_key"],
        "route_artifact_id": route_base["route_artifact_id"],
        "landcover_layer_count": upserted,
        "coverage_pct": coverage_pct,
        "coverage_status": layers[0]["coverage_status"] if layers else "unknown",
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write canonical route land-cover layer from the existing land-cover pipeline.")
    parser.add_argument("--route-id", dest="route_id")
    parser.add_argument("--route-base-id", dest="route_base_id", type=int)
    args = parser.parse_args(argv)
    result = ensure_route_landcover(route_id=args.route_id, route_base_id=args.route_base_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
