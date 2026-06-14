#!/usr/bin/env python3
"""qbot_query_handler.py — query_vnext read-only handler (ETAP 3A.2).

Deterministic, keyword-based intent routing over PostgreSQL.
No LLM, no MCP integration.  Local CLI test mode with ``python3 qbot_query_handler.py "pytanie"``.

Canonical data map: QBOT_CANONICAL_DATA_MAP_20260530_REV2.md
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

from garmin_auth import garmin_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
try:
    import zoneinfo
    WARSAW = zoneinfo.ZoneInfo("Europe/Warsaw")
except Exception:
    WARSAW = timezone(timedelta(hours=2))  # fallback CEST

PG_HOST = os.getenv("PGHOST", "127.0.0.1")
PG_PORT = os.getenv("PGPORT", "5432")
PG_DB   = os.getenv("PGDATABASE", "qbot")
PG_USER = os.getenv("PGUSER", "qbot")
PG_PASS = os.getenv("PGPASSWORD", "")

_TODAY = datetime.now(WARSAW).date()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
MONTHS_PL = {
    "stycznia":1,"lutego":2,"marca":3,"kwietnia":4,"maja":5,"czerwca":6,
    "lipca":7,"sierpnia":8,"września":9,"pazdziernika":10,"października":10,
    "listopada":11,"grudnia":12,
    "styczen":1,"luty":2,"marzec":3,"kwiecien":4,"maj":5,"czerwiec":6,
    "lipiec":7,"sierpien":8,"wrzesien":9,"pazdziernik":10,"listopad":11,"grudzien":12,
}

def _parse_date(text: str) -> date | None:
    text = text.strip()
    tl = text.lower()
    if tl in ("dziś", "dzisiaj", "today", "dzi\u015b"):
        return _TODAY
    if tl in ("wczoraj", "yesterday"):
        return _TODAY - timedelta(days=1)
    # YYYY-MM-DD
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try: return date(int(m[1]), int(m[2]), int(m[3]))
        except: pass
    # DD.MM.YYYY
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        try: return date(int(m[3]), int(m[2]), int(m[1]))
        except: pass
    # DD/MM/YYYY
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        try: return date(int(m[3]), int(m[2]), int(m[1]))
        except: pass
    # "1 czerwca 2026" or "1 czerwca"
    m = re.match(r"(\d{1,2})\s+([a-zA-Ząęśżźćńół]+)\s*(\d{4})?", tl)
    if m:
        mon = MONTHS_PL.get(m[2])
        yr = int(m[3]) if m[3] else _TODAY.year
        if mon:
            try: return date(yr, mon, int(m[1]))
            except: pass
    return None


def _parse_date_from_question(question: str) -> str:
    """Wyciagnij date z pelnego pytania - sprawdz wszystkie tokeny i multiword."""
    # Najpierw sprawdz jawne frazy wielowyrazowe
    q = question.strip()
    ql = q.lower()
    # "noc z X na Y" / "nocy z X na Y" → data Y (rano nastepnego dnia)
    _noc_m = re.search(
        r"noc[y]?\s+z\s+(\d{1,2})\s+na\s+(\d{1,2})\s*([a-zA-Ząęśżźćńół]+)?\s*(\d{4})?",
        ql)
    if _noc_m:
        _day2 = int(_noc_m.group(2))
        _mon_str = (_noc_m.group(3) or "").strip()
        _yr = int(_noc_m.group(4)) if _noc_m.group(4) else _TODAY.year
        _mon = MONTHS_PL.get(_mon_str, _TODAY.month)
        try:
            return str(date(_yr, _mon, _day2))
        except Exception:
            pass
    # "wczoraj" / "dzisiaj"

    if "wczoraj" in ql or "yesterday" in ql:
        return str(_TODAY - timedelta(days=1))
    if "dzisiaj" in ql or "dziś" in ql or "today" in ql:
        return str(_TODAY)
    # Sprawdz DD.MM.YYYY lub YYYY-MM-DD w tekscie
    for pat, fmt in [
        (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
        (r"(\d{1,2}\.\d{1,2}\.\d{4})", "%d.%m.%Y"),
    ]:
        m = re.search(pat, q)
        if m:
            d = _parse_date(m.group(1))
            if d:
                return str(d)
    # "D miesiac YYYY"
    m = re.search(r"(\d{1,2})\s+([a-zA-Ząęśżźćńół]+)\s*(\d{4})?", ql)
    if m:
        d = _parse_date(m.group(0).strip())
        if d:
            return str(d)
    # sprawdz token po tokenie
    for part in q.split():
        d = _parse_date(part)
        if d:
            return str(d)
    return ""


def _today_or(text) -> date:
    if not text:
        return _TODAY
    return _parse_date(str(text)) or _TODAY


_PSP_TRIG = re.compile(
    r"profil\w*|pr[oó]bk\w*|\bsample\b|rwgps_route_profile_sample|\bco\s*\d+\s*m\b|krok\w*\s*\d+\s*m?\b",
    re.IGNORECASE,
)
_PSP_ID = re.compile(r"\b(\d{6,})\b")
_PSP_STAGE = re.compile(r"etap\w*\s*(\d{1,2})", re.IGNORECASE)
_PSP_KM = re.compile(r"(?:km\s*[=:]?\s*)?(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)")
_PSP_STEP = re.compile(r"(?:krok\w*|step)\s*[=:]?\s*(\d+)|\b(\d+)\s*m\b", re.IGNORECASE)
_ROUTE_FIND_TRIGGERS = (
    "znajdź trasę",
    "znajdz trase",
    "wyszukaj trasę",
    "najnowsza trasa",
    "aktualna trasa",
    "aktualną trasę",
    "szukaj trasy",
)
_ROUTE_IMPORT_TRIGGERS = (
    "pobierz aktualną trasę",
    "pobierz aktualna trase",
    "aktualna wersja trasy",
    "nowa wersja trasy",
    "do artefaktów",
    "do artefaktow",
    "import gpx",
    "importuj gpx",
)
INTENT_REQUIRED_SLOTS = {
    "rwgps_route_profile_sample": ["route_id_numeric"],
    "rwgps_route_import_gpx": [],
}
_LAST_PROFILE_PARAMS: dict[str, Any] = {}
_GARMIN_ACTIVITY_ID = re.compile(r"\b(\d{8,})\b")
_GARMIN_ACTIVITY_DETAIL_ID = re.compile(r"\b(\d{10,})\b")
_GARMIN_STREAM_HINTS = (
    "stream", "streamy", "szczegóły jazdy", "szczegoly jazdy", "pola", "details",
    "hr", "heart rate", "moc", "power", "tempo", "cadence", "altitude", "wysokość",
    "wysokosc", "dostępne", "dostepne", "dane z jazdy", "analiza po km", "analiza po czasie",
)
_GARMIN_EXPORT_HINTS = (
    "export", "eksport", "pobierz fit", "pobierz gpx", "pobierz csv",
    "fit", "gpx", "csv", "plik fit", "plik gpx", "plik csv",
    "eksport aktywności", "eksport aktywnosci", "export aktywności", "export aktywnosci",
)
_GARMIN_ACTIVITY_CONTEXT_HINTS = (
    "garmin", "aktywność", "aktywnosc", "activity", "jazda", "ride",
    "trening", "training", "workout", "dane z jazdy", "dane z aktywności",
    "dane z aktywnosci", "dane aktywności", "dane aktywnosci", "pola",
    "fields", "szczegóły", "szczegoly", "details",
)
_GARMIN_ACTIVITY_DETAIL_HINTS = (
    "activity", "aktywność", "aktywnosc", "garmin activity", "szczegóły aktywności", "szczegoly aktywnosci",
)
# Guard: zapytanie negujace aktywnosc/Garmina ("nie aktywnosc z Garmina",
# "ale nie z Garmina") nie moze byc routowane jako garmin_activity_detail —
# ma spasc do trasy/UNRECOGNIZED -> planner. (test 14, item C)
_GARMIN_ACTIVITY_NEG_RE = re.compile(
    r"\bnie\b[^.,;:!?]{0,20}(?:aktywno|garmin)|bez\s+garmin",
    re.IGNORECASE,
)
_LAST_GARMIN_ACTIVITY_REQUEST: dict[str, Any] = {}


def _parse_profile_request(question: str) -> dict[str, Any] | None:
    has_profile_cue = bool(_PSP_TRIG.search(question or ""))

    route_id = None
    route_match = _PSP_ID.search(question)
    if route_match:
        route_id = int(route_match.group(1))
    else:
        stage_match = _PSP_STAGE.search(question)
        if stage_match:
            try:
                route_id = _resolve_tuscany_e07_live_route_id(
                    question,
                    stage_num=int(stage_match.group(1)),
                )
            except Exception:
                route_id = None

    km_start = km_end = None
    km_match = _PSP_KM.search(question)
    if km_match:
        km_start = float(km_match.group(1).replace(",", "."))
        km_end = float(km_match.group(2).replace(",", "."))

    step_m = 100
    step_match = _PSP_STEP.search(question)
    if step_match:
        step_m = int(step_match.group(1) or step_match.group(2))

    if not has_profile_cue and not (
        route_id is not None and km_start is not None and km_end is not None
    ):
        return None

    params = {
        "route_id": route_id,
        "km_start": km_start,
        "km_end": km_end,
        "step_m": step_m,
    }
    _LAST_PROFILE_PARAMS.clear()
    _LAST_PROFILE_PARAMS.update(params)
    return params


def _parse_route_find_request(question: str) -> dict[str, Any] | None:
    ql = (question or "").lower()
    if any(trigger in ql for trigger in _ROUTE_FIND_TRIGGERS):
        return {"name_hint": question}
    if re.search(r"\bznajd\w*\b.*\btras[aey]\w*\b", ql):
        return {"name_hint": question}
    return None


def _parse_route_import_request(question: str) -> dict[str, Any] | None:
    ql = (question or "").lower()
    if any(trigger in ql for trigger in _ROUTE_IMPORT_TRIGGERS):
        return {"route_name_hint": question}
    return None


def _escalate_to_albert(question: str, escalation_reason: str) -> dict:
    import os as _os
    if _os.getenv("QBOT3_ENABLED") != "1":
        return _envelope(
            "unrecognized",
            "Ten przypadek wymaga Alberta, ale QBOT3_ENABLED nie jest ustawione.",
            status_override="PARTIAL",
            fallback_reason=escalation_reason,
        )
    try:
        from qbot3.agent_runtime import orchestrate_query
        result = orchestrate_query(question)
        if isinstance(result, dict):
            result["escalation_reason"] = escalation_reason
            result["fallback_reason"] = escalation_reason
            return result
    except Exception as exc:
        return _envelope(
            "unrecognized",
            f"Albert fallback error: {exc}",
            status_override="ERROR",
            fallback_reason=escalation_reason,
        )
    return _envelope(
        "unrecognized",
        "Albert zwrócił nieoczekiwany wynik.",
        status_override="ERROR",
        fallback_reason=escalation_reason,
    )


def _parse_garmin_activity_request(question: str) -> dict[str, Any] | None:
    ql = (question or "").lower()
    match = _GARMIN_ACTIVITY_ID.search(question or "")
    activity_id = match.group(1) if match else None
    if not activity_id:
        return None

    has_export_hint = any(hint in ql for hint in _GARMIN_EXPORT_HINTS)
    has_stream_hint = any(hint in ql for hint in _GARMIN_STREAM_HINTS)
    has_generic_activity_context = any(hint in ql for hint in _GARMIN_ACTIVITY_CONTEXT_HINTS)
    has_export_artifact_hint = "artefakt" in ql or "artifact" in ql
    if has_export_hint or (has_export_artifact_hint and has_generic_activity_context):
        fmt = "fit"
        if "gpx" in ql:
            fmt = "gpx"
        elif "csv" in ql:
            fmt = "csv"
        req = {"intent": "garmin_activity_export", "activity_id": activity_id, "format": fmt}
    elif has_stream_hint or has_generic_activity_context:
        req = {"intent": "garmin_activity_streams", "activity_id": activity_id}
    else:
        return None

    _LAST_GARMIN_ACTIVITY_REQUEST.clear()
    _LAST_GARMIN_ACTIVITY_REQUEST.update(req)
    return req


def _parse_garmin_activity_detail_request(question: str) -> dict[str, Any] | None:
    ql = (question or "").lower()
    if not any(hint in ql for hint in _GARMIN_ACTIVITY_DETAIL_HINTS):
        return None

    match = _GARMIN_ACTIVITY_DETAIL_ID.search(question or "")
    if not match:
        return None

    return {"intent": "garmin_activity_detail", "activity_id": match.group(1)}


def _pg_conn():
    import psycopg
    return psycopg.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS,
        connect_timeout=5,
    )


def _sqlite_conn():
    import sqlite3
    conn = sqlite3.connect("/opt/qbot/app/data/garage.db")
    conn.row_factory = sqlite3.Row
    return conn


def _safe_fetch(pg, sql: str, params: tuple = ()) -> list[dict]:
    try:
        cur = pg.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as exc:
        return [{"_error": str(exc)}]


def _envelope(
    intent: str,
    answer: str,
    data: dict | None = None,
    sources_used: list | None = None,
    missing_sources: list | None = None,
    warnings: list | None = None,
    status_override: str | None = None,
    fallback_reason: str | None = None,
    freshness: dict | None = None,
) -> dict:
    status = status_override or "OK"
    if warnings and status == "OK":
        status = "PARTIAL"
    if missing_sources and status == "OK":
        status = "PARTIAL"
    if intent == "unrecognized":
        status = "UNRECOGNIZED"
    return {
        "status": status,
        "engine": "query_vnext",
        "intent": intent,
        "answer": answer,
        "data": data or {},
        "sources_used": sources_used or [],
        "missing_sources": missing_sources or [],
        "freshness": freshness or {},
        "action_draft": None,
        "fallback_reason": fallback_reason,
        "warnings": warnings or [],
    }


# ---------------------------------------------------------------------------
# Intent router  (deterministic, keyword-based)
# ---------------------------------------------------------------------------
INTENT_KEYWORDS: list[tuple[list[str], str]] = [
    (["feasibility", "ocena trasy", "czy dam rade", "czy moge jechac", "analiza wykonalnosci", "check feasibility", "czy trasa jest wykonalna"], "route_feasibility"),
    (["kafelki", "kwadraty", "tiles", "uberkwadrat", "statshunters", "nowe kwadraty", "nowe kafelki", "tile store", "przejechane kwadraty"], "tile_analysis"),
    (["planner claude", "przełącz planner na claude", "przelacz planner na claude",
       "ustaw planner claude", "aktywuj claude planner"], "planner_switch_claude"),
    (["planner openai", "planner gpt", "przełącz planner na openai", "przelacz planner na openai",
       "ustaw planner openai", "aktywuj openai planner"], "planner_switch_openai"),
    (["planner gemini", "przełącz planner na gemini", "przelacz planner na gemini",
       "ustaw planner gemini", "aktywuj gemini planner"], "planner_switch_gemini"),
    (["aktywny planner", "który planner", "status planner", "planner status",
       "jaki planner", "aktywny llm", "planner aktywny"], "planner_status"),
    (["/help", "help", "pomoc", "co umiesz", "co potrafisz", "lista komend", "komendy", "funkcje qbot", "co mozesz"], "qbot_help"),
    (["streamy aktywności", "streamy aktywnosci", "streams garmin", "hr stream", "moc stream",
      "power stream", "szczegóły jazdy", "szczegoly jazdy", "analiza po km", "analiza po czasie"], "garmin_activity_streams"),
    (["eksport aktywności", "eksport aktywnosci", "export aktywności", "export aktywnosci",
      "eksport fit", "export fit", "eksport gpx", "export gpx", "eksport csv", "export csv",
      "pobierz fit", "pobierz gpx", "pobierz csv", "plik fit", "plik gpx", "plik csv"], "garmin_activity_export"),
    (["ostatnia jazda garmin", "ostatnia aktywność garmin", "pobierz ostatnią jazdę", "pobierz ostatnią aktywność",
      "ostatnia aktywność rowerowa", "dzisiejsza jazda", "oceń moją jazdę", "oceń dzisiejszą jazdę",
      "oceń moją dzisiejszą jazdę", "jak mi poszło", "jak poszła jazda", "dane z jazdy",
      "pobierz jazdę z garmin", "pobierz aktywność z garmin"], "garmin_last_activity"),
    (["activity", "aktywność", "garmin activity", "szczegóły aktywności"], "garmin_activity_detail"),
    # Guard: "ile kalorii zjadlem" musi byc PRZED energy_day
    (["ile kalorii zjadłem", "ile kalorii zjadłam",
      "ile kcal zjadłem", "ile kcal zjadłam",
      "kalorii zjadłem", "kalorii zjadłam",
      "ile kalorii dziś", "kalorii dziś", "ile kalorii wczoraj",
      "ile zjadłem kcal", "ile zjadłam kcal"], "daily_balance"),
        (["ile kalorii", "ile spaliłem", "ile spaliłam", "kalorii spalone", "kalorii spaliłem", "energia", "energię", "energy", "spaliłem", "spaliłam", "kroki", "steps", "aktywność"], "energy_day"),
    # Write-intenty — muszą byc przed nutrition żeby nie wpaść w daily_balance
    (["dodaj posiłek", "dodaj posilek", "zapisz posiłek", "zapisz posilek",
      "dodaj jedzenie", "loguj posiłek", "wpisz posiłek", "batonik", "baton", "przekąska", "snack",
      "zjedziałem", "zjadłem", "zjadłam", "spożyłem", "spożyłam",
      "cały batonik", "porcja", "całe opakowanie"], "write_meal"),
    (["skasuj wpis", "usuń wpis", "skasuj posiłek", "usuń posiłek",
      "skasuj ostatni", "usuń ostatni", "delete", "kasuj"], "write_delete_unsupported"),
    (["dodaj etap", "dodaj trasę", "dodaj trasę", "utwórz etap",
      "zapisz etap", "nowy etap"], "write_planning_unsupported"),
    (["ustaw wagę", "ustaw wage", "zmień wagę", "set weight",
      "wpisz wagę", "wpisz wage"], "write_weight_unsupported"),
    (["bilans", "balance", "kalorii", "kalorie", "kcal"], "daily_balance"),
    # Safety: blokuj próby dostępu do tabel DB przez język naturalny
    (["qbot_v2.", "intake_logs", "meal_log_items", "public.nutrition",
      "tabela qbot", "jestem administratorem", "administrator systemu",
      "dostęp do tabeli", "dostep do tabeli", "show tables", "select *",
      "drop table", "truncate", "insert into", "update qbot"], "db_access_blocked"),
    (["meal_logs", "intake_logs", "lista posiłków", "lista wpisów", "całe jedzenie", "surową listę",
      "jadłem", "jadłam", "co jadłem", "co jadłam", "co zjadłem", "co zjadłam",
      "lista posilkow", "wszystkie posilki", "pelna lista jedzenia",
      "posiłki dziś", "posiłki wczoraj", "dzisiejsze posiłki", "wczorajsze posiłki",
      "moje posiłki", "moje jedzenie", "szczegóły posiłków"], "nutrition_intake_logs_list"),
    (["nutrition status", "status nutrition", "status bazy żywienia"], "nutrition_status"),
    # Multi-word trip keywords muszą być przed nutrition_day
    (["jedzenie etap", "jedzenie na etapie", "jedzenie na trasie",
      "zaopatrzenie etap", "zaopatrzenie na etapie", "zaopatrzenie na trasie",
      "co zjem na etapie", "gdzie zjem na etapie", "gdzie kupić na etapie",
      "sklepy na etapie", "sklep na etapie", "bar na etapie",
      "kawiarnia na etapie", "restauracja na etapie",
      "etap toskania jedzenie", "toskania jedzenie", "etap jedzenie"], "trip_attractions"),
    (["jedzenie", "jadło", "posiłek", "meal", "żywność", "spożycie"], "nutrition_day"),
    # ── Report and diagnostic intents (must precede nutrition_range) ──
    (["raport dobowy", "raport dzienny", "daily report", "podsumowanie dnia", "podsumowanie dni",
      "raport poranny", "poranny raport"], "daily_report"),
    (["raport z jazdy", "ride report", "ostatnia jazda", "raport z przejazdu", "raport aktywno\u015bci",
      "raport treningu", "raport po je\u017adzie", "analiza jazdy", "analiza przejazdu", "raport z ostatniej jazdy", "ostatnia jazda", "raport z ostatniej", "raport aktywności"], "ride_report"),
    (["brak danych w raporcie", "dlaczego raport jest pusty", "pusty raport", "raport pusty",
      "raport bez danych", "niekompletny raport", "czemu raport jest pusty",
      "diagnostyka raportu", "diagnostyka raport\u00f3w", "diagnostyka raportow",
      "status \u017ar\u00f3de\u0142 raportu", "status zrodel raportu",
      "dlaczego nie ma danych", "raport nie zawiera danych",
      "raport nie ma danych", "sprawd\u017a dane do raportu", "sprawdz dane do raportu",
      "dane do raportu", "sprawd\u017a \u017ar\u00f3d\u0142a raportu",
      "dlaczego raport jest niekompletny", "raport jest cz\u0119\u015bciowy",
      "raport nie dziala", "raport nie dzia\u0142a"], "report_diagnostic"),
    (["xert historia", "xert ostatni tydzień", "xert ostatni tydzien",
      "xert parametry tydzień", "xert parametry tydzien",
      "xert_profile_snapshots", "fitness signature historia",
      "freshness fatigue xert"], "xert_snapshot_range"),
    (["zakres", "od poniedziałku", "od poniedzialku", "ostatni tydzie\u0144", "ostatni tydzien",
      "makro za tydzie\u0144", "makro za tydzien", "ostatniego tygodnia"], "nutrition_range"),
    (["sen", "spałem", "spałam", "sleep", "spanie", "spaniu"], "sleep_day"),
    (["waga", "ważył", "wadze", "ważę", "masa ciała", "weight", "ile ważę"], "weight_lookup"),
    (["trend wagi", "trend waga", "trend wadze", "historia wagi", "historia wadze", "waga trend"], "weight_trend"),
    (["body composition", "skład ciała", "składzie ciała", "body fat", "tkanka tłuszczowa", "tkanki tłuszczowej", "tkankę tłuszczową", "body water", "woda w organizmie", "wody w organizmie", "wodę w organizmie", "masa mięśniowa", "masy mięśniowej", "masę mięśniową", "masa kostna", "masy kostnej", "masę kostną", "body comp", "body_comp", "bmi", "trend body composition", "pełny skład"], "body_comp"),
    (["body measurements", "body_measurements", "tabela body", "tabela wagi", "tabela składu", "wyniki ważenia", "pełna tabela body", "qbot_v2.body_measurements", "completeness_score", "pomiary body", "pomiary ciała", "pomiary składu"], "body_measurements_range"),
    (["wellness", "hrv", "body battery", "bateria", "tętno", "tętnie", "resting"], "wellness_day"),
    (["fit file", "fit etap", "streamy fit", "dane fit", "aktywnosc fit"], "fit_file_analyze"),
    (["trening", "treningi", "treningów", "training", "aktywność fizyczna", "aktywności", "ćwiczenia", "sport", "jazda", "jeździłem"], "training_recent"),
    (["notatki", "pamięć", "pamiętasz", "pamięci", "wiem o", "fakty o", "w notatkach", "w pamięci", "w wiedzy", "przypomnij"], "memories_search"),
    (["pobierz trase", "przetworz trase", "fetch route", "pobierz etap", "przetworz etap", "obrab trase", "analizuj trase"], "route_workflow_fetch"),
    (["wyslij trase", "upload trasy", "zatwierdz trase", "potwierdz trase do rwgps"], "route_workflow_upload"),
    (["lista tras", "przetworzone trasy", "historia tras"], "route_workflow_list"),
    (["trasy rwgps", "moje trasy rwgps", "ostatnie trasy", "nowe trasy rwgps",
      "trasy z ostatniego", "trasy ułożone", "historia tras", "trasy w rwgps",
      "co układałem", "co tworzyłem w rwgps"], "rwgps_recent_routes"),
    (["podjazdy", "climbs", "wzniesienia", "podejscia", "podjazd", "climb", "ile podjazdow", "trudne miejsca", "kategoria podjazdu", "hc", "cat 1", "cat 2", "cat 3", "cat 4"], "route_climbs"),
    (["wyslij poi", "dodaj poi", "wrzuc poi", "poi do rwgps", "wyslij do rwgps", "dodaj do trasy", "zatwierdz poi", "potwierdz poi", "wykonaj poi"], "rwgps_poi_push"),
    (["przeanalizuj poi", "analiza poi", "poi na trasie", "atrakcje na trasie", "atrakcje na etapie", "nawierzchnia trasy", "nawierzchnia etapu", "surface trasy", "analiza nawierzchni", "route_poi", "route_surface", "co po drodze", "sklepy na trasie", "woda na trasie", "jedzenie na trasie", "stacje na trasie", "stacja benzynowa", "paliwo na trasie", "fuel", "ładowanie na trasie", "poi etap", "poi trasy", "km trasy"], "route_poi_analyze"),
    (["xert", "forma", "gotowość", "readiness", "freshness", "fatigue", "ftp", "ltp", "w'", "w_prime", "w prime"], "xert_status"),
    # ── Artifact lookup intents (must precede garage_search) ──
    (["artefakt", "artifact", "artifact store", "artifact_id",
      "metadane", "metadata", "zarejestrowany artefakt", "zarejestrowane artefakty",
      "route_logistics", "logistics_tool_implementation",
      "qbot_artifact", "artifacts_list", "artifact_search",
      "przeszukaj artefakty", "przeszukaj zarejestrowane",
      "nie odczytuj filesystemu", "nie czytaj z dysku",
      "canonical", "shelf:", "polka", "półka", "artefakty wip", "artefakty canonical", "artefakty export"], "artifact_search"),
    # ── Artifact read intents ──
    (["zobacz /opt/qbot/artifacts/", "przeczytaj /opt/qbot/artifacts/",
      "odczytaj /opt/qbot/artifacts/", "poka\u017c /opt/qbot/artifacts/",
      "zobacz artefakt", "przeczytaj artefakt", "odczytaj artefakt",
      "poka\u017c artefakt", "artifact_get", "artifact_read",
      "artifact content", "odczytaj zarejestrowany",
      "poka\u017c zarejestrowany", "/opt/qbot/artifacts/"], "artifact_read"),
    (["wyjazd", "wyjazdy", "trip", "tripy", "zaplanowane"], "trips_status"),
    (["atrakcje", "atrakcja", "attractions", "must see", "must-see",
      "co warto", "co zobaczyć", "co zobaczyc", "poi wyjazd",
      "woda pitna", "woda na trasie", "woda na etapie",
      "punkty wody", "ile punktów wody", "ile wody",
      "jedzenie na etapie", "jedzenie na trasie", "jedzenie etap",
      "sklep na etapie", "sklep na trasie", "sklepy etap",
      "restauracja na etapie", "bar na etapie", "kawiarnia na etapie",
      "zaopatrzenie na etapie", "zaopatrzenie na trasie",
      "co zjem", "gdzie zjem", "gdzie kupić",
      "restauracje etap"], "trip_attractions"),
    (["pobierz aktualną trasę", "pobierz aktualna trase", "aktualna wersja trasy",
      "nowa wersja trasy", "do artefaktów", "do artefaktow", "import gpx", "importuj gpx"],
     "rwgps_route_import_gpx"),
    (list(_ROUTE_FIND_TRIGGERS), "rwgps_route_find"),
    (["profil trasy", "profil wysokości", "profil wysokosci", "profil km",
      "profil co", "nachylenie co", "nachylenie trasy", "profil nachylenia",
      "profil etap", "profil etapu", "profil etapie"],
     "rwgps_route_profile_sample"),
    (["generuj trasę", "generuj trase", "generate route", "wygeneruj trasę", "wygeneruj trase", "zaproponuj trasę", "zaproponuj trase", "nowa trasa", "trasa od zera"], "route_generate"),
    (["suma etapów", "suma kilometrów", "łącznie etapy", "lacznie etapy",
      "ile łącznie", "ile lacznie", "ile km toskania", "ile km tuscany",
      "najdłuższy etap", "najdluzszy etap", "longest stage",
      "który etap jest najdłuższy", "ktory etap jest najdluzszy",
      "który etap jest najkrótszy", "który etap jest najtrudniejszy",
      "najtrudniejszy etap", "najkrótszy etap", "najkrotszy etap",
      "statystyki etapów", "statystyki etapow", "podsumowanie etapów",
      "podsumowanie trasy", "overview etapów"], "trip_summary"),
    (["ocen forme", "ocen formę", "gotowość przed", "gotowosc przed", "czy jestem gotowy", "czy dam rade", "czy dam radę", "forma przed wyjazdem", "forma przed wyprawa", "readiness przed", "gotowy na wyjazd", "ocen moja forme", "ocen moją formę", "jaka mam forme", "jaka mam formę"], "xert_status"),
    (["etap", "etapy", "stage", "stages", "dzisiejszy etap", "etap dziś", "etap dzis", "plan etapów", "plan etapow", "jaki etap", "który etap"], "trip_stages"),
    (["odśwież xert", "wymuś live fetch", "live fetch xert", "sprawdź xert api", "refresh xert", "xert live", "xert na żywo", "xert live fetch", "wymuś xert"], "xert_live_fetch"),
    (["sprzęt", "sprzet", "rower", "rowery", "wyposażenie", "status garażu", "co mam w garażu", "garaż qbot", "mój garaż"], "garage_status"),
    (["garaż", "garage", "garażu", "w garażu", "w garazu", "kask", "kasku", "kasków", "kaskem", "kaskow", "buty", "but", "butach", "rękawiczki", "rękawiczek", "rekawiczki", "rekawiczek", "rękawiczkach", "kurtka", "kurtki", "jersey", "koszulka", "spodenki", "szukaj", "opony", "koła", "kola", "komponenty", "base layer", "rafa", "rapha", "pedaled", "kaski", "butów", "kurtek", "skarpety", "torby", "namiot", "kamizelka", "spodnie", "kierownica", "sioło", "siodlo", "lancuch", "łańcuch", "kaseta", "komin", "czapka", "chusta"], "garage_search"),
]

# ---------------------------------------------------------------------------
# Router v2 — domain classification (Etap 2)
# ---------------------------------------------------------------------------
OPEN_DOMAIN_INTENTS: set[str] = {
    "rwgps_route_find", "rwgps_route_import_gpx", "rwgps_route_profile_sample",
    "route_poi_analyze", "route_generate", "route_climbs", "route_feasibility",
    "route_workflow_fetch", "route_workflow_upload", "route_workflow_list",
    "rwgps_recent_routes", "rwgps_poi_push",
    "trip_stages", "trip_summary", "trip_attractions", "trips_status",
}

# Sygnały domeny otwartej — używane do wykrywania konfliktu
# (keyword trafił w zamkniętą domenę, ale treść mówi o trasach)
_OPEN_DOMAIN_SIGNALS: list[str] = [
    "trasa", "trasę", "etap", "stage", "rwgps", "gpx",
    "poi", "atrakcje", "route", "generuj tras",
    "profil trasy", "profil etap", "import gpx", "pobierz tras",
    "znajdz trase", "znajdź trasę", "pobierz aktualna trase",
    "aktualną trasę", "wersja trasy",
]


_MEAL_LOG_TITLE_RE = re.compile(
    r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]",
)
_MEAL_LOG_KCAL_RE = re.compile(
    r"^\s*\d+(?:[.,]\d+)?\s*kcal\s*$",
    re.IGNORECASE,
)
_MEAL_LOG_MACRO_RE = re.compile(
    r"^\s*([BWT])\s*:\s*\d+(?:[.,]\d+)?\s*g?\s*$",
    re.IGNORECASE,
)


def _looks_like_meal_log_entry(question: str) -> bool:
    """Rozpoznaj wpis posiłku w formacie nazwa + kcal + B/W/T.

    Taki tekst ma być traktowany jako write_meal, nawet jeśli zawiera liczby,
    które wcześniej mogły wpadać do daily_balance albo nutrition_range.
    """
    lines = [line.strip() for line in (question or "").splitlines() if line.strip()]
    if len(lines) < 4:
        return False

    has_title = any(
        _MEAL_LOG_TITLE_RE.search(line)
        and not re.fullmatch(r"\d+(?:[.,]\d+)?\s*(?:g|kg|ml|kcal)?", line, re.IGNORECASE)
        for line in lines
    )
    has_kcal = any(_MEAL_LOG_KCAL_RE.fullmatch(line) for line in lines)
    macros = {
        match.group(1).upper()
        for line in lines
        if (match := _MEAL_LOG_MACRO_RE.fullmatch(line))
    }

    return has_title and has_kcal and {"B", "W", "T"}.issubset(macros)


def _classify_domain(question: str) -> str:
    """Router v2: 'open' = trasy/planowanie (→ Planner), 'closed' = deterministyczne (→ keyword)."""
    ql = question.lower()
    if any(s in ql for s in _OPEN_DOMAIN_SIGNALS):
        return "open"
    return "closed"


def _resolve_intent(question: str) -> str:
    ql = question.lower()
    garmin_req = _resolve_garmin_activity_from_question(question)
    if garmin_req:
        return str(garmin_req.get("intent", "garmin_activity_streams"))
    if _looks_like_meal_log_entry(question):
        return "write_meal"
    if _parse_route_import_request(question) is not None:
        return "rwgps_route_import_gpx"
    if _parse_route_find_request(question) is not None:
        return "rwgps_route_find"
    if _parse_profile_request(question) is not None:
        return "rwgps_route_profile_sample"
    for keywords, intent in INTENT_KEYWORDS:
        if intent == "nutrition_range" and "xert" in ql:
            continue
        if intent in ("garmin_activity_detail", "energy_day") and _GARMIN_ACTIVITY_NEG_RE.search(ql):
            continue
        for kw in keywords:
            if kw in ql:
                return intent
    return "unrecognized"


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
def _handle_daily_balance(day_str: str) -> dict:
    d = _today_or(day_str)
    try:
        pg = _pg_conn()
        rows = _safe_fetch(pg, "SELECT * FROM qbot_v2.daily_summary WHERE date = %s", (d,))
        pg.close()
    except Exception as exc:
        return _envelope("daily_balance", f"Błąd połączenia: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        err = rows[0].get("_error") if rows else "no rows"
        return _envelope("daily_balance", f"Brak danych bilansu dla {d}.",
                         warnings=[err] if err != "no rows" else [])

    r = rows[0]
    freshness = {}
    if r.get("computed_at"):
        freshness["daily_summary_computed_at"] = str(r["computed_at"])
    if r.get("updated_at"):
        freshness["daily_summary_updated_at"] = str(r["updated_at"])

    parts = []
    missing_fields = []
    if r.get("intake_kcal") is not None:
        parts.append(f"🍽️  Zjedzone: {r['intake_kcal']:.0f} kcal (B:{r.get('intake_protein_g',0):.0f}g W:{r.get('intake_carbs_g',0):.0f}g T:{r.get('intake_fat_g',0):.0f}g)")
        if r.get("intake_source"):
            parts.append(f"     Źródło: {r['intake_source']}")
    else:
        missing_fields.append("intake_kcal")

    if r.get("expenditure_total") is not None:
        parts.append(f"🔥 Wydatek: {r['expenditure_total']:.0f} kcal (spoczynek:{r.get('expenditure_resting',0):.0f} + aktywny:{r.get('expenditure_active',0):.0f})")
    else:
        missing_fields.append("expenditure_total")

    if r.get("balance_kcal") is not None:
        parts.append(f"⚖️  Bilans: {r['balance_kcal']:+.0f} kcal")
    else:
        missing_fields.append("balance_kcal")

    if r.get("balance_note"):
        parts.append(f"📝 {r['balance_note']}")

    answer = "\n".join(parts) if parts else f"Brak szczegółowych danych bilansu dla {d}."
    data = dict(r)
    data["resolved_date"] = str(d)
    data["missing_fields"] = missing_fields

    warnings = []
    if missing_fields:
        warnings.append(f"Brakujące pola: {', '.join(missing_fields)}")

    return _envelope("daily_balance", answer, data=data, sources_used=["qbot_v2.daily_summary"],
                     warnings=warnings, freshness=freshness)


def _handle_intake_logs_list(day_str: str) -> dict:
    d = _today_or(day_str)
    try:
        pg = _pg_conn()
        rows = _safe_fetch(pg, """
            SELECT il.id, il.date, il.eaten_at, il.meal_type, il.note, il.source,
                   ii.id AS item_id, ii.food_name, ii.amount, ii.unit,
                   ii.kcal, ii.protein_g, ii.carbs_g, ii.fat_g, ii.fiber_g, ii.sodium_mg
            FROM qbot_v2.intake_logs il
            LEFT JOIN qbot_v2.intake_items ii ON ii.intake_log_id = il.id
            WHERE il.date = %s
            ORDER BY il.eaten_at, ii.id
        """, (d,))
        pg.close()
    except Exception as exc:
        return _envelope("nutrition_intake_logs_list", f"Błąd połączenia: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        err = rows[0].get("_error") if rows else "no rows"
        return _envelope("nutrition_intake_logs_list", f"Brak wpisów intake_logs dla {d}.",
                         missing_sources=["qbot_v2.intake_logs"],
                         warnings=[err] if err != "no rows" else [])

    meals_map: dict[int, dict] = {}
    for row in rows:
        log_id = row["id"]
        if log_id not in meals_map:
            meals_map[log_id] = {
                "id": log_id,
                "date": str(row["date"]),
                "eaten_at": str(row["eaten_at"]),
                "meal_type": row["meal_type"],
                "note": row["note"],
                "source": row["source"],
                "items": [],
            }
        if row["item_id"] is not None:
            meals_map[log_id]["items"].append({
                "food_name": row["food_name"],
                "amount": row["amount"],
                "unit": row["unit"],
                "kcal": row["kcal"],
                "protein_g": row["protein_g"],
                "carbs_g": row["carbs_g"],
                "fat_g": row["fat_g"],
                "fiber_g": row["fiber_g"],
                "sodium_mg": row["sodium_mg"],
            })

    totals = {"kcal_total": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "fiber_g": 0.0}
    meals_list = []
    for log_id in sorted(meals_map.keys()):
        meal = meals_map[log_id]
        mt = {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "fiber_g": 0.0}
        for item in meal["items"]:
            for k in mt:
                val = item.get(k)
                if val is not None:
                    mt[k] += float(val)
        meal["meal_totals"] = {k: round(v, 2) for k, v in mt.items()}
        for k in totals:
            totals[k] += mt[k.replace("_total", "")]
        meals_list.append(meal)

    totals_rounded = {k: round(v, 2) for k, v in totals.items()}

    parts = [f"📋 Lista posiłków z {d} ({len(meals_list)} wpisów):"]
    for meal in meals_list:
        name = meal["note"] or meal["meal_type"] or "posiłek"
        mt = meal["meal_totals"]
        parts.append(f"\n  ⏰ {meal['eaten_at'][:16]} — {name}")
        parts.append(f"     kcal: {mt['kcal']:.0f} | B:{mt['protein_g']:.1f}g W:{mt['carbs_g']:.1f}g T:{mt['fat_g']:.1f}g")
        for item in meal["items"]:
            parts.append(f"     • {item['food_name']} ({item.get('kcal',0):.0f} kcal)")

    parts.append(f"\n📊 Razem: {totals_rounded['kcal_total']:.0f} kcal")
    parts.append(f"   Białko: {totals_rounded['protein_g']:.1f}g | Węgle: {totals_rounded['carbs_g']:.1f}g | Tłuszcz: {totals_rounded['fat_g']:.1f}g")
    if totals_rounded['fiber_g']:
        parts.append(f"   Błonnik: {totals_rounded['fiber_g']:.1f}g")

    answer = "\n".join(parts)
    data = {
        "resolved_date": str(d),
        "meal_count": len(meals_list),
        "meals": meals_list,
        "totals": totals_rounded,
    }

    return _envelope("nutrition_intake_logs_list", answer, data=data,
                     sources_used=["qbot_v2.intake_logs", "qbot_v2.intake_items"])


def _handle_nutrition_day(day_str: str) -> dict:
    d = _today_or(day_str)
    missing = []
    used = []
    data = {}
    warnings = []
    freshness = {}
    fallback_reason = None

    try:
        pg = _pg_conn()

        # Nutrition summary — try qbot_v2 first (active pipeline)
        summary = _safe_fetch(pg, "SELECT * FROM qbot_v2.nutrition_daily_summary WHERE date = %s ORDER BY source", (d,))
        used_v2 = summary and "_error" not in summary[0] and len(summary) > 0 and summary[0].get("kcal_total") is not None
        if used_v2:
            data["summary"] = summary
            used.append("qbot_v2.nutrition_daily_summary")
            if summary[0].get("computed_at"):
                freshness["nutrition_summary_computed_at"] = str(summary[0]["computed_at"])
        else:
            # Fallback to public (legacy)
            summary = _safe_fetch(pg, "SELECT * FROM public.nutrition_daily_summary WHERE date = %s ORDER BY source", (d,))
            if summary and "_error" not in summary[0] and len(summary) > 0:
                data["summary"] = summary
                used.append("public.nutrition_daily_summary")
                fallback_reason = "public.nutrition_daily_summary used as fallback (qbot_v2 has no data for this date)"
                warnings.append("Źródło: public.nutrition_daily_summary (LEGACY) — qbot_v2 nie ma danych dla tej daty")
                if summary[0].get("computed_at"):
                    freshness["nutrition_summary_computed_at"] = str(summary[0]["computed_at"])
            else:
                missing.append("nutrition_daily_summary")

        # Meals — try qbot_v2 first (active pipeline)
        meals = _safe_fetch(pg, """
            SELECT il.eaten_at, il.meal_type, il.note,
                   ii.food_name, ii.amount, ii.unit, ii.kcal, ii.carbs_g, ii.protein_g, ii.fat_g
            FROM qbot_v2.intake_logs il
            LEFT JOIN qbot_v2.intake_items ii ON ii.intake_log_id = il.id
            WHERE il.date = %s
            ORDER BY il.eaten_at
        """, (d,))
        if meals and "_error" not in meals[0] and len(meals) > 0:
            data["meals"] = meals
            used.append("qbot_v2.intake_logs")
            used.append("qbot_v2.intake_items")
        else:
            # Fallback to public (legacy)
            meals = _safe_fetch(pg, """
                SELECT ml.eaten_at, ml.meal_type, ml.note,
                       mi.food_name, mi.amount, mi.unit, mi.kcal, mi.carbs_g, mi.protein_g, mi.fat_g
                FROM public.meal_logs ml
                LEFT JOIN public.meal_log_items mi ON mi.meal_log_id = ml.id
                WHERE ml.eaten_at::date = %s
                ORDER BY ml.eaten_at
            """, (d,))
            if meals and "_error" not in meals[0] and len(meals) > 0:
                data["meals"] = meals
                used.append("public.meal_logs")
                used.append("public.meal_log_items")
                if not fallback_reason:
                    fallback_reason = "public.meal_logs used as fallback (qbot_v2 intake has no data for this date)"
                warnings.append("Źródło: public.meal_logs (LEGACY) — qbot_v2 intake nie ma danych dla tej daty")
            else:
                missing.append("meal_logs")

        pg.close()
    except Exception as exc:
        return _envelope("nutrition_day", f"Błąd połączenia: {exc}", status_override="ERROR")

    if not data:
        return _envelope("nutrition_day", f"Brak danych nutrition dla {d}.", missing_sources=missing,
                         warnings=["no data found"])

    parts = []
    if data.get("summary"):
        s = data["summary"][0]
        parts.append(f"🍽️  Podsumowanie: {s.get('kcal_total',0):.0f} kcal (B:{s.get('protein_total',0):.0f}g W:{s.get('carbs_total',0):.0f}g T:{s.get('fat_total',0):.0f}g)")
    if data.get("meals"):
        parts.append(f"📋 Posiłki:")
        for m in data["meals"]:
            meal_type = m.get("meal_type") or "posiłek"
            food = m.get("food_name") or ""
            kcal = m.get("kcal")
            detail = f" — {food} ({kcal:.0f} kcal)" if kcal else f" — {food}" if food else ""
            eaten = m.get("eaten_at") or ""
            parts.append(f"   ⏰ {str(eaten)[:16]} {meal_type}{detail}")

    answer = "\n".join(parts) if parts else f"Brak szczegółów nutrition dla {d}."
    data_for_env = dict(data)
    data_for_env["resolved_date"] = str(d)
    return _envelope("nutrition_day", answer, data=data_for_env, sources_used=used,
                     missing_sources=missing, warnings=warnings, freshness=freshness,
                     fallback_reason=fallback_reason)


def _handle_weight_trend(text: str) -> dict:
    """Return weight trend from body_trend_weight view."""
    import re
    _ql_wt = text.lower()
    if any(w in _ql_wt for w in ["miesiąc", "miesiac", "month", "30 dni"]):
        days = 30
    elif any(w in _ql_wt for w in ["tydzień", "tydzien", "week", "7 dni"]):
        days = 7
    elif any(w in _ql_wt for w in ["kwartał", "kwartal", "quarter", "90 dni"]):
        days = 90
    else:
        m = re.search(r"(\d+)\s*(?:dni|d\b)", _ql_wt)
        days = min(int(m.group(1)), 90) if m else 30
    since = _TODAY - timedelta(days=days)

    try:
        pg = _pg_conn()
        rows = _safe_fetch(pg,
            "SELECT * FROM qbot_v2.body_trend_weight WHERE date >= %s ORDER BY date DESC",
            (since,))
        pg.close()
    except Exception as exc:
        return _envelope("weight_trend", f"Błąd połączenia: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        return _envelope("weight_trend", f"Brak danych wagi dla ostatnich {days} dni.",
                         missing_sources=["qbot_v2.body_measurements"])

    parts = [f"📊 Trend wagi — ostatnie {days} dni ({len(rows)} pomiarów):"]
    for r in rows:
        w = r.get("weight_kg")
        d = str(r["date"])
        src = r.get("source", "?")
        ct = r.get("canonical_type", "?")
        flag = "" if ct == "full_body_composition" else " (w-only)"
        if w:
            parts.append(f"  {d}: {w:.1f} kg [{src}]{flag}")

    # Compute min/max/delta
    weights = [r["weight_kg"] for r in rows if r.get("weight_kg")]
    if len(weights) >= 2:
        parts.append(f"  📉 Min: {min(weights):.1f} kg | Max: {max(weights):.1f} kg | Δ: {weights[0] - weights[-1]:+.1f} kg")

    answer = "\n".join(parts)
    data = {"rows": rows, "count": len(rows), "days": days, "since": str(since)}
    return _envelope("weight_trend", answer, data=data,
                     sources_used=["qbot_v2.body_measurements"])


def _handle_weight_lookup(day_str: str) -> dict:
    """Return weight for given date or latest."""
    req_date = _today_or(day_str or "")
    today = date.today()
    try:
        pg = _pg_conn()
        if req_date < today:
            # Szukaj konkretnej daty lub najblizszego wczesniejszego pomiaru
            rows = _safe_fetch(pg,
                "SELECT date, source, weight_kg, NULL as canonical_type "
                "FROM qbot_v2.body_measurements WHERE date <= %s "
                "ORDER BY date DESC LIMIT 1", (req_date,))
            pg.close()
            if not rows or "_error" in rows[0]:
                return _envelope("weight_lookup",
                    f"Brak danych wagi dla {req_date} (lub wcześniej).",
                    missing_sources=["qbot_v2.body_measurements"])
            r = rows[0]
            # Ostrzeżenie gdy znaleziony pomiar jest znacznie starszy niż zapytana data
            found_date = r.get("date")
            warn = ""
            if found_date and str(found_date) != str(req_date):
                warn = f"\n(Brak pomiaru z {req_date} — pokazuję najbliższy: {found_date})"
            w = r.get("weight_kg")
            if w is None:
                return _envelope("weight_lookup",
                    f"Brak danych wagi dla {req_date}.",
                    missing_sources=["qbot_v2.body_measurements"])
            return _envelope("weight_lookup",
                f"⚖️  Waga: {w:.1f} kg ({found_date}, źródło: {r.get('source','?')}).{warn}",
                data=dict(r), sources_used=["qbot_v2.body_measurements"])
        else:
            rows = _safe_fetch(pg, "SELECT * FROM qbot_v2.body_latest_weight")
            pg.close()
    except Exception as exc:
        return _envelope("weight_lookup", f"Błąd połączenia: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        return _envelope("weight_lookup", "Brak danych wagi.",
                         missing_sources=["qbot_v2.body_measurements"])

    r = rows[0]
    date_str = str(r["date"])
    w = r.get("weight_kg")
    src = r.get("source", "?")
    ctype = r.get("canonical_type", "weight_only")

    parts = [f"⚖️  Waga: {w:.1f} kg ({date_str}, źródło: {src})"]
    if ctype == "weight_only" and src in ("garmin/MFP", "garmin_mfp"):
        parts.append("ℹ️  weight-only — brak pełnego składu ciała (MFP)")

    answer = "\n".join(parts)
    data = dict(r)
    data["resolved_date"] = date_str
    return _envelope("weight_lookup", answer, data=data,
                     sources_used=["qbot_v2.body_measurements"])


def _handle_body_comp(day_str: str) -> dict:
    """Return body composition summary from qbot_v2.body_measurements (Garmin canonical).

    Zawsze zwraca dwa osobne rekordy:
      - latest_weight: najnowsza waga (dowolne źródło, priorytet Garmin)
      - latest_full: najnowszy pełny body composition (tylko INDEX_SCALE)

    Withings = historical/legacy, nie używany.
    public.body_composition = legacy, nie używany.
    qbot_v2.body_daily = legacy, nie używany.
    """
    try:
        pg = _pg_conn()

        # Resolve requested date
        req_date = _today_or(day_str)
        today = date.today()
        use_latest = (req_date >= today)

        if use_latest:
            # 1. Latest weight from canonical view
            weight_rows = _safe_fetch(pg, """
                SELECT date, source, weight_kg, imported_at, canonical_type
                FROM qbot_v2.body_latest_weight
                LIMIT 1
            """)
            # 2. Latest full body composition from canonical view
            full_rows = _safe_fetch(pg, """
                SELECT date, source, weight_kg, bmi, body_fat_pct,
                       body_water_pct, muscle_mass_kg, bone_mass_kg,
                       quality_status, imported_at, canonical_type
                FROM qbot_v2.body_latest_full_composition
                LIMIT 1
            """)
        else:
            # Historical: szukaj pomiaru z konkretnej daty lub najbliższego wcześniejszego
            weight_rows = _safe_fetch(pg, """
                SELECT date, source, weight_kg, NULL as imported_at,
                       'historical' as canonical_type
                FROM qbot_v2.body_measurements
                WHERE date <= %s
                ORDER BY date DESC LIMIT 1
            """, (req_date,))
            full_rows = _safe_fetch(pg, """
                SELECT date, source, weight_kg, bmi, body_fat_pct,
                       body_water_pct, muscle_mass_kg, bone_mass_kg,
                       NULL as quality_status, NULL as imported_at,
                       'historical' as canonical_type
                FROM qbot_v2.body_measurements
                WHERE date <= %s AND body_fat_pct IS NOT NULL
                ORDER BY date DESC LIMIT 1
            """, (req_date,))
            # Warn if best match is not exact date
            if weight_rows and str(weight_rows[0].get('date','')) != req_date.isoformat():
                pass  # ostrzeżenie dodamy w odpowiedzi poniżej

        pg.close()
    except Exception as exc:
        return _envelope("body_comp", f"Błąd połączenia: {exc}", status_override="ERROR")

    parts = []
    data = {}
    has_any_data = False

    # ── Latest weight ──────────────────────────────────────────────────
    lw = weight_rows[0] if weight_rows and "_error" not in weight_rows[0] else None
    if lw and lw.get("weight_kg") is not None:
        has_any_data = True
        w_date = str(lw["date"])
        w_src = lw["source"]
        w_kg = lw["weight_kg"]
        w_imp = lw.get("imported_at")
        w_ctype = lw.get("canonical_type", "?")
        parts.append(f"⚖️  **Najnowsza waga:** {w_kg:.1f} kg ({w_date}, źródło: {w_src})")
        data["latest_weight"] = {"date": w_date, "source": w_src, "weight_kg": w_kg}
        if w_imp:
            data["latest_weight"]["imported_at"] = str(w_imp)[:19]

        # Flag weight-only if that's all we have
        src_is_partial = (w_ctype == "weight_only")

        # ── Latest full body composition ────────────────────────────────
        lf = full_rows[0] if full_rows and "_error" not in full_rows[0] else None
        if lf and lf.get("body_fat_pct") is not None:
            f_date = str(lf["date"])
            f_src = lf["source"]
            f_bmi = lf.get("bmi")
            f_bf = lf.get("body_fat_pct")
            f_water = lf.get("body_water_pct")
            f_muscle = lf.get("muscle_mass_kg")
            f_bone = lf.get("bone_mass_kg")
            f_imp = lf.get("imported_at")

            parts.append(f"")
            parts.append(f"📋 **Pełny skład ciała (ostatni):** {f_date} — źródło: {f_src}")

            full_detail = []
            if f_bf is not None:
                full_detail.append(f"🔴 Tkanka tłuszczowa: {f_bf:.1f}%")
            if f_bmi is not None:
                full_detail.append(f"📊 BMI: {f_bmi:.1f}")
            if f_water is not None:
                full_detail.append(f"💧 Woda: {f_water:.1f}%")
            if f_muscle is not None:
                full_detail.append(f"💪 Mięśnie: {f_muscle:.2f} kg")
            if f_bone is not None:
                full_detail.append(f"🦴 Kości: {f_bone:.2f} kg")
            parts.extend([f"   {d}" for d in full_detail])

            data["latest_full_body_composition"] = {
                "date": f_date, "source": f_src,
                "weight_kg": lf.get("weight_kg"),
                "bmi": f_bmi, "body_fat_pct": f_bf,
                "body_water_pct": f_water, "muscle_mass_kg": f_muscle,
                "bone_mass_kg": f_bone,
            }
            if f_imp:
                data["latest_full_body_composition"]["imported_at"] = str(f_imp)[:19]

            # Warning if weight is newer than full comp
            if w_date > f_date:
                parts.append(f"")
                parts.append(f"⚠️  **Uwaga:** najnowsza waga jest z {w_date}, "
                              f"ale ostatni pełny skład ciała pochodzi z {f_date}. "
                              f"Garmin Index Scale nie był używany od {f_date}.")

        elif src_is_partial:
            # No full record — show when the last full one was
            # Check if ANY full record exists (even older)
            last_full_date = None
            if lf:
                last_full_date = str(lf["date"])
            if last_full_date:
                parts.append(f"")
                parts.append(f"⚠️  **Brak aktualnego pełnego składu ciała.**")
                parts.append(f"   Ostatni pełny pomiar Garmin Index Scale: {last_full_date}.")
                parts.append(f"   Dzisiejsza waga pochodzi z MyFitnessPal (MFP) — tylko waga, bez składu.")
            else:
                parts.append(f"")
                parts.append(f"⚠️  **Brak danych pełnego składu ciała w bazie.**")
                parts.append(f"   Waga pochodzi z MyFitnessPal (MFP).")
                parts.append(f"   Użyj Garmin Index Scale, aby uzyskać pełny pomiar body composition.")
    else:
        parts.append("Brak danych body composition.")

    answer = "\n".join(parts)
    data["resolved_date"] = str(req_date) if not use_latest else str(date.today())

    warnings = []
    if lw and lw.get("canonical_type") == "weight_only":
        warnings.append("Najnowsza waga: MFP weight-only (brak pełnego składu)")

    return _envelope("body_comp", answer, data=data,
                     sources_used=["qbot_v2.body_measurements"],
                     warnings=warnings)


def _handle_body_measurements_range(text: str) -> dict:
    """Return full table of body measurements from qbot_v2.body_measurements for a date range.

    Obsługuje zapytania o:
      - analiza body composition za ostatnie 14 dni
      - pełne wyniki ważenia za ostatnie 14 dni
      - pokaż tabelę body measurements za 14 dni
      - pokaż dane z qbot_v2.body_measurements
      - trend wagi i składu ciała za ostatnie 14 dni

    NEVER używa: qbot_v2.body_daily, public.body_composition, Withings.
    """
    import re

    # Parse range (default 14 days)
    rng = _parse_range(text)
    if rng:
        date_from, date_to = rng
    else:
        _ql = text.lower()
        if any(w in _ql for w in ["miesiąc", "miesiac", "month", "30 dni"]):
            days = 30
        elif any(w in _ql for w in ["tydzień", "tydzien", "week", "7 dni"]):
            days = 7
        elif any(w in _ql for w in ["kwartał", "kwartal", "quarter", "90 dni"]):
            days = 90
        else:
            m = re.search(r"(\d+)\s*dni", _ql)
            days = min(int(m.group(1)), 90) if m else 14
        date_to = _TODAY
        date_from = date_to - timedelta(days=days - 1)

    if date_from > date_to:
        date_from, date_to = date_to, date_from

    range_days = (date_to - date_from).days + 1
    if range_days > 90:
        return _envelope("body_measurements_range",
                         f"Zakres {range_days} dni przekracza limit 90 dni.",
                         status_override="ERROR")

    try:
        pg = _pg_conn()
        rows = _safe_fetch(pg, """
            SELECT
              date,
              weight_kg,
              bmi,
              body_fat_pct,
              body_water_pct,
              muscle_mass_kg,
              skeletal_muscle_mass_kg,
              bone_mass_kg,
              visceral_fat,
              metabolic_age,
              physique_rating,
              source_system,
              source_type,
              quality_status,
              completeness_score,
              imported_at
            FROM qbot_v2.body_measurements
            WHERE date >= %s AND date <= %s
            ORDER BY date
        """, (date_from, date_to))
        pg.close()
    except Exception as exc:
        return _envelope("body_measurements_range",
                         f"Błąd połączenia: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        err = rows[0].get("_error") if rows else "no rows"
        return _envelope("body_measurements_range",
                         f"Brak danych w qbot_v2.body_measurements dla zakresu {date_from}..{date_to}.",
                         missing_sources=["qbot_v2.body_measurements"],
                         warnings=[err] if err != "no rows" else [])

    full_count = sum(1 for r in rows if r.get("quality_status") == "full_body_composition")
    wo_count = sum(1 for r in rows if r.get("quality_status") == "weight_only")

    # Build table
    parts = [
        f"📊 Body Measurements — {date_from} do {date_to} ({len(rows)} pomiarów)",
        f"   Pełny skład: {full_count} | Weight-only: {wo_count}",
        "",
    ]

    # Column widths
    parts.append(
        f"  {'Data':<11} {'Waga':>7} {'BMI':>7} {'BF%':>5} {'Woda%':>6} "
        f"{'Mięśnie':>8} {'Kości':>7} {'Typ':<15} Źródło"
    )
    parts.append("  " + "-" * 80)

    for r in rows:
        d = str(r["date"])
        w = f"{r['weight_kg']:.1f}" if r.get("weight_kg") else "-"
        bmi = f"{r['bmi']:.1f}" if r.get("bmi") else "-"
        bf = f"{r['body_fat_pct']:.1f}" if r.get("body_fat_pct") else "-"
        bw = f"{r['body_water_pct']:.1f}" if r.get("body_water_pct") else "-"
        mm = f"{r['muscle_mass_kg']:.2f}" if r.get("muscle_mass_kg") else "-"
        bm = f"{r['bone_mass_kg']:.2f}" if r.get("bone_mass_kg") else "-"
        qs = r.get("quality_status", "")
        if qs == "full_body_composition":
            st_tag = "INDEX_SCALE"
        elif qs == "weight_only":
            st_tag = "MFP (w-only)"
        else:
            st_tag = r.get("source_type", "?")
        src = r.get("source_type", "?")

        parts.append(
            f"  {d:<11} {w:>7} {bmi:>7} {bf:>5} {bw:>6} "
            f"{mm:>8} {bm:>7} {st_tag:<15} {src}"
        )

    # Trend summary
    weights = [r["weight_kg"] for r in rows if r.get("weight_kg")]
    if len(weights) >= 2:
        parts.append("")
        delta = weights[-1] - weights[0]
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        parts.append(
            f"  Trend wagi: {weights[0]:.1f} → {weights[-1]:.1f} kg "
            f"({arrow}{delta:+.1f} kg) | "
            f"Min: {min(weights):.1f} | Max: {max(weights):.1f}"
        )

    # Full comp summary
    full_rows = [r for r in rows if r.get("quality_status") == "full_body_composition"]
    if full_rows:
        latest = full_rows[-1]  # last in sorted ASC
        parts.append(
            f"  Ostatni pełny skład: {latest['date']} | "
            f"BF={latest.get('body_fat_pct','?'):.1f}% | "
            f"BMI={latest.get('bmi','?'):.1f} | "
            f"Woda={latest.get('body_water_pct','?'):.1f}% | "
            f"Mięśnie={latest.get('muscle_mass_kg','?'):.2f}kg | "
            f"Kości={latest.get('bone_mass_kg','?'):.2f}kg"
        )

    answer = "\n".join(parts)
    data = {
        "rows": rows,
        "count": len(rows),
        "full_body_composition": full_count,
        "weight_only": wo_count,
        "date_from": str(date_from),
        "date_to": str(date_to),
        "range_days": range_days,
    }
    return _envelope("body_measurements_range", answer, data=data,
                     sources_used=["qbot_v2.body_measurements"])


def _handle_sleep_day(day_str: str) -> dict:
    d = _today_or(day_str)
    try:
        pg = _pg_conn()
        rows = _safe_fetch(pg, "SELECT * FROM qbot_v2.sleep_daily WHERE date = %s", (d,))
        pg.close()
    except Exception as exc:
        return _envelope("sleep_day", f"Błąd połączenia: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        return _envelope("sleep_day", f"Brak danych snu dla {d}.",
                         warnings=[] if not rows else [rows[0].get("_error","")])

    r = rows[0]
    freshness = {}
    if r.get("imported_at"):
        freshness["sleep_imported_at"] = str(r["imported_at"])

    parts = []
    if r.get("duration_min") is not None:
        h, m = divmod(r["duration_min"], 60)
        parts.append(f"😴 Czas snu: {h}h {m}min")
    if r.get("score") is not None:
        parts.append(f"⭐ Jakość: {r['score']}/100")
    for label, col in [("Głęboki", "deep_min"), ("Lekki", "light_min"), ("REM", "rem_min"), ("Czuwanie", "awake_min")]:
        val = r.get(col)
        if val is not None:
            parts.append(f"   {label}: {val}min")
    if r.get("hrv_ms") is not None:
        parts.append(f"💓 HRV: {r['hrv_ms']:.0f}ms")
    if r.get("resting_hr_bpm") is not None:
        parts.append(f"❤️  Tętno spoczynkowe: {r['resting_hr_bpm']}bpm")

    answer = "\n".join(parts) if parts else f"Dane snu dla {d} — brak szczegółów."
    data = dict(r)
    data["resolved_date"] = str(d)
    return _envelope("sleep_day", answer, data=data, sources_used=["qbot_v2.sleep_daily"],
                     freshness=freshness)


def _handle_wellness_day(day_str: str, question: str = "") -> dict:
    d = _today_or(day_str or "")
    try:
        pg = _pg_conn()
        rows = _safe_fetch(pg, "SELECT * FROM qbot_v2.wellness_daily WHERE date = %s", (d,))
        pg.close()
    except Exception as exc:
        return _envelope("wellness_day", f"Błąd połączenia: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        return _envelope("wellness_day", f"Brak danych wellness dla {d}.")

    r = rows[0]
    freshness = {}
    if r.get("imported_at"):
        freshness["wellness_imported_at"] = str(r["imported_at"])

    parts = []
    if r.get("hrv_ms") is not None:
        parts.append(f"💓 HRV: {r['hrv_ms']:.0f}ms")
    elif "hrv" in (question or "").lower():
        parts.append(f"💓 HRV: brak danych dla {d} (null w Garmin)")
    if r.get("resting_hr_bpm") is not None:
        parts.append(f"❤️  Tętno spoczynkowe: {r['resting_hr_bpm']}bpm")
    if r.get("body_battery_start") is not None and r.get("body_battery_end") is not None:
        parts.append(f"🔋 Body Battery: {r['body_battery_start']} → {r['body_battery_end']}")
    if r.get("stress_avg") is not None:
        parts.append(f"📊 Stres średni: {r['stress_avg']}")
    if r.get("spo2_avg") is not None:
        parts.append(f"🫁 SpO2: {r['spo2_avg']:.0f}%")
    if r.get("weight_kg") is not None:
        parts.append(f"⚖️  Waga: {r['weight_kg']:.1f}kg")

    answer = "\n".join(parts) if parts else f"Brak szczegółów wellness dla {d}."
    data = dict(r)
    data["resolved_date"] = str(d)
    return _envelope("wellness_day", answer, data=data, sources_used=["qbot_v2.wellness_daily"],
                     freshness=freshness)


def _handle_energy_day(day_str: str) -> dict:
    d = _today_or(day_str)
    try:
        pg = _pg_conn()
        rows = _safe_fetch(pg, "SELECT * FROM qbot_v2.energy_daily WHERE date = %s", (d,))
        pg.close()
    except Exception as exc:
        return _envelope("energy_day", f"Błąd połączenia: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        return _envelope("energy_day", f"Brak danych energii dla {d}.")

    r = rows[0]
    freshness = {}
    if r.get("imported_at"):
        freshness["energy_imported_at"] = str(r["imported_at"])
    if r.get("updated_at"):
        freshness["energy_updated_at"] = str(r["updated_at"])

    parts = []
    if r.get("total_kcal") is not None:
        resting = r.get("resting_kcal") or 0
        active = r.get("active_kcal") or 0
        parts.append(f"🔥 Całkowity wydatek: {r['total_kcal']:.0f} kcal (spoczynek:{resting:.0f} + aktywny:{active:.0f})")
    if r.get("steps") is not None:
        parts.append(f"🚶 Kroki: {r['steps']}")
    if r.get("is_partial_snapshot"):
        parts.append("⚠️  Częściowy snapshot (dane jeszcze niekompletne)")

    answer = "\n".join(parts) if parts else f"Brak szczegółów energii dla {d}."
    data = dict(r)
    data["resolved_date"] = str(d)
    return _envelope("energy_day", answer, data=data, sources_used=["qbot_v2.energy_daily"],
                     freshness=freshness)


def _load_latest_garmin_activity() -> dict:
    try:
        from qbot_garmin_history import read_training_sessions
    except Exception as exc:
        return {"status": "ERROR", "error": f"Błąd importu Garmin: {exc}"}

    yesterday = (_TODAY - timedelta(days=1)).isoformat()
    today = _TODAY.isoformat()
    try:
        activities = read_training_sessions(yesterday, today)
    except Exception as exc:
        return {"status": "ERROR", "error": f"Błąd połączenia z Garmin: {exc}"}

    if not activities:
        return {
            "status": "NO_DATA",
            "answer": "brak aktywności Garmin",
            "data": {"count": 0, "resolved_range": {"start": yesterday, "end": today}, "activities": []},
        }

    if len(activities) == 1 and isinstance(activities[0], dict) and activities[0].get("error"):
        err = activities[0].get("error") or "nieznany błąd"
        return {"status": "ERROR", "error": f"Błąd Garmin: {err}"}

    cycling_types = {
        "cycling",
        "biking",
        "mountain_biking",
        "road_biking",
        "gravel_cycling",
        "virtual_ride",
    }

    filtered: list[dict] = [
        a for a in activities
        if isinstance(a, dict) and (a.get("activity_type") or "").lower() in cycling_types
    ]

    if not filtered:
        return {
            "status": "NO_DATA",
            "answer": "brak aktywności Garmin",
            "data": {
                "count": 0,
                "resolved_range": {"start": yesterday, "end": today},
                "activities": activities,
            },
        }

    def _started_key(row: dict) -> datetime:
        value = row.get("started_at") or row.get("date")
        if isinstance(value, datetime):
            return value
        if not value:
            return datetime.min.replace(tzinfo=timezone.utc)
        text_value = str(value).strip().replace("Z", "+00:00")
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                parsed = datetime.strptime(text_value, fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(text_value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    last = sorted(filtered, key=_started_key, reverse=True)[0]
    return {
        "status": "OK",
        "data": {
            "count": len(filtered),
            "activities": filtered,
            "resolved_range": {"start": yesterday, "end": today},
        },
        "activity": last,
    }


def _resolve_garmin_activity_from_question(question: str) -> dict[str, Any] | None:
    req = _parse_garmin_activity_detail_request(question)
    if req:
        return req

    req = _parse_garmin_activity_request(question)
    if req:
        return req

    ql = (question or "").lower()
    if not any(hint in ql for hint in _GARMIN_STREAM_HINTS + _GARMIN_EXPORT_HINTS):
        return None

    match = _GARMIN_ACTIVITY_ID.search(question or "")
    if not match:
        return None

    req = {"intent": "garmin_activity_streams", "activity_id": match.group(1)}
    _LAST_GARMIN_ACTIVITY_REQUEST.clear()
    _LAST_GARMIN_ACTIVITY_REQUEST.update(req)
    return req


def _get_garmin_activity_id(question: str, last: dict[str, Any]) -> str | None:
    req = _resolve_garmin_activity_from_question(question)
    if req and req.get("activity_id"):
        return str(req["activity_id"])
    return _extract_garmin_activity_id(last)


def _extract_garmin_activity_id(activity: dict) -> str | None:
    route_ref = str(activity.get("route_ref") or "").strip()
    if route_ref.startswith("garmin://"):
        value = route_ref.split("://", 1)[1].strip()
        if value:
            return value
    external_id = str(activity.get("external_id") or "").strip()
    if external_id.startswith("garmin://"):
        external_id = external_id.split("://", 1)[1].strip()
    return external_id or None


def _safe_numeric_list(values) -> list[float]:
    out: list[float] = []
    for value in values or []:
        if value is None:
            continue
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            continue
    return out


def _avg(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _format_bin_value(avg_value: float | None, max_value: float | None, suffix: str) -> str:
    avg_text = f"{avg_value:.1f}" if avg_value is not None else "n/d"
    max_text = f"{max_value:.0f}" if max_value is not None else "n/d"
    return f"{avg_text}/{max_text}{suffix}"


def _garmin_stream_summary(streams: dict) -> list[str]:
    if streams.get("error"):
        available = ", ".join(streams.get("available", [])) or "brak danych"
        return [f"📈 Streamy: {streams['error']} ({available})"]

    times = _safe_numeric_list(streams.get("time"))
    heart_rate = _safe_numeric_list(streams.get("heart_rate"))
    power = _safe_numeric_list(streams.get("power"))
    altitude = _safe_numeric_list(streams.get("altitude"))
    cadence = _safe_numeric_list(streams.get("cadence"))

    if not times:
        return ["📈 Streamy: brak danych czasowych."]

    bins: dict[int, dict[str, list[float]]] = {}
    for idx, t in enumerate(times):
        bucket = bins.setdefault(int(t // 600), {"heart_rate": [], "power": []})
        if idx < len(heart_rate) and heart_rate[idx] is not None:
            bucket["heart_rate"].append(heart_rate[idx])
        if idx < len(power) and power[idx] is not None:
            bucket["power"].append(power[idx])

    bin_lines: list[str] = []
    for bin_idx in sorted(bins):
        bucket = bins[bin_idx]
        hr_vals = bucket["heart_rate"]
        pwr_vals = bucket["power"]
        start_min = bin_idx * 10
        end_min = start_min + 10
        hr_avg = _avg(hr_vals)
        hr_max = max(hr_vals) if hr_vals else None
        pwr_avg = _avg(pwr_vals)
        pwr_max = max(pwr_vals) if pwr_vals else None
        bin_lines.append(
            f"{start_min}-{end_min}' HR {_format_bin_value(hr_avg, hr_max, ' bpm')}, moc {_format_bin_value(pwr_avg, pwr_max, ' W')}"
        )

    if len(bin_lines) > 5:
        bin_lines = bin_lines[:3] + ["…"] + bin_lines[-2:]

    first_half = len(times) // 2
    hr_first = _avg(heart_rate[:first_half]) if first_half else None
    hr_second = _avg(heart_rate[first_half:]) if first_half else None
    pwr_first = _avg(power[:first_half]) if first_half else None
    pwr_second = _avg(power[first_half:]) if first_half else None
    decoupling = None
    if hr_first and hr_second and pwr_first and pwr_second and pwr_first > 0 and pwr_second > 0:
        first_ratio = hr_first / pwr_first
        second_ratio = hr_second / pwr_second
        decoupling = round((second_ratio / first_ratio - 1) * 100, 1) if first_ratio > 0 else None

    lines = ["📈 Streamy:"]
    lines.extend([f"  • {line}" for line in bin_lines])
    if decoupling is not None:
        lines.append(f"  • Dekuplowanie HR vs moc: {decoupling:+.1f}%")
    else:
        lines.append("  • Dekuplowanie HR vs moc: n/d")
    if altitude:
        lines.append(f"  • Altitude samples: {len(altitude)}")
    if cadence:
        lines.append(f"  • Cadence samples: {len(cadence)}")
    return lines


def _handle_garmin_last_activity(text: str) -> dict:
    explicit_req = _resolve_garmin_activity_from_question(text)
    if explicit_req and explicit_req.get("activity_id"):
        activity_id = str(explicit_req["activity_id"])
        try:
            from qbot_garmin_history import read_activity_summary, read_activity_streams
            last = read_activity_summary(activity_id)
            if last.get("error"):
                return _envelope("garmin_last_activity", f"Błąd Garmin: {last.get('error')}", status_override="ERROR")
            streams = read_activity_streams(activity_id)
        except Exception as exc:
            return _envelope("garmin_last_activity", f"Błąd Garmin: {exc}", status_override="ERROR")
    else:
        latest = _load_latest_garmin_activity()
        if latest.get("status") == "ERROR":
            return _envelope("garmin_last_activity", str(latest.get("error", "Błąd Garmin")), status_override="ERROR")
        if latest.get("status") == "NO_DATA":
            return _envelope(
                "garmin_last_activity",
                str(latest.get("answer", "brak aktywności Garmin")),
                data=latest.get("data") or {},
                sources_used=["garmin_connect_api"],
                status_override="NO_DATA",
            )
        last = latest.get("activity") or {}
        activity_id = _get_garmin_activity_id(text, last)
        if not activity_id:
            streams = {"error": "streams unavailable", "available": ["missing_activity_id"]}
        else:
            try:
                from qbot_garmin_history import read_activity_streams
                streams = read_activity_streams(activity_id)
            except Exception as exc:
                streams = {"error": f"streams unavailable: {exc}", "available": ["read_activity_streams"]}

    data = dict(last)
    data["streams"] = streams

    title = last.get("title") or last.get("activity_type") or "ostatnia aktywność"
    started_at = last.get("started_at") or last.get("date") or "n/d"
    dist_km = f"{float(last.get('distance_km')):.1f}" if last.get("distance_km") is not None else "n/d"
    duration_s = last.get("duration_sec") or last.get("elapsed_duration_sec")
    duration = "n/d"
    if duration_s is not None:
        try:
            total = int(float(duration_s))
            duration = f"{total // 3600}:{(total % 3600) // 60:02d}"
        except (TypeError, ValueError):
            pass
    elevation = f"{int(round(float(last['elevation_gain_m'])))}" if last.get("elevation_gain_m") is not None else "n/d"
    avg_hr = f"{int(round(float(last['avg_hr'])))}" if last.get("avg_hr") is not None else "n/d"
    max_hr = f"{int(round(float(last['max_hr'])))}" if last.get("max_hr") is not None else "n/d"
    avg_power = f"{int(round(float(last['avg_power_w'])))}" if last.get("avg_power_w") is not None else "n/d"
    np_value = last.get("normalized_power_w")
    if np_value is None:
        raw_json = last.get("raw_json") if isinstance(last.get("raw_json"), dict) else {}
        np_value = raw_json.get("normPower") or raw_json.get("normalizedPower") or raw_json.get("normalized_power")
    np_text = f"{int(round(float(np_value)))}" if np_value is not None else "n/d"
    load = f"{float(last['training_load']):.1f}" if last.get("training_load") is not None else "n/d"
    calories = f"{int(round(float(last['calories_kcal'])))}" if last.get("calories_kcal") is not None else "n/d"

    parts = [
        f"🚴 {title}",
        f"🕒 Start: {started_at}",
        f"📏 Dystans: {dist_km} km",
        f"⏱️ Czas: {duration}",
        f"⛰️ Przewyższenie: {elevation} m",
        f"❤️ HR: śr {avg_hr} / max {max_hr}",
        f"⚡ Moc: śr {avg_power} W / NP {np_text} W",
        f"🏋️ Training load: {load}",
        f"🔥 Kalorie: {calories} kcal",
    ]
    parts.extend(_garmin_stream_summary(streams))
    if streams.get("error"):
        parts.append("ℹ️ Streamy niedostępne, ale podsumowanie aktywności zwrócone normalnie.")

    answer = "\n".join(parts)
    return _envelope("garmin_last_activity", answer, data=data, sources_used=["garmin_connect_api"])


def _handle_garmin_activity_streams(text: str) -> dict:
    latest = {"data": {}}
    explicit_req = _resolve_garmin_activity_from_question(text)
    if explicit_req and explicit_req.get("activity_id"):
        activity_id = str(explicit_req["activity_id"])
        try:
            from qbot_garmin_history import read_activity_summary, read_activity_streams
            last = read_activity_summary(activity_id)
            if last.get("error"):
                return _envelope("garmin_activity_streams", f"Błąd Garmin: {last.get('error')}", status_override="ERROR")
            streams = read_activity_streams(activity_id)
        except Exception as exc:
            return _envelope("garmin_activity_streams", f"Błąd Garmin: {exc}", status_override="ERROR")
    else:
        latest = _load_latest_garmin_activity()
        if latest.get("status") == "ERROR":
            return _envelope("garmin_activity_streams", str(latest.get("error", "Błąd Garmin")), status_override="ERROR")
        if latest.get("status") == "NO_DATA":
            return _envelope(
                "garmin_activity_streams",
                str(latest.get("answer", "brak aktywności Garmin")),
                data=latest.get("data") or {},
                sources_used=["garmin_connect_api"],
                status_override="NO_DATA",
            )

        last = latest.get("activity") or {}
        activity_id = _get_garmin_activity_id(text, last)
        if not activity_id:
            streams = {"error": "streams unavailable", "available": ["missing_activity_id"]}
        else:
            try:
                from qbot_garmin_history import read_activity_streams
                streams = read_activity_streams(activity_id)
            except Exception as exc:
                streams = {"error": f"streams unavailable: {exc}", "available": ["read_activity_streams"]}

    streams_error = str(streams.get("error", ""))
    if streams_error and (
        "dev_data_index" in streams_error
        or "No such field" in streams_error
        or streams_error == "streams unavailable"
    ):
        activity_date = str(last.get("date") or "").strip()
        try:
            parsed_date = datetime.fromisoformat(activity_date[:10]).date() if activity_date else None
        except Exception:
            parsed_date = None
        if parsed_date is not None:
            fit_path = _find_local_fit_file_for_date(parsed_date)
            if fit_path:
                try:
                    parsed_fit = _parse_fit_safe(fit_path)
                    local_streams = dict(parsed_fit.get("streams") or {})
                    local_streams["available"] = parsed_fit.get("streams", {}).get("available", ["local_fit"])
                    local_streams["source"] = "local_fit"
                    local_streams["fit_path"] = str(fit_path)
                    local_streams["fallback_reason"] = streams_error
                    streams = local_streams
                except Exception:
                    pass

    data = {
        "activity": last,
        "streams": streams,
        "resolved_activity_id": activity_id,
        "resolved_range": latest.get("data", {}).get("resolved_range", {}),
        "count": latest.get("data", {}).get("count", 0),
    }

    title = last.get("title") or last.get("activity_type") or "ostatnia aktywność"
    started_at = last.get("started_at") or last.get("date") or "n/d"
    parts = [
        f"🚴 {title}",
        f"🕒 Start: {started_at}",
        f"📈 Streamy aktywności:",
    ]
    parts.extend(_garmin_stream_summary(streams)[1:])
    if streams.get("error"):
        parts.append("ℹ️ Streamy niedostępne, ale podsumowanie aktywności zwrócone normalnie.")

    return _envelope("garmin_activity_streams", "\n".join(parts), data=data, sources_used=["garmin_connect_api"])


def _handle_garmin_activity_export(text: str) -> dict:
    explicit_req = _resolve_garmin_activity_from_question(text)
    if explicit_req and explicit_req.get("activity_id"):
        activity_id = str(explicit_req["activity_id"])
        ql = text.lower()
        fmt = explicit_req.get("format") or "fit"
    else:
        latest = _load_latest_garmin_activity()
        if latest.get("status") == "ERROR":
            return _envelope("garmin_activity_export", str(latest.get("error", "Błąd Garmin")), status_override="ERROR")
        if latest.get("status") == "NO_DATA":
            return _envelope(
                "garmin_activity_export",
                str(latest.get("answer", "brak aktywności Garmin")),
                data=latest.get("data") or {},
                sources_used=["garmin_connect_api"],
                status_override="NO_DATA",
            )

        last = latest.get("activity") or {}
        activity_id = _get_garmin_activity_id(text, last)
        if not activity_id:
            return _envelope(
                "garmin_activity_export",
                "brak aktywności Garmin",
                data={"resolved_range": latest.get("data", {}).get("resolved_range", {}), "activity": last},
                sources_used=["garmin_connect_api"],
                status_override="NO_DATA",
            )
        ql = text.lower()
        fmt = "fit"
        if "gpx" in ql:
            fmt = "gpx"
        elif "csv" in ql:
            fmt = "csv"

    try:
        from qbot_garmin_history import export_activity_artifact, read_activity_summary
        export = export_activity_artifact(activity_id, fmt=fmt)
        last = read_activity_summary(activity_id)
    except Exception as exc:
        return _envelope("garmin_activity_export", f"Błąd eksportu Garmin: {exc}", status_override="ERROR")

    if not export.get("ok"):
        return _envelope(
            "garmin_activity_export",
            f"Export Garmin niedostępny: {export.get('error', 'unknown')}",
            data={"activity_id": activity_id, "format": fmt, "available": export.get("available", [])},
            sources_used=["garmin_connect_api"],
            status_override="ERROR" if export.get("status") == "ERROR" else "PARTIAL",
        )

    answer = (
        f"📦 Export Garmin aktywności {activity_id} ({fmt.upper()})\n"
        f"• activity: {last.get('title') or last.get('activity_type') or 'n/d'}\n"
        f"• artifact_path: {export.get('file_path') or export.get('artifact_path') or 'n/d'}\n"
        f"• filename: {export.get('filename') or 'n/d'}"
    )
    data = {"activity_id": activity_id, "format": fmt, "activity": last, "export": export}
    return _envelope("garmin_activity_export", answer, data=data, sources_used=["garmin_connect_api"])


def _handle_garmin_activity_detail(text: str) -> dict:
    req = _parse_garmin_activity_detail_request(text)
    activity_id = str(req["activity_id"]) if req and req.get("activity_id") else ""
    if not activity_id:
        match = _GARMIN_ACTIVITY_DETAIL_ID.search(text or "")
        activity_id = match.group(1) if match else ""

    if not activity_id:
        return _envelope("garmin_activity_detail", "brak activity_id", status_override="PARTIAL")

    try:
        details = garmin_client().get_activity_details(activity_id)
    except Exception as exc:
        return _envelope("garmin_activity_detail", f"Błąd Garmin: {exc}", status_override="ERROR")

    answer = json.dumps(details, ensure_ascii=False, default=str, indent=2)
    data = {"activity_id": activity_id, "details": details}
    return _envelope("garmin_activity_detail", answer, data=data, sources_used=["garmin_connect_api"])


_FIT_BASE_DIR = "/opt/qbot/app/outgoing/michal/hammerhead_originals"
_FIT_EN_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _parse_fit_query_target(query: str) -> dict[str, Any]:
    q = (query or "").strip()
    ql = q.lower()

    target: dict[str, Any] = {}

    uuid_match = re.search(r"\b([0-9a-f]{8,}(?:-[0-9a-f]{4,}){0,4})\b", ql, re.IGNORECASE)
    if uuid_match:
        target["uuid_fragment"] = uuid_match.group(1).lower()
        return target

    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", ql)
    if iso_match:
        try:
            target["date"] = datetime.fromisoformat(iso_match.group(1)).date()
            return target
        except Exception:
            pass

    en_match = re.search(
        r"\b(?:jun|june|jan|january|feb|february|mar|march|apr|april|may|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+(\d{1,2})(?:\s+(\d{4}))?\b",
        ql,
    )
    if en_match:
        month_match = re.search(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:\s+(\d{4}))?\b",
            ql,
        )
        if month_match:
            month_key = month_match.group(1)[:3].lower()
            month = _FIT_EN_MONTHS.get(month_key)
            day = int(month_match.group(2))
            year = int(month_match.group(3)) if month_match.group(3) else _TODAY.year
            if month:
                try:
                    target["date"] = date(year, month, day)
                    return target
                except Exception:
                    pass

    parsed = _parse_date_from_question(q)
    if parsed:
        try:
            target["date"] = datetime.fromisoformat(parsed).date()
            return target
        except Exception:
            pass

    return target


def _fit_json_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, tuple)):
        return [_fit_json_scalar(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _fit_json_scalar(v) for k, v in value.items()}
    return str(value)


def _find_local_fit_file_for_date(target_date: date, base_dir: str = _FIT_BASE_DIR):
    from pathlib import Path

    base_path = Path(base_dir)
    if not base_path.exists():
        return None

    best_path = None
    best_score = None
    for path in base_path.rglob("*.fit"):
        if not path.is_file():
            continue
        try:
            st = path.stat()
            file_date = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).astimezone(WARSAW).date()
            day_delta = abs((file_date - target_date).days)
            ts_delta = abs((st.st_mtime - datetime.combine(target_date, datetime.min.time(), tzinfo=WARSAW).timestamp()))
            score = (day_delta, ts_delta, -st.st_mtime)
        except Exception:
            continue
        if best_score is None or score < best_score:
            best_score = score
            best_path = path
    return best_path


def _parse_fit_safe(fit_path: str | Path) -> dict[str, Any]:
    from pathlib import Path
    from statistics import mean

    try:
        from fitparse import FitFile
        import fitparse.base as fit_base
        import fitparse.records as fit_records
    except ImportError:
        raise

    path = Path(fit_path)
    orig_get_dev_type = fit_records.get_dev_type
    orig_base_get_dev_type = fit_base.get_dev_type
    try:
        def _safe_get_dev_type(dev_data_index, field_def_num):
            try:
                return orig_get_dev_type(dev_data_index, field_def_num)
            except Exception:
                return fit_records.DevField(
                    dev_data_index=dev_data_index,
                    def_num=field_def_num,
                    type=fit_records.BASE_TYPES[0x0D],
                    name=f"unknown_dev_{dev_data_index}_{field_def_num}",
                    units=None,
                    native_field_num=None,
                )

        fit_records.get_dev_type = _safe_get_dev_type
        fit_base.get_dev_type = _safe_get_dev_type
        fit = FitFile(str(path), check_crc=False)
        field_values: dict[str, list[Any]] = {}
        record_count = 0
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
            try:
                record_count += 1
                row: dict[str, Any] = {}
                ts = None
                for field in msg:
                    try:
                        name = getattr(field, "name", None)
                        if not name:
                            continue
                        value = getattr(field, "value", None)
                        field_values.setdefault(str(name), []).append(value)
                        if name == "timestamp":
                            ts = value
                        elif name == "distance":
                            row["distance"] = value
                        elif name == "heart_rate":
                            row["heart_rate"] = value
                        elif name == "power":
                            row["power"] = value
                        elif name == "altitude":
                            row["altitude"] = value
                        elif name == "cadence":
                            row["cadence"] = value
                    except Exception:
                        continue
                if ts is not None:
                    if first_ts is None:
                        first_ts = ts
                    try:
                        streams["time"].append(int((ts - first_ts).total_seconds()))
                    except Exception:
                        streams["time"].append(None)
                    distance_value = row.get("distance")
                    if distance_value is not None:
                        last_distance = distance_value
                    else:
                        distance_value = last_distance
                    streams["distance"].append(distance_value)
                    streams["heart_rate"].append(row.get("heart_rate"))
                    streams["power"].append(row.get("power"))
                    streams["altitude"].append(row.get("altitude"))
                    streams["cadence"].append(row.get("cadence"))
            except Exception:
                continue
    finally:
        try:
            fit_records.get_dev_type = orig_get_dev_type
            fit_base.get_dev_type = orig_base_get_dev_type
        except Exception:
            pass

    channels = []
    for name in sorted(field_values.keys()):
        values = [v for v in field_values[name] if v not in (None, "")]
        preview = [_fit_json_scalar(v) for v in values[:3]]
        numeric_values = [
            float(v) for v in values
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        channel = {
            "name": name,
            "n_probek": len(values),
            "samples": preview,
        }
        if numeric_values:
            channel.update({
                "min": min(numeric_values),
                "max": max(numeric_values),
                "avg": round(mean(numeric_values), 3),
            })
        channels.append(channel)

    streams["available"] = ["local_fit"]
    streams["source"] = "local_fit"
    return {
        "fit_path": str(path),
        "record_count": record_count,
        "channels": channels,
        "streams": streams,
        "sources_used": ["filesystem", "fitparse"],
    }


def _handle_fit_file_analyze(query: str, params: dict[str, Any] | None = None) -> dict:
    params = params or {}
    try:
        from pathlib import Path
    except Exception as exc:
        return _envelope("fit_file_analyze", f"Błąd inicjalizacji: {exc}", status_override="ERROR")

    base_dir = Path(_FIT_BASE_DIR)
    if not base_dir.exists():
        return _envelope(
            "fit_file_analyze",
            f"Brak katalogu bazowego FIT: {base_dir}",
            status_override="ERROR",
        )

    target = _parse_fit_query_target(query)
    all_files = sorted(
        [p for p in base_dir.rglob("*.fit") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not target:
        files = []
        for path in all_files:
            st = path.stat()
            files.append({
                "filename": path.name,
                "path": str(path),
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).astimezone(WARSAW).strftime("%Y-%m-%d %H:%M:%S"),
                "size_bytes": st.st_size,
            })
        answer = "Podaj datę lub fragment UUID. Dostępne pliki FIT:\n" + "\n".join(
            f"- [{rec['mtime']}] {rec['filename']} ({rec['size_bytes']} B)" for rec in files
        )
        return _envelope(
            "fit_file_analyze",
            answer,
            data={"available_files": files, "base_dir": str(base_dir)},
            sources_used=["filesystem"],
        )

    matched: list[Path] = []
    uuid_fragment = str(target.get("uuid_fragment", "")).lower()
    target_date = target.get("date")
    for path in all_files:
        name_l = path.name.lower()
        if uuid_fragment and uuid_fragment not in name_l:
            continue
        if target_date is not None:
            try:
                if datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(WARSAW).date() != target_date:
                    continue
            except Exception:
                continue
        matched.append(path)

    if not matched:
        files = []
        for path in all_files:
            st = path.stat()
            files.append({
                "filename": path.name,
                "path": str(path),
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).astimezone(WARSAW).strftime("%Y-%m-%d %H:%M:%S"),
                "size_bytes": st.st_size,
            })
        criteria = target_date.isoformat() if target_date else uuid_fragment
        return _envelope(
            "fit_file_analyze",
            f"Nie znaleziono FIT dla: {criteria}",
            data={"available_files": files, "criteria": criteria, "base_dir": str(base_dir)},
            status_override="PARTIAL",
            sources_used=["filesystem"],
        )

    fit_path = matched[0]
    try:
        parsed_fit = _parse_fit_safe(fit_path)
    except ImportError as exc:
        return _envelope(
            "fit_file_analyze",
            f"Brak fitparse: {exc}",
            data={"fit_path": str(fit_path)},
            status_override="ERROR",
            sources_used=["filesystem"],
        )
    except Exception as exc:
        return _envelope(
            "fit_file_analyze",
            f"Błąd parsowania FIT: {exc}",
            data={"fit_path": str(fit_path)},
            status_override="ERROR",
            sources_used=["filesystem", "fitparse"],
        )

    channels = parsed_fit["channels"]
    record_count = parsed_fit["record_count"]
    lines = [f"FIT: {fit_path.name}", f"Recordy: {record_count}", f"Kanaly: {len(channels)}"]
    for ch in channels:
        line = f"- {ch['name']}: n={ch['n_probek']}"
        if "min" in ch:
            line += f" min={ch['min']} max={ch['max']} avg={ch['avg']}"
        line += f" sample={json.dumps(ch['samples'], ensure_ascii=False)}"
        lines.append(line)

    return _envelope(
        "fit_file_analyze",
        "\n".join(lines),
        data={
            "fit_path": str(fit_path),
            "matched_files": [str(p) for p in matched],
            "record_count": record_count,
            "channels": channels,
            "base_dir": str(base_dir),
            "query_target": {
                "date": target_date.isoformat() if target_date else None,
                "uuid_fragment": uuid_fragment or None,
            },
        },
        sources_used=["filesystem", "fitparse"],
    )


def _handle_training_recent(text: str) -> dict:
    days = 7
    m = re.search(r"ostatnie\s*(\d+)", text.lower())
    if m:
        days = int(m.group(1))
    since = _TODAY - timedelta(days=days)

    try:
        pg = _pg_conn()
        rows = _safe_fetch(pg, """
            SELECT date, started_at, sport_type, distance_m, duration_s, elevation_m,
                   avg_power_w, normalized_power_w, tss, avg_hr_bpm, activity_name
            FROM qbot_v2.training_sessions
            WHERE date >= %s
            ORDER BY date DESC, started_at DESC
        """, (since,))
        pg.close()
    except Exception as exc:
        return _envelope("training_recent", f"Błąd połączenia: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        return _envelope("training_recent", f"Brak treningów od {since}.")

    parts = [f"🏆 Treningi od {since} ({len(rows)} sesji):"]
    for r in rows:
        sport = r.get("sport_type") or "trening"
        dist = r.get("distance_m")
        dur_s = r.get("duration_s")
        dist_km = f"{dist/1000:.1f}km" if dist else ""
        dur_str = f"{dur_s//60}min" if dur_s else ""
        tss = r.get("tss")
        np = r.get("normalized_power_w")
        hr = r.get("avg_hr_bpm")
        line = f"   📅 {r['date']} {sport}"
        if dist_km or dur_str:
            line += f" — {dist_km} {dur_str}"
        if np:
            line += f" — NP {np:.0f}W"
        if tss:
            line += f" — TSS {tss:.0f}"
        if hr:
            line += f" — HR {hr}bpm"
        parts.append(line)

    answer = "\n".join(parts)
    data = {"count": len(rows), "rows": rows, "resolved_since": str(since), "resolved_days": days}
    return _envelope("training_recent", answer, data=data,
                     sources_used=["qbot_v2.training_sessions"],
                     freshness={"range_since": str(since), "range_days": days})


def _xert_live_fetch() -> dict | None:
    """Live fetch from Xert API with full extraction. Only used for explicit queries."""
    try:
        from qbot3.connectors.import_xert_profile_snapshot import fetch_full_xert
        return fetch_full_xert()
    except Exception:
        return None


def _xert_save_snapshot(pg, data: dict, source: str = "query_vnext_live") -> None:
    """Insert a new xert_profile_snapshot from live data (expanded fields)."""
    import datetime as _dt_mod
    now = _dt_mod.datetime.now(_dt_mod.timezone.utc)
    raw = json.dumps(data.get("raw_json", {}), default=str)
    pg.execute(
        """INSERT INTO qbot_v2.xert_profile_snapshots
           (snapshot_at, date, source,
            ftp_power_w, ltp_power_w, w_prime_kj, peak_power_w,
            training_load, recovery_load, form_ratio, ts_rating,
            form_status, freshness, fatigue, difficulty,
            quality_status, raw_json, imported_at)
           VALUES (%s, %s, %s,
                   %s, %s, %s, %s,
                   %s, %s, %s, %s,
                   %s, %s, %s, %s,
                   %s, %s, %s)""",
        (now, now.date(), source,
         data.get("ftp_watts"), data.get("ltp_watts"), data.get("w_prime_kj"), data.get("peak_power_w"),
         data.get("training_load"), data.get("recovery_load"), data.get("form_ratio"), data.get("ts_rating"),
         data.get("form_status"), data.get("freshness"), data.get("fatigue"), data.get("difficulty"),
         "full", raw, now),
    )
    pg.commit()


def _handle_xert_live_fetch(text: str) -> dict:
    """Diagnostic live fetch — tylko dla jawnych zapytań o odświeżenie."""
    try:
        pg = _pg_conn()
    except Exception as exc:
        return _envelope("xert_live_fetch", f"Błąd połączenia: {exc}", status_override="ERROR")

    live_data = _xert_live_fetch()
    if not live_data:
        pg.close()
        return _envelope("xert_live_fetch",
                         "Live fetch Xert API nie powiódł się. Spróbuj później lub sprawdź XERT_EMAIL/XERT_PASSWORD.",
                         missing_sources=["xert_api"], status_override="PARTIAL")

    try:
        _xert_save_snapshot(pg, live_data, source="manual_live_fetch")
        pg.commit()
    except Exception as exc:
        pg.close()
        return _envelope("xert_live_fetch", f"Xert API OK, ale błąd zapisu snapshotu: {exc}",
                         status_override="PARTIAL")

    pg.close()
    parts = [f"✅ Live fetch Xert wykonany — snapshot zapisany."]
    if live_data.get("ftp_watts") is not None:
        parts.append(f"⚡ FTP: {live_data['ftp_watts']:.0f}W")
    if live_data.get("ltp_watts") is not None:
        parts.append(f"🔻 LTP: {live_data['ltp_watts']:.0f}W")
    if live_data.get("w_prime_kj") is not None:
        parts.append(f"🔋 W': {live_data['w_prime_kj']:.1f}kJ")

    answer = "\n".join(parts)
    return _envelope("xert_live_fetch", answer, data=live_data,
                     sources_used=["xert_api", "qbot_v2.xert_profile_snapshots"])


def _handle_xert_status(text: str) -> dict:
    """Standard Xert handler — tylko odczyt ostatniego snapshotu z DB.
    Live fetch domyślnie WYŁĄCZONY (polityka: jeden snapshot dziennie z cron)."""
    try:
        pg = _pg_conn()
        rows = _safe_fetch(pg, """
            SELECT * FROM qbot_v2.xert_profile_snapshots
            ORDER BY snapshot_at DESC NULLS LAST
            LIMIT 1
        """)
        pg.close()
    except Exception as exc:
        return _envelope("xert_status", f"Błąd połączenia: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        err = rows[0].get("_error") if rows else "no rows"
        return _envelope("xert_status", "Brak danych Xert w DB. Kolejny snapshot o 00:15 z cron.",
                         missing_sources=["qbot_v2.xert_profile_snapshots"],
                         warnings=[err] if err != "no rows" else [])

    r = rows[0]
    freshness = {}
    if r.get("snapshot_at"):
        freshness["xert_snapshot_at"] = str(r["snapshot_at"])
    if r.get("imported_at"):
        freshness["xert_imported_at"] = str(r["imported_at"])

    source_label = r.get("source", "?")
    snapshot_at = r.get("snapshot_at", "?")

    parts = []
    if r.get("ftp_power_w") is not None:
        parts.append(f"⚡ FTP: {r['ftp_power_w']:.0f}W")
    if r.get("ltp_power_w") is not None:
        parts.append(f"🔻 LTP: {r['ltp_power_w']:.0f}W")
    if r.get("w_prime_kj") is not None:
        parts.append(f"🔋 W': {r['w_prime_kj']:.1f}kJ")
    if r.get("peak_power_w") is not None:
        parts.append(f"💥 PP: {r['peak_power_w']:.0f}W")
    if r.get("form_status"):
        parts.append(f"📊 Form status: {r['form_status']}")
    if r.get("form_ratio") is not None:
        parts.append(f"📈 Form ratio: {r['form_ratio']:.3f}")
    if r.get("ts_rating") is not None:
        parts.append(f"🎯 TS: {r['ts_rating']:.3f}")
    if r.get("training_load") is not None:
        parts.append(f"🏋️  Training load: {r['training_load']:.1f}")
    if r.get("recovery_load") is not None:
        parts.append(f"💆 Recovery load: {r['recovery_load']:.1f}")
    if r.get("freshness") is not None:
        parts.append(f"🆕 Freshness: {r['freshness']:.1f}")
    if r.get("fatigue") is not None:
        parts.append(f"😫 Fatigue: {r['fatigue']:.1f}")
    if r.get("difficulty") is not None:
        parts.append(f"📊 Difficulty: {r['difficulty']:.0f}")
    parts.append(f"🕐 Snapshot: {snapshot_at} (źródło: {source_label})")

    answer = "\n".join(parts) if parts else "Dane Xert — brak szczegółów."
    data = dict(r)
    data["resolved_date"] = str(r.get("date") or _TODAY)
    data["source_type"] = source_label

    return _envelope("xert_status", answer, data=data,
                     sources_used=["qbot_v2.xert_profile_snapshots"],
                     freshness=freshness)


def _handle_xert_snapshot_range(text: str) -> dict:
    ql = (text or "").lower()
    today = datetime.now(WARSAW).date()

    explicit_dates: list[date] = []
    for match in re.findall(r"(\d{4}-\d{2}-\d{2})", text or ""):
        try:
            explicit_dates.append(datetime.strptime(match, "%Y-%m-%d").date())
        except ValueError:
            continue

    if explicit_dates:
        date_from = min(explicit_dates)
        date_to = max(explicit_dates)
    elif "miesiąc" in ql or "miesiac" in ql:
        date_from = today - timedelta(days=30)
        date_to = today
    elif "tydzień" in ql or "tydzien" in ql:
        date_from = today - timedelta(days=7)
        date_to = today
    else:
        date_from = today - timedelta(days=30)
        date_to = today

    try:
        pg = _pg_conn()
        rows = _safe_fetch(pg, """
            SELECT snapshot_at, date, ftp_power_w, ltp_power_w, w_prime_kj, peak_power_w,
                   training_load, recovery_load, freshness, fatigue, form_status,
                   form_ratio, ts_rating, difficulty
            FROM qbot_v2.xert_profile_snapshots
            WHERE date BETWEEN %s AND %s
            ORDER BY snapshot_at
        """, (date_from, date_to))
        pg.close()
    except Exception as exc:
        return _envelope("xert_snapshot_range", f"Błąd połączenia: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        err = rows[0].get("_error") if rows else "no rows"
        return _envelope("xert_snapshot_range",
                         "Brak snapshotów w podanym zakresie",
                         data={"date_from": str(date_from), "date_to": str(date_to), "rows": []},
                         missing_sources=["qbot_v2.xert_profile_snapshots"],
                         warnings=[err] if err != "no rows" else [])

    if len(rows) == 1:
        only_date = rows[0].get("date")
        return _envelope(
            "xert_snapshot_range",
            f"Brak historii — dostępny tylko jeden snapshot z {only_date}",
            data={"date_from": str(date_from), "date_to": str(date_to), "rows": rows},
            sources_used=["qbot_v2.xert_profile_snapshots"],
        )

    answer = f"Znaleziono {len(rows)} snapshotów Xert w zakresie {date_from} – {date_to}."
    return _envelope(
        "xert_snapshot_range",
        answer,
        data={"date_from": str(date_from), "date_to": str(date_to), "rows": rows},
        sources_used=["qbot_v2.xert_profile_snapshots"],
    )


# ---------------------------------------------------------------------------
# Garage / Gear
# ---------------------------------------------------------------------------
GARAGE_DB = "/opt/qbot/app/data/garage.db"

GARAGE_ALIASES: dict[str, list[str]] = {
    "kask": ["helmet", "headwear"], "kaski": ["helmet", "headwear"], "kasków": ["helmet", "headwear"], "kasku": ["helmet", "headwear"],
    "buty": ["shoes", "shoe"], "obuwie": ["shoes", "shoe"],
    "rekawiczki": ["gloves"], "rękawiczki": ["gloves"], "rękawiczek": ["gloves"], "rekawiczek": ["gloves"], "rękawiczkach": ["gloves"],
    "kurtka": ["jacket"], "kurtki": ["jacket"],
    "kamizelka": ["vest", "gilet"], "kamizelki": ["vest", "gilet"], "gilet": ["vest"],
    "koszulka": ["jersey", "shirt"], "koszulki": ["jersey", "shirt"],
    "jersey": ["jersey", "shirt"], "jerseye": ["jersey", "shirt"],
    "spodnie": ["pants", "trousers", "bib tight"],
    "spodenki": ["shorts", "bib"], "bibsy": ["shorts", "bib"],
    "skarpety": ["socks"], "skarpetki": ["socks"],
    "czapka": ["cap", "headwear"], "czapki": ["cap", "headwear"],
    "komin": ["neck warmer", "buff"], "chusta": ["buff", "neck warmer"], "buff": ["neck warmer"],
    "kola": ["wheels", "wheelset"], "koła": ["wheels", "wheelset"],
    "opony": ["tires", "tyres", "tire", "tyre"], "opona": ["tire", "tyre"],
    "kaseta": ["cassette"],
    "korba": ["crank", "crankset"],
    "lancuch": ["chain"], "łańcuch": ["chain"],
    "hamulce": ["brakes", "brake"],
    "siodlo": ["saddle"], "siodło": ["saddle"],
    "kierownica": ["handlebar"],
    "torba": ["bag", "pack"], "torby": ["bag", "pack"],
    "namiot": ["tent"],
    "base layer": ["base layer"], "bielizna": ["base layer"],
    "but": ["shoes", "shoe"],
}



def _stem_polish(word: str) -> list[str]:
    """Strip common Polish noun suffixes to get base forms for search."""
    results = {word}
    suffixes = ["ów", "ow", "ach", "ami", "om", "ek", "ka", "ki", "ków", "kow",
                "ów", "em", "ie", "ów", "ce", "ów", "ek", "ko"]
    for s in suffixes:
        if word.endswith(s) and len(word) - len(s) >= 3:
            results.add(word[:-len(s)])
    # Also add without Polish diacritics
    import unicodedata
    for w in list(results):
        nfkd = unicodedata.normalize('NFKD', w)
        ascii_w = ''.join(c for c in nfkd if not unicodedata.combining(c))
        if ascii_w != w:
            results.add(ascii_w)
    return list(results)


def _expand_search_terms(raw_terms: list[str]) -> list[str]:
    """Expand search terms with PL→EN aliases."""
    expanded = []
    seen = set()
    for term in raw_terms:
        if term in seen:
            continue
        seen.add(term)
        expanded.append(term)
        aliases = GARAGE_ALIASES.get(term)
        if aliases:
            for a in aliases:
                if a not in seen:
                    seen.add(a)
                    expanded.append(a)
    return expanded


def _handle_garage_status(text: str) -> dict:
    used = []
    missing = []
    data = {}

    try:
        conn = _sqlite_conn()

        # bikes
        try:
            bikes_raw = conn.execute("SELECT id, name, brand, model, type, year, color, active FROM bikes").fetchall()
            bikes = [dict(r) for r in bikes_raw]
            active_bikes = [b for b in bikes if b.get("active")]
            data["bikes_count"] = len(active_bikes)
            data["bikes_total"] = len(bikes)
            data["bikes"] = [{"id": b["id"], "name": b["name"], "brand": b.get("brand"), "model": b.get("model"), "type": b.get("type")} for b in active_bikes]
            used.append("garage.db.bikes")
        except Exception as exc:
            missing.append("bikes")

        # components
        try:
            comps = conn.execute("SELECT COUNT(*) FROM components WHERE active=1").fetchone()[0]
            data["components_count"] = comps
            used.append("garage.db.components")
        except Exception:
            missing.append("components")

        # gear
        try:
            gear_total = conn.execute("SELECT COUNT(*) FROM gear WHERE active=1").fetchone()[0]
            data["gear_count"] = gear_total
            gear_cats = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM gear WHERE active=1 GROUP BY category ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            data["gear_top_categories"] = [{"category": r[0], "count": r[1]} for r in gear_cats]
            used.append("garage.db.gear")
        except Exception:
            missing.append("gear")

        conn.close()
    except Exception as exc:
        return _envelope("garage_status", f"Błąd dostępu do garage.db: {exc}", status_override="ERROR")

    if not data:
        return _envelope("garage_status", "Brak danych garażu.", missing_sources=missing, warnings=["no garage data"])

    parts = [f"🏠 Garaż QBot:"]
    if data.get("bikes_count") is not None:
        parts.append(f"🚲 Rowery: {data['bikes_count']}")
        for b in data.get("bikes", []):
            parts.append(f"   • {b['name']} ({b.get('brand','?')} {b.get('model','?')})")
    if data.get("components_count") is not None:
        parts.append(f"🔧 Komponenty: {data['components_count']}")
    if data.get("gear_count") is not None:
        parts.append(f"👕 Sprzęt/odzież: {data['gear_count']} pozycji")
        top = data.get("gear_top_categories", [])
        if top:
            cat_strs = [f"{c['category']} ({c['count']})" for c in top[:5]]
        parts.append(f"   Top kategorie: {', '.join(cat_strs)}")

    answer = "\n".join(parts)
    return _envelope("garage_status", answer, data=data, sources_used=used, missing_sources=missing)


STOP_WORDS = {
    "pokaż", "szukaj", "jakie", "mam", "co", "mojego", "moje", "moja",
    "proszę", "czy", "ma", "są", "się", "znajdź",
}


def _sql_like_clause(columns: list[str], terms: list[str]) -> tuple[str, list[str]]:
    """Build a parameterized WHERE clause with LIKE."""
    clauses = []
    params = []
    for col in columns:
        for t in terms:
            clauses.append(f"LOWER({col}) LIKE ?")
            params.append(f"%{t}%")
    return (" OR ".join(clauses), params)


def _handle_garage_search(text: str) -> dict:
    used = []
    missing = []
    warnings = []
    query = text.strip()
    ql = query.lower()
    results = []
    matched_tables = []
    alias_used = False

    # Strip punctuation from each token before processing
    import re as _re_gs
    raw_terms = [_re_gs.sub(r"[^\w\u00C0-\u024F]", "", t) for t in ql.split()]
    raw_terms = [t for t in raw_terms if len(t) > 2 and t not in STOP_WORDS]
    if not raw_terms:
        raw_terms = [_re_gs.sub(r"[^\w\u00C0-\u024F]", "", ql)]
    # Stem Polish words for better matching
    stemmed = []
    for t in raw_terms:
        stemmed.extend(_stem_polish(t))
    raw_terms = list(set(stemmed)) if stemmed else raw_terms

    expanded_terms = _expand_search_terms(raw_terms)
    alias_used = expanded_terms != raw_terms

    try:
        conn = _sqlite_conn()

        # gear
        try:
            clause, params = _sql_like_clause(
                ["category", "brand", "model"], expanded_terms
            )
            gear_rows = conn.execute(
                f"SELECT id, category, brand, model, size, color, condition FROM gear WHERE active=1 AND ({clause}) LIMIT 20",
                params,
            ).fetchall()
            if gear_rows:
                results.extend([dict(r) for r in gear_rows])
                matched_tables.append("gear")
        except Exception:
            missing.append("gear")

        # bikes
        try:
            clause, params = _sql_like_clause(
                ["name", "brand", "model", "type"], expanded_terms
            )
            bike_rows = conn.execute(
                f"SELECT id, name, brand, model, type, year, color FROM bikes WHERE active=1 AND ({clause}) LIMIT 10",
                params,
            ).fetchall()
            if bike_rows:
                results.extend([dict(r) for r in bike_rows])
                matched_tables.append("bikes")
        except Exception:
            missing.append("bikes")

        # components
        try:
            clause, params = _sql_like_clause(
                ["category", "brand", "model"], expanded_terms
            )
            comp_rows = conn.execute(
                f"SELECT id, bike_id, category, brand, model, position FROM components WHERE active=1 AND ({clause}) LIMIT 10",
                params,
            ).fetchall()
            if comp_rows:
                results.extend([dict(r) for r in comp_rows])
                matched_tables.append("components")
        except Exception:
            missing.append("components")

        conn.close()
    except Exception as exc:
        return _envelope("garage_search", f"Błąd dostępu do garage.db: {exc}", status_override="ERROR")

    for tbl in matched_tables:
        used.append(f"garage.db.{tbl}")

    # Helmet-first: jeśli search zawiera helmet i mamy wyniki Helmet, usuń Headwear
    if results and any("helmet" in str(t).lower() for t in expanded_terms):
        helmet_results = [r for r in results if str(r.get("category","")).lower() == "helmet"]
        if helmet_results:
            results = helmet_results

    if not results:
        return _envelope("garage_search", f"Nie znaleziono nic dla: {query}.",
                         missing_sources=missing,
                         data={"query": query, "original_terms": raw_terms, "expanded_terms": expanded_terms,
                               "alias_used": alias_used, "result_count": 0, "results": []})

    parts = [f"🔍 Znaleziono {len(results)} pozycji dla: {query}"]
    if alias_used:
        parts.append(f"   ↳ Rozszerzone terminy: {', '.join(expanded_terms)}")
    for r in results[:10]:
        tbl_hint = "🚲" if ("name" in r and "category" not in r) else "👕"
        name = r.get("name") or r.get("model") or ""
        brand = r.get("brand") or ""
        color = r.get("color") or ""
        extra = f" ({color})" if color else ""
        parts.append(f"   {tbl_hint} {brand} {name}{extra}" if brand else f"   {tbl_hint} {name}{extra}")

    answer = "\n".join(parts)

    data = {
        "query": query,
        "original_terms": raw_terms,
        "expanded_terms": expanded_terms,
        "alias_used": alias_used,
        "matched_tables": matched_tables,
        "result_count": len(results),
        "results": results[:20],
    }

    status = "PARTIAL" if missing else "OK"
    return _envelope("garage_search", answer, data=data, sources_used=used,
                     missing_sources=missing, warnings=warnings)


# ---------------------------------------------------------------------------
# Nutrition range
# ---------------------------------------------------------------------------
def _parse_explicit_date(s: str) -> date | None:
    """Parse a single date in YYYY-MM-DD or DD.MM.YYYY format."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    return None


