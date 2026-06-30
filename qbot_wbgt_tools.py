#!/usr/bin/env python3
"""QBot WBGT (Wet Bulb Globe Temperature) - obciazenie cieplne na trasie.

Zrodlo danych : Open-Meteo (darmowe, bez klucza) - jedyne z darmowa radiacja
                krotkofalowa (shortwave_radiation), ktorej OpenWeatherMap nie ma.
Model         : Liljegren et al. (2008), wariant operacyjny KNMI.
                Solver bilansu energetycznego kuli i mokrego termometru jest
                WBUDOWANY (vendored z thermofeel/ECMWF, Apache-2.0) - zaleznosci
                tylko numpy + stdlib, bez instalacji thermofeel na VPS.
Geometria     : cosinus kata zenitalnego liczony astronomicznie (NOAA).

Solver zweryfikowany bit-w-bit wzgledem thermofeel.calculate_wbgt_liljegren.
Referencja: Liljegren et al. (2008) https://doi.org/10.1080/15459620802310770
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import date as _date, datetime, timezone
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# ── Stale fizyczne (Liljegren 2008; mdljts/wbgt) ──────────────────────────
STEFANB = 5.6696e-8
CP = 1003.5
M_AIR = 28.97
M_H2O = 18.015
R_GAS = 8314.34
R_AIR = R_GAS / M_AIR
PR = CP / (CP + 1.25 * R_AIR)
RATIO = CP * M_AIR / M_H2O
EMIS_WICK = 0.95
ALB_WICK = 0.4
D_WICK = 0.007
L_WICK = 0.0254
EMIS_GLOBE = 0.95
ALB_GLOBE = 0.05
D_GLOBE = 0.0508
EMIS_SFC = 0.999
ALB_SFC = 0.45
CZA_MIN = 0.00873
MIN_SPEED = 0.13
CONVERGENCE = 0.02
MAX_ITER = 500
MIN_WIND_10M = 0.62

LSRDT = np.array([
    [1, 1, 2, 4, 0, 5, 6, 0],
    [1, 2, 3, 4, 0, 5, 6, 0],
    [2, 2, 3, 4, 0, 4, 4, 0],
    [3, 3, 4, 4, 0, 0, 0, 0],
    [3, 4, 4, 4, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0],
])
URBAN_EXP = np.array([0.15, 0.15, 0.20, 0.25, 0.30, 0.30])


def _esat(tk: ArrayLike) -> np.ndarray:
    y = (tk - 273.15) / (tk - 32.18)
    return 1.004 * 6.1121 * np.exp(17.502 * y)


def _dew_point(e: ArrayLike) -> np.ndarray:
    z = np.log(e / (6.1121 * 1.004))
    return 273.15 + 240.97 * z / (17.502 - z)


def _viscosity(tk: ArrayLike) -> np.ndarray:
    sigma = 3.617
    eps_kappa = 97.0
    tr = tk / eps_kappa
    omega = (tr - 2.9) / 0.4 * (-0.034) + 1.048
    return 2.6693e-6 * np.sqrt(M_AIR * tk) / (sigma * sigma * omega)


def _thermal_cond(tk: ArrayLike) -> np.ndarray:
    return (CP + 1.25 * R_AIR) * _viscosity(tk)


def _diffusivity(tk: ArrayLike, pair: ArrayLike) -> np.ndarray:
    pcrit_air = 36.4
    pcrit_h2o = 218.0
    tcrit_air = 132.0
    tcrit_h2o = 647.3
    a = 3.640e-4
    b = 2.334
    pcrit13 = (pcrit_air * pcrit_h2o) ** (1.0 / 3.0)
    tcrit512 = (tcrit_air * tcrit_h2o) ** (5.0 / 12.0)
    tcrit12 = np.sqrt(tcrit_air * tcrit_h2o)
    mmix = np.sqrt(1.0 / M_AIR + 1.0 / M_H2O)
    patm = pair / 1013.25
    return a * (tk / tcrit12) ** b * pcrit13 * tcrit512 * mmix / patm * 1e-4


def _evap(tk: ArrayLike) -> np.ndarray:
    return (313.15 - tk) / 30.0 * (-71100.0) + 2.4073e6


def _emis_atm(tk: ArrayLike, rh: ArrayLike) -> np.ndarray:
    e = rh * _esat(tk)
    return 0.575 * e ** 0.143


def _h_sphere_in_air(tk: ArrayLike, pair: ArrayLike, speed: ArrayLike) -> np.ndarray:
    density = pair * 100.0 / (R_AIR * tk)
    re = np.maximum(speed, MIN_SPEED) * density * D_GLOBE / _viscosity(tk)
    nu = 2.0 + 0.6 * np.sqrt(re) * PR ** 0.3333
    return nu * _thermal_cond(tk) / D_GLOBE


def _h_cylinder_in_air(tk: ArrayLike, pair: ArrayLike, speed: ArrayLike) -> np.ndarray:
    a = 0.56
    b = 0.281
    c = 0.4
    density = pair * 100.0 / (R_AIR * tk)
    re = np.maximum(speed, MIN_SPEED) * density * D_WICK / _viscosity(tk)
    nu = b * re ** (1.0 - c) * PR ** (1.0 - a)
    return nu * _thermal_cond(tk) / D_WICK


def _solve_globe(ta, rh, pair, speed, solar, fdir, cza) -> np.ndarray:
    tsfc = ta
    emis = _emis_atm(ta, rh)
    cza_safe = np.where(cza > CZA_MIN, cza, 1.0)
    beam = np.where(fdir > 0.0, fdir * (1.0 / (2.0 * cza_safe) - 1.0), 0.0)
    tg_prev = np.array(ta, dtype=float, copy=True)
    result = np.full(np.shape(ta), np.nan, dtype=float)
    converged = np.zeros(np.shape(ta), dtype=bool)
    for _ in range(MAX_ITER):
        tref = 0.5 * (tg_prev + ta)
        h = _h_sphere_in_air(tref, pair, speed)
        tg_new = (
            0.5 * (emis * ta ** 4 + EMIS_SFC * tsfc ** 4)
            - h / (STEFANB * EMIS_GLOBE) * (tg_prev - ta)
            + solar / (2.0 * STEFANB * EMIS_GLOBE)
            * (1.0 - ALB_GLOBE) * (beam + 1.0 + ALB_SFC)
        ) ** 0.25
        now = (~converged) & (np.abs(tg_new - tg_prev) < CONVERGENCE)
        result = np.where(now, tg_new - 273.15, result)
        converged = converged | now
        tg_prev = np.where(converged, tg_prev, 0.9 * tg_prev + 0.1 * tg_new)
        if converged.all():
            break
    return result


def _solve_wetbulb(ta, rh, pair, speed, solar, fdir, cza, rad) -> np.ndarray:
    tsfc = ta
    cza_safe = np.where(cza > CZA_MIN, cza, 1.0)
    sza = np.arccos(np.clip(cza_safe, -1.0, 1.0))
    emis = _emis_atm(ta, rh)
    eair = rh * _esat(ta)
    tw_prev = _dew_point(eair)
    result = np.full(np.shape(ta), np.nan, dtype=float)
    converged = np.zeros(np.shape(ta), dtype=bool)
    for _ in range(MAX_ITER):
        tref = 0.5 * (tw_prev + ta)
        h = _h_cylinder_in_air(tref, pair, speed)
        fatm = STEFANB * EMIS_WICK * (
            0.5 * (emis * ta ** 4 + EMIS_SFC * tsfc ** 4) - tw_prev ** 4
        ) + (1.0 - ALB_WICK) * solar * (
            (1.0 - fdir) * (1.0 + 0.25 * D_WICK / L_WICK)
            + fdir * ((np.tan(sza) / np.pi) + 0.25 * D_WICK / L_WICK)
            + ALB_SFC
        )
        ewick = _esat(tw_prev)
        density = pair * 100.0 / (R_AIR * tref)
        sc = _viscosity(tref) / (density * _diffusivity(tref, pair))
        tw_new = (
            ta
            - _evap(tref) / RATIO * (ewick - eair) / (pair - ewick) * (PR / sc) ** 0.56
            + (fatm / h) * rad
        )
        now = (~converged) & (np.abs(tw_new - tw_prev) < CONVERGENCE)
        result = np.where(now, tw_new - 273.15, result)
        converged = converged | now
        tw_prev = np.where(converged, tw_prev, 0.9 * tw_prev + 0.1 * tw_new)
        if converged.all():
            break
    return result


def _wind_speed_2m(va, cossza, ssrd) -> np.ndarray:
    va = np.asarray(va, dtype=float)
    cossza = np.asarray(cossza, dtype=float)
    ssrd = np.asarray(ssrd, dtype=float)
    daytime = cossza > 0.0
    col = np.where(ssrd >= 925.0, 0,
                   np.where(ssrd >= 675.0, 1, np.where(ssrd >= 175.0, 2, 3)))
    col = np.where(daytime, col, 5)
    row_day = np.where(va >= 6.0, 4,
                       np.where(va >= 5.0, 3, np.where(va >= 3.0, 2,
                                np.where(va >= 2.0, 1, 0))))
    row_night = np.where(va >= 2.5, 2, np.where(va >= 2.0, 1, 0))
    row = np.where(daytime, row_day, row_night)
    stability_class = LSRDT[row, col]
    exponent = URBAN_EXP[stability_class - 1]
    return np.maximum(va * (2.0 / 10.0) ** exponent, MIN_SPEED)


def wbgt_liljegren_k(t2_k, rh, pressure, va, ssrd, fdir, cossza) -> np.ndarray:
    """Liljegren WBGT [K]. Wejscia jak thermofeel.calculate_wbgt_liljegren."""
    t2_k = np.asarray(t2_k, dtype=float)
    rh = np.asarray(rh, dtype=float)
    pressure = np.asarray(pressure, dtype=float)
    ssrd = np.asarray(ssrd, dtype=float)
    fdir = np.asarray(fdir, dtype=float)
    cossza = np.asarray(cossza, dtype=float)

    va = np.maximum(np.asarray(va, dtype=float), MIN_WIND_10M)
    speed = _wind_speed_2m(va, cossza, ssrd)

    rh_frac = rh / 100.0
    fdir = np.clip(fdir, 0.0, 0.9)
    fdir = np.where(cossza < CZA_MIN, 0.0, fdir)

    tg_c = _solve_globe(t2_k, rh_frac, pressure, speed, ssrd, fdir, cossza)
    tnwb_c = _solve_wetbulb(t2_k, rh_frac, pressure, speed, ssrd, fdir, cossza, 1.0)
    t2_c = t2_k - 273.15
    return (0.1 * t2_c + 0.2 * tg_c + 0.7 * tnwb_c) + 273.15


# ── Geometria slonca ──────────────────────────────────────────────────────
def cos_solar_zenith(dt_utc: datetime, lat: float, lon: float) -> float:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt_utc.astimezone(timezone.utc)
    doy = dt_utc.timetuple().tm_yday
    hour = dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600
    g = 2 * math.pi / 365.0 * (doy - 1 + (hour - 12) / 24.0)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    tst = hour * 60 + eqtime + 4 * lon
    ha = math.radians(tst / 4.0 - 180.0)
    latr = math.radians(lat)
    cz = math.sin(latr) * math.sin(decl) + math.cos(latr) * math.cos(decl) * math.cos(ha)
    return max(cz, 0.0)


def solar_azimuth_deg(dt_utc: datetime, lat: float, lon: float) -> float:
    """Azymut slonca [deg], zgodnie z ruchem wskazowek od polnocy (0=N,90=E,180=S,270=W).
    Ta sama geometria NOAA co cos_solar_zenith (decl, eqtime, ha)."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt_utc.astimezone(timezone.utc)
    doy = dt_utc.timetuple().tm_yday
    hour = dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600
    g = 2 * math.pi / 365.0 * (doy - 1 + (hour - 12) / 24.0)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    tst = hour * 60 + eqtime + 4 * lon
    ha = math.radians(tst / 4.0 - 180.0)
    latr = math.radians(lat)
    sin_az = -math.sin(ha) * math.cos(decl)
    cos_az = math.cos(latr) * math.sin(decl) - math.sin(latr) * math.cos(decl) * math.cos(ha)
    return math.degrees(math.atan2(sin_az, cos_az)) % 360.0


