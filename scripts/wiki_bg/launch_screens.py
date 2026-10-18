#!/usr/bin/env python3
"""Ponowne zrzuty ekranow WIKI w tle (systemd-run qbot-wiki-screens)."""
import subprocess
APP = "/opt/qbot/app"
r = subprocess.run(["systemd-run", "--unit=qbot-wiki-screens", "--collect", "--property=WorkingDirectory=" + APP,
                    "--setenv=QBOT3_ENABLED=1", "--setenv=HOME=/root",
                    "/bin/sh", "-c", f"{APP}/.venv/bin/python3 {APP}/scripts/wiki_bg/screens.py > /opt/qbot/artifacts/wiki_bg/screens2.log 2>&1"],
                   capture_output=True, text=True, timeout=30)
print("rc", r.returncode, r.stdout.strip(), r.stderr.strip())
