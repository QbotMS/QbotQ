import ast
p="/opt/qbot/app/qbot_web.py"
s=open(p).read()

# 1) Dodaj weight_kg z wellness do calendar: LEFT JOIN na fitmodel query + wellness
old_fq='"hrv_night, rhr, sleep_h, glycogen_pct "\n            "FROM qbot_v2.fitmodel_daily WHERE day BETWEEN %s AND %s ORDER BY day"'
assert s.count(old_fq)==1
new_fq='"hrv_night, rhr, sleep_h, glycogen_pct, w.weight_kg "\n            "FROM qbot_v2.fitmodel_daily f LEFT JOIN qbot_v2.qbot_wellness_daily w ON w.date = f.day WHERE f.day BETWEEN %s AND %s ORDER BY f.day"'
s=s.replace(old_fq,new_fq)

# 2) W budowaniu days dict - dodaj weight_kg
old_glyc='"glyc": _n(r["glycogen_pct"]),'
assert s.count(old_glyc)==1
s=s.replace(old_glyc,'"glyc": _n(r["glycogen_pct"]), "weight_kg": (round(float(r["weight_kg"]),1) if r.get("weight_kg") else None),')

# 3) Napraw aliasy kolumn w zapytaniu (teraz f. prefix potrzebny)
old_cols='"SELECT day::text AS day, cp_modelq_w, ctl_xss, atl_raw, tsb_raw, "\n            "ftp_est_w, wprime_modelq_kj, w_per_kg, readiness_score, readiness_label, "'
assert s.count(old_cols)==1
new_cols='"SELECT f.day::text AS day, f.cp_modelq_w, f.ctl_xss, f.atl_raw, f.tsb_raw, "\n            "f.ftp_est_w, f.wprime_modelq_kj, f.w_per_kg, f.readiness_score, f.readiness_label, "'
s=s.replace(old_cols,new_cols)

old_hrv='"hrv_night, rhr, sleep_h, glycogen_pct, w.weight_kg "'
s=s.replace(old_hrv,'"f.hrv_night, f.rhr, f.sleep_h, f.glycogen_pct, w.weight_kg "')

ast.parse(s)
open(p,"w").write(s)
print("calendar weight_kg patched")
