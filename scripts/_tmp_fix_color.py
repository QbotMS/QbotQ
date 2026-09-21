p="/opt/qbot/web/public/kalendarz2-data.js"
s=open(p).read()

old='''if(e.kind==="illness")h+='<div class="ride" style="color:var(--bad)">🤒 '+qEsc(e.title||"choroba")+'</div>';'''
assert s.count(old)==1
s=s.replace(old,'''if(e.kind==="illness")h+='<div class="ride" style="color:#4eca6a">🤒 '+qEsc(e.title||"choroba")+'</div>';''')

open(p,"w").write(s)
print("fixed: illness green in tiles")
