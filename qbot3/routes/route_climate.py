"""Klimatologia dnia (ERA5 przez Open-Meteo archive) — UCZCIWY zamiennik prognozy.

Do czego: gdy data wyprawy jest dalej niz siega prognoza (ok. 16 dni) albo w przeszlosci,
nie da sie podac pogody. Zamiast zmyslania podajemy KLIMAT: co statystycznie bylo w tym
miejscu i w tej czesci roku w ostatnich latach.

Metoda: dla kazdego z N ostatnich lat bierzemy okno +-K dni wokol tego samego dnia roku
(domyslnie 10 lat x +-3 dni = ok. 70 dni-obserwacji) i liczymy srednie oraz percentyle.
Zrodlo: ERA5 (reanaliza), krok dobowy + godzinowa wilgotnosc.

CZEGO TU NIE MA (swiadomie): WBGT, odczuwalna po odcinkach, burze, wiatr wzgledem kierunku
jazdy. To wymaga chwilowej radiacji, cienia i ETA — czyli prognozy. Klimat mowi CZEGO SIE
SPODZIEWAC, nie CO BEDZIE.

Nie jest wpiete do tool_registry (uzywane przez qbot_web: /api/planer/pogoda).
"""
from __future__ import annotations

import datetime as _dt
import json
import urllib.parse
import urllib.request
from typing import Optional

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
TZ_NAME = "Europe/Warsaw"
YEARS_DEFAULT = 10
WINDOW_DAYS_DEFAULT = 3
WET_DAY_MM = 1.0        # dzien "z opadem" = suma dobowa >= 1 mm

_DAILY = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
          "precipitation_sum", "precipitation_hours", "wind_speed_10m_max",
          "wind_gusts_10m_max", "shortwave_radiation_sum"]


def _pct(vals: list[float], p: float) -> Optional[float]:
    """Percentyl (metoda najblizszej rangi) — bez numpy."""
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    k = min(len(v) - 1, max(0, int(round(p / 100.0 * (len(v) - 1)))))
    return v[k]


def _avg(vals: list[float]) -> Optional[float]:
    v = [x for x in vals if x is not None]
    return (sum(v) / len(v)) if v else None


