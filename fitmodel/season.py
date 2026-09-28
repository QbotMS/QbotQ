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
    # polaczenie (psycopg2/3) albo juz kursor (TRENER przekazuje kursor do build_context)
    cur = conn.cursor() if hasattr(conn, "cursor") else conn
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
    z = {"today": today.isoformat(), "where": where, "weeks": weeks, "typical_hours": typical, "status": status}
    try:
        z["story"] = story(z, fd, [r for r in rides if r["date"] >= start], ill)
    except Exception as exc:   # opis nie moze zablokowac danych
        z["story"] = {"error": str(exc)}
    try:
        z["insight"] = insight(conn, z, fd, [r for r in rides if r["date"] >= start], ill)
    except Exception as exc:
        import traceback
        z["insight"] = {"error": "%s: %s" % (type(exc).__name__, exc), "trace": traceback.format_exc()[-600:]}
    try:
        z["view"] = view(z, fd, [r for r in rides if r["date"] >= start], ill)
    except Exception as exc:
        z["view"] = {"error": str(exc)}
    try:
        z["facts"] = facts(conn, z, fd, [r for r in rides if r["date"] >= start], ill)
    except Exception as exc:
        import traceback
        z["facts"] = {"error": "%s: %s" % (type(exc).__name__, exc), "trace": traceback.format_exc()[-800:]}
    try:
        z["tiles"] = tiles(z, fd, [r for r in rides if r["date"] >= start])
    except Exception as exc:
        z["tiles"] = [{"id": "err", "title": "Status", "status": "błąd", "level": "bad", "line": str(exc), "more": []}]
    return z


# ======================= OPIS SLOWNY (2026-09-28) =======================
# Deterministyczne zdania z danych. Zasada: fakt w czasie ("po X nastapilo Y"),
# bez zgadywania przyczyn. Wnioski ("co z tego") tylko gdy wzor powtorzyl sie >= 2 razy.

MIES = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
        "września", "października", "listopada", "grudnia"]
MIES_M = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień",
          "wrzesień", "październik", "listopad", "grudzień"]
LONG_RIDE_H = 4.0          # "dluzsza jazda" w regule po infekcji
AFTER_ILL_DAYS = 14        # okno po infekcji
TRIP_PRE_READY = -0.3      # gotowosc przed wyjazdem ponizej -> obserwacja


def _pl(x, d=1):
    if x is None:
        return "—"
    return (("%." + str(d) + "f") % x).replace(".", ",")


def _dm(d):
    return "%d %s" % (d.day, MIES[d.month - 1])


def _phases(weeks):
    """Grupuje kolejne tygodnie w fazy: trening (budowa/mocny), luz, wyjazd, infekcja.
    Pojedynczy lzejszy tydzien miedzy treningami wchodzi do fazy treningu."""
    kind = {"budowa": "trening", "mocny": "trening", "lzejszy": "luz", "wyjazd": "wyjazd", "infekcja": "infekcja"}
    g = []
    for w in weeks:
        if w["partial"]:
            continue
        k = kind.get(w["type"], "trening")
        if g and g[-1]["kind"] == k:
            g[-1]["weeks"].append(w)
        else:
            g.append({"kind": k, "weeks": [w]})
    merged = []
    i = 0
    while i < len(g):
        cur = g[i]
        if (cur["kind"] == "luz" and len(cur["weeks"]) == 1 and merged and merged[-1]["kind"] == "trening"
                and i + 1 < len(g) and g[i + 1]["kind"] == "trening"):
            merged[-1]["weeks"] += cur["weeks"] + g[i + 1]["weeks"]
            i += 2
            continue
        if merged and merged[-1]["kind"] == cur["kind"]:
            merged[-1]["weeks"] += cur["weeks"]
        else:
            merged.append({"kind": cur["kind"], "weeks": list(cur["weeks"])})
        i += 1
    return merged


def trip_start(ph, rides):
    """Pierwszy dzien wyjazdu = pierwsza jazda >= TRIP_RIDE_H h w tygodniach fazy (nie poniedzialek)."""
    a = dt.date.fromisoformat(ph["weeks"][0]["week"])
    b = a + dt.timedelta(days=7 * len(ph["weeks"]) - 1)
    ds = [r["date"] for r in rides if a <= r["date"] <= b and (r["duration_s"] or 0) >= TRIP_RIDE_H * 3600]
    return min(ds) if ds else a


