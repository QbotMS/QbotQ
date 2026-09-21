p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()
old_start=s.index("function renderTrendy(){")
old_end=s.index("/* --- ODZYWIANIE ---")

new_fn=r'''function renderTrendy(){
  var S=forma.series||[];if(!S.length)return;
  var SN=S.slice(-RNG);var T=SN[SN.length-1]||{};var S0=SN[0]||{};
  var COLS={ctl:"#1baf7a",atl:"#eb6834",tsb:"#7d6fc4"};
  var LABELS={ctl:"forma (CTL)",atl:"zmeczenie (ATL)",tsb:"swiezosc (TSB)"};
  /* legenda */
  var leg=q$("trendy-legend");
  if(leg)leg.innerHTML='<span><i class="sw" style="background:#1baf7a"></i>forma (CTL)</span><span><i class="sw" style="background:#eb6834"></i>zmeczenie (ATL)</span><span style="border-left:2px dashed #7d6fc4;padding-left:6px">swiezosc (TSB)</span>';
  /* zbierz dane */
  var ctl=[],atl=[],tsb=[],days=[];
  SN.forEach(function(s2){
    ctl.push(s2.ctl_xss!=null?s2.ctl_xss:s2.ctl);
    atl.push(s2.atl_raw!=null?s2.atl_raw:s2.atl);
    tsb.push(s2.tsb_raw!=null?s2.tsb_raw:s2.tsb);
    days.push(s2.day);
  });
  var N=SN.length;if(N<2)return;
  /* skala: wspolna dla CTL/ATL/TSB */
  var allV=[].concat(ctl,atl,tsb).filter(function(v){return typeof v==="number"&&isFinite(v);});
  if(!allV.length)return;
  var vmin=Math.min.apply(null,allV),vmax=Math.max.apply(null,allV);
  var pad=Math.max((vmax-vmin)*0.12,3);vmin=Math.floor(vmin-pad);vmax=Math.ceil(vmax+pad);
  /* wymiary */
  var W=640,H=200,ml=38,mr=8,mt=10,mb=22,pw=W-ml-mr,ph=H-mt-mb;
  function yOf(v){return mt+(1-(v-vmin)/(vmax-vmin))*ph;}
  function xOf(i){return ml+(i/(N-1))*pw;}
  /* siatka */
  var svg='';
  var steps=[1,2,5,10,20,50];var st=steps.find(function(ss){return(vmax-vmin)/ss<=7;})||10;
  for(var gv=Math.ceil(vmin/st)*st;gv<=vmax;gv+=st){
    var gy=yOf(gv);
    svg+='<line x1="'+ml+'" y1="'+gy.toFixed(1)+'" x2="'+(W-mr)+'" y2="'+gy.toFixed(1)+'" stroke="var(--line)" stroke-width="0.5"/>';
    svg+='<text x="'+(ml-4)+'" y="'+(gy+3.5).toFixed(1)+'" text-anchor="end" font-size="11" fill="var(--muted)">'+Math.round(gv)+'</text>';
  }
  /* linia zero TSB */
  if(vmin<0&&vmax>0){var zy=yOf(0);svg+='<line x1="'+ml+'" y1="'+zy.toFixed(1)+'" x2="'+(W-mr)+'" y2="'+zy.toFixed(1)+'" stroke="var(--muted)" stroke-width="1" stroke-dasharray="4 4" opacity="0.4"/>';}
  /* serie */
  function polyline(arr,color,w,dash){var pts="";arr.forEach(function(v,i){if(typeof v!=="number"||!isFinite(v))return;pts+=xOf(i).toFixed(1)+","+yOf(v).toFixed(1)+" ";});if(!pts)return "";return '<polyline points="'+pts.trim()+'" fill="none" stroke="'+color+'" stroke-width="'+w+'" stroke-linejoin="round"'+(dash?' stroke-dasharray="'+dash+'"':'')+'"/>';}
  svg+=polyline(ctl,"#1baf7a",2.5);
  svg+=polyline(atl,"#eb6834",2.5);
  svg+=polyline(tsb,"#7d6fc4",2,"5 3");
  /* etykiety osi X */
  var xlabels=[0,Math.floor(N/4),Math.floor(N/2),Math.floor(3*N/4),N-1];
  xlabels.forEach(function(i){if(!days[i])return;svg+='<text x="'+xOf(i).toFixed(1)+'" y="'+(H-3)+'" text-anchor="'+(i===0?"start":i===N-1?"end":"middle")+'" font-size="10" fill="var(--muted)">'+days[i].slice(5)+'</text>';});
  /* kropki na koncu serii — aktualna wartosc */
  [ctl,atl,tsb].forEach(function(arr,si){var v=arr[N-1];if(typeof v!=="number")return;var cx=xOf(N-1),cy=yOf(v);var col=["#1baf7a","#eb6834","#7d6fc4"][si];svg+='<circle cx="'+cx.toFixed(1)+'" cy="'+cy.toFixed(1)+'" r="4" fill="'+col+'" stroke="var(--bg)" stroke-width="2"/>';svg+='<text x="'+(cx-8).toFixed(1)+'" y="'+(cy-8).toFixed(1)+'" text-anchor="end" font-size="11" font-weight="600" fill="'+col+'">'+Math.round(v)+'</text>';});
  /* pionowe linie chorob */
  var ents=cal.entries||[];
  ents.forEach(function(e){if(e.kind!=="illness")return;var di=-1;for(var j=0;j<N;j++){if(days[j]===e.day){di=j;break;}}if(di<0)return;var ex=xOf(di);svg+='<line x1="'+ex.toFixed(1)+'" y1="'+mt+'" x2="'+ex.toFixed(1)+'" y2="'+(H-mb)+'" stroke="#e34948" stroke-width="1" stroke-dasharray="3 3" opacity="0.5"/><text x="'+(ex+3).toFixed(1)+'" y="'+(H-mb-3)+'" font-size="9" fill="#e34948">'+(e.title||"choroba").slice(0,20)+'</text>';});
  q$("trendy-chart").innerHTML=svg;
  /* komentarz */
  var cEl=q$("trendy-comment");if(cEl){
    var ctlNow=ctl[N-1]||0,ctlPrev=ctl[0]||0,tsbNow=tsb[N-1]||0;
    var parts=[];
    if(ctlNow>ctlPrev+3)parts.push("forma rosnie ("+Math.round(ctlPrev)+" \u2192 "+Math.round(ctlNow)+")");
    else if(ctlNow<ctlPrev-3)parts.push("forma spada ("+Math.round(ctlPrev)+" \u2192 "+Math.round(ctlNow)+")");
    else parts.push("forma stabilna (~"+Math.round(ctlNow)+")");
    if(tsbNow>15)parts.push("duza swiezosc (+"+Math.round(tsbNow)+") \u2014 mozesz jechac mocno");
    else if(tsbNow>0)parts.push("lekka swiezosc (+"+Math.round(tsbNow)+")");
    else if(tsbNow>-10)parts.push("swiezosc blisko zera \u2014 umiarkowany wysilek");
    else parts.push("zmeczony (TSB "+Math.round(tsbNow)+") \u2014 daj sobie odpoczac");
    cEl.textContent=parts.join(" \u00b7 ");
  }
  /* FTP sparkline */
  var ftpArr=SN.map(function(s2){return s2.ftp_est_w||s2.ftp;}).filter(function(v){return typeof v==="number";});
  var ftpNow=ftpArr[ftpArr.length-1]||0,ftpPrev=ftpArr[0]||0,ftpD=ftpNow-ftpPrev;
  var fEl=q$("trendy-ftp-val");if(fEl)fEl.innerHTML=Math.round(ftpNow)+' W <span style="font-size:14px;color:'+(ftpD>=0?"var(--good)":"var(--bad)")+'">'+(ftpD>0?"+":"")+Math.round(ftpD)+' W / '+RNG+' dni</span>';
  var fSvg=q$("trendy-ftp-spark");
  if(fSvg&&ftpArr.length>1){var fmin=Math.min.apply(null,ftpArr)-2,fmax=Math.max.apply(null,ftpArr)+2;var fp="";ftpArr.forEach(function(v,i){fp+=(i/(ftpArr.length-1)*200).toFixed(1)+","+(36-(v-fmin)/(fmax-fmin)*32).toFixed(1)+" ";});fSvg.innerHTML='<polyline points="'+fp.trim()+'" fill="none" stroke="var(--blue)" stroke-width="2"/>';}
  /* statystyki */
  var sg=q$("trendy-stats");
  if(sg){var rideCnt=0,rideKm=0;(rides.rides||[]).forEach(function(r){var seen2={};if(seen2[r.ride_key])return;seen2[r.ride_key]=1;if(r.date>=days[0]&&r.date<=days[N-1]){rideCnt++;rideKm+=(r.dist_km||0);}});
    sg.innerHTML='<div class="mini"><p class="lbl">jazdy</p><div class="v">'+rideCnt+'</div></div><div class="mini"><p class="lbl">dystans</p><div class="v">'+Math.round(rideKm)+' km</div></div><div class="mini"><p class="lbl">FTP</p><div class="v">'+Math.round(ftpNow)+' W</div></div><div class="mini"><p class="lbl">W/kg</p><div class="v">'+qN(T.w_per_kg||T.wkg,2)+'</div></div>';}
}
'''
s=s[:old_start]+new_fn+s[old_end:]
open(p,"w").write(s)
print("renderTrendy v2 done, len:", len(s))
