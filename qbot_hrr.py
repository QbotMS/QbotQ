"""qbot_hrr.py - tetno odpoczynku po akcentach w jazdach (HRR60), liczone AUTOMATYCZNIE z plikow FIT (2026-10-14).

Po co: spadek tetna w 60 s po mocnym wysilku to wskaznik formy i zmeczenia (szybszy spadek = lepsza forma; wyraznie
wolniejszy niz norma = wczesny sygnal przemeczenia/choroby). Garmin go nie zapisuje (wymaga pasek/testu), Michal nie
chce robic testow - wiec QBot wyciaga go z normalnych jazd.

Algorytm (sprawdzony na 20 jazdach 12.10: 450 akcentow, 112 pomiarow, mediana ~15 bpm):
  akcent  = 30 s ze srednia moca >= CP albo tetno >= 90% maksimum tej jazdy,
  szczyt  = najwyzsze tetno w 20 s po akcencie,
  luz     = kolejne 60 s ciaglego zapisu (przerwy <= 5 s, bez auto-pauzy), srednia moc < 40% CP,
  HRR60   = tetno w szczycie - tetno po 60 s (HRR30 analogicznie po 30 s).
Na jazde: mediana zdarzen (min. 3), zapis w qbot_v2.ride_hrr. Trend tygodniowy = mediana jazd.
CP z fitmodel_daily (ftp_est_w) na dzien jazdy.  CLI: python qbot_hrr.py --days 365  (uzupelnienie wstecz)
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MIN_EVENTS = 3
EASY_FRAC = 0.40
DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.ride_hrr (
  external_id TEXT PRIMARY KEY, day DATE NOT NULL, n INT NOT NULL, hrr60 NUMERIC(5,1), hrr30 NUMERIC(5,1), peak_hr NUMERIC(5,1),
  cp_w NUMERIC(6,1), events JSONB, computed_at TIMESTAMPTZ NOT NULL DEFAULT now())"""


def _conn():
    import qbot_food_plan as FP
    return FP._conn()


def _fit_records(path: str) -> list[tuple]:
    import fitparse
    import fitparse.base as FB
    import fitparse.records as FR
    if not getattr(FB, "_qbot_safe_dev", False):      # pola deweloperskie bez definicji nie przerywaja odczytu
        orig = FR.get_dev_type

        def safe(idx, num):
            try:
                return orig(idx, num)
            except Exception:
                return FR.DevField(dev_data_index=idx, def_num=num, type=FR.BASE_TYPES[0x0D], name="dev_%s_%s" % (idx, num),
                                   units=None, native_field_num=None)
        FB.get_dev_type = safe
        FB._qbot_safe_dev = True
    out = []
    for m in fitparse.FitFile(path).get_messages("record"):
        d = m.get_values()
        if d.get("timestamp"):
            out.append((d["timestamp"], d.get("heart_rate"), d.get("power") or 0))
    return out


def analyse(R: list[tuple], cp: float) -> dict:
    hrs = [x[1] for x in R if x[1]]
    if len(R) < 300 or not hrs:
        return {"n": 0, "events": []}
    hmax = max(hrs)
    ev, i = [], 30
    while i < len(R) - 70:
        pw = sum(x[2] for x in R[i - 29:i + 1]) / 30
        if not (pw >= cp or (R[i][1] or 0) >= 0.9 * hmax):
            i += 1
            continue
        j = max(range(i, min(i + 20, len(R))), key=lambda k: R[k][1] or 0)
        seg = R[j:j + 61]
        ok = (len(seg) > 50 and all((seg[k + 1][0] - seg[k][0]).total_seconds() <= 5 for k in range(len(seg) - 1))
              and 55 <= (seg[-1][0] - seg[0][0]).total_seconds() <= 70 and sum(x[2] for x in seg) / len(seg) < EASY_FRAC * cp
              and seg[0][1] and seg[-1][1])
        if ok:
            h30 = next((x[1] for x in seg if (x[0] - seg[0][0]).total_seconds() >= 30 and x[1]), None)
            ev.append({"t": seg[0][0].isoformat(), "peak": seg[0][1], "d60": seg[0][1] - seg[-1][1], "d30": (seg[0][1] - h30) if h30 else None})
        i = j + 90
    return {"n": len(ev), "events": ev}


