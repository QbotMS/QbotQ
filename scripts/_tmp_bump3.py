for f,pairs in [
    ("kalendarz.html",[("kalendarz2-data.js?v=4","kalendarz2-data.js?v=5")]),
    ("forma.html",[("forma2-data.js?v=4","forma2-data.js?v=5")]),
    ("index.html",[("start2.js?v=4","start2.js?v=5")])]:
    p="/opt/qbot/web/public/"+f; t=open(p).read()
    for old,new in pairs:
        if old in t: t=t.replace(old,new); open(p,"w").write(t); print(f,"bumped")
        else: print(f,"skip",old)
