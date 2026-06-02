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
    # "wczoraj" / "dzisiaj"
    ql = q.lower()
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


def _today_or(text: str) -> date:
    return _parse_date(text) or _TODAY


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
    (["/help", "help", "pomoc", "co umiesz", "co potrafisz", "lista komend", "komendy", "funkcje qbot", "co mozesz"], "qbot_help"),
    (["bilans", "balance", "kalorii", "kalorie", "kcal"], "daily_balance"),
    (["meal_logs", "intake_logs", "lista posiłków", "lista wpisów", "całe jedzenie", "surową listę", "jadłem", "jadłam", "lista posilkow", "wszystkie posilki", "pelna lista jedzenia"], "nutrition_intake_logs_list"),
    (["jedzenie", "jadło", "posiłek", "posiłki", "meal", "nutrition", "żywność", "zjadłem", "zjadłam", "spożycie"], "nutrition_day"),
    # ── Report and diagnostic intents (must precede nutrition_range) ──
    (["raport dobowy", "raport dzienny", "daily report", "podsumowanie dnia", "podsumowanie dni",
      "raport poranny", "poranny raport"], "daily_report"),
    (["raport z jazdy", "ride report", "ostatnia jazda", "raport z przejazdu", "raport aktywno\u015bci",
      "raport treningu", "raport po je\u017adzie", "analiza jazdy", "analiza przejazdu"], "ride_report"),
    (["brak danych w raporcie", "dlaczego raport jest pusty", "pusty raport", "raport pusty",
      "raport bez danych", "niekompletny raport", "czemu raport jest pusty",
      "diagnostyka raportu", "diagnostyka raport\u00f3w", "diagnostyka raportow",
      "status \u017ar\u00f3de\u0142 raportu", "status zrodel raportu",
      "dlaczego nie ma danych", "raport nie zawiera danych",
      "raport nie ma danych", "sprawd\u017a dane do raportu", "sprawdz dane do raportu",
      "dane do raportu", "sprawd\u017a \u017ar\u00f3d\u0142a raportu",
      "dlaczego raport jest niekompletny", "raport jest cz\u0119\u015bciowy",
      "raport nie dziala", "raport nie dzia\u0142a"], "report_diagnostic"),
    (["zakres", "od poniedziałku", "od poniedzialku", "ostatni tydzie\u0144", "ostatni tydzien",
      "makro za tydzie\u0144", "makro za tydzien", "ostatniego tygodnia"], "nutrition_range"),
    (["sen", "spałem", "spałam", "sleep", "spanie", "spaniu"], "sleep_day"),
    (["waga", "ważył", "wadze", "ważę", "masa ciała", "weight", "ile ważę"], "weight_lookup"),
    (["trend wagi", "trend waga", "trend wadze", "historia wagi", "historia wadze", "waga trend"], "weight_trend"),
    (["body composition", "skład ciała", "składzie ciała", "body fat", "tkanka tłuszczowa", "tkanki tłuszczowej", "tkankę tłuszczową", "body water", "woda w organizmie", "wody w organizmie", "wodę w organizmie", "masa mięśniowa", "masy mięśniowej", "masę mięśniową", "masa kostna", "masy kostnej", "masę kostną", "body comp", "body_comp", "bmi", "trend body composition", "pełny skład"], "body_comp"),
    (["body measurements", "body_measurements", "tabela body", "tabela wagi", "tabela składu", "wyniki ważenia", "pełna tabela body", "qbot_v2.body_measurements", "completeness_score"], "body_measurements_range"),
    (["wellness", "hrv", "body battery", "bateria", "tętno", "tętnie", "resting"], "wellness_day"),
    (["energia", "energię", "energy", "spaliłem", "spaliłam", "kroki", "steps", "aktywność"], "energy_day"),
    (["trening", "treningi", "treningów", "training", "aktywność fizyczna", "aktywności", "ćwiczenia", "sport", "jazda", "jeździłem"], "training_recent"),
    (["notatki", "pamięć", "pamiętasz", "pamięci", "wiem o", "fakty o", "w notatkach", "w pamięci", "w wiedzy", "przypomnij"], "memories_search"),
    (["pobierz trase", "przetworz trase", "fetch route", "pobierz etap", "przetworz etap", "obrab trase", "analizuj trase"], "route_workflow_fetch"),
    (["wyslij trase", "upload trasy", "zatwierdz trase", "potwierdz trase do rwgps"], "route_workflow_upload"),
    (["lista tras", "przetworzone trasy", "historia tras"], "route_workflow_list"),
    (["podjazdy", "climbs", "wzniesienia", "podejscia", "podjazd", "climb", "ile podjazdow", "trudne miejsca", "kategoria podjazdu", "hc", "cat 1", "cat 2", "cat 3", "cat 4"], "route_climbs"),
    (["wyslij poi", "dodaj poi", "wrzuc poi", "poi do rwgps", "wyslij do rwgps", "dodaj do trasy", "zatwierdz poi", "potwierdz poi", "wykonaj poi"], "rwgps_poi_push"),
    (["przeanalizuj poi", "analiza poi", "poi na trasie", "atrakcje na trasie", "atrakcje na etapie", "nawierzchnia trasy", "nawierzchnia etapu", "surface trasy", "analiza nawierzchni", "route_poi", "route_surface", "co po drodze", "sklepy na trasie", "woda na trasie", "jedzenie na trasie", "stacje na trasie", "stacja benzynowa", "paliwo na trasie", "fuel", "ładowanie na trasie", "poi etap", "poi trasy", "km trasy"], "route_poi_analyze"),
    (["wyjazd", "wyjazdy", "trip", "tripy", "zaplanowane", "toskania", "toskanię", "toskanii", "tuscany", "tuscany trail"], "trips_status"),
    (["atrakcje", "atrakcja", "attractions", "must see", "must-see", "co warto", "co zobaczyć", "co zobaczyc", "poi wyjazd"], "trip_attractions"),
    (["generuj trasę", "generuj trase", "generate route", "wygeneruj trasę", "wygeneruj trase", "zaproponuj trasę", "zaproponuj trase", "nowa trasa", "trasa od zera"], "route_generate"),
    (["etap", "etapy", "stage", "stages", "dzisiejszy etap", "etap dziś", "etap dzis", "plan etapów", "plan etapow", "jaki etap", "który etap"], "trip_stages"),
    (["odśwież xert", "wymuś live fetch", "live fetch xert", "sprawdź xert api", "refresh xert", "xert live", "xert na żywo", "xert live fetch", "wymuś xert"], "xert_live_fetch"),
    (["xert", "forma", "gotowość", "readiness", "freshness", "fatigue", "ftp", "ltp", "w'", "w_prime", "w prime"], "xert_status"),
    # ── Artifact lookup intents (must precede garage_search) ──
    (["artefakt", "artifact", "artifact store", "artifact_id",
      "metadane", "metadata", "zarejestrowany artefakt", "zarejestrowane artefakty",
      "route_logistics", "logistics_tool_implementation",
      "qbot_artifact", "artifacts_list", "artifact_search",
      "przeszukaj artefakty", "przeszukaj zarejestrowane",
      "nie odczytuj filesystemu", "nie czytaj z dysku"], "artifact_search"),
    # ── Artifact read intents ──
    (["zobacz /opt/qbot/artifacts/", "przeczytaj /opt/qbot/artifacts/",
      "odczytaj /opt/qbot/artifacts/", "poka\u017c /opt/qbot/artifacts/",
      "zobacz artefakt", "przeczytaj artefakt", "odczytaj artefakt",
      "poka\u017c artefakt", "artifact_get", "artifact_read",
      "artifact content", "odczytaj zarejestrowany",
      "poka\u017c zarejestrowany", "/opt/qbot/artifacts/"], "artifact_read"),
    (["garaż", "garage", "sprzęt", "sprzet", "rower", "rowery", "wyposażenie"], "garage_status"),
    (["kask", "buty", "rękawiczki", "rekawiczki", "kurtka", "kurtki", "jersey", "koszulka", "spodenki", "szukaj", "opony", "koła", "kola", "komponenty", "base layer", "rafa", "rapha", "pedaled", "kaski", "butów", "kurtek", "skarpety", "torby", "namiot", "kamizelka", "spodnie", "kierownica", "siodło", "siodlo", "lancuch", "łańcuch", "kaseta", "komin", "czapka", "chusta"], "garage_search"),
]