def _parse_explicit_range(text: str) -> tuple[date, date, str] | None:
    """Return (date_from, date_to, error_or_empty) or None if no explicit range found."""
    ql = text.lower().strip()

    # Patterns:
    # od/za okres/między DATE do/a/do DATE
    # Also bare: DATE do DATE, DATE - DATE

    patterns = [
        # "od YYYY-MM-DD do YYYY-MM-DD"
        # "między YYYY-MM-DD a YYYY-MM-DD"
        # "za okres YYYY-MM-DD do YYYY-MM-DD"
        r"(?:od|za okres|od dnia|miedzy|między|miedzy)\s+(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})\s+(?:do|a|–|-)\s+(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})",
        # Bare: "YYYY-MM-DD do YYYY-MM-DD" or "YYYY-MM-DD - YYYY-MM-DD"
        r"(\d{4}-\d{2}-\d{2})\s+(?:do|–|-)\s+(\d{4}-\d{2}-\d{2})",
        # Bare: "DD.MM.YYYY do DD.MM.YYYY" or "DD.MM.YYYY - DD.MM.YYYY"
        r"(\d{2}\.\d{2}\.\d{4})\s+(?:do|–|-)\s+(\d{2}\.\d{2}\.\d{4})",
    ]

    for pat in patterns:
        m = re.search(pat, ql)
        if m:
            d1 = _parse_explicit_date(m.group(1))
            d2 = _parse_explicit_date(m.group(2))
            if d1 and d2:
                return (d1, d2, "")
    return None


