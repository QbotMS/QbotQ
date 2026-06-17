#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable

import psycopg
from psycopg.rows import dict_row

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from qbot3.artifacts.route_analyzer import _find_point_at_km, _parse_gpx_file_detailed
from tools.rwgps.route_profile_export import build_profile_segments

ARTIFACT_RWGPS_EXPORT_DIR = Path("/opt/qbot/artifacts/exports/rwgps")


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


def _valid_route_id(route_id: str | int) -> str:
    route_id_str = str(route_id).strip()
    if not route_id_str:
        raise ValueError("route_id must not be empty")
    return route_id_str


def _route_gpx_path(route_id: str | int) -> Path:
    return ARTIFACT_RWGPS_EXPORT_DIR / f"rwgps_{_valid_route_id(route_id)}.gpx"


def _normalize_export_result(result: Any) -> Path | None:
    if isinstance(result, (str, Path)):
        path = Path(result)
        return path if path.exists() else None
    if isinstance(result, dict):
        for key in ("artifact_path", "path", "file_path"):
            value = result.get(key)
            if value:
                path = Path(str(value))
                if path.exists():
                    return path
    return None


def _resolve_artifact_path(file_path: str) -> Path:
    path = Path(str(file_path))
    if not path.is_absolute():
        path = Path("/opt/qbot/artifacts") / path
    return path


def _lookup_route_profile_csv_artifact(route_id: str | int) -> tuple[Path, str] | None:
    query = """
        SELECT file_path, artifact_type::text AS artifact_type
        FROM qbot_v2.artifacts
        WHERE artifact_type::text = %s
          AND filename LIKE 'rwgps_' || %s || '_profile_100m.csv'
        ORDER BY created_at DESC
        LIMIT 1
    """
    route_id_str = _valid_route_id(route_id)
    try:
        with _db_conn() as conn:
            for artifact_type in ("route_analysis", "export"):
                row = conn.execute(query, (artifact_type, route_id_str)).fetchone()
                if not row or not row.get("file_path"):
                    continue
                path = _resolve_artifact_path(str(row["file_path"]))
                if path.exists():
                    return path, str(row.get("artifact_type") or artifact_type)
    except Exception:
        return None
    return None


def _load_profile_segments_csv(csv_path: Path) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row:
                continue
            segments.append(
                {
                    "km_start": round(float(row["km_start"]), 3),
                    "km_end": round(float(row["km_end"]), 3),
                    "ele_start": round(float(row["ele_start"]), 1),
                    "ele_end": round(float(row["ele_end"]), 1),
                    "delta_m": round(float(row["delta_m"]), 1),
                    "gain_m": round(float(row["gain_m"]), 1),
                    "loss_m": round(float(row["loss_m"]), 1),
                    "avg_grade_pct": round(float(row["avg_grade_pct"]), 1),
                    "max_grade_pct": round(float(row["max_grade_pct"]), 1),
                }
            )
    if not segments:
        raise ValueError(f"No segments in {csv_path}")
    return segments


def _sample_points_from_profile_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sample_points: list[dict[str, Any]] = [
        {
            "km": round(float(segments[0]["km_start"]), 3),
            "lat": None,
            "lon": None,
            "elevation_m": segments[0]["ele_start"],
            "on_track": True,
        }
    ]
    for seg in segments:
        sample_points.append(
            {
                "km": round(float(seg["km_end"]), 3),
                "lat": None,
                "lon": None,
                "elevation_m": seg["ele_end"],
                "on_track": True,
            }
        )
    return sample_points


