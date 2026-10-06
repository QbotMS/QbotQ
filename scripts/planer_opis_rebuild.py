#!/usr/bin/env python3
"""Wymusza ponowne wygenerowanie opisu trasy Planera (planer_route_opis, LLM).
  .venv/bin/python3 scripts/planer_opis_rebuild.py <route_id> --bg   # w tle, od razu wraca
log: /opt/qbot/artifacts/planer_opis_rebuild.log"""
import json
import os
import subprocess
import sys

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
LOG = "/opt/qbot/artifacts/planer_opis_rebuild.log"

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    raise SystemExit("Uzycie: planer_opis_rebuild.py <route_id> [--bg]")
if "--bg" in sys.argv:
    with open(os.devnull, "rb") as dn, open(LOG, "a") as lf:
        p = subprocess.Popen([sys.executable, __file__, args[0]], stdin=dn, stdout=lf, stderr=lf,
                             start_new_session=True, close_fds=True)
    print(f"w tle pid={p.pid}, log={LOG}")
    raise SystemExit(0)

from qbot3.routes.planer_opis import build_opis  # noqa: E402

out = build_opis(args[0], rebuild=True)
print(json.dumps({"route_id": args[0], "intro": (out or {}).get("intro"),
                  "top_atrakcje": (out or {}).get("top_atrakcje"), "error": (out or {}).get("error")},
                 ensure_ascii=False), flush=True)
