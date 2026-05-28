#!/usr/bin/env python3
"""QBot Query Router v2 — universal read-only MCP tool.

TOSKANIA 2026 / QBot MCP v2 — intent classification, reader dispatch,
structured output with answer, tables, provenance, no-data policy.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import uuid
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from datetime import date, datetime, timedelta
from pathlib import Path
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
        "ile spaliłem", "ile spalilem", "spaliłem dzisiaj", "spalilem dzisiaj",
        "ile kcal out", "kcal out dzisiaj", "wydatek energetyczny",
        "na deficycie", "deficycie", "nadwyżkę", "nadwyzke",
        "bilans netto", "bilans energetyczny",
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
    ("artifact_read", [
        "plik", "artefakt", "artifact", "csv",
        "biblia qbot", "qbot bible", "qbot_bible", "bible qbot",
        "know-how qbot", "knowhow qbot", "qbot_knowhow", "know how qbot",
        "instrukcja projektu qbot", "qbot_project_instruction_local",
        "instrukcja lokalna qbot", "lokalna instrukcja projektu qbot",
        "architektura qbot", "zasady mcp", "mcp qbot",
        "dokumenty kanoniczne qbot", "dokumenty kanoniczne", "kanoniczne qbot",
        "przeczytaj dokumenty kanoniczne qbot", "czy ten problem był już rozwiązany",
        "czy ten problem byl juz rozwiazany",
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
    # ── Write intents (draft only) ────────────────────────────────────
    ("nutrition_log_add_draft", [
        "dodaj do dzisiejszego spożycia", "dodaj do spożycia",
        "zapisz posiłek", "dodaj jedzenie",
        "dodaj do jedzenia", "dodaj posiłek",
        "dopisz do dzisiejszego jedzenia", "dopisz do jedzenia",
        "dodaj dzisiaj dietę", "dodaj dzisiaj",
        "dopisz dzisiaj", "zapisz dzisiaj",
        "dodaj dietę", "dopisz dietę", "zapisz dietę",
    ]),
    ("qcal_reminder_add_draft", [
        "przypomnij mi", "dodaj przypomnienie",
        "ustaw przypomnienie",
    ]),
    ("deadline_task_draft", [
        r"muszę.+do ", r"trzeba.+do ", r"mam\s+\w+\s+.*do ",
        r"muszę.+na ", r"trzeba.+na ",
    ]),
    ("qcal_event_add_draft", [
        "dodaj wydarzenie", "zapisz event", "dodaj event",
        "mam wizytę", "mam spotkanie",
    ]),
    ("qcal_event_cancel_draft", [
        "usuń event", "usuń wydarzenie", "anuluj event", "anuluj wydarzenie",
        "odwołaj wydarzenie", "odwołaj event", "skasuj wydarzenie", "skasuj event",
        "usuń event o id", "usuń wydarzenie o id",
    ]),
    ("qcal_event_update_draft", [
        "zmień datę", "zmień godzinę", "zmień opis", "zmień nazwę",
        "popraw datę", "popraw godzinę", "popraw opis",
        "przesuń wydarzenie", "przesuń event",
        "edytuj wydarzenie", "edytuj event",
    ]),
    # General intents
    ("nutrition_planning", [
        "ułóż mi jadłospis", "ułóż jadłospis", "zaplanuj jedzenie",
        "jadłospis", "ile mogę jeszcze zjeść", "dieta na dziś",
        "zaplanuj dietę", "plan posiłków", "meal plan",
        "rozpisz jedzenie", "rozplanuj posiłki", "co mogę zjeść",
        "zaplanuj mi jedzenie", "ułóż mi dietę",
        "co powinienem zjeść", "co zjeść przed",
    ]),
    ("saved_meals_catalog", [
        "zdefiniowane posiłki", "moje posiłki", "szablony posiłków",
        "standardowe posiłki", "posiłki z cronometer",
        "posiłki przeniesione z cronometer", "templates",
        "co to jest dieta", "pokaż zapisany posiłek",
        "znajdź posiłek", "znajdz posilek",
        "pokaż szablon", "pokaż template",
        "wyszukaj w posiłkach", "szukam w posiłkach",
        "wylistuj zapisane", "lista zapisanych", "zapisane posiłki",
        "zapisany posiłek", "lista posiłków",
    ]),
    ("food_link_audit", [
        "bez food_item_id", "niepołączone wpisy", "logi bez produktu",
        "niepołączone produkty", "food_item_id null",
        "audyt produktów", "bez produktu",
    ]),
    ("current_day_meals", [
        # empty — handled by canonicalize_query_intent() semantic classifier
    ]),
    ("nutrition_daily", [
        "bilans kalorii", "kalorii", "kcal", "zjadł", "zjedzone", "posiłk",
        "co jadł", "co zjadł", "dieta", "makro", "żywieni", "nutrition",
        "carbs", "białko", "tłuszcz", "węglowodan",
        "zjadlem", "zjadłam", "jadlem", "jadłam", "jadl", "jedzeni",
        "przed treningiem", "zjeść na trening", "jedzenie przed",
    ]),
    ("nutrition_range", [
        "kalorii z ostatnich", "w tym tygodniu", "podsumowanie tygodnia",
        "średni", "średnia kalorii", "trend", "7 dni",
        "bilans odżywiania", "bilans odżyw", "saldo kalorii",
    ]),
    ("hydration", [
        "wypi", "płyn", "woda", "nawodnieni", "hydration", "fluids",
    ]),
    ("fueling", [
        "żel", "fueling", "carbs na trasie", "węgli na trasie",
        "węgli przed", "carbs przed", "przed jazdą",
    ]),
    ("planning_notice", [
        "jadę dziś", "planuję trening", "rest day", "dzień odpoczynku",
        "dziś odpoczynek", "dziś wolne", "bez treningu",
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
    ("capability_check", [
        "czy masz", "czy qbot ma", "czy potrafisz", "dane do odpowiedzi",
    ]),
    ("project", [
        "projekt", "kod", "pliki projektu", "repozytorium",
    ]),
    ("health_advice", [
        "health check", "czy moja redukcja", "czy redukcja idzie",
        "czy waga spada", "czy masa spada", "czy chudnę",
        "czy mam za mało białka", "czy powinienem jeść mniej",
        "czy mój trening", "czy regeneracja",
        "zrób health check", "jak idzie redukcja",
        "jaka jest moja forma", "czy dobrze jem",
    ]),
    ("supplement_advice", [
        "czy moja suplementacja", "czy suplementacja ma sens",
        "jakie suplementy", "suplementy mam",
        "kiedy skończy mi się", "kiedy skończy się",
        "ile zostało", "czy mam brać melatoninę",
        "czy brać kreatynę", "suplement",
    ]),
    ("supplement_inventory", [
        "stan suplementów", "inventory suplementów",
        "lista suplementów", "co mam w suplementach",
        "pokaż suplementy",
    ]),
    ("recovery_advice", [
        "czy regeneracja", "jak śpię", "jak mój sen",
        "czy się regeneruję", "czy odpoczywam",
        "czy hrv", "zmęczenie", "przetrenowanie",
    ]),
    ("health_event_log", [
        "przeziębiłem", "przeziębienie", "zachorowałem",
        "jestem chory", "jestem chora", "choroba",
        "złapałem infekcję", "mam katar", "mam gorączkę",
        "mam ból gardła", "kaszel",
    ]),
    ("wellbeing_log", [
        "źle się czuję", "złe samopoczucie", "czuję się źle",
        "słabo się czuję", "rozbity", "rozbita",
        "nie mam energii", "brak energii",
        "czuję się słabo", "brak siły",
    ]),
    ("health_risk_note", [
        "możliwe stany przedcukrzycowe", "stan przedcukrzycowy",
        "ryzyko metaboliczne", "ryzyko sercowo",
        "uwzględniaj to w jedzeniu", "przy planowaniu diety",
    ]),
    ("recovery_anomaly_check", [
        "czy wszystko ok z regeneracją", "sprawdź regenerację",
        "czy hrv ok", "czy sen ok",
        "coś się dzieje z regeneracją",
    ]),
    ("calendar_day_context", [
        "pokaż wszystko co qbot wie o dzisiejszym", "pokaż wszystko co wiesz o",
        "kontekst dnia", "co było", "co qbot wie o",
        "dzienny kontekst", "jak wygląda dzień", "co jest dziś",
        "co mam dziś zaplanowane", "pokaż dzisiejszy",
        "przypomnienia na dziś", "eventy na dziś",
    ]),
    ("daily_timeline", [
        "oś czasu", "timeline", "co się działo",
        "historia dnia", "podsumowanie dnia",
    ]),
    ("reminder_status", [
        "jakie mam przypomnienia", "przypomnienia",
        "czy mam dziś przypomnienia",
    ]),
    ("event_lookup", [
        "jakie eventy", "jakie wydarzenia",
        "eventy zapisane", "co jest zaplanowane na",
    ]),
    ("status", [
        "status qbot", "jaki jest status", "czy wszystko działa",
        "system status", "smoke test", "czy qbot działa",
        "health check", "czy serwer chodzi", "czy api żyje",
    ]),
    ("readiness", [
        "readiness qbot", "gotowość", "gotowość qbot",
        "czy integracje działają", "czy api dostępne",
        "raport gotowości", "blockery", "readiness report",
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
            # Check if keyword contains regex metacharacters
            if any(c in kw for c in '.*+?[](){}^$\\|'):
                try:
                    if re.search(kw, q):
                        intents.append(intent)
                        break
                except re.error:
                    pass
            elif kw in q:
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

# Health advisor readers
_reader("health_advisor", "health", "qbot_health_advisor_check", {"period": "int"}, ["health_db", "nutrition_db", "supplement_db"])
_reader("supplement_inventory", "health", "qbot_health_supplement_inventory", {}, ["health_db"])
_reader("weight_advisor", "health", "qbot_health_weight_advice", {}, ["health_db", "weight_history"])
_reader("recovery_advisor", "health", "qbot_health_recovery_advice", {}, ["health_db", "garmin_api", "intervals_api"])

# Calendar core reader
_reader("calendar_snapshot", "calendar", "qbot_calendar_snapshot", {"date": "str"}, ["calendar_daily_snapshots", "calendar_core"])

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
_reader("qbot_canonical_docs", "project", "qbot_canonical_docs_read", {"query": "str"}, ["filesystem", "docs"])

# New: Garmin energy reader (live read via garminconnect, no DB storage needed)
_reader("garmin_energy", "garmin", "qbot_garmin_energy_read", {"date": "str"}, ["garminconnect_api"])

# New: Intervals activities reader
_reader("intervals_activities", "intervals", "qbot_intervals_activities_read", {"date": "str"}, ["intervals_api"])


# ── Intent → reader mapping ────────────────────────────────────────────────

_INTENT_TO_READERS: dict[str, list[str]] = {
    "calorie_balance": ["nutrition_range", "nutrition_day", "garmin_energy", "cronometer_status", "wellness_range", "nutrition_day_legacy", "nutrition_status"],
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
    "meal_log_inventory": [],
    "training_load": ["xert_readiness", "intervals_wellness"],
    "xert": ["xert_readiness", "xert_config"],
    "intervals": ["intervals_wellness", "intervals_config", "wellness_day", "intervals_activities"],
    "weather": ["weather_current", "weather_forecast"],
    "rwgps_route_list_only": ["rwgps_route_list"],
    "rwgps_route": ["rwgps_route_get", "rwgps_route_list", "gpx_artifact_parse", "route_artifact_enrich"],
    "rwgps_search": ["rwgps_route_search", "rwgps_route_list"],
    "rwgps_export": ["rwgps_export_links", "rwgps_route_get"],
    "route_surface": ["route_artifact_enrich", "gpx_artifact_parse"],
    "garage": ["garage_search", "garage_list", "garage_status"],
    "daily_report": ["daily_report_preview"],
    "ride_report": ["ride_report_preview", "ride_report_latest"],
    "wellness": ["wellness_day", "sleep_day", "nutrition_day_legacy", "garmin_status", "wellness_range"],
    "artifact_read": ["qbot_canonical_docs"],
    "capability_check": ["status", "capability_scan"],
    "project": [],
    "health_advice": ["health_advisor", "nutrition_day", "meal_list", "nutrition_planning", "supplement_inventory", "garmin_energy", "wellness_day", "garmin_status", "intervals_wellness"],
    "supplement_advice": ["supplement_inventory", "health_advisor"],
    "supplement_inventory": ["supplement_inventory"],
    "recovery_advice": ["recovery_advisor", "wellness_day", "sleep_day"],
    "health_event_log": ["health_advisor", "wellness_day"],
    "wellbeing_log": ["health_advisor", "wellness_day"],
    "health_risk_note": ["health_advisor"],
    "recovery_anomaly_check": ["recovery_advisor", "wellness_day", "sleep_day"],
    "calendar_day_context": ["calendar_snapshot", "nutrition_day", "meal_list", "health_advisor", "recovery_advisor"],
    "daily_timeline": ["calendar_snapshot", "wellness_day"],
    "reminder_status": ["calendar_snapshot"],
    "event_lookup": ["calendar_snapshot", "health_advisor"],
    "status": ["status"],
    "readiness": ["readiness", "xert_readiness"],
    "general": ["status", "readiness"],
    # Write intents (no readers — handled by draft pipeline)
    "nutrition_log_add_draft": [],
    "qcal_reminder_add_draft": [],
    "deadline_task_draft": [],
    "qcal_event_add_draft": [],
    "qcal_event_cancel_draft": [],
    "qcal_event_update_draft": [],
    # Planning intents (no readers — handled by planning_fact_drafts)
    "planning_notice": [],
    # Semantic-handled intents (no readers — planner handles via resolve_context)
    "saved_meals_catalog": [],
    "food_link_audit": [],
    # Daily meal log intents
    "current_day_meals": ["meal_list", "nutrition_day"],
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

    # New: Health advisor readers (read-only)
    _TOOL_DISPATCH["qbot_health_advisor_check"] = _read_health_advisor
    _TOOL_DISPATCH["qbot_health_supplement_inventory"] = _read_supplement_inventory
    _TOOL_DISPATCH["qbot_health_weight_advice"] = _read_weight_advice
    _TOOL_DISPATCH["qbot_health_recovery_advice"] = _read_recovery_advice

    # New: Recovery anomaly check reader
    _TOOL_DISPATCH["qbot_health_recovery_anomaly_check"] = _read_recovery_anomaly

    # New: Calendar snapshot reader
    _TOOL_DISPATCH["qbot_calendar_snapshot"] = _read_calendar_snapshot

    # Canonical QBot docs reader
    _TOOL_DISPATCH["qbot_canonical_docs_read"] = _read_qbot_canonical_docs


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

        # Persist to daily_energy_expenditure for future queries
        try:
            from qbot_energy_store import ensure_daily_energy_expenditure
            ensure_daily_energy_expenditure(day_str, reason="garmin_energy_read")
        except Exception:
            pass

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


def _read_health_advisor(args: dict | None = None) -> dict[str, Any]:
    from qbot_health_advisor import advisor_check
    period = int((args or {}).get("period", 14))
    return advisor_check(period)


def _read_supplement_inventory(args: dict | None = None) -> dict[str, Any]:
    from qbot_health_advisor import supplement_inventory_report
    return supplement_inventory_report()


def _read_weight_advice(args: dict | None = None) -> dict[str, Any]:
    from qbot_health_advisor import _weight_advice
    r = _weight_advice()
    r["tool"] = "qbot_health_weight_advice"
    r["safety_class"] = "READ_ONLY"
    r["status"] = "OK"
    return r


def _read_recovery_advice(args: dict | None = None) -> dict[str, Any]:
    from qbot_health_advisor import _recovery_advice
    r = _recovery_advice()
    r["tool"] = "qbot_health_recovery_advice"
    r["safety_class"] = "READ_ONLY"
    r["status"] = "OK"
    return r


def _read_recovery_anomaly(args: dict | None = None) -> dict[str, Any]:
    from qbot_health_advisor import recovery_anomaly_check
    return recovery_anomaly_check()


def _read_planning_constraints(args: dict | None = None) -> dict[str, Any]:
    from qbot_health_advisor import get_planning_constraints
    r = get_planning_constraints()
    r["tool"] = "qbot_health_planning_constraints"
    r["safety_class"] = "READ_ONLY"
    r["status"] = "OK"
    return r


def _read_calendar_snapshot(args: dict | None = None) -> dict[str, Any]:
    from qbot_calendar_core import build_snapshot
    day = (args or {}).get("date", date.today().isoformat())
    snap = build_snapshot(day)
    snap["tool"] = "qbot_calendar_snapshot"
    snap["safety_class"] = "READ_ONLY"
    snap["status"] = "OK"
    return snap


_QBOT_CANONICAL_DOCS: list[dict[str, Any]] = [
    {
        "key": "bible",
        "label": "QBOT_BIBLE",
        "title": "QBot Bible",
        "path": Path("/opt/qbot/docs/QBOT_BIBLE.md"),
        "aliases": (
            "biblia qbot",
            "qbot_bible",
            "qbot bible",
            "bible qbot",
            "architektura qbot",
            "zasady mcp",
            "mcp qbot",
        ),
    },
    {
        "key": "knowhow",
        "label": "QBOT_KNOWHOW",
        "title": "QBot Know-how",
        "path": Path("/opt/qbot/docs/QBOT_KNOWHOW.md"),
        "aliases": (
            "know-how qbot",
            "knowhow qbot",
            "qbot_knowhow",
            "know how qbot",
            "czy ten problem był już rozwiązany",
            "czy ten problem byl juz rozwiazany",
            "telegram 404",
        ),
    },
    {
        "key": "project_instruction",
        "label": "QBOT_PROJECT_INSTRUCTION_LOCAL",
        "title": "QBot Project Instruction",
        "path": Path("/opt/qbot/docs/QBOT_PROJECT_INSTRUCTION_LOCAL.md"),
        "aliases": (
            "instrukcja projektu qbot",
            "qbot_project_instruction_local",
            "lokalna instrukcja projektu qbot",
            "przeczytaj lokalną instrukcję projektu qbot",
            "przeczytaj lokalna instrukcje projektu qbot",
        ),
    },
]


def _safe_read_markdown(path: Path) -> str:
    try:
        if not path.exists() or not path.is_file():
            return ""
        if path.stat().st_size > 300_000:
            return ""
        text = path.read_text(encoding="utf-8", errors="ignore")
        return text if "\x00" not in text else ""
    except Exception:
        return ""


def _query_terms(question: str) -> list[str]:
    raw = re.findall(r"[A-Za-zÀ-ÿ0-9_ąćęłńóśźżĄĆĘŁŃÓŚŹŻ-]+", question.lower())
    stopwords = {
        "a", "i", "oraz", "lub", "w", "na", "do", "z", "ze", "o", "u", "dla", "ten",
        "ta", "to", "te", "przeczytaj", "sprawdź", "sprawdz", "podaj", "pokaż",
        "pokaz", "czy", "jest", "był", "byl", "już", "juz", "jak", "the", "and",
        "of", "for", "with", "czytaj", "dla",
    }
    return [w for w in raw if len(w) >= 3 and w not in stopwords]


def _doc_headings(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            headings.append(stripped.lstrip("#").strip())
        if len(headings) >= 12:
            break
    return headings


def _doc_summary(text: str, headings: list[str]) -> str:
    first_heading = headings[0] if headings else "Dokument QBot"
    paragraphs: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            if len(paragraphs) >= 2:
                break
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith(("-", "*")):
            current.append(stripped.lstrip("-* ").strip())
        else:
            current.append(stripped)
    if current and len(paragraphs) < 2:
        paragraphs.append(" ".join(current).strip())

    body = paragraphs[0] if paragraphs else ""
    body = re.sub(r"\s+", " ", body).strip()
    if len(body) > 240:
        body = body[:237].rstrip() + "..."
    summary = first_heading
    if body:
        summary = f"{summary}: {body}"
    if len(headings) > 1:
        extra = ", ".join(headings[1:4])
        summary = f"{summary} | sekcje: {extra}"
    return summary


def _doc_excerpts(text: str, question: str) -> list[str]:
    terms = _query_terms(question)
    lines = [line.rstrip() for line in text.splitlines()]
    matches: list[str] = []

    def add_excerpt(line: str) -> None:
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned and cleaned not in matches:
            matches.append(cleaned[:280])

    if terms:
        for idx, line in enumerate(lines):
            lower = line.lower()
            if any(term in lower for term in terms):
                if line.strip().startswith("#"):
                    add_excerpt(line.strip())
                else:
                    start = max(0, idx - 1)
                    end = min(len(lines), idx + 2)
                    for chunk in lines[start:end]:
                        if chunk.strip():
                            add_excerpt(chunk)
                if len(matches) >= 5:
                    break

    if not matches:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                add_excerpt(stripped)
            elif stripped.startswith(("- ", "* ")):
                add_excerpt(stripped)
            if len(matches) >= 5:
                break

    return matches


def _read_canonical_doc(entry: dict[str, Any], question: str) -> dict[str, Any]:
    path: Path = entry["path"]
    text = _safe_read_markdown(path)
    exists = bool(text)
    if not exists:
        return {
            "doc_key": entry["key"],
            "label": entry["label"],
            "title": entry["title"],
            "path": path.as_posix(),
            "exists": False,
            "summary": f"Plik nie istnieje: {path.as_posix()}",
            "matched_excerpts": [],
            "headings": [],
        }
    headings = _doc_headings(text)
    return {
        "doc_key": entry["key"],
        "label": entry["label"],
        "title": entry["title"],
        "path": path.as_posix(),
        "exists": True,
        "summary": _doc_summary(text, headings),
        "matched_excerpts": _doc_excerpts(text, question),
        "headings": headings[:10],
    }


def _select_canonical_docs(question: str) -> list[dict[str, Any]]:
    q = question.lower()
    if any(
        phrase in q
        for phrase in (
            "dokumenty kanoniczne",
            "kanoniczne qbot",
            "przeczytaj dokumenty kanoniczne qbot",
            "przeczytaj dokumenty kanoniczne",
            "read canonical docs",
            "canonical docs",
        )
    ):
        return list(_QBOT_CANONICAL_DOCS)

    selected: list[dict[str, Any]] = []
    for entry in _QBOT_CANONICAL_DOCS:
        if any(alias in q for alias in entry["aliases"]):
            selected.append(entry)
    if selected:
        return selected

    if "bible" in q or "biblia" in q:
        return [_QBOT_CANONICAL_DOCS[0]]
    if "knowhow" in q or "know-how" in q:
        return [_QBOT_CANONICAL_DOCS[1]]
    if "instrukcja" in q or "instruction" in q or "project" in q:
        return [_QBOT_CANONICAL_DOCS[2]]
    return list(_QBOT_CANONICAL_DOCS)


def _read_qbot_canonical_docs(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    question = str(args.get("query") or args.get("question") or "").strip()
    selected = _select_canonical_docs(question or "dokumenty kanoniczne qbot")
    doc_results = [_read_canonical_doc(entry, question) for entry in selected]
    missing = [f"{doc['label']}: missing" for doc in doc_results if not doc["exists"]]

    tables = [{
        "domain": "canonical_docs",
        "key": "canonical_docs",
        "columns": ["label", "path", "exists", "summary"],
        "rows": [
            {
                "label": doc["label"],
                "path": doc["path"],
                "exists": doc["exists"],
                "summary": doc["summary"],
            }
            for doc in doc_results
        ],
    }]

    excerpt_rows = [
        {"label": doc["label"], "excerpt": excerpt}
        for doc in doc_results
        for excerpt in doc["matched_excerpts"][:3]
    ]
    if excerpt_rows:
        tables.append({
            "domain": "canonical_doc_excerpts",
            "key": "canonical_doc_excerpts",
            "columns": ["label", "excerpt"],
            "rows": excerpt_rows,
        })

    summaries = []
    for doc in doc_results:
        state = "brak pliku" if not doc["exists"] else "ok"
        summaries.append(f"- {doc['label']}: {state} | {doc['summary']}")

    answer = "Przeczytałem dokumenty kanoniczne QBot:\n" + "\n".join(summaries)
    status = "partial" if missing else "ok"
    if not doc_results:
        status = "no_data"
        answer = "Brak zdefiniowanych dokumentów kanonicznych."

    return {
        "tool": "qbot_canonical_docs_read",
        "safety_class": "READ_ONLY",
        "status": status,
        "query": question,
        "documents": doc_results,
        "tables": tables,
        "answer": answer,
        "missing_fields": missing,
        "limitations": [
            "read-only filesystem access",
            "summaries are heuristic and derived from markdown structure",
        ],
        "provenance": [
            {"source": doc["path"], "exists": doc["exists"], "label": doc["label"]}
            for doc in doc_results
        ],
    }


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
                    f"Dzisiaj: {round(s.get('kcal_total', 0), 1)} kcal, "
                    f"{round(s.get('carbs_total', 0), 1)}g węgli, "
                    f"{round(s.get('protein_total', 0), 1)}g białka"
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
        elif reader == "health_advisor":
            recs = data.get("recommendations", [])
            warn = data.get("warnings", [])
            conf = data.get("confidence", "?")
            parts.append(
                f"Health check ({data.get('period_days','?')}d): "
                f"{len(recs)} rek., {len(warn)} ostrzeżeń, confidence={conf}"
            )
        elif reader == "supplement_inventory":
            items = data.get("items", [])
            if items:
                names = [i['name'] for i in items[:3]]
                parts.append(f"Suplementy: {len(items)} — {', '.join(names)}")
            else:
                parts.append("Suplementy: brak w inventory")
        elif reader == "weight_advisor":
            recs = data.get("recommendations", [])
            parts.append(f"Waga: {recs[0][:80] if recs else 'brak rekomendacji'}")
        elif reader == "calendar_snapshot":
            score = data.get("_completeness_score", 0) or 0
            sections = []
            for k in ("nutrition", "training", "sleep", "health_events",
                      "supplements", "goals", "reminders"):
                v = data.get(k)
                if isinstance(v, list) and v:
                    sections.append(f"{k}:{len(v)}")
                elif isinstance(v, dict) and v:
                    sections.append(k)
            missing = data.get("_missing_tables", [])
            parts.append(f"Dzień {data.get('date','?')}: completeness={score*100:.0f}%, "
                         f"sekcje: {', '.join(sections) if sections else 'brak'}, "
                         f"braki: {', '.join(missing[:4]) if missing else 'brak'}")
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


_TABLE_DOMAIN: dict[str, str] = {
    "nutrition_planning": "meal_plan_suggestions",
    "nutrition_day": "current_day_summary",
    "nutrition_range": "nutrition_range_summary",
    "nutrition_food_search": "food_catalog",
    "meal_list": "meal_logs",
    "rwgps_route_list": "route_list",
    "rwgps_route_get": "route_detail",
    "rwgps_route_search": "route_search",
    "gpx_artifact_parse": "gpx_summary",
    "route_artifact_enrich": "surface_profile",
    "garage_search": "garage_results",
    "garage_list": "garage_list",
    "intervals_activities": "activities",
    "xert_readiness": "xert_readiness",
    "xert_config": "xert_config",
    "weather_current": "weather",
    "garmin_energy": "garmin_energy",
    "ride_report_latest": "latest_training",
    "ride_report_preview": "ride_preview",
    "daily_report_preview": "daily_report",
    "calendar_snapshot": "calendar_snapshot",
    "health_advisor": "health_check",
    "supplement_inventory": "supplement_inventory",
    "wellness_day": "wellness",
    "sleep_day": "sleep",
}

def _round_row_vals(row: dict) -> dict:
    """Round float values in a row to 1 decimal place."""
    return {k: round(v, 1) if isinstance(v, float) else v for k, v in row.items()}

def _extract_tables(answers: list[dict]) -> list[dict]:
    tables: list[dict] = []
    seen_sigs: set[str] = set()
    for ans in answers:
        data = ans.get("data", {})
        reader = ans["reader"]

        for key in ("activities", "items", "routes", "records", "results", "rows", "meals", "hydration_events", "fueling_events"):
            if isinstance(data.get(key), list) and len(data[key]) > 0:
                rows_raw = data[key][:20]
                rows = [_round_row_vals(r) for r in rows_raw]
                cols = list(rows[0].keys()) if rows else []
                sig = f"{reader}:{cols}" if cols else reader
                if sig in seen_sigs:
                    continue
                seen_sigs.add(sig)
                dom = _TABLE_DOMAIN.get(reader, reader)
                tables.append({"reader": reader, "key": key, "domain": dom, "columns": cols, "count": len(rows), "rows": rows})
                break
        else:
            summary = data.get("summary", {})
            if isinstance(summary, dict) and summary:
                summary_rounded = _round_row_vals(summary)
                cols = list(summary_rounded.keys())
                dom = _TABLE_DOMAIN.get(reader, reader)
                sig = f"{reader}:summary"
                if sig not in seen_sigs:
                    seen_sigs.add(sig)
                    tables.append({"reader": reader, "key": "summary", "domain": dom, "columns": cols, "count": 1, "rows": [summary_rounded]})
    return tables


# ═══════════════════════════════════════════════════════════════════════════
# Write draft handlers (draft only — no actual writes)
# ═══════════════════════════════════════════════════════════════════════════

_WRITER_CAPABILITIES = {
    "nutrition_log_add": "nutrition_log_add",
    "qcal_reminder_add": "qcal_reminder_add",
    "qcal_event_add": "qcal_event_add",
    "qcal_event_cancel": "qcal_event_cancel",
    "qcal_event_update": "qcal_event_update",
}


def _check_writer_capability(cap_name: str) -> dict:
    """Check if a writer capability exists and is ready."""
    from qbot_capabilities import CAPABILITIES
    cap = CAPABILITIES.get(cap_name)
    if not cap:
        return {"exists": False, "status": "missing", "ready": False, "reason": f"capability {cap_name} not registered"}
    status = cap.get("status", "missing")
    return {"exists": True, "status": status, "ready": status == "ready"}


def _generate_idempotency_key(prefix: str, query: str) -> str:
    """Generate a deterministic idempotency key proposal."""
    h = uuid.uuid5(uuid.NAMESPACE_DNS, f"{prefix}:{query.strip().lower()}")
    return f"{prefix}_{h.hex[:16]}"


def _resolve_polish_date(expr: str) -> date | None:
    """Resolve Polish date expressions to date objects."""
    expr_lower = expr.lower().strip()
    today = date.today()

    if expr_lower in ("dziś", "dzisiaj", "dzisiejszego"):
        return today
    if expr_lower in ("jutro", "jutra", "jutrzejszego"):
        return today + timedelta(days=1)
    if expr_lower in ("pojutrze", "pojutrza", "pojutrzejszego"):
        return today + timedelta(days=2)

    weekday_map = {
        "poniedziałek": 0, "poniedziałku": 0, "poniedziałkiem": 0,
        "wtorek": 1, "wtorku": 1, "wtorkiem": 1,
        "środę": 2, "środy": 2, "środą": 2,
        "srodę": 2, "srody": 2, "srodą": 2,
        "czwartek": 3, "czwartku": 3, "czwartkiem": 3,
        "piątek": 4, "piątku": 4, "piątkiem": 4,
        "piatku": 4, "piatkiem": 4,
        "sobota": 5, "sobotę": 5, "soboty": 5, "sobotą": 5,
        "niedziela": 6, "niedzielę": 6, "niedzieli": 6, "niedzielą": 6,
    }

    # "następnego X" → next X
    m = re.search(r'następnego\s+(\w+)', expr_lower, re.IGNORECASE)
    if m:
        day_name = m.group(1).lower()
        target = weekday_map.get(day_name)
        if target is not None:
            days_ahead = target - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return today + timedelta(days=days_ahead)

    # "w X", "we X", "do X", "na X" where X is a weekday
    m = re.search(r'(?:w|we|do|na)\s+(\w+)', expr_lower)
    if m:
        day_name = m.group(1).lower()
        target = weekday_map.get(day_name)
        if target is not None:
            days_ahead = target - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return today + timedelta(days=days_ahead)

    # YYYY-MM-DD
    m = re.search(r'(\d{4}-\d{2}-\d{2})', expr)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass

    return None


def _resolve_polish_time(expr: str) -> str | None:
    """Resolve time expression like 'o 8', 'o 08:00', '20:00', 'za 10 minut'."""
    # Relative: za 10 minut / za 2 godziny / in 10 minutes
    rel = re.search(
        r'\b(?:za|in)\s+(\d{1,3})\s*(minut|minuty|min|minutes?|godzin(?:y|ę)?|godz|hours?)\b',
        expr,
        flags=re.IGNORECASE,
    )
    if rel:
        from datetime import datetime, timedelta
        amount = int(rel.group(1))
        unit = rel.group(2).lower()
        delta = timedelta(hours=amount) if unit.startswith(("godz", "hour")) else timedelta(minutes=amount)
        target = datetime.now() + delta
        return target.strftime("%H:%M")

    for pattern in [
        r'o\s+(\d{1,2})(?::(\d{2}))?\b',
        r'(\d{1,2}):(\d{2})\b',
    ]:
        m = re.search(pattern, expr)
        if m:
            h = int(m.group(1))
            minute = int(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else 0
            if 0 <= h <= 23 and 0 <= minute <= 59:
                return f"{h:02d}:{minute:02d}"
    return None


def _extract_quoted_field(expr: str, field: str) -> str | None:
    """Extract title="..." / title: "..." / message='...' from prompt."""
    m = re.search(
        rf'\b{re.escape(field)}\s*(?:=|:)\s*["\']([^"\']+)["\']',
        expr,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return None


def _extract_meal_name(raw: str) -> str:
    """Clean macro values from raw meal text, return food description."""
    cleaned = re.sub(r'\d+(?:\.\d+)?\s*kcal', '', raw, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b[BWT]\s*\d+(?:\.?\d+)?', '', cleaned)
    cleaned = re.sub(r'białko\s*\d+(?:\.?\d+)?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(?:węgl|węglow|carbs)\w*\s*\d+(?:\.?\d+)?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(?:tłuszcz|fat)\w*\s*\d+(?:\.?\d+)?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+,', ',', cleaned)
    cleaned = re.sub(r',\s+', ', ', cleaned)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip().strip(',').strip()
    return cleaned


def _strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    result = "".join(ch for ch in normalized if unicodedata.category(ch)[0] != 'M')
    # ł (U+0142) is the only Polish letter NFKD doesn't decompose — handle manually
    return result.replace('\u0142', 'l').replace('\u0141', 'L')


def _stem_polish_word(word: str) -> str:
    """Basic Polish stemmer: strips common inflectional suffixes.

    Handles case endings: genitive 'a', locative 'e', plural 'y'/'i',
    dative 'u', etc. Keeps at least 3 characters.
    """
    if len(word) <= 4:
        return word
    # Remove common adjective/noun case suffixes
    for suffix in ["ami", "emi", "ego", "emu", "ych", "ym", "ej", "im",
                   "ie", "ia", "ii", "iu", "om", "ow", "em", "y",
                   "a", "e", "i", "u"]:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            # Don't strip if it would lose the character identity
            stripped = word[:-len(suffix)]
            if len(stripped) >= 3:
                return stripped
    return word


def _normalize_template_text(text: str, *, stem: bool = False) -> str:
    text = _strip_diacritics(str(text or "")).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    stop_words = {
        "dieta", "dieta", "od", "na", "w", "we", "mojej", "moje", "moj", "mojey",
        "bazie", "bazie", "baza", "bazy", "mojejbazy", "zapisy", "zapisane",
        "zapisany", "zapisanych", "szablon", "szablony", "template", "templates",
        "posilek", "posilki", "posilku", "meal", "meals", "co", "to", "jest",
        "w", "m", "mojej", "ma", "moje", "baza", "baze", "my", "from",
        "dodaj", "dzisiaj", "dzisiejszy", "dzisiejszego", "spozycia", "spozycia",
        "jedzenia", "jadzenia", "posilek", "posilku", "zapisz",
        "szukam", "znajdz", "poka", "mam", "na", "mysli",
    }
    tokens = [tok for tok in text.split() if tok not in stop_words]
    if stem:
        tokens = [_stem_polish_word(tok) for tok in tokens]
    result = re.sub(r"\s+", " ", " ".join(tokens)).strip()
    if not result and stem:
        return _normalize_template_text(text, stem=False)
    return result


def _template_keywords(template: dict) -> set[str]:
    name = _normalize_template_text(template.get("name", ""))
    serving = _normalize_template_text(template.get("serving_label", ""))
    notes = _normalize_template_text(template.get("notes", ""))
    kws = {k for k in (name, serving, notes) if k}
    if name:
        parts = name.split()
        kws.update(parts)
        if parts:
            kws.add(" ".join(parts[:1]))
            kws.add(" ".join(parts[:2]))
    return {k for k in kws if k}


# ── Template alias map ─────────────────────────────────────────────────────
# Maps alias → list of template_ids. Length > 1 means ambiguous.
# Built at startup from cache + explicit overrides.
_TEMPLATE_ALIASES: dict[str, list[int]] = {}


def _build_template_aliases() -> dict[str, list[int]]:
    """Build alias map from cached templates.
    Auto-aliases: full name, first word, first two words (all normalized).
    If an auto-alias matches >1 template_id, it becomes ambiguous (len > 1).
    Explicit overrides always win (replace the list for that key).
    """
    aliases: dict[str, list[int]] = {}
    templates = list(_get_meal_templates_cache())
    for tmpl in templates:
        tid = tmpl.get("id")
        if not tid:
            continue
        name = str(tmpl.get("name", "")).strip()
        if not name:
            continue
        norm = _normalize_template_text(name, stem=False)
        auto_keys: list[str] = []
        if norm:
            auto_keys.append(norm)
        parts = norm.split()
        if parts:
            auto_keys.append(parts[0])
        if len(parts) >= 2:
            auto_keys.append(" ".join(parts[:2]))

        for key in auto_keys:
            if key in aliases:
                if tid not in aliases[key]:
                    aliases[key].append(tid)
            else:
                aliases[key] = [tid]

    # Explicit overrides — always win (single-element list)
    explicit: dict[str, int] = {
        "dieta od brokula": 4,
        "dieta brokula": 4,
        "dieta brokul": 4,
        "dieta od brokul": 4,
        "dieta brokula sport": 4,
        "dieta brokul sport": 4,
        "szukam brokula": 4,
        "szukam brokul": 4,
        "poka brokul sport": 4,
        "poka brokula sport": 4,
        "mam na mysli brokul sport": 4,
        "mam na mysli brokula sport": 4,
        "mam na mysli brokul sport 2000": 4,
        "brokula": 4,
        "co to jest dieta od brokula w mojej bazie": 4,
        "co to jest dieta od brokula": 4,
        "dieta od brokula w mojej bazie": 4,
    }
    for key, tid in explicit.items():
        aliases[key] = [tid]

    return aliases


def _alias_match_template(question: str) -> dict | None:
    """Check alias map for a quick template match.
    Returns certain match, ambiguous clarification, or None."""
    templates = list(_get_meal_templates_cache())
    templates_map: dict[int, dict] = {}
    for tmpl in templates:
        tid = tmpl.get("id")
        if tid:
            templates_map[tid] = tmpl

    if not _TEMPLATE_ALIASES:
        _TEMPLATE_ALIASES.update(_build_template_aliases())

    q_norm = _normalize_template_text(question, stem=False)
    q_stem = _normalize_template_text(question, stem=True)
    if not q_norm and not q_stem:
        return None

    # Try full normalized query (both stemmed and unstemmed)
    for variant in [q_norm, q_stem]:
        if variant and variant in _TEMPLATE_ALIASES:
            tids = _TEMPLATE_ALIASES[variant]
            if len(tids) > 1:
                return {
                    "match": False,
                    "ambiguous": True,
                    "score": 0.0,
                    "template": None,
                    "template_id": None,
                    "template_name": None,
                    "candidates": [{
                        "template": templates_map.get(tid),
                        "score": 1.0,
                        "template_id": tid,
                        "template_name": (templates_map.get(tid) or {}).get("name"),
                    } for tid in tids if tid in templates_map],
                    "needs_clarification": True,
                    "source": "alias_ambiguous",
                }
            tid = tids[0]
            if tid in templates_map:
                return {"score": 1.0, "match": True, "template": templates_map[tid],
                        "template_id": tid, "template_name": templates_map[tid].get("name"),
                        "ambiguous": False, "candidates": [], "needs_clarification": False,
                        "source": "alias"}

    # Try each individual token (both stemmed and unstemmed)
    for source in [q_norm, q_stem]:
        if not source:
            continue
        q_tokens = source.split()
        for token in q_tokens:
            if token in _TEMPLATE_ALIASES:
                tids = _TEMPLATE_ALIASES[token]
                if len(tids) > 1:
                    return {
                        "match": False,
                        "ambiguous": True,
                        "score": 0.0,
                        "template": None,
                        "template_id": None,
                        "template_name": None,
                        "candidates": [{
                            "template": templates_map.get(tid),
                            "score": 1.0,
                            "template_id": tid,
                            "template_name": (templates_map.get(tid) or {}).get("name"),
                        } for tid in tids if tid in templates_map],
                        "needs_clarification": True,
                        "source": "alias_token_ambiguous",
                    }
                tid = tids[0]
                if tid in templates_map:
                    return {"score": 0.98, "match": True, "template": templates_map[tid],
                            "template_id": tid, "template_name": templates_map[tid].get("name"),
                            "ambiguous": False, "candidates": [], "needs_clarification": False,
                            "source": "alias_token"}

    return None


@lru_cache(maxsize=1)
def _get_meal_templates_cache() -> tuple[dict, ...]:
    try:
        from qbot_nutrition_db import template_list
        return tuple(template_list(limit=200))
    except Exception:
        return tuple()


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def _fuzzy_token_match(tokens_a: list[str], tokens_b: list[str], threshold: float = 0.7) -> float:
    """Fuzzy token overlap: count stemmed+diacritics-free token matches
    using Levenshtein distance for near-miss tokens."""
    if not tokens_a or not tokens_b:
        return 0.0
    matched = 0
    for ta in tokens_a:
        for tb in tokens_b:
            if ta == tb or ta in tb or tb in ta:
                matched += 1
                break
        else:
            # Try Levenshtein for partial matches
            for tb in tokens_b:
                dist = _levenshtein(ta, tb)
                max_len = max(len(ta), len(tb))
                if max_len > 0 and dist / max_len <= 1.0 - threshold:
                    matched += 1
                    break
    return matched / max(len(tokens_b), 1)


def _score_template_candidate(question: str, template: dict) -> float:
    q = _normalize_template_text(question, stem=True)
    t = _normalize_template_text(template.get("name", ""), stem=True)
    if not q or not t:
        return 0.0

    q_tokens = q.split()
    t_tokens = t.split()
    if q == t:
        return 1.0
    if t in q or q in t:
        return 0.98

    overlap = len(set(q_tokens) & set(t_tokens))
    overlap_score = overlap / max(len(set(t_tokens)), 1)
    fuzzy_score = _fuzzy_token_match(q_tokens, t_tokens)
    seq = SequenceMatcher(None, q, t).ratio()

    score = 0.0
    if overlap:
        score += 0.55 * overlap_score
    else:
        score += 0.30 * fuzzy_score
    score += 0.35 * seq
    if t_tokens and q_tokens and q_tokens[0] == t_tokens[0]:
        score += 0.1
    if len(t_tokens) >= 2 and len(q_tokens) >= 2 and t_tokens[:2] == q_tokens[:2]:
        score += 0.12
    if len(q_tokens) == 1 and q_tokens[0] in t_tokens:
        score += 0.18
    # Bonus: single query token matches start of a template token (stemmed match)
    if len(q_tokens) == 1:
        for tt in t_tokens:
            if tt.startswith(q_tokens[0]) or q_tokens[0].startswith(tt):
                score += 0.10
                break
    return min(score, 1.0)


def _match_meal_template(question: str) -> dict[str, Any] | None:
    templates = list(_get_meal_templates_cache())
    if not templates:
        return None

    # Fast path: alias matching
    alias_result = _alias_match_template(question)
    if alias_result:
        return alias_result

    # Score all templates
    scored: list[dict[str, Any]] = []
    for tmpl in templates:
        score = _score_template_candidate(question, tmpl)
        if score <= 0:
            continue
        scored.append({
            "template": tmpl,
            "score": round(score, 3),
            "template_id": tmpl.get("id"),
            "template_name": tmpl.get("name"),
        })

    if not scored:
        return None

    scored.sort(key=lambda x: (-float(x["score"]), str(x["template_name"]).lower()))
    top = scored[0]
    second = scored[1] if len(scored) > 1 else None
    ambiguity = bool(second and abs(float(top["score"]) - float(second["score"])) < 0.08)

    # Dynamic threshold: 0.86 for multi-token queries, 0.72 for single-token
    q_norm = _normalize_template_text(question, stem=False)
    q_tokens = q_norm.split()
    threshold = 0.72 if len(q_tokens) <= 2 else 0.86
    strong = float(top["score"]) >= threshold and not ambiguity

    return {
        "match": strong,
        "ambiguous": ambiguity or not strong,
        "score": float(top["score"]),
        "template": top["template"],
        "candidates": scored[:5],
        "needs_clarification": not strong,
    }


def _template_lookup_response(question: str, *, match: dict[str, Any]) -> dict[str, Any]:
    template = match["template"]
    row = {
        "template_id": template.get("id"),
        "name": template.get("name"),
        "serving_label": template.get("serving_label"),
        "kcal": template.get("kcal"),
        "protein_g": template.get("protein_g"),
        "carbs_g": template.get("carbs_g"),
        "fat_g": template.get("fat_g"),
        "fiber_g": template.get("fiber_g"),
        "sodium_mg": template.get("sodium_mg"),
        "source": template.get("source"),
        "confidence": template.get("confidence"),
        "notes": template.get("notes"),
    }
    return {
        "tool": "qbot.query",
        "safety_class": "READ_ONLY",
        "mode": "read_only",
        "status": "ok",
        "query": question,
        "answer": (
            f"Znalazłem zapisany posiłek: {row['name']} "
            f"(ID {row['template_id']}, {row['serving_label']})."
        ),
        "tables": [{
            "domain": "saved_meals_catalog",
            "key": "meal_templates",
            "count": 1,
            "columns": list(row.keys()),
            "rows": [row],
        }],
        "template_match": {
            "template_id": row["template_id"],
            "template_name": row["name"],
            "score": match["score"],
        },
        "needs_clarification": False,
        "missing_fields": [],
        "limitations": [],
        "provenance": [{
            "source": "meal_template_match",
            "template_id": row["template_id"],
            "score": match["score"],
        }],
        "confidence": "high",
    }


def _saved_meals_catalog_response(question: str, *, max_rows: int = 20) -> dict[str, Any]:
    templates = list(_get_meal_templates_cache())
    rows = []
    for tmpl in templates[:max_rows]:
        rows.append({
            "template_id": tmpl.get("id"),
            "name": tmpl.get("name"),
            "serving_label": tmpl.get("serving_label"),
            "kcal": tmpl.get("kcal"),
            "protein_g": tmpl.get("protein_g"),
            "carbs_g": tmpl.get("carbs_g"),
            "fat_g": tmpl.get("fat_g"),
            "fiber_g": tmpl.get("fiber_g"),
            "sodium_mg": tmpl.get("sodium_mg"),
            "source": tmpl.get("source"),
            "confidence": tmpl.get("confidence"),
        })
    top_names = ", ".join(row["name"] for row in rows[:5])
    answer = f"Zapisane posiłki: {len(templates)} szablonów."
    if top_names:
        answer += f" Przykłady: {top_names}."
    return {
        "tool": "qbot.query",
        "safety_class": "READ_ONLY",
        "mode": "read_only",
        "status": "ok",
        "query": question,
        "answer": answer,
        "tables": [{
            "domain": "saved_meals_catalog",
            "key": "meal_templates",
            "count": len(templates),
            "columns": list(rows[0].keys()) if rows else [
                "template_id", "name", "serving_label", "kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sodium_mg", "source", "confidence",
            ],
            "rows": rows,
        }],
        "missing_fields": [],
        "limitations": [],
        "provenance": [{
            "source": "meal_template_list",
            "count": len(templates),
        }],
        "confidence": "high",
    }


def _template_lookup_clarification_response(question: str, *, match: dict[str, Any], intents: list[str]) -> dict[str, Any]:
    candidates = match.get("candidates", [])[:5]
    rows = []
    for cand in candidates:
        tmpl = cand.get("template", {})
        rows.append({
            "template_id": tmpl.get("id"),
            "name": tmpl.get("name"),
            "serving_label": tmpl.get("serving_label"),
            "kcal": tmpl.get("kcal"),
            "protein_g": tmpl.get("protein_g"),
            "carbs_g": tmpl.get("carbs_g"),
            "fat_g": tmpl.get("fat_g"),
            "score": cand.get("score"),
        })
    return {
        "tool": "qbot.query",
        "safety_class": "READ_ONLY",
        "mode": "read_only",
        "status": "partial",
        "query": question,
        "intents_detected": intents,
        "answer": "Nie mam jednoznacznego dopasowania do zapisanego posiłku. Podaj nazwę dokładniej.",
        "tables": [{
            "domain": "saved_meals_catalog",
            "key": "meal_template_candidates",
            "count": len(rows),
            "columns": list(rows[0].keys()) if rows else ["template_id", "name", "serving_label", "kcal", "protein_g", "carbs_g", "fat_g", "score"],
            "rows": rows,
        }],
        "template_match": {
            "score": match.get("score"),
            "candidates": [
                {
                    "template_id": c.get("template", {}).get("id"),
                    "template_name": c.get("template", {}).get("name"),
                    "score": c.get("score"),
                } for c in candidates
            ],
        },
        "needs_clarification": True,
        "clarification_question": "Który zapisany posiłek masz na myśli?",
        "missing_fields": ["template_id"],
        "limitations": [],
        "provenance": [{
            "source": "meal_template_match",
            "status": "ambiguous",
            "score": match.get("score"),
        }],
        "confidence": "medium",
    }


def _parse_nutrition_draft(question: str, date_ctx: dict, template_match: dict[str, Any] | None = None) -> dict:
    """Parse a nutrition log add request. Returns (payload, missing_fields)."""
    ql = question.lower()
    target_date = date.today().isoformat()
    resolved_date = date_ctx.get("date") or date_ctx.get("resolved_date") or target_date

    # Kcal
    kcal = None
    m = re.search(r'(\d+(?:\.?\d+)?)\s*kcal', ql)
    if m:
        kcal = round(float(m.group(1).replace(",", ".")), 1)
    if kcal is None:
        m = re.search(r'kcal\s*(\d+(?:\.?\d+)?)', ql)
        if m:
            kcal = round(float(m.group(1).replace(",", ".")), 1)

    # Protein
    protein = None
    m = re.search(r'\bB\s*(\d+(?:\.?\d+)?)\b', question)
    if m:
        protein = round(float(m.group(1).replace(",", ".")), 1)
    if protein is None:
        m = re.search(r'białko\s*(\d+(?:\.?\d+)?)', ql)
        if m:
            protein = round(float(m.group(1).replace(",", ".")), 1)

    # Carbs
    carbs = None
    m = re.search(r'\bW\s*(\d+(?:\.?\d+)?)\b', question)
    if m:
        carbs = round(float(m.group(1).replace(",", ".")), 1)
    if carbs is None:
        m = re.search(r'(?:węgl|węglow|carbs)\w*\s*(\d+(?:\.?\d+)?)', ql)
        if m:
            carbs = round(float(m.group(1).replace(",", ".")), 1)

    # Fat
    fat = None
    m = re.search(r'\bT\s*(\d+(?:\.?\d+)?)\b', question)
    if m:
        fat = round(float(m.group(1).replace(",", ".")), 1)
    if fat is None:
        m = re.search(r'(?:tłuszcz|fat)\w*\s*(\d+(?:\.?\d+)?)', ql)
        if m:
            fat = round(float(m.group(1).replace(",", ".")), 1)

    # Meal name: strip command prefix then clean
    meal_text = question
    for prefix in [
        r'dodaj\s+do\s+dzisiejszego\s+spożycia\s*:?\s*',
        r'dodaj\s+do\s+spożycia\s*:?\s*',
        r'zapisz\s+posiłek\s*:?\s*',
        r'dodaj\s+jedzenie\s*:?\s*',
        r'dopisz\s+do\s+dzisiejszego\s+jadzenia\s*:?\s*',
        r'dopisz\s+do\s+jadzenia\s*:?\s*',
        r'dodaj\s+do\s+dzisiejszego\s+jadzenia\s*:?\s*',
        r'dopisz\s+do\s+dzisiejszego\s+jedzenia\s*:?\s*',
        r'dopisz\s+do\s+jedzenia\s*:?\s*',
    ]:
        meal_text = re.sub(prefix, '', meal_text, flags=re.IGNORECASE).strip()

    meal_name = _extract_meal_name(meal_text)

    template = template_match.get("template") if template_match else None
    if template and template.get("id"):
        # Prefer the matched template as the canonical meal identity.
        meal_name = str(template.get("name", meal_name or "")).strip() or meal_name
        if kcal is None and template.get("kcal") is not None:
            kcal = round(float(template.get("kcal", 0) or 0), 1)
        if protein is None and template.get("protein_g") is not None:
            protein = round(float(template.get("protein_g", 0) or 0), 1)
        if carbs is None and template.get("carbs_g") is not None:
            carbs = round(float(template.get("carbs_g", 0) or 0), 1)
        if fat is None and template.get("fat_g") is not None:
            fat = round(float(template.get("fat_g", 0) or 0), 1)

    payload = {
        "date": resolved_date,
        "meal_name": meal_name,
        "raw_text": meal_text,
        "kcal_total": kcal,
        "protein_g": protein,
        "carbs_g": carbs,
        "fat_g": fat,
        "source": "qbot_query_draft",
        "confidence": "high" if (kcal is not None) else "medium",
    }

    if template and template.get("id"):
        payload["template_id"] = template.get("id")
        payload["template_name"] = template.get("name")
        payload["template_serving_label"] = template.get("serving_label")
        payload["template_match_score"] = template_match.get("score")

    missing = []
    if kcal is None:
        missing.append("kcal_total")
    if not meal_name:
        missing.append("meal_name")

    return payload, missing


def _parse_reminder_draft(question: str) -> dict:
    """Parse a reminder add request. Returns (payload, missing_fields)."""
    today = date.today()
    q = question
    ql = q.lower()

    # Resolve date
    reminder_date = today
    date_sources = ["jutro", "dziś", "dzisiaj", "pojutrze", "pojutrzejszego",
                    "następnego"]
    for token in date_sources:
        if token in ql:
            resolved = _resolve_polish_date(token.replace("jutra", "jutro").replace("dziś", "dziś"))
            # Actually just check each pattern
            break

    # Check various date expressions
    m = re.search(r'(jutro|dziś|dzisiaj|pojutrze)', ql)
    if m:
        reminder_date = _resolve_polish_date(m.group(1)) or today

    # Check for named days
    weekday_check = re.search(r'(następnego\s+\w+|w\s+\w+|do\s+\w+)', ql)
    if weekday_check:
        resolved = _resolve_polish_date(weekday_check.group(1))
        if resolved:
            reminder_date = resolved

    # YYYY-MM-DD
    m = re.search(r'(\d{4}-\d{2}-\d{2})', q)
    if m:
        try:
            reminder_date = date.fromisoformat(m.group(1))
        except ValueError:
            pass

    # Resolve time
    reminder_time = _resolve_polish_time(q) or "09:00"

    # Explicit fields win over natural-language fallback.
    explicit_title = _extract_quoted_field(q, "title")
    explicit_message = _extract_quoted_field(q, "message")

    # Extract title: text after time or after command prefix
    title = explicit_title or ""
    for cmd in ["przypomnij mi", "dodaj przypomnienie", "ustaw przypomnienie"]:
        if title:
            break
        if cmd in ql:
            rest = q[ql.find(cmd) + len(cmd):].strip().lstrip(":").strip()
            # Remove date/time fragments
            rest = re.sub(r'\b(jutro|dziś|dzisiaj|pojutrze)\b', '', rest, flags=re.IGNORECASE).strip()
            rest = re.sub(r'\bza\s+\d{1,3}\s*(?:minut|minuty|min|godzin(?:y|ę)?|godz)\b', '', rest, flags=re.IGNORECASE).strip()
            rest = re.sub(r'o\s*\d{1,2}(?::\d{2})?', '', rest).strip()
            rest = re.sub(r'\b\d{1,2}:\d{2}\b', '', rest).strip()
            title = rest
            break

    if not title:
        # Fallback: take all text after date/time
        title = q.strip()

    message = explicit_message or title

    payload = {
        "date": reminder_date.isoformat(),
        "time": reminder_time,
        "title": title,
        "message": message,
        "reminder_type": "custom",
        "channel": "telegram",
        "priority": "normal",
        "source": "qbot_query_draft",
    }

    missing = []
    if not title:
        missing.append("title")

    return payload, missing


def _parse_deadline_task_draft(question: str) -> dict:
    """Parse a deadline task request. Returns (payload, missing_fields)."""
    today = date.today()
    q = question
    ql = q.lower()

    # Extract task description (X) and deadline (DATE) from "muszę X do DATE"
    task = ""
    deadline_date = today + timedelta(days=7)  # default: a week out

    for prefix in ["muszę", "trzeba", "mam"]:
        pattern = rf'{re.escape(prefix)}\s+(.+?)\s+(?:do|na)\s+(.+)'
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            task = m.group(1).strip()
            deadline_text = m.group(2).strip()

            # Resolve deadline date
            resolved = _resolve_polish_date(deadline_text)
            if resolved:
                deadline_date = resolved
            else:
                # Try as a standalone date
                resolved = _resolve_polish_date("do " + deadline_text)
                if resolved:
                    deadline_date = resolved

            break

    if not task:
        # Broader fallback
        m = re.search(r'(?:muszę|trzeba|mam)\s+(.+?)\s+(?:do|na)\s+(.+)', q, re.IGNORECASE)
        if m:
            task = m.group(1).strip()
            deadline_text = m.group(2).strip()
            resolved = _resolve_polish_date(deadline_text) or _resolve_polish_date("do " + deadline_text)
            if resolved:
                deadline_date = resolved

    if not task:
        # Last resort: everything between command and deadline keyword
        m = re.search(r'(?:muszę|trzeba|mam)\s+(.+?)\s+(?:do|na)\s', q, re.IGNORECASE)
        if m:
            task = m.group(1).strip()

    message = f"{task} do {deadline_date.isoformat()}"
    if not task:
        task = question.strip()
        message = task

    payload = {
        "date": today.isoformat(),
        "time": "09:00",
        "title": task,
        "message": message,
        "reminder_type": "maintenance",
        "task_kind": "deadline_task",
        "deadline_date": deadline_date.isoformat(),
        "start_date": today.isoformat(),
        "repeat_until_done": True,
        "recurrence_rule": "daily",
        "channel": "telegram",
        "priority": "normal",
        "source": "qbot_query_draft",
    }

    missing = []
    if not task:
        missing.append("title")

    return payload, missing


def _parse_event_draft(question: str) -> dict:
    """Parse an event add request. Returns (payload, missing_fields)."""
    today = date.today()
    q = question
    ql = q.lower()

    # Resolve date from query
    event_date = today
    m = re.search(r'(jutro|dziś|dzisiaj|pojutrze)', ql)
    if m:
        event_date = _resolve_polish_date(m.group(1)) or today

    weekday_check = re.search(r'(w\s+\w+|do\s+\w+|następnego\s+\w+)', ql)
    if weekday_check:
        resolved = _resolve_polish_date(weekday_check.group(1))
        if resolved:
            event_date = resolved

    # Named day like "w sobotę"
    m = re.search(r'(?:w|we)\s+(\w+)', ql)
    if m:
        resolved = _resolve_polish_date(m.group(0))
        if resolved:
            event_date = resolved

    m = re.search(r'(\d{4}-\d{2}-\d{2})', q)
    if m:
        try:
            event_date = date.fromisoformat(m.group(1))
        except ValueError:
            pass

    # Resolve time
    event_time = _resolve_polish_time(q)

    # Determine event_type
    event_type = "custom"
    for kw, etype in [("dentysta", "appointment"), ("lekarz", "appointment"),
                       ("wizyt", "appointment"), ("spotkan", "appointment")]:
        if kw in ql:
            event_type = etype
            break

    # Extract title
    title = ""
    title_prefix = ""
    for cmd in ["dodaj wydarzenie", "zapisz event", "dodaj event",
                "mam wizytę", "mam spotkanie"]:
        if cmd in ql:
            rest = q[ql.find(cmd) + len(cmd):].strip().lstrip(":").strip()
            if "mam wizytę" in cmd:
                title_prefix = "wizyta "
            elif "mam spotkanie" in cmd:
                title_prefix = "spotkanie "
            # Remove date/time fragments
            rest = re.sub(r'\b(jutro|dziś|dzisiaj|pojutrze)\b', '', rest, flags=re.IGNORECASE).strip()
            rest = re.sub(r'\b(w|we)\s+\w+\b', '', rest, flags=re.IGNORECASE).strip()
            rest = re.sub(r'o\s*\d{1,2}(?::\d{2})?', '', rest).strip()
            rest = re.sub(r'\b\d{1,2}:\d{2}\b', '', rest).strip()
            rest = re.sub(r'\s{2,}', ' ', rest).strip().lstrip(":").strip()
            if rest:
                title = title_prefix + rest
            break

    if not title:
        # Fallback: everything after the date
        title = q.strip()
        for cmd in ["dodaj wydarzenie", "zapisz event", "dodaj event"]:
            if cmd in ql:
                title = q[ql.find(cmd) + len(cmd):].strip().lstrip(":").strip()
                break

    payload = {
        "date_start": event_date.isoformat(),
        "time_start": event_time,
        "event_type": event_type,
        "title": title or "Nowe wydarzenie",
        "description": title or "",
        "source": "qbot_query_draft",
    }

    missing = []
    if not title:
        missing.append("title")
    if not event_time:
        missing.append("time_start")

    return payload, missing


def _handle_write_draft(question: str, intents: list[str], date_ctx: dict) -> dict[str, Any] | None:
    """Handle write intents: build draft response without writing.

    Returns a structured draft response, or None if no write intent found.
    """
    write_intent = None
    for wi in ("nutrition_log_add_draft", "qcal_reminder_add_draft", "deadline_task_draft",
               "qcal_event_add_draft", "qcal_event_cancel_draft", "qcal_event_update_draft"):
        if wi in intents:
            write_intent = wi
            break

    if not write_intent:
        return None

    # ── Check writer capability ────────────────────────────────────────
    writer_cap_map = {
        "nutrition_log_add_draft": "nutrition_log_add",
        "qcal_reminder_add_draft": "qcal_reminder_add",
        "deadline_task_draft": "qcal_reminder_add",
        "qcal_event_add_draft": "qcal_event_add",
        "qcal_event_cancel_draft": "qcal_event_cancel",
        "qcal_event_update_draft": "qcal_event_update",
    }
    cap_name = writer_cap_map[write_intent]
    cap_check = _check_writer_capability(cap_name)

    if not cap_check["ready"]:
        answer = (
            f"Rozpoznałem intencję zapisu, ale capability {cap_name} "
            f"ma status {cap_check['status']}. Brakuje kontrolowanego writera."
        )
        return {
            "tool": "qbot.query",
            "safety_class": "READ_ONLY",
            "mode": "read_only",
            "status": "draft",
            "query": question,
            "intents_detected": intents,
            "answer": answer,
            "action_draft": None,
            "missing_capabilities": [cap_name],
            "provenance": [{"source": "qbot_query_draft", "capability": cap_name, "status": cap_check["status"]}],
        }

    # ── Parse draft ────────────────────────────────────────────────────
    if write_intent == "nutrition_log_add_draft":
        template_match = _match_meal_template(question)
        payload, missing = _parse_nutrition_draft(question, date_ctx, template_match=template_match)
        action_type = "nutrition_log_add"
        writer = "nutrition_log_add"
        # Build answer
        kcal_s = f"{payload['kcal_total']}" if payload['kcal_total'] is not None else "?"
        protein_s = f"{payload['protein_g']}" if payload['protein_g'] is not None else "?"
        carbs_s = f"{payload['carbs_g']}" if payload['carbs_g'] is not None else "?"
        fat_s = f"{payload['fat_g']}" if payload['fat_g'] is not None else "?"
        answer = (
            f"Przygotowałem draft wpisu żywieniowego:\n"
            f"- data: {payload['date']}\n"
            f"- posiłek: {payload['meal_name'] or '?'}\n"
            f"- kcal: {kcal_s}\n"
            f"- B/W/T: {protein_s} / {carbs_s} / {fat_s} g\n\n"
            f"Zapis wymaga potwierdzenia przez writer {writer}."
        )
        if template_match and template_match.get("match"):
            answer += (
                f"\nTemplate match: {payload.get('template_name')} "
                f"(ID {payload.get('template_id')}, score={template_match.get('score')})."
            )
        idem_prefix = "nl"
    elif write_intent == "qcal_reminder_add_draft":
        payload, missing = _parse_reminder_draft(question)
        action_type = "qcal_reminder_add"
        writer = "qcal_reminder_add"
        answer = (
            f"Przygotowałem draft przypomnienia:\n"
            f"{payload['date']} {payload['time']} — {payload['title']}.\n"
            f"Zapis wymaga potwierdzenia."
        )
        idem_prefix = "rem"
    elif write_intent == "deadline_task_draft":
        payload, missing = _parse_deadline_task_draft(question)
        action_type = "qcal_reminder_add"
        writer = "qcal_reminder_add"
        answer = (
            f"Rozumiem to jako zadanie do wykonania do {payload['deadline_date']}:\n"
            f"{payload['title']}.\n"
            f"Będę przypominał codziennie do deadline'u, aż oznaczysz jako zrobione.\n"
            f"Zapis wymaga potwierdzenia."
        )
        idem_prefix = "dl"
    elif write_intent == "qcal_event_add_draft":
        payload, missing = _parse_event_draft(question)
        action_type = "qcal_event_add"
        writer = "qcal_event_add"
        time_s = payload.get("time_start") or "brak godziny"
        answer = (
            f"Przygotowałem draft wydarzenia:\n"
            f"{payload['date_start']} o {time_s} — {payload['title']}.\n"
            f"Zapis wymaga potwierdzenia."
        )
        idem_prefix = "ev"
    elif write_intent == "qcal_event_cancel_draft":
        payload = {"raw_query": question, "intent": "cancel"}
        missing = []
        action_type = "qcal_event_cancel"
        writer = "qcal_event_cancel"
        answer = (
            f"Przygotowałem draft anulowania wydarzenia.\n"
            f"Zapytanie: {question}\n"
            f"Zapis wymaga potwierdzenia — użyj action_execute z action_type=qcal_event_cancel."
        )
        idem_prefix = "cancel"
    elif write_intent == "qcal_event_update_draft":
        payload = {"raw_query": question, "intent": "update"}
        missing = []
        action_type = "qcal_event_update"
        writer = "qcal_event_update"
        answer = (
            f"Przygotowałem draft edycji wydarzenia.\n"
            f"Zapytanie: {question}\n"
            f"Zapis wymaga potwierdzenia — użyj action_execute z action_type=qcal_event_update."
        )
        idem_prefix = "upd"
    else:
        return None

    idempotency_key = _generate_idempotency_key(idem_prefix, question)

    action_draft = {
        "action_type": action_type,
        "writer_capability": writer,
        "requires_confirm": True,
        "idempotency_key": idempotency_key,
        "payload": payload,
    }

    # Build tables with draft preview
    tables = []
    if write_intent == "nutrition_log_add_draft":
        tables.append({
            "reader": "action_draft_preview",
            "key": "draft",
            "rows": [{
                "date": payload["date"],
                "meal_name": payload["meal_name"],
                "template_id": payload.get("template_id"),
                "template_name": payload.get("template_name"),
                "kcal": payload["kcal_total"],
                "protein_g": payload["protein_g"],
                "carbs_g": payload["carbs_g"],
                "fat_g": payload["fat_g"],
            }],
        })

    return {
        "tool": "qbot.query",
        "safety_class": "READ_ONLY",
        "mode": "read_only",
        "status": "draft",
        "query": question,
        "intents_detected": intents,
        "answer": answer,
        "action_draft": action_draft,
        "missing_fields": missing,
        "tables": tables,
        "provenance": [{"source": "qbot_query_draft", "capability": cap_name, "status": cap_check["status"]}],
    }


# ── Public API ─────────────────────────────────────────────────────────────


def _tool_qbot_query(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    result = query(
        question=str(args.get("query", "")).strip(),
        mode=str(args.get("mode", "read_only")),
        scope=str(args.get("scope", "all")),
        context=str(args.get("context", "")),
        max_rows=int(args.get("max_rows", 500)),
        include_provenance=bool(args.get("include_provenance", True)),
        include_missing=bool(args.get("include_missing", True)),
    )
    # Attach planning_fact_drafts (for both read and write results)
    if "planning_fact_drafts" not in result:
        try:
            from qbot_planning_memory import detect_planning_facts
            question = str(args.get("query", "")).strip()
            pf_drafts = detect_planning_facts(question)
            if pf_drafts:
                result["planning_fact_drafts"] = pf_drafts
                pf_lines = ["\n\nWykryłem założenie planistyczne:"]
                for d in pf_drafts:
                    pf_lines.append(f"- {d['title']} ({d['confidence']})")
                pf_lines.append("Mogę to zapisać jako planning fact po potwierdzeniu.")
                result["answer"] = (result.get("answer", "") or "") + "\n".join(pf_lines)
        except Exception:
            pass
    return result


# ── Canonical intent → forced readers mapping ───────────────────────────
# When the canonicalizer returns a high-confidence intent with forced
# readers, bypass the semantic planner and dispatch directly.
# Empty list = use semantic planner.
_CANONICAL_FORCE_READERS: dict[str, list[str]] = {
    "current_day_meals": ["meal_list", "nutrition_day"],
    "food_link_audit": [],
    "saved_meals_catalog": [],
    "nutrition_planning": ["nutrition_planning", "nutrition_day", "meal_list", "nutrition_food_search"],
    "nutrition_balance": [],
    "latest_training": [],
    "route_list": [],
    "artifact_read": ["qbot_canonical_docs"],
}

# ── Allowed intents / capabilities (closed enum for LLM) ────────────────

_ALLOWED_CANONICAL_INTENTS = [
    "current_day_meals", "nutrition_balance", "food_product_catalog",
    "saved_meals_catalog", "food_link_audit", "nutrition_planning",
    "nutrition_log_add_draft", "latest_training", "training_summary",
    "meal_log_inventory",
    "route_list", "qcal_reminder_add_draft", "qcal_event_add_draft",
    "qcal_event_cancel_draft", "qcal_event_update_draft",
    "planning_fact_detect", "qcal_lookup", "calendar_day_context",
    "status_readiness", "artifact_read", "unknown",
]

_ALLOWED_CAPABILITIES = [
    "meal_log_inventory", "nutrition_balance", "food_product_catalog",
    "saved_meals_catalog", "food_link_audit", "nutrition_planning",
    "nutrition_log_add", "latest_training_session", "training_summary",
    "route_list", "qcal_reminder_add", "qcal_event_add",
    "qcal_event_update", "qcal_event_cancel",
    "planning_memory", "qcal_reminders", "qcal_events", "artifact_read",
    "calendar_daily_snapshot", "qbot_status", "unknown",
]

_CANONICALIZER_LLM_SYSTEM = """\
Jesteś klasyfikatorem intencji QBot. Twoim zadaniem jest wyłącznie zamapowanie \
pytania użytkownika na canonical_intent i capability z poniższej allowlisty.

