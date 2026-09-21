p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()
old_start=s.index("function renderTrendy(){")
old_end=s.index("/* --- ODZYWIANIE ---")

new_fn='''function renderTrendy(){
  var S=forma.series||[];if(!S.length)return;
  var SN=S.slice(-RNG);var T=SN[SN.length-1]||{};var S0=SN[0]||{};
  var N=SN.length;if(N<2)return;
  var labels=[],ctlD=[],atlD=[],tsbD=[],xssD=[];
  var MON=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paz","lis","gru"];
  SN.forEach(function(s2){
    var d=s2.day.slice(8);var m=parseInt(s2.day.slice(5,7))-1;
    labels.push(d==="01"||d==="15"?MON[m]+(d==="01"?" "+s2.day.slice(0,4):""):"");
    ctlD.push(s2.ctl_xss!=null?Math.round(s2.ctl_xss*10)/10:null);
    atlD.push(s2.atl_raw!=null?Math.round(s2.atl_raw*10)/10:null);
    tsbD.push(s2.tsb_raw!=null?Math.round(s2.tsb_raw*10)/10:null);
    xssD.push(s2.xss_day||0);
  });
  var isDark=document.documentElement.classList.contains("theme-dark");
  var gridCol=isDark?"rgba(255,255,255,0.06)":"rgba(0,0,0,0.06)";
  var txtCol=isDark?"#888":"#999";
  if(window._trendyChart){window._trendyChart.destroy();window._trendyChart=null;}
  var canvas=q$("trendy-canvas");if(!canvas)return;
  var illDays=[];(cal.entries||[]).forEach(function(e){if(e.kind!=="illness")return;for(var j=0;j<N;j++){if(SN[j].day===e.day){illDays.push({idx:j,label:(e.title||"choroba").slice(0,12)});break;}}});
  var vertPlugin={id:"vertLines",afterDraw:function(chart){var ctx=chart.ctx;var xA=chart.scales.x;var yA=chart.scales.y;illDays.forEach(function(ill){var x=xA.getPixelForValue(ill.idx);ctx.save();ctx.strokeStyle="rgba(231,76,60,0.4)";ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x,yA.top);ctx.lineTo(x,yA.bottom);ctx.stroke();ctx.fillStyle="rgba(231,76,60,0.6)";ctx.font="9px sans-serif";ctx.textAlign="center";ctx.fillText(ill.label,x,yA.top-4);ctx.restore();});}};
  window._trendyChart=new Chart(canvas,{
    type:"line",
    data:{labels:labels,datasets:[
      {label:"forma (CTL)",data:ctlD,borderColor:"#e67e22",backgroundColor:"transparent",borderWidth:3,pointRadius:0,pointHoverRadius:5,tension:0.4,fill:false,yAxisID:"y",order:1},
      {label:"zmeczenie (ATL)",data:atlD,borderColor:isDark?"#5a5a5a":"#bbb",backgroundColor:isDark?"rgba(90,90,90,0.15)":"rgba(180,180,180,0.15)",borderWidth:1.5,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:true,yAxisID:"y",order:2},
      {label:"swiezosc (TSB)",data:tsbD,borderColor:"#1a7a5a",backgroundColor:"transparent",borderWidth:2,borderDash:[6,3],pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"y2",order:1},
      {type:"bar",label:"obc. dnia",data:xssD,backgroundColor:isDark?"rgba(255,255,255,0.12)":"rgba(0,0,0,0.10)",borderWidth:0,yAxisID:"y3",order:3,barPercentage:0.8,categoryPercentage:1}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
      plugins:{legend:{display:true,position:"top",labels:{usePointStyle:true,pointStyle:"line",boxWidth:24,padding:14,color:txtCol,font:{size:12},filter:function(item){return item.text!=="obc. dnia";}}},
        tooltip:{backgroundColor:isDark?"rgba(30,30,30,0.95)":"rgba(255,255,255,0.95)",titleColor:isDark?"#ddd":"#333",bodyColor:isDark?"#bbb":"#555",borderColor:isDark?"#444":"#ddd",borderWidth:1,padding:10,displayColors:true,
          callbacks:{title:function(items){if(!items.length)return "";var i=items[0].dataIndex;return SN[i]?SN[i].day:"";},
            label:function(ctx){if(ctx.dataset.label==="obc. dnia"&&!ctx.parsed.y)return null;return ctx.dataset.label+": "+Math.round(ctx.parsed.y*10)/10;}}}},
      scales:{
        x:{ticks:{color:txtCol,font:{size:11},maxRotation:0,autoSkip:true,maxTicksLimit:10},grid:{display:false}},
        y:{position:"left",ticks:{color:"#e67e22",font:{size:11}},grid:{color:gridCol},title:{display:true,text:"forma / zmecz.",color:txtCol,font:{size:11}}},
        y2:{position:"right",ticks:{color:"#1a7a5a",font:{size:11}},grid:{drawOnChartArea:false},title:{display:true,text:"swiezosc",color:"#1a7a5a",font:{size:11}}},
        y3:{display:false,beginAtZero:true,position:"right"}
      }
    },
    plugins:[vertPlugin]
  });
  /* komentarz */
  var cEl=q$("trendy-comment");if(cEl){
    var ctlNow=ctlD[N-1]||0,ctlPrev=ctlD[0]||0,tsbNow=tsbD[N-1]||0,atlNow=atlD[N-1]||0;
    var parts=[];
    if(ctlNow>ctlPrev+3)parts.push("forma ro\\u015Bnie ("+Math.round(ctlPrev)+" \\u2192 "+Math.round(ctlNow)+")");
    else if(ctlNow<ctlPrev-3)parts.push("forma spada ("+Math.round(ctlPrev)+" \\u2192 "+Math.round(ctlNow)+")");
    else parts.push("forma stabilna (~"+Math.round(ctlNow)+")");
    if(tsbNow>15)parts.push("du\\u017Ca \\u015Bwie\\u017Co\\u015B\\u0107 (+"+Math.round(tsbNow)+")");
    else if(tsbNow>0)parts.push("lekka \\u015Bwie\\u017Co\\u015B\\u0107 (+"+Math.round(tsbNow)+")");
    else if(tsbNow>-10)parts.push("\\u015Bwie\\u017Co\\u015B\\u0107 blisko zera");
    else parts.push("zm\\u0119czony (TSB "+Math.round(tsbNow)+")");
    parts.push("zm\\u0119czenie "+Math.round(atlNow));
    cEl.textContent=parts.join(" \\u00b7 ");
  }
  /* FTP sparkline */
  if(window._ftpChart){window._ftpChart.destroy();window._ftpChart=null;}
  var ftpCanvas=q$("trendy-ftp-canvas");
  var ftpArr=SN.map(function(s2){return s2.ftp_est_w||s2.ftp||null;});
  var ftpNow=ftpArr[N-1]||0,ftpPrev=ftpArr[0]||0,ftpD=ftpNow-ftpPrev;
  var fEl=q$("trendy-ftp-val");
  if(fEl)fEl.innerHTML=Math.round(ftpNow)+' W <span style="font-size:14px;color:'+(ftpD>=0?"var(--good)":"var(--bad)")+'">'+(ftpD>0?"+":"")+Math.round(ftpD)+' W / '+RNG+' dni</span>';
  if(ftpCanvas){window._ftpChart=new Chart(ftpCanvas,{type:"line",data:{labels:labels,datasets:[{data:ftpArr,borderColor:"#e67e22",borderWidth:2,pointRadius:0,tension:0.4,fill:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{enabled:false}},scales:{x:{display:false},y:{display:false}}}});}
  /* statystyki */
  var sg=q$("trendy-stats");
  if(sg){var days2=SN.map(function(s2){return s2.day;});var rideCnt=0,rideKm=0,seen2={};(rides.rides||[]).forEach(function(r){if(seen2[r.ride_key])return;seen2[r.ride_key]=1;if(r.date>=days2[0]&&r.date<=days2[N-1]){rideCnt++;rideKm+=(r.dist_km||0);}});
    sg.innerHTML='<div class="mini"><p class="lbl">jazdy</p><div class="v">'+rideCnt+'</div></div><div class="mini"><p class="lbl">dystans</p><div class="v">'+Math.round(rideKm)+' km</div></div><div class="mini"><p class="lbl">FTP</p><div class="v">'+Math.round(ftpNow)+' W</div></div><div class="mini"><p class="lbl">W/kg</p><div class="v">'+qN(T.w_per_kg||T.wkg,2)+'</div></div>';}
}
'''
s=s[:old_start]+new_fn+s[old_end:]
open(p,"w").write(s)
print("renderTrendy v4 done, len:", len(s))
