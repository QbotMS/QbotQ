#!/usr/bin/env python3
"""Przeglad tabeli predkosci (SPEED_TABLE) na nowych jazdach -- TYLKO ODCZYT (2026-10-08).

Nic nie zmienia w kodzie ani w bazie. Wynik:
  /opt/qbot/artifacts/speed_table_review_<data>.json  (pelne dane)
  /opt/qbot/artifacts/speed_table_review_<data>.md    (podsumowanie)

Metoda (jak docs/ROUTE_TIME_ESTIMATE_V2.md, sek. 9):
- jazdy 1 Hz z qbot_v2.activity_record od --since (domyslnie 2026-07-01), dystans >= --min-km,
- tylko sekundy w ruchu (speed > 0.5 m/s, < 25 m/s),
- nachylenie: z wysokosci jazdy, okno 200 m po dystansie (+-100 m),
- nawierzchnia: po POZYCJI, najblizsza droga z lokalnej bazy OSM Polski (<= 25 m);
  tag surface -> klasa wg qbot_route_time_tools.surface_class; brak tagu -> wnioskowanie
  (tracktype / highway, oznaczone jako 'inferred'); poza PL / brak drogi -> pominiete,
- percentyle p50/p75/p90 per nawierzchnia x kubelek (czasowo: 1 probka = 1 s),
  podjazdy >= 6% scalone paved+unpaved (jak w oryginale),
- walidacja per jazda: przewidziany czas ruchu (stara vs nowa mediana) vs realny.
UWAGA: walidacja nowej tabeli jest in-sample (te same jazdy) -- optymistyczna.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

APP = Path("/opt/qbot/app")
sys.path.insert(0, str(APP))
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel.ftp_resolver import _db_connect  # noqa: E402
from qbot_route_time_tools import SPEED_TABLE, GRADE_LABELS, _grade_bin, surface_class  # noqa: E402
from tools.rwgps import osm_local  # noqa: E402

OUT = Path("/opt/qbot/artifacts")
MAX_MATCH_M = 25.0
CELL = 0.001  # ~110 m (lat)
PAVED_HW = {"motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link",
            "primary_link", "secondary_link", "tertiary_link", "residential", "living_street"}


def classify(tags: dict) -> tuple[str | None, str]:
    s = tags.get("surface")
    if s:
        c = surface_class(s)
        if c:
            return c, "tagged"
    tt = tags.get("tracktype")
    if tt == "grade1":
        return "paved", "inferred"
    if tt in ("grade2", "grade3", "grade4", "grade5"):
        return "unpaved", "inferred"
    hw = tags.get("highway")
    if hw in PAVED_HW:
        return "paved", "inferred"
    if hw in ("track", "path", "bridleway"):
        return "unpaved", "inferred"
    return None, "unknown"


def seg_dist_m(lat, lon, a, b, coslat):
    ax, ay = (a[1] - lon) * coslat, a[0] - lat
    bx, by = (b[1] - lon) * coslat, b[0] - lat
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
    px, py = ax + t * dx, ay + t * dy
    return math.sqrt(px * px + py * py) * 111320.0


class SurfaceIndex:
    """Siatka odcinkow drog dla prostokata (z bazy lokalnej OSM)."""

    def __init__(self, s, w, n, e):
        self.grid = defaultdict(list)
        data = osm_local.query_ways(s, w, n, e)
        for el in data["elements"]:
            cls, how = classify(el.get("tags") or {})
            g = [(p["lat"], p["lon"]) for p in el["geometry"]]
            for a, b in zip(g, g[1:]):
                for ci in range(int(math.floor(min(a[0], b[0]) / CELL)), int(math.floor(max(a[0], b[0]) / CELL)) + 1):
                    for cj in range(int(math.floor(min(a[1], b[1]) / CELL)), int(math.floor(max(a[1], b[1]) / CELL)) + 1):
                        self.grid[(ci, cj)].append((a, b, cls, how))

    def lookup(self, lat, lon):
        coslat = math.cos(math.radians(lat))
        ci, cj = int(math.floor(lat / CELL)), int(math.floor(lon / CELL))
        best, bd = None, MAX_MATCH_M
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for a, b, cls, how in self.grid.get((ci + di, cj + dj), ()):
                    d = seg_dist_m(lat, lon, a, b, coslat)
                    if d < bd:
                        bd, best = d, (cls, how)
        return best


def grade_series(dist, alt):
    """Nachylenie % w oknie 200 m (+-100 m) po dystansie, interpolacja liniowa."""
    def alt_at(d):
        k = bisect.bisect_left(dist, d)
        if k <= 0:
            return alt[0]
        if k >= len(dist):
            return alt[-1]
        d0, d1 = dist[k - 1], dist[k]
        if d1 == d0:
            return alt[k]
        return alt[k - 1] + (alt[k] - alt[k - 1]) * (d - d0) / (d1 - d0)
    out = []
    lo, hi = dist[0], dist[-1]
    for d in dist:
        a, b = max(lo, d - 100.0), min(hi, d + 100.0)
        out.append(None if b - a < 100.0 else (alt_at(b) - alt_at(a)) / (b - a) * 100.0)
    return out


def pct(vals, q):
    if not vals:
        return None
    v = sorted(vals)
    k = (len(v) - 1) * q
    f = math.floor(k)
    c = min(f + 1, len(v) - 1)
    return round(v[f] + (v[c] - v[f]) * (k - f), 1)


def load_rides(cur, since, min_km):
    cur.execute(
        """SELECT external_id, min(ts)::date, max(distance_m)/1000.0
           FROM qbot_v2.activity_record WHERE ts >= %s
           GROUP BY external_id HAVING max(distance_m) >= %s ORDER BY min(ts)""",
        (since, min_km * 1000.0),
    )
    return cur.fetchall()


def process_ride(cur, eid):
    cur.execute(
        """SELECT lat, lon, altitude_m, distance_m, speed_mps FROM qbot_v2.activity_record
           WHERE external_id=%s AND lat IS NOT NULL AND altitude_m IS NOT NULL
             AND distance_m IS NOT NULL AND speed_mps IS NOT NULL ORDER BY sec""",
        (eid,),
    )
    rows = cur.fetchall()
    if len(rows) < 600:
        return None
    # dystans musi byc niemalejacy dla bisect
    dist, alt, keep = [], [], []
    last = -1.0
    for r in rows:
        d = float(r[3])
        if d < last:
            continue
        last = d
        dist.append(d); alt.append(float(r[2])); keep.append(r)
    grades = grade_series(dist, alt)
    samples, stats = [], defaultdict(int)
    # indeks nawierzchni w kawalkach ~0.05 stopnia
    idx_cache = {}
    for r, g in zip(keep, grades):
        lat, lon, sp = float(r[0]), float(r[1]), float(r[4])
        if not (0.5 < sp < 25.0) or g is None:
            stats["skip_motion_or_grade"] += 1
            continue
        key = (int(lat / 0.05), int(lon / 0.05))
        if key not in idx_cache:
            s, w = key[0] * 0.05 - 0.002, key[1] * 0.05 - 0.002
            n, e = s + 0.054, w + 0.054
            idx_cache[key] = SurfaceIndex(s, w, n, e) if osm_local.covers_bbox(s, w, n, e) else None
        idx = idx_cache[key]
        if idx is None:
            stats["outside_pl"] += 1
            continue
        hit = idx.lookup(lat, lon)
        if hit is None or hit[0] is None:
            stats["no_surface"] += 1
            continue
        stats[hit[1]] += 1
        samples.append((hit[0], _grade_bin(g), sp * 3.6))
    return samples, dict(stats)


def build_table(all_samples):
    cells = defaultdict(list)
    for cls, b, v in all_samples:
        steep = b in ("6..8", ">8")
        cells[("merged" if steep else cls, b)].append(v)
    table = {}
    for cls in ("paved", "unpaved"):
        for b in GRADE_LABELS:
            src = cells.get(("merged", b)) if b in ("6..8", ">8") else cells.get((cls, b))
            src = src or []
            table.setdefault(cls, {})[b] = {"n": len(src), "p50": pct(src, .5), "p75": pct(src, .75), "p90": pct(src, .9)}
    return table


def predict_moving_s(samples, tab):
    t = 0.0
    for cls, b, v in samples:
        vt = tab[cls][b]
        if vt:
            t += (v / 3.6) / (vt / 3.6)   # metry tej sekundy / predkosc z tabeli
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-01")
    ap.add_argument("--min-km", type=float, default=40.0)
    args = ap.parse_args()
    if not osm_local.enabled():
        raise SystemExit("Brak lokalnej bazy OSM -- przerwano")
    conn = _db_connect()
    cur = conn.cursor()
    rides = load_rides(cur, args.since, args.min_km)
    print(f"jazd: {len(rides)}", flush=True)
    per_ride, all_samples, tot = [], [], defaultdict(int)
    for eid, d, km in rides:
        res = process_ride(cur, eid)
        if not res:
            continue
        samples, st = res
        for k, v in st.items():
            tot[k] += v
        all_samples.extend(samples)
        per_ride.append({"external_id": eid, "date": str(d), "km": round(float(km), 1),
                         "samples": samples, "stats": st})
        print(f"  {d} {eid} {float(km):.0f} km: {len(samples)} s dopasowanych {st}", flush=True)
    conn.close()

    new = build_table(all_samples)
    old = SPEED_TABLE["normalny"]
    new_p50 = {c: {b: new[c][b]["p50"] for b in GRADE_LABELS} for c in ("paved", "unpaved")}
    valid = []
    for r in per_ride:
        actual = len(r["samples"])
        if actual < 600:
            continue
        po, pn = predict_moving_s(r["samples"], old), predict_moving_s(r["samples"], new_p50)
        valid.append({"date": r["date"], "km": r["km"], "real_h": round(actual / 3600, 2),
                      "old_err_pct": round((po - actual) / actual * 100, 1),
                      "new_err_pct": round((pn - actual) / actual * 100, 1)})
    ts = date.today().isoformat().replace("-", "")
    js = {"since": args.since, "min_km": args.min_km, "rides": len(per_ride), "seconds": len(all_samples),
          "match_stats": dict(tot), "new": new, "old_normalny": old, "validation": valid}
    (OUT / f"speed_table_review_{ts}.json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")

    L = [f"# Przeglad tabeli predkosci -- {date.today()}", "",
         f"Jazdy od {args.since}, >= {args.min_km:.0f} km: **{len(per_ride)}**, dopasowanych sekund: **{len(all_samples)}**.",
         f"Dopasowanie: {dict(tot)}", "", "## Mediana (tryb normalny), km/h: stara -> nowa (n sekund)", "",
         "| nachylenie | asfalt stara | asfalt nowa | n | szuter stara | szuter nowa | n |", "|---|---|---|---|---|---|---|"]
    for b in GRADE_LABELS:
        L.append(f"| {b} | {old['paved'][b]} | {new['paved'][b]['p50']} | {new['paved'][b]['n']} | "
                 f"{old['unpaved'][b]} | {new['unpaved'][b]['p50']} | {new['unpaved'][b]['n']} |")
    if valid:
        mo = sum(v['old_err_pct'] for v in valid) / len(valid)
        mn = sum(v['new_err_pct'] for v in valid) / len(valid)
        L += ["", "## Walidacja czasu ruchu (blad przewidywania vs realny; nowa = in-sample)", "",
              f"Sredni blad: stara **{mo:+.1f}%**, nowa **{mn:+.1f}%** (minus = model za szybki).", "",
              "| data | km | realnie h | stara | nowa |", "|---|---|---|---|---|"]
        for v in valid:
            L.append(f"| {v['date']} | {v['km']} | {v['real_h']} | {v['old_err_pct']:+.1f}% | {v['new_err_pct']:+.1f}% |")
    (OUT / f"speed_table_review_{ts}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("GOTOWE", OUT / f"speed_table_review_{ts}.md", flush=True)


if __name__ == "__main__":
    main()
