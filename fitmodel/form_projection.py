"""Prognoza formy na dzien jazdy (CTL/ATL/TSB rano w dniu jazdy).

Zrodla i wzor 1:1 z ModelQ v2 (zweryfikowane 2026-09-23: odtworzenie historii z 1-28 dni
wstecz = dokladnie wartosci fitmodel_daily, blad kroku dziennego <= 0.09):
  - stan startowy: qbot_v2.fitmodel_daily (ctl_xss, atl_raw) z ostatniego policzonego dnia,
  - obciazenie dnia: SUM(qbot_v2.modelq2_ride.xss_total) po ride_date (kanon MQ2),
  - krok: CTL += (x - CTL)/TAU_TL, ATL += (x - ATL)/TAU_RL (fitmodel.modelq2.training_load).
Dni do jazdy wypelniane dwoma wariantami:
  - "jak_dotad": srednie dzienne obciazenie z ostatnich LOOKBACK dni (lacznie z dniami wolnymi),
  - "odpoczynek": 0 XSS.
Dni z wpisem w qbot_v2.planned_load_daily (np. planer wyprawy) maja pierwszenstwo w obu wariantach,
potem JAZDY Z KALENDARZA (wydarzenie z przypieta trasa albo event_type='jazda'): XSS z notatki (~N XSS),
a gdy brak - km (z notatki albo dlugosci trasy) x Twoj sredni XSS/km z ostatnich 120 dni.
Stan "rano w dniu jazdy" = stan po ostatnim dniu PRZED jazda (dzien jazdy jeszcze bez obciazenia).
Nie zapisuje niczego.
"""
from __future__ import annotations

import datetime as _dt

from fitmodel.modelq2.training_load import TAU_TL, TAU_RL

LOOKBACK_DAYS = 14


def _r(x, d=1):
    return None if x is None else round(float(x), d)


import re as _re

_XSS_RE = _re.compile(r"~\s*([0-9]+)\s*XSS", _re.I)
_KM_RE = _re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*km", _re.I)


def _vals(r):
    return list(r.values()) if isinstance(r, dict) else list(r)


def _xss_per_km(conn, last) -> float | None:
    a = last - _dt.timedelta(days=120)
    x = _vals(conn.execute("SELECT COALESCE(SUM(xss_total),0) FROM qbot_v2.modelq2_ride WHERE ride_date BETWEEN %s AND %s", (a, last)).fetchone())[0]
    k = _vals(conn.execute("SELECT COALESCE(SUM(distance_m),0)/1000.0 FROM qbot_v2.training_sessions WHERE sport_type IN "
                           "('cycling','gravel_cycling','road_biking','mountain_biking') AND date BETWEEN %s AND %s", (a, last)).fetchone())[0]
    return (float(x) / float(k)) if k and float(k) > 50 else None


def calendar_rides(conn, after, before) -> dict:
    """{dzien: {"xss", "zrodlo", "nazwa"}} dla jazd z kalendarza w (after, before) - bez obu granic."""
    rows = []
    try:
        rows += [dict(zip(("day", "note", "title", "route_id"), _vals(r))) for r in conn.execute(
            "SELECT r.day, e.note, e.title, r.route_id FROM qbot_v2.calendar_day_route r JOIN qbot_v2.calendar_entry e ON e.id=r.entry_id "
            "WHERE r.day > %s AND r.day < %s", (after, before)).fetchall()]
        rows += [dict(zip(("day", "note", "title", "route_id"), _vals(r))) for r in conn.execute(
            "SELECT e.day, e.note, e.title, NULL FROM qbot_v2.calendar_entry e WHERE e.kind='event' AND e.event_type='jazda' "
            "AND e.day > %s AND e.day < %s AND NOT EXISTS (SELECT 1 FROM qbot_v2.calendar_day_route r WHERE r.entry_id=e.id)",
            (after, before)).fetchall()]
    except Exception:
        return {}
    xpk = None
    out = {}
    for r in rows:
        note = r.get("note") or ""
        m = _XSS_RE.search(note)
        xss, zr = (float(m.group(1)), "kalendarz (XSS z notatki)") if m else (None, None)
        if xss is None:
            mk = _KM_RE.search(note)
            km = float(mk.group(1).replace(",", ".")) if mk else None
            if km is None and r.get("route_id"):
                rb = conn.execute("SELECT distance_m FROM qbot_v2.route_base WHERE route_id=%s ORDER BY updated_at DESC LIMIT 1",
                                  (r["route_id"],)).fetchone()
                km = (float(_vals(rb)[0]) / 1000.0) if rb and _vals(rb)[0] else None
            if km:
                if xpk is None:
                    xpk = _xss_per_km(conn, after) or 2.5
                xss, zr = km * xpk, "kalendarz (szac. z %.0f km)" % km
        if xss is None:
            continue
        d = r["day"]
        prev = out.get(d)
        out[d] = {"xss": (prev["xss"] if prev else 0.0) + xss, "zrodlo": zr, "nazwa": (r.get("title") or "jazda")[:80]}
    return out


