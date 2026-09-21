import subprocess
log = open("/opt/qbot/app/logs/_tmp_ride_report.log", "ab")
p = subprocess.Popen(
    ["/opt/qbot/app/.venv/bin/python3", "/opt/qbot/app/ride_report.py",
     "i175386234", "Morning Ride"],
    stdout=log, stderr=subprocess.STDOUT, cwd="/opt/qbot/app", start_new_session=True)
print("PID", p.pid)
