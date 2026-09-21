import subprocess
log = open("/opt/qbot/app/logs/_tmp_import_training.log", "ab")
p = subprocess.Popen(
    ["/opt/qbot/app/.venv/bin/python3", "/opt/qbot/app/qbot3/connectors/import_garmin_training.py"],
    stdout=log, stderr=subprocess.STDOUT, cwd="/opt/qbot/app", start_new_session=True)
print("PID", p.pid)
