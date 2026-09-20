#!/usr/bin/env python3
"""Cron job: import Garmin energy data into qbot_v2.energy_daily.

Two modes:
  09:00-23:59 every 2h → today's partial snapshot (quality_status=partial)
  05:00-08:59 every 15min → yesterday's finalization (quality_status=full if complete)
"""

import sys, os
sys.path.insert(0, "/opt/qbot/app")
import psycopg
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from garmin_auth import garmin_client
from dotenv import load_dotenv
load_dotenv("/opt/qbot/app/.env")

now = datetime.now(ZoneInfo("Europe/Warsaw"))
hour = now.hour
is_finalize = (5 <= hour <= 8)

if is_finalize:
    target_dates = [(now - timedelta(days=1)).strftime("%Y-%m-%d")]
    quality = "full"
    partial = False
else:
    target_dates = [now.strftime("%Y-%m-%d")]
    quality = "partial"
    partial = True

gc = garmin_client()
conn = psycopg.connect(host="127.0.0.1", dbname="qbot", user="qbot", password="")
cur = conn.cursor()

for ds in target_dates:
    try:
        s = gc.get_user_summary(ds)
    except Exception as e:
        print(f"energy {ds}: API error {e}")
        continue
    tk = s.get("totalKilocalories")
    if not tk:
        print(f"energy {ds}: no data from Garmin")
        continue
    cur.execute("INSERT INTO qbot_v2.days (date) VALUES (%s) ON CONFLICT DO NOTHING", (ds,))
    cur.execute(
        """INSERT INTO qbot_v2.energy_daily
(date,source,resting_kcal,active_kcal,total_kcal,steps,
 quality_status,is_partial_snapshot,snapshot_at,imported_at,updated_at)
VALUES (%s,'garmin_live',%s,%s,%s,%s,
        %s::qbot_v2.quality_status,%s,now(),now(),now())
ON CONFLICT (date) DO UPDATE SET
source='garmin_live',resting_kcal=EXCLUDED.resting_kcal,
active_kcal=EXCLUDED.active_kcal,total_kcal=EXCLUDED.total_kcal,
steps=EXCLUDED.steps,
quality_status=%s::qbot_v2.quality_status,
is_partial_snapshot=%s,snapshot_at=now(),updated_at=now()""",
        (ds, s.get("bmrKilocalories"), s.get("activeKilocalories"), tk, s.get("totalSteps"),
         quality, partial, quality, partial),
    )
    # Also write wellness (body battery, stress, SpO2, RHR, respiration)
    cur.execute(
        """INSERT INTO qbot_v2.wellness_daily
(date,source,resting_hr_bpm,body_battery_start,body_battery_end,
 stress_avg,spo2_avg,respiration_avg,body_battery_charged,body_battery_drained,
 quality_status,imported_at)
VALUES (%s,'garmin_live',%s,%s,%s,%s,%s,%s,%s,%s,%s::qbot_v2.quality_status,now())
ON CONFLICT (date) DO UPDATE SET
source='garmin_live',resting_hr_bpm=EXCLUDED.resting_hr_bpm,
body_battery_start=EXCLUDED.body_battery_start,
body_battery_end=EXCLUDED.body_battery_end,
stress_avg=EXCLUDED.stress_avg,spo2_avg=EXCLUDED.spo2_avg,
respiration_avg=EXCLUDED.respiration_avg,
body_battery_charged=EXCLUDED.body_battery_charged,
body_battery_drained=EXCLUDED.body_battery_drained,
quality_status=EXCLUDED.quality_status,imported_at=now()""",
        (ds,
         s.get("restingHeartRate"),
         s.get("bodyBatteryAtWakeTime"),
         s.get("bodyBatteryMostRecentValue"),
         s.get("averageStressLevel"),
         s.get("averageSpo2"),
         s.get("avgWakingRespirationValue"),
         s.get("bodyBatteryChargedValue"),
         s.get("bodyBatteryDrainedValue"),
         quality),
    )
    # HRV: qbot_v2.wellness_daily nie ma wlasnego zrodla HRV -- Garmin oddaje je
    # w danych snu (qbot_v2.sleep_daily). Domykamy tu, zeby JEDNA tabela wellness
    # miala komplet i raporty nie musialy siegac fallbackiem po sleep_daily.
    cur.execute(
        """UPDATE qbot_v2.wellness_daily w
           SET hrv_ms = s.hrv_ms
           FROM qbot_v2.sleep_daily s
           WHERE w.date = %s AND s.date = %s
             AND s.hrv_ms IS NOT NULL
             AND w.hrv_ms IS DISTINCT FROM s.hrv_ms""",
        (ds, ds),
    )
    print(f"energy {ds}: {tk} kcal quality={quality}")

# Fallback: podloga aktywnych kcal z ModelQ (jazdy z mocy 1Hz).
# Patrz fitmodel/energy_fallback.py -- Garmin zostaje glowny, ModelQ tylko podnosi.
try:
    from fitmodel.energy_fallback import compute_day
    for ds in target_dates:
        res = compute_day(conn, ds)
        if res:
            print(f"energy_eff {ds}: active_eff={res['active_kcal_eff']:.0f} source={res['source']}")
except Exception as e:
    print(f"energy_eff: fallback error {e}")

conn.commit()
cur.close()
conn.close()