# ── Strefy ryzyka (ACSM, pod wytrzymalosc) ─────────────────────────────────
_ZONES = [
    (18.0, "niskie",         "Brak ograniczen."),
    (23.0, "umiarkowane",    "Normalna jazda, pilnuj nawodnienia."),
    (28.0, "wysokie",        "Skroc/zwolnij, regularne picie, unikaj poludnia."),
    (32.0, "bardzo wysokie", "Mocno ogranicz wysilek, krotkie okno, cien."),
    (math.inf, "ekstremalne","Odpusc jazde na ostro - realne ryzyko udaru cieplnego."),
]


def wbgt_zone(wbgt_c: float) -> tuple[str, str]:
    for upper, label, advice in _ZONES:
        if wbgt_c < upper:
            return label, advice
    return _ZONES[-1][1], _ZONES[-1][2]


def wbgt_level(wbgt_c: float) -> int:
    """Maszynowy poziom alarmu 0-4, spojny ze strefami _ZONES.
    0=niskie, 1=umiarkowane, 2=wysokie, 3=bardzo wysokie, 4=ekstremalne.
    Lustro tej samej granicy progow co wbgt_zone (jedno zrodlo prawdy)."""
    for i, (upper, _label, _advice) in enumerate(_ZONES):
        if wbgt_c < upper:
            return i
    return len(_ZONES) - 1