def _resolve_intent(question: str) -> str:
    ql = question.lower()
    for keywords, intent in INTENT_KEYWORDS:
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
    days = 14
    m = re.search(r"(\d+)\s*dni", text.lower())
    if m:
        days = min(int(m.group(1)), 90)
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
    """Return latest weight only — uses body_trend_weight view."""
    try:
        pg = _pg_conn()
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
    data["resolved_date"] = str(date.today())

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
        m = re.search(r"(\d+)\s*dni", text.lower())
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


def _handle_wellness_day(day_str: str) -> dict:
    d = _today_or(day_str)
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


# ---------------------------------------------------------------------------
# Garage / Gear
# ---------------------------------------------------------------------------
GARAGE_DB = "/opt/qbot/app/data/garage.db"

GARAGE_ALIASES: dict[str, list[str]] = {
    "kask": ["helmet"], "kaski": ["helmet"],
    "buty": ["shoes", "shoe"], "obuwie": ["shoes", "shoe"],
    "rekawiczki": ["gloves"], "rękawiczki": ["gloves"],
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

    raw_terms = [t for t in ql.split() if len(t) > 2 and t not in STOP_WORDS]
    if not raw_terms:
        raw_terms = [ql]

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
    "nutrition": ["kalorii", "kcal", "jedzenie", "jadlem", "jadlam", "bilans", "bialko",
                  "wegle", "tluszcz", "makro", "nutrition", "posilek", "spozycle",
                  "intake", "dieta", "kaloryczny"],
    "body": ["body composition", "sklad ciala", "body fat", "tkanka tluszczowa",
             "masa miesniowa", "bmi", "waga", "body comp", "body_comp",
             "pomiary ciala", "wyniki wazenia"],
    "sleep": ["sen", "spalem", "spalem", "sleep", "spanie", "regeneracja snu"],
    "wellness": ["hrv", "wellness", "bateria", "body battery", "tetno spoczynkowe",
                 "resting hr", "stres"],
    "training": ["trening", "treningi", "aktywnosc", "jazda", "jezddem", "sport",
                 "training", "workout", "aktywnosc fizyczna"],
    "energy": ["energia", "wydatek", "spalone", "spalony", "kroki", "steps", "energy"],
}

