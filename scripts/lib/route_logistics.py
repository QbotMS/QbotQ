#!/usr/bin/env python3
"""QBot Route Logistics — shared library.

POI model, Overpass queries, buffer/distance calculations, GPX I/O, artifact writers.

Two-stage architecture:
  TEMPO 1: candidates → candidates.json/.geojson/.md/.xlsx
  TEMPO 2: commit-poi → selected_poi.json/.geojson/.gpx
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARTIFACTS_ROOT = Path("/opt/qbot/artifacts")
RWGPS_EXPORT_DIR = ARTIFACTS_ROOT / "exports" / "rwgps"
LOGISTICS_DIR = ARTIFACTS_ROOT / "route_logistics"

DEFAULT_BUFFERS: dict[str, int] = {
    "shops": 500,
    "water": 500,
    "pharmacy": 500,
    "food": 1000,
    "attractions": 1000,
    "bike_service": 3000,
    "transport": 1000,
    "lodging": 0,  # requires user input
}

CATEGORY_LABELS: dict[str, str] = {
    "shops": "Sklepy",
    "water": "Woda / picie",
    "food": "Gastronomia",
    "lodging": "Noclegi",
    "attractions": "Atrakcje",
    "bike_service": "Serwis rowerowy",
    "pharmacy": "Apteki",
    "transport": "Transport",
}

CATEGORY_ORDER = ["shops", "water", "food", "lodging", "attractions", "bike_service", "pharmacy", "transport"]

QUALITY_STATUSES = {
    "CONFIRMED": "Potwierdzony",
    "SOURCE_ONLY": "Tylko ze źródła",
    "LOW_CONFIDENCE": "Niska pewność",
    "NEEDS_REVIEW": "Wymaga przeglądu",
    "NEEDS_REQUIREMENTS": "Wymaga parametrów",
    "PRICE_UNKNOWN": "Cena nieznana",
    "AVAILABILITY_UNKNOWN": "Dostępność nieznana",
    "DETOUR": "Objazd / poza trasą",
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class POICandidate:
    candidate_id: str = ""
    category: str = ""
    subtype: str = ""
    name: str = ""
    lat: float = 0.0
    lon: float = 0.0
    distance_from_track_m: float | None = None
    distance_from_stage_end_m: float | None = None
    km_on_route: float | None = None
    detour_m: float | None = None
    source: str = "OSM"
    source_url: str | None = None
    confidence: str = "SOURCE_ONLY"
    status: str = "CANDIDATE"
    notes: str = ""
    opening_hours: str | None = None
    phone: str | None = None
    website: str | None = None
    estimated_stop_time_min: int | None = None
    price_eur: float | None = None
    availability: str | None = None
    rating: float | None = None
    osm_id: str | None = None
    osm_type: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @staticmethod
    def from_osm(element: dict, category: str, subtype: str, lat: float, lon: float) -> POICandidate:
        tags = element.get("tags", {})
        name = tags.get("name", tags.get("brand", tags.get("operator", element.get("id", "?"))))
        return POICandidate(
            candidate_id=f"{category}_{abs(hash(str(element.get('id','')))) % 10000:04d}",
            category=category,
            subtype=subtype,
            name=str(name)[:80],
            lat=lat,
            lon=lon,
            source="OSM",
            osm_id=str(element.get("id", "")),
            osm_type=element.get("type", "node"),
            confidence="SOURCE_ONLY",
            status="CANDIDATE",
            opening_hours=tags.get("opening_hours"),
            phone=tags.get("phone", tags.get("contact:phone")),
            website=tags.get("website", tags.get("contact:website")),
            notes=f"Do review; source: OSM",
        )


# ---------------------------------------------------------------------------
# GPX loading
# ---------------------------------------------------------------------------

def load_gpx_track(gpx_path: Path) -> list[dict[str, float]]:
    """Load track points from a GPX file. Returns list of {lat, lon, ele?}."""
    if not gpx_path.exists():
        raise FileNotFoundError(f"GPX not found: {gpx_path}")
    tree = ET.parse(str(gpx_path))
    root = tree.getroot()
    ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
    points: list[dict] = []
    for trkpt in root.iter("{http://www.topografix.com/GPX/1/1}trkpt"):
        lat = float(trkpt.attrib["lat"])
        lon = float(trkpt.attrib["lon"])
        ele_el = trkpt.find("{http://www.topografix.com/GPX/1/1}ele")
        ele = float(ele_el.text) if ele_el is not None and ele_el.text else None
        pt = {"lat": lat, "lon": lon}
        if ele is not None:
            pt["ele"] = ele
        points.append(pt)
    if not points:
        raise ValueError(f"No track points found in {gpx_path}")
    return points


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters."""
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return float(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def nearest_track_distance(lat: float, lon: float, track: list[dict]) -> tuple[float, int, float]:
    """Find nearest track point to (lat,lon). Returns (distance_m, index, km_on_route)."""
    best_dist = float("inf")
    best_idx = 0
    cumul_km = [0.0]
    for i in range(1, len(track)):
        d = haversine_m(track[i - 1]["lat"], track[i - 1]["lon"], track[i]["lat"], track[i]["lon"])
        cumul_km.append(cumul_km[-1] + d / 1000)

    for i, pt in enumerate(track):
        d = haversine_m(lat, lon, pt["lat"], pt["lon"])
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_dist, best_idx, cumul_km[best_idx] if best_idx < len(cumul_km) else 0.0


def detour_from_track(lat: float, lon: float, track: list[dict]) -> float:
    """Estimate detour in meters: distance from POI back to nearest track point * 2."""
    dist_m, _, _ = nearest_track_distance(lat, lon, track)
    return dist_m * 2


# ---------------------------------------------------------------------------
# Overpass queries
# ---------------------------------------------------------------------------

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

OVERPASS_QUERIES: dict[str, str] = {
    "shops": """
[out:json][timeout:15];
(
  node["shop"](around:{buffer},{lat},{lon});
  node["amenity"="marketplace"](around:{buffer},{lat},{lon});
  node["amenity"="convenience_store"](around:{buffer},{lat},{lon});
  node["amenity"="supermarket"](around:{buffer},{lat},{lon});
);
out center tags {nwr};
""",
    "water": """
[out:json][timeout:15];
(
  node["amenity"="drinking_water"](around:{buffer},{lat},{lon});
  node["amenity"="water_point"](around:{buffer},{lat},{lon});
  node["natural"="spring"](around:{buffer},{lat},{lon});
  node["man_made"="water_tap"](around:{buffer},{lat},{lon});
);
out center tags {nwr};
""",
    "food": """
[out:json][timeout:20];
(
  node["amenity"~"restaurant|cafe|fast_food|pub|bar|food_court|ice_cream"](around:{buffer},{lat},{lon});
  node["shop"="bakery"](around:{buffer},{lat},{lon});
  node["shop"="deli"](around:{buffer},{lat},{lon});
  node["shop"="convenience"](around:{buffer},{lat},{lon});
);
out center tags {nwr};
""",
    "attractions": """
[out:json][timeout:25];
(
  node["tourism"~"attraction|viewpoint|museum|artwork|gallery|picnic_site|zoo|theme_park"](around:{buffer},{lat},{lon});
  node["historic"](around:{buffer},{lat},{lon});
  node["natural"="peak"](around:{buffer},{lat},{lon});
  node["natural"="volcano"](around:{buffer},{lat},{lon});
  node["leisure"="park"](around:{buffer},{lat},{lon});
  node["leisure"="nature_reserve"](around:{buffer},{lat},{lon});
  way["tourism"~"attraction|viewpoint|museum"](around:{buffer},{lat},{lon});
  way["historic"](around:{buffer},{lat},{lon});
);
out center tags {nwr};
""",
    "bike_service": """
[out:json][timeout:15];
(
  node["shop"="bicycle"](around:{buffer},{lat},{lon});
  node["amenity"="bicycle_repair_station"](around:{buffer},{lat},{lon});
  node["amenity"="bicycle_rental"](around:{buffer},{lat},{lon});
  node["shop"="outdoor"](around:{buffer},{lat},{lon});
  node["craft"="bicycle_repair"](around:{buffer},{lat},{lon});
);
out center tags {nwr};
""",
    "pharmacy": """
[out:json][timeout:15];
(
  node["amenity"="pharmacy"](around:{buffer},{lat},{lon});
  node["amenity"="hospital"](around:{buffer},{lat},{lon});
  node["amenity"="clinic"](around:{buffer},{lat},{lon});
  node["amenity"="dentist"](around:{buffer},{lat},{lon});
  node["amenity"="veterinary"](around:{buffer},{lat},{lon});
);
out center tags {nwr};
""",
    "transport": """
[out:json][timeout:15];
(
  node["amenity"="bus_station"](around:{buffer},{lat},{lon});
  node["amenity"="ferry_terminal"](around:{buffer},{lat},{lon});
  node["amenity"="taxi"](around:{buffer},{lat},{lon});
  node["railway"="station"](around:{buffer},{lat},{lon});
  node["public_transport"="stop_position"](around:{buffer},{lat},{lon});
);
out center tags {nwr};
""",
    "lodging": """
[out:json][timeout:20];
(
  node["tourism"~"hotel|guest_house|hostel|apartment|motel|resort"](around:{buffer},{lat},{lon});
  node["tourism"="camp_site"](around:{buffer},{lat},{lon});
  node["tourism"="alpine_hut"](around:{buffer},{lat},{lon});
  node["tourism"="chalet"](around:{buffer},{lat},{lon});
  way["tourism"~"hotel|guest_house|hostel|apartment|motel|resort"](around:{buffer},{lat},{lon});
);
out center tags {nwr};
""",
}


def _overpass_category(category: str, lat: float, lon: float, buffer_m: int) -> tuple[list[dict], dict]:
    """Query Overpass for a category. Returns (elements, debug_info)."""
    import httpx
    query = OVERPASS_QUERIES.get(category)
    if not query:
        return [], {"endpoint": None, "status": "no_query", "error": f"no query for category {category}"}
    q = query.replace("{nwr}", "center").format(lat=lat, lon=lon, buffer=buffer_m)

    last_error = None
    for url in OVERPASS_URLS:
        try:
            resp = httpx.post(url, data={"data": q}, timeout=25)
            resp.raise_for_status()
            data = resp.json()
            return data.get("elements", []), {
                "endpoint": url,
                "status": "ok",
                "http_status": resp.status_code,
            }
        except httpx.ConnectError as exc:
            last_error = f"ConnectError: {exc}"
            continue
        except httpx.TimeoutException as exc:
            last_error = f"Timeout: {exc}"
            continue
        except Exception as exc:
            last_error = f"{exc.__class__.__name__}: {exc}"
            continue

    return [], {"endpoint": None, "status": "all_failed", "error": last_error}


def _overpass_segmented(
    category: str,
    track: list[dict],
    buffer_m: int,
    segment_interval_km: float = 10.0,
) -> tuple[list[dict], dict]:
    """Query Overpass for a category along a track, segmenting every N km.
    Returns (elements, debug_info)."""
    all_elements: list[dict] = []
    seen_ids: set[str] = set()

    sample_dist = segment_interval_km * 1000
    cumulative = 0.0
    sample_points = [track[0]]
    for i in range(1, len(track)):
        cumulative += haversine_m(track[i - 1]["lat"], track[i - 1]["lon"], track[i]["lat"], track[i]["lon"])
        if cumulative >= sample_dist:
            sample_points.append(track[i])
            cumulative = 0.0
    if sample_points[-1] != track[-1]:
        sample_points.append(track[-1])

    endpoint_used = None
    api_status = "ok"
    api_error = None
    for pt in sample_points:
        elements, dbg = _overpass_category(category, pt["lat"], pt["lon"], buffer_m)
        if not endpoint_used:
            endpoint_used = dbg.get("endpoint")
        if dbg.get("status") == "all_failed":
            api_status = "all_failed"
            api_error = dbg.get("error")
        for el in elements:
            el_id = f"{el.get('type', 'node')}_{el.get('id', '')}"
            if el_id not in seen_ids:
                seen_ids.add(el_id)
                all_elements.append(el)
        time.sleep(0.5)  # rate limit

    return all_elements, {
        "endpoint": endpoint_used,
        "status": api_status,
        "error": api_error,
        "sample_points": len(sample_points),
    }


# ---------------------------------------------------------------------------
# Candidate processing
# ---------------------------------------------------------------------------

def osm_elements_to_candidates(
    elements: list[dict],
    category: str,
    track: list[dict] | None = None,
) -> list[POICandidate]:
    """Convert raw OSM elements to POICandidate list."""
    candidates: list[POICandidate] = []
    seen_positions: set[str] = set()

    for el in elements:
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue

        pos_key = f"{lat:.5f}_{lon:.5f}"
        if pos_key in seen_positions:
            continue
        seen_positions.add(pos_key)

        tags = el.get("tags", {})

        # Determine subtype
        subtype = _determine_subtype(category, tags)

        candidate = POICandidate.from_osm(el, category, subtype, float(lat), float(lon))

        if track:
            dist_m, idx, km_on = nearest_track_distance(float(lat), float(lon), track)
            candidate.distance_from_track_m = round(dist_m, 1)
            candidate.km_on_route = round(km_on, 2)
            if dist_m > 50:
                candidate.detour_m = round(dist_m * 2, 1)
            if dist_m > 200:
                candidate.notes += "; DETOUR"
                if candidate.confidence == "SOURCE_ONLY":
                    candidate.confidence = "DETOUR"

        candidates.append(candidate)

    return candidates


def _determine_subtype(category: str, tags: dict) -> str:
    """Determine POI subtype from OSM tags."""
    if category == "shops":
        return tags.get("shop", "unknown_shop")
    elif category == "food":
        return tags.get("amenity", tags.get("shop", "unknown_food"))
    elif category == "attractions":
        if tags.get("tourism"):
            return tags["tourism"]
        if tags.get("historic"):
            return f"historic_{tags['historic']}"
        if tags.get("natural"):
            return f"natural_{tags['natural']}"
        return tags.get("leisure", "unknown_attraction")
    elif category == "lodging":
        return tags.get("tourism", "unknown_lodging")
    elif category == "bike_service":
        return tags.get("shop", tags.get("amenity", tags.get("craft", "bike_service")))
    elif category == "pharmacy":
        return tags.get("amenity", "pharmacy")
    elif category == "water":
        return tags.get("amenity", tags.get("natural", tags.get("man_made", "water")))
    elif category == "transport":
        return tags.get("amenity", tags.get("railway", tags.get("public_transport", "transport")))
    return "unknown"


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------

def ensure_dir(route_id: str) -> Path:
    out = LOGISTICS_DIR / str(route_id)
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_candidates_json(candidates: list[POICandidate], route_id: str, mode: str,
                          stage: int | None, warnings: list[str], errors: list[str]) -> Path:
    out_dir = ensure_dir(route_id)
    path = out_dir / "candidates.json"
    counts: dict[str, int] = {cat: 0 for cat in CATEGORY_ORDER}
    for c in candidates:
        counts[c.category] = counts.get(c.category, 0) + 1

    payload = {
        "ok": True,
        "status": "CANDIDATES_READY",
        "route_id": str(route_id),
        "stage": stage,
        "mode": mode,
        "counts": counts,
        "candidates": [c.to_dict() for c in candidates],
        "artifacts": {
            "candidates_json": str(path),
            "candidates_geojson": str(out_dir / "candidates.geojson"),
            "candidates_md": str(out_dir / "candidates.md"),
        },
        "warnings": warnings,
        "errors": errors,
        "next_action": "manual_review",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_candidates_geojson(candidates: list[POICandidate], route_id: str) -> Path:
    out_dir = ensure_dir(route_id)
    path = out_dir / "candidates.geojson"
    features = []
    for c in candidates:
        feat = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [c.lon, c.lat]},
            "properties": {
                "candidate_id": c.candidate_id,
                "category": c.category,
                "subtype": c.subtype,
                "name": c.name,
                "distance_from_track_m": c.distance_from_track_m,
                "km_on_route": c.km_on_route,
                "detour_m": c.detour_m,
                "confidence": c.confidence,
                "status": c.status,
            },
        }
        features.append(feat)
    geojson = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_candidates_md(candidates: list[POICandidate], route_id: str, mode: str) -> Path:
    out_dir = ensure_dir(route_id)
    path = out_dir / "candidates.md"

    lines = [f"# QBot Route Logistics — Kandydaci", f"**Trasa:** {route_id}  ", f"**Tryb:** {mode}  ", f"**Data:** {date.today().isoformat()}  ", ""]

    for cat in CATEGORY_ORDER:
        cat_candidates = [c for c in candidates if c.category == cat]
        if not cat_candidates:
            continue
        lines.append(f"## {CATEGORY_LABELS.get(cat, cat)} ({len(cat_candidates)})")
        lines.append("")
        lines.append("| ID | Nazwa | Typ | km na trasie | Odległość | Pewność |")
        lines.append("|---|---|---|---|---|---|")
        for c in cat_candidates:
            dist_s = f"{c.distance_from_track_m:.0f}m" if c.distance_from_track_m is not None else "-"
            km_s = f"{c.km_on_route:.1f}" if c.km_on_route is not None else "-"
            lines.append(f"| {c.candidate_id} | {c.name} | {c.subtype} | {km_s} | {dist_s} | {c.confidence} |")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_candidates_xlsx(candidates: list[POICandidate], route_id: str) -> Path:
    """Write candidates to xlsx. Falls back to CSV if openpyxl unavailable."""
    out_dir = ensure_dir(route_id)
    path = out_dir / "candidates.xlsx"
    csv_path = out_dir / "candidates.csv"

    rows = []
    for c in candidates:
        rows.append({
            "candidate_id": c.candidate_id,
            "category": c.category,
            "subtype": c.subtype,
            "name": c.name,
            "lat": c.lat,
            "lon": c.lon,
            "distance_from_track_m": c.distance_from_track_m,
            "km_on_route": c.km_on_route,
            "detour_m": c.detour_m,
            "confidence": c.confidence,
            "status": c.status,
            "notes": c.notes,
        })

    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Kandydaci"
        if rows:
            ws.append(list(rows[0].keys()))
            for r in rows:
                ws.append(list(r.values()))
        wb.save(str(path))
    except ImportError:
        # Fallback to CSV
        with open(str(csv_path), "w", newline="", encoding="utf-8") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=rows[0].keys())
                w.writeheader()
                w.writerows(rows)
        path = csv_path
    return path


