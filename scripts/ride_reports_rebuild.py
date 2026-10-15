#!/usr/bin/env python3
"""Przebudowa raportow z jazdy (W1), gdy ModelQ przeliczyl jazde PO zbudowaniu raportu (15.10.2026).

Raport z jazdy to zapisane "zdjecie" (qbot_v2.ride_report_data.built_at). Po przeliczeniu ModelQ (modelq2_ride.computed_at)
stare raporty pokazywaly nieaktualne wartosci (statyczny W'bal, porownanie z Xertem, przewyzszenie). Ten skrypt przebudowuje
raporty nieaktualne (domyslnie) albo wszystkie (--all), przez ten sam endpoint co strona (rebuild=1).

Wolany: w tle na koncu nocnego fitmodel/daily_job.py (krok 8) oraz recznie:
  cd /opt/qbot/app && nohup .venv/bin/python3 scripts/ride_reports_rebuild.py --all > /opt/qbot/artifacts/ride_reports_rebuild.txt 2>&1 &
~15 s na raport -> NIE przez dev_shell_exec (blokuje serwer DEV).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

APP = "/opt/qbot/app"
sys.path.insert(0, APP); sys.path.insert(0, APP + "/scripts")
os.chdir(APP)
os.environ.setdefault("QBOT3_ENABLED", "1")


def _stale_keys(all_: bool) -> list[str]:
    from fitmodel.api import _db_connect
    from qbot3.rides import ride_report_builder as RRB
    c = _db_connect().cursor()
    if all_:
        c.execute("SELECT ride_key FROM qbot_v2.ride_report_data WHERE schema_version=%s ORDER BY built_at", (RRB.SCHEMA_VERSION,))
    else:
        c.execute("SELECT d.ride_key FROM qbot_v2.ride_report_data d JOIN qbot_v2.modelq2_ride m ON m.external_id = d.ride_key "
                  "WHERE d.schema_version=%s AND (d.built_at IS NULL OR m.computed_at > d.built_at) ORDER BY d.built_at", (RRB.SCHEMA_VERSION,))
    return [(r[0] if not isinstance(r, dict) else r["ride_key"]) for r in c.fetchall()]


def main() -> int:
    keys = _stale_keys("--all" in sys.argv)
    print("raportow do przebudowy:", len(keys), flush=True)
    if not keys:
        return 0
    import dev_fetch as DF
    users, sv, mk = DF.get_auth()
    ck = mk(sorted(users)[0], sv)[0]
    ok = bad = 0
    for k in keys:
        t = time.time()
        try:
            req = urllib.request.Request("http://127.0.0.1:30181/api/ride-report/data?ride=%s&rebuild=1" % k,
                                         headers={"Cookie": "qbot_session=" + ck})
            json.loads(urllib.request.urlopen(req, timeout=300).read())
            ok += 1
            print("OK  ", k, "%.1fs" % (time.time() - t), flush=True)
        except Exception as e:
            bad += 1
            print("BLAD", k, type(e).__name__, str(e)[:160], flush=True)
    print("koniec: ok=%d blad=%d" % (ok, bad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
