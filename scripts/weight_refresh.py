#!/usr/bin/env python3
"""Odswiezenie wagi po NOWYM wazeniu (2026-10-08).

Wolany przez run_withings_garmin_sync.sh TYLKO gdy sync Withings przetworzyl nowy pomiar
(zmienil sie plik stanu). Dzieki temu Garmin jest pytany wylacznie po faktycznym wazeniu,
a nie co 15 min.

Kroki:
 1. import_garmin_body.py --days 3  -> qbot_v2.body_measurements
 2. save_readiness za 3 ostatnie dni -> fitmodel_daily.weight_kg (carry-forward z body_measurements)
 3. w_per_kg = ftp_est_w / weight_kg za te dni (progi ModelQ NIETKNIETE)
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

APP = Path("/opt/qbot/app")
PY = str(APP / ".venv/bin/python3")
sys.path.insert(0, str(APP))
os.environ.setdefault("QBOT3_ENABLED", "1")

try:
    from dotenv import load_dotenv
    load_dotenv(APP / ".env.local")
    load_dotenv(APP / ".env")
except Exception:
    pass

DAYS = 3


def main() -> int:
    print(f"[weight_refresh] start {date.today().isoformat()}")
    rc = subprocess.run([PY, "qbot3/connectors/import_garmin_body.py", "--days", str(DAYS)],
                        cwd=str(APP)).returncode
    print(f"[weight_refresh] import_garmin_body rc={rc}")

    from fitmodel.readiness import save_readiness, _db_connect
    conn = _db_connect()
    try:
        today = date.today()
        days = [today - timedelta(days=i) for i in range(DAYS - 1, -1, -1)]
        for d in days:
            save_readiness(conn, d)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE qbot_v2.fitmodel_daily SET w_per_kg = ftp_est_w / weight_kg "
                "WHERE day >= %s AND weight_kg IS NOT NULL AND weight_kg > 0 AND ftp_est_w IS NOT NULL",
                (days[0],),
            )
            cur.execute("SELECT weight_kg FROM qbot_v2.fitmodel_daily WHERE day=%s", (today,))
            r = cur.fetchone()
        conn.commit()
        print(f"[weight_refresh] ModelQ waga dzis: {r[0] if r else None}")
    finally:
        conn.close()
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
