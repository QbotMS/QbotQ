for f,pairs in [
    ("kalendarz.html",[("kalendarz2-data.js?v=13","kalendarz2-data.js?v=14")]),
    ("forma.html",[("forma2-data.js?v=7","forma2-data.js?v=8")]),
    ("index.html",[("start2.js?v=6","start2.js?v=7")])]:
    p="/opt/qbot/web/public/"+f; t=open(p).read()
    for old,new in pairs:
        if old in t: t=t.replace(old,new); open(p,"w").write(t); print(f,"ok")
        else: print(f,"skip",old)
