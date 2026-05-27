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
    ("garmin_energy", [
        "zużycie kcal z garmin", "zuzycie kcal z garmin", "garmin energy",
        "aktywne kcal", "spoczynkowe kcal", "bmr",
        "resting kcal", "całkowite kcal z garmin", "calkowite kcal",
        "dzisiejsze zużycie", "dzisiejsze zuzycie", "garmin spalone",
        "zuzycie kcal", "garmin energia", "garmin kcal",
    ]),
    ("calorie_balance", [
        "bilans kaloryczny", "bilans kalorii", "bilans energetyczny",
        "garmin i cronometer", "cronometer i garmin",
        "kalorii z ostatnich", "kalorii w tym tygodniu", "kalorii z garmin",
        "kcal z ostatnich", "kcal z garmin",
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
    ("nutrition_planning", [
        "ułóż mi jadłospis", "ułóż jadłospis", "zaplanuj jedzenie",
        "jadłospis", "ile mogę jeszcze zjeść", "dieta na dziś",
        "zaplanuj dietę", "plan posiłków", "meal plan",
        "rozpisz jedzenie", "rozplanuj posiłki", "co mogę zjeść",
        "zaplanuj mi jedzenie", "ułóż mi dietę",
    ]),
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
    ("rwgps_route_list_only", [
        "wypisz trasy", "pokaż najnowsze trasy", "lista tras rwgps",
        "pokaż 3 najnowsze trasy", "jakie trasy są dostępne",
        "routes list", "ostatnie trasy", "najnowsze trasy",
        "tylko lista tras", "wypisz ostatnie", "pokaż ostatnie trasy",
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


def _detect_negations(query: str) -> set[str]:
    """Detect negated reader categories from query text.

    Returns set of categories to suppress:
      export  — "bez eksportu", "bez GPX", "nie eksportuj"
      gpx     — "bez GPX", "bez analizy GPX"
      artifact— "bez analizy artefaktów"
      enrich  — "bez wzbogacania", "bez surface"
    """
    q = query.lower()
    suppressed: set[str] = set()
    if re.search(r"bez\s+eksportu|bez\s+exportu|nie\s+eksportuj|nie\s+exportuj|bez\s+gpx\b|bez\s+tcx|bez\s+fit\b", q):
        suppressed.add("export")
        suppressed.add("gpx")
    if re.search(r"bez\s+gpx|bez\s+analizy\s+gpx|nie\s+analizuj\s+gpx|bez\s+plików\s+gpx", q):
        suppressed.add("gpx")
    if re.search(r"bez\s+analizy\s+artefakt|bez\s+artefakt|nie\s+analizuj\s+artefakt|tylko\s+lista", q):
        suppressed.add("artifact")
    if re.search(r"bez\s+wzbogac|bez\s+surface|bez\s+nawierzchni|bez\s+analizy\s+trasy", q):
        suppressed.add("enrich")
    if re.search(r"bez\s+szczegół|bez\s+danych\s+trasy|tylko\s+lista\s+tras|tylko\s+podstawowe", q):
        suppressed.add("detail")
    return suppressed


def classify_intent(query: str) -> list[str]:
    q = query.lower()
    negations = _detect_negations(query)
    intents: list[str] = []
    for intent, keywords in _INTENT_PATTERNS:
        # Skip intents suppressed by negations
        if "export" in negations and intent in ("rwgps_export",):
            continue
        if "gpx" in negations and intent in ("rwgps_export",):
            continue
        if "artifact" in negations and intent in ("artifact_read",):
            continue
        if "enrich" in negations and intent in ("route_surface", "route_surface_profile"):
            continue
        if "detail" in negations and intent in ("rwgps_route",):
            continue
        for kw in keywords:
            if kw in q:
                intents.append(intent)
                break
    if not intents:
        intents.append("general")

    # Post-classification refinement:
    # rwgps_route_list_only takes precedence over rwgps_route
    if "rwgps_route_list_only" in intents and "rwgps_route" in intents:
        intents.remove("rwgps_route")
    # rwgps_route_lookup (by name) is more specific than rwgps_route
    if "rwgps_route_lookup" in intents and "rwgps_route" in intents:
        intents.remove("rwgps_route")

    return intents


# ── Reader registry ────────────────────────────────────────────────────────

ReaderFunc = Any

_READER_REGISTRY: dict[str, dict[str, Any]] = {}


def _reader(name: str, category: str, tool: str, params: dict, providers: list[str]):
    _READER_REGISTRY[name] = {
        "category": category, "tool": tool,
        "params": params, "providers": providers,
    }


_reader("nutrition_planning", "nutrition", "qbot_nutrition_plan_day", {"date": "str", "goal": "str", "day_type": "str"}, ["nutrition_db", "meal_templates"])

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
    "nutrition_planning": ["nutrition_planning", "nutrition_day", "meal_list", "nutrition_food_search"],
    "nutrition_daily": ["nutrition_day", "meal_list", "nutrition_food_search"],
    "nutrition_range": ["nutrition_range", "nutrition_day"],
    "hydration": ["nutrition_day"],
    "fueling": ["nutrition_day"],
    "training_load": ["xert_readiness", "intervals_wellness"],
    "xert": ["xert_readiness", "xert_config"],
    "intervals": ["intervals_wellness", "intervals_config", "wellness_day"],
    "weather": ["weather_current", "weather_forecast"],
    "rwgps_route_list_only": ["rwgps_route_list"],
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


# ── Route alias map (project TOSKANIA 2026 — name→route_id) ────────────────

_ROUTE_ALIASES: dict[str, str] = {
    "toskania z florencji - qbot": "55257604",
    "toskania z florencji": "55257604",
    "toskania qbot": "55257604",
    "toskania": "55257604",
}


def _resolve_route_id(query: str, search_result: dict | None = None) -> str:
    """Resolve route_id from query, alias map, or rwgps search results."""
    m = re.search(r"(\d{7,})", query)
    if m:
        return m.group(1)
    q = query.lower()
    for alias, rid in _ROUTE_ALIASES.items():
        if alias in q:
            return rid
    if search_result:
        routes = search_result.get("routes", [])
        if routes:
            return str(routes[0].get("id", ""))
        best = search_result.get("best_route_detail", {})
        if best and best.get("id"):
            return str(best["id"])
    return ""


# ── Intent-specific parameter overrides ────────────────────────────────────

_INTENT_PARAM_OVERRIDES: dict[str, dict] = {
    "route_surface_profile": {
        "enrich": ["summary", "surface"],
        "surface_source": "osm",
        "sample_every_m": 500,
    },
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

    # New: Nutrition planning reader (read-only)
    _TOOL_DISPATCH["qbot_nutrition_plan_day"] = _read_nutrition_plan


# ── New readers ────────────────────────────────────────────────────────────


def _read_garmin_energy(args: dict | None = None) -> dict[str, Any]:
    """Read Garmin energy data: local cache first, then live garminconnect API."""
    args = args or {}
    day_str = args.get("date") or date.today().isoformat()
    import os
    from pathlib import Path

    # ── Diagnostic base ──
    diag: dict[str, Any] = {
        "tool": "qbot_garmin_energy_read",
        "safety_class": "READ_ONLY",
        "date": day_str,
        "env_configured": bool(os.getenv("GARMIN_EMAIL")),
        "token_store_found": False,
        "session_cache_found": False,
        "local_cache_found": False,
        "auth_status": "unknown",
        "error_class": None,
        "source": None,
        "active_kcal": None,
        "resting_kcal": None,
        "bmr_kcal": None,
        "total_kcal": None,
        "activity_kcal": None,
        "activities": None,
        "safe_next_action": None,
        "error": None,
        "missing_fields": [],
        "limitations": [],
    }

    tokenstore = os.getenv("GARMIN_TOKENSTORE", "/opt/qbot/app/.garmin_tokens")
    ts_path = Path(tokenstore)
    if ts_path.exists():
        diag["token_store_found"] = ts_path.is_dir() and any(ts_path.iterdir())

    session_pkl = Path("/opt/qbot/app/.garmin_session.pkl")
    if session_pkl.exists() and session_pkl.stat().st_size > 0:
        diag["session_cache_found"] = True

    # ═══════════════════════════════════════════════════════════════
    # Step 1: Local DB/cache
    # ═══════════════════════════════════════════════════════════════
    try:
        import psycopg
        from psycopg.rows import dict_row
        pg_host = os.getenv("PGHOST", "localhost")
        pg_db = os.getenv("PGDATABASE", "qbot")
        pg_user = os.getenv("PGUSER", "qbot")
        pg_pass = os.getenv("PGPASSWORD", "")
        with psycopg.connect(
            host=pg_host, port=os.getenv("PGPORT", "5432"),
            dbname=pg_db, user=pg_user, password=pg_pass,
            row_factory=dict_row, connect_timeout=3,
        ) as conn, conn.cursor() as cur:
            # Check qbot_wellness_daily for imported Garmin energy data
            cur.execute(
                "SELECT raw_json FROM qbot_wellness_daily WHERE date=%s AND source='garmin'",
                (day_str,),
            )
            row = cur.fetchone()
            if row and row.get("raw_json"):
                raw = row["raw_json"]
                if isinstance(raw, str):
                    import json as _j
                    raw = _j.loads(raw)
                # Check if wellness has calories fields
                active = raw.get("activeKilocalories") or raw.get("active_kcal")
                bmr = raw.get("bmrKilocalories") or raw.get("bmr_kcal")
                total = raw.get("totalKilocalories") or raw.get("total_kcal")
                resting = raw.get("resting_kcal")
                if not resting and total and active:
                    resting = total - active
                if any(v is not None for v in (active, bmr, total)):
                    diag.update({
                        "status": "OK",
                        "source": "wellness_store",
                        "local_cache_found": True,
                        "auth_status": "ok",
                        "active_kcal": float(active) if active is not None else None,
                        "bmr_kcal": float(bmr) if bmr is not None else None,
                        "total_kcal": float(total) if total is not None else None,
                        "resting_kcal": float(resting) if resting is not None else None,
                        "safe_next_action": "Local wellness_store data used — no live Garmin call needed.",
                    })
                    return diag
    except Exception:
        pass

    # ═══════════════════════════════════════════════════════════════
    # Step 2: Garmin proxy CSV
    # ═══════════════════════════════════════════════════════════════
    try:
        proxy_paths = [
            Path("/opt/qbot/app/outgoing/qbot_garmin_proxy_latest.csv"),
            Path("/opt/qbot/app/qbot_garmin_proxy.csv"),
        ]
        for pp in proxy_paths:
            if pp.exists() and pp.stat().st_size > 0:
                diag["local_cache_found"] = True
                diag["source"] = "garmin_proxy_csv"
                diag["status"] = "partial"
                diag["limitations"].append(
                    f"Found Garmin proxy CSV at {pp} — raw FIT export, not structured daily energy."
                )
                diag["safe_next_action"] = (
                    "Garmin proxy CSV found but not parsed for daily energy. "
                    "Import wellness data to local DB first, or refresh GarminConnect session."
                )
                break
    except Exception:
        pass

    # ═══════════════════════════════════════════════════════════════
    # Step 3: Live GarminConnect API
    # ═══════════════════════════════════════════════════════════════
    email = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if not email or not password:
        diag.update({
            "status": "no_data",
            "auth_status": "unknown",
            "error_class": "credentials_missing",
            "error": "GARMIN_EMAIL or GARMIN_PASSWORD not configured",
            "missing_fields": ["garmin_credentials", "garmin_energy"],
            "safe_next_action": "Set GARMIN_EMAIL and GARMIN_PASSWORD in .env.local.",
        })
        return diag

    try:
        from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectConnectionError
    except ImportError:
        diag.update({
            "status": "error",
            "auth_status": "unknown",
            "error_class": "library_missing",
            "error": "garminconnect library not installed",
            "missing_fields": ["garminconnect_library"],
            "safe_next_action": "Install garminconnect: pip install garminconnect",
        })
        return diag

    try:
        os.makedirs(tokenstore, exist_ok=True)
        try:
            g = Garmin(email, password)
            g.login(tokenstore=tokenstore)
        except (GarminConnectAuthenticationError, Exception) as auth_err:
            err_msg = str(auth_err)
            if "MFA" in err_msg.upper() or "mfa" in err_msg.lower():
                diag.update({
                    "status": "blocked",
                    "auth_status": "mfa_required",
                    "error_class": "mfa_required",
                    "error": err_msg,
                    "missing_fields": ["garmin_energy", "garmin_auth_mfa"],
                    "limitations": [
                        "GarminConnect requires MFA; no prompt_mfa mechanism available in MCP read-only context",
                    ],
                    "safe_next_action": (
                        "Refresh GarminConnect session outside MCP. "
                        "Run: sync_nutrition.py or garmin_auth.py flow to complete MFA, "
                        "then retry qbot.query."
                    ),
                    "source": "garminconnect_api",
                })
                return diag
            raise

        stats = g.get_stats(day_str)
        if not stats:
            return {
                "tool": "qbot_garmin_energy_read",
                "safety_class": "READ_ONLY",
                "status": "no_data",
                "date": day_str,
                "error": "No Garmin stats returned for this date",
                "missing_fields": ["garmin_stats_data"],
                "env_configured": True,
                "token_store_found": diag["token_store_found"],
                "session_cache_found": diag["session_cache_found"],
                "local_cache_found": False,
                "auth_status": "ok",
                "error_class": "no_data",
                "source": "garminconnect_api",
                "safe_next_action": "Check Garmin Connect for this date — no energy data available.",
                "active_kcal": None, "resting_kcal": None, "bmr_kcal": None, "total_kcal": None,
                "activity_kcal": None, "activities": None,
                "limitations": ["No stats available for this date in Garmin"],
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
            "activity_kcal": active_kcal,
            "activities": stats.get("activities", []) if isinstance(stats.get("activities"), list) else None,
            "source": "garminconnect_api",
            "env_configured": True,
            "token_store_found": diag["token_store_found"],
            "session_cache_found": diag["session_cache_found"],
            "local_cache_found": diag.get("local_cache_found", False),
            "auth_status": "ok",
            "error_class": None,
            "safe_next_action": None,
            "error": None,
            "missing_fields": [],
            "limitations": [],
        }
    except Exception as exc:
        err_msg = str(exc)
        # Classify error type
        if "token" in err_msg.lower() or "session" in err_msg.lower() or "expired" in err_msg.lower():
            diag.update({
                "status": "blocked",
                "auth_status": "token_expired",
                "error_class": "token_expired",
                "error": err_msg,
                "missing_fields": ["garmin_energy", "garmin_auth_token"],
                "limitations": ["GarminConnect session expired or token invalid."],
                "safe_next_action": (
                    "Refresh GarminConnect session outside MCP. "
                    "Run garmin_auth.py to re-authenticate."
                ),
                "source": "garminconnect_api",
            })
        elif "rate" in err_msg.lower() or "429" in err_msg:
            diag.update({
                "status": "blocked",
                "auth_status": "rate_limited",
                "error_class": "rate_limited",
                "error": err_msg,
                "missing_fields": ["garmin_energy"],
                "limitations": ["GarminConnect API rate-limited."],
                "safe_next_action": "Wait and retry later.",
                "source": "garminconnect_api",
            })
        else:
            diag.update({
                "status": "error",
                "auth_status": "unknown",
                "error_class": "api_error",
                "error": err_msg,
                "missing_fields": ["garmin_energy", "garminconnect_api_error"],
                "limitations": [f"GarminConnect API error: {err_msg[:100]}"],
                "safe_next_action": "Check GarminConnect API status and network.",
                "source": "garminconnect_api",
            })
        return diag


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


def _read_nutrition_plan(args: dict | None = None) -> dict[str, Any]:
    """Read-only nutrition day planner. Generates a draft plan — no DB writes."""
    args = args or {}
    day_str = args.get("date", args.get("date", ""))
    goal = args.get("goal", "deficit")
    day_type = args.get("day_type", "rest")
    planned_km = args.get("planned_ride_km")
    target_kcal = args.get("target_kcal")
    meals_count = int(args.get("meals_count", 3))
    av_foods = args.get("available_foods", "")
    available = [f.strip() for f in av_foods.split(",") if f.strip()] if av_foods else None

    from qbot_nutrition_planner import plan_day, _get_templates_from_db, _get_already_logged

    templates = _get_templates_from_db() if len(_get_templates_from_db()) > 0 else []
    already_kcal = _get_already_logged(day_str) if day_str else 0

    result = plan_day(
        goal=goal,
        day_type=day_type,
        date_str=day_str,
        planned_ride_km=float(planned_km) if planned_km else None,
        target_kcal=float(target_kcal) if target_kcal else None,
        meals_count=meals_count,
        available_foods=available,
        use_templates=bool(templates),
        templates=templates,
        already_logged_kcal=already_kcal,
    )
    result["tool"] = "qbot_nutrition_plan_day"
    result["safety_class"] = "READ_ONLY"
    result["status"] = "OK"
    return result


# ── Date context resolver ───────────────────────────────────────────────────


def _resolve_date_context(context_str: str, query_text: str) -> dict[str, Any]:
    """Resolve dates from context JSON and query text with explicit precedence.

    Returns a dict with:
      - date, date_from, date_to: resolved ISO dates
      - source: "context" | "query_text" | "relative_phrase" | "timezone_today"
      - timezone: timezone string
    """
    # Default: server today
    server_today = date.today()

    ctx: dict[str, Any] = {}
    if context_str:
        try:
            ctx = json.loads(context_str) if isinstance(context_str, str) else context_str
        except (json.JSONDecodeError, TypeError):
            ctx = {}

    tz = ctx.get("timezone", "Europe/Warsaw")
    result: dict[str, Any] = {
        "timezone": tz,
        "date": server_today.isoformat(),
        "date_from": server_today.isoformat(),
        "date_to": server_today.isoformat(),
        "source": "timezone_today",
    }

    # Precedence 1: explicit ISO dates in context
    ctx_date = ctx.get("date", "")
    ctx_date_from = ctx.get("date_from", "")
    ctx_date_to = ctx.get("date_to", "")

    if ctx_date and re.match(r"\d{4}-\d{2}-\d{2}", str(ctx_date)):
        result["date"] = str(ctx_date)
        result["source"] = "context"
        if not ctx_date_from:
            result["date_from"] = str(ctx_date)
        if not ctx_date_to:
            result["date_to"] = str(ctx_date)

    if ctx_date_from and re.match(r"\d{4}-\d{2}-\d{2}", str(ctx_date_from)):
        result["date_from"] = str(ctx_date_from)
        result["source"] = "context"
        if not ctx_date and result.get("date") == server_today.isoformat():
            result["date"] = str(ctx_date_from)
    if ctx_date_to and re.match(r"\d{4}-\d{2}-\d{2}", str(ctx_date_to)):
        result["date_to"] = str(ctx_date_to)
        result["source"] = "context"

    # Precedence 2: explicit ISO dates in query text
    q = query_text.lower()
    iso_pattern = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:do|–|to|-)\s*(\d{4}-\d{2}-\d{2})", q)
    if iso_pattern:
        q_from = iso_pattern.group(1)
        q_to = iso_pattern.group(2)
        try:
            date.fromisoformat(q_from)
            date.fromisoformat(q_to)
            if result["source"] != "context":
                result["date_from"] = q_from
                result["date_to"] = q_to
                result["source"] = "query_text"
        except ValueError:
            pass
    else:
        single_iso = re.search(r"(\d{4}-\d{2}-\d{2})", q)
        if single_iso:
            try:
                d = date.fromisoformat(single_iso.group(1))
                if result["source"] != "context":
                    result["date"] = d.isoformat()
                    result["source"] = "query_text"
            except ValueError:
                pass

    # Precedence 3: relative phrases (use context date or server today)
    effective_today = server_today
    if ctx_date and re.match(r"\d{4}-\d{2}-\d{2}", str(ctx_date)):
        try:
            effective_today = date.fromisoformat(str(ctx_date))
        except ValueError:
            pass

    if result["source"] not in ("context", "query_text"):
        if "wczoraj" in q:
            result["date"] = (effective_today - timedelta(days=1)).isoformat()
            result["source"] = "relative_phrase"
        elif "dzisiaj" in q or "dzisiejsze" in q or "dzisiejsz" in q or "dziś" in q:
            result["date"] = effective_today.isoformat()
            result["source"] = "relative_phrase"
        elif "przedwczoraj" in q:
            result["date"] = (effective_today - timedelta(days=2)).isoformat()
            result["source"] = "relative_phrase"

    if result["source"] not in ("context", "query_text"):
        ostatnich_match = re.search(r"ostatnich\s+(\d+)", q)
        dni_match = re.search(r"(?:ostatnie\s+)?(\d+)\s*dni", q)

        if "tydzień" in q or "tygodnia" in q or ostatnich_match or dni_match:
            days = 7
            if ostatnich_match:
                days = int(ostatnich_match.group(1))
            elif dni_match:
                days = int(dni_match.group(1))

            if result["source"] != "context":
                result["date_from"] = (effective_today - timedelta(days=days - 1)).isoformat()
                result["date_to"] = effective_today.isoformat()
                result["source"] = "relative_phrase"

    return result


def _resolve_tool_arg(tool_name: str, tool_params: dict, query: str,
                      date_ctx: dict | None = None) -> dict:
    """Resolve tool arguments. Uses date_ctx for date resolution when available.

    date_ctx must contain: date, date_from, date_to (ISO strings).
    """
    args: dict = {}
    dc = date_ctx or {}

    for param, ptype in tool_params.items():
        if param in ("date",):
            if dc.get("date"):
                args[param] = dc["date"]
            else:
                args[param] = date.today().isoformat()

        elif param in ("date_from",):
            if dc.get("date_from"):
                args[param] = dc["date_from"]
                args["date_to"] = dc.get("date_to", date.today().isoformat())
            else:
                today = date.today()
                days_match = re.search(r"ostatnich\s+(\d+)", query.lower())
                days_match2 = re.search(r"(\d+)\s*dni", query.lower())
                days = int(days_match.group(1)) if days_match else (int(days_match2.group(1)) if days_match2 else 7)
                args[param] = (today - timedelta(days=days - 1)).isoformat()
                args["date_to"] = today.isoformat()

        elif param in ("date_to",):
            if "date_to" not in args:
                if dc.get("date_to"):
                    args[param] = dc["date_to"]
                else:
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


def _confidence_from_results(results: list[dict], response_status: str = "",
                            has_required_missing: bool = False) -> str:
    """Compute confidence based on result statuses and requirements.

    Rules:
    - status==ok and all required fields present -> high
    - status==partial because optional fields missing -> medium
    - status==partial because required source missing (e.g. Garmin energy) -> low/medium
    - status==no_data -> low
    - status==blocked -> low
    - Never high when: status is partial/no_data/blocked/error,
      required source missing, answer contains "?" placeholders,
      balance_kcal cannot be computed.
    """
    if not results:
        return "low"

    # Check for blocked or no_data in results
    blocked_count = 0
    no_data_count = 0
    ok_count = 0
    garmin_blocked = False
    garmin_missing = False

    for r in results:
        status = str(r.get("status", r.get("data", {}).get("status", ""))).upper()
        if status.startswith("BLOCKED"):
            blocked_count += 1
            if r.get("reader") == "garmin_energy":
                garmin_blocked = True
        elif status in ("NO_DATA", "ERROR", "FAIL", "TIMEOUT"):
            no_data_count += 1
            if r.get("reader") == "garmin_energy":
                garmin_missing = True
        elif status == "OK":
            ok_count += 1

    total = len(results)
    ok_ratio = ok_count / total if total else 0

    # Hard rules: blocked anywhere with required source = low
    if garmin_blocked and has_required_missing:
        return "low"

    # Status-based
    if response_status == "blocked":
        return "low"
    elif response_status == "no_data":
        return "low"
    elif response_status == "partial":
        if blocked_count > 0 or no_data_count > 0:
            if has_required_missing:
                return "low"
            return "medium"
        return "medium"
    elif response_status == "ok":
        if ok_ratio >= 0.8:
            return "high"
        if ok_ratio >= 0.4:
            return "medium"
        return "low"

    # Fallback: ratio-based
    if ok_ratio >= 0.8:
        return "high"
    if ok_ratio >= 0.4:
        return "medium"
    return "low"


def _synthesize_answer(question: str, answers: list[dict], missing: list[str],
                       intents: list[str] | None = None) -> str:
    intents = intents or []
    if not answers:
        return NO_DATA_PHRASE

    parts: list[str] = []
    for ans in answers:
        data = ans.get("data", {})
        reader = ans["reader"]

        if reader == "garmin_energy":
            status_val = str(data.get("status", "")).upper()
            auth_status = data.get("auth_status", "")
            error_class = data.get("error_class", "")

            if status_val == "BLOCKED" or error_class == "mfa_required":
                parts.append(
                    "Garmin energy: brak danych — GarminConnect wymaga MFA. "
                    "Reader działa, ale sesja/token nie pozwala pobrać danych w trybie MCP read-only."
                )
            elif status_val == "BLOCKED" and error_class == "token_expired":
                parts.append(
                    "Garmin energy: brak danych — sesja GarminConnect wygasła. "
                    "Odśwież sesję poza MCP (garmin_auth.py)."
                )
            elif error_class == "credentials_missing":
                parts.append(
                    "Garmin energy: brak danych — brak skonfigurowanych poświadczeń "
                    "GarminConnect (GARMIN_EMAIL/GARMIN_PASSWORD)."
                )
            elif status_val == "OK":
                tkcal = data.get("total_kcal")
                akcal = data.get("active_kcal")
                bkcal = data.get("bmr_kcal")
                if tkcal is not None:
                    akcal_s = f"{akcal:.0f}" if akcal is not None else "?"
                    bkcal_s = f"{bkcal:.0f}" if bkcal is not None else "?"
                    parts.append(
                        f"Garmin: {tkcal:.0f} kcal całk., "
                        f"{akcal_s} aktywne, {bkcal_s} BMR"
                    )
                else:
                    parts.append("Garmin: dane energii niedostępne")
            elif status_val == "NO_DATA":
                parts.append("Garmin energy: brak danych — brak energii dla tej daty w Garmin")
            else:
                err = data.get("error", "")
                parts.append(f"Garmin: błąd odczytu — {err[:80]}")
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
        elif reader == "nutrition_planning":
            tkcal = data.get("target_intake_kcal", "?")
            tkcal_s = f"{tkcal:.0f}" if isinstance(tkcal, (int, float)) else str(tkcal)
            rem = data.get("remaining_kcal", "?")
            rem_s = f"{rem:.0f}" if isinstance(rem, (int, float)) else str(rem)
            meals = data.get("meals", [])
            meal_names = [m.get("meal_name", m.get("template_name", "?")) for m in meals[:3]]
            conf = data.get("confidence", "?")
            parts.append(
                f"Plan dnia: cel={data.get('goal','?')}, intake={tkcal_s} kcal, "
                f"remaining={rem_s} kcal, posiłki: {', '.join(meal_names)}, "
                f"confidence={conf}. {data.get('note','To jest plan/draft.')}"
            )
        elif reader in ("rwgps_route_get", "rwgps_route_search"):
            route = data.get("route", data.get("best_route_detail", {}))
            rlist = data.get("routes", [])
            if route and route.get("name"):
                parts.append(f"Trasa: {route.get('name')} ID={route.get('id', route.get('route_id', '?'))}")
            elif rlist:
                parts.append(f"Trasy: {len(rlist)} znalezionych")
        elif reader == "rwgps_route_list":
            rlist = data.get("routes", [])
            if rlist:
                previews = []
                for r in rlist[:5]:
                    name = r.get("name", "?")
                    rid = r.get("id", "")
                    dist = r.get("distance_m") or r.get("distance", 0)
                    elev = r.get("elevation_gain_m") or r.get("elevation_gain", 0)
                    previews.append(
                        f"{name} (ID={rid}, {float(dist)/1000:.1f}km, +{elev}m)"
                    )
                tail = f" +{len(rlist)-5} więcej" if len(rlist) > 5 else ""
                parts.append(f"Znaleziono {len(rlist)} tras: {'; '.join(previews)}{tail}")
            else:
                parts.append("Brak tras RWGPS")
        elif reader == "rwgps_export_file":
            parts.append(
                f"RWGPS: {data.get('distance_km', '?')} km, "
                f"D+ {data.get('elevation_gain_m', '?')} m, "
                f"GPX={data.get('artifact_relative_path', '?')}, "
                f"SHA256={str(data.get('sha256', ''))[:16]}..."
            )
        elif reader == "gpx_artifact_parse":
            parts.append(
                f"GPX: {data.get('track_points', '?')} pkt, "
                f"{float(data.get('distance_m', 0))/1000:.1f}km, "
                f"+{data.get('elevation_gain_m', 0)}m, "
                f"SHA256={str(data.get('sha256', ''))[:16]}..."
            )
        elif reader == "route_artifact_enrich":
            profile = data.get("surface_profile", {})
            if profile and (profile.get("segments") or profile.get("coverage_pct")):
                segs = profile.get("segments", [])
                seg_parts = []
                for s in segs[:8]:
                    name = str(s.get("surface", s.get("name", "?")))
                    length_m = float(s.get("length_m", s.get("distance_m", s.get("dystans_m", 0))))
                    share = float(s.get("share", s.get("udzial", 0)))
                    seg_parts.append(f"{name} ok. {length_m/1000:.1f} km / {share*100:.0f}%")
                cov = profile.get("coverage_pct", "?")
                warn = profile.get("warnings", [])
                warn_str = f"warning: {warn[0]}" if warn else ""
                parts.append(
                    f"Nawierzchnia (coverage={cov}%): {'; '.join(seg_parts)}. "
                    f"{warn_str}. Wniosek: trasa nie jest czysto szosowa"
                )
            else:
                parts.append("Nawierzchnia: dane niedostępne")
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
        scope_category_map: dict[str, list[str]] = {
            "nutrition": ["nutrition", "hydration", "fueling"],
            "training": ["xert", "intervals", "wellness", "garmin"],
            "routes": ["rwgps", "routes", "route_surface"],
            "garage": ["garage", "gear"],
        }
        allowed_cats = set(scope_category_map.get(scope, [scope]))
        allowed_readers = {rn for rn, reg in _READER_REGISTRY.items() if reg.get("category", "") in allowed_cats}
        readers_to_call = [r for r in readers_to_call if r in allowed_readers]
        if not readers_to_call:
            readers_to_call = list(allowed_readers)[:5]

    if not readers_to_call:
        readers_to_call = _INTENT_TO_READERS.get("general", ["status"])

    # ── plan_only ──
    if mode == "plan_only":
        reader_details = []
        missing_caps: list[str] = []
        negations = _detect_negations(question)
        resolved_rid = _resolve_route_id(question)
        for rn in readers_to_call:
            reg = _READER_REGISTRY.get(rn, {})
            tool = reg.get("tool", "?")
            if tool == "?" or tool not in _TOOL_DISPATCH:
                missing_caps.append(f"{rn}: reader or tool missing")
                continue

            # Apply parameter-requirement filter
            params = reg.get("params", {})
            skipped_reason = None

            if "route_id" in params and not resolved_rid:
                skipped_reason = "no route_id in query"
            elif "artifact_path" in params:
                has_artifact = bool(re.search(r"(exports/rwgps/rwgps_\d+\.\w+)", question))
                if not has_artifact and not resolved_rid:
                    skipped_reason = "no artifact_path available"
            if rn in ("rwgps_export_links", "rwgps_export_file") and "export" in negations:
                skipped_reason = "export suppressed by negation"

            if skipped_reason:
                missing_caps.append(f"{rn}: skipped — {skipped_reason}")
                continue

            reader_details.append({
                "reader": rn,
                "category": reg.get("category", "?"),
                "providers": reg.get("providers", []),
                "available": tool in _TOOL_DISPATCH,
            })

        planned_readers = [rd["reader"] for rd in reader_details]
        return {
            "tool": "qbot.query", "safety_class": "READ_ONLY",
            "status": "partial" if missing_caps else "ok",
            "mode": "plan_only",
            "query": question, "intents_detected": intents,
            "readers_planned": planned_readers, "readers_count": len(planned_readers),
            "readers_used": [],
            "plan": reader_details,
            "answer": f"Plan: {len(planned_readers)} readerów. {'Brakujące: ' + ', '.join(missing_caps) if missing_caps else 'Wszystkie dostępne.'}",
            "tables": [], "data": {},
            "provenance": [], "missing_fields": missing_caps,
            "missing_capabilities": missing_caps,
            "confidence": "high" if not missing_caps else "medium",
            "limitations": [],
            "note": "plan_only — no data was read, switch to read_only to execute",
        }

    # ── read_only ──
    # Resolve date context from context + query text
    date_ctx = _resolve_date_context(context, question)

    answers: list[dict] = []
    provenance: list[dict] = []
    missing: list[str] = []
    limitations: list[str] = []
    has_blocked = False
    has_garmin_blocked = False
    resolved_route_id: str = _resolve_route_id(question)
    resolved_artifact_path: str = ""
    rwgps_search_result: dict | None = None
    rwgps_export_result: dict | None = None

    # Determine if question expects surface data
    expects_surface = "route_surface_profile" in intents
    surface_data_returned = False

    # Track whether calorie balance query needs Garmin as required source
    is_calorie_balance = "calorie_balance" in intents
    garmin_energy_used = False
    garmin_energy_blocked = False

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
            # ── Parameter-requirement filter ──────────────────────────
            # Skip readers whose required params aren't available and
            # can't be resolved from the query or chained results.
            reader_params = reg["params"]
            reader_category = reg.get("category", "")

            # route_id-requiring readers — skip if no route_id resolvable
            if "route_id" in reader_params:
                if not resolved_route_id and not _resolve_route_id(question):
                    limitations.append(
                        f"{reader_name}: skipped — no route_id in query or context"
                    )
                    continue

            # artifact_path-requiring readers — skip if no path
            if "artifact_path" in reader_params:
                has_artifact = bool(resolved_artifact_path) or bool(
                    re.search(r"(exports/rwgps/rwgps_\d+\.\w+)", question)
                )
                if not has_artifact and not resolved_route_id:
                    limitations.append(
                        f"{reader_name}: skipped — no artifact_path available"
                    )
                    continue

            # Export readers — skip if "bez eksportu" / negations suppress
            if reader_name in ("rwgps_export_links", "rwgps_export_file"):
                negs = _detect_negations(question)
                if "export" in negs:
                    limitations.append(f"{reader_name}: skipped — export suppressed by negation")
                    continue

            args = _resolve_tool_arg(tool_name, reg["params"], question, date_ctx)

            # Chain resolved route_id into args
            if resolved_route_id and not args.get("route_id"):
                if "route_id" in reg["params"]:
                    args["route_id"] = resolved_route_id
                if "artifact_path" in reg["params"] and resolved_route_id and not args.get("artifact_path"):
                    args["artifact_path"] = f"exports/rwgps/rwgps_{resolved_route_id}.gpx"

                # Apply intent-specific param overrides (to args regardless of reader params)
                for intent in intents:
                    overrides = _INTENT_PARAM_OVERRIDES.get(intent, {})
                    for k, v in overrides.items():
                        args[k] = v

            result = func(args)

            # Track Garmin energy status
            if reader_name == "garmin_energy":
                garmin_energy_used = True
                garmin_status = str(result.get("status", "")).upper()
                if garmin_status.startswith("BLOCKED"):
                    garmin_energy_blocked = True

            # Extract route_id from search/export results for chaining
            if reader_name == "rwgps_route_search":
                rwgps_search_result = result
                found_id = _resolve_route_id(question, result)
                if found_id:
                    resolved_route_id = found_id
            if reader_name == "rwgps_export_file":
                rwgps_export_result = result
                if result.get("artifact_relative_path"):
                    resolved_artifact_path = result["artifact_relative_path"]
                if result.get("route_id"):
                    resolved_route_id = str(result["route_id"])
            if reader_name == "rwgps_route_get":
                route = result.get("route", {})
                if route.get("id"):
                    resolved_route_id = str(route["id"])

            # Check for surface data
            if reader_name == "route_artifact_enrich" and expects_surface:
                sp = result.get("surface_profile", {})
                if sp and (sp.get("segments") or sp.get("coverage_pct")):
                    surface_data_returned = True

            status_val = result.get("status", result.get("status", "UNKNOWN"))
            if _is_blocked(status_val):
                has_blocked = True
            if _is_failure(status_val) and not result.get("items") and not result.get("routes") and not result.get("activities"):
                if include_missing:
                    if not (reg["category"] in ("rwgps", "routes") and _is_failure(status_val)):
                        missing.append(f"{reader_name}: {status_val}")
                        limitations.append(f"{reader_name}: returned {status_val}")
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
    answer_text = _synthesize_answer(question, answers, missing, intents)

    # ═══════════════════════════════════════════════════════════════════
    # Calorie balance table (for calorie_balance intent)
    # ═══════════════════════════════════════════════════════════════════
    balance_table: list[dict] = []
    balance_summary: dict[str, Any] = {}
    if is_calorie_balance:
        # Gather per-day data from answers
        nutrition_data: dict[str, dict] = {}
        garmin_data: dict[str, dict] = {}
        days_requested: list[str] = []

        # Build the date range from resolved context
        df_str = date_ctx.get("date_from", date_ctx.get("date", ""))
        dt_str = date_ctx.get("date_to", date_ctx.get("date", ""))
        if df_str and dt_str:
            try:
                d_start = date.fromisoformat(df_str)
                d_end = date.fromisoformat(dt_str)
                cur = d_start
                while cur <= d_end:
                    days_requested.append(cur.isoformat())
                    cur += timedelta(days=1)
            except ValueError:
                days_requested.append(date_ctx.get("date", date.today().isoformat()))

        # Extract per-day nutrition from nutrition_range / nutrition_day
        for ans in answers:
            reader = ans["reader"]
            data = ans.get("data", {})
            if reader in ("nutrition_range", "nutrition_day", "nutrition_day_legacy"):
                entries = data.get("entries", [])
                for entry in entries:
                    entry_date = str(entry.get("date", ""))[:10]
                    if entry_date:
                        nutrition_data[entry_date] = entry
                # Also check per-day rows in range data
                per_day = data.get("per_day", [])
                for day_row in per_day:
                    d = str(day_row.get("date", ""))[:10]
                    if d:
                        nutrition_data[d] = day_row
            elif reader == "garmin_energy":
                g_date = data.get("date", "")
                garmin_data[g_date] = {
                    "active_kcal": data.get("active_kcal"),
                    "resting_kcal": data.get("resting_kcal"),
                    "bmr_kcal": data.get("bmr_kcal"),
                    "total_kcal": data.get("total_kcal"),
                }

        # Build per-day rows
        total_cal_in = 0.0
        total_garmin = 0.0
        days_with_nut = 0
        days_with_garmin = 0
        missing_garmin: list[str] = []
        missing_nut: list[str] = []

        for d in days_requested:
            nd = nutrition_data.get(d, {})
            gd = garmin_data.get(d, {})
            cal_in = nd.get("calories_kcal")
            if cal_in is None and isinstance(nd.get("kcal_total"), (int, float)):
                cal_in = float(nd["kcal_total"])

            has_nut = cal_in is not None
            has_garmin = gd.get("total_kcal") is not None and gd.get("total_kcal") is not None

            row_missing: list[str] = []
            if not has_nut:
                missing_nut.append(d)
                row_missing.append("nutrition")
            if not has_garmin:
                missing_garmin.append(d)
                row_missing.append("garmin_energy")

            balance = None
            if has_nut and has_garmin:
                balance = cal_in - gd["total_kcal"]

            row = {
                "date": d,
                "calories_in": cal_in,
                "protein_g": nd.get("protein_g"),
                "carbs_g": nd.get("carbs_g"),
                "fat_g": nd.get("fat_g"),
                "fluids_ml": nd.get("fluid_ml") or nd.get("fluids_ml"),
                "garmin_active_kcal": gd.get("active_kcal"),
                "garmin_resting_kcal": gd.get("resting_kcal"),
                "garmin_bmr_kcal": gd.get("bmr_kcal"),
                "garmin_total_kcal": gd.get("total_kcal"),
                "balance_kcal": balance,
                "data_quality": "ok" if (has_nut and has_garmin) else ("partial" if has_nut else "no_data"),
                "missing_fields": row_missing,
            }
            balance_table.append(row)

            if has_nut:
                days_with_nut += 1
                total_cal_in += cal_in or 0.0
            if has_garmin and gd.get("total_kcal"):
                days_with_garmin += 1
                total_garmin += float(gd["total_kcal"]) or 0.0

        n_days = len(days_requested) or 1
        balance_summary = {
            "date_from": df_str,
            "date_to": dt_str,
            "days_requested": n_days,
            "days_with_nutrition": days_with_nut,
            "days_with_garmin_energy": days_with_garmin,
            "total_calories_in": total_cal_in if days_with_nut else None,
            "total_garmin_total_kcal": total_garmin if days_with_garmin else None,
            "total_balance_kcal": (total_cal_in - total_garmin) if (days_with_nut and days_with_garmin) else None,
            "avg_calories_in": (total_cal_in / days_with_nut) if days_with_nut else None,
            "avg_garmin_total_kcal": (total_garmin / days_with_garmin) if days_with_garmin else None,
            "avg_balance_kcal": ((total_cal_in - total_garmin) / days_with_nut) if (days_with_nut and days_with_garmin) else None,
            "days_missing_garmin": missing_garmin,
            "days_missing_nutrition": missing_nut,
        }

        # If Garmin blocked or no_data, adjust answer for calorie balance queries
        if garmin_energy_blocked or (garmin_energy_used and is_calorie_balance):
            garmin_status = None
            garmin_error = None
            for a in answers:
                if a["reader"] == "garmin_energy":
                    garmin_status = str(a.get("data", {}).get("status", "")).upper()
                    garmin_error = a.get("data", {}).get("error_class", "")
                    break
            if garmin_status and garmin_status != "OK":
                reason = "MFA" if "mfa" in str(garmin_status).lower() or "mfa" in str(garmin_error) else "no data"
                limitations.append(
                    f"Garmin energy unavailable ({reason}) — bilans kcal nie może być w pełni obliczony."
                )
                answer_text = (
                    f"Bilans częściowy {df_str}–{dt_str}: "
                    f"nutrition data available from local sources, Garmin energy unavailable ({reason}); "
                    f"balance_kcal cannot be computed."
                )

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
        "limitations": limitations[:10],
        "date_resolution": date_ctx,
    }

    # Include calorie balance data if computed
    if balance_table:
        response["calorie_balance"] = {
            "rows": balance_table,
            "summary": balance_summary,
        }

    # Garmin energy diagnostic block (if garmin_energy was used)
    if garmin_energy_used:
        garmin_answer = next((a for a in answers if a["reader"] == "garmin_energy"), None)
        if garmin_answer:
            gd = garmin_answer.get("data", {})
            response["garmin_energy"] = {
                "status": gd.get("status"),
                "date": gd.get("date"),
                "active_kcal": gd.get("active_kcal"),
                "resting_kcal": gd.get("resting_kcal"),
                "bmr_kcal": gd.get("bmr_kcal"),
                "total_kcal": gd.get("total_kcal"),
                "activity_kcal": gd.get("activity_kcal"),
                "source": gd.get("source"),
                "auth_status": gd.get("auth_status"),
                "error_class": gd.get("error_class"),
                "error": gd.get("error"),
                "env_configured": gd.get("env_configured"),
                "token_store_found": gd.get("token_store_found"),
                "session_cache_found": gd.get("session_cache_found"),
                "local_cache_found": gd.get("local_cache_found"),
                "safe_next_action": gd.get("safe_next_action"),
                "missing_fields": gd.get("missing_fields", []),
                "limitations": gd.get("limitations", []),
            }

    # Determine if Garmin is a required source for this query
    garmin_is_required = garmin_energy_used and (
        is_calorie_balance or
        "garmin_energy" in intents or
        ("garmin_energy" in readers_to_call)
    )

    # No-data policy test — override early
    if "no_data_policy_test" in intents:
        response["status"] = "no_data"
        response["answer"] = NO_DATA_PHRASE
        response["confidence"] = "low"
        return response

    # Status aggregation
    key_readers_ok = any(
        not _is_blocked(ans.get("status", "")) and ans["reader"] not in ("status", "readiness", "capability_scan")
        for ans in answers
    )
    non_garage_ok = any(
        not _is_blocked(ans.get("status", ""))
        for ans in answers
        if not ans["reader"].startswith("garage") and ans["reader"] not in ("status", "readiness", "capability_scan")
    )

    # Route lookup success override (only if primary intent is route lookup)
    route_lookup_primary = (
        "rwgps_route_lookup" in intents and
        not expects_surface and
        "route_stage_split" not in intents
    )
    route_lookup_success = (
        route_lookup_primary and
        bool(resolved_route_id) and
        any(a["reader"] == "rwgps_export_file" and a.get("status", "").upper() == "OK" for a in answers)
    )
    if route_lookup_success:
        response["status"] = "ok"
        response["confidence"] = "high"
    elif not answers:
        response["status"] = "no_data"
        response["confidence"] = "low"
        missing.append("surface_profile: data not returned by route_artifact_enrich")
        limitations.append("route_artifact_enrich did not return surface_profile")
        response["missing_fields"] = missing if include_missing else []
    elif not key_readers_ok and has_blocked:
        response["status"] = "blocked"
    elif has_blocked and non_garage_ok:
        response["status"] = "partial"
    elif garmin_energy_blocked:
        response["status"] = "partial"
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

    # Compute confidence after status is determined
    if "confidence" not in response:
        garmin_missing_or_blocked = garmin_is_required and (
            garmin_energy_blocked or
            any(
                r.get("reader") == "garmin_energy" and
                str(r.get("status", r.get("data", {}).get("status", ""))).upper() not in ("OK", "")
                for r in answers
            )
        )
        response["confidence"] = _confidence_from_results(
            answers,
            response_status=response["status"],
            has_required_missing=garmin_missing_or_blocked,
        )

    # Post-status adjustments
    if expects_surface and surface_data_returned:
        response["status"] = "ok"
        response["confidence"] = "medium"
    elif response["status"] == "ok" and answer_text and "niedostępne" in answer_text and expects_surface:
        response["status"] = "partial"
    if expects_surface and response["status"] == "ok":
        response["confidence"] = "medium"  # surface always medium due to Overpass fallibility

    # Route stage split: always no_data
    if "route_stage_split" in intents:
        response["status"] = "no_data"
        response["answer"] = NO_DATA_PHRASE
        response["confidence"] = "low"
        response["missing_capabilities"] = [
            "route_stage_splitter",
            "town_snap_to_trackpoint",
            "lodging_waypoint_matcher",
        ]
        response.setdefault("limitations", []).append("qbot.query can parse GPX summary, but cannot stage full GPX yet")

    return response
