# -*- coding: utf-8 -*-
"""Profile jazd dla modelu czasu przejazdu (2026-10-19, decyzje Michala). Dok.: docs/RIDE_PROFILES.md

Zasada (sprawdzona na 311 pelnych jazdach, walidacja na ostatnich 120 dniach):
- TEMPO W RUCHU = tabela config/speed_model.json (rekalibracja z ostatnich 120 dni) dla WSZYSTKICH profili --
  profile tempa (dluga wolniej itd.) z historii POGARSZALY wynik, wiec ich nie ma.
  Wyjatki: odcinki w zabudowie (ESA WorldCover klasa 50) x profiles.city.speed_factor; bikepacking x bikepacking_speed_factor.
- PROFIL ZMIENIA POSTOJE (brutto): mikro [min/km] + krotkie [min/h ruchu] od pierwszego km (bez "darmowej godziny"),
  liczone z ostatnich 365 dni. Dlugie postoje (>= 20 min: obiad, zwiedzanie) nadal deklaruje uzytkownik.
- Profil planowanej trasy (choose_profile): bagaz -> bikepacking; >= 50% w zabudowie -> miasto; czas ruchu >= p75 jazd
  z tego miesiaca (min 2 h) -> dluga; start daleko od domu (wakacje) -> krotka (liczy sie tylko dlugosc);
  dzien roboczy -> trening; weekend -> krotka. Uzytkownik moze podac profil recznie.
- Klasyfikacja historii (classify_rides, do rekalibracji): bikepacking = ciag dni A->B (meta dnia N = start dnia N+1,
  poza domem); miasto = dom<->centrum A->B albo >= 40% jazdy w centrum Warszawy w dzien roboczy; dluga = czas ruchu
  >= p75 jazd z +-30 dni roku (min 2 h); poza domem bez bagazu: tylko dlugosc; reszta pn-pt trening, sb-nd krotka.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

PROFILES = ("trening", "krotka_weekend", "dluga", "miasto", "bikepacking")
LABELS = {"trening": "trening tygodniowy", "krotka_weekend": "krótka weekendowa", "dluga": "długa",
          "miasto": "miasto", "bikepacking": "bikepacking"}
CITY_CORE = (52.17, 52.30, 20.90, 21.12)   # centrum Warszawy (lat_min, lat_max, lon_min, lon_max) -- tylko historia


def dist_km(a, b) -> float:
    la = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(la))


def _as_date(d) -> date:
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


# ------------------------------------------------------------------ planowana trasa
def choose_profile(prof_cfg: dict, *, moving_h: float, ride_date=None, start=None,
                   city_share: Optional[float] = None, bikepacking: bool = False) -> tuple[str, str]:
    """(profil, powod po polsku). prof_cfg = speed_model.json['profiles']."""
    if bikepacking:
        return "bikepacking", "jazda z bagażem"
    city = prof_cfg.get("city") or {}
    if city_share is not None and city_share >= float(city.get("profile_min_share", 0.5)):
        return "miasto", "%d%% trasy w zabudowie" % round(city_share * 100)
    rules = prof_cfg.get("rules") or {}
    d = _as_date(ride_date) if ride_date else date.today()
    p75 = float((rules.get("p75_moving_h_by_month") or {}).get(str(d.month), 3.0))
    thr = max(p75, float(rules.get("min_h", 2.0)))
    if moving_h >= thr:
        return "dluga", "ok. %.1f h ruchu – w tej porze roku to jedna z Twoich dłuższych jazd (próg %.1f h)" % (moving_h, thr)
    home = rules.get("home")
    if start and home and dist_km(start, home) > float(rules.get("away_km", 60)):
        return "krotka_weekend", "wyjazd poza dom – liczy się tylko długość"
    if d.isoweekday() <= 5:
        return "trening", "dzień roboczy, krótsza jazda"
    return "krotka_weekend", "weekend, krótsza jazda"


def stops_for(speed_model: dict, profile: str, *, km: float, moving_h: float, city_km: float = 0.0) -> dict:
    """Postoje modelowane (bez dlugich) dla profilu: {'mikro_min','krotkie_min','city_extra_min'}."""
    prof_cfg = speed_model.get("profiles") or {}
    if profile == "bikepacking":
        p = speed_model["stops"]["bikepacking"]
        micro = float(p["micro_min_per_km"]) * km
        short = float(p["short_min_per_h"]) * max(0.0, moving_h - float(p.get("free_h", 0.0)))
    else:
        p = (prof_cfg.get("stops") or {}).get(profile)
        if not p:   # brak profilu w konfiguracji -> dawny wzor 'normal'
            p0 = speed_model["stops"]["normal"]
            micro = float(p0["micro_min_per_km"]) * km
            short = float(p0["short_min_per_h"]) * max(0.0, moving_h - float(p0["free_h"]))
        else:
            micro = float(p["micro_min_per_km"]) * km
            short = float(p["short_min_per_h"]) * moving_h
    extra = 0.0
    if profile not in ("miasto", "bikepacking") and city_km > 0:
        extra = float((prof_cfg.get("city") or {}).get("extra_micro_min_per_km", 0.0)) * city_km
    return {"mikro_min": micro + extra, "krotkie_min": short, "city_extra_min": extra}


# ------------------------------------------------------------------ historia (rekalibracja)
FEATURE_SQL = """
WITH p AS (SELECT sec, lat, lon FROM qbot_v2.activity_record WHERE external_id=%s)
SELECT (SELECT lat FROM p WHERE lat IS NOT NULL ORDER BY sec LIMIT 1), (SELECT lon FROM p WHERE lat IS NOT NULL ORDER BY sec LIMIT 1),
       (SELECT lat FROM p WHERE lat IS NOT NULL ORDER BY sec DESC LIMIT 1), (SELECT lon FROM p WHERE lat IS NOT NULL ORDER BY sec DESC LIMIT 1),
       (SELECT count(*) FILTER (WHERE lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s)::float / NULLIF(count(lat),0) FROM p)
