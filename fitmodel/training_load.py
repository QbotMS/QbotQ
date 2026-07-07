from __future__ import annotations

"""ModelQ -- Training Load (CTL/ATL/TSB) na bazie XSS, w dwoch wariantach:
rownolegle, obok siebie:

  * "raw"  -- czysty model Bannistera/Coggana, tak jak liczy to kazde
              standardowe narzedzie (TrainingPeaks, Xert Training Load).
  * "plus" -- to samo, ale dzienny XSS przed wejsciem do wzoru na ZMECZENIE
              (ATL) jest skalowany wspolczynnikiem z `readiness_score`
              (fitmodel/readiness.py -- juz istniejacy, indywidualny
              z-score HRV+RHR+sen, 60-dniowy kroczacy baseline, mediana 3d).
              Slaba fizjologia -> ta sama jazda liczy sie jako ciezsza.
              Dobra fizjologia -> jako lzejsza. CTL (fitness) NIE jest
              korygowane -- to fakt historyczny (wykonana praca), korekta
              dotyczy tylko interpretacji zmeczenia.

Stale czasowe: CTL tau=42 dni, ATL tau=7 dni (Coggan, potwierdzone rowniez
jako wartosc uzywana przez Xert dla Training Load -- patrz DECISIONS.md
2026-07-07).

Konwencja TSB (jak w TrainingPeaks PMC): TSB(dzien D) = CTL(D-1) - ATL(D-1)
-- "forma NA WEJSCIU w dzien D", przed dzisiejszym treningiem.

Wspolczynnik korekty (kalibracja wstepna, do zweryfikowania na realnych
danych): fatigue_mult = clamp(1 - K*readiness_score, MULT_LO, MULT_HI).
K=0.4 dobrane tak, zeby przy progach readiness.py (+/-0.4 = swiezy/zmeczony)
dawac +/-16% korekty; twardy zacisk na wypadek ekstremalnych odczytow.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2

CTL_TAU_DAYS = 42
ATL_TAU_DAYS = 7
FATIGUE_MULT_K = 0.4
MULT_LO, MULT_HI = 0.5, 1.7


def _db_connect():
    kwargs: dict[str, Any] = {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER", "qbot"),
        "dbname": os.getenv("PGDATABASE", "qbot"),
    }
    pw = os.getenv("PGPASSWORD")
    if pw:
        kwargs["password"] = pw
    return psycopg2.connect(**kwargs)


def ensure_columns(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            ALTER TABLE qbot_v2.fitmodel_daily
                ADD COLUMN IF NOT EXISTS xss_daily NUMERIC,
                ADD COLUMN IF NOT EXISTS fatigue_mult NUMERIC,
                ADD COLUMN IF NOT EXISTS ctl_xss NUMERIC,
                ADD COLUMN IF NOT EXISTS atl_raw NUMERIC,
                ADD COLUMN IF NOT EXISTS atl_plus NUMERIC,
                ADD COLUMN IF NOT EXISTS tsb_raw NUMERIC,
                ADD COLUMN IF NOT EXISTS tsb_plus NUMERIC
        """)
    conn.commit()


def fatigue_multiplier(readiness_score: float | None) -> float:
    if readiness_score is None:
        return 1.0
    mult = 1.0 - FATIGUE_MULT_K * float(readiness_score)
    return max(MULT_LO, min(MULT_HI, mult))


def _daily_xss_series(conn, start: date, end: date) -> dict[date, float]:
    """Suma XSS z jazd OK per dzien (0.0 gdy brak jazdy tego dnia)."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT ride_date, sum(xss) FROM qbot_v2.fitmodel_wbal_ride
               WHERE status='OK' AND ride_date BETWEEN %s AND %s
               GROUP BY ride_date""",
            (start, end),
        )
        by_day = {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}
    out = {}
    d = start
    while d <= end:
        out[d] = by_day.get(d, 0.0)
        d += timedelta(days=1)
    return out


def _readiness_series(conn, start: date, end: date) -> dict[date, float | None]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT day, readiness_score FROM qbot_v2.fitmodel_daily
               WHERE day BETWEEN %s AND %s""",
            (start, end),
        )
        return {r[0]: (float(r[1]) if r[1] is not None else None) for r in cur.fetchall()}


def compute_and_store(conn, start: date, end: date,
                       ctl0: float = 0.0, atl0: float = 0.0) -> dict[str, Any]:
    """Przelicz CTL/ATL(raw)/ATL(plus)/TSB dla [start, end] wlacznie i zapisz
    do fitmodel_daily. Rekurencja EWMA startuje od ctl0/atl0 (domyslnie 0 --
    standardowa praktyka, po ~3xtau dni i tak w pelni sie "rozpedzi")."""
    ensure_columns(conn)
    xss_by_day = _daily_xss_series(conn, start, end)
    readiness_by_day = _readiness_series(conn, start, end)

    ctl_prev, atl_raw_prev, atl_plus_prev = ctl0, atl0, atl0
    rows_to_write = []
    d = start
    while d <= end:
        xss_today = xss_by_day.get(d, 0.0)
        readiness = readiness_by_day.get(d)
        mult = fatigue_multiplier(readiness)
        eff_xss_today = xss_today * mult

        tsb_raw = ctl_prev - atl_raw_prev
        tsb_plus = ctl_prev - atl_plus_prev

        ctl_today = ctl_prev + (xss_today - ctl_prev) / CTL_TAU_DAYS
        atl_raw_today = atl_raw_prev + (xss_today - atl_raw_prev) / ATL_TAU_DAYS
        atl_plus_today = atl_plus_prev + (eff_xss_today - atl_plus_prev) / ATL_TAU_DAYS

        rows_to_write.append((d, xss_today, round(mult, 3), round(ctl_today, 2),
                               round(atl_raw_today, 2), round(atl_plus_today, 2),
                               round(tsb_raw, 2), round(tsb_plus, 2)))

        ctl_prev, atl_raw_prev, atl_plus_prev = ctl_today, atl_raw_today, atl_plus_today
        d += timedelta(days=1)

    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO qbot_v2.fitmodel_daily
                   (day, xss_daily, fatigue_mult, ctl_xss, atl_raw, atl_plus, tsb_raw, tsb_plus)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (day) DO UPDATE SET
                   xss_daily=EXCLUDED.xss_daily, fatigue_mult=EXCLUDED.fatigue_mult,
                   ctl_xss=EXCLUDED.ctl_xss, atl_raw=EXCLUDED.atl_raw,
                   atl_plus=EXCLUDED.atl_plus, tsb_raw=EXCLUDED.tsb_raw,
                   tsb_plus=EXCLUDED.tsb_plus""",
            rows_to_write,
        )
    conn.commit()
    return {"days": len(rows_to_write), "start": start.isoformat(), "end": end.isoformat(),
            "last": rows_to_write[-1] if rows_to_write else None}


if __name__ == "__main__":
    conn = _db_connect()
    start = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2025, 5, 1)
    end = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today()
    print(compute_and_store(conn, start, end))
    conn.close()
