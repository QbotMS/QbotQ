#!/usr/bin/env python3
"""RWGPS sectors: land cover and surface cascade for unknown surface."""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2


OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
USER_AGENT = "QBot/1.0 (personal assistant; michal@qbot)"

_LANDCOVER_CACHE: dict[tuple[float, float], str] = {}
_LANDCOVER_BATCH_CACHE: dict[tuple[float, float, float, float], list[dict[str, Any]]] = {}
_HIGHWAY_BATCH_CACHE: dict[tuple[float, float, float, float], list[dict[str, Any]]] = {}


def _load_env_local() -> None:
    p = Path(__file__).resolve().parents[2] / ".env.local"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)


def _db_connect():
    _load_env_local()
    kwargs = {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER", "qbot"),
        "dbname": os.getenv("PGDATABASE", "qbot"),
    }
    pw = os.getenv("PGPASSWORD")
    if pw:
        kwargs["password"] = pw
    return psycopg2.connect(**kwargs)


def _overpass(query: str, timeout: int = 30) -> dict[str, Any] | None:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    retry_statuses = {429, 502, 503, 504}
    for url in OVERPASS_URLS:
        try:
            resp = httpx.post(url, data={"data": query}, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                try:
                    payload = resp.json()
                except ValueError:
                    payload = None
                if isinstance(payload, dict):
                    return payload
        except httpx.HTTPError:
            pass
        finally:
            time.sleep(0.5)
    return None


def _tags_from_overpass(payload: dict[str, Any] | None) -> list[dict[str, str]]:
    if not payload:
        return []
    out: list[dict[str, str]] = []
    for el in payload.get("elements", []):
        tags = el.get("tags")
        if isinstance(tags, dict) and tags:
            out.append({str(k): str(v) for k, v in tags.items() if v is not None})
    return out


def _bbox_of(sectors: list[dict[str, Any]], pad_deg: float = 0.01) -> tuple[float, float, float, float] | None:
    lats: list[float] = []
    lons: list[float] = []
    for sector in sectors:
        mid_lat = sector.get("mid_lat")
        mid_lon = sector.get("mid_lon")
        if mid_lat is None or mid_lon is None:
            continue
        try:
            lats.append(float(mid_lat))
            lons.append(float(mid_lon))
        except (TypeError, ValueError):
            continue
    if not lats or not lons:
        return None
    return (min(lats) - pad_deg, min(lons) - pad_deg, max(lats) + pad_deg, max(lons) + pad_deg)


def _point_in_ring(lat: float, lon: float, ring: list[tuple[float, float]]) -> bool:
    if len(ring) < 3:
        return False
    inside = False
    x = float(lon)
    y = float(lat)
    n = len(ring)
    for i in range(n):
        y1, x1 = ring[i]
        y2, x2 = ring[(i + 1) % n]
        y1 = float(y1)
        x1 = float(x1)
        y2 = float(y2)
        x2 = float(x2)
        intersects = ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1)
        if intersects:
            inside = not inside
    return inside


