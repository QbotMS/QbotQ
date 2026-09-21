p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# 1) gorny wykres: tooltip enabled z custom callback ktory dorzuca CP/LTP
old_top_tip='tooltip:{enabled:false,external:function(ctx){showTip(ctx,null);}}'
assert s.count(old_top_tip)==1
new_top_tip='''tooltip:{backgroundColor:isDark?"rgba(30,30,30,0.95)":"rgba(255,255,255,0.95)",titleColor:isDark?"#ddd":"#333",bodyColor:isDark?"#bbb":"#555",borderColor:isDark?"#444":"#ddd",borderWidth:1,padding:10,displayColors:true,
          callbacks:{title:function(items){if(!items.length)return "";var i=items[0].dataIndex;return SN[i]?SN[i].day:"";},
            label:function(ctx){if(ctx.dataset.label==="obc. dnia"&&!ctx.parsed.y)return null;return ctx.dataset.label+": "+Math.round(ctx.parsed.y*10)/10;},
            afterBody:function(items){if(!items.length)return "";var i=items[0].dataIndex;var lines=[];if(cpD[i]!=null)lines.push("CP: "+Math.round(cpD[i])+" W");if(ltpD[i]!=null)lines.push("LTP: "+Math.round(ltpD[i])+" W");return lines;}}}'''
s=s.replace(old_top_tip,new_top_tip)

# 2) dolny wykres: tooltip enabled, prosty
old_bot_tip='tooltip:{enabled:false,external:function(ctx){showTip(null,ctx);}}'
assert s.count(old_bot_tip)==1
new_bot_tip='tooltip:{backgroundColor:isDark?"rgba(30,30,30,0.95)":"rgba(255,255,255,0.95)",titleColor:isDark?"#ddd":"#333",bodyColor:isDark?"#bbb":"#555",borderColor:isDark?"#444":"#ddd",borderWidth:1,padding:10,displayColors:true,callbacks:{title:function(items){if(!items.length)return "";var i=items[0].dataIndex;return SN[i]?SN[i].day:"";}}}'
s=s.replace(old_bot_tip,new_bot_tip)

# 3) usun showTip i trendy-tip event listenery (juz niepotrzebne)
for needle in ['/* wspolny tooltip */','function showTip(','canvas.addEventListener("mouseleave",function(){var tip','q$("trendy-pwr-canvas").addEventListener("mouseleave"']:
    i=s.find(needle)
    if i>=0:
        # znajdz koniec bloku
        pass  # zostawiam — nie szkodzą, JS po prostu ich nie znajdzie

open(p,"w").write(s)
print("tooltips: native Chart.js with CP/LTP in afterBody")
