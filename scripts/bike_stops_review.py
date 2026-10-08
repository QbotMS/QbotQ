#!/usr/bin/env python3
"""Analiza 2026-10-08 (tylko odczyt): rower per jazda + postoje (predkosc brutto) vs model.

Wynik: /opt/qbot/artifacts/bike_stops_review_20261008.md
Postoj = przerwa miedzy sekundami w ruchu (speed > 0.5 m/s), liczona z ts (lapie tez autopauze).
Klasy jak w modelu: mikro < 2 min, krotkie 2-20 min, dlugie >= 20 min.
Model (qbot_route_time_tools): mikro 0.22 min/km, krotkie km/9 x 4.5 min, dlugie = wklad uzytkownika.
"""
import os, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from fitmodel.ftp_resolver import _db_connect
from qbot3.rides.activity_devices import bike_for_ride

conn = _db_connect(); cur = conn.cursor()
cur.execute("""SELECT external_id, min(ts)::date, max(distance_m)/1000.0 FROM qbot_v2.activity_record
               WHERE ts >= '2026-03-01' GROUP BY external_id HAVING max(distance_m) >= 20000 ORDER BY min(ts)""")
rides = cur.fetchall()
rows = []
for eid, d, km in rides:
    try:
        b = bike_for_ride(conn, eid)
        bike = (b.get("bike") or {}).get("name") if isinstance(b.get("bike"), dict) else b.get("bike")
    except Exception as e:
        bike = f"? ({type(e).__name__})"
    cur.execute("SELECT ts, speed_mps FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY ts", (eid,))
    pts = cur.fetchall()
    mov = [p[0] for p in pts if p[1] is not None and p[1] > 0.5]
    if len(mov) < 600:
        continue
    moving_s = len(mov)
    elapsed_s = (pts[-1][0] - pts[0][0]).total_seconds()
    st = defaultdict(float); cnt = defaultdict(int)
    for a, b2 in zip(mov, mov[1:]):
        gap = (b2 - a).total_seconds() - 1
        if gap < 5:
            continue
        k = "mikro" if gap < 120 else ("krotkie" if gap < 1200 else "dlugie")
        st[k] += gap / 60; cnt[k] += 1
    km = float(km)
    rows.append(dict(d=str(d), bike=bike or "?", km=round(km, 1), mov_h=moving_s / 3600, el_h=elapsed_s / 3600,
                     v_net=km / (moving_s / 3600), v_brut=km / (elapsed_s / 3600),
                     mikro=st["mikro"], krot=st["krotkie"], dl=st["dlugie"], n_dl=cnt["dlugie"],
                     m_mikro=0.22 * km, m_krot=km / 9 * 4.5))
conn.close()

L = ["# Rower i postoje -- jazdy >= 20 km od 2026-03-01", "",
     "| data | rower | km | netto km/h | brutto km/h | mikro min (model) | krotkie min (model) | dlugie min (n) |",
     "|---|---|---|---|---|---|---|---|"]
for r in rows:
    L.append(f"| {r['d']} | {r['bike']} | {r['km']} | {r['v_net']:.1f} | {r['v_brut']:.1f} | "
             f"{r['mikro']:.0f} ({r['m_mikro']:.0f}) | {r['krot']:.0f} ({r['m_krot']:.0f}) | {r['dl']:.0f} ({r['n_dl']}) |")
L += ["", "## Wg roweru (suma)", "", "| rower | jazd | km | netto km/h | mikro min/km (model 0.22) | krotkie min/km (model 0.50) |", "|---|---|---|---|---|---|"]
agg = defaultdict(lambda: defaultdict(float))
for r in rows:
    a = agg[r["bike"]]; a["n"] += 1; a["km"] += r["km"]; a["mov"] += r["mov_h"]; a["mikro"] += r["mikro"]; a["krot"] += r["krot"]
for bk, a in sorted(agg.items(), key=lambda x: -x[1]["km"]):
    L.append(f"| {bk} | {int(a['n'])} | {a['km']:.0f} | {a['km']/a['mov']:.1f} | {a['mikro']/a['km']:.2f} | {a['krot']/a['km']:.2f} |")
out = Path("/opt/qbot/artifacts/bike_stops_review_20261008.md")
out.write_text("\n".join(L) + "\n", encoding="utf-8")
print("GOTOWE", out, len(rows))
