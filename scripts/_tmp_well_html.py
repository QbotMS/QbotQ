p="/opt/qbot/web/public/forma.html"
t=open(p).read()

# dodaj trzeci wykres przed comment
i=t.index('<div style="font-size:13.5px;color:var(--ink2);margin:8px 2px 14px')
wellness_html='''<div class="card" style="padding:8px 10px 8px;margin-top:2px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;flex-wrap:wrap;gap:6px">
    <span style="font-size:13px;font-weight:600">Wellness</span>
    <div id="well-checks" style="display:flex;gap:10px;font-size:12px">
      <label style="cursor:pointer"><input type="checkbox" data-w="sleep" checked style="margin-right:3px">sen</label>
      <label style="cursor:pointer"><input type="checkbox" data-w="hrv" checked style="margin-right:3px">HRV</label>
      <label style="cursor:pointer"><input type="checkbox" data-w="rhr" checked style="margin-right:3px">RHR</label>
      <label style="cursor:pointer"><input type="checkbox" data-w="wt" style="margin-right:3px">waga</label>
    </div>
  </div>
  <div style="position:relative;width:100%;height:140px">
    <canvas id="trendy-well-canvas"></canvas>
  </div>
</div>
'''
t=t[:i]+wellness_html+t[i:]
t=t.replace("forma2-data.js?v=21","forma2-data.js?v=22")
open(p,"w").write(t)
print("html: wellness chart added")
