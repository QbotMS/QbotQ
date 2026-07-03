"""Minimal writer for canonical route base and axis segments.

This module writes the stable route facts into qbot_v2.route_base and
qbot_v2.route_axis_segments using existing RWGPS/GPX source data.
It does not compute surface, land-cover, POI, weather, or analysis runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from qbot3.artifacts.route_analyzer import _parse_gpx_file_detailed
from qbot_route_tools import _fetch_active_route_version

ARTIFACTS_ROOT = Path("/opt/qbot/artifacts")
AXIS_SAMPLE_M = 50.0


@dataclass(frozen=True)
class RouteBaseSource:
    route_id: str
    route_artifact_id: int
    route_parse_result_id: int | None
    route_version_key: str
    route_modified_at: datetime | None
    route_updated_at: datetime | None
    geometry_hash: str | None
    sha256: str | None
    distance_m: float | None
    distance_km: float | None
    track_points: int | None
    source_provider: str | None
    source_path: str | None
    source_relative_path: str | None
    route_status: str
    source_meta_json: dict[str, Any]
    detailed_points: list[dict[str, Any]]
    total_distance_m: float


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


def _route_parse_result_row(conn, route_artifact_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            id,
            route_artifact_id,
            parsed_at,
            parser_version,
            source_artifact_sha256,
            track_points,
            distance_m,
            distance_km,
            elevation_gain_m,
            elevation_loss_m,
            looks_valid,
            summary_json
        FROM qbot_v2.route_parse_results
        WHERE route_artifact_id = %s
        ORDER BY parsed_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        (route_artifact_id,),
    ).fetchone()
    return dict(row) if row else None


def _normalize_route_id(route_id: str | int) -> str:
    text = str(route_id).strip()
    if not text:
        raise ValueError("route_id required")
    return text


def _parse_points(file_path: Path) -> list[dict[str, Any]]:
    points = _parse_gpx_file_detailed(file_path)
    if not points:
        raise ValueError(f"No track points in {file_path}")
    return points


def _materialize_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    materialized: list[dict[str, Any]] = []
    for point in points:
        materialized.append(
            {
                "lat": float(point["lat"]),
                "lon": float(point["lon"]),
                "ele": float(point["ele"]) if point.get("ele") is not None else None,
                "cum_m": round(float(point.get("cum_km") or 0.0) * 1000.0, 3),
            }
        )
    if not materialized:
        raise ValueError("No materialized points")
    return materialized


def _geometry_hash(points: list[dict[str, Any]]) -> str:
    payload = [
        {
            "lat": round(float(point["lat"]), 7),
            "lon": round(float(point["lon"]), 7),
            "ele": round(float(point["ele"]), 1) if point.get("ele") is not None else None,
        }
        for point in points
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _coord(point: dict[str, Any]) -> list[float]:
    coord = [round(float(point["lon"]), 7), round(float(point["lat"]), 7)]
    if point.get("ele") is not None:
        coord.append(round(float(point["ele"]), 1))
    return coord


def _interpolate_point(points: list[dict[str, Any]], target_m: float) -> dict[str, Any]:
    if target_m <= points[0]["cum_m"]:
        return dict(points[0])
    if target_m >= points[-1]["cum_m"]:
        return dict(points[-1])

    for idx in range(len(points) - 1):
        left = points[idx]
        right = points[idx + 1]
        left_m = float(left["cum_m"])
        right_m = float(right["cum_m"])
        if left_m <= target_m <= right_m:
            if right_m == left_m:
                return dict(left)
            ratio = (target_m - left_m) / (right_m - left_m)
            ele = None
            if left.get("ele") is not None and right.get("ele") is not None:
                ele = round(float(left["ele"]) + ratio * (float(right["ele"]) - float(left["ele"])), 1)
            return {
                "lat": round(float(left["lat"]) + ratio * (float(right["lat"]) - float(left["lat"])), 7),
                "lon": round(float(left["lon"]) + ratio * (float(right["lon"]) - float(left["lon"])), 7),
                "ele": ele,
                "cum_m": round(target_m, 3),
            }
    return dict(points[-1])


def _segment_track(points: list[dict[str, Any]], start_m: float, end_m: float) -> list[dict[str, Any]]:
    if end_m < start_m:
        start_m, end_m = end_m, start_m
    start = _interpolate_point(points, start_m)
    end = _interpolate_point(points, end_m)
    interior = [dict(point) for point in points if start_m < float(point["cum_m"]) < end_m]
    segment = [start, *interior, end]
    compact: list[dict[str, Any]] = []
    for point in segment:
        if compact and (
            compact[-1]["lat"] == point["lat"]
            and compact[-1]["lon"] == point["lon"]
            and compact[-1].get("ele") == point.get("ele")
            and compact[-1]["cum_m"] == point["cum_m"]
        ):
            continue
        compact.append(point)
    return compact


def _segment_profile(segment: list[dict[str, Any]]) -> tuple[float | None, float | None, float | None, float | None]:
    if len(segment) < 2:
        return None, None, None, None
    elev_values = [float(point["ele"]) for point in segment if point.get("ele") is not None]
    start_ele = float(segment[0]["ele"]) if segment[0].get("ele") is not None else None
    end_ele = float(segment[-1]["ele"]) if segment[-1].get("ele") is not None else None
    gain = 0.0
    loss = 0.0
    for idx in range(1, len(segment)):
        prev = segment[idx - 1]
        curr = segment[idx]
        if prev.get("ele") is None or curr.get("ele") is None:
            continue
        delta = float(curr["ele"]) - float(prev["ele"])
        if delta > 0:
            gain += delta
        elif delta < 0:
            loss += abs(delta)
    if not elev_values:
        return start_ele, end_ele, None, None
    return start_ele, end_ele, round(gain, 1), round(loss, 1)


def _build_axis_segments(points: list[dict[str, Any]], total_distance_m: float) -> list[dict[str, Any]]:
    # Minimal axis writer: this is a deterministic 50 m segmentation adapter.
    # A future shared builder may be moved into route_surface_engine, but this
    # writer must stay stable and limited to canonical axis persistence.
    if total_distance_m <= 0:
        return []

    segments: list[dict[str, Any]] = []
    segment_count = max(1, int((total_distance_m + AXIS_SAMPLE_M - 1.0) // AXIS_SAMPLE_M))
    for segment_index in range(segment_count):
        start_m = round(segment_index * AXIS_SAMPLE_M, 3)
        end_m = round(min(total_distance_m, (segment_index + 1) * AXIS_SAMPLE_M), 3)
        if end_m <= start_m and segment_index > 0:
            continue
        track = _segment_track(points, start_m, end_m)
        start_ele, end_ele, gain_m, loss_m = _segment_profile(track)
        avg_grade = None
        if start_ele is not None and end_ele is not None and end_m > start_m:
            avg_grade = round(((end_ele - start_ele) / max(1e-6, end_m - start_m)) * 100.0, 3)
        source_quality = "parsed"
        if not any(point.get("ele") is not None for point in track):
            source_quality = "no_elevation"
        elif any(point.get("ele") is None for point in track):
            source_quality = "partial"
        segments.append(
            {
                "segment_index": segment_index,
                "km_from": round(start_m / 1000.0, 3),
                "km_to": round(end_m / 1000.0, 3),
                "distance_m": round(end_m - start_m, 1),
                "segment_geojson": {
                    "type": "LineString",
                    "coordinates": [_coord(point) for point in track],
                },
                "elevation_start_m": start_ele,
                "elevation_end_m": end_ele,
                "elevation_gain_m": gain_m,
                "elevation_loss_m": loss_m,
                "avg_grade_pct": avg_grade,
                "source_quality": source_quality,
            }
        )
    return segments


def _source_meta_json(
    *,
    route_artifact: dict[str, Any],
    route_parse_result: dict[str, Any] | None,
    geometry_hash: str,
    axis_segment_count: int,
) -> dict[str, Any]:
    def _iso(value: Any) -> Any:
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                return str(value)
        return value

    meta = {
        "source_provider": route_artifact.get("source"),
        "source_path": route_artifact.get("artifact_path"),
        "source_relative_path": route_artifact.get("artifact_relative_path"),
        "route_artifact_filename": route_artifact.get("filename"),
        "route_artifact_status": route_artifact.get("status"),
        "route_artifact_created_at": _iso(route_artifact.get("created_at")),
        "route_artifact_updated_at": _iso(route_artifact.get("updated_at")),
        "route_parse_result_id": route_parse_result.get("id") if route_parse_result else None,
        "route_parse_parser_version": route_parse_result.get("parser_version") if route_parse_result else None,
        "route_parse_parsed_at": _iso(route_parse_result.get("parsed_at")) if route_parse_result else None,
        "track_points": route_parse_result.get("track_points") if route_parse_result else None,
        "distance_m": route_parse_result.get("distance_m") if route_parse_result else None,
        "distance_km": route_parse_result.get("distance_km") if route_parse_result else None,
        "elevation_gain_m": route_parse_result.get("elevation_gain_m") if route_parse_result else None,
        "elevation_loss_m": route_parse_result.get("elevation_loss_m") if route_parse_result else None,
        "looks_valid": route_parse_result.get("looks_valid") if route_parse_result else None,
        "geometry_hash": geometry_hash,
        "axis_sample_m": AXIS_SAMPLE_M,
        "axis_segment_count": axis_segment_count,
    }
    return {key: value for key, value in meta.items() if value is not None}


def load_route_base_source(route_id: str | int) -> RouteBaseSource:
    route_id_text = _normalize_route_id(route_id)
    active_version = _fetch_active_route_version(route_id=route_id_text)
    if not active_version:
        raise LookupError(f"No active/stable route version for route_id={route_id_text}")

    active_route_id = str(active_version.get("route_id") or "").strip()
    if active_route_id and active_route_id != route_id_text:
        raise LookupError(
            f"Active route version mismatch for route_id={route_id_text}: resolved {active_route_id}"
        )

    route_artifact_id_raw = active_version.get("route_artifact_id")
    if route_artifact_id_raw is None:
        raise LookupError(f"No active route_artifact_id for route_id={route_id_text}")
    route_artifact_id = int(route_artifact_id_raw)

    route_version_key = str(active_version.get("route_version_key") or "").strip()
    if not route_version_key:
        raise LookupError(f"No route_version_key for active route_id={route_id_text}")

    with _db_conn() as conn:
        route_parse_result = _route_parse_result_row(conn, route_artifact_id)
        if not route_parse_result:
            raise LookupError(f"No route_parse_result for route_artifact_id={route_artifact_id}")

        route_artifact = conn.execute(
            """
            SELECT
                id,
                route_id,
                source,
                artifact_path,
                artifact_relative_path,
                filename,
                sha256,
                source_artifact_sha256,
                status,
                created_at,
                updated_at,
                metadata_json
            FROM qbot_v2.route_artifacts
            WHERE id = %s
            LIMIT 1
            """,
            (route_artifact_id,),
        ).fetchone()
        if not route_artifact:
            raise LookupError(f"route_artifact_id={route_artifact_id} not found")
        route_artifact = dict(route_artifact)

        source_path = route_artifact.get("artifact_path")
        if not source_path:
            raise LookupError(f"route_artifact_id={route_artifact_id} has no artifact_path")

        file_path = Path(str(source_path))
        if not file_path.exists():
            rel = route_artifact.get("artifact_relative_path")
            if rel:
                candidate = ARTIFACTS_ROOT / str(rel)
                if candidate.exists():
                    file_path = candidate
        if not file_path.exists():
            raise FileNotFoundError(f"GPX file not found for route_artifact_id={route_artifact_id}: {source_path}")

        detailed_points = _materialize_points(_parse_points(file_path))
        total_distance_m = float(route_parse_result.get("distance_m") or (detailed_points[-1]["cum_m"]))
        if total_distance_m <= 0:
            total_distance_m = float(detailed_points[-1]["cum_m"])

        source_provider = str(route_artifact.get("source") or "").strip() or None
        geometry_hash = _geometry_hash(detailed_points)
        route_status = "active" if route_parse_result.get("looks_valid", True) else "stale"
        source_meta = {
            "route_id": route_id_text,
            "route_artifact_id": route_artifact_id,
            "route_version_key": route_version_key,
            "created_at": route_artifact.get("created_at"),
            "updated_at": route_artifact.get("updated_at"),
            "sha256": route_artifact.get("sha256"),
            "source_artifact_sha256": route_artifact.get("source_artifact_sha256") or route_artifact.get("sha256"),
            "distance_m": route_parse_result.get("distance_m"),
            "distance_km": route_parse_result.get("distance_km"),
            "track_points": route_parse_result.get("track_points"),
            "point_count": route_parse_result.get("track_points"),
            "elevation_gain_m": route_parse_result.get("elevation_gain_m"),
        }
        return RouteBaseSource(
            route_id=route_id_text,
            route_artifact_id=route_artifact_id,
            route_parse_result_id=int(route_parse_result["id"]),
            route_version_key=route_version_key,
            route_modified_at=route_artifact.get("updated_at") or route_artifact.get("created_at"),
            route_updated_at=route_parse_result.get("parsed_at") or route_artifact.get("updated_at"),
            geometry_hash=geometry_hash,
            sha256=route_artifact.get("sha256"),
            distance_m=float(route_parse_result.get("distance_m")) if route_parse_result.get("distance_m") is not None else None,
            distance_km=float(route_parse_result.get("distance_km")) if route_parse_result.get("distance_km") is not None else None,
            track_points=int(route_parse_result.get("track_points")) if route_parse_result.get("track_points") is not None else None,
            source_provider=source_provider,
            source_path=str(file_path),
            source_relative_path=str(route_artifact.get("artifact_relative_path") or "").strip() or None,
            route_status=route_status,
            source_meta_json=_source_meta_json(
                route_artifact=route_artifact,
                route_parse_result=route_parse_result,
                geometry_hash=geometry_hash,
                axis_segment_count=max(1, int((total_distance_m + AXIS_SAMPLE_M - 1.0) // AXIS_SAMPLE_M)),
            ),
            detailed_points=detailed_points,
            total_distance_m=total_distance_m,
        )


def _upsert_route_base(conn, source: RouteBaseSource) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO qbot_v2.route_base (
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
            source_meta_json
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s::jsonb
        )
        ON CONFLICT (route_id, route_version_key) DO UPDATE SET
            route_artifact_id = EXCLUDED.route_artifact_id,
            route_parse_result_id = EXCLUDED.route_parse_result_id,
            route_modified_at = EXCLUDED.route_modified_at,
            route_updated_at = EXCLUDED.route_updated_at,
            geometry_hash = EXCLUDED.geometry_hash,
            sha256 = EXCLUDED.sha256,
            distance_m = EXCLUDED.distance_m,
            track_points = EXCLUDED.track_points,
            source_provider = EXCLUDED.source_provider,
            source_path = EXCLUDED.source_path,
            status = EXCLUDED.status,
            source_meta_json = EXCLUDED.source_meta_json,
            updated_at = now()
        RETURNING *
        """,
        (
            source.route_id,
            source.route_artifact_id,
            source.route_parse_result_id,
            source.route_version_key,
            source.route_modified_at,
            source.route_updated_at,
            source.geometry_hash,
            source.sha256,
            source.distance_m,
            source.track_points,
            source.source_provider,
            source.source_path,
            source.route_status,
            json.dumps(source.source_meta_json, ensure_ascii=False),
        ),
    ).fetchone()
    # Dezaktywuj pozostale wersje tej samej trasy: dokladnie jedna wersja
    # 'active' per route_id. Klucz konfliktu upsertu to (route_id,
    # route_version_key), wiec nowa wersja tworzy NOWY wiersz - bez tego
    # stara zostawala 'active' (naliczanie dubli). Ta sama transakcja.
    if str(row.get("status")) == "active":
        conn.execute(
            "UPDATE qbot_v2.route_base SET status = 'disabled', updated_at = now() "
            "WHERE route_id = %s AND route_base_id <> %s AND status = 'active'",
            (row["route_id"], row["route_base_id"]),
        )
    return dict(row)


