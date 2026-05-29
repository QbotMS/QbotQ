#!/usr/bin/env python3
"""Cron job: import Garmin training activities for last 2 days into qbot_v2.training_sessions.

Runs every 15 min 09:00-23:59.
Idempotent via UNIQUE(external_id).
"""

import sys, os
sys.path.insert(0, "/opt/qbot/app")
import psycopg
from datetime import datetime, timezone, timedelta
from garmin_auth import garmin_client
from dotenv import load_dotenv
load_dotenv("/opt/qbot/app/.env")

now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

gc = garmin_client()
acts = gc.get_activities_by_date(yesterday, today)

conn = psycopg.connect(host="127.0.0.1", dbname="qbot", user="qbot", password="")
cur = conn.cursor()
count = 0

for a in acts:
    if not isinstance(a, dict):
        continue
    aid = str(a.get("activityId", ""))
    if not aid:
        continue
    start_ts = a.get("startTimeGMT")
    if not start_ts:
        continue
    started_at = datetime.strptime(start_ts, "%Y-%m-%d %H:%M:%S")
    ds = started_at.strftime("%Y-%m-%d")
    cur.execute("INSERT INTO qbot_v2.days (date) VALUES (%s) ON CONFLICT DO NOTHING", (ds,))
    cur.execute(
        """INSERT INTO qbot_v2.training_sessions
(date,started_at,sport_type,activity_name,distance_m,duration_s,elevation_m,
 avg_power_w,normalized_power_w,tss,avg_hr_bpm,max_hr_bpm,
 calories,max_power_w,avg_cadence_rpm,
 aerobic_training_eff,anaerobic_training_eff,intensity_factor,
 source,external_id,quality_status,imported_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'garmin_live',%s,'full'::qbot_v2.quality_status,now())
ON CONFLICT (external_id) DO UPDATE SET
started_at=EXCLUDED.started_at,sport_type=EXCLUDED.sport_type,
activity_name=EXCLUDED.activity_name,distance_m=EXCLUDED.distance_m,
duration_s=EXCLUDED.duration_s,elevation_m=EXCLUDED.elevation_m,
avg_power_w=EXCLUDED.avg_power_w,normalized_power_w=EXCLUDED.normalized_power_w,
tss=EXCLUDED.tss,avg_hr_bpm=EXCLUDED.avg_hr_bpm,max_hr_bpm=EXCLUDED.max_hr_bpm,
calories=EXCLUDED.calories,max_power_w=EXCLUDED.max_power_w,
avg_cadence_rpm=EXCLUDED.avg_cadence_rpm,
aerobic_training_eff=EXCLUDED.aerobic_training_eff,
anaerobic_training_eff=EXCLUDED.anaerobic_training_eff,
intensity_factor=EXCLUDED.intensity_factor,imported_at=now()""",
        (ds, started_at,
         a.get("activityType", {}).get("typeKey", "other") if isinstance(a.get("activityType"), dict) else "other",
         (a.get("activityName") or "")[:200],
         a.get("distance"), int(a.get("duration", 0)) if a.get("duration") else None,
         a.get("elevationGain"), a.get("avgPower"), a.get("normPower"),
         a.get("trainingStressScore"),
         int(a.get("averageHR")) if a.get("averageHR") else None,
         int(a.get("maxHR")) if a.get("maxHR") else None,
         a.get("calories"), a.get("maxPower"), a.get("averageBikingCadenceInRevPerMinute"),
         a.get("aerobicTrainingEffect"), a.get("anaerobicTrainingEffect"), a.get("intensityFactor"),
         aid),
    )
    count += 1

conn.commit()
cur.close()
conn.close()
print(f"training: {count} activities imported")