def project_form(conn, target_date, lookback_days: int = LOOKBACK_DAYS) -> dict | None:
    if isinstance(target_date, str):
        target_date = _dt.date.fromisoformat(target_date[:10])
    row = conn.execute("SELECT day, ctl_xss, atl_raw FROM qbot_v2.fitmodel_daily "
                       "WHERE ctl_xss IS NOT NULL AND atl_raw IS NOT NULL ORDER BY day DESC LIMIT 1").fetchone()
    if not row:
        return None
    row = list(row.values()) if isinstance(row, dict) else list(row)
    last, ctl0, atl0 = row[0], float(row[1]), float(row[2])
    out = {"metoda": "ModelQ v2 (CTL/42, ATL/7), obciazenie z modelq2_ride",
           "stan_na": str(last), "dzis": {"ctl": _r(ctl0), "atl": _r(atl0), "tsb": _r(ctl0 - atl0)},
           "dzien_jazdy": str(target_date), "okno_dni": lookback_days}
    # jazda w przeszlosci / dzis: stan historyczny rano tego dnia (z dnia poprzedniego)
    if target_date <= last:
        prev = target_date - _dt.timedelta(days=1)
        h = conn.execute("SELECT ctl_xss, atl_raw FROM qbot_v2.fitmodel_daily WHERE day=%s", (prev,)).fetchone()
        if h:
            h = list(h.values()) if isinstance(h, dict) else list(h)
            c, a = float(h[0]), float(h[1])
            out.update({"typ": "historia", "dni_do_jazdy": (target_date - last).days,
                        "warianty": {"stan": {"ctl": _r(c), "atl": _r(a), "tsb": _r(c - a)}}})
            return out
        out.update({"typ": "brak_historii"})
        return out
    since = last - _dt.timedelta(days=lookback_days - 1)
    xs = conn.execute("SELECT ride_date, SUM(xss_total) FROM qbot_v2.modelq2_ride "
                      "WHERE ride_date BETWEEN %s AND %s GROUP BY ride_date", (since, last)).fetchall()
    tot = 0.0
    n_rides = 0
    for r in xs:
        v = list(r.values())[1] if isinstance(r, dict) else r[1]
        tot += float(v or 0.0)
        n_rides += 1 if v else 0
    avg = tot / float(lookback_days)
    planned, src = {}, {}
    try:
        for r in conn.execute("SELECT day, SUM(xss) FROM qbot_v2.planned_load_daily "
                              "WHERE day > %s AND day < %s GROUP BY day", (last, target_date)).fetchall():
            v = list(r.values()) if isinstance(r, dict) else list(r)
            planned[v[0]] = float(v[1] or 0.0)
            src[v[0]] = {"xss": _r(v[1]), "zrodlo": "planer wyprawy", "nazwa": None}
    except Exception:
        planned = {}
    for d, cr in calendar_rides(conn, last, target_date).items():
        if d not in planned:
            planned[d] = float(cr["xss"])
            src[d] = {"xss": _r(cr["xss"]), "zrodlo": cr["zrodlo"], "nazwa": cr["nazwa"]}
    var = {}
    for name, fill in (("jak_dotad", avg), ("odpoczynek", 0.0)):
        c, a = ctl0, atl0
        d = last
        while d < target_date - _dt.timedelta(days=1):
            d += _dt.timedelta(days=1)
            x = planned.get(d, fill)
            c += (x - c) / TAU_TL
            a += (x - a) / TAU_RL
        var[name] = {"ctl": _r(c), "atl": _r(a), "tsb": _r(c - a), "obciazenie_dzienne": _r(fill)}
    out.update({"typ": "prognoza", "dni_do_jazdy": (target_date - last).days,
                "srednie_obciazenie_14d": _r(avg), "jazd_w_oknie": n_rides,
                "dni_zaplanowane": {str(k): src.get(k) for k in sorted(planned)},
                "warianty": var})
    return out
