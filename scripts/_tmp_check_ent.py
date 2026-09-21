import subprocess,json
o=subprocess.run(["/opt/qbot/app/.venv/bin/python3","/opt/qbot/app/scripts/dev_fetch.py","/api/calendar?start=2026-09-01&end=2026-09-20","--max","80000"],capture_output=True,text=True).stdout
j=json.loads(o[o.find("{"):])
for ds in sorted(j["days"].keys()):
    d=j["days"][ds]
    ent=d.get("entries") or d.get("events") or d.get("items")
    if ent: print(ds,"entries:",ent)
print("--- keys in days[2026-09-10]:", list(j["days"].get("2026-09-10",{}).keys()))
