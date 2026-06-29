#!/usr/bin/env python3
"""Lokalny parser tras GPX/JSON dla QBot.

Parsuje geometrię lokalnie - nie wysyła pełnych danych do LLM.
Dla zadanych kilometrów wylicza punkty na śladzie i sprawdza noclegi przez Nominatim.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

ARTIFACTS_ROOT = Path("/opt/qbot/artifacts")
NOMINATIM_URL = "https://nominatim.openstreetmap.org"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
GOOGLE_PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
OVERPASS_URLS = [
    OVERPASS_URL,
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
USER_AGENT = "QBot/1.0 (personal assistant; michal@qbot)"
GOOGLE_SUPPLY_TYPES = [
    "supermarket",
    "grocery_store",
    "convenience_store",
    "bakery",
    "restaurant",
    "cafe",
    "bar",
]
GOOGLE_HARD_TYPES = {"supermarket", "grocery_store", "convenience_store", "bakery"}
GOOGLE_SOFT_TYPES = {"restaurant", "cafe", "bar"}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Odległość między dwoma punktami w km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _extract_geojson_coordinates(data: dict[str, Any]) -> list[list[float]]:
    """Wydobądź listę współrzędnych z geojson w pliku RWGPS."""
    candidates = [
        data.get("geometry", {}),
        data.get("route", {}).get("geometry", {}),
    ]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        geojson = candidate.get("geojson")
        if isinstance(geojson, dict):
            coords = geojson.get("coordinates")
            if isinstance(coords, list) and coords:
                return coords
        coords = candidate.get("coordinates")
        if isinstance(coords, list) and coords:
            return coords
        samples = candidate.get("samples")
        if isinstance(samples, dict):
            first = samples.get("first")
            if isinstance(first, list) and first:
                return [first]
    return []


def _load_track_points(route_id: int) -> list[dict]:
    """Wczytaj punkty śladu z lokalnego JSON.

    Zwraca listę dict: {lat, lon, ele, cum_km}
    """
    json_path = ARTIFACTS_ROOT / "exports" / "rwgps" / f"rwgps_{route_id}.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Brak pliku: {json_path}")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    raw_points = _extract_geojson_coordinates(data)
    if not raw_points:
        raw_points = data.get("track_points") or data.get("route", {}).get("track_points") or []

    if not raw_points:
        raise ValueError(f"Brak punktów śladu w pliku rwgps_{route_id}.json")

    points = []
    cum_km = 0.0
    prev = None

    for p in raw_points:
        lat = lon = ele = None
        if isinstance(p, dict):
            lat = p.get("y") or p.get("lat") or p.get("latitude")
            lon = p.get("x") or p.get("lon") or p.get("lng") or p.get("longitude")
            ele = p.get("e") or p.get("ele") or p.get("elevation")
        elif isinstance(p, (list, tuple)):
            if len(p) >= 2:
                lon, lat = p[0], p[1]
            if len(p) >= 3:
                ele = p[2]
        if lat is None or lon is None:
            continue

        lat = float(lat)
        lon = float(lon)
        if prev:
            cum_km += _haversine_km(prev["lat"], prev["lon"], lat, lon)

        point = {
            "lat": lat,
            "lon": lon,
            "ele": float(ele) if ele is not None else None,
            "cum_km": cum_km,
        }
        points.append(point)
        prev = point

    if not points:
        raise ValueError(f"Brak poprawnych punktów śladu w pliku rwgps_{route_id}.json")
    return points


def _find_point_at_km(points: list[dict], target_km: float) -> dict:
    """Znajdź punkt na śladzie dla zadanego kilometra."""
    if target_km <= 0:
        p = points[0]
        return {**p, "on_track": True, "nearest_km": 0.0}
    if target_km >= points[-1]["cum_km"]:
        p = points[-1]
        return {**p, "on_track": True, "nearest_km": round(points[-1]["cum_km"], 3)}

    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if a["cum_km"] <= target_km <= b["cum_km"]:
            if b["cum_km"] == a["cum_km"]:
                return {**a, "on_track": True, "nearest_km": round(a["cum_km"], 3)}
            t = (target_km - a["cum_km"]) / (b["cum_km"] - a["cum_km"])
            lat = a["lat"] + t * (b["lat"] - a["lat"])
            lon = a["lon"] + t * (b["lon"] - a["lon"])
            ele = None
            if a["ele"] is not None and b["ele"] is not None:
                ele = round(a["ele"] + t * (b["ele"] - a["ele"]), 1)
            return {
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "ele": ele,
                "cum_km": round(target_km, 3),
                "on_track": True,
            }

    return {**points[-1], "on_track": False, "nearest_km": round(points[-1]["cum_km"], 3)}


def _nominatim_reverse(lat: float, lon: float) -> dict:
    """Odwrotne geokodowanie przez Nominatim."""
    try:
        import urllib.request

        url = f"{NOMINATIM_URL}/reverse?lat={lat}&lon={lon}&format=json&zoom=10&addressdetails=1"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        addr = data.get("address", {})
        town = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("hamlet")
            or addr.get("municipality")
            or "nieznana"
        )
        return {
            "town": town,
            "country": addr.get("country", ""),
            "display": data.get("display_name", "")[:80],
        }
    except Exception as exc:
        return {"town": "UNKNOWN", "error": str(exc)[:100]}


def _overpass_lodging(lat: float, lon: float, radius_km: float = 5.0) -> dict:
    """Sprawdź noclegi przez Overpass API."""
    radius_m = int(radius_km * 1000)
    query = f"""
