#!/usr/bin/env python3
"""Garmin history reader — weight, body composition, training sessions.

Read-only data fetcher for import pipeline. Does NOT write to DB.
Used by calendar_core import-history and snapshot builder.
"""

from __future__ import annotations

import json
import os
import csv
import io
import zipfile
from xml.sax.saxutils import escape as _xml_escape
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


def _normalize_activity_id(activity_id: str) -> str:
    text = str(activity_id or "").strip()
    if text.startswith("garmin://"):
        text = text.split("://", 1)[1].strip()
    return text


def _coerce_series_values(value: Any) -> list[float] | list[int] | list[float | int]:
    if not isinstance(value, list):
        return []
    out: list[float | int] = []
    for item in value:
        candidate: Any = item
        if isinstance(item, dict):
            for key in (
                "value",
                "values",
                "data",
                "point",
                "points",
                "sample",
                "samples",
                "y",
                "x",
                "heart_rate",
                "power",
                "altitude",
                "cadence",
                "distance",
                "time",
            ):
                if item.get(key) is not None:
                    candidate = item.get(key)
                    break
            else:
                continue
        if isinstance(candidate, bool):
            continue
        if isinstance(candidate, int):
            out.append(candidate)
            continue
        if isinstance(candidate, float):
            out.append(candidate)
            continue
        num = _safe_float(candidate)
        if num is None:
            continue
        out.append(int(num) if float(num).is_integer() else num)
    return out


def _find_series(payload: Any, aliases: tuple[str, ...]) -> list[float] | list[int] | list[float | int]:
    if isinstance(payload, dict):
        for alias in aliases:
            if alias in payload:
                series = _coerce_series_values(payload.get(alias))
                if series:
                    return series
                nested = payload.get(alias)
                if isinstance(nested, dict):
                    for nested_key in ("values", "data", "points", "samples", "series", "stream", "items"):
                        series = _coerce_series_values(nested.get(nested_key))
                        if series:
                            return series
        for value in payload.values():
            if isinstance(value, (dict, list)):
                series = _find_series(value, aliases)
                if series:
                    return series
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                label = " ".join(
                    str(item.get(key, "")).lower()
                    for key in ("name", "type", "streamType", "fieldName", "measurement", "label")
                )
                if any(alias.lower() in label for alias in aliases):
                    for nested_key in ("values", "data", "points", "samples", "series", "stream"):
                        series = _coerce_series_values(item.get(nested_key))
                        if series:
                            return series
            if isinstance(item, (dict, list)):
                series = _find_series(item, aliases)
                if series:
                    return series
    return []


def _fit_streams_from_download(g, activity_id: str) -> dict[str, list[Any]]:
    from fitparse import FitFile

    blob = g.download_activity(activity_id, dl_fmt=g.ActivityDownloadFormat.ORIGINAL)
    fit_raw = blob
    if isinstance(blob, (bytes, bytearray)) and blob[:2] == b"PK":
        zf = zipfile.ZipFile(io.BytesIO(blob))
        names = zf.namelist()
        if not names:
            return {}
        fit_raw = zf.read(names[0])

    fit = FitFile(io.BytesIO(fit_raw))
    streams: dict[str, list[Any]] = {
        "time": [],
        "distance": [],
        "heart_rate": [],
        "power": [],
        "altitude": [],
        "cadence": [],
    }
    first_ts = None
    last_distance = None
    for msg in fit.get_messages("record"):
        ts = None
        row: dict[str, Any] = {}
        for field in msg:
            name = field.name
            value = field.value
            if value is None:
                continue
            if name == "timestamp":
                ts = value
            elif name == "distance":
                row["distance"] = _safe_float(value)
            elif name == "heart_rate":
                row["heart_rate"] = int(value)
            elif name == "power":
                row["power"] = int(value)
            elif name == "altitude":
                row["altitude"] = _safe_float(value)
            elif name == "cadence":
                row["cadence"] = int(value)
        if ts is None:
            continue
        if first_ts is None:
            first_ts = ts
        streams["time"].append(int((ts - first_ts).total_seconds()))
        last_distance = row.get("distance", last_distance)
        streams["distance"].append(row.get("distance", last_distance))
        streams["heart_rate"].append(row.get("heart_rate"))
        streams["power"].append(row.get("power"))
        streams["altitude"].append(row.get("altitude"))
        streams["cadence"].append(row.get("cadence"))
    return streams


