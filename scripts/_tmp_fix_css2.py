p="/opt/qbot/web/public/index.html"
t=open(p).read()

old='.drow{display:grid;grid-template-columns:70px 1fr 120px 1fr auto;gap:4px 10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line);font-size:14px}'
assert t.count(old)==1
new='.drow{display:grid;grid-template-columns:70px 80px 1fr 130px 1fr;gap:4px 10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line);font-size:14px}'
t=t.replace(old,new)

old2='@media(max-width:820px){.drow{grid-template-columns:60px 1fr auto;font-size:13px}.drow .dw,.drow .de{display:none}}'
assert t.count(old2)==1
new2='@media(max-width:820px){.drow{grid-template-columns:55px 65px 1fr;font-size:13px}.drow .dw,.drow .de{display:none}}'
t=t.replace(old2,new2)

t=t.replace("start2.js?v=9","start2.js?v=10")
open(p,"w").write(t)
print("css + bump done")
