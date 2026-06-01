"""QBot PostgreSQL wellness/sleep/nutrition store — import + query tools."""
from __future__ import annotations

import os
import json
import base64 as _b64
from datetime import date, timedelta, datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row


def _db_conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=5,
    )


def _today_str() -> str:
    return date.today().isoformat()


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# DB STATUS
# ═══════════════════════════════════════════════════════════════════════════

def _tool_qbot_wellness_db_status(_args: dict | None = None) -> dict[str, Any]:
    tables = ["qbot_wellness_daily", "qbot_sleep_daily", "qbot_nutrition_daily",
              "qbot_wellness_notes", "qbot_import_runs"]
    counts: dict[str, int] = {}
    issues: list[str] = []
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            for t in tables:
                cur.execute(f"SELECT COUNT(*) as c FROM {t}")
                row = cur.fetchone()
                counts[t] = row["c"] if row else 0
            cur.execute("SELECT date_from FROM qbot_import_runs ORDER BY created_at DESC LIMIT 1")
            last_run = cur.fetchone()
    except Exception as e:
        return {"tool": "qbot_wellness_db_status", "status": "ERROR",
                "safety_class": "READ_ONLY", "error": str(e)[:200]}

    if counts.get("qbot_wellness_daily", 0) == 0:
        issues.append("No wellness records imported yet")
    if counts.get("qbot_nutrition_daily", 0) == 0:
        issues.append("No nutrition records imported yet")

    return {
        "tool": "qbot_wellness_db_status",
        "status": "WARN" if issues else "OK",
        "safety_class": "READ_ONLY",
        "table_counts": counts,
        "last_import_run_date_from": last_run["date_from"].isoformat() if last_run and last_run.get("date_from") else None,
        "issues": issues,
        "notes": "DB OK, gotowe do importu." if not issues else "; ".join(issues),
    }


# ═══════════════════════════════════════════════════════════════════════════
# GARMIN IMPORTS
# ═══════════════════════════════════════════════════════════════════════════

def _garmin_fetch_wellness(date_str: str) -> dict[str, Any]:
    """Fetch Garmin wellness for a single day. Returns dict or error dict."""
    from garminconnect import Garmin as _G
    import json as _j

    garmin_email = os.getenv("GARMIN_EMAIL", "")
    garmin_pass = os.getenv("GARMIN_PASSWORD", "")
    if not garmin_email or not garmin_pass:
        return {"error": "MISSING_CREDENTIALS", "detail": "GARMIN_EMAIL/GARMIN_PASSWORD not set"}

    try:
        garmin_profile_path = "/opt/qbot/app/.garmin_profile.json"
        garmin_tokens_path = "/opt/qbot/app/.garmin_tokens"
        if not os.path.isfile(garmin_profile_path) or not os.path.exists(garmin_tokens_path):
            return {"error": "GARMIN_TOKENSTORE_MISSING", "detail": f"{garmin_profile_path} or {garmin_tokens_path} missing"}

        with open(garmin_profile_path) as f:
            profile = _j.load(f)
        g = _G(garmin_email, garmin_pass)
        g.client.load(garmin_tokens_path)
        g.display_name = profile["display_name"]

        result: dict[str, Any] = {"data": date_str}

        # Sleep
        try:
            sleep_raw = g.get_sleep_data(date_str)
            s = sleep_raw.get("dailySleepDTO", {})
            scores = s.get("sleepScores", {})
            result["sleep_duration_min"] = round(s.get("sleepTimeSeconds", 0) / 60)
            result["deep_sleep_min"] = round(s.get("deepSleepSeconds", 0) / 60)
            result["light_sleep_min"] = round(s.get("lightSleepSeconds", 0) / 60)
            result["rem_sleep_min"] = round(s.get("remSleepSeconds", 0) / 60)
            result["awake_min"] = round(s.get("awakeSleepSeconds", 0) / 60)
            result["sleep_score"] = scores.get("overall", {}).get("value")
            result["sleep_quality"] = scores.get("overall", {}).get("qualifierKey")
            result["spo2_avg"] = s.get("averageSpO2Value")
            sleep_start_ms = s.get("sleepStartTimestampGMT")
            sleep_end_ms = s.get("sleepEndTimestampGMT")
            if sleep_start_ms:
                try:
                    result["sleep_start"] = datetime.fromtimestamp(sleep_start_ms / 1000, tz=timezone.utc).isoformat()
                except Exception:
                    result["sleep_start"] = None
            if sleep_end_ms:
                try:
                    result["sleep_end"] = datetime.fromtimestamp(sleep_end_ms / 1000, tz=timezone.utc).isoformat()
                except Exception:
                    result["sleep_end"] = None
        except Exception:
            pass

        # Body Battery
        try:
            bb_raw = g.get_body_battery(date_str, date_str)
            if bb_raw:
                b = bb_raw[0]
                vals = [v[1] for v in b.get("bodyBatteryValuesArray", [])]
                result["body_battery_start"] = max(vals) if vals else None
                bb_end_raw = b.get("bodyBatteryDynamicFeedbackEvent", {}).get("bodyBatteryLevel")
                if isinstance(bb_end_raw, (int, float)):
                    result["body_battery_end"] = int(bb_end_raw)
                else:
                    result["body_battery_end_label"] = str(bb_end_raw) if bb_end_raw else None
        except Exception:
            pass

        # HRV
        try:
            hrv_raw = g.get_hrv_data(date_str)
            h = hrv_raw.get("hrvSummary", {})
            result["hrv_ms"] = h.get("lastNightAvg")
        except Exception:
            pass

        # Resting HR
        try:
            rhr_raw = g.get_rhr_day(date_str)
            rhr_val = (rhr_raw.get("allMetrics", {}).get("metricsMap", {})
                        .get("WELLNESS_RESTING_HEART_RATE", [{}])[0].get("value"))
            result["resting_hr_bpm"] = int(rhr_val) if rhr_val else None
        except Exception:
            pass

        return result
    except Exception as e:
        return {"error": str(e)[:200], "data": date_str}