def _fetch_landuse(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    key = tuple(round(v, 5) for v in bbox)
    cached = _LANDCOVER_BATCH_CACHE.get(key)
    if cached is not None:
        return cached
    s, w, n, e = bbox
    query = (
        f"[out:json][timeout:60];"
        f"(way[\"landuse\"]({s},{w},{n},{e});"
        f"way[\"natural\"~\"water|wood|wetland|scrub|grassland|heath\"]({s},{w},{n},{e}););"
        "out geom;"
    )
    payload = _overpass(query, timeout=60)
    out: list[dict[str, Any]] = []
    for el in (payload or {}).get("elements", []):
        # Multipolygon (relacje) pominięte swiadomie — wymaga sklejania outer ringow; TODO later.
        if el.get("type") != "way":
            continue
        tags = el.get("tags")
        if not isinstance(tags, dict):
            continue
        el_tags = {str(k): str(v) for k, v in tags.items() if v is not None}
        geometry = el.get("geometry")
        if not isinstance(geometry, list):
            continue
        ring: list[tuple[float, float]] = []
        for p in geometry:
            if not isinstance(p, dict):
                continue
            if "lat" not in p or "lon" not in p:
                continue
            try:
                ring.append((float(p["lat"]), float(p["lon"])))
            except (TypeError, ValueError):
                continue
        if len(ring) >= 3:
            out.append({"tags": el_tags, "ring": ring})
    _LANDCOVER_BATCH_CACHE[key] = out
    return out


def _landcover_rank(label: str) -> int:
    order = {
        "las": 0,
        "woda": 1,
        "pola": 2,
        "laki/zielen": 3,
        "zabudowa": 4,
        "surowa": 5,
        "teren otwarty": 99,
    }
    return order.get(label, 50)


def classify_tags(tags: dict[str, Any]) -> str:
    landuse = str(tags.get("landuse", "")).strip().lower()
    natural = str(tags.get("natural", "")).strip().lower()
    building = str(tags.get("building", "")).strip().lower()
    place = str(tags.get("place", "")).strip().lower()

    if landuse == "forest" or natural == "wood":
        return "las"
    if natural == "water" or landuse in {"reservoir", "basin"}:
        return "woda"
    if landuse == "farmland":
        return "pola"
    if landuse in {"meadow", "grass", "greenfield", "orchard", "vineyard", "allotments"} or natural in {"grassland", "scrub", "heath"}:
        return "laki/zielen"
    if landuse in {"residential", "industrial", "commercial", "retail", "construction", "railway"} or building or place:
        return "zabudowa"
    if landuse in {"quarry", "brownfield", "landfill"} or natural in {"bare_rock", "sand", "scree", "shingle"}:
        return "surowa"
    return "teren otwarty"


def landcover_for_point(lat: float, lon: float, polygons: list[dict[str, Any]]) -> str:
    candidates: list[str] = []
    for poly in polygons:
        ring = poly.get("ring")
        tags = poly.get("tags")
        if not isinstance(ring, list) or not isinstance(tags, dict):
            continue
        if _point_in_ring(lat, lon, ring):
            candidates.append(classify_tags(tags))
    if not candidates:
        return "teren otwarty"
    candidates.sort(key=_landcover_rank)
    return candidates[0]


def _fetch_highways(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    key = tuple(round(v, 5) for v in bbox)
    cached = _HIGHWAY_BATCH_CACHE.get(key)
    if cached is not None:
        return cached
    s, w, n, e = bbox
    query = f'[out:json][timeout:60];way["highway"]({s},{w},{n},{e});out tags geom;'
    payload = _overpass(query, timeout=60)
    out: list[dict[str, Any]] = []
    for el in (payload or {}).get("elements", []):
        tags = el.get("tags")
        geometry = el.get("geometry")
        if not isinstance(tags, dict) or not isinstance(geometry, list):
            continue
        ring: list[tuple[float, float]] = []
        for p in geometry:
            if not isinstance(p, dict):
                continue
            if "lat" not in p or "lon" not in p:
                continue
            try:
                ring.append((float(p["lat"]), float(p["lon"])))
            except (TypeError, ValueError):
                continue
        if len(ring) < 2:
            continue
        out.append({"tags": {str(k): str(v) for k, v in tags.items() if v is not None}, "ring": ring})
    _HIGHWAY_BATCH_CACHE[key] = out
    return out


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    r = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2.0) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2.0) ** 2
    return 2.0 * r * asin(min(1.0, sqrt(a)))


def _dist_point_to_polyline_m(lat: float, lon: float, ring: list[tuple[float, float]]) -> float:
    best = float("inf")
    for p_lat, p_lon in ring:
        dist = _haversine_m(lat, lon, float(p_lat), float(p_lon))
        if dist < best:
            best = dist
    return best


