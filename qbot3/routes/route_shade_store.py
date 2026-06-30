"""Writer for the canonical route land-cover cross-section (qbot_v2.route_shade_layer).

Samples ESA WorldCover (v200/2021) along the route axis (1:1 with
route_axis_segments, ~50 m). At each node it reads a 5-point cross-section
perpendicular to travel — class_left_20, class_left_10, class_center,
class_right_10, class_right_20 — plus the travel heading.

Stores ONLY raw WorldCover class codes (see qbot_v2.worldcover_classes) and
the heading. No derived shade / fractions / verdicts: consumers interpret it
(WBGT computes sun-vs-side shade, surface assessment takes its own view).

Tiles are pulled/cached on demand via qbot3.routes.worldcover_tiles, so a route
entering a new region downloads its tile once and reuses it after.

Dokumentacja: docs/PROJEKT_OTOCZENIE.md (skąd/gdzie/po co/dlaczego; §6 = co odrzucono).
"""
from __future__ import annotations

import argparse
import json
import math
import os
from typing import Any

import psycopg
import rasterio
from psycopg.rows import dict_row
from rasterio.transform import rowcol
from rasterio.windows import Window, from_bounds

from qbot3.routes import worldcover_tiles as wc

WC_CODES = {10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100}
SIDE_OFFSETS_M = (10.0, 20.0)        # próbki w poprzek na każdą stronę (piksel = 10 m)
SOURCE = "worldcover_v200_2021"


def _db_conn():
    conn = psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )
    conn.autocommit = True
    return conn


def _normalize_route_id(route_id: str | int) -> str:
    text = str(route_id).strip()
    if not text:
        raise ValueError("route_id required")
    return text