Nie odpowiadaj użytkownikowi. Nie wymyślaj narzędzi. Nie twórz nowych intentów \
ani capability. Zwróć tylko JSON.

Allowed canonical_intents:
""" + ", ".join(_ALLOWED_CANONICAL_INTENTS) + """

Allowed capabilities:
""" + ", ".join(_ALLOWED_CAPABILITIES) + """

{"canonical_intent":"...","domain":"...","capability":"...","confidence":"low|medium|high","needs_clarification":true|false,"missing_fields":[],"reason":"krótkie uzasadnienie","date_hint":null|"YYYY-MM-DD","write_intent":true|false}"""


# ── Semantic intent canonicalizer ────────────────────────────────────────

def canonicalize_query_intent(
    question: str,
    intents: list[str],
    context: str = "",
) -> dict | None:
    """Semantic intent canonicalizer.

    Uses hard guards for known patterns, then LLM if available,
    then heuristic fallback. Returns a canonical intent dict or None.

    This is the PRIMARY routing mechanism. Keyword-based classify_intent
    is a fallback for patterns the canonicalizer doesn't handle.
    """
    # ── Hard guards (high-priority patterns) ──
    # These are handled by classify_intent correctly, but the LLM
    # may produce a better canonical_intent. Only block obvious
    # patterns where classify_intent is already authoritative.
    _guarded_intents = {
        "planning_notice", "rwgps_route_list_only", "rwgps_route_lookup",
        "route_surface_profile",
    }
    if set(intents) & _guarded_intents:
        return {"canonical_intent": list(set(intents) & _guarded_intents)[0],
                "domain": "nutrition", "capability": "unknown",
                "confidence": "high", "source": "hard_guard",
                "reason": "hard guard pattern matched"}

    # ── LLM classifier ──
    try:
        canonical = _llm_classify_intent(question)
        if canonical and canonical.get("confidence") in ("high", "medium"):
            if canonical.get("canonical_intent") == "artifact_read":
                ql = question.lower()
                nutrition_cues = any(w in ql for w in (
                    "dieta", "posił", "posilk", "meal", "template", "szablon",
                    "brokuł", "brokul", "kcal", "kalor", "makro", "białk", "bialk",
                    "węgl", "wegl", "tłuszcz", "tluszcz", "jadł", "jedzeni", "nutrition",
                ))
                if nutrition_cues or bool(set(intents) & (_NUTRITION_READONLY_INTENTS | {"nutrition_log_add_draft"})):
                    return None
            canonical["source"] = "llm"
            return canonical
    except Exception:
        pass

    # ── Heuristic fallback ──
    result = _heuristic_canonicalize(question, intents)
    if result:
        result["source"] = "heuristic_fallback"
        return result
    return None


def _llm_classify_intent(question: str) -> dict | None:
    """LLM-based intent classifier.

    Uses qgpt_json() with a closed-enum prompt.
    Returns validated canonical intent or None on failure.
    """
    from qgpt_client import qgpt_json

    user = f"Użytkownik: {question}\n\nJaki to canonical_intent i capability?"
    try:
        result = qgpt_json(user, system=_CANONICALIZER_LLM_SYSTEM,
                           max_tokens=300, temperature=0)
    except Exception:
        return None

    if not isinstance(result, dict):
        return None

    ci = str(result.get("canonical_intent", "unknown"))
    cap = str(result.get("capability", "unknown"))
    conf = str(result.get("confidence", "low"))

    # Validate against allowlist
    if ci not in _ALLOWED_CANONICAL_INTENTS:
        ci = "unknown"
    if cap not in _ALLOWED_CAPABILITIES:
        cap = "unknown"

    return {
        "canonical_intent": ci,
        "domain": result.get("domain", "unknown"),
        "capability": cap,
        "confidence": conf,
        "needs_clarification": bool(result.get("needs_clarification", False)),
        "missing_fields": result.get("missing_fields", []),
        "reason": str(result.get("reason", "")),
        "date_hint": result.get("date_hint"),
        "write_intent": bool(result.get("write_intent", False)),
    }


def _heuristic_canonicalize(question: str, intents: list[str]) -> dict | None:
    """Heuristic fallback for intent canonicalization.

    Handles queries that the keyword classifier misses.
    Primarily catches nutrition/today queries like 'co dziś jadłem?'
    from ANY wording.
    """
    ql = question.lower()

    # Normalize Polish characters for matching
    def _norm(s: str) -> str:
        return s.replace("ł", "l").replace("ą", "a").replace("ę", "e").replace("ó", "o").replace("ś", "s").replace("ć", "c").replace("ź", "z").replace("ż", "z").replace("ń", "n")

    nq = _norm(ql)

    # Detect today reference
    has_today = any(w in nq for w in ("dzis", "dzisiaj", "dzisiejsz", "today"))

    # Detect food/intake concept: any query about eating, meals, food
    # Normalized words so Polish ł→l, etc.
    food_concepts = {
        # Verbs: eating/consuming
        "jadl", "jedz", "zjadl", "spozy", "konsum", "jem",
        # Nouns: food/meals
        "jedzeni", "posilek", "posilk", "intake", "zywieni",
        # Slang/colloquial
        "zarcie", "brzuch", "szamy", "szam",
        # Logging/tracking
        "wpis", "log",
        # Calories
        "kalor", "kcal",
    }
    has_food = any(c in nq for c in food_concepts)

    # If query is about today AND has a food/eating concept
    if has_today and has_food:
        return {
            "canonical_intent": "current_day_meals",
            "domain": "nutrition",
            "capability": "meal_log_inventory",
            "confidence": "medium",
            "reason": "heuristic: food concept + today reference",
            "needs_clarification": False,
        }

    return None


# ═══════════════════════════════════════════════════════════════════════
# LLM-first intent classifier (Phase 1 — comparative, default OFF)
# ═══════════════════════════════════════════════════════════════════════

_LLM_FIRST_ENABLED = os.getenv("QBOT_LLM_FIRST_QUERY", "0") == "1"
_LLM_FIRST_SAFE_DOMAINS_ENABLED = os.getenv("QBOT_LLM_FIRST_SAFE_DOMAINS", "0") == "1"
_LLM_CONFIDENCE_THRESHOLD = 0.6
_LLM_TIMEOUT_SEC = float(os.getenv("QBOT_LLM_FIRST_TIMEOUT_SEC", "3.0"))

_SAFE_DOMAIN_INTENTS: frozenset[str] = frozenset({
    "status", "readiness", "artifact_read", "weather",
})

_LLM_FIRST_CALENDAR_READONLY_ENABLED = os.getenv("QBOT_LLM_FIRST_CALENDAR_READONLY", "0") == "1"
_LLM_FIRST_NUTRITION_READONLY_ENABLED = os.getenv("QBOT_LLM_FIRST_NUTRITION_READONLY", "0") == "1"

_CALENDAR_READONLY_INTENTS: frozenset[str] = frozenset({
    "qcal_lookup", "reminder_status", "event_lookup",
    "calendar_day_context", "daily_timeline",
})

_NUTRITION_READONLY_INTENTS: frozenset[str] = frozenset({
    "saved_meals_catalog",
    "current_day_meals",
    "nutrition_daily",
    "nutrition_range",
    "calorie_balance",
    "nutrition_status",
    "meal_log_inventory",
    "nutrition_planning",
})

_ALLOWED_DOMAINS = [
    "nutrition", "health", "calendar", "wellness", "xert", "intervals",
    "weather", "rwgps", "routes", "garage", "reports", "garmin",
    "cronometer", "meta", "project", "write",
]

_LLM_FIRST_READER_NAMES = sorted(_READER_REGISTRY.keys())

_LLM_FIRST_ALLOWED_INTENTS = sorted(
    set(_ALLOWED_CANONICAL_INTENTS)
    | {name for name, _ in _INTENT_PATTERNS}
    | {"status", "readiness", "general"}
)

# ── LLM alias → canonical intent normalisation ────────────────────────
# Maps common LLM-generated intent labels to the existing canonical
# intent names used by the keyword classifier and reader dispatch.
_LLM_ALIAS_MAP: dict[str, str] = {
    # status / readiness family
    "status_check": "status",
    "system_status": "status",
    "health_check": "status",
    "smoke_test": "status",
    "readiness_report": "readiness",
    "project_status": "readiness",
    "integration_status": "readiness",
    "availability_check": "readiness",
    # docs / artifact family
    "document_read": "artifact_read",
    "artifact_lookup": "artifact_read",
    "knowhow_read": "artifact_read",
    "bible_read": "artifact_read",
    "canonical_docs": "artifact_read",
    "project_docs": "artifact_read",
    # nutrition family
    "daily_meals": "current_day_meals",
    "today_meals": "current_day_meals",
    "meal_log": "current_day_meals",
    "meal_list": "current_day_meals",
    "calorie_check": "calorie_balance",
    "calorie_summary": "calorie_balance",
    "balance_check": "calorie_balance",
    "nutrition_status": "nutrition_status",
    "template_lookup": "saved_meals_catalog",
    "meal_template_lookup": "saved_meals_catalog",
    "template_list": "saved_meals_catalog",
    "meal_history": "meal_log_inventory",
    "nutrition_history": "meal_log_inventory",
    "history_search": "meal_log_inventory",
    # calendar / reminders family
    "reminder_list": "reminder_status",
    "reminder_check": "reminder_status",
    "event_list": "event_lookup",
    "event_check": "event_lookup",
    "daily_plan": "daily_timeline",
    "day_timeline": "daily_timeline",
    "day_summary": "daily_timeline",
    "calendar_view": "calendar_day_context",
    # weather family
    "weather_check": "weather",
    "forecast": "weather",
    # planning family
    "planning_read": "planning_fact_detect",
    "planning_list": "planning_fact_detect",
    "planning_facts": "planning_fact_detect",
    # training family
    "training_history": "training_summary",
    "workout_history": "training_summary",
    "recent_workouts": "training_summary",
    "activity_list": "intervals",
    "recent_activities": "intervals",
    # write intents
    "reminder_create": "qcal_reminder_add_draft",
    "event_create": "qcal_event_add_draft",
    "event_cancel": "qcal_event_cancel_draft",
    "event_update": "qcal_event_update_draft",
    "meal_add": "nutrition_log_add_draft",
    "nutrition_log": "nutrition_log_add_draft",
    "note_save": "nutrition_log_add_draft",
}

_LLM_FIRST_SYSTEM = """\
Jesteś klasyfikatorem intencji asystenta rowerowego QBot.

