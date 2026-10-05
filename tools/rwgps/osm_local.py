"""Lokalne zrodlo drog OSM (Polska) dla silnika nawierzchni - zamiast publicznego Overpass.

Baza: /opt/qbot/data/osm/roads.sqlite (scripts/osm_local_build.py, Geofabrik).
Obszar pokrycia: /opt/qbot/data/osm/poland.poly - kawalek trasy idzie do bazy
lokalnej TYLKO gdy wszystkie 4 rogi jego prostokata leza w Polsce; inaczej Overpass.
Wynik w formacie odpowiedzi Overpass (elements: way/id/tags/geometry[{lat,lon}]),
wiec reszta silnika nie widzi roznicy. Wylacznik: QBOT_SURFACE_LOCAL_OSM=0.
Wprowadzone 2026-10-05 po blokadzie IP serwera przez overpass-api.de.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

DIR = Path(os.getenv("QBOT_OSM_DIR", "/opt/qbot/data/osm"))
DB = DIR / "roads.sqlite"
POLY = DIR / "poland.poly"
SOURCE_NAME = "local_osm_geofabrik_pl"

_lock = threading.Lock()
_rings: list[list[tuple[float, float]]] | None = None
_rings_mtime: float | None = None


def enabled() -> bool:
    return os.getenv("QBOT_SURFACE_LOCAL_OSM", "1").strip() not in {"0", "false", "no"} and DB.exists() and POLY.exists()


def _load_rings() -> list[list[tuple[float, float]]]:
    """Plik .poly (Osmosis): sekcje pierscieni 'lon lat'; sekcje z '!' to dziury - pomijamy."""
    global _rings, _rings_mtime
    mtime = POLY.stat().st_mtime
    with _lock:
        if _rings is not None and _rings_mtime == mtime:
            return _rings
        rings: list[list[tuple[float, float]]] = []
        cur: list[tuple[float, float]] | None = None
        hole = False
        lines = POLY.read_text(encoding="utf-8").splitlines()[1:]
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if line == "END":
                if cur is not None:
                    if not hole and len(cur) >= 3:
                        rings.append(cur)
                    cur = None
                continue
            if cur is None:
                hole = line.startswith("!")
                cur = []
                continue
            parts = line.split()
            if len(parts) >= 2:
                cur.append((float(parts[1]), float(parts[0])))  # (lat, lon)
        _rings, _rings_mtime = rings, mtime
        return rings


def _inside(lat: float, lon: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def covers_bbox(south: float, west: float, north: float, east: float) -> bool:
    if not enabled():
        return False
    rings = _load_rings()
    for lat, lon in ((south, west), (south, east), (north, west), (north, east)):
        if not any(_inside(lat, lon, r) for r in rings):
            return False
    return True


def query_ways(south: float, west: float, north: float, east: float) -> dict[str, Any]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    try:
        rows = con.execute(
            """
            SELECT w.id, w.tags_json, w.geom_json
            FROM ways_rtree r JOIN ways w ON w.id = r.id
            WHERE r.max_lat >= ? AND r.min_lat <= ? AND r.max_lon >= ? AND r.min_lon <= ?
            """,
            (south, north, west, east),
        ).fetchall()
    finally:
        con.close()
    elements = []
    for wid, tags_json, geom_json in rows:
        geom = json.loads(geom_json)
        elements.append({
            "type": "way",
            "id": int(wid),
            "tags": json.loads(tags_json),
            "geometry": [{"lat": p[0], "lon": p[1]} for p in geom],
        })
    return {"elements": elements, "generator": SOURCE_NAME}


def meta() -> dict[str, str]:
    if not DB.exists():
        return {}
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    try:
        return {k: v for k, v in con.execute("SELECT k, v FROM meta").fetchall()}
    finally:
        con.close()
