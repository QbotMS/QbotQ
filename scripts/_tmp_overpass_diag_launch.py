import subprocess, sys, os
os.makedirs("/opt/qbot/app/logs", exist_ok=True)
log = open("/opt/qbot/app/logs/_tmp_overpass_diag.log", "ab")
p = subprocess.Popen(
    ["/opt/qbot/app/.venv/bin/python3", "/opt/qbot/app/scripts/_tmp_overpass_diag.py"],
    stdout=log, stderr=subprocess.STDOUT, cwd="/opt/qbot/app", start_new_session=True)
print("PID", p.pid)
