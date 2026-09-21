p="/opt/qbot/web/public/forma.html"
t=open(p).read()

a=t.index('<!-- ============ TRENDY ============ -->')
b=t.index('<!-- ============ ODZYWIANIE ============ -->')

new_html='''<!-- ============ TRENDY ============ -->
<section class="panel stack" id="p-trendy" hidden>
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
  <div class="seg" id="rng"><button>30 dni</button><button class="on">90 dni</button><button>rok</button></div>
</div>
<div id="trendy-legend" style="display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:var(--ink2);margin-bottom:6px"></div>
<div class="card" style="padding:14px 10px 6px">
  <svg id="trendy-chart" viewBox="0 0 640 200" preserveAspectRatio="none" style="width:100%;height:200px;display:block"></svg>
</div>
<div style="font-size:13px;color:var(--ink2);margin:8px 0 12px;line-height:1.5" id="trendy-comment"></div>
<div class="card" style="padding:10px">
  <div style="font-size:12.5px;color:var(--ink2);margin-bottom:4px">Moc progowa (FTP)</div>
  <div style="display:flex;align-items:center;gap:12px">
    <span id="trendy-ftp-val" style="font-size:22px;font-weight:600"></span>
    <svg id="trendy-ftp-spark" viewBox="0 0 200 36" preserveAspectRatio="none" style="flex:1;height:36px"></svg>
  </div>
</div>
<div class="g4" id="trendy-stats" style="margin-top:12px"></div>
</section>

'''
t=t[:a]+new_html+t[b:]
t=t.replace("forma2-data.js?v=11","forma2-data.js?v=12")
open(p,"w").write(t)
print("trendy html v2 done")