def _route_base_row(conn, *, route_base_id=None, route_id=None) -> dict[str, Any] | None:
    if route_base_id is not None:
        row = conn.execute(
            "SELECT route_base_id, route_id, route_artifact_id, route_version_key, status "
            "FROM qbot_v2.route_base WHERE route_base_id = %s LIMIT 1", (route_base_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT route_base_id, route_id, route_artifact_id, route_version_key, status "
            "FROM qbot_v2.route_base WHERE route_id = %s "
            "ORDER BY updated_at DESC, route_base_id DESC LIMIT 1", (route_id,)).fetchone()
    return dict(row) if row else None


def _axis_nodes(conn, route_base_id: int) -> list[dict[str, Any]]:
    """One node per axis segment: midpoint + heading endpoints from segment geometry."""
    rows = conn.execute(
        "SELECT segment_index, segment_geojson FROM qbot_v2.route_axis_segments "
        "WHERE route_base_id = %s ORDER BY segment_index", (route_base_id,)).fetchall()
    nodes = []
    for r in rows:
        gj = r["segment_geojson"]
        if isinstance(gj, str):
            gj = json.loads(gj)
        coords = gj.get("coordinates") if isinstance(gj, dict) else None
        if not coords:
            continue
        lon_s, lat_s = coords[0][0], coords[0][1]
        lon_e, lat_e = coords[-1][0], coords[-1][1]
        mid = coords[len(coords) // 2]
        nodes.append({"segment_index": int(r["segment_index"]),
                      "lat": mid[1], "lon": mid[0],
                      "lat_s": lat_s, "lon_s": lon_s, "lat_e": lat_e, "lon_e": lon_e})
    return nodes


def _heading_and_perp(lat, lon_s, lat_s, lon_e, lat_e):
    """(heading_deg, left_unit, right_unit, m-per-deg lat, m-per-deg lon) in E/N space."""
    mlat = 111320.0
    mlon = 111320.0 * math.cos(math.radians(lat))
    dE = (lon_e - lon_s) * mlon
    dN = (lat_e - lat_s) * mlat
    L = math.hypot(dE, dN) or 1.0
    uE, uN = dE / L, dN / L
    heading = math.degrees(math.atan2(uE, uN)) % 360.0
    left = (-uN, uE)    # 90° CCW od kierunku jazdy
    right = (uN, -uE)   # 90° CW
    return heading, left, right, mlat, mlon


def _offset_point(lat, lon, unit, dist_m, mlat, mlon):
    return lat + unit[1] * dist_m / mlat, lon + unit[0] * dist_m / mlon


class _TileReader:
    """Reads the route-bbox window of each needed tile once, samples in memory."""
    def __init__(self, bbox):
        min_lat, min_lon, max_lat, max_lon = bbox
        self.layers = []   # (arr, window_transform, (left,bottom,right,top), tile)
        self.tiles_used: list[str] = []
        self.missing_tiles: list[str] = []
        for tile in wc.tiles_for_bbox(min_lat, min_lon, max_lat, max_lon):
            try:
                path = wc.ensure_tile(tile)
            except FileNotFoundError:
                self.missing_tiles.append(tile); continue
            if not os.path.exists(path):
                self.missing_tiles.append(tile); continue
            with rasterio.open(path) as ds:
                win = from_bounds(min_lon, min_lat, max_lon, max_lat, ds.transform)
                win = win.intersection(Window(0, 0, ds.width, ds.height))
                arr = ds.read(1, window=win)
                wt = ds.window_transform(win)
                b = ds.bounds
            if arr.size:
                self.layers.append((arr, wt, (b.left, b.bottom, b.right, b.top), tile))
                self.tiles_used.append(tile)
                wc.touch_tile(tile)

    def sample(self, lat, lon):
        """Return (class_code, tile) or (None, None)."""
        for arr, wt, (left, bottom, right, top), tile in self.layers:
            if not (left <= lon < right and bottom <= lat < top):
                continue
            r, c = rowcol(wt, lon, lat, op=math.floor)
            if 0 <= r < arr.shape[0] and 0 <= c < arr.shape[1]:
                v = int(arr[r, c])
                if v in WC_CODES:
                    return v, tile
        return None, None


def _build_rows(route_base, nodes):
    if not nodes:
        raise LookupError(f"No route_axis_segments for route_id={route_base['route_id']}")
    lats = [n["lat"] for n in nodes]
    lons = [n["lon"] for n in nodes]
    pad = 0.003  # ~330 m zapasu na bufor
    reader = _TileReader((min(lats) - pad, min(lons) - pad, max(lats) + pad, max(lons) + pad))

    rbid = int(route_base["route_base_id"])
    vkey = str(route_base["route_version_key"])
    rows = []
    for n in nodes:
        heading, left, right, mlat, mlon = _heading_and_perp(
            n["lat"], n["lon_s"], n["lat_s"], n["lon_e"], n["lat_e"])
        cc, tile = reader.sample(n["lat"], n["lon"])
        la, lo = _offset_point(n["lat"], n["lon"], left, 10.0, mlat, mlon)
        l10, t = reader.sample(la, lo); tile = tile or t
        la, lo = _offset_point(n["lat"], n["lon"], left, 20.0, mlat, mlon)
        l20, t = reader.sample(la, lo); tile = tile or t
        la, lo = _offset_point(n["lat"], n["lon"], right, 10.0, mlat, mlon)
        r10, t = reader.sample(la, lo); tile = tile or t
        la, lo = _offset_point(n["lat"], n["lon"], right, 20.0, mlat, mlon)
        r20, t = reader.sample(la, lo); tile = tile or t

        vals = [cc, l10, l20, r10, r20]
        n_valid = sum(1 for v in vals if v is not None)
        if n_valid == 0:
            coverage = "missing"
        elif n_valid == 5:
            coverage = "ok"
        else:
            coverage = "partial"
        rows.append({
            "route_base_id": rbid, "route_version_key": vkey,
            "segment_index": n["segment_index"], "heading_deg": round(heading, 1),
            "class_center": cc, "class_left_10": l10, "class_left_20": l20,
            "class_right_10": r10, "class_right_20": r20,
            "n_valid": n_valid, "tile": tile, "coverage_status": coverage,
            "meta": {"lat": round(n["lat"], 6), "lon": round(n["lon"], 6),
                     "offsets_m": list(SIDE_OFFSETS_M)},
        })
    return rows, reader


def _upsert(conn, rows):
    n = 0
    for x in rows:
        conn.execute(
            """
            INSERT INTO qbot_v2.route_shade_layer (
                route_base_id, route_version_key, segment_index, heading_deg,
                class_center, class_left_10, class_left_20, class_right_10, class_right_20,
                n_valid, source, tile, coverage_status, meta_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (route_base_id, segment_index) DO UPDATE SET
                route_version_key = EXCLUDED.route_version_key,
                heading_deg = EXCLUDED.heading_deg,
                class_center = EXCLUDED.class_center,
                class_left_10 = EXCLUDED.class_left_10,
                class_left_20 = EXCLUDED.class_left_20,
                class_right_10 = EXCLUDED.class_right_10,
                class_right_20 = EXCLUDED.class_right_20,
                n_valid = EXCLUDED.n_valid, source = EXCLUDED.source, tile = EXCLUDED.tile,
                coverage_status = EXCLUDED.coverage_status,
                meta_json = EXCLUDED.meta_json, updated_at = now()
            """,
            (x["route_base_id"], x["route_version_key"], x["segment_index"], x["heading_deg"],
             x["class_center"], x["class_left_10"], x["class_left_20"], x["class_right_10"],
             x["class_right_20"], x["n_valid"], SOURCE, x["tile"], x["coverage_status"],
             json.dumps(x["meta"], ensure_ascii=False)))
        n += 1
    return n


def ensure_route_shade(*, route_id: str | int | None = None, route_base_id: int | None = None) -> dict[str, Any]:
    if route_id is None and route_base_id is None:
        raise ValueError("route_id or route_base_id required")
    route_id_text = _normalize_route_id(route_id) if route_id is not None else None
    conn = _db_conn()
    try:
        rb = _route_base_row(conn, route_base_id=route_base_id, route_id=route_id_text)
        if not rb:
            raise LookupError(f"No route_base found for {route_id_text or route_base_id!r}")
        nodes = _axis_nodes(conn, int(rb["route_base_id"]))
        rows, reader = _build_rows(rb, nodes)
        with conn.transaction():
            upserted = _upsert(conn, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    covered = sum(1 for r in rows if r["coverage_status"] in ("ok", "partial"))
    return {
        "status": "OK",
        "route_id": rb["route_id"],
        "route_base_id": int(rb["route_base_id"]),
        "route_version_key": rb["route_version_key"],
        "shade_layer_count": upserted,
        "coverage_pct": round(covered / len(rows) * 100.0, 1) if rows else 0.0,
        "tiles_used": reader.tiles_used,
        "tiles_missing": reader.missing_tiles,
    }


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write route land-cover cross-section from ESA WorldCover.")
    ap.add_argument("--route-id", dest="route_id")
    ap.add_argument("--route-base-id", dest="route_base_id", type=int)
    a = ap.parse_args(argv)
    res = ensure_route_shade(route_id=a.route_id, route_base_id=a.route_base_id)
    print(json.dumps(res, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
