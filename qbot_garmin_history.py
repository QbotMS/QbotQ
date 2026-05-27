#!/usr/bin/env python3
"""Garmin history reader — weight, body composition, training sessions.

Read-only data fetcher for import pipeline. Does NOT write to DB.
Used by calendar_core import-history and snapshot builder.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from typing import Any


def _garmin_client():
    from garminconnect import Garmin
    email = os.getenv("GARMIN_EMAIL", "").strip()
    password = os.getenv("GARMIN_PASSWORD", "").strip()
    tokenstore = os.getenv("GARMIN_TOKENSTORE", "/opt/qbot/app/.garmin_tokens")
    g = Garmin(email, password)
    g.login(tokenstore=tokenstore)
    return g


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def read_weight_history(start_date: str, end_date: str) -> list[dict]:
    """Fetch Garmin weight history. Returns list of weight entries (kg)."""
    try:
        g = _garmin_client()
        raw = g.get_body_composition(start_date, end_date)
        results = []
        entries = raw.get("dateWeightList", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])

        for entry in entries:
            d = entry.get("calendarDate") or entry.get("date")
            if isinstance(d, str) and len(d) >= 10:
                d = d[:10]
            else:
                continue
            w = _safe_float(entry.get("weight"))
            if w is None:
                continue
            # Garmin returns weight in grams — convert to kg
            weight_kg = w / 1000.0 if w > 500 else w
            if weight_kg < 20 or weight_kg > 300:
                continue

            results.append({
                "date": d,
                "weight_kg": round(weight_kg, 1),
                "source": "garmin",
                "external_id": str(entry.get("samplePk", d)),
                "raw_json": entry,
            })
        return results
    except Exception as e:
        return [{"error": str(e)[:200]}]


def read_body_composition(start_date: str, end_date: str) -> list[dict]:
    """Fetch body composition: BMI, body fat, lean mass, water, bone."""
    try:
        g = _garmin_client()
        raw = g.get_body_composition(start_date, end_date)
        results = []
        entries = raw.get("dateWeightList", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        for entry in entries:
            d = entry.get("calendarDate") or entry.get("date")
            if isinstance(d, str) and len(d) >= 10:
                d = d[:10]
            else:
                continue

            w = _safe_float(entry.get("weight"))
            weight_kg = w / 1000.0 if (w and w > 500) else (w or 0)
            if weight_kg < 20:
                continue

            bmi = _safe_float(entry.get("bmi"))
            bf = _safe_float(entry.get("bodyFat"))
            bw = _safe_float(entry.get("bodyWater"))
            bm = _safe_float(entry.get("boneMass"))
            mm = _safe_float(entry.get("muscleMass"))

            # Only include if there's body composition data beyond weight
            if bmi or bf or bw or bm or mm:
                results.append({
                    "date": d, "weight_kg": round(weight_kg, 1),
                    "body_fat_pct": bf, "bmi": bmi,
                    "body_water_pct": bw, "bone_mass_kg": bm,
                    "muscle_mass_kg": mm, "lean_mass_kg": None,
                    "source": f"garmin_{entry.get('sourceType', '').lower()}",
                    "external_id": str(entry.get("samplePk", d)),
                    "raw_json": entry,
                })
        return results
    except Exception as e:
        return [{"error": str(e)[:200]}]


def read_training_sessions(start_date: str, end_date: str) -> list[dict]:
    """Fetch Garmin activities/training sessions for date range."""
    try:
        g = _garmin_client()
        activities = g.get_activities_by_date(start_date, end_date)
        if not isinstance(activities, list):
            return []

        results = []
        for a in activities:
            d = a.get("startTimeLocal") or a.get("startTimeGMT")
            if isinstance(d, str) and len(d) >= 10:
                d = d[:10]
            else:
                continue

            results.append({
                "date": d,
                "started_at": a.get("startTimeLocal") or a.get("startTimeGMT"),
                "ended_at": a.get("endTimeLocal") or a.get("endTimeGMT"),
                "source": "garmin",
                "external_id": str(a.get("activityId", "")),
                "activity_type": a.get("activityType", {}).get("typeKey", "") if isinstance(a.get("activityType"), dict) else "",
                "title": a.get("activityName", ""),
                "duration_sec": _safe_float(a.get("movingDuration")),
                "elapsed_duration_sec": _safe_float(a.get("elapsedDuration")),
                "distance_km": (_safe_float(a.get("distance")) / 1000.0) if a.get("distance") else None,
                "elevation_gain_m": _safe_float(a.get("elevationGain")),
                "calories_kcal": _safe_float(a.get("calories")),
                "avg_hr": int(a["averageHR"]) if a.get("averageHR") else None,
                "max_hr": int(a["maxHR"]) if a.get("maxHR") else None,
                "avg_power_w": _safe_float(a.get("averagePower")),
                "max_power_w": _safe_float(a.get("maxPower")),
                "training_load": _safe_float(a.get("activityTrainingLoad")),
                "training_effect": _safe_float(a.get("aerobicTrainingEffect")),
                "anaerobic_training_effect": _safe_float(a.get("anaerobicTrainingEffect")),
                "route_ref": f"garmin://{a.get('activityId','')}",
                "raw_json": a,
            })
        return results
    except Exception as e:
        return [{"error": str(e)[:200]}]


def read_intervals_comments(start_date: str, end_date: str) -> list[dict]:
    """Read nutrition data from Intervals wellness comments."""
    import re
    import psycopg
    from psycopg.rows import dict_row

    try:
        conn = psycopg.connect(
            host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT date, text FROM qbot_wellness_notes WHERE source='intervals_comment' AND date BETWEEN %s AND %s ORDER BY date",
            (start_date, end_date),
        )
        rows = cur.fetchall()
        conn.close()

        results = []
        for r in rows:
            d = str(r["date"])[:10]
            text = r["text"]
            parsed: dict[str, Any] = {"date": d, "raw_comment": text[:300]}

            m = re.search(r'Zjedzone:\s*([\d.]+)\s*kcal', text)
            if m: parsed["calories_kcal"] = float(m.group(1))
            m = re.search(r'B:\s*([\d.]+)\s*g', text)
            if m: parsed["protein_g"] = float(m.group(1))
            m = re.search(r'W:\s*([\d.]+)\s*g', text)
            if m: parsed["carbs_g"] = float(m.group(1))
            m = re.search(r'T:\s*([\d.]+)\s*g', text)
            if m: parsed["fat_g"] = float(m.group(1))
            m = re.search(r'Spalone:\s*([\d.]+)\s*kcal', text)
            if m: parsed["calories_burned"] = float(m.group(1))
            m = re.search(r'BMR:\s*([\d.]+)', text)
            if m: parsed["bmr_kcal"] = float(m.group(1))
            m = re.search(r'aktywne:\s*([\d.]+)', text)
            if m: parsed["active_kcal"] = float(m.group(1))

            has_nutrition = parsed.get("calories_kcal") and parsed.get("protein_g")
            parsed["confidence"] = "high" if has_nutrition else "medium"
            parsed["manual_review_required"] = not has_nutrition
            results.append(parsed)

        return results
    except Exception as e:
        return [{"error": str(e)[:200]}]
