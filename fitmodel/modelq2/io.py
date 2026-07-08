"""I/O dla ModelQ v2 -- JEDYNY modul dotykajacy bazy.

Read-only z activity_record (dane 1Hz) i fitmodel_daily (seed sygnatury cp_v3).
Zapis do modelq2_* dojdzie pozniej (osobne tabele, izolowane).
Wspoldzieli tylko _db_connect ze starym (polaczenie, nie logika).
"""
from __future__ import annotations
import datetime as dt

from fitmodel.ftp_resolver import _db_connect
from fitmodel.modelq2.signature import Signature


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


def seed_signature(as_of: dt.date) -> Signature | None:
    """Sygnatura poczatkowa (seed) z istniejacego ModelQ na dzien <= as_of.
    TP = cp_v3 (poprawny CP, NIE ftp_est). HIE = wprime_v3 (WIEMY ze zanizone,
    to tylko seed -- ekstrakcja przebic go poprawi). PP = najlepszy 5s w 90d.
    Zwraca None gdy brak danych.
    """
    conn = _db_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT cp_v3_w, wprime_v3_kj FROM qbot_v2.fitmodel_daily "
            "WHERE day <= %s AND cp_v3_w IS NOT NULL ORDER BY day DESC LIMIT 1", (as_of,))
        r = cur.fetchone()
        if not r or r[0] is None:
            return None
        tp = float(r[0])
        hie_kj = float(r[1]) if r[1] is not None else 8.0

        cur.execute(
            "SELECT MAX(mmp_5_w) FROM qbot_v2.training_sessions "
            "WHERE date BETWEEN %s AND %s", (as_of - dt.timedelta(days=90), as_of))
        r2 = cur.fetchone()
        pp = float(r2[0]) if r2 and r2[0] else tp * 3.5  # fallback

        # PP musi byc > TP; jesli surowe 5s dziwne, podnies
        if pp <= tp:
            pp = tp * 3.5
        return Signature.from_kj(tp_w=tp, hie_kj=hie_kj, pp_w=pp)
    finally:
        conn.close()
