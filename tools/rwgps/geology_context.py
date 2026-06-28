#!/usr/bin/env python3
"""Fail-open regional geology context for route surface analysis.

2026-06-28 intent: keep geology_context as a stable JSON stage with a real
Europe-wide EGDI provider first, then national enrichment later, and
heuristic_region_v1 as the last fail-open fallback.
"""
from __future__ import annotations

from typing import Any

from tools.rwgps.egdi_geology_provider import get_egdi_geology_context


SAMPLE_STRATEGY = "centroid+bbox+10km_control_points"


REGIONS = [
    {
        "id": "mazowsze_sandy_lowland",
        "label": "Mazowsze / niziny piaszczyste",
        "bbox": (51.0, 19.5, 53.6, 23.5),
        "material_hint": "sand_loose_ground_possible",
        "risk_flags": ["sand_possible", "loose_surface_possible"],
        "explanation": "regional heuristic: Mazowsze lowland context can increase sand/loose ground risk on untagged tracks and paths",
    },
    {
        "id": "swietokrzyskie_rocky_upland",
        "label": "Gory Swietokrzyskie / obszary skaliste",
        "bbox": (50.2, 19.8, 51.4, 21.8),
        "material_hint": "rocky_stony_gravel_possible",
        "risk_flags": ["rocky_possible", "stony_surface_possible"],
        "explanation": "regional heuristic: Swietokrzyskie upland context can increase rocky/stony gravel risk on weakly tagged tracks and paths",
    },
    {
        "id": "tuscany_white_roads",
        "label": "Toskania / white-road context",
        "bbox": (42.2, 9.5, 44.5, 12.5),
        "material_hint": "compacted_gravel_white_road_possible",
        "risk_flags": ["loose_gravel_possible", "dusty_hardpack_possible"],
        "explanation": "regional heuristic: Tuscany rural white-road context can increase compacted gravel and dusty hardpack risk",
    },
    {
        "id": "andalusia_dry_hills",
        "label": "Andaluzja / dry hills",
        "bbox": (35.8, -7.6, 38.8, -1.5),
        "material_hint": "hardpack_loose_gravel_rocky_possible",
        "risk_flags": ["loose_gravel_possible", "rocky_possible", "dry_hardpack_possible"],
        "explanation": "regional heuristic: Andalusia dry-hill context can increase hardpack, loose gravel, and rocky risk",
    },
]


def _point(sample: Any) -> tuple[float, float, float]:
    return float(getattr(sample, "lat")), float(getattr(sample, "lon")), float(getattr(sample, "dist_m", 0.0) or 0.0)


def _bbox(points: list[tuple[float, float, float]]) -> tuple[float, float, float, float] | None:
    if not points:
        return None
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return min(lats), min(lons), max(lats), max(lons)


def _centroid(points: list[tuple[float, float, float]]) -> tuple[float, float] | None:
    if not points:
        return None
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def _control_points(points: list[tuple[float, float, float]], interval_m: float = 10000.0) -> list[dict[str, float]]:
    if not points:
        return []
    controls: list[tuple[float, float, float]] = [points[0]]
    total_m = points[-1][2]
    if total_m <= interval_m:
        controls.append(points[-1])
    else:
        target = interval_m
        idx = 0
        while target < total_m:
            while idx + 1 < len(points) and points[idx][2] < target:
                idx += 1
            controls.append(points[min(idx, len(points) - 1)])
            target += interval_m
        controls.append(points[-1])
    dedup: list[tuple[float, float, float]] = []
    seen: set[tuple[int, int, int]] = set()
    for lat, lon, dist_m in controls:
        key = (round(lat * 1_000_000), round(lon * 1_000_000), round(dist_m))
        if key in seen:
            continue
        seen.add(key)
        dedup.append((lat, lon, dist_m))
    return [{"lat": round(lat, 7), "lon": round(lon, 7), "km": round(dist_m / 1000.0, 3)} for lat, lon, dist_m in dedup]


def _bbox_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    south, west, north, east = a
    bs, bw, bn, be = b
    return not (north < bs or south > bn or east < bw or west > be)


def _point_in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    south, west, north, east = bbox
    return south <= lat <= north and west <= lon <= east


def _empty_context(enabled: bool, status: str, warning: str | None = None) -> dict[str, Any]:
    warnings = [warning] if warning else []
    return {
        "enabled": bool(enabled),
        "status": status,
        "provider": None,
        "dominant_region": None,
        "dominant_unit": None,
        "units": [],
        "sections": [],
        "material_hint": "unknown",
        "confidence": "unknown",
        "source_resolution": None,
        "sample_strategy": SAMPLE_STRATEGY,
        "explanation": None,
        "warnings": warnings,
        "provider_chain": ["egdi", "national_provider_stub", "heuristic_region_v1"],
    }


