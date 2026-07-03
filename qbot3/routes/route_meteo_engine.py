"""Silnik METEO trasy — tryby UPAŁ (WBGT) + DESZCZ + BURZA + ODCZUWALNA (Steadman) + wiatr.

Jeden przebieg = jedno źródło prawdy. Dla każdego segmentu trasy w momencie przejazdu
(ETA z modelu czasu) liczy: efektywny WBGT (cień wpięty w radiację) vs limit wg nachylenia
(ACGIH), opad (moknięcie, wjeżdżasz/wyjeżdżasz), burzę (kod=NO-GO + CAPE/porywy, z faktami
do decyzji: ile trwa + gdzie przeczekać), oraz odczuwalną temperaturę UTCI (całoroczną:
ciepło i zimno). Z gęstych danych wyznacza najgorsze ciągłe okna -> FLAGA/ALARM/NO-GO
i agreguje tabelę co 30 min.

UTCI: wejścia = temperatura powietrza, temperatura promieniowania (Tmrt~Tg z solvera kuli),
wilgotność i WIATR EFEKTYWNY = wiatr otoczenia (wektor vs kierunek jazdy) + wiatr pozorny
z prędkości jazdy (v_kmh z modelu czasu, prosto w twarz). Zakres UTCI dla wiatru 0.5..17 m/s
-> przycinamy z flagą (zwykle na szybkich zjazdach). Alerty z UTCI: tylko ZIMNO (ciepło
pokrywa WBGT). Wiatr pozorny na razie tylko do UTCI (nie do WBGT).

Wejścia (żywe): estimate_route_time_v2 (km/ETA/grade/surface/v_kmh), kanoniczna siatka 50 m
(route_segments_50m: mid_lat/mid_lon), route_shade_layer+segment_tau (cień), route_poi_layer (miejscowości),
Open-Meteo w N punktach (temp/RH/wiatr/ciśnienie/radiacja/opad/kod/CAPE/porywy).

NIE wpięte do tool_registry ani promptu Alberta. Pelna dokumentacja (kontrakt): docs/METEO_ENGINE.md. Kontekst projektu: docs/PROJEKT_METEO.md.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import urllib.parse
import urllib.request
from typing import Any, Optional

from qbot_wbgt_tools import (CZA_MIN, cos_solar_zenith, mean_radiant_temp_c,
                             wbgt_level, wbgt_liljegren_k)
from qbot3.routes.route_utci import utci_c, utci_category, apparent_temp_steadman

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TZ_NAME = "Europe/Warsaw"

# --- Model UPAŁ (ACGIH; regulowalne) ---------------------------------------
GRADE_CLIMB = 3.0
GRADE_DESCENT = -3.0
LIMIT_CLIMB_C = 23.0
LIMIT_FLAT_C = 25.0
LIMIT_DESCENT_C = 28.0
WINDOW_MIN = 30

# --- Model DESZCZ (klasy opadu, regulowalne) -------------------------------
RAIN_LIGHT_MM = 2.5
RAIN_HEAVY_MM = 7.6
RAIN_WET_MM = 0.5
RAIN_PROB_MIN = 40
RAIN_PROB_RISK = 30       # >= 30% = ryzyko deszczu (FLAGA), niezaleznie od mm
RAIN_PROB_SERIOUS = 60    # >= 60% = powazne ryzyko deszczu (ALARM)
RAIN_TREND_MM = 0.5

# --- Model BURZA (regulowalne) ---------------------------------------------
STORM_CODES = {95, 96, 99}
CAPE_MOD_J = 1000.0
CAPE_STRONG_J = 2500.0
CAPE_TREND_J = 200.0
GUST_NOTE_MS = 14.0
GUST_ALARM_MS = 17.0
_STORM_ORDER = {"FLAGA": 1, "ALARM": 2, "NO-GO": 3}
TOWN_CATEGORY = "town"

# --- Model ODCZUWALNA / ZIMNO (UTCI; regulowalne) --------------------------
UTCI_SLIGHT_COLD = 9.0      # < 9 C = lagodny stres zimna (poczatek)
UTCI_MODERATE_COLD = 0.0    # < 0 C = umiarkowany
UTCI_STRONG_COLD = -13.0    # < -13 C = silny
UTCI_VSTRONG_COLD = -27.0   # < -27 C = bardzo silny/ekstremalny
V_UTCI_MIN, V_UTCI_MAX = 0.5, 17.0  # zakres waznosci wiatru w UTCI
COLD_FLAG_C = 0.0          # srednia odczuwalna OTOCZENIA < 0 C -> FLAGA (kalibracja kolarska)
COLD_ALARM_C = -8.0        # < -8 C -> ALARM
SHELTER_FOREST = 0.4       # WorldCover 10 (las): tlumi wiatr
SHELTER_BUILT = 0.6        # WorldCover 50 (zabudowa): tlumi wiatr


def metabolic_limit_c(grade_pct: float) -> float:
    """Limit WBGT zależny od nachylenia (kategoria metaboliczna ACGIH)."""
    if grade_pct > GRADE_CLIMB:
        return LIMIT_CLIMB_C
    if grade_pct < GRADE_DESCENT:
        return LIMIT_DESCENT_C
    return LIMIT_FLAT_C


def window_severity(exceed_c: float, minutes: float, max_alert_level: int) -> Optional[str]:
    """UPAŁ: z przekroczenia limitu + długości ciągłego okna -> None / 'FLAGA' / 'ALARM'."""
    if max_alert_level >= 4:
        return "ALARM"
    if exceed_c <= 0:
        return None
    if exceed_c > 6:
        return "ALARM"
    if exceed_c > 4:
        if minutes >= 15:
            return "ALARM"
        if minutes >= 7:
            return "FLAGA"
        return None
    if exceed_c > 2:
        if minutes >= 60:
            return "ALARM"
        if minutes >= 30:
            return "FLAGA"
        return None
    if minutes >= 120:
        return "ALARM"
    if minutes >= 45:
        return "FLAGA"
    return None


def rain_severity(max_precip_mm: float, minutes: float, max_prob: Optional[float] = None) -> Optional[str]:
    """DESZCZ: z natezenia (mm) LUB prawdopodobienstwa (%) + dlugosci -> None/'FLAGA'/'ALARM'.

    Prawdopodobienstwo jest rownorzednym wyzwalaczem: mzawka/przelotne przy wysokim
    prob (niskie mm) tez ostrzega. >=60% = powazne (ALARM), >=30% = ryzyko (FLAGA).
    """
    if max_precip_mm >= RAIN_HEAVY_MM:
        return "ALARM"
    if max_prob is not None and max_prob >= RAIN_PROB_SERIOUS and minutes >= 15:
        return "ALARM"
    if max_precip_mm >= RAIN_LIGHT_MM:
        return "ALARM" if minutes >= 90 else "FLAGA"
    if max_prob is not None and max_prob >= RAIN_PROB_RISK and minutes >= 15:
        return "FLAGA"
    if max_precip_mm >= RAIN_WET_MM and minutes >= 60:
        return "FLAGA"
    return None


def storm_segment_level(weather_code: Optional[int], cape: Optional[float]) -> Optional[str]:
    """BURZA per segment: kod burzy z prognozy = NO-GO; inaczej gradacja z CAPE."""
    if weather_code is not None and int(weather_code) in STORM_CODES:
        return "NO-GO"
    if cape is None:
        return None
    if cape >= CAPE_STRONG_J:
        return "ALARM"
    if cape >= CAPE_MOD_J:
        return "FLAGA"
    return None


def cold_severity(min_utci: float, minutes: float) -> Optional[str]:
    """ZIMNO (z UTCI): z odczuwalnej + długości ciągłej ekspozycji -> None/'FLAGA'/'ALARM'."""
    if min_utci < UTCI_VSTRONG_COLD:            # bardzo silny/ekstremalny -> od razu
        return "ALARM"
    if min_utci < UTCI_STRONG_COLD:             # silny
        return "ALARM" if minutes >= 15 else "FLAGA"
    if min_utci < UTCI_MODERATE_COLD:           # umiarkowany
        if minutes >= 60:
            return "ALARM"
        if minutes >= 30:
            return "FLAGA"
        return None
    if min_utci < UTCI_SLIGHT_COLD:             # lagodny -> tylko dluga ekspozycja
        return "FLAGA" if minutes >= 60 else None
    return None


def cold_severity_cyclist(avg_utci: float, minutes: float) -> Optional[str]:
    """ZIMNO (kalibracja kolarska): ze SREDNIEJ odczuwalnej OTOCZENIA + dlugosci.

    Kolarz pedalujac produkuje 2-3x wiecej ciepla niz spacerowicz z definicji UTCI
    (135 W/m2, 2.3 MET), a wind chill slabnie w cieplym powietrzu -> prog przesuniety
    w dol: FLAGA < 0 C, ALARM < -8 C. Latem przy normalnym wietrze NIE odpala.
    """
    if avg_utci < COLD_ALARM_C and minutes >= 15:
        return "ALARM"
    if avg_utci < COLD_FLAG_C and minutes >= 30:
        return "FLAGA"
    return None


def _storm_worse(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if a is None:
        return b
    if b is None:
        return a
    return a if _STORM_ORDER.get(a, 0) >= _STORM_ORDER.get(b, 0) else b


def _trend(first: float, last: float, thr: float, up: str, down: str) -> str:
    d = last - first
    if d > thr:
        return up
    if d < -thr:
        return down
    return "równomierny"


def rain_trend(first_mm: float, last_mm: float) -> str:
    return _trend(first_mm, last_mm, RAIN_TREND_MM,
                  "narasta (wjeżdżasz w deszcz)", "słabnie (wychodzisz z deszczu)")


def _nearest_town_before(towns: list[dict], km: float) -> Optional[dict]:
    """Najbliższa miejscowość o km <= podanego (gdzie przeczekać przed burzą)."""
    best = None
    for t in towns:
        if t["km"] <= km and (best is None or t["km"] > best["km"]):
            best = t
    return best


def _terrain_label(grade_pct: float) -> str:
    if grade_pct > GRADE_CLIMB:
        return "podjazd"
    if grade_pct < GRADE_DESCENT:
        return "zjazd"
    return "płasko"


def _wind_shelter(wc_class: Optional[int]) -> float:
    """Tlumienie wiatru przez pokrycie terenu (WorldCover): las 0.4, zabudowa 0.6, reszta 1.0."""
    if wc_class == 10:
        return SHELTER_FOREST
    if wc_class == 50:
        return SHELTER_BUILT
    return 1.0


def effective_wind_ms(v_kmh: float, ws: float, tail: Optional[float],
                      cross: Optional[float]) -> float:
    """Wiatr efektywny [m/s] dla UTCI = wiatr pozorny (pęd jazdy, prosto w twarz)
    złożony z wiatrem otoczenia względem kierunku jazdy.
    tail>0 = z tyłu (zmniejsza czoło), cross = z boku. Brak heading -> pełne czoło."""
    v_ride = max(0.0, v_kmh) / 3.6
    if tail is None or cross is None:
        return v_ride + max(0.0, ws)
    return math.hypot(v_ride - tail, cross)


# --- Czas / strefa czasowa --------------------------------------------------
def _tz():
    from zoneinfo import ZoneInfo
    return ZoneInfo(TZ_NAME)


def _start_local(date_str: str, start_time: str) -> _dt.datetime:
    hh, mm = start_time.split(":")
    d = _dt.date.fromisoformat(date_str)
    return _dt.datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=_tz())


# --- DB ---------------------------------------------------------------------
def _pg_connect():
    try:
        import psycopg2 as pg  # type: ignore
    except ModuleNotFoundError:
        import psycopg as pg  # type: ignore
    return pg.connect(host=os.getenv("PGHOST", "127.0.0.1"), port=int(os.getenv("PGPORT", "5432")),
                      user=os.getenv("PGUSER", "qbot"), dbname=os.getenv("PGDATABASE", "qbot"),
                      password=os.getenv("PGPASSWORD"))


def _load_frame_geo(conn, route_id: str) -> list[dict]:
    """Per segment osi 50 m (w kolejnosci): mid_lat/mid_lon. 1:1 z profilem modelu czasu.
    Zrodlo: kanoniczny czytnik 50 m (route_segments_50m) - TA SAMA siatka co model czasu,
    zastepuje stare qbot_v2.route_frames (80 m). Param conn zachowany dla zgodnosci wywolania."""
    from qbot3.routes.route_segments_50m import load_canonical_segments_50m
    out = load_canonical_segments_50m(route_id=str(route_id))
    if out.get("status") != "OK":
        return []
    res = []
    for s in out.get("segments") or []:
        res.append({"lat": float(s.get("mid_lat") or 0.0), "lon": float(s.get("mid_lon") or 0.0)})
    return res


def _load_shade(conn, route_id: str) -> list[dict]:
    """Warstwa cienia (oś 50 m) posortowana po km. Wiersz: km_from/km_to + dane do segment_tau."""
    cur = conn.cursor()
    cur.execute("""SELECT a.km_from, a.km_to, s.heading_deg, s.class_center,
                          s.class_left_10, s.class_left_20, s.class_right_10, s.class_right_20,
                          s.coverage_status
                   FROM qbot_v2.route_shade_layer s
                   JOIN qbot_v2.route_axis_segments a USING (route_base_id, segment_index)
                   JOIN qbot_v2.route_base rb ON rb.route_base_id = s.route_base_id
                   WHERE rb.route_id=%s ORDER BY a.km_from""", (route_id,))
    out = []
    for r in cur.fetchall():
        out.append({"km_from": float(r[0] or 0.0), "km_to": float(r[1] or 0.0),
                    "heading_deg": r[2], "class_center": r[3],
                    "class_left_10": r[4], "class_left_20": r[5],
                    "class_right_10": r[6], "class_right_20": r[7],
                    "coverage_status": r[8]})
    return out


def _load_towns(conn, route_id: str) -> list[dict]:
    """Miejscowości na trasie (POI kategorii 'town') posortowane po km — gdzie przeczekać."""
    cur = conn.cursor()
    cur.execute("""SELECT p.name, p.km_on_route
                   FROM qbot_v2.route_poi_layer p
                   JOIN qbot_v2.route_base rb USING (route_base_id)
                   WHERE rb.route_id=%s AND p.category=%s AND p.km_on_route IS NOT NULL
                   ORDER BY p.km_on_route""", (route_id, TOWN_CATEGORY))
    return [{"name": r[0], "km": round(float(r[1]), 1)} for r in cur.fetchall()]


def _shade_for_km(shade: list[dict], km: float) -> Optional[dict]:
    if not shade:
        return None
    lo, hi = 0, len(shade) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        r = shade[mid]
        if km < r["km_from"]:
            hi = mid - 1
        elif km > r["km_to"]:
            lo = mid + 1
        else:
            return r
    return shade[min(max(lo, 0), len(shade) - 1)]


# --- Open-Meteo -------------------------------------------------------------
def _fetch_point(lat: float, lon: float, date_str: str, timeout: float = 15.0) -> dict:
    hourly = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m",
              "surface_pressure", "shortwave_radiation_instant", "direct_radiation_instant",
              "precipitation", "precipitation_probability", "weather_code", "cape", "wind_gusts_10m"]
    params = {"latitude": round(lat, 3), "longitude": round(lon, 3), "hourly": ",".join(hourly),
              "windspeed_unit": "ms", "timezone": "UTC", "start_date": date_str, "end_date": date_str}
    url = OPEN_METEO_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "QBot-METEO/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    h = data["hourly"]
    times = [_dt.datetime.fromisoformat(t).replace(tzinfo=_dt.timezone.utc) for t in h["time"]]
    return {"times": times, "h": h}


def _interp(times: list[_dt.datetime], vals: list, when: _dt.datetime) -> float:
    def _v(x):
        return float(x) if x is not None else 0.0
    if when <= times[0]:
        return _v(vals[0])
    if when >= times[-1]:
        return _v(vals[-1])
    for i in range(1, len(times)):
        if when <= times[i]:
            t0, t1 = times[i - 1], times[i]
            v0, v1 = _v(vals[i - 1]), _v(vals[i])
            f = (when - t0).total_seconds() / max((t1 - t0).total_seconds(), 1.0)
            return v0 + f * (v1 - v0)
    return _v(vals[-1])


def _nearest(times: list[_dt.datetime], vals: list, when: _dt.datetime):
    """Wartość kategoryczna (np. kod pogody) z najbliższej godziny — bez interpolacji."""
    i = min(range(len(times)), key=lambda k: abs((times[k] - when).total_seconds()))
    return vals[i]


def _storm_clear_after(times: list, codes: list, capes: list, when: _dt.datetime) -> Optional[_dt.datetime]:
    """Pierwsza godzina po `when`, gdy nie ma już burzy (kod poza STORM_CODES i CAPE < próg).
    None = burza trwa do końca horyzontu prognozy (nie wiadomo jak długo)."""
    for j in range(len(times)):
        if times[j] <= when:
            continue
        cj = codes[j]
        cj = int(cj) if cj is not None else None
        capej = float(capes[j]) if capes[j] is not None else 0.0
        if (cj not in STORM_CODES) and capej < CAPE_STRONG_J:
            return times[j]
    return None


# --- Główny przebieg --------------------------------------------------------
def run_meteo_engine(route_id: str, date_str: str, start_time: str = "08:00",
                     mode: str = "normalny") -> dict:
    """Jeden przebieg silnika METEO. date=YYYY-MM-DD, start=HH:MM (lokalny).

    Pelna dokumentacja (kontrakt wejscia/wyjscia): docs/METEO_ENGINE.md.
    """
    from qbot_route_time_tools import estimate_route_time_v2
    from qbot3.routes.route_shade_resolver import segment_tau
    from tools.rwgps.route_weather import _rel_wind

    start_local = _start_local(date_str, start_time)
    tt = estimate_route_time_v2(route_id=route_id, mode=mode,
                                start_time=f"{date_str}T{start_time}")
    if tt.get("status") != "OK" or not tt.get("profile"):
        return {"status": tt.get("status", "ERROR"),
                "error": tt.get("notes") or tt.get("error") or "model czasu nie zwrócił profilu"}
    profile = tt["profile"]

    conn = _pg_connect()
    try:
        geo = _load_frame_geo(conn, route_id)
        shade = _load_shade(conn, route_id)
        towns = _load_towns(conn, route_id)
    finally:
        conn.close()

    if len(geo) != len(profile):
        return {"status": "ERROR",
                "error": f"niespójność siatek: profil {len(profile)} != ramki z geo {len(geo)}"}

    segs = []
    prev_cum = 0.0
    for row, g in zip(profile, geo):
        cum_h = float(row.get("moving_h", 0.0)) + float(row.get("stop_h", 0.0))
        eta_local = start_local + _dt.timedelta(hours=cum_h)
        segs.append({"km": float(row["km"]), "grade_pct": float(row["grade_pct"]),
                     "surface": row.get("surface"), "v_kmh": float(row.get("v_kmh", 0.0)),
                     "lat": g["lat"], "lon": g["lon"],
                     "eta_local": eta_local, "eta_utc": eta_local.astimezone(_dt.timezone.utc),
                     "dur_min": max(0.0, (cum_h - prev_cum) * 60.0)})
        prev_cum = cum_h

    t0 = segs[0]["eta_utc"]
    t_end = segs[-1]["eta_utc"]
    n_win = max(1, int(math.ceil((t_end - t0).total_seconds() / 60.0 / WINDOW_MIN)))
    win_centers = [t0 + _dt.timedelta(minutes=WINDOW_MIN * (i + 0.5)) for i in range(n_win)]

    def _win_idx(eta_utc):
        k = int((eta_utc - t0).total_seconds() / 60.0 // WINDOW_MIN)
        return min(max(k, 0), n_win - 1)

    win_point = []
    for c in win_centers:
        best = min(segs, key=lambda s: abs((s["eta_utc"] - c).total_seconds()))
        win_point.append((best["lat"], best["lon"]))

    weather = []
    for (lat, lon) in win_point:
        try:
            weather.append(_fetch_point(lat, lon, date_str))
        except Exception as exc:  # noqa
            return {"status": "ERROR", "error": f"Open-Meteo nieudane: {str(exc)[:160]}"}

    per_segment = []
    for s in segs:
        wi = _win_idx(s["eta_utc"])
        h = weather[wi]["h"]
        tms = weather[wi]["times"]
        when = s["eta_utc"]
        ta = _interp(tms, h["temperature_2m"], when)
        rh = _interp(tms, h["relative_humidity_2m"], when)
        ws = _interp(tms, h["wind_speed_10m"], when)
        wd = _interp(tms, h["wind_direction_10m"], when)
        pres = _interp(tms, h["surface_pressure"], when)
        ghi = _interp(tms, h["shortwave_radiation_instant"], when)
        dir_ = _interp(tms, h["direct_radiation_instant"], when)
        prec = _interp(tms, h["precipitation"], when) if "precipitation" in h else 0.0
        prob = (_interp(tms, h["precipitation_probability"], when)
                if h.get("precipitation_probability") else None)
        wcode_raw = _nearest(tms, h["weather_code"], when) if "weather_code" in h else None
        wcode = int(wcode_raw) if wcode_raw is not None else None
        cape = _interp(tms, h["cape"], when) if "cape" in h else None
        gust = _interp(tms, h["wind_gusts_10m"], when) if "wind_gusts_10m" in h else None

        cza = cos_solar_zenith(when, s["lat"], s["lon"])
        fdir_base = (max(0.0, min(dir_ / ghi, 0.9)) if ghi > 1.0 else 0.0)
        if cza < CZA_MIN:
            fdir_base = 0.0

        sh = _shade_for_km(shade, s["km"])
        tau = segment_tau(sh, when, s["lat"], s["lon"]) if sh else 1.0
        fdir_eff = fdir_base * tau

        wbgt = float(wbgt_liljegren_k(ta + 273.15, rh, pres, ws, ghi, fdir_eff, cza)) - 273.15
        lvl = wbgt_level(wbgt)
        limit = metabolic_limit_c(s["grade_pct"])
        exceed = round(wbgt - limit, 1)

        heading = sh["heading_deg"] if sh else None
        tail, cross, _ = _rel_wind(heading, wd, ws)
        storm = storm_segment_level(wcode, cape)
        clear_utc = (_storm_clear_after(tms, h.get("weather_code", []), h.get("cape", []), when)
                     if storm else None)

        # ODCZUWALNA (UTCI): Tmrt z solvera (cień wpięty), wiatr efektywny (otoczenie + ped jazdy)
        tmrt = float(mean_radiant_temp_c(ta + 273.15, rh, pres, ws, ghi, fdir_eff, cza))
        eff = effective_wind_ms(s["v_kmh"], ws, tail, cross)
        wind_oob = eff > V_UTCI_MAX or eff < V_UTCI_MIN
        eff_c = min(max(eff, V_UTCI_MIN), V_UTCI_MAX)
        utci = utci_c(ta, tmrt, eff_c, rh)
        # ODCZUWALNA OTOCZENIA (do alertu zimna): wiatr 10 m tlumiony oslona terenu,
        # BEZ wiatru pozornego jazdy. utci (wyzej) zostaje do notki na zjazdy/postoje.
        shelter = _wind_shelter(sh["class_center"] if sh else None)
        ws_amb = min(max(ws * shelter, V_UTCI_MIN), V_UTCI_MAX)
        utci_amb = utci_c(ta, tmrt, ws_amb, rh)
        # ODCZUWALNA (headline) = Steadman + radiacja: wiatr OTOCZENIA 10 m (surowy,
        # bez oslony i bez pedu jazdy) + slonce z Tmrt (cap radiacji +8 C).
        # utci/utci_amb zostaja wylacznie do flagi zimna.
        feels = apparent_temp_steadman(ta, rh, ws, tmrt)

        per_segment.append({
            "km": round(s["km"], 2), "eta": s["eta_local"].strftime("%H:%M"),
            "grade_pct": round(s["grade_pct"], 1), "teren": _terrain_label(s["grade_pct"]),
            "surface": s["surface"], "wbgt_eff": round(wbgt, 1), "alert_level": lvl,
            "limit": limit, "exceed": exceed, "tau": round(tau, 2),
            "opad_mm": round(prec, 1), "opad_prob": (round(prob) if prob is not None else None),
            "burza": storm, "burza_kod": wcode,
            "cape": (round(cape) if cape is not None else None),
            "gust_ms": (round(gust, 1) if gust is not None else None),
            "tmrt": round(tmrt, 1), "feels": round(feels, 1),
            "utci": round(utci, 1), "utci_kat": utci_category(utci),
            "utci_amb": round(utci_amb, 1), "utci_amb_kat": utci_category(utci_amb),
            "shelter": round(shelter, 2),
            "wind_eff_ms": round(eff_c, 1), "wind_oob": wind_oob,
            "wind_dir_deg": round(wd), "wind_speed_ms": round(ws, 1),
            "wind_tail_ms": round(tail, 1) if tail is not None else None,
            "wind_cross_ms": round(cross, 1) if cross is not None else None,
            "_dur_min": s["dur_min"], "_win": _win_idx(s["eta_utc"]),
            "_eta_utc": s["eta_utc"], "_storm_clear_utc": clear_utc,
        })

    alerts = (_build_alerts(per_segment) + _build_rain_alerts(per_segment)
              + _build_storm_alerts(per_segment, towns) + _build_cold_alerts(per_segment))
    order = {"NO-GO": 0, "ALARM": 1, "FLAGA": 2}
    alerts.sort(key=lambda a: (a["eta_od"], order.get(a["severity"], 9)))
    table = _build_table(per_segment, n_win, t0)
    peak = max(per_segment, key=lambda x: x["wbgt_eff"])

    return {
        "status": "OK",
        "route_id": route_id, "date": date_str, "start": start_time, "mode": mode,
        "n_segments": len(per_segment), "n_windows": n_win,
        "peak": {"wbgt_eff": peak["wbgt_eff"], "km": peak["km"], "eta": peak["eta"],
                 "alert_level": peak["alert_level"], "teren": peak["teren"]},
        "alerts": alerts,
        "tabela_30min": table,
        "per_segment": [{k: v for k, v in s.items() if not k.startswith("_")} for s in per_segment],
        "caveats": ["Limity ACGIH (upał) zakładają osobę zaaklimatyzowaną.",
                    "WBGT liczony z wiatrem otoczenia; wiatr pozorny jazdy na razie tylko w UTCI.",
                    "Burza: 'szansa na piorun' nie jest wprost w darmowej prognozie -> kod burzy + CAPE. "
                    "Czas trwania z prognozy (kroki godzinne) = przybliżony. Miejscowość = ogólne "
                    "schronienie. Decyzję jedź/przeczekaj/odpuść podejmujesz sam.",
                    "Odczuwalna = Steadman (temperatura + wilgotnosc + wiatr 10 m + slonce z Tmrt, "
                    "cap radiacji +8 C), usredniona po oknie. UTCI sluzy WYLACZNIE do flagi ZIMNA: "
                    "prog skalibrowany pod kolarza (FLAGA <0 C, ALARM <-8 C, wiatr otoczenia z oslona "
                    "terenu, bez pedu jazdy). Wiatr pozorny jazdy NIE jest alarmem: na dlugich "
                    "zjazdach i postojach dorzuc warstwe."],
    }


def _build_alerts(per_segment: list[dict]) -> list[dict]:
    """UPAŁ: najgorsze ciągłe okna z gęstych danych (exceed>0 lub strefa ekstremalna)."""
    alerts = []

    def flush(run):
        if not run:
            return
        minutes = sum(x["_dur_min"] for x in run)
        max_exceed = max(x["exceed"] for x in run)
        max_lvl = max(x["alert_level"] for x in run)
        sev = window_severity(max_exceed, minutes, max_lvl)
        if not sev:
            return
        driver = max(run, key=lambda x: x["exceed"])
        peak_seg = max(run, key=lambda x: x["wbgt_eff"])
        powod = []
        if driver["teren"] == "podjazd":
            powod.append("podjazd")
        if driver["tau"] >= 0.9:
            powod.append("odkryte")
        alerts.append({
            "typ": "upał", "severity": sev, "km_od": run[0]["km"], "km_do": run[-1]["km"],
            "eta_od": run[0]["eta"], "eta_do": run[-1]["eta"], "minuty": round(minutes),
            "wbgt_max": peak_seg["wbgt_eff"], "alert_level": max_lvl,
            "powod": ", ".join(powod) or "upał",
        })

    run = []
    for s in per_segment:
        over = s["exceed"] > 0 or s["alert_level"] >= 4
        if over:
            run.append(s)
        else:
            flush(run)
            run = []
    flush(run)
    return alerts


def _build_rain_alerts(per_segment: list[dict]) -> list[dict]:
    """DESZCZ: ciągłe okna moknięcia (opad >= próg i prawdopodobieństwo dostateczne)."""
    alerts = []

    def flush(run):
        if not run:
            return
        minutes = sum(x["_dur_min"] for x in run)
        max_precip = max(x["opad_mm"] for x in run)
        probs = [x["opad_prob"] for x in run if x["opad_prob"] is not None]
        max_prob = max(probs) if probs else None
        sev = rain_severity(max_precip, minutes, max_prob)
        if not sev:
            return
        if max_precip < RAIN_LIGHT_MM and max_prob is not None:
            opis = f"prawdopodobienstwo do {round(max_prob)}% (mzawka/przelotne, malo mm)"
        else:
            opis = f"opad do {round(max_precip, 1)} mm" + (f", prawdop. {round(max_prob)}%" if max_prob is not None else "")
        alerts.append({
            "typ": "deszcz", "severity": sev, "km_od": run[0]["km"], "km_do": run[-1]["km"],
            "eta_od": run[0]["eta"], "eta_do": run[-1]["eta"], "minuty": round(minutes),
            "opad_max_mm": round(max_precip, 1),
            "prawdopod": (max(probs) if probs else None), "opis": opis,
            "trend": rain_trend(run[0]["opad_mm"], run[-1]["opad_mm"]),
        })

    run = []
    for s in per_segment:
        wet = (s["opad_prob"] is not None and s["opad_prob"] >= RAIN_PROB_RISK) or s["opad_mm"] >= RAIN_WET_MM
        if wet:
            run.append(s)
        else:
            flush(run)
            run = []
    flush(run)
    return alerts


def _build_storm_alerts(per_segment: list[dict], towns: list[dict]) -> list[dict]:
    """BURZA: ciągłe okna ryzyka. Przy realnej burzy (NO-GO) dokłada FAKTY do decyzji:
    ile trwa w tym miejscu (z prognozy) i w jakiej miejscowości przeczekać. Bez werdyktu jedź/nie."""
    alerts = []

    def flush(run):
        if not run:
            return
        minutes = sum(x["_dur_min"] for x in run)
        worst = None
        for x in run:
            worst = _storm_worse(worst, x["burza"])
        if not worst:
            return
        capes = [x["cape"] for x in run if x["cape"] is not None]
        gusts = [x["gust_ms"] for x in run if x["gust_ms"] is not None]
        max_gust = max(gusts) if gusts else None
        if worst == "FLAGA" and max_gust is not None and max_gust >= GUST_ALARM_MS:
            worst = "ALARM"
        kod_burzy = any(x["burza_kod"] in STORM_CODES for x in run if x["burza_kod"] is not None)
        cape_first = next((x["cape"] for x in run if x["cape"] is not None), None)
        cape_last = next((x["cape"] for x in reversed(run) if x["cape"] is not None), None)
        trend = (_trend(cape_first, cape_last, CAPE_TREND_J,
                        "narasta (wjeżdżasz w warunki burzowe)", "słabnie (wychodzisz)")
                 if cape_first is not None and cape_last is not None else None)

        alert = {
            "typ": "burza", "severity": worst, "km_od": run[0]["km"], "km_do": run[-1]["km"],
            "eta_od": run[0]["eta"], "eta_do": run[-1]["eta"], "minuty": round(minutes),
            "kod_burzy": kod_burzy, "cape_max": (max(capes) if capes else None),
            "porywy_max_ms": max_gust, "trend": trend,
            "porywy_silne": (max_gust is not None and max_gust >= GUST_NOTE_MS),
        }

        if kod_burzy:
            clears = [x["_storm_clear_utc"] for x in run]
            if all(c is not None for c in clears) and clears:
                wait = round((max(clears) - run[0]["_eta_utc"]).total_seconds() / 60.0)
                alert["czekanie_min"] = max(0, wait)
            else:
                alert["czekanie_min"] = None
            town = _nearest_town_before(towns, run[0]["km"])
            alert["przeczekaj_w"] = ({"miejscowosc": town["name"], "km": town["km"]} if town else None)

        alerts.append(alert)

    run = []
    for s in per_segment:
        if s["burza"]:
            run.append(s)
        else:
            flush(run)
            run = []
    flush(run)
    return alerts


def _build_cold_alerts(per_segment: list[dict]) -> list[dict]:
    """ZIMNO (kalibracja kolarska): okna, gdzie SREDNIA odczuwalna OTOCZENIA < 0 C.

    utci_amb = wiatr 10 m z oslona terenu, bez wiatru pozornego jazdy; usredniane po
    oknie -> nie strasi zimnem od zimnego piksela ani od pedu roweru w cieple lato.
    Wiatr pozorny (zjazdy/postoje) idzie jako notka w caveats, nie jako alarm.
    """
    alerts = []

    def flush(run):
        if not run:
            return
        minutes = sum(x["_dur_min"] for x in run)
        avg_amb = sum(x["utci_amb"] for x in run) / len(run)
        sev = cold_severity_cyclist(avg_amb, minutes)
        if not sev:
            return
        alerts.append({
            "typ": "zimno", "severity": sev, "km_od": run[0]["km"], "km_do": run[-1]["km"],
            "eta_od": run[0]["eta"], "eta_do": run[-1]["eta"], "minuty": round(minutes),
            "utci_avg": round(avg_amb, 1), "kategoria": utci_category(avg_amb),
            "opis": "srednia odczuwalna otoczenia (wiatr z oslona terenu, bez pedu jazdy)",
        })

    run = []
    for s in per_segment:
        if s["utci_amb"] < COLD_FLAG_C:
            run.append(s)
        else:
            flush(run)
            run = []
    flush(run)
    return alerts


def _build_table(per_segment: list[dict], n_win: int, t0: _dt.datetime) -> list[dict]:
    """Agregacja co 30 min (jedno źródło do wyświetlania)."""
    buckets: dict[int, list[dict]] = {}
    for s in per_segment:
        buckets.setdefault(s["_win"], []).append(s)
    rows = []
    tz = _tz()
    for w in range(n_win):
        b = buckets.get(w)
        if not b:
            continue
        wmax = max(b, key=lambda x: x["wbgt_eff"])
        tails = [x["wind_tail_ms"] for x in b if x["wind_tail_ms"] is not None]
        pmax = max(b, key=lambda x: x["opad_mm"])
        probs = [x["opad_prob"] for x in b if x["opad_prob"] is not None]
        capes = [x["cape"] for x in b if x["cape"] is not None]
        gusts = [x["gust_ms"] for x in b if x["gust_ms"] is not None]
        feels_vals = [x["feels"] for x in b]
        u_avg = sum(feels_vals) / len(feels_vals)
        storm_w = None
        for x in b:
            storm_w = _storm_worse(storm_w, x["burza"])
        win_start = (t0 + _dt.timedelta(minutes=WINDOW_MIN * w)).astimezone(tz)
        rows.append({
            "okno": win_start.strftime("%H:%M"),
            "km_od": b[0]["km"], "km_do": b[-1]["km"],
            "wbgt_max": wmax["wbgt_eff"], "alert_level": wmax["alert_level"],
            "wiatr_wzdluz_ms": round(sum(tails) / len(tails), 1) if tails else None,
            "opad": {"mm": round(pmax["opad_mm"], 1), "prob": (max(probs) if probs else None)},
            "burza": {"poziom": storm_w, "cape": (max(capes) if capes else None),
                      "porywy_ms": (max(gusts) if gusts else None)},
            "odczuwalna": {"od": round(u_avg), "do": round(u_avg), "srednia": round(u_avg)},
        })
    return rows


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else "55798129"
    date_s = sys.argv[2] if len(sys.argv) > 2 else _dt.date.today().isoformat()
    stime = sys.argv[3] if len(sys.argv) > 3 else "08:00"
    res = run_meteo_engine(rid, date_s, stime)
    print(json.dumps({k: res[k] for k in res if k != "per_segment"}, ensure_ascii=False, indent=2, default=str))
    print("per_segment[0]:", res.get("per_segment", [{}])[0])
