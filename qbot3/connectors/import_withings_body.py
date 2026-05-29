#!/usr/bin/env python3
"""Cron job: import Withings body composition for last 3 days into qbot_v2.body_daily.

Runs at 07:00, 08:00, 09:00.
Only records with actual measurements — no empty days.
Replaces Garmin records for the same date (Withings has precedence).
"""

import sys, json, psycopg, os
sys.path.insert(0, "/opt/qbot/app")
from datetime import datetime, timezone, timedelta

# Load secrets from env file
env_path = "/opt/q/secrets/withings/withings.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k] = v

ACCESS_TOKEN = os.environ.get("WITHINGS_ACCESS_TOKEN", "")
if not ACCESS_TOKEN:
    print("NO ACCESS_TOKEN — attempting refresh")
    sys.exit(1)

import httpx
from dotenv import load_dotenv
load_dotenv("/opt/qbot/app/.env")

now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
three_days_ago = (now - timedelta(days=3)).strftime("%Y-%m-%d")
start_ts = int((now - timedelta(days=3)).timestamp())
end_ts = int(now.timestamp())

response = httpx.get(
    "https://wbsapi.withings.net/v2/measure",
    params={"action": "getmeas", "startdate": start_ts, "enddate": end_ts},
    headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
    timeout=15,
)
data = response.json()
if data.get("status") != 0:
    print(f"Withings API error: status={data.get('status')}")
    exit(1)

grps = data.get("body", {}).get("measuregrps", [])
parsed = {}
for g in grps:
    ts = g.get("date")
    if not ts:
        continue
    ds = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    if ds not in parsed:
        parsed[ds] = {}
    for m in g.get("measures", []):
        t, v, u = m.get("type"), m.get("value", 0), m.get("unit", 0)
        r = v * (10**u)
        if t == 1: parsed[ds]["weight_kg"] = round(r, 2)
        elif t == 5: parsed[ds]["fat_free_kg"] = round(r, 2)
        elif t == 6: parsed[ds]["fat_mass_kg"] = round(r, 2)
        elif t == 8: parsed[ds]["muscle_mass_kg"] = round(r, 2)
        elif t == 9: parsed[ds]["bone_mass_kg"] = round(r, 2)
        elif t == 12: parsed[ds]["visceral_fat"] = int(r) if r else None
        elif t == 76: parsed[ds]["body_water_pct"] = round(r, 1)
        elif t == 88: parsed[ds].setdefault("bone_mass_kg", round(r, 2))

if not parsed:
    print("Withings: no new measurements")
    exit(0)

conn = psycopg.connect(host="127.0.0.1", dbname="qbot", user="qbot", password="")
cur = conn.cursor()
inserted = 0

for ds in sorted(parsed.keys()):
    p = parsed[ds]
    w = p.get("weight_kg")
    if not w:
        continue
    fm = p.get("fat_mass_kg")
    bf = round(fm / w * 100, 1) if fm else None
    # Remove Garmin record (Withings is authoritative for body)
    cur.execute("DELETE FROM qbot_v2.body_daily WHERE date=%s AND source='garmin_live'", (ds,))
    cur.execute(
        """INSERT INTO qbot_v2.body_daily
(date,source,weight_kg,body_fat_pct,fat_mass_kg,muscle_mass_kg,bone_mass_kg,
 body_water_pct,visceral_fat,quality_status,raw_json,imported_at)
VALUES (%s,'withings',%s,%s,%s,%s,%s,%s,%s,'full'::qbot_v2.quality_status,%s::jsonb,now())
ON CONFLICT (date,source) DO UPDATE SET
weight_kg=EXCLUDED.weight_kg,body_fat_pct=EXCLUDED.body_fat_pct,
fat_mass_kg=EXCLUDED.fat_mass_kg,muscle_mass_kg=EXCLUDED.muscle_mass_kg,
bone_mass_kg=EXCLUDED.bone_mass_kg,body_water_pct=EXCLUDED.body_water_pct,
visceral_fat=EXCLUDED.visceral_fat,raw_json=EXCLUDED.raw_json,imported_at=now()""",
        (ds, w, bf, fm, p.get("muscle_mass_kg"), p.get("bone_mass_kg"),
         p.get("body_water_pct"), p.get("visceral_fat"), json.dumps(p)),
    )
    inserted += 1

conn.commit()
cur.close()
conn.close()
print(f"Withings: {inserted} records imported")
