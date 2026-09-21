p="/opt/qbot/web/public/index.html"
t=open(p).read()

css='''.drow{display:grid;grid-template-columns:70px 1fr 120px 1fr auto;gap:4px 10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line);font-size:14px}
.drow .dc{color:var(--ink2);white-space:nowrap;font-variant-numeric:tabular-nums}
.drow .da{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.drow .dw{color:var(--ink2);white-space:nowrap;font-variant-numeric:tabular-nums}
.drow .de{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(max-width:820px){.drow{grid-template-columns:60px 1fr auto;font-size:13px}.drow .dw,.drow .de{display:none}}
'''

old='</style>'
assert t.count(old)>=1
t=t.replace(old,css+old,1)
t=t.replace("start2.js?v=8","start2.js?v=9")
open(p,"w").write(t)
print("css+bump done")
