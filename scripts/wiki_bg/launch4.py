#!/usr/bin/env python3
"""Start przebiegu 4 WIKI (strona /wiki.html) w tle (systemd-run, jednostka qbot-wiki-bg4)."""
import subprocess
APP = "/opt/qbot/app"
r = subprocess.run(["systemd-run", "--unit=qbot-wiki-bg4", "--collect", "--property=WorkingDirectory=" + APP,
                    "--setenv=QBOT3_ENABLED=1", "--setenv=HOME=/root",
                    f"{APP}/.venv/bin/python3", f"{APP}/scripts/wiki_bg/pass4.py"],
                   capture_output=True, text=True, timeout=30)
print("rc", r.returncode, r.stdout.strip(), r.stderr.strip())
