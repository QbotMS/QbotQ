#!/usr/bin/env python3
"""data_freshness_check.py — read-only diagnostics for QBot data pipelines.

Outputs JSON to stdout with freshness info for PostgreSQL and SQLite tables.
Does NOT send Telegram. Does NOT modify data.
"""
import json, os, sys, sqlite3
from datetime import datetime, timezone

start = datetime.now(timezone.utc)
result = {
    "status": "OK",
    "checked_at": start.isoformat(),
    "postgres": {},
    "sqlite": {},
    "warnings": [],
}

GARAGE_DB = "/opt/qbot/app/data/garage.db"

# --- PostgreSQL -----------------------------------------------------------
PG_TABLES = [
    "qbot_v2.wellness_daily",
    "qbot_v2.sleep_daily",
    "qbot_v2.energy_daily",
    "qbot_v2.training_sessions",
    "qbot_v2.body_daily",
    "qbot_v2.daily_summary",
]

pg_host = os.getenv("PGHOST", "127.0.0.1")
pg_port = os.getenv("PGPORT", "5432")
pg_db   = os.getenv("PGDATABASE", "qbot")
pg_user = os.getenv("PGUSER", "qbot")
pg_pass = os.getenv("PGPASSWORD", "")

if not all([pg_host, pg_db, pg_user]):
    result["warnings"].append("PGHOST / PGDATABASE / PGUSER not set — skipping PostgreSQL checks")
    result["status"] = "PARTIAL"
else:
    try:
        import psycopg
        conn = psycopg.connect(
            host=pg_host, port=pg_port, dbname=pg_db,
            user=pg_user, password=pg_pass,
            connect_timeout=5,
        )
        for tbl in PG_TABLES:
            try:
                cur = conn.execute(f"SELECT MAX(date)::text, COUNT(*) FROM {tbl}")
                max_date, cnt = cur.fetchone()
                result["postgres"][tbl] = {
                    "max_date": max_date,
                    "row_count": cnt,
                }
            except Exception as exc:
                result["warnings"].append(f"{tbl}: {exc}")
                result["postgres"][tbl] = {"error": str(exc)}
        conn.close()
    except ImportError:
        result["warnings"].append("psycopg not installed — skipping PostgreSQL checks")
        result["status"] = "PARTIAL"
    except Exception as exc:
        result["warnings"].append(f"PostgreSQL connection failed: {exc}")
        result["status"] = "PARTIAL"

# --- SQLite ---------------------------------------------------------------
if not os.path.isfile(GARAGE_DB):
    result["sqlite"]["error"] = f"garage.db not found at {GARAGE_DB}"
    result["status"] = "ERROR"
else:
    try:
        conn = sqlite3.connect(GARAGE_DB)

        # qbot_nutrition_daily
        try:
            cur = conn.execute("SELECT MAX(date), COUNT(*) FROM qbot_nutrition_daily")
            row = cur.fetchone()
            result["sqlite"]["qbot_nutrition_daily"] = {
                "max_date": row[0],
                "row_count": row[1],
            }
        except sqlite3.OperationalError:
            result["sqlite"]["qbot_nutrition_daily"] = {"error": "table not found"}
            result["warnings"].append("SQLite qbot_nutrition_daily table does not exist")

        # reminders
        try:
            cur = conn.execute("SELECT COUNT(*) FROM reminders WHERE active = 1")
            active_cnt = cur.fetchone()[0]
            result["sqlite"]["reminders"] = {
                "active_count": active_cnt,
            }
        except sqlite3.OperationalError:
            result["sqlite"]["reminders"] = {"error": "table not found"}

        # xert_snapshots
        try:
            cur = conn.execute("SELECT MAX(fetched_at), COUNT(*) FROM xert_snapshots")
            row = cur.fetchone()
            result["sqlite"]["xert_snapshots"] = {
                "max_fetched_at": row[0],
                "row_count": row[1],
            }
        except sqlite3.OperationalError:
            result["sqlite"]["xert_snapshots"] = {"error": "table not found"}

        conn.close()
    except Exception as exc:
        result["sqlite"]["error"] = str(exc)
        result["status"] = "ERROR"

# --- Final status ---------------------------------------------------------
if result["status"] == "OK":
    has_errors = any(
        "error" in v for v in {**result["postgres"], **result["sqlite"]}.values()
        if isinstance(v, dict)
    )
    if has_errors or result["warnings"]:
        result["status"] = "PARTIAL"

print(json.dumps(result, indent=2, ensure_ascii=False))
