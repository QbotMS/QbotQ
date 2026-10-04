"""Synchronizacja progu mocy ModelQ -> intervals.icu -> Hammerhead -> Karoo -> FIT -> Garmin Connect.

DECISIONS 2026-10-04. Ustalenia:
- Garmin Connect liczy IF/TSS z `threshold_power` zapisanego przez Karoo w FIT (session: 247 W w jazdach
  04.10 i 27.09; IF/TSS w FIT == w Garmin). Wystarczy poprawic FTP na Karoo - zapis do Garmina zbedny.
- Karoo bierze FTP z Hammerheada, Hammerhead z intervals.icu (Third-party Sync, polaczone przez Michala).
  Sync Hammerheada przenosi tez strefy, max HR (173, ustawione 04.10) i wage z intervals.icu.
- Zrodlo: najnowsze `qbot_v2.fitmodel_daily.cp_modelq_w` (niesie TP z sygnatury MQ2; nazwa historyczna).
- Histereza 2%: zapis tylko gdy |TP - FTP_intervals| / FTP_intervals >= 2% (strefy nie skacza codziennie).
- NIE wolamy `.../sport-settings/{id}/apply` (przeliczyloby wstecz historie aktywnosci w intervals).
- Kazda zmiana i kazdy blad -> qbot_v2.threshold_sync_log + Telegram. Bledy NIE sa polykane (lekcja fit_ingest).

CLI: .venv/bin/python3 fitmodel/threshold_sync.py [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt

API = "https://intervals.icu/api/v1/athlete/0"
HYSTERESIS = 0.02
TARGET = "intervals"

_DDL = """
CREATE TABLE IF NOT EXISTS qbot_v2.threshold_sync_log (
    id            bigserial PRIMARY KEY,
    at            timestamptz NOT NULL DEFAULT now(),
    target        text NOT NULL,
    old_w         int,
    new_w         int,
    cp_source_day date,
    status        text NOT NULL,
    error         text
)
"""


def needs_update(old_w, new_w, hysteresis: float = HYSTERESIS) -> bool:
    if new_w is None:
        return False
    if not old_w:
        return True
    return abs(float(new_w) - float(old_w)) / float(old_w) >= hysteresis


def _log(conn, old_w, new_w, day, status, error=None) -> None:
    if conn is None:
        return
    with conn.cursor() as cur:
        cur.execute(_DDL)
        cur.execute("INSERT INTO qbot_v2.threshold_sync_log (target, old_w, new_w, cp_source_day, status, error) "
                    "VALUES (%s,%s,%s,%s,%s,%s)", (TARGET, old_w, new_w, day, status, error))
    conn.commit()


def latest_tp(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT day, cp_modelq_w FROM qbot_v2.fitmodel_daily "
                    "WHERE cp_modelq_w IS NOT NULL AND day <= current_date ORDER BY day DESC LIMIT 1")
        r = cur.fetchone()
    if not r:
        return None, None
    return r[0], float(r[1])


def _ride_settings(client) -> dict:
    r = client.get(f"{API}/sport-settings")
    r.raise_for_status()
    for s in r.json():
        if "Ride" in (s.get("types") or []):
            return s
    raise RuntimeError("intervals.icu: brak ustawien sportu Ride")


def _client():
    import httpx
    import qbot_config as cfg
    if not cfg.INTERVALS_API_KEY:
        raise RuntimeError("brak INTERVALS_API_KEY w konfiguracji")
    return httpx.Client(auth=("API_KEY", cfg.INTERVALS_API_KEY), timeout=30)


def run(conn, send=None, client=None, dry_run: bool = False, tp_day=None, tp_w=None) -> dict:
    """Krok daily_job. Zwraca slownik statusu; przy bledzie loguje, alarmuje i rzuca wyjatek."""
    day, tp = (tp_day, tp_w) if tp_w is not None else latest_tp(conn)
    if tp is None:
        raise RuntimeError("brak cp_modelq_w w fitmodel_daily")
    target = int(round(tp))
    old = None
    own = client is None
    try:
        client = client or _client()
        s = _ride_settings(client)
        old = s.get("ftp")
        if not needs_update(old, target):
            return {"threshold_sync": "bez zmian", "intervals_ftp": old, "tp": target, "tp_day": str(day)}
        if dry_run:
            return {"threshold_sync": "dry-run: zapisalbym", "old": old, "new": target, "tp_day": str(day)}
        r = client.put(f"{API}/sport-settings/{s['id']}", json={"ftp": target})
        r.raise_for_status()
        check = _ride_settings(client).get("ftp")
        if int(check or 0) != target:
            raise RuntimeError(f"odczyt kontrolny: intervals ma {check} W zamiast {target} W")
        _log(conn, old, target, day, "ok")
        if send:
            send(f"\u2699\ufe0f Prog mocy na Karoo: {old} -> {target} W (TP ModelQ z {day}). "
                 f"Hammerhead pobierze go z intervals.icu; IF/TSS w Garmin Connect od nastepnej jazdy.")
        return {"threshold_sync": "zapisano", "old": old, "new": target, "tp_day": str(day)}
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"[:500]
        _log(conn, old, target, day, "error", err)
        if send:
            try:
                send(f"\u26a0\ufe0f Synchronizacja progu mocy do intervals.icu NIEUDANA: {err}. "
                     f"Karoo zostaje na {old} W, TP ModelQ = {target} W.")
            except Exception:
                pass
        raise
    finally:
        if own and client is not None:
            try:
                client.close()
            except Exception:
                pass


def _cli() -> None:
    import os
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.api import _db_connect
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    send = None
    if not a.dry_run:
        from fitmodel.power_meter_guard import _telegram_send
        send = _telegram_send
    print(run(_db_connect(), send=send, dry_run=a.dry_run))


if __name__ == "__main__":
    _cli()