# ── Open-Meteo ─────────────────────────────────────────────────────────────
def _fetch_openmeteo(lat, lon, start_date, end_date, timeout=15.0) -> dict:
    hourly = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m",
              "surface_pressure", "shortwave_radiation_instant",
              "direct_radiation_instant"]
    params = {"latitude": lat, "longitude": lon, "hourly": ",".join(hourly),
              "windspeed_unit": "ms", "timezone": "UTC"}
    if start_date:
        params["start_date"] = start_date
        params["end_date"] = end_date or start_date
    url = OPEN_METEO_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "QBot-WBGT/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def compute_wbgt_series(lat, lon, start_date=None, end_date=None,
                        ride_start=None, ride_end=None, _payload=None) -> dict:
    data = _payload if _payload is not None else _fetch_openmeteo(lat, lon, start_date, end_date)
    h = data["hourly"]
    times = h["time"]
    t2m = np.array(h["temperature_2m"], dtype=float)
    rh = np.array(h["relative_humidity_2m"], dtype=float)
    wind = np.array(h["wind_speed_10m"], dtype=float)
    pres = np.array(h["surface_pressure"], dtype=float)
    ghi = np.array(h["shortwave_radiation_instant"], dtype=float)
    dir_ = np.array(h["direct_radiation_instant"], dtype=float)

    with np.errstate(divide="ignore", invalid="ignore"):
        fdir = np.where(ghi > 1.0, np.clip(dir_ / ghi, 0.0, 1.0), 0.0)
    cossza = np.array([
        cos_solar_zenith(datetime.fromisoformat(t).replace(tzinfo=timezone.utc), lat, lon)
        for t in times], dtype=float)

    wbgt_c = wbgt_liljegren_k(t2m + 273.15, rh, pres, wind, ghi, fdir, cossza) - 273.15

    hours = []
    for i, t in enumerate(times):
        w = float(wbgt_c[i])
        if math.isnan(w):
            continue
        label, advice = wbgt_zone(w)
        hours.append({"time": t, "wbgt_c": round(w, 1), "zone": label,
                      "alert_level": wbgt_level(w), "advice": advice,
                      "t2m": round(float(t2m[i]), 1), "rh": round(float(rh[i])),
                      "wind_ms": round(float(wind[i]), 1), "ghi": round(float(ghi[i])),
                      "fdir": round(float(fdir[i]), 2)})

    window = hours
    if ride_start or ride_end:
        def _in(t):
            ts = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
            if ride_start and ts < ride_start.astimezone(timezone.utc):
                return False
            if ride_end and ts > ride_end.astimezone(timezone.utc):
                return False
            return True
        window = [x for x in hours if _in(x["time"])]

    summary = None
    if window:
        peak = max(window, key=lambda x: x["wbgt_c"])
        label, advice = wbgt_zone(peak["wbgt_c"])
        summary = {"wbgt_max": peak["wbgt_c"], "wbgt_max_time": peak["time"],
                   "zone": label, "alert_level": wbgt_level(peak["wbgt_c"]),
                   "advice": advice, "n_hours": len(window)}
    return {"hours": hours, "summary": summary}


