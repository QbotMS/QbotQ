p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# zamieniam cala funkcje renderTrendy
old_start=s.index("function renderTrendy(){")
old_end=s.index("/* --- ODZYWIANIE ---")
old=s[old_start:old_end]

new='''function renderTrendy(){
  var S=forma.series||[];if(!S.length)return;
  var SN=S.slice(-RNG);var T=S[S.length-1];var S0=SN[0]||{};
  var g=GROUPS[GRP];if(!g)return;
  /* legenda */
  var leg=q$("trendy-legend");
  if(leg)leg.innerHTML=g.label.map(function(l,i){return '<span style="display:inline-flex;align-items:center;gap:4px;margin-right:12px;font-size:13px;color:var(--text-secondary)"><span style="width:10px;height:10px;border-radius:2px;background:'+g.color[i]+'"></span>'+l+'</span>';}).join("");
  /* metryki */
  var met=q$("trendy-metrics");
  if(met){
    var ftpNow=T.ftp_est_w||T.ftp||0,ftpPrev=S0.ftp_est_w||S0.ftp||0,ftpD=ftpNow-ftpPrev;
    met.innerHTML='<div class="card tight" style="background:var(--surface-1);padding:12px"><p class="lbl">Moc progowa</p><div style="font-size:22px;font-weight:500;margin:4px 0">'+qN(ftpNow,0)+' W</div><div style="font-size:13px;color:'+(ftpD>=0?"var(--text-success)":"var(--text-danger)")+'">'+((ftpD>0?"+":"")+qN(ftpD,0))+' W \u00b7 '+RNG+' dni</div></div>'
      +'<div class="card tight" style="background:var(--surface-1);padding:12px"><p class="lbl">Pr\u00f3g spokojny</p><div style="font-size:22px;font-weight:500;margin:4px 0">'+qN(T.ltp_modelq_w,0)+' W</div></div>'
      +'<div class="card tight" style="background:var(--surface-1);padding:12px"><p class="lbl">Zapas W\\'</p><div style="font-size:22px;font-weight:500;margin:4px 0">'+qN(T.wprime_modelq_kj||T.wprime,1)+' kJ</div></div>'
      +'<div class="card tight" style="background:var(--surface-1);padding:12px"><p class="lbl">Moc na kilogram</p><div style="font-size:22px;font-weight:500;margin:4px 0">'+qN(T.w_per_kg||T.wkg,2)+' W/kg</div></div>';
  }
  /* wykres SVG */
  var ch=q$("trendy-chart");if(!ch)return;
  var W=640,H=160,ml=44,mr=10,mt=12,mb=24,pw=W-ml-mr,ph=H-mt-mb;
  var allVals=[];g.series.forEach(function(k){SN.forEach(function(s2){var v=s2[k];if(typeof v==="number"&&isFinite(v))allVals.push(v);});});
  if(!allVals.length){ch.innerHTML='<text x="320" y="80" text-anchor="middle" font-size="14" fill="var(--text-muted)">brak danych</text>';return;}
  var vmin=Math.min.apply(null,allVals),vmax=Math.max.apply(null,allVals);var pad=(vmax-vmin)*0.1||1;vmin-=pad;vmax+=pad;
  var svg='';
  var steps=[0.5,1,2,5,10,20,50];var st=steps.find(function(ss){return(vmax-vmin)/ss<=6;})||steps[steps.length-1];
  for(var gv=Math.ceil(vmin/st)*st;gv<=vmax;gv+=st){var gy=mt+(1-(gv-vmin)/(vmax-vmin))*ph;svg+='<line x1="'+ml+'" y1="'+gy.toFixed(1)+'" x2="'+(W-mr)+'" y2="'+gy.toFixed(1)+'" stroke="var(--border)" stroke-width="1"/><text x="'+(ml-6)+'" y="'+(gy+4).toFixed(1)+'" text-anchor="end" font-size="11" fill="var(--text-muted)">'+qN(gv,st<1?1:0)+'</text>';}
  g.series.forEach(function(k,si){var pts="";SN.forEach(function(s2,i){var v=s2[k];if(typeof v!=="number"||!isFinite(v))return;pts+=((ml+i/(SN.length-1)*pw).toFixed(1))+","+(mt+(1-(v-vmin)/(vmax-vmin))*ph).toFixed(1)+" ";});
    if(pts)svg+='<polyline points="'+pts.trim()+'" fill="none" stroke="'+g.color[si]+'" stroke-width="2.5" stroke-linejoin="round"/>';});
  var labels=SN.filter(function(_,i){return i===0||i===SN.length-1||i===Math.floor(SN.length/2);});
  [0,Math.floor(SN.length/2),SN.length-1].forEach(function(i){if(!SN[i])return;var x=ml+i/(SN.length-1)*pw;svg+='<text x="'+x.toFixed(1)+'" y="'+(H-4)+'" text-anchor="'+(i===0?"start":i===SN.length-1?"end":"middle")+'" font-size="11" fill="var(--text-muted)">'+SN[i].day.slice(5)+'</text>';});
  ch.innerHTML=svg;
  /* statystyki */
  var sg=q$("trendy-stats-grid");
  if(sg&&stats&&stats.totals){var sm=stats.totals;
    sg.innerHTML='<div style="text-align:center"><div class="lbl">jazdy</div><div style="font-size:18px;font-weight:500">'+qN(sm.count,0)+'</div></div>'
      +'<div style="text-align:center"><div class="lbl">dystans</div><div style="font-size:18px;font-weight:500">'+qN((sm.distance_m||0)/1000,0)+' km</div></div>'
      +'<div style="text-align:center"><div class="lbl">czas ruchu</div><div style="font-size:18px;font-weight:500">'+qHM(sm.moving_s)+'</div></div>'
      +'<div style="text-align:center"><div class="lbl">przewy\u017cszenie</div><div style="font-size:18px;font-weight:500">'+qN(sm.elevation_m,0)+' m</div></div>';}
}
'''
s=s[:old_start]+new+s[old_end:]
open(p,"w").write(s)
print("renderTrendy rewritten, len:", len(s))
