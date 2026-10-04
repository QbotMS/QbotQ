"""Ponowny przeglad progu TP ModelQ (MQ2) - automat uruchamiany w daily_job.

Tlo (DECISIONS 2026-10-04): kotwica EF z 11.08 (TP 265.5) policzona na skazonej sprawnosci
(EF 1.877 vs czyste ~1.55-1.58, 9 jazd z kwarantanny miernika w oknie). Bez niej TP bylby
o 17.4 W nizszy. Dowody 04.10: dolna granica z W'bal ~238-240 W (nizej jazdy 19.09, 27.09,
04.10 "przejezdzaja przez zero" przy W'~18 kJ, a uzytkownik sie nie odcial); EF po infekcji
09.2026 dawal 216 W - zanizony przez infekcje. Gornej granicy brak (brak wysilkow max).
DECYZJA: kotwica zostaje, TP uznany za niepewny ~239-256 W, przeglad powtorzyc gdy okno EF
wyjdzie poza wplyw infekcji. Ten modul robi to automatycznie.

Wyzwalacz (co nastapi PIERWSZE, od armed_at): after_days / after_rides / after_hours / after_km.
Bezpieczniki (musza byc spelnione, inaczej czeka): okno EF 28 dni zaczyna sie po
(koniec ostatniej infekcji z Kalendarza + post_ill_days) i ma >= min_segments czystych segmentow.
Wynik: jeden raport na Telegram + zapis w data/tp_recheck.json. NIC nie zmienia w modelu.

CLI:
  .venv/bin/python3 -m fitmodel.tp_recheck --status
  .venv/bin/python3 -m fitmodel.tp_recheck --arm [--days N] [--rides N] [--hours H] [--km K]
  .venv/bin/python3 -m fitmodel.tp_recheck --force      # analiza teraz, wydruk, bez Telegrama i bez zmiany stanu
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from statistics import median, quantiles

STATE = Path(__file__).resolve().parents[1] / "data" / "tp_recheck.json"
DEFAULTS = {
    "armed_at": "2026-10-04",
    "after_days": 21,
    "after_rides": 8,
    "after_hours": 15.0,
    "after_km": 400.0,
    "post_ill_days": 14,
    "min_segments": 8,
    "done_at": None,
    "last_check": None,
    "last_reason": None,
    "result": None,
}
EF_WINDOW = 28
LB_WINDOW = 42            # dni jazd do dolnej granicy z W'bal
LB_TOLERANCE_KJ = 1.0     # deficyt W'bal ponizej zera tolerowany (szum, wygladzanie)
REF_XERT = (dt.date(2026, 5, 29), dt.date(2026, 8, 9))   # czysty Xert (przed skazeniem)
REF_MQ2 = (dt.date(2026, 3, 1), dt.date(2026, 5, 28))    # MQ2 na kotwicach z Xerta


# ---------------------------------------------------------------- stan
def load_state() -> dict:
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    return {**DEFAULTS, **st}


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------- czyste funkcje (testowane)
def trigger_reason(st: dict, today: dt.date, progress: dict) -> str | None:
    """Ktory warunek uzytkownika juz zaszedl (pierwszy wygrywa); None = jeszcze nie."""
    armed = dt.date.fromisoformat(str(st["armed_at"]))
    if st.get("after_days") is not None and (today - armed).days >= int(st["after_days"]):
        return f"minelo {(today - armed).days} dni"
    if st.get("after_rides") is not None and progress.get("rides", 0) >= int(st["after_rides"]):
        return f"{progress['rides']} jazd"
    if st.get("after_hours") is not None and progress.get("hours", 0.0) >= float(st["after_hours"]):
        return f"{progress['hours']:.1f} h jazdy"
    if st.get("after_km") is not None and progress.get("km", 0.0) >= float(st["after_km"]):
        return f"{progress['km']:.0f} km"
    return None


def gate_reason(today: dt.date, last_ill_end: dt.date | None, post_ill_days: int,
                n_segments: int, min_segments: int) -> str | None:
    """Powod wstrzymania analizy (None = mozna liczyc)."""
    window_start = today - dt.timedelta(days=EF_WINDOW)
    if last_ill_end is not None:
        clear_from = last_ill_end + dt.timedelta(days=post_ill_days)
        if window_start <= clear_from:
            return (f"okno EF ({window_start}..{today}) obejmuje infekcje/okres po niej "
                    f"(koniec {last_ill_end} + {post_ill_days} dni)")
    if n_segments < min_segments:
        return f"za malo czystych segmentow w oknie: {n_segments} < {min_segments}"
    return None


def wbal_min_kj(rows, tp: float, hie_j: float) -> float:
    """Najglebszy NIEZAKLAMROWANY W'bal [kJ] (ujemny = model mowi 'ponad wyczerpanie')."""
    deficit, prev, buf, mn = hie_j, None, [], hie_j
    for ts, p in rows:
        if p is None:
            continue
        step = 1.0 if prev is None else max((ts - prev).total_seconds(), 1.0)
        prev = ts
        if step >= 30:
            tau = 546.0 * math.exp(-0.01 * tp) + 316.0
            deficit = hie_j - (hie_j - deficit) * math.exp(-step / tau)
            buf = []
            continue
        buf = (buf + [float(p)])[-3:]
        pe = sum(buf) / len(buf)
        if pe > tp:
            deficit -= (pe - tp) * step
        else:
            tau = 546.0 * math.exp(-0.01 * (tp - pe)) + 316.0
            deficit = hie_j - (hie_j - deficit) * math.exp(-step / tau)
        deficit = min(deficit, hie_j)
        mn = min(mn, deficit)
    return mn / 1000.0


