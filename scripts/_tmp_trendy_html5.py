p="/opt/qbot/web/public/forma.html"
t=open(p).read()

# usun dolny panel FTP — zostaje jeden wykres
old_ftp='<div style="border-top:1px solid var(--line);margin:0 -10px;padding:6px 10px 8px">\n    <div style="font-size:11px;color:var(--ink2);margin-bottom:2px">moc progowa (FTP) <span id="trendy-ftp-val2" style="font-weight:600"></span></div>\n    <div style="position:relative;width:100%;height:80px">\n      <canvas id="trendy-ftp-canvas"></canvas>\n    </div>\n  </div>'
if t.count(old_ftp)==1:
    t=t.replace(old_ftp,'')
    print("removed ftp panel")

# powieksz glowny wykres
t=t.replace("height:360px","height:400px")
t=t.replace("forma2-data.js?v=17","forma2-data.js?v=18")
open(p,"w").write(t)
print("html done")