def _garmin_import_wellness(date_from: str, date_to: str, dry_run: bool) -> dict[str, Any]:
    import_type = "wellness"
    source = "garmin"
    dates = _date_range(date_from, date_to)
    rows_seen, rows_ins, rows_upd = 0, 0, 0
    warnings: list[str] = []
    errors: list[str] = []
    raw_snapshots: list[dict] = []

    for d in dates:
        raw = _garmin_fetch_wellness(d)
        rows_seen += 1
        if "error" in raw:
            errors.append(f"{d}: {raw['error']}")
            continue
        raw_snapshots.append(raw)

        sleep_score = raw.get("sleep_score")
        # ensure sleep_score is int or None
        try:
            sleep_score = int(sleep_score) if sleep_score is not None else None
        except (ValueError, TypeError):
            sleep_score = None
        sleep_quality = raw.get("sleep_quality")
        hrv = raw.get("hrv_ms")
        rhr = raw.get("resting_hr_bpm")
        sleep_dur = raw.get("sleep_duration_min")
        bb_start = raw.get("body_battery_start")
        bb_end = raw.get("body_battery_end")

        has_wellness = any(v is not None for v in (sleep_dur, hrv, rhr, bb_start, bb_end))
        has_sleep_detail = any(v is not None for v in (raw.get("deep_sleep_min"), raw.get("rem_sleep_min"),
                                                         raw.get("light_sleep_min"), raw.get("awake_min"),
                                                         sleep_score))

        if not dry_run:
            with _db_conn() as conn, conn.cursor() as cur:
                if has_wellness:
                    cur.execute("""
                        INSERT INTO qbot_wellness_daily (date, source, source_priority, source_record_id,
                            sleep_duration_min, sleep_score, sleep_quality,
                            hrv_ms, resting_hr_bpm, body_battery_start, body_battery_end,
                            raw_json)
                        VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (date, source) DO UPDATE SET
                            sleep_duration_min = EXCLUDED.sleep_duration_min,
                            sleep_score = EXCLUDED.sleep_score,
                            sleep_quality = EXCLUDED.sleep_quality,
                            hrv_ms = EXCLUDED.hrv_ms,
                            resting_hr_bpm = EXCLUDED.resting_hr_bpm,
                            body_battery_start = EXCLUDED.body_battery_start,
                            body_battery_end = EXCLUDED.body_battery_end,
                            raw_json = EXCLUDED.raw_json,
                            imported_at = now()
                    """, (d, source, d, sleep_dur, sleep_score, sleep_quality,
                          hrv, rhr, bb_start, bb_end,
                          json.dumps(raw, ensure_ascii=False, default=str)))
                    rows_ins += 1

                if has_sleep_detail:
                    sleep_start_val = raw.get("sleep_start")
                    sleep_end_val = raw.get("sleep_end")
                    cur.execute("""
                        INSERT INTO qbot_sleep_daily (date, source,
                            sleep_start, sleep_end, sleep_duration_min,
                            deep_sleep_min, light_sleep_min, rem_sleep_min, awake_min,
                            sleep_score, hrv_ms, resting_hr_bpm, raw_json)
                        VALUES (%s, %s, %s::timestamptz, %s::timestamptz, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (date, source) DO UPDATE SET
                            sleep_start = EXCLUDED.sleep_start,
                            sleep_end = EXCLUDED.sleep_end,
                            sleep_duration_min = EXCLUDED.sleep_duration_min,
                            deep_sleep_min = EXCLUDED.deep_sleep_min,
                            light_sleep_min = EXCLUDED.light_sleep_min,
                            rem_sleep_min = EXCLUDED.rem_sleep_min,
                            awake_min = EXCLUDED.awake_min,
                            sleep_score = EXCLUDED.sleep_score,
                            hrv_ms = EXCLUDED.hrv_ms,
                            resting_hr_bpm = EXCLUDED.resting_hr_bpm,
                            raw_json = EXCLUDED.raw_json,
                            imported_at = now()
                    """, (d, source, sleep_start_val, sleep_end_val, sleep_dur,
                          raw.get("deep_sleep_min"), raw.get("light_sleep_min"),
                          raw.get("rem_sleep_min"), raw.get("awake_min"),
                          sleep_score, hrv, rhr,
                          json.dumps(raw, ensure_ascii=False, default=str)))
                    rows_ins += 1

    # Log import run
    status = "OK" if not errors else ("PARTIAL" if rows_ins > 0 else "ERROR")
    if not dry_run:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO qbot_import_runs (import_type, source, date_from, date_to, dry_run,
                    status, rows_seen, rows_inserted, rows_updated, warnings)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (import_type, source, date_from, date_to, dry_run,
                  status, rows_seen, rows_ins, rows_upd,
                  json.dumps(warnings + errors, ensure_ascii=False)))

    return {
        "import_type": import_type, "source": source, "date_from": date_from, "date_to": date_to,
        "dry_run": dry_run, "status": status, "dates_processed": len(dates),
        "rows_seen": rows_seen, "rows_inserted": rows_ins if not dry_run else 0,
        "rows_skipped_dry_run": rows_ins if dry_run else 0,
        "errors": errors[:10], "warnings": warnings[:10],
        "sample_dates": [r["data"] for r in raw_snapshots[:5] if "error" not in r],
    }