def _parse_range(text: str) -> tuple[date, date] | None:
    """Return (date_from, date_to) inclusive, or None."""
    ql = text.lower().strip()

    # Try explicit range first (od X do Y etc.)
    explicit = _parse_explicit_range(text)
    if explicit:
        d1, d2, err = explicit
        return (d1, d2)

    # "od poniedziałku" — Monday of current week
    if "od poniedziałku" in ql:
        days_since_monday = _TODAY.weekday()
        monday = _TODAY - timedelta(days=days_since_monday)
        return (monday, _TODAY)

    # "ostatnie X dni" or "ostatnich X dni"
    m = re.search(r"ostatni[ech]\s*(\d+)", ql)
    if m:
        days = int(m.group(1))
        return (_TODAY - timedelta(days=days - 1), _TODAY)

    # "ostatni tydzień" = 7 days
    if "ostatni tydzień" in ql or "ostatniego tygodnia" in ql:
        return (_TODAY - timedelta(days=6), _TODAY)

    # "7 dni" or "14 dni" etc — bare number + dni in a nutrition context
    m = re.search(r"(\d+)\s*dni", ql)
    if m:
        days = int(m.group(1))
        return (_TODAY - timedelta(days=days - 1), _TODAY)

    return None


RANGE_INDICATORS = [
    "ostatnie", "ostatnich", "ostatni tydzień", "ostatniego tygodnia",
    "od poniedziałku", "zakres",
]