Na podstawie pytania użytkownika zwróć WYŁĄCZNIE JSON o tej strukturze:
{
  "domain": "nutrition|health|calendar|wellness|xert|intervals|weather|rwgps|routes|garage|reports|garmin|cronometer|meta|project|write",
  "intent": "nazwa_intentu_z_allowlisty",
  "parameters": {},
  "confidence": 0.0,
  "needs_clarification": false,
  "clarification_question": "",
  "readers": [],
  "action_type": null,
  "is_write_intent": false
}

Zasady:
- confidence 0.0–1.0 (>= """ + str(_LLM_CONFIDENCE_THRESHOLD) + """ = pewna decyzja LLM, < """ + str(_LLM_CONFIDENCE_THRESHOLD) + """ = zapytaj użytkownika).
- readers to lista nazw readerów potrzebnych do odpowiedzi (pusta jeśli nie wiesz).
- Jeśli pytanie dotyczy zapisu (dodanie/jako dodanie/edycja/usunięcie), ustaw is_write_intent=true.
- Dla zapisów NIGDY nie używaj fallbacku — oznacz is_write_intent=true i tyle.
- Dla odczytów z niskim confidence ustaw needs_clarification=true i podaj clarification_question.
- parameters: wyciągnij daty, ID, nazwy, keywords z pytania.

