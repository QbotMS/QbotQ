p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# zamieniam caly blok tworzenia wierszy dni
old_start=s.index("ks.forEach(function(ds){var dd2=days[ds]")
old_end=s.index("rows.appendChild(div);\n  });")+len("rows.appendChild(div);\n  });")
old=s[old_start:old_end]

new='''ks.forEach(function(ds){var dd2=days[ds]||{};var rr=rmap[ds]||[];
    var lbl=qDayName(ds)+" "+ds.slice(8)+"."+(parseInt(ds.slice(5,7)));
    var sleepLbl=dd2.sleep_score?"sen "+dd2.sleep_score:"sen "+qN(dd2.sleep,1)+"h";
    var ents=(entMap[ds]||[]);
    var entHtml=ents.map(function(e){return e.kind==="illness"?'<span style="color:#4eca6a">\U0001F915 '+qEsc(e.title||"choroba")+"</span>":e.kind==="feel"?'<span style="color:#d9a441">\U0001F60A '+qEsc(e.title||"")+"</span>":"";}).filter(Boolean).join(" ");
    var actHtml=rr.length?rr.map(function(r){return '\U0001F6B4\U0001F3FB '+(r.dist_km?qN(r.dist_km,0)+"km":"")+(r.duration_s?" "+qHM(r.duration_s):"");}).join(", "):'<span class="muted">odpoczynek</span>';
    var readLbl=dd2.readiness_label||"\u2014";
    var rdyCls=dd2.readiness>0.3?"good":dd2.readiness>-0.3?"":"bad";
    var moreH='<div class="g4"><div class="mini"><p class="lbl">FTP</p><div class="v">'+qN(dd2.ftp,0)+'</div></div><div class="mini"><p class="lbl">Forma/zmecz.</p><div class="v">'+qN(dd2.ctl,0)+'/'+qN(dd2.atl,0)+'</div></div><div class="mini"><p class="lbl">Swiezosc</p><div class="v">'+(dd2.tsb>0?"+":"")+qN(dd2.tsb,1)+'</div></div><div class="mini"><p class="lbl">Gotowosc</p><div class="v">'+(typeof dd2.readiness==="number"?(dd2.readiness>0?"+":"")+qN(dd2.readiness,2):"\u2014")+'</div></div></div>';
    if(rr.length)moreH+='<div style="margin-top:8px">'+rr.map(function(r){return '<a class="link" href="/raport-jazdy.html?ride='+encodeURIComponent(r.ride_key)+'">Raport \u2192</a>';}).join(" \u00b7 ")+'</div>';
    var div=document.createElement("div");div.className="drow";
    div.innerHTML='<span class="dc">'+lbl+'</span><span class="pill small '+rdyCls+'">'+qEsc(readLbl)+'</span><span class="da">'+actHtml+'</span><span class="dw">'+sleepLbl+' \u00b7 HRV '+qN(dd2.hrv,0)+'</span><span class="de">'+entHtml+'</span><span class="chev">\u203a</span><div class="more">'+moreH+'</div>';
    div.addEventListener("click",function(){div.classList.toggle("open");div.querySelector(".chev").textContent=div.classList.contains("open")?"\u2304":"\u203a";});
    rows.appendChild(div);
  });'''

s=s[:old_start]+new+s[old_end:]
open(p,"w").write(s)
print("forma days: grid like start")