[out:json][timeout:10];
(
  node["tourism"~"hotel|guest_house|hostel|apartment|motel|resort"](around:{radius_m},{lat},{lon});
  way["tourism"~"hotel|guest_house|hostel|apartment|motel|resort"](around:{radius_m},{lat},{lon});
  node["tourism"="camp_site"](around:{radius_m},{lat},{lon});
  node["tourism"="alpine_hut"](around:{radius_m},{lat},{lon});
);
out count;
"""
    try:
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode({"data": query}).encode()
        req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=12) as resp:
            result = json.loads(resp.read())

        elements = result.get("elements", [])
        total = 0
        for element in elements:
            if element.get("type") == "count":
                tags = element.get("tags", {})
                for key in ("nodes", "ways", "relations", "total"):
                    try:
                        total += int(tags.get(key, 0))
                    except (TypeError, ValueError):
                        continue
        if total == 0:
            total = len([e for e in elements if e.get("type") != "count"])

        if total >= 5:
            status = "OK"
        elif total >= 1:
            status = "WEAK"
        else:
            status = "MISSING"

        return {"lodging_count": total, "lodging_status": status, "radius_km": radius_km}
    except Exception as exc:
        return {"lodging_count": None, "lodging_status": "UNKNOWN", "error": str(exc)[:100]}


def analyze_stage_endpoints(
    route_id: int,
    stage_km: list[float],
    lodging_radius_km: float = 5.0,
    check_lodging: bool = True,
) -> dict[str, Any]:
    """Główna funkcja: analizuje końcówki etapów dla podanych kilometrów."""
    try:
        points = _load_track_points(route_id)
    except (FileNotFoundError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}

    total_km = round(points[-1]["cum_km"], 3)
    endpoints = []

    for i, km in enumerate(stage_km, 1):
        pt = _find_point_at_km(points, km)
        endpoint = {
            "stage": i,
            "target_km": km,
            "actual_km": pt["cum_km"],
            "lat": pt["lat"],
            "lon": pt["lon"],
            "elevation_m": pt.get("ele"),
            "on_track": pt.get("on_track", False),
        }

        geo = _nominatim_reverse(pt["lat"], pt["lon"])
        endpoint["town"] = geo.get("town", "UNKNOWN")
        endpoint["location"] = geo.get("display", "")
        time.sleep(1.1)

        if check_lodging:
            lodging = _overpass_lodging(pt["lat"], pt["lon"], lodging_radius_km)
            endpoint["lodging_count"] = lodging.get("lodging_count")
            endpoint["lodging_status"] = lodging.get("lodging_status", "UNKNOWN")
            if "error" in lodging:
                endpoint["lodging_note"] = lodging["error"]
            time.sleep(0.5)
        else:
            endpoint["lodging_status"] = "UNCHECKED"

        endpoints.append(endpoint)

    return {
        "status": "OK",
        "route_id": route_id,
        "route_total_km": total_km,
        "track_points_count": len(points),
        "stage_count": len(endpoints),
        "lodging_radius_km": lodging_radius_km,
        "endpoints": endpoints,
    }


def _parse_gpx_file_detailed(file_path: Path) -> list[dict]:
    """Parse GPX file into list of {lat, lon, ele, cum_km}."""
    import xml.etree.ElementTree as ET

    points: list[dict] = []
    ns = "http://www.topografix.com/GPX/1/1"
    tree = ET.parse(str(file_path))
    root = tree.getroot()

    for trkpt in root.iter(f"{{{ns}}}trkpt"):
        lat = trkpt.get("lat")
        lon = trkpt.get("lon")
        if lat is None or lon is None:
            continue
        ele_el = trkpt.find(f"{{{ns}}}ele")
        ele = float(ele_el.text) if ele_el is not None and ele_el.text else None
        try:
            points.append({"lat": float(lat), "lon": float(lon), "ele": ele})
        except (TypeError, ValueError):
            continue

    if not points:
        return []

    # add cumulative distance
    result = []
    cum_km = 0.0
    prev = None
    for p in points:
        if prev:
            cum_km += _haversine_km(prev["lat"], prev["lon"], p["lat"], p["lon"])
        result.append({**p, "cum_km": round(cum_km, 4)})
        prev = p
    return result


def analyze_stage_gpx(file_path: str) -> dict:
    """Analyze a local GPX stage file and return full profile data.

    Returns:
        distance_km, elevation_gain_m, elevation_loss_m, min/max elevation,
        profile_5km (elevation at 5km intervals), climbs, descents.
    """
    path = Path(file_path)
    if not path.exists():
        return {"status": "ERROR", "error": f"File not found: {file_path}"}

    points = _parse_gpx_file_detailed(path)
    if not points:
        return {"status": "ERROR", "error": f"No track points in {file_path}"}

    total_km = points[-1]["cum_km"]
    elevations = [p["ele"] for p in points if p["ele"] is not None]

    # Elevation gain/loss
    gain = 0.0
    loss = 0.0
    for i in range(1, len(elevations)):
        delta = elevations[i] - elevations[i - 1]
        if delta > 0:
            gain += delta
        elif delta < 0:
            loss += abs(delta)

    min_ele = min(elevations) if elevations else None
    max_ele = max(elevations) if elevations else None

    # Profile at 5km intervals
    profile_5km = []
    for km in range(0, int(total_km) + 1, 5):
        pt = _find_point_at_km(points, float(km))
        profile_5km.append({
            "km": km,
            "elevation_m": pt.get("ele"),
            "lat": pt["lat"],
            "lon": pt["lon"],
        })

    # Detect climbs (≥30m gain, ≥1km length) and descents
    # Uses running accumulator with hysteresis — only switches direction
    # when cumulative elevation change exceeds HYST_M (avoids toggling on
    # every small gpx fluctuation).
    HYST_M = 5.0
    climbs = []
    descents = []
    seg_start = 0
    seg_base_ele = points[0]["ele"]
    seg_direction = 0  # +1 climbing, -1 descending, 0 flat

    def _emit_climb(s, e, base, top):
        seg_len = points[e]["cum_km"] - points[s]["cum_km"]
        rise = top - base
        if rise >= 30 and seg_len >= 1.0:
            climbs.append({
                "start_km": round(points[s]["cum_km"], 2),
                "end_km": round(points[e]["cum_km"], 2),
                "length_km": round(seg_len, 2),
                "rise_m": round(rise, 1),
                "avg_gradient_pct": round(rise / max(seg_len * 1000, 1) * 100, 1),
            })

    def _emit_descent(s, e, base, bottom):
        seg_len = points[e]["cum_km"] - points[s]["cum_km"]
        drop = base - bottom
        if drop >= 30 and seg_len >= 1.0:
            descents.append({
                "start_km": round(points[s]["cum_km"], 2),
                "end_km": round(points[e]["cum_km"], 2),
                "length_km": round(seg_len, 2),
                "drop_m": round(drop, 1),
                "avg_gradient_pct": round(drop / max(seg_len * 1000, 1) * 100, 1),
            })

    for i in range(1, len(points)):
        p = points[i]
        if p["ele"] is None:
            continue
        delta = p["ele"] - points[i - 1]["ele"]

        if seg_direction == 0:
            seg_direction = 1 if delta > 0 else (-1 if delta < 0 else 0)
            seg_start = i - 1
            seg_base_ele = points[i - 1]["ele"]

        elif seg_direction == 1:  # climbing
            cum_rise = p["ele"] - seg_base_ele
            if delta >= 0:
                continue  # still climbing
            if cum_rise - abs(delta) > HYST_M:
                # small dip — ignore, keep climbing
                continue
            # significant enough down — end climb, start descent
            _emit_climb(seg_start, i - 1, seg_base_ele,
                        max(points[s]["ele"] for s in range(seg_start, i) if points[s]["ele"] is not None))
            seg_direction = -1
            seg_start = i - 1
            seg_base_ele = points[i - 1]["ele"]

        elif seg_direction == -1:  # descending
            cum_drop = seg_base_ele - (p["ele"] or 0)
            if delta <= 0:
                continue  # still descending
            if cum_drop - delta > HYST_M:
                # small bump — ignore, keep descending
                continue
            # significant enough up — end descent, start climb
            _emit_descent(seg_start, i - 1, seg_base_ele,
                          min(points[s]["ele"] for s in range(seg_start, i) if points[s]["ele"] is not None))
            seg_direction = 1
            seg_start = i - 1
            seg_base_ele = points[i - 1]["ele"]

    # Flush last segment
    last = len(points) - 1
    if seg_direction == 1:
        _emit_climb(seg_start, last, seg_base_ele,
                    max(points[s]["ele"] for s in range(seg_start, last + 1) if points[s]["ele"] is not None))
    elif seg_direction == -1:
        _emit_descent(seg_start, last, seg_base_ele,
                      min(points[s]["ele"] for s in range(seg_start, last + 1) if points[s]["ele"] is not None))

    # Max grade (wygladzone okno ~100m, redukcja szumu GPS)
    max_grade_pct = None
    if len(points) >= 2:
        _win_m = 100.0
        _j = 0
        _best = 0.0
        for _i in range(len(points)):
            if points[_i]["ele"] is None:
                continue
            if _j < _i:
                _j = _i
            while _j < len(points) - 1 and (points[_j]["cum_km"] - points[_i]["cum_km"]) * 1000.0 < _win_m:
                _j += 1
            if _j <= _i or points[_j]["ele"] is None:
                continue
            _dist_m = (points[_j]["cum_km"] - points[_i]["cum_km"]) * 1000.0
            if _dist_m <= 0:
                continue
            _g = (points[_j]["ele"] - points[_i]["ele"]) / _dist_m * 100.0
            if _g > _best:
                _best = _g
        max_grade_pct = round(_best, 1)

    return {
        "status": "OK",
        "file_path": str(path),
        "filename": path.name,
        "track_points": len(points),
        "distance_km": round(total_km, 3),
        "elevation_gain_m": round(gain, 1),
        "elevation_loss_m": round(loss, 1),
        "min_elevation_m": round(min_ele, 1) if min_ele is not None else None,
        "max_elevation_m": round(max_ele, 1) if max_ele is not None else None,
        "start_elevation_m": round(points[0]["ele"], 1) if points[0]["ele"] is not None else None,
        "end_elevation_m": round(points[-1]["ele"], 1) if points[-1]["ele"] is not None else None,
        "profile_5km": profile_5km,
        "max_grade_pct": max_grade_pct,
        "max_grade_window_m": 100,
        "climbs": climbs,
        "descents": descents,
    }


def _project_xy(lat: float, lon: float, ref_lat: float) -> tuple[float, float]:
    """Approximate WGS84 -> local meters using an equirectangular projection."""
    lat_m = 111_320.0
    lon_m = 111_320.0 * math.cos(math.radians(ref_lat))
    return lon * lon_m, lat * lat_m


def _point_to_segment_distance_m(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> tuple[float, float]:
    """Return distance from point to segment plus interpolation factor t."""
    vx = bx - ax
    vy = by - ay
    wx = px - ax
    wy = py - ay
    seg_len2 = vx * vx + vy * vy
    if seg_len2 <= 0:
        dist = math.hypot(px - ax, py - ay)
        return dist, 0.0
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / seg_len2))
    nx = ax + t * vx
    ny = ay + t * vy
    return math.hypot(px - nx, py - ny), t


def _track_projection(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not points:
        return []
    ref_lat = sum(float(p["lat"]) for p in points) / len(points)
    projected: list[dict[str, Any]] = []
    cum_m = 0.0
    prev = None
    for point in points:
        lat = float(point["lat"])
        lon = float(point["lon"])
        x, y = _project_xy(lat, lon, ref_lat)
        if prev is not None:
            cum_m += _haversine_km(prev["lat"], prev["lon"], lat, lon) * 1000.0
        projected.append({
            "lat": lat,
            "lon": lon,
            "ele": point.get("ele"),
            "cum_m": cum_m,
            "x": x,
            "y": y,
        })
        prev = projected[-1]
    return projected


def _track_segment_projection(
    track: list[dict[str, Any]],
    km_from: float,
    km_to: float,
) -> list[dict[str, Any]]:
    if not track:
        return []
    start_m = max(0.0, float(km_from) * 1000.0)
    end_m = max(start_m, float(km_to) * 1000.0)
    segment: list[dict[str, Any]] = []
    if start_m <= 0.0:
        segment.append(dict(track[0]))
    for idx in range(len(track) - 1):
        a = track[idx]
        b = track[idx + 1]
        a_m = float(a["cum_m"])
        b_m = float(b["cum_m"])
        if b_m < start_m or a_m > end_m:
            continue
        if a_m <= start_m <= b_m and (not segment or segment[-1].get("cum_m") != start_m):
            t = 0.0 if b_m == a_m else (start_m - a_m) / (b_m - a_m)
            segment.append({
                "lat": a["lat"] + t * (b["lat"] - a["lat"]),
                "lon": a["lon"] + t * (b["lon"] - a["lon"]),
                "ele": None if a.get("ele") is None or b.get("ele") is None else a["ele"] + t * (b["ele"] - a["ele"]),
                "cum_m": start_m,
                "x": None,
                "y": None,
            })
        if a_m >= start_m and a_m <= end_m:
            segment.append(dict(a))
        if a_m <= end_m <= b_m:
            t = 0.0 if b_m == a_m else (end_m - a_m) / (b_m - a_m)
            segment.append({
                "lat": a["lat"] + t * (b["lat"] - a["lat"]),
                "lon": a["lon"] + t * (b["lon"] - a["lon"]),
                "ele": None if a.get("ele") is None or b.get("ele") is None else a["ele"] + t * (b["ele"] - a["ele"]),
                "cum_m": end_m,
                "x": None,
                "y": None,
            })
            break
    if not segment:
        segment.append(dict(track[0]))
        if track[-1]["cum_m"] > end_m:
            segment.append(dict(track[-1]))
    deduped: list[dict[str, Any]] = []
    seen_positions: set[tuple[float, float, float]] = set()
    for point in segment:
        key = (round(float(point["lat"]), 7), round(float(point["lon"]), 7), round(float(point["cum_m"]), 2))
        if key in seen_positions:
            continue
        seen_positions.add(key)
        deduped.append(point)
    return deduped


def _nearest_track_projection(
    track: list[dict[str, Any]],
    lat: float,
    lon: float,
) -> dict[str, Any]:
    if not track:
        return {
            "route_km": None,
            "distance_to_track_m": None,
            "nearest_lat": None,
            "nearest_lon": None,
        }
    ref_lat = sum(point["lat"] for point in track) / len(track)
    px, py = _project_xy(lat, lon, ref_lat)
    best: dict[str, Any] | None = None
    for idx in range(len(track) - 1):
        a = track[idx]
        b = track[idx + 1]
        dist_m, t = _point_to_segment_distance_m(px, py, a["x"], a["y"], b["x"], b["y"])
        seg_len_m = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
        route_m = a["cum_m"] + t * seg_len_m
        lat_i = a["lat"] + t * (b["lat"] - a["lat"])
        lon_i = a["lon"] + t * (b["lon"] - a["lon"])
        candidate = {
            "route_km": round(route_m / 1000.0, 3),
            "distance_to_track_m": round(dist_m, 1),
            "nearest_lat": round(lat_i, 6),
            "nearest_lon": round(lon_i, 6),
        }
        if best is None or dist_m < float(best["distance_to_track_m"] or 10**9):
            best = candidate
    if best is None:
        first = track[0]
        dist_m = math.hypot(px - first["x"], py - first["y"])
        best = {
            "route_km": round(first["cum_m"] / 1000.0, 3),
            "distance_to_track_m": round(dist_m, 1),
            "nearest_lat": round(first["lat"], 6),
            "nearest_lon": round(first["lon"], 6),
        }
    return best


def _track_bbox(points: list[dict[str, Any]]) -> dict[str, float]:
    lats = [float(p["lat"]) for p in points]
    lons = [float(p["lon"]) for p in points]
    return {
        "min_lat": min(lats),
        "min_lon": min(lons),
        "max_lat": max(lats),
        "max_lon": max(lons),
    }


def _expand_bbox(bbox: dict[str, float], buffer_m: float) -> dict[str, float]:
    center_lat = (bbox["min_lat"] + bbox["max_lat"]) / 2.0
    lat_delta = buffer_m / 111_320.0
    lon_delta = buffer_m / max(1.0, 111_320.0 * math.cos(math.radians(center_lat)))
    return {
        "min_lat": bbox["min_lat"] - lat_delta,
        "min_lon": bbox["min_lon"] - lon_delta,
        "max_lat": bbox["max_lat"] + lat_delta,
        "max_lon": bbox["max_lon"] + lon_delta,
    }


def _bbox_to_overpass_string(bbox: dict[str, float]) -> str:
    return f"{bbox['min_lat']},{bbox['min_lon']},{bbox['max_lat']},{bbox['max_lon']}"


def _overpass_fetch_candidates(query: str) -> list[dict[str, Any]]:
    timeout = httpx.Timeout(60.0, connect=10.0, read=60.0, write=10.0, pool=10.0)
    last_error: Exception | None = None
    for endpoint in OVERPASS_URLS:
        try:
            resp = httpx.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=timeout,
            )
            if resp.status_code in {429, 502, 503, 504}:
                last_error = httpx.HTTPStatusError(
                    f"Overpass HTTP {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                continue
            resp.raise_for_status()
            payload = resp.json()
            return [element for element in payload.get("elements", []) if isinstance(element, dict)]
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return []


def _element_lat_lon(element: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = element.get("lat")
    lon = element.get("lon")
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            return None, None
    center = element.get("center")
    if isinstance(center, dict) and center.get("lat") is not None and center.get("lon") is not None:
        try:
            return float(center["lat"]), float(center["lon"])
        except (TypeError, ValueError):
            return None, None
    return None, None


def _element_source_tags(element: dict[str, Any]) -> dict[str, Any]:
    tags = element.get("tags") or {}
    if not isinstance(tags, dict):
        return {}
    wanted = {}
    for key in ("name", "tourism", "historic", "shop", "amenity", "drinking_water", "man_made", "wheelchair", "operator", "cuisine"):
        value = tags.get(key)
        if value not in (None, ""):
            wanted[key] = value
    return wanted


def _classify_poi(element: dict[str, Any]) -> tuple[str | None, str]:
    tags = element.get("tags") or {}
    if not isinstance(tags, dict):
        return None, "unclassified"

    amenity = str(tags.get("amenity", "")).strip().lower()
    shop = str(tags.get("shop", "")).strip().lower()
    tourism = str(tags.get("tourism", "")).strip().lower()
    historic = str(tags.get("historic", "")).strip().lower()
    man_made = str(tags.get("man_made", "")).strip().lower()
    drinking_water = str(tags.get("drinking_water", "")).strip().lower()

    if amenity in {"drinking_water", "fountain"} or drinking_water in {"yes", "potable", "true"} or man_made == "water_tap":
        return "water", "water access"

    if amenity in {"restaurant", "cafe", "bar", "fast_food", "pub", "biergarten", "food_court", "ice_cream"}:
        cuisine = str(tags.get("cuisine", "")).strip()
        name = str(tags.get("name", "")).strip()
        label = name if name else (cuisine if cuisine else amenity)
        return "food", label

    if shop in {"supermarket", "convenience", "bakery", "deli", "greengrocer", "general"} or amenity == "marketplace":
        name = str(tags.get("name", "")).strip()
        return "shop", name if name else f"{shop} shop"

    if amenity in {"fuel", "charging_station"}:
        brand = str(tags.get("brand", tags.get("operator", tags.get("name", "")))).strip()
        kind = "EV charging" if amenity == "charging_station" else "fuel station"
        return "shop", f"{kind} ({brand})" if brand else kind

    if tourism in {"attraction", "artwork", "gallery", "museum", "viewpoint", "theme_park", "zoo", "aquarium", "picnic_site"} or historic:
        return "attractions", "attraction / historic"

    return None, "unclassified"


def _source_tags_text(tags: dict[str, Any]) -> str:
    ordered = []
    for key in ("name", "tourism", "historic", "shop", "amenity", "drinking_water", "man_made", "operator", "cuisine"):
        value = tags.get(key)
        if value not in (None, ""):
            ordered.append(f"{key}={value}")
    return "; ".join(ordered)


def _render_route_poi_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# {result.get('report_title', 'Route POI analysis')}")
    lines.append("")
    lines.append(f"- route_id: {result.get('route_id') or ''}")
    if result.get("artifact_id"):
        lines.append(f"- artifact_id: {result.get('artifact_id')}")
    lines.append(f"- source_path: {result.get('source_path')}")
    if result.get("poi_source_mode"):
        lines.append(f"- poi_source_mode: {result.get('poi_source_mode')}")
    if result.get("google_supply_count") is not None:
        lines.append(f"- google_supply_count: {result.get('google_supply_count')}")
    lines.append(f"- km_from: {result.get('km_from')}")
    lines.append(f"- km_to: {result.get('km_to')}")
    lines.append(
        "- buffers_m: "
        f"attractions={result.get('buffers', {}).get('attractions_m')}, "
        f"food={result.get('buffers', {}).get('food_m')}, "
        f"water={result.get('buffers', {}).get('water_m')}"
    )
    lines.append(f"- track_points: {result.get('track_points_count')}")
    lines.append(f"- distance_km: {result.get('distance_km')}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- attractions: {len(result.get('attractions', []))}")
    lines.append(f"- food: {len(result.get('food', []))}")
    lines.append(f"- water: {len(result.get('water', []))}")
    lines.append("")

    def _table(title: str, rows: list[dict[str, Any]]) -> None:
        lines.append(f"## {title}")
        if not rows:
            lines.append("")
            lines.append("_No candidates found._")
            lines.append("")
            return
        lines.append("")
        lines.append("| name | category | lat | lon | route_km | distance_to_track_m | source_tags | note |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | --- | --- |")
        for row in rows:
            lines.append(
                "| "
                f"{row.get('name', '')} | {row.get('category', '')} | "
                f"{row.get('lat', '')} | {row.get('lon', '')} | {row.get('route_km', '')} | "
                f"{row.get('distance_to_track_m', '')} | {row.get('source_tags', '')} | "
                f"{row.get('note', '')} |"
            )
        lines.append("")

    _table("Attractions", result.get("attractions", []))
    _table("Food", result.get("food", []))
    _table("Shop", result.get("shop", []))
    _table("Water", result.get("water", []))

    return "\n".join(lines).rstrip() + "\n"


def _analyze_route_poi_artifact_legacy(
    file_path: str | Path,
    *,
    route_id: str | None = None,
    artifact_id: str | None = None,
    km_from: float,
    km_to: float,
    buffers: dict[str, float] | None = None,
    output_format: str = "md",
) -> dict[str, Any]:
    """Analyze POI candidates along a GPX route segment."""
    path = Path(file_path)
    if not path.exists():
        return {"ok": False, "status": "ERROR", "error": f"File not found: {path}"}
    if km_to < km_from:
        return {"ok": False, "status": "ERROR", "error": "km_to must be >= km_from"}

    buffers = buffers or {}
    attractions_m = float(buffers.get("attractions_m", 1000))
    food_m = float(buffers.get("food_m", 500))
    shop_m = float(buffers.get("shop_m", 1000))
    water_m = float(buffers.get("water_m", 200))
    max_buffer_m = max(attractions_m, food_m, shop_m, water_m)

    points = _parse_gpx_file_detailed(path)
    if not points:
        return {"ok": False, "status": "ERROR", "error": f"No track points in {path}"}

    projected = _track_projection(points)
    total_km = round(projected[-1]["cum_m"] / 1000.0, 3)
    overpass_queries = [
        (
            "attractions",
            """
