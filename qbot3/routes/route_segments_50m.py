#!/usr/bin/env python3
"""Kanoniczny czytnik segmentow trasy w siatce 50 m — JEDNO zrodlo prawdy.

Cel: zlikwidowac rozjazd zrodel nawierzchni/geometrii. Wszystkie narzedzia
(model czasu, meteo, raport, Albert) maja docelowo czytac segmenty STAD, a nie
z route_frames(80m) / route_surface_profiles / route_surface_segments.

Sklada per segment osi 50 m (qbot_v2.route_axis_segments):
  - len_m       : distance_m (osi)
  - km_from/to  : km_from/km_to (osi)
  - mid_lat/lon : srodek geometrii segmentu (segment_geojson LineString)
  - grade_pct   : z qbot_v2.route_elevation_samples (DEM 50 m), wygladzone
                  oknem 200 m przez route_elevation_engine (KANON — nie
                  avg_grade_pct z osi, ktory jest jawnie niekanoniczny)
  - surface     : rzut qbot_v2.route_surface_layer po km (km_from/km_to z
                  surface_meta_json) — warstwa jest zdrowa i ma 100% pokrycia
  - surface_class: paved/unpaved/None wg reguly modelu czasu

Zasada: TYLKO odczyt. Nic nie liczy od nowa i nic nie zapisuje.
Dokumentacja kierunku: docs/CONTEXT.md (architektura 50 m).
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from qbot3.routes.route_elevation_engine import (ElevationSample, _frame_grades,
                                                 smooth_elevation, summarize)

GRADE_WINDOW_M = 200.0  # spojnie z kalibracja sumy przewyzszen

# nawierzchnia binarna — kanon EN (warstwa uzywa etykiet EN); PL zostawione
# na wypadek starych danych, ale warstwa 50m ich nie produkuje.
_PAVED = {"asphalt", "paving_stones", "concrete", "cobblestone", "concrete:plates"}
_UNPAVED = {"gravel", "ground", "dirt", "compacted", "grass", "fine_gravel",
            "sand", "wood", "mixed"}


def _db_conn():
    try:
        import psycopg2 as pg  # type: ignore
    except ModuleNotFoundError:
        import psycopg as pg  # type: ignore
    return pg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "qbot"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        password=os.getenv("PGPASSWORD"),
    )


def surface_class(raw: Optional[str]) -> Optional[str]:
    """surowa nazwa -> 'paved'/'unpaved'/None (None = nieznana)."""
    if not raw:
        return None
    r = str(raw).strip().lower()
    if r in _PAVED:
        return "paved"
    if r in _UNPAVED:
        return "unpaved"
    return None


# ---------------------------------------------------------- CZESC CZYSTA (testowalna offline)
def build_surface_ranges(surface_rows: list[dict]) -> list[tuple[float, float, str]]:
    """Z wierszy warstwy (surface + km_from/km_to w surface_meta_json) buduje
    posortowana liste (km_from, km_to, surface) do rzutowania po km."""
    ranges: list[tuple[float, float, str]] = []
    for row in surface_rows:
        meta = row.get("surface_meta_json") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        kf = meta.get("km_from")
        kt = meta.get("km_to")
        if kf is None or kt is None:
            continue
        ranges.append((float(kf), float(kt), str(row.get("surface") or "unknown")))
    ranges.sort(key=lambda x: x[0])
    return ranges


def project_surface(km_mid: float, ranges: list[tuple[float, float, str]]) -> str:
    """Zwraca nawierzchnie dla srodka segmentu wg zakresow km warstwy."""
    if not ranges:
        return "unknown"
    for kf, kt, surf in ranges:
        if kf <= km_mid < kt:
            return surf
    # poza ostatnim zakresem (zaokraglenia na koncu trasy) -> ostatni zakres
    if km_mid >= ranges[-1][1]:
        return ranges[-1][2]
    if km_mid < ranges[0][0]:
        return ranges[0][2]
    return "unknown"


def _midpoint(segment_geojson: Any) -> tuple[Optional[float], Optional[float]]:
    """Srodek LineString (srodkowy wezel geometrii)."""
    geo = segment_geojson
    if isinstance(geo, str):
        try:
            geo = json.loads(geo)
        except Exception:
            return None, None
    coords = (geo or {}).get("coordinates") or []
    if not coords:
        return None, None
    c = coords[len(coords) // 2]
    # GeoJSON = [lon, lat, (ele)]
    return (float(c[1]), float(c[0]))


# ---------------------------------------------------------- CZYTNIK Z BAZY
def load_canonical_segments_50m(*, route_id: Optional[str] = None,
                                route_base_id: Optional[int] = None) -> dict:
    """Zwraca kanoniczne segmenty 50 m dla trasy. status: OK / NO_BASE / NO_AXIS."""
    conn = _db_conn()
    cur = conn.cursor()

    if route_base_id is None:
        if route_id is None:
            conn.close()
            raise ValueError("route_id lub route_base_id wymagane")
        cur.execute("""SELECT route_base_id, route_version_key FROM qbot_v2.route_base
                       WHERE route_id=%s ORDER BY updated_at DESC, route_base_id DESC LIMIT 1""",
                    (str(route_id),))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"status": "NO_BASE", "segments": []}
        route_base_id, route_version_key = int(row[0]), row[1]
    else:
        cur.execute("SELECT route_version_key FROM qbot_v2.route_base WHERE route_base_id=%s",
                    (route_base_id,))
        row = cur.fetchone()
        route_version_key = row[0] if row else None

    # 1) os 50 m
    cur.execute("""SELECT segment_index, km_from, km_to, distance_m, segment_geojson
                   FROM qbot_v2.route_axis_segments WHERE route_base_id=%s
                   ORDER BY segment_index""", (route_base_id,))
    axis = cur.fetchall()
    if not axis:
        conn.close()
        return {"status": "NO_AXIS", "route_base_id": route_base_id, "segments": []}

    # 2) wysokosci DEM 50 m -> nachylenie kanoniczne (okno 200 m)
    cur.execute("""SELECT sample_index, distance_m, lat, lon, elevation_m
                   FROM qbot_v2.route_elevation_samples WHERE route_base_id=%s
                   ORDER BY sample_index""", (route_base_id,))
    esrows = cur.fetchall()
    grades: list[float | None] = []
    _sm: list = []
    _esum: dict = {}
    if esrows:
        samples = [ElevationSample(int(r[0]), float(r[1] or 0.0), float(r[2] or 0.0),
                                   float(r[3] or 0.0),
                                   (float(r[4]) if r[4] is not None else None),
                                   "route_elevation_samples") for r in esrows]
        dists = [s.distance_m for s in samples]
        _sm = smooth_elevation(samples, GRADE_WINDOW_M)
        grades = _frame_grades(_sm, dists)
        _esum = summarize(samples, GRADE_WINDOW_M)

    # 3) nawierzchnia z warstwy -> zakresy km
    cur.execute("""SELECT surface, surface_meta_json FROM qbot_v2.route_surface_layer
                   WHERE route_base_id=%s ORDER BY segment_index""", (route_base_id,))
    surf_rows = [{"surface": r[0], "surface_meta_json": r[1]} for r in cur.fetchall()]
    ranges = build_surface_ranges(surf_rows)
    conn.close()

    segments: list[dict] = []
    unknown_m = 0.0
    total_m = 0.0
    for i, (seg_idx, km_from, km_to, dist_m, geo) in enumerate(axis):
        km_from = float(km_from); km_to = float(km_to)
        ln = float(dist_m or 0.0)
        total_m += ln
        km_mid = (km_from + km_to) / 2.0
        surf = project_surface(km_mid, ranges)
        sc = surface_class(surf)
        if sc is None:
            unknown_m += ln
        g = grades[i] if i < len(grades) and grades[i] is not None else 0.0
        lat, lon = _midpoint(geo)
        _e0 = _sm[i] if i < len(_sm) else None
        _e1 = _sm[i + 1] if (i + 1) < len(_sm) else _e0
        _gain = (_e1 - _e0) if (_e0 is not None and _e1 is not None) else 0.0
        segments.append({
            "segment_index": int(seg_idx),
            "km_from": round(km_from, 3),
            "km_to": round(km_to, 3),
            "len_m": ln,
            "mid_lat": lat,
            "mid_lon": lon,
            "grade_pct": round(float(g or 0.0), 2),
            "elevation_m": (round(_e0, 1) if _e0 is not None else None),
            "elev_gain_m": round(float(_gain), 2),
            "surface": surf,
            "surface_class": sc,
        })

    return {
        "status": "OK",
        "route_base_id": route_base_id,
        "route_version_key": route_version_key,
        "grid_m": 50,
        "segments": segments,
        "summary": {
            "n_segments": len(segments),
            "distance_km": round(total_m / 1000.0, 2),
            "unknown_surface_pct": round(100.0 * unknown_m / total_m, 1) if total_m else 0.0,
            "ascent_m": _esum.get("ascent_smoothed_m", 0.0),
            "descent_m": _esum.get("descent_smoothed_m", 0.0),
            "max_grade_pct": _esum.get("max_grade_pct", 0.0),
        },
    }


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else "55798129"
    out = load_canonical_segments_50m(route_id=rid)
    s = out.get("summary", {})
    print("status:", out["status"], "route_base_id:", out.get("route_base_id"))
    print("segmentow:", s.get("n_segments"), "dystans_km:", s.get("distance_km"),
          "nieznana_%:", s.get("unknown_surface_pct"))
    import collections
    dist = collections.Counter(x["surface"] for x in out["segments"])
    cls = collections.Counter(x["surface_class"] or "None" for x in out["segments"])
    print("nawierzchnia:", dict(dist.most_common()))
    print("klasy:", dict(cls))
    print("przyklad 3 srodkowe segmenty:")
    for x in out["segments"][700:703]:
        print("  ", x)
