"""Twardy bezpiecznik na wywolania Google Places (searchNearby).

Limity (nadpisywalne przez env):
- GOOGLE_PLACES_DAILY_LIMIT   (domyslnie 200) — na dobe kalendarzowa,
- GOOGLE_PLACES_MONTHLY_LIMIT (domyslnie 1000) — na miesiac kalendarzowy.

Kazde zapytanie do Places MUSI najpierw wywolac check_and_reserve(). Funkcja
sprawdza OBA liczniki; jesli ktorykolwiek zostalby przekroczony -> rzuca
PlacesBudgetExceeded i NIE rezerwuje (zero kosztu). W przeciwnym razie
inkrementuje licznik dnia i zwraca stan zuzycia.

Licznik: qbot_v2.google_places_usage (jeden wiersz na dzien: usage_date, calls).
Miesiac liczony jako SUM(calls) po biezacym miesiacu kalendarzowym.
"""

from __future__ import annotations

import os
from datetime import date

import psycopg


def _daily_limit() -> int:
    try:
        return int(os.getenv("GOOGLE_PLACES_DAILY_LIMIT", "200"))
    except (TypeError, ValueError):
        return 200


def _monthly_limit() -> int:
    try:
        return int(os.getenv("GOOGLE_PLACES_MONTHLY_LIMIT", "1000"))
    except (TypeError, ValueError):
        return 1000


class PlacesBudgetExceeded(RuntimeError):
    """Podniesione, gdy limit dzienny lub miesieczny Places jest wyczerpany."""


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )


_ensured = False


def _ensure_table(conn) -> None:
    global _ensured
    if _ensured:
        return
    conn.execute(
        "CREATE TABLE IF NOT EXISTS qbot_v2.google_places_usage ("
        "usage_date date PRIMARY KEY, calls integer NOT NULL DEFAULT 0)"
    )
    _ensured = True


def usage_snapshot() -> dict[str, int]:
    """Biezace zuzycie bez rezerwacji (do podgladu/logow)."""
    today = date.today()
    conn = _conn()
    try:
        _ensure_table(conn)
        day = conn.execute(
            "SELECT calls FROM qbot_v2.google_places_usage WHERE usage_date=%s",
            (today,),
        ).fetchone()
        month = conn.execute(
            "SELECT COALESCE(SUM(calls),0) FROM qbot_v2.google_places_usage "
            "WHERE date_trunc('month', usage_date)=date_trunc('month', %s::date)",
            (today,),
        ).fetchone()
        conn.commit()
        return {
            "day_used": int(day[0]) if day else 0,
            "day_limit": _daily_limit(),
            "month_used": int(month[0]) if month else 0,
            "month_limit": _monthly_limit(),
        }
    finally:
        conn.close()


def check_and_reserve(n: int = 1) -> dict[str, int]:
    """Sprawdz limity i zarezerwuj n wywolan Places.

    Rzuca PlacesBudgetExceeded, gdy dodanie n przekroczyloby limit dzienny
    lub miesieczny. W razie sukcesu zwraca stan po rezerwacji.
    """
    today = date.today()
    daily_limit = _daily_limit()
    monthly_limit = _monthly_limit()
    conn = _conn()
    try:
        _ensure_table(conn)
        with conn.transaction():
            row = conn.execute(
                "SELECT calls FROM qbot_v2.google_places_usage WHERE usage_date=%s FOR UPDATE",
                (today,),
            ).fetchone()
            day_used = int(row[0]) if row else 0
            month_row = conn.execute(
                "SELECT COALESCE(SUM(calls),0) FROM qbot_v2.google_places_usage "
                "WHERE date_trunc('month', usage_date)=date_trunc('month', %s::date)",
                (today,),
            ).fetchone()
            month_used = int(month_row[0]) if month_row else 0

            if day_used + n > daily_limit:
                raise PlacesBudgetExceeded(
                    f"limit dzienny Google Places wyczerpany ({day_used}/{daily_limit})"
                )
            if month_used + n > monthly_limit:
                raise PlacesBudgetExceeded(
                    f"limit miesieczny Google Places wyczerpany ({month_used}/{monthly_limit})"
                )

            conn.execute(
                "INSERT INTO qbot_v2.google_places_usage (usage_date, calls) VALUES (%s,%s) "
                "ON CONFLICT (usage_date) DO UPDATE "
                "SET calls = qbot_v2.google_places_usage.calls + EXCLUDED.calls",
                (today, n),
            )
        return {
            "day_used": day_used + n,
            "day_limit": daily_limit,
            "month_used": month_used + n,
            "month_limit": monthly_limit,
        }
    finally:
        conn.close()