def write_debug_json(data: dict, route_id: str) -> Path:
    out_dir = ensure_dir(route_id)
    path = out_dir / "debug.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Commit POI writers
# ---------------------------------------------------------------------------

def write_selected_poi_json(selected: list[POICandidate], route_id: str) -> Path:
    out_dir = ensure_dir(route_id)
    path = out_dir / "selected_poi.json"
    counts = {cat: 0 for cat in CATEGORY_ORDER}
    for c in selected:
        counts[c.category] = counts.get(c.category, 0) + 1

    payload = {
        "ok": True,
        "status": "GPX_READY_FOR_RIDEWITHGPS_IMPORT",
        "route_id": str(route_id),
        "selected_count": len(selected),
        "counts": {k: v for k, v in counts.items() if v},
        "pois": [c.to_dict() for c in selected],
        "artifacts": {
            "selected_poi_json": str(path),
            "selected_poi_geojson": str(out_dir / "selected_poi.geojson"),
            "selected_poi_gpx": str(out_dir / "selected_poi.gpx"),
            "route_with_selected_poi_gpx": str(out_dir / "route_with_selected_poi.gpx"),
            "summary_md": str(out_dir / "poi_commit_summary.md"),
        },
        "import_gpx": str(out_dir / "route_with_selected_poi.gpx"),
        "next_action": "rwgps_import_via_enriched_gpx",
        "notes": "Import route_with_selected_poi.gpx to RWGPS as a new route (contains track + POI waypoints). selected_poi.gpx is debug-only, not for import.",
        "committed_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_selected_poi_geojson(selected: list[POICandidate], route_id: str) -> Path:
    out_dir = ensure_dir(route_id)
    path = out_dir / "selected_poi.geojson"
    features = []
    for c in selected:
        feat = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [c.lon, c.lat]},
            "properties": {
                "candidate_id": c.candidate_id,
                "category": c.category,
                "subtype": c.subtype,
                "name": c.name,
                "confidence": c.confidence,
            },
        }
        features.append(feat)
    geojson = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_selected_poi_gpx(selected: list[POICandidate], route_id: str) -> Path:
    """Write GPX with <wpt> entries for selected POIs. No <trk> — only waypoints.
    
    This is a debug/review artifact only. Use write_route_with_selected_poi_gpx()
    for RWGPS import.
    """
    out_dir = ensure_dir(route_id)
    path = out_dir / "selected_poi.gpx"

    root = ET.Element("gpx", {
        "version": "1.1",
        "creator": "QBot Route Logistics",
        "xmlns": "http://www.topografix.com/GPX/1/1",
    })

    for c in selected:
        wpt = ET.SubElement(root, "wpt", {"lat": str(c.lat), "lon": str(c.lon)})
        name = ET.SubElement(wpt, "name")
        name.text = c.candidate_id
        desc = ET.SubElement(wpt, "desc")
        desc.text = f"{c.name} ({c.category}/{c.subtype})"
        type_el = ET.SubElement(wpt, "type")
        type_el.text = c.category
        sym = ET.SubElement(wpt, "sym")
        sym.text = _rwgps_sym(c.category)

    tree = ET.ElementTree(root)
    tree.write(str(path), encoding="utf-8", xml_declaration=True)
    return path


