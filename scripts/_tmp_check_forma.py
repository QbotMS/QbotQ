import subprocess,json
o=subprocess.run(["/opt/qbot/app/.venv/bin/python3","/opt/qbot/app/scripts/dev_fetch.py","/api/forma/data","--max","2000"],capture_output=True,text=True).stdout
j=json.loads(o[o.find("{"):])
S=j.get("series") or []
print("forma series len:", len(S))
if S: print("last day:", S[-1].get("day"), "sleep_score:", S[-1].get("sleep_score"))

o2=subprocess.run(["/opt/qbot/app/.venv/bin/python3","/opt/qbot/app/scripts/dev_fetch.py","/api/calendar?start=2025-09-21&end=2026-09-21","--max","1000"],capture_output=True,text=True).stdout
j2=json.loads(o2[o2.find("{"):])
days=j2.get("days") or {}
print("calendar days count:", len(days), "first 3:", sorted(days.keys())[:3], "last 3:", sorted(days.keys())[-3:])
entries=j2.get("entries") or []
print("entries count:", len(entries))
