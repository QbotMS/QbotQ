#!/usr/bin/env python3
"""FAZA A — nakladka pogody na pudelka trasy (prognoza per pudelko).

Zrodlo pogody: OpenWeatherMap PRIMARY, Open-Meteo FALLBACK (spec: OWM primary).
OWM /data/2.5/forecast = 3-godzinowe, do 5 dni. Dla dat dalej niz 5 dni OWM nie
siega -> automatyczny fallback na Open-Meteo (16 dni).

Liczy ETA do kazdego pudelka i sklada per pudelko: temp, opady, wiatr + KIERUNEK,
oraz skladowa wiatru WZGLEDEM kierunku jazdy (+ w plecy / - w twarz) z heading pudelka.

Uzycie:
  .venv/bin/python -m tools.rwgps.route_weather --artifact-id 274 --start "2026-06-22 09:00" [--speed-kmh 22] [--dry-run] [--show 8]
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Warsaw")
except Exception:
    _TZ = None

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2

import httpx

OWM_URL = "https://api.openweathermap.org/data/2.5/forecast"
OM_URL = "https://api.open-meteo.com/v1/forecast"


def _load_env_local() -> None:
    p = Path(__file__).resolve().parents[2] / ".env.local"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)


def _db_connect():
    _load_env_local()
    kwargs = {"host": os.getenv("PGHOST", "127.0.0.1"), "port": int(os.getenv("PGPORT", "5432")),
              "user": os.getenv("PGUSER", "qbot"), "dbname": os.getenv("PGDATABASE", "qbot")}
    pw = os.getenv("PGPASSWORD")
    if pw:
        kwargs["password"] = pw
    return psycopg2.connect(**kwargs)


def _owm_key() -> str | None:
    _load_env_local()
    return (os.getenv("OPENWEATHERMAP_API_KEY") or os.getenv("OWM_API_KEY")
            or os.getenv("OPENWEATHER_API_KEY") or None)


def _local_hourkey(dt_local: datetime) -> str:
    return dt_local.strftime("%Y-%m-%dT%H")


def _fetch_owm(lat, lon, key):
    """OWM 3-godzinowa prognoza. Klucz mapy = lokalna godzina 'YYYY-MM-DDTHH'."""
    params = {"lat": round(lat, 4), "lon": round(lon, 4), "appid": key,
              "units": "metric", "lang": "pl"}
    r = httpx.get(OWM_URL, params=params, timeout=20.0)
    r.raise_for_status()
    items = r.json().get("list", [])
    out = {}
    for it in items:
        dt_utc = datetime.fromtimestamp(it["dt"], tz=timezone.utc)
        dt_local = dt_utc.astimezone(_TZ) if _TZ else dt_utc
        wind = it.get("wind", {})
        rain = it.get("rain", {}) or {}
        out[_local_hourkey(dt_local)] = {
            "temp": (it.get("main") or {}).get("temp"),
            "precip": rain.get("3h", 0.0),
            "wspeed": wind.get("speed"),     # units=metric -> m/s
            "wdir": wind.get("deg"),         # skad wieje
        }
    return out


def _fetch_open_meteo(lat, lon, day: str):
    params = {"latitude": round(lat, 4), "longitude": round(lon, 4),
              "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m",
              "wind_speed_unit": "ms", "timezone": "auto", "start_date": day, "end_date": day}
    r = httpx.get(OM_URL, params=params, timeout=20.0)
    r.raise_for_status()
    h = r.json().get("hourly", {})
    times = h.get("time", [])
    out = {}
    for i, ts in enumerate(times):
        out[ts[:13]] = {"temp": h.get("temperature_2m", [None] * len(times))[i],
                        "precip": h.get("precipitation", [None] * len(times))[i],
                        "wspeed": h.get("wind_speed_10m", [None] * len(times))[i],
                        "wdir": h.get("wind_direction_10m", [None] * len(times))[i]}
    return out


def _fetch_weather(lat, lon, dates):
    """OWM primary; fallback Open-Meteo gdy brak klucza / blad / brak pokrycia dat."""
    key = _owm_key()
    if key:
        try:
            owm = _fetch_owm(lat, lon, key)
            owm_dates = {k[:10] for k in owm}
            if owm and all(d in owm_dates for d in dates):
                return owm, "openweathermap"
            # OWM nie pokrywa wszystkich dat (np. >5 dni) -> fallback
        except Exception as e:
            print(f"  (OWM nieudane: {e!r} -> fallback Open-Meteo)")
    out = {}
    for d in dates:
        try:
            out.update(_fetch_open_meteo(lat, lon, d))
        except Exception as e:
            print(f"  (Open-Meteo nieudane dla {d}: {e!r})")
    return out, "open-meteo/forecast"


def _angnorm(d: float) -> float:
    return ((d + 180.0) % 360.0) - 180.0


def _rel_wind(heading_deg, wind_from_deg, wind_speed):
    if heading_deg is None or wind_from_deg is None or wind_speed is None:
        return None, None, None
    wind_to = (wind_from_deg + 180.0) % 360.0
    delta = _angnorm(heading_deg - wind_to)
    tail = wind_speed * math.cos(math.radians(delta))
    cross = wind_speed * math.sin(math.radians(delta))
    return tail, cross, delta


def build(artifact_id=None, route_id=None, start=None, speed_kmh=22.0,
          frame_size=80.0, kind="forecast", dry_run=False, show=0):
    if not start:
        print("BLAD: podaj --start \"YYYY-MM-DD HH:MM\"")
        return 2
    start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
    speed_ms = speed_kmh / 3.6

    conn = _db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    if artifact_id is not None:
        cur.execute("SELECT route_artifact_id, frame_index, dist_start_m, dist_end_m, mid_lat, mid_lon, heading_deg "
                    "FROM qbot_v2.route_frames WHERE route_artifact_id=%s AND frame_size_m=%s ORDER BY frame_index",
                    (artifact_id, int(frame_size)))
    else:
        cur.execute("SELECT route_artifact_id, frame_index, dist_start_m, dist_end_m, mid_lat, mid_lon, heading_deg "
                    "FROM qbot_v2.route_frames WHERE route_id=%s AND frame_size_m=%s ORDER BY frame_index",
                    (route_id, int(frame_size)))
    rows = cur.fetchall()
    if not rows:
        print("BLAD: brak pudelek (route_frames) — najpierw zbuduj siatke")
        return 2
    art_id = rows[0][0]

    lats = [r[4] for r in rows if r[4] is not None]
    lons = [r[5] for r in rows if r[5] is not None]
    clat, clon = sum(lats) / len(lats), sum(lons) / len(lons)

    last_eta = start_dt + timedelta(seconds=(rows[-1][2] / speed_ms))
    dates = sorted({start_dt.strftime("%Y-%m-%d"), last_eta.strftime("%Y-%m-%d")})
    hourly, source = _fetch_weather(clat, clon, dates)
    if not hourly:
        print("BLAD: zadne zrodlo pogody nie zwrocilo danych")
        return 1

    out_rows = []
    for (_aid, fidx, d0, _d1, _mlat, _mlon, head) in rows:
        eta = start_dt + timedelta(seconds=(d0 / speed_ms))
        key = eta.strftime("%Y-%m-%dT%H")
        w = hourly.get(key)
        if w is None:
            key2 = min(hourly.keys(), key=lambda k: abs(datetime.strptime(k, "%Y-%m-%dT%H") - eta))
            w = hourly[key2]
        tail, cross, rel = _rel_wind(head, w["wdir"], w["wspeed"])
        out_rows.append((art_id, int(frame_size), fidx, kind, eta, w["temp"], w["precip"],
                         w["wspeed"], w["wdir"], rel, tail, cross, source))

    tails = [r[10] for r in out_rows if r[10] is not None]
    temps = [r[5] for r in out_rows if r[5] is not None]
    print(f"Trasa artifact_id={art_id} | pudelka: {len(out_rows)} | centroid {clat:.3f},{clon:.3f} | zrodlo: {source}")
    print(f"  start {start_dt}  tempo {speed_kmh:.0f} km/h  ETA konca {last_eta:%H:%M}")
    if temps:
        print(f"  temperatura: {min(temps):.1f}..{max(temps):.1f} C")
    if tails:
        tw = sum(1 for t in tails if t > 0.5)
        hw = sum(1 for t in tails if t < -0.5)
        print(f"  wiatr wzgledny: {tw} w plecy, {hw} w twarz (z {len(tails)}); skladowa {min(tails):.1f}..{max(tails):.1f} m/s")
    if show:
        print(f"  --- pierwsze {show} pudelek ---")
        for r in out_rows[:show]:
            comp = f"{r[10]:+.1f}" if r[10] is not None else "n/a"
            print(f"   #{r[2]:>3} {r[4]:%H:%M} temp={r[5]}C opad={r[6]}mm wiatr={r[7]}m/s skad={r[8]} -> wzgl={comp}m/s")

    if dry_run:
        print("  [DRY-RUN] nie zapisuje")
        conn.rollback()
        return 0

    cur.execute("DELETE FROM qbot_v2.route_frame_weather WHERE route_artifact_id=%s AND frame_size_m=%s AND kind=%s",
                (art_id, int(frame_size), kind))
    for r in out_rows:
        cur.execute(
            "INSERT INTO qbot_v2.route_frame_weather "
            "(route_artifact_id, frame_size_m, frame_index, kind, valid_at, temp_c, precip_mm, "
            " wind_speed_ms, wind_dir_from_deg, wind_rel_deg, wind_component_ms, crosswind_ms, source) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", r)
    conn.commit()
    print(f"  ZAPISANO {len(out_rows)} wierszy pogody ({kind}, {source}) do route_frame_weather")
    return 0


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--artifact-id", type=int)
    g.add_argument("--route-id", type=str)
    ap.add_argument("--start", type=str, help="YYYY-MM-DD HH:MM")
    ap.add_argument("--speed-kmh", type=float, default=22.0)
    ap.add_argument("--frame-size", type=float, default=80.0)
    ap.add_argument("--kind", type=str, default="forecast")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    sys.exit(build(a.artifact_id, a.route_id, a.start, a.speed_kmh, a.frame_size, a.kind, a.dry_run, a.show))


if __name__ == "__main__":
    main()
