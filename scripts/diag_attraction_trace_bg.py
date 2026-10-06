#!/usr/bin/env python3
"""Uruchamia scripts/diag_attraction_trace.py w tle (trwa ~1 min), wynik do logu.
  .venv/bin/python3 scripts/diag_attraction_trace_bg.py <gpx> <fraza> [...]
log: /opt/qbot/artifacts/diag_attraction_trace.log (nadpisywany)"""
import os
import subprocess
import sys

LOG = "/opt/qbot/artifacts/diag_attraction_trace.log"
with open(os.devnull, "rb") as dn, open(LOG, "w") as lf:
    p = subprocess.Popen([sys.executable, "/opt/qbot/app/scripts/diag_attraction_trace.py", *sys.argv[1:]],
                         cwd="/opt/qbot/app", stdin=dn, stdout=lf, stderr=lf, start_new_session=True, close_fds=True)
print(f"w tle pid={p.pid}, log={LOG}")
