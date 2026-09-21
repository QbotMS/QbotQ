for f,pairs in [
    ("kalendarz.html",[("kalendarz2-data.js?v=5","kalendarz2-data.js?v=6")]),
    ("forma.html",[("forma2-data.js?v=5","forma2-data.js?v=6")]),
    ("index.html",[("start2.js?v=5","start2.js?v=6")])]:
    p="/opt/qbot/web/public/"+f; t=open(p).read()
    for old,new in pairs:
        if old in t: t=t.replace(old,new); open(p,"w").write(t); print(f,"ok")
        else: print(f,"skip",old)