EXPLICIT_RANGE_PATTERNS = [
    r"od\s+\d{4}-\d{2}-\d{2}\s+do",
    r"od\s+\d{2}\.\d{2}\.\d{4}\s+do",
    r"(?:miedzy|między|miedzy)\s+\d{4}-\d{2}-\d{2}\s+a",
    r"(?:miedzy|między|miedzy)\s+\d{2}\.\d{2}\.\d{4}\s+a",
    r"za\s+okres\s+\d{4}-\d{2}-\d{2}",
    r"za\s+okres\s+\d{2}\.\d{2}\.\d{4}",
    r"\d{4}-\d{2}-\d{2}\s+(?:do|–|-)\s+\d{4}-\d{2}-\d{2}",
    r"\d{2}\.\d{2}\.\d{4}\s+(?:do|–|-)\s+\d{2}\.\d{2}\.\d{4}",
]



# ── Multi-intent: domeny i ich sygnaly ─────────────────────────────────────
_DOMAIN_SIGNALS: dict[str, list[str]] = {
    "nutrition": ["kalorii", "kcal", "jedzenie", "jad\u0142em", "jadlem", "jad\u0142am", "jadlam", "bilans", "bia\u0142ko", "bialko",
                  "wegle", "tluszcz", "makro", "nutrition", "posilek", "spozycle",
                  "intake", "dieta", "kaloryczny"],
    "body": ["body composition", "sklad ciala", "body fat", "tkanka tluszczowa",
             "masa miesniowa", "bmi", "waga", "body comp", "body_comp",
             "pomiary ciala", "wyniki wazenia"],
    "sleep": ["sen", "spalem", "spa\u0142em", "sleep", "spanie", "spaniu", "regeneracja snu", "spa\u0142am"],
    "wellness": ["hrv", "wellness", "bateria", "body battery", "tetno spoczynkowe",
                 "resting hr", "stres"],
    "training": ["trening", "treningi", "aktywnosc", "jazda", "jezddem", "sport",
                 "training", "workout", "aktywnosc fizyczna"],
    "energy": ["energia", "wydatek", "spalone", "spalony", "kroki", "steps", "energy"],
    "xert": ["xert", "forma", "ftp", "freshness", "fatigue", "gotowość", "gotowosc", "readiness"],
    "trip": ["etap", "stage", "toskania", "tuscany", "atrakcje"],
}

