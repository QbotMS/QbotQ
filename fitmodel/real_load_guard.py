from __future__ import annotations

"""Straznik korekty ciala (2026-09-29) - TYLKO POWIADOMIENIA, niczego nie zmienia.

Pilnuje faktycznego zmeczenia/swiezosci (fitmodel/real_load.py). Gdy pojawia sie sygnal, ze korekta ze stanu ciala
moze sie rozjezdzac, wysyla jedna wiadomosc na Telegram ("do analizy w sesji"). Kody:
  SILA        |zmeczenie_faktyczne - zmeczenie z treningow| > STRENGTH_MAX * forma
  DANE        < 2 sygnaly ciala w wyliczeniu, albo brak Body Battery / tetna spocz. od >= STALE_DAYS dni
  DOMINACJA   jeden skladnik daje > DOMINANCE czesci korekty (|skladnik| >= 1.0), a pozostale sa w normie (|x| <= 0.3)
  ROZBIEZNOSC |swiezosc faktyczna - swiezosc treningowa (TSB+)| > DIVERGE_PTS przez >= DIVERGE_DAYS dni z rzedu,
              poza infekcja i 14 dniami po niej
Deduplikacja: ten sam kod najwyzej raz na REPEAT_DAYS dni (tabela qbot_v2.real_load_guard_log).
check(conn, day) jest czysta wzgledem bazy (tylko odczyt) - uzywana tez do testu wstecznego.
"""

import datetime as dt
import json

STRENGTH_MAX = 0.60
STALE_DAYS = 2
DOMINANCE = 0.60
DIVERGE_PTS, DIVERGE_DAYS = 15.0, 7
REPEAT_DAYS = 7
ILL_TAIL = 14
DOMINANCE_DAYS = 3          # dominacja musi sie utrzymac tyle dni z rzedu (pojedynczy dzien Body Battery = szum)
SERIES_LONG_H = 3.0         # dni z jazda >= 3 h: znana przyczyna mocnej korekty (wyjazd) -> SILA milczy


def _t(rows):
    return [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in rows]


