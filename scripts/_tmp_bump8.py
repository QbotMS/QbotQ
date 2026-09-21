p="/opt/qbot/web/public/kalendarz.html"; t=open(p).read()
t=t.replace("kalendarz2-data.js?v=9","kalendarz2-data.js?v=10")
open(p,"w").write(t); print("bumped")
