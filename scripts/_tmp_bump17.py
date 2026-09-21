p="/opt/qbot/web/public/forma.html"
t=open(p).read()
t=t.replace("height:260px","height:320px")
t=t.replace("forma2-data.js?v=15","forma2-data.js?v=16")
open(p,"w").write(t)
print("bumped + taller chart")