_DOMAIN_TO_HANDLER: dict[str, str] = {
    "nutrition": "daily_balance",
    "body": "body_comp",
    "sleep": "sleep_day",
    "wellness": "wellness_day",
    "training": "training_recent",
    "energy": "energy_day",
    "xert": "xert_status",
    "trip": "trip_stages",
}


def _detect_domains(question: str) -> list[str]:
    # Early exit: pytania o POI na etapie to single-domain trip, nie multi
    _ql_dd = question.lower()
    _TRIP_POI_PHRASES = ["jedzenie etap", "jedzenie na etapie", "zaopatrzenie etap",
                         "zaopatrzenie na etapie", "co zjem na etapie",
                         "sklepy etap", "sklep na etapie", "woda etap",
                         "woda na etapie", "atrakcje etap", "poi etap",
                         "toskania jedzenie", "etap jedzenie", "etap toskania jedzenie",
                         "tuscany jedzenie", "etap woda", "etap sklep", "etap sklepy"]
    if any(p in _ql_dd for p in _TRIP_POI_PHRASES):
        return ["trip"]
    # Pytania o gotowość/formę przed wyjazdem — trip to tylko kontekst, nie domena danych
    # Wykluczamy 'trip' zeby nie routowac do trip_stages ktory zwroci ERROR
    _READINESS_PHRASES = [
        "gotowy na", "gotowa na", "gotowosc na", "gotowos na",
        "czy moge jechac", "czy dam rade", "forma przed",
        "forma na toskanie", "forma przed toskania", "forma na tuscany",
        "ocen forme", "ocen moja forme", "moja forma przed",
        "readiness", "czy jestem gotowy", "czy jestem gotowa",
        "przygotowany na", "przygotowana na",
    ]
    if any(p in _ql_dd for p in _READINESS_PHRASES):
        # Wykryj domeny ale bez trip — trip to kontekst geograficzny, nie zrodlo danych
        ql = _ql_dd
        found = []
        for domain, signals in _DOMAIN_SIGNALS.items():
            if domain == "trip":
                continue
            if domain == "nutrition" and "xert" in ql:
                continue
            if any(s in ql for s in signals):
                found.append(domain)
        # Jesli brak innych domen, fallback do xert (forma)
        if not found:
            found = ["xert"]
        return found
    """Wykryj domeny w pytaniu - zwroc liste gdy >1."""
    ql = question.lower()
    found = []
    for domain, signals in _DOMAIN_SIGNALS.items():
        if domain == "nutrition" and "xert" in ql:
            continue
        if any(s in ql for s in signals):
            found.append(domain)
    return found


def _handle_multi_intent(question: str, domains: list[str]) -> dict:
    """Wywolaj wiele handlerow i scalaj odpowiedzi."""
    results = []
    errors = []

    for domain in domains:
        intent = _DOMAIN_TO_HANDLER.get(domain)
        if not intent:
            continue
        try:
            _dt = _parse_date_from_question(question)
            _day = _today_or(str(_dt) if _dt else None)
            if intent == "daily_balance":
                r = _handle_daily_balance(str(_day))
            elif intent == "nutrition_range":
                r = _handle_nutrition_range(question)
            elif intent == "body_comp":
                r = _handle_body_comp(str(_day))
            elif intent == "body_measurements_range":
                r = _handle_body_measurements_range(question)
            elif intent == "sleep_day":
                r = _handle_sleep_day(str(_day))
            elif intent == "wellness_day":
                r = _handle_wellness_day(str(_day))
            elif intent == "training_recent":
                r = _handle_training_recent(question)
            elif intent == "energy_day":
                r = _handle_energy_day(_dt)
            elif intent == "xert_status":
                r = _handle_xert_status(question)
            elif intent == "trip_stages":
                r = _handle_trip_stages(question)
            elif intent == "weight_lookup":
                r = _handle_weight_lookup(str(_day))
            else:
                continue

            if r.get("status") not in ("ERROR",):
                results.append((domain, r.get("answer", "")))
            else:
                errors.append(domain)
        except Exception as exc:
            errors.append(f"{domain}:{exc}")

    if not results:
        domains_str = ", ".join(domains) if domains else "nieznane"
        err_str = ("; ".join(str(e) for e in errors)) if errors else "brak odpowiedzi"
        msg = (f"Nie udalo sie pobrac danych dla domen: {domains_str}.\n"
               f"Bledy: {err_str}\n"
               f"Sprobuj pytac osobno, np. 'moja forma xert' lub 'sen dzisiaj'.")
        return _envelope("multi_intent", msg, status_override="PARTIAL")

    # Scal odpowiedzi
    parts = []
    for domain, answer in results:
        label = {
            "nutrition": "🍽️ ŻYWIENIE",
            "body": "📊 SKŁAD CIAŁA",
            "sleep": "😴 SEN",
            "wellness": "💓 WELLNESS",
            "training": "🚴 TRENING",
            "energy": "⚡ ENERGIA",
            "xert": "📈 FORMA (XERT)",
            "trip": "🗺️ TRASA/ETAP",
        }.get(domain, domain.upper())
        parts.append(f"{label}\n{answer}")

    combined = "\n\n".join(parts)
    if errors:
        combined += f"\n\n⚠️ Błąd dla: {', '.join(str(e) for e in errors)}"

    return _envelope("multi_intent", combined,
                     data={"domains": domains, "results_count": len(results)},
                     sources_used=list(_DOMAIN_TO_HANDLER.values()))


def _has_range_indicator(text: str) -> bool:
    ql = text.lower()
    for ind in RANGE_INDICATORS:
        if ind in ql:
            return True
    # Check explicit range patterns
    for pat in EXPLICIT_RANGE_PATTERNS:
        if re.search(pat, ql):
            return True
    # Also check "X dni" pattern in a nutrition/balance context
    if re.search(r"\d+\s*dni", ql):
        return True
    return False


MAX_RANGE_DAYS = 31


