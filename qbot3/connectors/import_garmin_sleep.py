#!/usr/bin/env python3
"""Cron job: import Garmin sleep data for yesterday/today into qbot_v2.sleep_daily.

Runs every 15 min 05:00-09:00.
Idempotent — upsert per date.
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
conn = psycopg.connect(host="127.0.0.1", dbname="qbot", user="qbot", password="")
cur = conn.cursor()

for ds in (yesterday, today):
    try:
        sl = gc.get_sleep_data(ds)
    except Exception:
        continue
    if not isinstance(sl, dict):
        continue
    daily = sl.get("dailySleepDTO") or {}
    secs = daily.get("sleepTimeSeconds")
    if not secs:
        continue
    st = daily.get("sleepStartTimestampGMT")
    et = daily.get("sleepEndTimestampGMT")
    ss = datetime.fromtimestamp(st / 1000, tz=timezone.utc) if st else None
    se = datetime.fromtimestamp(et / 1000, tz=timezone.utc) if et else None
    cur.execute("INSERT INTO qbot_v2.days (date) VALUES (%s) ON CONFLICT DO NOTHING", (ds,))
    cur.execute(
        """INSERT INTO qbot_v2.sleep_daily
(date,source,sleep_start,sleep_end,duration_min,deep_min,light_min,rem_min,awake_min,score,hrv_ms,resting_hr_bpm,quality_status,imported_at)
VALUES (%s,'garmin_live',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'full'::qbot_v2.quality_status,now())
ON CONFLICT (date) DO UPDATE SET
source='garmin_live',sleep_start=EXCLUDED.sleep_start,sleep_end=EXCLUDED.sleep_end,
duration_min=EXCLUDED.duration_min,deep_min=EXCLUDED.deep_min,light_min=EXCLUDED.light_min,
rem_min=EXCLUDED.rem_min,awake_min=EXCLUDED.awake_min,score=EXCLUDED.score,
hrv_ms=EXCLUDED.hrv_ms,resting_hr_bpm=EXCLUDED.resting_hr_bpm,imported_at=now()""",
        (ds, ss, se, secs // 60,
         (daily.get("deepSleepSeconds") or 0) // 60,
         (daily.get("lightSleepSeconds") or 0) // 60,
         (daily.get("remSleepSeconds") or 0) // 60,
         (daily.get("awakeSleepSeconds") or 0) // 60,
         daily.get("sleepScores", {}).get("overall", {}).get("value"),
         sl.get("avgOvernightHrv"), sl.get("restingHeartRate")),
    )
    print(f"sleep {ds}: {secs // 60} min")

conn.commit()
cur.close()
conn.close()
