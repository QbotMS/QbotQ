#!/usr/bin/env python3
"""Minimal EGDI geology provider prototype for Europe.

This module is intentionally isolated from route_surface_engine. It probes the
EGDI pan-European surface geology WMS using JSON GetFeatureInfo and fails open
on any transport or parsing issue.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import Any

import requests


EGDI_WMS_URL = "https://geoserver.geo-zs.si/egdi-surface-geology/gsmlp/wms"
EGDI_SAMPLE_STRATEGY = "centroid+bbox+10km_control_points"
EGDI_PRIMARY_LAYER = "GeologicUnitView_Lithology"
EGDI_FALLBACK_LAYER = "GeologicUnitView_Age"

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; QBot/1.0; +https://qbot.local)",
})


def _point_from_any(point: Any) -> tuple[float, float]:
    if isinstance(point, dict):
        lat = point.get("lat", point.get("latitude"))
        lon = point.get("lon", point.get("lng", point.get("longitude")))
    elif isinstance(point, (tuple, list)) and len(point) >= 2:
        lat, lon = point[0], point[1]
    else:
        lat = getattr(point, "lat", getattr(point, "latitude", None))
        lon = getattr(point, "lon", getattr(point, "lng", getattr(point, "longitude", None)))
    if lat is None or lon is None:
        raise ValueError("point must expose lat/lon coordinates")
    return float(lat), float(lon)


def _bbox_from_points(points: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    if not points:
        return None
    lats = [lat for lat, _ in points]
    lons = [lon for _, lon in points]
    return min(lats), min(lons), max(lats), max(lons)


def _window_delta(bbox: tuple[float, float, float, float] | None) -> float:
    if bbox is None:
        return 0.05
    south, west, north, east = bbox
    lat_span = abs(north - south)
    lon_span = abs(east - west)
    span = max(lat_span, lon_span)
    return max(0.02, min(0.15, span * 0.02 if span else 0.05))


def _point_window(lat: float, lon: float, bbox: tuple[float, float, float, float] | None) -> str:
    delta = _window_delta(bbox)
    return f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"


@lru_cache(maxsize=4096)
def _get_feature_info_cached(layer: str, bbox: str, timeout_sec: int) -> dict[str, Any]:
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": layer,
        "QUERY_LAYERS": layer,
        "CRS": "CRS:84",
        "BBOX": bbox,
        "WIDTH": "101",
        "HEIGHT": "101",
        "I": "50",
        "J": "50",
        "INFO_FORMAT": "application/json",
    }
    response = _SESSION.get(EGDI_WMS_URL, params=params, timeout=timeout_sec)
    response.raise_for_status()
    return response.json()


def _extract_features(payload: dict[str, Any]) -> list[dict[str, Any]]:
    feats = payload.get("features")
    return feats if isinstance(feats, list) else []


def _extract_feature_payload(feature: dict[str, Any], point_idx: int, point_lat: float, point_lon: float, layer: str) -> dict[str, Any]:
    props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    lithology = str(props.get("lithology") or props.get("representativeLithology_uri") or "").strip()
    name = str(props.get("name") or "").strip()
    age_uri = str(props.get("representativeAge_uri") or "").strip()
    source = str(props.get("source") or "").strip()
    material_hint = normalize_material_hint(" ".join([lithology, name, age_uri, source]))
    return {
        "point_index": point_idx,
        "point": {"lat": round(point_lat, 7), "lon": round(point_lon, 7)},
        "feature_id": feature.get("id"),
        "name": name or None,
        "lithology": lithology or None,
        "formation": name or None,
        "age": age_uri or None,
        "description": props.get("description"),
        "source": source or None,
        "scale": "1:1M",
        "material_hint": material_hint,
        "layer": layer,
        "metadata_uri": props.get("metadata_uri"),
        "specification_uri": props.get("specification_uri"),
    }


def normalize_material_hint(text: str | None) -> str:
    value = (text or "").lower()
    if not value:
        return "unknown"
    if "sandstone" in value or "gravel" in value:
        return "sandstone_gravel_rocky_possible"
    if "sand" in value:
        return "sand_loose_sand_possible"
    if "clay" in value or "mud" in value or "marl" in value or "silt" in value:
        return "clay_mud_possible"
    if "limestone" in value or "carbonate" in value or "dolomite" in value or "chalk" in value:
        return "limestone_hardpack_white_gravel_possible"
    if "alluvial" in value or "alluv" in value or "fluvial" in value:
        return "alluvial_loose_wet_possible"
    if "granite" in value or "gneiss" in value or "basalt" in value or "volcan" in value:
        return "granite_stony_hardpack_possible" if "granite" in value or "gneiss" in value else "volcanic_stony_hardpack_possible"
    if "clastic" in value or "sedimentary" in value:
        return "mixed"
    if any(token in value for token in ["mixed", "undiff", "unknown", "not specified"]):
        return "mixed"
    return "unknown"


def _pick_dominant(units: list[dict[str, Any]]) -> tuple[str | None, str]:
    if not units:
        return None, "unknown"
    counts = Counter(unit.get("material_hint", "unknown") for unit in units if unit.get("material_hint"))
    dominant_hint = counts.most_common(1)[0][0] if counts else "unknown"
    dominant_units = [u for u in units if u.get("material_hint") == dominant_hint]
    if dominant_units:
        name_counts = Counter(str(u.get("name") or u.get("feature_id")) for u in dominant_units)
        dominant_unit = name_counts.most_common(1)[0][0]
    else:
        name_counts = Counter(str(u.get("name") or u.get("feature_id")) for u in units)
        dominant_unit = name_counts.most_common(1)[0][0]
    return dominant_unit, dominant_hint


def _confidence_for(units: list[dict[str, Any]], warnings: list[str]) -> str:
    if not units:
        return "unknown"
    if len(units) == 1:
        return "low"
    hints = Counter(unit.get("material_hint", "unknown") for unit in units if unit.get("material_hint"))
    if not hints:
        return "low"
    dominant, count = hints.most_common(1)[0]
    if dominant == "unknown":
        return "low"
    if count >= 3 and not warnings:
        return "high"
    return "medium"


def _status_for(units: list[dict[str, Any]], warnings: list[str]) -> str:
    if units and not warnings:
        return "OK"
    if units:
        return "WARN"
    return "UNAVAILABLE"


def get_egdi_geology_context(points: list[Any], bbox: tuple[float, float, float, float] | None = None, timeout_sec: int = 10) -> dict[str, Any]:
    """Return a fail-open EGDI geology context for a route."""
    try:
        normalized_points = [_point_from_any(point) for point in points]
    except Exception as exc:
        return {
            "provider": "egdi",
            "status": "UNAVAILABLE",
            "dominant_unit": None,
            "units": [],
            "material_hint": "unknown",
            "confidence": "unknown",
            "source_resolution": None,
            "sample_strategy": EGDI_SAMPLE_STRATEGY,
            "raw_provider": {"endpoint": EGDI_WMS_URL, "layer": EGDI_PRIMARY_LAYER, "method": "WMS.GetFeatureInfo(application/json)"},
            "warnings": [f"invalid input points: {exc}"],
        }

    route_bbox = bbox if bbox is not None else _bbox_from_points(normalized_points)
    units: list[dict[str, Any]] = []
    warnings: list[str] = []
    methods_seen: set[str] = set()
    endpoint = EGDI_WMS_URL

    for idx, (lat, lon) in enumerate(normalized_points):
        point_bbox = _point_window(lat, lon, route_bbox)
        feature_payload = None
        used_layer = None
        for layer in (EGDI_PRIMARY_LAYER, EGDI_FALLBACK_LAYER):
            try:
                payload = _get_feature_info_cached(layer, point_bbox, int(timeout_sec))
                features = _extract_features(payload)
                if features:
                    feature_payload = (payload, features)
                    used_layer = layer
                    methods_seen.add("WMS.GetFeatureInfo(application/json)")
                    break
            except Exception as exc:
                warnings.append(f"{layer} failed at point {idx}: {exc}")
                continue

        if feature_payload is None:
            warnings.append(f"no EGDI feature returned at point {idx}")
            continue

        _, features = feature_payload
        for feature in features[:3]:
            units.append(_extract_feature_payload(feature, idx, lat, lon, used_layer or EGDI_PRIMARY_LAYER))

    dominant_unit, dominant_hint = _pick_dominant(units)
    if units and any(unit.get("material_hint") == "unknown" for unit in units):
        warnings.append("some EGDI features had no usable lithology string")

    status = _status_for(units, warnings)
    confidence = _confidence_for(units, warnings)
    if not units:
        source_resolution = None
    else:
        source_resolution = "EGDI 1:1M pan-European surface geology"

    return {
        "provider": "egdi",
        "status": status,
        "dominant_unit": dominant_unit,
        "units": units,
        "material_hint": dominant_hint,
        "confidence": confidence,
        "source_resolution": source_resolution,
        "sample_strategy": EGDI_SAMPLE_STRATEGY,
        "raw_provider": {
            "endpoint": endpoint,
            "layer": EGDI_PRIMARY_LAYER if units else EGDI_FALLBACK_LAYER,
            "method": "WMS.GetFeatureInfo(application/json)" if "WMS.GetFeatureInfo(application/json)" in methods_seen else None,
        },
        "warnings": warnings,
    }
