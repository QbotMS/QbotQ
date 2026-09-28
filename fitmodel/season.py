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
    z = {"today": today.isoformat(), "where": where, "weeks": weeks, "typical_hours": typical, "status": status}
    try:
        z["story"] = story(z, fd, [r for r in rides if r["date"] >= start], ill)
    except Exception as exc:   # opis nie moze zablokowac danych
        z["story"] = {"error": str(exc)}
    try:
        z["view"] = view(z, fd, [r for r in rides if r["date"] >= start], ill)
    except Exception as exc:
        z["view"] = {"error": str(exc)}
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
