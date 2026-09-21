p="/opt/qbot/web/public/forma.html"
t=open(p).read()

# zamieniam sekcje wykresu: dwa canvasy w jednym bloku, bez przerwy
old_card='<div class="card" style="padding:14px 10px 8px">\n  <div style="position:relative;width:100%;height:320px">\n    <canvas id="trendy-canvas"></canvas>\n  </div>\n</div>'
assert t.count(old_card)==1

new_card='''<div class="card" style="padding:14px 10px 0;overflow:hidden">
  <div style="position:relative;width:100%;height:360px">
    <canvas id="trendy-canvas"></canvas>
  </div>
  <div style="border-top:1px solid var(--line);margin:0 -10px;padding:6px 10px 8px">
    <div style="font-size:11px;color:var(--ink2);margin-bottom:2px">moc progowa (FTP) <span id="trendy-ftp-val2" style="font-weight:600"></span></div>
    <div style="position:relative;width:100%;height:80px">
      <canvas id="trendy-ftp-canvas"></canvas>
    </div>
  </div>
</div>'''
t=t.replace(old_card,new_card)

# usuwam stary osobny blok FTP
old_ftp='<div class="card" style="padding:10px">\n  <div style="font-size:12.5px;color:var(--ink2);margin-bottom:4px">Moc progowa (FTP)</div>\n  <div style="display:flex;align-items:center;gap:12px">\n    <span id="trendy-ftp-val" style="font-size:22px;font-weight:600;white-space:nowrap"></span>\n    <div style="position:relative;flex:1;height:40px"><canvas id="trendy-ftp-canvas"></canvas></div>\n  </div>\n</div>'
if t.count(old_ftp)==1:
    t=t.replace(old_ftp,'')

t=t.replace("forma2-data.js?v=16","forma2-data.js?v=17")
open(p,"w").write(t)
print("html: stacked charts done")