def _download_fit_records(g, activity_id: str) -> list[dict[str, Any]]:
    from fitparse import FitFile

    blob = g.download_activity(activity_id, dl_fmt=g.ActivityDownloadFormat.ORIGINAL)
    fit_raw = blob
    if isinstance(blob, (bytes, bytearray)) and blob[:2] == b"PK":
        zf = zipfile.ZipFile(io.BytesIO(blob))
        names = zf.namelist()
        if not names:
            return []
        fit_raw = zf.read(names[0])

    fit = FitFile(io.BytesIO(fit_raw))
    records: list[dict[str, Any]] = []
    first_ts = None
    for msg in fit.get_messages("record"):
        row: dict[str, Any] = {}
        ts = None
        for field in msg:
            name = field.name
            value = field.value
            if value is None:
                continue
            if name == "timestamp":
                ts = value
                row["timestamp"] = value
            elif name == "distance":
                row["distance"] = _safe_float(value)
            elif name == "heart_rate":
                row["heart_rate"] = int(value)
            elif name == "power":
                row["power"] = int(value)
            elif name == "altitude":
                row["altitude"] = _safe_float(value)
            elif name == "cadence":
                row["cadence"] = int(value)
            elif name in ("position_lat", "position_long"):
                row[name] = value
        if ts is None:
            continue
        if first_ts is None:
            first_ts = ts
        row["time_s"] = int((ts - first_ts).total_seconds())
        records.append(row)
    return records


def read_activity_streams(activity_id: str) -> dict:
    """Fetch Garmin activity streams (FIT-style time series) when available."""
    activity_id = _normalize_activity_id(activity_id)
    if not activity_id:
        return {"error": "streams unavailable", "available": []}

    available: list[str] = []
    collected: dict[str, Any] = {}

    try:
        g = _garmin_client()
    except Exception as exc:
        return {"error": f"streams unavailable: {exc}", "available": []}

    fetchers = [
        ("details", lambda: g.get_activity_details(activity_id)),
        ("splits", lambda: g.get_activity_splits(activity_id)),
        ("hr_timezones", lambda: g.get_activity_hr_in_timezones(activity_id)),
        ("power_timezones", lambda: g.get_activity_power_in_timezones(activity_id)),
    ]
    for name, fetch in fetchers:
        try:
            collected[name] = fetch()
            available.append(name)
        except Exception as exc:
            collected[f"{name}_error"] = str(exc)[:200]

    streams: dict[str, Any] = {}
    details = collected.get("details")
    splits = collected.get("splits")

    if details is not None:
        streams["time"] = _find_series(details, ("time", "elapsed_time", "elapsedtime", "elapsedSec", "time_s", "seconds"))
        streams["distance"] = _find_series(details, ("distance", "dist", "distance_m", "distanceMeters", "distanceMetersAccumulated"))
        streams["heart_rate"] = _find_series(details, ("heart_rate", "heartRate", "hr", "heartrate"))
        streams["power"] = _find_series(details, ("power", "watts", "avgPower", "power_w"))
        streams["altitude"] = _find_series(details, ("altitude", "alt", "elevation", "elevation_m"))
        streams["cadence"] = _find_series(details, ("cadence", "rpm", "avgCadence"))

    if splits is not None and not any(streams.get(k) for k in ("time", "distance", "heart_rate", "power", "altitude", "cadence")):
        # Basic fallback for APIs that expose split-like data only.
        series_map = {
            "time": ("time", "duration", "duration_s", "movingDuration"),
            "distance": ("distance", "distance_m", "distanceMeters"),
            "heart_rate": ("avg_hr", "averageHR", "heart_rate", "heartRate"),
            "power": ("avg_power", "averagePower", "power", "watts"),
            "altitude": ("altitude", "elevation", "elevationGain"),
            "cadence": ("cadence", "avgCadence", "averageCadence"),
        }
        for key, aliases in series_map.items():
            series = _find_series(splits, aliases)
            if series:
                streams[key] = series

    try:
        fit_streams = _fit_streams_from_download(g, activity_id)
        if fit_streams:
            available.append("fit_download")
            streams = fit_streams
    except Exception as exc:
        collected["fit_download_error"] = str(exc)[:200]

    # Normalize missing keys so callers can rely on the shape.
    for key in ("time", "distance", "heart_rate", "power", "altitude", "cadence"):
        streams.setdefault(key, [])

    has_any = any(streams[key] for key in ("time", "distance", "heart_rate", "power", "altitude", "cadence"))
    if not has_any:
        return {
            "error": "streams unavailable",
            "available": available,
            **{k: v for k, v in collected.items() if k.endswith("_error")},
        }

    result = dict(streams)
    result["available"] = available
    if any(k.endswith("_error") for k in collected):
        result["errors"] = {k: v for k, v in collected.items() if k.endswith("_error")}
    return result


