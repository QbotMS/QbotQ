"""Temperatura 'na rowerze' dla planu trasy (decyzja Michala 2026-09-25).

Trzy poziomy (kazdy odcinek trasy z silnika meteo):
 1. prognoza  - temperatura powietrza z prognozy (temp_c odcinka),
 2. na trasie - prognoza + poprawka z kalibracji na czujniku Karoo (scripts/thermal_calibrate.py ->
                data/thermal_model.json): tam, gdzie Michal jezdzi, jest zwykle chlodniej niz w prognozie
                (popoludnie/wieczor wyraznie), niepewnosc z walidacji (p10/p90),
 3. na rowerze (DO UBIORU) - WARIANT v3 (decyzja Michala 2026-09-25): = temperatura na trasie (to, co pokazuje
                Karoo i co Michal czuje na twarzy - ped jazdy i cieplo z wysilku sie znosza) + osobista korekta
                z "W czym jechalem". Bez dodatkow za ped i slonce (v2 odejmowal ped drugi raz -> za zimno).
 4. wiatr - NIE zmienia temperatury do ubioru, decyduje o OCHRONIE OD WIATRU (wiatr_ochrona w oknie):
                "na_sobie" / "pod_reka" wg wiatru czolowego (srednia okna), wiatru 10 m, porywow i temperatury.
Wiatr NIE zmienia odczytu termometru (sprawdzone na 983 h), dziala przez ped powietrza na cialo - pkt 3.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import sqlite3

MODEL_PATH = "/opt/qbot/app/data/thermal_model.json"
GARAGE_DB = "/opt/qbot/app/data/garage.db"
FEATURES = ["stala", "sezon_sin", "sezon_cos", "doba_sin", "doba_cos", "po15_h", "po15_x_sezon",
            "zachmurzenie", "wiatr_5ms", "wiatr_kw", "wilgotnosc", "temp_20c", "predkosc"]
# awaryjnie (gdy brak pliku modelu): srednia poprawka z analizy 2026-09-25
_FALLBACK = {"coef": [-1.9] + [0.0] * (len(FEATURES) - 1), "cv": {"p10": -2.7, "p90": 2.6, "mae": 1.9},
             "n_rides": 0, "n_hours": 0, "built_at": None}
_CACHE = {"m": None, "mtime": None}
# progi ochrony od wiatru (propozycja 2026-09-25, do weryfikacji na jazdach): (czolowy_sr, wiatr_10m, porywy, temp_do)
WIND_ON = [(4.0, 8.0, 12.0, 18.0), (2.5, 5.0, 99.0, 15.0)]   # -> "na_sobie"
WIND_HAND = (2.0, 4.0, 99.0, 18.0)                           # -> "pod_reka"


def feature_vector(doy, hour_local, cloud_pct, wind10_ms, rh_pct, air_c, v_kmh):
    ang = 2 * math.pi * float(doy) / 365.25
    ha = 2 * math.pi * float(hour_local) / 24.0
    late = max(0.0, float(hour_local) - 15.0)
    w = float(wind10_ms or 0.0)
    return [1.0, math.sin(ang), math.cos(ang), math.sin(ha), math.cos(ha), late, late * math.cos(ang),
            float(cloud_pct or 0) / 100.0, w / 5.0, min(w, 8.0) ** 2 / 25.0, float(rh_pct or 60) / 100.0,
            float(air_c) / 20.0, (float(v_kmh or 20) - 20.0) / 5.0]


def model():
    try:
        mt = os.path.getmtime(MODEL_PATH)
        if _CACHE["m"] is None or _CACHE["mtime"] != mt:
            m = json.load(open(MODEL_PATH, encoding="utf-8"))
            if m.get("features") != FEATURES:
                raise ValueError("inne cechy modelu")
            _CACHE.update(m=m, mtime=mt)
        return _CACHE["m"]
    except Exception:
        return _FALLBACK


def route_delta(doy, hour_local, cloud_pct, wind10_ms, rh_pct, air_c, v_kmh):
    """Poprawka prognoza -> na trasie (C)."""
    c = model()["coef"]
    x = feature_vector(doy, hour_local, cloud_pct, wind10_ms, rh_pct, air_c, v_kmh)
    return sum(a * b for a, b in zip(c, x))


def personal_offset():
    """Osobista korekta z 'W czym jechalem': zimno -1.5, cieplo +1.5, ok 0; sciaganie do 0 (n+3); limit +-3 C.
    Waga jazdy = min(1, czas/3h) nieznana tutaj -> kazda jazda 1 (do dopracowania, gdy bedzie wiecej jazd)."""
    try:
        g = sqlite3.connect(GARAGE_DB)
        vals = [r[0] for r in g.execute("SELECT value FROM ride_gear_log WHERE slot='_odczucie'")]
        g.close()
    except Exception:
        vals = []
    s = {"zimno": -1.5, "cieplo": 1.5, "ciep\u0142o": 1.5}
    tot = sum(s.get((v or "").strip().lower(), 0.0) for v in vals)
    off = max(-3.0, min(3.0, tot / (len(vals) + 3.0)))
    return {"c": round(off, 1), "jazd": len(vals)}


def _mins(hhmm):
    try:
        h, m = [int(x) for x in str(hhmm).split(":")[:2]]
        return h * 60 + m
    except Exception:
        return None


def window_stats(segs, date_str, personal=None):
    """Statystyki okna (lista odcinkow silnika meteo) na trzech poziomach temperatury."""
    segs = [x for x in segs if x.get("temp_c") is not None]
    if not segs:
        return {}
    doy = _dt.date.fromisoformat(date_str).timetuple().tm_yday
    t0, t1 = _mins(segs[0].get("eta")), _mins(segs[-1].get("eta"))
    dkm = float(segs[-1]["km"]) - float(segs[0]["km"])
    v = (dkm / ((t1 - t0) / 60.0)) if (t0 is not None and t1 is not None and t1 > t0 and dkm > 0) else 20.0
    v = max(8.0, min(35.0, v))
    po = (personal or personal_offset())["c"]
    air, route, head, w10, gust = [], [], [], [], []
    for s_ in segs:
        hm = _mins(s_.get("eta"))
        hl = (hm / 60.0) if hm is not None else 12.0
        ta = float(s_["temp_c"])
        route.append(ta + route_delta(doy, hl, s_.get("chmury_pct"), s_.get("wind_speed_ms"), s_.get("rh_pct"), ta, v))
        air.append(ta)
        if s_.get("wind_tail_ms") is not None:
            head.append(-float(s_["wind_tail_ms"]))
        if s_.get("wind_speed_ms") is not None:
            w10.append(float(s_["wind_speed_ms"]))
        if s_.get("gust_ms") is not None:
            gust.append(float(s_["gust_ms"]))
    avg = lambda x: round(sum(x) / len(x), 1)
    na_trasie = avg(route)
    na_rowerze = round(na_trasie + po, 1)
    hs = round(max(0.0, sum(head) / len(head)), 1) if head else 0.0
    wm = round(max(w10), 1) if w10 else 0.0
    gm = round(max(gust), 1) if gust else 0.0

    def hit(th):
        return (hs >= th[0] or wm >= th[1] or gm >= th[2]) and na_rowerze < th[3]
    ochr = "na_sobie" if any(hit(t) for t in WIND_ON) else ("pod_reka" if hit(WIND_HAND) else None)
    return {"prognoza": avg(air), "na_trasie": na_trasie, "na_rowerze": na_rowerze,
            "czolowy_max": round(max(head), 1) if head else None, "czolowy_sr": hs, "wiatr_max": wm, "porywy_max": gm,
            "wiatr_ochrona": ochr, "predkosc_kmh": round(v, 1)}


def meta():
    m = model()
    return {"kalibracja_jazd": m.get("n_rides"), "kalibracja_godzin": m.get("n_hours"), "zbudowano": m.get("built_at"),
            "niepewnosc_80proc": [m["cv"].get("p10"), m["cv"].get("p90")], "sredni_blad": m["cv"].get("mae")}
