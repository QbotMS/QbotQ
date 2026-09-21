p="/opt/qbot/web/public/kalendarz2-data.js"
s=open(p).read()
old="""h+='<div class="ride"><span style="color:var(--accent)">●</span> '"""
assert s.count(old)==1
s=s.replace(old,"""h+='<div class="ride">\U0001F6B4\U0001F3FB '""")
open(p,"w").write(s)
print("fixed: light skin cyclist emoji")
