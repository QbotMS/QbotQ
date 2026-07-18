"""Open-data discovery for the canonical route-attraction ranking.

Wikipedia supplies the broad semantic catalogue, Wikidata supplies types and
heritage claims, and Google supplies locations plus supporting ranking evidence.
Google-only rows still pass the same deterministic semantic gate.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

import requests

from qbot3.artifacts.route_analyzer import analyze_route_poi_artifact
from qbot3.routes.route_attraction_engine import (
    haversine_m,
    normalize_analyzer_candidates,
    normalize_google_source_candidates,
)


WIKIPEDIA_API = "https://pl.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
OVERPASS_APIS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
USER_AGENT = "QBot-route-attractions/2.2 (private cycling route planner)"
DEFAULT_CACHE_ROOT = Path(os.getenv("QBOT_ATTRACTION_CACHE_ROOT", "/opt/qbot/artifacts/attraction_cache"))


def _route_points(path: Path) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    total_km = 0.0
    previous: tuple[float, float] | None = None
    for node in ET.parse(path).getroot().iter():
        if not node.tag.endswith("trkpt") and not node.tag.endswith("rtept"):
            continue
        lat, lon = float(node.attrib["lat"]), float(node.attrib["lon"])
        if previous:
            total_km += haversine_m(previous[0], previous[1], lat, lon) / 1000.0
        points.append((total_km, lat, lon))
        previous = (lat, lon)
    if not points:
        raise ValueError(f"No route points in {path}")
    return points


def _at_km(points: list[tuple[float, float, float]], km: float) -> tuple[float, float, float]:
    if km <= 0:
        return points[0]
    if km >= points[-1][0]:
        return points[-1]
    lo, hi = 0, len(points) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if points[mid][0] < km:
            lo = mid
        else:
            hi = mid
    first, second = points[lo], points[hi]
    ratio = (km - first[0]) / max(1e-9, second[0] - first[0])
    return km, first[1] + ratio * (second[1] - first[1]), first[2] + ratio * (second[2] - first[2])


def _samples(points: list[tuple[float, float, float]], step_km: float) -> list[tuple[float, float, float]]:
    count = math.ceil(points[-1][0] / step_km)
    return [_at_km(points, min(points[-1][0], index * step_km)) for index in range(count + 1)]


def _nearest(route: Iterable[tuple[float, float, float]], lat: float, lon: float) -> tuple[float, float]:
    closest = min(route, key=lambda point: haversine_m(point[1], point[2], lat, lon))
    return closest[0], haversine_m(closest[1], closest[2], lat, lon)


def _chunks(values: list[str], size: int = 40) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _cached_json(session: requests.Session, namespace: str, url: str, params: dict[str, Any], cache_root: Path) -> dict[str, Any]:
    key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()[:24]
    path = cache_root / f"{namespace}-{key}.json"
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    last_response = None
    for attempt in range(5):
        response = session.get(url, params=params, timeout=40)
        last_response = response
        if response.status_code not in {429, 502, 503, 504}:
            response.raise_for_status()
            result = response.json()
            try:
                cache_root.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
                temporary.replace(path)
            except OSError:
                pass
            return result
        retry_after = response.headers.get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else min(16.0, 2.0 ** attempt)
        except ValueError:
            delay = min(16.0, 2.0 ** attempt)
        time.sleep(delay)
    assert last_response is not None
    last_response.raise_for_status()
    raise RuntimeError("unreachable")


def discover_wikipedia(
    session: requests.Session,
    points: list[tuple[float, float, float]],
    *,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    corridor_m: float = 2050.0,
) -> list[dict[str, Any]]:
    route = _samples(points, 0.1)
    result: dict[int, dict[str, Any]] = {}
    possible_cities: dict[str, tuple[float, float]] = {}

    def add_page(page: dict[str, Any], fallback: tuple[float, float] | None = None) -> None:
        coordinates = page.get("coordinates") or []
        if coordinates:
            lat, lon = float(coordinates[0]["lat"]), float(coordinates[0]["lon"])
        elif fallback:
            lat, lon = fallback
        else:
            return
        km, distance = _nearest(route, lat, lon)
        if distance > corridor_m or page.get("missing") or page.get("pageid") is None:
            return
        page_id = int(page["pageid"])
        result[page_id] = {
            "name": str(page.get("title") or "").strip(), "lat": lat, "lon": lon,
            "km": km, "dist": distance, "sources": {"wikipedia"}, "pageid": page_id,
            "wiki": f"https://pl.wikipedia.org/?curid={page_id}",
            "qid": (page.get("pageprops") or {}).get("wikibase_item"),
            "extract": page.get("extract") or "",
            "image": (page.get("thumbnail") or {}).get("source"), "tags": {}, "osm_ids": [],
        }

    for _, lat, lon in _samples(points, 12.0):
        data = _cached_json(session, "wiki", WIKIPEDIA_API, {
            "action": "query", "format": "json", "formatversion": 2,
            "generator": "geosearch", "ggscoord": f"{lat:.6f}|{lon:.6f}",
            "ggsradius": 8000, "ggslimit": 100,
            "prop": "coordinates|pageimages|pageprops|extracts", "pithumbsize": 640,
            "exintro": 1, "explaintext": 1, "exsentences": 5,
        }, cache_root)
        for page in data.get("query", {}).get("pages", []):
            title = str(page.get("title") or "")
            coordinates = page.get("coordinates") or []
            if re.search(r"\(gmina(?:\s|\))", title, re.I) and coordinates:
                possible_cities[title.split("(", 1)[0].strip()] = (
                    float(coordinates[0]["lat"]), float(coordinates[0]["lon"]),
                )
            add_page(page)

    # Geosearch frequently returns the surrounding gmina but omits its town.
    for group in _chunks(sorted(possible_cities)):
        data = _cached_json(session, "wiki-cities", WIKIPEDIA_API, {
            "action": "query", "format": "json", "formatversion": 2,
            "titles": "|".join(group), "prop": "coordinates|pageimages|pageprops|extracts",
            "pithumbsize": 640, "exintro": 1, "explaintext": 1, "exsentences": 5,
        }, cache_root)
        for page in data.get("query", {}).get("pages", []):
            add_page(page, possible_cities.get(str(page.get("title") or "")))
    return [row for row in result.values() if not re.search(r"\(gmina(?:\s|\))", row["name"], re.I)]


def discover_wikidata(session: requests.Session, qids: Iterable[str], *, cache_root: Path = DEFAULT_CACHE_ROOT) -> dict[str, dict[str, Any]]:
    identifiers = sorted({qid for qid in qids if isinstance(qid, str) and re.fullmatch(r"Q\d+", qid)})
    entities: dict[str, dict[str, Any]] = {}
    for group in _chunks(identifiers, 50):
        data = _cached_json(session, "wikidata", WIKIDATA_API, {
            "action": "wbgetentities", "format": "json", "ids": "|".join(group),
            "props": "labels|descriptions|claims", "languages": "pl|en|de", "languagefallback": 1,
        }, cache_root)
        entities.update(data.get("entities") or {})
    type_ids: set[str] = set()
    for entity in entities.values():
        for claim in (entity.get("claims") or {}).get("P31", []):
            try:
                type_ids.add(claim["mainsnak"]["datavalue"]["value"]["id"])
            except (KeyError, TypeError):
                pass
    labels: dict[str, str] = {}
    for group in _chunks(sorted(type_ids), 50):
        data = _cached_json(session, "wikidata-types", WIKIDATA_API, {
            "action": "wbgetentities", "format": "json", "ids": "|".join(group),
            "props": "labels", "languages": "pl|en|de", "languagefallback": 1,
        }, cache_root)
        for qid, entity in (data.get("entities") or {}).items():
            values = entity.get("labels") or {}
            labels[qid] = next((values[key]["value"] for key in ("pl", "en", "de") if key in values), "")
    for entity in entities.values():
        entity["types"] = []
        for claim in (entity.get("claims") or {}).get("P31", []):
            try:
                entity["types"].append(labels.get(claim["mainsnak"]["datavalue"]["value"]["id"], ""))
            except (KeyError, TypeError):
                pass
    return entities


def discover_osm_landmarks(
    session: requests.Session,
    points: list[tuple[float, float, float]],
    *,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    corridor_m: float = 2050.0,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch only landmark-like OSM objects; never run the general POI query."""
    route = _samples(points, 0.1)
    found: dict[str, dict[str, Any]] = {}
    missing_chunks = 0
    samples = _samples(points, 2.0)
    chunks = [samples[index:index + 11] for index in range(0, len(samples), 10)]

    def query_for(chunk: list[tuple[float, float, float]]) -> str:
        path_coordinates = ",".join(f"{lat:.6f},{lon:.6f}" for _, lat, lon in chunk)
        around = f"around:{int(corridor_m)},{path_coordinates}"
        return f"""[out:json][timeout:12];(
          nwr({around})[\"historic\"];
          nwr({around})[\"heritage\"];
          nwr({around})[\"military\"~\"bunker|fort|trench\",i];
          nwr({around})[\"tourism\"~\"attraction|museum\",i];
          nwr({around})[\"man_made\"][\"wikipedia\"];
          nwr({around})[\"man_made\"][\"wikidata\"];
        );out center tags;"""

    queries = [query_for(chunk) for chunk in chunks]

    def fetch(query: str) -> None:
        key = hashlib.sha256(query.encode()).hexdigest()[:24]
        path = cache_root / f"osm-landmarks-{key}.json"
        try:
            if path.exists():
                json.loads(path.read_text(encoding="utf-8"))
                return
        except (OSError, ValueError):
            pass
        for endpoint in OVERPASS_APIS:
            try:
                response = requests.post(endpoint, data={"data": query}, timeout=15, headers={"User-Agent": USER_AGENT})
                response.raise_for_status()
                data = response.json()
                try:
                    cache_root.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                except OSError:
                    pass
                return
            except (requests.RequestException, ValueError):
                continue

    with ThreadPoolExecutor(max_workers=min(4, len(queries))) as executor:
        list(executor.map(fetch, queries))

    for query in queries:
        key = hashlib.sha256(query.encode()).hexdigest()[:24]
        path = cache_root / f"osm-landmarks-{key}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        except (OSError, ValueError):
            data = None
        if data is None:
            missing_chunks += 1
            continue
        for element in data.get("elements") or []:
            tags = {str(k): str(v) for k, v in (element.get("tags") or {}).items()}
            center = element.get("center") or element
            if center.get("lat") is None or center.get("lon") is None:
                continue
            elat, elon = float(center["lat"]), float(center["lon"])
            route_km, distance = _nearest(route, elat, elon)
            if distance > corridor_m:
                continue
            osm_id = f"{element.get('type')}:{element.get('id')}"
            name = str(tags.get("name") or tags.get("name:pl") or "").strip()
            if not name and (tags.get("historic") == "bunker" or tags.get("military") == "bunker"):
                name = "Schron bojowy" + (f" {tags['ref']}" if tags.get("ref") else "")
            if not name:
                continue
            wiki = tags.get("wikipedia")
            if wiki and not wiki.startswith("http"):
                language, _, title = wiki.partition(":")
                wiki = f"https://{language or 'pl'}.wikipedia.org/wiki/{title.replace(' ', '_')}"
            found[osm_id] = {
                "name": name, "lat": elat, "lon": elon, "km": route_km, "dist": distance,
                "sources": {"osm"}, "pageid": None, "wiki": wiki,
                "qid": tags.get("wikidata"), "extract": tags.get("description") or tags.get("inscription") or "",
                "image": tags.get("image"), "tags": tags, "osm_ids": [osm_id],
            }
    return list(found.values()), missing_chunks