def _tool_qbot_garmin_wellness_import_preview(args: dict | None = None) -> dict[str, Any]:
    return _tool_qbot_garmin_wellness_import_execute({**(args or {}), "dry_run": True})


def _tool_qbot_garmin_wellness_import_execute(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    date_from = str(args.get("date_from", "2026-05-01"))
    date_to = str(args.get("date_to", _today_str()))
    dry_run = bool(args.get("dry_run", True))
    result = _garmin_import_wellness(date_from, date_to, dry_run)
    result["tool"] = "qbot_garmin_wellness_import_preview" if dry_run else "qbot_garmin_wellness_import_execute"
    result["safety_class"] = "READ_ONLY" if dry_run else "WRITE_SAFE"
    return result


def _tool_qbot_garmin_sleep_import_preview(args: dict | None = None) -> dict[str, Any]:
    return _tool_qbot_garmin_wellness_import_execute({**(args or {}), "dry_run": True})


def _tool_qbot_garmin_sleep_import_execute(args: dict | None = None) -> dict[str, Any]:
    return _tool_qbot_garmin_wellness_import_execute({**(args or {}), "dry_run": False})


# ═══════════════════════════════════════════════════════════════════════════
# INTERVALS IMPORTS
# ═══════════════════════════════════════════════════════════════════════════

def _intervals_api_get(endpoint: str, params: dict | None = None) -> tuple[int, Any]:
    """Call Intervals.icu API and return (status_code, data_or_error)."""
    api_key = os.getenv("INTERVALS_API_KEY", "")
    athlete_id = os.getenv("INTERVALS_ATHLETE_ID", "")
    if not api_key or not athlete_id:
        return 401, {"error": "MISSING_CREDENTIALS"}

    import httpx
    encoded = _b64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(
                f"https://intervals.icu/api/v1/athlete/{athlete_id}{endpoint}",
                headers={"Authorization": f"Basic {encoded}"},
                params=params,
            )
            if r.status_code == 401:
                return 401, {"error": "AUTH_ERROR"}
            r.raise_for_status()
            return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)[:200]}


def _intervals_import_wellness(date_from: str, date_to: str, dry_run: bool) -> dict[str, Any]:
    import_type = "wellness"
    source = "intervals"
    code, data = _intervals_api_get("/wellness", {"oldest": date_from, "newest": date_to})
    if code != 200:
        return {
            "import_type": import_type, "source": source, "date_from": date_from, "date_to": date_to,
            "dry_run": dry_run, "status": "API_ERROR" if code else "NETWORK_ERROR",
            "error": str(data.get("error", data))[:200],
        }

    records = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
    rows_seen, rows_ins = 0, 0
    sample_dates: list[str] = []

    for rec in records:
        if not isinstance(rec, dict):
            continue
        d = str(rec.get("id", ""))[:10]
        if not d:
            continue
        rows_seen += 1
        if len(sample_dates) < 5:
            sample_dates.append(d)

        weight = rec.get("weight")
        hrv = rec.get("hrv")
        rhr = rec.get("restingHR")
        sleep_secs = rec.get("sleepSecs")
        sleep_dur = round(sleep_secs / 60) if sleep_secs is not None else None
        feel = rec.get("feel")

        if not dry_run:
            with _db_conn() as conn, conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO qbot_wellness_daily (date, source, source_priority, source_record_id,
                        sleep_duration_min, hrv_ms, resting_hr_bpm, weight_kg,
                        subjective_feel, raw_json)
                    VALUES (%s, %s, 2, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (date, source) DO UPDATE SET
                        sleep_duration_min = COALESCE(EXCLUDED.sleep_duration_min, qbot_wellness_daily.sleep_duration_min),
                        hrv_ms = COALESCE(EXCLUDED.hrv_ms, qbot_wellness_daily.hrv_ms),
                        resting_hr_bpm = COALESCE(EXCLUDED.resting_hr_bpm, qbot_wellness_daily.resting_hr_bpm),
                        weight_kg = COALESCE(EXCLUDED.weight_kg, qbot_wellness_daily.weight_kg),
                        subjective_feel = COALESCE(EXCLUDED.subjective_feel, qbot_wellness_daily.subjective_feel),
                        raw_json = EXCLUDED.raw_json,
                        imported_at = now()
                """, (d, source, d, sleep_dur, hrv, rhr, weight,
                      str(feel)[:200] if feel else None,
                      json.dumps(rec, ensure_ascii=False, default=str)))
                rows_ins += 1

    status = "OK" if rows_seen > 0 else "NO_DATA"
    if not dry_run and rows_ins > 0:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO qbot_import_runs (import_type, source, date_from, date_to, dry_run,
                    status, rows_seen, rows_inserted, rows_updated, warnings)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s)
            """, (import_type, source, date_from, date_to, dry_run,
                  status, rows_seen, rows_ins if not dry_run else 0,
                  json.dumps([], ensure_ascii=False)))

    return {
        "import_type": import_type, "source": source, "date_from": date_from, "date_to": date_to,
        "dry_run": dry_run, "status": status, "rows_seen": rows_seen,
        "rows_inserted": rows_ins if not dry_run else 0,
        "rows_skipped_dry_run": rows_ins if dry_run else 0,
        "sample_dates": sample_dates,
    }