def highway_surface_for_point(
    lat: float,
    lon: float,
    highways: list[dict[str, Any]],
    max_m: float = 80,
) -> tuple[str | None, str]:
    best_item: dict[str, Any] | None = None
    best_dist = float("inf")
    for item in highways:
        ring = item.get("ring")
        tags = item.get("tags")
        if not isinstance(ring, list) or not isinstance(tags, dict) or len(ring) < 2:
            continue
        dist = _dist_point_to_polyline_m(lat, lon, ring)
        if dist < best_dist:
            best_dist = dist
            best_item = item
    if best_item is None or best_dist > float(max_m):
        return None, "none"

    tags = best_item["tags"]
    tracktype = str(tags.get("tracktype", "")).strip().lower()
    if tracktype == "grade1":
        return "szuter ubity (szac.)", "tracktype"
    if tracktype == "grade2":
        return "szuter (szac.)", "tracktype"
    if tracktype == "grade3":
        return "gruntowa (szac.)", "tracktype"
    if tracktype in {"grade4", "grade5"}:
        return "gruntowa techniczna (szac.)", "tracktype"

    highway_val = str(tags.get("highway", "")).strip().lower()
    if highway_val == "track":
        return "gruntowa/szuter (szac.)", "highway"
    if highway_val == "path":
        return "sciezka (szac.)", "highway"
    if highway_val in {"residential", "living_street", "unclassified", "tertiary", "secondary", "primary", "trunk", "service"}:
        return "asfalt (szac.)", "highway"
    if highway_val == "cycleway":
        return "asfalt/utwardzona (szac.)", "highway"
    return None, "none"


def _norm_surface(value: Any) -> str:
    txt = str(value).strip().lower() if value is not None else ""
    return txt or "nieznana"


