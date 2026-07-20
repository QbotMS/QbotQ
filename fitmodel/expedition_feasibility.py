from __future__ import annotations

"""Silnik wykonalnosci wyprawy (Planer Wypraw) -- MODEL DWOCH SCIAN (2026-07-20).

Cel: ocenic, na ile wielodniowy podzial wyprawy jest wykonalny. STARY werdykt stal
na progu swiezosci TSB (p05 z historii) -- odrzucony: realnie UKONCZONY blok
(Toskania 7 dni, XSS 179/294/242/149/208/246/186) dostawalby "nie jedz", bo TSB
schodzi glęboko na kazdej wielodniowce. TSB nie jest miara wykonalnosci wielodniowki.

WYKONALNOSC = dwie fizyczne SCIANY, liczy sie ta ktora uderzy pierwsza:
- SCIANA 1-DNIA: rekord demonstrowany (max pojedyncza jazda, modelq2_ride.xss_total)
  oraz sciana metaboliczna (3.5xBMR - NONEX) / kcal_per_XSS = limit wchlaniania jelit.
- SUFIT TYGODNIOWY (srednia/dzien): (3.0xBMR - NONEX)/kcal_per_XSS.
- SUFIT WIELOTYGODNIOWY: (2.5xBMR - NONEX)/kcal_per_XSS.
Mnoznik xBMR = limit WCHLANIANIA (uniwersalny), NIE galka wytrenowania -- nie podkrecac
za forme. Wytrenowanie wchodzi przez sklad ciala (BMR), glikogen i DEMONSTROWANA POJEMNOSC.

Narastajace zmeczenie (symulacja TSB) = INFORMACJA obok werdyktu, nie pass/fail.
BMR = Mifflin-St Jeor z qbot_v2.athlete_profile (sex/wzrost/rok ur.) + biezaca waga.

WALUTA: XSS. XSS etapu z fizyki trasy (route_xss_phys._route_physics_xss).
Czesc czysta (bez DB) testowalna offline. Czesc "na zywo" czyta fitmodel_daily /
athlete_profile / modelq2_ride przez fitmodel.api._db_connect.
"""

import math
from datetime import date as _date, timedelta as _timedelta
from typing import Any, Optional

TAU_CTL = 42.0
TAU_ATL = 7.0
TSB_YELLOW = -20.0             # fallback podrecznikowy (info)
TSB_RED = -30.0               # fallback podrecznikowy (info)
SAFE_CTL_RAMP_PER_WEEK = 6.0   # (legacy, nieuzywane w werdykcie dwoch scian)
_K_CTL = 1.0 - math.exp(-1.0 / TAU_CTL)
_K_ATL = 1.0 - math.exp(-1.0 / TAU_ATL)

# --- kotwice modelu dwoch scian (z DECISIONS/CURRENT 2026-07-20) ---
KCAL_PER_XSS = 9.3            # mediana dlugich jazd (kcal na 1 XSS)
NONEX_MULT = 1.4             # TEE poza jazda = 1.4 x BMR
CEIL_DAY_MULT = 3.5         # sciana metaboliczna 1-dnia (izolowany dzien)
CEIL_WEEK_MULT = 3.0        # srednia/dzien - tydzien
CEIL_MULTIWEEK_MULT = 2.5   # srednia/dzien - wielotygodniowa


# ---- CZESC CZYSTA (testowalna offline) ------------------------------------

def ctl_trend_slope(ctl_series):
    """Nachylenie CTL (XSS/dzien) z regresji liniowej po serii (dzien, ctl).
    ctl_series: lista (idx_dnia:int, ctl:float) LUB lista samych ctl (kolejno).
    Zwraca slope (XSS/dzien) albo 0.0 gdy za malo danych."""
    pts = []
    for i, v in enumerate(ctl_series):
        if isinstance(v, (tuple, list)):
            x, y = float(v[0]), v[1]
        else:
            x, y = float(i), v
        if y is None:
            continue
        pts.append((x, float(y)))
    n = len(pts)
    if n < 3:
        return 0.0
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    num = sum((p[0] - mx) * (p[1] - my) for p in pts)
    den = sum((p[0] - mx) ** 2 for p in pts)
    if den == 0:
        return 0.0
    return num / den