def discover_sources(source_path: Path, *, route_id: str, route_distance_km: float) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    points = _route_points(source_path)
    wikipedia = discover_wikipedia(session, points)
    osm_rows, osm_missing = discover_osm_landmarks(session, points)
    google_analysis = analyze_route_poi_artifact(
        str(source_path), route_id=route_id, km_from=0.0, km_to=route_distance_km,
        buffers={"google_hours": False, "open_window": False, "attractions_enabled": True,
                 "overpass_enabled": False, "attractions_m": 2050.0, "analysis_timeout_sec": 120.0},
        focus="attractions_only", output_format="json",
    )
    _, google_rows = normalize_analyzer_candidates(google_analysis.get("attractions") or [])
    combined = wikipedia + osm_rows + normalize_google_source_candidates(google_rows)
    wikidata = discover_wikidata(session, (row.get("qid") for row in combined))
    # Wikipedia is the complete semantic baseline. OSM is additive and may be
    # temporarily degraded; keep the honest missing-chunk count and retry those
    # chunks on the next fetch instead of suppressing all valid attractions.
    status = "COMPLETE" if osm_missing == 0 else "DEGRADED_OSM"
    return {
        "status": status,
        "complete": True,
        "source_rows": combined,
        "google_rows": google_rows,
        "wikidata": wikidata,
        "source_status": {
            "wikipedia": len(wikipedia), "osm": len(osm_rows), "google": len(google_rows),
            "wikidata": len(wikidata), "analyzer_status": status,
            "missing_chunks": osm_missing,
        },
    }
