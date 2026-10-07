"""Ocena formy wyprawy - rozszerzenie (2026-10-07, Planer v3).

Do wyniku expedition_feasibility.assess (model dwoch scian) dokleja:
- forme na start liczona z PLANU TRENERA (planowane XSS dzien po dniu do wyjazdu; zrobione - realne),
  zamiast samego trendu CTL; potem symulacja dni wyprawy od tej formy,
- tydzien przed wyprawa (sesje TRENERA),
- miejsce kazdego dnia wyprawy wsrod Twoich jazd z 365 dni (top 5 + ile jazd bylo ciezszych),
- krotkie podsumowanie (deterministyczne, bez AI).
"""
from __future__ import annotations

from datetime import date as _date, timedelta as _td

from fitmodel import expedition_feasibility as EF


def _rows(conn, sql, args=()):
    return conn.execute(sql, args).fetchall()


def _g(r, k, i):
    try:
        return r[k]
    except Exception:
        return r[i]


def trener_user(conn):
    r = conn.execute("SELECT username FROM qbot_v2.trainer_session GROUP BY 1 ORDER BY count(*) DESC LIMIT 1").fetchone()
    return _g(r, "username", 0) if r else None


def planned_load(conn, user, d0, d1):
    """XSS per dzien z TRENERA (zrobione: realne XSS, plan: planowane; pominiete/odpuszczone = 0)."""
    out = {}
    if not user:
        return out
    for r in _rows(conn, """SELECT day, status, COALESCE(real_xss, xss) AS x FROM qbot_v2.trainer_session
                            WHERE username=%s AND day BETWEEN %s AND %s""", (user, d0, d1)):
        st = _g(r, "status", 1)
        if st in ("skip", "cut_skip", "skipped"):
            continue
        d = _g(r, "day", 0)
        out[d] = out.get(d, 0.0) + float(_g(r, "x", 2) or 0.0)
    return out


def project_with_plan(ctl, atl, loads, d_from, d_to):
    """EWMA dzien po dniu od d_from do d_to wlacznie (obciazenie z planu)."""
    c, a = float(ctl or 0.0), float(atl if atl is not None else ctl or 0.0)
    d = d_from
    while d <= d_to:
        x = loads.get(d, 0.0)
        c = c + (x - c) * EF._K_CTL
        a = a + (x - a) * EF._K_ATL
        d += _td(days=1)
    return round(c, 1), round(a, 1), round(c - a, 1)


def week_before(conn, user, dep, today=None):
    """Sesje TRENERA z 7 dni przed wyjazdem: dni minione - tylko zrobione, dni przyszle - plan."""
    if not user:
        return []
    today = today or _date.today()
    out = []
    for r in _rows(conn, """SELECT day, name, sport, status, dur_min, COALESCE(real_xss, xss) AS x FROM qbot_v2.trainer_session
                            WHERE username=%s AND day BETWEEN %s AND %s ORDER BY day, start_time NULLS LAST, id""",
                   (user, dep - _td(days=7), dep - _td(days=1))):
        if _g(r, "day", 0) < today and _g(r, "status", 3) != "done":
            continue
        out.append({"day": _g(r, "day", 0).isoformat(), "name": _g(r, "name", 1), "sport": _g(r, "sport", 2),
                    "status": _g(r, "status", 3), "dur_min": _g(r, "dur_min", 4),
                    "xss": (round(float(_g(r, "x", 5)), 0) if _g(r, "x", 5) is not None else None)})
    return out


def top_rides(conn, today, n=5):
    rows = _rows(conn, """SELECT t.date, t.distance_m, m.xss_total FROM qbot_v2.modelq2_ride m
                          JOIN qbot_v2.training_sessions t ON t.external_id = m.external_id
                          WHERE t.date > %s AND m.xss_total IS NOT NULL ORDER BY m.xss_total DESC""",
                   (today - _td(days=365),))
    xs = [float(_g(r, "xss_total", 2)) for r in rows]
    top = [{"date": _g(r, "date", 0).isoformat() if hasattr(_g(r, "date", 0), "isoformat") else str(_g(r, "date", 0)),
            "km": (round(float(_g(r, "distance_m", 1)) / 1000.0, 0) if _g(r, "distance_m", 1) else None),
            "xss": round(float(_g(r, "xss_total", 2)), 0)} for r in rows[:n]]
    return top, xs


