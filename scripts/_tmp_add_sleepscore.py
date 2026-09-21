import ast
p="/opt/qbot/app/qbot_web.py"
s=open(p).read()

# Zapytanie fitmodel w calendar: dodaj LEFT JOIN wellness po sleep_score
old='"f.hrv_night, f.rhr, f.sleep_h, f.glycogen_pct, f.weight_kg "\n            "FROM qbot_v2.fitmodel_daily f WHERE f.day BETWEEN %s AND %s ORDER BY f.day"'
assert s.count(old)==1
new='"f.hrv_night, f.rhr, f.sleep_h, f.glycogen_pct, f.weight_kg, w.sleep_score "\n            "FROM qbot_v2.fitmodel_daily f LEFT JOIN qbot_v2.qbot_wellness_daily w ON w.date = f.day "\n            "WHERE f.day BETWEEN %s AND %s ORDER BY f.day"'
s=s.replace(old,new)

# Dodaj sleep_score do days dict
old='"weight_kg": (round(float(r["weight_kg"]),1) if r.get("weight_kg") else None),'
assert s.count(old)==1
new='"weight_kg": (round(float(r["weight_kg"]),1) if r.get("weight_kg") else None), "sleep_score": (int(r["sleep_score"]) if r.get("sleep_score") else None),'
s=s.replace(old,new)

ast.parse(s)
open(p,"w").write(s)
print("calendar: sleep_score added from wellness")
