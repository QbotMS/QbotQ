#!/usr/bin/env python3
"""Deterministic analysis of tourist attractions within 1km of a GPX track.

Usage:
  .venv/bin/python scripts/analyze_route_poi_within_1km.py --route-id 55395119 --project-id tuscany_2026 --max-distance-m 1000 --limit 10
"""

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path("/opt/qbot/app")
ARTIFACTS_DIR = Path("/opt/qbot/artifacts")
sys.path.insert(0, str(APP_DIR))

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "QBot/1.0 (route poi analysis; michal@qbot)"

POI_QUERY_TEMPLATE = """
[out:json][timeout:45];
(
  node["tourism"="attraction"]{bbox};
  node["tourism"="museum"]{bbox};
  node["tourism"="viewpoint"]{bbox};
  node["tourism"="artwork"]{bbox};
  node["tourism"="information"]{bbox};
  node["tourism"="gallery"]{bbox};
  node["historic"]{bbox};
  node["ruins"]{bbox};
  node["castle_type"]{bbox};
  node["amenity"="place_of_worship"]{bbox};
  node["natural"="peak"]{bbox};
  node["natural"="viewpoint"]{bbox};
  node["natural"="cave_entrance"]{bbox};
  node["leisure"="park"]{bbox};
  node["leisure"="garden"]{bbox};
  way["tourism"="attraction"]{bbox};
  way["tourism"="museum"]{bbox};
  way["tourism"="viewpoint"]{bbox};
  way["tourism"="artwork"]{bbox};
  way["historic"]{bbox};
  way["ruins"]{bbox};
  way["castle_type"]{bbox};
  way["amenity"="place_of_worship"]{bbox};
  way["natural"="peak"]{bbox};
  way["natural"="viewpoint"]{bbox};
  way["natural"="cave_entrance"]{bbox};
  way["leisure"="park"]{bbox};
  way["leisure"="garden"]{bbox};
);
out center tags 500;
""".strip()


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _parse_coord(val: Any) -> float | None:
    try:
        v = float(val)
        if math.isfinite(v):
            return v
    except (TypeError, ValueError):
        pass
    return None


def get_track_geometry(route_id: str) -> dict:
    from tools.rwgps.client import parse_gpx_artifact_geometry

    result = parse_gpx_artifact_geometry(route_id=route_id)
    if not result.get("ok"):
        raise RuntimeError(f"parse_gpx_artifact_geometry failed: {result.get('status')} – {result.get('error')}")
    return result


