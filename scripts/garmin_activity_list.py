"""garmin_activity_list.py (2026-10-08) - pobiera z Garmin Connect LISTE wszystkich aktywnosci (same podsumowania, bez GPS),
od najnowszej do najstarszej, i zapisuje do /opt/qbot/artifacts/garmin/activities_list.json. Tylko odczyt z Garmina, nic nie zapisuje do bazy.
Uzycie: .venv/bin/python3 scripts/garmin_activity_list.py"""
import json, os, sys, time
sys.path.insert(0, "/opt/qbot/app")
for l in open("/opt/qbot/app/.env.local"):
    if "=" in l and not l.startswith("#"):
        k, v = l.strip().split("=", 1); os.environ.setdefault(k, v.strip().strip('"'))
from qbot_garmin_history import _garmin_client
g = _garmin_client()
out, start, N = [], 0, 100
while True:
    batch = g.get_activities(start, N) or []
    for a in batch:
        t = a.get("activityType") or {}
        out.append({"id": a.get("activityId"), "start": a.get("startTimeLocal"), "name": a.get("activityName"),
                    "type": t.get("typeKey"), "dist_m": a.get("distance"), "dur_s": a.get("duration"),
                    "lat": a.get("startLatitude"), "lon": a.get("startLongitude"), "device": a.get("deviceId"),
                    "manufacturer": a.get("manufacturer")})
    if len(batch) < N: break
    start += N; time.sleep(0.4)
os.makedirs("/opt/qbot/artifacts/garmin", exist_ok=True)
json.dump(out, open("/opt/qbot/artifacts/garmin/activities_list.json", "w"), ensure_ascii=False)
from collections import Counter
print("aktywnosci:", len(out), "| najstarsza:", out[-1]["start"] if out else None, "| najnowsza:", out[0]["start"] if out else None)
print("typy:", Counter(a["type"] for a in out).most_common(12))
