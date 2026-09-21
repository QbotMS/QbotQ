p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# wstawiam wellness chart budowanie + checkboxy po buildPwr i przelacznikach
insert_before="/* komentarz */"
assert s.count(insert_before)==1

wellness_code='''/* WELLNESS CHART */
  var sleepD=[],hrvD=[],rhrD=[],wtD=[];
  SN.forEach(function(s2){sleepD.push(s2.sleep_score||null);hrvD.push(s2.hrv_night||null);rhrD.push(s2.rhr||null);wtD.push(s2.weight_kg||null);});
  function buildWellness(){
    if(window._wellChart){window._wellChart.destroy();}
    var wc=q$("trendy-well-canvas");if(!wc)return;
    var checks=q$("well-checks");var show={sleep:true,hrv:true,rhr:true,wt:false};
    if(checks)checks.querySelectorAll("input").forEach(function(cb){show[cb.dataset.w]=cb.checked;});
    var ds=[],hasRight=show.wt;
    if(show.sleep)ds.push({label:"sen (score)",data:sleepD,borderColor:"#3b82f6",borderWidth:2,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"yw"});
    if(show.hrv)ds.push({label:"HRV",data:hrvD,borderColor:"#9b59b6",borderWidth:2,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"yw"});
    if(show.rhr)ds.push({label:"RHR",data:rhrD,borderColor:"#e74c3c",borderWidth:1.5,borderDash:[4,3],pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"yw"});
    if(show.wt)ds.push({label:"waga (kg)",data:wtD,borderColor:"#e67e22",borderWidth:2,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"yw2"});
    var scalesW={x:{display:false},yw:{position:"left",ticks:{color:txtCol,font:{size:10}},grid:{color:gridCol}}};
    if(hasRight)scalesW.yw2={position:"right",ticks:{color:"#e67e22",font:{size:10}},grid:{drawOnChartArea:false},title:{display:true,text:"kg",color:"#e67e22",font:{size:10}}};
    window._wellChart=new Chart(wc,{type:"line",data:{labels:labels,datasets:ds},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
      plugins:{legend:{display:true,position:"top",labels:{usePointStyle:true,pointStyle:"line",boxWidth:20,padding:10,color:txtCol,font:{size:11}}},
        tooltip:{backgroundColor:isDark?"rgba(30,30,30,0.95)":"rgba(255,255,255,0.95)",titleColor:isDark?"#ddd":"#333",bodyColor:isDark?"#bbb":"#555",borderColor:isDark?"#444":"#ddd",borderWidth:1,padding:10,displayColors:true,callbacks:{title:function(items){if(!items.length)return "";var i=items[0].dataIndex;return SN[i]?SN[i].day:"";}}}},
      scales:scalesW}});
  }
  buildWellness();
  q$("well-checks").querySelectorAll("input").forEach(function(cb){cb.addEventListener("change",buildWellness);});
  '''

s=s.replace(insert_before,wellness_code+"\n  "+insert_before)
open(p,"w").write(s)
print("wellness chart added to JS")
