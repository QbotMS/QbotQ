from __future__ import annotations

import math
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import numpy as np
import psycopg2
from fitparse import FitFile


WINDOW_SECONDS = 60
MIN_SEGMENT_SECONDS = 180
MIN_START_OFFSET_SECONDS = 1200
POWER_CV_MAX = 0.15
HR_LOCK_DELTA = 3
HR_JUMP_DELTA = 15
HR_LOCK_SECONDS = 30
POWER_JUMP_DELTA = 5


def extract_ride_id(fit_path: str) -> str:
    return Path(fit_path).stem


def _get_field_value(message: Any, field_name: str) -> Any:
    try:
        if hasattr(message, "get_value"):
            return message.get_value(field_name)
    except Exception:
        pass
    try:
        for field in getattr(message, "fields", []):
            if getattr(field, "name", None) == field_name:
                return getattr(field, "value", None)
    except Exception:
        pass
    return None


def parse_fit_to_seconds(fit_path: str) -> list[dict]:
    rows: list[dict[str, Any]] = []
    try:
        fit = FitFile(fit_path)
        for message in fit.get_messages("record"):
            timestamp = _get_field_value(message, "timestamp")
            if timestamp is None:
                continue
            if isinstance(timestamp, datetime):
                timestamp = timestamp.replace(microsecond=0)
            row = {
                "timestamp": timestamp,
                "power": _get_field_value(message, "power"),
                "heart_rate": _get_field_value(message, "heart_rate"),
                "cadence": _get_field_value(message, "cadence"),
                "temperature": _get_field_value(message, "temperature"),
                "speed": _get_field_value(message, "speed"),
                "distance": _get_field_value(message, "distance"),
                "altitude": _get_field_value(message, "altitude"),
            }
            rows.append(row)
    except Exception:
        return []

    if not rows:
        return []

    rows.sort(key=lambda item: item["timestamp"])

    first_ts = rows[0]["timestamp"]
    last_ts = rows[-1]["timestamp"]
    if not isinstance(first_ts, datetime) or not isinstance(last_ts, datetime):
        return rows

    second_map: dict[datetime, dict[str, Any]] = {}
    for row in rows:
        ts = row["timestamp"]
        if not isinstance(ts, datetime):
            continue
        sec = ts.replace(microsecond=0)
        second_map[sec] = dict(row, timestamp=sec)

    timeline: list[dict[str, Any]] = []
    current = first_ts.replace(microsecond=0)
    end = last_ts.replace(microsecond=0)
    while current <= end:
        timeline.append(
            second_map.get(
                current,
                {
                    "timestamp": current,
                    "power": None,
                    "heart_rate": None,
                    "cadence": None,
                    "temperature": None,
                    "speed": None,
                    "distance": None,
                    "altitude": None,
                },
            )
        )
        current += timedelta(seconds=1)

    return timeline