"""


def ride_features(cur, external_id) -> Optional[dict]:
    """Start/meta i udzial centrum z zapisu 1 Hz (kursor psycopg, krotki odczyt)."""
    cur.execute(FEATURE_SQL, (external_id,) + CITY_CORE)
    r = cur.fetchone()
    if not r or r[0] is None:
        return None
    return {"start": (float(r[0]), float(r[1])), "end": (float(r[2]), float(r[3])), "city_core": float(r[4] or 0.0)}


def classify_rides(rides: list[dict], home, away_km: float = 60.0) -> dict:
    """rides: [{id, date, km, mov_h, start, end, city_core}] -> {id: profil}. Patrz opis modulu."""
    by_day: dict = {}
    for r in rides:
        r["_d"] = _as_date(r["date"])
        r["_home0"] = dist_km(r["start"], home) if r.get("start") else 0.0
        r["_home1"] = dist_km(r["end"], home) if r.get("end") else 0.0
        r["_ab"] = dist_km(r["start"], r["end"]) if r.get("start") and r.get("end") else 0.0
        by_day.setdefault(r["_d"], []).append(r)
    # bikepacking: ciag dni A->B
    bp, seq = set(), []
    stage = lambda r: r.get("start") and r["_ab"] > 10 and min(r["_home0"], r["_home1"]) > 30
    def close(s):
        if len(s) >= 2:
            bp.update(x["id"] for x in s)
    for d in sorted(by_day):
        st = [x for x in by_day[d] if stage(x)]
        if not st:
            close(seq); seq = []; continue
        x = st[0]
        if seq and d - seq[-1]["_d"] == timedelta(days=1) and dist_km(seq[-1]["end"], x["start"]) < 5:
            seq.append(x)
        else:
            close(seq); seq = [x]
    close(seq)
    out = {}
    for r in rides:
        core = r.get("city_core") or 0.0
        if r["id"] in bp:
            out[r["id"]] = "bikepacking"
        elif r.get("start") and r["_ab"] > 3 and min(r["_home0"], r["_home1"]) < 1.0 and core >= 0.3:
            out[r["id"]] = "miasto"          # dojazd dom <-> centrum
        elif core >= 0.4 and r["_d"].isoweekday() <= 5:
            out[r["id"]] = "miasto"
    base = [r for r in rides if r["id"] not in out]
    for r in base:
        doy = r["_d"].timetuple().tm_yday
        win = sorted(x["mov_h"] for x in base
                     if min(abs(x["_d"].timetuple().tm_yday - doy), 365 - abs(x["_d"].timetuple().tm_yday - doy)) <= 30)
        p75 = win[int(0.75 * (len(win) - 1))] if len(win) >= 6 else 3.0
        away = min(r["_home0"], r["_home1"]) > away_km
        if r["mov_h"] >= max(p75, 2.0):
            out[r["id"]] = "dluga"
        elif away or r["_d"].isoweekday() >= 6:
            out[r["id"]] = "krotka_weekend"
        else:
            out[r["id"]] = "trening"
    return out


def p75_by_month(rides: list[dict], classes: dict) -> dict:
    """p75 czasu ruchu jazd (bez miasta i bikepackingu) z +-30 dni roku, dla 15. dnia kazdego miesiaca."""
    base = [r for r in rides if classes.get(r["id"]) in ("dluga", "krotka_weekend", "trening")]
    out = {}
    for m in range(1, 13):
        mid = date(2025, m, 15).timetuple().tm_yday
        w = sorted(r["mov_h"] for r in base
                   if min(abs(_as_date(r["date"]).timetuple().tm_yday - mid), 365 - abs(_as_date(r["date"]).timetuple().tm_yday - mid)) <= 30)
        out[str(m)] = round(w[int(0.75 * (len(w) - 1))], 2) if len(w) >= 6 else 3.0
    return out


def fit_stops(rows: list[dict], classes: dict, min_rides: int = 8) -> dict:
    """rows: [{id, km, mov_h, mikro, krotkie}] -> {profil: {micro_min_per_km, short_min_per_h, free_h, rides}}."""
    out = {}
    for p in ("trening", "krotka_weekend", "dluga", "miasto"):
        rs = [r for r in rows if classes.get(r["id"]) == p and r.get("mov_h")]
        if len(rs) < min_rides:
            continue
        out[p] = {"micro_min_per_km": round(sum(r["mikro"] for r in rs) / sum(r["km"] for r in rs), 3),
                  "short_min_per_h": round(sum(r["krotkie"] for r in rs) / sum(r["mov_h"] for r in rs), 2),
                  "free_h": 0.0, "rides": len(rs)}
    return out