def write_route_with_selected_poi_gpx(selected: list[POICandidate], route_id: str) -> Path:
    """Create enriched GPX: original track + selected POI <wpt>.
    
    Follows the G3 gravel pipeline format proven to work with RWGPS web UI import:
    - default GPX namespace
    - <wpt> before <trk>
    - <type>Alert</type> (maps to points_of_interest type_id=17 Information)
    - human-readable <name>
    - no <sym> element
    This file is ready for upload via RWGPS web UI Import → Upload File.
    """
    import xml.etree.ElementTree as _ET
    _ET.register_namespace("", "http://www.topografix.com/GPX/1/1")

    out_dir = ensure_dir(route_id)
    path = out_dir / "route_with_selected_poi.gpx"

    gpx_path = resolve_route_gpx(route_id)
    if not gpx_path:
        raise FileNotFoundError(f"Cannot resolve GPX for route {route_id}")

    tree = _ET.parse(str(gpx_path))
    root = tree.getroot()
    NS = "http://www.topografix.com/GPX/1/1"

    trk_elements = root.findall(f"{{{NS}}}trk")
    insert_before = trk_elements[0] if trk_elements else None

    for c in selected:
        label = c.category.upper()[:12]
        dist_s = f" {c.distance_from_track_m:.0f}m" if c.distance_from_track_m is not None else ""
        wpt = _ET.Element(f"{{{NS}}}wpt", {"lat": str(c.lat), "lon": str(c.lon)})
        name_el = _ET.SubElement(wpt, f"{{{NS}}}name")
        name_el.text = f"{label}{dist_s}"
        desc_el = _ET.SubElement(wpt, f"{{{NS}}}desc")
        desc_el.text = f"{c.name} — {c.category}/{c.subtype}. km {c.km_on_route:.1f}, {c.distance_from_track_m:.0f}m od trasy. Źródło: {c.source}."
        type_el = _ET.SubElement(wpt, f"{{{NS}}}type")
        type_el.text = "Alert"

        if insert_before is not None:
            root.insert(list(root).index(insert_before), wpt)
        else:
            root.append(wpt)

    tree.write(str(path), encoding="UTF-8", xml_declaration=True)
    return path


