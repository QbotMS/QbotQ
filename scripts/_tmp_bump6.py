p="/opt/qbot/web/public/kalendarz.html"; t=open(p).read()
t=t.replace("kalendarz2-data.js?v=7","kalendarz2-data.js?v=8")
open(p,"w").write(t); print("bumped")