def _ensure_segment_index(db_conn) -> None:
    with db_conn.cursor() as cur:
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS fitmodel_segment_ride_started_idx
            ON qbot_v2.fitmodel_segment (ride_id, started_at)
            """
        )
    db_conn.commit()


def _load_fitmodel_params(db_conn) -> dict[str, float]:
    defaults = {
        "hr_max_bpm": 184.0,
        "k_temp": 0.004,
        "t_ref_c": 20.0,
    }
    keys = tuple(defaults.keys())
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT key, value FROM qbot_v2.fitmodel_param WHERE key = ANY(%s)",
            (list(keys),),
        )
        for key, value in cur.fetchall():
            try:
                defaults[str(key)] = float(value)
            except Exception:
                continue
    return defaults


def _rolling_np(power_values: list[float]) -> float | None:
    if len(power_values) < 30:
        return None
    arr = np.asarray(power_values, dtype=float)
    kernel = np.ones(30, dtype=float) / 30.0
    rolling = np.convolve(arr, kernel, mode="valid")
    if rolling.size == 0:
        return None
    return float(np.mean(rolling ** 4) ** 0.25)


def _segment_hr_quality_ok(segment_rows: list[dict[str, Any]]) -> bool:
    paired = [
        row for row in segment_rows
        if row.get("heart_rate") is not None and row.get("cadence") is not None
    ]
    if sum(1 for row in paired if abs(float(row["heart_rate"]) - float(row["cadence"])) < HR_LOCK_DELTA) > HR_LOCK_SECONDS:
        return False

    for prev, curr in zip(segment_rows, segment_rows[1:]):
        hr_prev = prev.get("heart_rate")
        hr_curr = curr.get("heart_rate")
        p_prev = prev.get("power")
        p_curr = curr.get("power")
        if hr_prev is None or hr_curr is None or p_prev is None or p_curr is None:
            continue
        if abs(float(hr_curr) - float(hr_prev)) > HR_JUMP_DELTA and abs(float(p_curr) - float(p_prev)) <= POWER_JUMP_DELTA:
            return False

    return True


def _segment_metrics(segment_rows: list[dict[str, Any]], params: dict[str, float]) -> dict[str, Any]:
    power_values = [float(row["power"]) for row in segment_rows if row.get("power") is not None]
    hr_values = [float(row["heart_rate"]) for row in segment_rows if row.get("heart_rate") is not None]
    cadence_values = [float(row["cadence"]) for row in segment_rows if row.get("cadence") is not None]
    temp_values = [float(row["temperature"]) for row in segment_rows if row.get("temperature") is not None]

    np_w = _rolling_np(power_values)
    hr_avg = float(mean(hr_values)) if hr_values else None
    cadence_avg = float(mean(cadence_values)) if cadence_values else None
    temp_c = float(mean(temp_values)) if temp_values else None

    ef_raw = None
    ef_norm = None
    if np_w is not None and hr_avg not in (None, 0):
        ef_raw = float(np_w / hr_avg)
        ef_norm = ef_raw
        if temp_c is not None:
            ef_norm = ef_raw * (1.0 + float(params["k_temp"]) * (float(params["t_ref_c"]) - temp_c))

    return {
        "np_w": np_w,
        "hr_avg": hr_avg,
        "cadence_avg": cadence_avg,
        "temp_c": temp_c,
        "ef_raw": ef_raw,
        "ef_norm": ef_norm,
        "hr_quality_ok": _segment_hr_quality_ok(segment_rows),
    }


def _stable_window_ok(window_rows: list[dict[str, Any]], hr_max: float) -> bool:
    valid_points = [
        row for row in window_rows
        if row.get("power") is not None and row.get("heart_rate") is not None
    ]
    if len(valid_points) < 5:
        return False

    power_values = [float(row["power"]) for row in valid_points]
    hr_values = [float(row["heart_rate"]) for row in valid_points]
    power_mean = float(np.mean(power_values))
    if power_mean <= 0:
        return False

    power_cv = float(np.std(power_values, ddof=0) / power_mean)
    window_np = _rolling_np(power_values)
    variability_index = float(window_np / power_mean) if window_np is not None else None
    if power_cv > 0.30 and (variability_index is None or variability_index > 1.10):
        return False

    hr_mean = float(np.mean(hr_values))
    hr_low = 0.65 * hr_max
    hr_high = 0.85 * hr_max
    return hr_low <= hr_mean <= hr_high


def ingest_fit_file(fit_path: str, db_conn) -> dict:
    ride_id = extract_ride_id(fit_path)
    rows = parse_fit_to_seconds(fit_path)
    if not rows:
        return {"segments_found": 0, "segments_saved": 0, "ride_id": ride_id}

    _ensure_segment_index(db_conn)
    params = _load_fitmodel_params(db_conn)
    hr_max = float(params["hr_max_bpm"])

    stable_flags: list[bool] = [False] * len(rows)
    first_ts = rows[0]["timestamp"]
    if not isinstance(first_ts, datetime):
        return {"segments_found": 0, "segments_saved": 0, "ride_id": ride_id}

    for idx, row in enumerate(rows):
        timestamp = row["timestamp"]
        if not isinstance(timestamp, datetime):
            continue
        elapsed_s = int((timestamp - first_ts).total_seconds())
        if elapsed_s < MIN_START_OFFSET_SECONDS:
            continue
        window_start = max(0, idx - WINDOW_SECONDS + 1)
        window_rows = rows[window_start : idx + 1]
        stable_flags[idx] = _stable_window_ok(window_rows, hr_max)

    segments: list[tuple[int, int]] = []
    run_start: int | None = None
    for idx, stable in enumerate(stable_flags):
        if stable and run_start is None:
            run_start = idx
        if (not stable or idx == len(stable_flags) - 1) and run_start is not None:
            run_end = idx if stable and idx == len(stable_flags) - 1 else idx - 1
            run_len = run_end - run_start + 1
            if run_len >= MIN_SEGMENT_SECONDS:
                segments.append((run_start, run_end))
            run_start = None if not stable else idx

    if run_start is not None:
        run_end = len(stable_flags) - 1
        run_len = run_end - run_start + 1
        if run_len >= MIN_SEGMENT_SECONDS:
            segments.append((run_start, run_end))

    saved = 0
    insert_rows: list[tuple[Any, ...]] = []
    for start_idx, end_idx in segments:
        segment_rows = rows[start_idx : end_idx + 1]
        if not segment_rows:
            continue
        metrics = _segment_metrics(segment_rows, params)
        started_at = segment_rows[0]["timestamp"]
        dur_s = len(segment_rows)
        insert_rows.append(
            (
                ride_id,
                started_at,
                dur_s,
                metrics["np_w"],
                metrics["hr_avg"],
                metrics["cadence_avg"],
                metrics["temp_c"],
                None,
                metrics["ef_raw"],
                metrics["ef_norm"],
                metrics["hr_quality_ok"],
                1.0,
            )
        )

    if insert_rows:
        with db_conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO qbot_v2.fitmodel_segment (
                    ride_id, started_at, dur_s, np_w, hr_avg, cadence_avg, temp_c,
                    surface_type, ef_raw, ef_norm, hr_quality_ok, readiness_weight
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (ride_id, started_at) DO NOTHING
                """,
                insert_rows,
            )
            saved = cur.rowcount if cur.rowcount != -1 else len(insert_rows)
        db_conn.commit()

    return {
        "segments_found": len(segments),
        "segments_saved": saved,
        "ride_id": ride_id,
    }


