from __future__ import annotations

"""Sezon (2026-09-28): "gdzie jestem" na tle calego sezonu + tydzien po tygodniu.

Zrodla (celowo odporne na miernik mocy):
  - godziny / km / najdluzsza jazda: training_sessions (sport_type='cycling')
  - obciazenie XSS: modelq2_ride (PO korekcie - kwarantanna miernika liczy z tetna)
  - forma (CTL), gotowosc, tetno spoczynkowe, HRV, skok obciazenia: fitmodel_daily
  - infekcje: calendar_entry kind='illness' (z end_day)
Sezon = od 1 marca biezacego roku. Typ tygodnia to prosta regula (bez interpretacji przyczyn):
  infekcja >= 2 dni choroby | wyjazd >= 3 jazdy >= 3 h | mocny >= 1.3 x typowe godziny |
  lzejszy <= 0.6 x typowe godziny | budowa (reszta) | biezacy (niepelny tydzien).
build(conn) dziala z psycopg2 i psycopg3 (dict_row) - wiersze normalizowane do dict.
"""

import datetime as dt
from statistics import median

ILL_MIN_DAYS = 2
TRIP_MIN_RIDES, TRIP_RIDE_H = 3, 3.0
STRONG_X, LIGHT_X = 1.3, 0.6


def _rows(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    res = cur.fetchall()
    if res and not isinstance(res[0], dict):
        cols = [d[0] for d in cur.description]
        res = [dict(zip(cols, r)) for r in res]
    return res


def _f(x, d=1):
    return round(float(x), d) if x is not None else None


def week_type(hours, ill_days, long_rides, typical_h, partial=False) -> str:
    """Czysta funkcja - typ tygodnia."""
    if partial:
        return "biezacy"
    if ill_days >= ILL_MIN_DAYS:
        return "infekcja"
    if long_rides >= TRIP_MIN_RIDES:
        return "wyjazd"
    if typical_h and hours >= STRONG_X * typical_h:
        return "mocny"
    if typical_h is not None and hours <= LIGHT_X * typical_h:
        return "lzejszy"
    return "budowa"


def build(conn, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    start = dt.date(today.year, 3, 1)
    if today < start:
        start = dt.date(today.year - 1, 3, 1)
    w0 = start - dt.timedelta(days=start.weekday())

    rides = _rows(conn, "SELECT date, duration_s, distance_m FROM qbot_v2.training_sessions "
                        "WHERE sport_type='cycling' AND date BETWEEN %s AND %s", (w0, today))
    xss = {r["ride_date"]: float(r["x"] or 0) for r in _rows(conn,
           "SELECT ride_date, SUM(xss_total) AS x FROM qbot_v2.modelq2_ride WHERE ride_date BETWEEN %s AND %s "
           "GROUP BY ride_date", (w0, today))}
    fd = {r["day"]: r for r in _rows(conn,
          "SELECT day, ctl_xss, readiness_effective, readiness_score, rhr, hrv_night, load_ramp, tsb_plus "
          "FROM qbot_v2.fitmodel_daily WHERE day BETWEEN %s AND %s", (w0, today))}
    ill = set()
    for r in _rows(conn, "SELECT day, COALESCE(end_day, day) AS e FROM qbot_v2.calendar_entry WHERE kind='illness' "
                         "AND COALESCE(end_day, day) >= %s AND day <= %s", (w0 - dt.timedelta(days=30), today)):
        d = r["day"]
        while d <= r["e"]:
            ill.add(d); d += dt.timedelta(days=1)

    # --- tygodnie ---
    weeks = []
    ws = w0
    while ws <= today:
        we = ws + dt.timedelta(days=6)
        rs = [r for r in rides if ws <= r["date"] <= we]
        hrs = sum((r["duration_s"] or 0) for r in rs) / 3600.0
        days = [ws + dt.timedelta(days=i) for i in range(7) if ws + dt.timedelta(days=i) <= today]
        rd = [float(fd[d]["readiness_effective"] if fd[d]["readiness_effective"] is not None else fd[d]["readiness_score"])
              for d in days if d in fd and (fd[d]["readiness_effective"] is not None or fd[d]["readiness_score"] is not None)]
        rh = [float(fd[d]["rhr"]) for d in days if d in fd and fd[d]["rhr"] is not None]
        weeks.append({
            "week": ws.isoformat(), "hours": round(hrs, 1),
            "km": round(sum((r["distance_m"] or 0) for r in rs) / 1000.0),
            "xss": round(sum(xss.get(d, 0.0) for d in days)),
            "longest_h": round(max([(r["duration_s"] or 0) / 3600.0 for r in rs] or [0]), 1),
            "long_rides": sum(1 for r in rs if (r["duration_s"] or 0) >= TRIP_RIDE_H * 3600),
            "ill_days": sum(1 for d in days if d in ill),
            "readiness": _f(sum(rd) / len(rd), 2) if rd else None,
            "rhr": _f(sum(rh) / len(rh), 1) if rh else None,
            "partial": we > today,
        })
        ws += dt.timedelta(days=7)
    full = [w for w in weeks if not w["partial"] and w["ill_days"] < ILL_MIN_DAYS and w["hours"] > 0]
    typical = round(median([w["hours"] for w in full]), 1) if full else None
    for w in weeks:
        w["type"] = week_type(w["hours"], w["ill_days"], w["long_rides"], typical, w["partial"])

    # --- gdzie jestem ---
    def avg(vals):
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None
    sdays = [d for d in sorted(fd) if d >= start]
    ctl_now = next((float(fd[d]["ctl_xss"]) for d in reversed(sdays) if fd[d]["ctl_xss"] is not None), None)
    ctl_pts = [(d, float(fd[d]["ctl_xss"])) for d in sdays if fd[d]["ctl_xss"] is not None]
    ctl_max = max(ctl_pts, key=lambda x: x[1]) if ctl_pts else (None, None)
    last4 = [w for w in weeks if not w["partial"]][-4:]
    r28 = [r for r in rides if r["date"] > today - dt.timedelta(days=28)]
    rs_all = [r for r in rides if r["date"] >= start]
    longest = max(rs_all, key=lambda r: r["duration_s"] or 0) if rs_all else None
    first28 = [d for d in sdays if d < start + dt.timedelta(days=28)]
    last14 = [d for d in sdays if d > today - dt.timedelta(days=14)]
    rhr0, rhr_now = avg([fd[d]["rhr"] and float(fd[d]["rhr"]) for d in first28]), avg([fd[d]["rhr"] and float(fd[d]["rhr"]) for d in last14])
    hrv0, hrv_now = avg([fd[d]["hrv_night"] and float(fd[d]["hrv_night"]) for d in first28]), avg([fd[d]["hrv_night"] and float(fd[d]["hrv_night"]) for d in last14])
    rdy14 = avg([(fd[d]["readiness_effective"] if fd[d]["readiness_effective"] is not None else fd[d]["readiness_score"]) and
                 float(fd[d]["readiness_effective"] if fd[d]["readiness_effective"] is not None else fd[d]["readiness_score"]) for d in last14])
    h4 = avg([w["hours"] for w in last4])
    ill_past = sorted(d for d in ill if d <= today)
    ill_end = ill_past[-1] if ill_past else None
    days_after_ill = (today - ill_end).days if ill_end else None
    today_row = fd.get(today) or (fd[sdays[-1]] if sdays else {})

    where = {
        "season_start": start.isoformat(),
        "ctl": {"now": _f(ctl_now), "max": _f(ctl_max[1]), "max_day": ctl_max[0].isoformat() if ctl_max[0] else None,
                "avg": _f(avg([v for _, v in ctl_pts]))},
        "hours_week": {"now_4w": _f(h4), "typical": typical,
                       "max": _f(max([w["hours"] for w in weeks if not w["partial"]] or [0])),
                       "max_week": max([w for w in weeks if not w["partial"]] or [{"week": None, "hours": 0}], key=lambda w: w["hours"])["week"]},
        "longest_ride_h": {"last_28d": _f(max([(r["duration_s"] or 0) / 3600.0 for r in r28] or [0])),
                           "season": _f((longest["duration_s"] or 0) / 3600.0) if longest else None,
                           "season_day": longest["date"].isoformat() if longest else None},
        "rhr": {"now_14d": _f(rhr_now), "start_28d": _f(rhr0), "delta": _f(rhr_now - rhr0) if (rhr_now and rhr0) else None},
        "hrv": {"now_14d": _f(hrv_now, 0), "start_28d": _f(hrv0, 0), "delta": _f(hrv_now - hrv0, 0) if (hrv_now and hrv0) else None},
        "readiness_14d": _f(rdy14, 2),
        "load_ramp": _f(today_row.get("load_ramp"), 2) if today_row else None,
        "tsb": _f(today_row.get("tsb_plus")) if today_row else None,
        "illness_last_end": ill_end.isoformat() if ill_end else None,
        "days_after_illness": days_after_ill,
    }

    # --- status do Dziennika: TYLKO rzeczy, ktorych nie mowi Swiezosc ---
    status = []
    if days_after_ill is not None and 0 < days_after_ill <= 14:
        status.append("odbudowa po infekcji — dzień %d z ~14" % days_after_ill)
    if h4 is not None and typical and h4 <= LIGHT_X * typical:
        status.append("objętość niska: %s h/tydz. (typowo %s h)" % (str(_f(h4)).replace(".", ","), str(typical).replace(".", ",")))
    if where["rhr"]["delta"] is not None and where["rhr"]["delta"] >= 1.5:
        status.append("tętno spoczynkowe +%s względem startu sezonu" % str(where["rhr"]["delta"]).replace(".", ","))
    return {"today": today.isoformat(), "where": where, "weeks": weeks, "typical_hours": typical, "status": status}