def extend(conn, feas: dict, departure, stage_xss: list, today=None) -> dict:
    today = today or _date.today()
    dep = _date.fromisoformat(str(departure)[:10]) if departure else None
    form = (feas or {}).get("form") or EF.load_form_context(conn, today=today) or {}
    user = trener_user(conn)
    res = {"today": {"ctl": form.get("ctl"), "atl": form.get("atl"), "tsb": form.get("tsb"), "as_of": form.get("as_of")}}
    if dep and form.get("ctl") is not None:
        loads = planned_load(conn, user, today + _td(days=1), dep - _td(days=1))
        c, a, t = project_with_plan(form.get("ctl"), form.get("atl"), loads, today + _td(days=1), dep - _td(days=1))
        res["start"] = {"ctl": c, "atl": a, "tsb": t, "planned_xss": round(sum(loads.values()), 0), "days": (dep - today).days,
                        "source": "plan TRENERA do dnia wyjazdu" if loads else "bez planu TRENERA (forma zanika)"}
        sim = EF.simulate_expedition(c, a, stage_xss)
        res["sim"] = sim
        res["week_before"] = week_before(conn, user, dep, today)
    top, all_x = top_rides(conn, today)
    res["top"] = top
    res["stages"] = [{"day": i + 1, "xss": round(float(x or 0.0), 0),
                      "harder_rides": sum(1 for v in all_x if v >= float(x or 0.0)),
                      "rides_365": len(all_x)} for i, x in enumerate(stage_xss)]
    res["summary"] = summary(feas, res)
    return res


def summary(feas, res) -> list:
    out = []
    st, td = res.get("start"), res.get("today") or {}
    if st:
        trend = "rośnie" if st["ctl"] > (td.get("ctl") or 0) + 0.5 else ("spada" if st["ctl"] < (td.get("ctl") or 0) - 0.5 else "bez zmian")
        fresh = "świeży" if st["tsb"] >= 0 else ("lekko zmęczony" if st["tsb"] > -15 else "zmęczony")
        out.append("Na start (za %d dni, wg %s): forma %.0f (%s), świeżość %+.0f — %s." % (st["days"], st["source"], st["ctl"], trend, st["tsb"], fresh))
    stg = res.get("stages") or []
    if stg:
        hardest = max(stg, key=lambda s: s["xss"])
        if hardest["harder_rides"] == 0:
            out.append("Dzień %d (%.0f) byłby Twoją najcięższą jazdą z ostatniego roku." % (hardest["day"], hardest["xss"]))
        else:
            out.append("Najcięższy dzień wyprawy (Dzień %d, %.0f) — w ostatnim roku %d jazd było równie lub bardziej obciążających." % (hardest["day"], hardest["xss"], hardest["harder_rides"]))
    sim = res.get("sim")
    if sim and sim.get("days"):
        last = sim["days"][-1]
        out.append("Narastające zmęczenie: poranna świeżość ostatniego dnia ~%+.0f (informacja, nie stop)." % last["tsb_morning"])
    wb = res.get("week_before") or []
    if wb:
        tday = _date.today().isoformat()
        left = [w for w in wb if w["day"] >= tday and w.get("status") != "done"]
        heavy = [w for w in left if (w.get("xss") or 0) >= 80]
        done_x = sum((w.get("xss") or 0) for w in wb if w.get("status") == "done")
        out.append("Tydzień przed: zrobione %.0f XSS; do wyjazdu jeszcze %d sesji%s." % (done_x, len(left), (", w tym %d mocniejsze — rozważ luz ostatnie 2 dni" % len(heavy)) if heavy else " — lekko, dobry luz przed startem"))
    if feas and feas.get("verdict"):
        out.append(feas["verdict"])
    return out
