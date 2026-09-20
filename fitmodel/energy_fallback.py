#!/usr/bin/env python3
"""Energy fallback: podloga dobowego wydatku aktywnego z ModelQ (moc 1Hz).

Problem (2026-08-18): jazdy z Karoo laduja w Garmin Connect BEZ kalorii
(od ~2026-06), wiec dzienne "aktywne kcal" Garmina to wylacznie szacunek
z tetna nadgarstka Fenixa -- w dni jazdowe zaniza (obserwowane do -40%).

Zasada FALLBACK (podloga, nigdy sufit):
  ride_active   = koszt metaboliczny jazd z mocy 1Hz - nakladka spoczynkowa
  active_eff    = max(garmin_active, ride_active)
  - Garmin pozostaje zrodlem glownym; ModelQ tylko PODNOSI, nigdy nie obniza.
  - Gdy Garmin wroci do normy (>= podlogi), automatycznie wygrywa Garmin
    (energy_eff_source='garmin') -- zero recznego wylaczania.
  - Jazdy w AKTYWNEJ kwarantannie miernika (released IS NULL) nie buduja
    podlogi -- zepsuty miernik nie zawyzy bilansu.
  - Surowe kolumny Garmina (active_kcal/total_kcal) pozostaja nietkniete;
    fallback pisze wylacznie *_eff + mq_ride_kcal + energy_eff_source.

Stale energetyczne wspoldzielone z fitmodel.glycogen (jedna prawda:
GROSS_EFFICIENCY=0.23, J_PER_KCAL=4184).

CLI (backfill / recznie):
  .venv/bin/python3 -m fitmodel.energy_fallback 2026-06-01 2026-08-18
  .venv/bin/python3 -m fitmodel.energy_fallback 2026-08-18
  .venv/bin/python3 -m fitmodel.energy_fallback            # dzis + wczoraj
"""

from __future__ import annotations

import sys
from datetime import date as date_cls, timedelta
from typing import Any

from fitmodel.glycogen import DEFAULT_BMR_KCAL, GROSS_EFFICIENCY, J_PER_KCAL

SECONDS_PER_DAY = 86400.0
SOURCE_GARMIN = "garmin"
SOURCE_FLOOR = "modelq_ride_floor"
# Minimalna roznica [kcal], od ktorej uznajemy ze podloga faktycznie podnosi
FLOOR_MARGIN_KCAL = 1.0


def _ride_power_and_secs(cur, day: Any) -> tuple[float, float]:
    """(suma mocy 1Hz [J] jazd dnia, laczny czas tych jazd [s]).

    Tylko jazdy spoza aktywnej kwarantanny miernika i tylko te, ktore
    maja strumien mocy w activity_record.
    """
    cur.execute(
        """
        WITH rides AS (
            SELECT ts.external_id, ts.duration_s
            FROM qbot_v2.training_sessions ts
            WHERE ts.date = %s
              AND NOT EXISTS (
                  SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine q
                  WHERE q.external_id = ts.external_id
                    AND q.released IS NULL
              )
        ),
        work AS (
            SELECT r.external_id,
                   SUM(ar.power_w) AS sum_power_j,
                   MAX(r.duration_s) AS dur_s
            FROM rides r
            JOIN qbot_v2.activity_record ar ON ar.external_id = r.external_id
            GROUP BY r.external_id
        )
        SELECT COALESCE(SUM(sum_power_j), 0)::float8,
               COALESCE(SUM(dur_s), 0)::float8
        FROM work
        """,
        (day,),
    )
    row = cur.fetchone()
    if row is None:
        return 0.0, 0.0
    if isinstance(row, dict):
        vals = list(row.values())
        return float(vals[0] or 0), float(vals[1] or 0)
    return float(row[0] or 0), float(row[1] or 0)


def compute_day(conn, day: Any) -> dict[str, Any] | None:
    """Policz i zapisz active_kcal_eff/total_kcal_eff dla jednego dnia.

    Wymaga istniejacego wiersza w energy_daily (Garmin jest baza; bez
    wiersza nie ma czego podnosic). NIE robi commit -- commit po stronie
    wolajacego (import cron / recompute_range).
    Zwraca dict z wynikiem albo None gdy brak wiersza energy_daily.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT resting_kcal, active_kcal, total_kcal "
        "FROM qbot_v2.energy_daily WHERE date = %s",
        (day,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        resting_raw = row.get("resting_kcal")
        active_raw = row.get("active_kcal")
        total_raw = row.get("total_kcal")
    else:
        resting_raw, active_raw, total_raw = row

    resting = float(resting_raw) if resting_raw else DEFAULT_BMR_KCAL
    garmin_active = float(active_raw or 0)

    sum_power_j, ride_secs = _ride_power_and_secs(cur, day)
    ride_metab_kcal = (sum_power_j / GROSS_EFFICIENCY) / J_PER_KCAL
    bmr_overlap = resting * (ride_secs / SECONDS_PER_DAY)
    ride_active = max(0.0, ride_metab_kcal - bmr_overlap)

    if ride_active > garmin_active + FLOOR_MARGIN_KCAL:
        active_eff = ride_active
        total_eff = resting + active_eff
        source = SOURCE_FLOOR
    else:
        active_eff = garmin_active
        total_eff = float(total_raw) if total_raw else resting + garmin_active
        source = SOURCE_GARMIN

    cur.execute(
        """UPDATE qbot_v2.energy_daily
           SET active_kcal_eff = %s,
               total_kcal_eff = %s,
               mq_ride_kcal = %s,
               energy_eff_source = %s,
               updated_at = now()
           WHERE date = %s""",
        (round(active_eff, 1), round(total_eff, 1),
         round(ride_metab_kcal, 1), source, day),
    )
    return {
        "date": str(day),
        "garmin_active": round(garmin_active, 1),
        "mq_ride_kcal": round(ride_metab_kcal, 1),
        "ride_active": round(ride_active, 1),
        "active_kcal_eff": round(active_eff, 1),
        "total_kcal_eff": round(total_eff, 1),
        "source": source,
    }


def recompute_range(conn, d_from: date_cls, d_to: date_cls) -> list[dict[str, Any]]:
    """Backfill zakresu dat (wlacznie). Commit na koncu."""
    out: list[dict[str, Any]] = []
    day = d_from
    while day <= d_to:
        res = compute_day(conn, day)
        if res:
            out.append(res)
        day += timedelta(days=1)
    conn.commit()
    return out


def _main(argv: list[str]) -> int:
    sys.path.insert(0, "/opt/qbot/app")
    from fitmodel.api import _db_connect

    today = date_cls.today()
    if len(argv) >= 2:
        d_from = date_cls.fromisoformat(argv[0])
        d_to = date_cls.fromisoformat(argv[1])
    elif len(argv) == 1:
        d_from = d_to = date_cls.fromisoformat(argv[0])
    else:
        d_from, d_to = today - timedelta(days=1), today

    conn = _db_connect()
    try:
        results = recompute_range(conn, d_from, d_to)
    finally:
        conn.close()

    floored = [r for r in results if r["source"] == SOURCE_FLOOR]
    for r in results:
        mark = " <- FLOOR" if r["source"] == SOURCE_FLOOR else ""
        print(f"{r['date']}: garmin={r['garmin_active']:.0f} "
              f"ride_active={r['ride_active']:.0f} "
              f"eff={r['active_kcal_eff']:.0f}{mark}")
    print(f"-- dni: {len(results)}, podniesione: {len(floored)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