def _get(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "QBot-KLIMAT/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _target_in_year(year: int, month: int, day: int) -> _dt.date:
    """Ten sam dzien roku w innym roku; 29.02 w roku nieprzestepnym -> 28.02."""
    try:
        return _dt.date(year, month, day)
    except ValueError:
        return _dt.date(year, month, day - 1)


def climate_for_day(lat: float, lon: float, date_str: str,
                    years: int = YEARS_DEFAULT,
                    window_days: int = WINDOW_DAYS_DEFAULT,
                    timeout: float = 25.0) -> dict:
    """Klimat dla jednego punktu i jednego dnia roku. Zwraca dict ze status OK/ERROR."""
    try:
        target = _dt.date.fromisoformat(date_str[:10])
    except ValueError:
        return {"status": "ERROR", "error": "date_str musi byc RRRR-MM-DD"}

    years = max(3, min(30, int(years)))
    window_days = max(0, min(10, int(window_days)))

    # ERA5 ma opoznienie kilku dni -> ostatni pewny rok to rok poprzedni wzgledem dzisiaj
    last_year = _dt.date.today().year - 1
    year_list = [last_year - i for i in range(years)]

    tmax, tmin, tmean, psum, phours, wmax, gmax, rad, rh_all = [], [], [], [], [], [], [], [], []
    wet_days = 0
    n_days = 0
    lat_used = lon_used = None
    problems = []

    for y in year_list:
        t = _target_in_year(y, target.month, target.day)
        a = (t - _dt.timedelta(days=window_days)).isoformat()
        b = (t + _dt.timedelta(days=window_days)).isoformat()
        params = {"latitude": round(float(lat), 3), "longitude": round(float(lon), 3),
                  "start_date": a, "end_date": b,
                  "daily": ",".join(_DAILY),
                  "hourly": "relative_humidity_2m",
                  "windspeed_unit": "ms", "timezone": TZ_NAME}
        try:
            data = _get(ARCHIVE_URL + "?" + urllib.parse.urlencode(params), timeout)
        except Exception as exc:  # noqa
            problems.append("%d: %s" % (y, str(exc)[:60]))
            continue
        lat_used = data.get("latitude", lat_used)
        lon_used = data.get("longitude", lon_used)
        d = data.get("daily") or {}
        days = d.get("time") or []
        n_days += len(days)
        for i in range(len(days)):
            def _v(key):
                arr = d.get(key) or []
                return float(arr[i]) if i < len(arr) and arr[i] is not None else None
            tmax.append(_v("temperature_2m_max"))
            tmin.append(_v("temperature_2m_min"))
            tmean.append(_v("temperature_2m_mean"))
            wmax.append(_v("wind_speed_10m_max"))
            gmax.append(_v("wind_gusts_10m_max"))
            rad.append(_v("shortwave_radiation_sum"))
            phours.append(_v("precipitation_hours"))
            pv = _v("precipitation_sum")
            psum.append(pv)
            if pv is not None and pv >= WET_DAY_MM:
                wet_days += 1
        hv = ((data.get("hourly") or {}).get("relative_humidity_2m") or [])
        rh_all += [float(x) for x in hv if x is not None]

    if n_days == 0:
        return {"status": "ERROR",
                "error": "Archiwum ERA5 nie odpowiedzialo (%s)" % ("; ".join(problems)[:200] or "brak danych")}

    def _r(v, nd=1):
        return round(v, nd) if v is not None else None

    lata_ok = years - len({p.split(":")[0] for p in problems})
    return {
        "status": "OK",
        "typ": "klimat",
        "punkt": {"lat": lat_used, "lon": lon_used},
        "data": target.isoformat(),
        "podstawa": {"lata": lata_ok, "okno_dni": window_days, "obserwacji_dni": n_days,
                     "zrodlo": "ERA5 / Open-Meteo archive",
                     "braki": problems or None},
        "temp": {"max_sr": _r(_avg(tmax)), "max_p90": _r(_pct(tmax, 90)),
                 "min_sr": _r(_avg(tmin)), "min_p10": _r(_pct(tmin, 10)),
                 "sr": _r(_avg(tmean)),
                 "max_rekord": _r(max([x for x in tmax if x is not None], default=None)),
                 "min_rekord": _r(min([x for x in tmin if x is not None], default=None))},
        "rh": {"sr": _r(_avg(rh_all), 0), "p90": _r(_pct(rh_all, 90), 0)},
        "opad": {"mm_dobowe_sr": _r(_avg(psum)), "mm_dobowe_p90": _r(_pct(psum, 90)),
                 "szansa_dnia_z_opadem_pct": round(100.0 * wet_days / n_days),
                 "godzin_opadu_sr": _r(_avg(phours))},
        "wiatr": {"max_dobowy_sr_ms": _r(_avg(wmax)), "max_dobowy_p90_ms": _r(_pct(wmax, 90)),
                  "porywy_p90_ms": _r(_pct(gmax, 90))},
        "slonce": {"radiacja_mj_sr": _r(_avg(rad))},
        "uwagi": [
            "To KLIMAT (ERA5, ostatnie %d lat, okno +-%d dni), nie prognoza tego dnia." % (lata_ok, window_days),
            "Prognoza pogody siega ok. 16 dni — dalej nie da sie przewidziec konkretnego dnia.",
            "Brak WBGT, burz i wiatru wzgledem kierunku jazdy — te licza sie tylko z prognozy.",
            "p90 = wartosc przekraczana w co dziesiatym takim dniu (scenariusz niekorzystny).",
        ],
    }


if __name__ == "__main__":
    import sys
    la = float(sys.argv[1]) if len(sys.argv) > 1 else 52.23
    lo = float(sys.argv[2]) if len(sys.argv) > 2 else 21.01
    ds = sys.argv[3] if len(sys.argv) > 3 else (_dt.date.today() + _dt.timedelta(days=60)).isoformat()
    print(json.dumps(climate_for_day(la, lo, ds), ensure_ascii=False, indent=2))
