#!/usr/bin/env python3
"""Lokalny parser tras GPX/JSON dla QBot.

Parsuje geometrię lokalnie - nie wysyła pełnych danych do LLM.
Dla zadanych kilometrów wylicza punkty na śladzie i sprawdza noclegi przez Nominatim.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

ARTIFACTS_ROOT = Path("/opt/qbot/artifacts")
NOMINATIM_URL = "https://nominatim.openstreetmap.org"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "QBot/1.0 (personal assistant; michal@qbot)"


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
        "climbs": climbs,
        "descents": descents,
    }
