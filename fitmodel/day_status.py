from __future__ import annotations

"""Status dnia (2026-09-29) - jeden wspolny werdykt dla Dziennika, Alberta i TRENERA.

Laczy ORGANIZM (trend, nie jedna noc) z OBCIAZENIEM (jak "przeciazenie" w Garminie):
  gotowosc_3d  = srednia gotowosci z 3 dni (readiness_effective, zapas readiness_score)
  zmeczony_org = histereza na gotowosc_3d: wejscie <= TIRED_IN (-0.4), wyjscie dopiero > TIRED_OUT (-0.2)
  tetno_wysokie= tetno spoczynkowe (srednia 7 dni) > norma (srednia z 28 dni od startu sezonu 1.03) + RHR_MARGIN
  po_infekcji  = <= AFTER_ILL_DAYS dni od konca infekcji z Kalendarza
  skok         = load_ramp (sr. obciazenie 7 dni / 28 dni) >= RAMP_HIGH (1.3)
Status:
  przeciazenie : skok  I  (zmeczony_org LUB tetno_wysokie LUB po_infekcji)
  zmeczony     : zmeczony_org LUB tetno_wysokie
  uwaga        : sam skok albo sam okres po infekcji
  w_normie     : reszta
Dodatkowo early_warn: gotowosc_3d <= TIRED_IN przy MALYM obciazeniu (skok < 0.9, bez jazdy >= 3 h w 3 dniach)
  -> "organizm slabnie bez powodu w obciazeniu - mozliwy poczatek infekcji" (w 2026 wyprzedzilo obie infekcje o 5-6 dni).
Walidacja (sezon 2026, 3.2026-9.2026): okno 3 dni + histereza -0.4/-0.2: 22 przelaczenia, 1 epizod 1-2 dniowy (szum)
zamiast 5, oba sygnaly przed infekcja zachowane. Okna 4-5 dni gubia ostrzezenia, 6-8 dni stabilne ale spoznione.
Liczone po CALEJ historii (histereza wymaga stanu dnia poprzedniego); wolane z apply_hidden_fatigue.
"""

import datetime as dt

TIRED_IN, TIRED_OUT = -0.4, -0.2
RHR_MARGIN = 1.0
AFTER_ILL_DAYS = 14
RAMP_HIGH = 1.3
EW_RAMP_MAX, EW_LONG_H = 0.9, 3.0

LABEL = {"przeciazenie": "przeciążenie", "zmeczony": "zmęczony", "uwaga": "uwaga", "w_normie": "w normie"}
ADVICE = {"przeciazenie": "Przeciążenie — dziś wolne albo bardzo lekko (do ~1 h spokojnie).",
          "zmeczony": "Organizm zmęczony — lekko albo wolne.",
          "uwaga": "Uwaga — jedź spokojnie, bez akcentów.",
          "w_normie": "W normie — trening wg planu."}


def classify(r3_tired: bool, rhr_high: bool, post_ill: bool, ramp) -> str:
    """Czysta funkcja - status dnia z sygnalow."""
    jump = ramp is not None and ramp >= RAMP_HIGH
    body = r3_tired or rhr_high
    if jump and (body or post_ill):
        return "przeciazenie"
    if body:
        return "zmeczony"
    if jump or post_ill:
        return "uwaga"
    return "w_normie"


def why_text(r3, r3_tired, rhr7, norm, post_ill_day, ramp, early) -> str:
    bits = []
    if ramp is not None and ramp >= RAMP_HIGH:
        bits.append("skok obciążenia ×%s" % ("%.2f" % ramp).replace(".", ","))
    if r3 is not None and r3_tired:
        bits.append("gotowość z 3 dni %s" % ("%+.2f" % r3).replace(".", ","))
    if rhr7 is not None and norm is not None and rhr7 > norm:
        bits.append("tętno spocz. %s > norma %s" % (("%.1f" % rhr7).replace(".", ","), ("%.1f" % norm).replace(".", ",")))
    if post_ill_day is not None:
        bits.append("%d. dzień po infekcji" % post_ill_day)
    if early:
        bits.append("organizm słabnie bez powodu w obciążeniu — możliwy początek infekcji")
    return "; ".join(bits)


