#!/usr/bin/env python3
"""[GARMIN-DANE] Etap 7: migracja sql/heat_drift_v1.sql + dociagniecie dryfu dla historii (jazdy > 1,5 h).
Wznawialny (pomija policzone). Paczkami: --limit N (domyslnie 40) -- kilkanascie s na paczke, mozna przez dev_shell_exec.
  .venv/bin/python3 scripts/heat_drift_backfill.py [--from 2024-01-01] [--limit 40]"""
import argparse
import sys
from datetime import date

sys.path.insert(0, "/opt/qbot/app")
from dotenv import load_dotenv

load_dotenv("/opt/qbot/app/.env.local")
load_dotenv("/opt/qbot/app/.env")
from fitmodel.heat_drift import ensure_rides, ensure_schema  # noqa: E402
from qbot_wellness_store import _db_conn  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--from", dest="d0", default="2024-01-01")
p.add_argument("--limit", type=int, default=40)
p.add_argument("--recompute", action="store_true", help="wyczysc cache i licz od nowa")
a = p.parse_args()

conn = _db_conn()
ensure_schema(conn)
if a.recompute:
    conn.execute("TRUNCATE qbot_v2.ride_heat_drift")
    conn.commit()
n = ensure_rides(conn, date.fromisoformat(a.d0), date.today(), limit=a.limit)
conn.commit()
left = conn.execute("""SELECT count(*) AS n FROM qbot_v2.training_sessions t WHERE t.date >= %s AND t.duration_s > 5400
    AND EXISTS (SELECT 1 FROM qbot_v2.activity_record ar WHERE ar.external_id = t.external_id AND ar.sec = 0)
    AND NOT EXISTS (SELECT 1 FROM qbot_v2.ride_heat_drift h WHERE h.external_id = t.external_id)""",
                    (date.fromisoformat(a.d0),)).fetchone()["n"]
conn.close()
print(f"policzone: {n}, zostalo: {left}")
