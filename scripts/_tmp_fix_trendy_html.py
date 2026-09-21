import re
p="/opt/qbot/web/public/forma.html"
t=open(p).read()

# wycinam cala sekcje p-trendy i wstawiam nowa
a=t.index('<!-- ============ TRENDY ============ -->')
b=t.index('<!-- ============ ODZYWIANIE ============ -->')

new_trendy='''<!-- ============ TRENDY ============ -->
<section class="panel stack" id="p-trendy" hidden>
<div class="toolbar">
  <div class="seg" id="rng"><button>7 dni</button><button>30 dni</button><button class="on">90 dni</button><button>rok</button></div>
  <div class="seg" id="grp"><button class="on" data-g="moc">Moc</button><button data-g="obc">Obciążenie</button><button data-g="well">Wellness</button><button data-g="cialo">Ciało</button></div>
</div>
<div class="card">
  <div id="trendy-legend" class="legend" style="margin-bottom:8px"></div>
  <svg id="trendy-chart" class="chart" viewBox="0 0 640 160" preserveAspectRatio="none" style="width:100%;height:160px"></svg>
</div>
<div class="g4" id="trendy-metrics"></div>
<div class="card" id="trendy-stats">
  <h3 style="margin:0 0 8px;font-size:15px">Statystyki jazd</h3>
  <div class="g4" id="trendy-stats-grid"></div>
</div>
</section>

'''
t=t[:a]+new_trendy+t[b:]
t=t.replace("forma2-data.js?v=10","forma2-data.js?v=11")
open(p,"w").write(t)
print("trendy HTML rewritten")
