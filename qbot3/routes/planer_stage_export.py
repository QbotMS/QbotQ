"""Create deterministic day GPX routes from one Planner expedition route.

The parent route remains the source of attraction discovery. Each generated
day stores only lineage (parent route + km range), so attraction readers can
reuse one published run without another external request.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qbot3.artifacts.gpx_splitter import (
    _build_segment_points,
    _gpx_xml,
    _parse_gpx_points,
    _validate_gpx_file,
)
from qbot3.routes.route_base_store import ensure_route_base
from qbot3.routes.route_poi_store import _db_conn, _resolve_source_path, _route_base_row


EXPORT_ROOT = Path("/opt/qbot/artifacts/exports/rwgps")


def _validated_bounds(cuts: list[Any], total_km: float) -> list[tuple[float, float]]:
    if total_km <= 0:
        raise ValueError("route has no usable distance")
    values: list[float] = []
    for raw in cuts or []:
        try:
            value = round(float(raw), 3)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid cut: {raw!r}") from exc
        if value <= 0 or value >= total_km:
            raise ValueError(f"cut outside route: {value}")
        values.append(value)
    if values != sorted(values) or len(values) != len(set(values)):
        raise ValueError("cuts must be unique and strictly increasing")
    bounds = [0.0, *values, round(float(total_km), 3)]
    stages = list(zip(bounds, bounds[1:]))
    if any(end - start < 1.0 for start, end in stages):
        raise ValueError("each day must be at least 1 km")
    if len(stages) > 12:
        raise ValueError("at most 12 days are supported")
    return stages


def _split_key(parent_version_key: str, stages: list[tuple[float, float]]) -> str:
    raw = json.dumps(
        {"parent_version_key": parent_version_key, "stages": stages},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _child_route_id(parent_route_id: str, split_key: str, day_index: int) -> str:
    parent_key = hashlib.sha256(parent_route_id.encode("utf-8")).hexdigest()[:8]
    return f"planer-{parent_key}-{split_key[:10]}-d{day_index:02d}"


def _parent_name(conn, route_base: dict[str, Any]) -> str:
    row = conn.execute(
        "SELECT metadata_json->>'route_name' AS name FROM qbot_v2.route_artifacts WHERE id=%s",
        (route_base.get("route_artifact_id"),),
    ).fetchone()
    name = (row.get("name") if isinstance(row, dict) else (row[0] if row else None)) if row else None
    return str(name or f"Trasa {route_base['route_id']}").strip()


def _register_canonical_gpx(
    file_path: Path,
    *,
    child_route_id: str,
    title: str,
    lineage_meta: dict[str, Any],
) -> dict[str, Any]:
    # Existing parser writes both qbot_v2.route_artifacts and route_parse_results.
    from tools.rwgps.client import summarize_rwgps_artifact

    summary = summarize_rwgps_artifact(str(file_path))
    if not summary.get("ok"):
        raise RuntimeError(summary.get("reason") or summary.get("error") or "GPX registration failed")
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT id FROM qbot_v2.route_artifacts WHERE route_id=%s "
            "ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 1",
            (child_route_id,),
        ).fetchone()
        if not row:
            raise RuntimeError(f"route artifact was not persisted for {child_route_id}")
        artifact_id = int(row.get("id") if isinstance(row, dict) else row[0])
        conn.execute(
            "UPDATE qbot_v2.route_artifacts SET source='planer', "
            "metadata_json=COALESCE(metadata_json, '{}'::jsonb) || %s::jsonb, updated_at=now() "
            "WHERE id=%s",
            (json.dumps({"route_name": title, **lineage_meta}, ensure_ascii=False), artifact_id),
        )
        conn.commit()
    base = ensure_route_base(child_route_id)
    return {
        "route_artifact_id": artifact_id,
        "route_base_id": int(base["route_base"]["route_base_id"]),
        "route_version_key": str(base["route_version_key"]),
        "summary": summary,
    }


def _inherit_parent_baseline(
    conn,
    *,
    parent_route_base_id: int,
    stage: dict[str, Any],
) -> dict[str, int]:
    """Slice stable DB layers only; never call an external provider."""
    child_base_id = int(stage["route_base_id"])
    child_version = str(stage["route_version_key"])
    offset = float(stage["km_from"])
    end = float(stage["km_to"])
    conn.execute("DELETE FROM qbot_v2.route_surface_layer WHERE route_base_id=%s", (child_base_id,))
    surface_rows = conn.execute(
        """
        INSERT INTO qbot_v2.route_surface_layer (
            route_base_id, route_version_key, segment_index, surface, highway,
            tracktype, source, confidence, coverage_status, fetched_at, surface_meta_json
        )
        SELECT %s, %s, child_axis.segment_index, parent_surface.surface,
               parent_surface.highway, parent_surface.tracktype,
               'inherited:' || parent_surface.source, parent_surface.confidence,
               parent_surface.coverage_status, parent_surface.fetched_at,
               parent_surface.surface_meta_json
        FROM qbot_v2.route_axis_segments child_axis
        JOIN LATERAL (
            SELECT surface.*
            FROM qbot_v2.route_axis_segments parent_axis
            JOIN qbot_v2.route_surface_layer surface
              ON surface.route_base_id=parent_axis.route_base_id
             AND surface.segment_index=parent_axis.segment_index
            WHERE parent_axis.route_base_id=%s
              AND parent_axis.km_from <= %s + (child_axis.km_from + child_axis.km_to) / 2.0
              AND parent_axis.km_to >= %s + (child_axis.km_from + child_axis.km_to) / 2.0
            ORDER BY parent_axis.segment_index
            LIMIT 1
        ) parent_surface ON true
        WHERE child_axis.route_base_id=%s
        ON CONFLICT (route_base_id, segment_index) DO UPDATE SET
            route_version_key=EXCLUDED.route_version_key,
            surface=EXCLUDED.surface, highway=EXCLUDED.highway,
            tracktype=EXCLUDED.tracktype, source=EXCLUDED.source,
            confidence=EXCLUDED.confidence, coverage_status=EXCLUDED.coverage_status,
            fetched_at=EXCLUDED.fetched_at, surface_meta_json=EXCLUDED.surface_meta_json,
            updated_at=now()
        """,
        (child_base_id, child_version, parent_route_base_id, offset, offset, child_base_id),
    ).rowcount
    axis_count_row = conn.execute(
        "SELECT count(*) AS n FROM qbot_v2.route_axis_segments WHERE route_base_id=%s",
        (child_base_id,),
    ).fetchone()
    axis_count = int(axis_count_row.get("n") if isinstance(axis_count_row, dict) else axis_count_row[0])
    if axis_count and int(surface_rows or 0) < math.ceil(axis_count * 0.9):
        raise RuntimeError(
            f"parent surface coverage is insufficient for day {stage['day']}: {surface_rows}/{axis_count}"
        )

    conn.execute("DELETE FROM qbot_v2.route_poi_layer WHERE route_base_id=%s", (child_base_id,))
    poi_rows = conn.execute(
        """
        INSERT INTO qbot_v2.route_poi_layer (
            route_base_id, route_version_key, poi_key, poi_id, source_place_id,
            provider, name, category, lat, lon, km_on_route,
            distance_from_route_m, opening_hours, opening_hours_fetched_at,
            source_updated_at, confidence, validity_hint, stale_after, status, poi_meta_json
        )
        SELECT %s, %s, poi_key, poi_id, source_place_id, provider, name, category,
               lat, lon, km_on_route-%s, distance_from_route_m, opening_hours,
               opening_hours_fetched_at, source_updated_at, confidence,
               'inherited from expedition route; ' || COALESCE(validity_hint, ''),
               stale_after, status,
               COALESCE(poi_meta_json, '{}'::jsonb) ||
                 jsonb_build_object('inherited_from_route_base_id', %s, 'parent_km', km_on_route)
        FROM qbot_v2.route_poi_layer
        WHERE route_base_id=%s
          AND km_on_route >= %s AND km_on_route <= %s
          AND category <> 'attraction'
        ON CONFLICT (route_base_id, poi_key) DO UPDATE SET
            route_version_key=EXCLUDED.route_version_key, name=EXCLUDED.name,
            category=EXCLUDED.category, lat=EXCLUDED.lat, lon=EXCLUDED.lon,
            km_on_route=EXCLUDED.km_on_route,
            distance_from_route_m=EXCLUDED.distance_from_route_m,
            opening_hours=EXCLUDED.opening_hours,
            opening_hours_fetched_at=EXCLUDED.opening_hours_fetched_at,
            source_updated_at=EXCLUDED.source_updated_at,
            confidence=EXCLUDED.confidence, validity_hint=EXCLUDED.validity_hint,
            stale_after=EXCLUDED.stale_after, status=EXCLUDED.status,
            poi_meta_json=EXCLUDED.poi_meta_json, updated_at=now()
        """,
        (
            child_base_id, child_version, offset, parent_route_base_id,
            parent_route_base_id, offset, end,
        ),
    ).rowcount

    now = datetime.now(timezone.utc)
    for job_type, row_count in (
        ("route_base", axis_count),
        ("route_surface", int(surface_rows or 0)),
        ("route_poi", int(poi_rows or 0)),
    ):
        idem = f"route_precompute:{stage['route_id']}:{child_version}:{job_type}"
        conn.execute(
            """
            INSERT INTO qbot_v2.route_precompute_jobs (
                route_id, route_artifact_id, route_version_key, route_base_id,
                trigger_source, job_type, status, started_at, finished_at,
                layer_status_json, idempotency_key
            ) VALUES (%s,%s,%s,%s,'planer_inherit',%s,'complete',%s,%s,%s::jsonb,%s)
            ON CONFLICT (idempotency_key) DO UPDATE SET
                status='complete', started_at=EXCLUDED.started_at,
                finished_at=EXCLUDED.finished_at,
                layer_status_json=EXCLUDED.layer_status_json, updated_at=now()
            """,
            (
                stage["route_id"], stage["route_artifact_id"], child_version,
                child_base_id, job_type, now, now,
                json.dumps({
                    "status": "OK", "source": "parent_route_slice",
                    "parent_route_base_id": parent_route_base_id,
                    "parent_km_from": offset, "parent_km_to": end,
                    "row_count": row_count,
                }, ensure_ascii=False),
                idem,
            ),
        )
    return {"axis_rows": axis_count, "surface_rows": int(surface_rows or 0), "poi_rows": int(poi_rows or 0)}


def create_planer_day_routes(*, route_id: str, cuts: list[Any]) -> dict[str, Any]:
    route_id = str(route_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", route_id):
        raise ValueError("invalid route_id")

    with _db_conn() as conn:
        parent = _route_base_row(conn, route_id=route_id)
        if not parent:
            raise LookupError(f"route not found: {route_id}")
        parent = dict(parent)
        source_path = _resolve_source_path(parent, conn)
        parent_name = _parent_name(conn, parent)

    points, _ = _parse_gpx_points(Path(source_path))
    actual_total_km = float(points[-1]["cum_km"])
    declared_total_km = float(parent.get("distance_m") or 0.0) / 1000.0
    total_km = actual_total_km if actual_total_km > 0 else declared_total_km
    stages = _validated_bounds(cuts, total_km)
    split_key = _split_key(str(parent["route_version_key"]), stages)
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)

    created: list[dict[str, Any]] = []
    for day_index, (start_km, end_km) in enumerate(stages, 1):
        child_route_id = _child_route_id(route_id, split_key, day_index)
        filename = f"rwgps_{child_route_id}.gpx"
        file_path = EXPORT_ROOT / filename
        title = f"{parent_name} — dzień {day_index}/{len(stages)}"
        segment, used_end = _build_segment_points(points, start_km, end_km)
        xml = _gpx_xml(segment, parent_name, title)
        temporary = file_path.with_suffix(".gpx.tmp")
        temporary.write_bytes(xml)
        temporary.replace(file_path)
        validation = _validate_gpx_file(file_path, round(used_end - start_km, 3))
        if not validation.get("valid_gpx"):
            raise RuntimeError(f"invalid generated GPX for day {day_index}")
        lineage_meta = {
            "kind": "planer_day_route",
            "parent_route_id": route_id,
            "parent_route_base_id": int(parent["route_base_id"]),
            "parent_route_version_key": str(parent["route_version_key"]),
            "parent_km_from": round(start_km, 3),
            "parent_km_to": round(used_end, 3),
            "split_key": split_key,
            "day_index": day_index,
            "day_count": len(stages),
        }
        registered = _register_canonical_gpx(
            file_path,
            child_route_id=child_route_id,
            title=title,
            lineage_meta=lineage_meta,
        )
        created.append({
            "day": day_index,
            "route_id": child_route_id,
            "name": title,
            "km_from": round(start_km, 3),
            "km_to": round(used_end, 3),
            "distance_km": round(used_end - start_km, 3),
            "file_path": str(file_path),
            "valid_gpx": True,
            **{key: registered[key] for key in ("route_artifact_id", "route_base_id", "route_version_key")},
        })

    with _db_conn() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE qbot_v2.route_base SET status='disabled', updated_at=now() "
                "WHERE route_base_id IN ("
                "SELECT stage_route_base_id FROM qbot_v2.route_stage_lineage "
                "WHERE parent_route_base_id=%s AND split_key<>%s AND active=true"
                ")",
                (int(parent["route_base_id"]), split_key),
            )
            conn.execute(
                "UPDATE qbot_v2.route_stage_lineage SET active=false, updated_at=now() "
                "WHERE parent_route_base_id=%s AND split_key<>%s AND active=true",
                (int(parent["route_base_id"]), split_key),
            )
            for stage in created:
                conn.execute(
                    "UPDATE qbot_v2.route_base SET status='active', updated_at=now() WHERE route_base_id=%s",
                    (stage["route_base_id"],),
                )
                conn.execute(
                    "INSERT INTO qbot_v2.route_stage_lineage ("
                    "stage_route_base_id, stage_route_id, parent_route_base_id, parent_route_id, "
                    "split_key, day_index, parent_km_from, parent_km_to, active"
                    ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,true) "
                    "ON CONFLICT (stage_route_base_id) DO UPDATE SET "
                    "stage_route_id=EXCLUDED.stage_route_id, parent_route_base_id=EXCLUDED.parent_route_base_id, "
                    "parent_route_id=EXCLUDED.parent_route_id, split_key=EXCLUDED.split_key, "
                    "day_index=EXCLUDED.day_index, parent_km_from=EXCLUDED.parent_km_from, "
                    "parent_km_to=EXCLUDED.parent_km_to, active=true, updated_at=now()",
                    (
                        stage["route_base_id"], stage["route_id"], int(parent["route_base_id"]), route_id,
                        split_key, stage["day"], stage["km_from"], stage["km_to"],
                    ),
                )
                stage["inherited_layers"] = _inherit_parent_baseline(
                    conn,
                    parent_route_base_id=int(parent["route_base_id"]),
                    stage=stage,
                )

    return {
        "status": "OK",
        "parent_route_id": route_id,
        "parent_route_base_id": int(parent["route_base_id"]),
        "split_key": split_key,
        "day_count": len(created),
        "days": created,
        "attractions_source": "parent_route_attraction_run",
        "external_attraction_requests": 0,
    }
