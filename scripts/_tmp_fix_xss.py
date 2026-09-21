import ast
p="/opt/qbot/app/qbot_web.py"
s=open(p).read()
old='"ts.xss "'
assert s.count(old)==1
s=s.replace(old, '"ts.tss AS xss "')
old2='r.get("xss")'
assert s.count(old2)==1
s=s.replace(old2, 'r.get("xss")')
ast.parse(s)
open(p,"w").write(s)
print("fixed: ts.tss AS xss")
