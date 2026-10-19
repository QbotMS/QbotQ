#!/usr/bin/env python3
"""Przebudowa / zbudowanie danych raportu jazdy (W1) z zachowaniem analizy AI (w2_json) i wejsc (inputs_json).

Po co: save_report() nadpisuje w2_json tym, co dostanie (None = kasuje analize AI), wiec zwykla
przebudowa gubila analize. Ten skrypt bierze istniejace fit_path/inputs/w2 i podmienia tylko W1.

Uzycie (DLUGIE - przez SSH w tle, nie przez DEV MCP):
  cd /opt/qbot/app && runuser -u qbot -- nohup .venv/bin/python3 scripts/rebuild_ride_reports.py --missing --notify \\
      > /opt/qbot/artifacts/rebuild_ride_reports.txt 2>&1 &
Wybor jazd:
  --broken-surface   raporty z aktualnej wersji schematu, w ktorych nawierzchnia = plugin (brak)
  --missing          jazdy z moca i danymi 1 Hz BEZ raportu w aktualnej wersji schematu (od najnowszych)
  --since RRRR-MM-DD istniejace raporty jazd od daty (np. po poprawce opadu 19.10)
  RIDE_KEY ...       konkretne jazdy
Opcje:
  --sleep N          przerwa miedzy jazdami w s (domyslnie 4; silnik nawierzchni pyta Overpass - nie zalewac)
  --notify           na koniec (takze po bledzie krytycznym) wiadomosc na Telegram z podsumowaniem
  --dry              tylko lista, bez przebudowy
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from qbot3.rides import ride_report_builder as rrb


def _opt(args, name, default):
    if name in args:
        try:
            return float(args[args.index(name) + 1])
        except (IndexError, ValueError):
            pass
    return default


def targets(cur, args):
    if "--broken-surface" in args:
        cur.execute("SELECT ride_key FROM qbot_v2.ride_report_data WHERE schema_version=%s "
                    "AND w1_json->'surface'->>'source'='plugin' ORDER BY ride_key", (rrb.SCHEMA_VERSION,))
        return [r["ride_key"] for r in cur.fetchall()]
    if "--since" in args:   # 2026-10-19: istniejace raporty jazd od daty (np. po poprawce opadu)
        d = args[args.index("--since") + 1]
        cur.execute("SELECT d.ride_key FROM qbot_v2.ride_report_data d JOIN qbot_v2.training_sessions t ON t.external_id=d.ride_key "
                    "WHERE d.schema_version=%s AND t.date >= %s::date ORDER BY t.date DESC", (rrb.SCHEMA_VERSION, d))
        return [r["ride_key"] for r in cur.fetchall()]
    if "--missing" in args:
        cur.execute("SELECT t.external_id FROM qbot_v2.training_sessions t "
                    "WHERE t.avg_power_w IS NOT NULL AND t.distance_m > 5000 "
                    "AND EXISTS (SELECT 1 FROM qbot_v2.activity_record r WHERE r.external_id=t.external_id) "
                    "AND NOT EXISTS (SELECT 1 FROM qbot_v2.ride_report_data d WHERE d.ride_key=t.external_id "
                    "                AND d.schema_version=%s) "
                    "ORDER BY t.started_at DESC", (rrb.SCHEMA_VERSION,))
        return [str(r["external_id"]) for r in cur.fetchall()]
    skip = {"--sleep"}
    out, i = [], 0
    while i < len(args):
        if args[i] in skip:
            i += 2; continue
        if not args[i].startswith("--"):
            out.append(args[i])
        i += 1
    return out


def fit_for(cur, k):
    cur.execute("SELECT fit_path FROM qbot_v2.ride_report_data WHERE ride_key=%s AND fit_path IS NOT NULL "
                "ORDER BY schema_version DESC LIMIT 1", (k,))
    r = cur.fetchone()
    cands = [(r or {}).get("fit_path")]
    cur.execute("SELECT fit_path FROM qbot_v2.activity_fit_raw WHERE external_id=%s", (k,))
    r = cur.fetchone()
    cands += [(r or {}).get("fit_path"), "/opt/qbot/artifacts/fit/%s.fit" % k]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def notify(text):
    try:
        from qbot3.rides.ride_report_notify import _tg
        _tg(text)
    except Exception as e:
        print("Telegram: blad", repr(e), flush=True)


def main(args):
    conn = rrb._connect(); cur = conn.cursor()
    keys = targets(cur, args)
    pause = _opt(args, "--sleep", 4.0)
    print("jazd do przebudowy:", len(keys), keys[:20], "..." if len(keys) > 20 else "", flush=True)
    if "--dry" in args:
        return 0, 0, []
    ok, bad, errs, t_all = 0, 0, [], time.time()
    for n, k in enumerate(keys, 1):
        t0 = time.time()
        fit = fit_for(cur, k)
        if not fit:
            print(n, k, "BRAK FIT", flush=True); bad += 1; errs.append((k, "brak FIT")); continue
        cur.execute("SELECT inputs_json, w2_json FROM qbot_v2.ride_report_data "
                    "WHERE ride_key=%s ORDER BY schema_version DESC LIMIT 1", (k,))
        r = cur.fetchone() or {}
        inputs = r.get("inputs_json") or {}
        w2 = r.get("w2_json")
        inputs = json.loads(inputs) if isinstance(inputs, str) else inputs
        w2 = json.loads(w2) if isinstance(w2, str) else w2
        try:
            w1 = rrb.build_w1(fit, k, inputs)
            rrb.save_report(k, fit, inputs, w1, w2)
            s = (w1.get("surface") or {})
            print(n, k, "OK %.1fs" % (time.time() - t0), "nawierzchnia:", s.get("source"),
                  (s.get("value") or {}).get("types_pct") if isinstance(s.get("value"), dict) else s.get("reason"), flush=True)
            ok += 1
        except Exception as e:
            print(n, k, "BLAD:", repr(e), flush=True); bad += 1; errs.append((k, type(e).__name__))
        if n < len(keys) and pause > 0:
            time.sleep(pause)
    mins = (time.time() - t_all) / 60
    print("KONIEC: ok=%d blad=%d czas %.0f min" % (ok, bad, mins), flush=True)
    return ok, bad, errs, mins


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        res = main(a)
        if "--notify" in a and "--dry" not in a:
            ok, bad, errs, mins = res
            txt = "🛠 <b>Raporty jazd przebudowane</b>\n✅ %d  ❌ %d  ·  %.0f min" % (ok, bad, mins)
            if errs:
                txt += "\nBledy: " + ", ".join("%s (%s)" % e for e in errs[:5]) + (" …" if len(errs) > 5 else "")
            txt += "\nLog: /opt/qbot/artifacts/rebuild_ride_reports.txt"
            notify(txt)
    except Exception:
        traceback.print_exc()
        if "--notify" in a:
            notify("⚠️ <b>Przebudowa raportow jazd przerwana</b>\nLog: /opt/qbot/artifacts/rebuild_ride_reports.txt")
        sys.exit(1)
