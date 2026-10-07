"""Pogoda jazdy w 'W czym jechalem' (garage.db ride_gear_log) - decyzja Michala 2026-10-07.

Po co: analiza "stroj <-> warunki <-> odczucie" bez recznego laczenia SQLite (garaz) i PostgreSQL (raport).
Denormalizacja: przy zapisie stroju / raportu kopiujemy 3 liczby z raportu jazdy do slotow meta:
  _temp_app = weather.apparent_c.value.avg  (open-meteo, tier B) - WIODACA (czujnik FIT nagrzewa sie na postoju)
  _temp_fit = weather.temp_c.value.avg      (FIT, tier A)        - tylko referencja
  _precip   = weather.precip_mm.value.sum   (open-meteo, tier B)
value = tekst z jedna cyfra po przecinku ("14.5").

Zasady:
- Tylko jazdy, ktore maja juz zapisany stroj. Brak stroju -> sloty pogodowe kasowane (bez sierot).
- Brak raportu (buduje sie asynchronicznie) -> nic nie robimy; dopisze save_report po zbudowaniu raportu.
- updated_at wierszy pogodowych = czas stroju tej jazdy (NIE 'teraz'): od updated_at zalezy
  "ostatnia jazda" w formularzu i kolejnosc historii doradcy ubioru.
- Sloty pogodowe NIE sa w _RIDE_GEAR_ALLOWED (qbot_web) - formularz nie moze ich nadpisac.

Uzycie:
  from qbot3.rides.gear_weather import sync_ride
  .venv/bin/python3 -m qbot3.rides.gear_weather [ride_key ...]   # bez argumentow: wszystkie jazdy z logu
"""
from __future__ import annotations

import os
import sqlite3
import sys

GARAGE_DB = "/opt/qbot/app/data/garage.db"
# slot -> (klucz w w1_json.weather, pole w value)
SLOTS = {"_temp_app": ("apparent_c", "avg"),
         "_temp_fit": ("temp_c", "avg"),
         "_precip": ("precip_mm", "sum")}


def _connect():
    try:
        import qbot_config  # noqa: F401  (laduje env)
    except Exception:
        pass
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
        connect_timeout=5, autocommit=True)


def fmt(v):
    try:
        return "%.1f" % float(v)
    except (TypeError, ValueError):
        return None


def values_from_weather(we) -> dict:
    """{slot: "x.x"} z bloku w1_json.weather; pomija brakujace."""
    out = {}
    for slot, (key, field) in SLOTS.items():
        blk = (we or {}).get(key)
        val = blk.get("value") if isinstance(blk, dict) else None
        s = fmt(val.get(field)) if isinstance(val, dict) else None
        if s is not None:
            out[slot] = s
    return out


def weather_for(cur, ride_key):
    """Blok weather z najnowszego raportu jazdy albo None, gdy raportu jeszcze nie ma."""
    cur.execute("SELECT w1_json->'weather' AS we FROM qbot_v2.ride_report_data "
                "WHERE ride_key=%s AND w1_json IS NOT NULL ORDER BY schema_version DESC LIMIT 1", (ride_key,))
    r = cur.fetchone()
    if not r:
        return None
    we = r["we"] if isinstance(r, dict) else r[0]
    return we or {}


def write_slots(g, ride_key, vals) -> dict:
    """Zapis do SQLite (bez commita). vals=None -> raportu brak, nic nie zmieniamy."""
    ph = ",".join("?" * len(SLOTS))
    row = g.execute("SELECT max(updated_at) FROM ride_gear_log WHERE ride_key=? AND slot NOT IN (%s)" % ph,
                    (ride_key, *SLOTS)).fetchone()
    ts = row[0] if row else None
    if ts is None:
        n = g.execute("DELETE FROM ride_gear_log WHERE ride_key=? AND slot IN (%s)" % ph, (ride_key, *SLOTS)).rowcount
        return {"ride": ride_key, "ok": False, "why": "brak stroju", "usuniete": n}
    if vals is None:
        return {"ride": ride_key, "ok": False, "why": "brak raportu"}
    for slot in SLOTS:
        if slot in vals:
            g.execute("INSERT INTO ride_gear_log (ride_key, slot, gear_id, value, updated_at) VALUES (?,?,NULL,?,?) "
                      "ON CONFLICT(ride_key, slot) DO UPDATE SET gear_id=NULL, value=excluded.value, "
                      "updated_at=excluded.updated_at", (ride_key, slot, vals[slot], ts))
        else:
            g.execute("DELETE FROM ride_gear_log WHERE ride_key=? AND slot=?", (ride_key, slot))
    return {"ride": ride_key, "ok": True, **vals}


def sync_ride(ride_key, cur=None) -> dict:
    """Uzupelnij/odswiez sloty pogodowe jednej jazdy. cur = opcjonalny kursor PG (dict_row)."""
    ride_key = str(ride_key or "").strip()
    if not ride_key:
        return {"ride": ride_key, "ok": False, "why": "brak ride_key"}
    g = sqlite3.connect(GARAGE_DB, timeout=5)
    try:
        has = g.execute("SELECT 1 FROM ride_gear_log WHERE ride_key=? LIMIT 1", (ride_key,)).fetchone()
        if not has:
            return {"ride": ride_key, "ok": False, "why": "brak stroju"}
        conn = None
        try:
            if cur is None:
                conn = _connect()
                cur = conn.cursor()
            we = weather_for(cur, ride_key)
        finally:
            if conn is not None:
                conn.close()
        res = write_slots(g, ride_key, None if we is None else values_from_weather(we))
        g.commit()
        return res
    finally:
        g.close()


def gear_log_rides() -> list:
    g = sqlite3.connect(GARAGE_DB, timeout=5)
    try:
        return [r[0] for r in g.execute("SELECT DISTINCT ride_key FROM ride_gear_log ORDER BY ride_key")]
    finally:
        g.close()


if __name__ == "__main__":
    sys.path.insert(0, "/opt/qbot/app")
    keys = sys.argv[1:] or gear_log_rides()
    c = _connect()
    try:
        k = c.cursor()
        for rk in keys:
            print(sync_ride(rk, cur=k))
    finally:
        c.close()
