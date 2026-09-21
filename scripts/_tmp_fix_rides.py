import ast
p="/opt/qbot/app/qbot_web.py"; s=open(p).read()
old="""            "(afr.summary->>'distance')::numeric/1000 AS dist_km, "
            "(afr.summary->>'duration')::numeric AS duration_s, "
            "ts.xss \""""
assert s.count(old)==1
new="""            "(afr.summary->>'distance')::numeric / 1000 AS dist_km, "
            "(afr.summary->>'duration')::numeric AS duration_s, "
            "ts.xss \""""
s=s.replace(old,new)
ast.parse(s); open(p,"w").write(s); print("fixed")
