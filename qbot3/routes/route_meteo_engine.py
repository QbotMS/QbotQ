"""Silnik METEO trasy — tryby UPAŁ (WBGT) + DESZCZ + wiatr względem kierunku jazdy.

Jeden przebieg = jedno źródło prawdy. Dla każdego segmentu trasy liczy EFEKTYWNY WBGT
(z cieniem wpiętym w radiację) w momencie przejazdu (ETA z modelu czasu), porównuje go
z limitem zależnym od nachylenia (ACGIH: podjazd = wysiłek cięższy = niższy limit),
i z gęstych danych wyznacza "najgorsze ciągłe okno" -> FLAGA / ALARM. Analogicznie liczy
opad per segment (ile pada + prawdopodobieństwo) i alerty deszczu (długie moknięcie,
wjeżdżasz/wyjeżdżasz z deszczu). Z tego samego przebiegu agreguje tabelę co 30 min.

Wejścia (żywe):
- estimate_route_time_v2  -> km, ETA, grade, surface per segment (czas->miejsce->godzina),
- qbot_v2.route_frames    -> mid_lat/mid_lon per segment (gdzie pytać o pogodę),
- qbot_v2.route_shade_layer (oś 50 m) + segment_tau -> cień -> fdir_eff,
- Open-Meteo w N punktach (= N okien 30 min) -> temp, RH, wiatr, ciśnienie, radiacja, opad,
- route_weather._rel_wind -> wiatr wzdłuż/w poprzek jazdy.

Tryb burza (pioruny, NO-GO) i odczuwalne (UTCI) = jeszcze nie liczone (osobne kroki).
Progi/polityka = parametry (regulowalne), nie fizyka. Fizyka: qbot_wbgt_tools (Liljegren).

NIE wpięte do tool_registry ani promptu Alberta (najpierw walidacja silnika).
Dok.: docs/PROJEKT_METEO.md.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import urllib.parse
import urllib.request
from typing import Any, Optional

from qbot_wbgt_tools import (CZA_MIN, cos_solar_zenith, wbgt_level,
                             wbgt_liljegren_k)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TZ_NAME = "Europe/Warsaw"

# --- Model UPAŁ (ACGIH; regulowalne) ---------------------------------------
GRADE_CLIMB = 3.0          # > +3% = podjazd (wysiłek bardzo ciężki)
GRADE_DESCENT = -3.0       # < -3% = zjazd (wysiłek lekki, plus wiatr pozorny)
LIMIT_CLIMB_C = 23.0       # bardzo ciężka praca, zaaklimatyzowany (ACGIH)
LIMIT_FLAT_C = 25.0        # ciężka praca
LIMIT_DESCENT_C = 28.0     # umiarkowana/lekka
WINDOW_MIN = 30            # okno tabeli [min]

# --- Model DESZCZ (klasy opadu, regulowalne) -------------------------------
RAIN_LIGHT_MM = 2.5        # >= umiarkowany opad [mm/h]
RAIN_HEAVY_MM = 7.6        # >= silny opad [mm/h]
RAIN_WET_MM = 0.5          # od tego uznajemy, że realnie pada (moknięcie)
RAIN_PROB_MIN = 40         # [%] poniżej: nie straszymy (za mała szansa)
RAIN_TREND_MM = 0.5        # próg zmiany, by mówić że narasta/słabnie


def metabolic_limit_c(grade_pct: float) -> float:
    """Limit WBGT zależny od nachylenia (kategoria metaboliczna ACGIH)."""
    if grade_pct > GRADE_CLIMB:
        return LIMIT_CLIMB_C
    if grade_pct < GRADE_DESCENT:
        return LIMIT_DESCENT_C
    return LIMIT_FLAT_C


def window_severity(exceed_c: float, minutes: float, max_alert_level: int) -> Optional[str]:
    """Z przekroczenia limitu + długości ciągłego okna -> None / 'FLAGA' / 'ALARM'.
    Im większe przekroczenie, tym krótszy tolerowany czas (logika praca/odpoczynek ACGIH)."""
    if max_alert_level >= 4:           # strefa ekstremalna -> alarm bez względu na czas
        return "ALARM"
    if exceed_c <= 0:
        return None
    if exceed_c > 6:                   # daleko nad limitem -> natychmiast
        return "ALARM"
    if exceed_c > 4:                   # 4-6 C
        if minutes >= 15:
            return "ALARM"
        if minutes >= 7:
            return "FLAGA"
        return None
    if exceed_c > 2:                   # 2-4 C
        if minutes >= 60:
            return "ALARM"
        if minutes >= 30:
            return "FLAGA"
        return None
    # 0-2 C
    if minutes >= 120:
        return "ALARM"
    if minutes >= 45:
        return "FLAGA"
    return None


def rain_severity(max_precip_mm: float, minutes: float) -> Optional[str]:
    """Z natężenia opadu + długości ciągłego moknięcia -> None / 'FLAGA' / 'ALARM'."""
    if max_precip_mm >= RAIN_HEAVY_MM:            # silny -> alarm
        return "ALARM"
    if max_precip_mm >= RAIN_LIGHT_MM:            # umiarkowany
        return "ALARM" if minutes >= 90 else "FLAGA"
    # lekki / mżawka: dopiero długie moknięcie warte flagi (ale musi realnie padać)
    if max_precip_mm >= RAIN_WET_MM and minutes >= 60:
        return "FLAGA"
    return None


def rain_trend(first_mm: float, last_mm: float) -> str:
    """Czy w trakcie okna deszcz narasta (wjeżdżasz) czy słabnie (wychodzisz)."""
    d = last_mm - first_mm
    if d > RAIN_TREND_MM:
        return "narasta (wjeżdżasz w deszcz)"
    if d < -RAIN_TREND_MM:
        return "słabnie (wychodzisz z deszczu)"
    return "równomierny"


def _terrain_label(grade_pct: float) -> str:
    if grade_pct > GRADE_CLIMB:
        return "podjazd"
    if grade_pct < GRADE_DESCENT:
        return "zjazd"
    return "płasko"


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
    """Per ramka (len>0, w kolejności): mid_lat/mid_lon. 1:1 z profilem modelu czasu."""
    cur = conn.cursor()
    cur.execute("""SELECT frame_index, frame_len_m, mid_lat, mid_lon
                   FROM qbot_v2.route_frames WHERE route_id=%s ORDER BY frame_index""", (route_id,))
    out = []
    for r in cur.fetchall():
        if float(r[1] or 0.0) <= 0:
            continue
        out.append({"lat": float(r[2] or 0.0), "lon": float(r[3] or 0.0)})
    return out


def _load_shade(conn, route_id: str) -> list[dict]:
    """Warstwa cienia (oś 50 m) posortowana po km. Każdy wiersz: km_from/km_to + dane do segment_tau."""
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
    return shade[min(max(lo, 0), len(shade) - 1)]  # poza zakresem -> najbliższy


# --- Open-Meteo -------------------------------------------------------------
def _fetch_point(lat: float, lon: float, date_str: str, timeout: float = 15.0) -> dict:
    hourly = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m",
              "surface_pressure", "shortwave_radiation_instant", "direct_radiation_instant",
              "precipitation", "precipitation_probability"]
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


# --- Główny przebieg --------------------------------------------------------
def run_meteo_engine(route_id: str, date_str: str, start_time: str = "08:00",
                     mode: str = "normalny") -> dict:
    """Jeden przebieg silnika METEO (UPAŁ + DESZCZ + wiatr). date=YYYY-MM-DD, start=HH:MM (lokalny)."""
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
    finally:
        conn.close()

    if len(geo) != len(profile):
        return {"status": "ERROR",
                "error": f"niespójność siatek: profil {len(profile)} != ramki z geo {len(geo)}"}

    # per segment: ETA (lokalny+UTC), duracja segmentu, lat/lon
    segs = []
    prev_cum = 0.0
    for row, g in zip(profile, geo):
        cum_h = float(row.get("moving_h", 0.0)) + float(row.get("stop_h", 0.0))
        eta_local = start_local + _dt.timedelta(hours=cum_h)
        segs.append({"km": float(row["km"]), "grade_pct": float(row["grade_pct"]),
                     "surface": row.get("surface"), "lat": g["lat"], "lon": g["lon"],
                     "eta_local": eta_local, "eta_utc": eta_local.astimezone(_dt.timezone.utc),
                     "dur_min": max(0.0, (cum_h - prev_cum) * 60.0)})
        prev_cum = cum_h

    # okna 30 min -> punkty pogody (= N punktów); jeden fetch na okno
    t0 = segs[0]["eta_utc"]
    t_end = segs[-1]["eta_utc"]
    n_win = max(1, int(math.ceil((t_end - t0).total_seconds() / 60.0 / WINDOW_MIN)))
    win_centers = [t0 + _dt.timedelta(minutes=WINDOW_MIN * (i + 0.5)) for i in range(n_win)]

    def _win_idx(eta_utc):
        k = int((eta_utc - t0).total_seconds() / 60.0 // WINDOW_MIN)
        return min(max(k, 0), n_win - 1)

    # dla każdego okna: ramka najbliższa środkowi okna -> punkt pogody
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

    # per segment: efektywny WBGT + limit + opad + wiatr względny
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

        per_segment.append({
            "km": round(s["km"], 2), "eta": s["eta_local"].strftime("%H:%M"),
            "grade_pct": round(s["grade_pct"], 1), "teren": _terrain_label(s["grade_pct"]),
            "surface": s["surface"], "wbgt_eff": round(wbgt, 1), "alert_level": lvl,
            "limit": limit, "exceed": exceed, "tau": round(tau, 2),
            "opad_mm": round(prec, 1), "opad_prob": (round(prob) if prob is not None else None),
            "wind_tail_ms": round(tail, 1) if tail is not None else None,
            "wind_cross_ms": round(cross, 1) if cross is not None else None,
            "_dur_min": s["dur_min"], "_win": _win_idx(s["eta_utc"]),
        })

    alerts = _build_alerts(per_segment) + _build_rain_alerts(per_segment)
    alerts.sort(key=lambda a: a["eta_od"])
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
        "caveats": ["Limity ACGIH zakładają osobę zaaklimatyzowaną.",
                    "Wiatr pozorny rowerzysty jeszcze nie wpięty -> progi cieplne zachowawcze na płaskim/zjazdach.",
                    "Tryb burza (pioruny, NO-GO) i odczuwalne (UTCI) jeszcze nie liczone."],
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
        driver = max(run, key=lambda x: x["exceed"])     # segment napędzający zagrożenie
        peak_seg = max(run, key=lambda x: x["wbgt_eff"])  # najgorętszy (do wyświetlenia)
        powod = []
        if driver["teren"] == "podjazd":
            powod.append("podjazd")
        if driver["tau"] >= 0.9:
            powod.append("odkryte")  # pełne słońce = czynnik nasilający
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
        sev = rain_severity(max_precip, minutes)
        if not sev:
            return
        probs = [x["opad_prob"] for x in run if x["opad_prob"] is not None]
        alerts.append({
            "typ": "deszcz", "severity": sev, "km_od": run[0]["km"], "km_do": run[-1]["km"],
            "eta_od": run[0]["eta"], "eta_do": run[-1]["eta"], "minuty": round(minutes),
            "opad_max_mm": round(max_precip, 1),
            "prawdopod": (max(probs) if probs else None),
            "trend": rain_trend(run[0]["opad_mm"], run[-1]["opad_mm"]),
        })

    run = []
    for s in per_segment:
        wet = s["opad_mm"] >= RAIN_WET_MM and (s["opad_prob"] is None or s["opad_prob"] >= RAIN_PROB_MIN)
        if wet:
            run.append(s)
        else:
            flush(run)
            run = []
    flush(run)
    return alerts


def _build_table(per_segment: list[dict], n_win: int, t0: _dt.datetime) -> list[dict]:
    """Agregacja co 30 min (jedno źródło do wyświetlania). Kolumny burza/feel = placeholder."""
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
        win_start = (t0 + _dt.timedelta(minutes=WINDOW_MIN * w)).astimezone(tz)
        rows.append({
            "okno": win_start.strftime("%H:%M"),
            "km_od": b[0]["km"], "km_do": b[-1]["km"],
            "wbgt_max": wmax["wbgt_eff"], "alert_level": wmax["alert_level"],
            "wiatr_wzdluz_ms": round(sum(tails) / len(tails), 1) if tails else None,
            "opad": {"mm": round(pmax["opad_mm"], 1), "prob": (max(probs) if probs else None)},
            "burza": None, "odczuwalna": None,  # placeholdery
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
