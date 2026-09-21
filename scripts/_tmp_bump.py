for f,old,new in [("kalendarz2.html","kalendarz2-data.js?v=1","kalendarz2-data.js?v=3"),
                  ("kalendarz2.html","ui2-common.js?v=1","ui2-common.js?v=2"),
                  ("start2.html","start2.js?v=1","start2.js?v=3"),
                  ("start2.html","ui2-common.js?v=1","ui2-common.js?v=2"),
                  ("forma2.html","forma2-data.js?v=1","forma2-data.js?v=3"),
                  ("forma2.html","ui2-common.js?v=1","ui2-common.js?v=2")]:
    p="/opt/qbot/web/public/"+f; t=open(p).read()
    if old in t: t=t.replace(old,new); open(p,"w").write(t); print(f,"bumped")
    else: print(f,"already up to date or not found:",old)