def ingest_all_new(fit_dir: str, db_conn) -> dict:
    fit_dir_path = Path(fit_dir)
    fit_files = sorted(
        path for path in fit_dir_path.iterdir()
        if path.is_file() and path.suffix.lower() == ".fit"
    )

    existing_rides: set[str] = set()
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT ride_id FROM qbot_v2.fitmodel_segment")
        existing_rides = {str(row[0]) for row in cur.fetchall()}

    processed = 0
    skipped = 0
    total_segments = 0
    for fit_file in fit_files:
        ride_id = extract_ride_id(str(fit_file))
        if ride_id in existing_rides:
            skipped += 1
            continue
        result = ingest_fit_file(str(fit_file), db_conn)
        processed += 1
        total_segments += int(result.get("segments_saved", 0) or 0)
        existing_rides.add(ride_id)

    return {
        "processed": processed,
        "skipped": skipped,
        "total_segments": total_segments,
    }


def _connect_db():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        dbname=os.getenv("PGDATABASE", "qbot"),
    )


if __name__ == "__main__":
    fit_dir = "/opt/qbot/app/outgoing/michal/hammerhead_originals/"
    conn = _connect_db()
    try:
        result = ingest_all_new(fit_dir, conn)
        print(result)
    finally:
        conn.close()