def apply_day_status(conn) -> dict:
    cur = conn.cursor()
    cur.execute("ALTER TABLE qbot_v2.fitmodel_daily ADD COLUMN IF NOT EXISTS readiness_3d NUMERIC, "
                "ADD COLUMN IF NOT EXISTS day_status TEXT, ADD COLUMN IF NOT EXISTS day_status_note TEXT, "
                "ADD COLUMN IF NOT EXISTS early_warn BOOLEAN")
    conn.commit()
    cur.execute("SELECT day, readiness_effective, readiness_score, rhr, load_ramp FROM qbot_v2.fitmodel_daily ORDER BY day")
    rows = cur.fetchall()
    rows = [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in rows]
    if not rows:
        return {"updated": 0}
    cur.execute("SELECT day, COALESCE(end_day, day) FROM qbot_v2.calendar_entry WHERE kind='illness'")
    ill = [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in cur.fetchall()]
    ill_end = sorted({b for a, b in ill})
    ill_set = set()
    for a, b in ill:
        d = a
        while d <= b:
            ill_set.add(d); d += dt.timedelta(days=1)
    cur.execute("SELECT date, sum(duration_s) FROM qbot_v2.training_sessions WHERE sport_type='cycling' GROUP BY date")
    long_days = {r[0] if not isinstance(r, dict) else r["date"]: float((r[1] if not isinstance(r, dict) else r["sum"]) or 0)
                 for r in cur.fetchall()}
    by = {d: (re, rs, rh, lr) for d, re, rs, rh, lr in rows}

    def rdy(d):
        v = by.get(d)
        if not v:
            return None
        x = v[0] if v[0] is not None else v[1]
        return float(x) if x is not None else None

    norm_cache = {}

    def rhr_norm(d):
        y = d.year if d >= dt.date(d.year, 3, 1) else d.year - 1
        if y not in norm_cache:
            s = dt.date(y, 3, 1)
            vals = [float(by[s + dt.timedelta(days=k)][2]) for k in range(28)
                    if (s + dt.timedelta(days=k)) in by and by[s + dt.timedelta(days=k)][2] is not None]
            norm_cache[y] = (sum(vals) / len(vals) + RHR_MARGIN) if len(vals) >= 10 else None
        return norm_cache[y]

    tired = False
    n = 0
    stats = {}
    for d, _re, _rs, _rh, lr in rows:
        r3v = [rdy(d - dt.timedelta(days=k)) for k in range(3)]
        r3v = [x for x in r3v if x is not None]
        r3 = sum(r3v) / len(r3v) if r3v else None
        if r3 is not None:
            if not tired and r3 <= TIRED_IN:
                tired = True
            elif tired and r3 > TIRED_OUT:
                tired = False
        rh = [float(by[d - dt.timedelta(days=k)][2]) for k in range(7)
              if (d - dt.timedelta(days=k)) in by and by[d - dt.timedelta(days=k)][2] is not None]
        rhr7 = sum(rh) / len(rh) if len(rh) >= 3 else None
        norm = rhr_norm(d)
        rhr_high = bool(rhr7 is not None and norm is not None and rhr7 > norm)
        past = [e for e in ill_end if e <= d]
        pid = None
        if d in ill_set:
            pid = 0
        elif past and (d - past[-1]).days <= AFTER_ILL_DAYS:
            pid = (d - past[-1]).days
        post_ill = pid is not None
        ramp = float(lr) if lr is not None else None
        st = classify(tired and r3 is not None, rhr_high, post_ill, ramp)
        recent_long = any(long_days.get(d - dt.timedelta(days=k), 0) >= EW_LONG_H * 3600 for k in range(3))
        early = bool(r3 is not None and r3 <= TIRED_IN and (ramp is None or ramp < EW_RAMP_MAX)
                     and not recent_long and d not in ill_set and not post_ill)
        note = why_text(r3, tired, rhr7, norm, pid if pid else None, ramp, early)
        cur.execute("UPDATE qbot_v2.fitmodel_daily SET readiness_3d=%s, day_status=%s, day_status_note=%s, early_warn=%s WHERE day=%s",
                    (round(r3, 3) if r3 is not None else None, st, note or None, early, d))
        n += 1
        stats[st] = stats.get(st, 0) + 1
    conn.commit()
    return {"updated": n, "statusy": stats}
