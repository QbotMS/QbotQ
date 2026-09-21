p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()
old_start=s.index("function renderTrendy(){")
old_end=s.index("/* --- ODZYWIANIE ---")

new_fn='''function renderTrendy(){
  var S=forma.series||[];if(!S.length)return;
  var SN=S.slice(-RNG);var T=SN[SN.length-1]||{};var N=SN.length;if(N<2)return;
  var labels=[],ctlD=[],atlD=[],tsbD=[],xssD=[],cpD=[],ltpD=[];
  var MON=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paz","lis","gru"];
  SN.forEach(function(s2){
    var d=s2.day.slice(8);var m=parseInt(s2.day.slice(5,7))-1;
    labels.push(d==="01"||d==="15"?MON[m]:"");
    ctlD.push(s2.ctl_xss!=null?Math.round(s2.ctl_xss*10)/10:null);
    atlD.push(s2.atl_raw!=null?Math.round(s2.atl_raw*10)/10:null);
    tsbD.push(s2.tsb_raw!=null?Math.round(s2.tsb_raw*10)/10:null);
    var _xd=0;(rides.rides||[]).forEach(function(r){if(r.date===s2.day)_xd+=(r.xss||0);});xssD.push(_xd);
    cpD.push(s2.ftp_est_w||s2.ftp||null);
    ltpD.push(s2.ltp_modelq_w||null);
  });
  var isDark=document.documentElement.classList.contains("theme-dark");
  var gridCol=isDark?"rgba(255,255,255,0.06)":"rgba(0,0,0,0.06)";
  var txtCol=isDark?"#888":"#999";
  /* choroby */
  var illDays=[];(cal.entries||[]).forEach(function(e){if(e.kind!=="illness")return;for(var j=0;j<N;j++){if(SN[j].day===e.day){illDays.push({idx:j,label:(e.title||"choroba").slice(0,12)});break;}}});
  var vertPlugin={id:"vertLines",afterDraw:function(chart){var ctx=chart.ctx;var xA=chart.scales.x;var yA=chart.scales.y;illDays.forEach(function(ill){var x=xA.getPixelForValue(ill.idx);ctx.save();ctx.strokeStyle="rgba(231,76,60,0.4)";ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x,yA.top);ctx.lineTo(x,yA.bottom);ctx.stroke();ctx.fillStyle="rgba(231,76,60,0.6)";ctx.font="9px sans-serif";ctx.textAlign="center";ctx.fillText(ill.label,x,yA.top-4);ctx.restore();});}};
  /* GORNY WYKRES */
  if(window._trendyChart){window._trendyChart.destroy();}
  var canvas=q$("trendy-canvas");if(!canvas)return;
  window._trendyChart=new Chart(canvas,{type:"line",data:{labels:labels,datasets:[
    {label:"forma (CTL)",data:ctlD,borderColor:"#e67e22",borderWidth:3,pointRadius:0,pointHoverRadius:5,tension:0.4,fill:false,yAxisID:"y",order:1},
    {label:"zmeczenie (ATL)",data:atlD,borderColor:isDark?"#5a5a5a":"#bbb",backgroundColor:isDark?"rgba(90,90,90,0.15)":"rgba(180,180,180,0.15)",borderWidth:1.5,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:true,yAxisID:"y",order:2},
    {label:"swiezosc (TSB)",data:tsbD,borderColor:"#1a7a5a",borderWidth:2,borderDash:[6,3],pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"y2",order:1},
    {type:"bar",label:"obc. dnia",data:xssD,backgroundColor:isDark?"rgba(255,255,255,0.12)":"rgba(0,0,0,0.10)",borderWidth:0,yAxisID:"y3",order:3,barPercentage:0.8,categoryPercentage:1}
  ]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
    plugins:{legend:{display:true,position:"top",labels:{usePointStyle:true,pointStyle:"line",boxWidth:24,padding:14,color:txtCol,font:{size:12},filter:function(it){return it.text!=="obc. dnia";}}},
      tooltip:{enabled:false,external:function(ctx){showTip(ctx,null);}}},
    scales:{x:{ticks:{color:txtCol,font:{size:11},maxRotation:0,autoSkip:true,maxTicksLimit:10},grid:{display:false}},
      y:{position:"left",ticks:{color:"#e67e22",font:{size:11}},grid:{color:gridCol},title:{display:true,text:"forma / zmecz.",color:txtCol,font:{size:11}}},
      y2:{position:"right",ticks:{color:"#1a7a5a",font:{size:11}},grid:{drawOnChartArea:false},title:{display:true,text:"swiezosc",color:"#1a7a5a",font:{size:11}}},
      y3:{display:false,beginAtZero:true}}
  },plugins:[vertPlugin]});
  /* DOLNY WYKRES (moc) */
  var PWRMODE="cp";
  function buildPwr(){
    if(window._pwrChart){window._pwrChart.destroy();}
    var pwrCanvas=q$("trendy-pwr-canvas");if(!pwrCanvas)return;
    var ds=[];
    if(PWRMODE==="cp"||PWRMODE==="oba")ds.push({label:"CP",data:cpD,borderColor:"#3b82f6",borderWidth:2.5,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false});
    if(PWRMODE==="ltp"||PWRMODE==="oba")ds.push({label:"LTP",data:ltpD,borderColor:"#9b59b6",borderWidth:2,borderDash:[4,3],pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false});
    window._pwrChart=new Chart(pwrCanvas,{type:"line",data:{labels:labels,datasets:ds},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
      plugins:{legend:{display:ds.length>1,position:"top",labels:{usePointStyle:true,pointStyle:"line",boxWidth:20,padding:10,color:txtCol,font:{size:11}}},
        tooltip:{enabled:false,external:function(ctx){showTip(null,ctx);}}},
      scales:{x:{display:false},y:{position:"left",ticks:{color:txtCol,font:{size:10}},grid:{color:gridCol}}}}});
    /* sync hover */
    canvas.addEventListener("mousemove",function(evt){syncHover(window._trendyChart,window._pwrChart,evt);});
    canvas.addEventListener("mouseleave",function(){clearSync(window._pwrChart);});
    pwrCanvas.addEventListener("mousemove",function(evt){syncHover(window._pwrChart,window._trendyChart,evt);});
    pwrCanvas.addEventListener("mouseleave",function(){clearSync(window._trendyChart);});
    var pl=q$("pwr-label");if(pl){var cpNow=cpD[N-1],ltpNow=ltpD[N-1];pl.textContent=(cpNow?"CP "+Math.round(cpNow)+" W":"")+(cpNow&&ltpNow?" / ":"")+(ltpNow?"LTP "+Math.round(ltpNow)+" W":"");}
  }
  function syncHover(src,dst,evt){
    var pts=src.getElementsAtEventForMode(evt,"index",{intersect:false},true);
    if(pts.length){var idx=pts[0].index;var els=[];dst.data.datasets.forEach(function(_,di){els.push({datasetIndex:di,index:idx});});
      dst.setActiveElements(els);dst.update("none");}
  }
  function clearSync(dst){dst.setActiveElements([]);dst.update("none");}
  /* wspolny tooltip */
  function showTip(topCtx,botCtx){
    var tip=document.getElementById("trendy-tip");if(!tip)return;
    var ctx=topCtx||botCtx;if(!ctx||!ctx.tooltip||!ctx.tooltip.dataPoints||!ctx.tooltip.dataPoints.length){tip.style.display="none";return;}
    var idx=ctx.tooltip.dataPoints[0].dataIndex;
    var day=SN[idx]?SN[idx].day:"";
    var html='<b>'+day+'</b><br>';
    html+='<span style="color:#e67e22">forma: '+(ctlD[idx]!=null?Math.round(ctlD[idx]):"—")+'</span><br>';
    html+='<span style="color:'+(isDark?"#777":"#aaa")+'">zmeczenie: '+(atlD[idx]!=null?Math.round(atlD[idx]):"—")+'</span><br>';
    html+='<span style="color:#1a7a5a">swiezosc: '+(tsbD[idx]!=null?Math.round(tsbD[idx]):"—")+'</span><br>';
    if(xssD[idx])html+='obc. dnia: '+Math.round(xssD[idx])+'<br>';
    html+='<span style="color:#3b82f6">CP: '+(cpD[idx]!=null?Math.round(cpD[idx])+" W":"—")+'</span>';
    if(ltpD[idx]!=null)html+=' <span style="color:#9b59b6">LTP: '+Math.round(ltpD[idx])+' W</span>';
    tip.innerHTML=html;tip.style.display="block";
    var ev=ctx.tooltip.caretX!=null?ctx.tooltip:ctx.tooltip;
    var rect=(topCtx?q$("trendy-canvas"):q$("trendy-pwr-canvas")).getBoundingClientRect();
    tip.style.left=Math.min(rect.left+(ctx.tooltip.caretX||0)+12,window.innerWidth-200)+"px";
    tip.style.top=(rect.top+(ctx.tooltip.caretY||0)-10)+"px";
  }
  canvas.addEventListener("mouseleave",function(){var tip=document.getElementById("trendy-tip");if(tip)tip.style.display="none";});
  q$("trendy-pwr-canvas").addEventListener("mouseleave",function(){var tip=document.getElementById("trendy-tip");if(tip)tip.style.display="none";});
  buildPwr();
  /* przelacznik CP/LTP */
  q$("pwr-seg").querySelectorAll("button").forEach(function(b){b.addEventListener("click",function(){
    q$("pwr-seg").querySelectorAll("button").forEach(function(x){x.classList.remove("on");});b.classList.add("on");PWRMODE=b.dataset.p;buildPwr();});});
  /* komentarz */
  var cEl=q$("trendy-comment");if(cEl){
    var ctlNow=ctlD[N-1]||0,ctlPrev=ctlD[0]||0,tsbNow=tsbD[N-1]||0;
    var parts=[];
    if(ctlNow>ctlPrev+3)parts.push("forma rosnie ("+Math.round(ctlPrev)+" \\u2192 "+Math.round(ctlNow)+")");
    else if(ctlNow<ctlPrev-3)parts.push("forma spada ("+Math.round(ctlPrev)+" \\u2192 "+Math.round(ctlNow)+")");
    else parts.push("forma stabilna (~"+Math.round(ctlNow)+")");
    if(tsbNow>15)parts.push("duza swiezosc (+"+Math.round(tsbNow)+")");
    else if(tsbNow>0)parts.push("lekka swiezosc (+"+Math.round(tsbNow)+")");
    else if(tsbNow>-10)parts.push("swiezosc blisko zera");
    else parts.push("zmeczony (TSB "+Math.round(tsbNow)+")");
    cEl.textContent=parts.join(" \\u00b7 ");
  }
  /* statystyki */
  var sg=q$("trendy-stats");
  if(sg){var days2=SN.map(function(s2){return s2.day;});var rideCnt=0,rideKm=0,seen2={};(rides.rides||[]).forEach(function(r){if(seen2[r.ride_key])return;seen2[r.ride_key]=1;if(r.date>=days2[0]&&r.date<=days2[N-1]){rideCnt++;rideKm+=(r.dist_km||0);}});
    sg.innerHTML='<div class="mini"><p class="lbl">jazdy</p><div class="v">'+rideCnt+'</div></div><div class="mini"><p class="lbl">dystans</p><div class="v">'+Math.round(rideKm)+' km</div></div><div class="mini"><p class="lbl">CP</p><div class="v">'+Math.round(cpD[N-1]||0)+' W</div></div><div class="mini"><p class="lbl">W/kg</p><div class="v">'+qN(T.w_per_kg||T.wkg,2)+'</div></div>';}
}
'''
s=s[:old_start]+new_fn+s[old_end:]
open(p,"w").write(s)
print("renderTrendy v5: two synced charts + shared tooltip + pwr toggle")
