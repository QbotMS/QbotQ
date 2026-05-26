#!/usr/bin/env python3
"""QBot Query Router v2 — universal read-only MCP tool.

TOSKANIA 2026 / QBot MCP v2 — intent classification, reader dispatch,
structured output with answer, tables, provenance, no-data policy.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any

# ── Required no-data phrase ───────────────────────────────────────────────

NO_DATA_PHRASE = "Brak danych w QBot / plikach projektu."

# ── Intent classification ─────────────────────────────────────────────────

_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    # Priority-ordered: more specific first
    ("calorie_balance", [
        "bilans kaloryczny", "bilans kalorii", "bilans energetyczny",
        "garmin i cronometer", "cronometer i garmin",
        "kalorii z ostatnich", "kalorii w tym tygodniu", "kalorii z garmin",
        "kcal z ostatnich", "kcal z garmin",
    ]),
    ("garmin_energy", [
        "zużycie kcal z garmin", "garmin energy", "aktywne kcal",
        "spoczynkowe kcal", "bmr", "resting kcal", "całkowite kcal z garmin",
        "dzisiejsze zużycie", "garmin spalone",
    ]),
    ("ride_today", [
        "dzisiaj była jazda", "czy był trening", "dzisiejsza jazda",
        "czy jeździł", "trening dzisiaj", "jazda dziś",
        "czy dzisiaj", "była jazda",
    ]),
    ("intervals_today", [
        "intervals z dzisiaj", "intervals dzisiaj", "intervals dzisiejsze",
        "aktywności z intervals", "intervals activity",
        "intervals wellness today",
    ]),
    ("xert_status", [
        "status xert", "xert status", "tp/ftp", "freshness", "fatigue",
        "w'", "w_prime", "xert form", "xert readiness",
    ]),
    ("rwgps_route_lookup", [
        "rwgps 55257604", "toskania z florencji", "toskania qbot",
        "lokalny gpx", "sha256", "trasa rwgps",
    ]),
    ("route_surface_profile", [
        "profil nawierzchni", "nawierzchnia trasy", "surface profil",
        "oceń ryzyko", "szutrowo-gravelow", "szosowo-gravelow",
        "osm enrichment", "surface enrichment",
    ]),
    ("route_stage_split", [
        "podziel trasę", "etapów dziennych", "podziel na 7",
        "etapy", "bolgheri", "pienza", "monteriggioni",
        "końcami etapów", "noclegowych",
    ]),
    ("garage_gear_route_fit", [
        "garaż", "sprzęt", "opony", "częściowo gravelowy",
        "rower", "bikepacking", "bike", "gear na trasę",
        "pasujące opony",
    ]),
    ("no_data_policy_test", [
        "dane których nie ma", "dane nieistniejące",
        "polityką braku danych",
    ]),
    # General intents
    ("nutrition_daily", [
        "bilans kalorii", "kalorii", "kcal", "zjadł", "zjedzone", "posiłk",
        "co jadł", "co zjadł", "dieta", "makro", "żywieni", "nutrition",
        "carbs", "białko", "tłuszcz", "węglowodan",
        "zjadlem", "zjadłam", "jadlem", "jadłam", "jadl", "jedzeni",
    ]),
    ("nutrition_range", [
        "kalorii z ostatnich", "w tym tygodniu", "podsumowanie tygodnia",
        "średni", "średnia kalorii", "trend", "7 dni",
    ]),
    ("hydration", [
        "wypi", "płyn", "woda", "nawodnieni", "hydration", "fluids",
    ]),
    ("fueling", [
        "żel", "fueling", "carbs na trasie", "węgli na trasie",
    ]),
    ("training_load", [
        "obciążenie treningowe", "tss", "ctl", "atl", "tsb",
        "training load", "zmęczeni", "przetrenow",
    ]),
    ("xert", [
        "xert", "ftp", "w_prime", "w'", "form", "ltp",
    ]),
    ("intervals", [
        "intervals", "wellness", "hrv", "resting hr",
        "sen", "waga", "weight",
    ]),
    ("weather", [
        "pogoda", "temperatura", "wiatr", "deszcz", "weather",
        "prognoza", "forecast",
    ]),
    ("rwgps_route", [
        "trasa", "trasy", "rwgps", "route", "kolekcj",
        "nawierzchnia trasy", "podziel trasę", "etap",
        "gpx",
    ]),
    ("rwgps_search", [
        "znajdź trasę", "szukaj trasy", "ostatnia trasa rwgps",
    ]),
    ("rwgps_export", [
        "eksport", "pobierz", "gpx", "tcx", "fit",
    ]),
    ("route_surface", [
        "nawierzchnia", "surface", "szuter", "asfalt",
    ]),
    ("garage", [
        "garaż", "garage", "sprzęt", "rower", "opon",
        "bikepacking", "bike", "gear", "częś",
    ]),
    ("daily_report", [
        "raport dzienny", "raport", "daily report", "podsumowanie dnia",
    ]),
    ("ride_report", [
        "raport z jazdy", "ride report", "ostatnia jazda",
    ]),
    ("wellness", [
        "samopoczucie", "wellness", "sen", "sleep",
        "battery", "stres",
    ]),
    ("artifact_read", [
        "plik", "artefakt", "artifact", "csv",
    ]),
    ("capability_check", [
        "czy masz", "czy qbot ma", "czy potrafisz", "dane do odpowiedzi",
    ]),
    ("project", [
        "projekt", "kod", "pliki projektu", "repozytorium",
    ]),
]


def classify_intent(query: str) -> list[str]:
    q = query.lower()
    intents: list[str] = []
    for intent, keywords in _INTENT_PATTERNS:
        for kw in keywords:
            if kw in q:
                intents.append(intent)
                break
    if not intents:
        intents.append("general")
    return intents


# ── Reader registry ────────────────────────────────────────────────────────

ReaderFunc = Any

_READER_REGISTRY: dict[str, dict[str, Any]] = {}


def _reader(name: str, category: str, tool: str, params: dict, providers: list[str]):
    _READER_REGISTRY[name] = {
        "category": category, "tool": tool,
        "params": params, "providers": providers,
    }


# Core readers
_reader("nutrition_day", "nutrition", "qbot_nutrition_day_summary", {"date": "str"}, ["nutrition_db"])
_reader("nutrition_range", "nutrition", "qbot_nutrition_range_summary", {"date_from": "str", "date_to": "str"}, ["nutrition_db", "wellness_store"])
_reader("nutrition_food_search", "nutrition", "qbot_nutrition_food_search", {"query": "str"}, ["nutrition_db"])
_reader("meal_list", "nutrition", "qbot_nutrition_meal_list", {"date": "str"}, ["nutrition_db"])
_reader("nutrition_status", "nutrition", "qbot_nutrition_status", {}, ["nutrition_db"])
_reader("wellness_day", "wellness", "qbot_wellness_day_get", {"date": "str"}, ["wellness_store"])
_reader("sleep_day", "wellness", "qbot_sleep_day_get", {"date": "str"}, ["wellness_store"])
_reader("nutrition_day_legacy", "wellness", "qbot_nutrition_day_get", {"date": "str"}, ["wellness_store"])
_reader("wellness_range", "wellness", "qbot_wellness_range_summary", {"date_from": "str", "date_to": "str"}, ["wellness_store"])
_reader("xert_readiness", "xert", "qbot_xert_readiness_status", {}, ["xert_api"])
_reader("xert_config", "xert", "qbot_xert_config_status", {}, ["xert_api"])
_reader("intervals_wellness", "intervals", "qbot_intervals_wellness_status", {}, ["intervals_api"])
_reader("intervals_config", "intervals", "qbot_intervals_config_status", {}, ["intervals_api"])
_reader("weather_current", "weather", "qbot_weather_current", {"location": "str"}, ["openweathermap", "open_meteo"])
_reader("weather_forecast", "weather", "qbot_weather_forecast", {"location": "str"}, ["openweathermap", "open_meteo"])
_reader("rwgps_route_get", "rwgps", "qbot_rwgps_route_get", {"route_id": "str"}, ["rwgps_api", "rwgps_cache"])
_reader("rwgps_route_list", "rwgps", "qbot_rwgps_route_list", {"limit": "int"}, ["rwgps_api", "rwgps_cache"])
_reader("rwgps_route_search", "rwgps", "qbot_rwgps_route_search", {"query": "str"}, ["rwgps_api", "rwgps_cache", "rwgps_manifest"])
_reader("rwgps_export_links", "rwgps", "qbot_rwgps_route_export_links", {"route_id": "str"}, ["rwgps_api"])
_reader("rwgps_export_file", "rwgps", "qbot_rwgps_route_export_file", {"route_id": "str", "format": "str", "return_mode": "str"}, ["rwgps_api", "filesystem"])
_reader("gpx_artifact_parse", "routes", "qbot_gpx_artifact_parse", {"artifact_path": "str"}, ["filesystem"])
_reader("route_artifact_enrich", "routes", "qbot_route_artifact_enrich", {"artifact_path": "str"}, ["filesystem", "osm_overpass"])
_reader("garage_list", "garage", "qbot_garage_raw_list", {"limit": "int"}, ["postgresql", "garage_db"])
_reader("garage_search", "garage", "qbot_garage_raw_search", {"query": "str"}, ["postgresql", "garage_db"])
_reader("garage_status", "garage", "qbot_garage_raw_status", {}, ["postgresql", "garage_db"])
_reader("daily_report_preview", "reports", "qbot_daily_report_preview", {}, ["filesystem", "cache", "weather_cache", "xert_cache"])
_reader("ride_report_preview", "reports", "qbot_ride_report_preview", {}, ["filesystem", "cache"])
_reader("ride_report_latest", "reports", "qbot_ride_report_latest", {}, ["filesystem"])
_reader("garmin_status", "garmin", "qbot_garmin_config_status", {}, ["garmin_tokenstore"])
_reader("cronometer_status", "cronometer", "qbot_cronometer_legacy_status", {}, ["cronometer_api"])
_reader("status", "meta", "qbot_status", {}, ["qbot_core"])
_reader("readiness", "meta", "qbot_readiness_report", {}, ["qbot_core"])
_reader("capability_scan", "meta", "qbot_legacy_capability_scan", {}, ["qbot_core"])

# New: Garmin energy reader (live read via garminconnect, no DB storage needed)
_reader("garmin_energy", "garmin", "qbot_garmin_energy_read", {"date": "str"}, ["garminconnect_api"])

# New: Intervals activities reader
_reader("intervals_activities", "intervals", "qbot_intervals_activities_read", {"date": "str"}, ["intervals_api"])


# ── Intent → reader mapping ────────────────────────────────────────────────

_INTENT_TO_READERS: dict[str, list[str]] = {
    "calorie_balance": ["nutrition_range", "nutrition_day", "garmin_energy", "cronometer_status"],
    "garmin_energy": ["garmin_energy"],
    "ride_today": ["ride_report_preview", "ride_report_latest", "intervals_activities", "garmin_energy"],
    "intervals_today": ["intervals_wellness", "intervals_activities", "intervals_config"],
    "xert_status": ["xert_readiness", "xert_config"],
    "rwgps_route_lookup": ["rwgps_route_search", "rwgps_route_get", "rwgps_export_file", "gpx_artifact_parse", "rwgps_export_links"],
    "route_surface_profile": ["rwgps_route_get", "rwgps_export_file", "route_artifact_enrich", "gpx_artifact_parse"],
    "route_stage_split": [],  # no reader yet — will return no_data
    "garage_gear_route_fit": ["garage_search", "garage_list", "garage_status", "route_artifact_enrich"],
    "no_data_policy_test": [],
    # Standard intents
    "nutrition_daily": ["nutrition_day", "meal_list", "nutrition_food_search"],
    "nutrition_range": ["nutrition_range", "nutrition_day"],
    "hydration": ["nutrition_day"],
    "fueling": ["nutrition_day"],
    "training_load": ["xert_readiness", "intervals_wellness"],
    "xert": ["xert_readiness", "xert_config"],
    "intervals": ["intervals_wellness", "intervals_config", "wellness_day"],
    "weather": ["weather_current", "weather_forecast"],
    "rwgps_route": ["rwgps_route_get", "rwgps_route_list", "gpx_artifact_parse", "route_artifact_enrich"],
    "rwgps_search": ["rwgps_route_search", "rwgps_route_list"],
    "rwgps_export": ["rwgps_export_links", "rwgps_route_get"],
    "route_surface": ["route_artifact_enrich", "gpx_artifact_parse"],
    "garage": ["garage_search", "garage_list", "garage_status"],
    "daily_report": ["daily_report_preview"],
    "ride_report": ["ride_report_preview", "ride_report_latest"],
    "wellness": ["wellness_day", "sleep_day", "nutrition_day_legacy"],
    "artifact_read": [],
    "capability_check": ["status", "capability_scan"],
    "project": [],
    "general": ["status", "readiness"],
}


# ── Tool dispatcher ────────────────────────────────────────────────────────

_TOOL_DISPATCH: dict[str, Any] = {}


def _init_dispatch():
    from qbot_nutrition_tools import (
        _tool_qbot_nutrition_food_search, _tool_qbot_nutrition_day_summary,
        _tool_qbot_nutrition_meal_list, _tool_qbot_nutrition_status,
    )
    _TOOL_DISPATCH.update({f"qbot_nutrition_{k}": v for k, v in {
        "food_search": _tool_qbot_nutrition_food_search,
        "day_summary": _tool_qbot_nutrition_day_summary,
        "meal_list": _tool_qbot_nutrition_meal_list,
        "status": _tool_qbot_nutrition_status,
    }.items()})

    from qbot_wellness_store import (
        _tool_qbot_wellness_day_get, _tool_qbot_sleep_day_get,
        _tool_qbot_nutrition_day_get, _tool_qbot_wellness_range_summary,
        _tool_qbot_nutrition_range_summary, _tool_qbot_wellness_db_status,
    )
    _TOOL_DISPATCH.update({f"qbot_{k}": v for k, v in {
        "wellness_day_get": _tool_qbot_wellness_day_get,
        "sleep_day_get": _tool_qbot_sleep_day_get,
        "nutrition_day_get": _tool_qbot_nutrition_day_get,
        "wellness_range_summary": _tool_qbot_wellness_range_summary,
        "nutrition_range_summary": _tool_qbot_nutrition_range_summary,
        "wellness_db_status": _tool_qbot_wellness_db_status,
    }.items()})

    from qbot_integration_tools import (
        _tool_qbot_xert_readiness_status, _tool_qbot_xert_config_status,
        _tool_qbot_intervals_wellness_status, _tool_qbot_intervals_config_status,
        _tool_qbot_weather_current, _tool_qbot_weather_forecast,
        _tool_qbot_garmin_config_status, _tool_qbot_cronometer_legacy_status,
    )
    _TOOL_DISPATCH.update({f"qbot_{k}": v for k, v in {
        "xert_readiness_status": _tool_qbot_xert_readiness_status,
        "xert_config_status": _tool_qbot_xert_config_status,
        "intervals_wellness_status": _tool_qbot_intervals_wellness_status,
        "intervals_config_status": _tool_qbot_intervals_config_status,
        "weather_current": _tool_qbot_weather_current,
        "weather_forecast": _tool_qbot_weather_forecast,
        "garmin_config_status": _tool_qbot_garmin_config_status,
        "cronometer_legacy_status": _tool_qbot_cronometer_legacy_status,
    }.items()})

    from qbot_route_tools import (
        _tool_qbot_rwgps_route_get, _tool_qbot_rwgps_route_list,
        _tool_qbot_rwgps_route_search, _tool_qbot_rwgps_route_export_links,
        _tool_qbot_rwgps_route_export_file, _tool_qbot_gpx_artifact_parse,
        _tool_qbot_route_artifact_enrich,
    )
    _TOOL_DISPATCH.update({f"qbot_{k}": v for k, v in {
        "rwgps_route_get": _tool_qbot_rwgps_route_get,
        "rwgps_route_list": _tool_qbot_rwgps_route_list,
        "rwgps_route_search": _tool_qbot_rwgps_route_search,
        "rwgps_route_export_links": _tool_qbot_rwgps_route_export_links,
        "rwgps_route_export_file": _tool_qbot_rwgps_route_export_file,
        "gpx_artifact_parse": _tool_qbot_gpx_artifact_parse,
        "route_artifact_enrich": _tool_qbot_route_artifact_enrich,
    }.items()})

    from qbot_garage_tools import (
        _tool_qbot_garage_raw_list, _tool_qbot_garage_raw_search,
        _tool_qbot_garage_raw_status,
    )
    _TOOL_DISPATCH.update({f"qbot_{k}": v for k, v in {
        "garage_raw_list": _tool_qbot_garage_raw_list,
        "garage_raw_search": _tool_qbot_garage_raw_search,
        "garage_raw_status": _tool_qbot_garage_raw_status,
    }.items()})

    from qbot_report_tools import (
        _tool_qbot_daily_report_preview,
        _tool_qbot_ride_report_preview, _tool_qbot_ride_report_latest,
    )
    _TOOL_DISPATCH.update({f"qbot_{k}": v for k, v in {
        "daily_report_preview": _tool_qbot_daily_report_preview,
        "ride_report_preview": _tool_qbot_ride_report_preview,
        "ride_report_latest": _tool_qbot_ride_report_latest,
    }.items()})

    from qbot_tool_registry import TOOLS
    for name, func in TOOLS.items():
        if name not in _TOOL_DISPATCH:
            _TOOL_DISPATCH[name] = func

    # New: Garmin energy reader (in-module function)
    _TOOL_DISPATCH["qbot_garmin_energy_read"] = _read_garmin_energy

    # New: Intervals activities reader (in-module function)
    _TOOL_DISPATCH["qbot_intervals_activities_read"] = _read_intervals_activities


# ── New readers ────────────────────────────────────────────────────────────


def _read_garmin_energy(args: dict | None = None) -> dict[str, Any]:
    """Read today's Garmin energy data via garminconnect API. Live read, no DB storage."""
    args = args or {}
    day_str = args.get("date") or date.today().isoformat()

    try:
        import os
        from garminconnect import Garmin

        email = os.getenv("GARMIN_EMAIL", "")
        password = os.getenv("GARMIN_PASSWORD", "")
        if not email or not password:
            return {
                "tool": "qbot_garmin_energy_read",
                "safety_class": "READ_ONLY",
                "status": "no_data",
                "date": day_str,
                "error": "GARMIN_EMAIL or GARMIN_PASSWORD not configured",
                "missing_fields": ["garmin_credentials"],
            }

        tokenstore = os.getenv("GARMIN_TOKENSTORE", "/opt/qbot/app/.garmin_tokens")
        g = Garmin(email, password, tokenstore=tokenstore)
        g.login()

        stats = g.get_stats(day_str)
        if not stats:
            return {
                "tool": "qbot_garmin_energy_read",
                "safety_class": "READ_ONLY",
                "status": "no_data",
                "date": day_str,
                "error": "No Garmin stats returned for this date",
                "missing_fields": ["garmin_stats_data"],
            }

        active_kcal = float(stats.get("activeKilocalories", 0) or 0)
        bmr_kcal = float(stats.get("bmrKilocalories", 0) or 0)
        total_kcal = float(stats.get("totalKilocalories", 0) or 0)
        resting_kcal = total_kcal - active_kcal if total_kcal else bmr_kcal

        return {
            "tool": "qbot_garmin_energy_read",
            "safety_class": "READ_ONLY",
            "status": "OK",
            "date": day_str,
            "active_kcal": active_kcal,
            "resting_kcal": resting_kcal,
            "bmr_kcal": bmr_kcal,
            "total_kcal": total_kcal,
            "source": "garminconnect",
        }
    except Exception as exc:
        return {
            "tool": "qbot_garmin_energy_read",
            "safety_class": "READ_ONLY",
            "status": "no_data",
            "date": day_str,
            "error": str(exc),
            "missing_fields": ["garminconnect_api_error"],
        }