def _rwgps_sym(category: str) -> str:
    """Map QBot category to RWGPS symbol name."""
    mapping = {
        "shops": "Convenience Store",
        "water": "Water Source",
        "food": "Food",
        "lodging": "Accommodation",
        "attractions": "Museum",
        "bike_service": "Bike Shop",
        "pharmacy": "Hospital",
        "transport": "Bus Stop",
    }
    return mapping.get(category, "Custom POI")


def write_commit_summary_md(selected: list[POICandidate], rejected_ids: list[str], route_id: str) -> Path:
    out_dir = ensure_dir(route_id)
    path = out_dir / "poi_commit_summary.md"

    lines = [
        f"# QBot Route Logistics — Zatwierdzone POI",
        f"**Trasa:** {route_id}  ",
        f"**Data:** {date.today().isoformat()}  ",
        f"**Liczba POI:** {len(selected)}  ",
        f"**Odrzucone:** {len(rejected_ids)}  ",
        "",
        "## Zatwierdzone punkty",
        "",
        "| ID | Kategoria | Nazwa | Szerokość | Długość | Pewność |",
        "|---|---|---|---|---|---|",
    ]
    for c in selected:
        lines.append(f"| {c.candidate_id} | {CATEGORY_LABELS.get(c.category, c.category)} | {c.name} | {c.lat:.5f} | {c.lon:.5f} | {c.confidence} |")

    if rejected_ids:
        lines.append("")
        lines.append("## Odrzucone")
        lines.append("")
        for rid in rejected_ids:
            lines.append(f"- {rid}")

    lines.append("")
    lines.append("---")
    lines.append(f"Pliki: selected_poi.json, selected_poi.geojson, selected_poi.gpx")
    lines.append(f"GPX zawiera wyłącznie {len(selected)} zatwierdzone POI.")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Lodging requirements parsing
