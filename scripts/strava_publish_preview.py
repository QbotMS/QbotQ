#!/usr/bin/env python3
"""Podglad (bez wysylania) dla jazd od --od: rower, tytul, opis. Wynik -> stdout."""
import argparse, os, sys
sys.path.insert(0, "/opt/qbot/app"); os.environ.setdefault("QBOT3_ENABLED", "1")
import qbot_strava as S
import qbot_strava_publish as P

ap = argparse.ArgumentParser(); ap.add_argument("--od", default="2026-10-01"); a = ap.parse_args()
cn = S._dict_conn(); c = cn.cursor(); P.ensure(c)
gm = {r["bike"]: r["strava_name"] for r in P._rows(c, "SELECT bike, strava_name FROM qbot_v2.strava_gear_map")}
acts = P._rows(c, "SELECT strava_id, ride_key, start_date, name FROM qbot_v2.strava_activity WHERE start_date >= %s "
                  "AND ride_key IS NOT NULL AND sport_type ~* 'ride' ORDER BY start_date", (a.od,))
for t in acts:
    print("=" * 70)
    print("%s  strava %s  ride_key %s" % (str(t["start_date"])[:16], t["strava_id"], t["ride_key"]))
    try:
        bike, why = P.bike_of(c, t["ride_key"])
        f = P.build(c, t["ride_key"])
        print("ROWER : %s -> %s (%s)" % (bike, gm.get(bike, "?"), why))
        if P.is_default_name(t["name"]):
            print("TYTUL : %r  ->  %s" % (t["name"], f.get("title")))
        else:
            print("TYTUL : %r  (zostaje - Twoja nazwa)" % t["name"])
        print("OPIS  :\n" + (f["description"] or "(pusty - jazda do Mamy)"))
    except Exception as e:
        print("BLAD  :", e)
cn.close()
