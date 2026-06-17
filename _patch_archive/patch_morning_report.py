#!/usr/bin/env python3
import ast, shutil, sys
from pathlib import Path

SRC = Path("/opt/qbot/app/event_morning_report.py")
BAK = SRC.with_suffix(".py.bak_patch_20260603")
shutil.copy2(SRC, BAK)
print(f"Backup: {BAK}")
src = SRC.read_text()

OLD_WELLNESS = '''def _wellness_today():
    try:
        import db
        conn = db.get_conn()
        cur = conn.cursor()
        today = date.today().isoformat()
        cur.execute("SELECT hrv_rmssd, resting_hr, sleep_score, sleep_hours, hrv_status FROM wellness WHERE date=%s", (today,))
        row = cur.fetchone()
        conn.close()
        if row:
            return {"hrv": row[0], "resting_hr": row[1], "sleep_score": row[2], "sleep_hours": row[3], "hrv_status": row[4]}
    except Exception as e:
        pass
    return {}'''