# ---------------------------------------------------------------------------

REQUIRED_LODGING_FIELDS = ["people", "budget", "radius_from_stage_end_m"]


def parse_lodging_requirements(args: dict | None) -> dict:
    """Validate lodging requirements. If missing, return NEEDS_REQUIREMENTS."""
    if not args:
        return {"status": "NEEDS_REQUIREMENTS", "missing": REQUIRED_LODGING_FIELDS}

    missing = []
    for field in REQUIRED_LODGING_FIELDS:
        if field not in args or args[field] is None:
            missing.append(field)

    if missing:
        return {"status": "NEEDS_REQUIREMENTS", "missing": missing}

    return {
        "status": "OK",
        "people": int(args["people"]),
        "budget": float(args["budget"]),
        "radius_from_stage_end_m": int(args.get("radius_from_stage_end_m", 5000)),
        "room_type": args.get("room_type", "twin"),
        "beds": int(args.get("beds", 1)),
        "bike_storage": bool(args.get("bike_storage", False)),
        "breakfast": bool(args.get("breakfast", False)),
        "rating_min": float(args.get("rating_min", 0)),
        "air_conditioning": bool(args.get("air_conditioning", False)),
    }


# ---------------------------------------------------------------------------
# Route ID helpers
# ---------------------------------------------------------------------------

def resolve_route_gpx(route_id: str) -> Path | None:
    """Find GPX file for a route ID from exports directory."""
    # Direct export
    candidates = [
        RWGPS_EXPORT_DIR / f"rwgps_{route_id}.gpx",
        ARTIFACTS_ROOT / "projects" / f"{route_id}.gpx",
        ARTIFACTS_ROOT / "combined" / f"combined_import_{route_id}.gpx",
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 0:
            return p

    # Glob for any GPX with route_id in name under exports
    for p in sorted(RWGPS_EXPORT_DIR.glob(f"*{route_id}*.gpx")):
        if p.exists() and p.stat().st_size > 0:
            return p

    return None


def safe_int(val: Any, default: int | None = None) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def safe_float(val: Any, default: float | None = None) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default