_DOMAIN_TO_HANDLER: dict[str, str] = {
    "nutrition": "nutrition_range",
    "body": "body_measurements_range",
    "sleep": "sleep_day",
    "wellness": "wellness_day",
    "training": "training_recent",
    "energy": "energy_day",
}


def _detect_domains(question: str) -> list[str]:
    """Wykryj domeny w pytaniu - zwroc liste gdy >1."""
    ql = question.lower()
    found = []
    for domain, signals in _DOMAIN_SIGNALS.items():
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
            if intent == "nutrition_range":
                r = _handle_nutrition_range(question)
            elif intent == "body_measurements_range":
                r = _handle_body_measurements_range(question)
            elif intent == "sleep_day":
                r = _handle_sleep_day(_parse_date_from_question(question))
            elif intent == "wellness_day":
                r = _handle_wellness_day(_parse_date_from_question(question))
            elif intent == "training_recent":
                r = _handle_training_recent(question)
            elif intent == "energy_day":
                r = _handle_energy_day(_parse_date_from_question(question))
            else:
                continue

            if r.get("status") not in ("ERROR",):
                results.append((domain, r.get("answer", "")))
            else:
                errors.append(domain)
        except Exception as exc:
            errors.append(f"{domain}:{exc}")

    if not results:
        return _envelope("multi_intent", "Brak danych dla podanych domen.", status_override="PARTIAL")

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
            entry.update(dse)
            had_data = True
            if dse.get("expenditure_total") is not None:
                totals["expenditure_kcal"] += dse["expenditure_total"]
                totals_count["expenditure_kcal"] += 1
            # Uzywaj balance_kcal jesli jest, w przeciwnym razie oblicz z intake-expenditure
            _bal = dse.get("balance_kcal")
            if _bal is None and dse.get("intake_kcal") is not None and dse.get("expenditure_total") is not None:
                _bal = dse["intake_kcal"] - dse["expenditure_total"]
            if _bal is not None:
                totals["balance_kcal"] += _bal
                totals_count["balance_kcal"] += 1
            # If no nutrition summary but daily_summary has intake, use that
            if not n and dse.get("intake_kcal") is not None:
                totals["intake_kcal"] += dse["intake_kcal"]
                totals_count["intake_kcal"] += 1

        per_day.append(entry)
        if not had_data:
            missing_days.append(ds)
        current += timedelta(days=1)

    # Build answer
    parts = [f"📊 Bilans od {date_from} do {date_to} ({len(per_day)} dni):"]
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
def _handle_trip_stages(text: str) -> dict:
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