Przykłady:
- Pytanie: "status QBot" → {"domain":"meta","intent":"status","parameters":{},"confidence":0.95,"needs_clarification":false,"clarification_question":"","readers":["status"],"action_type":null,"is_write_intent":false}
- Pytanie: "readiness QBot" → {"domain":"meta","intent":"readiness","parameters":{},"confidence":0.95,"needs_clarification":false,"clarification_question":"","readers":["readiness"],"action_type":null,"is_write_intent":false}
- Pytanie: "Przeczytaj Biblię QBot" → {"domain":"project","intent":"artifact_read","parameters":{"query":"Biblię QBot"},"confidence":0.95,"needs_clarification":false,"clarification_question":"","readers":["qbot_canonical_docs"],"action_type":null,"is_write_intent":false}
- Pytanie: "wylistuj zapisane posiłki" → {"domain":"nutrition","intent":"saved_meals_catalog","parameters":{},"confidence":0.95,"needs_clarification":false,"clarification_question":"","readers":[],"action_type":null,"is_write_intent":false}
- Pytanie: "co to jest dieta od Brokuła w mojej bazie?" → {"domain":"nutrition","intent":"saved_meals_catalog","parameters":{"query":"Brokuł"},"confidence":0.95,"needs_clarification":false,"clarification_question":"","readers":[],"action_type":null,"is_write_intent":false}
- Pytanie: "dodaj dzisiaj dietę od Brokuła" → {"domain":"nutrition","intent":"nutrition_log_add_draft","parameters":{"template_query":"Brokuł"},"confidence":0.95,"needs_clarification":false,"clarification_question":"","readers":[],"action_type":null,"is_write_intent":true}
- Pytanie: "Dodaj przypomnienie jutro o 8:00: test" → {"domain":"calendar","intent":"qcal_reminder_add_draft","parameters":{"date":"jutro","time":"8:00","title":"test"},"confidence":0.95,"needs_clarification":false,"clarification_question":"","readers":[],"action_type":null,"is_write_intent":true}