def _handle_nutrition_range(text: str) -> dict:
    fallback_reason = None
    warnings = []
    used = []
    missing = []

    rng = _parse_range(text)
    if not rng:
        date_from = _TODAY - timedelta(days=6)
        date_to = _TODAY
    else:
        date_from, date_to = rng

    # Validate date order
    if date_from > date_to:
        date_from, date_to = date_to, date_from
        warnings.append("Odwrócona kolejność dat — zamieniono date_from z date_to")

    # Validate range <= MAX_RANGE_DAYS
    range_days = (date_to - date_from).days + 1
    if range_days > MAX_RANGE_DAYS:
        return _envelope(
            "nutrition_range",
            f"Zakres {range_days} dni przekracza limit {MAX_RANGE_DAYS} dni. "
            f"Podaj mniejszy zakres (maksymalnie {MAX_RANGE_DAYS} dni).",
            data={"date_from": str(date_from), "date_to": str(date_to),
                  "days_requested": range_days, "max_days": MAX_RANGE_DAYS},
            warnings=[f"Zakres {range_days}d > limit {MAX_RANGE_DAYS}d"],
            status_override="PARTIAL",
        )

    try:
        pg = _pg_conn()

        # Try qbot_v2.nutrition_daily_summary first
        rows = _safe_fetch(pg, """
            SELECT date, kcal_total, carbs_total, protein_total, fat_total, source, computed_at
            FROM qbot_v2.nutrition_daily_summary
            WHERE date BETWEEN %s AND %s
            ORDER BY date
        """, (date_from, date_to))
        used_v2 = rows and "_error" not in rows[0] and len(rows) > 0
        if used_v2:
            used.append("qbot_v2.nutrition_daily_summary")
        else:
            # Fallback to public
            rows = _safe_fetch(pg, """
                SELECT date, kcal_total, carbs_total, protein_total, fat_total, source, computed_at
                FROM public.nutrition_daily_summary
                WHERE date BETWEEN %s AND %s
                ORDER BY date
            """, (date_from, date_to))
            if rows and "_error" not in rows[0] and len(rows) > 0:
                used.append("public.nutrition_daily_summary")
                fallback_reason = "public.nutrition_daily_summary used as fallback"
                warnings.append("public.nutrition_daily_summary (LEGACY) — qbot_v2 nie ma danych dla tego zakresu")
            else:
                missing.append("nutrition_daily_summary")

        # Daily summary for expenditure/balance
        ds_rows = _safe_fetch(pg, """
            SELECT date, intake_kcal, expenditure_total, balance_kcal,
                   intake_protein_g, intake_carbs_g, intake_fat_g
            FROM qbot_v2.daily_summary
            WHERE date BETWEEN %s AND %s
            ORDER BY date
        """, (date_from, date_to))
        if ds_rows and "_error" not in ds_rows[0] and len(ds_rows) > 0:
            used.append("qbot_v2.daily_summary")

        pg.close()
    except Exception as exc:
        return _envelope("nutrition_range", f"Błąd połączenia: {exc}", status_override="ERROR")

    # Build per-day map from nutrition summary
    nutr_by_date: dict[str, dict] = {}
    if rows and "_error" not in rows[0]:
        for r in rows:
            d = str(r["date"])
            nutr_by_date[d] = {
                "kcal_total": r.get("kcal_total"),
                "carbs_total": r.get("carbs_total"),
                "protein_total": r.get("protein_total"),
                "fat_total": r.get("fat_total"),
            }

    # Build per-day map from daily summary
    ds_by_date: dict[str, dict] = {}
    if ds_rows and "_error" not in ds_rows[0]:
        for r in ds_rows:
            d = str(r["date"])
            ds_by_date[d] = {
                "intake_kcal": r.get("intake_kcal"),
                "expenditure_total": r.get("expenditure_total"),
                "balance_kcal": r.get("balance_kcal"),
            }

    # Merge into per_day list
    per_day = []
    totals = {"intake_kcal": 0, "expenditure_kcal": 0, "balance_kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    totals_count = {"intake_kcal": 0, "expenditure_kcal": 0, "balance_kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    missing_days = []

    current = date_from
    while current <= date_to:
        ds = str(current)
        entry: dict[str, Any] = {"date": ds}
        had_data = False

        n = nutr_by_date.get(ds)
        if n:
            entry.update(n)
            had_data = True
            if n.get("kcal_total") is not None:
                totals["intake_kcal"] += n["kcal_total"]
                totals_count["intake_kcal"] += 1
            if n.get("protein_total") is not None:
                totals["protein_g"] += n["protein_total"]
                totals_count["protein_g"] += 1
            if n.get("carbs_total") is not None:
                totals["carbs_g"] += n["carbs_total"]
                totals_count["carbs_g"] += 1
            if n.get("fat_total") is not None:
                totals["fat_g"] += n["fat_total"]
                totals_count["fat_g"] += 1

        dse = ds_by_date.get(ds)
        if dse:
            # Kopiuj tylko potrzebne pola — NIE intake_kcal (Garmin, myli GPT)
            for _k in ("expenditure_total", "balance_kcal"):
                if _k in dse:
                    entry[_k] = dse[_k]
            had_data = True
            if dse.get("expenditure_total") is not None:
                totals["expenditure_kcal"] += dse["expenditure_total"]
                totals_count["expenditure_kcal"] += 1
            # Bilans: preferuj QBot intake - expenditure
            # Pomijaj dni bez zadnego intake (dzien niepelny)
            _our_intake = n.get("kcal_total") if n else None
            _expenditure = dse.get("expenditure_total")
            _garmin_intake = dse.get("intake_kcal")
            if _our_intake is not None and _expenditure is not None:
                _bal = _our_intake - _expenditure
            elif _garmin_intake is not None and _garmin_intake > 0 and _expenditure is not None:
                _bal = _garmin_intake - _expenditure
            else:
                _bal = None  # dzien bez intake — nie wliczaj do bilansu
            if _bal is not None:
                totals["balance_kcal"] += _bal
                totals_count["balance_kcal"] += 1
            # Nadpisz balance_kcal w entry obliczonym bilansem (nie Garmin)
            entry["balance_kcal"] = _bal
            # If no nutrition summary but daily_summary has intake, use that
            if not n and dse.get("intake_kcal") is not None:
                totals["intake_kcal"] += dse["intake_kcal"]
                totals_count["intake_kcal"] += 1

        per_day.append(entry)
        if not had_data:
            missing_days.append(ds)
        current += timedelta(days=1)

    # Build answer
    # ── Tabela per-day ──────────────────────────────────────────────
    hdr = f"  {'Data':<12} {'Kcal':>6} {'B':>5} {'W':>5} {'T':>5} {'Bilans':>7}"
    sep = "  " + "-" * (len(hdr) - 2)
    table_lines = [hdr, sep]
    for e in per_day:
        d    = str(e.get("date",""))[:10]
        kcal = f'{e["kcal_total"]:.0f}' if e.get("kcal_total") is not None else "—"
        prot = f'{e["protein_total"]:.0f}g' if e.get("protein_total") is not None else "—"
        carb = f'{e["carbs_total"]:.0f}g' if e.get("carbs_total") is not None else "—"
        fat  = f'{e["fat_total"]:.0f}g' if e.get("fat_total") is not None else "—"
        _ei = e.get("kcal_total"); _ex = e.get("expenditure_total")
        bal  = f'{(_ei-_ex):+.0f}' if (_ei is not None and _ex is not None) else "—"
        table_lines.append(f"  {d:<12} {kcal:>6} {prot:>5} {carb:>5} {fat:>5} {bal:>7}")
    table_lines.append(sep)

    parts = [f"📊 Bilans od {date_from} do {date_to} ({len(per_day)} dni):", ""]
    parts.extend(table_lines)
    parts.append("")
    if totals_count["intake_kcal"] > 0:
        avg = totals["intake_kcal"] / totals_count["intake_kcal"]
        parts.append(f"🍽️  Zjedzone: {totals['intake_kcal']:.0f} kcal (śr. {avg:.0f}/d)")
    if totals_count["expenditure_kcal"] > 0:
        avg = totals["expenditure_kcal"] / totals_count["expenditure_kcal"]
        parts.append(f"🔥 Spalone: {totals['expenditure_kcal']:.0f} kcal (śr. {avg:.0f}/d)")
    if totals_count["balance_kcal"] > 0:
        avg = totals["balance_kcal"] / totals_count["balance_kcal"]
        parts.append(f"⚖️  Bilans: {totals['balance_kcal']:+.0f} kcal (śr. {avg:+.0f}/d)")
    if totals_count["protein_g"] > 0:
        parts.append(f"🥩 Białko: {totals['protein_g']:.0f}g | Węgle: {totals['carbs_g']:.0f}g | Tłuszcz: {totals['fat_g']:.0f}g")
    if missing_days:
        parts.append(f"⚠️  Brak danych dla: {', '.join(missing_days[:5])}{'...' if len(missing_days) > 5 else ''}")

    answer = "\n".join(parts)

    data = {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "days_count": len(per_day),
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "per_day": per_day,
        "missing_days": missing_days,
    }

    for k in list(totals_count.keys()):
        if totals_count[k] == 0:
            data["totals"].pop(k, None)

    if not used:
        return _envelope("nutrition_range", f"Brak danych nutrition dla zakresu {date_from} – {date_to}.",
                         missing_sources=missing, warnings=["no data found"])

    return _envelope("nutrition_range", answer, data=data, sources_used=used,
                     missing_sources=missing, warnings=warnings, fallback_reason=fallback_reason)


# ---------------------------------------------------------------------------
# Memories search
# ---------------------------------------------------------------------------
MEMORY_EXTRACT_PATTERNS = [
    r"(?:co wiem o|co pamiętasz o|co wiesz o|znajdź w notatkach|znajdź w pamięci|pokaż fakty o|szukaj w pamięci|szukaj w notatkach|przypomnij mi o)\s+(.+)",
    r"(?:co wiem|co pamiętasz|co wiesz|pokaż notatki|pokaż pamięć)\s*(.*)",
]


def _extract_memory_query(text: str) -> str:
    ql = text.lower().strip()
    for pat in MEMORY_EXTRACT_PATTERNS:
        m = re.search(pat, ql)
        if m:
            return m.group(1).strip()
    return ""


def _handle_memories_search(text: str) -> dict:
    try:
        conn = _sqlite_conn()
    except Exception as exc:
        return _envelope("memories_search", f"Błąd dostępu do garage.db: {exc}", status_override="ERROR")

    search_term = _extract_memory_query(text)

    try:
        if search_term:
            like = f"%{search_term}%"
            rows = conn.execute(
                "SELECT id, topic, content, created_at, updated_at FROM memories "
                "WHERE LOWER(topic) LIKE ? OR LOWER(content) LIKE ? ORDER BY updated_at DESC LIMIT 10",
                (like, like),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, topic, content, created_at, updated_at FROM memories ORDER BY updated_at DESC LIMIT 10"
            ).fetchall()

        results = []
        for r in rows:
            content = r["content"] or ""
            results.append({
                "id": r["id"],
                "topic": r["topic"],
                "content_preview": content[:300] + ("..." if len(content) > 300 else ""),
                "content_len": len(content),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            })

        conn.close()
    except Exception as exc:
        conn.close()
        return _envelope("memories_search", f"Błąd zapytania: {exc}", status_override="ERROR")

    if not results:
        # Fallback: szukaj w qbot_planning_facts
        pf_results = []
        try:
            _pg2 = _pg_conn()
            import re as _re_mem
            _st_clean = _re_mem.sub(r"[^\w\u00C0-\u024F]", " ", search_term or "toskania").strip()
            # Mapuj PL→EN dla tytułów w DB
            _PL_EN = {"toskania": "tuscany", "toskanii": "tuscany", "toskani": "tuscany",
                      "florencja": "florence"}
            for _pl, _en in _PL_EN.items():
                if _pl in _st_clean.lower():
                    _st_clean = _en
                    break
            _pf_like = f"%{_st_clean}%" if _st_clean else "%tuscany%"
            _pf_rows = _safe_fetch(_pg2, """
                SELECT id, fact_type, title, date, status
                FROM qbot_v2.qbot_planning_facts
                WHERE LOWER(title) LIKE %s OR LOWER(fact_type) LIKE %s
                ORDER BY date DESC LIMIT 10
            """, (_pf_like, _pf_like))
            _pg2.close()
            if _pf_rows and "_error" not in _pf_rows[0]:
                pf_results = _pf_rows
        except Exception:
            pass

        if pf_results:
            _pf_parts = [f"\U0001f9e0 Brak w memories, znaleziono w planning_facts ({len(pf_results)}):"]
            for _pf in pf_results:
                _pf_parts.append(f"  [{_pf.get('fact_type','?')}] {_pf.get('title','?')} ({_pf.get('date','?')})")
            return _envelope("memories_search", "\n".join(_pf_parts),
                             data={"query": search_term, "planning_facts": pf_results, "result_count": len(pf_results)},
                             sources_used=["sqlite.memories", "qbot_v2.qbot_planning_facts"])

        return _envelope("memories_search",
                         f"W memories nie znaleziono pasujących wpisów dla: {search_term}" if search_term else "Brak notatek w pamięci.",
                         data={"query": search_term or "(all)", "result_count": 0, "results": []},
                         sources_used=["sqlite.memories"])

    parts = [f"📝 Znaleziono {len(results)} wpisów w pamięci:"]
    for r in results:
        prev = (r["content_preview"][:80] + "...") if r["content_preview"] else ""
        parts.append(f"   • {r['topic']}")
        if prev:
            parts.append(f"     {prev}")

    answer = "\n".join(parts)
    data = {
        "query": search_term or "(all)",
        "result_count": len(results),
        "results": results,
    }

    return _envelope("memories_search", answer, data=data, sources_used=["sqlite.memories"])


# ---------------------------------------------------------------------------
# Trips status
# ---------------------------------------------------------------------------
TRIPS_SEARCH_MAP = {
    "tuscany trail": ["tuscany trail", "tuscany"],
    "tuscany": ["tuscany"],
    "toskania": ["tuscany", "toskania"],
    "toskanii": ["tuscany", "toskania"],
    "toskanię": ["tuscany", "toskania"],
    "toskanie": ["tuscany", "toskania"],
}


def _extract_trip_terms(text: str) -> list[str]:
    ql = text.lower()
    # Check for known trip keywords
    for phrase, terms in TRIPS_SEARCH_MAP.items():
        if phrase in ql:
            return terms
    # "wyjazd do X" — extract X
    m = re.search(r"wyjazd[^\s]*\s+(?:do|na|w)\s+(.+)", ql)
    if m:
        return [m.group(1).strip()]
    return []



# ── Trip stages (generic, DB-backed) ──────────────────────────────────
def _handle_trip_summary(text: str) -> dict:
    """Podsumowanie wszystkich etapów: suma km, D+, najdłuższy, najkrótszy."""
    ql = text.lower()
    try:
        pg = _pg_conn()
        rows = _safe_fetch(pg, """
            SELECT fact_json->>'stages' as stages_json
            FROM qbot_v2.qbot_planning_facts
            WHERE fact_type='route_stages'
            ORDER BY date DESC LIMIT 1
        """)
        pg.close()
    except Exception as exc:
        return _envelope("trip_summary", f"Błąd: {exc}", status_override="ERROR")

    if not rows or "_error" in rows[0]:
        return _envelope("trip_summary", "Brak planów etapów w bazie.")

    import json
    stages = json.loads(rows[0]["stages_json"] or "[]")
    if not stages:
        return _envelope("trip_summary", "Brak etapów w planie.")

    total_km = sum(float(s.get("distance_km") or 0) for s in stages)
    longest = max(stages, key=lambda s: float(s.get("distance_km") or 0))
    shortest = min(stages, key=lambda s: float(s.get("distance_km") or 0))

    lines = [f"📊 Podsumowanie trasy ({len(stages)} etapów):",
             f"  Łącznie: {total_km:.1f} km",
             f"  Najdłuższy: Etap {longest.get('stage')} — {longest.get('segment','?')} ({longest.get('distance_km')} km)",
             f"  Najkrótszy: Etap {shortest.get('stage')} — {shortest.get('segment','?')} ({shortest.get('distance_km')} km)",
             "",
             "  Etapy:"]
    for s in sorted(stages, key=lambda x: x.get("stage", 0)):
        lines.append(f"  {s.get('stage','?')}: {s.get('segment','?')} — {s.get('distance_km','?')} km")

    return _envelope("trip_summary", "\n".join(lines),
                     data={"stages": stages, "total_km": total_km,
                           "longest": longest, "shortest": shortest},
                     sources_used=["qbot_v2.qbot_planning_facts"])


def _handle_trip_stages(text: str) -> dict:
    # Deleguj agregacje do trip_summary
    if any(w in text.lower() for w in ["najdłuższy", "najdluzszy",
                                        "najkrótszy", "najkrotszy",
                                        "łącznie", "lacznie", "razem", "suma"]):
        return _handle_trip_summary(text)

    try:
        from tools.trip_stages import handle_trip_stages
        res = handle_trip_stages(text)
        return _envelope("trip_stages", res.get("answer", ""), data=res.get("data"), sources_used=res.get("sources"))
    except Exception as exc:
        return _envelope("trip_stages", f"Błąd trip_stages: {exc}", status_override="ERROR")

# ── Trip attractions (generic, DB-backed) ─────────────────────────────
def _handle_trip_attractions(text: str) -> dict:
    try:
        from tools.trip_attractions import handle_trip_attractions
        res = handle_trip_attractions(text)
        return _envelope("trip_attractions", res.get("answer", ""), data=res.get("data"), sources_used=res.get("sources"))
    except Exception as exc:
        return _envelope("trip_attractions", f"Błąd trip_attractions: {exc}", status_override="ERROR")


def _handle_rwgps_route_find(question: str) -> dict:
    try:
        from tools.rwgps.route_find import find_routes

        candidates = find_routes(question, limit=5)
        matched = [item for item in candidates if int(item.get("score", 0) or 0) > 0]
        if matched:
            top = matched[:5]
            lines = ["🚴 RWGPS — wyniki wyszukiwania tras:"]
            for item in top:
                lines.append(
                    f"  [{item.get('route_id')}] {item.get('name')} | {item.get('distance_km')} km | +{item.get('elevation_m')} m | {item.get('updated_at')}"
                )
            answer = "\n".join(lines)
            status_override = "OK"
            data = {"query": question, "matches": top, "candidates": candidates}
        else:
            top = candidates[:5]
            names = [str(item.get("name") or "") for item in candidates[:5] if item.get("name")]
            answer = "Brak pewnych trafień. Najbliższe nazwy: " + ", ".join(names) if names else "Brak trafień."
            status_override = "PARTIAL"
            data = {"query": question, "matches": [], "candidates": candidates, "closest_names": names}
        return _envelope("rwgps_route_find", answer, data=data, sources_used=["rwgps"], status_override=status_override)
    except Exception as exc:
        return _envelope("rwgps_route_find", f"Błąd wyszukiwania tras: {exc}", status_override="ERROR")


def _handle_rwgps_route_import_gpx(question: str) -> dict:
    albert_result = _escalate_to_albert(question, "rwgps_route_import_gpx_slot_gate")
    if isinstance(albert_result, dict) and (albert_result.get("artifact_id") or albert_result.get("new_route_id")):
        return albert_result

    try:
        from qbot3.adapters.mcp_adapter import _execute_rwgps_import
        from tools.rwgps.route_find import find_routes
        import base64
        project_id = "tuscany_2026"
        resolved_candidates = find_routes(question, limit=10)
        resolved_route_id = ""
        for candidate in resolved_candidates:
            route_id_text = str(candidate.get("route_id") or "").strip()
            if route_id_text.isdigit():
                resolved_route_id = route_id_text
                break
        if not resolved_route_id:
            return _envelope(
                "rwgps_route_import_gpx",
                "Nie udało się rozwiązać route_id dla importu RWGPS.",
                status_override="PARTIAL",
                data={"query": question, "candidates": resolved_candidates[:5]},
                fallback_reason="rwgps_route_import_gpx_slot_gate",
            )
        import_key = f"qbot_query_route_import:{project_id}:{resolved_route_id}"

        result = _execute_rwgps_import(
            "rwgps_route_import_gpx",
            {
                "route_name_hint": question,
                "find_latest": True,
                "import_to_artifacts": True,
            },
            import_key,
        )
        if isinstance(result, dict):
            if not result.get("artifact_id") and result.get("source_gpx_path"):
                try:
                    with open(str(result["source_gpx_path"]), "rb") as fh:
                        artifact_b64 = base64.b64encode(fh.read()).decode("ascii")
                    from qbot3.adapters.mcp_adapter import _execute_qbot_artifact_put

                    artifact_record = _execute_qbot_artifact_put(
                        "qbot_artifact_put",
                        {
                            "project_id": "tuscany_2026",
                            "artifact_type": "route",
                            "filename": f"rwgps_{result.get('resolved_route_id') or result.get('route_id') or 'route'}.gpx",
                            "content_base64": artifact_b64,
                            "title": str(result.get("route_name") or result.get("resolved_route_name") or question),
                            "source": "rwgps",
                            "mutation_type": "import",
                            "confirm": True,
                        },
                        f"{import_key}:artifact",
                    )
                    if artifact_record:
                        result["artifact_id"] = artifact_record.get("artifact_id") or artifact_record.get("artifact_store_id")
                        result["artifact_path"] = artifact_record.get("file_path") or artifact_record.get("path")
                        result["artifact_status"] = artifact_record.get("status") or "registered"
                        if not result.get("artifact_id") and artifact_record.get("status") == "CONFLICT":
                            try:
                                from qbot3.artifacts.store import search_artifacts

                                existing = search_artifacts(
                                    query=f"rwgps_{result.get('resolved_route_id') or result.get('route_id') or 'route'}.gpx",
                                    project_id=project_id,
                                    artifact_type="route",
                                    status="active",
                                    limit=1,
                                )
                                if existing:
                                    result["artifact_id"] = existing[0].get("artifact_id")
                                    result["artifact_path"] = existing[0].get("file_path")
                                    result["artifact_status"] = "registered"
                            except Exception:
                                pass
                except Exception:
                    pass
            result["escalation_reason"] = "rwgps_route_import_gpx_slot_gate"
            result["fallback_reason"] = "rwgps_route_import_gpx_slot_gate"
            return result
    except Exception as exc:
        return _envelope(
            "rwgps_route_import_gpx",
            f"Blad importu RWGPS: {exc}",
            status_override="ERROR",
            fallback_reason="rwgps_route_import_gpx_slot_gate",
        )

    return albert_result

def _handle_rwgps_route_profile_sample(question: str) -> dict:
    import re as _re
    ql = question.lower()

    route_id = None
    route_id_m = _re.search(r"\b(?:trasa|route)\s*(\d{7,8})\b", ql)
    if route_id_m:
        route_id = route_id_m.group(1)
    else:
        rid_m = _re.search(r"(?<![\d.])(\d{7,8})(?![\d.])", ql)
        if rid_m:
            route_id = rid_m.group(1)

    stage_m = _re.search(r"\b(?:etap|stage)[a-ząćęłńóśźż]*\s*(\d+)\b", ql)
    stage_n = int(stage_m.group(1)) if stage_m else None
    route_id = _resolve_tuscany_e07_live_route_id(question, stage_num=stage_n, route_id=route_id)
    if not route_id and stage_n is not None:
        route_id = _resolve_tuscany_e07_live_route_id(question, stage_num=stage_n)
        if not route_id:
            return _envelope(
                "rwgps_route_profile_sample",
                _stage_spec_error("tuscany_2026", stage_n),
                status_override="PARTIAL",
            )

    km_m = _re.search(r"\bkm\s*(\d+(?:\.\d+)?)\s*[-\u2013]\s*(\d+(?:\.\d+)?)\b", ql)
    if not km_m:
        km_m = _re.search(r"(\d+(?:\.\d+)?)\s*[-\u2013]\s*(\d+(?:\.\d+)?)\s*km\b", ql)
    km_from = float(km_m.group(1)) if km_m else None
    km_to = float(km_m.group(2)) if km_m else None

    sample_m_m = _re.search(r"\bco\s+(\d+(?:\.\d+)?)\s*m\b", ql)
    sample_m = float(sample_m_m.group(1)) if sample_m_m else 100.0

    if not route_id or km_from is None or km_to is None:
        return _escalate_to_albert(
            question,
            "rwgps_route_profile_sample_slot_gate",
        )

    try:
        from tools.rwgps.rwgps_route_profile_sample import rwgps_route_profile_sample
        result = rwgps_route_profile_sample(
            route_id=route_id,
            km_from=km_from,
            km_to=km_to,
            sample_m=sample_m,
        )
        if result.get("status") == "OK":
            summary = result.get("summary", "Profil trasy gotowy.")
            if not isinstance(summary, str):
                summary = json.dumps(summary, ensure_ascii=False, sort_keys=True)
            return _envelope(
                "rwgps_route_profile_sample",
                summary,
                data=result,
                sources_used=["rwgps"],
            )
        return _envelope(
            "rwgps_route_profile_sample",
            "Blad profilu trasy: {}".format(result.get("error", "nieznany")),
            data=result,
            sources_used=["rwgps"],
            status_override="ERROR",
        )
    except Exception as exc:
        return _envelope("rwgps_route_profile_sample", f"Blad: {exc}", status_override="ERROR")

# ── Route generate (Valhalla + tile scoring) ──────────────────────────
def _handle_route_generate(text: str) -> dict:
    try:
        from tools.route_generator import handle_route_generate
        res = handle_route_generate(text)
        return _envelope("route_generate", res.get("answer", ""), data=res.get("data"), sources_used=res.get("sources"))
    except Exception as exc:
        return _envelope("route_generate", f"Błąd route_generate: {exc}", status_override="ERROR")

def _handle_trips_status(text: str) -> dict:
    try:
        conn = _sqlite_conn()
    except Exception as exc:
        return _envelope("trips_status", f"Błąd dostępu do garage.db: {exc}", status_override="ERROR")

    search_terms = _extract_trip_terms(text)
    filtered = len(search_terms) > 0
    results = []

    try:
        if filtered:
            clauses = []
            params = []
            for term in search_terms:
                like = f"%{term}%"
                clauses.append("(LOWER(name) LIKE ? OR LOWER(destination) LIKE ? OR LOWER(country) LIKE ?)")
                params.extend([like, like, like])
            where = " OR ".join(clauses)
            rows = conn.execute(
                f"SELECT * FROM trips WHERE {where} ORDER BY start_date DESC LIMIT 10",
                params,
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM trips ORDER BY start_date DESC LIMIT 10").fetchall()

        for r in rows:
            d = dict(r)
            d.pop("notes", None)
            results.append(d)
        conn.close()
    except Exception as exc:
        conn.close()
        return _envelope("trips_status", f"Błąd zapytania: {exc}", status_override="ERROR")

    if not results:
        return _envelope("trips_status",
                         "Brak wyjazdów w bazie.",
                         data={"original_query": text, "search_terms": search_terms,
                               "filtered": filtered, "result_count": 0, "results": []},
                         sources_used=["sqlite.trips"])

    parts = [f"🗺️ Znaleziono {len(results)} wyjazdów:"]
    for r in results:
        name = r.get("name", "?")
        dest = r.get("destination") or ""
        country = r.get("country") or ""
        sd = r.get("start_date") or ""
        ed = r.get("end_date") or ""
        dist = r.get("distance_km")
        elev = r.get("elevation_m")
        typ = r.get("type") or ""
        st = r.get("status") or ""
        extra = f" ({typ})" if typ else ""
        days = ""
        if sd and ed:
            try:
                from datetime import date as _d
                s = _d.fromisoformat(sd)
                e = _d.fromisoformat(ed)
                days = f", {(e - s).days}d"
            except Exception:
                pass
        parts.append(f"   • {name}{extra}")
        parts.append(f"     📍 {dest}, {country}" if dest and country else f"     📍 {dest or country}" if (dest or country) else "")
        parts.append(f"     📅 {sd} → {ed}{days}")
        if dist:
            parts.append(f"     📏 {dist:.0f} km" + (f", ↑{elev:.0f}m" if elev else ""))
        if st:
            parts.append(f"     📌 Status: {st}")

    answer = "\n".join(parts)
    data = {"original_query": text, "search_terms": search_terms,
            "filtered": filtered, "result_count": len(results), "results": results}

    return _envelope("trips_status", answer, data=data, sources_used=["sqlite.trips"])


def _normalize_project_id(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _load_route_stage_plan(project_id: str = "tuscany_2026") -> dict[str, Any] | None:
    try:
        pg = _pg_conn()
        rows = _safe_fetch(
            pg,
            """
            SELECT id, fact_json
            FROM qbot_v2.qbot_planning_facts
            WHERE fact_type='route_stages'
            ORDER BY id DESC
            LIMIT 20
            """,
        )
        pg.close()
    except Exception:
        return None

    target = _normalize_project_id(project_id)
    for row in rows:
        fact_json = row.get("fact_json")
        if isinstance(fact_json, str):
            try:
                fact_json = json.loads(fact_json or "{}")
            except Exception:
                fact_json = {}
        if not isinstance(fact_json, dict):
            continue
        row_project = _normalize_project_id(fact_json.get("project_id") or fact_json.get("project"))
        if target and row_project and row_project != target:
            continue
        if target and not row_project:
            continue
        stages = fact_json.get("stages")
        if isinstance(stages, list):
            return {"id": row.get("id"), "fact_json": fact_json, "stages": stages}
    return None


def _resolve_stage_route_id(stage_n: int, project_id: str = "tuscany_2026") -> str | None:
    try:
        plan = _load_route_stage_plan(project_id)
        if not plan:
            return None
        for stage in plan.get("stages", []):
            if int(stage.get("stage")) == int(stage_n):
                route_id = stage.get("route_id")
                if route_id in (None, ""):
                    return None
                return str(route_id)
        return None
    except Exception:
        return None


def _stage_spec_error(project_id: str, stage_n: int) -> str:
    return f"brak StageSpec dla project {project_id} stage {stage_n}"


def _resolve_tuscany_route_id(stage_num: int | str | None = None) -> str | None:
    """
    Resolve Tuscany stage->route_id from qbot_planning_facts.
    Accepts either a numeric stage or a free-form string containing the stage number.
    """
    if stage_num is None:
        return None
    try:
        if isinstance(stage_num, int):
            return _resolve_stage_route_id(stage_num, "tuscany_2026")
        m = re.search(r"(?:etap|stage)[a-ząćęłńóśźż]*\s*(\d+)", str(stage_num).lower())
        if m:
            return _resolve_stage_route_id(int(m.group(1)), "tuscany_2026")
        return _resolve_stage_route_id(int(str(stage_num).strip()), "tuscany_2026")
    except Exception:
        return None


_TUSCANY_E07_LIVE_ROUTE_ID = "55567991"
_TUSCANY_E07_ARTIFACT_ROUTE_ID = "55590078"
_TUSCANY_E07_LIVE_ANALYSIS_HINTS = (
    "analiz",
    "analysis",
    "profil",
    "profile",
    "nawierzchn",
    "surface",
    "climb",
    "podjazd",
    "feasibility",
    "poi",
    "final",
    "finalna",
    "aktualna",
    "current",
    "obecna",
    "live",
)


def _is_tuscany_e07_live_analysis_question(question: str | None) -> bool:
    ql = (question or "").lower()
    # Pytania o E07 bywaja bez slowa "Tuscany", wiec nie wymagamy go wprost.
    if not any(kw in ql for kw in ("e07", "etap 7", "stage 7", "tt e07")):
        return False
    return any(kw in ql for kw in _TUSCANY_E07_LIVE_ANALYSIS_HINTS)


def _resolve_tuscany_e07_live_route_id(
    question: str | None = None,
    *,
    stage_num: int | str | None = None,
    route_id: str | None = None,
) -> str | None:
    """Prefer the live Tuscany E07 route for analysis-style questions."""
    ql = (question or "").lower()
    if route_id is not None:
        route_id_text = str(route_id).strip()
        if route_id_text == _TUSCANY_E07_ARTIFACT_ROUTE_ID and _is_tuscany_e07_live_analysis_question(ql):
            return _TUSCANY_E07_LIVE_ROUTE_ID
        return route_id_text or None

    if stage_num is not None:
        try:
            stage_int = int(stage_num)
        except Exception:
            stage_int = None
        if stage_int == 7 and _is_tuscany_e07_live_analysis_question(ql):
            return _TUSCANY_E07_LIVE_ROUTE_ID

    resolved = _resolve_tuscany_route_id(question if question is not None else stage_num)
    if resolved == _TUSCANY_E07_ARTIFACT_ROUTE_ID and _is_tuscany_e07_live_analysis_question(ql):
        return _TUSCANY_E07_LIVE_ROUTE_ID
    return resolved


# ---------------------------------------------------------------------------
# Report diagnostic handlers
# ---------------------------------------------------------------------------
def _diagnose_source_status() -> dict:
    """Check freshness of all data sources for today."""
    # Deleguj zapytania agregujące do trip_summary
    today = _TODAY
    yesterday = today - timedelta(days=1)
    sources = {}

    try:
        pg = _pg_conn()
        # Sleep
        rows = _safe_fetch(pg, "SELECT date, imported_at FROM qbot_v2.sleep_daily WHERE date >= %s ORDER BY date DESC LIMIT 1", (yesterday,))
        if rows and "_error" not in rows[0]:
            sources["sleep_daily"] = {"date": str(rows[0]["date"]), "imported_at": str(rows[0].get("imported_at",""))[:19] if rows[0].get("imported_at") else None}
        else:
            sources["sleep_daily"] = {"status": "no_data"}
        # Wellness
        rows = _safe_fetch(pg, "SELECT date, imported_at FROM qbot_v2.wellness_daily WHERE date >= %s ORDER BY date DESC LIMIT 1", (yesterday,))
        if rows and "_error" not in rows[0]:
            sources["wellness_daily"] = {"date": str(rows[0]["date"]), "imported_at": str(rows[0].get("imported_at",""))[:19] if rows[0].get("imported_at") else None}
        else:
            sources["wellness_daily"] = {"status": "no_data"}
        # Energy
        rows = _safe_fetch(pg, "SELECT date, imported_at FROM qbot_v2.energy_daily WHERE date >= %s ORDER BY date DESC LIMIT 1", (yesterday,))
        if rows and "_error" not in rows[0]:
            sources["energy_daily"] = {"date": str(rows[0]["date"]), "imported_at": str(rows[0].get("imported_at",""))[:19] if rows[0].get("imported_at") else None}
        else:
            sources["energy_daily"] = {"status": "no_data"}
        # Training sessions
        rows = _safe_fetch(pg, "SELECT date, started_at FROM qbot_v2.training_sessions WHERE date >= %s ORDER BY date DESC LIMIT 1", (yesterday,))
        if rows and "_error" not in rows[0]:
            sources["training_sessions"] = {"date": str(rows[0]["date"]), "started_at": str(rows[0].get("started_at",""))[:19] if rows[0].get("started_at") else None}
        else:
            sources["training_sessions"] = {"status": "no_data"}
        # Nutrition summary
        rows = _safe_fetch(pg, "SELECT date, computed_at FROM qbot_v2.nutrition_daily_summary WHERE date >= %s ORDER BY date DESC LIMIT 1", (yesterday,))
        if rows and "_error" not in rows[0]:
            sources["nutrition_daily_summary"] = {"date": str(rows[0]["date"]), "computed_at": str(rows[0].get("computed_at",""))[:19] if rows[0].get("computed_at") else None}
        else:
            sources["nutrition_daily_summary"] = {"status": "no_data"}
        # Body measurements
        rows = _safe_fetch(pg, "SELECT date, imported_at FROM qbot_v2.body_measurements WHERE date >= %s ORDER BY date DESC LIMIT 1", (yesterday,))
        if rows and "_error" not in rows[0]:
            sources["body_measurements"] = {"date": str(rows[0]["date"]), "imported_at": str(rows[0].get("imported_at",""))[:19] if rows[0].get("imported_at") else None}
        else:
            sources["body_measurements"] = {"status": "no_data"}
        # Xert snapshots
        rows = _safe_fetch(pg, "SELECT date, snapshot_at FROM qbot_v2.xert_profile_snapshots ORDER BY snapshot_at DESC NULLS LAST LIMIT 1")
        if rows and "_error" not in rows[0]:
            sources["xert_profile_snapshots"] = {"date": str(rows[0].get("date","")), "snapshot_at": str(rows[0].get("snapshot_at",""))[:19] if rows[0].get("snapshot_at") else None}
        else:
            sources["xert_profile_snapshots"] = {"status": "no_data"}

        pg.close()
    except Exception as exc:
        return {"error": str(exc)}

    return sources



def _handle_daily_report(question: str) -> dict:
    """Generuje codzienny raport QBot: sen + wellness + energia + treningi + nutrition.

    Zbiera dane za wczoraj (domyślnie), łączy w czytelną odpowiedź.
    Diagnostykę źródeł wyświetla tylko gdy brakuje danych.
    """
    from datetime import timedelta
    report_date = _TODAY - timedelta(days=1)
    for part in question.split():
        parsed = _parse_date(part)
        if parsed and parsed < _TODAY:
            report_date = parsed
            break

    ds = report_date.isoformat()
    parts = [f"📅 Raport dzienny — {ds}", ""]
    data = {"report_date": ds}
    sources = []
    missing = []

    try:
        pg = _pg_conn()

        # Sen
        sleep = _safe_fetch(pg,
            "SELECT duration_min, score, deep_min, rem_min, "
            "light_min, awake_min, resting_hr_bpm, hrv_ms "
            "FROM qbot_v2.sleep_daily WHERE date = %s", (report_date,))
        if sleep and "_error" not in sleep[0]:
            s = sleep[0]
            _dur = (s.get('duration_min') or 0)
            h = _dur // 60
            m = _dur % 60
            hrv = f", HRV {s['hrv_ms']:.0f}ms" if s.get('hrv_ms') else ""
            rhr = f", RHR {s['resting_hr_bpm']}" if s.get('resting_hr_bpm') else ""
            parts.append(f"😴 Sen: {h}h{m:02d}  score {s.get('score','?')}{hrv}{rhr}")
            sources.append("sleep_daily")
            data["sleep"] = dict(s)
        else:
            missing.append("sen")

        # Wellness
        well = _safe_fetch(pg,
            "SELECT body_battery_start, body_battery_end, stress_avg, resting_hr_bpm, hrv_ms "
            "FROM qbot_v2.wellness_daily WHERE date = %s", (report_date,))
        if well and "_error" not in well[0]:
            w = well[0]
            bb = f"BB {w['body_battery_start']}→{w['body_battery_end']}" if w.get('body_battery_start') is not None else ""
            stress = f", stres {w['stress_avg']:.0f}" if w.get("stress_avg") else ""
            if bb:
                parts.append(f"⚡ Wellness: {bb}{stress}")
                sources.append("wellness_daily")
                data["wellness"] = dict(w)
        else:
            missing.append("wellness")

        # Energia
        en = _safe_fetch(pg,
            "SELECT active_kcal, resting_kcal, steps, total_kcal "
            "FROM qbot_v2.energy_daily WHERE date = %s", (report_date,))
        if en and "_error" not in en[0]:
            e = en[0]
            steps = f", {e['steps']:,.0f} kroków" if e.get("steps") else ""
            total = (e.get("total_kcal") or 0)
            parts.append(f"🔥 Spalone: {total:.0f} kcal (rest {e.get('resting_kcal',0):.0f} + aktywność {e.get('active_kcal',0):.0f}){steps}")
            sources.append("energy_daily")
            data["energy"] = dict(e)
        else:
            missing.append("energia")

        # Treningi
        tr = _safe_fetch(pg,
            "SELECT activity_name, sport_type, duration_s, distance_m, avg_hr_bpm, tss "
            "FROM qbot_v2.training_sessions WHERE date = %s ORDER BY started_at", (report_date,))
        if tr and "_error" not in tr[0]:
            for t in tr:
                km = f"{t['distance_m']/1000:.1f}km " if t.get('distance_m') else ""
                _ds = t.get('duration_s') or 0
                h = _ds // 3600; m2 = (_ds % 3600) // 60
                hr = f", HR {t['avg_hr_bpm']}" if t.get('avg_hr_bpm') else ""
                tss = f", TSS {t['tss']:.0f}" if t.get('tss') else ""
                parts.append(f"🚴 {t.get('activity_name') or t.get('sport_type','Trening')}: {km}{h}h{m2:02d}{hr}{tss}")
            sources.append("training_sessions")
            data["training"] = [dict(t) for t in tr]
        else:
            missing.append("trening")

        # Nutrition
        nutr = _safe_fetch(pg,
            "SELECT kcal_total, protein_total, carbs_total, fat_total "
            "FROM qbot_v2.nutrition_daily_summary WHERE date = %s", (report_date,))
        exp_r = _safe_fetch(pg,
            "SELECT expenditure_total FROM qbot_v2.daily_summary WHERE date = %s", (report_date,))
        if nutr and "_error" not in nutr[0]:
            n = nutr[0]
            exp = (exp_r[0].get("expenditure_total") or 0) if exp_r and "_error" not in exp_r[0] else None
            bal = f"  bilans {n['kcal_total']-exp:+.0f}" if exp else ""
            parts.append(
                f"🍽️  Jedzenie: {n.get('kcal_total',0):.0f} kcal  "
                f"B{n.get('protein_total',0):.0f}g W{n.get('carbs_total',0):.0f}g T{n.get('fat_total',0):.0f}g{bal}"
            )
            sources.append("nutrition_daily_summary")
            data["nutrition"] = dict(n)
        else:
            missing.append("nutrition")

        pg.close()
    except Exception as exc:
        parts.append(f"⚠️  Błąd pobierania danych: {exc}")

    if missing:
        parts.append("")
        parts.append(f"⚠️  Brak danych: {', '.join(missing)}")

    answer = "\n".join(p for p in parts if p is not None)
    data["missing"] = missing
    return _envelope("daily_report", answer, data=data, sources_used=sources,
                     missing_sources=missing)


def _handle_daily_report_diagnostic(question: str) -> dict:
    """Diagnostic response for daily report queries."""
    report_date = _TODAY
    for part in question.split():
        parsed = _parse_date(part)
        if parsed:
            report_date = parsed
            break

    sources = _diagnose_source_status()
    today_str = _TODAY.isoformat()

    # Determine if report should be sent
    has_sleep = sources.get("sleep_daily", {}).get("date") == today_str or sources.get("sleep_daily", {}).get("date") == (_TODAY - timedelta(days=1)).isoformat()
    has_wellness = sources.get("wellness_daily", {}).get("date") == today_str
    has_energy = sources.get("energy_daily", {}).get("date") == today_str
    has_nutrition = sources.get("nutrition_daily_summary", {}).get("date") == today_str or sources.get("nutrition_daily_summary", {}).get("date") == (_TODAY - timedelta(days=1)).isoformat()
    has_training = sources.get("training_sessions", {}).get("date") == today_str
    has_xert = sources.get("xert_profile_snapshots", {}).get("date") == today_str or sources.get("xert_profile_snapshots", {}).get("date") == (_TODAY - timedelta(days=1)).isoformat()
    has_body = sources.get("body_measurements", {}).get("date") in (today_str, (_TODAY - timedelta(days=1)).isoformat())

    present = sum(1 for v in [has_sleep, has_wellness, has_energy, has_nutrition, has_training, has_xert, has_body] if v)
    total = 7

    should_send = "TAK" if present >= 3 else "NIE"
    status_label = "DATA_OK" if present >= 5 else ("DATA_PARTIAL" if present >= 2 else "DATA_MISSING")

    answer_lines = [
        f"📊 Diagnostyka \u017ar\u00f3de\u0142 danych na {report_date}:",
        f"",
    ]
    for src, info in sorted(sources.items()):
        if isinstance(info, dict) and info.get("date"):
            answer_lines.append(f"  ✅ {src}: ostatni rekord {info['date']} ({info.get('imported_at') or info.get('snapshot_at') or info.get('computed_at') or info.get('started_at') or '?'})")
        elif isinstance(info, dict) and info.get("status") == "no_data":
            answer_lines.append(f"  ❌ {src}: brak danych")
        elif isinstance(info, dict) and info.get("error"):
            answer_lines.append(f"  ⚠️  {src}: b\u0142\u0105d - {info['error']}")
    answer_lines.append(f"")
    answer_lines.append(f"  \u0179r\u00f3d\u0142a z danymi: {present}/{total}")
    answer_lines.append(f"  Status: {status_label}")
    answer_lines.append(f"  Raport dobowy powinien zosta\u0107 wys\u0142any: {should_send}")
    if status_label != "DATA_OK":
        missing = []
        if not has_sleep: missing.append("sleep")
        if not has_wellness: missing.append("wellness")
        if not has_energy: missing.append("energy")
        if not has_nutrition: missing.append("nutrition")
        if not has_training: missing.append("training")
        if not has_xert: missing.append("xert")
        if not has_body: missing.append("body_comp")
        answer_lines.append(f"  Brakuj\u0105ce: {', '.join(missing)}")

    answer = "\n".join(answer_lines)

    data = {
        "report_date": str(report_date),
        "today": today_str,
        "status": status_label,
        "should_send_daily_report": should_send,
        "sources_present": present,
        "sources_total": total,
        "sources": sources,
    }

    return _envelope("daily_report", answer, data=data, sources_used=list(sources.keys()))


def _handle_ride_report_diagnostic(question: str) -> dict:
    """Diagnostic response for ride report queries."""
    today_str = _TODAY.isoformat()

    # Check training sessions for today
    try:
        pg = _pg_conn()
        # Szukaj w żądanym dniu, jeśli podany — inaczej ostatnie 14 dni
        import re as _re_rr
        _rr_date = None
        for part in question.split():
            _rr_date = _parse_date(part)
            if _rr_date:
                break
        if _rr_date:
            rows = _safe_fetch(pg, """
                SELECT id, date, started_at, sport_type, distance_m, duration_s, elevation_m,
                       avg_power_w, avg_hr_bpm, activity_name
                FROM qbot_v2.training_sessions
                WHERE date = %s
                ORDER BY started_at DESC LIMIT 5
            """, (_rr_date.isoformat(),))
        else:
            rows = _safe_fetch(pg, """
                SELECT id, date, started_at, sport_type, distance_m, duration_s, elevation_m,
                       avg_power_w, avg_hr_bpm, activity_name
                FROM qbot_v2.training_sessions
                ORDER BY date DESC, started_at DESC LIMIT 5
            """)
        pg.close()
    except Exception as exc:
        return _envelope("ride_report", f"B\u0142\u0105d diagnostyczny: {exc}", status_override="ERROR")

    all_rows = rows if rows and "_error" not in rows[0] else []

    if not all_rows:
        answer = (
            f"Brak aktywno\u015bci w qbot_v2.training_sessions na {today_str} lub dzie\u0144 wcze\u015bniej.\n"
            f"Raport z jazdy nie powinien by\u0107 wys\u0142any \u2014 brak danych aktywno\u015bci."
        )
        return _envelope("ride_report", answer, data={"today": today_str, "activities_found": 0, "should_send_ride_report": "NIE", "status": "DATA_MISSING"},
                         sources_used=["qbot_v2.training_sessions"])

    total_acts = len(all_rows)
    has_fit = any(r.get("avg_power_w") is not None or r.get("avg_hr_bpm") is not None for r in all_rows)

    parts = [f"🏆 Znaleziono {total_acts} aktywno\u015bci:"]
    for r in all_rows:
        sport = r.get("sport_type") or "?"
        dist = r.get("distance_m")
        dur = r.get("duration_s")
        elev = r.get("elevation_m")
        pwr = r.get("avg_power_w")
        hr = r.get("avg_hr_bpm")
        dist_km = f"{dist/1000:.1f}km" if dist else "-"
        dur_s = f"{dur//60}min" if dur else "-"
        elev_s = f"+{elev}m" if elev else "-"
        pwr_s = f"{pwr:.0f}W" if pwr else "b/d"
        hr_s = f"{hr:.0f}bpm" if hr else "b/d"
        parts.append(f"  \u2022 {r['date']} {sport}: {dist_km}, {dur_s}, {elev_s}, HR {hr_s}, moc {pwr_s}")
        parts.append(f"    FIT: {'tak' if has_fit else 'nie'}, \u017ar\u00f3d\u0142o: intervals_icu")

    status_label = "DATA_OK" if has_fit else "DATA_PARTIAL"
    should_send = "TAK" if total_acts > 0 else "NIE"

    parts.append(f"")
    parts.append(f"  Status: {status_label}")
    parts.append(f"  Raport z jazdy powinien zosta\u0107 wys\u0142any: {should_send}")

    answer = "\n".join(parts)
    data = {
        "today": today_str,
        "activities_found": total_acts,
        "has_fit_data": has_fit,
        "status": status_label,
        "should_send_ride_report": should_send,
        "activities": [dict(r) for r in all_rows],
    }

    return _envelope("ride_report", answer, data=data,
                     sources_used=["qbot_v2.training_sessions"],
                     freshness={"report_date": today_str})


def _handle_report_diagnostic(question: str) -> dict:
    """Combined diagnostic for any report issue query."""
    daily = _handle_daily_report_diagnostic(question)
    ride = _handle_ride_report_diagnostic(question)

    daily_data = daily.get("data", {})
    ride_data = ride.get("data", {})

    answer = (
        "=== DIAGNOSTYKA RAPORT\u00d3W QBOT ===\n\n"
        "--- RAPORT DOBOWY ---\n"
        f"{daily.get('answer', '')}\n\n"
        "--- RAPORT Z JAZDY ---\n"
        f"{ride.get('answer', '')}\n\n"
        "--- PODSUMOWANIE ---\n"
        f"Raport dobowy: {daily_data.get('should_send_daily_report', 'NIE')} "
        f"({daily_data.get('status', '?')})\n"
        f"Raport z jazdy: {ride_data.get('should_send_ride_report', 'NIE')} "
        f"({ride_data.get('status', '?')})\n"
    )

    data = {
        "daily_report": daily_data,
        "ride_report": ride_data,
        "should_send_daily": daily_data.get("should_send_daily_report"),
        "should_send_ride": ride_data.get("should_send_ride_report"),
    }

    warnings = []
    if daily_data.get("status") == "DATA_MISSING":
        warnings.append("Raport dobowy: DATA_MISSING — brak wystarczaj\u0105cych danych")
    if ride_data.get("status") == "DATA_MISSING":
        warnings.append("Raport z jazdy: DATA_MISSING — brak aktywno\u015bci")

    return _envelope("report_diagnostic", answer, data=data,
                     sources_used=list(set(daily.get("sources_used", []) + ride.get("sources_used", []))),
                     warnings=warnings)


# ---------------------------------------------------------------------------
# Artifact lookup (from DB qbot_v2.artifacts, NOT filesystem)
# ---------------------------------------------------------------------------
def _handle_artifact_search(question: str) -> dict:
    """Search registered artifacts in QBot artifact store (DB qbot_v2.artifacts).

    Uses search_artifacts() which does ILIKE on filename, title, project_id, artifact_id.
    If DB unavailable, tries a raw SQL query as fallback.
    Does NOT read from filesystem — returns metadata only.
    """
    q = question.lower()
    search_term = ""

    # Extract likely filename from query — look for .md, .json, .gpx etc.
    import re
    file_match = re.search(r'[\w\-]+\.(?:md|json|gpx|txt|csv|xlsx|html)', question)
    if file_match:
        search_term = file_match.group(0)

    # If no filename found, extract quoted string or meaningful noun phrase
    if not search_term:
        qm = re.search(r'"([^"]+)"', question)
        if qm:
            search_term = qm.group(1).strip()
        else:
            # Extract after specific prefixes (prioritized)
            # "po frazie route_logistics" → "route_logistics"
            for prefix in ["po frazie", "frazie", "fraza"]:
                if prefix in q:
                    idx = q.find(prefix) + len(prefix)
                    after = question[idx:].strip().lstrip(":,. ")
                    words = after.split()[:3]
                    candidate = " ".join(words).strip(".,;:!?").strip()
                    if candidate:
                        search_term = candidate
                        break
            if not search_term:
                # Extract after 'artefakt*' or 'artifact*' (skip to word boundary, then noise)
                for prefix in ["artefakt", "artifact"]:
                    if prefix in q:
                        idx = q.find(prefix) + len(prefix)
                        # Skip to end of current word (artefakty, artefaktow etc)
                        while idx < len(q) and q[idx].isalpha():
                            idx += 1
                        after = question[idx:].strip().lstrip(":,.—–- ")
                        # Skip known noise words
                        noise = {"store", "w", "na", "z", "po", "do", "QBot", "qbot", "i", "oraz", "the",
                                 "canonical", "kanoniczne", "export", "eksport", "wip", "robocze",
                                 "artefakty", "artefakt", "p\u00f3\u0142ka", "shelf"}
                        words = [w for w in after.split() if w.lower() not in noise][:3]
                        candidate = " ".join(words).strip(".,;:!?").strip()
                        if candidate:
                            search_term = candidate
                            break

    # ── Shelf filter detection (PRZED last-resort search_term) ──
    import re as _re2
    _shelf_filter = None
    _shelf_kw_map = {
        "canonical": "canonical", "kanoniczne": "canonical", "kanoniczna": "canonical",
        "export": "export", "eksport": "export", "do eksportu": "export",
        "wip": "wip", "w obrobce": "wip", "w trakcie": "wip", "robocze": "wip",
        "old": "old", "kosz": "old", "archiwum": "old",
    }
    _q_lower = question.lower()
    _shelf_explicit = _re2.search(r"shelf\s*[:=]\s*(\w+)", _q_lower)
    if _shelf_explicit:
        _shelf_filter = _shelf_explicit.group(1).strip()
    else:
        for kw, shelf in _shelf_kw_map.items():
            if kw in _q_lower:
                _shelf_filter = shelf
                break

    # Shelf keywords stripped from search_term
    _shelf_noise = {"canonical", "kanoniczne", "kanoniczna", "export", "eksport",
                    "wip", "robocze", "old", "kosz", "archiwum", "artefakty", "artefakt",
                    "shelf", "p\u00f3\u0142ka", "p\u00f3\u0142ce"}

    if not search_term:
        # Gdy shelf_filter jest: użyj pozostałych słów jako project hint
        if _shelf_filter:
            _remaining = [w for w in _q_lower.split() if w not in _shelf_noise and len(w) > 2]
            search_term = " ".join(_remaining).strip() or ""
        else:
            search_term = question.strip()[:80]

    # ── Method 1: Try search_artifacts() from artifact store module ──
    all_artifacts = []
    store_unavailable = bool(_shelf_filter)  # skip Method 1 when shelf filter set
    try:
        from qbot3.artifacts.store import search_artifacts
        all_artifacts = search_artifacts(query=search_term, limit=50)
    except ImportError:
        store_unavailable = True
    except Exception as exc:
        return _envelope("artifact_search",
                         f"B\u0142\u0105d zapytania artifact store: {exc}",
                         status_override="ERROR",
                         sources_used=["qbot_v2.artifacts"],
                         data={"question": question, "search_term": search_term})

    # ── Method 2: Fallback to raw SQL if module unavailable ──
    if store_unavailable or not all_artifacts:
        try:
            pg = _pg_conn()
            _shelf_clause = ""
            _shelf_params = ()
            if _shelf_filter:
                # file_path w DB jest relatywna (canonical/...), nie absolutna
                _shelf_clause = "  AND (LOWER(file_path) LIKE %s OR LOWER(file_path) LIKE %s)"
                _shelf_params = (
                    f"{_shelf_filter}/%",
                    f"/opt/qbot/artifacts/{_shelf_filter}/%",
                )
            like = f"%{search_term.lower()}%" if search_term else "%"
            rows = _safe_fetch(pg, f"""
                SELECT artifact_id, project_id, artifact_type, title, filename,
                       file_path, size_bytes, sha256, source, status, metadata_json,
                       created_at, updated_at
                FROM qbot_v2.artifacts
                WHERE status = 'active'::qbot_v2.artifact_status
                  AND (LOWER(filename) LIKE %s
                    OR LOWER(title) LIKE %s
                    OR LOWER(project_id) LIKE %s
                    OR artifact_id::text LIKE %s)
                {_shelf_clause}
                ORDER BY created_at DESC
                LIMIT 50
            """, (like, like, like, like) + _shelf_params)
            all_artifacts = rows if rows else []
            pg.close()
        except Exception:
            pass

    if not all_artifacts:
        parts = [f"\U0001f50d Nie znaleziono artefaktu{' ' + search_term if search_term else ''} w rejestrze QBot."]
        if search_term:
            parts.append(f"")
            parts.append(f"Poszukiwano: \"{search_term}\"")
            parts.append(f"Spr\u00f3buj: innej nazwy, artifact_id, lub sprawd\u017a czy plik zosta\u0142 zarejestrowany przez qbot_artifact_put.")
        parts.append(f"")
        parts.append(f"Plik mo\u017ce istnie\u0107 na filesystemie /opt/qbot/artifacts/")
        parts.append(f"ale nie jest zarejestrowany jako artefakt QBot w qbot_v2.artifacts.")
        parts.append(f"Aby zarejestrowa\u0107, u\u017Cyj narz\u0119dzia qbot_artifact_put.")

        return _envelope("artifact_search", "\n".join(parts),
                         data={"question": question, "search_term": search_term,
                               "found": False, "count": 0,
                               "filesystem_only": store_unavailable},
                         sources_used=["qbot_v2.artifacts"],
                         missing_sources=["qbot_v2.artifacts"])

    # Build answer
    parts = [f"\U0001f4c1 Znaleziono {len(all_artifacts)} artefakt(y/\u00f3w) w rejestrze QBot:"]
    for a in all_artifacts:
        parts.append(f"")
        # Wyciągnij shelf z file_path
        _fp = str(a.get('file_path', ''))
        _shelf_display = '?'
        for _s in ('canonical', 'export', 'wip', 'old'):
            # Sprawdź zarówno relatywną jak i absolutną ścieżkę
            if _fp.startswith(_s + '/') or f'/artifacts/{_s}/' in _fp:
                _shelf_display = _s
                break
        parts.append(f"  artifact_id: {a.get('artifact_id', '?')}")
        parts.append(f"  polka: {_shelf_display}")
        parts.append(f"  nazwa: {a.get('filename', '?')}")
        parts.append(f"  tytu\u0142: {a.get('title', '?')}")
        parts.append(f"  typ: {a.get('artifact_type', '?')}")
        parts.append(f"  projekt: {a.get('project_id', '?')}")
        parts.append(f"  \u015bcie\u017cka: {a.get('file_path', '?')}")
        parts.append(f"  rozmiar: {a.get('size_bytes', '?')} bajt\u00f3w")
        parts.append(f"  status: {a.get('status', '?')}")
        if a.get("metadata"):
            import json
            parts.append(f"  metadane: {json.dumps(a['metadata'], ensure_ascii=False)[:200]}")
        if a.get("created_at"):
            parts.append(f"  utworzono: {str(a['created_at'])[:19]}")
        if a.get("updated_at"):
            parts.append(f"  aktualizacja: {str(a['updated_at'])[:19]}")

    answer = "\n".join(parts)

    data = {
        "question": question,
        "search_term": search_term,
        "shelf_filter": _shelf_filter,
        "found": True,
        "count": len(all_artifacts),
        "store_unavailable": store_unavailable,
        "filesystem_only": False,
        "artifacts": all_artifacts,
    }

    return _envelope("artifact_search", answer, data=data,
                     sources_used=["qbot_v2.artifacts"],
                     freshness={"search_term": search_term})


# ---------------------------------------------------------------------------
# Artifact Read Handler
# ---------------------------------------------------------------------------
def _handle_artifact_read(question: str) -> dict:
    """Read artifact content from qbot_v2.artifacts via identifier."""
    q = question.lower()
    search_term = ""

    # Extract artifact_id UUID from query
    import re as _re
    uuid_match = _re.search(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        question, _re.IGNORECASE)
    if uuid_match:
        search_term = uuid_match.group(0)
    else:
        # Extract filename or path
        file_match = _re.search(r'[\w\-\.\/]+\.(?:md|json|txt|csv|xlsx|html)', question)
        if file_match:
            search_term = file_match.group(0).lstrip("/")
        else:
            # Extract after "artefakt" or "artifact"
            for prefix in ["artefakt", "artifact"]:
                if prefix in q:
                    idx = q.find(prefix) + len(prefix)
                    after = question[idx:].strip().lstrip(":,. ")
                    noise = {"store", "w", "na", "z", "po", "do", "QBot", "qbot", "i", "oraz",
                             "the", "content", "get", "read"}
                    words = [w for w in after.split() if w.lower() not in noise][:3]
                    candidate = " ".join(words).strip(".,;:!?").strip()
                    if candidate:
                        search_term = candidate
                        break

            if not search_term:
                # Clean path from query
                path_match = _re.search(r'/opt/qbot/artifacts/[^\s]+', question)
                if path_match:
                    search_term = path_match.group(0)

    if not search_term:
        return _envelope("artifact_read",
                         "Podaj artifact_id, nazw\u0119 pliku lub \u015bcie\u017ck\u0119 artefaktu do odczytu.",
                         data={"question": question, "search_term": ""},
                         sources_used=["qbot_v2.artifacts"],
                         warnings=["no identifier found in query"])

    try:
        from qbot3.artifacts.store import read_artifact_content
        result = read_artifact_content(identifier=search_term, start_line=1, max_lines=200, max_bytes=65536)
    except ImportError:
        return _envelope("artifact_read",
                         "Modu\u0142 artifact store niedost\u0119pny.",
                         status_override="ERROR",
                         sources_used=["qbot_v2.artifacts"],
                         data={"question": question, "search_term": search_term})
    except Exception as exc:
        return _envelope("artifact_read",
                         f"B\u0142\u0105d odczytu artefaktu: {exc}",
                         status_override="ERROR",
                         sources_used=["qbot_v2.artifacts"],
                         data={"question": question, "search_term": search_term})

    if not result.get("ok"):
        status_map = {
            "NOT_FOUND": "PARTIAL",
            "DENIED": "ERROR",
            "TOO_LARGE": "PARTIAL",
            "BINARY_FILE": "PARTIAL",
            "READ_ERROR": "ERROR",
            "DB_ERROR": "ERROR",
        }
        error_status = status_map.get(result.get("status", ""), "ERROR")
        warnings = [result.get("error", "unknown error")]
        if result.get("status") == "NOT_FOUND":
            warnings.append(
                "Artefakt nie istnieje w rejestrze qbot_v2.artifacts. "
                "Mo\u017ce istnie\u0107 na filesystemie /opt/qbot/artifacts/ "
                "ale nie jest zarejestrowany. U\u017Cyj qbot_artifact_put aby zarejestrowa\u0107.")

        parts = [f"\u26A0\ufe0f Nie mo\u017cna odczyta\u0107 artefaktu: {result.get('error', '')}"]
        if result.get("artifact_id"):
            parts.append(f"artifact_id: {result['artifact_id']}")
        if result.get("path"):
            parts.append(f"\u015bcie\u017cka: {result['path']}")
        if result.get("status") == "NOT_FOUND":
            parts.append(f"")
            parts.append(f"Spr\u00f3buj: innej nazwy, artifact_id, lub sprawd\u017a czy plik zosta\u0142 zarejestrowany.")

        return _envelope("artifact_read", "\n".join(parts),
                         data={"question": question, "search_term": search_term,
                               "found": False, "read_status": result.get("status")},
                         sources_used=["qbot_v2.artifacts"],
                         missing_sources=["artifact_file_read"] if result.get("status") == "NOT_FOUND" else [],
                         warnings=warnings,
                         status_override=error_status)

    # Success
    aid = result.get("artifact_id", "?")
    fname = result.get("filename", "?")
    atype = result.get("artifact_type", "?")
    lines = result.get("line_count", 0)
    sz = result.get("size_bytes", 0)
    truncated = result.get("truncated", False)

    parts = [f"\U0001f4c4 Artefakt: {fname}"]
    parts.append(f"  artifact_id: {aid}")
    parts.append(f"  typ: {atype}")
    parts.append(f"  rozmiar: {sz} bajt\u00f3w, linii: {lines}")
    if result.get("project_id"):
        parts.append(f"  projekt: {result['project_id']}")
    parts.append(f"")
    parts.append(result.get("content", ""))

    if truncated:
        parts.append(f"")
        parts.append(f"\u26A0\ufe0f Tre\u015b\u0107 przyci\u0119ta (max 65536 bajt\u00f3w / 200 linii). "
                      f"U\u017Cyj start_line/max_lines aby czyta\u0107 fragmentami.")

    answer = "\n".join(parts)
    data = {
        "question": question,
        "search_term": search_term,
        "found": True,
        "artifact_id": aid,
        "filename": fname,
        "artifact_type": atype,
        "project_id": result.get("project_id"),
        "line_count": lines,
        "size_bytes": sz,
        "truncated": truncated,
    }

    return _envelope("artifact_read", answer, data=data,
                     sources_used=["qbot_v2.artifacts", "artifact_file_read"],
                     freshness={"artifact_id": aid})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _handle_qbot_help() -> dict:
    help_text = """\U0001f916 *QBot3 — lista komend*

**\U0001f34e ŻYWIENIE**
• bilans / kcal → dzienny bilans kalorii
• jedzenie / posiłki → co jadłem dziś
• zakres / ostatni tydzień → makro za zakres dat
• dodaj posiłek [nazwa] [kcal] [B/W/T] → zapis żywienia

**\u2764\ufe0f ZDROWIE**
• sen / sleep → dane snu (REM, deep, light)
• wellness / hrv / bateria → HRV, body battery, tętno spoczynkowe
• energia / kroki → wydatek energetyczny
• waga → aktualna waga
• body composition / skład ciała → pełny skład (tłuszcz, mięśnie, BMI)
• trend wagi → historia wagi
• tabela body → pełna tabela pomiarów za okres

**\U0001f3cb TRENING**
• trening / aktywność → ostatnie treningi
• xert / forma / ftp → status Xert (FTP, LTP, W', forma)
• odśwież xert → live fetch z API Xert

**\U0001f6e3 TRASY**
• przeanalizuj poi [trasa] km [X-Y] → POI na trasie (woda/jedzenie/sklepy+stacje/atrakcje)
• nawierzchnia trasy [trasa] → analiza nawierzchni
• podjazdy [trasa] km [X-Y] → lista podjazdów
• ocena trasy [trasa] start [HH:MM] → feasibility check (forma + pogoda + profil)
• kafelki [share_id] trasa [route_id] → analiza kafelków + Überkwadrat
• generuj trasę [X]km start [lat,lon] → nowa trasa Valhalla + tile scoring
• pobierz trasę [route_id] → pobierz i przetwórz trasę z RWGPS
• lista tras → przetworzone trasy
• wyślij poi do rwgps [trasa] → wyślij POI do RWGPS (dry-run)
• wyślij poi ... potwierdź → rzeczywisty zapis

**\U0001f9f3 WYJAZDY**
• wyjazd / toskania → status wyjazdu
• etap / dzisiejszy etap → info o etapie (data lub numer)
• etap 3 / plan etapów → konkretny etap lub cały plan
• atrakcje / co warto → atrakcje na etapie/trasie
• atrakcje etap 2 / must see → POI z bazy planowania

**\U0001f4ca RAPORTY**
• raport dobowy → status raportu dziennego
• raport z jazdy → ostatni raport po jeździe
• diagnostyka raportu → sprawdź źródła danych

**\U0001f6b2 GARAŻ**
• garaż / sprzęt → status sprzętu
• szukaj [element] → szukaj w garażu

**\U0001f4be SYSTEM**
• /help → ta lista
• przypomnij / pamięć → notatki i fakty
• artefakt / artifact [id] → przeszukaj/odczytaj artefakty"""
    return _envelope("qbot_help", help_text, sources_used=[])

def _normalize_question(q: str) -> str:
    """Normalizuj wejscie: etap4->etap 4, stage3->stage 3, 30d->30 dni."""
    import re as _re_n
    q = _re_n.sub(r"etap([0-9]+)", r"etap \1", q)
    q = _re_n.sub(r"\bstage([0-9]+)\b", r"stage \1", q)
    q = _re_n.sub(r"\b([0-9]+)d\b", r"\1 dni", q)
    return q


def handle_query(question: str, context: dict | None = None) -> dict:
    # Refresh _TODAY on every request. It was a module-level constant frozen at
    # import time, so a long-running server resolved "wczoraj"/"dziś" against a
    # stale date (off by one+ after midnight / multi-day uptime).
    global _TODAY
    _TODAY = datetime.now(WARSAW).date()
    question = _normalize_question(question)
    ql = question.lower().strip()
    intent = _resolve_intent(question)
    if intent in ("planner_switch_claude", "planner_switch_openai", "planner_switch_gemini", "planner_status"):
        try:
            from core.planner import set_active_provider, _get_active_provider
            _labels = {
                "planner_switch_claude": "claude",
                "planner_switch_openai": "openai",
                "planner_switch_gemini": "gemini",
            }
            _names = {
                "claude": "Claude Sonnet (-> OpenAI -> Gemini)",
                "openai": "OpenAI gpt-4.1-mini (-> Gemini)",
                "gemini": "Gemini PRO",
            }
            if intent in _labels:
                _prov = _labels[intent]
                set_active_provider(_prov)
                _msg = f"Planner: {_names[_prov]} aktywny."
            else:
                _active = _get_active_provider()
                _msg = f"Aktywny: {_active.upper()} — {_names.get(_active, _active)}. Komendy: planner claude / openai / gemini."
            return _envelope("planner_switch", _msg, sources_used=[])
        except Exception as _ps_exc:
            return _envelope("planner_switch", f"Blad: {_ps_exc}", sources_used=[])

    if intent == "qbot_help":
        return _handle_qbot_help()
    if intent == "garmin_activity_export":
        return _handle_garmin_activity_export(question)
    if intent == "garmin_activity_streams":
        return _handle_garmin_activity_streams(question)
    if intent == "garmin_last_activity":
        return _handle_garmin_last_activity(question)
    if intent == "garmin_activity_detail":
        return _handle_garmin_activity_detail(question)

    # Redirect artifact_search to artifact_read when query starts with a read verb
    # and contains a filename/identifier pattern — this handles "Zobacz <filename>"
    # where the filename itself matches artifact_search keywords (e.g. "route_logistics")
    if intent == "artifact_search":
        read_prefixes = ("zobacz", "poka\u017c", "przeczytaj", "odczytaj", "see", "show", "read", "display")
        has_read_file = any(ql.startswith(p) for p in read_prefixes) and ("." in question or any(c.isdigit() for c in question))
        has_uuid = bool(__import__("re").search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', question, __import__("re").IGNORECASE))
        has_full_path = "/opt/qbot/artifacts/" in ql
        if has_read_file or has_uuid or has_full_path:
            intent = "artifact_read"

    # ── Router v2: eskalacja domeny otwartej → Albert/Planner ──────────────
    # Uruchamia się gdy:
    #   a) keyword trafił w intent z domeny otwartej (trasy/trip), LUB
    #   b) keyword trafił w domenę zamkniętą ale treść sygnalizuje domenę otwartą (konflikt)
    # W obu przypadkach: próba Alberta, fallback do handlera keywordowego (brak regresji).
    _rv2_albert_enabled = os.getenv("QBOT3_ENABLED") == "1"
    _rv2_is_open_intent = intent in OPEN_DOMAIN_INTENTS
    _rv2_domain_conflict = (
        not _rv2_is_open_intent
        and _classify_domain(question) == "open"
        and intent not in {
            "unrecognized", "qbot_help", "db_access_blocked",
            "write_meal", "write_delete_unsupported",
            "write_planning_unsupported", "write_weight_unsupported",
        }
    )
    if _rv2_is_open_intent or _rv2_domain_conflict:
        try:
            from core.planner import plan_routes
            _rv2_result = plan_routes(question=question)
            _rv2_result["router_v2"] = (
                f"open_domain intent={intent} "
                f"conflict={_rv2_domain_conflict}"
            )
            return _rv2_result
        except Exception as _rv2_exc:
            import logging as _rv2_log
            _rv2_log.getLogger("qbot.router_v2").warning(
                "Planner niedostepny (%s) -> keyword fallback", _rv2_exc
            )

    # ── Analytical fallback → Albert ─────────────────────────────────────
    # Gdy pytanie zawiera słowa analityczne a intent jest prostym readerem
    _ANALYTICAL_WORDS = [
        "najlepszy", "najgorszy", "najwyższy", "najniższy",
        "najdłuższy dzień", "najkrótszy dzień",
        "porównaj", "porównanie", "compare",
        "ile łącznie", "łącznie za", "suma za", "razem za",
        "średni", "średnia", "average",
        "delta", "różnica między", "zmiana od",
        "czy byłem", "czy jestem", "czy mój",
        "kiedy miałem", "kiedy byłem",
        "w którym dniu", "który dzień",
        "ile schudłem", "ile przytyłem", "ile urosłem",
        "przed czy po", "lepszy niż", "gorszy niż",
        "lepszy od", "gorszy od", "czy mój sen", "czy spałem lepiej",
    ]
    _ANALYTICAL_INTENTS_EXEMPT = {
        # Te intenty mają własną analitykę — nie przekierowuj
        "trip_summary", "route_climbs", "route_feasibility",
        "report_diagnostic", "ride_report", "daily_report",
        "artifact_search", "artifact_read",
        "write_meal", "write_delete_unsupported", "write_planning_unsupported",
        "write_weight_unsupported", "db_access_blocked",
        "unrecognized", "qbot_help", "action_execute",
        "body_measurements_range", "training_recent",
        "fit_file_analyze",
        "garmin_activity_streams", "garmin_activity_export", "garmin_last_activity",
        "garmin_activity_detail",
        "weight_trend",
    }
    _ql_analytical = question.lower()
    _is_analytical = any(w in _ql_analytical for w in _ANALYTICAL_WORDS)
    _albert_enabled = __import__("os").getenv("QBOT3_ENABLED") == "1"
    if _is_analytical and intent not in _ANALYTICAL_INTENTS_EXEMPT and _albert_enabled:
        try:
            import os as _os
            # Użyj Gemini dla analytical queries (OpenRouter free nie obsługuje tool-calling)
            _an_url = _os.getenv("QGPT_ANALYTICAL_BASE_URL")
            _an_key = _os.getenv("QGPT_ANALYTICAL_API_KEY")
            _an_model = _os.getenv("QGPT_ANALYTICAL_MODEL")
            _orig = {}
            if _an_url and _an_key and _an_model:
                for _k, _v in [("QGPT_BASE_URL", _an_url), ("QGPT_API_KEY", _an_key),
                               ("QGPT_MODEL", _an_model), ("ALBERT_LLM_PROVIDER", "openai")]:
                    _orig[_k] = _os.environ.get(_k)
                    _os.environ[_k] = _v
            try:
                from qbot3.agent_runtime import orchestrate_query
                _albert_result = orchestrate_query(question=question)
                _albert_result["fallback_reason"] = f"analytical_fallback (intent={intent})"
                return _albert_result
            finally:
                for _k, _v in _orig.items():
                    if _v is None:
                        _os.environ.pop(_k, None)
                    else:
                        _os.environ[_k] = _v
        except Exception as _exc:
            # Albert niedostępny — kontynuuj deterministycznie
            pass
    # ── Multi-intent: sprawdz czy pytanie obejmuje >1 domene ──────────
    # Multi-intent: sprawdz czy pytanie obejmuje >1 domene
    domains = _detect_domains(question)
    if len(domains) >= 2:
        return _handle_multi_intent(question, domains)


    day_str = _parse_date_from_question(question)

    # If daily_balance or nutrition_day but query has range indicators → nutrition_range
    if intent in ("daily_balance", "nutrition_day") and _has_range_indicator(question) and "xert" not in question.lower():
        return _handle_nutrition_range(question)

    # If body_comp/weight_lookup/weight_trend + range → body_measurements_range
    if intent in ("body_comp", "weight_lookup", "weight_trend") and _has_range_indicator(question):
        return _handle_body_measurements_range(question)

    if intent == "nutrition_status":
        from qbot_nutrition_tools import _tool_qbot_nutrition_status
        r = _tool_qbot_nutrition_status()
        if r.get("status") == "OK":
            _food = r.get("food_items_count", "?")
            _meal = r.get("meal_logs_count", "?")
            _hyd  = r.get("hydration_events_count", "?")
            _fuel = r.get("fueling_events_count", "?")
            _summ = r.get("daily_summaries_count", "?")
            _ns_answer = (
                f"\U0001f4e6 Status bazy \u017cywienia:\n"
                f"  Produkty:          {_food:>6}\n"
                f"  Logi posi\u0142k\u00f3w:     {_meal:>6}\n"
                f"  Nawodnienie:       {_hyd:>6}\n"
                f"  Fueling (on-bike): {_fuel:>6}\n"
                f"  Podsumowania dni:  {_summ:>6}"
            )
        else:
            _ns_answer = f"B\u0142\u0105d nutrition_status: {r.get('error', '?')!r}"
        return _envelope("nutrition_status", _ns_answer, data=r, sources_used=["qbot_nutrition_db"])
    elif intent == "nutrition_range":
        return _handle_nutrition_range(question)
    elif intent == "xert_snapshot_range":
        return _handle_xert_snapshot_range(question)
    elif intent == "daily_balance":
        return _handle_daily_balance(day_str)
    elif intent == "nutrition_intake_logs_list":
        return _handle_intake_logs_list(day_str)
    elif intent == "nutrition_day":
        return _handle_nutrition_day(day_str)
    elif intent == "sleep_day":
        return _handle_sleep_day(day_str)
    elif intent == "wellness_day":
        return _handle_wellness_day(day_str, question)
    elif intent == "weight_lookup":
        return _handle_weight_lookup(day_str)
    elif intent == "weight_trend":
        return _handle_weight_trend(question)
    elif intent == "body_comp":
        return _handle_body_comp(day_str)
    elif intent == "body_measurements_range":
        return _handle_body_measurements_range(question)
    elif intent == "garmin_activity_detail":
        return _handle_garmin_activity_detail(question)
    elif intent == "energy_day":
        return _handle_energy_day(day_str)
    elif intent == "garmin_activity_export":
        return _handle_garmin_activity_export(question)
    elif intent == "garmin_activity_streams":
        return _handle_garmin_activity_streams(question)
    elif intent == "garmin_last_activity":
        return _handle_garmin_last_activity(question)
    elif intent == "fit_file_analyze":
        return _handle_fit_file_analyze(question, context)
    elif intent == "training_recent":
        return _handle_training_recent(question)
    elif intent == "xert_status":
        return _handle_xert_status(question)
    elif intent == "xert_live_fetch":
        return _handle_xert_live_fetch(question)
    elif intent == "garage_status":
        return _handle_garage_status(question)
    elif intent == "garage_search":
        return _handle_garage_search(question)
    elif intent == "memories_search":
        return _handle_memories_search(question)
    elif intent == "trips_status":
        return _handle_trips_status(question)
    elif intent == "trip_summary":
        return _handle_trip_summary(question)
    elif intent == "trip_stages":
        return _handle_trip_stages(question)
    elif intent == "trip_attractions":
        return _handle_trip_attractions(question)
    elif intent == "rwgps_route_find":
        return _handle_rwgps_route_find(question)
    elif intent == "rwgps_route_import_gpx":
        return _handle_rwgps_route_import_gpx(question)
    elif intent == "rwgps_route_profile_sample":
        return _handle_rwgps_route_profile_sample(question)
    elif intent == "route_generate":
        return _handle_route_generate(question)
    elif intent == "daily_report":
        return _handle_daily_report(question)
    elif intent == "ride_report":
        return _handle_ride_report_diagnostic(question)
    elif intent == "report_diagnostic":
        return _handle_report_diagnostic(question)
    elif intent == "route_feasibility":
        return _handle_route_feasibility(question)
    elif intent == "tile_analysis":
        return _handle_tile_analysis(question)
    elif intent == "route_workflow_fetch":
        return _handle_route_workflow_fetch(question)
    elif intent == "route_workflow_upload":
        return _handle_route_workflow_upload(question)
    elif intent == "route_workflow_list":
        return _handle_route_workflow_list()
    elif intent == "rwgps_recent_routes":
        return _handle_rwgps_recent_routes(question)
    elif intent == "route_climbs":

        return _handle_route_climbs(question)
    elif intent == "rwgps_poi_push":
        return _handle_rwgps_poi_push(question)
    elif intent == "route_poi_analyze":
        return _handle_route_poi_analyze(question)
    elif intent == "artifact_search":
        return _handle_artifact_search(question)
    elif intent == "artifact_read":
        return _handle_artifact_read(question)
    elif intent == "db_access_blocked":
        return _envelope("db_access_blocked",
                         "🚫 Bezpośredni dostęp do tabel bazy danych nie jest obsługiwany przez qbot.query.\n"
                         "QBot udostępnia dane wyłącznie przez zdefiniowane intenty (bilans, sen, trening itp.).",
                         status_override="BLOCKED")
    elif intent == "write_meal":

        return _envelope("write_meal",
                         "📝 Zapis posiłku wymaga potwierdzenia.\n"
                         "Użyj ChatGPT z narzędziem qbot.action_execute i confirm=true.\n"
                         "Przykład: qbot.action_execute z action_type=nutrition_log_add.",
                         data={"action_type": "nutrition_log_add", "requires_confirm": True},
                         status_override="ACTION_REQUIRED")
    elif intent == "write_delete_unsupported":
        return _envelope("write_delete_unsupported",
                         "🚫 Kasowanie wpisów nie jest obsługiwane przez qbot.query.\n"
                         "Operacja delete nie jest na liście dozwolonych akcji.",
                         status_override="PARTIAL")
    elif intent == "write_planning_unsupported":
        return _envelope("write_planning_unsupported",
                         "🚫 Dodawanie etapów/tras przez qbot.query nie jest obsługiwane.\n"
                         "Użyj qbot.action_execute z action_type=planning_fact_add i confirm=true.",
                         data={"action_type": "planning_fact_add", "requires_confirm": True},
                         status_override="BLOCKED")
    elif intent == "write_weight_unsupported":
        return _envelope("write_weight_unsupported",
                         "🚫 Waga pochodzi z Garmin Index Scale — nie można jej ustawić ręcznie.\n"
                         "Zważ się na wadze Garmin, dane zostaną zaimportowane automatycznie.",
                         status_override="BLOCKED")
    else:
        _ql_ur = question.lower()
        # Krótkie pytania bez kontekstu — prośba o doprecyzowanie zamiast zgadywania
        _short_ctx = ["tam", "ten etap", "ten", "to", "tutaj", "na nim", "na niej",
                      "tego etapu", "tej trasy", "ile to", "ile km"]
        if any(kw in _ql_ur for kw in _short_ctx) :
            return _envelope("unrecognized",
                             "Nie mam kontekstu poprzedniego zapytania — każde wywołanie jest niezależne.\n"
                             "Podaj pełne pytanie, np. 'atrakcje etap 3 toskania' lub 'woda etap 3 toskania'.",
                             status_override="PARTIAL")
        return _envelope("unrecognized",
                         "Nie rozpoznano intencji. Spróbuj: bilans, jedzenie, sen, wellness, energia, trening, xert, garaż, notatki, wyjazdy, raport dobowy, raport z jazdy.")


def _handle_route_feasibility(question):
    import re as _re
    ql=question.lower()
    route_id_m=_re.search(r"\b(\d{6,8})\b",question)
    route_id=route_id_m.group(1) if route_id_m else None
    hour_m=_re.search(r"(\d{1,2}):\d{2}|start\s*(\d{1,2})",ql)
    start_hour=int((hour_m.group(1) or hour_m.group(2))) if hour_m else 8
    if not route_id:
        for kw in ["toskani", "tuscany"]:
            if kw in ql:
                route_id = _resolve_tuscany_e07_live_route_id(question)
                break
    route_id = _resolve_tuscany_e07_live_route_id(question, route_id=route_id)
    try:
        from tools.feasibility import check_feasibility,format_report
        r=check_feasibility(route_id=route_id,start_hour=start_hour)
        answer=format_report(r)
        return _envelope("route_feasibility",answer,data=r,sources_used=["xert","rwgps","owm"])
    except Exception as exc:
        return _envelope("route_feasibility","Blad: {}".format(exc),status_override="ERROR")


def _handle_tile_analysis(question):
    import re as _re
    ql=question.lower()
    share_m=_re.search(r'share[=:]?\s*([a-zA-Z0-9_-]{4,20})',ql)
    share_id=share_m.group(1) if share_m else None
    if not share_id:
        share_m=_re.search(r'[a-zA-Z0-9_-]{8,20}',question)
        share_id=share_m.group(0) if share_m else None
    route_id_m=_re.search(r'(\d{6,8})',question)
    route_id=route_id_m.group(1) if route_id_m else None
    if not share_id:
        return _envelope('tile_analysis','Podaj share_id ze StatsHunters.',status_override='PARTIAL')
    try:
        from tools.tile_store import build_route_report
        r=build_route_report(share_id,route_id=route_id)
        ub=r.get('uberkwadrat',{})
        sep=chr(10)
        lines=['Kafelki StatsHunters (share={}):'.format(share_id),
               'Przejechane: {} kafelkow'.format(r.get('existing_tiles_count',0)),
               'Uberkwadrat: {}x{} = {} kafelkow'.format(ub.get('width',0),ub.get('height',0),ub.get('area',0)),
               'Centrum Uberkwadratu: lat={} lon={}'.format(ub.get('center_lat',0),ub.get('center_lon',0))]
        if r.get('route_tile_score'):
            sc=r['route_tile_score']
            lines.append('Trasa {}: {} nowych kafelkow ({:.0f}%) | score={:.2f}'.format(
                route_id,sc['new_tiles'],sc['new_pct']*100,sc['score']))
        if r.get('tile_error'): lines.append('Blad pobierania: '+str(r['tile_error']))
        _te=str(r.get('tile_error',''))
        _ts='ERROR' if ('401' in _te or 'Unauthorized' in _te or ('error' in _te.lower() and _te)) else None
        return _envelope('tile_analysis',sep.join(lines),data=r,sources_used=['statshunters'],status_override=_ts)
    except Exception as exc:
        return _envelope('tile_analysis','Blad: {}'.format(exc),status_override='ERROR')


def _handle_route_workflow_fetch(question: str) -> dict:
    import re as _re
    ql = question.lower()
    route_id_m = _re.search(r"\b(\d{6,8})\b", question)
    route_id = route_id_m.group(1) if route_id_m else None
    if not route_id:
        return _envelope("route_workflow", "Podaj route_id RWGPS.", status_override="PARTIAL")
    try:
        from tools.rwgps.route_workflow import fetch_and_process
        r = fetch_and_process(route_id)
        climbs = r.get("climbs_count", 0)
        poi = r.get("poi_candidates", {})
        poi_str = " | ".join(f"{k}: {v}" for k,v in poi.items() if v)
        answer = "Trasa {} przetworzona lokalnie.\n{}km | +{}m | {} podjazdow\nPOI: {}\n\nKatalog: {}\n\n{}".format(
            r.get("name"), r.get("distance_km"), r.get("elevation_gain_m"),
            climbs, poi_str or "brak", r.get("work_dir"), r.get("note",""))
        return _envelope("route_workflow", answer, data=r, sources_used=["rwgps"])
    except Exception as exc:
        return _envelope("route_workflow", "Blad: {}".format(exc), status_override="ERROR")


def _handle_route_workflow_upload(question: str) -> dict:
    import re as _re
    ql = question.lower()
    route_id_m = _re.search(r"\b(\d{6,8})\b", question)
    route_id = route_id_m.group(1) if route_id_m else None
    if not route_id:
        return _envelope("route_workflow", "Podaj route_id RWGPS.", status_override="PARTIAL")
    dry_run = not any(w in ql for w in ["potwierdz", "zatwierdz", "wykonaj"])
    try:
        from tools.rwgps.route_workflow import upload_to_rwgps
        r = upload_to_rwgps(route_id, dry_run=dry_run)
        if r.get("dry_run"):
            answer = "Dry-run upload trasy {}:\nNowa nazwa: {}\n\n{}".format(
                route_id, r.get("new_name"), r.get("note",""))
        else:
            answer = "Wyslano do RWGPS!\nNowa nazwa: {}".format(r.get("new_name"))
        return _envelope("route_workflow", answer, data=r, sources_used=["rwgps"])
    except Exception as exc:
        return _envelope("route_workflow", "Blad: {}".format(exc), status_override="ERROR")


def _handle_route_workflow_list() -> dict:
    try:
        from tools.rwgps.route_workflow import list_processed_routes
        routes = list_processed_routes(days=14)
        if not routes:
            answer = "Brak przetworzonych tras w ostatnich 14 dniach."
        else:
            lines = ["Przetworzone trasy:"]
            for r in routes:
                lines.append("  {} | [{}] {} | {} km | {}".format(
                    r.get("date"), r.get("route_id", "—"), r.get("name"),
                    r.get("distance_km"), r.get("status")))
            answer = "\n".join(lines)
        return _envelope("route_workflow", answer, data={"routes": routes}, sources_used=[])
    except Exception as exc:
        return _envelope("route_workflow", "Blad: {}".format(exc), status_override="ERROR")

def _handle_rwgps_recent_routes(question: str) -> dict:
    """Lista tras RWGPS z ostatnich N dni — z planning_facts + RWGPS API."""
    import re, httpx, os, json
    from datetime import datetime, timezone, timedelta
    ql = question.lower()
    days = 7
    m = re.search(r"(\d+)\s*(?:dni|tygod)", ql)
    if m:
        n = int(m.group(1))
        days = n * 7 if "tygod" in ql[m.start():m.start()+20] else n
    elif "miesi" in ql:
        days = 30
    try:
        env = {}
        for ef in ["/opt/qbot/app/.env", "/etc/qbot/qbot-api.env"]:
            try:
                for line in open(ef):
                    if "=" in line and not line.startswith("#"):
                        k, _, v = line.strip().partition("=")
                        env[k] = v
            except Exception:
                pass
        api_key = env.get("RWGPS_API_KEY", os.getenv("RWGPS_API_KEY", ""))
        auth_token = env.get("RWGPS_AUTH_TOKEN", os.getenv("RWGPS_AUTH_TOKEN", ""))

        # Pobierz route_id z planning_facts
        pg = _pg_conn()
        rows = _safe_fetch(pg, """
            SELECT fact_json->>'stages' as stages_json
            FROM qbot_v2.qbot_planning_facts
            WHERE fact_type='route_stages'
            ORDER BY date DESC LIMIT 1
        """)
        pg.close()
        known_ids = []
        if rows and rows[0].get("stages_json"):
            stages = json.loads(rows[0]["stages_json"])
            known_ids = [str(s.get("route_id")) for s in stages if s.get("route_id")]

        # Sprawdź każdy known route_id w RWGPS
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = []
        for rid in known_ids:
            try:
                url = (f"https://ridewithgps.com/routes/{rid}.json"
                       f"?apikey={api_key}&auth_token={auth_token}&version=2")
                resp = httpx.get(url, timeout=10.0)
                if resp.status_code != 200:
                    continue
                r = resp.json().get("route", {})
                upd = r.get("updated_at", "")
                if upd:
                    dt = datetime.fromisoformat(upd.replace("Z", "+00:00"))
                    recent.append({
                        "id": r.get("id"), "name": r.get("name", "?"),
                        "distance_km": round(r.get("distance", 0) / 1000, 1),
                        "elevation_gain": r.get("elevation_gain", 0),
                        "updated_at": upd[:10],
                        "url": f"https://ridewithgps.com/routes/{rid}",
                        "recent": dt > cutoff,
                    })
            except Exception:
                pass

        if not recent:
            return _envelope("rwgps_recent_routes",
                f"Brak tras RWGPS w planning_facts. Znane ID: {known_ids}",
                data={"days": days, "known_ids": known_ids})

        recent.sort(key=lambda x: x["updated_at"], reverse=True)
        recent_only = [r for r in recent if r["recent"]]
        label = f"ostatnich {days} dni" if recent_only else "z planning_facts"
        show = recent_only if recent_only else recent

        parts = [f"\U0001f5fa\ufe0f Trasy RWGPS ({label}, {len(show)} tras):"]
        for r in show:
            flag = "" if r["recent"] else " (starszy niż 7 dni)"
            parts.append(f"  • [{r['updated_at']}] {r['name']} "
                        f"— {r['distance_km']} km, +{r['elevation_gain']}m{flag}")
            parts.append(f"    ID: {r['id']} | {r['url']}")

        return _envelope("rwgps_recent_routes", "\n".join(parts),
            data={"days": days, "count": len(show), "routes": show},
            sources_used=["rwgps", "qbot_v2.qbot_planning_facts"])
    except Exception as exc:
        return _envelope("rwgps_recent_routes", f"Błąd RWGPS: {exc}", status_override="ERROR")


def _handle_route_climbs(question: str) -> dict:

    import re as _re, os, httpx
    ql = question.lower()
    route_id_m = _re.search(r"\b(\d{6,8})\b", question)
    route_id = route_id_m.group(1) if route_id_m else None
    stage_m = _re.search(r"\b(?:etap|stage)[a-ząćęłńóśźż]*\s*(\d+)\b", ql)
    stage_n = int(stage_m.group(1)) if stage_m else None
    km_m = _re.search(r"(\d+(?:\.\d+)?)\s*[-\u2013]\s*(\d+(?:\.\d+)?)\s*km", question)
    km_from = float(km_m.group(1)) if km_m else 0.0
    km_to = float(km_m.group(2)) if km_m else None
    if not route_id:
        for kw in ["toskani", "tuscany"]:
            if kw in ql:
                route_id = _resolve_tuscany_e07_live_route_id(question)
                break
    route_id = _resolve_tuscany_e07_live_route_id(question, stage_num=stage_n, route_id=route_id)
    if not route_id and stage_n is not None:
        route_id = _resolve_tuscany_e07_live_route_id(question, stage_num=stage_n)
        if not route_id:
            return _envelope(
                "route_climbs",
                _stage_spec_error("tuscany_2026", stage_n),
                status_override="PARTIAL",
            )
    if not route_id:
        return _envelope("route_climbs", "Podaj route_id RWGPS lub nazwe trasy.", status_override="PARTIAL")
    try:
        env = dict(line.strip().split("=",1) for line in open("/opt/qbot/app/.env.local") if "=" in line and not line.startswith("#"))
        url = "https://ridewithgps.com/routes/{}.json?apikey={}&auth_token={}&version=2".format(
            route_id, env.get("RWGPS_API_KEY",""), env.get("RWGPS_AUTH_TOKEN",""))
        r = httpx.get(url, timeout=15.0)
        tp = r.json().get("route",{}).get("track_points",[])
        from tools.rwgps.climbs import detect_climbs, format_climbs_report
        climbs = detect_climbs(tp, km_from=km_from, km_to=km_to or (km_from+200))
        report = format_climbs_report(climbs)
        _header = f"Trasa: {route_id}\n"
        return _envelope("route_climbs", _header + report,
                         data={"climbs": climbs, "count": len(climbs),
                               "resolved_route_id": route_id, "km_from": km_from},
                         sources_used=["rwgps"])
    except Exception as exc:
        return _envelope("route_climbs", "Blad: {}".format(exc), status_override="ERROR")


def _handle_rwgps_poi_push(question: str) -> dict:
    import re as _re
    ql = question.lower()
    route_id_m = _re.search(r"\b(\d{6,8})\b", question)
    route_id = route_id_m.group(1) if route_id_m else None
    stage_m = _re.search(r"\b(?:etap|stage)[a-ząćęłńóśźż]*\s*(\d+)\b", ql)
    stage_n = int(stage_m.group(1)) if stage_m else None
    km_m = _re.search(r"(\d+(?:\.\d+)?)\s*[-\u2013]\s*(\d+(?:\.\d+)?)\s*km", question)
    km_from = float(km_m.group(1)) if km_m else 0.0
    km_to = float(km_m.group(2)) if km_m else None
    dry_run = not any(w in ql for w in ["potwierdz", "zatwierdz", "wykonaj", "wrzuc", "wyslij"])
    confirm = not dry_run
    if not route_id:
        for kw in ["toskani", "tuscany"]:
            if kw in ql:
                route_id = _resolve_tuscany_e07_live_route_id(question)
                break
    route_id = _resolve_tuscany_e07_live_route_id(question, stage_num=stage_n, route_id=route_id)
    if not route_id and stage_n is not None:
        route_id = _resolve_tuscany_e07_live_route_id(question, stage_num=stage_n)
        if not route_id:
            return _envelope(
                "rwgps_poi_push",
                _stage_spec_error("tuscany_2026", stage_n),
                status_override="PARTIAL",
            )
    if not route_id:
        return _envelope("rwgps_poi_push", "Podaj route_id RWGPS lub nazwe trasy.", status_override="PARTIAL")
    if km_to is None:
        km_to = 530.0 if (route_id and route_id.startswith("5539")) else 100.0
    try:
        from qbot_route_tools import _tool_qbot_rwgps_poi_push
        result = _tool_qbot_rwgps_poi_push({
            "route_id": route_id, "km_from": km_from, "km_to": km_to,
            "km_total": 530.0 if (route_id and route_id.startswith("5539")) else 0.0,
            "dry_run": dry_run, "confirm": confirm,
        })
        status = result.get("status")
        if status == "DRY_RUN":
            sel = result.get("selected_pois") or []
            lines = ["km{:.1f} | {} | {}m | {}".format(
                p.get("route_km", 0), p.get("category"),
                int(p.get("distance_to_track_m", 0)), p.get("name")) for p in sel]
            preview = "\n".join(lines) if lines else "Brak POI w tym odcinku."
            answer = "Dry-run: {} POI z {} kandydatow.\n\n{}\n\nDodaj: potwierdz / wykonaj aby wyslac do RWGPS.".format(
                result.get("selected_count", 0), result.get("raw_poi_count", 0), preview)
        elif status == "OK":
            answer = "Wyslano {} POI do trasy {} w RWGPS. Lacznie: {} POI.".format(
                result.get("selected_count", 0), route_id, result.get("final_pois_count", 0))
        else:
            answer = "Blad: {}".format(result.get("error", status))
        return _envelope("rwgps_poi_push", answer, data=result, sources_used=["route_analyzer", "rwgps"])
    except Exception as exc:
        return _envelope("rwgps_poi_push", "Blad: {}".format(exc), status_override="ERROR")


def _handle_route_poi_analyze(question: str) -> dict:
    import re as _re2
    from qbot3.artifacts import store as _store
    ql = question.lower()
    route_id_m = _re2.search(r"\b(\d{6,8})\b", question)
    route_id = route_id_m.group(1) if route_id_m else None
    stage_m = _re2.search(r"\b(?:etap|stage)[a-ząćęłńóśźż]*\s*(\d+)\b", ql)
    stage_n = int(stage_m.group(1)) if stage_m else None
    km_m = _re2.search(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*km", question)
    km_from = float(km_m.group(1)) if km_m else 0.0
    km_to = float(km_m.group(2)) if km_m else None
    if any(w in ql for w in ["nawierzchnia", "surface", "asfalt", "szuter"]):
        focus = "logistics"
    elif any(w in ql for w in ["jedzenie", "sklep", "woda", "resupply"]):
        focus = "logistics"
    else:
        focus = None
    artifact_id = None
    gpx_path = None
    if not route_id:
        try:
            arts = _store.list_artifacts(artifact_type="route")
            for a in arts:
                fname = (a.get("filename") or "").lower()
                if any(t in ql for t in ["toskania", "tuscany"] if t in fname):
                    artifact_id = a.get("artifact_id")
                    gpx_path = a.get("file_path") or a.get("abs_path")
                    rid_m2 = _re2.search(r"(\d{6,8})", fname)
                    if rid_m2:
                        route_id = rid_m2.group(1)
                    break
        except Exception:
            pass
    route_id = _resolve_tuscany_e07_live_route_id(question, stage_num=stage_n, route_id=route_id)
    if not route_id and not artifact_id and not gpx_path:
        # Fallback: spróbuj rozwiązać przez planning_facts (Toskania + etap N)
        for kw in ["toskani", "tuscany"]:
            if kw in ql:
                route_id = _resolve_tuscany_e07_live_route_id(question)
                break
    if not route_id and stage_n is not None:
        route_id = _resolve_tuscany_e07_live_route_id(question, stage_num=stage_n)
        if not route_id:
            return _envelope(
                "route_poi_analyze",
                _stage_spec_error("tuscany_2026", stage_n),
                status_override="PARTIAL",
            )
    if not route_id and not artifact_id and not gpx_path:
        return _envelope("route_poi_analyze", "Nie mogę zidentyfikować trasy. Podaj route_id RWGPS lub nazwę trasy (np. 'toskania etap 2').", status_override="PARTIAL")
    if km_to is None:
        km_to = 530.0 if (route_id and str(route_id).startswith("5539")) else 100.0
    try:
        from qbot_route_tools import _tool_qbot_route_poi_analyze
        result = _tool_qbot_route_poi_analyze({"route_id": route_id, "artifact_id": artifact_id, "path": gpx_path, "km_from": km_from, "km_to": km_to, "focus": focus, "output_format": "md", "confirm": True})
        if result.get("status") in ("OK", "PARTIAL"):
            answer = result.get("report_md") or result.get("answer") or "Analiza zakończona."
            return _envelope("route_poi_analyze", answer, data=result, sources_used=["route_analyzer"])
        return _envelope("route_poi_analyze", "Blad analizy: " + str(result.get("error", "nieznany")), status_override="ERROR")
    except Exception as exc:
        return _envelope("route_poi_analyze", "Blad: " + str(exc), status_override="ERROR")


# ---------------------------------------------------------------------------
# CLI test mode
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "pokaż dzisiejszy bilans"
    result = handle_query(q)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
