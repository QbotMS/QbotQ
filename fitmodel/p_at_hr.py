# -*- coding: utf-8 -*-
"""Moc przy tym samym tetnie (P@HR) per jazda -- WSKAZNIK FORMY (wykres "Wydolnosc" w Formie).

Od 2026-10-18 zastepuje stary straznik fitmodel/power_meter_guard.py (przeniesiony do archive/).
Tu NIE MA progow, baz miernika ani werdyktow (ALERT/OK). Jedynym straznikiem wiarygodnosci mocy
jest fitmodel/load_guard.py, a jedynym miejscem decyzji -- kwarantanna
(qbot_v2.fitmodel_ride_quarantine). Patrz DECISIONS 2026-10-18.

Liczenie (bez zmian wzgledem starego straznika, zeby wykres byl ciagly):
mediana mocy z sekund z tetnem 115-134, kadencja >= 40, predkosc >= 3 m/s, moc > 0.
Ponizej 10 min takich sekund -> p_at_hr_w = NULL (jazda krotka/regeneracyjna).
Tabela qbot_v2.ride_p_at_hr: external_id, ride_date, p_at_hr_w, meter_key, temp_c.
"""
from __future__ import annotations

import statistics as st

HR_LO, HR_HI = 115, 135
MIN_S = 600

DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.ride_p_at_hr (
    external_id  text PRIMARY KEY,
    ride_date    date,
    p_at_hr_w    numeric,
    meter_key    text,
    temp_c       numeric,
    computed_at  timestamptz NOT NULL DEFAULT now())"""

_METER_SQL = ("COALESCE('ant:' || d.ant_device_number::text, "
              "'sn:' || d.serial_number::text)")


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def meter_key(cur, external_id: str):
    """Miernik jazdy z pliku FIT ('ant:<id>' / 'sn:<serial>') albo None. Informacyjnie."""
    cur.execute(
        f"SELECT {_METER_SQL} FROM qbot_v2.activity_device d "
        "WHERE d.external_id=%s AND d.device_type='bike_power' "
        f"AND {_METER_SQL} IS NOT NULL ORDER BY d.device_index LIMIT 1",
        (external_id,))
    r = cur.fetchone()
    return r[0] if r else None


def compute(cur, external_id: str):
    """(P@HR w W albo None, mediana temperatury albo None)."""
    cur.execute("SELECT power_w, hr_bpm, cadence_rpm, speed_mps, temperature_c "
                "FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY sec", (external_id,))
    raw = cur.fetchall()
    temps = [t for *_, t in raw if t is not None]
    temp = st.median(temps) if temps else None
    vals = [p for p, h, c, v, _t in raw
            if p and p > 0 and h and HR_LO <= h < HR_HI and (c or 0) >= 40 and (v or 0) >= 3.0]
    if len(vals) < MIN_S:
        return None, temp
    return st.median(vals), temp


_UPSERT = ("INSERT INTO qbot_v2.ride_p_at_hr (external_id, ride_date, p_at_hr_w, meter_key, temp_c) "
           "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (external_id) DO UPDATE SET "
           "ride_date=EXCLUDED.ride_date, p_at_hr_w=EXCLUDED.p_at_hr_w, meter_key=EXCLUDED.meter_key, "
           "temp_c=EXCLUDED.temp_c, computed_at=now()")


def run(conn, lookback_days: int = 7, recheck: bool = False) -> dict:
    """Liczy P@HR jazd z ostatnich N dni bez wpisu (recheck=True: wszystkie z okna)."""
    ensure_table(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT t.external_id, t.date FROM qbot_v2.training_sessions t "
        "WHERE t.date >= CURRENT_DATE - %s * interval '1 day' AND t.avg_power_w IS NOT NULL "
        + ("" if recheck else
           "AND NOT EXISTS (SELECT 1 FROM qbot_v2.ride_p_at_hr g WHERE g.external_id = t.external_id) ")
        + "ORDER BY t.date, t.external_id", (lookback_days,))
    out = {"computed": 0, "no_value": 0}
    for eid, d in cur.fetchall():
        p, temp = compute(cur, eid)
        cur.execute(_UPSERT, (eid, d, None if p is None else round(p, 1), meter_key(cur, eid),
                              None if temp is None else round(temp, 1)))
        out["computed" if p is not None else "no_value"] += 1
    conn.commit()
    return out


def migrate_from_old_guard(conn) -> int:
    """Jednorazowo 2026-10-18: przenosi policzone P@HR ze starej tabeli power_meter_guard
    (bez temperatury -- stara tabela jej nie trzymala). Istniejacych wpisow nie nadpisuje."""
    ensure_table(conn)
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('qbot_v2.power_meter_guard')")
    if cur.fetchone()[0] is None:
        return 0
    cur.execute("INSERT INTO qbot_v2.ride_p_at_hr (external_id, ride_date, p_at_hr_w, meter_key) "
                "SELECT external_id, ride_date, p_at_hr_w, meter_key FROM qbot_v2.power_meter_guard "
                "WHERE p_at_hr_w IS NOT NULL ON CONFLICT (external_id) DO NOTHING")
    n = cur.rowcount
    conn.commit()
    return n


if __name__ == "__main__":
    #   .venv/bin/python3 fitmodel/p_at_hr.py [--recheck DNI]
    import os, sys
    sys.path.insert(0, "/opt/qbot/app")
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.api import _db_connect
    rech = len(sys.argv) > 2 and sys.argv[1] == "--recheck"
    c = _db_connect()
    try:
        print(run(c, lookback_days=int(sys.argv[2]) if rech else 7, recheck=rech))
    finally:
        c.close()
