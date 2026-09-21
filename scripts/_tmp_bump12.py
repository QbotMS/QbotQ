p="/opt/qbot/web/public/forma.html"; t=open(p).read()
t=t.replace("forma2-data.js?v=6","forma2-data.js?v=7")
open(p,"w").write(t); print("bumped")
