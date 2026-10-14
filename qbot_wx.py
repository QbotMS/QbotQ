"""QBot -- RDZEN DANYCH POGODOWYCH (jeden silnik, etap E1). Dok.: docs/POGODA_SILNIK.md

Jedno miejsce na: klienta Open-Meteo (prognoza i zespol), pamiec podreczna, POPRAWNE GODZINY.
Pozostale moduly (Pogoda, Okno jazdy, ostrzezenia; dalej w E2/E4: silnik tras, Trener, powiadomienia) pobieraja dane TYLKO stad.

Godziny (Open-Meteo): czesc wielkosci to wartosc z GODZINY POPRZEDZAJACEJ znacznik T (przedzial T-1..T) -- PREV_HOUR.
Dla godziny T..T+1 bierz wartosc ze znacznika T+1 (funkcja next_hour). 14.10.2026 ten blad byl w 4 modulach.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.parse
import urllib.request

FORECAST = "https://api.open-meteo.com/v1/forecast"
ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"
TZ_NAME = "Europe/Warsaw"
PREV_HOUR = frozenset({"precipitation", "rain", "showers", "snowfall", "precipitation_probability", "wind_gusts_10m", "weather_code"})
EPS_PROG = 0.2          # mm/h -- "pada" dla rowerzysty (szansa = odsetek wariantow >= progu)
_C: dict = {}           # (url, parametry) -> (czas, json)


def _get(url: str, params: dict, ttl: int, timeout: float) -> dict:
    return get_url(url + "?" + urllib.parse.urlencode(params), timeout=timeout, ttl=ttl)


ALLOWED = ("https://api.open-meteo.com/", "https://archive-api.open-meteo.com/", "https://ensemble-api.open-meteo.com/",
           "https://previous-runs-api.open-meteo.com/", "https://historical-forecast-api.open-meteo.com/", "https://geocoding-api.open-meteo.com/")


def get_url(url: str, timeout: float = 15, ttl: int = 600, ua: str = "QBot/1.0") -> dict:
    """Wspolny transport dla GOTOWYCH adresow Open-Meteo (moduly zachowuja swoje parametry -- E1/E2). Cache po pelnym adresie:
    prognoza ~10 min, archiwum/klimat dluzej (ttl podaje wolajacy). Tylko adresy Open-Meteo (ALLOWED)."""
    if not url.startswith(ALLOWED):
        raise ValueError("qbot_wx.get_url: tylko adresy Open-Meteo")
    hit = _C.get(url)
    if hit and hit[0] > time.time() - ttl:
        return hit[1]
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=timeout) as r:
        j = json.loads(r.read().decode("utf-8"))
    _C[url] = (time.time(), j)
    if len(_C) > 400:
        for k in sorted(_C, key=lambda k: _C[k][0])[:100]:
            _C.pop(k, None)
    return j


def forecast(lat: float, lon: float, hourly: str, models: list[str] | None = None, past_hours: int | None = None,
             forecast_hours: int | None = None, forecast_days: int | None = None, ttl: int = 600, timeout: float = 12) -> dict:
    """Surowa odpowiedz Open-Meteo /forecast (wiatr w m/s, czas lokalny Europe/Warsaw). Wyjatek przy bledzie sieci --
    obsluga po stronie wolajacego (kazdy modul ma wlasny komunikat)."""
    p = {"latitude": round(lat, 4), "longitude": round(lon, 4), "hourly": hourly, "wind_speed_unit": "ms", "timezone": TZ_NAME}
    if models:
        p["models"] = ",".join(models)
    if past_hours is not None:
        p["past_hours"] = past_hours
    if forecast_hours is not None:
        p["forecast_hours"] = forecast_hours
    if forecast_days is not None:
        p["forecast_days"] = forecast_days
    return _get(FORECAST, p, ttl, timeout)


def next_hour(series: list, i: int):
    """Wartosc wielkosci z PREV_HOUR dla godziny T..T+1, gdy T = znacznik i (czyli znacznik i+1)."""
    return series[i + 1] if series is not None and i + 1 < len(series) else None


def ens_prob(lat: float, lon: float, prog: float = EPS_PROG, days: int = 6, ttl: int = 900) -> dict:
    """Szansa opadu >= prog mm/h z zespolu ICON-EU-EPS (40 wariantow): {'RRRR-MM-DDTHH': 0..1} dla GODZINY HH..HH+1."""
    try:
        h = _get(ENSEMBLE, {"latitude": round(lat, 4), "longitude": round(lon, 4), "models": "icon_eu_eps", "hourly": "precipitation",
                            "forecast_days": days, "timezone": TZ_NAME}, ttl, 15).get("hourly") or {}
    except Exception:
        return {}
    mem = [k for k in h if k.startswith("precipitation")]
    out = {}
    for i, t in enumerate(h.get("time") or []):
        v = [h[k][i] for k in mem if h[k][i] is not None]
        if v:   # wartosc o T = opad z godziny PRZED T -> godzina T-1..T
            k = (dt.datetime.fromisoformat(t) - dt.timedelta(hours=1)).isoformat()[:13]
            out[k] = sum(1 for x in v if x >= prog) / len(v)
    return out
