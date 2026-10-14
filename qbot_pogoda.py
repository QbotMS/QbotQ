"""Pogoda -- dane punktowe obok radaru: dom (z Trenera) i opad z modelu ICON-D2 co 15 min.

- model_point(lat, lon): Open-Meteo, models=icon_seamless (14.10.2026: samo icon_d2 zwracalo 400 'No data is available
  for this location' takze dla Warszawy; seamless = ICON-D2 gdzie jest, dalej ICON-EU), minutely_15=precipitation, na 12 h do przodu. ICON-D2 = siatka 2,2 km,
  liczony co 3 h, uwzglednia dane radarowe (asymilacja). Uzywany na osi czasu PO horyzoncie radaru (0-60/120 min).
  Cache w pamieci 10 min na punkt (zaokraglony do 0,05 st).
- home(): najczestszy punkt startu jazd (qbot_trener_engine.home_point, 60 ostatnich jazd, zaokr. 0,1 st).
Dok.: docs/POGODA_RADAR.md
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
URL = "https://api.open-meteo.com/v1/forecast"
HOURS = 12
_CACHE: dict = {}
CACHE_S = 600


def model_point(lat: float, lon: float, hours: int = HOURS) -> dict:
    key = (round(lat / 0.05) * 0.05, round(lon / 0.05) * 0.05, hours)
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time() - CACHE_S:
        return hit[1]
    q = urllib.parse.urlencode({"latitude": round(lat, 4), "longitude": round(lon, 4), "models": "icon_seamless",
                                "minutely_15": "precipitation", "forecast_minutely_15": hours * 4,
                                "timezone": "Europe/Warsaw"})
    try:
        with urllib.request.urlopen(URL + "?" + q, timeout=12) as r:
            j = json.load(r)
    except Exception as e:  # siec/serwis -- pokaz, nie zgaduj
        return {"status": "ERROR", "error": f"Model ICON-D2 niedostepny: {type(e).__name__}"}
    m = j.get("minutely_15") or {}
    pts = []
    for t, mm in zip(m.get("time") or [], m.get("precipitation") or []):
        if mm is None:
            continue
        pts.append({"iso": t, "t": t[11:16], "mm15": round(mm, 2), "mmh": round(mm * 4, 1)})
    res = {"status": "OK" if pts else "BRAK_DANYCH", "model": "ICON (DWD): D2 2 km, dalej EU 7 km", "krok_min": 15, "punkty": pts}
    _CACHE[key] = (time.time(), res)
    return res


def home(cur) -> dict | None:
    """cur: kursor psycopg z wierszami jako dict."""
    import qbot_trener_engine as E
    p = E.home_point(cur)
    if not p:
        return None
    return {"lat": float(p[0]), "lon": float(p[1]), "zrodlo": "najczestszy start jazd (Trener)"}


# ---------------------------------------------------------------- warunki dla roweru (punkt, godzinowo)
HOURLY = ("temperature_2m,apparent_temperature,relative_humidity_2m,dew_point_2m,precipitation,snowfall,"
          "wind_speed_10m,wind_gusts_10m,wind_direction_10m,visibility,soil_temperature_0cm,weather_code")
_CC: dict = {}


def _kier(deg):
    if deg is None:
        return None
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((deg + 22.5) // 45) % 8]


def conditions_point(lat: float, lon: float, hours: int = 24) -> dict:
    """Godzinowe warunki dla roweru (Open-Meteo best_match = w Europie ICON, 12 h wstecz + `hours` naprzod).

    Wyliczane flagi (proste, jawne progi -- do kalibracji):
      mgla: widocznosc < 1000 m; ograniczona < 4000 m
      oblodzenie: grunt (0 cm) <= 0,5 C ORAZ (opad/snieg w ostatnich 12 h lub punkt rosy >= temp. gruntu -> szron)
      nawierzchnia: suma opadu z 6 h wstecz >= 2 mm -> mokra/bloto; >= 0,3 mm -> wilgotna
      rosa: temp - punkt rosy < 2 C
    Wiatr w m/s.
    """
    key = (round(lat / 0.05) * 0.05, round(lon / 0.05) * 0.05, hours)
    hit = _CC.get(key)
    if hit and hit[0] > time.time() - CACHE_S:
        return hit[1]
    q = urllib.parse.urlencode({"latitude": round(lat, 4), "longitude": round(lon, 4), "hourly": HOURLY,
                                "past_hours": 12, "forecast_hours": hours, "wind_speed_unit": "ms",
                                "timezone": "Europe/Warsaw"})
    try:
        with urllib.request.urlopen(URL + "?" + q, timeout=12) as r:
            j = json.load(r)
    except Exception as e:
        return {"status": "ERROR", "error": f"Prognoza warunkow niedostepna: {type(e).__name__}"}
    h = j.get("hourly") or {}
    tt = h.get("time") or []
    g = lambda k, i: (h.get(k) or [None] * len(tt))[i]
    import datetime as _dt
    now = _dt.datetime.now(TZ).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    rows = []
    for i, t in enumerate(tt):
        prec = [g("precipitation", k) or 0 for k in range(max(0, i - 12), i)]
        snow = [g("snowfall", k) or 0 for k in range(max(0, i - 12), i)]
        p6 = sum((g("precipitation", k) or 0) for k in range(max(0, i - 6), i + 1))
        T, Td, Ts, vis = g("temperature_2m", i), g("dew_point_2m", i), g("soil_temperature_0cm", i), g("visibility", i)
        lod = 0
        if Ts is not None and Ts <= 0.5:
            wet = sum(prec) > 0.1 or sum(snow) > 0 or (g("precipitation", i) or 0) > 0
            frost = Td is not None and Td >= Ts
            lod = 3 if (wet and Ts <= -0.5) else 2 if (wet or frost) else 1
        mgla = None if vis is None else (2 if vis < 1000 else 1 if vis < 4000 else 0)
        naw = 2 if p6 >= 2 else 1 if p6 >= 0.3 else 0
        rosa = None if (T is None or Td is None) else round(T - Td, 1)
        rows.append({"iso": t, "t": t[11:16], "przeszlosc": _dt.datetime.fromisoformat(t) < now,
                     "temp": T, "odcz": g("apparent_temperature", i), "rh": g("relative_humidity_2m", i), "rosa_pkt": Td,
                     "opad": g("precipitation", i), "snieg": g("snowfall", i), "wiatr": g("wind_speed_10m", i),
                     "porywy": g("wind_gusts_10m", i), "kier": g("wind_direction_10m", i), "skad": _kier(g("wind_direction_10m", i)),
                     "widocznosc": vis, "grunt": Ts, "kod": g("weather_code", i),
                     "mgla": mgla, "lod": lod, "nawierzchnia": naw, "zapas_rosy": rosa})
    res = {"status": "OK" if rows else "BRAK_DANYCH", "model": "Open-Meteo (Europa: ICON DWD)", "godziny": rows}
    _CC[key] = (time.time(), res)
    return res


def kwadraty(share: str = "") -> dict:
    """Wszystkie zdobyte kwadraty z14 (StatsHunters) -- [x, y]. Strona rysuje te w widoku.
    share: STATSHUNTERS_SHARE_ID (qbot_web podaje z _env(), jak route_tiles)."""
    import os as _os
    from tools.tile_store import fetch_tiles, get_tile_set
    share = share or _os.getenv("STATSHUNTERS_SHARE_ID", "")
    if not share:
        try:
            for line in open("/opt/qbot/app/.env"):
                if line.startswith("STATSHUNTERS_SHARE_ID="):
                    share = line.strip().split("=", 1)[1]
        except Exception:
            pass
    if not share:
        return {"status": "BRAK_DANYCH", "error": "brak STATSHUNTERS_SHARE_ID", "zoom": 14, "kwadraty": []}
    td = fetch_tiles(share)
    owned = sorted(get_tile_set(td.get("tiles", [])))
    return {"status": "OK" if not td.get("_error") else "BLAD", "error": td.get("_error"), "zoom": 14,
            "kwadraty": [[x, y] for x, y in owned]}
