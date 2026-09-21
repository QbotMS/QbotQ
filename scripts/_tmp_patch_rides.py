import ast
p="/opt/qbot/app/qbot_web.py"; s=open(p).read()
old='"(rrd.built_at IS NOT NULL) AS has_report "'
assert s.count(old)==1
s=s.replace(old,'"(rrd.built_at IS NOT NULL) AS has_report, "\n            "(afr.summary->>\'distance\')::numeric/1000 AS dist_km, "\n            "(afr.summary->>\'duration\')::numeric AS duration_s, "\n            "ts.xss "')
old='"has_report": bool(r["has_report"]),\n            })'
assert s.count(old)==1
s=s.replace(old,'"has_report": bool(r["has_report"]),\n                "dist_km": round(float(r["dist_km"]),1) if r["dist_km"] else None,\n                "duration_s": round(float(r["duration_s"])) if r["duration_s"] else None,\n                "xss": round(float(r["xss"])) if r.get("xss") else None,\n            })')
ast.parse(s); open(p,"w").write(s); print("rides/ready patched")