def _parse_comment_for_nutrition(comment_text: str) -> dict[str, Any] | None:
    """Try to extract nutrition data from Intervals comment text.

    Obsługuje pełny blok dziennego bilansu:
      🍽️ Zjedzone: 2126 kcal | B:140g W:198g T:81g
      🔥 Spalone: 3221 kcal (BMR:2287 + aktywne:934)
      ⚖️ Bilans: -1095 kcal
    """
    import re
    result: dict[str, Any] = {}
    try:
        # Full block: Zjedzone + B/W/T macros (priorytet)
        m = re.search(
            r'Zjedzone:\s*([\d.]+)\s*kcal\s*\|\s*'
            r'B:\s*([\d.]+)g\s+'
            r'W:\s*([\d.]+)g\s+'
            r'T:\s*([\d.]+)g',
            comment_text, re.I,
        )
        if m:
            result["calories_kcal"] = round(float(m.group(1)), 1)
            result["protein_g"] = round(float(m.group(2)), 1)
            result["carbs_g"] = round(float(m.group(3)), 1)
            result["fat_g"] = round(float(m.group(4)), 1)
        else:
            # Fallback: line-by-line for legacy format
            for line in comment_text.split("\n"):
                if "Zjedzone:" in line:
                    try:
                        result["calories_kcal"] = float(line.split("Zjedzone:")[1].split("kcal")[0].strip())
                    except Exception:
                        pass
                    if "B:" in line and "W:" in line and "T:" in line:
                        try:
                            b_part = line.split("B:")[1].split("W:")[0].replace("g", "").strip()
                            w_part = line.split("W:")[1].split("T:")[0].replace("g", "").strip()
                            t_part = line.split("T:")[1].replace("g", "").strip()
                            result["protein_g"] = float(b_part)
                            result["carbs_g"] = float(w_part)
                            result["fat_g"] = float(t_part)
                        except Exception:
                            pass

        # Spalone: (expenditure)
        m = re.search(r'Spalone:\s*([\d.]+)\s*kcal', comment_text, re.I)
        if m:
            result["calories_burned_kcal"] = round(float(m.group(1)), 1)

        m = re.search(r'BMR:\s*([\d.]+)', comment_text)
        if m:
            result["bmr_kcal"] = round(float(m.group(1)), 1)

        m = re.search(r'aktywne:\s*([\d.]+)', comment_text)
        if m:
            result["active_kcal"] = round(float(m.group(1)), 1)

        # Bilans:
        m = re.search(r'Bilans:\s*(-?[\d.]+)\s*kcal', comment_text)
        if m:
            result["balance_kcal"] = round(float(m.group(1)), 1)

    except Exception:
        return None
    return result if result else None


