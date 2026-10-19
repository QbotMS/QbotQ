# -*- coding: utf-8 -*-
"""Profile jazd -- krok 1 (2026-10-19): cechy historycznych jazd + wstepna klasyfikacja -> data/ride_features.json.
Bez zmian w modelu czasu. Uruchom: .venv/bin/python3 scripts/ride_profile_features.py
Cechy: geolokalizacja (dom/praca/wyjazd, A->B, udzial centrum Warszawy), dlugosc WZGLEDEM SEZONU
(jazdy +-30 dni roku, wszystkie lata), dzien/godzina (czas PL), temperatura, postoje z przerw w zapisie 1 Hz.
Klasy: bikepacking > commuting > dluga > trening tygodniowy (pn-pt) / krotka weekendowa (sb-nd); flaga wyjazd."""
import json, math, sys, time, statistics
from zoneinfo import ZoneInfo
sys.path.insert(0, "/opt/qbot/app")
from qbot_brokul_meals import _conn

TZ = ZoneInfo("Europe/Warsaw")
HOME = (52.345, 21.11)          # najczestszy start/meta (383 z 658 koncow jazd)
WORK = [(52.221, 21.023), (52.256, 20.982)]   # konce dojazdow z domu w dni robocze
OUT = "/opt/qbot/app/data/ride_features.json"
SPEED = json.load(open("/opt/qbot/app/config/speed_model.json"))
BP = [tuple(x) for x in SPEED.get("bikepacking_dates", [])]


def dist_km(a, b):
    la = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(la))


Q = """
WITH p AS (SELECT sec, lat, lon, speed_mps, temperature_c FROM qbot_v2.activity_record WHERE external_id=%s),
g AS (SELECT sec - lag(sec) OVER (ORDER BY sec) gap FROM p)
SELECT (SELECT lat FROM p WHERE lat IS NOT NULL ORDER BY sec LIMIT 1) la0, (SELECT lon FROM p WHERE lat IS NOT NULL ORDER BY sec LIMIT 1) lo0,
       (SELECT lat FROM p WHERE lat IS NOT NULL ORDER BY sec DESC LIMIT 1) la1, (SELECT lon FROM p WHERE lat IS NOT NULL ORDER BY sec DESC LIMIT 1) lo1,
       (SELECT max(sec) - min(sec) FROM p) el_s, (SELECT avg(temperature_c) FROM p) temp,
       (SELECT count(*) FROM g WHERE gap BETWEEN 5 AND 180) st_short, (SELECT COALESCE(sum(gap),0) FROM g WHERE gap BETWEEN 5 AND 180) st_short_s,
       (SELECT count(*) FROM g WHERE gap > 180) st_long, (SELECT count(*) FROM p WHERE COALESCE(speed_mps,0) < 1) still_s,
       (SELECT count(*) FILTER (WHERE lat BETWEEN 52.17 AND 52.30 AND lon BETWEEN 20.90 AND 21.12)::float / NULLIF(count(lat),0) FROM p) core
"""

t0 = time.time()
with _conn() as c:
    rides = c.execute("SELECT external_id, date, started_at, distance_m, duration_s FROM qbot_v2.training_sessions "
                      "WHERE sport_type='cycling' AND date>='2025-04-01' AND distance_m>3000 ORDER BY date").fetchall()
    out = []
    for r in rides:
        a = c.execute(Q, (r["external_id"],)).fetchone()
        km = (r["distance_m"] or 0) / 1000
        mov = (r["duration_s"] or 0) / 3600
        f = {"id": r["external_id"], "date": str(r["date"]), "dow": r["date"].isoweekday(),
             "hour": r["started_at"].astimezone(TZ).hour if r["started_at"] else None,
             "km": round(km, 1), "mov_h": round(mov, 2), "v": round(km / mov, 1) if mov else None}
        if a and a["la0"] is not None:
            s0, s1 = (a["la0"], a["lo0"]), (a["la1"], a["lo1"])
            el = (a["el_s"] or 0) / 3600
            f.update(start_home=round(dist_km(s0, HOME), 1), end_home=round(dist_km(s1, HOME), 1),
                     work=round(min(dist_km(p, w) for p in (s0, s1) for w in WORK), 1),
                     a_to_b=round(dist_km(s0, s1), 1), el_h=round(el, 2),
                     temp=round(a["temp"], 1) if a["temp"] is not None else None,
                     stops_per_10km=round(a["st_short"] * 10 / km, 1) if km else None,
                     stop_min_per_h=round(((a["st_short_s"] or 0) / 60 + (a["still_s"] or 0) / 60) / mov, 1) if mov else None,
                     long_stops=a["st_long"], city_core=round(a["core"] or 0, 2))
        out.append(f)

# --- klasyfikacja
def in_bp(d):
    return any(a <= d <= b for a, b in BP)

for f in out:
    away = min(f.get("start_home", 0), f.get("end_home", 0)) > 60
    f["away"] = away
    if in_bp(f["date"]):
        f["cls"] = "bikepacking"
    elif f.get("work", 99) < 1.0 and min(f.get("start_home", 99), f.get("end_home", 99)) < 1.0 and f.get("a_to_b", 0) > 3:
        f["cls"] = "commuting"
    elif f.get("city_core", 0) >= 0.4 and f["dow"] <= 5:
        f["cls"] = "commuting"          # jazda po miescie w dzien roboczy
    else:
        f["cls"] = None

# dlugosc wzgledem sezonu: czas ruchu vs jazdy z +-30 dni roku (bez commutingu i bikepackingu), p75
from datetime import date as _d
base = [f for f in out if f["cls"] is None]
for f in base:
    doy = _d.fromisoformat(f["date"]).timetuple().tm_yday
    win = [g["mov_h"] for g in base if min(abs(_d.fromisoformat(g["date"]).timetuple().tm_yday - doy),
                                           365 - abs(_d.fromisoformat(g["date"]).timetuple().tm_yday - doy)) <= 30]
    win.sort()
    p75 = win[int(0.75 * (len(win) - 1))] if len(win) >= 6 else 3.0
    f["season_p75_h"] = round(p75, 2)
    f["season_rank"] = round(sum(1 for x in win if x <= f["mov_h"]) / len(win), 2) if win else None
    if f["mov_h"] >= max(p75, 2.0):
        f["cls"] = "dluga"
    elif f["dow"] <= 5:
        f["cls"] = "trening"
    else:
        f["cls"] = "krotka_weekend"

json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=0)
print("OK", len(out), "jazd, %.0f s" % (time.time() - t0))
for k in ("bikepacking", "commuting", "dluga", "krotka_weekend", "trening"):
    g = [f for f in out if f["cls"] == k]
    km = sum(f["km"] for f in g); h = sum(f["mov_h"] for f in g)
    st = [f["stop_min_per_h"] for f in g if f.get("stop_min_per_h") is not None]
    print("%-15s n=%3d  km med %5.1f (%.0f-%.0f)  v_ruch %.1f  postoje med %.1f min/h" % (
        k, len(g), statistics.median([f["km"] for f in g]), min(f["km"] for f in g), max(f["km"] for f in g),
        km / h if h else 0, statistics.median(st) if st else -1))
