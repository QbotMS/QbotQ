p="/opt/qbot/web/public/forma.html"
t=open(p).read()

# zamieniam card z jednym canvasem na dwa + przelacznik
old_card_start=t.index('<div class="card" style="padding:14px 10px 0;overflow:hidden">')
old_card_end=t.index('</div>\n</div>\n<div style="font-size:13.5px')
# caly blok od card do zamkniecia

new_card='''<div class="card" style="padding:14px 10px 8px">
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
<div id="trendy-tip" style="display:none;position:fixed;z-index:999;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:12.5px;line-height:1.6;pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,0.15)"></div>
'''

t=t[:old_card_start]+new_card+t[old_card_end:]
t=t.replace("forma2-data.js?v=19","forma2-data.js?v=20")
open(p,"w").write(t)
print("html: two charts + power toggle done")
