import subprocess
log = open("/opt/qbot/app/logs/_tmp_rerun_komoot2.log", "ab")
p = subprocess.Popen(
    ["/opt/qbot/app/.venv/bin/python3", "/opt/qbot/app/scripts/_tmp_rerun_komoot2.py"],
    stdout=log, stderr=subprocess.STDOUT, cwd="/opt/qbot/app", start_new_session=True)
print("PID", p.pid)
