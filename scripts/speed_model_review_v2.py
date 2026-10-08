#!/usr/bin/env python3
"""Przeglad modelu czasu v2 -- TYLKO ODCZYT (2026-10-08). Nic nie zmienia w kodzie ani bazie.

Ustalenia Michala (08.10): Grand Canyon = Monster; jazdy bikepackingowe = 05-11.06 i 01-03.08.2026.

Czesc A -- predkosc ruchu (netto):
- baza: jazdy BEZ bagazu od --since (>= 40 km, Polska -- lokalna baza OSM),
- wartosc kratki = SREDNIA predkosc sekund (= dystans/czas -> czas przewidywany bez obciazenia),
  sport/wyscig nadal p75/p90; kratka < 300 s -> stara wartosc,
- walidacja leave-one-out (tabela liczona bez danej jazdy) -> bez oszukiwania in-sample,
- blad wg roweru (Grizl / Grail / Monster) -> czy potrzebny wspolczynnik roweru,
- bikepacking: blad tabeli bazowej na dniach z bagazem -> wspolczynnik trybu "wyprawa".
Czesc B -- postoje (brutto):
- mikro (<2 min) min/km, krotkie (2-20 min) min na godzine ruchu wg dlugosci jazdy,
  osobno bikepacking; porownanie bledu czasu calkowitego (bez dlugich) stary vs nowy wzor.
Wynik: /opt/qbot/artifacts/speed_model_review_v2_<data>.md
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, "/opt/qbot/app")
sys.path.insert(0, "/opt/qbot/app/scripts")
os.environ.setdefault("QBOT3_ENABLED", "1")

import speed_table_review as STR  # noqa: E402
from fitmodel.ftp_resolver import _db_connect  # noqa: E402
from qbot3.rides.activity_devices import bike_for_ride  # noqa: E402
from qbot_route_time_tools import SPEED_TABLE, GRADE_LABELS  # noqa: E402

BIKEPACK = [("2026-06-05", "2026-06-11"), ("2026-08-01", "2026-08-03")]
BIKE_ALIAS = {"Canyon Grand Canyon": "Monster (Grand Canyon)"}
SINCE_BASE = "2026-07-01"
SINCE_ALL = "2026-05-01"
MIN_CELL_S = 300
OLD = SPEED_TABLE["normalny"]


def is_bp(d: str) -> bool:
    return any(a <= d <= b for a, b in BIKEPACK)


def key(cls, b):
    return ("merged", b) if b in ("6..8", ">8") else (cls, b)


def sums_of(samples):
    s = defaultdict(lambda: [0.0, 0])
    for cls, b, v in samples:
        k = key(cls, b); s[k][0] += v; s[k][1] += 1
    return s


def table_from(tot):
    t = {}
    for cls in ("paved", "unpaved"):
        for b in GRADE_LABELS:
            sv, n = tot.get(key(cls, b), (0.0, 0))
            t.setdefault(cls, {})[b] = round(sv / n, 1) if n >= MIN_CELL_S else OLD[cls][b]
    return t


def pred_s(samples, tab):
    return sum(v / tab[c][b] for c, b, v in samples)


def stops(cur, eid):
    cur.execute("SELECT ts, speed_mps FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY ts", (eid,))
    mov = [r[0] for r in cur.fetchall() if r[1] is not None and r[1] > 0.5]
    if len(mov) < 600:
        return None
    st = defaultdict(float)
    for a, b in zip(mov, mov[1:]):
        g = (b - a).total_seconds() - 1
        if g >= 5:
            st["mikro" if g < 120 else ("krotkie" if g < 1200 else "dlugie")] += g / 60
    return len(mov) / 3600, st


def main():
    conn = _db_connect(); cur = conn.cursor()
    cur.execute("""SELECT external_id, min(ts)::date::text, max(distance_m)/1000.0 FROM qbot_v2.activity_record
                   WHERE ts >= %s GROUP BY external_id HAVING max(distance_m) >= 20000 ORDER BY 2""", (SINCE_ALL,))
    rides = cur.fetchall()
    base, bp, stop_rows = [], [], []
    for eid, d, km in rides:
        km = float(km)
        try:
            bk = bike_for_ride(conn, eid).get("bike") or "?"
        except Exception:
            bk = "?"
        bk = BIKE_ALIAS.get(bk, bk)
        s = stops(cur, eid)
        if s:
            stop_rows.append(dict(d=d, km=km, bike=bk, bp=is_bp(d), mov_h=s[0],
                                  mikro=s[1].get("mikro", 0.0), krotkie=s[1].get("krotkie", 0.0),
                                  dlugie=s[1].get("dlugie", 0.0)))
        if km < 40 or not (is_bp(d) or d >= SINCE_BASE):
            continue
        res = STR.process_ride(cur, eid)
        if not res or len(res[0]) < 600:
            continue
        r = dict(d=d, km=round(km, 1), bike=bk, samples=res[0], sums=sums_of(res[0]))
        (bp if is_bp(d) else base).append(r)
        print(f"{d} {bk} {km:.0f} km bp={is_bp(d)} s={len(res[0])}", flush=True)
    conn.close()

    tot = defaultdict(lambda: [0.0, 0])
    for r in base:
        for k, (sv, n) in r["sums"].items():
            tot[k][0] += sv; tot[k][1] += n
    full = table_from(tot)

    val = []
    for r in base:
        loo = {k: (tot[k][0] - r["sums"].get(k, (0, 0))[0], tot[k][1] - r["sums"].get(k, (0, 0))[1]) for k in tot}
        t_loo = table_from(loo)
        n = len(r["samples"])
        val.append(dict(r, old=(pred_s(r["samples"], OLD) - n) / n * 100, new=(pred_s(r["samples"], t_loo) - n) / n * 100))

    L = [f"# Model czasu -- przeglad v2 ({date.today()})", "",
         f"Baza: jazdy bez bagazu od {SINCE_BASE}, >= 40 km, w PL: **{len(base)}** "
         f"({sum(len(r['samples']) for r in base)/3600:.0f} h ruchu). Kratka < {MIN_CELL_S} s -> stara wartosc.", "",
         "## A1. Predkosc w ruchu, tryb normalny (srednia, km/h): stara -> nowa", "",
         "| nachylenie | asfalt stara | asfalt nowa | szuter stara | szuter nowa | n s (asf/szut) |", "|---|---|---|---|---|---|"]
    for b in GRADE_LABELS:
        na, nu = tot.get(key("paved", b), (0, 0))[1], tot.get(key("unpaved", b), (0, 0))[1]
        L.append(f"| {b} | {OLD['paved'][b]} | {full['paved'][b]} | {OLD['unpaved'][b]} | {full['unpaved'][b]} | {na}/{nu} |")

    def avg(xs):
        return sum(xs) / len(xs) if xs else float("nan")
    L += ["", "## A2. Walidacja leave-one-out (blad czasu ruchu; minus = model za szybki)", "",
          f"Sredni blad: stara **{avg([v['old'] for v in val]):+.1f}%**, nowa **{avg([v['new'] for v in val]):+.1f}%**; "
          f"sredni |blad| stara {avg([abs(v['old']) for v in val]):.1f}%, nowa {avg([abs(v['new']) for v in val]):.1f}%.", "",
          "| data | rower | km | stara | nowa |", "|---|---|---|---|---|"]
    for v in val:
        L.append(f"| {v['d']} | {v['bike']} | {v['km']} | {v['old']:+.1f}% | {v['new']:+.1f}% |")
    L += ["", "## A3. Wg roweru (nowa tabela, LOO)", "", "| rower | jazd | sredni blad | wspolczynnik predkosci |", "|---|---|---|---|"]
    byb = defaultdict(list)
    for v in val:
        byb[v["bike"]].append(v["new"])
    for bk, xs in byb.items():
        e = avg(xs)
        L.append(f"| {bk} | {len(xs)} | {e:+.1f}% | x{(1 + e/100):.2f} (wiarygodny od 5 jazd) |")
    if bp:
        a = sum(len(r["samples"]) for r in bp)
        p = sum(pred_s(r["samples"], full) for r in bp)
        L += ["", "## A4. Bikepacking (z bagazem) vs tabela bazowa", "",
              f"Dni: {len(bp)}, ruch {a/3600:.1f} h. Tabela bazowa przewiduje {p/3600:.1f} h -> "
              f"**wspolczynnik predkosci wyprawy x{p/a:.2f}** (realnie wolniej o {(1-p/a)*100:.0f}%)."]

    # ---- B. postoje
    def grp(r):
        if r["bp"]:
            return "bikepacking"
        h = r["mov_h"]
        return "< 1,5 h" if h < 1.5 else ("1,5-3 h" if h < 3 else ("3-5 h" if h < 5 else "> 5 h"))
    G = defaultdict(list)
    for r in stop_rows:
        G[grp(r)].append(r)
    L += ["", f"## B1. Postoje wg dlugosci jazdy (jazdy >= 20 km od {SINCE_ALL})", "",
          "| grupa | jazd | mikro min/km (model 0,22) | krotkie min/h ruchu | krotkie realnie min/jazde | model stary min/jazde |",
          "|---|---|---|---|---|---|"]
    for g in ("< 1,5 h", "1,5-3 h", "3-5 h", "> 5 h", "bikepacking"):
        rs = G.get(g, [])
        if not rs:
            continue
        km = sum(r["km"] for r in rs); mh = sum(r["mov_h"] for r in rs)
        mik = sum(r["mikro"] for r in rs); kr = sum(r["krotkie"] for r in rs)
        old_kr = sum(round(r["km"] / 9) * 4.5 for r in rs)
        L.append(f"| {g} | {len(rs)} | {mik/km:.2f} | {kr/mh:.1f} | {kr/len(rs):.0f} | {old_kr/len(rs):.0f} |")

    # propozycja: krotkie = rate * max(0, h - H0); osobno bikepacking; mikro = stala/km
    H0 = 1.0
    norm = [r for r in stop_rows if not r["bp"]]
    bpr = [r for r in stop_rows if r["bp"]]
    def fit(rs, h0):
        den = sum(max(0.0, r["mov_h"] - h0) for r in rs)
        return (sum(r["krotkie"] for r in rs) / den) if den else 0.0, (sum(r["mikro"] for r in rs) / sum(r["km"] for r in rs))
    rn, mn = fit(norm, H0)
    rb, mb = fit(bpr, 0.0)
    def err(rs, f):
        e = []
        for r in rs:
            real = r["mov_h"] * 60 + r["mikro"] + r["krotkie"]
            e.append((r["mov_h"] * 60 + f(r) - real) / real * 100)
        return avg(e), avg([abs(x) for x in e])
    old_f = lambda r: 0.22 * r["km"] + round(r["km"] / 9) * 4.5
    new_n = lambda r: mn * r["km"] + rn * max(0.0, r["mov_h"] - H0)
    new_b = lambda r: mb * r["km"] + rb * r["mov_h"]
    L += ["", "## B2. Propozycja wzoru postojow i blad czasu calkowitego (bez dlugich postojow)", "",
          f"- zwykle jazdy: mikro **{mn:.2f} min/km**, krotkie **{rn:.1f} min na kazda godzine ruchu po pierwszej**",
          f"- bikepacking: mikro **{mb:.2f} min/km**, krotkie **{rb:.1f} min na godzine ruchu**", "",
          "| grupa | blad stary (sredni / |sredni|) | blad nowy |", "|---|---|---|"]
    for name, rs, fn in (("zwykle", norm, new_n), ("bikepacking", bpr, new_b)):
        if rs:
            o, oa = err(rs, old_f); n_, na_ = err(rs, fn)
            L.append(f"| {name} ({len(rs)}) | {o:+.1f}% / {oa:.1f}% | {n_:+.1f}% / {na_:.1f}% |")
    L += ["", "Uwaga: B2 dopasowane in-sample (2 parametry na grupe, duzo jazd -> ryzyko male)."]
    out = Path(f"/opt/qbot/artifacts/speed_model_review_v2_{date.today().isoformat().replace('-', '')}.md")
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("GOTOWE", out, flush=True)


if __name__ == "__main__":
    main()
