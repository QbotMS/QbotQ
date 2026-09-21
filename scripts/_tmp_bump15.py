p="/opt/qbot/web/public/index.html"; t=open(p).read()
t=t.replace("start2.js?v=7","start2.js?v=8")
open(p,"w").write(t); print("bumped")
