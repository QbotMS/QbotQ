import os
d="/opt/qbot/web/public"
for f in os.listdir(d):
    if not f.endswith((".js",".html")): continue
    if f.endswith("-old.html"): continue
    p=os.path.join(d,f); t=open(p).read()
    n=t.replace("raport-jazdy2.html","raport-jazdy.html").replace("forma2.html","forma.html").replace("kalendarz2.html","kalendarz.html").replace("start2.html","index.html")
    if n!=t: open(p,"w").write(n); print("fixed",f)
