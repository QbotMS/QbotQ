#!/usr/bin/env python3
"""Parametrized POI analysis tool — finds POIs within a buffer from a GPX track.

Supports categories: attractions, food, groceries, water, bike_service.
Segments the track into max-10km chunks to avoid heavy single queries.
Caches raw Overpass results per category.

Usage:
  .venv/bin/python scripts/analyze_route_poi_within_track_buffer.py \\
      --route-id 55395119 --project-id tuscany_2026 \\
      --category attractions --max-distance-m 1000 --limit 10
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path("/opt/qbot/app")
ARTIFACTS_DIR = Path("/opt/qbot/artifacts")
sys.path.insert(0, str(APP_DIR))

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "QBot/1.0 (route poi buffer analysis; michal@qbot)"
SEGMENT_MAX_KM = 10.0
OVERPASS_TIMEOUT = 25

# ── Category definitions ────────────────────────────────────────────────────

CATEGORY_DEFS: dict[str, dict[str, Any]] = {
    "attractions": {
        "tags": [
            'node["tourism"="attraction"]',
            'node["tourism"="museum"]',
            'node["tourism"="viewpoint"]',
            'node["tourism"="artwork"]',
            'node["tourism"="information"]',
            'node["tourism"="gallery"]',
            'node["historic"]',
            'node["ruins"]',
            'node["castle_type"]',
            'node["natural"="peak"]',
            'node["natural"="viewpoint"]',
            'node["natural"="cave_entrance"]',
            'node["leisure"="park"]',
            'node["leisure"="garden"]',
            'way["tourism"="attraction"]',
            'way["tourism"="museum"]',
            'way["tourism"="viewpoint"]',
            'way["tourism"="artwork"]',
            'way["historic"]',
            'way["ruins"]',
            'way["castle_type"]',
            'way["natural"="peak"]',
            'way["natural"="viewpoint"]',
            'way["leisure"="park"]',
            'way["leisure"="garden"]',
        ],
        "rank_weight": {
            "tourism=museum": 1, "tourism=attraction": 2,
            "historic=castle": 3, "castle_type=": 3,
            "tourism=viewpoint": 4, "natural=viewpoint": 4,
            "natural=peak": 4, "tourism=artwork": 5,
            "historic=": 6, "ruins=": 7,
            "tourism=gallery": 8, "tourism=information": 9,
            "leisure=park": 9, "leisure=garden": 9,
            "natural=cave_entrance": 10,
        },
        "label": "Atrakcje turystyczne",
    },
    "food": {
        "tags": [
            'node["amenity"="restaurant"]',
            'node["amenity"="cafe"]',
            'node["amenity"="bar"]',
            'node["amenity"="pub"]',
            'node["amenity"="fast_food"]',
            'node["amenity"="food_court"]',
            'node["shop"="bakery"]',
            'node["shop"="pastry"]',
            'node["shop"="deli"]',
            'node["cuisine"="italian"]',
            'node["cuisine"="pizza"]',
            'node["cuisine"="regional"]',
            'node["cuisine"="seafood"]',
            'node["cuisine"="sandwich"]',
            'way["amenity"="restaurant"]',
            'way["amenity"="cafe"]',
            'way["amenity"="bar"]',
            'way["amenity"="pub"]',
            'way["amenity"="fast_food"]',
            'way["shop"="bakery"]',
            'way["shop"="pastry"]',
            'way["shop"="deli"]',
        ],
        "rank_weight": {
            "amenity=restaurant": 1, "cuisine=italian": 1,
            "cuisine=regional": 1, "cuisine=pizza": 1,
            "amenity=cafe": 2, "amenity=bar": 3, "amenity=pub": 3,
            "amenity=fast_food": 4, "shop=bakery": 5,
            "shop=pastry": 5, "shop=deli": 5,
            "amenity=food_court": 6,
        },
        "label": "Jedzenie",
    },
    "groceries": {
        "tags": [
            'node["shop"="supermarket"]',
            'node["shop"="convenience"]',
            'node["shop"="greengrocer"]',
            'node["shop"="butcher"]',
            'node["shop"="bakery"]',
            'node["shop"="deli"]',
            'node["shop"="cheese"]',
            'node["shop"="pasta"]',
            'node["shop"="general"]',
            'node["shop"="department_store"]',
            'node["amenity"="marketplace"]',
            'way["shop"="supermarket"]',
            'way["shop"="convenience"]',
            'way["shop"="greengrocer"]',
            'way["shop"="butcher"]',
            'way["shop"="bakery"]',
            'way["shop"="deli"]',
            'way["shop"="cheese"]',
            'way["shop"="general"]',
            'way["amenity"="marketplace"]',
        ],
        "rank_weight": {
            "shop=supermarket": 1, "shop=convenience": 2,
            "shop=bakery": 3, "shop=deli": 3,
            "shop=greengrocer": 4, "shop=butcher": 4,
            "shop=cheese": 5, "shop=pasta": 5,
            "shop=general": 5, "shop=department_store": 5,
            "amenity=marketplace": 6,
        },
        "label": "Zakupy spożywcze",
    },
    "water": {
        "tags": [
            'node["amenity"="drinking_water"]',
            'node["man_made"="water_tap"]',
            'node["natural"="spring"]',
            'node["amenity"="fountain"]',
            'node["drinking_water"="yes"]',
        ],
        "rank_weight": {
            "amenity=drinking_water": 1, "man_made=water_tap": 1,
            "natural=spring": 2, "amenity=fountain": 3,
        },
        "label": "Punkty wody",
    },
    "bike_service": {
        "tags": [
            'node["shop"="bicycle"]',
            'node["amenity"="bicycle_repair_station"]',
            'node["service:bicycle:repair"="yes"]',
            'node["service:bicycle:pump"="yes"]',
            'way["shop"="bicycle"]',
        ],
        "rank_weight": {
            "shop=bicycle": 1, "amenity=bicycle_repair_station": 2,
            "service:bicycle:repair=yes": 2, "service:bicycle:pump=yes": 3,
        },
        "label": "Serwis rowerowy",
    },
}

OVERPASS_QUERY_TEMPLATE = """[out:json][timeout:{timeout}];
(
{taggings}
);
out center tags 300;"""


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _parse_coord(val: Any) -> float | None:
    try:
        v = float(val)
        if math.isfinite(v):
            return v
    except (TypeError, ValueError):
        pass
    return None


def _category_tag(category: str) -> str:
    return CATEGORY_DEFS[category]["label"]


# ── GPX / geometry ──────────────────────────────────────────────────────────

def get_track_geometry(route_id: str) -> dict:
    from tools.rwgps.client import parse_gpx_artifact_geometry
    result = parse_gpx_artifact_geometry(route_id=route_id)
    if not result.get("ok"):
        raise RuntimeError(f"parse_gpx_artifact_geometry failed: {result.get('status')} – {result.get('error')}")
    return result


def load_detailed_points(gpx_path: str) -> list[dict]:
    from qbot3.artifacts.route_analyzer import _parse_gpx_file_detailed
    pts = _parse_gpx_file_detailed(gpx_path)
    if not pts:
        raise RuntimeError("No track points parsed from GPX")
    return pts


# ── Track segmentation ──────────────────────────────────────────────────────

def segment_track(points: list[dict], max_segment_km: float = SEGMENT_MAX_KM) -> list[dict]:
    segments: list[dict] = []
    if not points:
        return segments

    seg_start_idx = 0
    seg_start_km = 0.0
    for i in range(1, len(points)):
        if points[i]["cum_km"] - seg_start_km >= max_segment_km or i == len(points) - 1:
            seg_pts = points[seg_start_idx:i + 1]
            lats = [p["lat"] for p in seg_pts]
            lons = [p["lon"] for p in seg_pts]
            segments.append({
                "start_idx": seg_start_idx,
                "end_idx": i,
                "start_km": seg_start_km,
                "end_km": points[i]["cum_km"],
                "points": seg_pts,
                "bbox_south": min(lats),
                "bbox_north": max(lats),
                "bbox_west": min(lons),
                "bbox_east": max(lons),
            })
            seg_start_idx = i
            seg_start_km = points[i]["cum_km"]

    return segments


def expand_bbox(south: float, north: float, west: float, east: float, buffer_m: float) -> tuple[float, float, float, float]:
    lat_per_m = 1.0 / 111320.0
    mid_lat = (south + north) / 2.0
    lon_per_m = 1.0 / (111320.0 * math.cos(math.radians(mid_lat)))
    buf_lat = buffer_m * lat_per_m
    buf_lon = buffer_m * lon_per_m
    return (south - buf_lat, north + buf_lat, west - buf_lon, east + buf_lon)


# ── Overpass ────────────────────────────────────────────────────────────────

def build_overpass_query(segment_bbox: tuple[float, float, float, float], tags: list[str], timeout: int = OVERPASS_TIMEOUT) -> str:
    south, north, west, east = segment_bbox
    bbox_str = f"({south},{west},{north},{east})"
    taggings = "\n".join(f"  {t}{bbox_str};" for t in tags)
    return OVERPASS_QUERY_TEMPLATE.format(timeout=timeout, taggings=taggings)


def query_overpass(query: str) -> list[dict]:
    from urllib.parse import urlencode
    import httpx

    try:
        with httpx.Client(timeout=OVERPASS_TIMEOUT + 10) as c:
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

    return data.get("elements", [])


def parse_overpass_elements(elements: list[dict]) -> list[dict]:
    pois: list[dict] = []
    seen: set[str] = set()

    for el in elements:
        osm_type = el.get("type", "node")
        osm_id = el.get("id")
        dedup_key = f"{osm_type}/{osm_id}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        tags = el.get("tags") or {}
        lat = _parse_coord(el.get("lat"))
        lon = _parse_coord(el.get("lon"))
        if lat is None or lon is None:
            center = el.get("center") or {}
            lat = _parse_coord(center.get("lat"))
            lon = _parse_coord(center.get("lon"))
        if lat is None or lon is None:
            continue

        name = tags.get("name", "").strip()
        category_tag = classify_poi_category(tags)
        if not category_tag:
            continue

        pois.append({
            "name": name or None,
            "category": category_tag,
            "tags": tags,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "osm_type": osm_type,
            "osm_id": osm_id,
            "opening_hours": tags.get("opening_hours"),
            "cuisine": tags.get("cuisine"),
            "shop": tags.get("shop"),
        })

    return pois


def classify_poi_category(tags: dict) -> str | None:
    for key in ("tourism", "historic", "amenity", "natural", "leisure", "shop", "man_made", "cuisine",
                "castle_type", "ruins", "drinking_water", "service:bicycle:repair", "service:bicycle:pump"):
        val = tags.get(key)
        if val and isinstance(val, str) and val.strip():
            return f"{key}={val.strip()}"
    # Check for drinking_water=yes separately
    if tags.get("drinking_water") == "yes" and tags.get("amenity") != "drinking_water":
        return "drinking_water=yes"
    return None


def _segment_cache_path(project_dir: Path, route_id: str, category: str) -> Path:
    return project_dir / f"rwgps_{route_id}_{category}_candidates_raw.json"


def load_cache(cache_path: Path) -> list[dict] | None:
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("ok") and isinstance(data.get("candidates"), list):
                return data["candidates"]
        except Exception:
            pass
    return None


def save_cache(cache_path: Path, candidates: list[dict], route_id: str, category: str) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "ok": True,
        "route_id": route_id,
        "category": category,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


# ── Distance to track ───────────────────────────────────────────────────────

def distance_to_polyline_segments(track_points: list[dict], lat: float, lon: float) -> tuple[float, float | None]:
    min_d = float("inf")
    nearest_km = None
    for i in range(len(track_points) - 1):
        a, b = track_points[i], track_points[i + 1]
        ax, ay = a["lat"], a["lon"]
        bx, by = b["lat"], b["lon"]
        dx = bx - ax
        dy = by - ay
        if dx == 0 and dy == 0:
            d = _haversine_m(ax, ay, lat, lon)
            km = a.get("cum_km")
        else:
            t = max(0, min(1, ((lat - ax) * dx + (lon - ay) * dy) / (dx * dx + dy * dy)))
            px = ax + t * dx
            py = ay + t * dy
            d = _haversine_m(px, py, lat, lon)
            km = a.get("cum_km")
            if km is not None and b.get("cum_km") is not None:
                km = a["cum_km"] + t * (b["cum_km"] - a["cum_km"])
        if d < min_d:
            min_d = d
            nearest_km = km
    return min_d, nearest_km


# ── Ranking ─────────────────────────────────────────────────────────────────

def compute_rank(poi: dict, category: str) -> int:
    rank_map = CATEGORY_DEFS.get(category, {}).get("rank_weight", {})
    cat = poi.get("category", "")
    if cat in rank_map:
        return rank_map[cat]
    # partial match
    for key, rank in rank_map.items():
        if cat.startswith(key):
            return rank
    return 99


def sort_pois(pois: list[dict], category: str, limit: int) -> list[dict]:
    pois.sort(key=lambda x: (compute_rank(x, category), x.get("distance_to_track_m", 99999), (x.get("name") or "").lower()))
    return pois[:limit]


# ── Output ──────────────────────────────────────────────────────────────────

def output_json(filepath: Path, data: Any) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def output_md(filepath: Path, results: list[dict], meta: dict) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# {meta.get('title', 'POI')} w odległości ≤{meta['max_distance_m']}m od śladu GPX")
    lines.append("")
    lines.append(f"- **Route:** {meta.get('route_name', meta['route_id'])}")
    lines.append(f"- **Route ID:** {meta['route_id']}")
    lines.append(f"- **Kategoria:** {meta['category']} — {meta.get('category_label', '')}")
    lines.append(f"- **Maks. odległość:** {meta['max_distance_m']} m")
    lines.append(f"- **Limit wyników:** {meta.get('limit', 'bez limitu')}")
    lines.append(f"- **GPX punktów:** {meta.get('point_count', '?')}")
    lines.append(f"- **Dystans trasy:** {meta.get('distance_km', '?')} km")
    lines.append(f"- **Źródło:** Overpass API (segmentacja co {SEGMENT_MAX_KM} km)")
    lines.append(f"- **Kandydaci raw:** {meta.get('raw_count', '?')}")
    lines.append(f"- **Wyniki po filtrze:** {meta.get('filtered_count', '?')}")
    lines.append(f"- **Generowane:** {meta.get('generated_at', '')}")
    if meta.get("segment_errors"):
        lines.append(f"- **Błędy segmentów:** {len(meta['segment_errors'])} segmentów — {'; '.join(meta['segment_errors'][:3])}")
    lines.append("")

    if not results:
        lines.append("## Brak wyników")
        lines.append("")
        lines.append(f"Nie znaleziono POI kategorii '{meta['category']}' w odległości ≤{meta['max_distance_m']}m od śladu.")
        lines.append("")
        filepath.write_text("\n".join(lines), encoding="utf-8")
        return

    lines.append("## Wyniki")
    lines.append("")
    lines.append("| # | Nazwa | Kategoria | Odległość (m) | Km na trasie | Opis")
    lines.append("|---|-------|-----------|---------------|--------------|------")
    for i, p in enumerate(results, 1):
        name = p.get("name") or "(bez nazwy)"
        cat = p.get("category", "?")
        d = p.get("distance_to_track_m", "?")
        d_s = f"{d:.0f}" if isinstance(d, float) else str(d)
        km = p.get("nearest_track_km")
        km_s = f"{km:.1f}" if km is not None else "?"
        desc = ""
        if p.get("opening_hours"):
            desc += f" h:{p['opening_hours']}"
        if p.get("cuisine"):
            desc += f" kuchnia:{p['cuisine']}"
        if p.get("shop"):
            desc += f" shop:{p['shop']}"
        if p.get("risk_note"):
            desc += f" ⚠{p['risk_note']}"
        lines.append(f"| {i} | {name} | {cat} | {d_s} | {km_s} |{desc[:120]}")
    lines.append("")

    lines.append("## Szczegóły")
    lines.append("")
    for i, p in enumerate(results, 1):
        name = p.get("name") or "(bez nazwy)"
        lines.append(f"### {i}. {name}")
        lines.append("")
        lines.append(f"- **Kategoria:** {p.get('category', '?')}")
        lines.append(f"- **Lokalizacja:** {p.get('lat', '?')}, {p.get('lon', '?')}")
        lines.append(f"- **Odległość od trasy:** {p.get('distance_to_track_m', '?'):.1f} m")
        if p.get("nearest_track_km") is not None:
            lines.append(f"- **Najbliższy km trasy:** {p['nearest_track_km']:.2f} km")
        lines.append(f"- **OSM:** {p.get('osm_type', '?')}/{p.get('osm_id', '?')}")
        if p.get("opening_hours"):
            lines.append(f"- **Godziny otwarcia:** {p['opening_hours']}")
        if p.get("cuisine"):
            lines.append(f"- **Kuchnia:** {p['cuisine']}")
        if p.get("shop"):
            lines.append(f"- **Shop:** {p['shop']}")
        if p.get("reason"):
            lines.append(f"- **Powód:** {p['reason']}")
        if p.get("risk_note"):
            lines.append(f"- **Ryzyko/Uwaga:** {p['risk_note']}")
        lines.append("")

    lines.append("---")
    lines.append("*Raport wygenerowany automatycznie przez analyze_route_poi_within_track_buffer.py*")
    lines.append(f"*Metoda: segmenty Overpass co {SEGMENT_MAX_KM} km, odległość haversine do segmentów polyline*")
    filepath.write_text("\n".join(lines), encoding="utf-8")


# ── Main ────────────────────────────────────────────────────────────────────

def build_description(poi: dict) -> str:
    parts = []
    if poi.get("opening_hours"):
        parts.append(f"h:{poi['opening_hours']}")
    if poi.get("cuisine"):
        parts.append(f"kuchnia:{poi['cuisine']}")
    if poi.get("shop"):
        parts.append(f"shop:{poi['shop']}")
    return "; ".join(parts) if parts else None


def main():
    parser = argparse.ArgumentParser(description="Find POIs within a buffer from a GPX track")
    parser.add_argument("--route-id", required=True)
    parser.add_argument("--artifact-id")
    parser.add_argument("--project-id", default="tuscany_2026")
    parser.add_argument("--category", required=True,
                        choices=list(CATEGORY_DEFS.keys()),
                        help="POI category to search")
    parser.add_argument("--max-distance-m", type=int, default=1000)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--refresh-cache", action="store_true", default=False,
                        help="Ignore cached Overpass results")
    args = parser.parse_args()

    route_id = args.route_id
    category = args.category
    max_dist_m = args.max_distance_m
    limit = args.limit
    refresh = args.refresh_cache

    cat_def = CATEGORY_DEFS[category]
    cat_label = cat_def["label"]

    project_dir = ARTIFACTS_DIR / "projects" / args.project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    raw_cache_path = _segment_cache_path(project_dir, route_id, category)
    filtered_json_path = project_dir / f"rwgps_{route_id}_{category}_within_{max_dist_m}m.json"
    filtered_md_path = project_dir / f"rwgps_{route_id}_{category}_within_{max_dist_m}m.md"

    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] Starting POI analysis: category={category}, max_dist={max_dist_m}m, limit={limit}")

    # Step 1: GPX geometry
    print("  [1/6] Reading GPX geometry...")
    geometry = get_track_geometry(route_id)
    point_count = geometry.get("point_count")
    distance_km = geometry.get("distance_km")
    print(f"    points={point_count}, dist={distance_km}km")

    gpx_path = geometry.get("absolute_path")
    if not gpx_path or not Path(gpx_path).exists():
        raise SystemExit(f"GPX file not found: {gpx_path}")
    detailed_points = load_detailed_points(gpx_path)
    print(f"    detailed points: {len(detailed_points)}")

    # Step 2: Segment track
    print(f"  [2/6] Segmenting track (max {SEGMENT_MAX_KM}km per segment)...")
    segments = segment_track(detailed_points, SEGMENT_MAX_KM)
    print(f"    segments: {len(segments)}")
    for s in segments:
        print(f"      {s['start_km']:.1f}-{s['end_km']:.1f}km ({len(s['points'])} pts)")

    # Step 3: Try cache
    all_candidates: list[dict] = []
    if not refresh:
        cached = load_cache(raw_cache_path)
        if cached is not None:
            all_candidates = cached
            print(f"  [3/6] Loaded {len(all_candidates)} cached candidates (refresh-cache=false)")

    if not all_candidates:
        # Step 3: Fetch via Overpass per segment
        print(f"  [3/6] Fetching POI from Overpass ({len(segments)} segments)...")
        seg_errors: list[str] = []
        total_raw = 0
        buffer_m = max(max_dist_m, 1200)

        for idx, seg in enumerate(segments):
            south, north, west, east = expand_bbox(
                seg["bbox_south"], seg["bbox_north"], seg["bbox_west"], seg["bbox_east"], buffer_m
            )
            query = build_overpass_query((south, north, west, east), cat_def["tags"])
            print(f"      seg {idx + 1}/{len(segments)} ({seg['start_km']:.1f}-{seg['end_km']:.1f}km) ...", end=" ")

            try:
                elements = query_overpass(query)
                pois = parse_overpass_elements(elements)
                all_candidates.extend(pois)
                print(f"{len(pois)} POIs")
                total_raw += len(elements)
            except RuntimeError as e:
                err_msg = f"seg {seg['start_km']:.0f}-{seg['end_km']:.0f}km: {e}"
                print(f"ERROR: {e}")
                seg_errors.append(err_msg)

            time.sleep(0.3)  # polite delay between segments

        # Deduplicate across segments
        seen_keys: set[str] = set()
        deduped: list[dict] = []
        for p in all_candidates:
            key = f"{p['osm_type']}/{p['osm_id']}"
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(p)
        all_candidates = deduped
        print(f"    total raw elements: {total_raw}, unique POIs: {len(all_candidates)}")

        # Save cache
        save_cache(raw_cache_path, all_candidates, route_id, category)
        print(f"    cached to {raw_cache_path.name}")

    # Step 4: Calculate distances
    print(f"  [4/6] Calculating distances to track (max {max_dist_m}m)...")
    filtered: list[dict] = []
    for poi in all_candidates:
        d, nearest_km = distance_to_polyline_segments(detailed_points, poi["lat"], poi["lon"])
        if d > max_dist_m:
            continue

        name = poi.get("name")
        if not name:
            name = f"{poi.get('osm_type', 'node')}/{poi.get('osm_id', '')}"

        risk_notes = []
        if not poi.get("name"):
            risk_notes.append("brak nazwy w OSM")
        if d > max_dist_m * 0.85:
            risk_notes.append(f"blisko granicy {max_dist_m}m")

        result = {
            "name": name,
            "category": poi["category"],
            "tags": {k: v for k, v in poi.get("tags", {}).items()
                     if k in ("tourism", "historic", "amenity", "natural", "leisure", "shop",
                              "cuisine", "opening_hours", "name", "description",
                              "man_made", "castle_type", "ruins", "drinking_water",
                              "service:bicycle:repair", "service:bicycle:pump")},
            "lat": poi["lat"],
            "lon": poi["lon"],
            "distance_to_track_m": round(d, 1),
            "nearest_track_km": round(nearest_km, 3) if nearest_km is not None else None,
            "osm_type": poi.get("osm_type"),
            "osm_id": poi.get("osm_id"),
            "opening_hours": poi.get("opening_hours"),
            "cuisine": poi.get("cuisine"),
            "shop": poi.get("shop"),
            "description": build_description(poi),
            "reason": f"{poi['category']} — {d:.0f}m od trasy",
            "risk_note": "; ".join(risk_notes) if risk_notes else None,
        }
        filtered.append(result)

    print(f"    POIs within {max_dist_m}m: {len(filtered)}")

    # Step 5: Sort and rank
    print(f"  [5/6] Ranking (limit={limit})...")
    ranked = sort_pois(filtered, category, limit)

    # Step 6: Output
    print(f"  [6/6] Saving artifacts...")
    meta = {
        "route_id": route_id,
        "route_name": geometry.get("route_id", route_id),
        "artifact_id": geometry.get("artifact_id"),
        "gpx_path": geometry.get("absolute_path"),
        "point_count": point_count,
        "distance_km": distance_km,
        "category": category,
        "category_label": cat_label,
        "max_distance_m": max_dist_m,
        "limit": limit,
        "raw_count": len(all_candidates),
        "filtered_count": len(filtered),
        "segment_errors": seg_errors if 'seg_errors' in dir() else [],
        "source": "overpass_segmented",
        "distance_method": "haversine to polyline segments",
        "generated_at": ts,
    }

    filtered_output = {**meta, "ok": True, "status": "OK", "results": ranked}
    output_json(filtered_json_path, filtered_output)

    md_meta = {
        "title": cat_label,
        "route_id": route_id,
        "route_name": geometry.get("route_id", route_id),
        "category": category,
        "category_label": cat_label,
        "max_distance_m": max_dist_m,
        "limit": limit,
        "point_count": point_count,
        "distance_km": distance_km,
        "raw_count": len(all_candidates),
        "filtered_count": len(filtered),
        "segment_errors": seg_errors if 'seg_errors' in dir() else [],
        "generated_at": ts,
    }
    output_md(filtered_md_path, ranked, md_meta)

    print(f"\n{'='*60}")
    print(f"RESULTS: category={category} max_dist={max_dist_m}m limit={limit}")
    print(f"  Raw candidates: {len(all_candidates)}")
    print(f"  Within {max_dist_m}m: {len(filtered)}")
    print(f"  Top {len(ranked)}:")
    for i, p in enumerate(ranked, 1):
        d_s = f"{p['distance_to_track_m']:.0f}m" if isinstance(p.get('distance_to_track_m'), float) else "?"
        km_s = f"km {p['nearest_track_km']:.1f}" if p.get('nearest_track_km') is not None else ""
        extra = ""
        if p.get("opening_hours"):
            extra += f" [h:{p['opening_hours']}]"
        if p.get("cuisine"):
            extra += f" [{p['cuisine']}]"
        print(f"    {i}. {p['name']} | {p['category']} | {d_s} | {km_s}{extra}")
    print(f"  JSON: {filtered_json_path}")
    print(f"  MD:   {filtered_md_path}")

    all_valid = all(
        a.get("distance_to_track_m") is not None and a["distance_to_track_m"] <= max_dist_m
        for a in filtered
    )
    print(f"  All <= {max_dist_m}m: {all_valid}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
