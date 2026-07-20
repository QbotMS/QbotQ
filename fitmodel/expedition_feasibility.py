from __future__ import annotations

"""Silnik wykonalnosci wyprawy (Planer Wypraw).

Cel: ocenic, na ile wielodniowy podzial wyprawy jest wykonalny przy OBECNEJ
formie i jej trendzie z ostatnich 30 dni, zrzutowanej do przodu na date wyjazdu
(planowanie nie pokrywa sie z dniem startu). Jesli plan przekracza forme --
policzyc, ile treningu tygodniowo trzeba dolozyc, albo powiedziec wprost, ze w
tym oknie sie nie da bezpiecznie (przesun date / skroc plan).

WALUTA: wszystko w XSS. CTL liczone jest z XSS (qbot_v2.fitmodel_daily.ctl_xss),
a XSS etapu pochodzi z tego samego wzoru fizyki co dla trasy
(route_report_canonical._estimate_route_xss). Nie mieszamy XSS z TSS.

PROGI = Z WLASNEJ HISTORII (nie z podrecznika): zolty = p10, czerwony = p05
rozkladu tsb_raw z ostatniego roku. Michal nie ocenia abstrakcyjnych liczb --
skala jest jego wlasna i sama sie aktualizuje. Fallback podrecznikowy (-20/-30)
tylko gdy za malo historii.

Czesc czysta (bez DB) jest testowalna offline. Czesc "na zywo" czyta
fitmodel_daily przez fitmodel.api._db_connect.
"""

import math
from datetime import date as _date, timedelta as _timedelta
from typing import Any, Optional