def lower_bound_tp(rides: list, hie_j: float, lo: float = 180.0, hi: float = 320.0,
                   tol_kj: float = LB_TOLERANCE_KJ) -> float:
    """Najnizszy TP, przy ktorym zadna jazda nie schodzi glebiej niz -tol_kj (bisekcja, 0.5 W)."""
    def ok(tp):
        return all(wbal_min_kj(r, tp, hie_j) >= -tol_kj for r in rides)
    if ok(lo):
        return lo
    while hi - lo > 0.5:
        mid = (lo + hi) / 2.0
        if ok(mid):
            hi = mid
        else:
            lo = mid
    return round(hi, 1)


# ---------------------------------------------------------------- dane
def _clean_segments(cur):
    cur.execute("""SELECT s.started_at, s.ef_norm::float FROM qbot_v2.fitmodel_segment s
                   WHERE s.hr_quality_ok AND s.ef_norm IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine q
                                     WHERE q.external_id=s.ride_id)""")
    return [(r[0].date(), float(r[1])) for r in cur.fetchall()]


def _ef28(segs, day):
    v = [e for d, e in segs if day - dt.timedelta(days=EF_WINDOW) < d <= day]
    return (median(v) if v else None), len(v)


def _progress(cur, armed: dt.date) -> dict:
    cur.execute("""SELECT count(*), COALESCE(sum(x.dur),0)/3600.0, COALESCE(sum(x.km),0)
                   FROM (SELECT f.external_id, max(a.sec) AS dur, max(a.distance_m)/1000.0 AS km
                         FROM qbot_v2.activity_fit_raw f
                         JOIN qbot_v2.activity_record a ON a.external_id=f.external_id
                         WHERE f.started_at::date > %s AND f.n_records > 1200
                         GROUP BY f.external_id) x""", (armed,))
    n, h, km = cur.fetchone()
    return {"rides": int(n or 0), "hours": float(h or 0), "km": float(km or 0)}


def _last_ill_end(cur):
    cur.execute("SELECT max(COALESCE(end_day, day)) FROM qbot_v2.calendar_entry WHERE kind='illness'")
    r = cur.fetchone()
    return r[0] if r and r[0] else None


def analyse(conn, today: dt.date | None = None) -> dict:
    from fitmodel.modelq2 import io
    today = today or dt.date.today()
    cur = conn.cursor()
    segs = _clean_segments(cur)
    # kalibracja k = prog / EF28 na czystych okresach (niedziele)
    ref = {}
    cur.execute("SELECT date, ftp_power_w FROM qbot_v2.xert_profile_snapshots WHERE date BETWEEN %s AND %s", REF_XERT)
    for d, tp in cur.fetchall():
        ref[d] = float(tp)
    cur.execute("SELECT day, tp_w FROM qbot_v2.modelq2_signature WHERE day BETWEEN %s AND %s", REF_MQ2)
    for d, tp in cur.fetchall():
        ref.setdefault(d, float(tp))
    ks = []
    for d in sorted(ref):
        if d.weekday() == 6:
            e, n = _ef28(segs, d)
            if e and n >= 8:
                ks.append(ref[d] / e)
    out = {"day": str(today), "k_weeks": len(ks)}
    ef, n = _ef28(segs, today)
    out["ef28"], out["ef_segments"] = (round(ef, 3) if ef else None), n
    if len(ks) >= 4 and ef:
        q1, q2, q3 = quantiles(ks, n=4)
        out["tp_ef_w"] = round(q2 * ef)
        out["tp_ef_range_w"] = [round(q1 * ef), round(q3 * ef)]
    cur.execute("SELECT tp_w, hie_kj FROM qbot_v2.modelq2_signature ORDER BY day DESC LIMIT 1")
    tp_now, hie_kj = (float(x) for x in cur.fetchone())
    out["tp_model_w"], out["hie_kj"] = tp_now, hie_kj
    # dolna granica z W'bal (czyste jazdy z LB_WINDOW dni)
    cur.execute("""SELECT f.external_id FROM qbot_v2.activity_fit_raw f
                   WHERE f.started_at::date > %s AND f.n_records > 1800
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine q
                                     WHERE q.external_id=f.external_id AND q.released IS NULL)""",
                (today - dt.timedelta(days=LB_WINDOW),))
    rides = []
    for (eid,) in cur.fetchall():
        rows = io.fetch_ride_rows(eid)
        if rows and sum(1 for _, p in rows if p) >= 600:
            rides.append(rows)
    out["lb_rides"] = len(rides)
    out["tp_lower_bound_w"] = lower_bound_tp(rides, hie_kj * 1000.0) if rides else None
    return out