def _heuristic_context(samples: list[Any], enabled: bool = True, warnings: list[str] | None = None) -> dict[str, Any]:
    if not enabled:
        return _empty_context(False, "DISABLED")
    warnings = list(warnings or [])
    points = [_point(sample) for sample in samples]
    route_bbox = _bbox(points)
    route_centroid = _centroid(points)
    controls = _control_points(points)
    if route_bbox is None or route_centroid is None:
        return _empty_context(True, "UNAVAILABLE", "no route points available for geology heuristic")

    centroid_lat, centroid_lon = route_centroid
    matched: list[dict[str, Any]] = []
    for region in REGIONS:
        bbox = region["bbox"]
        if _point_in_bbox(centroid_lat, centroid_lon, bbox) or _bbox_intersects(route_bbox, bbox):
            matched.append(region)

    if not matched:
        context = _empty_context(True, "WARN", "no heuristic geology region matched")
        context.update({
            "provider": "heuristic_region_v1",
            "source_resolution": "regional_heuristic",
            "explanation": "no EGDI feature matched, using regional heuristic fallback",
            "route_bbox": {
                "south": round(route_bbox[0], 7),
                "west": round(route_bbox[1], 7),
                "north": round(route_bbox[2], 7),
                "east": round(route_bbox[3], 7),
            },
            "centroid": {"lat": round(centroid_lat, 7), "lon": round(centroid_lon, 7)},
            "control_points": controls,
            "warnings": warnings,
        })
        return context

    dominant = matched[0]
    return {
        "enabled": True,
        "status": "OK",
        "provider": "heuristic_region_v1",
        "dominant_region": dominant["id"],
        "dominant_unit": dominant["label"],
        "units": [
            {
                "region": region["id"],
                "label": region["label"],
                "material_hint": region["material_hint"],
                "confidence": "medium",
            }
            for region in matched
        ],
        "sections": [],
        "material_hint": dominant["material_hint"],
        "confidence": "medium",
        "source_resolution": "regional_heuristic",
        "sample_strategy": SAMPLE_STRATEGY,
        "explanation": dominant["explanation"],
        "warnings": warnings,
        "provider_chain": ["egdi", "national_provider_stub", "heuristic_region_v1"],
        "route_bbox": {
            "south": round(route_bbox[0], 7),
            "west": round(route_bbox[1], 7),
            "north": round(route_bbox[2], 7),
            "east": round(route_bbox[3], 7),
        },
        "centroid": {"lat": round(centroid_lat, 7), "lon": round(centroid_lon, 7)},
        "control_points": controls,
    }


def _egdi_probe_points(points: list[tuple[float, float, float]], controls: list[dict[str, float]], centroid: tuple[float, float]) -> list[dict[str, float]]:
    probe_points: list[dict[str, float]] = []
    seen: set[tuple[int, int]] = set()

    def add(lat: float, lon: float) -> None:
        key = (round(lat * 1_000_000), round(lon * 1_000_000))
        if key in seen:
            return
        seen.add(key)
        probe_points.append({"lat": round(lat, 7), "lon": round(lon, 7)})

    add(centroid[0], centroid[1])
    if points:
        add(points[0][0], points[0][1])
        add(points[-1][0], points[-1][1])
    for control in controls:
        add(float(control["lat"]), float(control["lon"]))
    return probe_points


def _egdi_context_context(egdi: dict[str, Any], route_bbox: tuple[float, float, float, float], route_centroid: tuple[float, float], controls: list[dict[str, float]]) -> dict[str, Any]:
    warnings = [str(w) for w in egdi.get("warnings") or []]
    confidence = str(egdi.get("confidence") or "unknown")
    if confidence in {"low", "unknown"}:
        warnings.append("EGDI confidence is low; regional hint only")
    if egdi.get("status") == "WARN":
        warnings.append("EGDI returned WARN; keeping it as best available Europe-wide hint")

    context = {
        "enabled": True,
        "status": "OK",
        "provider": "egdi",
        "dominant_region": "egdi_pan_european_surface_geology",
        "dominant_unit": egdi.get("dominant_unit"),
        "units": egdi.get("units", []),
        "sections": [],
        "material_hint": str(egdi.get("material_hint") or "unknown"),
        "confidence": confidence,
        "source_resolution": egdi.get("source_resolution") or "EGDI 1:1M pan-European surface geology",
        "sample_strategy": egdi.get("sample_strategy") or SAMPLE_STRATEGY,
        "explanation": f"EGDI pan-European surface geology hint: {egdi.get('material_hint') or 'unknown'}",
        "warnings": warnings,
        "provider_chain": ["egdi", "national_provider_stub", "heuristic_region_v1"],
        "route_bbox": {
            "south": round(route_bbox[0], 7),
            "west": round(route_bbox[1], 7),
            "north": round(route_bbox[2], 7),
            "east": round(route_bbox[3], 7),
        },
        "centroid": {"lat": round(route_centroid[0], 7), "lon": round(route_centroid[1], 7)},
        "control_points": controls,
    }
    return context