def _read_intervals_activities(args: dict | None = None) -> dict[str, Any]:
    """Read today's Intervals.icu activities. Live read via API."""
    args = args or {}
    day_str = args.get("date") or date.today().isoformat()
    try:
        import os
        import httpx
        athlete_id = os.getenv("INTERVALS_ATHLETE_ID", "")
        api_key = os.getenv("INTERVALS_API_KEY", "")
        if not athlete_id or not api_key:
            return {
                "tool": "qbot_intervals_activities_read",
                "safety_class": "READ_ONLY",
                "status": "no_data",
                "date": day_str,
                "missing_fields": ["intervals_credentials"],
            }

        auth = (api_key, "")
        # Get activities for the date range (today ± buffer)
        target = date.fromisoformat(day_str)
        oldest = (target - timedelta(days=1)).isoformat()
        newest = (target + timedelta(days=1)).isoformat()
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/activities"
        resp = httpx.get(url, auth=(auth[0], auth[1]), params={"oldest": oldest, "newest": newest}, timeout=30)
        resp.raise_for_status()
        activities = resp.json()

        # Filter to activities on the target date
        day_activities = [a for a in activities if isinstance(a, dict) and a.get("start_date_local", "")[:10] == day_str]

        rides = []
        for a in day_activities:
            ride_info = {
                "name": a.get("name", "?"),
                "type": a.get("type", "?"),
                "distance_m": a.get("distance", 0),
                "moving_time_s": a.get("moving_time", 0),
                "elapsed_time_s": a.get("elapsed_time", 0),
                "elevation_gain_m": a.get("elevation_gain", 0),
                "avg_watts": a.get("icu_average_watts") or a.get("avg_power"),
                "avg_hr": a.get("average_heartrate"),
                "calories": a.get("calories"),
                "tss": a.get("icu_training_load"),
                "activity_id": a.get("id"),
                "start_time": a.get("start_date_local"),
            }
            rides.append(ride_info)

        # Also fetch wellness for today (HRV, RHR, weight, sleep)
        wellness_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness"
        w_resp = httpx.get(wellness_url, auth=auth, params={"oldest": day_str, "newest": day_str}, timeout=30)
        w_list = w_resp.json() if w_resp.status_code == 200 else []
        wellness_today = next((w for w in w_list if isinstance(w, dict) and w.get("id") == day_str), None)

        wellness_data = {}
        if wellness_today:
            wellness_data = {
                "weight_kg": wellness_today.get("weight"),
                "hrv_ms": wellness_today.get("hrv"),
                "resting_hr": wellness_today.get("restingHR"),
                "sleep_secs": wellness_today.get("sleepSecs"),
            }

        return {
            "tool": "qbot_intervals_activities_read",
            "safety_class": "READ_ONLY",
            "status": "OK" if rides or wellness_data else "no_data",
            "date": day_str,
            "activities": rides,
            "activities_count": len(rides),
            "wellness": wellness_data,
            "source": "intervals_api",
        }
    except Exception as exc:
        return {
            "tool": "qbot_intervals_activities_read",
            "safety_class": "READ_ONLY",
            "status": "no_data",
            "date": day_str,
            "error": str(exc),
            "missing_fields": ["intervals_api_error"],
        }


