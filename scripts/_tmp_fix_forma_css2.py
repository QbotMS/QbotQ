p="/opt/qbot/web/public/forma.html"
t=open(p).read()

css='''<style>
.drow{display:grid;grid-template-columns:70px 80px 1fr 130px 1fr 20px;gap:4px 10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line);font-size:14px;cursor:pointer}
.drow .dc{color:var(--ink2);white-space:nowrap;font-variant-numeric:tabular-nums}
.drow .da{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.drow .dw{color:var(--ink2);white-space:nowrap;font-variant-numeric:tabular-nums}
.drow .de{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.drow .chev{color:var(--muted);text-align:center}
.drow .more{display:none;grid-column:1/-1;padding:8px 0 4px}
.drow.open .more{display:block}
@media(max-width:820px){.drow{grid-template-columns:55px 65px 1fr 20px;font-size:13px}.drow .dw,.drow .de{display:none}}
</style>
'''

old='</head>'
assert t.count(old)==1
t=t.replace(old,css+old)
t=t.replace("forma2-data.js?v=9","forma2-data.js?v=10")
open(p,"w").write(t)
print("forma: style+bump done")