def build_geology_context(samples: list[Any], enabled: bool = True) -> dict[str, Any]:
    if not enabled:
        return _empty_context(False, "DISABLED")
    points = [_point(sample) for sample in samples]
    route_bbox = _bbox(points)
    route_centroid = _centroid(points)
    controls = _control_points(points)
    if route_bbox is None or route_centroid is None:
        return _empty_context(True, "UNAVAILABLE", "no route points available for geology heuristic")

    egdi_points = _egdi_probe_points(points, controls, route_centroid)
    try:
        egdi = get_egdi_geology_context(egdi_points, bbox=route_bbox, timeout_sec=10)
    except Exception as exc:
        egdi = {
            "provider": "egdi",
            "status": "UNAVAILABLE",
            "dominant_unit": None,
            "units": [],
            "material_hint": "unknown",
            "confidence": "unknown",
            "source_resolution": None,
            "sample_strategy": SAMPLE_STRATEGY,
            "raw_provider": {"endpoint": None, "layer": None, "method": None},
            "warnings": [f"EGDI provider failed open: {exc}"],
        }

    if str(egdi.get("status") or "").upper() == "OK":
        return _egdi_context_context(egdi, route_bbox, route_centroid, controls)

    fallback_warnings = [f"EGDI unavailable; using heuristic_region_v1 fallback ({egdi.get('status')})"]
    fallback_warnings.extend(str(w) for w in egdi.get("warnings") or [])
    return _heuristic_context(samples, enabled=True, warnings=fallback_warnings)


def risk_flags_for_segment(context: dict[str, Any], row: dict[str, Any]) -> list[str]:
    if not context.get("enabled") or context.get("status") not in {"OK", "WARN"}:
        return []
    if context.get("provider") not in {"heuristic_region_v1", "egdi"}:
        return []
    material_hint = str(context.get("material_hint") or "unknown")
    if material_hint == "unknown":
        return []

    raw_surface = str(row.get("surface_raw") or "unknown")
    refined = str(row.get("surface_refined") or "unknown")
    highway = str(row.get("highway") or "")
    confidence = str(row.get("confidence") or "")
    classification_source = str(row.get("classification_source") or "")

    if raw_surface in {"asphalt", "concrete", "paving_stones"}:
        return []
    candidate_surface = refined in {"unknown", "ground", "dirt", "grass", "sand", "loose", "rocky", "stony", "gravel", "fine_gravel", "compacted"}
    candidate_source = classification_source in {"unknown", "inferred_highway", "inferred_tracktype", "inferred_landcover", "inferred_service_default"}
    candidate_highway = highway in {"track", "path", "footway", "bridleway"}
    candidate_conf = confidence in {"unknown", "very_low", "low"}
    if not (candidate_surface and (candidate_source or candidate_highway or candidate_conf)):
        return []

    hint = material_hint.lower()
    if hint in {"sand_loose_ground_possible", "sand_loose_sand_possible"} or hint.startswith("sand") or hint == "alluvial_loose_wet_possible":
        return ["sand_possible", "loose_surface_possible"]
    if hint in {"clay_mud_possible"} or "clay" in hint or "mud" in hint or "marl" in hint:
        return ["mud_possible"]
    if hint in {"rocky_stony_gravel_possible", "limestone_hardpack_white_gravel_possible", "granite_stony_hardpack_possible", "volcanic_stony_hardpack_possible", "sandstone_gravel_rocky_possible"} or "limestone" in hint or "carbonate" in hint or "granite" in hint or "volcan" in hint or "sandstone" in hint or "gravel" in hint:
        return ["rocky_possible", "stony_surface_possible"]
    if hint == "compacted_gravel_white_road_possible":
        return ["loose_gravel_possible", "dusty_hardpack_possible"]
    if hint == "hardpack_loose_gravel_rocky_possible":
        return ["loose_gravel_possible", "rocky_possible", "dry_hardpack_possible"]
    return []