def _format_analysis(out: dict, lat: float, lon: float) -> str:
    s = out["summary"]
    if not s:
        return "Brak danych WBGT dla zadanego punktu/okna."
    lines = [f"WBGT (obciazenie cieplne) dla {lat:.3f},{lon:.3f}:",
             f"Szczyt {s['wbgt_max']} C o {s['wbgt_max_time']} UTC "
             f"-> ryzyko {s['zone'].upper()} | {s['advice']}", "",
             "Godzinowo (UTC):"]
    for r in out["hours"]:
        lines.append(f"  {r['time'][11:]}  {r['wbgt_c']:>5} C  {r['zone']:<14} "
                     f"(T{r['t2m']} RH{r['rh']}% GHI{r['ghi']})")
    return "\n".join(lines)


def _tool_qbot_route_wbgt(args: dict[str, Any]) -> dict[str, Any]:
    """Punktowy WBGT z Open-Meteo + Liljegren. Args: lat, lon, date, from, to."""
    args = args or {}
    try:
        lat = float(args["lat"])
        lon = float(args["lon"])
    except (KeyError, TypeError, ValueError):
        return {"status": "ERROR", "error": "wymagane numeryczne lat i lon"}

    start_date = args.get("date") or None
    end_date = args.get("end") or start_date
    day = start_date or _date.today().isoformat()

    ride_start = ride_end = None
    try:
        if args.get("from"):
            ride_start = datetime.fromisoformat(f"{day}T{args['from']}").replace(tzinfo=timezone.utc)
        if args.get("to"):
            ride_end = datetime.fromisoformat(f"{day}T{args['to']}").replace(tzinfo=timezone.utc)
    except ValueError:
        return {"status": "ERROR", "error": "from/to musza byc w formacie HH:MM (UTC)"}

    try:
        out = compute_wbgt_series(lat, lon, start_date=start_date, end_date=end_date,
                                  ride_start=ride_start, ride_end=ride_end)
    except Exception as exc:
        return {"status": "ERROR", "error": f"Open-Meteo/oblczenie nieudane: {str(exc)[:200]}"}

    return {"status": "OK", "analysis": _format_analysis(out, lat, lon),
            "notes": "Model Liljegren (KNMI). Czas w UTC. Strefy: ACSM (wytrzymalosc).",
            "data": out["summary"] or {}}