def _upsert_route_axis_segments(conn, route_base_id: int, route_version_key: str, segments: list[dict[str, Any]]) -> int:
    inserted = 0
    for segment in segments:
        conn.execute(
            """
            INSERT INTO qbot_v2.route_axis_segments (
                route_base_id,
                route_version_key,
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
                source_quality
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (route_base_id, segment_index) DO UPDATE SET
                route_version_key = EXCLUDED.route_version_key,
                km_from = EXCLUDED.km_from,
                km_to = EXCLUDED.km_to,
                distance_m = EXCLUDED.distance_m,
                segment_geojson = EXCLUDED.segment_geojson,
                elevation_start_m = EXCLUDED.elevation_start_m,
                elevation_end_m = EXCLUDED.elevation_end_m,
                elevation_gain_m = EXCLUDED.elevation_gain_m,
                elevation_loss_m = EXCLUDED.elevation_loss_m,
                avg_grade_pct = EXCLUDED.avg_grade_pct,
                source_quality = EXCLUDED.source_quality,
                updated_at = now()
            """,
            (
                route_base_id,
                route_version_key,
                segment["segment_index"],
                segment["km_from"],
                segment["km_to"],
                segment["distance_m"],
                json.dumps(segment["segment_geojson"], ensure_ascii=False),
                segment["elevation_start_m"],
                segment["elevation_end_m"],
                segment["elevation_gain_m"],
                segment["elevation_loss_m"],
                segment["avg_grade_pct"],
                segment["source_quality"],
            ),
        )
        inserted += 1
    return inserted