def _intervals_import_comments(date_from: str, date_to: str, dry_run: bool) -> dict[str, Any]:
    import_type = "comments"
    source = "intervals_comment"
    code, data = _intervals_api_get("/wellness", {"oldest": date_from, "newest": date_to})
    if code != 200:
        return {
            "import_type": import_type, "source": source, "date_from": date_from, "date_to": date_to,
            "dry_run": dry_run, "status": "API_ERROR" if code else "NETWORK_ERROR",
            "error": str(data.get("error", data))[:200],
        }

    records = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
    rows_seen, rows_ins, nutrition_ins = 0, 0, 0
    sample: list[str] = []

    for rec in records:
        if not isinstance(rec, dict):
            continue
        d = str(rec.get("id", ""))[:10]
        if not d:
            continue
        comments = rec.get("comments", "")
        if not comments or not isinstance(comments, str):
            continue
        rows_seen += 1

        if len(sample) < 3:
            sample.append(f"{d}: {comments[:150]}...")

    if not dry_run and rows_seen > 0:
        conn = _db_conn()
        cur = conn.cursor()
        try:
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                d = str(rec.get("id", ""))[:10]
                if not d:
                    continue
                comments = rec.get("comments", "")
                if not comments or not isinstance(comments, str):
                    continue

                cur.execute("""
                    INSERT INTO qbot_wellness_notes (date, source, note_type, text, source_record_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (date, source, note_type, text) DO NOTHING
                """, (d, source, "intervals_comment", comments, d))
                rows_ins += cur.rowcount

                nutrition = _parse_comment_for_nutrition(comments)
                if nutrition and "calories_kcal" in nutrition:
                    cur.execute("""
                        INSERT INTO qbot_nutrition_daily (date, source, calories_kcal,
                            carbs_g, protein_g, fat_g, raw_text, raw_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (date, source) DO UPDATE SET
                            calories_kcal = EXCLUDED.calories_kcal,
                            carbs_g = EXCLUDED.carbs_g,
                            protein_g = EXCLUDED.protein_g,
                            fat_g = EXCLUDED.fat_g,
                            raw_text = EXCLUDED.raw_text,
                            raw_json = EXCLUDED.raw_json,
                            imported_at = now()
                    """, (d, "intervals_comment_mfp",
                          nutrition.get("calories_kcal"),
                          nutrition.get("carbs_g"),
                          nutrition.get("protein_g"),
                          nutrition.get("fat_g"),
                          comments,
                          json.dumps(nutrition, ensure_ascii=False, default=str)))
                    nutrition_ins += cur.rowcount

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    status = "OK" if rows_seen > 0 else "NO_COMMENTS_FOUND"
    if not dry_run and rows_ins > 0:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO qbot_import_runs (import_type, source, date_from, date_to, dry_run,
                    status, rows_seen, rows_inserted, rows_updated, warnings)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s)
            """, (import_type, source, date_from, date_to, dry_run,
                  status, rows_seen, rows_ins if not dry_run else 0,
                  json.dumps([], ensure_ascii=False)))

    return {
        "import_type": import_type, "source": source, "date_from": date_from, "date_to": date_to,
        "dry_run": dry_run, "status": status, "rows_seen": rows_seen,
        "rows_inserted": rows_ins if not dry_run else 0,
        "nutrition_rows": nutrition_ins if not dry_run else 0,
        "rows_skipped_dry_run": rows_ins if dry_run else 0,
        "sample": sample[:3],
    }


def _tool_qbot_intervals_wellness_import_preview(args: dict | None = None) -> dict[str, Any]:
    return _tool_qbot_intervals_wellness_import_execute({**(args or {}), "dry_run": True})


def _tool_qbot_intervals_wellness_import_execute(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    date_from = str(args.get("date_from", "2026-05-01"))
    date_to = str(args.get("date_to", _today_str()))
    dry_run = bool(args.get("dry_run", True))
    result = _intervals_import_wellness(date_from, date_to, dry_run)
    result["tool"] = "qbot_intervals_wellness_import_preview" if dry_run else "qbot_intervals_wellness_import_execute"
    result["safety_class"] = "READ_ONLY" if dry_run else "WRITE_SAFE"
    return result


def _tool_qbot_intervals_comments_import_preview(args: dict | None = None) -> dict[str, Any]:
    return _tool_qbot_intervals_comments_import_execute({**(args or {}), "dry_run": True})


def _tool_qbot_intervals_comments_import_execute(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    date_from = str(args.get("date_from", "2026-05-01"))
    date_to = str(args.get("date_to", _today_str()))
    dry_run = bool(args.get("dry_run", True))
    result = _intervals_import_comments(date_from, date_to, dry_run)
    result["tool"] = "qbot_intervals_comments_import_preview" if dry_run else "qbot_intervals_comments_import_execute"
    result["safety_class"] = "READ_ONLY" if dry_run else "WRITE_SAFE"
    return result


# ═══════════════════════════════════════════════════════════════════════════
# CRONOMETER
# ═══════════════════════════════════════════════════════════════════════════

def _cronometer_import(date_from: str, date_to: str, dry_run: bool) -> dict[str, Any]:
    import_type = "nutrition"
    source = "cronometer"
    crono_email = os.getenv("CRONOMETER_EMAIL", "")
    crono_pass = os.getenv("CRONOMETER_PASSWORD", "")
    if not crono_email or not crono_pass:
        return {
            "import_type": import_type, "source": source, "date_from": date_from, "date_to": date_to,
            "dry_run": dry_run, "status": "BLOCKED_BY_SECRET",
            "error": "CRONOMETER_EMAIL/CRONOMETER_PASSWORD not set",
        }

    try:
        os.environ['CRONOMETER_USERNAME'] = crono_email
        os.environ['CRONOMETER_PASSWORD'] = crono_pass
        from cronometer_mcp import CronometerClient
        c = CronometerClient()
        c.authenticate()
    except Exception as e:
        return {
            "import_type": import_type, "source": source, "date_from": date_from, "date_to": date_to,
            "dry_run": dry_run, "status": "AUTH_ERROR",
            "error": f"Cronometer auth failed: {str(e)[:200]}",
        }

    try:
        df = date.fromisoformat(date_from)
        dt_val = date.fromisoformat(date_to)
        rows = c.get_daily_summary(df, dt_val)
        if not rows:
            return {
                "import_type": import_type, "source": source, "date_from": date_from, "date_to": date_to,
                "dry_run": dry_run, "status": "NO_DATA",
            }

        rows_seen, rows_ins = 0, 0
        for row in rows:
            d = str(row.get("date", ""))[:10] or _today_str()
            rows_seen += 1
            if not dry_run:
                with _db_conn() as conn, conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO qbot_nutrition_daily (date, source, calories_kcal,
                            carbs_g, protein_g, fat_g, fiber_g, sugar_g, sodium_mg, fluid_ml,
                            raw_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (date, source) DO UPDATE SET
                            calories_kcal = EXCLUDED.calories_kcal,
                            carbs_g = EXCLUDED.carbs_g,
                            protein_g = EXCLUDED.protein_g,
                            fat_g = EXCLUDED.fat_g,
                            fiber_g = EXCLUDED.fiber_g,
                            sugar_g = EXCLUDED.sugar_g,
                            sodium_mg = EXCLUDED.sodium_mg,
                            fluid_ml = EXCLUDED.fluid_ml,
                            raw_json = EXCLUDED.raw_json,
                            imported_at = now()
                    """, (d, source,
                          float(row.get("Energy (kcal)", 0) or 0),
                          float(row.get("Carbs (g)", 0) or 0),
                          float(row.get("Protein (g)", 0) or 0),
                          float(row.get("Fat (g)", 0) or 0),
                          float(row.get("Fiber (g)", 0) or 0),
                          float(row.get("Sugars (g)", 0) or 0),
                          float(row.get("Sodium (mg)", 0) or 0),
                          float(row.get("Water (ml)", 0) or 0),
                          json.dumps(row, ensure_ascii=False, default=str)))
                    rows_ins += cur.rowcount

        status = "OK" if rows_ins > 0 else "NO_NEW_DATA"
        if not dry_run and rows_ins > 0:
            with _db_conn() as conn, conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO qbot_import_runs (import_type, source, date_from, date_to, dry_run,
                        status, rows_seen, rows_inserted, rows_updated, warnings)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s)
                """, (import_type, source, date_from, date_to, dry_run,
                      status, rows_seen, rows_ins, json.dumps([], ensure_ascii=False)))

        return {
            "import_type": import_type, "source": source, "date_from": date_from, "date_to": date_to,
            "dry_run": dry_run, "status": status, "rows_seen": rows_seen,
            "rows_inserted": rows_ins if not dry_run else 0,
            "rows_skipped_dry_run": rows_ins if dry_run else 0,
        }
    except Exception as e:
        return {
            "import_type": import_type, "source": source, "date_from": date_from, "date_to": date_to,
            "dry_run": dry_run, "status": "API_ERROR",
            "error": str(e)[:200],
        }


def _tool_qbot_cronometer_nutrition_import_preview(args: dict | None = None) -> dict[str, Any]:
    return _tool_qbot_cronometer_nutrition_import_execute({**(args or {}), "dry_run": True})


def _tool_qbot_cronometer_nutrition_import_execute(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    date_from = str(args.get("date_from", "2026-05-01"))
    date_to = str(args.get("date_to", _today_str()))
    dry_run = bool(args.get("dry_run", True))
    result = _cronometer_import(date_from, date_to, dry_run)
    result["tool"] = "qbot_cronometer_nutrition_import_preview" if dry_run else "qbot_cronometer_nutrition_import_execute"
    result["safety_class"] = "READ_ONLY" if dry_run else "WRITE_SAFE"
    return result


# ═══════════════════════════════════════════════════════════════════════════
# DB QUERY TOOLS
# ═══════════════════════════════════════════════════════════════════════════

def _date_range(start: str, end: str) -> list[str]:
    """Generate list of ISO date strings from start to end inclusive."""
    d_start = date.fromisoformat(start)
    d_end = date.fromisoformat(end)
    dates: list[str] = []
    cur = d_start
    while cur <= d_end:
        dates.append(cur.isoformat())
        cur += timedelta(days=1)
    return dates


def _tool_qbot_wellness_day_get(args: dict | None = None) -> dict[str, Any]:
    d = str((args or {}).get("date", _today_str()))[:10]
    data: dict[str, Any] = {}
    sources_available: list[str] = []

    try:
        with _db_conn() as conn, conn.cursor() as cur:
            # 1. Try qbot_v2.wellness_daily (HRV, RHR, body battery, stress, weight)
            cur.execute("SELECT * FROM qbot_v2.wellness_daily WHERE date = %s", (d,))
            wrows = cur.fetchall()
            if wrows:
                sources_available.append(f"wellness/{wrows[0]['source']}")
                for k, v in wrows[0].items():
                    if k not in ("id", "quality_status", "imported_at"):
                        data[k] = _serialize_val(v)

            # 2. Try qbot_v2.energy_daily (kcal, steps)
            cur.execute("SELECT * FROM qbot_v2.energy_daily WHERE date = %s", (d,))
            erows = cur.fetchall()
            if erows:
                sources_available.append(f"energy/{erows[0]['source']}")
                data["total_kcal"] = _serialize_val(erows[0].get("total_kcal"))
                data["active_kcal"] = _serialize_val(erows[0].get("active_kcal"))
                data["resting_kcal"] = _serialize_val(erows[0].get("resting_kcal"))
                data["steps"] = _serialize_val(erows[0].get("steps"))

            # 2b. Try qbot_v2.body_measurements (Garmin canonical)
            try:
                cur.execute(
                    """SELECT weight_kg, bmi, body_fat_pct, body_water_pct,
                              muscle_mass_kg, bone_mass_kg,
                              source_system, source_type, quality_status
                       FROM qbot_v2.body_measurements WHERE date = %s
                       ORDER BY completeness_score DESC, imported_at DESC
                       LIMIT 1""", (d,))
                bm = cur.fetchone()
                if bm and bm.get("weight_kg") is not None:
                    data["weight_kg"] = _serialize_val(bm.get("weight_kg"))
                    data["body_fat_pct"] = _serialize_val(bm.get("body_fat_pct"))
                    data["bmi"] = _serialize_val(bm.get("bmi"))
                    data["muscle_mass_kg"] = _serialize_val(bm.get("muscle_mass_kg"))
                    data["bone_mass_kg"] = _serialize_val(bm.get("bone_mass_kg"))
                    data["body_water_pct"] = _serialize_val(bm.get("body_water_pct"))
                    data["weight_source"] = f"body_measurements/{bm.get('source_type','?')}"
            except Exception:
                conn.rollback()
            # Fallback: legacy body_daily
            if data.get("weight_kg") is None:
                try:
                    cur.execute(
                        """SELECT * FROM qbot_v2.body_daily WHERE date = %s
                           ORDER BY CASE source
                               WHEN 'garmin_index_scale' THEN 1
                               WHEN 'garmin_mfp' THEN 2
                               ELSE 3
                           END, imported_at DESC
                           LIMIT 1""", (d,))
                    bd = cur.fetchone()
                    if bd:
                        data["weight_kg"] = _serialize_val(bd.get("weight_kg"))
                        data["body_fat_pct"] = _serialize_val(bd.get("body_fat_pct"))
                        data["bmi"] = _serialize_val(bd.get("bmi"))
                        data["muscle_mass_kg"] = _serialize_val(bd.get("muscle_mass_kg"))
                        data["bone_mass_kg"] = _serialize_val(bd.get("bone_mass_kg"))
                        data["body_water_pct"] = _serialize_val(bd.get("body_water_pct"))
                        data["visceral_fat"] = _serialize_val(bd.get("visceral_fat"))
                        data["weight_source"] = f"body_daily/{bd.get('source','?')} (legacy)"
                except Exception:
                    conn.rollback()
            if data.get("weight_kg") is None:
                # Legacy fallback: public tables
                for wt_tbl, wt_col in [("public.weight_history", "weight_kg"),
                                        ("public.body_composition", "weight_kg")]:
                    try:
                        cur.execute(f"SELECT {wt_col} FROM {wt_tbl} WHERE date = %s ORDER BY created_at DESC LIMIT 1", (d,))
                        wr = cur.fetchone()
                        if wr and wr.get(wt_col) is not None:
                            data["weight_kg"] = _serialize_val(wr[wt_col])
                            data["weight_source"] = wt_tbl.split(".")[-1].replace("_", "/")
                            break
                    except Exception:
                        conn.rollback()
                        continue
            if data.get("weight_kg") is None and "weight_source" not in data:
                data["weight_status"] = "NO_RECORD_FOR_DATE"

            # 3. Try qbot_v2.sleep_daily (sleep duration, score)
            cur.execute("SELECT * FROM qbot_v2.sleep_daily WHERE date = %s", (d,))
            srows = cur.fetchall()
            if srows:
                sources_available.append(f"sleep/{srows[0]['source']}")
                data["sleep_duration_min"] = _serialize_val(srows[0].get("duration_min"))
                data["sleep_score"] = _serialize_val(srows[0].get("score"))
                data["deep_min"] = _serialize_val(srows[0].get("deep_min"))
                data["light_min"] = _serialize_val(srows[0].get("light_min"))
                data["rem_min"] = _serialize_val(srows[0].get("rem_min"))
                data["awake_min"] = _serialize_val(srows[0].get("awake_min"))
                data["sleep_start"] = _serialize_val(srows[0].get("sleep_start"))
                data["sleep_end"] = _serialize_val(srows[0].get("sleep_end"))
                if data.get("hrv_ms") is None:
                    data["hrv_ms"] = _serialize_val(srows[0].get("hrv_ms"))
                if data.get("resting_hr_bpm") is None:
                    data["resting_hr_bpm"] = _serialize_val(srows[0].get("resting_hr_bpm"))
    except Exception as e:
        return {"tool": "qbot_wellness_day_get", "status": "ERROR", "date": d,
                "safety_class": "READ_ONLY", "error": str(e)[:200]}

    # Fallback to old public.qbot_wellness_daily if qbot_v2 had nothing
    if not data:
        try:
            with _db_conn() as conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM qbot_wellness_daily WHERE date = %s ORDER BY source_priority", (d,))
                rows = cur.fetchall()
                if rows:
                    sources_available.append(rows[0]["source"])
                    data = {k: _serialize_val(v) for k, v in rows[0].items() if k not in ("raw_json", "id")}
        except Exception:
            pass

    if not data:
        return {"tool": "qbot_wellness_day_get", "status": "NO_DATA", "date": d,
                "safety_class": "READ_ONLY", "sources_available": [],
                "data": None, "missing_fields": ["all"], "raw_sources_available": False,
                "reason": "Brak danych wellness w DB dla tej daty."}

    missing = [k for k in ("sleep_duration_min", "sleep_score", "hrv_ms", "resting_hr_bpm",
                            "body_battery_start", "weight_kg") if data.get(k) is None]

    return {"tool": "qbot_wellness_day_get", "status": "OK", "date": d,
            "safety_class": "READ_ONLY", "sources_available": sources_available,
            "data": data, "missing_fields": missing, "raw_sources_available": len(sources_available) > 0}


def _tool_qbot_sleep_day_get(args: dict | None = None) -> dict[str, Any]:
    d = str((args or {}).get("date", _today_str()))[:10]
    data: dict[str, Any] = {}
    source_name = None

    try:
        with _db_conn() as conn, conn.cursor() as cur:
            # Try qbot_v2.sleep_daily first
            cur.execute("SELECT * FROM qbot_v2.sleep_daily WHERE date = %s", (d,))
            rows = cur.fetchall()
            if rows:
                source_name = rows[0].get("source", "garmin_live")
                r = rows[0]
                data = {
                    "sleep_duration_min": _serialize_val(r.get("duration_min")),
                    "sleep_score": _serialize_val(r.get("score")),
                    "deep_sleep_min": _serialize_val(r.get("deep_min")),
                    "light_sleep_min": _serialize_val(r.get("light_min")),
                    "rem_sleep_min": _serialize_val(r.get("rem_min")),
                    "awake_min": _serialize_val(r.get("awake_min")),
                    "hrv_ms": _serialize_val(r.get("hrv_ms")),
                    "resting_hr_bpm": _serialize_val(r.get("resting_hr_bpm")),
                    "sleep_start": _serialize_val(r.get("sleep_start")),
                    "sleep_end": _serialize_val(r.get("sleep_end")),
                    "source": source_name,
                }
    except Exception as e:
        return {"tool": "qbot_sleep_day_get", "status": "ERROR", "date": d,
                "safety_class": "READ_ONLY", "error": str(e)[:200]}

    # Fallback to old public.qbot_sleep_daily if qbot_v2 had nothing
    if not data:
        try:
            with _db_conn() as conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM qbot_sleep_daily WHERE date = %s ORDER BY source", (d,))
                rows = cur.fetchall()
                if rows:
                    source_name = rows[0].get("source")
                    r = rows[0]
                    data = {k: _serialize_val(v) for k, v in r.items() if k not in ("raw_json", "id")}
        except Exception:
            pass

    if not data:
        return {"tool": "qbot_sleep_day_get", "status": "NO_DATA", "date": d,
                "safety_class": "READ_ONLY", "data": None, "reason": "Brak danych snu w DB."}

    missing = [k for k in ("sleep_duration_min", "sleep_score", "deep_sleep_min", "rem_sleep_min",
                            "light_sleep_min", "awake_min") if data.get(k) is None]
    return {"tool": "qbot_sleep_day_get", "status": "OK", "date": d,
            "safety_class": "READ_ONLY", "sources_available": [source_name or "garmin_live"],
            "data": data, "missing_fields": missing, "raw_sources_available": True}


def _tool_qbot_nutrition_day_get(args: dict | None = None) -> dict[str, Any]:
    d = str((args or {}).get("date", _today_str()))[:10]
    rows = []
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM qbot_nutrition_daily WHERE date = %s ORDER BY source", (d,))
            rows = cur.fetchall()
    except Exception as e:
        return {"tool": "qbot_nutrition_day_get", "status": "ERROR", "date": d,
                "safety_class": "READ_ONLY", "error": str(e)[:200]}

    if not rows:
        return {"tool": "qbot_nutrition_day_get", "status": "NO_DATA", "date": d,
                "safety_class": "READ_ONLY", "data": None, "reason": "Brak danych żywieniowych w DB."}

    results = []
    for r in rows:
        results.append({k: _serialize_val(v) for k, v in r.items() if k not in ("raw_json", "raw_text", "id")})
    return {"tool": "qbot_nutrition_day_get", "status": "OK", "date": d,
            "safety_class": "READ_ONLY", "entries": results,
            "sources_available": [r["source"] for r in results],
            "raw_sources_available": len(results) > 0}


def _tool_qbot_wellness_range_summary(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    date_from = str(args.get("date_from", _today_str()))[:10]
    date_to = str(args.get("date_to", _today_str()))[:10]
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT source, COUNT(*) as days,
                       AVG(hrv_ms) as avg_hrv, AVG(resting_hr_bpm) as avg_rhr,
                       AVG(sleep_duration_min) as avg_sleep_min,
                       MIN(sleep_duration_min) as min_sleep, MAX(sleep_duration_min) as max_sleep
                FROM qbot_wellness_daily
                WHERE date >= %s AND date <= %s
                GROUP BY source ORDER BY source
            """, (date_from, date_to))
            summary = cur.fetchall()
    except Exception as e:
        return {"tool": "qbot_wellness_range_summary", "status": "ERROR",
                "safety_class": "READ_ONLY", "error": str(e)[:200]}

    return {"tool": "qbot_wellness_range_summary", "status": "OK",
            "safety_class": "READ_ONLY", "date_from": date_from, "date_to": date_to,
            "summary": [{k: _serialize_val(v) for k, v in row.items()} for row in summary],
            "days_in_range": (date.fromisoformat(date_to) - date.fromisoformat(date_from)).days + 1}