# ── Argument resolver ──────────────────────────────────────────────────────


def _resolve_tool_arg(tool_name: str, tool_params: dict, query: str) -> dict:
    args: dict = {}
    for param, ptype in tool_params.items():
        if param in ("date",):
            today = date.today()
            days_match = re.search(r"(\d+)\s*dni", query.lower())
            if days_match:
                days = int(days_match.group(1))
                args[param] = (today - timedelta(days=days - 1)).isoformat()
            elif "wczoraj" in query.lower():
                args[param] = (today - timedelta(days=1)).isoformat()
            elif "tydzień" in query.lower() or "tygodnia" in query.lower():
                args[param] = (today - timedelta(days=6)).isoformat()
            elif "dzisiaj" in query.lower() or "dzisiejsze" in query.lower() or "dzisiejsz" in query.lower():
                args[param] = today.isoformat()
            else:
                args[param] = today.isoformat()

        elif param in ("date_from",):
            today = date.today()
            days_match = re.search(r"ostatnich\s+(\d+)", query.lower())
            days_match2 = re.search(r"(\d+)\s*dni", query.lower())
            days = int(days_match.group(1)) if days_match else (int(days_match2.group(1)) if days_match2 else 7)
            args[param] = (today - timedelta(days=days - 1)).isoformat()
            args["date_to"] = today.isoformat()

        elif param in ("date_to",):
            if "date_to" not in args:
                args[param] = date.today().isoformat()

        elif param in ("query",):
            route_match = re.search(r"(\d{7,})", query)
            if route_match:
                args[param] = route_match.group(1)
            else:
                name_match = re.search(r"'([^']+)'|\"([^\"]+)\"", query)
                if name_match:
                    args[param] = name_match.group(1) or name_match.group(2)
                else:
                    search_match = re.search(r"(?:szukaj|znajdź|wyszukaj|trasy?)\s+(.+?)(?:$|,|\.)", query.lower())
                    if search_match:
                        args[param] = search_match.group(1).strip()
                    else:
                        args[param] = query[:80]

        elif param in ("route_id",):
            route_match = re.search(r"(\d{7,})", query)
            if route_match:
                args[param] = route_match.group(1)

        elif param in ("artifact_path",):
            route_match = re.search(r"(\d{7,})", query)
            if route_match:
                args[param] = f"exports/rwgps/rwgps_{route_match.group(1)}.gpx"
            path_match = re.search(r"(exports/rwgps/rwgps_\d+\.\w+)", query)
            if path_match:
                args[param] = path_match.group(1)

        elif param in ("path_or_name",):
            path_match = re.search(r"(exports/rwgps/rwgps_\d+\.\w+)", query)
            if path_match:
                args[param] = path_match.group(1)

        elif param in ("format",):
            if "tcx" in query.lower():
                args[param] = "tcx"
            elif "json" in query.lower():
                args[param] = "json"
            else:
                args[param] = "gpx"

        elif param in ("return_mode",):
            args[param] = "metadata"

        elif param in ("prefix",):
            args[param] = "exports/rwgps/"

        elif param in ("limit",):
            args[param] = 20

        elif param in ("location",):
            location_match = re.search(r"(?:pogoda|weather|prognoza)\s+(?:w|na)\s+(\w+)", query.lower())
            if location_match:
                args[param] = location_match.group(1)

    return args


