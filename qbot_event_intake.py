"""Ryczalt kaloryczny z eventu kalendarza (wakacje itp.).

Event w qbot_v2.calendar_entry z ustawionym kcal_planned oznacza:
"tych dni nie loguje, przyjmij X kcal dziennie".

Zasada:
  - dzien z REALNYM jedzeniem  -> nietkniety, a nasz stary szacunek znika,
  - dzien bez realnego jedzenia -> jeden wpis szacunkowy X kcal + makra
    liczone jak w presetach (mediana z realnych dni o zblizonym spozyciu,
    fallback: podzial FALLBACK_SPLIT).

Zrodlo wpisu = SOURCE (zawiera slowo 'preset'), dzieki czemu:
  - UI kalendarza pokazuje dzien jako SZACUNEK, nie ZALOGOWANE,
  - silnik presetow nie uczy sie makr z wlasnych szacunkow.

Wpiete w nocny fitmodel.daily_job (dzien poprzedni + kilka wstecz).
"""
from __future__ import annotations

from datetime import date, timedelta

import qbot_nutrition_presets as _presets

SOURCE = "event_preset"
_NOTE_PREFIX = "Ryczalt z eventu: "


def _has_real_intake(conn, day) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM qbot_v2.intake_logs WHERE date=%s "
        "AND COALESCE(quality_status::text,'')<>'estimated' "
        "AND source NOT ILIKE '%%preset%%' LIMIT 1", (day,)).fetchone())


def _has_any_estimate(conn, day, other_than_ours: bool = False) -> bool:
    sql = ("SELECT 1 FROM qbot_v2.intake_logs WHERE date=%s "
           "AND source ILIKE '%%preset%%'")
    if other_than_ours:
        sql += " AND source <> '" + SOURCE + "'"
    return bool(conn.execute(sql + " LIMIT 1", (day,)).fetchone())


def _drop_ours(conn, day) -> int:
    rows = conn.execute(
        "SELECT id FROM qbot_v2.intake_logs WHERE date=%s AND source=%s",
        (day, SOURCE)).fetchall()
    for r in rows:
        conn.execute("DELETE FROM qbot_v2.intake_items WHERE intake_log_id=%s", (r["id"],))
        conn.execute("DELETE FROM qbot_v2.intake_logs WHERE id=%s", (r["id"],))
    return len(rows)


def events_for_day(conn, day):
    """Eventy z ryczaltem pokrywajace dany dzien (najswiezszy pierwszy)."""
    return conn.execute(
        "SELECT id, title, day, end_day, kcal_planned FROM qbot_v2.calendar_entry "
        "WHERE kcal_planned IS NOT NULL AND kcal_planned > 0 "
        "AND day <= %s AND COALESCE(end_day, day) >= %s "
        "ORDER BY created_at DESC", (day, day)).fetchall()


def fill_day(conn, day) -> dict:
    """Wyrownuje jeden dzien. Zwraca {'day':..., 'action':...}."""
    if isinstance(day, date):
        day = day.isoformat()

    evs = events_for_day(conn, day)
    if not evs:
        if _drop_ours(conn, day):
            return {"day": day, "action": "usuniety_ryczalt_brak_eventu"}
        return {"day": day, "action": "brak_eventu"}

    if _has_real_intake(conn, day):
        n = _drop_ours(conn, day)
        return {"day": day, "action": "realne_jedzenie" + ("_usunieto_ryczalt" if n else "")}

    ev = evs[0]
    kcal = int(ev["kcal_planned"])
    m = _presets.macros_for_kcal(conn, kcal)

    # juz mamy wlasny wpis z ta sama kaloryka -> nic nie rob
    cur = conn.execute(
        "SELECT i.kcal FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i "
        "ON i.intake_log_id=l.id WHERE l.date=%s AND l.source=%s", (day, SOURCE)).fetchall()
    if cur and abs(float(cur[0]["kcal"] or 0) - kcal) < 1:
        return {"day": day, "action": "bez_zmian", "kcal": kcal}

    # recznie wybrany preset dnia ma pierwszenstwo przed ryczaltem z eventu
    if _has_any_estimate(conn, day, other_than_ours=True):
        return {"day": day, "action": "wlasny_preset_dnia"}

    _drop_ours(conn, day)
    label = (ev["title"] or "event").strip()
    logid = conn.execute(
        "INSERT INTO qbot_v2.intake_logs (date, eaten_at, meal_type, note, source, quality_status) "
        "VALUES (%s, %s, 'meal', %s, %s, 'estimated') RETURNING id",
        (day, day + " 12:00", _NOTE_PREFIX + label + " (" + str(kcal) + " kcal)", SOURCE)).fetchone()["id"]
    conn.execute(
        "INSERT INTO qbot_v2.intake_items (intake_log_id, food_name, amount, unit, kcal, "
        "protein_g, carbs_g, fat_g, source) VALUES (%s, %s, 1, 'dzien', %s, %s, %s, %s, %s)",
        (logid, "Ryczalt: " + label + " (szacunek)", kcal,
         m["protein_g"], m["carbs_g"], m["fat_g"], SOURCE))
    return {"day": day, "action": "zapisany_ryczalt", "kcal": kcal,
            "protein_g": m["protein_g"], "carbs_g": m["carbs_g"], "fat_g": m["fat_g"],
            "n_days": m["n_days"], "low_confidence": m["low_confidence"], "event": label}


def fill_recent(conn, days_back: int = 7, until=None) -> list[dict]:
    """Wyrownuje ostatnie dni (domyslnie 7 wstecz do WCZORAJ wlacznie).

    Dzien biezacy pomijamy celowo: jest jeszcze w toku, moze zostac zalogowany.
    """
    end = until or (date.today() - timedelta(days=1))
    if isinstance(end, str):
        end = date.fromisoformat(end)
    out = []
    for i in range(days_back - 1, -1, -1):
        out.append(fill_day(conn, end - timedelta(days=i)))
    conn.commit()
    return out


def fill_range(conn, start, end) -> list[dict]:
    """Wyrownuje konkretny zakres dat (uzywane przy zalozeniu ryczaltu wstecz)."""
    if isinstance(start, str):
        start = date.fromisoformat(start)
    if isinstance(end, str):
        end = date.fromisoformat(end)
    out = []
    d = start
    while d <= end:
        out.append(fill_day(conn, d))
        d += timedelta(days=1)
    conn.commit()
    return out
