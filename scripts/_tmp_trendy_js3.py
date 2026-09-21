p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()
old_start=s.index("function renderTrendy(){")
old_end=s.index("/* --- ODZYWIANIE ---")

new_fn='''function renderTrendy(){
  var S=forma.series||[];if(!S.length)return;
  var SN=S.slice(-RNG);var T=SN[SN.length-1]||{};var S0=SN[0]||{};
  var N=SN.length;if(N<2)return;
  var labels=[],ctlD=[],atlD=[],tsbD=[];
  SN.forEach(function(s2){
    labels.push(s2.day.slice(5));
    ctlD.push(s2.ctl_xss!=null?Math.round(s2.ctl_xss*10)/10:s2.ctl!=null?Math.round(s2.ctl*10)/10:null);
    atlD.push(s2.atl_raw!=null?Math.round(s2.atl_raw*10)/10:s2.atl!=null?Math.round(s2.atl*10)/10:null);
    tsbD.push(s2.tsb_raw!=null?Math.round(s2.tsb_raw*10)/10:s2.tsb!=null?Math.round(s2.tsb*10)/10:null);
  });
  /* kolory z ui2.css */
  var isDark=document.documentElement.classList.contains("theme-dark");
  var ctlCol="#2ecc71",atlCol="#e67e22",tsbCol="#9b59b6";
  var gridCol=isDark?"rgba(255,255,255,0.08)":"rgba(0,0,0,0.08)";
  var txtCol=isDark?"#999":"#666";
  /* niszcz stary chart */
  if(window._trendyChart){window._trendyChart.destroy();window._trendyChart=null;}
  var canvas=q$("trendy-canvas");if(!canvas)return;
  /* choroby: pionowe linie jako plugin */
  var illDays=[];(cal.entries||[]).forEach(function(e){if(e.kind!=="illness")return;for(var j=0;j<N;j++){if(SN[j].day===e.day){illDays.push({idx:j,label:(e.title||"choroba").slice(0,15)});break;}}});
  var vertPlugin={id:"vertLines",afterDraw:function(chart){var ctx=chart.ctx;var xA=chart.scales.x;var yA=chart.scales.y;illDays.forEach(function(ill){var x=xA.getPixelForValue(ill.idx);ctx.save();ctx.strokeStyle="rgba(231,76,60,0.5)";ctx.lineWidth=1;ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(x,yA.top);ctx.lineTo(x,yA.bottom);ctx.stroke();ctx.fillStyle="rgba(231,76,60,0.7)";ctx.font="10px sans-serif";ctx.textAlign="center";ctx.fillText(ill.label,x,yA.bottom+12);ctx.restore();});}};
  window._trendyChart=new Chart(canvas,{
    type:"line",
    data:{labels:labels,datasets:[
      {label:"forma (CTL)",data:ctlD,borderColor:ctlCol,backgroundColor:ctlCol+"22",borderWidth:2.5,pointRadius:0,pointHoverRadius:5,tension:0.3,fill:false},
      {label:"zmeczenie (ATL)",data:atlD,borderColor:atlCol,backgroundColor:atlCol+"22",borderWidth:2.5,pointRadius:0,pointHoverRadius:5,tension:0.3,fill:false},
      {label:"swiezosc (TSB)",data:tsbD,borderColor:tsbCol,backgroundColor:tsbCol+"22",borderWidth:2,borderDash:[6,4],pointRadius:0,pointHoverRadius:5,tension:0.3,fill:true}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
      plugins:{legend:{display:true,position:"top",labels:{usePointStyle:true,pointStyle:"line",boxWidth:20,padding:12,color:txtCol,font:{size:12}}},
        tooltip:{backgroundColor:isDark?"#2a2a2a":"#fff",titleColor:isDark?"#eee":"#333",bodyColor:isDark?"#ccc":"#555",borderColor:isDark?"#444":"#ddd",borderWidth:1,padding:10,displayColors:true,
          callbacks:{label:function(ctx){return ctx.dataset.label+": "+ctx.parsed.y}}}},
      scales:{x:{ticks:{color:txtCol,font:{size:10},maxTicksLimit:8,maxRotation:0},grid:{display:false}},
        y:{ticks:{color:txtCol,font:{size:11}},grid:{color:gridCol},
          afterBuildTicks:function(axis){/* linia zero */}}}
    },
    plugins:[vertPlugin]
  });
  /* komentarz */
  var cEl=q$("trendy-comment");if(cEl){
    var ctlNow=ctlD[N-1]||0,ctlPrev=ctlD[0]||0,tsbNow=tsbD[N-1]||0;
    var parts=[];
    if(ctlNow>ctlPrev+3)parts.push("forma ro\\u015Bnie ("+Math.round(ctlPrev)+" \\u2192 "+Math.round(ctlNow)+")");
    else if(ctlNow<ctlPrev-3)parts.push("forma spada ("+Math.round(ctlPrev)+" \\u2192 "+Math.round(ctlNow)+")");
    else parts.push("forma stabilna (~"+Math.round(ctlNow)+")");
    if(tsbNow>15)parts.push("du\\u017Ca \\u015Bwie\\u017Co\\u015B\\u0107 (+"+Math.round(tsbNow)+") \\u2014 mo\\u017Cesz jecha\\u0107 mocno");
    else if(tsbNow>0)parts.push("lekka \\u015Bwie\\u017Co\\u015B\\u0107 (+"+Math.round(tsbNow)+")");
    else if(tsbNow>-10)parts.push("\\u015Bwie\\u017Co\\u015B\\u0107 blisko zera");
    else parts.push("zm\\u0119czony (TSB "+Math.round(tsbNow)+")");
    cEl.textContent=parts.join(" \\u00b7 ");
  }
  /* FTP sparkline */
  if(window._ftpChart){window._ftpChart.destroy();window._ftpChart=null;}
  var ftpCanvas=q$("trendy-ftp-canvas");
  var ftpArr=SN.map(function(s2){return s2.ftp_est_w||s2.ftp||null;});
  var ftpNow=ftpArr[N-1]||0,ftpPrev=ftpArr[0]||0,ftpD=ftpNow-ftpPrev;
  var fEl=q$("trendy-ftp-val");
  if(fEl)fEl.innerHTML=Math.round(ftpNow)+' W <span style="font-size:14px;color:'+(ftpD>=0?"var(--good)":"var(--bad)")+'">'+(ftpD>0?"+":"")+Math.round(ftpD)+' W / '+RNG+' dni</span>';
  if(ftpCanvas){window._ftpChart=new Chart(ftpCanvas,{type:"line",data:{labels:labels,datasets:[{data:ftpArr,borderColor:isDark?"#7fb0e0":"#4a7fb5",borderWidth:2,pointRadius:0,tension:0.3,fill:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{enabled:false}},scales:{x:{display:false},y:{display:false}}}});}
  /* statystyki */
  var sg=q$("trendy-stats");
  if(sg){var days2=SN.map(function(s2){return s2.day;});var rideCnt=0,rideKm=0,seen2={};(rides.rides||[]).forEach(function(r){if(seen2[r.ride_key])return;seen2[r.ride_key]=1;if(r.date>=days2[0]&&r.date<=days2[N-1]){rideCnt++;rideKm+=(r.dist_km||0);}});
    sg.innerHTML='<div class="mini"><p class="lbl">jazdy</p><div class="v">'+rideCnt+'</div></div><div class="mini"><p class="lbl">dystans</p><div class="v">'+Math.round(rideKm)+' km</div></div><div class="mini"><p class="lbl">FTP</p><div class="v">'+Math.round(ftpNow)+' W</div></div><div class="mini"><p class="lbl">W/kg</p><div class="v">'+qN(T.w_per_kg||T.wkg,2)+'</div></div>';}
}
'''
s=s[:old_start]+new_fn+s[old_end:]
open(p,"w").write(s)
print("renderTrendy v3 chartjs done, len:", len(s))
