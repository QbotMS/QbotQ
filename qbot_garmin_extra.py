"""[GARMIN-DANE] Pelne dane snu/HRV z Garmina + pola dodatkowe (Etap 1, 2026-10-14).

Wczesniej importer (qbot_wellness_store._garmin_fetch_wellness) pobieral pelne
odpowiedzi get_sleep_data / get_hrv_data, ale zapisywal tylko wycinek. Ten modul:
  - zapisuje PELNA odpowiedz do qbot_v2.garmin_daily_raw (date, kind),
  - wyciaga pola dodatkowe do qbot_v2.qbot_wellness_daily (wiersz source='garmin'):
    temp. skory, potrzeba snu (dzis/jutro), status HRV Garmina + norma.

Zasada: status/norma HRV Garmina sa TYLKO do porownan -- wlasny status liczy QBot
(decyzja 2026-10-14). Schemat: sql/garmin_extra_v1.sql. Dok.: docs/GARMIN_DANE.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

APP_DIR = Path("/opt/qbot/app")
SQL_FILE = APP_DIR / "sql" / "garmin_extra_v1.sql"

EXTRA_COLUMNS = (
    "skin_temp_dev_c", "sleep_need_min", "sleep_need_baseline_min", "sleep_need_feedback",
    "next_sleep_need_min", "next_sleep_need_feedback", "garmin_hrv_status",
    "hrv_weekly_avg", "hrv_balanced_low", "hrv_balanced_high",
)


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _int(v: Any) -> int | None:
    n = _num(v)
    return int(round(n)) if n is not None else None


def _d(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def extract_extra(sleep_raw: Any, hrv_raw: Any) -> dict[str, Any]:
    """Wyciaga pola dodatkowe z pelnych odpowiedzi Garmina. Brak pola -> None."""
    s = _d(sleep_raw)
    dto = _d(s.get("dailySleepDTO"))
    need = _d(dto.get("sleepNeed"))
    nxt = _d(dto.get("nextSleepNeed"))
    h = _d(_d(hrv_raw).get("hrvSummary"))
    base = _d(h.get("baseline"))

    skin = None
    if s.get("skinTempDataExists") is not False:
        skin = _num(s.get("avgSkinTempDeviationC"))

    return {
        "skin_temp_dev_c": skin,
        "sleep_need_min": _int(need.get("actual")),
        "sleep_need_baseline_min": _int(need.get("baseline")),
        "sleep_need_feedback": need.get("feedback") or None,
        "next_sleep_need_min": _int(nxt.get("actual")),
        "next_sleep_need_feedback": nxt.get("feedback") or None,
        "garmin_hrv_status": h.get("status") or s.get("hrvStatus") or None,
        "hrv_weekly_avg": _num(h.get("weeklyAvg")),
        "hrv_balanced_low": _num(base.get("balancedLow")),
        "hrv_balanced_high": _num(base.get("balancedUpper")),
    }


def ensure_schema(conn) -> None:
    """Aplikuje sql/garmin_extra_v1.sql (idempotentne)."""
    with conn.cursor() as cur:
        cur.execute(SQL_FILE.read_text())
    conn.commit()


def save_extra(cur, date_str: str, source: str, sleep_raw: Any, hrv_raw: Any) -> dict[str, Any]:
    """Zapisuje pelne odpowiedzi + aktualizuje pola dodatkowe w wierszu (date, source).

    Wiersz qbot_wellness_daily musi juz istniec (tworzy go importer); gdy go nie ma,
    zapisuje sie tylko pelna odpowiedz. Zwraca wyciagniete pola.
    """
    for kind, payload in (("sleep", sleep_raw), ("hrv", hrv_raw)):
        if isinstance(payload, (dict, list)) and payload:
            cur.execute(
                """
                INSERT INTO qbot_v2.garmin_daily_raw (date, kind, payload)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (date, kind) DO UPDATE SET
                    payload = EXCLUDED.payload, fetched_at = now()
                """,
                (date_str, kind, json.dumps(payload, ensure_ascii=False, default=str)),
            )
    extra = extract_extra(sleep_raw, hrv_raw)
    sets = ", ".join(f"{c} = %s" for c in EXTRA_COLUMNS)
    cur.execute(
        f"UPDATE qbot_v2.qbot_wellness_daily SET {sets} WHERE date = %s AND source = %s",
        tuple(extra[c] for c in EXTRA_COLUMNS) + (date_str, source),
    )
    return extra
