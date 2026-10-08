#!/usr/bin/env python3
"""Rekalibracja modelu czasu (2026-10-08) -- KANDYDAT do zatwierdzenia, nic nie zmienia sam.

Cron root: pon. 05:15 -> liczy kandydata z ostatnich jazd, zapisuje
  config/speed_model_candidate.json + /opt/qbot/artifacts/speed_model_candidate_<data>.md
  i wysyla podsumowanie na Telegram. Aktywny model (config/speed_model.json) BEZ ZMIAN.
Zatwierdzenie (decyzja Michala):  speed_model_recalibrate.py --approve
  -> kandydat staje sie aktywny (historia wersji w pliku), uslugi przeladuja go same (mtime).
Podglad stanu:                     speed_model_recalibrate.py --status

Zasady (te same co przeglad v2, scripts/speed_model_review_v2.py):
- baza: jazdy BEZ bagazu z ostatnich BASE_DAYS dni, >= 40 km, w PL; kratka = srednia czasowa,
  kratka < 300 s albo zmiana > 25% vs aktywna -> aktywna wartosc (oznaczone),
- sport/wyscig = max(aktywna, nowy normalny),
- walidacja leave-one-out: blad czasu ruchu aktywny vs kandydat,
- postoje z jazd >= 20 km z ostatnich STOP_DAYS dni (min. 20 zwyklych / 5 dni bikepacking, inaczej bez zmian),
- bikepacking: dni z bikepacking_dates (konfiguracja), min. 5 h ruchu, inaczej bez zmian,
- rower: wspolczynnik, gdy rower ma >= bike_factor_min_rides jazd i odchylenie >= 3%.
Kandydat NIE powstaje, gdy baza < MIN_RIDES jazd.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

APP = Path("/opt/qbot/app")
sys.path.insert(0, str(APP)); sys.path.insert(0, str(APP / "scripts"))
os.environ.setdefault("QBOT3_ENABLED", "1")

ACTIVE = APP / "config/speed_model.json"
CAND = APP / "config/speed_model_candidate.json"
ART = Path("/opt/qbot/artifacts")
BASE_DAYS, STOP_DAYS, MIN_RIDES, MAX_CHANGE = 120, 180, 8, 0.25


def telegram(text: str) -> None:
    try:
        import requests
        import qbot_config as cfg
        requests.post(f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": text}, timeout=15)
    except Exception as exc:
        print("telegram nieudany:", exc)


def build_candidate() -> dict | None:
    import speed_model_review_v2 as V2
    import speed_table_review as STR
    from fitmodel.ftp_resolver import _db_connect
    from qbot3.rides.activity_devices import bike_for_ride
    from qbot_route_time_tools import GRADE_LABELS

    act = json.loads(ACTIVE.read_text(encoding="utf-8"))
    V2.BIKEPACK = [tuple(x) for x in act.get("bikepacking_dates", [])]
    V2.OLD = act["table"]["normalny"]
    since_base = (date.today() - timedelta(days=BASE_DAYS)).isoformat()
    since_stop = (date.today() - timedelta(days=STOP_DAYS)).isoformat()

    conn = _db_connect(); cur = conn.cursor()
    cur.execute("""SELECT external_id, min(ts)::date::text, max(distance_m)/1000.0 FROM qbot_v2.activity_record
                   WHERE ts >= %s GROUP BY external_id HAVING max(distance_m) >= 20000 ORDER BY 2""", (since_stop,))
    base, bp, stop_rows = [], [], []
    for eid, d, km in cur.fetchall():
        km = float(km)
        try:
            bk = bike_for_ride(conn, eid).get("bike") or "?"
        except Exception:
            bk = "?"
        s = V2.stops(cur, eid)
        if s:
            stop_rows.append(dict(km=km, bp=V2.is_bp(d), mov_h=s[0], mikro=s[1].get("mikro", 0.0),
                                  krotkie=s[1].get("krotkie", 0.0)))
        if km < 40 or not (V2.is_bp(d) or d >= since_base):
            continue
        res = STR.process_ride(cur, eid)
        if not res or len(res[0]) < 600:
            continue
        r = dict(d=d, bike=bk, samples=res[0], sums=V2.sums_of(res[0]))
        (bp if V2.is_bp(d) else base).append(r)
    conn.close()
    if len(base) < MIN_RIDES:
        print(f"za malo jazd w bazie ({len(base)} < {MIN_RIDES}) -- brak kandydata")
        return None

    tot = defaultdict(lambda: [0.0, 0])
    for r in base:
        for k, (sv, n) in r["sums"].items():
            tot[k][0] += sv; tot[k][1] += n

    def guarded(t_raw):
        out, flags = {}, []
        for c in ("paved", "unpaved"):
            for b in GRADE_LABELS:
                old = float(V2.OLD[c][b]); new = float(t_raw[c][b])
                n = tot.get(V2.key(c, b), (0, 0))[1]
                if n >= V2.MIN_CELL_S and abs(new - old) / old > MAX_CHANGE:
                    flags.append(f"{c} {b}: {old}->{new} (>{int(MAX_CHANGE*100)}%, zostaje {old})")
                    new = old
                out.setdefault(c, {})[b] = new
        return out, flags

    normal, flags = guarded(V2.table_from(tot))
    val = []
    for r in base:
        loo = {k: (tot[k][0] - r["sums"].get(k, (0, 0))[0], tot[k][1] - r["sums"].get(k, (0, 0))[1]) for k in tot}
        t_loo, _ = guarded(V2.table_from(loo))
        n = len(r["samples"])
        val.append(dict(bike=r["bike"], old=(V2.pred_s(r["samples"], V2.OLD) - n) / n * 100,
                        new=(V2.pred_s(r["samples"], t_loo) - n) / n * 100))

    table = {"normalny": normal}
    for m in ("sport", "wyscig"):
        table[m] = {c: {b: max(float(act["table"][m][c][b]), normal[c][b]) for b in GRADE_LABELS}
                    for c in ("paved", "unpaved")}

    stops = json.loads(json.dumps(act["stops"]))
    norm = [r for r in stop_rows if not r["bp"]]; bpr = [r for r in stop_rows if r["bp"]]
    def fit(rs, h0):
        den = sum(max(0.0, r["mov_h"] - h0) for r in rs)
        return (round(sum(r["krotkie"] for r in rs) / den, 1) if den else None,
                round(sum(r["mikro"] for r in rs) / sum(r["km"] for r in rs), 2))
    if len(norm) >= 20:
        s_, m_ = fit(norm, stops["normal"]["free_h"])
        if s_ is not None:
            stops["normal"].update(short_min_per_h=s_, micro_min_per_km=m_)
    if len(bpr) >= 5:
        s_, m_ = fit(bpr, stops["bikepacking"]["free_h"])
        if s_ is not None:
            stops["bikepacking"].update(short_min_per_h=s_, micro_min_per_km=m_)

    bpf = act["bikepacking_speed_factor"]
    a_s = sum(len(r["samples"]) for r in bp)
    if a_s >= 5 * 3600:
        bpf = round(sum(V2.pred_s(r["samples"], normal) for r in bp) / a_s, 2)

    bike_f = {}
    byb = defaultdict(list)
    for v in val:
        byb[v["bike"]].append(v["new"])
    for bk, xs in byb.items():
        f = round(1 + sum(xs) / len(xs) / 100, 2)
        if bk != "?" and len(xs) >= int(act.get("bike_factor_min_rides", 5)) and abs(f - 1) >= 0.03:
            bike_f[bk] = f

    avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
    cand = dict(act)
    cand.update(version=date.today().isoformat(), approved_at=None, approved_by=None,
                source=(f"speed_model_recalibrate.py: {len(base)} jazd bez bagazu od {since_base} "
                        f"({sum(len(r['samples']) for r in base)/3600:.0f} h), postoje: {len(norm)} jazd + {len(bpr)} dni bikepacking"),
                table=table, stops=stops, bikepacking_speed_factor=bpf, bike_factors=bike_f,
                validation={"rides": len(val), "old_err_pct": round(avg([v["old"] for v in val]), 1),
                            "new_err_pct": round(avg([v["new"] for v in val]), 1),
                            "old_abs_pct": round(avg([abs(v["old"]) for v in val]), 1),
                            "new_abs_pct": round(avg([abs(v["new"]) for v in val]), 1)},
                guard_flags=flags)
    return cand


def report(act: dict, cand: dict) -> str:
    from qbot_route_time_tools import GRADE_LABELS
    v = cand["validation"]
    L = [f"Model czasu -- kandydat {cand['version']} (aktywny: {act['version']})",
         f"Blad czasu ruchu (LOO, {v['rides']} jazd): aktywny {v['old_err_pct']:+.1f}% -> kandydat {v['new_err_pct']:+.1f}% "
         f"(typowy {v['old_abs_pct']:.1f}% -> {v['new_abs_pct']:.1f}%)", "Zmiany predkosci (normalny, >= 0,5 km/h):"]
    ch = 0
    for c, lab in (("paved", "asfalt"), ("unpaved", "szuter")):
        for b in GRADE_LABELS:
            o, n = act["table"]["normalny"][c][b], cand["table"]["normalny"][c][b]
            if abs(n - o) >= 0.5:
                L.append(f"  {lab} {b}%: {o} -> {n} km/h"); ch += 1
    if not ch:
        L.append("  brak istotnych zmian")
    for k, lab in (("normal", "zwykle"), ("bikepacking", "bikepacking")):
        o, n = act["stops"][k], cand["stops"][k]
        L.append(f"Postoje {lab}: krotkie {o['short_min_per_h']} -> {n['short_min_per_h']} min/h, "
                 f"mikro {o['micro_min_per_km']} -> {n['micro_min_per_km']} min/km")
    L.append(f"Bikepacking x{act['bikepacking_speed_factor']} -> x{cand['bikepacking_speed_factor']}; "
             f"rowery: {cand['bike_factors'] or 'bez wspolczynnikow'}")
    if cand.get("guard_flags"):
        L.append("Zablokowane bezpiecznikiem: " + "; ".join(cand["guard_flags"]))
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    a = ap.parse_args()
    act = json.loads(ACTIVE.read_text(encoding="utf-8"))

    if a.status:
        print(f"aktywny: {act['version']} (zatwierdzony {act.get('approved_at')})")
        if CAND.exists():
            c = json.loads(CAND.read_text(encoding="utf-8"))
            print("kandydat czeka:\n" + report(act, c))
        else:
            print("brak kandydata")
        return 0

    if a.approve:
        if not CAND.exists():
            print("brak kandydata do zatwierdzenia"); return 1
        c = json.loads(CAND.read_text(encoding="utf-8"))
        c["approved_at"] = date.today().isoformat(); c["approved_by"] = "Michal"
        hist = list(act.get("history") or [])
        hist.append({"version": act["version"], "approved_at": act.get("approved_at"), "table": act["table"],
                     "stops": act["stops"], "bikepacking_speed_factor": act["bikepacking_speed_factor"],
                     "bike_factors": act.get("bike_factors") or {}})
        c["history"] = hist[-12:]
        tmp = ACTIVE.with_suffix(".tmp"); tmp.write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, ACTIVE); CAND.unlink()
        print(f"zatwierdzono {c['version']} (poprzednia {act['version']} w historii) -- uslugi przeladuja model same")
        return 0

    cand = build_candidate()
    if not cand:
        return 0
    CAND.write_text(json.dumps(cand, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    txt = report(act, cand)
    (ART / f"speed_model_candidate_{cand['version'].replace('-', '')}.md").write_text(txt + "\n", encoding="utf-8")
    print(txt)
    if not a.no_telegram:
        telegram(txt + "\n\nZatwierdzenie: popros Claude'a albo uruchom\n"
                       "scripts/speed_model_recalibrate.py --approve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