TAU_CTL = 42.0
TAU_ATL = 7.0
TSB_YELLOW = -20.0             # fallback podrecznikowy (gdy za malo historii)
TSB_RED = -30.0               # fallback podrecznikowy
SAFE_CTL_RAMP_PER_WEEK = 6.0   # podrecznikowy bezpieczny przyrost CTL/tydz (ostrzezenie, nie zakaz)
_K_CTL = 1.0 - math.exp(-1.0 / TAU_CTL)
_K_ATL = 1.0 - math.exp(-1.0 / TAU_ATL)


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
    Nie ekstrapoluje w kosmos: dodatni trend ograniczony do cap_ramp/7 na dzien;
    spadek (roztrenowanie) dozwolony bez ograniczenia."""
    if today_ctl is None:
        return None
    cap_day = cap_ramp_per_week / 7.0
    s = float(slope_per_day)
    if s > cap_day:
        s = cap_day
    proj = float(today_ctl) + s * max(0, int(days_ahead))
    return max(0.0, proj)


def simulate_expedition(start_ctl, start_atl, stage_xss_list, yellow=TSB_YELLOW, red=TSB_RED):
    """Forward-symulacja dzien po dniu. Kazdy dzien = obciazenie = XSS etapu.
    TSB "poranny" dnia d = CTL_{d-1} - ATL_{d-1} (swiezosc, z ktora zaczynasz dzien).
    Zwraca liste per-dzien {idx, xss, tsb_morning, ctl_after, atl_after, color}
    + min_tsb. color: green / yellow / red wg progow (z historii)."""
    ctl = float(start_ctl or 0.0)
    atl = float(start_atl if start_atl is not None else start_ctl or 0.0)
    days = []
    min_tsb = None
    for i, xss in enumerate(stage_xss_list):
        load = float(xss or 0.0)
        tsb_morning = ctl - atl
        ctl = ctl + (load - ctl) * _K_CTL
        atl = atl + (load - atl) * _K_ATL
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
    """Najmniejsze startowe CTL (przy zalozeniu swiezosci TSB=0 -> ATL=CTL),
    przy ktorym min. poranny TSB nie schodzi ponizej progu 'red'.
    Zwraca (min_ctl, min_tsb_at_that_ctl)."""
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
    """Ile XSS/tydzien trzeba dolozyc do treningu, by z projected_ctl dobic do
    ctl_needed na date wyjazdu. Zwraca dict z ocena wykonalnosci samego rampu."""
    gap = float(ctl_needed) - float(projected_ctl)
    weeks = max(0.1, float(weeks_to_departure))
    ramp_per_week = gap / weeks if gap > 0 else 0.0
    extra_weekly_xss = ramp_per_week * 7.0 if ramp_per_week > 0 else 0.0
    safe = ramp_per_week <= SAFE_CTL_RAMP_PER_WEEK + 1e-9
    return {
        "gap_ctl": round(gap, 1),
        "ramp_per_week": round(ramp_per_week, 1),
        "extra_weekly_xss": round(extra_weekly_xss, 0),
        "safe": bool(safe),
        "safe_cap_per_week": SAFE_CTL_RAMP_PER_WEEK,
    }


def verdict_text(sim, projected_ctl, ctl_needed, ramp, weeks, yellow=TSB_YELLOW, red=TSB_RED):
    """Sklada jedno zdanie werdyktu po polsku. Progi = z historii (yellow/red)."""
    min_tsb = sim["min_tsb"]
    if min_tsb is not None and min_tsb >= yellow:
        return ("Wyprawa wygląda na wykonalną przy obecnej formie i trendzie — "
                "TSB nie schodzi w Twoją strefę zmęczenia (poniżej %.0f)." % yellow)
    if min_tsb is not None and min_tsb >= red:
        return ("Wyprawa na granicy: TSB spada do %.0f, czyli w Twoje 10%% "
                "najcięższych dni. Do zniesienia, ale zaplanuj lżejszy dzień "
                "lub dodatkowy nocleg." % min_tsb)
    # ponizej czerwonego = tam, gdzie bywasz rzadko (dolne ~5%)
    base = ("Plan zbyt ciężki: TSB spadłoby do %.0f — niżej niż %.0f byłeś tylko "
            "w ~5%% najcięższych dni." % (min_tsb, red))
    if ramp is None:
        return base
    if ramp["safe"]:
        return (base + " Do wyjazdu ~%d tyg. — aby był bezpieczny, podnieś trening tak, "
                "by CTL rosło o ~%.0f/tydz (≈ +%.0f XSS tygodniowo)."
                % (round(weeks), ramp["ramp_per_week"], ramp["extra_weekly_xss"]))
    return (base + " Wymagany przyrost formy (~%.0f/tydz) jest duży. W tym oknie "
            "trudno to bezpiecznie nadrobić — rozważ przesunięcie daty lub "
            "rozłożenie trasy na więcej dni." % ramp["ramp_per_week"])


# ---- CZESC NA ZYWO (DB) ---------------------------------------------------

def load_tsb_thresholds(conn, today=None, window_days=365, min_days=60):
    """Progi TSB z WLASNEJ historii: zolty=p10, czerwony=p05 rozkladu tsb_raw
    w oknie window_days. Za malo danych -> fallback podrecznikowy (-20/-30)."""
    end = today or _date.today()
    start = end - _timedelta(days=window_days)
    rows = conn.execute(
        "SELECT tsb_raw FROM qbot_v2.fitmodel_daily "
        "WHERE day BETWEEN %s AND %s AND tsb_raw IS NOT NULL",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    def _g(r):
        try:
            return r["tsb_raw"]
        except Exception:
            return r[0]
    vals = sorted(float(_g(r)) for r in rows if _g(r) is not None)
    if len(vals) < min_days:
        return {"yellow": TSB_YELLOW, "red": TSB_RED,
                "source": "domyślne podręcznikowe (za mało historii)", "n": len(vals)}
    return {"yellow": round(percentile(vals, 10)), "red": round(percentile(vals, 5)),
            "source": "z Twojej historii (p10 / p05)", "n": len(vals)}


def load_form_context(conn, today=None, lookback_days=30):
    """Dzisiejsze CTL/ATL/TSB + trend z ostatnich lookback_days (z fitmodel_daily).
    Zwraca dict lub None gdy brak danych CTL."""
    end = today or _date.today()
    start = end - _timedelta(days=lookback_days)
    rows = conn.execute(
        "SELECT day, ctl_xss, atl_raw, tsb_raw FROM qbot_v2.fitmodel_daily "
        "WHERE day BETWEEN %s AND %s AND ctl_xss IS NOT NULL ORDER BY day",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    if not rows:
        return None
    def _g(r, k, i):
        try:
            return r[k]
        except Exception:
            return r[i]
    series = []
    base = None
    for r in rows:
        d = _g(r, "day", 0)
        c = _g(r, "ctl_xss", 1)
        if base is None:
            base = d
        series.append(((d - base).days, float(c) if c is not None else None))
    last = rows[-1]
    today_ctl = float(_g(last, "ctl_xss", 1))
    atl = _g(last, "atl_raw", 2)
    tsb = _g(last, "tsb_raw", 3)
    slope = ctl_trend_slope(series)
    return {
        "as_of": _g(last, "day", 0).isoformat(),
        "ctl": round(today_ctl, 1),
        "atl": (round(float(atl), 1) if atl is not None else None),
        "tsb": (round(float(tsb), 1) if tsb is not None else None),
        "slope_per_day": round(slope, 3),
        "n_days": len(series),
    }


def assess(conn, departure_date, stage_xss_list, today=None):
    """Pelna ocena wykonalnosci wyprawy na date wyjazdu.
    stage_xss_list: lista XSS per dzien (kolejno). departure_date: date lub 'YYYY-MM-DD'.
    Progi TSB brane z WLASNEJ historii. Zwraca dict gotowy dla frontendu."""
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
    # na wyjezdzie zakladamy forme utrzymana treningiem: TSB~0 -> ATL=CTL (bez taperu).
    sim = simulate_expedition(proj_ctl, proj_ctl, stage_xss_list, yellow=yellow, red=red)
    ctl_needed, _ = min_start_ctl_feasible(stage_xss_list, red=red)
    ramp = None
    if sim["min_tsb"] is not None and sim["min_tsb"] < red and ctl_needed > proj_ctl:
        ramp = required_weekly_ramp(proj_ctl, ctl_needed, weeks if weeks > 0 else 0.1)
    txt = verdict_text(sim, proj_ctl, ctl_needed, ramp, weeks, yellow=yellow, red=red)
    total_xss = round(sum(float(x or 0.0) for x in stage_xss_list), 1)
    return {
        "ok": True,
        "form": ctx,
        "departure": departure_date.isoformat(),
        "days_ahead": days_ahead,
        "weeks_to_departure": round(weeks, 1),
        "projected_ctl": (round(proj_ctl, 1) if proj_ctl is not None else None),
        "ctl_needed": ctl_needed,
        "total_xss": total_xss,
        "avg_daily_xss": (round(total_xss / len(stage_xss_list), 1) if stage_xss_list else None),
        "simulation": sim,
        "ramp": ramp,
        "verdict": txt,
        "caveats": [
            "XSS etapu to estymata (tier B), zależna od założonej intensywności — nie pomiar.",
            "Projekcja formy zakłada utrzymanie obecnego trendu treningu; odpuszczenie = spadek CTL.",
            "Na dzień wyjazdu przyjęto TSB≈0 (bez taperu); realny taper poprawi świeżość.",
        ],
        "thresholds": {"tsb_yellow": yellow, "tsb_red": red,
                       "source": thr["source"], "n": thr["n"],
                       "safe_ramp_per_week": SAFE_CTL_RAMP_PER_WEEK},
    }


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, "/opt/qbot/app")
    os.environ["QBOT3_ENABLED"] = "1"
    from fitmodel.api import _db_connect
    conn = _db_connect()
    try:
        print("PROGI:", load_tsb_thresholds(conn))
        print("FORMA:", load_form_context(conn))
        demo = [140.0, 160.0, 130.0]
        dep = (_date.today() + _timedelta(days=21)).isoformat()
        import json
        print(json.dumps(assess(conn, dep, demo), ensure_ascii=False, indent=2, default=str))
    finally:
        conn.close()