def export_activity_artifact(activity_id: str, fmt: str = "fit") -> dict[str, Any]:
    """Export Garmin activity to a local artifact file."""
    from qbot3.artifacts.store import save_file

    activity_id = _normalize_activity_id(activity_id)
    fmt = str(fmt or "fit").strip().lower()
    if not activity_id:
        return {"ok": False, "status": "ERROR", "error": "activity_id required", "available": []}
    if fmt not in {"fit", "gpx", "csv"}:
        return {"ok": False, "status": "ERROR", "error": "format must be fit, gpx or csv", "available": []}

    try:
        g = _garmin_client()
    except Exception as exc:
        return {"ok": False, "status": "ERROR", "error": f"streams unavailable: {exc}", "available": []}

    available: list[str] = []
    try:
        records = _download_fit_records(g, activity_id)
        available.append("fit_download")
    except Exception as exc:
        return {"ok": False, "status": "ERROR", "error": f"streams unavailable: {exc}", "available": available}

    if not records:
        return {"ok": False, "status": "ERROR", "error": "streams unavailable", "available": available}

    filename = f"garmin_{activity_id}.{fmt}"
    title = f"Garmin activity {activity_id} export ({fmt.upper()})"
    subdir = "exports/garmin"
    artifact_type = "export"

    if fmt == "fit":
        blob = g.download_activity(activity_id, dl_fmt=g.ActivityDownloadFormat.ORIGINAL)
        if isinstance(blob, str):
            content = blob.encode("utf-8")
        else:
            content = bytes(blob)
        result = save_file(
            content=content,
            filename=filename,
            artifact_type=artifact_type,
            title=title,
            subdir=subdir,
            source="garmin_connect_api",
            metadata={"activity_id": activity_id, "format": fmt, "available": available},
            is_tmp=False,
        )
    elif fmt == "csv":
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=["time_s", "distance", "heart_rate", "power", "altitude", "cadence"])
        writer.writeheader()
        for row in records:
            writer.writerow({k: row.get(k) for k in writer.fieldnames})
        result = save_file(
            content=out.getvalue(),
            filename=filename,
            artifact_type=artifact_type,
            title=title,
            subdir=subdir,
            source="garmin_connect_api",
            metadata={"activity_id": activity_id, "format": fmt, "available": available},
            is_tmp=False,
        )
    else:
        # Minimal GPX export built from FIT track points.
        # If GPS points are absent, return an explicit error rather than inventing geometry.
        points: list[str] = []
        for row in records:
            lat = row.get("position_lat")
            lon = row.get("position_long")
            if lat is None or lon is None:
                continue
            lat_deg = float(lat) * (180 / 2**31)
            lon_deg = float(lon) * (180 / 2**31)
            ele = row.get("altitude")
            ts = row.get("timestamp")
            ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else ""
            pt = f'<trkpt lat="{lat_deg:.7f}" lon="{lon_deg:.7f}">'
            if ele is not None:
                pt += f"<ele>{float(ele):.1f}</ele>"
            if ts_iso:
                pt += f"<time>{_xml_escape(ts_iso)}</time>"
            pt += "</trkpt>"
            points.append(pt)
        if not points:
            return {"ok": False, "status": "ERROR", "error": "streams unavailable", "available": available}
        gpx = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<gpx version="1.1" creator="QBot Garmin export" xmlns="http://www.topografix.com/GPX/1/1">'
            f'<trk><name>Garmin {activity_id}</name><trkseg>{"".join(points)}</trkseg></trk></gpx>'
        )
        result = save_file(
            content=gpx,
            filename=filename,
            artifact_type=artifact_type,
            title=title,
            subdir=subdir,
            source="garmin_connect_api",
            metadata={"activity_id": activity_id, "format": fmt, "available": available},
            is_tmp=False,
        )

    result["activity_id"] = activity_id
    result["format"] = fmt
    result["available"] = available
    result["ok"] = True
    return result


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

            # Convert grams to kg for muscle/bone mass
            if mm and mm > 500: mm = mm / 1000.0
            if bm and bm > 500: bm = bm / 1000.0

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