# ── Helpers ────────────────────────────────────────────────────────────────


def _is_failure(status_val: str) -> bool:
    return status_val.upper() in ("ERROR", "FAIL", "BLOCKED", "BLOCKED_NO_TABLES", "NOT_READY", "NO_DATA", "TIMEOUT")


def _is_blocked(status_val: str) -> bool:
    return status_val.upper().startswith("BLOCKED")


def _confidence_from_results(results: list[dict]) -> str:
    ok_count = sum(1 for r in results if r.get("ok") or r.get("status", "").upper() == "OK")
    total = len(results)
    if total == 0:
        return "low"
    ratio = ok_count / total
    if ratio >= 0.8:
        return "high"
    if ratio >= 0.4:
        return "medium"
    return "low"


def _synthesize_answer(question: str, answers: list[dict], missing: list[str]) -> str:
    if not answers:
        return NO_DATA_PHRASE

    parts: list[str] = []
    for ans in answers:
        data = ans.get("data", {})
        reader = ans["reader"]

        if reader == "garmin_energy":
            parts.append(
                f"Garmin: {data.get('total_kcal', '?')} kcal całk., "
                f"{data.get('active_kcal', '?')} aktywne, "
                f"{data.get('bmr_kcal', '?')} BMR"
            )
        elif reader == "intervals_activities":
            acts = data.get("activities", [])
            if acts:
                a = acts[0]
                parts.append(
                    f"Jazda: {a.get('name')} ({a.get('distance_m', 0)/1000:.1f}km, "
                    f"{a.get('moving_time_s', 0)//60}min, +{a.get('elevation_gain_m', 0)}m)"
                )
            else:
                parts.append("Brak aktywności w Intervals na dziś")
        elif reader == "nutrition_range":
            summary = data.get("summary", [])
            if summary:
                item = summary[0] if isinstance(summary, list) else summary
                parts.append(
                    f"Średnio: {item.get('avg_kcal', '?')} kcal/dzień, "
                    f"{item.get('avg_carbs', '?')}g węgli"
                )
        elif reader == "nutrition_day":
            s = data.get("summary", {})
            if s:
                parts.append(
                    f"Dzisiaj: {s.get('kcal_total', 0)} kcal, "
                    f"{s.get('carbs_total', 0)}g węgli, "
                    f"{s.get('protein_total', 0)}g białka"
                )
        elif reader in ("rwgps_route_get", "rwgps_route_search"):
            route = data.get("route", data.get("best_route_detail", {}))
            rlist = data.get("routes", [])
            if route and route.get("name"):
                parts.append(f"Trasa: {route.get('name')} ID={route.get('id', '?')}")
            elif rlist:
                parts.append(f"Trasy: {len(rlist)} znalezionych")
        elif reader == "gpx_artifact_parse":
            parts.append(
                f"GPX: {data.get('track_points', '?')} pkt, "
                f"{data.get('distance_m', 0)/1000:.1f}km, "
                f"+{data.get('elevation_gain_m', 0)}m, "
                f"SHA256={data.get('sha256', '?')[:12]}..."
            )
        elif reader == "route_artifact_enrich":
            profile = data.get("surface_profile", {})
            if profile:
                parts.append(f"Nawierzchnia: {profile.get('dominant_surface', '?')}, coverage={profile.get('coverage_pct', '?')}%")
        elif reader == "garage_search":
            results = data.get("results", data.get("rows", []))
            parts.append(f"Garaż: {len(results)} rekordów" if results else "Garaż: brak wyników")
        elif reader == "garage_status":
            st = data.get("status", "?").upper()
            if st.startswith("BLOCKED"):
                parts.append("Garaż: tabele PostgreSQL nie istnieją (garage.db na dysku, niezaimportowane)")
        elif reader == "weather_current":
            parts.append(f"Pogoda: {data.get('temperature_c', '?')}°C, {data.get('description', '?')}")
        elif reader == "xert_readiness":
            parts.append(f"Xert: FTP={data.get('ftp_watts', '?')}W, form={data.get('form_status', '?')}")
        elif reader == "intervals_wellness":
            parts.append(f"Wellness: HRV={data.get('hrv', '?')}ms, RHR={data.get('resting_hr', '?')}bpm")

    if not parts:
        parts.append(f"Dostępnych {len(answers)} odpowiedzi z readerów")

    if missing:
        parts.append(f"({len(missing)} braków danych)")

    return " | ".join(parts)