def _profile_summary_from_segments(
    *,
    route_id: str,
    route_name: str | None,
    artifact_path: Path,
    requested_km_from: float,
    requested_km_to: float,
    sample_m: float,
    sample_points: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    source_info: dict[str, Any],
    total_route_km: float,
) -> dict[str, Any]:
    elevations = [p["elevation_m"] for p in sample_points if p.get("elevation_m") is not None]
    elev_gain = sum(float(seg["gain_m"]) for seg in segments)
    elev_loss = sum(float(seg["loss_m"]) for seg in segments)
    resolved_km_from = sample_points[0]["km"] if sample_points else round(max(0.0, requested_km_from), 3)
    resolved_km_to = sample_points[-1]["km"] if sample_points else round(min(total_route_km, requested_km_to), 3)
    total_distance_m = max((resolved_km_to - resolved_km_from) * 1000.0, 0.0)
    avg_grade_pct = round(elev_gain / total_distance_m * 100.0, 2) if total_distance_m > 0 else None
    max_grade_pct = None
    segment_max_values = [float(seg["max_grade_pct"]) for seg in segments if seg.get("max_grade_pct") is not None]
    if segment_max_values:
        max_grade_pct = round(max(segment_max_values), 2)
    return {
        "route_id": route_id,
        "route_name": route_name,
        "artifact_path": str(artifact_path),
        "gpx_source": source_info.get("source"),
        "requested_km_from": round(requested_km_from, 3),
        "requested_km_to": round(requested_km_to, 3),
        "resolved_km_from": resolved_km_from,
        "resolved_km_to": resolved_km_to,
        "sample_m": sample_m,
        "sample_step_km": round(sample_m / 1000.0, 3),
        "sample_point_count": len(sample_points),
        "segment_count": len(segments),
        "total_gain": round(elev_gain, 1),
        "total_loss": round(elev_loss, 1),
        "max_grade": max_grade_pct,
        "total_route_km": round(total_route_km, 3),
        "elevation_min_m": round(min(elevations), 1) if elevations else None,
        "elevation_max_m": round(max(elevations), 1) if elevations else None,
        "elevation_gain_m": round(elev_gain, 1),
        "elevation_loss_m": round(elev_loss, 1),
        "avg_grade_pct": avg_grade_pct,
        "max_grade_pct": max_grade_pct,
        "start_point": sample_points[0] if sample_points else None,
        "end_point": sample_points[-1] if sample_points else None,
        "first_segments": segments[:5],
        "source_info": source_info,
    }