def fetch_overpass_pois(west: float, south: float, east: float, north: float) -> list[dict]:
    bbox_str = f"({south},{west},{north},{east})"
    query = POI_QUERY_TEMPLATE.format(bbox=bbox_str)

    import httpx
    from urllib.parse import urlencode

    try:
        with httpx.Client(timeout=60) as c:
            r = c.post(
                OVERPASS_URL,
                content=urlencode({"data": query}).encode("utf-8"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": USER_AGENT,
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        raise RuntimeError(f"Overpass API error: {exc}")

    elements = data.get("elements", [])
    if not elements:
        return []

    pois = []
    for el in elements:
        tags = el.get("tags") or {}
        osm_type = el.get("type", "node")
        osm_id = el.get("id")

        lat = _parse_coord(el.get("lat"))
        lon = _parse_coord(el.get("lon"))
        if lat is None or lon is None:
            center = el.get("center") or {}
            lat = _parse_coord(center.get("lat"))
            lon = _parse_coord(center.get("lon"))
        if lat is None or lon is None:
            continue

        name = tags.get("name", "").strip()

        category = _classify_poi_category(tags)
        if not category:
            continue

        description = _build_description(tags)

        pois.append({
            "name": name or None,
            "category": category,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "osm_type": osm_type,
            "osm_id": osm_id,
            "tags": {k: v for k, v in tags.items() if k in ("tourism", "historic", "ruins", "castle_type",
                                                              "amenity", "natural", "leisure", "name", "description",
                                                              "historic:civilization", "site_type", "museum",
                                                              "artwork_type", "wikipedia", "wheelchair")},
            "description": description,
        })

    return pois


def _classify_poi_category(tags: dict) -> str | None:
    tourism = (tags.get("tourism") or "").lower()
    historic = (tags.get("historic") or "").lower()
    ruins = (tags.get("ruins") or "").lower()
    castle_type = (tags.get("castle_type") or "").lower()
    amenity = (tags.get("amenity") or "").lower()
    natural = (tags.get("natural") or "").lower()
    leisure = (tags.get("leisure") or "").lower()

    if tourism in ("attraction", "museum", "viewpoint", "artwork", "gallery", "information"):
        return f"tourism={tourism}"
    if historic:
        return f"historic={historic}"
    if ruins and ruins != "no":
        return f"ruins={ruins}"
    if castle_type:
        return f"castle_type={castle_type}"
    if amenity == "place_of_worship":
        return "amenity=place_of_worship"
    if natural in ("peak", "viewpoint", "cave_entrance"):
        return f"natural={natural}"
    if leisure in ("park", "garden"):
        return f"leisure={leisure}"
    return None


def _build_description(tags: dict) -> str:
    parts = []
    desc = tags.get("description") or tags.get("historic") or tags.get("ruins") or ""
    if desc and isinstance(desc, str) and desc.strip():
        parts.append(desc.strip()[:120])
    if tags.get("wikipedia"):
        parts.append(f"wiki:{tags['wikipedia']}")
    if tags.get("wheelchair"):
        parts.append(f"wheelchair:{tags['wheelchair']}")
    if tags.get("operator"):
        parts.append(f"op:{tags['operator']}")
    return "; ".join(parts) if parts else None


def _point_distance_m(p: dict, lat: float, lon: float) -> float:
    # min distance to cum_km-labeled points (from parse_gpx_artifact_geometry geometry sample)
    return _haversine_m(p["lat"], p["lon"], lat, lon)


def min_distance_to_track(track_points: list[dict], lat: float, lon: float) -> tuple[float, float | None]:
    min_d = float("inf")
    nearest_km = None
    for tp in track_points:
        d = _point_distance_m(tp, lat, lon)
        if d < min_d:
            min_d = d
            km = tp.get("cum_km")
            if km is not None:
                nearest_km = km
    return min_d, nearest_km


def distance_to_polyline_segments(track_points: list[dict], lat: float, lon: float) -> tuple[float, float | None]:
    min_d = float("inf")
    nearest_km = None
    for i in range(len(track_points) - 1):
        a, b = track_points[i], track_points[i + 1]
        ax, ay = a["lat"], a["lon"]
        bx, by = b["lat"], b["lon"]

        # project point onto segment
        dx = bx - ax
        dy = by - ay
        if dx == 0 and dy == 0:
            d = _haversine_m(ax, ay, lat, lon)
            km = a.get("cum_km")
        else:
            t = ((lat - ax) * dx + (lon - ay) * dy) / (dx * dx + dy * dy)
            if t < 0:
                px, py = ax, ay
                km = a.get("cum_km")
            elif t > 1:
                px, py = bx, by
                km = b.get("cum_km")
            else:
                px = ax + t * dx
                py = ay + t * dy
                km = a.get("cum_km") if a.get("cum_km") is not None else None
                if km is not None and b.get("cum_km") is not None:
                    km = a["cum_km"] + t * (b["cum_km"] - a["cum_km"])
            d = _haversine_m(px, py, lat, lon)
        if d < min_d:
            min_d = d
            nearest_km = km
    return min_d, nearest_km


def _category_rank(category: str) -> int:
    ranking = {
        "tourism=museum": 1,
        "tourism=attraction": 2,
        "historic=castle": 3,
        "castle_type=": 3,
        "tourism=viewpoint": 4,
        "natural=viewpoint": 4,
        "natural=peak": 4,
        "tourism=artwork": 5,
        "historic=": 6,
        "ruins=": 7,
        "amenity=place_of_worship": 8,
        "tourism=gallery": 8,
        "tourism=information": 9,
        "leisure=park": 9,
        "leisure=garden": 9,
        "natural=cave_entrance": 9,
    }
    for key, rank in ranking.items():
        if category.startswith(key):
            return rank
    return 10


def sort_and_limit(attractions: list[dict], limit: int = 10) -> list[dict]:
    attractions.sort(key=lambda x: (_category_rank(x["category"]), x.get("distance_to_track_m", 99999), (x.get("name") or "").lower()))
    return attractions[:limit]


def _tags_to_short_name(tags: dict) -> str:
    name = tags.get("name", "").strip()
    if name:
        return name
    for key in ("historic", "ruins", "tourism", "natural", "leisure"):
        v = tags.get(key)
        if v and isinstance(v, str) and v.strip():
            return v.strip()[:60]
    return "unnamed"


def output_json(filepath: Path, data: Any) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def output_md(filepath: Path, data: list[dict], route_info: dict, source: str, raw_count: int, filtered_count: int) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"# Atrakcje turystyczne w odległości ≤{route_info['max_distance_m']}m od śladu GPX")
    lines.append("")
    lines.append(f"- **Route:** {route_info.get('route_name', route_info['route_id'])}")
    lines.append(f"- **Route ID:** {route_info['route_id']}")
    lines.append(f"- **Artifact ID:** {route_info.get('artifact_id', 'N/A')}")
    lines.append(f"- **GPX:** {route_info.get('gpx_path', 'N/A')}")
    lines.append(f"- **Punktów śladu:** {route_info.get('point_count', 'N/A')}")
    lines.append(f"- **Dystans trasy:** {route_info.get('distance_km', '?')} km")
    lines.append(f"- **Źródło POI:** {source}")
    lines.append(f"- **Kandydaci POI (raw):** {raw_count}")
    lines.append(f"- **Atrakcje ≤{route_info['max_distance_m']}m:** {filtered_count}")
    lines.append(f"- **Generowane:** {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    if not data:
        lines.append("## Brak atrakcji w zadanym promieniu")
        lines.append("")
        lines.append("Nie znaleziono atrakcji turystycznych w odległości ≤1 km od śladu GPX.")
        lines.append("")
        lines.append("Możliwe przyczyny:")
        lines.append("- Trasa wiedzie przez obszary bez zinwentaryzowanych atrakcji w OSM")
        lines.append("- Atrakcje mogą istnieć, ale nie są otagowane w OSM")
        lines.append("- Overpass API nie zwróciło danych (np. błąd sieci)")
        lines.append("")
        filepath.write_text("\n".join(lines), encoding="utf-8")
        return

    lines.append("## Top atrakcje")
    lines.append("")
    lines.append("| # | Nazwa | Kategoria | Odległość od trasy (m) | Km na trasie | Opis")
    lines.append("|---|-------|-----------|------------------------|-------------|------")

    for i, poi in enumerate(data, 1):
        name = poi.get("name") or "(bez nazwy)"
        cat = poi.get("category", "?")
        dist = poi.get("distance_to_track_m", "?")
        if isinstance(dist, float):
            dist = f"{dist:.0f}"
        nearest_km = poi.get("nearest_track_km")
        if nearest_km is not None:
            nearest_km_s = f"{nearest_km:.1f}"
        else:
            nearest_km_s = "?"
        desc = poi.get("description") or poi.get("reason", "")
        lines.append(f"| {i} | {name} | {cat} | {dist} | {nearest_km_s} | {desc[:100]}")
    lines.append("")

    lines.append("## Szczegóły")
    lines.append("")
    for i, poi in enumerate(data, 1):
        name = poi.get("name") or "(bez nazwy)"
        lines.append(f"### {i}. {name}")
        lines.append("")
        lines.append(f"- **Kategoria:** {poi.get('category', '?')}")
        lines.append(f"- **Lokalizacja:** {poi.get('lat', '?')}, {poi.get('lon', '?')}")
        lines.append(f"- **Odległość od trasy:** {poi.get('distance_to_track_m', '?')} m")
        if poi.get("nearest_track_km") is not None:
            lines.append(f"- **Najbliższy km trasy:** {poi['nearest_track_km']:.2f} km")
        lines.append(f"- **OSM ID:** {poi.get('osm_type', '?')}/{poi.get('osm_id', '?')}")
        if poi.get("description"):
            lines.append(f"- **Opis:** {poi['description']}")
        if poi.get("reason"):
            lines.append(f"- **Powód wyboru:** {poi['reason']}")
        if poi.get("risk_note"):
            lines.append(f"- **Ryzyko/Uwaga:** {poi['risk_note']}")
        lines.append("")

    lines.append("---")
    lines.append("*Raport wygenerowany automatycznie – nie zgadywano atrakcji poza rzeczywistym śladem GPX.*")
    lines.append(f"*Metoda liczenia odległości: haversine do {route_info.get('distance_method', 'segmentów polyline')}*")
    lines.append(f"*Liczba kandydatów raw: {raw_count}*")
    lines.append(f"*Liczba atrakcji po filtrze: {filtered_count}*")

    filepath.write_text("\n".join(lines), encoding="utf-8")


def find_nearest_point_idx(points: list[dict], lat: float, lon: float) -> int:
    min_d = float("inf")
    idx = 0
    for i, p in enumerate(points):
        d = _haversine_m(p["lat"], p["lon"], lat, lon)
        if d < min_d:
            min_d = d
            idx = i
    return idx


def main():
    parser = argparse.ArgumentParser(description="Analyze POI within N meters of a GPX route")
    parser.add_argument("--route-id", required=True, help="RWGPS route ID")
    parser.add_argument("--project-id", default="tuscany_2026", help="Project ID")
    parser.add_argument("--max-distance-m", type=int, default=1000, help="Max distance from track in meters")
    parser.add_argument("--limit", type=int, default=10, help="Max results to report")
    args = parser.parse_args()

    route_id = args.route_id
    project_id = args.project_id
    max_dist_m = args.max_distance_m
    limit = args.limit

    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting route POI analysis")
    print(f"  route_id={route_id}, project_id={project_id}, max_distance_m={max_dist_m}, limit={limit}")

    project_dir = ARTIFACTS_DIR / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    raw_candidates_path = project_dir / f"rwgps_{route_id}_poi_candidates_raw.json"
    filtered_path = project_dir / f"rwgps_{route_id}_attractions_within_1km.json"
    md_path = project_dir / f"rwgps_{route_id}_attractions_within_1km.md"

    # Step 1: Get track geometry
    print("  [1/5] Reading GPX geometry via parse_gpx_artifact_geometry...")
    try:
        geometry = get_track_geometry(route_id)
    except RuntimeError as e:
        error_report = {
            "ok": False,
            "status": "GEOMETRY_ERROR",
            "error": str(e),
            "route_id": route_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        output_json(raw_candidates_path, error_report)
        output_json(filtered_path, error_report)
        output_md(md_path, [], error_report, "N/A", 0, 0)
        print(f"  ERROR: {e}")
        sys.exit(1)

    print(f"    point_count={geometry.get('point_count')}, distance_km={geometry.get('distance_km')}, "
          f"bbox={geometry.get('bbox')}")

    # Get detailed track points from the geometry_sample + add cum_km from the detailed data
    # We need to reconstruct cum_km for each point. The geometry_sample has lat/lon but not cum_km.
    # We need the full detailed points. Let me use route_analyzer directly.
    from qbot3.artifacts.route_analyzer import _parse_gpx_file_detailed

    gpx_path_str = geometry.get("absolute_path")
    if not gpx_path_str or not Path(gpx_path_str).exists():
        print(f"  ERROR: GPX file not found at {gpx_path_str}")
        sys.exit(1)

    gpx_path = Path(gpx_path_str)
    detailed_points = _parse_gpx_file_detailed(gpx_path)
    if not detailed_points:
        print("  ERROR: No track points parsed from GPX")
        sys.exit(1)

    print(f"    detailed track points: {len(detailed_points)}")

    # Use segment-based distance calculation
    track_points_segments = detailed_points

    print("  [2/5] Extending bbox for Overpass query...")
    bbox = geometry.get("bbox", {})
    sw_lat = bbox.get("sw_lat", 0)
    sw_lng = bbox.get("sw_lng", 0)
    ne_lat = bbox.get("ne_lat", 0)
    ne_lng = bbox.get("ne_lng", 0)

    lat_buffer = max_dist_m / 111320.0 * 2  # ~2km buffer
    mid_lat = (sw_lat + ne_lat) / 2.0
    lon_buffer = max_dist_m / (111320.0 * math.cos(math.radians(mid_lat))) * 2

    query_south = sw_lat - lat_buffer
    query_north = ne_lat + lat_buffer
    query_west = sw_lng - lon_buffer
    query_east = ne_lng + lon_buffer

    print(f"    query bbox: ({query_south:.4f}, {query_west:.4f}) -> ({query_north:.4f}, {query_east:.4f})")

    # Step 3: Fetch POI candidates from Overpass
    print(f"  [3/5] Fetching POI candidates from Overpass API...")
    try:
        poi_candidates = fetch_overpass_pois(query_west, query_south, query_east, query_north)
    except RuntimeError as e:
        error_report = {
            "ok": False,
            "status": "OVERPASS_ERROR",
            "error": str(e),
            "route_id": route_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "partial_artifacts": True,
        }
        output_json(raw_candidates_path, error_report)
        output_json(filtered_path, error_report)
        output_md(md_path, [], {
            "route_id": route_id, "project_id": project_id,
            "max_distance_m": max_dist_m, "error": str(e)
        }, "overpass", 0, 0)
        print(f"  ERROR: Overpass API error: {e}")
        sys.exit(1)

    print(f"    raw POI candidates: {len(poi_candidates)}")

    # Save raw candidates
    raw_output = {
        "ok": True,
        "status": "OK",
        "route_id": route_id,
        "source": "overpass",
        "bbox": {"south": query_south, "west": query_west, "north": query_north, "east": query_east},
        "candidate_count": len(poi_candidates),
        "candidates": poi_candidates,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output_json(raw_candidates_path, raw_output)
    print(f"    saved raw candidates to {raw_candidates_path}")

    # Step 4: Filter by distance to track
    print(f"  [4/5] Calculating distances to track (max {max_dist_m}m)...")

    filtered = []
    for poi in poi_candidates:
        d, nearest_km = distance_to_polyline_segments(track_points_segments, poi["lat"], poi["lon"])
        if d > max_dist_m:
            continue

        name = poi.get("name") or _tags_to_short_name(poi.get("tags", {}))
        if not name or name == "unnamed":
            name = f"{poi.get('osm_type', 'node')}/{poi.get('osm_id', '')}"

        risk_notes = []
        if not poi.get("name"):
            risk_notes.append("brak nazwy w OSM")
        if d > 800:
            risk_notes.append("blisko granicy 1 km od trasy")

        result = {
            "name": name,
            "category": poi["category"],
            "lat": poi["lat"],
            "lon": poi["lon"],
            "distance_to_track_m": round(d, 1),
            "nearest_track_km": round(nearest_km, 3) if nearest_km is not None else None,
            "osm_type": poi.get("osm_type"),
            "osm_id": poi.get("osm_id"),
            "description": poi.get("description"),
            "reason": f"{poi['category']} within {d:.0f}m of track",
            "risk_note": "; ".join(risk_notes) if risk_notes else None,
        }
        filtered.append(result)

    print(f"    attractions within {max_dist_m}m: {len(filtered)}")

    # Step 5: Sort and rank
    sorted_filtered = sort_and_limit(filtered, limit=limit)

    print(f"  [5/5] Saving results...")

    filtered_output = {
        "ok": True,
        "status": "OK",
        "route_id": route_id,
        "project_id": project_id,
        "source": "overpass",
        "max_distance_m": max_dist_m,
        "limit": limit,
        "total_candidates": len(poi_candidates),
        "total_within_distance": len(filtered),
        "distance_method": "haversine to polyline segments (detailed track points)",
        "attractions": sorted_filtered,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output_json(filtered_path, filtered_output)

    route_info = {
        "route_id": route_id,
        "route_name": geometry.get("route_id", route_id),
        "artifact_id": geometry.get("artifact_id"),
        "gpx_path": geometry.get("absolute_path"),
        "point_count": geometry.get("point_count"),
        "distance_km": geometry.get("distance_km"),
        "max_distance_m": max_dist_m,
        "distance_method": "haversine to polyline segments (detailed track points)",
    }
    output_md(md_path, sorted_filtered, route_info, "overpass", len(poi_candidates), len(filtered))

    print(f"    saved filtered results to {filtered_path}")
    print(f"    saved MD report to {md_path}")

    # Validation
    print(f"\n{'='*60}")
    print(f"VALIDATION:")
    print(f"  Raw POI candidates: {len(poi_candidates)}")
    print(f"  Attractions within {max_dist_m}m: {len(filtered)}")
    print(f"  All have distance_to_track_m <= {max_dist_m}: {all(a['distance_to_track_m'] <= max_dist_m for a in filtered) if filtered else 'N/A (no results)'}")
    all_valid = all(a.get("distance_to_track_m") is not None and a["distance_to_track_m"] <= max_dist_m for a in filtered)
    if filtered and not all_valid:
        print(f"  WARNING: Some entries exceed max distance!")
    print(f"  JSON saved: {filtered_path}")
    print(f"  MD saved: {md_path}")
    print(f"{'='*60}")

    print(f"\nTOP {len(sorted_filtered)} ATRAKCJI:")
    for i, a in enumerate(sorted_filtered, 1):
        print(f"  {i}. {a['name']} | {a['category']} | {a['distance_to_track_m']:.0f}m | km {a.get('nearest_track_km', '?')}")
    print(f"\nDone at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
