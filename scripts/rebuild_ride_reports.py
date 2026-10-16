#!/usr/bin/env python3
"""Przebudowa danych raportu jazdy (W1) z zachowaniem analizy AI (w2_json) i wejsc (inputs_json).

Po co: save_report() nadpisuje w2_json tym, co dostanie (None = kasuje analize AI), wiec zwykla
przebudowa gubila analize. Ten skrypt bierze istniejace fit_path/inputs/w2 i podmienia tylko W1.

Uzycie (DLUGIE - przez SSH w tle, nie przez DEV MCP):
  cd /opt/qbot/app && runuser -u qbot -- nohup .venv/bin/python3 scripts/rebuild_ride_reports.py --broken-surface \\
      > /opt/qbot/artifacts/rebuild_ride_reports.txt 2>&1 &
Opcje:
  --broken-surface   raporty z aktualnej wersji schematu, w ktorych nawierzchnia = plugin (brak)
  RIDE_KEY ...       konkretne jazdy
  --dry              tylko lista, bez przebudowy
"""
import json
import os
import sys
import time

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from qbot3.rides import ride_report_builder as rrb


def targets(cur, args):
    if "--broken-surface" in args:
        cur.execute("SELECT ride_key FROM qbot_v2.ride_report_data WHERE schema_version=%s "
                    "AND w1_json->'surface'->>'source'='plugin' ORDER BY ride_key", (rrb.SCHEMA_VERSION,))
        return [r["ride_key"] for r in cur.fetchall()]
    return [a for a in args if not a.startswith("--")]


def main(args):
    conn = rrb._connect(); cur = conn.cursor()
    keys = targets(cur, args)
    print("jazd do przebudowy:", len(keys), keys, flush=True)
    if "--dry" in args:
        return
    ok = bad = 0
    for k in keys:
        t0 = time.time()
        cur.execute("SELECT fit_path, inputs_json, w2_json FROM qbot_v2.ride_report_data "
                    "WHERE ride_key=%s ORDER BY schema_version DESC LIMIT 1", (k,))
        r = cur.fetchone()
        fit = (r or {}).get("fit_path") or "/opt/qbot/artifacts/fit/%s.fit" % k
        if not os.path.exists(fit):
            print(k, "BRAK FIT:", fit, flush=True); bad += 1; continue
        inputs = (r or {}).get("inputs_json") or {}
        w2 = (r or {}).get("w2_json")
        inputs = json.loads(inputs) if isinstance(inputs, str) else inputs
        w2 = json.loads(w2) if isinstance(w2, str) else w2
        try:
            w1 = rrb.build_w1(fit, k, inputs)
            rrb.save_report(k, fit, inputs, w1, w2)
            s = (w1.get("surface") or {})
            print(k, "OK %.1fs" % (time.time() - t0), "nawierzchnia:", s.get("source"),
                  (s.get("value") or {}).get("types_pct") if isinstance(s.get("value"), dict) else s.get("reason"), flush=True)
            ok += 1
        except Exception as e:
            print(k, "BLAD:", repr(e), flush=True); bad += 1
    print("KONIEC: ok=%d blad=%d" % (ok, bad), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