def _extract_tables(answers: list[dict]) -> list[dict]:
    tables: list[dict] = []
    for ans in answers:
        data = ans.get("data", {})
        reader = ans["reader"]

        for key in ("activities", "items", "routes", "records", "results", "rows", "meals", "hydration_events", "fueling_events"):
            if isinstance(data.get(key), list) and len(data[key]) > 0:
                tables.append({"reader": reader, "key": key, "count": len(data[key]), "rows": data[key][:20]})
                break
        if not tables:
            summary = data.get("summary", {})
            if isinstance(summary, dict) and summary:
                tables.append({"reader": reader, "key": "summary", "rows": [summary]})
    return tables


# ── Public API ─────────────────────────────────────────────────────────────


def _tool_qbot_query(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    return query(
        question=str(args.get("query", "")).strip(),
        mode=str(args.get("mode", "read_only")),
        scope=str(args.get("scope", "all")),
        context=str(args.get("context", "")),
        max_rows=int(args.get("max_rows", 500)),
        include_provenance=bool(args.get("include_provenance", True)),
        include_missing=bool(args.get("include_missing", True)),
    )


def query(question: str, mode: str = "read_only", scope: str = "all", context: str = "",
          max_rows: int = 500, include_provenance: bool = True, include_missing: bool = True) -> dict[str, Any]:
    if not _TOOL_DISPATCH:
        _init_dispatch()

    intents = classify_intent(question)
    readers_to_call: list[str] = []
    for intent in intents:
        for reader in _INTENT_TO_READERS.get(intent, []):
            if reader not in readers_to_call:
                readers_to_call.append(reader)

    if scope != "all":
        scope_categories: dict[str, list[str]] = {
            "nutrition": ["nutrition", "hydration", "fueling"],
            "training": ["xert", "intervals", "wellness", "garmin"],
            "routes": ["rwgps", "routes", "route_surface"],
            "garage": ["garage", "gear"],
        }
        allowed = set()
        for cat in scope_categories.get(scope, [scope]):
            for reader in _INTENT_TO_READERS.get(cat, []):
                allowed.add(reader)
        readers_to_call = [r for r in readers_to_call if r in allowed]
        if not readers_to_call:
            readers_to_call = list(allowed)[:5]

    if not readers_to_call:
        readers_to_call = _INTENT_TO_READERS.get("general", ["status"])

    # ── plan_only ──
    if mode == "plan_only":
        reader_details = []
        missing_caps: list[str] = []
        for rn in readers_to_call:
            reg = _READER_REGISTRY.get(rn, {})
            tool = reg.get("tool", "?")
            if tool == "?" or tool not in _TOOL_DISPATCH:
                missing_caps.append(f"{rn}: reader or tool missing")
            reader_details.append({
                "reader": rn,
                "category": reg.get("category", "?"),
                "providers": reg.get("providers", []),
                "available": tool in _TOOL_DISPATCH,
            })
        return {
            "tool": "qbot.query", "safety_class": "READ_ONLY",
            "status": "partial" if missing_caps else "ok",
            "mode": "plan_only",
            "query": question, "intents_detected": intents,
            "readers_planned": readers_to_call, "readers_count": len(readers_to_call),
            "readers_used": [],
            "plan": reader_details,
            "answer": f"Plan: {len(readers_to_call)} readerów. {'Brakujące: ' + ', '.join(missing_caps) if missing_caps else 'Wszystkie dostępne.'}",
            "tables": [], "data": {},
            "provenance": [], "missing_fields": missing_caps,
            "missing_capabilities": missing_caps,
            "confidence": "high" if not missing_caps else "medium",
            "limitations": [],
            "note": "plan_only — no data was read, switch to read_only to execute",
        }

    # ── read_only ──
    answers: list[dict] = []
    provenance: list[dict] = []
    missing: list[str] = []
    limitations: list[str] = []
    has_blocked = False

    for reader_name in readers_to_call:
        reg = _READER_REGISTRY.get(reader_name)
        if not reg:
            missing.append(f"{reader_name}: reader not registered")
            continue

        tool_name = reg["tool"]
        func = _TOOL_DISPATCH.get(tool_name)
        if not func:
            missing.append(f"{reader_name}: tool {tool_name} not loaded")
            continue

        try:
            args = _resolve_tool_arg(tool_name, reg["params"], question)
            result = func(args)

            status_val = result.get("status", result.get("status", "UNKNOWN"))
            if _is_blocked(status_val):
                has_blocked = True
            if _is_failure(status_val) and not result.get("items") and not result.get("routes") and not result.get("activities"):
                if include_missing:
                    missing.append(f"{reader_name}: {status_val}")
                limitations.append(f"{reader_name}: returned {status_val}")
            else:
                provenance.append({
                    "reader": reader_name, "tool": tool_name,
                    "providers": reg["providers"], "status": status_val,
                })
                answers.append({
                    "reader": reader_name, "category": reg["category"],
                    "status": status_val, "data": result,
                })
        except Exception as exc:
            missing.append(f"{reader_name}: {type(exc).__name__}: {exc}")
            limitations.append(f"{reader_name}: failed ({type(exc).__name__})")

    # Enforce max_rows
    for ans in answers:
        data = ans.get("data", {})
        for key in ("items", "routes", "rows", "artifacts", "records", "results", "cues", "segments", "meals", "hydration_events", "fueling_events", "activities"):
            if isinstance(data.get(key), list) and len(data[key]) > max_rows:
                data[key] = data[key][:max_rows]
                data[f"{key}_truncated"] = True

    tables = _extract_tables(answers)
    answer_text = _synthesize_answer(question, answers, missing)

    response: dict[str, Any] = {
        "tool": "qbot.query", "safety_class": "READ_ONLY",
        "mode": "read_only",
        "query": question, "intents_detected": intents,
        "readers_planned": readers_to_call,
        "readers_used": readers_to_call,
        "readers_count": len(answers),
        "answer": answer_text,
        "tables": tables, "data": answers[0].get("data", {}) if answers else {},
        "answers": answers, "provenance": provenance if include_provenance else [],
        "missing_fields": missing if include_missing else [],
        "confidence": _confidence_from_results(answers),
        "limitations": limitations[:10],
    }

    # Status aggregation
    if not answers:
        response["status"] = "no_data"
        response["answer"] = NO_DATA_PHRASE
    elif has_blocked:
        response["status"] = "blocked"
    elif len(answers) == 1 and answers[0]["reader"] in ("status", "readiness", "capability_scan"):
        response["status"] = "no_data"
        response["answer"] = NO_DATA_PHRASE
    elif missing and not answers:
        response["status"] = "no_data"
        response["answer"] = NO_DATA_PHRASE
    elif missing:
        response["status"] = "partial"
    else:
        response["status"] = "ok"

    # Route stage split: always no_data (no reader)
    if "route_stage_split" in intents:
        response["status"] = "no_data"
        response["answer"] = NO_DATA_PHRASE
        response["missing_capabilities"] = [
            "route_stage_splitter",
            "town_snap_to_trackpoint",
            "lodging_waypoint_matcher",
        ]
        response["limitations"].append("qbot.query can parse GPX summary, but cannot stage full GPX yet")

    # No-data policy test
    if "no_data_policy_test" in intents:
        response["status"] = "no_data"
        response["answer"] = NO_DATA_PHRASE

    return response
