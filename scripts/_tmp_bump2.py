for f,pairs in [
    ("kalendarz2.html",[("kalendarz2-data.js?v=3","kalendarz2-data.js?v=4"),("ui2-common.js?v=2","ui2-common.js?v=3")]),
    ("start2.html",[("start2.js?v=3","start2.js?v=4"),("ui2-common.js?v=2","ui2-common.js?v=3")]),
    ("forma2.html",[("forma2-data.js?v=3","forma2-data.js?v=4"),("ui2-common.js?v=2","ui2-common.js?v=3")])]:
    p="/opt/qbot/web/public/"+f; t=open(p).read()
    for old,new in pairs:
        t=t.replace(old,new)
    open(p,"w").write(t); print(f,"done")
