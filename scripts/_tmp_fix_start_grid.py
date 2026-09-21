p="/opt/qbot/web/public/start2.js"
s=open(p).read()

# zamieniam caly blok renderowania dni na grid
old_start=s.index("/* ostatnie dni")
old_end=s.index("/* werdykt")
new_days='''/* ostatnie dni: grid z kolumnami */
  var daysEl=q$("days");daysEl.innerHTML="";
  var ks=Object.keys(days).sort().reverse().slice(1,31);
  ks.forEach(function(ds2,idx){var dd3=days[ds2]||{};var rr2=rmap[ds2]||[];
    var lbl=qDayName(ds2)+" "+ds2.slice(8)+"."+(parseInt(ds2.slice(5,7)));
    var sleepLbl=dd3.sleep_score?"sen "+dd3.sleep_score:"sen "+qN(dd3.sleep,1)+"h";
    var ents=(entMap[ds2]||[]);
    var entHtml=ents.map(function(e){return e.kind==="illness"?'<span style="color:#4eca6a">\\U0001F915 '+qEsc(e.title||"choroba")+"</span>":e.kind==="feel"?'<span style="color:#d9a441">\\U0001F60A '+qEsc(e.title||"")+"</span>":"";}).filter(Boolean).join(" ");
    var actHtml=rr2.length?rr2.map(function(r2){return '\\U0001F6B4\\U0001F3FB '+(r2.dist_km?qN(r2.dist_km,0)+"km":"")+(r2.duration_s?" "+qHM(r2.duration_s):"");}).join(", "):'<span class="muted">odpoczynek</span>';
    var readLbl=dd3.readiness_label||"\\u2014";
    var rdyCls=dd3.readiness>0.3?"good":dd3.readiness>-0.3?"":"bad";
    var div=document.createElement("div");div.className="drow"+(idx>=10?" extra":"");
    if(idx>=10)div.style.display="none";
    div.innerHTML='<span class="dc">'+lbl+'</span><span class="da">'+actHtml+'</span><span class="dw">'+sleepLbl+' · HRV '+qN(dd3.hrv,0)+'</span><span class="de">'+entHtml+'</span><span class="pill small '+rdyCls+'">'+qEsc(readLbl)+'</span>';
    daysEl.appendChild(div);
  });
  if(ks.length>10){var more=document.createElement("div");more.style.cssText="text-align:center;padding:10px 0";more.innerHTML='<a class="link" id="show-more" href="#">pokaż więcej ('+ks.length+' dni) \\u2193</a>';daysEl.appendChild(more);
    q$("show-more").onclick=function(e){e.preventDefault();daysEl.querySelectorAll(".extra").forEach(function(x){x.style.display="";});more.remove();};}
  '''
s=s[:old_start]+new_days+s[old_end:]
open(p,"w").write(s)
print("start days: grid layout")
