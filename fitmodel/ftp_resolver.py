from __future__ import annotations

import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import median
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2


ENV_FILE = Path("/etc/qbot/qbot-api.env")
DEFAULT_WINDOW_DAYS = 28


def _load_env_file(env_path: Path = ENV_FILE) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _coerce_date(value: date | datetime | str | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _db_connect():
    _load_env_file()
    kwargs: dict[str, Any] = {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER", "qbot"),
        "dbname": os.getenv("PGDATABASE", "qbot"),
    }
    password = os.getenv("PGPASSWORD")
    if password:
        kwargs["password"] = password
    return psycopg2.connect(**kwargs)


def load_params(db_conn) -> dict:
    with db_conn.cursor() as cur:
        cur.execute("SELECT key, value FROM qbot_v2.fitmodel_param")
        params: dict[str, float] = {}
        for key, value in cur.fetchall():
            if key is None or value is None:
                continue
            params[str(key)] = float(value)
    return params


def compute_ef_median(db_conn, as_of_date=None, window_days=28) -> float | None:
    day = _coerce_date(as_of_date)
    start_day = day - timedelta(days=int(window_days))
    start_ts = datetime.combine(start_day, time.min)
    end_ts = datetime.combine(day + timedelta(days=1), time.min)
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT ef_norm
            FROM qbot_v2.fitmodel_segment
            WHERE hr_quality_ok IS TRUE
              AND ef_norm IS NOT NULL
              AND started_at > %s
              AND started_at < %s
            ORDER BY started_at
            """,
            (start_ts, end_ts),
        )
        values = [float(row[0]) for row in cur.fetchall() if row[0] is not None]
    if len(values) < 3:
        return None
    return float(median(values))


def compute_ftp_est(ef_med, params) -> float | None:
    if ef_med is None:
        return None
    ftp_anchor = params.get("ftp_anchor_w")
    ef_anchor = params.get("ef_anchor")
    if ftp_anchor is None or ef_anchor in (None, 0):
        return None
    return float(ftp_anchor * (float(ef_med) / float(ef_anchor)))


def _fetch_daily_wellness(db_conn, day_value: date) -> dict[str, Any]:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT sleep_duration_min, hrv_ms, resting_hr_bpm, weight_kg
            FROM qbot_v2.qbot_wellness_daily
            WHERE date = %s
            ORDER BY source_priority ASC, imported_at DESC
            LIMIT 1
            """,
            (day_value,),
        )
        row = cur.fetchone()
        if not row:
            return {}
        sleep_duration_min, hrv_ms, resting_hr_bpm, weight_kg = row
        return {
            "sleep_h": float(sleep_duration_min) / 60.0 if sleep_duration_min is not None else None,
            "hrv_night": float(hrv_ms) / 1000.0 if hrv_ms is not None else None,
            "rhr": int(resting_hr_bpm) if resting_hr_bpm is not None else None,
            "weight_kg": float(weight_kg) if weight_kg is not None else None,
        }


def _fetch_last_weight(db_conn, day_value: date) -> float | None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT weight_kg
            FROM qbot_v2.qbot_wellness_daily
            WHERE date <= %s
              AND weight_kg IS NOT NULL
            ORDER BY date DESC, source_priority ASC, imported_at DESC
            LIMIT 1
            """,
            (day_value,),
        )
        row = cur.fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0])


def _count_segments_in_window(db_conn, day_value: date, window_days: int) -> int:
    start_day = day_value - timedelta(days=int(window_days))
    start_ts = datetime.combine(start_day, time.min)
    end_ts = datetime.combine(day_value + timedelta(days=1), time.min)
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM qbot_v2.fitmodel_segment
            WHERE hr_quality_ok IS TRUE
              AND ef_norm IS NOT NULL
              AND started_at > %s
              AND started_at < %s
            """,
            (start_ts, end_ts),
        )
        row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def update_fitmodel_daily(db_conn, day=None) -> dict:
    day_value = _coerce_date(day)
    params = load_params(db_conn)
    window_days = int(params.get("ef_window_days", DEFAULT_WINDOW_DAYS))
    ef_med_28d = compute_ef_median(db_conn, day_value, window_days=window_days)
    ftp_est_w = compute_ftp_est(ef_med_28d, params)
    daily = _fetch_daily_wellness(db_conn, day_value)
    weight_kg = _fetch_last_weight(db_conn, day_value)
    if weight_kg is None and daily.get("weight_kg") is not None:
        weight_kg = float(daily["weight_kg"])
    w_per_kg = float(ftp_est_w / weight_kg) if ftp_est_w is not None and weight_kg not in (None, 0) else None
    segment_count = _count_segments_in_window(db_conn, day_value, window_days)
    notes = f"segments={segment_count}; window_days={window_days}"

    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO qbot_v2.fitmodel_daily (
                day, ftp_est_w, ef_med_28d, weight_kg, w_per_kg,
                glycogen_pct, glycogen_g, sleep_h, hrv_night, rhr, notes
            )
            VALUES (%s, %s, %s, %s, %s, NULL, NULL, %s, %s, %s, %s)
            ON CONFLICT (day) DO UPDATE SET
                ftp_est_w = EXCLUDED.ftp_est_w,
                ef_med_28d = EXCLUDED.ef_med_28d,
                weight_kg = EXCLUDED.weight_kg,
                w_per_kg = EXCLUDED.w_per_kg,
                sleep_h = EXCLUDED.sleep_h,
                hrv_night = EXCLUDED.hrv_night,
                rhr = EXCLUDED.rhr,
                notes = EXCLUDED.notes
            """,
            (
                day_value,
                ftp_est_w,
                ef_med_28d,
                weight_kg,
                w_per_kg,
                daily.get("sleep_h"),
                daily.get("hrv_night"),
                daily.get("rhr"),
                notes,
            ),
        )
    db_conn.commit()

    result = {
        "day": day_value.isoformat(),
        "ftp_est_w": ftp_est_w,
        "ef_med_28d": ef_med_28d,
        "weight_kg": weight_kg,
        "w_per_kg": w_per_kg,
    }
    if daily:
        result.update(daily)
    return result


def run_weekly_job(db_conn) -> dict:
    today = date.today()
    start_day = today - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    start_ts = datetime.combine(start_day, time.min)
    end_ts = datetime.combine(today + timedelta(days=1), time.min)
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT date(started_at) AS day
            FROM qbot_v2.fitmodel_segment
            WHERE started_at >= %s
              AND started_at < %s
            ORDER BY day
            """,
            (start_ts, end_ts),
        )
        days = [row[0] for row in cur.fetchall() if row and row[0] is not None]

    updated_days = 0
    latest_ftp_est_w = None
    for day_value in days:
        result = update_fitmodel_daily(db_conn, day_value)
        updated_days += 1
        if result.get("ftp_est_w") is not None:
            latest_ftp_est_w = result["ftp_est_w"]

    return {"updated_days": updated_days, "latest_ftp_est_w": latest_ftp_est_w}


if __name__ == "__main__":
    conn = _db_connect()
    try:
        result = run_weekly_job(conn)
        print("RESULT:", result)
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM qbot_v2.fitmodel_daily ORDER BY day DESC LIMIT 5")
            print("fitmodel_daily:")
            for row in cur.fetchall():
                print(row)
    finally:
        conn.close()
