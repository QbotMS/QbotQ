#!/usr/bin/env python3
"""Uzupelnia qbot_v2.activity_device z plikow FIT w /opt/qbot/artifacts/fit dla jazd z activity_fit_raw. Uzycie: --apply [--limit N]"""
import sys, os; sys.path.insert(0, "/opt/qbot/app")
from qbot3.rides import activity_devices as ad
apply = "--apply" in sys.argv
lim = int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else 100000
conn = ad._conn(); ad.ensure_tables(conn); cur = conn.cursor()
import glob
cur.execute("SELECT DISTINCT external_id FROM qbot_v2.activity_device"); have = {r[0] for r in cur.fetchall()}
rows = sorted([(os.path.basename(f)[:-4], f) for f in glob.glob("/opt/qbot/artifacts/fit/*.fit") if os.path.basename(f)[:-4] not in have], reverse=True)[:lim]
done = 0; miss = 0
for ext, fit in rows:
    p = fit if fit and os.path.exists(fit) else "/opt/qbot/artifacts/fit/%s.fit" % ext
    if not os.path.exists(p): miss += 1; continue
    if apply:
        try: ad.store_devices(conn, ext, ad.parse_fit_devices(p)); done += 1
        except Exception as e: print("ERR", ext, e)
    else: done += 1
print(("zapisano" if apply else "do zrobienia"), done, "| brak FIT:", miss)
