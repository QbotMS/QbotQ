p="/opt/qbot/web/public/forma.html"
t=open(p).read()
t=t.replace("forma2-data.js?v=18","forma2-data.js?v=19")
# usun trendy-ftp-val2 i ftp panel jesli jeszcze zostal
if "trendy-ftp-val2" in t and "trendy-ftp-canvas" not in t:
    print("ftp val2 orphan, removing line")
open(p,"w").write(t)
print("bumped v19")
