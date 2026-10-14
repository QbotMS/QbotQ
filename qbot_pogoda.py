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
