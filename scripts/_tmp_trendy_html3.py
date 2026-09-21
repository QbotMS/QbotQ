p="/opt/qbot/web/public/forma.html"
t=open(p).read()

a=t.index('<!-- ============ TRENDY ============ -->')
b=t.index('<!-- ============ ODZYWIANIE ============ -->')

new_html='''<!-- ============ TRENDY ============ -->
<section class="panel stack" id="p-trendy" hidden>
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
  <div class="seg" id="rng"><button>30 dni</button><button class="on">90 dni</button><button>rok</button></div>
</div>
<div class="card" style="padding:14px 10px 8px">
  <div style="position:relative;width:100%;height:260px">
    <canvas id="trendy-canvas"></canvas>
  </div>
</div>
<div style="font-size:13.5px;color:var(--ink2);margin:8px 2px 14px;line-height:1.5" id="trendy-comment"></div>
<div class="card" style="padding:10px">
  <div style="font-size:12.5px;color:var(--ink2);margin-bottom:4px">Moc progowa (FTP)</div>
  <div style="display:flex;align-items:center;gap:12px">
    <span id="trendy-ftp-val" style="font-size:22px;font-weight:600;white-space:nowrap"></span>
    <div style="position:relative;flex:1;height:40px"><canvas id="trendy-ftp-canvas"></canvas></div>
  </div>
</div>
<div class="g4" id="trendy-stats" style="margin-top:12px"></div>
</section>

'''
t=t[:a]+new_html+t[b:]
# dodaj Chart.js przed forma2-data.js
if 'chart.umd' not in t:
    t=t.replace('forma2-data.js','https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>\n<script src="/forma2-data.js')
t=t.replace("forma2-data.js?v=12","forma2-data.js?v=13")
open(p,"w").write(t)
print("trendy html v3 + chartjs done")
