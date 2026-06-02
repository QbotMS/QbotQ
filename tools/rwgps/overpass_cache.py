"""
Bulk Overpass download for a route bounding box.
Saves per-category JSON files to a local cache directory.
Subsequent POI analysis uses the cache instead of live Overpass.
"""
from __future__ import annotations
import json, time, logging
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("overpass_cache")

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

CATEGORIES: dict[str, str] = {
    "water": """
nwr["amenity"="drinking_water"]({bbox});
nwr["amenity"="fountain"]["drinking_water"!="no"]({bbox});
nwr["drinking_water"="yes"]({bbox});
nwr["man_made"="water_tap"]({bbox});
""",
    "food": """
nwr["shop"~"supermarket|convenience|grocery|bakery|deli|butcher|greengrocer|pastry|farm|general"]({bbox});
nwr["amenity"~"marketplace|fuel"]({bbox});
nwr["amenity"~"cafe|bar|restaurant|fast_food|pub|ice_cream"]({bbox});
nwr["vending"~"food|drinks"]({bbox});
""",
    "attraction": """
nwr["tourism"~"attraction|artwork|gallery|museum|viewpoint|theme_park|zoo|aquarium|picnic_site"]({bbox});
nwr["historic"]({bbox});
""",
    "town": """
node["place"~"city|town|village|hamlet"]({bbox});
""",
}

CHUNK_DEG = 0.25  # ~25km chunks


def _bbox_str(min_lat, min_lon, max_lat, max_lon) -> str:
    return f"{min_lat:.6f},{min_lon:.6f},{max_lat:.6f},{max_lon:.6f}"


def _overpass_fetch(query: str, timeout: int = 60) -> list[dict]:
    for url in OVERPASS_URLS:
        try:
            resp = httpx.post(
                url,
                data={"data": query},
                headers={"User-Agent": "QBot/3.0 overpass_cache"},
                timeout=httpx.Timeout(timeout, connect=10.0),
            )
            if resp.status_code in (429, 502, 503, 504):
                log.warning("Overpass %s HTTP %s", url, resp.status_code)
                time.sleep(5)
                continue
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as exc:
            log.warning("Overpass %s error: %s", url, exc)
            time.sleep(3)
    return []


def build_route_cache(
    route_bbox: dict,
    cache_dir: str | Path,
    route_slug: str = "route",
    chunk_deg: float = CHUNK_DEG,
    categories: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Download all POI for route bbox and save to cache_dir/{route_slug}_{category}.json.

    Splits bbox into chunks of chunk_deg x chunk_deg to avoid Overpass timeout.
    Deduplicates by osm type+id across chunks.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cats = categories or list(CATEGORIES.keys())

    min_lat = route_bbox["min_lat"]
    min_lon = route_bbox["min_lon"]
    max_lat = route_bbox["max_lat"]
    max_lon = route_bbox["max_lon"]

    # build chunk grid
    lat_chunks = []
    cur = min_lat
    while cur < max_lat:
        lat_chunks.append((cur, min(cur + chunk_deg, max_lat)))
        cur += chunk_deg

    lon_chunks = []
    cur = min_lon
    while cur < max_lon:
        lon_chunks.append((cur, min(cur + chunk_deg, max_lon)))
        cur += chunk_deg

    total_chunks = len(lat_chunks) * len(lon_chunks)
    results: dict[str, Any] = {}

    for cat in cats:
        out_file = cache_dir / f"{route_slug}_{cat}.json"
        if out_file.exists() and not force:
            log.info("cache hit: %s", out_file)
            with open(out_file) as f:
                results[cat] = json.load(f)
            continue

        log.info("downloading %s (%d chunks)...", cat, total_chunks)
        query_template = CATEGORIES[cat].strip()
        seen: dict[str, dict] = {}  # dedup by "type:id"
        chunk_n = 0

        for lat_a, lat_b in lat_chunks:
            for lon_a, lon_b in lon_chunks:
                chunk_n += 1
                bbox = _bbox_str(lat_a, lon_a, lat_b, lon_b)
                query_lines = query_template.format(bbox=bbox).strip().splitlines()
                query = f"[out:json][timeout:60];\n(\n" + "\n".join(f"  {l}" for l in query_lines) + "\n);\nout center tags;\n"
                elements = _overpass_fetch(query, timeout=60)
                for el in elements:
                    key = f"{el.get('type')}:{el.get('id')}"
                    if key not in seen:
                        seen[key] = el
                log.info("  chunk %d/%d bbox=%s elements=%d total=%d",
                          chunk_n, total_chunks, bbox, len(elements), len(seen))
                time.sleep(1.0)  # be polite to Overpass

        elements_list = list(seen.values())
        out_file.write_text(json.dumps({
            "route_slug": route_slug,
            "category": cat,
            "bbox": route_bbox,
            "chunk_deg": chunk_deg,
            "count": len(elements_list),
            "elements": elements_list,
        }, ensure_ascii=False), encoding="utf-8")
        log.info("saved %s: %d elements", out_file, len(elements_list))
        results[cat] = {"count": len(elements_list), "cached": True}
        time.sleep(2.0)

    return {
        "ok": True,
        "route_slug": route_slug,
        "cache_dir": str(cache_dir),
        "categories": {cat: results.get(cat, {}) for cat in cats},
        "total_chunks": total_chunks,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    route_bbox = {
        "min_lat": 42.755, "min_lon": 10.456,
        "max_lat": 43.758, "max_lon": 11.682,
    }
    force = "--force" in sys.argv
    result = build_route_cache(
        route_bbox=route_bbox,
        cache_dir="/opt/qbot/artifacts/overpass_cache",
        route_slug="tuscany_2026",
        force=force,
    )
    print(json.dumps(result, indent=2))