def story(z, fd, rides, ill):
    """z = wynik build() bez story; fd = {day: row}; rides = lista jazd; ill = zbior dni infekcji."""
    W = z["where"]
    weeks = z["weeks"]
    typical = z["typical_hours"]

    def ctl_on(d):
        for k in range(0, 8):
            r = fd.get(d - dt.timedelta(days=k))
            if r and r.get("ctl_xss") is not None:
                return float(r["ctl_xss"])
        return None

    def rdy(d):
        r = fd.get(d)
        if not r:
            return None
        v = r.get("readiness_effective") if r.get("readiness_effective") is not None else r.get("readiness_score")
        return float(v) if v is not None else None

    # --- 1. przebieg sezonu (fazy) ---
    przebieg = []
    s_start = dt.date.fromisoformat(W["season_start"])
    for ph in _phases(weeks):
        a = max(s_start, dt.date.fromisoformat(ph["weeks"][0]["week"]))
        b = dt.date.fromisoformat(ph["weeks"][-1]["week"]) + dt.timedelta(days=6)
        n = len(ph["weeks"])
        h = sum(w["hours"] for w in ph["weeks"]) / n
        c0, c1 = ctl_on(a), ctl_on(b)
        if ph["kind"] == "trening":
            nl = sum(1 for w in ph["weeks"] if w["type"] == "lzejszy")
            t = "%s – %s: trening, %d tyg., średnio %s h/tydz.%s" % (_dm(a), _dm(b), n, _pl(h), (" (w tym %d lżejszy)." % nl) if nl else "")
        elif ph["kind"] == "wyjazd":
            t = "%s – %s: wyjazd, %d tyg., średnio %s h/tydz." % (_dm(a), _dm(b), n, _pl(h))
        elif ph["kind"] == "infekcja":
            t = "%s – %s: infekcja, %s h/tydz." % (_dm(a), _dm(b), _pl(h))
        else:
            t = "%s – %s: luz, %d tyg., %s h/tydz." % (_dm(a), _dm(b), n, _pl(h))
        if c0 is not None and c1 is not None:
            t += " Forma %s → %s." % (_pl(c0, 0), _pl(c1, 0))
        przebieg.append(t)

    # --- 2. gdzie jestes ---
    gdzie = []
    C = W["ctl"]
    if C["now"] is not None and C["max"]:
        pct = round(100 * C["now"] / C["max"])
        s = "Forma %s to %d%% szczytu sezonu (%s, %s)." % (_pl(C["now"], 0), pct, _pl(C["max"], 0),
                                                         _dm(dt.date.fromisoformat(C["max_day"])))
        # kiedy ostatnio forma byla tak niska (przed obecnym spadkiem)
        start = dt.date.fromisoformat(W["season_start"])
        peak_day = dt.date.fromisoformat(C["max_day"])
        cand = [d for d in sorted(fd) if start <= d < peak_day and fd[d].get("ctl_xss") is not None
                and float(fd[d]["ctl_xss"]) <= C["now"] + 0.5]
        if cand:
            s += " Tak niską formę miałeś ostatnio %s." % _dm(cand[-1])
        gdzie.append(s)
    HW = W["hours_week"]
    if HW["now_4w"] is not None and HW["typical"]:
        gdzie.append("Jeździsz %s h tygodniowo (średnia 4 tygodni) — to %d%% Twojego typowego tygodnia (%s h)."
                     % (_pl(HW["now_4w"]), round(100 * HW["now_4w"] / HW["typical"]), _pl(HW["typical"])))
    RH, HV = W["rhr"], W["hrv"]
    if RH["delta"] is not None:
        hi_weeks = [w for w in weeks if w["rhr"] is not None and RH["now_14d"] is not None and w["rhr"] >= RH["now_14d"] - 0.2 and not w["partial"]]
        kinds = sorted({w["type"] for w in hi_weeks})
        s = "Tętno spoczynkowe %s (%s%s względem startu sezonu)" % (_pl(RH["now_14d"]), "+" if RH["delta"] > 0 else "", _pl(RH["delta"]))
        if HV["delta"] is not None:
            s += ", HRV %s (%s%s)" % (_pl(HV["now_14d"], 0), "+" if HV["delta"] > 0 else "", _pl(HV["delta"], 0))
        s += "."
        if hi_weeks:
            names = {"infekcja": "infekcja", "wyjazd": "wyjazd", "mocny": "mocny tydzień", "budowa": "trening", "lzejszy": "lżejszy tydzień"}
            s += " Podobnie wysokie tętno było w sezonie tylko %d razy: %s." % (len(hi_weeks), ", ".join(
                "%s (%s)" % (_dm(dt.date.fromisoformat(w["week"])), names.get(w["type"], w["type"])) for w in hi_weeks))
        gdzie.append(s)
    if W["readiness_14d"] is not None:
        r = W["readiness_14d"]
        gdzie.append("Gotowość z 14 dni: %s — %s." % (_pl(r, 2), "poniżej Twojej normy" if r <= -0.4 else "powyżej normy" if r >= 0.4 else "w granicach normy"))
    if W["days_after_illness"] is not None and W["days_after_illness"] <= 30:
        gdzie.append("Minęło %d dni od końca infekcji (%s)." % (W["days_after_illness"], _dm(dt.date.fromisoformat(W["illness_last_end"]))))

    # --- 3. pod planowanie: porownanie z wyjazdami sezonu ---
    plan = []
    phs = _phases(weeks)
    for ph in phs:
        if ph["kind"] != "wyjazd":
            continue
        a0 = trip_start(ph, rides)
        pre = [rdy(a0 - dt.timedelta(days=k)) for k in range(1, 8)]
        pre = [v for v in pre if v is not None]
        h = sum(w["hours"] for w in ph["weeks"]) / len(ph["weeks"])
        c0 = ctl_on(a0 - dt.timedelta(days=1))
        s = "Wyjazd od %s (%d tyg. po %s h): na starcie forma %s" % (_dm(a0), len(ph["weeks"]), _pl(h), _pl(c0, 0))
        if pre:
            s += ", gotowość z tygodnia przed %s" % _pl(sum(pre) / len(pre), 2)
        s += "."
        if C["now"] is not None and c0:
            dlt = C["now"] - c0
            s += " Dziś forma %s — %s." % (_pl(C["now"], 0), "praktycznie tyle samo" if abs(dlt) < 1.5 else
                                          ("o %s mniej" % _pl(-dlt, 0)) if dlt < 0 else ("o %s więcej" % _pl(dlt, 0)))
        if pre and W["readiness_14d"] is not None:
            s += " Gotowość: wtedy %s, teraz %s." % (_pl(sum(pre) / len(pre), 2), _pl(W["readiness_14d"], 2))
        plan.append(s)
    if W["days_after_illness"] is not None and W["days_after_illness"] < AFTER_ILL_DAYS:
        plan.append("Jesteś w pierwszych 2 tygodniach po infekcji — w Twoim sezonie dłuższe jazdy w tym okresie kończyły się dołkiem gotowości (patrz obserwacje).")

    # --- 4. obserwacje z sezonu ---
    obs, lessons = [], []
    # R1: dluzsza jazda w 14 dni po infekcji
    ill_sorted = sorted(ill)
    ends = [d for d in ill_sorted if (d + dt.timedelta(days=1)) not in ill]
    season_r = [rdy(d) for d in sorted(fd)]
    season_r = sorted(v for v in season_r if v is not None)
    r_med = season_r[len(season_r) // 2] if season_r else 0.0
    n1 = 0
    for e in ends:
        cand = sorted([r for r in rides if e < r["date"] <= e + dt.timedelta(days=AFTER_ILL_DAYS)
                       and (r["duration_s"] or 0) >= LONG_RIDE_H * 3600], key=lambda r: r["date"])
        if not cand:
            continue
        r0 = cand[0]
        nxt = [rdy(r0["date"] + dt.timedelta(days=k)) for k in range(1, 4)]
        nxt = [v for v in nxt if v is not None]
        if not nxt:
            continue
        mn = min(nxt)
        obs.append("%s: jazda %s h, %d dni po infekcji → przez 3 kolejne dni gotowość spadła do %s (typowo w sezonie %s)."
                   % (_dm(r0["date"]), _pl((r0["duration_s"] or 0) / 3600.0), (r0["date"] - e).days, _pl(mn, 2), _pl(r_med, 2)))
        if mn <= -0.8:
            n1 += 1
    if n1 >= 2:
        lessons.append("Powtórzyło się %d razy: dłuższa jazda w pierwszych 2 tygodniach po infekcji kończyła się głębokim dołkiem gotowości. Następnym razem odłóż ją o tydzień." % n1)
    # R2: start wyjazdu ponizej normy
    n2 = 0
    for ph in phs:
        if ph["kind"] != "wyjazd":
            continue
        a0 = trip_start(ph, rides)
        pre = [rdy(a0 - dt.timedelta(days=k)) for k in range(1, 8)]
        pre = [v for v in pre if v is not None]
        if pre and sum(pre) / len(pre) <= TRIP_PRE_READY:
            n2 += 1
            obs.append("%s: wyjazd zaczęty przy gotowości %s z tygodnia przed (poniżej normy)." % (_dm(a0), _pl(sum(pre) / len(pre), 2)))
    if n2 >= 1:
        lessons.append("Przed wyjazdem zaplanuj kilka luźniejszych dni, żeby startować z gotowością co najmniej w normie.")
    # R3: lzejszy tydzien po wyjezdzie / mocnym tygodniu
    n3 = 0
    for i in range(1, len(weeks)):
        w, p = weeks[i], weeks[i - 1]
        prev2 = [weeks[j]["type"] for j in (i - 1, i - 2) if j >= 0]
        if w["partial"] or w["type"] != "lzejszy" or not any(t in ("wyjazd", "mocny") for t in prev2):
            continue
        src_t = "wyjazd" if "wyjazd" in prev2 else "mocny"
        if w["readiness"] is not None and p["readiness"] is not None and w["readiness"] - p["readiness"] >= 0.3:
            n3 += 1
            obs.append("%s: lżejszy tydzień (%s h) po %s → gotowość %s → %s." % (
                _dm(dt.date.fromisoformat(w["week"])), _pl(w["hours"]), "wyjeździe" if src_t == "wyjazd" else "mocnym tygodniu",
                _pl(p["readiness"], 2), _pl(w["readiness"], 2)))
    if n3 >= 1:
        lessons.append("Działało: lżejszy tydzień po wyjeździe albo mocnym tygodniu wyraźnie poprawiał gotowość.")

    return {"przebieg": przebieg, "gdzie": gdzie, "plan": plan, "obserwacje": obs, "wnioski": lessons,
            "zasady": ("Zdania powstają z danych według stałych reguł (fakty w czasie, bez zgadywania przyczyn). "
                       "Wniosek pojawia się dopiero, gdy wzór powtórzył się w sezonie.")}


# ======================= KAFLE STATUSU (2026-09-28) =======================
# Szybka odpowiedz "co to znaczy / co robic / czy gotowy na wyjazd". Progi jawne:
REGEN_RDY3 = -0.4          # gotowosc (srednia 3 dni) >= -> regeneracja w normie
REGEN_RHR_MARGIN = 1.0     # tetno spocz. (7 dni) <= start sezonu + margines
AFTER_ILL_EASY_DAYS = 14   # po infekcji: tylko krotko (reguła z Twojego sezonu, 2x dolek)
EASY_RIDE_H = 1.5
FORM_TOL = 3.0             # forma >= forma na starcie ostatniego wyjazdu - tolerancja
NORMAL_WEEK_X = 0.8        # "normalny tydzien" >= 0.8 x typowy


def tiles(z, fd, rides):
    W, weeks, typical = z["where"], z["weeks"], z["typical_hours"]
    today = dt.date.fromisoformat(z["today"])

    def val(d, k):
        r = fd.get(d)
        return float(r[k]) if r and r.get(k) is not None else None

    def rdy(d):
        v = val(d, "readiness_effective")
        return v if v is not None else val(d, "readiness_score")

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    rdy3 = mean([rdy(today - dt.timedelta(days=k)) for k in range(0, 3)])
    rhr7 = mean([val(today - dt.timedelta(days=k), "rhr") for k in range(0, 7)])
    rhr_ref = W["rhr"]["start_28d"]
    rhr_goal = (rhr_ref + REGEN_RHR_MARGIN) if rhr_ref is not None else None
    rdy_ok = rdy3 is not None and rdy3 >= REGEN_RDY3
    rhr_ok = rhr7 is not None and rhr_goal is not None and rhr7 <= rhr_goal
    regen_ok = rdy_ok and rhr_ok

    # forma odniesienia: start ostatniego wyjazdu w sezonie
    ref = None
    for ph in _phases(weeks):
        if ph["kind"] == "wyjazd":
            a = trip_start(ph, rides)
            c0 = None
            for k in range(1, 9):
                c0 = val(a - dt.timedelta(days=k), "ctl_xss")
                if c0 is not None:
                    break
            ref = {"start": a, "ctl": c0, "weeks": len(ph["weeks"]),
                   "hours": sum(w["hours"] for w in ph["weeks"]) / len(ph["weeks"])}
    ctl = W["ctl"]["now"]
    dai = W["days_after_illness"]
    ill_end = dt.date.fromisoformat(W["illness_last_end"]) if W["illness_last_end"] else None
    full = [w for w in weeks if not w["partial"]]
    # typowy tydzien PO okresie ochronnym (spojne z planem powrotu i warunkami wyjazdu)
    protect_end = (ill_end + dt.timedelta(days=AFTER_ILL_EASY_DAYS)) if ill_end else None
    normal_after = [w for w in full if protect_end and dt.date.fromisoformat(w["week"]) > protect_end
                    and typical and w["hours"] >= 0.95 * typical and w["type"] != "infekcja"]
    h4, tw = W["hours_week"]["now_4w"], typical
    T = []

    # 1. forma
    if ctl is not None and ref and ref["ctl"]:
        d = ctl - ref["ctl"]
        lvl = "good" if d >= -FORM_TOL else ("warn" if d >= -10 else "bad")
        T.append({"id": "forma", "title": "Forma", "status": "wystarcza" if lvl == "good" else ("trochę brakuje" if lvl == "warn" else "za niska"),
                  "level": lvl,
                  "line": "%s — jak na starcie wyjazdu %s (%s)" % (_pl(ctl, 0), _dm(ref["start"]), _pl(ref["ctl"], 0)) if lvl == "good"
                          else "%s, na starcie wyjazdu %s było %s" % (_pl(ctl, 0), _dm(ref["start"]), _pl(ref["ctl"], 0)),
                  "more": ["Forma (CTL) to średnie obciążenie z ok. 6 tygodni — baza treningowa.",
                           "Szczyt sezonu %s (%s) był w trakcie wyjazdu, więc do planowania porównuję z formą na jego starcie."
                           % (_pl(W["ctl"]["max"], 0), _dm(dt.date.fromisoformat(W["ctl"]["max_day"]))),
                           "Obciążenie po korekcie miernika (jazdy w kwarantannie liczone z tętna)."]})
    # 2. regeneracja
    lvl = "good" if regen_ok else ("warn" if (rdy3 is not None and rdy3 > -0.8) else "bad")
    T.append({"id": "regen", "title": "Regeneracja", "status": "w normie" if regen_ok else "niepełna", "level": lvl,
              "line": "gotowość %s · tętno %s (norma do %s)" % (_pl(rdy3, 2), _pl(rhr7), _pl(rhr_goal)),
              "more": ["Gotowość (średnia 3 dni): %s — w normie od %s. %s" % (_pl(rdy3, 2), _pl(REGEN_RDY3, 1), "✓" if rdy_ok else "✗"),
                       "Tętno spoczynkowe (średnia 7 dni): %s — w normie do %s (start sezonu %s + %s). %s"
                       % (_pl(rhr7), _pl(rhr_goal), _pl(rhr_ref), _pl(REGEN_RHR_MARGIN), "✓" if rhr_ok else "✗"),
                       "To mówi, czy organizm odrobił zmęczenie — niezależnie od miernika mocy."]})
    # 3. po infekcji
    if dai is not None and dai <= 30:
        if dai < AFTER_ILL_EASY_DAYS:
            left = AFTER_ILL_EASY_DAYS - dai
            T.append({"id": "infekcja", "title": "Po infekcji", "status": "dzień %d z %d" % (dai, AFTER_ILL_EASY_DAYS), "level": "warn",
                      "line": "jeszcze %d dni: tylko krótko i spokojnie (do ~%s h)" % (left, _pl(EASY_RIDE_H)),
                      "more": ["Koniec objawów: %s." % _dm(ill_end),
                               "W Twoim sezonie 2 razy (21.05 i 27.09) dłuższa jazda w pierwszych 2 tygodniach po infekcji dała najgłębszy dołek gotowości.",
                               "Do %s bez długich jazd." % _dm(ill_end + dt.timedelta(days=AFTER_ILL_EASY_DAYS))]})
        else:
            T.append({"id": "infekcja", "title": "Po infekcji", "status": "okres ochronny minął", "level": "good",
                      "line": "%d dni od końca infekcji" % dai, "more": ["Koniec objawów: %s." % _dm(ill_end)]})
    # 4. objetosc
    if h4 is not None and tw:
        x = h4 / tw
        lvl = "good" if x >= NORMAL_WEEK_X else ("warn" if x >= 0.6 else "bad")
        T.append({"id": "objetosc", "title": "Objętość", "status": "normalna" if lvl == "good" else "obniżona" if lvl == "warn" else "niska",
                  "level": lvl, "line": "%s h/tydz. (typowo %s h)" % (_pl(h4), _pl(tw)),
                  "more": ["Średnia z 4 ostatnich pełnych tygodni: %s h. Typowy tydzień sezonu (mediana, bez infekcji): %s h." % (_pl(h4), _pl(tw)),
                           "Godziny nie zależą od miernika mocy."]})
    # 5. gotowosc na wyjazd (jak ostatni wyjazd sezonu)
    if ref:
        checks = [
            ("forma jak na starcie wyjazdu %s" % _dm(ref["start"]), ctl is not None and ref["ctl"] is not None and ctl >= ref["ctl"] - FORM_TOL),
            ("regeneracja w normie", regen_ok),
            ("co najmniej %d dni po infekcji" % AFTER_ILL_EASY_DAYS, dai is None or dai >= AFTER_ILL_EASY_DAYS),
            ("co najmniej 1 pełny typowy tydzień (~%s h) po okresie ochronnym" % _pl(tw), dai is None or len(normal_after) >= 1),
        ]
        ok = sum(1 for _, v in checks if v)
        lvl = "good" if ok == len(checks) else ("warn" if ok >= len(checks) - 2 else "bad")
        miss = [n for n, v in checks if not v]
        T.append({"id": "wyjazd", "title": "Wyjazd jak w czerwcu", "status": "gotowy" if lvl == "good" else "jeszcze nie",
                  "level": lvl, "line": ("wszystkie warunki spełnione" if not miss else "brakuje: " + ", ".join(miss)),
                  "more": ["Odniesienie: wyjazd od %s, %d tyg. po %s h." % (_dm(ref["start"]), ref["weeks"], _pl(ref["hours"]))]
                          + [("✓ " if v else "✗ ") + n for n, v in checks]
                          + ["Przed samym startem: kilka luźniejszych dni."]})
    return T


# ======================= WIDOK SEZONU v2 (2026-09-28) =======================
# Odpowiedzi dla kolarza amatora: gdzie jestem (wykres formy + zdarzenia), plan powrotu
# tydzien po tygodniu, najwczesniejszy wyjazd, lekcje sezonu.
WEEK_STEP = 1.15           # tydzien planu <= +15% wzgledem poprzedniego tygodnia planu
LONG_STEP_H = 1.0          # najdluzsza jazda rosnie o max 1 h / tydzien
PLAN_WEEKS = 8


def view(z, fd, rides, ill):
    W, weeks, typical = z["where"], z["weeks"], z["typical_hours"]
    today = dt.date.fromisoformat(z["today"])
    start = dt.date.fromisoformat(W["season_start"])
    full = [w for w in weeks if not w["partial"]]

    # --- wykres formy + zdarzenia ---
    form = [{"day": d.isoformat(), "v": round(float(fd[d]["ctl_xss"]), 1)}
            for d in sorted(fd) if d >= start and fd[d].get("ctl_xss") is not None]
    ev = []
    for ph in _phases(weeks):
        if ph["kind"] != "wyjazd":
            continue
        a = trip_start(ph, rides)
        b0 = dt.date.fromisoformat(ph["weeks"][-1]["week"]) + dt.timedelta(days=6)
        ds = [r["date"] for r in rides if a <= r["date"] <= b0 and (r["duration_s"] or 0) >= TRIP_RIDE_H * 3600]
        b = max(ds) if ds else b0
        ev.append({"kind": "wyjazd", "from": a.isoformat(), "to": b.isoformat(),
                   "label": "wyjazd %s–%s" % (_dm(a), _dm(b)),
                   "hours": round(sum((r["duration_s"] or 0) for r in rides if a <= r["date"] <= b) / 3600.0, 1)})
    ill_s = sorted(d for d in ill if d >= start)
    grp = []
    for d in ill_s:
        if grp and (d - grp[-1][1]).days <= 1:
            grp[-1][1] = d
        else:
            grp.append([d, d])
    for a, b in grp:
        ev.append({"kind": "infekcja", "from": a.isoformat(), "to": b.isoformat(), "label": "infekcja %s–%s" % (_dm(a), _dm(b))})
    for r in rides:
        if r["date"] >= start and (r["duration_s"] or 0) >= 5 * 3600:
            ev.append({"kind": "dluga", "from": r["date"].isoformat(), "to": r["date"].isoformat(),
                       "label": "%s: %s h" % (_dm(r["date"]), _pl((r["duration_s"] or 0) / 3600.0))})

    # --- plan powrotu ---
    T = typical or 0.0
    longs = sorted(w["longest_h"] for w in full if w["type"] not in ("infekcja",) and w["longest_h"])
    L_typ = longs[len(longs) // 2] if longs else 3.0
    ill_end = dt.date.fromisoformat(W["illness_last_end"]) if W["illness_last_end"] else None
    protect_to = (ill_end + dt.timedelta(days=AFTER_ILL_EASY_DAYS)) if ill_end else None
    # punkt wyjscia: FORMA przeliczona na godziny (forma = srednie dzienne obciazenie ~6 tyg.;
    # obciazenie na godzine = mediana z pelnych tygodni sezonu bez infekcji)
    rat = sorted(w["xss"] / w["hours"] for w in full if w["hours"] >= 3 and w["type"] != "infekcja" and w["xss"])
    xss_h = rat[len(rat) // 2] if rat else 55.0
    base_h = ((C_now := W["ctl"]["now"]) or 0) * 7.0 / xss_h if xss_h else T
    prev_h, prev_protect = None, False
    cur = next((w for w in weeks if w["partial"]), None)
    ws = dt.date.fromisoformat(cur["week"]) if cur else today - dt.timedelta(days=today.weekday())
    prev_long = EASY_RIDE_H
    plan, reached, earliest = [], 0, None
    for i in range(PLAN_WEEKS):
        we = ws + dt.timedelta(days=6)
        protect = protect_to is not None and ws <= protect_to
        if prev_h is None or protect or prev_protect:
            # pierwszy tydzien / okres ochronny / pierwszy tydzien po nim: poziom formy
            h = min(T, round(base_h * 2) / 2.0)
        else:
            h = min(T, max(prev_h, round(prev_h * WEEK_STEP * 2) / 2.0))
        if protect:
            h = min(h, 3 * EASY_RIDE_H)
            lng = EASY_RIDE_H
            rule = "po infekcji: tylko krótkie spokojne jazdy (do %s h)" % _pl(EASY_RIDE_H)
            if protect_to < we:
                rule += "; od %s wolno dłużej" % _dm(protect_to + dt.timedelta(days=1))
        else:
            lng = min(L_typ, prev_long + LONG_STEP_H)
            rule = "dalej tylko przy regeneracji w normie; inaczej powtórz poprzedni tydzień"
        prev_long = lng
        is_typ = (not protect) and T and h >= 0.95 * T
        plan.append({"week": ws.isoformat(), "to": we.isoformat(), "hours": h, "long_h": round(lng, 1),
                     "rule": rule, "typical": bool(is_typ), "current": i == 0})
        prev_h, prev_protect = h, protect
        if is_typ:
            reached += 1
            if reached == 1 and earliest is None:
                earliest = we + dt.timedelta(days=1)   # po 1 pelnym typowym tygodniu
        ws += dt.timedelta(days=7)
        if reached >= 2:
            break

    # --- najwczesniejszy wyjazd (jak ostatni wyjazd sezonu) ---
    trip = None
    tr = [e for e in ev if e["kind"] == "wyjazd"]
    if tr:
        t = tr[-1]
        trip = {"ref": t["label"], "ref_hours": t["hours"],
                "earliest": earliest.isoformat() if earliest else None,
                "earliest_txt": (_dm(earliest) if earliest else "poza horyzontem planu"),
                "conditions": ["regeneracja w normie (gotowość ≥ −0,4 i tętno spoczynkowe do %s)" % _pl((W["rhr"]["start_28d"] or 0) + REGEN_RHR_MARGIN),
                               "co najmniej 1 pełny typowy tydzień (~%s h) za Tobą" % _pl(T),
                               "2–3 luźniejsze dni tuż przed startem"]}

    # --- naglowek: jedno zdanie ---
    C = W["ctl"]
    lvl_txt = None
    cand = [d for d in sorted(fd) if start <= d < dt.date.fromisoformat(C["max_day"])
            and fd[d].get("ctl_xss") is not None and float(fd[d]["ctl_xss"]) <= (C["now"] or 0) + 0.5] if C["max_day"] else []
    if cand:
        lvl_txt = _dm(cand[-1])
    n_back = sum(1 for p in plan if not p["typical"])
    head = []
    if lvl_txt:
        head.append("Formę masz na poziomie z %s%s." % (lvl_txt, " — tuż przed czerwcowym wyjazdem" if tr and cand[-1] <= dt.date.fromisoformat(tr[-1]["from"]) and (dt.date.fromisoformat(tr[-1]["from"]) - cand[-1]).days <= 10 else ""))
    if W["days_after_illness"] is not None and W["days_after_illness"] <= 30:
        head.append("Organizm jeszcze wraca po infekcji.")
    if n_back:
        head.append("Plan: %d tyg. stopniowego powrotu do typowego tygodnia (%s h)%s." % (
            n_back, _pl(T), (", wyjazd najwcześniej od %s" % _dm(earliest)) if earliest else ""))

    # --- lekcje (tylko powtorzone wzory) ---
    lessons = (z.get("story") or {}).get("wnioski", [])
    return {"headline": " ".join(head), "form": form, "events": ev, "form_now": C["now"],
            "form_hours": round(base_h, 1), "xss_per_h": round(xss_h, 1),
            "form_peak": {"v": C["max"], "day": C["max_day"]}, "plan": plan, "trip": trip, "lessons": lessons,
            "typical_hours": T, "typical_long_h": L_typ}


# ======================= SEZON v3 (2026-09-28) =======================
# Trzy pytania kolarza: co sie ze mna dzieje / jak prowadze sezon / na co moge liczyc.
# Wydolnosc = moc przy tym samym tetnie (power_meter_guard.p_at_hr_w), bez jazd w kwarantannie
# miernika. Regeneracja = tetno spoczynkowe + gotowosc (niezalezne od miernika). Fazy = TRENER.
CAP_OK, CAP_WARN = -0.03, -0.08     # zmiana mocy przy tetnie: >= -3% bez spadku, >= -8% lekki spadek
RETURN_HOLD_DAYS = 5               # "powrot do normy" = warunki spelnione 5 dni z rzedu
PRE_ILL_DIP = -0.07                 # moc przy tetnie w 5 dni przed infekcja nizsza o >= 7% -> sygnal
LVL = {"good": "good", "bad": "bad", "warn": "warn", "info": "info"}


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def insight(conn, z, fd, rides, ill):
    W, weeks, typical = z["where"], z["weeks"], z["typical_hours"]
    today = dt.date.fromisoformat(z["today"])
    start = dt.date.fromisoformat(W["season_start"])

    def val(d, k):
        r = fd.get(d)
        return float(r[k]) if r and r.get(k) is not None else None

    def rdy(d):
        v = val(d, "readiness_effective")
        return v if v is not None else val(d, "readiness_score")

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    # --- dane dodatkowe ---
    pah = _rows(conn, """SELECT g.ride_date AS d, g.p_at_hr_w AS p FROM qbot_v2.power_meter_guard g
                         WHERE g.ride_date >= %s AND g.p_at_hr_w IS NOT NULL
                           AND NOT EXISTS (SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine q
                                           WHERE q.external_id = g.external_id AND q.released IS NULL)
                         ORDER BY g.ride_date""", (start,))
    pah = [(r["d"], float(r["p"])) for r in pah]
    wts = _rows(conn, "SELECT day AS d, weight_kg AS w FROM qbot_v2.fitmodel_daily WHERE day >= %s AND weight_kg IS NOT NULL ORDER BY day",
                (start,))
    wts = [(r["d"], float(r["w"])) for r in wts]
    goal_w = None
    try:
        g = _rows(conn, "SELECT target, date_to FROM qbot_v2.trainer_goal WHERE kind='weight' AND status='active' ORDER BY id DESC LIMIT 1")
        if g:
            t = g[0]["target"] or {}
            goal_w = {"kg": float(t.get("weight_kg")), "by": g[0]["date_to"].isoformat() if g[0]["date_to"] else None} if t.get("weight_kg") else None
    except Exception:
        goal_w = None

    # --- infekcje (grupy) ---
    ill_s = sorted(ill)
    grp = []
    for d in ill_s:
        if grp and (d - grp[-1][1]).days <= 1:
            grp[-1][1] = d
        else:
            grp.append([d, d])
    last_ill = grp[-1] if grp else None
    recent_ill = last_ill if (last_ill and (today - last_ill[1]).days <= 60) else None

    # ============ 1. CO SIE ZE MNA DZIEJE ============
    now_items = []
    # wydolnosc
    rec = [p for d, p in pah if d > today - dt.timedelta(days=21) and (not recent_ill or d > recent_ill[1])][-4:]
    if recent_ill:
        ref_w = [p for d, p in pah if recent_ill[0] - dt.timedelta(days=21) <= d < recent_ill[0]]
        ref_lbl = "3 tygodnie przed infekcją"
    else:
        ref_w = [p for d, p in pah if today - dt.timedelta(days=81) <= d < today - dt.timedelta(days=21)]
        ref_lbl = "poprzednie 2 miesiące"
    p_now, p_ref = _median(rec), _median(ref_w)
    cap_ch = (p_now / p_ref - 1.0) if (p_now and p_ref) else None
    if cap_ch is not None:
        lvl = "good" if cap_ch >= CAP_OK else ("warn" if cap_ch >= CAP_WARN else "bad")
        now_items.append({"key": "wydolnosc", "title": "Wydolność", "level": lvl,
                          "status": "nie spadła" if lvl == "good" else ("lekko niższa" if lvl == "warn" else "wyraźnie niższa"),
                          "text": "Moc przy tym samym tętnie: teraz %s W, %s %s W (%s%s%%)." % (
                              _pl(p_now, 0), ref_lbl, _pl(p_ref, 0), "+" if cap_ch >= 0 else "", _pl(100 * cap_ch, 0)),
                          "note": "Liczone z ostatnich jazd (bez jazd z wadliwym miernikiem). W chłodzie wynik bywa trochę wyższy."})
    # regeneracja
    rhr7 = mean([val(today - dt.timedelta(days=k), "rhr") for k in range(7)])
    rhr0 = W["rhr"]["start_28d"]
    rhr_max_w = max([w["rhr"] for w in weeks if w["rhr"] is not None and not w["partial"]] or [0])
    rdy3 = mean([rdy(today - dt.timedelta(days=k)) for k in range(3)])
    regen_ok = (rdy3 is not None and rdy3 >= REGEN_RDY3) and (rhr7 is not None and rhr0 is not None and rhr7 <= rhr0 + REGEN_RHR_MARGIN)
    if rhr7 is not None:
        worst = rhr7 >= rhr_max_w - 0.1
        now_items.append({"key": "regeneracja", "title": "Regeneracja", "level": "good" if regen_ok else ("bad" if (rdy3 or 0) <= -0.8 else "warn"),
                          "status": "w normie" if regen_ok else "organizm zmęczony",
                          "text": "Tętno spoczynkowe %s (na starcie sezonu %s)%s, gotowość %s." % (
                              _pl(rhr7), _pl(rhr0), " — najwyżej w sezonie" if worst else "", _pl(rdy3, 2)),
                          "note": "Tętno i gotowość nie zależą od miernika mocy — mówią, czy organizm odrobił zmęczenie."})
    # co dolozylo zmeczenia
    extra = []
    if recent_ill:
        e = recent_ill[1]
        lr = [r for r in rides if e < r["date"] <= e + dt.timedelta(days=AFTER_ILL_EASY_DAYS) and (r["duration_s"] or 0) >= LONG_RIDE_H * 3600]
        if lr:
            r0 = lr[0]
            extra.append("długa jazda %s (%s h), %d dni po infekcji" % (_dm(r0["date"]), _pl((r0["duration_s"] or 0) / 3600.0), (r0["date"] - e).days))
        extra.insert(0, "infekcja %s – %s" % (_dm(recent_ill[0]), _dm(recent_ill[1])))
    h4 = W["hours_week"]["now_4w"]
    if h4 is not None and typical:
        now_items.append({"key": "objetosc", "title": "Jazda", "level": "info",
                          "status": "%s h/tydz." % _pl(h4),
                          "text": "Ostatnie 4 tygodnie średnio %s h, typowo w sezonie %s h." % (_pl(h4), _pl(typical)),
                          "note": "Godziny nie zależą od miernika."})
    last7 = wts[-7:]
    w_now = mean([w for _, w in last7])
    w_now_day = last7[-1][0] if last7 else None
    w_then = mean([w for d, w in wts if w_now_day and w_now_day - dt.timedelta(days=97) <= d < w_now_day - dt.timedelta(days=83)])
    if w_now is not None:
        dw = (w_now - w_then) if w_then is not None else None
        now_items.append({"key": "waga", "title": "Waga", "level": "warn" if (dw is not None and dw >= 1.0) else "info",
                          "status": "%s kg" % _pl(w_now),
                          "text": (("%s%s kg w 3 miesiące" % ("+" if dw >= 0 else "", _pl(dw))) if dw is not None else "brak porównania")
                                  + (" (ostatni pomiar %s)" % _dm(w_now_day) if w_now_day and (today - w_now_day).days > 3 else ""),
                          "note": ("Cel w TRENERZE: %s kg do %s." % (_pl(goal_w["kg"], 0), _dm(dt.date.fromisoformat(goal_w["by"])))) if goal_w and goal_w.get("by") else ""})
    # sygnal przed infekcja
    pre_sig = None
    if recent_ill and p_ref:
        pre = [(d, p) for d, p in pah if recent_ill[0] - dt.timedelta(days=5) <= d < recent_ill[0]]
        dips = [(d, p) for d, p in pre if p / p_ref - 1.0 <= PRE_ILL_DIP]
        if dips:
            pre_sig = "Sygnał przed infekcją: %s moc przy tętnie %s W (%s%% poniżej normy) — kilka dni przed objawami." % (
                ", ".join(_dm(d) for d, _ in dips), "/".join(_pl(p, 0) for _, p in dips), _pl(100 * (min(p for _, p in dips) / p_ref - 1.0), 0))
    # zdanie podsumowania
    cap_ok = cap_ch is not None and cap_ch >= CAP_OK
    if cap_ch is None:
        head = "Za mało wiarygodnych danych mocy, żeby ocenić wydolność."
    elif cap_ok and not regen_ok:
        head = "Formy nie straciłeś — zmęczony jest organizm. Stąd złe samopoczucie."
    elif not cap_ok and not regen_ok:
        head = "Spadła i wydolność, i regeneracja — organizm potrzebuje odpoczynku."
    elif cap_ok and regen_ok:
        head = "Wydolność i regeneracja w normie."
    else:
        head = "Regeneracja w normie, ale moc przy tętnie niższa niż wcześniej."
    if extra and not regen_ok:
        head += " Zmęczenie dołożyły: " + ", ".join(extra) + "."

    # ============ 2. JAK PROWADZE SEZON ============
    full = [w for w in weeks if not w["partial"] and dt.date.fromisoformat(w["week"]) >= start - dt.timedelta(days=6)]
    nonill = [w for w in full if w["type"] != "infekcja"]
    reg = [w for w in nonill if typical and w["hours"] >= LIGHT_X * typical]
    manage = []
    if nonill:
        frac = len(reg) / len(nonill)
        manage.append({"level": "good" if frac >= 0.75 else "warn", "title": "Regularność",
                       "text": "%d z %d tygodni (bez infekcji) z normalną jazdą, typowo %s h." % (len(reg), len(nonill), _pl(typical))})
    st = z.get("story") or {}
    obs = st.get("obserwacje") or []
    ill_obs = [o for o in obs if "po infekcji" in o]
    rebound = [o for o in obs if "lżejszy tydzień" in o]
    if rebound:
        manage.append({"level": "good", "title": "Odpoczynek po dużym wysiłku",
                       "text": "Lżejszy tydzień po wyjeździe / mocnym tygodniu poprawiał gotowość (%s)." % "; ".join(o.split(":")[0] for o in rebound)})
    if ill_obs:
        manage.append({"level": "bad", "title": "Powrót po infekcji",
                       "text": "%s: długa jazda w pierwszych 2 tygodniach po infekcji → najgłębszy dołek gotowości. %s" % (
                           ", ".join(o.split(":")[0] for o in ill_obs),
                           "Powtórzyło się — to Twój najczęstszy błąd." if len(ill_obs) >= 2 else "")})
    if len(wts) >= 20:
        w_first = mean([w for d, w in wts[:14]])
        dws = (w_now - w_first) if (w_now is not None and w_first is not None) else None
        if dws is not None:
            manage.append({"level": "bad" if dws >= 1.0 else ("good" if dws <= -1.0 else "info"), "title": "Waga w sezonie",
                           "text": "Od %s: %s → %s kg (%s%s kg)%s." % (_dm(wts[0][0]), _pl(w_first), _pl(w_now), "+" if dws >= 0 else "", _pl(dws),
                                    (", cel %s kg" % _pl(goal_w["kg"], 0)) if goal_w else "")})
    qd = _rows(conn, "SELECT m.ride_date AS d FROM qbot_v2.fitmodel_ride_quarantine q JOIN qbot_v2.modelq2_ride m ON m.external_id=q.external_id "
                     "WHERE q.released IS NULL AND m.ride_date >= %s ORDER BY m.ride_date", (start,))
    if qd:
        ms = []
        for r in qd:
            nm = MIES_M[r["d"].month - 1]
            if nm not in ms:
                ms.append(nm)
        manage.append({"level": "info", "title": "Dane mocy",
                       "text": "%d jazd z wadliwym pomiarem liczonych z tętna (%s)." % (len(qd), ", ".join(ms))})

    # ============ 3. NA CO MOGE LICZYC ============
    expect = []
    # ile trwal powrot po poprzedniej infekcji (tetno i gotowosc w normie jednoczesnie)
    rhr_goal = (rhr0 + REGEN_RHR_MARGIN) if rhr0 is not None else None
    back_days = None
    def ok_on(d):
        r3 = mean([rdy(d - dt.timedelta(days=j)) for j in range(3)])
        h7 = mean([val(d - dt.timedelta(days=j), "rhr") for j in range(7)])
        return r3 is not None and h7 is not None and rhr_goal is not None and r3 >= REGEN_RDY3 and h7 <= rhr_goal
    for a, b in grp[:-1] if (recent_ill and grp[-1] == recent_ill) else grp:
        for k in range(1, 45):
            d = b + dt.timedelta(days=k)
            if all(ok_on(d + dt.timedelta(days=j)) for j in range(RETURN_HOLD_DAYS)):   # stan utrzymany, nie chwilowe odbicie
                back_days = (k, a, b)
                break
    if back_days:
        k, a, b = back_days
        s = "Po infekcji %s – %s organizm wrócił do normy na stałe po %d dniach od końca objawów." % (_dm(a), _dm(b), k)
        if recent_ill and not regen_ok:
            eta = recent_ill[1] + dt.timedelta(days=k)
            s += " Teraz odpowiada to okolicy %s — jeśli do tego czasu jeździsz spokojnie." % _dm(max(eta, today + dt.timedelta(days=1)))
        expect.append(s)
    if cap_ok:
        expect.append("Wydolność zachowałeś — po odpoczynku wracasz z tego samego poziomu, bez nadrabiania.")
    # fazy TRENERA
    try:
        import qbot_trener_engine as TE
        ovr = _rows(conn, "SELECT overrides FROM qbot_v2.trainer_settings ORDER BY username LIMIT 1")
        ov = (ovr[0]["overrides"] if ovr else None) or {}
        goals = _rows(conn, "SELECT kind, priority, date_from, date_to, status, name FROM qbot_v2.trainer_goal WHERE status='active'")
        sb = TE.season_bounds(today.year, ov, goals)
        nb = TE.season_bounds(today.year + 1, ov, goals)
        if today < sb["roz"]:
            expect.append("TRENER: roztrenowanie od %s, pełny luz od %s, nowy sezon od %s — nie musisz teraz niczego nadrabiać." % (
                _dm(sb["roz"]), _dm(sb["luz"]), _dm(nb["start"])))
        elif today < sb["luz"]:
            expect.append("TRENER: jesteś w roztrenowaniu (do %s), potem pełny luz, nowy sezon od %s." % (_dm(sb["luz"]), _dm(nb["start"])))
        else:
            expect.append("TRENER: pełny luz, nowy sezon od %s." % _dm(nb["start"]))
    except Exception:
        pass

    # --- serie do wykresow ---
    ch_start = today - dt.timedelta(days=120)
    ser_p = [{"day": d.isoformat(), "v": round(p)} for d, p in pah if d >= ch_start]
    ser_r = []
    for i in range(120, -1, -1):
        d = today - dt.timedelta(days=i)
        v = mean([val(d - dt.timedelta(days=j), "rhr") for j in range(7)])
        if v is not None:
            ser_r.append({"day": d.isoformat(), "v": round(v, 1)})
    ser_w = []
    wd = dict(wts)
    for i in range(120, -1, -1):
        d = today - dt.timedelta(days=i)
        v = mean([wd.get(d - dt.timedelta(days=j)) for j in range(7)])
        if v is not None:
            ser_w.append({"day": d.isoformat(), "v": round(v, 1)})
    return {"head": head, "now": now_items, "pre_signal": pre_sig, "manage": manage, "expect": expect,
            "series": {"p_at_hr": ser_p, "p_ref": round(p_ref) if p_ref else None, "rhr7": ser_r, "rhr_ref": rhr0,
                       "rhr_goal": rhr_goal, "weight7": ser_w, "goal_w": goal_w,
                       "ill": [[a.isoformat(), b.isoformat()] for a, b in grp if b >= ch_start]}}


# ======================= SEZON v4: FAKTY (2026-09-28) =======================
# Ogolny obraz sezonu niezalezny od biezacej sytuacji: tydzien po tygodniu od startu sezonu
# do konca roku (przeszlosc = wykonanie, przyszlosc = plan TRENERA), okna -30 / dzis / +30 dni.
# Skrypt TYLKO liczy fakty; interpretacje pisze AI (/api/forma/season/analyze).
WIN_DAYS = 30
TAU_CTL = 42.0
# Serie mocy wg ROWERU (2026-09-28, wg Michala): Grizl mial JEDEN miernik (os Quarq AHP29525) do konca sierpnia;
# FIT raz zapisuje jego ANT id (ant:29525), raz nie ('nieznany') - to ten sam miernik. Od 23.08 nowy pajak Quarq
# (ant:18383) na tym samym rowerze - ta sama seria, znacznik zmiany. Inne id = inny rower / trenazer (osobno).
GRIZL_METERS = {"nieznany", "ant:29525", "ant:18383"}
GRIZL_SPIDER_KEY = "ant:18383"


def _weight_path(last_day, last_w, goal):
    """Liniowa sciezka do celu wagi z TRENERA: funkcja d -> kg (None gdy brak celu)."""
    if not goal or not goal.get("by") or last_w is None:
        return None
    by = dt.date.fromisoformat(goal["by"])
    span = max(1, (by - last_day).days)
    return lambda d: round(last_w + (goal["kg"] - last_w) * min(1.0, max(0.0, (d - last_day).days / span)), 1)


def facts(conn, z, fd, rides, ill):
    W, weeks_s, typical = z["where"], z["weeks"], z["typical_hours"]
    today = dt.date.fromisoformat(z["today"])
    import qbot_trener_engine as TE
    ovr = _rows(conn, "SELECT overrides FROM qbot_v2.trainer_settings ORDER BY username LIMIT 1")
    ov = (ovr[0]["overrides"] if ovr else None) or {}
    goals = _rows(conn, "SELECT kind, priority, date_from, date_to, status, name, target FROM qbot_v2.trainer_goal WHERE status='active'")
    sb = TE.season_bounds(TE.season_of(today, ov), ov, goals)
    start = sb["start"]                              # sezon wg TRENERA (np. 29.12.2025)
    s0 = start - dt.timedelta(days=start.weekday())
    fdl = {r["day"]: r for r in _rows(conn, "SELECT day, ctl_xss, readiness_effective, readiness_score, rhr "
                                            "FROM qbot_v2.fitmodel_daily WHERE day >= %s", (s0 - dt.timedelta(days=7),))}
    rides_all = _rows(conn, "SELECT date, duration_s FROM qbot_v2.training_sessions WHERE sport_type='cycling' AND date >= %s", (s0,))
    # seria dlugich dni (2026-09-28): n-ty kolejny dzien z jazda >= 3 h; od 3. dnia moc przy tetnie bywa wyraznie nizsza
    long_days = {}
    for r in rides_all:
        long_days[r["date"]] = long_days.get(r["date"], 0) + (r["duration_s"] or 0)
    long_set = {d for d, s in long_days.items() if s >= 3 * 3600}

    def series_n(d):
        n = 0
        while d in long_set:
            n += 1
            d = d - dt.timedelta(days=1)
        return n

    def val(d, k):
        r = fdl.get(d)
        return float(r[k]) if r and r.get(k) is not None else None

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    # --- TRENER: fazy + cele ---
    end = sb["end"]
    n_w = ((end - s0).days // 7) + 1
    sw = {w["s"]: w for w in TE.season_weeks(goals, ov, s0, n_w)}
    # sesje zaplanowane
    sess = _rows(conn, "SELECT day, sport, dur_min, xss, name FROM qbot_v2.trainer_session WHERE day >= %s AND day <= %s",
                 (today - dt.timedelta(days=today.weekday()), end))
    # --- dane ---
    pah = _rows(conn, """SELECT g.ride_date AS d, g.p_at_hr_w AS p, COALESCE(g.meter_key, 'nieznany') AS m, g.external_id AS e,
                                EXISTS (SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine q WHERE q.external_id=g.external_id AND q.released IS NULL) AS bad
                         FROM qbot_v2.power_meter_guard g WHERE g.ride_date >= %s AND g.p_at_hr_w IS NOT NULL ORDER BY g.ride_date""", (s0,))
    qdays = {r["d"] for r in _rows(conn, "SELECT m.ride_date AS d FROM qbot_v2.fitmodel_ride_quarantine q JOIN qbot_v2.modelq2_ride m "
                                         "ON m.external_id=q.external_id WHERE q.released IS NULL AND m.ride_date >= %s", (s0,))}
    # okres wady miernika = od pierwszej do ostatniej jazdy w kwarantannie; w nim KAZDY pomiar mocy jest podejrzany
    bad_from, bad_to = (min(qdays), max(qdays)) if qdays else (None, None)
    for r in pah:
        if bad_from and bad_from <= r["d"] <= bad_to:
            r["bad"] = True
    for r in pah:
        r["grizl"] = r["m"] in GRIZL_METERS
    # estymacja z fizyki dla okresu wady miernika (fitmodel/meter_physics.py): P@HR * wzorzec / ratio jazdy
    phys, ref_ratio, ref_n = {}, None, 0
    try:
        from fitmodel import meter_physics as MP
        MP.ensure(conn, s0)
        ref_ratio, ref_n = MP.reference_ratio(conn, bad_from, bad_to)
        phys = {r["e"]: r for r in _rows(conn, "SELECT external_id AS e, ratio AS q, ratio_weak AS qw, n_windows AS n, "
                                                "temp_avg AS ta, temp_max AS tm FROM qbot_v2.meter_phys WHERE ride_date >= %s", (s0,))}
    except Exception:
        phys = {}
    HOT = 30.0
    for r in pah:
        ph = phys.get(r["e"]) or {}
        q, qw = ph.get("q"), ph.get("qw")
        r["n_win"] = int(ph.get("n") or 0)
        r["t_max"] = float(ph["tm"]) if ph.get("tm") is not None and float(ph["tm"]) > -50 else None
        r["t_avg"] = float(ph["ta"]) if ph.get("ta") is not None else None
        r["p_est"] = (float(r["p"]) * ref_ratio / float(q)) if (r["bad"] and q and ref_ratio) else None
        r["p_est_weak"] = (float(r["p"]) * ref_ratio / float(qw)) if (r["bad"] and qw and ref_ratio) else None
    clean_all = [r for r in pah if not r["bad"]]
    cur_m = "Grizl"
    spider_from = min((r["d"] for r in pah if r["m"] == GRIZL_SPIDER_KEY), default=None)
    m_first = spider_from
    wts = [(r["d"], float(r["w"])) for r in _rows(conn, "SELECT day AS d, weight_kg AS w FROM qbot_v2.fitmodel_daily "
                                                        "WHERE day >= %s AND weight_kg IS NOT NULL ORDER BY day", (s0,))]
    goal_w = None
    for g in goals:
        if g["kind"] == "weight" and (g.get("target") or {}).get("weight_kg"):
            goal_w = {"kg": float(g["target"]["weight_kg"]), "by": g["date_to"].isoformat() if g.get("date_to") else None}
    wpath = _weight_path(wts[-1][0], mean([w for _, w in wts[-7:]]), goal_w) if wts else None
    rat = sorted(w["xss"] / w["hours"] for w in weeks_s if not w["partial"] and w["hours"] >= 3 and w["type"] != "infekcja" and w["xss"])
    xss_h = rat[len(rat) // 2] if rat else 55.0
    rhr0 = W["rhr"]["start_28d"]
    rhr_norm = (rhr0 + REGEN_RHR_MARGIN) if rhr0 is not None else None
    wk_by = {dt.date.fromisoformat(w["week"]): w for w in weeks_s}

    # --- tygodnie ---
    rows = []
    ctl = val(today, "ctl_xss") or W["ctl"]["now"]
    ctl_proj = ctl
    cur_ws = today - dt.timedelta(days=today.weekday())
    for i in range(n_w):
        ws = s0 + dt.timedelta(weeks=i)
        we = ws + dt.timedelta(days=6)
        t = sw.get(ws, {})
        ph = t.get("ph")
        w = wk_by.get(ws)
        past = we < today
        ps = [s for s in sess if ws <= s["day"] <= we]
        plan_h = round(sum((s["dur_min"] or 0) for s in ps if s["sport"] == "rower") / 60.0, 1) if ps else (round(t.get("h", 0), 1) if t else None)
        plan_xss = sum(float(s["xss"] or 0) for s in ps) if ps else ((t.get("h", 0) or 0) * xss_h if t else 0)
        p_w = [float(r["p"]) for r in pah if ws <= r["d"] <= we and not r["bad"] and r["grizl"]]
        p_o = [float(r["p"]) for r in pah if ws <= r["d"] <= we and not r["bad"] and not r["grizl"]]
        # caly sezon: dominujacy miernik tygodnia (najwiecej jazd) i mediana z jego jazd
        # seria Grizla (jeden rower, jeden system pomiaru) = glowna seria wydolnosci
        dom_m = ("Grizl (nowy pająk)" if any(r["m"] == GRIZL_SPIDER_KEY for r in pah if ws <= r["d"] <= we and r["grizl"])
                 else "Grizl") if p_w else None
        p_dom = round(_median(p_w)) if p_w else None
        # estymacja tygodnia = srednia WAZONA liczba podjazdow (pewniejsza jazda liczy sie mocniej)
        est_r = [r for r in pah if ws <= r["d"] <= we and r.get("p_est") and r["grizl"]]
        p_e = [r["p_est"] for r in est_r]
        w_sum = sum(r["n_win"] for r in est_r)
        p_est = round(sum(r["p_est"] * r["n_win"] for r in est_r) / w_sum) if w_sum else None
        est_conf = bool(w_sum >= 20)
        weak = [{"d": r["d"].isoformat(), "p": round(r["p_est_weak"]), "n": r["n_win"]} for r in pah
                if ws <= r["d"] <= we and r.get("p_est_weak") and r["grizl"]]
        est_rides = [{"d": r["d"].isoformat(), "p": round(r["p_est"]), "n": r["n_win"],
                      "tmax": r["t_max"]} for r in est_r]
        wk_t = [r for r in pah if ws <= r["d"] <= we]
        tmaxs = [r["t_max"] for r in wk_t if r["t_max"] is not None]
        tavgs = [r["t_avg"] for r in wk_t if r["t_avg"] is not None]
        hot_n = sum(1 for x in tmaxs if x >= HOT)
        series3 = [ws + dt.timedelta(days=k) for k in range(7) if series_n(ws + dt.timedelta(days=k)) >= 3]
        bad_w = bool(bad_from and not (we < bad_from or ws > bad_to))
        wt = [x for d, x in wts if ws <= d <= we]
        hrs = round(sum((r["duration_s"] or 0) for r in rides_all if ws <= r["date"] <= we) / 3600.0, 1) if ws <= today else None
        rh = [val(ws + dt.timedelta(days=k), "rhr") for k in range(7) if ws + dt.timedelta(days=k) <= today]
        rd = [val(ws + dt.timedelta(days=k), "readiness_effective") if val(ws + dt.timedelta(days=k), "readiness_effective") is not None
              else val(ws + dt.timedelta(days=k), "readiness_score") for k in range(7) if ws + dt.timedelta(days=k) <= today]
        row = {"week": ws.isoformat(), "phase": ph, "phase_name": TE.PH_NAME.get(ph, ph) if ph else None,
               "light": bool(t.get("lt")), "past": past, "current": ws == cur_ws,
               "hours": hrs, "plan_h": plan_h if ws >= cur_ws else None,
               "p_at_hr": round(_median(p_w)) if p_w else None, "p_n": len(p_w),
               "p_at_hr_other_meter": round(_median(p_o)) if p_o else None, "meter_bad": bad_w,
               "p_week": p_dom, "p_meter": dom_m,
               "p_est": p_est, "p_est_n": len(p_e), "p_est_windows": w_sum, "p_est_conf": est_conf,
               "p_est_rides": est_rides, "p_est_weak": weak,
               "temp_max": round(max(tmaxs)) if tmaxs else None, "temp_avg": round(sum(tavgs) / len(tavgs)) if tavgs else None,
               "hot_rides": hot_n,
               "series_days": [x.isoformat() for x in series3],
               "series_max": max([series_n(ws + dt.timedelta(days=k)) for k in range(7)] or [0]),
               "p_est_lo": round(p_est * (1 - 0.10)) if p_est else None, "p_est_hi": round(p_est * (1 + 0.10)) if p_est else None,
               "rhr": round(mean(rh), 1) if mean(rh) is not None else None,
               "readiness": round(mean(rd), 2) if mean(rd) is not None else None,
               "weight": round(sum(wt) / len(wt), 1) if wt else None, "weight_path": wpath(we) if (wpath and we > today) else None,
               "ill_days": w["ill_days"] if w else 0, "type": w["type"] if w else None}
        if we <= today:
            row["ctl"] = round(val(we, "ctl_xss"), 1) if val(we, "ctl_xss") is not None else None
        else:
            # prognoza formy wg planu TRENERA (EWMA 42 dni, dzienne XSS = plan tygodnia / 7)
            d0 = max(ws, today + dt.timedelta(days=1))
            for k in range((we - d0).days + 1):
                ctl_proj = ctl_proj + (plan_xss / 7.0 - ctl_proj) / TAU_CTL
            row["ctl_proj"] = round(ctl_proj, 1)
        rows.append(row)

    # --- okna -30 / dzis / +30 ---
    def phase_on(d):
        ws = d - dt.timedelta(days=d.weekday())
        t = sw.get(ws)
        return TE.PH_NAME.get(t["ph"], t["ph"]) if t and t.get("ph") else None

    def hours_4w(d):
        a = d - dt.timedelta(days=d.weekday()) - dt.timedelta(weeks=4)
        b = d - dt.timedelta(days=d.weekday()) - dt.timedelta(days=1)
        return round(sum((r["duration_s"] or 0) for r in rides_all if a <= r["date"] <= b) / 3600.0 / 4.0, 1)

    def win(d):
        fut = d > today
        rec = {"date": d.isoformat(), "future": fut, "phase": phase_on(d)}
        if not fut:
            rec["hours_week"] = hours_4w(d)
            rec["ctl"] = round(val(d, "ctl_xss"), 1) if val(d, "ctl_xss") is not None else None
            p = [float(r["p"]) for r in pah if d - dt.timedelta(days=28) <= r["d"] <= d and not r["bad"] and r["grizl"]]
            rec["p_at_hr"] = round(_median(p)) if p else None
            rec["p_at_hr_n"] = len(p)
            rec["rhr7"] = round(mean([val(d - dt.timedelta(days=j), "rhr") for j in range(7)]), 1) if mean([val(d - dt.timedelta(days=j), "rhr") for j in range(7)]) else None
            rec["readiness7"] = round(mean([val(d - dt.timedelta(days=j), "readiness_effective") for j in range(7)]), 2) if mean([val(d - dt.timedelta(days=j), "readiness_effective") for j in range(7)]) is not None else None
            ww = [x for dd, x in wts if dd <= d][-7:]
            rec["weight"] = round(sum(ww) / len(ww), 1) if ww else None
        else:
            wsd = d - dt.timedelta(days=d.weekday())
            r = next((x for x in rows if x["week"] == wsd.isoformat()), None)
            rec["hours_week_plan"] = r["plan_h"] if r else None
            rec["ctl_proj"] = r.get("ctl_proj") if r else None
            rec["weight_path"] = wpath(d) if wpath else None
        return rec
    windows = [win(today - dt.timedelta(days=WIN_DAYS)), win(today), win(today + dt.timedelta(days=WIN_DAYS))]

    # --- trendy (fakty do analizy) ---
    clean = [(r["d"], float(r["p"])) for r in pah if not r["bad"] and r["grizl"]]
    # seria Grizla: ostatnie 3 tyg. vs te same 3 tyg. przed okresem wady miernika i vs szczyt sezonu (mediana 4 tyg.)
    p8 = [p for d, p in clean if d > today - dt.timedelta(weeks=3)]
    p8b = [p for d, p in clean if bad_from and bad_from - dt.timedelta(weeks=4) <= d < bad_from]
    guard_alerts = [r["d"].isoformat() for r in _rows(conn, "SELECT ride_date AS d FROM qbot_v2.power_meter_guard "
                    "WHERE verdict='ALERT' AND ride_date >= %s ORDER BY ride_date", (s0,))]
    rhr_above = sum(1 for k in range(14) if rhr_norm and val(today - dt.timedelta(days=k), "rhr") is not None
                    and val(today - dt.timedelta(days=k), "rhr") > rhr_norm)
    trends = {"p_at_hr_last_3w": round(_median(p8)) if p8 else None, "p_at_hr_4w_before_meter_fault": round(_median(p8b)) if p8b else None,
              "p_at_hr_n": [len(p8), len(p8b)], "series": "Grizl", "spider_change": spider_from.isoformat() if spider_from else None,
              "p_at_hr_note": ("jedna seria Grizla przez caly sezon; od spider_change nowy pajak Quarq (ta sama os/rower, "
                               "mozliwa roznica kalibracji ok. 1-2%). Straznik zglaszal odchylenia miernika juz przed okresem "
                               "kwarantanny: guard_alert_days."),
              "guard_alert_days": guard_alerts,
              "phys_ref_ratio": ref_ratio, "phys_ref_n": ref_n,
              "phys_note": ("p_est = estymacja wydolnosci w okresie wady z fizyki na podjazdach (moc z miernika skorygowana "
                            "o stosunek do mocy z grawitacji), srednia wazona liczba podjazdow, dokladnosc ok. +-10%. "
                            "p_est_conf=false (<20 podjazdow w tygodniu) = niska pewnosc. hot_rides = jazdy z max >= 30 C "
                            "(upal podnosi tetno przy tych samych watach -> nizsza moc przy tetnie). Analiza z fizyki (21 jazd): "
                            "przy 18-22 C +6%, powyzej ~24 C srednio -5..-10% wzgledem normy. series_days = 3. i dalszy "
                            "kolejny dzien jazdy >= 3 h - moc przy tetnie bywa nizsza (np. 3.08 -19%). Pojedyncza jazda ma "
                            "rozrzut ok. +-15% - nie wnioskuj o formie z jednej goracej jazdy ani z 3. dnia wyjazdu."), "rhr_days_above_norm_14d": rhr_above, "rhr_norm": rhr_norm,
              "weight_last": wts[-1][1] if wts else None, "weight_last_day": wts[-1][0].isoformat() if wts else None,
              "weight_goal": goal_w, "typical_hours": typical, "xss_per_h": round(xss_h, 1)}
    planned = [{"day": s["day"].isoformat(), "name": s["name"], "sport": s["sport"], "min": s["dur_min"], "xss": float(s["xss"] or 0)}
               for s in sorted(sess, key=lambda s: s["day"]) if s["day"] >= today]
    gl = [{"name": g["name"], "kind": g["kind"], "priority": g["priority"],
           "from": g["date_from"].isoformat() if g.get("date_from") else None,
           "to": g["date_to"].isoformat() if g.get("date_to") else None, "target": g.get("target")} for g in goals]
    return {"weeks": rows, "windows": windows, "trends": trends, "trainer": {
                "season": {"start": sb["start"].isoformat(), "roz": sb["roz"].isoformat(), "luz": sb["luz"].isoformat(),
                           "end": end.isoformat(), "next_start": TE.season_bounds(today.year + 1, ov, goals)["start"].isoformat()},
                "planned_sessions": planned, "goals": gl},
            "events": (z.get("view") or {}).get("events", []),
            "meter_bad_period": [bad_from.isoformat(), bad_to.isoformat()] if bad_from else None,
            "meter_note": ("W okresie meter_bad_period pomiar mocy byl wadliwy: wydolnosc (moc przy tetnie) z tego okresu "
                           "pominieta, a obciazenie jazd w kwarantannie liczone z tetna. Wydolnosc tylko z czystych jazd.")}


# ======================= SYGNALY DLA TRENERA (2026-09-28) =======================
def trainer_signals(conn, today: dt.date | None = None) -> dict:
    """Lekkie sygnaly z Sezonu dla qbot_trener_engine.plan_week (bez pelnego build()):
    - okres ochronny po infekcji: AFTER_ILL_EASY_DAYS dni od konca ostatniej infekcji (u Michala 2x dluga jazda
      w tym okresie = najglebszy dolek gotowosci: 21.05 i 27.09.2026),
    - regeneracja: gotowosc (srednia 3 dni) >= REGEN_RDY3 i tetno spocz. (7 dni) <= start sezonu + REGEN_RHR_MARGIN,
    - skok obciazenia dzis (load_ramp 7/28 dni).
    Te same progi co kafle/tabela zakladki Sezon."""
    today = today or dt.date.today()
    out = {"today": today.isoformat(), "easy_max_min": int(EASY_RIDE_H * 60), "protect_days": AFTER_ILL_EASY_DAYS}
    r = _rows(conn, "SELECT day, COALESCE(end_day, day) AS e FROM qbot_v2.calendar_entry WHERE kind='illness' AND day <= %s "
                    "ORDER BY COALESCE(end_day, day) DESC LIMIT 1", (today,))
    if r:
        ill_end = r[0]["e"]
        prot = ill_end + dt.timedelta(days=AFTER_ILL_EASY_DAYS)
        if prot >= today:
            out.update({"ill_start": r[0]["day"].isoformat(), "ill_end": ill_end.isoformat(), "protect_to": prot.isoformat()})
    start = dt.date(today.year, 3, 1)
    if today < start:
        start = dt.date(today.year - 1, 3, 1)
    fd = {x["day"]: x for x in _rows(conn, "SELECT day, rhr, readiness_effective, readiness_score, load_ramp FROM qbot_v2.fitmodel_daily "
                                             "WHERE (day >= %s AND day < %s) OR day > %s", (start, start + dt.timedelta(days=28), today - dt.timedelta(days=8)))}

    def m(vals):
        vals = [float(v) for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None
    rhr0 = m([fd[d]["rhr"] for d in fd if start <= d < start + dt.timedelta(days=28)])
    rhr7 = m([(fd.get(today - dt.timedelta(days=k)) or {}).get("rhr") for k in range(7)])
    rdy3 = m([((fd.get(today - dt.timedelta(days=k)) or {}).get("readiness_effective")
               if (fd.get(today - dt.timedelta(days=k)) or {}).get("readiness_effective") is not None
               else (fd.get(today - dt.timedelta(days=k)) or {}).get("readiness_score")) for k in range(3)])
    norm = (rhr0 + REGEN_RHR_MARGIN) if rhr0 is not None else None
    ok = (rdy3 is not None and rdy3 >= REGEN_RDY3) and (rhr7 is not None and norm is not None and rhr7 <= norm)
    out["regen"] = {"ok": bool(ok), "rdy3": round(rdy3, 2) if rdy3 is not None else None,
                    "rhr7": round(rhr7, 1) if rhr7 is not None else None, "rhr_norm": round(norm, 1) if norm is not None else None}
    lr = next((fd[d]["load_ramp"] for d in sorted(fd, reverse=True) if d <= today and fd[d].get("load_ramp") is not None), None)
    out["load_ramp"] = round(float(lr), 2) if lr is not None else None
    return out