def _tool_qbot_nutrition_range_summary(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    date_from = str(args.get("date_from", _today_str()))[:10]
    date_to = str(args.get("date_to", _today_str()))[:10]
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT source, COUNT(*) as days,
                       AVG(calories_kcal) as avg_kcal,
                       SUM(calories_kcal) as total_kcal,
                       AVG(carbs_g) as avg_carbs, AVG(protein_g) as avg_protein, AVG(fat_g) as avg_fat
                FROM qbot_nutrition_daily
                WHERE date >= %s AND date <= %s
                GROUP BY source ORDER BY source
            """, (date_from, date_to))
            summary = cur.fetchall()
    except Exception as e:
        return {"tool": "qbot_nutrition_range_summary", "status": "ERROR",
                "safety_class": "READ_ONLY", "error": str(e)[:200]}

    return {"tool": "qbot_nutrition_range_summary", "status": "OK",
            "safety_class": "READ_ONLY", "date_from": date_from, "date_to": date_to,
            "summary": [{k: _serialize_val(v) for k, v in row.items()} for row in summary]}


def _tool_qbot_nutrition_db_status(args: dict | None = None) -> dict[str, Any]:
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT source, COUNT(*) as cnt FROM qbot_nutrition_daily GROUP BY source ORDER BY source")
            rows = cur.fetchall()
            cur.execute("SELECT MIN(date) as earliest, MAX(date) as latest FROM qbot_nutrition_daily")
            range_r = cur.fetchone()
    except Exception as e:
        return {"tool": "qbot_nutrition_db_status", "status": "ERROR",
                "safety_class": "READ_ONLY", "error": str(e)[:200]}

    return {"tool": "qbot_nutrition_db_status", "status": "OK",
            "safety_class": "READ_ONLY",
            "sources": {r["source"]: r["cnt"] for r in rows},
            "date_range": {"from": str(range_r["earliest"]) if range_r and range_r.get("earliest") else None,
                           "to": str(range_r["latest"]) if range_r and range_r.get("latest") else None}}


def _serialize_val(v: Any) -> Any:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, timedelta):
        return str(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v
