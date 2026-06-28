#!/usr/bin/env python3
"""Production gravel surface analysis along the real route track.

2026-06-28 intent: make route surface truth track-based, not route_frames-based.
route_frames may remain a legacy profile/weather/debug layer, but this module is
the backend surface engine for GPX/TCX/JSON/RWGPS artifacts.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from tools.rwgps.client import _resolve_artifact_for_summary, extract_artifact_points

try:
    from tools.rwgps.surface_landcover import _fetch_landuse, landcover_for_point
except Exception:  # pragma: no cover - import fallback only
    _fetch_landuse = None
    landcover_for_point = None


ENGINE_VERSION = "route_surface_engine_v1"
DEFAULT_SAMPLE_DISTANCE_M = 50
PRIMARY_CORRIDOR_RADIUS_M = 50
FALLBACK_CORRIDOR_RADIUS_M = 80
DEBUG_MAX_MATCH_DIST_M = 150
CACHE_ROOT = Path("/opt/qbot/artifacts/analysis")
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
USER_AGENT = "QBot/1.0 route_surface_engine_v1"


SURFACE_CANONICAL = {
    "asphalt": "asphalt",
    "paved": "asphalt",
    "chipseal": "asphalt",
    "concrete": "concrete",
    "concrete:plates": "concrete",
    "concrete:lanes": "concrete",
    "paving_stones": "paving_stones",
    "sett": "cobblestone",
    "cobblestone": "cobblestone",
    "unhewn_cobblestone": "cobblestone",
    "gravel": "gravel",
    "fine_gravel": "fine_gravel",
    "compacted": "compacted",
    "dirt": "dirt",
    "earth": "dirt",
    "ground": "ground",
    "soil": "ground",
    "grass": "grass",
    "sand": "sand",
    "mud": "mud",
    "rock": "rocky",
    "stone": "stony",
    "pebblestone": "stony",
    "unpaved": "mixed",
}

TRACKTYPE_SURFACE = {
    "grade1": ("compacted", "medium", "tracktype=grade1 implies paved/compacted track"),
    "grade2": ("fine_gravel", "medium", "tracktype=grade2 implies compacted fine gravel"),
    "grade3": ("gravel", "medium", "tracktype=grade3 implies gravel/ground"),
    "grade4": ("dirt", "low", "tracktype=grade4 implies dirt/grass/loose surface"),
    "grade5": ("grass", "low", "tracktype=grade5 implies weak dirt/grass surface"),
}

PAVED_HIGHWAYS = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "residential",
    "living_street",
    "service",
}

DIFFICULT_SURFACES = {
    "sand",
    "loose",
    "cobblestone",
    "rocky",
    "stony",
    "mud",
    "unknown",
}


@dataclass(frozen=True)
class Sample:
    index: int
    lat: float
    lon: float
    ele: float | None
    dist_m: float


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _point_segment_dist_m(lat: float, lon: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    lat0 = math.radians(lat)
    mx = 111320.0 * math.cos(lat0)
    my = 111320.0
    px, py = lon * mx, lat * my
    ax, ay = a[1] * mx, a[0] * my
    bx, by = b[1] * mx, b[0] * my
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _way_distance_m(lat: float, lon: float, geometry: list[dict[str, Any]]) -> float:
    coords: list[tuple[float, float]] = []
    for node in geometry or []:
        try:
            coords.append((float(node["lat"]), float(node["lon"])))
        except Exception:
            continue
    if not coords:
        return float("inf")
    if len(coords) == 1:
        return _haversine_m(lat, lon, coords[0][0], coords[0][1])
    return min(_point_segment_dist_m(lat, lon, coords[i - 1], coords[i]) for i in range(1, len(coords)))


def _way_bbox(geometry: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    vals: list[tuple[float, float]] = []
    for node in geometry or []:
        try:
            vals.append((float(node["lat"]), float(node["lon"])))
        except Exception:
            continue
    if not vals:
        return None
    lats = [v[0] for v in vals]
    lons = [v[1] for v in vals]
    return min(lats), min(lons), max(lats), max(lons)


def _cumulative_distances(points: list[list[float]]) -> list[float]:
    dists = [0.0]
    for i in range(1, len(points)):
        dists.append(dists[-1] + _haversine_m(float(points[i - 1][0]), float(points[i - 1][1]), float(points[i][0]), float(points[i][1])))
    return dists


def _interpolate_sample(points: list[list[float]], dists: list[float], target_m: float, index: int) -> Sample:
    for i in range(1, len(dists)):
        if dists[i] >= target_m:
            prev_d = dists[i - 1]
            span = max(dists[i] - prev_d, 1e-9)
            t = (target_m - prev_d) / span
            a = points[i - 1]
            b = points[i]
            lat = float(a[0]) + (float(b[0]) - float(a[0])) * t
            lon = float(a[1]) + (float(b[1]) - float(a[1])) * t
            ele = None
            if len(a) >= 3 and len(b) >= 3:
                try:
                    ele = float(a[2]) + (float(b[2]) - float(a[2])) * t
                except Exception:
                    ele = None
            return Sample(index=index, lat=lat, lon=lon, ele=ele, dist_m=target_m)
    last = points[-1]
    ele = float(last[2]) if len(last) >= 3 else None
    return Sample(index=index, lat=float(last[0]), lon=float(last[1]), ele=ele, dist_m=dists[-1])


def _sample_track(points: list[list[float]], dists: list[float], sample_distance_m: int) -> list[Sample]:
    total = dists[-1]
    samples = [Sample(0, float(points[0][0]), float(points[0][1]), float(points[0][2]) if len(points[0]) >= 3 else None, 0.0)]
    target = float(sample_distance_m)
    idx = 1
    while target < total:
        samples.append(_interpolate_sample(points, dists, target, idx))
        idx += 1
        target += float(sample_distance_m)
    if total > 0 and (not samples or samples[-1].dist_m < total):
        last = points[-1]
        samples.append(Sample(idx, float(last[0]), float(last[1]), float(last[2]) if len(last) >= 3 else None, total))
    return samples


def _bbox_for_samples(samples: list[Sample], pad_m: float = 120.0) -> tuple[float, float, float, float]:
    lats = [s.lat for s in samples]
    lons = [s.lon for s in samples]
    mid_lat = sum(lats) / len(lats)
    pad_lat = pad_m / 111320.0
    pad_lon = pad_m / max(111320.0 * math.cos(math.radians(mid_lat)), 1.0)
    return min(lats) - pad_lat, min(lons) - pad_lon, max(lats) + pad_lat, max(lons) + pad_lon


def _overpass(query: str, timeout: int = 8) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    last: str | None = None
    effective_timeout = max(3, min(int(timeout), 8))
    for url in OVERPASS_URLS[:1]:
        try:
            response = httpx.post(url, data={"data": query}, headers=headers, timeout=effective_timeout)
            if response.status_code == 200:
                return response.json()
            last = f"{response.status_code} @ {url}"
        except Exception as exc:
            last = f"{exc.__class__.__name__}: {exc}"
        time.sleep(0.4)
    raise RuntimeError(f"Overpass unavailable: {last}")


def _fetch_highways_along_track(samples: list[Sample], radius_m: int, warnings: list[str]) -> list[dict[str, Any]]:
    ways: dict[int | str, dict[str, Any]] = {}
    chunk_size = 220
    for chunk_idx, start in enumerate(range(0, len(samples), chunk_size), start=1):
        chunk = samples[start : start + chunk_size]
        south, west, north, east = _bbox_for_samples(chunk, pad_m=float(radius_m))
        query = f'[out:json][timeout:8];way["highway"]({south:.7f},{west:.7f},{north:.7f},{east:.7f});out tags geom;'
        try:
            payload = _overpass(query, timeout=8)
        except Exception as exc:
            warnings.append(f"Overpass highway chunk {chunk_idx} failed-open: {exc}")
            continue
        for el in payload.get("elements", []) if isinstance(payload, dict) else []:
            if el.get("type") != "way":
                continue
            tags = el.get("tags")
            geom = el.get("geometry")
            if not isinstance(tags, dict) or not isinstance(geom, list):
                continue
            bbox = _way_bbox(geom)
            if bbox is None:
                continue
            el["_qbot_bbox"] = bbox
            key = el.get("id")
            ways[key if key is not None else f"anon-{id(el)}"] = el
    return list(ways.values())


def _confidence_for_distance(dist_m: float) -> str:
    if dist_m <= 25:
        return "high"
    if dist_m <= 50:
        return "medium"
    if dist_m <= 80:
        return "low"
    if dist_m <= DEBUG_MAX_MATCH_DIST_M:
        return "very_low"
    return "unknown"


def _canonical_surface(raw: Any) -> str | None:
    txt = str(raw).strip().lower() if raw is not None else ""
    if not txt:
        return None
    if txt in SURFACE_CANONICAL:
        return SURFACE_CANONICAL[txt]
    if "asph" in txt:
        return "asphalt"
    if "concrete" in txt:
        return "concrete"
    if "paving" in txt:
        return "paving_stones"
    if "cobble" in txt or txt == "sett":
        return "cobblestone"
    if "fine_gravel" in txt:
        return "fine_gravel"
    if "gravel" in txt:
        return "gravel"
    if "compact" in txt:
        return "compacted"
    if "sand" in txt:
        return "sand"
    if "mud" in txt or "clay" in txt:
        return "mud"
    if "rock" in txt:
        return "rocky"
    if "stone" in txt:
        return "stony"
    if any(k in txt for k in ("dirt", "earth", "ground", "soil")):
        return "ground"
    if "grass" in txt:
        return "grass"
    return "mixed"


def _infer_from_tags(tags: dict[str, Any]) -> tuple[str, str, str]:
    raw = _canonical_surface(tags.get("surface"))
    if raw:
        return raw, "high", "explicit OSM surface tag"
    tracktype = str(tags.get("tracktype") or "").strip().lower()
    if tracktype in TRACKTYPE_SURFACE:
        return TRACKTYPE_SURFACE[tracktype]
    highway = str(tags.get("highway") or "").strip().lower()
    smoothness = str(tags.get("smoothness") or "").strip().lower()
    if highway in PAVED_HIGHWAYS:
        if smoothness in {"bad", "very_bad", "horrible", "very_horrible"}:
            return "mixed", "medium", f"highway={highway} is usually paved but smoothness={smoothness}"
        return "asphalt", "medium", f"highway={highway} usually implies paved surface"
    if highway == "cycleway":
        return "asphalt", "medium", "cycleway usually implies paved surface"
    if highway == "track":
        return "ground", "low", "highway=track without surface/tracktype"
    if highway in {"path", "footway", "bridleway"}:
        return "dirt", "low", f"highway={highway} without surface"
    return "unknown", "unknown", "no surface-relevant OSM tags"


def _landcover_label(lat: float, lon: float, polygons: list[dict[str, Any]]) -> str | None:
    if not polygons or landcover_for_point is None:
        return None
    try:
        pl = landcover_for_point(lat, lon, polygons)
    except Exception:
        return None
    return {
        "las": "forest",
        "pola": "farmland",
        "laki/zielen": "meadow",
        "zabudowa": "residential",
        "surowa": "bare",
        "woda": "water",
        "teren otwarty": "open",
    }.get(str(pl), str(pl))


def _refine_context(surface: str, confidence: str, tags: dict[str, Any], landcover: str | None, geology_hint: str) -> tuple[str, str, list[str], str, bool]:
    highway = str(tags.get("highway") or "").strip().lower()
    tracktype = str(tags.get("tracktype") or "").strip().lower()
    refined = surface
    risk_flags: list[str] = []
    applied_geo = False
    explanation = "kept OSM-derived surface"

    if surface in {"unknown", "mixed"} or confidence in {"low", "very_low", "unknown"}:
        if highway == "track" and landcover == "forest":
            refined = "ground" if tracktype not in {"grade2", "grade3"} else surface
            explanation = "surface missing/weak; forest track context suggests ground/compacted"
        elif highway == "track" and landcover == "farmland":
            refined = "ground"
            explanation = "surface missing/weak; farmland track context suggests dirt/ground/grass"
        elif highway == "service" and landcover in {"residential", "industrial"}:
            refined = "asphalt"
            explanation = "service road in built-up context is probably paved"
        elif highway in {"path", "footway", "bridleway"} and landcover == "forest":
            refined = "dirt"
            explanation = "forest path context suggests dirt, with limited confidence"

    if geology_hint in {"sand", "alluvial"} and refined in {"unknown", "ground", "dirt", "grass"}:
        risk_flags.append("sand_possible")
        applied_geo = True
    elif geology_hint in {"clay"} and refined in {"unknown", "ground", "dirt"}:
        risk_flags.append("mud_possible")
        applied_geo = True
    elif geology_hint in {"limestone", "sandstone", "granite", "volcanic"} and refined in {"unknown", "ground", "dirt", "gravel", "compacted"}:
        risk_flags.append("stony_or_hardpack_possible")
        applied_geo = True
    return refined, explanation, risk_flags, "osm_tags_plus_landcover_plus_geology_hint" if applied_geo or landcover else "osm_tags", applied_geo


def _geology_context(samples: list[Sample], enabled: bool, warnings: list[str]) -> dict[str, Any]:
    context = {
        "enabled": bool(enabled),
        "provider": None,
        "status": "UNAVAILABLE" if enabled else "DISABLED",
        "dominant_unit": None,
        "units": [],
        "sections": [],
        "material_hint": "unknown",
        "confidence": "unknown",
        "source_resolution": None,
        "sample_strategy": "centroid+bbox+10km_control_points",
        "explanation": None,
        "warnings": [],
    }
    if not enabled:
        return context
    # Provider chain is intentionally stubbed in phase 1. The engine keeps the
    # geology stage in the JSON contract but never samples geology at 50 m.
    msg = "geology provider chain not connected yet; fail-open without surface override"
    context["warnings"].append(msg)
    warnings.append(msg)
    return context


def _maybe_valhalla_refinement(samples: list[Sample], enabled: bool, warnings: list[str]) -> dict[str, Any]:
    result = {"enabled": bool(enabled), "used": False, "status": "DISABLED", "warnings": []}
    if not enabled:
        return result
    result["status"] = "UNAVAILABLE"
    msg = "Valhalla trace_attributes refinement not connected in phase 1; OSM/contextual result kept"
    result["warnings"].append(msg)
    warnings.append(msg)
    return result


def _match_sample(sample: Sample, ways: list[dict[str, Any]], max_dist_m: float) -> tuple[dict[str, Any] | None, float | None, Any | None]:
    best: dict[str, Any] | None = None
    best_id: Any | None = None
    best_dist = float("inf")
    pad_deg = max_dist_m / 111320.0 + 0.00015
    for way in ways:
        bbox = way.get("_qbot_bbox")
        if isinstance(bbox, tuple) and len(bbox) == 4:
            south, west, north, east = bbox
            if sample.lat < south - pad_deg or sample.lat > north + pad_deg or sample.lon < west - pad_deg or sample.lon > east + pad_deg:
                continue
        dist = _way_distance_m(sample.lat, sample.lon, way.get("geometry") or [])
        if dist < best_dist:
            best = way
            best_id = way.get("id")
            best_dist = dist
    if best is None or best_dist > max_dist_m:
        return None, None, None
    return best, best_dist, best_id


def _segment_from_run(run: list[dict[str, Any]], next_dist: float | None = None) -> dict[str, Any]:
    first = run[0]
    last = run[-1]
    end_m = next_dist if next_dist is not None else last["dist_m"]
    dist_m = max(0.0, end_m - first["dist_m"])
    conf_counts = Counter(item["confidence"] for item in run)
    confidence = sorted(conf_counts, key=lambda c: {"unknown": 0, "very_low": 1, "low": 2, "medium": 3, "high": 4}.get(c, 0))[0]
    match_vals = [item["match_distance_m"] for item in run if item.get("match_distance_m") is not None]
    warnings = []
    for item in run:
        warnings.extend(item.get("warnings") or [])
    risk_flags = sorted({flag for item in run for flag in item.get("risk_flags", [])})
    return {
        "km_from": round(first["dist_m"] / 1000.0, 3),
        "km_to": round(end_m / 1000.0, 3),
        "distance_m": round(dist_m, 1),
        "surface_raw": first["surface_raw"],
        "surface_inferred": first["surface_inferred"],
        "surface_refined": first["surface_refined"],
        "highway": first.get("highway"),
        "tracktype": first.get("tracktype"),
        "smoothness": first.get("smoothness"),
        "landcover": first.get("landcover"),
        "geology_hint_applied": any(item.get("geology_hint_applied") for item in run),
        "confidence": confidence,
        "source": first["source"],
        "method": first["method"],
        "match_distance_m_avg": round(sum(match_vals) / len(match_vals), 1) if match_vals else None,
        "match_distance_m_max": round(max(match_vals), 1) if match_vals else None,
        "way_id": first.get("way_id"),
        "valhalla_snap_quality": first.get("valhalla_snap_quality"),
        "risk_flags": risk_flags,
        "warnings": sorted(set(warnings)),
        "explanation": first["explanation"],
    }


def _merge_samples(sample_rows: list[dict[str, Any]], total_m: float) -> list[dict[str, Any]]:
    if not sample_rows:
        return []
    segments: list[dict[str, Any]] = []
    run = [sample_rows[0]]
    for row in sample_rows[1:]:
        prev = run[-1]
        same = row["surface_refined"] == prev["surface_refined"] and row["confidence"] == prev["confidence"]
        difficult = row["surface_refined"] in DIFFICULT_SURFACES or prev["surface_refined"] in DIFFICULT_SURFACES
        if same and not (difficult and (row["dist_m"] - run[0]["dist_m"]) >= 150):
            run.append(row)
            continue
        segments.append(_segment_from_run(run, next_dist=row["dist_m"]))
        run = [row]
    segments.append(_segment_from_run(run, next_dist=total_m))
    return [seg for seg in segments if seg["distance_m"] > 0]


def _percentages(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    counts = Counter(row.get(key) or "unknown" for row in rows)
    total = sum(counts.values()) or 1
    return {name: round(count / total * 100.0, 1) for name, count in counts.most_common()}


def _route_id_from_path(path: Path) -> str | None:
    m = re.search(r"rwgps_(\d+)", path.name)
    return m.group(1) if m else None


def analyze_route_surface(
    route_id: str | int | None = None,
    artifact_path: str | None = None,
    mode: str = "gravel_detail",
    sample_distance_m: int | None = None,
    use_valhalla: bool = False,
    use_landcover: bool = True,
    use_geology_context: bool = True,
    refresh: bool = False,
) -> dict[str, Any]:
    mode = mode if mode in {"gravel_detail", "overview", "debug"} else "gravel_detail"
    sample_distance_m = int(sample_distance_m or DEFAULT_SAMPLE_DISTANCE_M)
    sample_distance_m = max(25, min(sample_distance_m, 5000))
    warnings: list[str] = []

    if artifact_path:
        input_ref = str(artifact_path)
    elif route_id is not None:
        input_ref = f"rwgps_{route_id}.gpx"
    else:
        return {"ok": False, "error": "MISSING_INPUT", "reason": "route_id or artifact_path is required"}

    try:
        file_path = _resolve_artifact_for_summary(input_ref)
        file_bytes = file_path.read_bytes()
        file_sha = hashlib.sha256(file_bytes).hexdigest()
    except Exception as exc:
        return {"ok": False, "error": "NOT_FOUND", "reason": str(exc), "route_id": str(route_id) if route_id is not None else None, "artifact_path": artifact_path}

    route_id_str = str(route_id) if route_id is not None else _route_id_from_path(file_path)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_ROOT / f"route_surface_engine_{file_path.stem}_{sample_distance_m}m_{ENGINE_VERSION}_{file_sha[:12]}.json"
    if cache_path.exists() and not refresh:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and cached.get("ok"):
                cached["cache_hit"] = True
                return cached
        except Exception:
            pass

    try:
        points = extract_artifact_points(str(file_path))
    except Exception as exc:
        return {"ok": False, "error": "POINT_EXTRACTION_FAILED", "reason": str(exc), "artifact_path": str(file_path), "route_id": route_id_str}
    if len(points) < 2:
        return {"ok": False, "error": "NO_POINTS", "reason": "artifact has fewer than 2 points", "artifact_path": str(file_path), "route_id": route_id_str, "point_count": len(points)}

    dists = _cumulative_distances(points)
    samples = _sample_track(points, dists, sample_distance_m)
    landcover_used = False
    valhalla_info = _maybe_valhalla_refinement(samples, use_valhalla, warnings)
    geology = _geology_context(samples, use_geology_context, warnings)
    geology_hint = str(geology.get("material_hint") or "unknown")

    ways = _fetch_highways_along_track(samples, PRIMARY_CORRIDOR_RADIUS_M, warnings)
    if not ways:
        warnings.append("primary corridor returned no highways; trying fallback 80 m corridor")
        ways = _fetch_highways_along_track(samples, FALLBACK_CORRIDOR_RADIUS_M, warnings)

    polygons: list[dict[str, Any]] = []
    if use_landcover and _fetch_landuse is not None:
        warnings.append("landcover network refinement disabled in phase 1 after timeout tests; chunked landcover cache needed")

    sample_rows: list[dict[str, Any]] = []
    for sample in samples:
        way, dist_m, way_id = _match_sample(sample, ways, DEBUG_MAX_MATCH_DIST_M if mode == "debug" else FALLBACK_CORRIDOR_RADIUS_M)
        row_warnings: list[str] = []
        if way is None:
            surface_raw = "unknown"
            inferred = "unknown"
            confidence = "unknown"
            tags: dict[str, Any] = {}
            source = "unmatched"
            explanation = "no OSM highway matched within 80 m corridor"
            method = "unmatched"
        else:
            tags = {str(k): v for k, v in (way.get("tags") or {}).items()}
            surface_raw = _canonical_surface(tags.get("surface")) or "unknown"
            inferred, tag_conf, tag_expl = _infer_from_tags(tags)
            dist_conf = _confidence_for_distance(float(dist_m or 9999))
            confidence = min([tag_conf, dist_conf], key=lambda c: {"unknown": 0, "very_low": 1, "low": 2, "medium": 3, "high": 4}.get(c, 0))
            if dist_conf == "very_low":
                row_warnings.append("debug fallback match >80 m; do not treat as normal surface match")
            source = "osm_contextual" if surface_raw == "unknown" else "osm_surface"
            explanation = tag_expl
            method = "osm_tags"

        landcover = _landcover_label(sample.lat, sample.lon, polygons) if polygons else None
        if landcover:
            landcover_used = True
        refined, context_expl, risk_flags, method2, geo_applied = _refine_context(inferred, confidence, tags, landcover, geology_hint)
        if context_expl != "kept OSM-derived surface":
            explanation = f"{explanation}; {context_expl}"
            method = method2
            source = "osm_contextual"

        sample_rows.append({
            "dist_m": sample.dist_m,
            "surface_raw": surface_raw,
            "surface_inferred": inferred,
            "surface_refined": refined,
            "highway": tags.get("highway"),
            "tracktype": tags.get("tracktype"),
            "smoothness": tags.get("smoothness"),
            "landcover": landcover,
            "confidence": confidence,
            "source": source,
            "method": method,
            "match_distance_m": dist_m,
            "way_id": way_id,
            "valhalla_snap_quality": None,
            "risk_flags": risk_flags,
            "warnings": row_warnings,
            "explanation": explanation,
            "geology_hint_applied": geo_applied,
        })

    coverage = sum(1 for row in sample_rows if row["match_distance_m"] is not None and row["match_distance_m"] <= FALLBACK_CORRIDOR_RADIUS_M)
    raw_pct = _percentages(sample_rows, "surface_raw")
    refined_pct = _percentages(sample_rows, "surface_refined")
    confidence_counts = Counter(row["confidence"] for row in sample_rows)
    confidence_breakdown = {k: round(v / max(1, len(sample_rows)) * 100.0, 1) for k, v in confidence_counts.most_common()}
    segments = _merge_samples(sample_rows, dists[-1])

    result = {
        "ok": True,
        "route_id": route_id_str,
        "artifact_path": str(file_path),
        "artifact_sha256": file_sha,
        "engine_version": ENGINE_VERSION,
        "mode": mode,
        "distance_km": round(dists[-1] / 1000.0, 3),
        "point_count": len(points),
        "sample_distance_m": sample_distance_m,
        "sampled_points": len(samples),
        "coverage_pct": round(coverage / max(1, len(samples)) * 100.0, 1),
        "unknown_pct_raw": raw_pct.get("unknown", 0.0),
        "unknown_pct_refined": refined_pct.get("unknown", 0.0),
        "surface_percentages_raw": raw_pct,
        "surface_percentages_refined": refined_pct,
        "confidence_breakdown": confidence_breakdown,
        "geology_context": geology,
        "segments": segments,
        "valhalla": valhalla_info,
        "landcover_used": landcover_used,
        "warnings": warnings,
        "cache_hit": False,
        "cache_path": str(cache_path),
    }
    try:
        cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        result["warnings"].append(f"cache write failed: {exc}")
    return result


def analyze_route_surface_json(**kwargs: Any) -> str:
    return json.dumps(analyze_route_surface(**kwargs), ensure_ascii=False)


def legacy_surface_shape(result: dict[str, Any]) -> dict[str, Any]:
    """Compatibility layer for existing analyze_rwgps_artifact_surface callers."""
    if not result.get("ok"):
        return result
    segs = []
    for seg in result.get("segments") or []:
        segs.append({
            "surface": seg.get("surface_refined") or seg.get("surface_raw") or "unknown",
            "confidence": seg.get("confidence"),
            "distance_m": seg.get("distance_m"),
            "source": seg.get("source"),
            "start_lat": None,
            "start_lon": None,
            "end_lat": None,
            "end_lon": None,
            "km_from": seg.get("km_from"),
            "km_to": seg.get("km_to"),
            "surface_raw": seg.get("surface_raw"),
            "method": seg.get("method"),
            "warnings": seg.get("warnings"),
        })
    out = dict(result)
    out.update({
        "status": "OK",
        "source": "route_surface_engine_v1",
        "surface_percentages": result.get("surface_percentages_refined") or {},
        "dominant_surface": next(iter((result.get("surface_percentages_refined") or {"unknown": 100}).keys())),
        "segments": segs,
        "matched_points": round(result.get("sampled_points", 0) * result.get("coverage_pct", 0) / 100.0),
        "unmatched_points": max(0, int(result.get("sampled_points", 0)) - round(result.get("sampled_points", 0) * result.get("coverage_pct", 0) / 100.0)),
        "confidence": "high" if result.get("coverage_pct", 0) >= 80 else "medium" if result.get("coverage_pct", 0) >= 50 else "low",
    })
    return out