def percentile(sorted_vals, p):
    """Percentyl p (0-100) z posortowanej listy. None gdy pusto."""
    if not sorted_vals:
        return None
    i = max(0, min(len(sorted_vals) - 1, int(round(p / 100.0 * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def project_ctl(today_ctl, slope_per_day, days_ahead, cap_ramp_per_week=SAFE_CTL_RAMP_PER_WEEK):
    """Rzutuje CTL do przodu wg trendu, przycinajac tempo WZROSTU do bezpiecznego.
    Dodatni trend ograniczony do cap_ramp/7 na dzien; spadek dozwolony bez ograniczenia."""
    if today_ctl is None:
        return None
    cap_day = cap_ramp_per_week / 7.0
    s = float(slope_per_day)
    if s > cap_day:
        s = cap_day
    proj = float(today_ctl) + s * max(0, int(days_ahead))
    return max(0.0, proj)


def simulate_expedition(start_ctl, start_atl, stage_xss_list, yellow=TSB_YELLOW, red=TSB_RED):
    """Forward-symulacja dzien po dniu (INFORMACJA o narastajacym zmeczeniu, nie werdykt).

    KOLEJNOSC (fix 2026-07-20): najpierw NOCNA/miedzydniowa regeneracja (decay EWMA
    ku 0), POTEM odczyt porannego TSB, POTEM obciazenie dnia. Koniec dnia identyczny
    jak przy jednokrokowym EWMA, ale poranny TSB nie jest zawyzony o niezregenerowane
    ATL. Dowod: Toskania min TSB -64 (stara kolejnosc) -> ~-47 (poprawna)."""
    ctl = float(start_ctl or 0.0)
    atl = float(start_atl if start_atl is not None else start_ctl or 0.0)
    days = []
    min_tsb = None
    for i, xss in enumerate(stage_xss_list):
        load = float(xss or 0.0)
        # 1) regeneracja przed rankiem (obciazenie nocy = 0 -> czysty decay)
        ctl = ctl * (1.0 - _K_CTL)
        atl = atl * (1.0 - _K_ATL)
        # 2) poranny TSB (swiezosc, z ktora zaczynasz dzien)
        tsb_morning = ctl - atl
        # 3) obciazenie dnia (dopelnienie EWMA -> koniec dnia == jednokrokowe EWMA)
        ctl = ctl + load * _K_CTL
        atl = atl + load * _K_ATL
        if min_tsb is None or tsb_morning < min_tsb:
            min_tsb = tsb_morning
        if tsb_morning < red:
            color = "red"
        elif tsb_morning < yellow:
            color = "yellow"
        else:
            color = "green"
        days.append({
            "idx": i, "xss": round(load, 1), "tsb_morning": round(tsb_morning, 1),
            "ctl_after": round(ctl, 1), "atl_after": round(atl, 1), "color": color,
        })
    return {"days": days, "min_tsb": (round(min_tsb, 1) if min_tsb is not None else None),
            "tsb_end": round(ctl - atl, 1)}


def min_start_ctl_feasible(stage_xss_list, red=TSB_RED):
    """(legacy, nieuzywane w werdykcie dwoch scian) Najmniejsze startowe CTL, przy
    ktorym min. poranny TSB nie schodzi ponizej 'red'. Zostawione dla zgodnosci."""
    if not stage_xss_list:
        return (0.0, 0.0)
    hi = max(float(x or 0.0) for x in stage_xss_list) * 2.0 + 10.0
    lo = 0.0
    for _ in range(40):
        mid = (lo + hi) / 2.0
        sim = simulate_expedition(mid, mid, stage_xss_list, yellow=red, red=red)
        if sim["min_tsb"] is not None and sim["min_tsb"] >= red:
            hi = mid
        else:
            lo = mid
    sim = simulate_expedition(hi, hi, stage_xss_list, yellow=red, red=red)
    return (round(hi, 1), sim["min_tsb"])


def required_weekly_ramp(projected_ctl, ctl_needed, weeks_to_departure):
    """(legacy, nieuzywane) Ile XSS/tydzien dolozyc, by dobic ctl_needed."""
    gap = float(ctl_needed) - float(projected_ctl)
    weeks = max(0.1, float(weeks_to_departure))
    ramp_per_week = gap / weeks if gap > 0 else 0.0
    extra_weekly_xss = ramp_per_week * 7.0 if ramp_per_week > 0 else 0.0
    safe = ramp_per_week <= SAFE_CTL_RAMP_PER_WEEK + 1e-9
    return {"gap_ctl": round(gap, 1), "ramp_per_week": round(ramp_per_week, 1),
            "extra_weekly_xss": round(extra_weekly_xss, 0), "safe": bool(safe),
            "safe_cap_per_week": SAFE_CTL_RAMP_PER_WEEK}


def verdict_text(sim, projected_ctl, ctl_needed, ramp, weeks, yellow=TSB_YELLOW, red=TSB_RED):
    """(legacy, fallback gdy brak BMR/scian) Jedno zdanie wg progu TSB."""
    min_tsb = sim["min_tsb"]
    if min_tsb is not None and min_tsb >= yellow:
        return ("Wyprawa wyglada na wykonalna przy obecnej formie -- TSB nie schodzi "
                "w Twoja strefe zmeczenia (ponizej %.0f)." % yellow)
    if min_tsb is not None and min_tsb >= red:
        return ("Wyprawa na granicy: TSB spada do %.0f. Do zniesienia, ale zaplanuj "
                "lzejszy dzien lub dodatkowy nocleg." % min_tsb)
    return ("Ciezki plan: TSB spadloby do %.0f. Narastajace zmeczenie -- rozwaz "
            "lzejszy dzien." % (min_tsb if min_tsb is not None else 0.0))


# --- MODEL DWOCH SCIAN (czyste) ---

def mifflin_bmr(weight_kg, height_cm, age_years, sex="M"):
    """BMR wg Mifflin-St Jeor [kcal/d]. sex 'M'/'K'."""
    base = 10.0 * float(weight_kg) + 6.25 * float(height_cm) - 5.0 * float(age_years)
    return base + (5.0 if str(sex or "M").upper().startswith("M") else -161.0)


def compute_ceilings(bmr, demonstrated_max):
    """Cztery kotwice XSS z BMR + demonstrowany rekord dnia. None gdy brak BMR."""
    if not bmr:
        return None
    nonex = NONEX_MULT * float(bmr)

    def _ceil(mult):
        return round((mult * float(bmr) - nonex) / KCAL_PER_XSS, 0)

    return {
        "bmr": round(float(bmr), 0),
        "kcal_per_xss": KCAL_PER_XSS,
        "day_metabolic": _ceil(CEIL_DAY_MULT),
        "week_avg": _ceil(CEIL_WEEK_MULT),
        "multiweek_avg": _ceil(CEIL_MULTIWEEK_MULT),
        "day_demonstrated": (round(float(demonstrated_max), 0) if demonstrated_max else None),
    }


def day_wall(xss, ceilings):
    """Kolor dnia wg scian: red = powyzej sciany metabolicznej 1-dnia; yellow =
    powyzej demonstrowanego rekordu (ale ponizej metabolicznej); green = w normie."""
    x = float(xss or 0.0)
    met = ceilings.get("day_metabolic") if ceilings else None
    dem = ceilings.get("day_demonstrated") if ceilings else None
    if met is not None and x > met:
        return "red", "powyzej sciany 1-dnia"
    if dem is not None and x > dem:
        return "yellow", "powyzej rekordu dnia"
    return "green", "w normie"


def verdict_two_walls(stage_xss_list, ceilings, min_tsb=None):
    """Werdykt tekstowy modelu dwoch scian (po polsku, 2-4 zdania)."""
    n = len(stage_xss_list)
    if n == 0 or not ceilings:
        return "Brak danych do oceny scian."
    xs = [float(x or 0.0) for x in stage_xss_list]
    avg = sum(xs) / n
    met = ceilings.get("day_metabolic")
    dem = ceilings.get("day_demonstrated")
    wk = ceilings.get("week_avg")
    mw = ceilings.get("multiweek_avg")
    reds = [i + 1 for i, x in enumerate(xs) if met is not None and x > met]
    yellows = [i + 1 for i, x in enumerate(xs) if met is not None and dem is not None and dem < x <= met]

    if reds:
        head = "Plan przeladowany."
    elif yellows:
        head = "Plan ambitny, ale w granicach."
    else:
        head = "Plan wykonalny."

    parts = [head]
    if reds:
        dni = ", ".join(str(i) for i in reds)
        parts.append("Dzien %s przebija sciane 1-dnia (~%.0f XSS = limit wchlaniania jelit) -- "
                      "podziel ten dzien." % (dni, met))
    if yellows:
        dni = ", ".join(str(i) for i in yellows)
        parts.append("Dzien %s powyzej Twojego rekordu dnia (%.0f), ale ponizej sciany "
                      "metabolicznej -- da sie, trzymaj tempo i dojadaj." % (dni, dem))
    if wk is not None and avg > wk:
        parts.append("Srednia %.0f/dzien przewyzsza Twoj sufit tygodniowy (~%.0f) -- przy "
                     "dluzszym bloku dlug glikogenowy narasta." % (avg, wk))
    elif n >= 7 and mw is not None and avg > mw:
        parts.append("Srednia %.0f/dzien OK na tydzien, ale powyzej sufitu wielotygodniowego "
                     "(~%.0f) -- nie przedluzaj bez dnia lzejszego." % (avg, mw))
    elif wk is not None:
        parts.append("Srednia %.0f/dzien miesci sie w suficie tygodniowym (~%.0f)." % (avg, wk))
    if min_tsb is not None:
        parts.append("Narastajace zmeczenie: min. poranny TSB ~%.0f (informacja, nie stop)." % min_tsb)
    return " ".join(parts)


# ---- CZESC NA ZYWO (DB) ---------------------------------------------------

def _rget(r, key, idx):
    try:
        return r[key]
    except Exception:
        try:
            return r[idx]
        except Exception:
            return None


def load_tsb_thresholds(conn, today=None, window_days=365, min_days=60):
    """Progi TSB z historii (info do symulacji): zolty=p10, czerwony=p05 tsb_raw."""
    end = today or _date.today()
    start = end - _timedelta(days=window_days)
    rows = conn.execute(
        "SELECT tsb_raw FROM qbot_v2.fitmodel_daily "
        "WHERE day BETWEEN %s AND %s AND tsb_raw IS NOT NULL",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    vals = sorted(float(_rget(r, "tsb_raw", 0)) for r in rows if _rget(r, "tsb_raw", 0) is not None)
    if len(vals) < min_days:
        return {"yellow": TSB_YELLOW, "red": TSB_RED,
                "source": "domyslne podrecznikowe (za malo historii)", "n": len(vals)}
    return {"yellow": round(percentile(vals, 10)), "red": round(percentile(vals, 5)),
            "source": "z Twojej historii (p10 / p05)", "n": len(vals)}


def load_form_context(conn, today=None, lookback_days=30):
    """Dzisiejsze CTL/ATL/TSB + trend z ostatnich lookback_days. None gdy brak CTL."""
    end = today or _date.today()
    start = end - _timedelta(days=lookback_days)
    rows = conn.execute(
        "SELECT day, ctl_xss, atl_raw, tsb_raw FROM qbot_v2.fitmodel_daily "
        "WHERE day BETWEEN %s AND %s AND ctl_xss IS NOT NULL ORDER BY day",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    if not rows:
        return None
    series = []
    base = None
    for r in rows:
        d = _rget(r, "day", 0)
        c = _rget(r, "ctl_xss", 1)
        if base is None:
            base = d
        series.append(((d - base).days, float(c) if c is not None else None))
    last = rows[-1]
    today_ctl = float(_rget(last, "ctl_xss", 1))
    atl = _rget(last, "atl_raw", 2)
    tsb = _rget(last, "tsb_raw", 3)
    slope = ctl_trend_slope(series)
    return {
        "as_of": _rget(last, "day", 0).isoformat(),
        "ctl": round(today_ctl, 1),
        "atl": (round(float(atl), 1) if atl is not None else None),
        "tsb": (round(float(tsb), 1) if tsb is not None else None),
        "slope_per_day": round(slope, 3),
        "n_days": len(series),
    }


def load_athlete_bmr(conn, today=None):
    """BMR (Mifflin) z athlete_profile (sex/wzrost/rok ur.) + biezaca waga
    (fitmodel_daily.weight_kg). None gdy brak profilu/wagi."""
    today = today or _date.today()
    try:
        prof = conn.execute(
            "SELECT sex, height_cm, birth_year FROM qbot_v2.athlete_profile WHERE id=1").fetchone()
    except Exception:
        prof = None
    if not prof:
        return None
    sex = _rget(prof, "sex", 0)
    height = _rget(prof, "height_cm", 1)
    byear = _rget(prof, "birth_year", 2)
    try:
        wr = conn.execute(
            "SELECT weight_kg FROM qbot_v2.fitmodel_daily "
            "WHERE weight_kg IS NOT NULL ORDER BY day DESC LIMIT 1").fetchone()
    except Exception:
        wr = None
    weight = _rget(wr, "weight_kg", 0) if wr else None
    if not (height and byear and weight):
        return None
    age = today.year - int(byear)
    bmr = mifflin_bmr(float(weight), float(height), age, sex)
    return {"bmr": round(bmr, 0), "weight_kg": round(float(weight), 1),
            "height_cm": float(height), "age": age, "sex": sex}


def load_demonstrated_max_day(conn):
    """Najwiekszy XSS pojedynczej jazdy (modelq2_ride.xss_total) = demonstrowany
    rekord 1-dnia. None gdy brak."""
    try:
        r = conn.execute("SELECT max(xss_total) AS mx FROM qbot_v2.modelq2_ride").fetchone()
    except Exception:
        return None
    v = _rget(r, "mx", 0) if r else None
    return round(float(v), 1) if v is not None else None


def assess(conn, departure_date, stage_xss_list, today=None):
    """Ocena wykonalnosci wg MODELU DWOCH SCIAN. stage_xss_list: XSS per dzien.
    Zachowuje klucze czytane przez frontend (form/simulation/thresholds/verdict/...)
    + dodaje ceilings/walls/block. Kolor dni w simulation = SCIANA (nie TSB)."""
    if isinstance(departure_date, str):
        departure_date = _date.fromisoformat(departure_date[:10])
    today = today or _date.today()
    ctx = load_form_context(conn, today=today)
    if ctx is None:
        return {"ok": False, "reason": "Brak danych CTL w fitmodel_daily."}
    thr = load_tsb_thresholds(conn, today=today)
    yellow, red = float(thr["yellow"]), float(thr["red"])
    days_ahead = max(0, (departure_date - today).days)
    weeks = days_ahead / 7.0
    proj_ctl = project_ctl(ctx["ctl"], ctx["slope_per_day"], days_ahead)
    # symulacja TSB = INFORMACJA (narastajace zmeczenie), nie werdykt
    sim = simulate_expedition(proj_ctl, proj_ctl, stage_xss_list, yellow=yellow, red=red)

    bmr_info = load_athlete_bmr(conn, today=today)
    demonstrated = load_demonstrated_max_day(conn)
    ceilings = compute_ceilings(bmr_info["bmr"], demonstrated) if bmr_info else None

    total_xss = round(sum(float(x or 0.0) for x in stage_xss_list), 1)
    n = len(stage_xss_list)
    avg = round(total_xss / n, 1) if n else None

    walls = []
    if ceilings:
        for i, x in enumerate(stage_xss_list):
            c, lab = day_wall(x, ceilings)
            walls.append({"idx": i, "xss": round(float(x or 0.0), 1), "color": c, "label": lab})
            if i < len(sim["days"]):
                sim["days"][i]["color"] = c        # kropka dnia = SCIANA
                sim["days"][i]["wall"] = lab
        txt = verdict_two_walls(stage_xss_list, ceilings, sim.get("min_tsb"))
    else:
        txt = verdict_text(sim, proj_ctl, None, None, weeks, yellow=yellow, red=red)

    block = None
    if ceilings and avg is not None:
        block = {"avg_daily": avg, "week_ceiling": ceilings["week_avg"],
                 "multiweek_ceiling": ceilings["multiweek_avg"],
                 "over_week": bool(ceilings["week_avg"] is not None and avg > ceilings["week_avg"]),
                 "n_days": n}

    caveats = [
        "Narastajace zmeczenie (TSB w symulacji) = informacja, nie pass/fail.",
        "XSS etapu to estymata fizyczna (predkosc v2 -> moc), nie pomiar.",
        "Projekcja formy zaklada utrzymanie obecnego trendu treningu.",
    ]
    if ceilings:
        caveats.insert(0,
            "Wykonalnosc = model dwoch scian: dzien vs rekord (~%s) i sciana metaboliczna "
            "(~%s XSS = 3.5xBMR), srednia vs sufit tygodniowy (~%s)." % (
                (round(ceilings["day_demonstrated"]) if ceilings["day_demonstrated"] else "b/d"),
                round(ceilings["day_metabolic"]), round(ceilings["week_avg"])))
        caveats.insert(1,
            "Sciana metaboliczna = limit wchlaniania jelit (~uniwersalny), NIE galka wytrenowania. "
            "Glikogen (bufor) tlumaczy roznice sciany 1-dnia vs tygodniowej; dlug narasta dzien po dniu.")

    return {
        "ok": True,
        "form": ctx,
        "departure": departure_date.isoformat(),
        "days_ahead": days_ahead,
        "weeks_to_departure": round(weeks, 1),
        "projected_ctl": (round(proj_ctl, 1) if proj_ctl is not None else None),
        "total_xss": total_xss,
        "avg_daily_xss": avg,
        "simulation": sim,
        "ramp": None,
        "ceilings": ceilings,
        "walls": walls,
        "block": block,
        "verdict": txt,
        "caveats": caveats,
        "thresholds": {"tsb_yellow": yellow, "tsb_red": red,
                       "source": thr["source"], "n": thr["n"]},
    }


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, "/opt/qbot/app")
    os.environ["QBOT3_ENABLED"] = "1"
    from fitmodel.api import _db_connect
    conn = _db_connect()
    try:
        import json
        print("PROGI:", load_tsb_thresholds(conn))
        print("FORMA:", load_form_context(conn))
        print("BMR:", load_athlete_bmr(conn))
        print("DEMO_MAX:", load_demonstrated_max_day(conn))
        tosk = [179.0, 294.0, 242.0, 149.0, 208.0, 246.0, 186.0]
        dep = (_date.today() + _timedelta(days=21)).isoformat()
        print(json.dumps(assess(conn, dep, tosk), ensure_ascii=False, indent=2, default=str))
    finally:
        conn.close()
