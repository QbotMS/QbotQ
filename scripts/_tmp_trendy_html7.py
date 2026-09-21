p="/opt/qbot/web/public/forma.html"
t=open(p).read()

old='''<div class="card" style="padding:14px 10px 0;overflow:hidden">
  <div style="position:relative;width:100%;height:400px">
    <canvas id="trendy-canvas"></canvas>
  </div>
  
</div>
<div style="font-size:13.5px;color:var(--ink2);margin:8px 2px 14px;line-height:1.5" id="trendy-comment"></div>

<div class="g4" id="trendy-stats" style="margin-top:12px"></div>'''

new='''<div class="card" style="padding:14px 10px 8px">
  <div style="position:relative;width:100%;height:300px">
    <canvas id="trendy-canvas"></canvas>
  </div>
</div>
<div class="card" style="padding:8px 10px 8px;margin-top:2px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
    <div class="seg" id="pwr-seg"><button class="on" data-p="cp">CP</button><button data-p="ltp">LTP</button><button data-p="oba">CP + LTP</button></div>
    <span id="pwr-label" style="font-size:12px;color:var(--ink2)"></span>
  </div>
  <div style="position:relative;width:100%;height:120px">
    <canvas id="trendy-pwr-canvas"></canvas>
  </div>
</div>
<div style="font-size:13.5px;color:var(--ink2);margin:8px 2px 14px;line-height:1.5" id="trendy-comment"></div>
<div class="g4" id="trendy-stats" style="margin-top:12px"></div>'''

assert t.count(old)==1
t=t.replace(old,new)
t=t.replace("forma2-data.js?v=19","forma2-data.js?v=20")
open(p,"w").write(t)
print("html done: two charts + pwr toggle")
