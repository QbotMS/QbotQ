#!/usr/bin/env python3
"""GEAR-OBS: jednorazowe przetworzenie istniejacych uwag z 'W czym jechalem' (od 2026-09-01).
Uruchamianie: ten skrypt z argumentem 'start' odpala sam siebie w tle (odlaczony, nie blokuje DEV MCP) i od razu konczy;
wynik w /opt/qbot/artifacts/gear_obs_backfill.txt. Bez argumentu = wlasciwa praca."""
import os, sys, json, subprocess

OUT = "/opt/qbot/artifacts/gear_obs_backfill.txt"
if len(sys.argv) > 1 and sys.argv[1] == "start":
    os.makedirs("/opt/qbot/artifacts", exist_ok=True)
    f = open(OUT, "w")
    subprocess.Popen([sys.executable, os.path.abspath(__file__)], stdout=f, stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, start_new_session=True, cwd="/opt/qbot/app")
    print("uruchomione w tle -> " + OUT)
    sys.exit(0)

sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from qbot3.routes import gear_obs as GO
r = GO.backfill("2026-09-01")
print("uwag:", r["n"])
for k, x in r["wyniki"]:
    print(k, json.dumps(x, ensure_ascii=False, default=str)[:300])
print("KONIEC")
