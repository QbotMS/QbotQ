import ast
p="/opt/qbot/app/qbot_web.py"
s=open(p).read()
# Usun JOIN wellness (pusty), uzyj weight_kg z fitmodel_daily bezposrednio
old='"f.hrv_night, f.rhr, f.sleep_h, f.glycogen_pct, w.weight_kg "\n            "FROM qbot_v2.fitmodel_daily f LEFT JOIN qbot_v2.qbot_wellness_daily w ON w.date = f.day WHERE f.day BETWEEN %s AND %s ORDER BY f.day"'
assert s.count(old)==1
new='"f.hrv_night, f.rhr, f.sleep_h, f.glycogen_pct, f.weight_kg "\n            "FROM qbot_v2.fitmodel_daily f WHERE f.day BETWEEN %s AND %s ORDER BY f.day"'
s=s.replace(old,new)
# napraw odwolanie do r["weight_kg"]
old_wt='(round(float(r["weight_kg"]),1) if r.get("weight_kg") else None)'
assert s.count(old_wt)==1
# zostaje bez zmian — r["weight_kg"] z fitmodel_daily
ast.parse(s)
open(p,"w").write(s)
print("fixed: weight from fitmodel_daily directly")