def report_text(res: dict, reason: str) -> str:
    lb, tpe, tpm = res.get("tp_lower_bound_w"), res.get("tp_ef_w"), res.get("tp_model_w")
    lines = [f"\U0001f4ca Przeglad progu TP ModelQ ({reason})",
             f"TP modelu: {tpm:.0f} W (W' {res.get('hie_kj'):.1f} kJ)"]
    if lb is not None:
        lines.append(f"Dolna granica z W'bal ({res['lb_rides']} jazd, {LB_WINDOW} dni): {lb:.0f} W "
                     f"- nizej Twoje jazdy 'przejezdzalyby przez zero'")
    if tpe is not None:
        lo, hi = res["tp_ef_range_w"]
        lines.append(f"Prog ze sprawnosci (EF {res['ef28']}, {res['ef_segments']} odcinkow): {tpe} W ({lo}-{hi} W)")
    verdict = []
    if lb is not None and tpm < lb:
        verdict.append(f"TP modelu PONIZEJ dolnej granicy - prog za nisko o >= {lb - tpm:.0f} W")
    if tpe is not None and lb is not None and tpe < lb:
        verdict.append("EF nizej niz dolna granica - EF wciaz zanizony (tetno?), nie przesadza")
    if tpe is not None and tpe < tpm - 10 and (lb is None or tpe >= lb):
        verdict.append(f"EF i W'bal zgodnie sugeruja TP nizszy niz model ({tpe} vs {tpm:.0f} W)")
    if tpe is not None and tpe > tpm + 5:
        verdict.append(f"EF sugeruje TP wyzszy niz model ({tpe} vs {tpm:.0f} W)")
    lines.append("Wniosek: " + ("; ".join(verdict) if verdict else "brak sprzecznosci z obecnym TP"))
    lines.append("Nic nie zostalo zmienione - decyzja w sesji (DECISIONS 2026-10-04).")
    return "\n".join(lines)


def run(conn, send=None, today: dt.date | None = None) -> dict:
    """Krok daily_job. Raport wysylany raz; potem modul spi do ponownego --arm."""
    today = today or dt.date.today()
    st = load_state()
    if st.get("done_at"):
        return {"tp_recheck": "zrobione %s (uzbroj ponownie: --arm)" % st["done_at"]}
    cur = conn.cursor()
    prog = _progress(cur, dt.date.fromisoformat(str(st["armed_at"])))
    st["last_check"] = str(today)
    reason = trigger_reason(st, today, prog)
    if reason is None:
        st["last_reason"] = f"czeka na wyzwalacz: {prog['rides']} jazd, {prog['hours']:.1f} h, {prog['km']:.0f} km"
        save_state(st)
        return {"tp_recheck": st["last_reason"]}
    segs = _clean_segments(cur)
    _, n = _ef28(segs, today)
    gate = gate_reason(today, _last_ill_end(cur), int(st["post_ill_days"]), n, int(st["min_segments"]))
    if gate:
        st["last_reason"] = f"wyzwalacz ({reason}), ale czeka: {gate}"
        save_state(st)
        return {"tp_recheck": st["last_reason"]}
    res = analyse(conn, today)
    text = report_text(res, reason)
    if send is not None:
        send(text)
    st.update({"done_at": str(today), "last_reason": reason, "result": res})
    save_state(st)
    return {"tp_recheck": "raport wyslany", **res}


def _cli() -> None:
    import os, sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.api import _db_connect
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--arm", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--days", type=int); ap.add_argument("--rides", type=int)
    ap.add_argument("--hours", type=float); ap.add_argument("--km", type=float)
    a = ap.parse_args()
    st = load_state()
    if a.arm:
        st.update({"armed_at": str(dt.date.today()), "done_at": None, "result": None, "last_reason": None})
        for k, v in (("after_days", a.days), ("after_rides", a.rides), ("after_hours", a.hours), ("after_km", a.km)):
            if v is not None:
                st[k] = v
        save_state(st)
    if a.force:
        conn = _db_connect()
        print(report_text(analyse(conn), "reczne uruchomienie"))
        return
    print(json.dumps(load_state(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    _cli()
