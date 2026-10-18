#!/usr/bin/env python3
"""Start przebiegu N WIKI w tle: launch_pass.py <nr> -> systemd-run qbot-wiki-bg<nr>, scripts/wiki_bg/pass<nr>.py."""
import subprocess, sys
APP = "/opt/qbot/app"
n = sys.argv[1]
r = subprocess.run(["systemd-run", f"--unit=qbot-wiki-bg{n}", "--collect", "--property=WorkingDirectory=" + APP,
                    "--setenv=QBOT3_ENABLED=1", "--setenv=HOME=/root",
                    f"{APP}/.venv/bin/python3", f"{APP}/scripts/wiki_bg/pass{n}.py"],
                   capture_output=True, text=True, timeout=30)
print("rc", r.returncode, r.stdout.strip(), r.stderr.strip())