def ensure_route_base(route_id: str | int) -> dict[str, Any]:
    """Write the canonical route base and 50 m axis for a route_id."""
    source = load_route_base_source(route_id)
    segments = _build_axis_segments(source.detailed_points, source.total_distance_m)

    with _db_conn() as conn:
        with conn.transaction():
            base_row = _upsert_route_base(conn, source)
            segment_count = _upsert_route_axis_segments(conn, int(base_row["route_base_id"]), source.route_version_key, segments)

    return {
        "status": "OK",
        "route_id": source.route_id,
        "route_artifact_id": source.route_artifact_id,
        "route_parse_result_id": source.route_parse_result_id,
        "route_version_key": source.route_version_key,
        "route_base": base_row,
        "route_axis_segments_count": segment_count,
        "segment_sample_m": AXIS_SAMPLE_M,
        "route_status": source.route_status,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write canonical route base + axis segments for a route_id.")
    parser.add_argument("route_id", help="RWGPS route_id")
    parser.add_argument("--repeat", type=int, default=1, help="Run the writer N times for idempotency checks")
    args = parser.parse_args(argv)

    result: dict[str, Any] | None = None
    for run_idx in range(max(1, int(args.repeat))):
        result = ensure_route_base(args.route_id)
        print(json.dumps({
            "run": run_idx + 1,
            "route_id": result["route_id"],
            "route_artifact_id": result["route_artifact_id"],
            "route_parse_result_id": result["route_parse_result_id"],
            "route_version_key": result["route_version_key"],
            "route_base_id": result["route_base"]["route_base_id"],
            "route_axis_segments_count": result["route_axis_segments_count"],
        }, ensure_ascii=False, sort_keys=True))
    return 0 if result else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