# ---------------------------------------------------------------------------
# Report diagnostic handlers
# ---------------------------------------------------------------------------
def _diagnose_source_status() -> dict:
    """Check freshness of all data sources for today."""
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
        rows = _safe_fetch(pg, """
            SELECT id, date, started_at, sport_type, distance_m, duration_s, elevation_m,
                   avg_power_w, avg_hr_bpm, activity_name
            FROM qbot_v2.training_sessions
            WHERE date = %s
            ORDER BY started_at DESC
            LIMIT 5
        """, (today_str,))
        yesterday_rows = _safe_fetch(pg, """
            SELECT id, date, started_at, sport_type, distance_m, duration_s, elevation_m,
                   avg_power_w, avg_hr_bpm, activity_name
            FROM qbot_v2.training_sessions
            WHERE date = %s
            ORDER BY started_at DESC
            LIMIT 5
        """, ((_TODAY - timedelta(days=1)).isoformat(),))
        pg.close()
    except Exception as exc:
        return _envelope("ride_report", f"B\u0142\u0105d diagnostyczny: {exc}", status_override="ERROR")

    all_rows = rows + yesterday_rows if rows and yesterday_rows else (rows or yesterday_rows or [])

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
                # Extract after 'artefakt' or 'artifact' (skip common noise words)
                for prefix in ["artefakt", "artifact"]:
                    if prefix in q:
                        idx = q.find(prefix) + len(prefix)
                        after = question[idx:].strip().lstrip(":,. ")
                        # Skip known noise words
                        noise = {"store", "w", "na", "z", "po", "do", "QBot", "qbot", "i", "oraz", "the"}
                        words = [w for w in after.split() if w.lower() not in noise][:3]
                        candidate = " ".join(words).strip(".,;:!?").strip()
                        if candidate:
                            search_term = candidate
                            break

    if not search_term:
        # Last resort: use the whole query
        search_term = question.strip()[:80]

    # ── Method 1: Try search_artifacts() from artifact store module ──
    all_artifacts = []
    store_unavailable = False
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
            like = f"%{search_term.lower()}%"
            rows = _safe_fetch(pg, """
                SELECT artifact_id, project_id, artifact_type, title, filename,
                       file_path, size_bytes, sha256, source, status, metadata_json,
                       created_at, updated_at
                FROM qbot_v2.artifacts
                WHERE status = 'active'::qbot_v2.artifact_status
                  AND (LOWER(filename) LIKE %s
                    OR LOWER(title) LIKE %s
                    OR LOWER(project_id) LIKE %s
                    OR artifact_id::text LIKE %s)
                ORDER BY created_at DESC
                LIMIT 50
            """, (like, like, like, like))
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
        parts.append(f"  artifact_id: {a.get('artifact_id', '?')}")
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

def handle_query(question: str, context: dict | None = None) -> dict:
    ql = question.lower().strip()
    intent = _resolve_intent(question)
    if intent == "qbot_help":
        return _handle_qbot_help()

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

    # ── Multi-intent: sprawdz czy pytanie obejmuje >1 domene ──────────
    if _has_range_indicator(question):
        domains = _detect_domains(question)
        if len(domains) >= 2:
            return _handle_multi_intent(question, domains)

    day_str = _parse_date_from_question(question)

    # If daily_balance or nutrition_day but query has range indicators → nutrition_range
    if intent in ("daily_balance", "nutrition_day") and _has_range_indicator(question):
        return _handle_nutrition_range(question)

    # If body_comp/weight_lookup/weight_trend + range → body_measurements_range
    if intent in ("body_comp", "weight_lookup", "weight_trend") and _has_range_indicator(question):
        return _handle_body_measurements_range(question)

    if intent == "nutrition_range":
        return _handle_nutrition_range(question)
    elif intent == "daily_balance":
        return _handle_daily_balance(day_str)
    elif intent == "nutrition_intake_logs_list":
        return _handle_intake_logs_list(day_str)
    elif intent == "nutrition_day":
        return _handle_nutrition_day(day_str)
    elif intent == "sleep_day":
        return _handle_sleep_day(day_str)
    elif intent == "wellness_day":
        return _handle_wellness_day(day_str)
    elif intent == "weight_lookup":
        return _handle_weight_lookup(day_str)
    elif intent == "weight_trend":
        return _handle_weight_trend(question)
    elif intent == "body_comp":
        return _handle_body_comp(day_str)
    elif intent == "body_measurements_range":
        return _handle_body_measurements_range(question)
    elif intent == "energy_day":
        return _handle_energy_day(day_str)
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
    elif intent == "trip_stages":
        return _handle_trip_stages(question)
    elif intent == "trip_attractions":
        return _handle_trip_attractions(question)
    elif intent == "route_generate":
        return _handle_route_generate(question)
    elif intent == "daily_report":
        return _handle_daily_report_diagnostic(question)
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
    else:
        return _envelope("unrecognized",
                         "Nie rozpoznano intencji. Spróbuj: bilans, jedzenie, sen, wellness, energia, trening, xert, garaż, notatki, wyjazdy, raport dobowy, raport z jazdy.")