def _ensure_gpx_file(
    route_id: str | int,
    export_fn: Callable[[str | int], Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    route_id_str = _valid_route_id(route_id)
    local_path = _route_gpx_path(route_id_str)
    if local_path.exists() and local_path.is_file():
        return local_path, {
            "source": "local",
            "artifact_path": str(local_path),
            "download_ready": True,
        }

    exporter = export_fn
    if exporter is None:
        from tools.rwgps.client import export_route_to_artifact

        exporter = lambda rid: export_route_to_artifact(rid, fmt="gpx", return_mode="metadata")

    export_result = exporter(route_id_str)
    exported_path = _normalize_export_result(export_result)
    if exported_path is None:
        raise FileNotFoundError(f"Could not resolve GPX for route_id={route_id_str}")
    return exported_path, {
        "source": "exported",
        "artifact_path": str(exported_path),
        "export_result": export_result,
        "download_ready": exported_path.exists(),
    }


def _sample_positions(start_km: float, end_km: float, sample_m: float) -> list[float]:
    if end_km < start_km:
        raise ValueError("km_to must be >= km_from")
    if sample_m <= 0:
        raise ValueError("sample_m must be > 0")

    step_km = float(sample_m) / 1000.0
    positions = [round(start_km, 6)]
    current = start_km
    while current + step_km < end_km - 1e-9:
        current += step_km
        positions.append(round(current, 6))
    if not math.isclose(positions[-1], end_km, abs_tol=1e-9):
        positions.append(round(end_km, 6))
    return positions


def _point_at_km(points: list[dict[str, Any]], km_value: float) -> dict[str, Any]:
    pt = _find_point_at_km(points, float(km_value))
    return {
        "km": round(float(pt.get("cum_km", km_value)), 3),
        "lat": round(float(pt["lat"]), 6),
        "lon": round(float(pt["lon"]), 6),
        "elevation_m": pt.get("ele"),
        "on_track": pt.get("on_track", False),
    }


def _segment_track_points(points: list[dict[str, Any]], start_km: float, end_km: float) -> list[dict[str, Any]]:
    segment_points = [point for point in points if start_km < float(point["cum_km"]) < end_km]
    start_point = _find_point_at_km(points, start_km)
    end_point = _find_point_at_km(points, end_km)
    return [dict(start_point), *segment_points, dict(end_point)]


def _segment_grade_profile(segment_points: list[dict[str, Any]]) -> dict[str, float | None]:
    grades: list[float] = []
    for index in range(1, len(segment_points)):
        prev = segment_points[index - 1]
        curr = segment_points[index]
        prev_ele = prev.get("ele")
        curr_ele = curr.get("ele")
        if prev_ele is None or curr_ele is None:
            continue
        distance_m = (float(curr["cum_km"]) - float(prev["cum_km"])) * 1000.0
        if distance_m <= 0:
            continue
        grades.append((float(curr_ele) - float(prev_ele)) / distance_m * 100.0)

    if not grades:
        return {"avg_grade_pct": None, "max_grade_pct": None}

    smoothed_grades: list[float] = []
    for index in range(len(grades)):
        window = grades[max(0, index - 1): min(len(grades), index + 2)]
        smoothed_grades.append(sum(window) / len(window))

    avg_grade = (sum(float(grades[index]) for index in range(len(grades))) / len(grades)) if grades else None
    return {
        "avg_grade_pct": round(avg_grade, 2) if avg_grade is not None else None,
        "max_grade_pct": round(max(smoothed_grades), 2) if smoothed_grades else None,
    }


def sample_profile(points: list[dict[str, Any]], start_km: float, end_km: float) -> dict[str, Any]:
    segment_points = _segment_track_points(points, start_km, end_km)
    if len(segment_points) < 2:
        return {
            "km_start": round(start_km, 3),
            "km_end": round(end_km, 3),
            "distance_m": 0.0,
            "elevation_gain_m": None,
            "avg_grade_pct": None,
            "max_grade_pct": None,
        }

    start_ele = segment_points[0].get("ele")
    end_ele = segment_points[-1].get("ele")
    distance_m = round((float(segment_points[-1]["cum_km"]) - float(segment_points[0]["cum_km"])) * 1000.0, 3)
    elevation_gain_m = None
    if start_ele is not None and end_ele is not None:
        elevation_gain_m = round(float(end_ele) - float(start_ele), 1)

    grade_profile = _segment_grade_profile(segment_points)
    avg_grade_pct = None
    if elevation_gain_m is not None and distance_m > 0:
        avg_grade_pct = round(elevation_gain_m / distance_m * 100.0, 2)

    return {
        "km_start": round(start_km, 3),
        "km_end": round(end_km, 3),
        "distance_m": distance_m,
        "elevation_gain_m": elevation_gain_m,
        "avg_grade_pct": avg_grade_pct if avg_grade_pct is not None else grade_profile["avg_grade_pct"],
        "max_grade_pct": grade_profile["max_grade_pct"],
    }


def _build_segments(sample_points: list[dict[str, Any]], points: list[dict[str, Any]], sample_m: float) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for index in range(len(sample_points) - 1):
        start = sample_points[index]
        end = sample_points[index + 1]
        profile = sample_profile(points, float(start["km"]), float(end["km"]))
        segments.append(
            {
                "km_start": profile["km_start"],
                "km_end": profile["km_end"],
                "distance_m": profile["distance_m"],
                "elevation_gain_m": profile["elevation_gain_m"],
                "avg_grade_pct": profile["avg_grade_pct"],
                "max_grade_pct": profile["max_grade_pct"],
            }
        )
    return segments


def _profile_summary(
    *,
    route_id: str,
    route_name: str | None,
    gpx_path: Path,
    requested_km_from: float,
    requested_km_to: float,
    sample_m: float,
    sample_points: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    source_info: dict[str, Any],
    total_route_km: float,
) -> dict[str, Any]:
    elevations = [p["elevation_m"] for p in sample_points if p.get("elevation_m") is not None]
    elev_gain = 0.0
    elev_loss = 0.0
    for index in range(1, len(sample_points)):
        prev_ele = sample_points[index - 1].get("elevation_m")
        curr_ele = sample_points[index].get("elevation_m")
        if prev_ele is None or curr_ele is None:
            continue
        delta = float(curr_ele) - float(prev_ele)
        if delta > 0:
            elev_gain += delta
        elif delta < 0:
            elev_loss += abs(delta)

    resolved_km_from = sample_points[0]["km"] if sample_points else round(max(0.0, requested_km_from), 3)
    resolved_km_to = sample_points[-1]["km"] if sample_points else round(min(total_route_km, requested_km_to), 3)
    total_distance_m = max((resolved_km_to - resolved_km_from) * 1000.0, 0.0)
    avg_grade_pct = round(elev_gain / total_distance_m * 100.0, 2) if total_distance_m > 0 else None
    max_grade_pct = None
    segment_max_values = [float(seg["max_grade_pct"]) for seg in segments if seg.get("max_grade_pct") is not None]
    if segment_max_values:
        max_grade_pct = round(max(segment_max_values), 2)
    return {
        "route_id": route_id,
        "route_name": route_name,
        "artifact_path": str(gpx_path),
        "gpx_source": source_info.get("source"),
        "requested_km_from": round(requested_km_from, 3),
        "requested_km_to": round(requested_km_to, 3),
        "resolved_km_from": resolved_km_from,
        "resolved_km_to": resolved_km_to,
        "sample_m": sample_m,
        "sample_step_km": round(sample_m / 1000.0, 3),
        "sample_point_count": len(sample_points),
        "segment_count": len(segments),
        "total_gain": round(elev_gain, 1),
        "total_loss": round(elev_loss, 1),
        "max_grade": max_grade_pct,
        "total_route_km": round(total_route_km, 3),
        "elevation_min_m": round(min(elevations), 1) if elevations else None,
        "elevation_max_m": round(max(elevations), 1) if elevations else None,
        "elevation_gain_m": round(elev_gain, 1),
        "elevation_loss_m": round(elev_loss, 1),
        "avg_grade_pct": avg_grade_pct,
        "max_grade_pct": max_grade_pct,
        "start_point": sample_points[0] if sample_points else None,
        "end_point": sample_points[-1] if sample_points else None,
        "first_segments": segments[:5],
        "source_info": source_info,
    }


def rwgps_route_profile_sample(
    route_id: str | int,
    km_from: float,
    km_to: float,
    sample_m: float = 100,
    max_segments: int | None = None,
    export_fn: Callable[[str | int], Any] | None = None,
) -> dict[str, Any]:
    route_id_str = _valid_route_id(route_id)
    km_from_f = float(km_from)
    km_to_f = float(km_to)
    sample_m_f = float(sample_m)

    effective_from = max(0.0, km_from_f)
    cached_profile = _lookup_route_profile_csv_artifact(route_id_str)
    if cached_profile is not None:
        cached_profile_path, cached_profile_type = cached_profile
        segments = _load_profile_segments_csv(cached_profile_path)
        sample_points = _sample_points_from_profile_segments(segments)
        total_route_km = float(segments[-1]["km_end"])
        effective_to = min(total_route_km, km_to_f)
        if effective_to < effective_from:
            return {
                "ok": False,
                "status": "ERROR",
                "error": "km_to must be >= km_from",
                "route_id": route_id_str,
                "artifact_path": str(cached_profile_path),
                "source_info": {"source": cached_profile_type, "artifact_path": str(cached_profile_path)},
            }
        if sample_m_f <= 0:
            return {
                "ok": False,
                "status": "ERROR",
                "error": "sample_m must be > 0",
                "route_id": route_id_str,
                "artifact_path": str(cached_profile_path),
                "source_info": {"source": cached_profile_type, "artifact_path": str(cached_profile_path)},
            }
        source_info = {
            "source": cached_profile_type,
            "artifact_path": str(cached_profile_path),
            "download_ready": True,
        }
        gpx_path = cached_profile_path
        route_name = None
        segments = segments
    else:
        gpx_path, source_info = _ensure_gpx_file(route_id_str, export_fn=export_fn)
        points = _parse_gpx_file_detailed(gpx_path)
        if not points:
            return {
                "ok": False,
                "status": "ERROR",
                "error": f"No track points in {gpx_path}",
                "route_id": route_id_str,
                "artifact_path": str(gpx_path),
                "source_info": source_info,
            }

        total_route_km = float(points[-1]["cum_km"])
        effective_to = min(total_route_km, km_to_f)
        if effective_to < effective_from:
            return {
                "ok": False,
                "status": "ERROR",
                "error": "km_to must be >= km_from",
                "route_id": route_id_str,
                "artifact_path": str(gpx_path),
                "source_info": source_info,
            }
        if sample_m_f <= 0:
            return {
                "ok": False,
                "status": "ERROR",
                "error": "sample_m must be > 0",
                "route_id": route_id_str,
                "artifact_path": str(gpx_path),
                "source_info": source_info,
            }

        segs, total_m = build_profile_segments(gpx_path, km_from=effective_from, km_to=effective_to, sample_m=sample_m_f)
        sample_positions = _sample_positions(effective_from, effective_to, sample_m_f)
        sample_points = [_point_at_km(points, pos) for pos in sample_positions]
        segments = segs
        if max_segments is not None:
            max_segments_int = max(0, int(max_segments))
            if max_segments_int:
                segments = segments[:max_segments_int]
            else:
                segments = []

        route_name = source_info.get("export_result", {}).get("route_name") if isinstance(source_info.get("export_result"), dict) else None
        if not route_name and isinstance(source_info.get("export_result"), dict):
            route_name = source_info["export_result"].get("route_name")

        summary = _profile_summary(
            route_id=route_id_str,
            route_name=route_name,
            gpx_path=gpx_path,
            requested_km_from=km_from_f,
            requested_km_to=km_to_f,
            sample_m=sample_m_f,
            sample_points=sample_points,
            segments=segments,
            source_info=source_info,
            total_route_km=round(total_m / 1000.0, 3),
        )

        return {
            "ok": True,
            "status": "OK",
            "tool": "rwgps_route_profile_sample",
            "route_id": route_id_str,
            "artifact_path": str(gpx_path),
            "sample_m": sample_m_f,
            "max_segments": max_segments,
            "km_from": round(km_from_f, 3),
            "km_to": round(km_to_f, 3),
            "sample_points": sample_points,
            "segments": segments,
            "summary": summary,
            "source_info": source_info,
        }

    if effective_to < effective_from:
        return {
            "ok": False,
            "status": "ERROR",
            "error": "km_to must be >= km_from",
            "route_id": route_id_str,
            "artifact_path": str(gpx_path),
            "source_info": source_info,
        }
    if sample_m_f <= 0:
        return {
            "ok": False,
            "status": "ERROR",
            "error": "sample_m must be > 0",
            "route_id": route_id_str,
            "artifact_path": str(gpx_path),
            "source_info": source_info,
        }

    if max_segments is not None:
        max_segments_int = max(0, int(max_segments))
        if max_segments_int:
            segments = segments[:max_segments_int]
        else:
            segments = []

    summary = _profile_summary_from_segments(
        route_id=route_id_str,
        route_name=route_name,
        artifact_path=gpx_path,
        requested_km_from=km_from_f,
        requested_km_to=km_to_f,
        sample_m=sample_m_f,
        sample_points=sample_points,
        segments=segments,
        source_info=source_info,
        total_route_km=total_route_km,
    )

    return {
        "ok": True,
        "status": "OK",
        "tool": "rwgps_route_profile_sample",
        "route_id": route_id_str,
        "artifact_path": str(gpx_path),
        "sample_m": sample_m_f,
        "max_segments": max_segments,
        "km_from": round(km_from_f, 3),
        "km_to": round(km_to_f, 3),
        "sample_points": sample_points,
        "segments": segments,
        "summary": summary,
        "source_info": source_info,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample GPX elevation profile every N meters.")
    parser.add_argument("--route-id", required=True)
    parser.add_argument("--km-from", required=True, type=float)
    parser.add_argument("--km-to", required=True, type=float)
    parser.add_argument("--sample-m", type=float, default=100.0)
    parser.add_argument("--max-segments", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = rwgps_route_profile_sample(
        route_id=args.route_id,
        km_from=args.km_from,
        km_to=args.km_to,
        sample_m=args.sample_m,
        max_segments=args.max_segments,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