def _merge_adjacent(sectors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for item in sectors:
        if merged and merged[-1]["surface"] == item["surface"]:
            merged[-1]["e_m"] = item["e_m"]
            merged[-1]["frames"].extend(item["frames"])
        else:
            merged.append(
                {
                    "s_m": item["s_m"],
                    "e_m": item["e_m"],
                    "surface": item["surface"],
                    "frames": list(item["frames"]),
                }
            )
    return merged


def build_sectors(
    artifact_id: int | None = None,
    route_id: str | None = None,
    frame_size: int = 80,
    min_seg_m: float = 250.0,
) -> list[dict[str, Any]]:
    conn = _db_connect()
    cur = conn.cursor()
    if artifact_id is not None:
        cur.execute(
            "SELECT frame_index, dist_start_m, dist_end_m, surface, mid_lat, mid_lon "
            "FROM qbot_v2.route_frames "
            "WHERE route_artifact_id=%s AND frame_size_m=%s ORDER BY frame_index",
            (artifact_id, int(frame_size)),
        )
    else:
        cur.execute(
            "SELECT frame_index, dist_start_m, dist_end_m, surface, mid_lat, mid_lon "
            "FROM qbot_v2.route_frames "
            "WHERE route_id=%s AND frame_size_m=%s ORDER BY frame_index",
            (route_id, int(frame_size)),
        )
    rows = cur.fetchall()
    if not rows:
        return []

    merged: list[dict[str, Any]] = []
    for frame_index, s_m, e_m, surface, mid_lat, mid_lon in rows:
        item = {
            "s_m": float(s_m),
            "e_m": float(e_m),
            "surface": _norm_surface(surface),
            "frames": [
                {
                    "frame_index": int(frame_index),
                    "mid_m": (float(s_m) + float(e_m)) / 2.0,
                    "mid_lat": float(mid_lat) if mid_lat is not None else None,
                    "mid_lon": float(mid_lon) if mid_lon is not None else None,
                }
            ],
        }
        if merged and merged[-1]["surface"] == item["surface"]:
            merged[-1]["e_m"] = item["e_m"]
            merged[-1]["frames"].extend(item["frames"])
        else:
            merged.append(item)

    cleaned: list[dict[str, Any]] = []
    for seg in merged:
        if cleaned and (seg["e_m"] - seg["s_m"]) < float(min_seg_m):
            cleaned[-1]["e_m"] = seg["e_m"]
            cleaned[-1]["frames"].extend(seg["frames"])
        else:
            cleaned.append(seg)

    final = _merge_adjacent(cleaned)
    out: list[dict[str, Any]] = []
    for seg in final:
        mid_m = (seg["s_m"] + seg["e_m"]) / 2.0
        best_frame = None
        best_dist = float("inf")
        for fr in seg["frames"]:
            if fr["mid_lat"] is None or fr["mid_lon"] is None:
                continue
            dist = abs(fr["mid_m"] - mid_m)
            if dist < best_dist:
                best_dist = dist
                best_frame = fr
        out.append(
            {
                "s_m": seg["s_m"],
                "e_m": seg["e_m"],
                "surface": seg["surface"],
                "mid_lat": best_frame["mid_lat"] if best_frame else None,
                "mid_lon": best_frame["mid_lon"] if best_frame else None,
            }
        )
    return out


def annotate_sectors(
    sectors: list[dict[str, Any]],
    want_landcover: bool = True,
    want_surface_cascade: bool = True,
) -> list[dict[str, Any]]:
    bbox = _bbox_of(sectors)
    if bbox is None:
        return sectors

    polygons: list[dict[str, Any]] = []
    highways: list[dict[str, Any]] = []

    if want_landcover:
        try:
            polygons = _fetch_landuse(bbox)
        except Exception:
            polygons = []

    need_surface = want_surface_cascade and any(sector.get("surface") in (None, "", "nieznana") for sector in sectors)
    if need_surface:
        try:
            highways = _fetch_highways(bbox)
        except Exception:
            highways = []

    for sector in sectors:
        mid_lat = sector.get("mid_lat")
        mid_lon = sector.get("mid_lon")
        if want_landcover and mid_lat is not None and mid_lon is not None:
            try:
                sector["land_cover"] = landcover_for_point(float(mid_lat), float(mid_lon), polygons)
            except Exception:
                pass
        if want_surface_cascade and sector.get("surface") in (None, "", "nieznana") and mid_lat is not None and mid_lon is not None:
            try:
                guess, source = highway_surface_for_point(float(mid_lat), float(mid_lon), highways)
                if guess:
                    sector["surface_guess"] = guess
                    sector["surface_guess_source"] = source
            except Exception:
                pass
    return sectors


def render_sectors_text(sectors: list[dict[str, Any]]) -> str:
    if not sectors:
        return "Brak sektorow."

    lines: list[str] = []
    land_cover_m: Counter[str] = Counter()
    land_cover_total = 0.0

    for sector in sectors:
        s_km = float(sector["s_m"]) / 1000.0
        e_km = float(sector["e_m"]) / 1000.0
        span_km = e_km - s_km
        surface = sector.get("surface") or "nieznana"
        parts = [f"  km {s_km:.1f}-{e_km:.1f} ({span_km:.1f}): {surface}"]
        land_cover = sector.get("land_cover")
        if land_cover:
            parts.append(f"teren: {land_cover}")
            land_cover_m[str(land_cover)] += max(float(sector["e_m"]) - float(sector["s_m"]), 0.0)
            land_cover_total += max(float(sector["e_m"]) - float(sector["s_m"]), 0.0)
        surface_guess = sector.get("surface_guess")
        if surface_guess:
            parts.append(f"~ {surface_guess}")
        lines.append("{0}".format(" , ".join(parts)))

    if land_cover_total > 0:
        items = [f"{name} {land_cover_m[name] / land_cover_total * 100.0:.0f}%" for name, _ in land_cover_m.most_common()]
        lines.append("Pokrycie terenu: " + ", ".join(items))
    else:
        lines.append("Pokrycie terenu: brak danych")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--artifact-id", type=int)
    g.add_argument("--route-id", type=str)
    ap.add_argument("--frame-size", type=int, default=80)
    ap.add_argument("--no-landcover", action="store_true")
    ap.add_argument("--no-cascade", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = _parse_args()
    sectors = build_sectors(args.artifact_id, args.route_id, args.frame_size)
    sectors = annotate_sectors(
        sectors,
        want_landcover=not args.no_landcover,
        want_surface_cascade=not args.no_cascade,
    )
    print(render_sectors_text(sectors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