def process(c, ext_id: str) -> dict | None:
    r = c.execute("SELECT external_id, started_at, fit_path FROM qbot_v2.activity_fit_raw WHERE external_id=%s", (ext_id,)).fetchone()
    if not r or not r["fit_path"] or not os.path.exists(r["fit_path"]):
        return None
    day = r["started_at"].date()
    cpr = c.execute("SELECT ftp_est_w FROM qbot_v2.fitmodel_daily WHERE ftp_est_w IS NOT NULL AND day <= %s ORDER BY day DESC LIMIT 1", (day,)).fetchone()
    cp = float(cpr["ftp_est_w"]) if cpr else 240.0
    try:
        res = analyse(_fit_records(r["fit_path"]), cp)
    except Exception as ex:
        res = {"n": 0, "events": [], "error": type(ex).__name__}
    ev = res["events"]
    d60 = [e["d60"] for e in ev]
    d30 = [e["d30"] for e in ev if e["d30"] is not None]
    ok = len(ev) >= MIN_EVENTS
    c.execute("INSERT INTO qbot_v2.ride_hrr (external_id, day, n, hrr60, hrr30, peak_hr, cp_w, events) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
              "ON CONFLICT (external_id) DO UPDATE SET n=EXCLUDED.n, hrr60=EXCLUDED.hrr60, hrr30=EXCLUDED.hrr30, peak_hr=EXCLUDED.peak_hr, "
              "cp_w=EXCLUDED.cp_w, events=EXCLUDED.events, computed_at=now()",
              (ext_id, day, len(ev), st.median(d60) if ok else None, st.median(d30) if ok and d30 else None,
               st.median([e["peak"] for e in ev]) if ok else None, cp, json.dumps(ev)))
    c.commit()
    return {"day": day.isoformat(), "n": len(ev), "hrr60": st.median(d60) if ok else None}


def pending(c, days: int = 14, limit: int = 2) -> list[str]:
    return [x["external_id"] for x in c.execute(
        "SELECT a.external_id FROM qbot_v2.activity_fit_raw a LEFT JOIN qbot_v2.ride_hrr h ON h.external_id=a.external_id "
        "WHERE h.external_id IS NULL AND a.fit_path IS NOT NULL AND a.sport_type IN ('cycling','gravel_cycling','road_biking','mountain_biking') "
        "AND a.started_at >= now() - make_interval(days => %s) ORDER BY a.started_at DESC LIMIT %s", (days, limit)).fetchall()]


def tick(limit: int = 2) -> list:
    """Wolane z ticka Brokula (co 15 min): nowe jazdy z ostatnich 14 dni, maks. 2 na raz."""
    with _conn() as c:
        c.execute(DDL)
        c.commit()
        return [process(c, e) for e in pending(c, 14, limit)]


def summary(days: int = 365) -> dict:
    """Jazdy z HRR60 + norma (mediana roku bez ostatnich 28 dni) + ostatnie 28 dni."""
    today = date.today()
    with _conn() as c:
        c.execute(DDL)
        rows = c.execute("SELECT day, n, hrr60, hrr30 FROM qbot_v2.ride_hrr WHERE hrr60 IS NOT NULL AND day >= %s ORDER BY day",
                         (today - timedelta(days=days),)).fetchall()
    rides = [{"day": r["day"].isoformat(), "n": r["n"], "hrr60": float(r["hrr60"]), "hrr30": float(r["hrr30"]) if r["hrr30"] is not None else None} for r in rows]
    old = [x["hrr60"] for x in rides if (today - date.fromisoformat(x["day"])).days > 28]
    rec = [x["hrr60"] for x in rides if (today - date.fromisoformat(x["day"])).days <= 28]
    return {"rides": rides, "norm": st.median(old) if len(old) >= 5 else None, "recent": st.median(rec) if len(rec) >= 2 else None,
            "n_recent": len(rec)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    a = ap.parse_args()
    with _conn() as c:
        c.execute(DDL)
        c.commit()
        ids = pending(c, a.days, 10000)
        print("jazd do policzenia:", len(ids), flush=True)
        for k, e in enumerate(ids, 1):
            print(k, process(c, e), flush=True)
    print("KONIEC", summary(a.days)["norm"])
