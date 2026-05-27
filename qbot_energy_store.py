#!/usr/bin/env python3
"""QBot Energy Store — on-demand Garmin energy fetch + daily_energy_expenditure persistence."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from typing import Any


def _db():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
    )


def _garmin_stats(date_str: str) -> dict[str, Any] | None:
    """Fetch Garmin energy stats for a single date via garminconnect API.

    Returns dict with active_kcal, resting_kcal, bmr_kcal, total_kcal
    or None on failure.
    """
    email = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if not email or not password:
        return None

    tokenstore = os.getenv("GARMIN_TOKENSTORE", "/opt/qbot/app/.garmin_tokens")
    profile_path = "/opt/qbot/app/.garmin_profile.json"

    if not os.path.exists(tokenstore) or not os.path.exists(profile_path):
        return None

    try:
        from garminconnect import Garmin

        with open(profile_path) as f:
            profile = json.load(f)
        g = Garmin(email, password)
        g.client.load(tokenstore)
        g.display_name = profile.get("display_name", "?")

        stats = g.get_stats(date_str)
        if not stats:
            return None

        active = float(stats.get("activeKilocalories", 0) or 0)
        bmr = float(stats.get("bmrKilocalories", 0) or 0)
        total = float(stats.get("totalKilocalories", 0) or 0)
        resting = total - active if total else bmr

        return {
            "active_kcal": round(active, 1),
            "resting_kcal": round(resting, 1),
            "bmr_kcal": round(bmr, 1),
            "total_kcal": round(total, 1),
        }
    except Exception:
        return None


def ensure_daily_energy_expenditure(
    date_str: str,
    reason: str = "qbot_query",
    raw_query: str | None = None,
) -> dict[str, Any]:
    """Ensure daily_energy_expenditure exists for a date.

    If no record exists, attempts to fetch energy data from Garmin
    and persist it.

    Returns:
      status: existing | fetched | error
      date: the date string
      record: the daily_energy_expenditure row (if available)
      error_reason: one of garmin_auth_failed | garmin_no_data | importer_error | db_write_failed | unknown
    """
    c = _db()
    cur = c.cursor()

    # 1. Check existing
    cur.execute("SELECT * FROM daily_energy_expenditure WHERE date=%s", (date_str,))
    row = cur.fetchone()
    if row:
        record = _serialize(dict(row))
        c.close()
        return {"status": "existing", "date": date_str, "record": record}

    # 2. Fetch from Garmin
    c.close()
    try:
        stats = _garmin_stats(date_str)
    except Exception as e:
        return {"status": "error", "date": date_str, "record": None,
                "error_reason": "garmin_auth_failed", "details": str(e)[:200]}

    if stats is None:
        return {"status": "error", "date": date_str, "record": None,
                "error_reason": "garmin_auth_failed",
                "details": "Garmin credentials or token unavailable, or API call failed."}

    total = stats["total_kcal"]
    if not total or total == 0:
        return {"status": "error", "date": date_str, "record": None,
                "error_reason": "garmin_no_data_for_date",
                "details": f"Garmin returned total_kcal={total} for {date_str}."}

    # 3. Insert
    try:
        c2 = _db()
        cur2 = c2.cursor()
        cur2.execute(
            """INSERT INTO daily_energy_expenditure
               (date, resting_kcal_out, active_kcal_out, total_kcal_out, kcal_burned_total,
                source, confidence, imported_at, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (date) DO UPDATE SET
                 resting_kcal_out=EXCLUDED.resting_kcal_out,
                 active_kcal_out=EXCLUDED.active_kcal_out,
                 total_kcal_out=EXCLUDED.total_kcal_out,
                 kcal_burned_total=EXCLUDED.kcal_burned_total,
                 source=EXCLUDED.source,
                 updated_at=EXCLUDED.updated_at
               RETURNING *""",
            (date_str, stats["resting_kcal"], stats["active_kcal"], total, total,
             "garmin_on_demand", "high",
             datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc)),
        )
        record = _serialize(dict(cur2.fetchone()))
        c2.commit()
        c2.close()
    except Exception:
        try:
            c2.close()
        except Exception:
            pass
        # ON CONFLICT may not work if there's no unique constraint on date.
        # Fallback: just insert.
        try:
            c3 = _db()
            cur3 = c3.cursor()
            cur3.execute(
                """INSERT INTO daily_energy_expenditure
                   (date, resting_kcal_out, active_kcal_out, total_kcal_out, kcal_burned_total,
                    source, confidence, imported_at, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (date_str, stats["resting_kcal"], stats["active_kcal"], total, total,
                 "garmin_on_demand", "high",
                 datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc)),
            )
            record = _serialize(dict(cur3.fetchone()))
            c3.commit()
            c3.close()
        except Exception as e:
            return {"status": "error", "date": date_str, "record": None,
                    "error_reason": "db_write_failed", "details": str(e)[:200]}

    return {"status": "fetched", "date": date_str, "record": record}


def _serialize(d: dict) -> dict:
    """Convert non-serializable types to strings."""
    out = {}
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, (int, float, str, bool, type(None))):
            out[k] = v
        else:
            out[k] = str(v)
    return out
