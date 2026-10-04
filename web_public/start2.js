/* start2.js — Start v2 na prawdziwych danych v2 */
(function(){
"use strict";
var today=qToday();
var weekAgo=qLocalISO(new Date(Date.now()-7*864e5));
var d30=qLocalISO(new Date(Date.now()-30*864e5));
var app=q$("app"); app.classList.add("loading");

Promise.all([
  qJSON("/api/forma/data"),
  qJSON("/api/rides/ready"),
  qJSON("/api/nutrition/day-summary?day="+today),
  qJSON("/api/calendar?start="+d30+"&end="+today)
]).then(function(all){
  var forma=all[0], rides=all[1], nutri=all[2], cal=all[3];
  var S=forma.series||[]; var T=S.length?S[S.length-1]:{}; var prev=S.length>1?S[S.length-2]:{};
  var dn=["niedziela","poniedziałek","wtorek","środa","czwartek","piątek","sobota"];
  var dd=new Date(today+"T12:00:00");
  q$("h-date").textContent=dn[dd.getDay()]+", "+dd.getDate()+"."+(dd.getMonth()+1)+"."+dd.getFullYear();
  /* gotowość */
  var r=T.readiness_effective!=null?T.readiness_effective:T.readiness_score;
  if(typeof r==="number"){
    var pct=Math.max(0,Math.min(1,(r+1.5)/3));var ang=Math.PI+pct*Math.PI;var x=60+50*Math.cos(ang),y=65+50*Math.sin(ang);
    q$("g-arc").setAttribute("d","M10 65 A50 50 0 0 1 "+x.toFixed(1)+" "+y.toFixed(1));
    q$("g-val").textContent=(r>0?"+":"")+qN(r,2);
    var w=r>0.3?"świeży":r>-0.3?"neutralny":"zmęczony";
    q$("g-word").textContent=w;
    q$("g-sub").textContent="HRV "+qN(T.hrv_night||T.hrv,0)+" · RHR "+qN(T.rhr,0)+" · sen "+(T.sleep_score||qN(T.sleep_h||T.sleep,1)+"h");
    q$("h-pill").textContent=w;q$("h-pill").className="pill "+(r>0.3?"good":r>-0.3?"":"bad");
    q$("h-title").textContent=r>0.3?"Dobry dzień na jazdę":r>-0.3?"Dzień bez skrajności":"Daj sobie odpocząć";
  }
  /* metryki */
  q$("m-ftp-v").innerHTML=qN(T.ftp_est_w||T.ftp,0)+' <small>W</small>';
  q$("m-ftp-d").innerHTML=qDelta(T.ftp_est_w||T.ftp,prev.ftp_est_w||prev.ftp," W");
  q$("m-wkg-v").innerHTML=qN(T.w_per_kg||T.wkg,2)+' <small>W/kg</small>';
  q$("m-wkg-d").innerHTML=qDelta(T.w_per_kg||T.wkg,prev.w_per_kg||prev.wkg,"");
  var tsb=T.tsb_plus!=null?T.tsb_plus:(T.tsb_raw!=null?T.tsb_raw:(T.tsb!=null?T.tsb:null));  /* kanon: z korekta */
  q$("m-tsb-v").innerHTML=tsb!=null?(tsb>0?"+":"")+qN(tsb,1):"—";
  q$("m-tsb-d").innerHTML=qDelta(tsb,prev.tsb_plus!=null?prev.tsb_plus:(prev.tsb_raw!=null?prev.tsb_raw:prev.tsb),"");
  var wt=T.weight_kg;if(!wt)for(var wi=S.length-1;wi>=0;wi--)if(S[wi].weight_kg){wt=S[wi].weight_kg;break;}
  q$("m-kg-v").innerHTML=wt?qN(wt,1)+' <small>kg</small>':"—";
  q$("m-ftp-s").innerHTML='<small>forma '+qN(T.ctl_xss||T.ctl,0)+' · zmęcz. '+qN(T.atl_plus!=null?T.atl_plus:(T.atl_raw||T.atl),0)+'</small>';
  /* tydzien */
  var days=cal.days||{};var entMap={};(cal.entries||[]).forEach(function(e){entMap[e.day]=entMap[e.day]||[];entMap[e.day].push(e);});var rmap={},seen={};
  (rides.rides||[]).forEach(function(ri){if(seen[ri.ride_key])return;seen[ri.ride_key]=1;rmap[ri.date]=rmap[ri.date]||[];rmap[ri.date].push(ri);});
  /* statystyki jazd: tydzien vs sr. tyg. roku, miesiac vs sr. mies. roku, rok vs poprzedni rok */
  (function(){
    var g=q$("stats-grid");if(!g)return;
    var MN=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"];
    var Y=dd.getFullYear();
    var dow=(dd.getDay()+6)%7;var mon=new Date(dd);mon.setDate(dd.getDate()-dow);
    var doy=Math.round((new Date(Y,dd.getMonth(),dd.getDate())-new Date(Y,0,1))/864e5)+1;
    var pyEnd=(Y-1)+"-"+qPad2(dd.getMonth()+1)+"-"+qPad2(Math.min(dd.getDate(),new Date(Y-1,dd.getMonth()+1,0).getDate()));
    var Q=[
      ["week",qLocalISO(mon),today],
      ["month",Y+"-"+qPad2(dd.getMonth()+1)+"-01",today],
      ["ytd",Y+"-01-01",today],
      ["pytd",(Y-1)+"-01-01",pyEnd],
      ["py",(Y-1)+"-01-01",(Y-1)+"-12-31"]
    ];
    function hm(s){s=Math.round(s||0);var h=Math.floor(s/3600),m=Math.round((s%3600)/60);if(m===60){h++;m=0;}return h+":"+qPad2(m);}
    function n0(x){return Math.round(x||0).toLocaleString("pl-PL");}
    function n1(x){return x>=100?n0(x):(Math.round(x*10)/10).toLocaleString("pl-PL");}
    function V(t){t=t||{};return {km:(t.distance_m||0)/1000,cnt:t.count||0,mv:t.moving_s||0,el:t.elevation_m||0};}
    function scale(v,f){return {km:v.km*f,cnt:v.cnt*f,mv:v.mv*f,el:v.el*f};}
    function pct(c,r){if(!r)return '<span class="muted">—</span>';var p=Math.round((c/r-1)*100);var col=p>=0?"var(--good)":"var(--bad)";return '<b style="color:'+col+'">'+(p>0?"+":"")+p+'%</b>';}
    var ST='border:1px solid var(--line);border-radius:12px;background:var(--well);padding:12px 14px;display:flex;flex-direction:column;gap:9px';
    function bar(c,r){
      if(!r)return "";
      var ratio=c/r,w=Math.min(ratio,1.5)/1.5*100,mark=100/1.5;
      var col=ratio>=1?"var(--good)":"var(--accent)";
      return '<div style="position:relative;height:8px;border-radius:4px;background:var(--line)"><div style="position:absolute;left:0;top:0;bottom:0;width:'+w.toFixed(1)+'%;border-radius:4px;background:'+col+'"></div><div style="position:absolute;top:-3px;bottom:-3px;left:'+mark.toFixed(1)+'%;width:2px;background:var(--ink)" title="poziom odniesienia"></div></div>';
    }
    function card(title,sub,cur,ref,refLbl,extra){
      var h='<div style="'+ST+'">';
      h+='<div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px"><b style="font-size:14px">'+title+'</b><span class="muted" style="font-size:11px">'+sub+'</span></div>';
      h+='<div style="display:flex;align-items:baseline;gap:8px"><span style="font-size:30px;font-weight:800;line-height:1;color:var(--accent)">'+n0(cur.km)+'</span><span class="muted" style="font-size:13px;font-weight:600">km</span><span style="margin-left:auto;font-size:14px">'+pct(cur.km,ref&&ref.km)+'</span></div>';
      h+=bar(cur.km,ref&&ref.km);
      h+='<div style="display:grid;grid-template-columns:auto 1fr 1fr auto;gap:3px 10px;font-size:12.5px;align-items:baseline">';
      h+='<span></span><span class="muted" style="font-size:10.5px;text-align:right">teraz</span><span class="muted" style="font-size:10.5px;text-align:right">'+refLbl+'</span><span></span>';
      function row(l,c,r,f,u){h+='<span class="muted">'+l+'</span><b style="text-align:right">'+f(c)+(u?' <span class="muted" style="font-weight:400">'+u+'</span>':'')+'</b><span style="text-align:right;color:var(--ink2)">'+(ref?f(r)+(u?' '+u:''):'—')+'</span><span style="text-align:right;font-size:11.5px">'+pct(c,r)+'</span>';}
      row("km",cur.km,ref&&ref.km,n0,"");
      row("jazdy",cur.cnt,ref&&ref.cnt,function(x){return n1(x);},"");
      row("czas",cur.mv,ref&&ref.mv,hm,"h");
      row("w górę",cur.el,ref&&ref.el,n0,"m");
      h+='</div>';
      if(extra)h+='<div class="muted" style="font-size:11.5px;border-top:1px dashed var(--line);padding-top:6px">'+extra+'</div>';
      return h+'</div>';
    }
    g.innerHTML=["Tydzień","Miesiąc","Rok"].map(function(n){return '<div style="'+ST+';opacity:.5"><b style="font-size:14px">'+n+'</b><span class="muted" style="font-size:12px">ładuję…</span></div>';}).join("");
    Promise.all(Q.map(function(q){return qJSON("/api/stats/rides?start="+q[1]+"&end="+q[2]).catch(function(){return null;});})).then(function(r){
      var wk=V(r[0]&&r[0].totals),mo=V(r[1]&&r[1].totals),ytd=V(r[2]&&r[2].totals);
      var pytd=r[3]?V(r[3].totals):null,py=r[4]?V(r[4].totals):null;
      var weeksY=doy/7,monthsY=doy/(365.25/12);
      var refW=r[2]?scale(ytd,1/weeksY):null,refM=r[2]?scale(ytd,1/monthsY):null;
      var out="";
      out+=card("Tydzień",mon.getDate()+"."+(mon.getMonth()+1)+"–"+dd.getDate()+"."+(dd.getMonth()+1)+" · dzień "+(dow+1)+"/7",wk,refW,"śr. tyg. "+Y,"średnia tygodniowa od 1 stycznia "+Y);
      out+=card("Miesiąc",MN[dd.getMonth()]+" · dzień "+dd.getDate(),mo,refM,"śr. mies. "+Y,"średnia miesięczna od 1 stycznia "+Y);
      out+=card("Rok",Y+" do "+dd.getDate()+"."+(dd.getMonth()+1),ytd,pytd,(Y-1)+" do "+dd.getDate()+"."+(dd.getMonth()+1),py?("cały "+(Y-1)+": <b style=\"color:var(--ink)\">"+n0(py.km)+" km</b> · "+py.cnt+" jazd · "+hm(py.mv)+" h · "+n0(py.el)+" m"):"");
      g.innerHTML=out;
    });
  })();
  /* ostatnia jazda */
  var uniRides=[];seen={};(rides.rides||[]).forEach(function(ri){if(!seen[ri.ride_key]){seen[ri.ride_key]=1;uniRides.push(ri);}});
  var last=uniRides[0];
  if(last){q$("r-name").textContent=last.name||last.ride_key;q$("r-sub").textContent=last.date+" · "+(last.dist_km?qN(last.dist_km,1)+" km · ":"")+(last.xss?"obc. "+last.xss:"");q$("r-link").href="/raport-jazdy.html?ride="+encodeURIComponent(last.ride_key);}
  /* odzywianie */
  if(nutri){q$("n-kcal").textContent=nutri.kcal?nutri.kcal+" kcal":"brak wpisów";q$("n-prot").textContent=nutri.protein_g?"białko "+qN(nutri.protein_g,0)+" g":"";var tgt=2100;if(nutri.kcal>0){q$("n-bar").innerHTML='<div style="display:flex;height:8px;border-radius:4px;overflow:hidden;background:var(--well)"><div style="width:'+Math.min(100,Math.round(nutri.kcal/tgt*100))+'%;background:var(--accent);border-radius:4px"></div></div>';q$("n-foot").textContent=Math.round(nutri.kcal/tgt*100)+"% celu "+tgt+" kcal";}else{q$("n-foot").textContent="Cel: "+tgt+" kcal";}}
  /* ostatnie dni: grid z kolumnami */
  var daysEl=q$("days");daysEl.innerHTML="";
  var ks=Object.keys(days).sort().reverse().slice(1,31);
  ks.forEach(function(ds2,idx){var dd3=days[ds2]||{};var rr2=rmap[ds2]||[];
    var lbl=qDayName(ds2)+" "+ds2.slice(8)+"."+(parseInt(ds2.slice(5,7)));
    var sleepLbl=dd3.sleep_score?"sen "+dd3.sleep_score:"sen "+qN(dd3.sleep,1)+"h";
    var ents=(entMap[ds2]||[]);
    var entHtml=ents.map(function(e){return e.kind==="illness"?'<span style="color:#4eca6a">🤕 '+qEsc(e.title||"choroba")+"</span>":e.kind==="feel"?'<span style="color:#d9a441">😊 '+qEsc(e.title||"")+"</span>":"";}).filter(Boolean).join(" ");
    var actHtml=rr2.length?rr2.map(function(r2){return '🚴🏻 '+(r2.dist_km?qN(r2.dist_km,0)+"km":"")+(r2.duration_s?" "+qHM(r2.duration_s):"");}).join(", "):'<span class="muted">odpoczynek</span>';
    var readLbl=dd3.readiness_label||"—";
    var rdyCls=dd3.readiness>0.3?"good":dd3.readiness>-0.3?"":"bad";
    var div=document.createElement("div");div.className="drow"+(idx>=10?" extra":"");
    if(idx>=10)div.style.display="none";
    div.innerHTML='<span class="dc">'+lbl+'</span><span class="pill small '+rdyCls+'">'+qEsc(readLbl)+'</span><span class="da">'+actHtml+'</span><span class="dw">'+sleepLbl+' · HRV '+qN(dd3.hrv,0)+'</span><span class="de">'+entHtml+'</span>';
    daysEl.appendChild(div);
  });
  if(ks.length>10){var more=document.createElement("div");more.style.cssText="text-align:center;padding:10px 0";more.innerHTML='<a class="link" id="show-more" href="#">pokaż więcej ('+ks.length+' dni) ↓</a>';daysEl.appendChild(more);
    q$("show-more").onclick=function(e){e.preventDefault();daysEl.querySelectorAll(".extra").forEach(function(x){x.style.display="";});more.remove();};}
  /* werdykt */
  var verdictEl=q$("verdict");
  if(typeof r==="number"){
    var tsb2=T.tsb_plus!=null?T.tsb_plus:(T.tsb_raw!=null?T.tsb_raw:(T.tsb||0));
    if(r>0.5&&tsb2>10)verdictEl.textContent="Świeży i wypoczęty — idealny dzień na mocny trening.";
    else if(r>0.3)verdictEl.textContent="Gotowy do jazdy — forma w normie, bez obciążenia.";
    else if(r>-0.3)verdictEl.textContent="Neutralny dzień — lżejsza jazda lub odpoczynek.";
    else verdictEl.textContent="Organizm potrzebuje regeneracji — daj sobie dzień wolny.";
  }
  q$("verdict-src").textContent="ModelQ · gotowość + forma · "+today;
  app.classList.remove("loading");
}).catch(function(e){q$("h-title").textContent="Błąd: "+e.message;app.classList.remove("loading");});
qTip();
})();
