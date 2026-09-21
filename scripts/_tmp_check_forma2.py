import subprocess,json
o=subprocess.run(["/opt/qbot/app/.venv/bin/python3","/opt/qbot/app/scripts/dev_fetch.py","/api/calendar?start=2026-09-01&end=2026-09-21","--max","200000"],capture_output=True,text=True).stdout
j=json.loads(o[o.find("{"):])
days=j.get("days") or {}
print("days count:", len(days))
print("keys:", sorted(days.keys())[:5], "...", sorted(days.keys())[-5:])
d=days.get("2026-09-20",{})
print("2026-09-20:", {k:v for k,v in d.items() if k!="_entries"})
print("entries in response:", len(j.get("entries",[])))