def read_activity_summary(activity_id: str) -> dict[str, Any]:
    """Fetch and normalize a single Garmin activity summary by activity_id."""
    activity_id = _normalize_activity_id(activity_id)
    if not activity_id:
        return {"error": "activity_id required"}

    try:
        g = _garmin_client()
        raw = g.get_activity(activity_id)
        if not isinstance(raw, dict):
            return {"error": "unexpected activity payload"}
        summary = raw.get("summaryDTO") if isinstance(raw.get("summaryDTO"), dict) else {}
        activity_type = raw.get("activityTypeDTO") if isinstance(raw.get("activityTypeDTO"), dict) else {}
        return {
            "date": str(summary.get("startTimeLocal") or raw.get("startTimeLocal") or "")[:10],
            "started_at": summary.get("startTimeLocal") or raw.get("startTimeLocal") or raw.get("startTimeGMT"),
            "ended_at": None,
            "source": "garmin",
            "external_id": str(raw.get("activityId") or activity_id),
            "activity_type": activity_type.get("typeKey", "") or raw.get("activityType", "") or "",
            "title": raw.get("activityName", ""),
            "duration_sec": _safe_float(summary.get("movingDuration") or summary.get("duration")),
            "elapsed_duration_sec": _safe_float(summary.get("elapsedDuration")),
            "distance_km": (_safe_float(summary.get("distance")) / 1000.0) if summary.get("distance") is not None else None,
            "elevation_gain_m": _safe_float(summary.get("elevationGain")),
            "calories_kcal": _safe_float(summary.get("calories") or raw.get("calories")),
            "avg_hr": int(summary["averageHR"]) if summary.get("averageHR") is not None else None,
            "max_hr": int(summary["maxHR"]) if summary.get("maxHR") is not None else None,
            "avg_power_w": _safe_float(summary.get("averagePower")),
            "max_power_w": _safe_float(summary.get("maxPower")),
            "normalized_power_w": _safe_float(summary.get("normalizedPower")),
            "training_load": _safe_float(summary.get("activityTrainingLoad") or summary.get("trainingStressScore")),
            "training_effect": _safe_float(summary.get("trainingEffect")),
            "anaerobic_training_effect": _safe_float(summary.get("anaerobicTrainingEffect")),
            "route_ref": f"garmin://{raw.get('activityId', activity_id)}",
            "raw_json": raw,
        }
    except Exception as e:
        return {"error": str(e)[:200]}


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
