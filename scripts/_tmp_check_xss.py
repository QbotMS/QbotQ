import subprocess,json
o=subprocess.run(["/opt/qbot/app/.venv/bin/python3","/opt/qbot/app/scripts/dev_fetch.py","/api/forma/data","--max","200000"],capture_output=True,text=True).stdout
j=json.loads(o[o.find("{"):])
S=j["series"]
print("keys in last:", sorted(S[-1].keys()))
# szukamy xss per dzien
for k in ["xss_day","xss","daily_xss","tss","xss_total"]:
    v=S[-5].get(k)
    if v is not None: print(k,"=",v)