def check(conn, day: dt.date) -> list:
    cur = conn.cursor()
    cur.execute("SELECT day, atl_raw, ctl_xss, atl_real, tsb_real, tsb_plus, body_load_parts, rhr FROM qbot_v2.fitmodel_daily "
                "WHERE day BETWEEN %s AND %s ORDER BY day", (day - dt.timedelta(days=DIVERGE_DAYS + 3), day))
    rows = {r[0]: r for r in _t(cur.fetchall())}
    r = rows.get(day)
    if not r or r[3] is None:
        return []
    atl, ctl, atl_f, tsb_f, tsb_p, parts_s, rhr = [r[i] for i in range(1, 8)]
    parts = json.loads(parts_s) if parts_s else {}
    out = []
    # znane przyczyny mocnej korekty: infekcja (+14 dni) albo seria dlugich jazd (>= 2 dni z rzedu >= 3 h)
    cur.execute("SELECT day, COALESCE(end_day, day) FROM qbot_v2.calendar_entry WHERE kind='illness' AND day <= %s", (day,))
    ill_until = max([b for a, b in _t(cur.fetchall())], default=None)
    in_ill = bool(ill_until and (day - ill_until).days <= ILL_TAIL)
    cur.execute("SELECT date, sum(duration_s) FROM qbot_v2.training_sessions WHERE sport_type='cycling' AND date BETWEEN %s AND %s GROUP BY 1",
                (day - dt.timedelta(days=4), day))
    lng = {d for d, sd in _t(cur.fetchall()) if (sd or 0) >= SERIES_LONG_H * 3600}
    in_series = sum(1 for k in range(5) if (day - dt.timedelta(days=k)) in lng) >= 2
    # SILA
    if not in_ill and not in_series and ctl and atl is not None and abs(float(atl_f) - float(atl)) > STRENGTH_MAX * float(ctl):
        out.append(("SILA", "korekta ciała %+.0f przy formie %.0f (>%d%% formy)" % (float(atl_f) - float(atl), float(ctl), STRENGTH_MAX * 100)))
    # DANE
    body = [k for k in ("gotowosc_3d", "tetno", "body_battery") if k in parts]
    cur.execute("SELECT max(date) FROM qbot_v2.qbot_wellness_daily WHERE body_battery_start IS NOT NULL AND date <= %s", (day,))
    bb_last = _t(cur.fetchall())[0][0]
    rhr_days = [d for d, x in rows.items() if x[7] is not None and d <= day]
    rhr_last = max(rhr_days) if rhr_days else None
    stale = []
    if bb_last is None or (day - bb_last).days >= STALE_DAYS:
        stale.append("Body Battery (ostatnie %s)" % (bb_last.strftime("%d.%m") if bb_last else "brak"))
    if rhr_last is None or (day - rhr_last).days >= STALE_DAYS:
        stale.append("tętno spocz. (ostatnie %s)" % (rhr_last.strftime("%d.%m") if rhr_last else "brak"))
    if len(body) < 2 or stale:
        out.append(("DANE", "sygnały ciała w wyliczeniu: %d z 3%s" % (len(body), ("; nieświeże: " + ", ".join(stale)) if stale else "")))
    # DOMINACJA (utrzymana DOMINANCE_DAYS dni z rzedu, ten sam skladnik)
    def dom(dd):
        x = rows.get(dd)
        if not x or not x[6]:
            return None
        pp = json.loads(x[6])
        comp = {k: float(pp[k]) for k in ("gotowosc_3d", "tetno", "body_battery") if k in pp}
        tot = sum(abs(v) for v in comp.values())
        if tot <= 0 or len(comp) < 2:
            return None
        k, v = max(comp.items(), key=lambda kv: abs(kv[1]))
        others = [abs(y) for kk, y in comp.items() if kk != k]
        return (k, v) if (abs(v) >= 1.0 and abs(v) / tot > DOMINANCE and all(q <= 0.3 for q in others)) else None
    ds = [dom(day - dt.timedelta(days=k)) for k in range(DOMINANCE_DAYS)]
    if all(ds) and len({x[0] for x in ds}) == 1:
        names = {"gotowosc_3d": "gotowość z 3 dni", "tetno": "tętno spocz.", "body_battery": "Body Battery"}
        out.append(("DOMINACJA", "od %d dni korekta głównie z: %s (dziś %+.2f), pozostałe sygnały w normie"
                    % (DOMINANCE_DAYS, names[ds[0][0]], ds[0][1])))
    # ROZBIEZNOSC
    if not in_ill:
        run = 0
        for k in range(DIVERGE_DAYS):
            x = rows.get(day - dt.timedelta(days=k))
            if x and x[4] is not None and x[5] is not None and abs(float(x[4]) - float(x[5])) > DIVERGE_PTS:
                run += 1
            else:
                break
        if run >= DIVERGE_DAYS:
            out.append(("ROZBIEZNOSC", "od %d dni świeżość faktyczna różni się od treningowej o >%d pkt (dziś %+.0f vs %+.0f)"
                        % (run, DIVERGE_PTS, float(tsb_f), float(tsb_p))))
    return out


def _ensure_log(conn):
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS qbot_v2.real_load_guard_log (id serial PRIMARY KEY, day date, code text, "
                "msg text, sent_at timestamptz DEFAULT now())")
    conn.commit()


def run(conn, day: dt.date | None = None, send=None) -> dict:
    """Wejscie dla daily_job. send(text) - Telegram; None = tylko zapis w logu."""
    day = day or dt.date.today()
    _ensure_log(conn)
    alerts = check(conn, day)
    cur = conn.cursor()
    new = []
    for code, msg in alerts:
        cur.execute("SELECT 1 FROM qbot_v2.real_load_guard_log WHERE code=%s AND day > %s LIMIT 1", (code, day - dt.timedelta(days=REPEAT_DAYS)))
        if _t(cur.fetchall()):
            continue
        cur.execute("INSERT INTO qbot_v2.real_load_guard_log (day, code, msg) VALUES (%s,%s,%s)", (day, code, msg))
        new.append((code, msg))
    conn.commit()
    if new and send is not None:
        send("Strażnik korekty ciała (%s) — do analizy w sesji:\n" % day.strftime("%d.%m") + "\n".join("• " + m for _, m in new)
             + "\nNic nie zostało zmienione automatycznie.")
    return {"alerts": alerts, "sent": [c for c, _ in new]}
