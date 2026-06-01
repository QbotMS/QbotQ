#!/usr/bin/env python3
"""Garmin pipeline diagnostic — file status, DB tables, data freshness."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, "/opt/qbot/app")

APP = Path("/opt/qbot/app")
OUT = APP / "outgoing"

print("=" * 60)
print("GARMIN PIPELINE CHECK")
print("=" * 60)

# ── Files ──────────────────────────────────────────────────────────────────
print("\n--- Files ---")
profiles = sorted(OUT.iterdir()) if OUT.exists() else []
status = "PASS"
for prof in profiles:
    gp = prof / "garmin_proxy"
    if not gp.exists():
        continue
    fits = sorted(gp.glob("*.fit"))
    csvs = sorted(gp.glob("*.csv"))
    newest = None
    for f in sorted(gp.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        newest = f
        break
    print(f"  {prof.name}: {len(fits)} .fit, {len(csvs)} .csv")
    if newest:
        from datetime import datetime
        mt = datetime.fromtimestamp(newest.stat().st_mtime)
        print(f"    newest: {newest.name} ({mt.strftime('%Y-%m-%d %H:%M')})")
    if not fits and not csvs:
        print("    ⚠️  WARN: no proxy files")
        status = "WARN"

# ── DB ─────────────────────────────────────────────────────────────────────
print("\n--- DB Tables ---")
try:
    import psycopg
    conn = psycopg.connect(host="127.0.0.1", dbname="qbot", user="qbot", password="", connect_timeout=5)
    cur = conn.cursor()
    tables = [
        ("qbot_v2.sleep_daily", "sleep"),
        ("qbot_v2.energy_daily", "energy"),
        ("qbot_v2.wellness_daily", "wellness"),
        ("qbot_v2.training_sessions", "training"),
    ]
    for schema_tbl, label in tables:
        schema, tbl = schema_tbl.split(".")
        cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema=%s AND table_name=%s)", (schema, tbl))
        exists = cur.fetchone()[0]
        if not exists:
            print(f"  {label:12s}: TABLE NOT FOUND ❌")
            status = "FAIL"
            continue
        cur.execute(f"SELECT count(*) FROM {schema_tbl}")
        total = cur.fetchone()[0]
        cur.execute(f"SELECT count(*) FROM {schema_tbl} WHERE date >= NOW() - interval '30 days'")
        last30 = cur.fetchone()[0]
        cur.execute(f"SELECT MAX(date) FROM {schema_tbl}")
        last_dt = cur.fetchone()[0]
        status_icon = "✅" if last30 > 0 else "⚠️"
        print(f"  {label:12s}: {total:>5} rows, {last30:>4} last 30d, last={last_dt} {status_icon}")
        if last30 == 0:
            status = "WARN" if status != "FAIL" else status
    conn.close()
except Exception as e:
    print(f"  DB ERROR: {e}")
    status = "FAIL"

# ── Summary ────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"STATUS: {status}")
print(f"{'='*60}")
print("Next actions:" if status != "PASS" else "All checks passed. ✅")
if status == "FAIL":
    print("  - Check if psycopg is installed")
    print("  - Check PostgreSQL is running")
    print("  - Run: systemctl status postgresql")
elif status == "WARN":
    print("  - Check connector logs: /opt/qbot/logs/connector_*.log")
    print("  - Check garmin_auth token is valid")
    print("  - Run: /opt/qbot/app/.venv/bin/python qbot3/connectors/import_garmin_energy.py")

# ── Date-level detail ──────────────────────────────────────────────────────
print("\n--- Date Detail ---")
from psycopg.rows import dict_row
conn2 = psycopg.connect(host="127.0.0.1", dbname="qbot", user="qbot", password="", row_factory=dict_row, connect_timeout=3)
cur2 = conn2.cursor()

for date in ("2026-05-30", "2026-05-29"):
    print(f"\n  {date}:")
    cur2.execute("SELECT body_battery_start, body_battery_end, stress_avg, resting_hr_bpm, spo2_avg, respiration_avg, weight_kg FROM qbot_v2.wellness_daily WHERE date=%s", (date,))
    r = cur2.fetchone()
    if r:
        bb = f"✅ BB {r['body_battery_start']}→{r['body_battery_end']}" if r['body_battery_start'] is not None else "⚠️ BB missing"
        wt = f"weight={r['weight_kg']}kg" if r['weight_kg'] else "weight=NO_RECORD"
        print(f"    {bb} stress={r['stress_avg']} RHR={r['resting_hr_bpm']} SpO2={r['spo2_avg']} {wt}")
    else:
        print("    ⚠️ NO wellness_daily ROW")

    cur2.execute("SELECT total_kcal, steps, quality_status FROM qbot_v2.energy_daily WHERE date=%s", (date,))
    r = cur2.fetchone()
    if r:
        print(f"    ✅ energy {r['total_kcal']}kcal steps={r['steps']} quality={r['quality_status']}")
    else:
        print("    ⚠️ NO energy_daily ROW")

    cur2.execute("SELECT duration_min, score, hrv_ms, resting_hr_bpm FROM qbot_v2.sleep_daily WHERE date=%s", (date,))
    r = cur2.fetchone()
    if r:
        print(f"    ✅ sleep {r['duration_min']}min score={r['score']} HRV={r['hrv_ms']} RHR={r['resting_hr_bpm']}")
    else:
        print("    ⚠️ NO sleep_daily ROW")

conn2.close()
