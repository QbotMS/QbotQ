#!/usr/bin/env python3
"""Przelicza atrakcje trasy (kanoniczny silnik, force) i wlacza przelacznik atrakcji.
  .venv/bin/python3 scripts/route_attractions_recompute.py <route_id> --bg
log: /opt/qbot/artifacts/route_attractions_recompute.log
Wczytuje env uslugi (klucz Google!) - bez tego Google=0 i wynik jest zubozony."""
import json
import os
import subprocess
import sys

sys.path.insert(0, "/opt/qbot/app")
os.chdir("/opt/qbot/app")
for _p in ("/opt/qbot/app/.env.local", "/etc/qbot/qbot-api.env", "/opt/qbot/app/.env"):
    try:
        for _line in open(_p, encoding="utf-8"):
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip().removeprefix("export ").strip(), _v.strip().strip('"').strip("'"))
    except OSError:
        pass
os.environ.setdefault("QBOT3_ENABLED", "1")
import qbot_config  # noqa: E402,F401  (ten sam loader konfiguracji co worker analizy)

LOG = "/opt/qbot/artifacts/route_attractions_recompute.log"
args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    raise SystemExit("Uzycie: route_attractions_recompute.py <route_id> [--bg]")
if "--bg" in sys.argv:
    with open(os.devnull, "rb") as dn, open(LOG, "a") as lf:
        p = subprocess.Popen([sys.executable, __file__, args[0]], stdin=dn, stdout=lf, stderr=lf,
                             start_new_session=True, close_fds=True)
    print(f"w tle pid={p.pid}, log={LOG}")
    raise SystemExit(0)

print("google key:", any(k for k in os.environ if "GOOGLE" in k.upper()), flush=True)
from qbot3.routes.route_attraction_store import ensure_route_attractions  # noqa: E402
from qbot3.routes.route_poi_store import set_route_poi_attractions  # noqa: E402

set_route_poi_attractions(args[0], True)
out = ensure_route_attractions(route_id=args[0], force=True)
print(json.dumps({"route_id": args[0], "run_id": out.get("run_id"), "status": out.get("status"),
                  "summary": out.get("summary"), "source_status": out.get("source_status")},
                 ensure_ascii=False, default=str), flush=True)
