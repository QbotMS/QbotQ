import subprocess
p = subprocess.run(
    ["/opt/qbot/app/.venv/bin/python3", "-u", "/opt/qbot/app/ride_report.py",
     "i175386234", "Morning Ride"],
    cwd="/opt/qbot/app", capture_output=True, text=True, timeout=600)
print("RC", p.returncode)
print("--- STDOUT ---")
print(p.stdout[-4000:])
print("--- STDERR ---")
print(p.stderr[-2000:])
