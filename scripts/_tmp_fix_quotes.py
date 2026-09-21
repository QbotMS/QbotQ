import ast
p="/opt/qbot/app/qbot_web.py"
s=open(p).read()
old="(afr.summary->>\\'distance\\')::numeric/1000 AS dist_km"
new='(afr.summary->>\'distance\')::numeric/1000 AS dist_km'
assert s.count(old)==1, "nie znalazlem old"
s=s.replace(old,new)
old2="(afr.summary->>\\'duration\\')::numeric AS duration_s"
new2='(afr.summary->>\'duration\')::numeric AS duration_s'
assert s.count(old2)==1
s=s.replace(old2,new2)
ast.parse(s)
open(p,"w").write(s)
print("fixed quotes")
