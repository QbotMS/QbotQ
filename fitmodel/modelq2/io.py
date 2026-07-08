"""I/O dla ModelQ v2 -- JEDYNY modul dotykajacy bazy.

Read-only z activity_record (dane 1Hz). ZERO zaleznosci od v1/fitmodel_daily.
Zapis do modelq2_* dojdzie pozniej (osobne tabele, izolowane).
Wspoldzieli tylko _db_connect ze starym (polaczenie, nie logika).
"""
from __future__ import annotations
import datetime as dt

from fitmodel.ftp_resolver import _db_connect


def fetch_ride_rows(external_id: str) -> list:
    """Zwraca [(ts, power_w), ...] 1Hz dla jazdy, posortowane po czasie."""
    conn = _db_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ts, power_w FROM qbot_v2.activity_record "
            "WHERE external_id = %s ORDER BY ts", (external_id,))
        return [(ts, float(p) if p is not None else None) for ts, p in cur.fetchall()]
    finally:
        conn.close()


def list_rides(date_from: dt.date, date_to: dt.date, min_ticks: int = 600) -> list:
    """Lista jazd (external_id, date, n) w oknie, z min. liczba probek 1Hz.
    Dedup po dacie NIE jest robiony tu -- zwraca wszystkie strumienie."""
    conn = _db_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT external_id, MIN(ts)::date AS d, COUNT(*) AS n "
            "FROM qbot_v2.activity_record "
            "WHERE ts::date BETWEEN %s AND %s "
            "GROUP BY external_id HAVING COUNT(*) >= %s "
            "ORDER BY d", (date_from, date_to, min_ticks))
        return [(eid, d, n) for eid, d, n in cur.fetchall()]
    finally:
        conn.close()
