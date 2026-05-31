#!/usr/bin/env python3
"""weather_modifier.py — Open-Meteo weather modifier dla Gravel Intelligence.

Dostosowuje scoring nawierzchni w oparciu o opady (precipitation_sum)
z Open-Meteo API. Soil moisture wnioskowany z opadów (API nie zwraca
bezpośrednio soil_moisture w warstwie darmowej).

Usage:
    from lib.weather_modifier import fetch_weather, classify_soil, weather_multiplier
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any


# ── Thresholds ────────────────────────────────────────────────────────────

SOIL_THRESHOLDS = {
    "dry": {"precip_7d_max": 2.0},
    "wet": {"precip_7d_min": 20.0},
}

FORECAST_PRECIP_THRESHOLD = 10.0  # mm in 3-day forecast = notable


# ── Fetch from Open-Meteo ────────────────────────────────────────────────

def fetch_open_meteo_precipitation(
    latitude: float,
    longitude: float,
    target_date: str | None = None,
    past_days: int = 7,
    forecast_days: int = 3,
) -> dict:
    """Fetch precipitation data from Open-Meteo for a point.

    Returns dict with:
      - precipitation_7d_total_mm
      - precipitation_7d_list
      - forecast_3d_total_mm
      - forecast_3d_list
      - soil_condition: dry|normal|wet|unknown
      - note
    """
    import httpx

    if target_date is None:
        target_date = date.today().isoformat()

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        f"&daily=precipitation_sum"
        f"&past_days={past_days + 1}"
        f"&forecast_days={forecast_days}"
        f"&timezone=Europe/Warsaw"
    )

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return {
            "precipitation_7d_total_mm": None,
            "precipitation_7d_list": [],
            "forecast_3d_total_mm": None,
            "forecast_3d_list": [],
            "soil_condition": "unknown",
            "note": f"Open-Meteo fetch failed: {exc}",
            "error": str(exc)[:100],
        }

    daily = data.get("daily", {})
    times = daily.get("time", [])
    precip = daily.get("precipitation_sum", [])

    if not times or not precip:
        return {
            "precipitation_7d_total_mm": None,
            "precipitation_7d_list": [],
            "forecast_3d_total_mm": None,
            "forecast_3d_list": [],
            "soil_condition": "unknown",
            "note": "No precipitation data in Open-Meteo response",
        }

    # Split into past (up to target_date) and forecast (after target_date)
    try:
        td = date.fromisoformat(target_date)
    except ValueError:
        td = date.today()

    past_vals = []
    forecast_vals = []
    for t, p in zip(times, precip):
        try:
            d = date.fromisoformat(t)
        except ValueError:
            continue
        p_safe = p if p is not None else 0.0
        if d <= td:
            past_vals.append(p_safe)
        else:
            forecast_vals.append(p_safe)

    past_7d = past_vals[-past_days:] if len(past_vals) > past_days else past_vals
    forecast_3d = forecast_vals[:forecast_days]

    past_total = round(sum(past_7d), 1) if past_7d else 0.0
    forecast_total = round(sum(forecast_3d), 1) if forecast_3d else 0.0

    # Classify soil condition
    soil_condition = classify_soil(past_total)

    note_parts = []
    if soil_condition == "dry":
        note_parts.append(f"Suszne warunki ({past_total} mm opadów w 7 dni)")
    elif soil_condition == "wet":
        note_parts.append(f"Mokre warunki ({past_total} mm opadów w 7 dni)")
    else:
        note_parts.append(f"Normalne warunki ({past_total} mm opadów w 7 dni)")

    if forecast_total > FORECAST_PRECIP_THRESHOLD:
        note_parts.append(f"UWAGA: prognoza {forecast_total} mm opadów w 3 dni")

    return {
        "precipitation_7d_total_mm": past_total,
        "precipitation_7d_list": past_7d,
        "forecast_3d_total_mm": forecast_total,
        "forecast_3d_list": forecast_3d,
        "soil_condition": soil_condition,
        "note": ". ".join(note_parts) if note_parts else "Brak danych opadowych.",
    }


def classify_soil(precip_7d_mm: float | None) -> str:
    """Classify soil condition based on 7-day precipitation.

    - < 2 mm → dry
    - 2–20 mm → normal (default)
    - > 20 mm → wet
    """
    if precip_7d_mm is None:
        return "unknown"
    if precip_7d_mm < SOIL_THRESHOLDS["dry"]["precip_7d_max"]:
        return "dry"
    if precip_7d_mm > SOIL_THRESHOLDS["wet"]["precip_7d_min"]:
        return "wet"
    return "normal"


# ── Weather multiplier ───────────────────────────────────────────────────

def weather_multiplier(
    surface_class: str | None,
    highway: str | None,
    soil_condition: str,
) -> dict:
    """Apply weather-based multiplier to a surface class.

    Returns dict with:
      - multiplier (float)
      - reason (str)
    """
    hw = (highway or "").lower()
    sc = (surface_class or "").lower()

    if soil_condition == "dry":
        # Sucho: piach sypki, ziemia twarda, track/forest piaszczysty
        if sc == "sand":
            return {"multiplier": 1.25, "reason": "sucho: piasek sypki = trudniej"}
        if sc in ("dirt", "ground", "earth"):
            return {"multiplier": 0.85, "reason": "sucho: twarda ziemia = łatwiej"}
        if sc in ("unpaved_track",):
            return {"multiplier": 1.15, "reason": "sucho: nieutwardzona, możliwy piach"}
        if hw in ("track", "path", "bridleway", "footway") and sc in (None, "", "unknown"):
            return {"multiplier": 1.30, "reason": "sucho: track/path w lesie bez surface = ryzyko piachu"}
        if sc in ("gravel", "compacted"):
            return {"multiplier": 1.00, "reason": "sucho: gravel/compacted bez zmian"}
        return {"multiplier": 1.00, "reason": "sucho: brak zmian"}

    if soil_condition == "wet":
        # Mokro: piach twardnieje, dirt/gruzgnie, gravel lekko gorzej
        if sc == "sand":
            return {"multiplier": 0.80, "reason": "mokro: piasek ubity = łatwiej"}
        if sc in ("dirt", "ground", "earth", "mud"):
            return {"multiplier": 1.35, "reason": "mokro: błoto/grunt = trudniej"}
        if sc == "grass":
            return {"multiplier": 1.25, "reason": "mokro: śliska trawa = trudniej"}
        if sc in ("gravel", "compacted"):
            return {"multiplier": 1.05, "reason": "mokro: gravel lekko śliski"}
        if hw in ("track", "path", "bridleway", "footway") and sc in (None, "", "unknown"):
            return {"multiplier": 1.20, "reason": "mokro: track/path bez surf. = błoto"}
        return {"multiplier": 1.10, "reason": "mokro: ogólnie trudniejsze warunki"}

    # Normal / unknown
    if soil_condition == "unknown":
        return {"multiplier": 1.00, "reason": "brak danych pogodowych — brak modyfikatora"}
    return {"multiplier": 1.00, "reason": "normalne warunki — brak modyfikatora"}


# ── Apply to G10 samples ────────────────────────────────────────────────

def apply_weather_to_samples(
    samples: list[dict],
    weather: dict,
    region: str = "default",
) -> list[dict]:
    """Apply weather modifier to G10 sample results.

    Each sample should have at minimum:
      - score (float or None)
      - best_tags (dict with surface/highway)
      - sample_lat, sample_lon

    Returns list of samples with added weather fields:
      - base_score (original)
      - weather_multiplier
      - weather_score (clamped 0-1)
      - weather_note
      - soil_condition
    """
    soil_condition = weather.get("soil_condition", "unknown")
    results = []
    for s in samples:
        score = s.get("score")
        tags = s.get("best_tags", {}) or {}
        surface = tags.get("surface")
        highway = tags.get("highway")

        wm = weather_multiplier(surface, highway, soil_condition)
        multiplier = wm["multiplier"]

        if score is not None:
            weather_score = max(0.0, min(1.0, score * multiplier))
        else:
            weather_score = None

        result = dict(s)
        result["base_score"] = score
        result["weather_multiplier"] = multiplier
        result["weather_score"] = round(weather_score, 4) if weather_score is not None else None
        result["weather_note"] = wm["reason"]
        result["soil_condition"] = soil_condition
        results.append(result)

    return results


def aggregate_weather_stats(results: list[dict]) -> dict:
    """Compute aggregate stats from weather-modified samples."""
    if not results:
        return {}

    base_scores = [s["base_score"] for s in results if s.get("base_score") is not None]
    weather_scores = [s["weather_score"] for s in results if s.get("weather_score") is not None]
    multipliers = [s["weather_multiplier"] for s in results if s.get("weather_multiplier") is not None]

    avg_base = sum(base_scores) / len(base_scores) if base_scores else 0
    avg_weather = sum(weather_scores) / len(weather_scores) if weather_scores else 0
    avg_mult = sum(multipliers) / len(multipliers) if multipliers else 0

    # Count how many samples changed
    changed = sum(1 for s in results if s.get("weather_multiplier", 1.0) != 1.0)
    increased = sum(1 for s in results if (s.get("weather_multiplier") or 1.0) > 1.0)
    decreased = sum(1 for s in results if (s.get("weather_multiplier") or 1.0) < 1.0)

    return {
        "avg_base_score": round(avg_base, 4),
        "avg_weather_score": round(avg_weather, 4),
        "avg_multiplier": round(avg_mult, 4),
        "samples_changed": changed,
        "samples_increased": increased,
        "samples_decreased": decreased,
        "soil_condition": (results[0].get("soil_condition") if results else "unknown"),
    }


def route_centroid(points: list[list[float]]) -> tuple[float, float]:
    """Compute centroid of a list of [lat, lon] points."""
    if not points:
        return (52.0, 21.0)  # default Poland
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return (sum(lats) / len(lats), sum(lons) / len(lons))
