import subprocess
r = subprocess.run(["systemd-run", "--unit=qbot-wiki-mirror", "--collect", "--property=WorkingDirectory=/opt/qbot/app", "--setenv=HOME=/root",
                    "/bin/sh", "-c", "/opt/qbot/app/.venv/bin/python3 /opt/qbot/app/scripts/_tmp_mirror.py > /opt/qbot/artifacts/wiki_bg/mirror.log 2>&1"],
                   capture_output=True, text=True)
print(r.returncode, r.stdout, r.stderr)