Dozwolone domeny: """ + ", ".join(_ALLOWED_DOMAINS) + """

Dozwolone intenty: """ + ", ".join(_LLM_FIRST_ALLOWED_INTENTS) + """

Dozwoleni readerzy: """ + ", ".join(_LLM_FIRST_READER_NAMES) + """

Nie dodawaj własnych domain/intent/reader — użyj tylko z powyższych list."""


def _build_intent_domain_map() -> dict[str, set[str]]:
    """Build intent → expected domains from _INTENT_TO_READERS + _READER_REGISTRY."""
    mapping: dict[str, set[str]] = {}
    for intent, readers in _INTENT_TO_READERS.items():
        domains: set[str] = set()
        for reader in readers:
            info = _READER_REGISTRY.get(reader)
            if info:
                domains.add(info["category"])
        if domains:
            mapping[intent] = domains
    return mapping


def _validate_llm_intent(result: Any) -> dict | None:
    """Validate LLM result structure and values. Returns cleaned dict or None.

    Checks:
      1. domain in allowlist
      2. intent (after alias normalisation) in allowlist
      3. confidence 0.0–1.0
      4. readers exist in _READER_REGISTRY
      5. all LLM-chosen readers are allowed for the intent (per _INTENT_TO_READERS)
      6. for write intents: must not have readers

    Returns dict with extra diagnostic fields:
      - raw_intent: the intent string returned by the LLM
      - normalized_intent: the canonical intent after alias mapping
      - fallback_reason: set if validation determined that fallback is needed
    """
    if not isinstance(result, dict):
        return None

    domain = str(result.get("domain", "")).strip()
    raw_intent = str(result.get("intent", "")).strip()
    intent = _LLM_ALIAS_MAP.get(raw_intent, raw_intent)
    confidence = result.get("confidence", 0.0)
    readers = result.get("readers", [])
    is_write = bool(result.get("is_write_intent", False))
    needs_clar = bool(result.get("needs_clarification", False))

    # ── Basic field validation ──
    if domain not in _ALLOWED_DOMAINS:
        return None
    if intent not in _LLM_FIRST_ALLOWED_INTENTS:
        return {
            "status": "unrecognised_intent",
            "error": f"intent '{raw_intent}' not recognised (normalised to '{intent}', not in allowlist)",
            "raw_intent": raw_intent,
            "normalized_intent": intent,
            "domain": domain, "intent": intent,
            "parameters": result.get("parameters", {}),
            "confidence": float(confidence),
            "needs_clarification": True,
            "clarification_question": f"Nie rozpoznano intencji: {raw_intent}",
            "readers": [],
            "action_type": None,
            "is_write_intent": is_write,
            "llm_status": "fallback_needed",
            "fallback_reason": f"unrecognised_intent: {raw_intent} → {intent}",
        }
    if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
        confidence = 0.0
    if not isinstance(readers, list):
        readers = []

    # ── Filter readers to registry-known only ──
    known_readers = [r for r in readers if r in _READER_REGISTRY]

    # ── Intent + reader consistency (primary check) ──
    allowed_readers_for_intent = set(_INTENT_TO_READERS.get(intent, []))
    consistency_issues: list[str] = []
    for r in known_readers:
        if allowed_readers_for_intent and r not in allowed_readers_for_intent:
            consistency_issues.append(
                f"reader '{r}' not allowed for intent '{intent}' (allowed: {sorted(allowed_readers_for_intent) or 'none'})"
            )

    # ── Write-intent checks ──
    if is_write and known_readers:
        consistency_issues.append("write intent must not specify readers")
        known_readers = []

    # ── If consistency fails, force fallback ──
    if consistency_issues:
        return {
            "status": "inconsistent",
            "error": "; ".join(consistency_issues),
            "raw_intent": raw_intent,
            "normalized_intent": intent,
            "domain": domain, "intent": intent,
            "parameters": result.get("parameters", {}),
            "confidence": float(confidence),
            "needs_clarification": True,
            "clarification_question": f"Wynik klasyfikacji jest niespójny: {'; '.join(consistency_issues)}",
            "readers": known_readers,
            "action_type": None,
            "is_write_intent": is_write,
            "llm_status": "fallback_needed",
            "fallback_reason": f"inconsistent: {'; '.join(consistency_issues)}",
        }

    return {
        "status": "validated",
        "error": None,
        "raw_intent": raw_intent,
        "normalized_intent": intent,
        "domain": domain,
        "intent": intent,
        "parameters": result.get("parameters", {}),
        "confidence": float(confidence),
        "needs_clarification": needs_clar,
        "clarification_question": str(result.get("clarification_question", "")),
        "readers": known_readers,
        "action_type": result.get("action_type"),
        "is_write_intent": is_write,
        "llm_status": "pending",
        "fallback_reason": None,
    }


def llm_first_classify_intent(
    question: str,
    context: str = "",
    *,
    _retry_count: int = 0,
) -> dict:
    """LLM-first intent classifier.

    Calls qgpt_json() as the FIRST decision mechanism.
    Each call is bounded by _LLM_TIMEOUT_SEC (env QBOT_LLM_FIRST_TIMEOUT_SEC, default 3.0s).
    Retries once on failure.
    Returns a validated structured dict or a fallback指示.
    """
    from qgpt_client import qgpt_json

    user_prompt = f"Użytkownik: {question}\n\nKontekst: {context}"
    last_error: str | None = None

    for attempt in range(2):
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            fut = pool.submit(
                qgpt_json, user_prompt,
                system=_LLM_FIRST_SYSTEM, max_tokens=500, temperature=0,
            )
            raw = fut.result(timeout=_LLM_TIMEOUT_SEC)
        except concurrent.futures.TimeoutError:
            fut.cancel()
            return {
                "status": "fallback_needed",
                "error": f"LLM timeout after {_LLM_TIMEOUT_SEC}s",
                "raw_intent": None, "normalized_intent": None,
                "domain": None, "intent": None, "parameters": {},
                "confidence": 0.0, "needs_clarification": False,
                "clarification_question": "", "readers": [],
                "action_type": None, "is_write_intent": False,
                "llm_status": "fallback_needed",
                "fallback_reason": f"timeout: {_LLM_TIMEOUT_SEC}s",
            }
        except Exception as exc:
            last_error = str(exc)
            if attempt == 0:
                continue
            return {
                "status": "fallback_needed",
                "error": f"LLM call failed after retry: {last_error}",
                "raw_intent": None, "normalized_intent": None,
                "domain": None, "intent": None, "parameters": {},
                "confidence": 0.0, "needs_clarification": False,
                "clarification_question": "", "readers": [],
                "action_type": None, "is_write_intent": False,
                "llm_status": "fallback_needed",
                "fallback_reason": f"api_error: {last_error}",
            }
        finally:
            pool.shutdown(wait=False)

        validated = _validate_llm_intent(raw)
        if validated is not None:
            if validated["status"] in ("inconsistent", "unrecognised_intent"):
                return {
                    "status": "fallback_needed",
                    "error": validated.get("error", "LLM result invalid"),
                    "raw_intent": validated.get("raw_intent"),
                    "normalized_intent": validated.get("normalized_intent"),
                    "domain": validated["domain"],
                    "intent": validated["intent"],
                    "parameters": validated["parameters"],
                    "confidence": validated["confidence"],
                    "needs_clarification": True,
                    "clarification_question": validated.get("clarification_question", ""),
                    "readers": validated["readers"],
                    "action_type": None,
                    "is_write_intent": validated["is_write_intent"],
                    "llm_status": "fallback_needed",
                    "fallback_reason": validated.get("fallback_reason", validated.get("error", "validation failed")),
                }

            status = "use_llm" if validated["confidence"] >= _LLM_CONFIDENCE_THRESHOLD else "ask_clarification"
            validated["status"] = status
            validated["llm_status"] = status
            validated["fallback_reason"] = None if status == "use_llm" else f"low_confidence: {validated['confidence']}"
            return validated

        last_error = "LLM returned invalid/unparseable result"
        if attempt == 0:
            continue
        return {
            "status": "fallback_needed",
            "error": last_error,
            "raw_intent": None, "normalized_intent": None,
            "domain": None, "intent": None, "parameters": {},
            "confidence": 0.0, "needs_clarification": False,
            "clarification_question": "", "readers": [],
            "action_type": None, "is_write_intent": False,
            "llm_status": "fallback_needed",
            "fallback_reason": "unparseable_json",
        }

    return {
        "status": "fallback_needed",
        "error": last_error or "Unknown LLM failure",
        "raw_intent": None, "normalized_intent": None,
        "domain": None, "intent": None, "parameters": {},
        "confidence": 0.0, "needs_clarification": False,
        "clarification_question": "", "readers": [],
        "action_type": None, "is_write_intent": False,
        "llm_status": "fallback_needed",
        "fallback_reason": "unknown_error",
    }


def compare_classifiers(test_queries: list[str]) -> list[dict]:
    """Run comparative test: old classify_intent vs llm_first_classify_intent.

    Returns list of dicts with:
      - query
      - keyword_intents (from classify_intent)
      - llm_result (from llm_first_classify_intent)
      - llm_valid (bool)
      - differences: list of noted differences
      - recommendation: use_llm / ask_clarification / fallback_readonly
    """
    results = []
    for q in test_queries:
        kw_intents = classify_intent(q)
        llm = llm_first_classify_intent(q)
        diff: list[str] = []
        kw_set = set(kw_intents)
        if llm["status"] == "fallback_needed":
            diff.append(f"LLM failed: {llm.get('error')}")
        elif llm["intent"] and llm["intent"] not in kw_set:
            diff.append(f"LLM intent '{llm['intent']}' not in keyword intents {kw_intents}")
        # Determine recommendation
        if llm["status"] == "fallback_needed":
            rec = "fallback_readonly"
        elif llm["needs_clarification"]:
            rec = "ask_clarification"
        elif llm["confidence"] >= _LLM_CONFIDENCE_THRESHOLD:
            rec = "use_llm"
        else:
            rec = "ask_clarification"

        results.append({
            "query": q,
            "keyword_intents": kw_intents,
            "llm_result": llm,
            "llm_valid": llm["status"] != "fallback_needed",
            "differences": diff,
            "recommendation": rec,
        })
    return results


def query(question: str, mode: str = "read_only", scope: str = "all", context: str = "",
          max_rows: int = 500, include_provenance: bool = True, include_missing: bool = True) -> dict[str, Any]:
    if not _TOOL_DISPATCH:
        _init_dispatch()

    # ── Intent classification ──────────────────────────────────────────
    nutrition_llm_result: dict[str, Any] | None = None
    if _LLM_FIRST_ENABLED:
        llm_result = llm_first_classify_intent(question, context)
        if llm_result["status"] == "use_llm" and llm_result["confidence"] >= _LLM_CONFIDENCE_THRESHOLD:
            intents = [llm_result["intent"]] if llm_result["intent"] and llm_result["intent"] != "unknown" else classify_intent(question)
        else:
            intents = classify_intent(question)
    elif _LLM_FIRST_SAFE_DOMAINS_ENABLED:
        kw_intents = classify_intent(question)
        ql = question.lower()
        nutrition_cues = _LLM_FIRST_NUTRITION_READONLY_ENABLED and any(w in ql for w in (
            "dieta", "posił", "posilk", "meal", "template", "szablon",
            "brokuł", "brokul", "kcal", "kalor", "makro", "białk", "bialk",
            "węgl", "wegl", "tłuszcz", "tluszcz", "jadł", "jedzeni", "nutrition",
        ))
        nutrition_hit = _LLM_FIRST_NUTRITION_READONLY_ENABLED and (
            bool(_NUTRITION_READONLY_INTENTS & set(kw_intents))
            or "nutrition_log_add_draft" in kw_intents
            or nutrition_cues
        )
        if _SAFE_DOMAIN_INTENTS & set(kw_intents) or nutrition_hit:
            llm_result = llm_first_classify_intent(question, context)
            if nutrition_hit:
                nutrition_llm_result = llm_result
            if llm_result["status"] == "use_llm" and llm_result["confidence"] >= _LLM_CONFIDENCE_THRESHOLD:
                intents = [llm_result["intent"]] if llm_result["intent"] and llm_result["intent"] != "unknown" else kw_intents
            else:
                intents = kw_intents
        else:
            intents = kw_intents
    elif _LLM_FIRST_CALENDAR_READONLY_ENABLED:
        kw_intents = classify_intent(question)
        if _CALENDAR_READONLY_INTENTS & set(kw_intents):
            llm_result = llm_first_classify_intent(question, context)
            if llm_result["status"] == "use_llm" and llm_result["confidence"] >= _LLM_CONFIDENCE_THRESHOLD:
                intents = [llm_result["intent"]] if llm_result["intent"] and llm_result["intent"] != "unknown" else kw_intents
            else:
                intents = kw_intents
        else:
            intents = kw_intents
    elif _LLM_FIRST_NUTRITION_READONLY_ENABLED:
        kw_intents = classify_intent(question)
        ql = question.lower()
        nutrition_cues = any(w in ql for w in (
            "dieta", "posił", "posilk", "meal", "template", "szablon",
            "brokuł", "brokul", "kcal", "kalor", "makro", "białk", "bialk",
            "węgl", "wegl", "tłuszcz", "tluszcz", "jadł", "jedzeni", "nutrition",
        ))
        if _NUTRITION_READONLY_INTENTS & set(kw_intents) or "nutrition_log_add_draft" in kw_intents or nutrition_cues:
            llm_result = llm_first_classify_intent(question, context)
            nutrition_llm_result = llm_result
            if llm_result["status"] == "use_llm" and llm_result["confidence"] >= _LLM_CONFIDENCE_THRESHOLD:
                llm_intent = llm_result["intent"]
                if "nutrition_log_add_draft" in kw_intents and not str(llm_intent or "").endswith("_draft"):
                    intents = kw_intents
                else:
                    intents = [llm_intent] if llm_intent and llm_intent != "unknown" else kw_intents
            else:
                intents = kw_intents
        else:
            intents = kw_intents
    else:
        intents = classify_intent(question)

    # ── Semantic intent canonicalization ──
    # Overrides keyword classification for queries the canonicalizer
    # can handle more accurately (e.g., "co dziś jadłem?").
    canonical_intent_info = canonicalize_query_intent(question, intents, context)
    if canonical_intent_info:
        ci = canonical_intent_info.get("canonical_intent")
        if ci and ci not in intents:
            intents = [ci] + [i for i in intents if i != "general"]
            # If canonicalizer says current_day_meals and we have no
            # more specific nutrition intent, promote it.
            if ci == "current_day_meals":
                intents = [ci]
    if _LLM_FIRST_NUTRITION_READONLY_ENABLED and nutrition_llm_result:
        if nutrition_llm_result.get("status") == "use_llm" and nutrition_llm_result.get("confidence", 0.0) >= _LLM_CONFIDENCE_THRESHOLD:
            nutrition_intent = nutrition_llm_result.get("intent")
            if nutrition_intent in _NUTRITION_READONLY_INTENTS or nutrition_intent == "nutrition_log_add_draft":
                intents = [nutrition_intent]
                canonical_intent_info = None

    date_ctx = _resolve_date_context(context, question)
    write_result = _handle_write_draft(question, intents, date_ctx)
    if write_result is not None:
        return write_result

    if _LLM_FIRST_NUTRITION_READONLY_ENABLED:
        nutrition_params = {}
        if nutrition_llm_result and isinstance(nutrition_llm_result.get("parameters"), dict):
            nutrition_params = dict(nutrition_llm_result.get("parameters") or {})
        template_probe_text = str(
            nutrition_params.get("query")
            or nutrition_params.get("template_query")
            or question
        ).strip()
        template_match = _match_meal_template(template_probe_text)
        if "saved_meals_catalog" in intents:
            explicit_template_lookup = bool(nutrition_params.get("query") or nutrition_params.get("template_query"))
            if explicit_template_lookup and template_match and template_match.get("match"):
                return _template_lookup_response(question, match=template_match)
            if explicit_template_lookup and template_match and template_match.get("ambiguous"):
                return _template_lookup_clarification_response(question, match=template_match, intents=intents)
            return _saved_meals_catalog_response(question, max_rows=max_rows)
        if template_match and template_match.get("match") and (set(intents) & {"nutrition_planning", "meal_log_inventory", "nutrition_daily", "calorie_balance"}):
            return _template_lookup_response(question, match=template_match)
        if template_match and template_match.get("ambiguous") and (set(intents) & {"nutrition_planning", "meal_log_inventory", "nutrition_daily", "calorie_balance"}):
            return _template_lookup_clarification_response(question, match=template_match, intents=intents)

    # ── Universal saved_meals_catalog / template matching ──────────────
    # Works regardless of QBOT_LLM_FIRST_NUTRITION_READONLY flag.
    if "saved_meals_catalog" in intents:
        template_match = _match_meal_template(question)
        # Heuristic: if query explicitly mentions a template name (not just a list request),
        # show the template; otherwise show the full catalog.
        ql = question.lower()
        explicit_lookup = any(w in ql for w in (
            "dieta od", "co to jest", "znajdź", "znajdz", "szukam",
            "pokaż zapisany", "pokaż szablon", "wyszukaj",
        ))
        if explicit_lookup and template_match and template_match.get("match"):
            return _template_lookup_response(question, match=template_match)
        if explicit_lookup and template_match and template_match.get("ambiguous"):
            return _template_lookup_clarification_response(question, match=template_match, intents=intents)
        return _saved_meals_catalog_response(question, max_rows=max_rows)

    # ── Catch-all template alias matching ────────────────────────────
    # Handles standalone template name queries like "Brokuł", "Brokuł sport 2000"
    # when no explicit saved_meals_catalog intent was detected by keywords.
    if not set(intents) & {"nutrition_log_add_draft"}:
        alias_match = _match_meal_template(question)
        if alias_match:
            q_norm = _normalize_template_text(question, stem=False)
            q_len = len(q_norm.split())
            if alias_match.get("match") and not alias_match.get("ambiguous") and q_len <= 3:
                return _template_lookup_response(question, match=alias_match)
            if alias_match.get("ambiguous") and q_len <= 2:
                return _template_lookup_clarification_response(question, match=alias_match, intents=intents)

    # ── Semantic Planner route ──
    # Skip semantic planner when canonicalizer has an authoritative intent
    # with forced readers, OR when keyword classifier matched specific intents.
    _canonical_forced = False
    _canonical_forced_readers: list[str] = []
    if canonical_intent_info and canonical_intent_info.get("confidence") in ("high", "medium"):
        _ci = canonical_intent_info.get("canonical_intent")
        _cfr = _CANONICAL_FORCE_READERS.get(_ci, None)
        if _cfr is not None and len(_cfr) > 0:
            _canonical_forced = True
            _canonical_forced_readers = list(_cfr)
    _nutrition_intents = {"nutrition_planning", "fueling", "current_day_meals", "calorie_balance"}
    _planning_intents = {"planning_notice"}
    _docs_intents = {"artifact_read"}
    _bypass_semantic = _canonical_forced or bool((_nutrition_intents | _planning_intents | _docs_intents) & set(intents))
    if not _bypass_semantic:
        try:
            from qbot_context_resolver import resolve as resolve_context
            canonical = resolve_context(question, context)
            task_type = canonical.get("task", {}).get("type", "")
            # Route list, calendar context, range analysis → semantic planner
            if task_type in ("route_list", "calendar_day_context", "range_analysis",
                             "missing_data_check", "comparison", "trend", "lookup"):
                from qbot_query_planner import semantic_query
                sp_result = semantic_query(question, context, mode="read_only")
                try:
                    from qbot_planning_memory import detect_planning_facts
                    pf_drafts = detect_planning_facts(question)
                    if pf_drafts:
                        sp_result["planning_fact_drafts"] = pf_drafts
                        pf_lines = ["\n\nWykryłem założenie planistyczne:"]
                        for d in pf_drafts:
                            pf_lines.append(f"- {d['title']} ({d['confidence']})")
                        pf_lines.append("Mogę to zapisać jako planning fact po potwierdzeniu.")
                        sp_result["answer"] = (sp_result.get("answer", "") or "") + "\n".join(pf_lines)
                        _sp_tables = sp_result.get("tables", [])
                        _sp_tables.append({
                            "domain": "planning_fact_drafts", "key": "planning_fact_drafts",
                            "count": len(pf_drafts),
                            "columns": ["fact_type", "date", "title", "confidence"],
                            "rows": [{"fact_type": d.get("fact_type",""), "date": d.get("date",""), "title": d.get("title",""), "confidence": d.get("confidence","")} for d in pf_drafts],
                        })
                        sp_result["tables"] = _sp_tables
                except Exception:
                    pass
                try:
                    if isinstance(canonical_intent_info, dict):
                        sp_result["canonicalizer"] = canonical_intent_info
                except Exception:
                    pass
                return sp_result
        except Exception:
            pass

    # Fallback: keyword-based heuristic detection
    q = question.lower()
    is_analytical = any(w in q for w in [
        "od pocz", "od 1.", "od 202", "zakres dat", "zestawienie", "tabel",
        "porównaj", "porównanie", "czy w dni", "które dni", "trend",
        "wszystko co qbot wie", "co qbot wie o", "co wiesz o dniu",
        "pokaż wage", "pokaż wag", "pokaż sen", "pokaż hrv", "pokaż tętno",
        "pokaż body fat", "pokaż bmi", "pokaż spalanie", "pokaż żywienie",
        "pokaż treningi", "pokaż kalorie", "pokaż kcal",
    ]) or ("od " in q and re.search(r"\d{1,2}[\.\-/]\d{1,2}|\d{4}-\d{2}-\d{2}", q))

    if is_analytical and mode == "read_only":
        try:
            from qbot_query_planner import semantic_query
            sp_result = semantic_query(question, context, mode="read_only")
            try:
                from qbot_planning_memory import detect_planning_facts
                pf_drafts = detect_planning_facts(question)
                if pf_drafts:
                    sp_result["planning_fact_drafts"] = pf_drafts
                    pf_lines = ["\n\nWykryłem założenie planistyczne:"]
                    for d in pf_drafts:
                        pf_lines.append(f"- {d['title']} ({d['confidence']})")
                    pf_lines.append("Mogę to zapisać jako planning fact po potwierdzeniu.")
                    sp_result["answer"] = (sp_result.get("answer", "") or "") + "\n".join(pf_lines)
                    _sp_tables = sp_result.get("tables", [])
                    _sp_tables.append({
                        "domain": "planning_fact_drafts", "key": "planning_fact_drafts",
                        "count": len(pf_drafts),
                        "columns": ["fact_type", "date", "title", "confidence"],
                        "rows": [{"fact_type": d.get("fact_type",""), "date": d.get("date",""), "title": d.get("title",""), "confidence": d.get("confidence","")} for d in pf_drafts],
                    })
                    sp_result["tables"] = _sp_tables
            except Exception:
                pass
            try:
                if isinstance(canonical_intent_info, dict):
                    sp_result["canonicalizer"] = canonical_intent_info
            except Exception:
                pass
            return sp_result
        except Exception:
            pass  # fall through to keyword classifier

    readers_to_call: list[str] = []
    # When canonicalizer has authoritative intent with forced readers, use those
    if _canonical_forced:
        readers_to_call = list(_canonical_forced_readers)
    else:
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

    # ── Planning notice ──
    # Pure planning declarations (e.g. "Jadę dziś luźne Z2 45 min", "Dziś rest day")
    # return early with planning_fact_drafts — no data readers to execute.
    if "planning_notice" in intents:
        response = {
            "tool": "qbot.query", "safety_class": "READ_ONLY",
            "mode": "read_only",
            "query": question, "intents_detected": intents,
            "readers_planned": [], "readers_used": [], "readers_count": 0,
            "answer": "Wykryto deklarację planistyczną.",
            "tables": [], "data": {},
            "answers": [], "provenance": [],
            "missing_fields": [], "limitations": [],
            "date_resolution": date_ctx,
            "status": "ok",
            "confidence": "high",
        }
        try:
            from qbot_planning_memory import detect_planning_facts
            pf_drafts = detect_planning_facts(question)
            if pf_drafts:
                response["planning_fact_drafts"] = pf_drafts
                pf_lines = ["\n\nWykryłem założenie planistyczne:"]
                for d in pf_drafts:
                    pf_lines.append(f"- {d['title']} ({d['confidence']})")
                pf_lines.append("Mogę to zapisać jako planning fact po potwierdzeniu.")
                response["answer"] = (response.get("answer", "") or "") + "\n".join(pf_lines)
                response["tables"].append({
                    "domain": "planning_fact_drafts", "key": "planning_fact_drafts",
                    "count": len(pf_drafts),
                    "columns": ["fact_type", "date", "title", "confidence"],
                    "rows": [{"fact_type": d.get("fact_type",""), "date": d.get("date",""), "title": d.get("title",""), "confidence": d.get("confidence","")} for d in pf_drafts],
                })
            try:
                if isinstance(canonical_intent_info, dict):
                    response["canonicalizer"] = canonical_intent_info
            except Exception:
                pass
        except Exception:
            pass
        return response

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

    # ── Clean up tables for nutrition/planning intents ──────────────
    _nutri_clean_intents = {"nutrition_planning", "nutrition_daily", "fueling", "nutrition_range", "calorie_balance", "current_day_meals"}
    if _nutri_clean_intents & set(intents):
        verbose_fields = {"items_json", "provenance", "raw_text", "source", "context", "created_at", "updated_at"}
        cleaned_tables: list[dict] = []
        seen_domains: set[str] = set()
        daily_summary_totals: dict[str, float] = {}
        for t in tables:
            dom = t.get("domain", "")
            # For current_day_meals intent: rename meal_logs → current_day_meals
            if "current_day_meals" in intents and dom == "meal_logs":
                dom = "current_day_meals"
                t = {**t, "domain": dom}
            # Remove duplicate meal_logs (same data as current_day_summary)
            if dom == "meal_logs":
                continue
            # Strip verbose JSON, add aggregated macros for current_day_meals
            if dom == "current_day_meals":
                stripped_rows = []
                for row in t["rows"]:
                    # Aggregate items into per-meal macros
                    items_list = row.get("items", []) or []
                    if isinstance(items_list, list):
                        kcal = sum(float(i.get("kcal", 0) or 0) for i in items_list)
                        prot = sum(float(i.get("protein_g", 0) or 0) for i in items_list)
                        carbs = sum(float(i.get("carbs_g", 0) or 0) for i in items_list)
                        fat = sum(float(i.get("fat_g", 0) or 0) for i in items_list)
                    else:
                        kcal = prot = carbs = fat = 0.0
                    stripped = {
                        "id": row.get("id"),
                        "eaten_at": row.get("eaten_at"),
                        "meal_type": row.get("meal_type"),
                        "note": (row.get("note") or "")[:80],
                        "kcal": round(kcal, 1) if kcal else None,
                        "protein_g": round(prot, 1) if prot else None,
                        "carbs_g": round(carbs, 1) if carbs else None,
                        "fat_g": round(fat, 1) if fat else None,
                    }
                    stripped_rows.append(stripped)
                    daily_summary_totals["kcal_total"] = daily_summary_totals.get("kcal_total", 0) + kcal
                    daily_summary_totals["protein_g"] = daily_summary_totals.get("protein_g", 0) + prot
                    daily_summary_totals["carbs_g"] = daily_summary_totals.get("carbs_g", 0) + carbs
                    daily_summary_totals["fat_g"] = daily_summary_totals.get("fat_g", 0) + fat
                if not stripped_rows:
                    continue
                new_cols = ["id", "eaten_at", "meal_type", "note", "kcal", "protein_g", "carbs_g", "fat_g"]
                t = {**t, "rows": stripped_rows, "columns": new_cols, "count": len(stripped_rows)}
                # Add daily_nutrition_summary table
                if daily_summary_totals:
                    summary_row = {k: round(v, 1) for k, v in daily_summary_totals.items()}
                    cleaned_tables.append({
                        "domain": "daily_nutrition_summary",
                        "key": "summary",
                        "count": 1,
                        "columns": list(summary_row.keys()),
                        "rows": [summary_row],
                    })
            # Strip verbose JSON from current_day_summary
            elif dom == "current_day_summary":
                stripped_rows = []
                keep = {"id", "eaten_at", "meal_type", "note"}
                for row in t["rows"]:
                    stripped = {k: v for k, v in row.items() if k in keep}
                    stripped_rows.append(stripped)
                if not stripped_rows:
                    continue
                new_cols = list(stripped_rows[0].keys()) if stripped_rows else []
                t = {**t, "rows": stripped_rows, "columns": new_cols, "count": len(stripped_rows)}
            if dom not in seen_domains:
                seen_domains.add(dom)
                cleaned_tables.append(t)
        tables = cleaned_tables

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
        "canonicalizer": canonical_intent_info if isinstance(canonical_intent_info, dict) else None,
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

    canonical_docs_answer = next((a for a in answers if a.get("reader") == "qbot_canonical_docs"), None)
    if canonical_docs_answer:
        doc_payload = canonical_docs_answer.get("data", {}) or {}
        response["answer"] = str(doc_payload.get("answer", response.get("answer", "")))
        response["tables"] = doc_payload.get("tables", [])
        response["documents"] = doc_payload.get("documents", [])
        response["provenance"] = doc_payload.get("provenance", response.get("provenance", []))
        response["missing_fields"] = doc_payload.get("missing_fields", response.get("missing_fields", []))
        response["limitations"] = doc_payload.get("limitations", response.get("limitations", []))
        response["status"] = str(doc_payload.get("status", response.get("status", "ok")))
        if response["status"] == "ok":
            response["confidence"] = "high"
        elif response["status"] == "partial":
            response["confidence"] = "medium"
        elif response["status"] == "no_data":
            response["confidence"] = "low"

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

    # Attach planning_fact_drafts (detected from query text, never auto-saved)
    planning_fact_drafts: list[dict] = []
    try:
        from qbot_planning_memory import detect_planning_facts
        pf_drafts = detect_planning_facts(question)
        if pf_drafts:
            planning_fact_drafts = pf_drafts
            pf_lines = ["\n\nWykryłem założenie planistyczne:"]
            for d in pf_drafts:
                pf_lines.append(f"- {d['title']} ({d['confidence']})")
            pf_lines.append("Mogę to zapisać jako planning fact po potwierdzeniu.")
            response["answer"] = (response.get("answer", "") or "") + "\n".join(pf_lines)
    except Exception:
        pass
    if planning_fact_drafts:
        response["planning_fact_drafts"] = planning_fact_drafts
        pf_table = {
            "domain": "planning_fact_drafts",
            "key": "planning_fact_drafts",
            "count": len(planning_fact_drafts),
            "columns": ["fact_type", "date", "title", "confidence"],
            "rows": [
                {
                    "fact_type": d.get("fact_type", ""),
                    "date": d.get("date", ""),
                    "title": d.get("title", ""),
                    "confidence": d.get("confidence", ""),
                }
                for d in planning_fact_drafts
            ],
        }
        tables.append(pf_table)
        response["tables"] = tables

    return response
