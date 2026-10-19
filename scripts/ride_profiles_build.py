# -*- coding: utf-8 -*-
"""Profile jazd -> sekcja "profiles" w config/speed_model.json (2026-10-19). Dok.: docs/RIDE_PROFILES.md

compute(cur, days=365): klasyfikacja jazd z ostatnich `days` dni (qbot3/routes/ride_profiles.classify_rides),
postoje per profil (mikro min/km, krotkie min/h ruchu, od pierwszego km) z zapisu 1 Hz (speed_model_review_v2.stops),
p75 czasu ruchu wg miesiaca (regula "dluga"). Uzywane tez przez tygodniowa rekalibracje (speed_model_recalibrate.py).
Wspolczynnik tempa w zabudowie (city.speed_factor) -- z analizy 19.10 (pelne jazdy miejskie vs tabela, 38 jazd: x0,925);
rekalibracja go nie zmienia (za malo jazd miejskich na tydzien).

Uruchom: .venv/bin/python3 scripts/ride_profiles_build.py            (raport)
         .venv/bin/python3 scripts/ride_profiles_build.py --write    (zapis do aktywnego modelu -- tylko po decyzji Michala)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

APP = "/opt/qbot/app"
sys.path.insert(0, APP); sys.path.insert(0, APP + "/scripts")
os.environ.setdefault("QBOT3_ENABLED", "1")

HOME = [52.345, 21.11]          # najczestszy start/meta jazd (analiza 19.10)
CITY_SPEED = 0.925              # tempo w zabudowie vs tabela (analiza 19.10, pelne jazdy)


def compute(cur, days: int = 365, prev: dict | None = None) -> dict:
    import speed_model_review_v2 as V2
    from qbot3.routes import ride_profiles as RP
    since = (date.today() - timedelta(days=days)).isoformat()
    cur.execute("SELECT external_id, date, distance_m FROM qbot_v2.training_sessions "
                "WHERE sport_type='cycling' AND date >= %s AND distance_m >= 5000 ORDER BY date", (since,))
    rides, rows = [], []
    for eid, d, dist in cur.fetchall():
        f = RP.ride_features(cur, eid)
        s = V2.stops(cur, eid)
        if not f or not s:
            continue
        km = float(dist) / 1000.0
        rides.append(dict(id=eid, date=d, km=km, mov_h=s[0], **f))
        rows.append(dict(id=eid, km=km, mov_h=s[0], mikro=s[1].get("mikro", 0.0), krotkie=s[1].get("krotkie", 0.0)))
    cls = RP.classify_rides(rides, HOME)
    stops = RP.fit_stops(rows, cls)
    prev = prev or {}
    for p in ("trening", "krotka_weekend", "dluga", "miasto"):   # za malo jazd -> poprzednia wartosc
        if p not in stops and (prev.get("stops") or {}).get(p):
            stops[p] = prev["stops"][p]
    city = dict(prev.get("city") or {}, speed_factor=(prev.get("city") or {}).get("speed_factor", CITY_SPEED),
                profile_min_share=0.5)
    if stops.get("miasto") and stops.get("trening"):
        city["extra_micro_min_per_km"] = round(max(0.0, stops["miasto"]["micro_min_per_km"] - stops["trening"]["micro_min_per_km"]), 3)
    counts = {p: sum(1 for v in cls.values() if v == p) for p in RP.PROFILES}
    return {"stops": stops, "city": city,
            "rules": {"home": HOME, "away_km": 60, "min_h": 2.0, "p75_moving_h_by_month": RP.p75_by_month(rides, cls)},
            "rides": counts, "window_days": days, "since": since, "doc": "docs/RIDE_PROFILES.md"}


def main() -> int:
    from fitmodel.ftp_resolver import _db_connect
    path = APP + "/config/speed_model.json"
    act = json.load(open(path, encoding="utf-8"))
    conn = _db_connect(); cur = conn.cursor()
    prof = compute(cur, 365, act.get("profiles"))
    conn.close()
    print(json.dumps(prof, ensure_ascii=False, indent=1))
    if "--write" in sys.argv:
        hist = act.setdefault("history", [])
        hist.append({"version": act.get("version"), "approved_at": act.get("approved_at"),
                     "note": "przed profilami jazd (postoje normal: free_h 1 h)"})
        act["profiles"] = prof
        act["version"] = date.today().isoformat() + "p"
        act["approved_at"] = date.today().isoformat()
        act["approved_by"] = ("Michal (czat 19.10): profile jazd -- tempo z tabeli 120 dni, postoje wg profilu (365 dni), "
                              "miasto x0,925 na odcinkach w zabudowie")
        tmp = path + ".tmp"
        json.dump(act, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        print("ZAPISANO", path, act["version"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
