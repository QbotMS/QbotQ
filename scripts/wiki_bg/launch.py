#!/usr/bin/env python3
"""Start runnera WIKI w tle (systemd-run, jednostka qbot-wiki-bg) -- wraca od razu, nie blokuje DEV MCP."""
import os, shutil, subprocess, sys
APP = "/opt/qbot/app"
OUT = "/opt/qbot/artifacts/wiki_bg"
os.makedirs(OUT, exist_ok=True)
cmd = [f"{APP}/.venv/bin/python3", f"{APP}/scripts/wiki_bg/runner.py"]
if shutil.which("systemd-run"):
    r = subprocess.run(["systemd-run", "--unit=qbot-wiki-bg", "--collect", "--property=WorkingDirectory=" + APP,
                        "--setenv=QBOT3_ENABLED=1", "--setenv=HOME=/root"] + cmd,
                       capture_output=True, text=True, timeout=30)
    print("systemd-run rc", r.returncode, r.stdout.strip(), r.stderr.strip())
    if r.returncode == 0:
        sys.exit(0)
lf = open(f"{OUT}/launch.out", "a")
p = subprocess.Popen(cmd, cwd=APP, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
print("setsid pid", p.pid)