def _handle_route_feasibility(question):
    import re as _re
    ql=question.lower()
    route_id_m=_re.search(r"\b(\d{6,8})\b",question)
    route_id=route_id_m.group(1) if route_id_m else None
    hour_m=_re.search(r"(\d{1,2}):\d{2}|start\s*(\d{1,2})",ql)
    start_hour=int((hour_m.group(1) or hour_m.group(2))) if hour_m else 8
    for name,rid in [("toskania","55257604"),("tuscany","55257604")]:
        if name in ql and not route_id: route_id=rid; break
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
        return _envelope('tile_analysis',sep.join(lines),data=r,sources_used=['statshunters'])
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
                lines.append("  {} | {} | {} km | {}".format(
                    r.get("date"), r.get("name"), r.get("distance_km"), r.get("status")))
            answer = "\n".join(lines)
        return _envelope("route_workflow", answer, data={"routes": routes}, sources_used=[])
    except Exception as exc:
        return _envelope("route_workflow", "Blad: {}".format(exc), status_override="ERROR")


def _handle_route_climbs(question: str) -> dict:
    import re as _re, os, httpx
    ql = question.lower()
    route_id_m = _re.search(r"\b(\d{6,8})\b", question)
    route_id = route_id_m.group(1) if route_id_m else None
    km_m = _re.search(r"(\d+(?:\.\d+)?)\s*[-\u2013]\s*(\d+(?:\.\d+)?)\s*km", question)
    km_from = float(km_m.group(1)) if km_m else 0.0
    km_to = float(km_m.group(2)) if km_m else None
    if not route_id:
        for name, rid in [("toskania","55257604"),("tuscany","55257604")]:
            if name in ql: route_id = rid; break
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
        return _envelope("route_climbs", report, data={"climbs": climbs, "count": len(climbs)}, sources_used=["rwgps"])
    except Exception as exc:
        return _envelope("route_climbs", "Blad: {}".format(exc), status_override="ERROR")


def _handle_rwgps_poi_push(question: str) -> dict:
    import re as _re
    ql = question.lower()
    route_id_m = _re.search(r"\b(\d{6,8})\b", question)
    route_id = route_id_m.group(1) if route_id_m else None
    km_m = _re.search(r"(\d+(?:\.\d+)?)\s*[-\u2013]\s*(\d+(?:\.\d+)?)\s*km", question)
    km_from = float(km_m.group(1)) if km_m else 0.0
    km_to = float(km_m.group(2)) if km_m else None
    dry_run = not any(w in ql for w in ["potwierdz", "zatwierdz", "wykonaj", "wrzuc", "wyslij"])
    confirm = not dry_run
    if not route_id:
        for name, rid in [("toskania", "55257604"), ("tuscany", "55257604")]:
            if name in ql:
                route_id = rid
                break
    if not route_id:
        return _envelope("rwgps_poi_push", "Podaj route_id RWGPS lub nazwe trasy.", status_override="PARTIAL")
    if km_to is None:
        km_to = 530.0 if route_id == "55257604" else 100.0
    try:
        from qbot_route_tools import _tool_qbot_rwgps_poi_push
        result = _tool_qbot_rwgps_poi_push({
            "route_id": route_id, "km_from": km_from, "km_to": km_to,
            "km_total": 530.0 if route_id == "55257604" else 0.0,
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
    if not route_id and not artifact_id and not gpx_path:
        return _envelope("route_poi_analyze", "Nie mogę zidentyfikować trasy. Podaj route_id RWGPS, artifact_id lub nazwę trasy.", status_override="PARTIAL")
    if km_to is None:
        km_to = 530.0 if route_id == "55257604" else 100.0
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
