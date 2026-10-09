#!/usr/bin/env python3
"""Walidacja rozpoznawania MyBiom / do Mamy na historii (leave-one-out), jedno zapytanie. Wynik -> stdout."""
import os, re, sys, time
sys.path.insert(0, "/opt/qbot/app"); os.environ.setdefault("QBOT3_ENABLED", "1")
import qbot_strava as S
import qbot_strava_publish as P

t0 = time.time()
cn = S._dict_conn(); c = cn.cursor()
m = P.kind_model(c)
rows = P._rows(c, "WITH a AS (SELECT ride_key, name, distance_m/1000.0 km, start_date::date d FROM qbot_v2.strava_activity "
                  "WHERE ride_key IS NOT NULL AND distance_m <= 45000 AND sport_type ~* 'ride' AND start_date >= '2025-01-01') "
                  "SELECT DISTINCT a.ride_key, a.name, a.km, a.d, " + P._Z15 + " FROM qbot_v2.activity_record r JOIN a ON r.external_id=a.ride_key "
                  "WHERE r.lat IS NOT NULL")
rides = {}
for r in rows:
    x = rides.setdefault(r["ride_key"], {"name": r["name"], "km": float(r["km"]), "d": str(r["d"]), "t": set()})
    x["t"].add((r["x"], r["y"]))
conf, bad = {}, []
for rk, x in rides.items():
    truth = "domamy" if re.search("mam", x["name"] or "", re.I) else ("mybiom" if re.search("biom", x["name"] or "", re.I) else "inna")
    sc = P.kind_scores(x["t"], m, rk)
    k = P.kind_decide(x["km"], sc) or "inna"
    conf[(truth, k)] = conf.get((truth, k), 0) + 1
    if truth != k:
        bad.append((x["d"], x["name"], round(x["km"], 1), truth, k, sc))
print("jazd:", len(rides), "czas: %.1f s" % (time.time() - t0))
for (t, k), n in sorted(conf.items()):
    print("prawda=%-7s  QBot=%-7s  %d" % (t, k, n))
print("\nPOMYLKI:")
for b in sorted(bad):
    print(b)
cn.close()