[out:json][timeout:25];
(
  node["tourism"~"attraction|artwork|gallery|museum|viewpoint|theme_park|zoo|aquarium|picnic_site"](around:{radius},{lat},{lon});
  node["historic"](around:{radius},{lat},{lon});
);
out center tags;
""",
        ),
        (
            "food",
            """
[out:json][timeout:25];
(
  node["amenity"~"restaurant|cafe|bar|fast_food|pub|biergarten|food_court|ice_cream"](around:{radius},{lat},{lon});
);
out center tags;
""",
        ),
        (
            "shop",
            """
[out:json][timeout:25];
(
  node["shop"~"supermarket|convenience|bakery|deli|greengrocer|general"](around:{radius},{lat},{lon});
  node["amenity"~"marketplace|fuel|charging_station"](around:{radius},{lat},{lon});
);
out center tags;
""",
        ),
        (
            "water",
            """
[out:json][timeout:25];
(
  node["amenity"="drinking_water"](around:{radius},{lat},{lon});
  node["amenity"="fountain"](around:{radius},{lat},{lon});
  node["drinking_water"="yes"](around:{radius},{lat},{lon});
  node["man_made"="water_tap"](around:{radius},{lat},{lon});
);
out center tags;
""",
        ),
    ]
    candidates_raw: list[dict[str, Any]] = []
    radius_m = int(max(max_buffer_m + 500.0, 1000.0))
    sample_step_km = 10.0 if (km_to - km_from) > 10.0 else max(1.0, float(km_to - km_from) or 1.0)
    sample_km = float(km_from)
    while sample_km <= float(km_to) + 1e-9:
        sample_point = _find_point_at_km(points, sample_km)
        for category_name, overpass_query_template in overpass_queries:
            overpass_query = overpass_query_template.format(radius=radius_m, lat=sample_point["lat"], lon=sample_point["lon"])
            try:
                candidates_raw.extend(_overpass_fetch_candidates(overpass_query))
            except Exception:
                continue
        sample_km += sample_step_km

    categorized: dict[str, list[dict[str, Any]]] = {"attractions": [], "food": [], "shop": [], "water": []}
    seen_keys: set[str] = set()
    for element in candidates_raw:
        lat, lon = _element_lat_lon(element)
        if lat is None or lon is None:
            continue
        category, note = _classify_poi(element)
        if not category:
            continue
        key = f"{element.get('type')}:{element.get('id')}:{category}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

        nearest = _nearest_track_projection(projected, lat, lon)
        route_km = nearest.get("route_km")
        distance_to_track_m = nearest.get("distance_to_track_m")
        if route_km is None or distance_to_track_m is None:
            continue
        if route_km < km_from or route_km > km_to:
            continue

        limit = attractions_m if category == "attractions" else food_m if category == "food" else water_m
        if float(distance_to_track_m) > limit:
            continue

        tags = _element_source_tags(element)
        name = str(tags.get("name") or element.get("tags", {}).get("name") or f"{category[:-1].capitalize()} {element.get('id')}")
        categorized[category].append({
            "name": name,
            "category": category[:-1],
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "route_km": route_km,
            "distance_to_track_m": distance_to_track_m,
            "source_tags": _source_tags_text(tags),
            "note": note,
        })

    for category in categorized:
        categorized[category].sort(key=lambda item: (float(item.get("route_km") or 0), float(item.get("distance_to_track_m") or 0)))

    categorized["attractions"] = categorized["attractions"][:15]
    categorized["food"] = categorized["food"][:12]
    categorized["food"] = categorized["food"][:15]
    categorized["shop"] = categorized.get("shop", [])[:15]
    categorized["water"] = categorized["water"][:12]

    result: dict[str, Any] = {
        "ok": True,
        "status": "OK",
        "route_id": route_id,
        "artifact_id": artifact_id,
        "source_path": str(path),
        "km_from": km_from,
        "km_to": km_to,
        "buffers": {
            "attractions_m": attractions_m,
            "food_m": food_m,
            "water_m": water_m,
        },
        "track_points_count": len(projected),
        "distance_km": total_km,
        "bbox": bbox,
        "attractions": categorized["attractions"],
        "food": categorized["food"],
        "food": categorized["food"],
        "shop": categorized.get("shop", []),
        "water": categorized["water"],
        "report_title": f"POI analysis — route {route_id or artifact_id or path.stem}",
    }
    result["markdown"] = _render_route_poi_markdown(result)
    if output_format == "json":
        result["output_format"] = "json"
    else:
        result["output_format"] = "md"
    return result


def analyze_route_poi_artifact(
    file_path: str | Path,
    *,
    route_id: str | None = None,
    artifact_id: str | None = None,
    project_id: str | None = None,
    km_from: float,
    km_to: float,
    buffers: dict[str, float] | None = None,
    focus: str | None = None,
    retry_chunk_id: str | None = None,
    retry_mode: bool = False,
    merge_artifact_ids: list[str] | None = None,
    timeout_sec: float | None = None,
    output_format: str = "md",
) -> dict[str, Any]:
    """Deterministic POI analysis with retries, chunk splitting and merge support."""
    log = logging.getLogger("route_poi_analyze")
    t_start = time.perf_counter()
    buffers = buffers or {}
    focus_mode = _route_poi_v2_focus_mode(focus or buffers.get("focus"))
    categories_requested = _route_poi_v2_requested_categories(focus_mode)
    route_source_path = str(file_path).strip()
    path = Path(route_source_path) if route_source_path else None
    source_slug = str(route_id or artifact_id or (path.stem if path else "route_poi")).strip() or "route_poi"
    deadline_sec = float(timeout_sec if timeout_sec is not None else buffers.get("analysis_timeout_sec", 80.0))
    overpass_timeout_sec = float(buffers.get("overpass_timeout_sec", 30.0))
    chunk_km = float(buffers.get("chunk_km", 8.0))
    overlap_km = max(1.0, float(buffers.get("chunk_overlap_km", 1.0)))
    min_chunk_km = max(1.0, float(buffers.get("min_chunk_km", 5.0)))
    retry_attempts = max(1, int(buffers.get("overpass_retries", 3)))
    retry_backoff_sec = max(0.1, float(buffers.get("retry_backoff_sec", 1.25)))
    attractions_m = float(buffers.get("attractions_m", 1000))
    hard_resupply_m = float(buffers.get("hard_resupply_m", buffers.get("food_m", 400)))
    soft_food_m = float(buffers.get("soft_food_m", buffers.get("food_m", 400)))
    water_m = float(buffers.get("water_m", 200))
    max_buffer_m = max(
        attractions_m,
        hard_resupply_m,
        soft_food_m,
        water_m,
    )
    deadline_at = t_start + deadline_sec
    open_window_enabled = bool(buffers.get("open_window", False))
    ride_start_raw = buffers.get("ride_start")
    ride_start_dt: datetime | None = None
    if ride_start_raw:
        try:
            ride_start_dt = datetime.fromisoformat(str(ride_start_raw).replace("Z", "+00:00"))
        except ValueError:
            ride_start_dt = None
    try:
        avg_speed_kmh = float(buffers.get("avg_speed_kmh", 18.0))
    except (TypeError, ValueError):
        avg_speed_kmh = 18.0
    try:
        google_hours_flag = bool(buffers.get("google_hours", True))
    except Exception:
        google_hours_flag = True

    def _retry_payload(
        *,
        chunk_id: str,
        km_a: float,
        km_b: float,
        bbox: dict[str, float],
        reason: str,
    ) -> dict[str, Any]:
        return _route_poi_v2_missing_chunk_entry(
            route_id=route_id,
            artifact_id=artifact_id,
            source_path=route_source_path or None,
            km_from=km_a,
            km_to=km_b,
            bbox=bbox,
            focus=focus_mode,
            categories_requested=categories_requested,
            buffers={
                "attractions_m": float(buffers.get("attractions_m", 1000)),
                "hard_resupply_m": float(buffers.get("hard_resupply_m", buffers.get("food_m", 400))),
                "soft_food_m": float(buffers.get("soft_food_m", buffers.get("food_m", 400))),
                "water_m": float(buffers.get("water_m", 200)),
                "chunk_km": chunk_km,
                "chunk_overlap_km": overlap_km,
                "analysis_timeout_sec": deadline_sec,
                "overpass_timeout_sec": overpass_timeout_sec,
                "min_chunk_km": min_chunk_km,
                "open_window": open_window_enabled,
                "ride_start": ride_start_raw,
                "avg_speed_kmh": avg_speed_kmh,
                "google_hours": google_hours_flag,
            },
            reason=reason,
            retry_chunk_id=chunk_id,
            timeout_sec=deadline_sec,
            overpass_timeout_sec=overpass_timeout_sec,
            output_format=output_format,
        )

    def _collect_chunk(km_a: float, km_b: float, chunk_id: str | None = None) -> dict[str, Any]:
        chunk_id = chunk_id or _route_poi_v2_chunk_id(km_a, km_b)
        segment = _track_segment_projection(projected, km_a, km_b)
        if len(segment) < 2:
            bbox0 = _expand_bbox(_track_bbox(points), max_buffer_m + 500.0)
            return {
                "chunks": [{
                    "chunk_id": chunk_id,
                    "chunk_from_km": round(km_a, 3),
                    "chunk_to_km": round(km_b, 3),
                    "status": "EMPTY",
                    "reason": "insufficient_track_points",
                    "bbox": bbox0,
                    "categories_requested": list(categories_requested),
                    "attempts": 0,
                }],
                "poi_candidates": [],
                "town_candidates": [],
                "missing_chunks": [],
            }

        bbox = _expand_bbox(_track_bbox(segment), max_buffer_m + 500.0)
        query = _route_poi_v2_build_query(
            bbox,
            focus_mode,
            timeout_sec=overpass_timeout_sec,
            include_supply=not prefer_google_supply,
        )
        last_exc: Exception | None = None
        for attempt in range(1, retry_attempts + 1):
            if time.perf_counter() > deadline_at:
                retry = _retry_payload(chunk_id=chunk_id, km_a=km_a, km_b=km_b, bbox=bbox, reason="analysis_timeout")
                retry["status"] = "MISSING"
                retry["error"] = "analysis timeout reached before Overpass request"
                return {"chunks": [retry], "poi_candidates": [], "town_candidates": [], "missing_chunks": [retry]}
            try:
                log.info(
                    "route_poi_analyze overpass attempt %s/%s chunk=%s km=%.2f-%.2f focus=%s",
                    attempt, retry_attempts, chunk_id, km_a, km_b, focus_mode,
                )
                raw_elements = _route_poi_v2_overpass_candidates(query, overpass_timeout_sec, bbox=bbox)
                poi_candidates: list[dict[str, Any]] = []
                town_candidates: list[dict[str, Any]] = []
                for element in raw_elements:
                    tags = element.get("tags") or {}
                    if not isinstance(tags, dict):
                        continue
                    lat, lon = _element_lat_lon(element)
                    if lat is None or lon is None:
                        continue
                    category, note = _route_poi_v2_classify(tags)
                    if not category:
                        continue
                    if focus_mode == "logistics" and category == "attraction":
                        continue
                    nearest = _nearest_track_projection(projected, lat, lon)
                    route_km = nearest.get("route_km")
                    distance_to_track_m = nearest.get("distance_to_track_m")
                    if route_km is None or distance_to_track_m is None:
                        continue
                    if route_km < km_a or route_km > km_b:
                        continue
                    if category == "hard_resupply" and float(distance_to_track_m) > float(buffers.get("hard_resupply_m", buffers.get("food_m", 400))):
                        continue
                    if category == "soft_food_stop" and float(distance_to_track_m) > float(buffers.get("soft_food_m", buffers.get("food_m", 400))):
                        continue
                    if category == "water" and float(distance_to_track_m) > float(buffers.get("water_m", 200)):
                        continue
                    if category == "attraction" and float(distance_to_track_m) > float(buffers.get("attractions_m", 1000)):
                        continue
                    item = {
                        "osm_type": element.get("type"),
                        "osm_id": element.get("id"),
                        "name": _route_poi_v2_name(element, tags, category),
                        "category": category,
                        "lat": round(float(lat), 6),
                        "lon": round(float(lon), 6),
                        "route_km": route_km,
                        "distance_to_track_m": distance_to_track_m,
                        "source_tags": _route_poi_v2_source_tags(_element_source_tags(element)),
                        "opening_hours_osm": tags.get("opening_hours") if tags.get("opening_hours") not in (None, "") else None,
                        "note": note,
                    }
                    if category == "town":
                        town_candidates.append(item)
                    else:
                        poi_candidates.append(item)
                chunk_record = {
                    "chunk_id": chunk_id,
                    "chunk_from_km": round(km_a, 3),
                    "chunk_to_km": round(km_b, 3),
                    "status": "OK",
                    "attempts": attempt,
                    "bbox": bbox,
                    "categories_requested": list(categories_requested),
                    "overpass_candidates": len(raw_elements),
                    "poi_candidates": len(poi_candidates),
                    "town_candidates": len(town_candidates),
                    "duration_ms": round((time.perf_counter() - t_start) * 1000.0, 1),
                }
                log.info(
                    "route_poi_analyze chunk %s finished in %.1fms: raw=%s poi=%s town=%s",
                    chunk_id,
                    chunk_record["duration_ms"],
                    len(raw_elements),
                    len(poi_candidates),
                    len(town_candidates),
                )
                return {"chunks": [chunk_record], "poi_candidates": poi_candidates, "town_candidates": town_candidates, "missing_chunks": []}
            except Exception as exc:
                last_exc = exc
                log.warning("route_poi_analyze overpass error chunk %s attempt %s/%s: %s", chunk_id, attempt, retry_attempts, exc)
                if attempt < retry_attempts:
                    time.sleep(min(retry_backoff_sec * attempt, 3.0))

        reason_text = str(last_exc or "overpass error").lower()
        reason = "overpass_timeout" if any(token in reason_text for token in ("timeout", "timed out", "read timed out")) else "overpass_error"
        if (km_b - km_a) <= min_chunk_km:
            retry = _retry_payload(chunk_id=chunk_id, km_a=km_a, km_b=km_b, bbox=bbox, reason=reason)
            retry["status"] = "MISSING"
            retry["error"] = str(last_exc)[:200] if last_exc else reason
            return {"chunks": [retry], "poi_candidates": [], "town_candidates": [], "missing_chunks": [retry]}

        mid = round((km_a + km_b) / 2.0, 3)
        left = _collect_chunk(km_a, mid, f"{chunk_id}a")
        right = _collect_chunk(mid, km_b, f"{chunk_id}b")
        return {
            "chunks": list(left.get("chunks", [])) + list(right.get("chunks", [])),
            "poi_candidates": list(left.get("poi_candidates", [])) + list(right.get("poi_candidates", [])),
            "town_candidates": list(left.get("town_candidates", [])) + list(right.get("town_candidates", [])),
            "missing_chunks": list(left.get("missing_chunks", [])) + list(right.get("missing_chunks", [])),
        }

    timings: dict[str, float] = {}
    if merge_artifact_ids:
        merge_payloads: list[dict[str, Any]] = []
        for art_id in merge_artifact_ids:
            art_id = str(art_id or "").strip()
            if not art_id:
                continue
            merge_payloads.append(_route_poi_v2_load_analysis_payload(art_id))
        if not merge_payloads:
            return {"ok": False, "status": "ERROR", "error": "No merge artifacts found"}
        t_merge = time.perf_counter()
        result = _route_poi_v2_merge_analysis_payloads(merge_payloads)
        timings.update(result.get("timings_ms") or {})
        if path and path.exists():
            try:
                t0 = time.perf_counter()
                points = _parse_gpx_file_detailed(path)
                timings["gpx_load_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
                t1 = time.perf_counter()
                projected = _track_projection(points)
                timings["track_projection_ms"] = round((time.perf_counter() - t1) * 1000.0, 1)
                result["track_points_count"] = len(projected)
                result["distance_km"] = round(projected[-1]["cum_m"] / 1000.0, 3)
                result["bbox"] = _track_bbox(points)
            except Exception as exc:
                log.warning("route_poi_analyze merge GPX refresh failed: %s", exc)
        result["route_id"] = result.get("route_id") or route_id
        result["project_id"] = result.get("project_id") or project_id
        result["artifact_id"] = artifact_id
        result["source_path"] = result.get("source_path") or route_source_path
        result["focus"] = focus_mode
        result["analysis_status"] = result.get("status")
        result["report_tag"] = "FINAL"
        report_stem = _route_poi_v2_report_stem(source_slug, km_from, km_to, "FINAL")
        result["report_filename"] = f"{report_stem}.md"
        result["report_json_filename"] = f"{report_stem}.json"
        result["markdown"] = _route_poi_v2_build_markdown(result)
        timings["merge_ms"] = round((time.perf_counter() - t_merge) * 1000.0, 1)
        timings["total_ms"] = round((time.perf_counter() - t_start) * 1000.0, 1)
        result["timings_ms"] = timings
        result["output_format"] = output_format
        return result

    if path is None or not path.exists():
        return {"ok": False, "status": "ERROR", "error": f"File not found: {path}"}

    t0 = time.perf_counter()
    points = _parse_gpx_file_detailed(path)
    if not points:
        return {"ok": False, "status": "ERROR", "error": f"No track points in {path}"}
    timings["gpx_load_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)

    t1 = time.perf_counter()
    projected = _track_projection(points)
    total_km = round(projected[-1]["cum_m"] / 1000.0, 3)
    timings["track_projection_ms"] = round((time.perf_counter() - t1) * 1000.0, 1)
    bbox = _track_bbox(points)

    t_google = time.perf_counter()
    google_api_key = _route_poi_v2_google_api_key()
    google_supply_candidates: list[dict[str, Any]] = []
    if google_api_key:
        google_supply_candidates = _route_poi_v2_google_supply_candidates(
            points,
            projected,
            km_from=km_from,
            km_to=km_to,
            sample_step_km=min(8.0, max(4.0, chunk_km)),
            radius_m=max(max_buffer_m + 800.0, 1500.0),
            ride_start_dt=ride_start_dt,
            avg_speed_kmh=avg_speed_kmh,
            api_key=google_api_key,
        )
    timings["google_ms"] = round((time.perf_counter() - t_google) * 1000.0, 1)
    prefer_google_supply = bool(google_supply_candidates)

    t_overpass = time.perf_counter()
    chunk_start = float(km_from)
    chunk_end_limit = float(km_to)
    if chunk_km <= 0:
        chunk_km = max(1.0, float(km_to - km_from) or 1.0)
    step_km = max(0.5, chunk_km - overlap_km)
    all_candidates: list[dict[str, Any]] = []
    town_candidates: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    missing_chunks: list[dict[str, Any]] = []
    partial = False

    while chunk_start <= chunk_end_limit + 1e-9:
        if time.perf_counter() > deadline_at:
            partial = True
            remaining_from = chunk_start
            remaining_to = chunk_end_limit
            remaining_segment = _track_segment_projection(projected, remaining_from, remaining_to) or projected
            remaining_bbox = _expand_bbox(_track_bbox(remaining_segment), max_buffer_m + 500.0)
            missing = _retry_payload(chunk_id=_route_poi_v2_chunk_id(remaining_from, remaining_to), km_a=remaining_from, km_b=remaining_to, bbox=remaining_bbox, reason="analysis_timeout")
            missing["status"] = "MISSING"
            missing["error"] = "analysis timeout reached before chunk start"
            missing_chunks.append(missing)
            chunks.append({
                "chunk_id": missing["chunk_id"],
                "chunk_from_km": missing["km_from"],
                "chunk_to_km": missing["km_to"],
                "status": "MISSING",
                "reason": missing["reason"],
                "bbox": missing["bbox"],
                "categories_requested": missing["categories_requested"],
                "attempts": 0,
            })
            log.info("route_poi_analyze deadline reached before chunk start %.2f", chunk_start)
            break

        chunk_stop = min(chunk_end_limit, chunk_start + chunk_km)
        result_chunk = _collect_chunk(chunk_start, chunk_stop)
        chunks.extend(list(result_chunk.get("chunks", [])))
        all_candidates.extend(list(result_chunk.get("poi_candidates", [])))
        town_candidates.extend(list(result_chunk.get("town_candidates", [])))
        missing_chunks.extend(list(result_chunk.get("missing_chunks", [])))
        if result_chunk.get("missing_chunks"):
            partial = True
        chunk_start += step_km

    timings["overpass_ms"] = round((time.perf_counter() - t_overpass) * 1000.0, 1)

    t_filter = time.perf_counter()
    all_candidates.extend(google_supply_candidates)
    deduped = _route_poi_v2_dedupe(all_candidates)
    grouped: dict[str, list[dict[str, Any]]] = {"hard_resupply": [], "soft_food_stop": [], "water": [], "attraction": []}
    for item in deduped:
        grouped.setdefault(str(item.get("category") or ""), []).append(item)
    for key in grouped:
        grouped[key] = _route_poi_v2_mark_clusters(grouped[key])
        grouped[key].sort(key=lambda item: (float(item.get("route_km") or 0), float(item.get("distance_to_track_m") or 10**9)))
    timings["filter_ms"] = round((time.perf_counter() - t_filter) * 1000.0, 1)

    if open_window_enabled:
        try:
            from tools.rwgps.poi_open_window import enrich_open_window, _api_key

            google_api_key = _api_key()
            use_google = bool(google_hours_flag and google_api_key)
            enrich_open_window(
                grouped.get("hard_resupply", []),
                ride_start=ride_start_dt,
                avg_speed_kmh=avg_speed_kmh,
                use_google=use_google,
                api_key=google_api_key,
            )
            enrich_open_window(
                grouped.get("soft_food_stop", []),
                ride_start=ride_start_dt,
                avg_speed_kmh=avg_speed_kmh,
                use_google=use_google,
                api_key=google_api_key,
            )
            enrich_open_window(
                grouped.get("water", []),
                ride_start=ride_start_dt,
                avg_speed_kmh=avg_speed_kmh,
                use_google=use_google,
                api_key=google_api_key,
            )
            if "shop" in grouped:
                enrich_open_window(
                    grouped.get("shop", []),
                    ride_start=ride_start_dt,
                    avg_speed_kmh=avg_speed_kmh,
                    use_google=use_google,
                    api_key=google_api_key,
                )
        except Exception as exc:
            log.warning("route_poi_analyze open_window enrichment failed: %s", exc)

    t_town = time.perf_counter()
    town_deduped = _route_poi_v2_mark_clusters(_route_poi_v2_dedupe(town_candidates))
    town_deduped.sort(key=lambda item: (float(item.get("route_km") or 0), float(item.get("distance_to_track_m") or 10**9)))
    for town in town_deduped:
        nearby_hard = [
            item for item in grouped.get("hard_resupply", [])
            if abs(float(item.get("route_km") or 0) - float(town.get("route_km") or 0)) <= 2.0
            and float(item.get("distance_to_track_m") or 10**9) <= max(hard_resupply_m, soft_food_m, 1000.0)
        ]
        town["hard_resupply_found"] = bool(nearby_hard)
        town["hard_resupply_names"] = ", ".join([str(item.get("name") or "") for item in nearby_hard[:5]])
    timings["town_fallback_ms"] = round((time.perf_counter() - t_town) * 1000.0, 1)

    summary = {
        "hard_resupply": len(grouped.get("hard_resupply", [])),
        "soft_food_stop": len(grouped.get("soft_food_stop", [])),
        "water": len(grouped.get("water", [])),
        "attraction": len(grouped.get("attraction", [])),
        "town": len(town_deduped),
    }

    report_tag_effective = retry_chunk_id if retry_mode and retry_chunk_id else (
        "FINAL" if not missing_chunks and focus_mode == "logistics" and float(km_from) <= 0.0 and float(km_to) >= 80.0 else None
    )
    report_stem = _route_poi_v2_report_stem(source_slug, km_from, km_to, report_tag_effective)
    result: dict[str, Any] = {
        "ok": True,
        "status": "PARTIAL" if partial or missing_chunks else "OK",
        "analysis_status": "PARTIAL" if partial or missing_chunks else "OK",
        "route_id": route_id,
        "project_id": project_id,
        "artifact_id": artifact_id,
        "source_path": str(path),
        "focus": focus_mode,
        "km_from": km_from,
        "km_to": km_to,
        "buffers": {
            "attractions_m": attractions_m,
            "hard_resupply_m": hard_resupply_m,
            "soft_food_m": soft_food_m,
            "water_m": water_m,
            "chunk_km": chunk_km,
            "chunk_overlap_km": overlap_km,
            "analysis_timeout_sec": deadline_sec,
            "overpass_timeout_sec": overpass_timeout_sec,
            "min_chunk_km": min_chunk_km,
            "open_window": open_window_enabled,
            "ride_start": ride_start_raw,
            "avg_speed_kmh": avg_speed_kmh,
            "google_hours": google_hours_flag,
        },
        "track_points_count": len(projected),
        "distance_km": total_km,
        "bbox": bbox,
        "chunks": chunks,
        "missing_chunks": missing_chunks,
        "missing_chunks_count": len(missing_chunks),
        "timings_ms": timings,
        "summary": summary,
        "poi_source_mode": "google_places_primary" if prefer_google_supply else "overpass_primary",
        "google_supply_count": len(google_supply_candidates),
        "hard_resupply": grouped.get("hard_resupply", [])[:15],
        "soft_food_stop": grouped.get("soft_food_stop", [])[:12],
        "water": grouped.get("water", [])[:12],
        "attractions": grouped.get("attraction", [])[:15],
        "town_fallback_check": town_deduped[:20],
        "report_title": f"POI analysis — route {source_slug}",
        "report_tag": report_tag_effective,
        "report_filename": f"{report_stem}.md",
        "report_json_filename": f"{report_stem}.json",
        "warnings": [],
        "retry_chunk_id": retry_chunk_id,
        "retry_mode": bool(retry_mode),
    }
    if missing_chunks:
        result["warnings"].append("analysis truncated due to timeout budget; partial artifact written")
        result["warnings"].append("missing_chunks include retry_payload_json for targeted retries")
    result["warnings"].append("candidate counts are filtered by route distance and per-category distance-to-track buffers")
    timings["total_ms"] = round((time.perf_counter() - t_start) * 1000.0, 1)
    result["timings_ms"] = timings
    result["markdown"] = _route_poi_v2_build_markdown(result)
    result["output_format"] = output_format
    return result


# ── route_poi_analyze v2 ───────────────────────────────────────────────

def _route_poi_v2_norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _route_poi_v2_is_food_hard(tags: dict[str, Any], name_text: str) -> bool:
    shop = _route_poi_v2_norm_text(tags.get("shop"))
    amenity = _route_poi_v2_norm_text(tags.get("amenity"))
    vending = _route_poi_v2_norm_text(tags.get("vending"))
    if shop in {"convenience", "supermarket", "grocery", "bakery", "deli", "butcher", "greengrocer", "pastry", "farm", "general"}:
        return True
    if amenity == "marketplace":
        return True
    if amenity == "fuel":
        if shop:
            return True
        cues = ("convenience", "alimentari", "market", "shop", "store", "gas", "station", "ristoro", "bar", "cafe", "caff", "food", "snack", "spesa")
        return any(cue in name_text for cue in cues) or vending in {"food", "drinks", "food;drinks", "drinks;food"}
    if vending in {"food", "drinks", "food;drinks", "drinks;food"}:
        return True
    return False


def _route_poi_v2_classify(tags: dict[str, Any]) -> tuple[str | None, str]:
    name_text = _route_poi_v2_norm_text(tags.get("name") or tags.get("operator") or tags.get("brand"))
    amenity = _route_poi_v2_norm_text(tags.get("amenity"))
    shop = _route_poi_v2_norm_text(tags.get("shop"))
    tourism = _route_poi_v2_norm_text(tags.get("tourism"))
    historic = _route_poi_v2_norm_text(tags.get("historic"))
    place = _route_poi_v2_norm_text(tags.get("place"))
    man_made = _route_poi_v2_norm_text(tags.get("man_made"))
    drinking_water = _route_poi_v2_norm_text(tags.get("drinking_water"))

    if amenity in {"drinking_water", "fountain"} or drinking_water in {"yes", "potable", "true"} or man_made == "water_tap":
        return "water", "water"
    if _route_poi_v2_is_food_hard(tags, name_text):
        return "hard_resupply", "hard_resupply"
    if amenity in {"cafe", "bar", "restaurant", "fast_food", "pub", "ice_cream"}:
        return "soft_food_stop", "soft_food_stop"
    if tourism in {"attraction", "artwork", "gallery", "museum", "viewpoint", "theme_park", "zoo", "aquarium", "picnic_site"} or historic:
        return "attraction", "attraction"
    if place in {"city", "town", "village", "hamlet"}:
        return "town", "town_fallback_check"
    if shop in {"convenience", "supermarket", "grocery", "bakery", "deli", "butcher", "greengrocer", "pastry", "farm", "general"}:
        return "hard_resupply", "hard_resupply"
    return None, "unclassified"


def _route_poi_v2_source_tags(tags: dict[str, Any]) -> str:
    ordered = []
    for key in ("name", "place", "tourism", "historic", "shop", "amenity", "drinking_water", "man_made", "vending", "operator", "brand", "cuisine"):
        value = tags.get(key)
        if value not in (None, ""):
            ordered.append(f"{key}={value}")
    return "; ".join(ordered)


def _route_poi_v2_name(element: dict[str, Any], tags: dict[str, Any], category: str) -> str:
    name = str(tags.get("name") or "").strip()
    if name:
        return name
    fallback = {
        "hard_resupply": "Hard resupply",
        "soft_food_stop": "Food stop",
        "water": "Water",
        "attraction": "Attraction",
        "town": "Town",
    }.get(category, "POI")
    osm_id = element.get("id")
    return f"{fallback} {osm_id}" if osm_id is not None else fallback


def _route_poi_v2_round_key(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def _route_poi_v2_dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in sorted(items, key=lambda x: (float(x.get("route_km") or 0), float(x.get("distance_to_track_m") or 10**9), str(x.get("name") or ""))):
        osm_id = item.get("osm_id")
        if osm_id not in (None, ""):
            key = (item.get("category"), str(osm_id))
        else:
            key = (
                item.get("category"),
                _route_poi_v2_norm_text(item.get("name")),
                _route_poi_v2_round_key(float(item.get("lat") or 0.0), 3),
                _route_poi_v2_round_key(float(item.get("lon") or 0.0), 3),
            )
        existing = grouped.get(key)
        if existing is None:
            item["cluster_size"] = 1
            grouped[key] = item
            continue
        existing["cluster_size"] = int(existing.get("cluster_size", 1)) + 1
        if float(item.get("distance_to_track_m") or 10**9) < float(existing.get("distance_to_track_m") or 10**9):
            grouped[key] = item
            grouped[key]["cluster_size"] = existing["cluster_size"]
    return list(grouped.values())


def _route_poi_v2_mark_clusters(items: list[dict[str, Any]], proximity_m: float = 120.0, route_km_window: float = 0.25) -> list[dict[str, Any]]:
    if not items:
        return items
    items = sorted(items, key=lambda x: (float(x.get("route_km") or 0), float(x.get("distance_to_track_m") or 10**9)))
    cluster_start = 0
    for idx in range(1, len(items) + 1):
        same_cluster = False
        if idx < len(items):
            prev = items[idx - 1]
            cur = items[idx]
            if abs(float(cur.get("route_km") or 0) - float(prev.get("route_km") or 0)) <= route_km_window:
                if _haversine_km(float(cur["lat"]), float(cur["lon"]), float(prev["lat"]), float(prev["lon"])) * 1000.0 <= proximity_m:
                    same_cluster = True
        if same_cluster:
            continue
        cluster = items[cluster_start:idx]
        if len(cluster) > 1:
            label = f"cluster: {len(cluster)} POI"
            for row in cluster:
                note = str(row.get("note") or "").strip()
                extra = f"{note}; {label}; logistics_stop" if note else f"{label}; logistics_stop"
                row["note"] = extra
        cluster_start = idx
    return items


def _route_poi_v2_google_api_key() -> str | None:
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    return key.strip() if isinstance(key, str) and key.strip() else None


def _route_poi_v2_google_search_nearby(
    lat: float,
    lon: float,
    *,
    radius_m: float,
    api_key: str,
) -> list[dict[str, Any]]:
    payload = {
        "includedTypes": list(GOOGLE_SUPPLY_TYPES),
        "maxResultCount": 10,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": float(lat), "longitude": float(lon)},
                "radius": float(radius_m),
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.rating,places.userRatingCount,"
            "places.location,places.types,places.currentOpeningHours,places.regularOpeningHours"
        ),
    }
    resp = httpx.post(GOOGLE_PLACES_URL, json=payload, headers=headers, timeout=10.0)
    resp.raise_for_status()
    places = resp.json().get("places", [])
    return list(places) if isinstance(places, list) else []


def _route_poi_v2_google_place_to_candidate(
    place: dict[str, Any],
    *,
    projected: list[dict[str, Any]],
    ride_start_dt: datetime | None,
    avg_speed_kmh: float,
) -> dict[str, Any] | None:
    if not isinstance(place, dict):
        return None
    loc = place.get("location") or {}
    try:
        lat = float(loc.get("latitude"))
        lon = float(loc.get("longitude"))
    except (TypeError, ValueError):
        return None

    nearest = _nearest_track_projection(projected, lat, lon)
    route_km = nearest.get("route_km")
    distance_to_track_m = nearest.get("distance_to_track_m")
    if route_km is None or distance_to_track_m is None:
        return None

    display = place.get("displayName") or {}
    name = str(display.get("text") or "").strip()
    place_id = str(place.get("id") or "").strip() or None
    types = [str(t).strip().lower() for t in (place.get("types") or []) if str(t).strip()]

    category = None
    kind_tags: dict[str, str] = {"name": name}
    if any(t in GOOGLE_HARD_TYPES for t in types):
        category = "hard_resupply"
        if "supermarket" in types:
            kind_tags["shop"] = "supermarket"
        elif "grocery_store" in types:
            kind_tags["shop"] = "grocery"
        elif "convenience_store" in types:
            kind_tags["shop"] = "convenience"
        elif "bakery" in types:
            kind_tags["shop"] = "bakery"
    elif any(t in GOOGLE_SOFT_TYPES for t in types):
        category = "soft_food_stop"
        if "restaurant" in types:
            kind_tags["amenity"] = "restaurant"
        elif "cafe" in types:
            kind_tags["amenity"] = "cafe"
        elif "bar" in types:
            kind_tags["amenity"] = "bar"
        elif "fast_food" in types:
            kind_tags["amenity"] = "fast_food"
    else:
        low_name = _route_poi_v2_norm_text(name)
        if any(tok in low_name for tok in ("zabka", "biedronka", "lidl", "dino", "netto", "aldi", "kaufland", "carrefour", "lewiatan", "groszek", "abc")):
            category = "hard_resupply"
            kind_tags["shop"] = "convenience"

    if category is None:
        return None

    eta_dt = None
    if ride_start_dt is not None:
        try:
            from tools.rwgps.poi_open_window import eta_at_km, google_open_at

            eta_dt = eta_at_km(float(route_km), ride_start_dt, avg_speed_kmh)
            google_obj = {
                "currentOpeningHours": place.get("currentOpeningHours"),
                "regularOpeningHours": place.get("regularOpeningHours"),
            }
            open_at_arrival = google_open_at(google_obj, eta_dt)
        except Exception:
            eta_dt = None
            open_at_arrival = None
    else:
        open_at_arrival = None

    opening_hours = None
    regular = place.get("regularOpeningHours") or {}
    current = place.get("currentOpeningHours") or {}
    weekday_descriptions = regular.get("weekdayDescriptions") or current.get("weekdayDescriptions") or []
    if isinstance(weekday_descriptions, list) and weekday_descriptions:
        opening_hours = "; ".join(str(line).strip() for line in weekday_descriptions if str(line).strip()) or None
    elif regular or current:
        opening_hours = "Google Places"

    return {
        "osm_type": "google_places",
        "osm_id": place_id,
        "google_place_id": place_id,
        "google_name": name or None,
        "name": name or f"Google {category}",
        "category": category,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "route_km": float(route_km),
        "distance_to_track_m": float(distance_to_track_m),
        "source_tags": _route_poi_v2_source_tags(kind_tags | {"provider": "google_places", "google_type": ",".join(types[:5])}),
        "opening_hours_osm": opening_hours,
        "open_at_arrival": open_at_arrival,
        "open_source": "google",
        "eta_iso": eta_dt.isoformat() if eta_dt is not None else None,
        "note": "google_primary",
    }


def _route_poi_v2_google_supply_candidates(
    points: list[dict[str, Any]],
    projected: list[dict[str, Any]],
    *,
    km_from: float,
    km_to: float,
    sample_step_km: float = 8.0,
    radius_m: float = 2000.0,
    ride_start_dt: datetime | None = None,
    avg_speed_kmh: float = 18.0,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    api_key = api_key or _route_poi_v2_google_api_key()
    if not api_key or not points or not projected:
        return []

    try:
        step_km = max(4.0, float(sample_step_km))
    except (TypeError, ValueError):
        step_km = 8.0

    sample_km = float(km_from)
    seen: dict[str, dict[str, Any]] = {}
    while sample_km <= float(km_to) + 1e-9:
        sample = _find_point_at_km(points, sample_km)
        try:
            places = _route_poi_v2_google_search_nearby(
                float(sample["lat"]),
                float(sample["lon"]),
                radius_m=radius_m,
                api_key=api_key,
            )
        except Exception as exc:
            log.warning("route_poi_analyze google places error at km %.2f: %s", sample_km, exc)
            sample_km += step_km
            continue

        for place in places:
            candidate = _route_poi_v2_google_place_to_candidate(
                place,
                projected=projected,
                ride_start_dt=ride_start_dt,
                avg_speed_kmh=avg_speed_kmh,
            )
            if candidate is None:
                continue
            key = str(candidate.get("google_place_id") or candidate.get("osm_id") or candidate.get("name") or "").strip().lower()
            if not key:
                key = f"{candidate.get('category')}:{candidate.get('route_km')}:{candidate.get('distance_to_track_m')}"
            existing = seen.get(key)
            if existing is None or _route_poi_v2_is_better_candidate(candidate, existing):
                seen[key] = candidate
        sample_km += step_km
        time.sleep(0.03)

    return list(seen.values())


def _route_poi_v2_build_query(
    bbox: dict[str, float],
    focus: str | None = None,
    timeout_sec: float = 30.0,
    *,
    include_supply: bool = True,
) -> str:
    bbox_s = _bbox_to_overpass_string(bbox)
    focus_mode = _route_poi_v2_focus_mode(focus)
    t = int(timeout_sec)
    parts = [f"[out:json][timeout:{t}];", "("]
    if focus_mode != "logistics":
        parts.append(f'  nwr["tourism"~"attraction|artwork|gallery|museum|viewpoint|theme_park|zoo|aquarium|picnic_site"]({bbox_s});')
        parts.append(f'  nwr["historic"]({bbox_s});')
    if include_supply:
        parts.append(f'  nwr["shop"~"supermarket|convenience|grocery|bakery|deli|butcher|greengrocer|pastry|farm|general"]({bbox_s});')
        parts.append(f'  nwr["amenity"~"marketplace|fuel|cafe|bar|restaurant|fast_food|pub|ice_cream|drinking_water|fountain"]({bbox_s});')
        parts.append(f'  nwr["vending"~"food|drinks"]({bbox_s});')
    parts.append(f'  nwr["drinking_water"="yes"]({bbox_s});')
    parts.append(f'  nwr["man_made"="water_tap"]({bbox_s});')
    parts.append(f'  node["place"~"city|town|village|hamlet"]({bbox_s});')
    parts.append(");")
    parts.append("out center tags;")
    return chr(10).join(parts) + chr(10)

def _geofabrik_cache_candidates(bbox: dict[str, float]) -> list[dict[str, Any]] | None:
    """Load POI from local Geofabrik cache if available for this bbox.
    Returns None if no cache found (fallback to Overpass).

    Generic: scans CACHE_DIR for any project's "*_{cat}.json" cache files
    (built via tools/rwgps/overpass_cache.py under any slug) and merges
    elements from all of them, filtered to the requested bbox. No
    project/event-specific slug or bbox is hardcoded here.
    """
    import json as _json
    from pathlib import Path as _Path

    CACHE_DIR = _Path("/opt/qbot/artifacts/overpass_cache")

    all_elements: list[dict] = []
    found_any = False
    for cat in ("water", "food", "attraction"):
        for cache_file in sorted(CACHE_DIR.glob(f"*_{cat}.json")):
            if not cache_file.exists():
                continue
            found_any = True
            data = _json.loads(cache_file.read_text(encoding="utf-8"))
            for el in data.get("elements", []):
                lat = float(el.get("lat") or 0)
                lon = float(el.get("lon") or 0)
                if not lat or not lon:
                    continue
                # filter to bbox
                if lat < bbox["min_lat"] or lat > bbox["max_lat"]:
                    continue
                if lon < bbox["min_lon"] or lon > bbox["max_lon"]:
                    continue
                # normalize tags from geofabrik CSV format
                tags = el.get("tags") or {}
                normalized_tags: dict[str, str] = {}
                for k, v in tags.items():
                    if v and str(v).strip():
                        # map CSV column names back to OSM tag names
                        osm_key = {"name_en": "name:en", "name_it": "name:it"}.get(k, k)
                        normalized_tags[osm_key] = str(v).strip()
                all_elements.append({
                    "type": el.get("type", "node"),
                    "id": el.get("id"),
                    "lat": lat,
                    "lon": lon,
                    "tags": normalized_tags,
                })

    if not all_elements:
        # Brak elementow w bbox ma oznaczac brak cache, zeby spasc do Overpass.
        return None
    return all_elements


def _route_poi_v2_overpass_candidates(query: str, timeout_sec: float, bbox: dict[str, float] | None = None) -> list[dict[str, Any]]:
    # Try local Geofabrik cache first
    if bbox is not None:
        cached = _geofabrik_cache_candidates(bbox)
        if cached is not None:
            return cached

    timeout = httpx.Timeout(timeout_sec, connect=8.0, read=timeout_sec, write=8.0, pool=8.0)
    last_error: Exception | None = None
    for endpoint in OVERPASS_URLS:
        try:
            resp = httpx.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=timeout,
            )
            if resp.status_code in {429, 502, 503, 504}:
                last_error = httpx.HTTPStatusError(
                    f"Overpass HTTP {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                continue
            resp.raise_for_status()
            payload = resp.json()
            return [element for element in payload.get("elements", []) if isinstance(element, dict)]
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return []


_ROUTE_POI_CATEGORY_PRIORITY = {
    "hard_resupply": 0,
    "water": 1,
    "soft_food_stop": 2,
    "attraction": 3,
    "town": 9,
}


def _route_poi_v2_focus_mode(focus: str | None) -> str:
    focus_norm = _route_poi_v2_norm_text(focus)
    if focus_norm in {"food_only", "hard_resupply", "logistics"}:
        return "logistics"
    if focus_norm in {"all", "attractions", ""}:
        return "all"
    return focus_norm or "all"


def _route_poi_v2_requested_categories(focus: str | None) -> list[str]:
    categories = ["hard_resupply", "soft_food_stop", "water", "town_fallback_check"]
    if _route_poi_v2_focus_mode(focus) != "logistics":
        categories.insert(3, "attraction")
    return categories


def _route_poi_v2_chunk_id(km_from: float, km_to: float) -> str:
    return f"{float(km_from):06.2f}_{float(km_to):06.2f}"


def _route_poi_v2_report_stem(source_slug: str, km_from: float, km_to: float, suffix: str | None = None) -> str:
    stem = f"poi_analysis_{source_slug}_{int(float(km_from)):02d}_{int(float(km_to)):02d}"
    if suffix:
        stem = f"{stem}_{suffix}"
    return stem


def _route_poi_v2_category_priority(category: str | None) -> int:
    return _ROUTE_POI_CATEGORY_PRIORITY.get(str(category or ""), 50)


def _route_poi_v2_is_better_candidate(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    cand_priority = _route_poi_v2_category_priority(candidate.get("category"))
    exist_priority = _route_poi_v2_category_priority(existing.get("category"))
    if cand_priority != exist_priority:
        return cand_priority < exist_priority
    cand_dist = float(candidate.get("distance_to_track_m") or 10**9)
    exist_dist = float(existing.get("distance_to_track_m") or 10**9)
    if cand_dist != exist_dist:
        return cand_dist < exist_dist
    cand_route = float(candidate.get("route_km") or 10**9)
    exist_route = float(existing.get("route_km") or 10**9)
    if cand_route != exist_route:
        return cand_route < exist_route
    return _route_poi_v2_norm_text(candidate.get("name")) < _route_poi_v2_norm_text(existing.get("name"))


def _route_poi_v2_dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []

    ordered = sorted(items, key=lambda x: (float(x.get("route_km") or 0), float(x.get("distance_to_track_m") or 10**9), str(x.get("name") or "")))
    by_osm: dict[str, dict[str, Any]] = {}
    nameless: list[dict[str, Any]] = []
    for item in ordered:
        osm_id = item.get("osm_id")
        if osm_id not in (None, ""):
            key = str(osm_id)
            existing = by_osm.get(key)
            if existing is None:
                fresh = dict(item)
                fresh["cluster_size"] = int(fresh.get("cluster_size", 1) or 1)
                by_osm[key] = fresh
            else:
                existing["cluster_size"] = int(existing.get("cluster_size", 1)) + 1
                if _route_poi_v2_is_better_candidate(item, existing):
                    replacement = dict(item)
                    replacement["cluster_size"] = int(existing.get("cluster_size", 1))
                    by_osm[key] = replacement
        else:
            nameless.append(dict(item))

    grouped = list(by_osm.values()) + nameless
    merged: list[dict[str, Any]] = []
    proximity_m = 80.0
    route_km_window = 0.15
    for item in sorted(grouped, key=lambda x: (float(x.get("route_km") or 0), float(x.get("distance_to_track_m") or 10**9), str(x.get("name") or ""))):
        item = dict(item)
        item.setdefault("cluster_size", 1)
        item_name = _route_poi_v2_norm_text(item.get("name"))
        placed = False
        for idx, existing in enumerate(merged):
            if item_name and item_name == _route_poi_v2_norm_text(existing.get("name")):
                if abs(float(item.get("route_km") or 0) - float(existing.get("route_km") or 0)) <= route_km_window:
                    if _haversine_km(float(item.get("lat") or 0.0), float(item.get("lon") or 0.0), float(existing.get("lat") or 0.0), float(existing.get("lon") or 0.0)) * 1000.0 <= proximity_m:
                        existing["cluster_size"] = int(existing.get("cluster_size", 1)) + 1
                        if _route_poi_v2_is_better_candidate(item, existing):
                            replacement = dict(item)
                            replacement["cluster_size"] = int(existing.get("cluster_size", 1))
                            merged[idx] = replacement
                        placed = True
                        break
        if not placed:
            merged.append(item)
    return merged


def _route_poi_v2_missing_chunk_entry(
    *,
    route_id: str | None,
    artifact_id: str | None,
    source_path: str | None,
    km_from: float,
    km_to: float,
    bbox: dict[str, float],
    focus: str | None,
    categories_requested: list[str],
    buffers: dict[str, float],
    reason: str,
    retry_chunk_id: str | None,
    timeout_sec: float,
    overpass_timeout_sec: float,
    output_format: str,
) -> dict[str, Any]:
    chunk_id = retry_chunk_id or _route_poi_v2_chunk_id(km_from, km_to)
    retry_payload_json = {
        "route_id": route_id,
        "artifact_id": artifact_id,
        "path": source_path,
        "km_from": round(float(km_from), 3),
        "km_to": round(float(km_to), 3),
        "buffers": buffers,
        "focus": focus,
        "output_format": output_format,
        "retry_mode": True,
        "retry_chunk_id": chunk_id,
        "timeout_sec": timeout_sec,
    }
    return {
        "chunk_id": chunk_id,
        "km_from": round(float(km_from), 3),
        "km_to": round(float(km_to), 3),
        "bbox": dict(bbox),
        "categories_requested": list(categories_requested),
        "reason": reason,
        "attempts": 0,
        "timeout_sec": timeout_sec,
        "overpass_timeout_sec": overpass_timeout_sec,
        "retry_payload_json": retry_payload_json,
    }


def _route_poi_v2_load_analysis_payload(artifact_id: str) -> dict[str, Any]:
    from qbot3.artifacts.store import get_artifact as _get_artifact

    record = _get_artifact(artifact_id)
    if not record:
        raise FileNotFoundError(f"artifact not found: {artifact_id}")
    file_path = str(record.get("file_path") or "").strip()
    if not file_path:
        raise FileNotFoundError(f"artifact {artifact_id} has no file_path")
    rel = file_path.replace("\\", "/").lstrip("/")
    abs_path = (ARTIFACTS_ROOT / rel).resolve()
    candidates = [abs_path]
    if abs_path.suffix.lower() == ".md":
        candidates.insert(0, abs_path.with_suffix(".json"))
    else:
        candidates.append(abs_path.with_suffix(".json"))
    for candidate in candidates:
        if candidate.exists() and candidate.suffix.lower() == ".json":
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload.setdefault("source_artifact_id", artifact_id)
                payload.setdefault("source_report_path", str(abs_path))
                payload.setdefault("analysis_artifact_id", artifact_id)
                return payload
    raise FileNotFoundError(f"analysis JSON sidecar not found for artifact {artifact_id}: {abs_path.with_suffix('.json')}")


def _route_poi_v2_merge_analysis_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if not payloads:
        return {"ok": False, "status": "ERROR", "error": "No analysis payloads to merge"}

    merged_route_id = None
    merged_project_id = None
    merged_source_path = ""
    merged_artifact_id = None
    km_from = None
    km_to = None
    buffers = {}
    focus = None
    output_format = "md"
    all_chunks: dict[str, dict[str, Any]] = {}
    missing_chunks: dict[str, dict[str, Any]] = {}
    merged_items: dict[str, list[dict[str, Any]]] = {
        "hard_resupply": [],
        "soft_food_stop": [],
        "water": [],
        "attraction": [],
        "town_fallback_check": [],
    }
    timings: dict[str, float] = {
        "gpx_load_ms": 0.0,
        "track_projection_ms": 0.0,
        "overpass_ms": 0.0,
        "filter_ms": 0.0,
        "town_fallback_ms": 0.0,
        "merge_ms": 0.0,
    }

    t_merge = time.perf_counter()
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        merged_route_id = merged_route_id or payload.get("route_id")
        merged_project_id = merged_project_id or payload.get("project_id")
        merged_source_path = merged_source_path or str(payload.get("source_path") or "")
        merged_artifact_id = merged_artifact_id or payload.get("artifact_id")
        km_from = payload.get("km_from") if km_from is None else min(float(km_from), float(payload.get("km_from") or km_from))
        km_to = payload.get("km_to") if km_to is None else max(float(km_to), float(payload.get("km_to") or km_to))
        buffers = buffers or dict(payload.get("buffers") or {})
        focus = focus or payload.get("focus")
        output_format = str(payload.get("output_format", output_format) or output_format)
        for key in merged_items:
            merged_items[key].extend(list(payload.get(key) or []))
        for chunk in list(payload.get("chunks") or []):
            if not isinstance(chunk, dict):
                continue
            chunk_id = str(chunk.get("chunk_id") or f"{chunk.get('chunk_from_km', '')}_{chunk.get('chunk_to_km', '')}").strip()
            if not chunk_id:
                continue
            existing = all_chunks.get(chunk_id)
            if existing is None:
                all_chunks[chunk_id] = dict(chunk)
            else:
                if str(chunk.get("status", "")).upper() == "OK" and str(existing.get("status", "")).upper() != "OK":
                    all_chunks[chunk_id] = dict(chunk)
        for missing in list(payload.get("missing_chunks") or []):
            if not isinstance(missing, dict):
                continue
            chunk_id = str(missing.get("chunk_id") or "").strip()
            if not chunk_id:
                continue
            missing_chunks[chunk_id] = dict(missing)

    successful_chunk_ids = {chunk_id for chunk_id, chunk in all_chunks.items() if str(chunk.get("status", "")).upper() == "OK"}
    for chunk_id in list(missing_chunks):
        if chunk_id in successful_chunk_ids:
            missing_chunks.pop(chunk_id, None)

    successful_ranges: list[tuple[float, float]] = []
    for chunk in all_chunks.values():
        if str(chunk.get("status", "")).upper() != "OK":
            continue
        try:
            start = float(chunk.get("chunk_from_km", chunk.get("km_from", 0)) or 0)
            end = float(chunk.get("chunk_to_km", chunk.get("km_to", 0)) or 0)
        except Exception:
            continue
        if end < start:
            start, end = end, start
        successful_ranges.append((start, end))
    successful_ranges.sort()
    merged_ranges: list[tuple[float, float]] = []
    for start, end in successful_ranges:
        if not merged_ranges or start > merged_ranges[-1][1] + 1e-9:
            merged_ranges.append((start, end))
        else:
            merged_ranges[-1] = (merged_ranges[-1][0], max(merged_ranges[-1][1], end))

    def _covered(start: float, end: float) -> bool:
        for range_start, range_end in merged_ranges:
            if start >= range_start - 1e-9 and end <= range_end + 1e-9:
                return True
        return False

    for chunk_id in list(missing_chunks):
        missing = missing_chunks.get(chunk_id) or {}
        try:
            start = float(missing.get("km_from", 0) or 0)
            end = float(missing.get("km_to", 0) or 0)
        except Exception:
            continue
        if _covered(start, end):
            missing_chunks.pop(chunk_id, None)

    for key in ("hard_resupply", "soft_food_stop", "water", "attraction"):
        merged_items[key] = _route_poi_v2_mark_clusters(_route_poi_v2_dedupe(merged_items[key]))
        merged_items[key].sort(key=lambda item: (float(item.get("route_km") or 0), float(item.get("distance_to_track_m") or 10**9)))

    open_window_enabled = bool((buffers or {}).get("open_window", False))
    if open_window_enabled:
        ride_start_raw = (buffers or {}).get("ride_start")
        ride_start_dt: datetime | None = None
        if ride_start_raw:
            try:
                ride_start_dt = datetime.fromisoformat(str(ride_start_raw).replace("Z", "+00:00"))
            except ValueError:
                ride_start_dt = None
        try:
            avg_speed_kmh = float((buffers or {}).get("avg_speed_kmh", 18.0))
        except (TypeError, ValueError):
            avg_speed_kmh = 18.0
        try:
            google_hours_flag = bool((buffers or {}).get("google_hours", True))
        except Exception:
            google_hours_flag = True
        try:
            from tools.rwgps.poi_open_window import enrich_open_window, _api_key

            google_api_key = _api_key()
            use_google = bool(google_hours_flag and google_api_key)
            enrich_open_window(
                merged_items["hard_resupply"],
                ride_start=ride_start_dt,
                avg_speed_kmh=avg_speed_kmh,
                use_google=use_google,
                api_key=google_api_key,
            )
            enrich_open_window(
                merged_items["soft_food_stop"],
                ride_start=ride_start_dt,
                avg_speed_kmh=avg_speed_kmh,
                use_google=use_google,
                api_key=google_api_key,
            )
            enrich_open_window(
                merged_items["water"],
                ride_start=ride_start_dt,
                avg_speed_kmh=avg_speed_kmh,
                use_google=use_google,
                api_key=google_api_key,
            )
            if "shop" in merged_items:
                enrich_open_window(
                    merged_items["shop"],
                    ride_start=ride_start_dt,
                    avg_speed_kmh=avg_speed_kmh,
                    use_google=use_google,
                    api_key=google_api_key,
                )
        except Exception as exc:
            log.warning("route_poi_analyze merge open_window enrichment failed: %s", exc)

    town_items = _route_poi_v2_mark_clusters(_route_poi_v2_dedupe(merged_items["town_fallback_check"]))
    town_items.sort(key=lambda item: (float(item.get("route_km") or 0), float(item.get("distance_to_track_m") or 10**9)))
    for town in town_items:
        nearby_hard = [
            item for item in merged_items["hard_resupply"]
            if abs(float(item.get("route_km") or 0) - float(town.get("route_km") or 0)) <= 2.0
            and float(item.get("distance_to_track_m") or 10**9) <= max(
                float((buffers or {}).get("hard_resupply_m", 400)),
                float((buffers or {}).get("soft_food_m", 400)),
                1000.0,
            )
        ]
        town["hard_resupply_found"] = bool(nearby_hard)
        town["hard_resupply_names"] = ", ".join(str(item.get("name") or "") for item in nearby_hard[:5])
    timings["merge_ms"] = round((time.perf_counter() - t_merge) * 1000.0, 1)

    summary = {
        "hard_resupply": len(merged_items["hard_resupply"]),
        "soft_food_stop": len(merged_items["soft_food_stop"]),
        "water": len(merged_items["water"]),
        "attraction": len(merged_items["attraction"]),
        "town": len(town_items),
    }
    missing_list = sorted(
        list(missing_chunks.values()),
        key=lambda item: (float(item.get("km_from") or 0), float(item.get("km_to") or 0), str(item.get("chunk_id") or "")),
    )

    status = "PARTIAL" if missing_list else "OK"
    result: dict[str, Any] = {
        "ok": True,
        "status": status,
        "analysis_status": status,
        "route_id": merged_route_id,
        "project_id": merged_project_id,
        "artifact_id": merged_artifact_id,
        "source_path": merged_source_path,
        "km_from": km_from,
        "km_to": km_to,
        "focus": _route_poi_v2_focus_mode(focus),
        "buffers": {
            "attractions_m": float((buffers or {}).get("attractions_m", 1000)),
            "hard_resupply_m": float((buffers or {}).get("hard_resupply_m", (buffers or {}).get("food_m", 400))),
            "soft_food_m": float((buffers or {}).get("soft_food_m", (buffers or {}).get("food_m", 400))),
            "water_m": float((buffers or {}).get("water_m", 200)),
            "open_window": bool((buffers or {}).get("open_window", False)),
            "ride_start": (buffers or {}).get("ride_start"),
            "avg_speed_kmh": float((buffers or {}).get("avg_speed_kmh", 18.0)),
            "google_hours": bool((buffers or {}).get("google_hours", True)),
        },
        "track_points_count": None,
        "distance_km": None,
        "bbox": None,
        "chunks": list(all_chunks.values()),
        "missing_chunks": missing_list,
        "missing_chunks_count": len(missing_list),
        "timings_ms": timings,
        "summary": summary,
        "hard_resupply": merged_items["hard_resupply"][:15],
        "soft_food_stop": merged_items["soft_food_stop"][:12],
        "water": merged_items["water"][:12],
        "attractions": merged_items["attraction"][:15],
        "town_fallback_check": town_items[:20],
        "report_title": f"POI analysis — route {merged_route_id or merged_artifact_id or merged_source_path}",
        "warnings": [
            "candidate counts are filtered by route distance and per-category distance-to-track buffers",
        ],
    }
    if missing_list:
        result["warnings"].append("analysis truncated due to timeout budget; partial artifact written")
        result["warnings"].append("missing_chunks include retry_payload_json for targeted retries")
    result["markdown"] = _route_poi_v2_build_markdown(result)
    result["timings_ms"]["total_ms"] = round(sum(v for v in timings.values()) if timings else 0.0, 1)
    result["report_tag"] = "FINAL" if not missing_list else None
    return result


def _route_poi_v2_build_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# {result.get('report_title', 'Route POI analysis')}")
    lines.append("")
    lines.append(f"- route_id: {result.get('route_id') or ''}")
    lines.append(f"- project_id: {result.get('project_id') or ''}")
    if result.get("focus"):
        lines.append(f"- focus: {result.get('focus')}")
    if result.get("artifact_id"):
        lines.append(f"- artifact_id: {result.get('artifact_id')}")
    lines.append(f"- source_path: {result.get('source_path')}")
    lines.append(f"- km_from: {result.get('km_from')}")
    lines.append(f"- km_to: {result.get('km_to')}")
    lines.append(
        "- buffers_m: "
        f"attractions={result.get('buffers', {}).get('attractions_m')}, "
        f"hard_resupply={result.get('buffers', {}).get('hard_resupply_m')}, "
        f"soft_food={result.get('buffers', {}).get('soft_food_m')}, "
        f"water={result.get('buffers', {}).get('water_m')}"
    )
    lines.append(f"- track_points: {result.get('track_points_count')}")
    lines.append(f"- distance_km: {result.get('distance_km')}")
    if result.get("status"):
        lines.append(f"- analysis_status: {result.get('status')}")
    lines.append(f"- missing_chunks_count: {len(result.get('missing_chunks') or [])}")
    if result.get("report_tag"):
        lines.append(f"- report_tag: {result.get('report_tag')}")
    timings = result.get("timings_ms") or {}
    if timings:
        lines.append(f"- timings_ms: {json.dumps(timings, ensure_ascii=False)}")
    lines.append("")
    lines.append("## Summary")
    summary = result.get("summary") or {}
    lines.append(f"- hard_resupply: {summary.get('hard_resupply', 0)}")
    lines.append(f"- soft_food_stop: {summary.get('soft_food_stop', 0)}")
    lines.append(f"- water: {summary.get('water', 0)}")
    lines.append(f"- attractions: {summary.get('attraction', 0)}")
    lines.append(f"- towns: {summary.get('town', 0)}")
    lines.append("")

    def _table(title: str, rows: list[dict[str, Any]], extra_cols: list[str] | None = None) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not rows:
            lines.append("_No candidates found._")
            lines.append("")
            return
        extra_cols = extra_cols or []
        header = ["name", "category", "lat", "lon", "route_km", "distance_to_track_m", "source_tags", "note"] + extra_cols
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join("---" if col in {"name", "category", "source_tags", "note"} else "---:" for col in header) + " |")
        for row in rows:
            values = [str(row.get(col, "")) for col in header]
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")

    _table("Hard resupply", result.get("hard_resupply", []), ["cluster_size"])
    _table("Soft food stop", result.get("soft_food_stop", []), ["cluster_size"])
    _table("Water", result.get("water", []), ["cluster_size"])
    _table("Attractions", result.get("attractions", []), ["cluster_size"])

    lines.append("## Missing chunks")
    lines.append("")
    missing_chunks = result.get("missing_chunks") or []
    if not missing_chunks:
        lines.append("_No missing chunks._")
        lines.append("")
    else:
        lines.append("| chunk_id | km_from | km_to | bbox | categories requested | reason | retry_payload_json |")
        lines.append("| --- | ---: | ---: | --- | --- | --- | --- |")
        for row in missing_chunks:
            lines.append(
                "| "
                f"{row.get('chunk_id', '')} | {row.get('km_from', '')} | {row.get('km_to', '')} | "
                f"{json.dumps(row.get('bbox', {}), ensure_ascii=False)} | "
                f"{', '.join(row.get('categories_requested', []) or [])} | {row.get('reason', '')} | "
                f"{json.dumps(row.get('retry_payload_json', {}), ensure_ascii=False)} |"
            )
        lines.append("")

    lines.append("## Town fallback check")
    lines.append("")
    town_rows = result.get("town_fallback_check", [])
    if not town_rows:
        lines.append("_No town nodes found._")
        lines.append("")
    else:
        lines.append("| name | category | lat | lon | route_km | distance_to_track_m | hard_resupply_found | hard_resupply_names | source_tags | note |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |")
        for row in town_rows:
            lines.append(
                "| "
                f"{row.get('name', '')} | {row.get('category', '')} | {row.get('lat', '')} | {row.get('lon', '')} | "
                f"{row.get('route_km', '')} | {row.get('distance_to_track_m', '')} | "
                f"{row.get('hard_resupply_found', '')} | {row.get('hard_resupply_names', '')} | "
                f"{row.get('source_tags', '')} | {row.get('note', '')} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _analyze_route_poi_artifact_legacy(
    file_path: str | Path,
    *,
    route_id: str | None = None,
    artifact_id: str | None = None,
    project_id: str | None = None,
    km_from: float,
    km_to: float,
    buffers: dict[str, float] | None = None,
    output_format: str = "md",
) -> dict[str, Any]:
    """Improved POI analysis with chunked Overpass queries and partial results."""
    log = logging.getLogger("route_poi_analyze")
    t_start = time.perf_counter()
    path = Path(file_path)
    if not path.exists():
        return {"ok": False, "status": "ERROR", "error": f"File not found: {path}"}
    if km_to < km_from:
        return {"ok": False, "status": "ERROR", "error": "km_to must be >= km_from"}

    buffers = buffers or {}
    attractions_m = float(buffers.get("attractions_m", 1000))
    hard_resupply_m = float(buffers.get("hard_resupply_m", buffers.get("food_m", 400)))
    soft_food_m = float(buffers.get("soft_food_m", buffers.get("food_m", 400)))
    water_m = float(buffers.get("water_m", 200))
    max_buffer_m = max(attractions_m, hard_resupply_m, soft_food_m, water_m)
    chunk_km = float(buffers.get("chunk_km", 12.0))
    overlap_km = max(1.0, float(buffers.get("chunk_overlap_km", 1.0)))
    overpass_timeout_sec = float(buffers.get("overpass_timeout_sec", 20.0))
    deadline_sec = float(buffers.get("analysis_timeout_sec", 80.0))

    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    points = _parse_gpx_file_detailed(path)
    if not points:
        return {"ok": False, "status": "ERROR", "error": f"No track points in {path}"}
    timings["gpx_load_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)

    t1 = time.perf_counter()
    projected = _track_projection(points)
    total_km = round(projected[-1]["cum_m"] / 1000.0, 3)
    timings["track_projection_ms"] = round((time.perf_counter() - t1) * 1000.0, 1)
    bbox = _track_bbox(points)

    chunks: list[dict[str, Any]] = []
    chunk_start = float(km_from)
    chunk_end_limit = float(km_to)
    if chunk_km <= 0:
        chunk_km = max(1.0, float(km_to - km_from) or 1.0)
    step_km = max(0.5, chunk_km - overlap_km)
    all_candidates: list[dict[str, Any]] = []
    town_candidates: list[dict[str, Any]] = []
    t_overpass = time.perf_counter()
    partial = False

    while chunk_start <= chunk_end_limit + 1e-9:
        if (time.perf_counter() - t_start) > deadline_sec:
            partial = True
            log.info("route_poi_analyze deadline reached before chunk start %.2f", chunk_start)
            break
        chunk_stop = min(chunk_end_limit, chunk_start + chunk_km)
        segment = _track_segment_projection(projected, chunk_start, chunk_stop)
        if len(segment) < 2:
            chunk_start += step_km
            continue

        segment_bbox = _expand_bbox(_track_bbox(segment), max_buffer_m + 500.0)
        query = _route_poi_v2_build_query(segment_bbox)
        query_started = time.perf_counter()
        try:
            raw_elements = _route_poi_v2_overpass_candidates(query, overpass_timeout_sec)
        except Exception as exc:
            partial = True
            chunks.append({
                "chunk_from_km": round(chunk_start, 3),
                "chunk_to_km": round(chunk_stop, 3),
                "status": "ERROR",
                "error": str(exc)[:200],
                "candidates": 0,
            })
            log.warning("route_poi_analyze overpass error chunk %.2f-%.2f: %s", chunk_start, chunk_stop, exc)
            chunk_start += step_km
            continue

        chunk_candidates: list[dict[str, Any]] = []
        chunk_town_candidates: list[dict[str, Any]] = []
        for element in raw_elements:
            tags = element.get("tags") or {}
            if not isinstance(tags, dict):
                continue
            lat, lon = _element_lat_lon(element)
            if lat is None or lon is None:
                continue
            category, note = _route_poi_v2_classify(tags)
            if not category:
                continue

            nearest = _nearest_track_projection(projected, lat, lon)
            route_km = nearest.get("route_km")
            distance_to_track_m = nearest.get("distance_to_track_m")
            if route_km is None or distance_to_track_m is None:
                continue
            if route_km < km_from or route_km > km_to:
                continue

            source_category = category
            if category == "hard_resupply" and float(distance_to_track_m) > hard_resupply_m:
                continue
            if category == "soft_food_stop" and float(distance_to_track_m) > soft_food_m:
                continue
            if category == "water" and float(distance_to_track_m) > water_m:
                continue
            if category == "attraction" and float(distance_to_track_m) > attractions_m:
                continue

            tags_snapshot = _element_source_tags(element)
            item = {
                "osm_type": element.get("type"),
                "osm_id": element.get("id"),
                "name": _route_poi_v2_name(element, tags, source_category),
                "category": source_category,
                "lat": round(float(lat), 6),
                "lon": round(float(lon), 6),
                "route_km": route_km,
                "distance_to_track_m": distance_to_track_m,
                "source_tags": _route_poi_v2_source_tags(tags_snapshot),
                "note": note,
            }
            if category == "town":
                chunk_town_candidates.append(item)
            else:
                chunk_candidates.append(item)

        chunk_duration_ms = round((time.perf_counter() - query_started) * 1000.0, 1)
        chunks.append({
            "chunk_from_km": round(chunk_start, 3),
            "chunk_to_km": round(chunk_stop, 3),
            "status": "OK",
            "overpass_candidates": len(raw_elements),
            "poi_candidates": len(chunk_candidates),
            "town_candidates": len(chunk_town_candidates),
            "duration_ms": chunk_duration_ms,
        })
        all_candidates.extend(chunk_candidates)
        town_candidates.extend(chunk_town_candidates)

        log.info(
            "route_poi_analyze chunk %.2f-%.2f finished in %.1fms: raw=%s poi=%s town=%s",
            chunk_start,
            chunk_stop,
            chunk_duration_ms,
            len(raw_elements),
            len(chunk_candidates),
            len(chunk_town_candidates),
        )
        if (time.perf_counter() - t_start) > deadline_sec:
            partial = True
            break
        chunk_start += step_km

    timings["overpass_ms"] = round((time.perf_counter() - t_overpass) * 1000.0, 1)

    t_filter = time.perf_counter()
    deduped = _route_poi_v2_dedupe(all_candidates)
    grouped: dict[str, list[dict[str, Any]]] = {"hard_resupply": [], "soft_food_stop": [], "water": [], "attraction": []}
    for item in deduped:
        grouped.setdefault(item["category"], []).append(item)
    for key in grouped:
        grouped[key] = _route_poi_v2_mark_clusters(grouped[key])
        grouped[key].sort(key=lambda item: (float(item.get("route_km") or 0), float(item.get("distance_to_track_m") or 10**9)))
    timings["filter_ms"] = round((time.perf_counter() - t_filter) * 1000.0, 1)

    t_town = time.perf_counter()
    town_deduped = _route_poi_v2_dedupe(town_candidates)
    town_deduped.sort(key=lambda item: (float(item.get("route_km") or 0), float(item.get("distance_to_track_m") or 10**9)))
    for town in town_deduped:
        nearby_hard = [
            item for item in grouped.get("hard_resupply", [])
            if abs(float(item.get("route_km") or 0) - float(town.get("route_km") or 0)) <= 2.0
            and float(item.get("distance_to_track_m") or 10**9) <= max(hard_resupply_m, soft_food_m, 1000.0)
        ]
        town["hard_resupply_found"] = bool(nearby_hard)
        town["hard_resupply_names"] = ", ".join([str(item.get("name") or "") for item in nearby_hard[:5]])
    timings["town_fallback_ms"] = round((time.perf_counter() - t_town) * 1000.0, 1)

    raw_counts = {
        "hard_resupply": len(grouped.get("hard_resupply", [])),
        "soft_food_stop": len(grouped.get("soft_food_stop", [])),
        "water": len(grouped.get("water", [])),
        "attraction": len(grouped.get("attraction", [])),
        "town": len(town_deduped),
    }
    limited = {
        "hard_resupply": grouped.get("hard_resupply", [])[:15],
        "soft_food_stop": grouped.get("soft_food_stop", [])[:12],
        "water": grouped.get("water", [])[:12],
        "attraction": grouped.get("attraction", [])[:15],
        "town_fallback_check": town_deduped[:20],
    }

    result: dict[str, Any] = {
        "ok": True,
        "status": "PARTIAL" if partial else "OK",
        "route_id": route_id,
        "project_id": project_id,
        "artifact_id": artifact_id,
        "source_path": str(path),
        "km_from": km_from,
        "km_to": km_to,
        "buffers": {
            "attractions_m": attractions_m,
            "hard_resupply_m": hard_resupply_m,
            "soft_food_m": soft_food_m,
            "water_m": water_m,
        },
        "track_points_count": len(projected),
        "distance_km": total_km,
        "bbox": bbox,
        "chunks": chunks,
        "timings_ms": timings,
        "summary": raw_counts,
        "hard_resupply": limited["hard_resupply"],
        "soft_food_stop": limited["soft_food_stop"],
        "water": limited["water"],
        "attractions": limited["attraction"],
        "town_fallback_check": limited["town_fallback_check"],
        "report_title": f"POI analysis — route {route_id or artifact_id or path.stem}",
        "warnings": [],
    }
    if partial:
        result["warnings"].append("analysis truncated due to timeout budget; partial artifact written")
    result["warnings"].append(
        "candidate counts are filtered by route distance and per-category distance-to-track buffers"
    )
    result["markdown"] = _route_poi_v2_build_markdown(result)
    result["timings_ms"]["total_ms"] = round((time.perf_counter() - t_start) * 1000.0, 1)
    if output_format == "json":
        result["output_format"] = "json"
    else:
        result["output_format"] = "md"
    return result
