import subprocess,json
o=subprocess.run(["/opt/qbot/app/.venv/bin/python3","/opt/qbot/app/scripts/dev_fetch.py","/api/calendar?start=2026-09-01&end=2026-09-10","--max","4000"],capture_output=True,text=True).stdout
j=json.loads(o[o.find("{"):])
for ds in sorted(j["days"].keys()):
    d=j["days"][ds]
    print(ds,"wt:",d.get("weight_kg"),"sleep:",d.get("sleep"),"rdy:",d.get("readiness_label"))
