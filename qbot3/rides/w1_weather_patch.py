"""Dociaganie brakujacej pogody (sila wiatru + opad) do ZAPISANYCH raportow z jazdy (W1).

Raporty zbudowane przed 2026-09-24 nie maja weather.wind_ms / weather.precip_mm. Zamiast przebudowy
calego raportu (nawierzchnia, W'bal...) liczymy tylko pogode tym samym kodem co builder
(ride_report_builder._weather_block: te same godziny Open-Meteo dla GPS tej jazdy) i wpisujemy dwa pola.

Uzycie:
  from qbot3.rides.w1_weather_patch import patch_ride, missing_for, patch_in_background
  .venv/bin/python3 -m qbot3.rides.w1_weather_patch [--gear-log | ride_key ...]   # recznie / jednorazowo
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading

GARAGE_DB = "/opt/qbot/app/data/garage.db"
_LOCK = threading.Lock()
_RUNNING: set = set()


def _has(we: dict, k: str) -> bool:
    v = (we or {}).get(k)
    return isinstance(v, dict) and v.get("value") is not None


def missing_for(cur, ride_keys) -> list:
    """Ktore z podanych jazd maja zapisany raport, ale bez wind_ms lub precip_mm."""
    if not ride_keys:
        return []
    cur.execute("SELECT DISTINCT ON (ride_key) ride_key, schema_version, w1_json->'weather' AS we "
                "FROM qbot_v2.ride_report_data WHERE ride_key = ANY(%s) AND w1_json IS NOT NULL "
                "ORDER BY ride_key, schema_version DESC", (list(ride_keys),))
    out = []
    for r in cur.fetchall():
        we = r["we"] or {}
        if not (_has(we, "wind_ms") and _has(we, "precip_mm")):
            out.append(r["ride_key"])
    return out


def _recs_from_db(cur, ride_key):
    """Rekordy w formacie _parse_fit (ts, temp, lat/lon w semicircles) z activity_record, co 60 s."""
    from qbot3.rides.ride_report_builder import SC_DEG
    cur.execute("SELECT ts, lat, lon, temperature_c FROM qbot_v2.activity_record WHERE external_id=%s "
                "AND (sec::int %% 60)=0 ORDER BY ts", (ride_key,))
    out = []
    for x in cur.fetchall():
        la, lo = x.get("lat"), x.get("lon")
        out.append({"ts": x["ts"], "temp": x.get("temperature_c"),
                    "lat": (float(la) / SC_DEG) if la is not None else None,
                    "lon": (float(lo) / SC_DEG) if lo is not None else None})
    return out


def patch_ride(cur, ride_key: str) -> dict:
    """Liczy pogode jazdy i wpisuje weather.wind_ms + weather.precip_mm do najnowszego W1."""
    from qbot3.rides import ride_report_builder as rrb
    cur.execute("SELECT schema_version, fit_path, w1_json->'ride'->>'date' AS day FROM qbot_v2.ride_report_data "
                "WHERE ride_key=%s AND w1_json IS NOT NULL ORDER BY schema_version DESC LIMIT 1", (ride_key,))
    r = cur.fetchone()
    if not r:
        return {"ride": ride_key, "ok": False, "why": "brak raportu"}
    recs = None                                    # FIT najpierw (czas UTC pewny), 1 Hz z bazy awaryjnie
    fit = r["fit_path"]
    if not fit or not os.path.exists(fit):
        cand = "/opt/qbot/artifacts/fit/%s.fit" % ride_key
        fit = cand if os.path.exists(cand) else None
    if fit:
        try:
            recs, _ev, _ses = rrb._parse_fit(fit)
        except Exception:  # noqa
            recs = None
    if not recs:
        recs = _recs_from_db(cur, ride_key)
    if not recs:
        return {"ride": ride_key, "ok": False, "why": "brak pliku FIT i danych 1 Hz"}
    day = r["day"] or (recs[0]["ts"].strftime("%Y-%m-%d") if recs else None)
    if not recs or not day:
        return {"ride": ride_key, "ok": False, "why": "pusty FIT"}
    we = rrb._weather_block(recs, day)
    wm, pr = we.get("wind_ms"), we.get("precip_mm")
    if not (_has(we, "wind_ms") or _has(we, "precip_mm")):
        return {"ride": ride_key, "ok": False, "why": "Open-Meteo bez danych"}
    # caly blok pogody z tego samego kodu co builder (po naprawie strefy czasu 2026-09-24)
    cur.execute("UPDATE qbot_v2.ride_report_data SET w1_json = jsonb_set(w1_json, '{weather}', %s::jsonb, true) "
                "WHERE ride_key=%s AND schema_version=%s",
                (json.dumps(we, ensure_ascii=False, default=str), ride_key, r["schema_version"]))
    return {"ride": ride_key, "ok": True, "wind_ms": (wm or {}).get("value"), "precip_mm": (pr or {}).get("value")}


def _worker(keys):
    try:
        from qbot3.rides import ride_report_builder as rrb
        conn = rrb._connect()
        try:
            cur = conn.cursor()
            for k in keys:
                try:
                    print("w1_weather_patch:", patch_ride(cur, k))
                except Exception as e:  # noqa
                    print("w1_weather_patch blad", k, e)
        finally:
            conn.close()
    finally:
        with _LOCK:
            _RUNNING.difference_update(keys)


def patch_in_background(ride_keys) -> int:
    """Nieblokujaco: uzupelnij pogode dla podanych jazd (pomija juz liczone w tle)."""
    with _LOCK:
        keys = [k for k in ride_keys if k not in _RUNNING]
        _RUNNING.update(keys)
    if keys:
        threading.Thread(target=_worker, args=(keys,), daemon=True, name="w1_weather_patch").start()
    return len(keys)


def gear_log_rides() -> list:
    g = sqlite3.connect(GARAGE_DB)
    try:
        return [r[0] for r in g.execute("SELECT DISTINCT ride_key FROM ride_gear_log")]
    finally:
        g.close()


if __name__ == "__main__":
    sys.path.insert(0, "/opt/qbot/app")
    from qbot3.rides import ride_report_builder as rrb
    args = sys.argv[1:]
    conn = rrb._connect()
    cur = conn.cursor()
    keys = gear_log_rides() if (not args or args == ["--gear-log"]) else args
    todo = missing_for(cur, keys)
    print("jazd: %d, bez pogody: %d" % (len(keys), len(todo)))
    for k in todo:
        print(patch_ride(cur, k))
    conn.close()
