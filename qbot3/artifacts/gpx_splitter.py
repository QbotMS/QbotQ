#!/usr/bin/env python3
"""Local GPX splitter for QBot route artifacts.

Reads a source GPX from /opt/qbot/artifacts, cuts it into stage files by
cumulative distance, and writes valid GPX artifacts back into the sandbox.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GPX_NS = "http://www.topografix.com/GPX/1/1"
ET.register_namespace("", GPX_NS)

ARTIFACTS_ROOT = Path("/opt/qbot/artifacts")

SOURCE_DIR = ARTIFACTS_ROOT / "exports" / "rwgps"
PROJECT_ROUTE_DIR = ARTIFACTS_ROOT / "projects" / "tuscany_2026" / "projects"


@dataclass(frozen=True)
class StageSpec:
    stage: int
    start_km: float
    end_km: float | None
    filename: str
    title: str


DEFAULT_STAGE_SPECS: dict[tuple[str, int], list[StageSpec]] = {
    (
        "tuscany_2026",
        55256628,
    ): [
        StageSpec(1, 0.0, 65.0, "tuscany_2026_stage_01_scandicci_capannoli.gpx", "Tuscany 2026 Stage 01"),
        StageSpec(2, 65.0, 150.0, "tuscany_2026_stage_02_capannoli_castagneto_carducci.gpx", "Tuscany 2026 Stage 02"),
        StageSpec(3, 150.0, 235.0, "tuscany_2026_stage_03_castagneto_carducci_castiglione_della_pescaia.gpx", "Tuscany 2026 Stage 03"),
        StageSpec(4, 235.0, 330.0, "tuscany_2026_stage_04_castiglione_della_pescaia_paganico.gpx", "Tuscany 2026 Stage 04"),
        StageSpec(5, 330.0, 380.0, "tuscany_2026_stage_05_paganico_pienza.gpx", "Tuscany 2026 Stage 05"),
        StageSpec(6, 380.0, 455.0, "tuscany_2026_stage_06_pienza_monteriggioni.gpx", "Tuscany 2026 Stage 06"),
        StageSpec(7, 455.0, None, "tuscany_2026_stage_07_monteriggioni_scandicci.gpx", "Tuscany 2026 Stage 07"),
    ]
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _resolve_source_path(route_id: int, source_gpx_path: str | None = None) -> Path:
    if source_gpx_path:
        raw = Path(str(source_gpx_path).strip())
        if raw.is_absolute():
            return raw
        return (ARTIFACTS_ROOT / raw).resolve(strict=False)
    return SOURCE_DIR / f"rwgps_{route_id}.gpx"


def _parse_gpx_points(source_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tree = ET.parse(str(source_path))
    root = tree.getroot()

    metadata_name = ""
    for node in root.iter():
        if node.tag.endswith("name") and node.text and not metadata_name:
            metadata_name = node.text.strip()
            break

    points: list[dict[str, Any]] = []
    prev: dict[str, Any] | None = None
    cum_km = 0.0

    for trkpt in root.iter():
        if not trkpt.tag.endswith("trkpt"):
            continue
        lat = trkpt.get("lat")
        lon = trkpt.get("lon")
        if lat is None or lon is None:
            continue
        ele = None
        for child in list(trkpt):
            if child.tag.endswith("ele") and child.text:
                try:
                    ele = float(child.text)
                except ValueError:
                    ele = None
                break

        lat_f = float(lat)
        lon_f = float(lon)
        if prev is not None:
            cum_km += _haversine_km(prev["lat"], prev["lon"], lat_f, lon_f)

        point = {
            "lat": lat_f,
            "lon": lon_f,
            "ele": ele,
            "cum_km": cum_km,
        }
        points.append(point)
        prev = point

    if len(points) < 2:
        raise ValueError(f"Brak wystarczającej liczby trackpointów w {source_path}")

    return points, {"route_name": metadata_name or source_path.stem}


def _point_at_km(points: list[dict[str, Any]], target_km: float) -> dict[str, Any]:
    if target_km <= 0:
        first = points[0]
        return {**first, "cum_km": 0.0}

    total_km = points[-1]["cum_km"]
    if target_km >= total_km:
        last = points[-1]
        return {**last, "cum_km": total_km}

    for a, b in zip(points, points[1:]):
        if a["cum_km"] <= target_km <= b["cum_km"]:
            span = b["cum_km"] - a["cum_km"]
            if span <= 0:
                return {**a, "cum_km": a["cum_km"]}
            t = (target_km - a["cum_km"]) / span
            lat = a["lat"] + t * (b["lat"] - a["lat"])
            lon = a["lon"] + t * (b["lon"] - a["lon"])
            ele = None
            if a.get("ele") is not None and b.get("ele") is not None:
                ele = a["ele"] + t * (b["ele"] - a["ele"])
            return {
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "ele": round(ele, 1) if ele is not None else None,
                "cum_km": round(target_km, 6),
            }

    return {**points[-1], "cum_km": total_km}


def _build_segment_points(points: list[dict[str, Any]], start_km: float, end_km: float | None) -> tuple[list[dict[str, Any]], float]:
    total_km = points[-1]["cum_km"]
    final_km = total_km if end_km is None else min(float(end_km), total_km)
    if final_km <= start_km:
        raise ValueError(f"Nieprawidłowy zakres etapu: {start_km} -> {final_km}")

    segment: list[dict[str, Any]] = [_point_at_km(points, start_km)]
    for point in points:
        if start_km < point["cum_km"] < final_km:
            segment.append(dict(point))
    segment.append(_point_at_km(points, final_km))
    return segment, final_km


def _distance_km(points: list[dict[str, Any]]) -> float:
    total_m = 0.0
    for a, b in zip(points, points[1:]):
        total_m += _haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) * 1000.0
    return round(total_m / 1000.0, 3)


def _gpx_xml(segment_points: list[dict[str, Any]], route_name: str, stage_title: str) -> bytes:
    gpx = ET.Element(
        f"{{{GPX_NS}}}gpx",
        {
            "version": "1.1",
            "creator": "QBot route_gpx_split",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": (
                "http://www.topografix.com/GPX/1/1 "
                "http://www.topografix.com/GPX/1/1/gpx.xsd"
            ),
        },
    )
    metadata = ET.SubElement(gpx, f"{{{GPX_NS}}}metadata")
    name = ET.SubElement(metadata, f"{{{GPX_NS}}}name")
    name.text = stage_title
    desc = ET.SubElement(metadata, f"{{{GPX_NS}}}desc")
    desc.text = f"Split from {route_name}"
    trk = ET.SubElement(gpx, f"{{{GPX_NS}}}trk")
    trk_name = ET.SubElement(trk, f"{{{GPX_NS}}}name")
    trk_name.text = stage_title
    trkseg = ET.SubElement(trk, f"{{{GPX_NS}}}trkseg")
    for point in segment_points:
        trkpt = ET.SubElement(trkseg, f"{{{GPX_NS}}}trkpt", {"lat": f"{point['lat']:.6f}", "lon": f"{point['lon']:.6f}"})
        if point.get("ele") is not None:
            ele = ET.SubElement(trkpt, f"{{{GPX_NS}}}ele")
            ele.text = f"{float(point['ele']):.1f}"
    tree = ET.ElementTree(gpx)
    try:
        ET.indent(tree, space="  ")
    except Exception:
        pass
    xml = ET.tostring(gpx, encoding="utf-8", xml_declaration=True)
    return xml


def _validate_gpx_file(file_path: Path, expected_distance_km: float, expected_min_trackpoints: int = 3) -> dict[str, Any]:
    size_bytes = file_path.stat().st_size if file_path.exists() else 0
    valid_gpx = False
    trackpoint_count = 0
    distance_km = None
    try:
        tree = ET.parse(str(file_path))
        root = tree.getroot()
        pts: list[dict[str, Any]] = []
        for trkpt in root.iter():
            if not trkpt.tag.endswith("trkpt"):
                continue
            lat = trkpt.get("lat")
            lon = trkpt.get("lon")
            if lat is None or lon is None:
                continue
            ele = None
            for child in list(trkpt):
                if child.tag.endswith("ele") and child.text:
                    try:
                        ele = float(child.text)
                    except ValueError:
                        ele = None
                    break
            pts.append({"lat": float(lat), "lon": float(lon), "ele": ele})
        trackpoint_count = len(pts)
        distance_km = _distance_km(pts) if trackpoint_count > 1 else 0.0
        valid_gpx = size_bytes > 0 and trackpoint_count >= expected_min_trackpoints and abs(distance_km - expected_distance_km) <= max(1.0, expected_distance_km * 0.02)
    except Exception:
        valid_gpx = False
    return {
        "size_bytes": size_bytes,
        "trackpoint_count": trackpoint_count,
        "distance_km": distance_km,
        "valid_gpx": valid_gpx,
    }


def _upsert_artifact_record(
    *,
    file_path: Path,
    route_id: int,
    stage: int,
    title: str,
    project_id: str,
    source_route_path: Path,
    source_route_name: str,
    expected_distance_km: float,
    trackpoint_count: int,
    stage_start_km: float,
    stage_end_km: float,
    sha256: str,
    size_bytes: int,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    from qbot3.artifacts.store import _db_conn, ensure_bootstrap

    ensure_bootstrap()
    rel_path = str(file_path.relative_to(ARTIFACTS_ROOT))
    metadata = {
        "route_id": route_id,
        "project_id": project_id,
        "stage": stage,
        "stage_start_km": stage_start_km,
        "stage_end_km": stage_end_km,
        "distance_km": expected_distance_km,
        "trackpoint_count": trackpoint_count,
        "source_route_path": str(source_route_path.relative_to(ARTIFACTS_ROOT)),
        "source_route_name": source_route_name,
        "splitter": "route_gpx_split",
    }

    mime_type = "application/gpx+xml"
    with _db_conn() as conn:
        existing = conn.execute(
            "SELECT artifact_id FROM qbot_v2.artifacts WHERE file_path = %s ORDER BY created_at DESC LIMIT 1",
            (rel_path,),
        ).fetchone()
        if existing:
            art_id = existing["artifact_id"]
            row = conn.execute(
                """
                UPDATE qbot_v2.artifacts
                SET project_id = %s,
                    artifact_type = %s::qbot_v2.artifact_type,
                    mutation_type = %s::qbot_v2.mutation_type,
                    title = %s,
                    filename = %s,
                    mime_type = %s,
                    file_path = %s,
                    size_bytes = %s,
                    sha256 = %s,
                    source = %s,
                    status = %s::qbot_v2.artifact_status,
                    version = COALESCE(version, 1),
                    expires_at = NULL,
                    idempotency_key = %s,
                    metadata_json = %s::jsonb,
                    updated_at = now()
                WHERE artifact_id = %s
                RETURNING *
                """,
                (
                    project_id,
                    "route",
                    "split",
                    title,
                    file_path.name,
                    mime_type,
                    rel_path,
                    size_bytes,
                    sha256,
                    "albert",
                    "active",
                    f"route_gpx_split:{route_id}:{stage}:{file_path.name}",
                    json.dumps(metadata, ensure_ascii=False),
                    art_id,
                ),
            ).fetchone()
        else:
            art_id = artifact_id or str(uuid.uuid4())
            row = conn.execute(
                """
                INSERT INTO qbot_v2.artifacts (
                    artifact_id, project_id, artifact_type, mutation_type,
                    title, filename, mime_type, file_path,
                    size_bytes, sha256, source, status,
                    parent_artifact_id, version, expires_at, idempotency_key, metadata_json
                ) VALUES (
                    %s, %s, %s::qbot_v2.artifact_type, %s::qbot_v2.mutation_type,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s::qbot_v2.artifact_status,
                    %s, %s, %s, %s, %s::jsonb
                )
                RETURNING *
                """,
                (
                    art_id,
                    project_id,
                    "route",
                    "split",
                    title,
                    file_path.name,
                    mime_type,
                    rel_path,
                    size_bytes,
                    sha256,
                    "albert",
                    "active",
                    None,
                    1,
                    None,
                    f"route_gpx_split:{route_id}:{stage}:{file_path.name}",
                    json.dumps(metadata, ensure_ascii=False),
                ),
            ).fetchone()
        conn.commit()
    return dict(row)


def _default_stage_specs(project_id: str, route_id: int) -> list[StageSpec]:
    specs = DEFAULT_STAGE_SPECS.get((project_id, route_id))
    if not specs:
        raise ValueError(
            "Brak domyślnych cięć dla tego projektu/trasy. Podaj stage_specs albo użyj "
            "kanonicznej trasy tuscany_2026 / 55256628."
        )
    return list(specs)


def split_route_gpx(
    route_id: int,
    *,
    project_id: str = "tuscany_2026",
    source_gpx_path: str | None = None,
    overwrite_existing: bool = True,
) -> dict[str, Any]:
    """Split a source RWGPS GPX into stage artifacts."""
    from qbot3.artifacts.store import _db_conn, ensure_bootstrap

    ensure_bootstrap()
    source_path = _resolve_source_path(route_id, source_gpx_path)
    if not source_path.exists():
        return {"status": "error", "error": f"Brak pliku źródłowego: {source_path}"}
    if source_path.stat().st_size <= 0:
        return {"status": "error", "error": f"Plik źródłowy jest pusty: {source_path}"}

    points, meta = _parse_gpx_points(source_path)
    source_name = str(meta.get("route_name") or source_path.stem)
    total_km = points[-1]["cum_km"]
    if total_km <= 0:
        return {"status": "error", "error": f"Trasa ma zerową długość: {source_path}"}

    stage_specs = _default_stage_specs(project_id, route_id)
    results: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    source_artifact_row = None
    try:
        with _db_conn() as conn:
            source_artifact_row = conn.execute(
                "SELECT artifact_id FROM qbot_v2.artifacts WHERE file_path = %s ORDER BY created_at DESC LIMIT 1",
                (str(source_path.relative_to(ARTIFACTS_ROOT)),),
            ).fetchone()
    except Exception:
        source_artifact_row = None

    for spec in stage_specs:
        final_end_km = total_km if spec.end_km is None else min(float(spec.end_km), total_km)
        segment_points, used_end_km = _build_segment_points(points, spec.start_km, spec.end_km)
        xml_bytes = _gpx_xml(segment_points, source_name, spec.title)

        file_path = PROJECT_ROUTE_DIR / spec.filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.exists() and not overwrite_existing:
            return {"status": "error", "error": f"Plik docelowy już istnieje: {file_path}"}
        file_path.write_bytes(xml_bytes)

        sha256 = hashlib.sha256(xml_bytes).hexdigest()
        validation = _validate_gpx_file(file_path, expected_distance_km=round(used_end_km - spec.start_km, 3))
        validation.update({
            "stage": spec.stage,
            "start_km": round(spec.start_km, 3),
            "end_km": round(used_end_km, 3),
            "file_path": str(file_path),
            "sha256": sha256,
        })
        if source_artifact_row and source_artifact_row.get("artifact_id"):
            validation["source_artifact_id"] = str(source_artifact_row["artifact_id"])
        valid_gpx = bool(validation["valid_gpx"])

        artifact_row = _upsert_artifact_record(
            file_path=file_path,
            route_id=route_id,
            stage=spec.stage,
            title=spec.title,
            project_id=project_id,
            source_route_path=source_path,
            source_route_name=source_name,
            expected_distance_km=round(used_end_km - spec.start_km, 3),
            trackpoint_count=validation["trackpoint_count"],
            stage_start_km=spec.start_km,
            stage_end_km=used_end_km,
            sha256=sha256,
            size_bytes=validation["size_bytes"],
        )

        result = {
            "stage": spec.stage,
            "start_km": round(spec.start_km, 3),
            "end_km": round(used_end_km, 3),
            "distance_km": validation["distance_km"],
            "file_path": str(file_path),
            "size_bytes": validation["size_bytes"],
            "trackpoint_count": validation["trackpoint_count"],
            "sha256": sha256,
            "valid_gpx": valid_gpx,
            "artifact_id": str(artifact_row.get("artifact_id")) if artifact_row.get("artifact_id") else None,
        }
        results.append(result)
        validations.append(validation)

    return {
        "status": "OK",
        "route_id": route_id,
        "project_id": project_id,
        "source_gpx_path": str(source_path),
        "source_route_name": source_name,
        "source_distance_km": round(total_km, 3),
        "stage_count": len(results),
        "stages": results,
        "valid_gpx_count": sum(1 for r in results if r.get("valid_gpx")),
        "all_valid_gpx": all(r.get("valid_gpx") for r in results),
        "validation": validations,
    }
