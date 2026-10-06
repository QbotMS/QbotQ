/* czas lokalny (strefa przegladarki) -- wspolne dla QBot lab */function qTsLocal(s,naiveUtc){if(!s)return"";var t=String(s).trim().replace(" ","T").replace(/\.\d+/,"");if(/[+-]\d\d$/.test(t))t+=":00";t=t.replace(/([+-]\d\d)(\d\d)$/,"$1:$2");if(!/(Z|[+-]\d\d:\d\d)$/i.test(t)){if(!naiveUtc)return t.slice(0,16).replace("T"," ");t+="Z";}var d=new Date(t);if(isNaN(d.getTime()))return String(s).slice(0,16);var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());}function qDateLocal(d){d=d||new Date();var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
/* raport-trasy2-plan.js - Plan dnia (godzina/przerwy bez AI) + pakiet dnia + forma na dzien jazdy (wdrozone 2026-09-23). */
/* raport-mock-plan.js -- MOCKUP E2d: Plan dnia (godzina startu 08-12 + przerwy) przeliczany na zywo
   przez /api/report/plan (bez AI, bez zapisu), pakiet dnia z /api/report/day-pack (AI raz na date). */
(function(){
"use strict";
var rep=document.getElementById("report");
var ST={route:null,date:null,start:"10:00",n:0,m:30,pack:null,apply:null,seq:0,busy:false,gen:false,tmr:null,first:true};
var LSD="qbot_mock_plan_date";
function isoLocal(d){return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");}
function todayIso(){return isoLocal(new Date());}
function tomorrowIso(){var d=new Date();d.setDate(d.getDate()+1);return isoLocal(d);}
function savedDate(){try{var v=localStorage.getItem(LSD);return (v&&v>=todayIso())?v:null;}catch(e){return null;}}
function rememberDate(v){try{localStorage.setItem(LSD,v);}catch(e){}}
function pad(n){return String(n).padStart(2,"0");}
function toMin(h){var p=String(h).split(":");return (+p[0])*60+(+p[1]);}
function toHM(m){return pad(Math.floor(m/60))+":"+pad(m%60);}
function nf(x,d){if(x==null||isNaN(x))return "\u2014";return Number(x).toFixed(d==null?1:d).replace(".",",");}
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function clampStart(t){var m=toMin(t||"10:00");m=Math.round(m/15)*15;return toHM(Math.max(360,Math.min(1200,m)));}
function q(){return "route_id="+encodeURIComponent(ST.route)+"&date="+encodeURIComponent(ST.date);}

/* przechwycenie renderu: trasa/data, komentarze ryzyka z pakietu */
var _orig=window.renderReport;
if(typeof _orig==="function"){
  window.renderReport=function(d,m){
    try{
      if(d&&d.route&&d.start){
        var nr=d.route.id,nd=d.start.date;
        if(nr!==ST.route||nd!==ST.date){ST.route=nr;ST.date=nd;ST.pack=null;ST.apply=null;
          if(!d.plan_mode){ST.start=clampStart(d.start.time);}
          /* pierwsze otwarcie: zapis z przeszlosci -> planujemy od zapamietanej daty albo od jutra */
          if(ST.first&&!d.plan_mode&&!ST.routeFlow){
            /* pierwsze otwarcie: najblizsza data od dzis z pakietem -> zapamietana -> jutro
               (zapis z Historii zostaje tylko, gdy jego data jest >= dzis i nie ma pakietu wczesniej) */
            ST.first=false;var rid=nr,snapD=nd;
            fetch("/api/report/day-packs?route_id="+encodeURIComponent(rid),{credentials:"same-origin",cache:"no-store"})
              .then(function(r){return r.json();}).catch(function(){return {items:[]};})
              .then(function(js){
                var t=todayIso(),dates=((js&&js.items)||[]).map(function(x){return x.date;}).filter(function(x){return x>=t;}).sort();
                var target=dates[0]||(snapD>=t?snapD:null)||savedDate()||tomorrowIso();
                /* zawsze przelicz plan z ustawien panelu - zapis z Historii nie zostaje widokiem (inne przerwy!) */
                ST.date=target;var fd=document.getElementById("f-date");if(fd)fd.value=target;
                loadPack();runPlan(true);
              });
          }else{loadPack();}
        }
        injectPack(d);
      }
    }catch(e){}
    return _orig.apply(this,arguments);
  };
}
function injectPack(d){
  if(!ST.pack||!d||!d.details||!d.details.surface)return;
  var rk=(ST.pack.dzien&&ST.pack.dzien.ryzyka)||[],by={};
  rk.forEach(function(r){by[r.id]=r;});
  (d.details.surface.risk||[]).forEach(function(r,i){var p=by["r"+(i+1)];if(p&&p.komentarz)r.comment=p.komentarz+" ("+[p.pod_kolami,"piach: "+p.piach,"po opadach: "+p.po_opadach].filter(Boolean).join(", ")+")";});
}

/* pakiet */
function loadPack(){
  if(!ST.route||!ST.date)return;
  fetch("/api/report/day-pack?"+q(),{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.json();}).then(function(p){
    ST.pack=(p&&p.meta)?p:null;renderControls();render();
    if(ST.pack)runPlan(false);
  }).catch(function(){ST.pack=null;renderControls();});
}
function genPack(){
  if(ST.gen||!ST.route)return;ST.gen=true;renderControls();render();
  /* zlecenie w tle + odpytywanie (bez limitu 100 s Cloudflare) */
  var t0=Date.now(),qq=q();ST.err=null;
  fetch("/api/report/day-pack?"+qq,{method:"POST",credentials:"same-origin"}).then(function(r){if(!r.ok)throw new Error("HTTP "+r.status);return r.json();}).then(function(){
    (function poll(){
      if(q()!==qq){ST.gen=false;renderControls();render();return;}
      fetch("/api/report/day-pack/status?"+qq,{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.json();}).then(function(s){
        if(s.status==="done"){ST.gen=false;ST.pack=null;loadPack();runPlan(true);loadPackList&&loadPackList();return;}
        if(s.status==="error"){ST.gen=false;ST.err="Nie uda\u0142o si\u0119 wygenerowa\u0107 pakietu: "+(s.blad||"b\u0142\u0105d");renderControls();render();return;}
        ST.genS=Math.round((Date.now()-t0)/1000);renderControls();
        if(Date.now()-t0>6*60*1000){ST.gen=false;ST.err="Generowanie trwa ponad 6 min \u2014 sprawd\u017a p\u00f3\u017aniej (pakiet zapisze si\u0119 sam).";renderControls();return;}
        setTimeout(poll,4000);
      }).catch(function(){setTimeout(poll,6000);});
    })();
  }).catch(function(e){ST.gen=false;ST.err="Nie uda\u0142o si\u0119 zleci\u0107 pakietu: "+e.message;renderControls();render();});
}

/* plan (bez AI) */
function runPlan(doRender){
  if(!ST.route)return;
  /* prosba o odswiezenie widoku nie moze przepasc, gdy w miedzyczasie idzie przeliczenie "tylko regul" */
  ST.wantRender=ST.wantRender||(doRender!==false);
  var my=++ST.seq;ST.busy=true;renderControls();
  var u="/api/report/plan?"+q()+"&time="+encodeURIComponent(ST.start)+"&long_stops="+ST.n+"&long_stop_min="+ST.m;
  fetch(u,{credentials:"same-origin",cache:"no-store"}).then(function(r){if(!r.ok)throw new Error("HTTP "+r.status);return r.json();}).then(function(d){
    if(my!==ST.seq)return;
    ST.busy=false;ST.apply=d.pakiet||null;ST.lastMeta=(d.pakiet&&d.pakiet.meta)||null;ST.lastPlanMs=d.plan_ms;
    syncParams();
    var _wr=ST.wantRender;ST.wantRender=false;
    if(_wr){
      window.__mkReopen=(window.__mk&&window.__mk.active())||null;
      window.renderReport(d,rep);
    }else{renderControls();render();}
  }).catch(function(e){if(my!==ST.seq)return;ST.busy=false;ST.err="B\u0142\u0105d przeliczenia: "+e.message;renderControls();});
}
function schedule(){clearTimeout(ST.tmr);ST.tmr=setTimeout(function(){runPlan(true);},500);}
function syncParams(){
  var t=document.getElementById("f-time"),n=document.getElementById("f-nlong"),m=document.getElementById("f-longmin");
  if(t)t.value=ST.start;if(n)n.value=ST.n;if(m&&[].some.call(m.options,function(o){return +o.value===ST.m;}))m.value=String(ST.m);
}

/* sterowanie w lewym panelu */
function renderControls(){
  var hd=rep&&rep.querySelector("header");if(!hd)return;
  var box=document.getElementById("mk-plan");
  if(!box){box=document.createElement("div");box.id="mk-plan";hd.insertBefore(box,hd.firstChild);}
  var pk=ST.pack,dt=ST.date?ST.date.split("-").reverse().slice(0,2).join("."):"";
  var nOpt=[0,1,2,3,4].map(function(v){return '<option'+(v===ST.n?" selected":"")+'>'+v+'</option>';}).join("");
  var mOpt=[15,20,30,45,60].map(function(v){return '<option'+(v===ST.m?" selected":"")+'>'+v+'</option>';}).join("");
  var status=ST.gen?'<span class="mkp-busy">generuj\u0119 pakiet dnia\u2026 '+(ST.genS?ST.genS+' s':'')+'</span>':
    (pk?'<span>pakiet: '+(pk.meta.wiek_h!=null&&pk.meta.wiek_h>=1?nf(pk.meta.wiek_h,0)+" h temu":"aktualny")+'</span> <button type="button" class="mkp-btn" id="mkp-gen" title="Nowy przebieg AI dla tej daty">od\u015bwie\u017c</button>':
     '<span class="mkp-warn">brak pakietu dnia</span> <button type="button" class="mkp-btn pri" id="mkp-gen">Generuj pakiet dnia</button>');
  var ap=ST.apply||{};
  var metaTxt=ST.busy?'<span class="mkp-busy">przeliczam\u2026</span>':(ap.meta?"meta ~"+ap.meta:"");
  box.innerHTML='<div class="mkp-h"><b>Plan dnia</b><input type="date" id="mkp-d" value="'+esc(ST.date||"")+'"></div>'+
    '<div class="mkp-row"><span class="mkp-l">start</span><input type="range" id="mkp-st" min="360" max="1200" step="15" value="'+toMin(ST.start)+'"><b id="mkp-stv">'+ST.start+'</b></div>'+
    '<div class="mkp-row"><span class="mkp-l">przerwy</span><select id="mkp-n">'+nOpt+'</select><span>\u00d7</span><select id="mkp-m">'+mOpt+'</select><span>min</span></div>'+
    '<div class="mkp-row mkp-s"><span>'+metaTxt+'</span></div>'+
    '<div class="mkp-row mkp-s">'+status+'</div>'+(ST.err?'<div class="mkp-err">'+esc(ST.err)+'</div>':"");
  var sl=document.getElementById("mkp-st"),sv=document.getElementById("mkp-stv");
  sl.oninput=function(){ST.start=toHM(+sl.value);sv.textContent=ST.start;};
  sl.onchange=function(){ST.err=null;schedule();};
  document.getElementById("mkp-n").onchange=function(){ST.n=+this.value;ST.err=null;schedule();};
  document.getElementById("mkp-m").onchange=function(){ST.m=+this.value;ST.err=null;schedule();};
  var g=document.getElementById("mkp-gen");if(g)g.onclick=genPack;
  setTimeout(calButton,0);
  var di=document.getElementById("mkp-d");
  di.onchange=function(){if(!di.value||di.value===ST.date)return;ST.date=di.value;rememberDate(ST.date);ST.pack=null;ST.apply=null;ST.err=null;
    var fd=document.getElementById("f-date");if(fd)fd.value=ST.date;loadPack();schedule();};
}

/* sekcja Plan dnia */
var KL={dobre:"dobre",akceptowalne:"akceptowalne",slabe:"s\u0142abe"};
var TR={atak:"atak",tempo:"tempo",spokojnie:"spokojnie"};
function nearestKey(){var w=(ST.pack&&ST.pack.warianty)||{},sm=toMin(ST.start),best=null;Object.keys(w).forEach(function(k){if(best==null||Math.abs(toMin(k)-sm)<Math.abs(toMin(best)-sm))best=k;});return best;}
function render(){
  var el=document.getElementById("mk-plansec");if(!el)return;
  var pk=ST.pack,ap=ST.apply||{};
  if(!pk){var _ra=document.getElementById("r-alerts"),_na=_ra?_ra.querySelectorAll(".alert").length:0,_si=window.__mkSunInfo&&window.__mkSunInfo();
    var _pre=(_si&&_si.warn.length?'<div class="mkp-rule p1"><span class="mkp-sek">s\u0142o\u0144ce</span>'+esc(_si.warn.join(" \u00b7 "))+' \u2014 we\u017a o\u015bwietlenie</div>':'')+
      '<div class="ms-sub">Alerty pogodowe'+(_na?' ('+_na+')':'')+'</div>'+(_na?'<div class="alerts mkp-alerts">'+_ra.innerHTML+'</div>':'<div class="mkp-ok">Brak alert\u00f3w pogodowych dla tego planu.</div>');
    el.innerHTML=_pre+'<div class="ms-sub">Pakiet dnia</div><div class="mkp-empty">'+(ST.gen?"Generuj\u0119 pakiet dnia\u2026 (~40 s)":"Brak pakietu dnia dla tej daty. Kliknij <b>Generuj pakiet dnia</b> w panelu \u2014 AI przygotuje warianty startu 8:00\u201312:00, regu\u0142y i notatki; potem godzin\u0119 i przerwy zmieniasz bez AI.")+'</div>';return;}
  var key=ap.wariant||nearestKey(),v=(pk.warianty||{})[key]||{},h="";
  var rules=ap.reguly_aktywne||[];
  h+='<div class="ms-sub">Aktywne dla Twojego planu ('+esc(ST.start)+', '+ST.n+' \u00d7 '+ST.m+' min)</div>';
  if(ap.w_zakresie===false)h+='<div class="mkp-rule p1">Start poza zakresem pakietu (8:00\u201312:00) \u2014 u\u017cyty najbli\u017cszy wariant.</div>';
  if(rules.length)rules.forEach(function(r){h+='<div class="mkp-rule p'+(r.priorytet||3)+'"><span class="mkp-sek">'+esc(r.sekcja)+'</span>'+esc(r.zdanie)+(r.korekta_mocy_pct?' <b>(moc '+r.korekta_mocy_pct+'%)</b>':"")+'</div>';});
  else h+='<div class="mkp-ok">Brak ostrze\u017ce\u0144 dla tego planu.</div>';
  /* slonce + alerty pogodowe dla tego planu (przeniesione z osobnej ikony) */
  var si=window.__mkSunInfo&&window.__mkSunInfo();
  if(si&&si.warn.length)h+='<div class="mkp-rule p1"><span class="mkp-sek">s\u0142o\u0144ce</span>'+esc(si.warn.join(" \u00b7 "))+' \u2014 we\u017a o\u015bwietlenie</div>';
  var ra=document.getElementById("r-alerts"),na=ra?ra.querySelectorAll(".alert").length:0;
  h+='<div class="ms-sub">Alerty pogodowe'+(na?' ('+na+')':'')+'</div>'+(ra&&na?'<div class="alerts mkp-alerts">'+ra.innerHTML+'</div>':'<div class="mkp-ok">Brak alert\u00f3w pogodowych dla tego planu.</div>');
  var oc=v.ocena_okna||{};
  h+='<div class="ms-sub">Wariant startu '+esc(key||"\u2014")+(key&&key!==ST.start?' <span class="k">(najbli\u017cszy Twojemu '+esc(ST.start)+')</span>':"")+'</div>';
  h+='<div class="mkp-win"><span class="mkp-kl '+esc(oc.klasa)+'">'+esc(KL[oc.klasa]||oc.klasa||"\u2014")+'</span> '+esc(oc.zdanie||"")+'</div>';
  if(oc.powody&&oc.powody.length)h+='<div class="mkp-tags">'+oc.powody.map(function(t){return '<span>'+esc(String(t).replace(/_/g," "))+'</span>';}).join("")+'</div>';
  h+='<div class="ms-sub">Strategia na etapy</div><div><button type="button" class="mkp-link" id="mkp-tostrat">poka\u017c strategi\u0119 dla tego planu \u2192</button></div>';
  var pp=(pk.dzien&&pk.dzien.pogoda_przebieg)||[];
  if(pp.length){h+='<div class="ms-sub">Przebieg dnia</div><ul class="ms-list">';pp.forEach(function(p){h+='<li><b>'+esc(p.od)+'\u2013'+esc(p.do)+'</b> \u00b7 '+esc((p.zjawiska||[]).join(", ").replace(/_/g," "))+'<div class="k">'+esc(p.opis)+'</div></li>';});h+='</ul>';}
  var wk=pk.dzien&&pk.dzien.wykonalnosc;
  if(wk)h+='<div class="ms-sub">Wykonalno\u015b\u0107</div><div class="mkp-win"><span class="mkp-kl '+(wk.werdykt==="w_normie"?"dobre":wk.werdykt==="na_granicy"?"akceptowalne":"slabe")+'">'+esc(String(wk.werdykt||"").replace(/_/g," "))+'</span> '+esc(wk.komentarz)+'</div>';
  var nt=pk.notatki_alberta||[];
  if(nt.length)h+='<details class="mkp-notes"><summary>Notatki dla Alberta ('+nt.length+')</summary><ul>'+nt.map(function(x){return '<li>'+esc(x)+'</li>';}).join("")+'</ul></details>';
  h+='<div class="mkp-foot">Pakiet: '+esc((pk.meta.model||"AI"))+' \u00b7 '+esc(qTsLocal(pk.meta.created_at,true))+' \u00b7 regu\u0142 '+(pk.reguly||[]).length+(ST.lastPlanMs?' \u00b7 przeliczenie planu '+nf(ST.lastPlanMs/1000,1)+' s':"")+'</div>';
  el.innerHTML=h;
  var ts=document.getElementById("mkp-tostrat");if(ts)ts.onclick=function(){if(window.__mk)window.__mk.toggle("strategia");};
  if(window.__mk&&window.__mk.markRows)window.__mk.markRows();
}
function renderStrategy(mb){
  var pk=ST.pack,ap=ST.apply||{};
  if(!pk){mb.innerHTML='<div class="mkp-empty">Strategia powstaje w <b>pakiecie dnia</b> (AI, warianty startu 8:00\u201312:00). Potem dopasowuje si\u0119 do Twojej godziny i przerw bez ponownego AI.<br><button type="button" class="mkp-go" id="mkp-gen2">'+(ST.gen?'Generuj\u0119\u2026 (~40 s)':'Generuj pakiet dnia')+'</button></div>';
    var g=document.getElementById("mkp-gen2");if(g&&!ST.gen)g.onclick=function(){genPack();renderStrategy(mb);};return;}
  var key=ap.wariant||nearestKey(),v=(pk.warianty||{})[key]||{},h='';
  h+='<div class="ms-sub">Plan: start '+esc(ST.start)+', przerwy '+ST.n+' \u00d7 '+ST.m+' min'+(ap.meta?' \u00b7 meta ~'+esc(ap.meta):'')+'</div>';
  h+='<div class="mkp-win k">Wariant pakietu: '+esc(key||'\u2014')+(key&&key!==ST.start?' (najbli\u017cszy Twojemu startowi)':'')+'</div>';
  (ap.reguly_aktywne||[]).filter(function(r){return r.sekcja==="strategia"||r.korekta_mocy_pct;}).forEach(function(r){h+='<div class="mkp-rule p'+(r.priorytet||3)+'">'+esc(r.zdanie)+(r.korekta_mocy_pct?' <b>(moc '+r.korekta_mocy_pct+'%)</b>':'')+'</div>';});
  h+='<div class="ms-sub">Etapy</div><ul class="ms-list mkp-et">';
  (v.etapy||[]).forEach(function(e){
    var km=e.km||[],mw=e.moc_w||[],mp=e.moc_pct_ftp||[];
    h+='<li><b>km '+nf(km[0],1)+'\u2013'+nf(km[1],1)+'</b> \u00b7 <span class="mkp-tr '+esc(e.tryb)+'">'+esc(TR[e.tryb]||e.tryb)+'</span> \u00b7 <b>'+(mw[0]||"?")+'\u2013'+(mw[1]||"?")+' W</b> <span class="k">('+(mp[0]||"?")+'\u2013'+(mp[1]||"?")+'% FTP)</span> \u00b7 '+(e.jedzenie_g_h||"?")+' g/h \u00b7 '+nf(e.picie_l_h,1)+' l/h'+
      '<div class="k">'+esc((e.charakter||[]).join(", ").replace(/_/g," "))+(e.uwaga?" \u2014 "+esc(e.uwaga):"")+'</div></li>';
  });
  h+='</ul>';
  mb.innerHTML=h;if(window.__mk&&window.__mk.markRows)window.__mk.markRows();
}
window.__mkStrategy=renderStrategy;
var LAST_FORMA=null;
var _orig2=window.renderReport,LAST_ROUTE=null,LAST_TIME=null;
window.renderReport=function(d,m){try{LAST_FORMA=(d&&d.details&&d.details.forma)||null;LAST_ROUTE=(d&&d.route)||null;LAST_TIME=(d&&d.time)||null;}catch(e){}return _orig2.apply(this,arguments);};
var PF_CACHE={};
window.__mkForma=function(mb){
  var pf=LAST_FORMA&&LAST_FORMA.prognoza_dnia;
  var ck=ST.route+"|"+ST.date;
  if((!pf||!pf.warianty)&&PF_CACHE[ck])pf=PF_CACHE[ck];
  if(!pf||!pf.warianty){
    /* zapis z Historii sprzed prognozy -> dociagnij z warstwy planu (bez AI) */
    if(!ST.route||!ST.date)return;
    var ex0=mb.querySelector(".mkp-fp");if(ex0)ex0.remove();
    mb.insertAdjacentHTML("afterbegin",'<div class="mkp-fp"><div class="ms-sub">Forma na dzie\u0144 jazdy</div><div class="k">licz\u0119 prognoz\u0119\u2026</div></div>');
    fetch("/api/report/plan?"+q()+"&time="+encodeURIComponent(ST.start)+"&long_stops="+ST.n+"&long_stop_min="+ST.m,{credentials:"same-origin",cache:"no-store"})
      .then(function(r){return r.json();}).then(function(d){var f=d&&d.details&&d.details.forma&&d.details.forma.prognoza_dnia;
        if(f&&f.warianty){PF_CACHE[ck]=f;window.__mkForma(mb);}else{var e=mb.querySelector(".mkp-fp .k");if(e)e.textContent="brak danych do prognozy";}})
      .catch(function(){var e=mb.querySelector(".mkp-fp .k");if(e)e.textContent="nie uda\u0142o si\u0119 policzy\u0107 prognozy";});
    return;
  }
  var F=LAST_FORMA||{},W=pf.warianty,pr=W.jak_dotad||W.stan,alt=W.odpoczynek||null;
  var dd=String(pf.dzien_jazdy||"").split("-").reverse().slice(0,2).join(".");
  var thr=((F.wykonalnosc_dane||{}).thresholds)||{},YEL=+(thr.tsb_yellow!=null?thr.tsb_yellow:-25),RED=+(thr.tsb_red!=null?thr.tsb_red:-33);
  var xss=(F.vs_route&&F.vs_route.xss!=null)?+F.vs_route.xss:null;
  /* ModelQ v2: CTL/42, ATL/7 (jak fitmodel/form_projection.py) */
  function after(v,x){var c=v.ctl+(x-v.ctl)/42,a=v.atl+(x-v.atl)/7;return {ctl:c,atl:a,tsb:c-a};}
  function rec(v){var c=v.ctl,a=v.atl,n=0;while(c-a<-10&&n<30){c+=(0-c)/42;a+=(0-a)/7;n++;}return n;}
  function zone(t){return t>=10?["swiezy","wypocz\u0119ty"]:t>=-10?["neutral","neutralnie"]:t>=YEL?["zmecz","zm\u0119czenie"]:t>=RED?["mocno","du\u017ce zm\u0119czenie"]:["krytyczne","przeci\u0105\u017cenie"];}
  var po=(xss!=null&&pr)?after(pr,xss):null,poA=(xss!=null&&alt)?after(alt,xss):null;
  var z0=zone(pr.tsb),zp=po?zone(po.tsb):null,nrec=po?rec(po):null;
  function sg(t){return (t>0?"+":"")+nf(t,0);}
  var h='<div class="mkp-fp">';
  h+='<div class="mkf-h"><b>Forma na '+esc(dd)+'</b><span>'+(pf.typ==="historia"?"stan rzeczywisty (data w przesz\u0142o\u015bci)":"prognoza z ostatnich "+pf.okno_dni+" dni")+'</span></div>';
  var s1='Rano '+esc(dd)+' b\u0119dziesz <b>'+z0[1]+'</b> (\u015bwie\u017co\u015b\u0107 '+sg(pr.tsb)+(alt?', przy odpoczynku '+sg(alt.tsb):'')+').';
  if(po)s1+=' Po tej trasie (~'+nf(xss,0)+' XSS) \u015bwie\u017co\u015b\u0107 spadnie do <b>'+sg(po.tsb)+'</b> \u2014 '+zp[1]+(nrec>0?', do normy wr\u00f3cisz po ~'+nrec+' '+(nrec===1?"dniu":"dniach")+' odpoczynku.':'.');
  if(pf.typ==="historia")s1='Rano '+esc(dd)+' by\u0142e\u015b <b>'+z0[1]+'</b> (\u015bwie\u017co\u015b\u0107 '+sg(pr.tsb)+').'+(po?' Po tej trasie \u015bwie\u017co\u015b\u0107 spad\u0142aby do <b>'+sg(po.tsb)+'</b> \u2014 '+zp[1]+'.':'');
  h+='<div class="mkf-verdict">'+s1+'</div>';
  function tile(lbl,v,va,desc){return '<div class="mkf-t"><div class="mkf-l">'+lbl+'</div><div class="mkf-v">'+v+'</div>'+(va!=null?'<div class="mkf-a">przy odpoczynku '+va+'</div>':'')+'<div class="mkf-d">'+desc+'</div></div>';}
  h+='<div class="mkf-tiles">'+
     tile("Kondycja",nf(pr.ctl,0),alt?nf(alt.ctl,0):null,"poziom wytrenowania (CTL), zmienia si\u0119 powoli")+
     tile("Zm\u0119czenie",nf(pr.atl,0),alt?nf(alt.atl,0):null,"skutki ostatnich dni (ATL)")+
     tile("\u015awie\u017co\u015b\u0107",sg(pr.tsb),alt?sg(alt.tsb):null,"kondycja minus zm\u0119czenie (TSB)")+'</div>';
  /* pasek swiezosci ze strefami */
  var LO=-45,HI=40;function X(t){return Math.max(0,Math.min(100,(t-LO)/(HI-LO)*100));}
  var zs=[[LO,RED,"krytyczne"],[RED,YEL,"mocno"],[YEL,-10,"zmecz"],[-10,10,"neutral"],[10,HI,"swiezy"]];
  h+='<div class="mkf-bar">'+zs.map(function(z){return '<span class="z '+z[2]+'" style="left:'+X(z[0])+'%;width:'+(X(z[1])-X(z[0]))+'%"></span>';}).join("");
  h+='<i class="mk rano" style="left:'+X(pr.tsb)+'%" title="rano"></i>';
  if(alt)h+='<i class="mk alt" style="left:'+X(alt.tsb)+'%" title="rano przy odpoczynku"></i>';
  if(po)h+='<i class="mk po" style="left:'+X(po.tsb)+'%" title="po je\u017adzie"></i>';
  h+='</div><div class="mkf-legend"><span><i class="mk rano"></i>rano ('+sg(pr.tsb)+')</span>'+(alt?'<span><i class="mk alt"></i>przy odpoczynku ('+sg(alt.tsb)+')</span>':'')+(po?'<span><i class="mk po"></i>po je\u017adzie ('+sg(po.tsb)+')</span>':'')+'<span class="k">progi: \u017c\u00f3\u0142ty '+nf(YEL,0)+', czerwony '+nf(RED,0)+'</span></div>';
  /* parametry - bez dubla CTL/ATL */
  var par=[["FTP",F.ftp!=null?nf(F.ftp,0)+" W":null],["W/kg",F.w_kg!=null?nf(F.w_kg,2):null],["pr\u00f3g tlenowy",F.ltp!=null?nf(F.ltp,0)+" W":null],["W\u2032",F.w_prime_kj!=null?nf(F.w_prime_kj,1)+" kJ":null],["moc szczytowa",F.peak_w!=null?nf(F.peak_w,0)+" W":null]].filter(function(x){return x[1];});
  h+='<div class="mkf-par">'+par.map(function(x){return '<span><em>'+x[0]+'</em> '+x[1]+'</span>';}).join("")+'<span class="k">bez zmian do dnia jazdy</span></div>';
  h+='</div>';
  /* ukryj stara tabele parametrow (dubel) */
  var t1=mb.querySelector("table");
  if(t1&&/FTP/.test(t1.textContent)){t1.style.display="none";var pv=t1.previousElementSibling;if(pv&&/^\s*Forma/.test(pv.textContent))pv.style.display="none";}
  var ex=mb.querySelector(".mkp-fp");if(ex)ex.remove();
  mb.insertAdjacentHTML("afterbegin",h);
};
window.__mkPlanRender=render;
function decorateLoad(){
  var box=document.querySelector("#r-extra .cx-xss");if(!box)return;
  var F=LAST_FORMA||{},wd=F.wykonalnosc_dane||{},wall=((wd.walls||[])[0])||{};
  var thr=wd.thresholds||{},YEL=+(thr.tsb_yellow!=null?thr.tsb_yellow:-25),RED=+(thr.tsb_red!=null?thr.tsb_red:-33);
  var lvl={green:0,yellow:1,red:2}[wall.color];var why=[];
  if(lvl!=null)why.push("limit dnia: "+(wall.label||wall.color));
  var pf=(F.prognoza_dnia&&F.prognoza_dnia.warianty)?F.prognoza_dnia:(PF_CACHE[ST.route+"|"+ST.date]||null);
  var xss=(F.vs_route&&F.vs_route.xss!=null)?+F.vs_route.xss:null;
  if(pf&&xss!=null){var v=pf.warianty.jak_dotad||pf.warianty.stan;
    if(v){var c=v.ctl+(xss-v.ctl)/42,a=v.atl+(xss-v.atl)/7,t=c-a,tl=t<RED?2:t<YEL?1:0;
      why.push("\u015bwie\u017co\u015b\u0107 po je\u017adzie "+(t>0?"+":"")+Math.round(t));
      lvl=(lvl==null)?tl:Math.max(lvl,tl);}}
  var old=box.querySelector(".mkx-b");if(old)old.remove();
  if(lvl==null)return;
  var L=[["ok","wykonalne"],["mid","trudne"],["bad","ponad si\u0142y"]][lvl];
  var b=document.createElement("span");b.className="mkx-b "+L[0];b.textContent=L[1];b.title=why.join(" \u00b7 ");
  box.appendChild(b);
}
/* Dodaj do kalendarza: wydarzenie na date planu + godzina startu + przypieta trasa */
var CAL_STATE={};
function calTitle(){var n=(LAST_ROUTE&&LAST_ROUTE.name)||"Jazda";return String(n).split(" \u00b7 ")[0].slice(0,200);}
function calNote(){var ap=ST.apply||{},r=LAST_ROUTE||{},F=LAST_FORMA||{};
  var parts=["Plan z Analizy trasy: start "+ST.start,"przerwy "+ST.n+" \u00d7 "+ST.m+" min"];
  if(ap.meta)parts.push("meta ~"+ap.meta);
  if(r.distance_km!=null)parts.push(nf(r.distance_km,1)+" km");
  if(r.ascent_m!=null)parts.push("+"+Math.round(r.ascent_m)+" m");
  if(F.vs_route&&F.vs_route.xss!=null)parts.push("~"+Math.round(F.vs_route.xss)+" XSS");
  return parts.join(" \u00b7 ");}
function calButton(){
  var host=document.getElementById("mk-plan");if(!host||!ST.route||!ST.date)return;
  var row=host.querySelector(".mkx-cal");
  if(!row){row=document.createElement("div");row.className="mkx-cal";host.appendChild(row);}
  var key=ST.route+"|"+ST.date,st=CAL_STATE[key];
  if(st==="busy"){row.innerHTML='<span class="k">dodaj\u0119\u2026</span>';return;}
  if(st&&st.id){row.innerHTML='<a class="mkx-in" href="/kalendarz.html">\u2713 w kalendarzu '+esc(ST.date.split("-").reverse().slice(0,2).join("."))+'</a>';return;}
  row.innerHTML='<button type="button" class="mkx-add">+ Dodaj do kalendarza</button>'+(st&&st.err?'<span class="mkx-err">'+esc(st.err)+'</span>':'');
  row.querySelector(".mkx-add").onclick=addToCalendar;
  if(st===undefined){CAL_STATE[key]=null;
    fetch("/api/calendar?start="+ST.date+"&end="+ST.date,{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.json();}).then(function(js){
      var hit=(js.entry_routes||[]).filter(function(x){return String(x.route_id)===String(ST.route)&&x.day===ST.date;})[0];
      if(hit){CAL_STATE[key]={id:hit.entry_id};calButton();}
    }).catch(function(){});}
}
function addToCalendar(){
  var key=ST.route+"|"+ST.date,day=ST.date,rid=ST.route,title=calTitle();CAL_STATE[key]="busy";calButton();
  var post=function(u,b){return fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify(b)}).then(function(r){if(!r.ok)return r.text().then(function(t){throw new Error(t||("HTTP "+r.status));});return r.json();});};
  /* 2026-10-03: jedna jazda na dzien. Jesli tego dnia jest juz w Kalendarzu jazda BEZ trasy
     (np. "Dluzsza jazda 100 km"), podpinamy trase pod nia zamiast tworzyc drugi wpis (TRENER liczyl dwie). */
  fetch("/api/calendar?start="+day+"&end="+day,{credentials:"same-origin",cache:"no-store"})
    .then(function(r){return r.ok?r.json():{};}).catch(function(){return {};})
    .then(function(js){
      var routed={};(js.entry_routes||[]).forEach(function(x){routed[x.entry_id]=1;});
      var ex=(js.entries||[]).filter(function(e){return e.kind==="event"&&e.event_type==="jazda"&&e.day===day&&(!e.end_day||e.end_day===day)&&!routed[e.id];})[0];
      if(ex)return post("/api/calendar/edit",{id:ex.id,title:title,note:calNote(),at_time:ST.start,event_type:"jazda",
          color:ex.color||"",remind_offsets:ex.remind_offsets||"",end_day:ex.end_day||"",feel:ex.feel,severity:ex.severity||""})
        .then(function(){return ex.id;});
      return post("/api/calendar/entry",{day:day,kind:"event",title:title,note:calNote(),at_time:ST.start,event_type:"jazda"})
        .then(function(res){var id=res&&(res.id||(res.entry&&res.entry.id));if(!id)throw new Error("brak id wpisu");return id;});
    })
    .then(function(id){return post("/api/calendar/route",{entry_id:id,day:day,route_id:rid,route_name:title}).then(function(){return id;});})
    .then(function(id){CAL_STATE[key]={id:id};calButton();})
    .catch(function(e){CAL_STATE[key]={err:"nie dodano: "+String(e.message||e).slice(0,80)};calButton();});
}
/* rozciaganie dolnego panelu (wykres): uchwyt na gornej krawedzi, zapamietana wysokosc */
var LSH="qbot_mock_chart_h2";try{localStorage.removeItem("qbot_mock_chart_h");}catch(e){}
var WINH_MIN=60,WINH_MAX=360;
try{var _h0=+localStorage.getItem(LSH);if(_h0>=WINH_MIN&&_h0<=WINH_MAX)window.__QBOT_CHART_WINH=_h0;}catch(e){}
function addGrip(){
  var cw=document.getElementById("chartwrap");if(!cw||cw.querySelector(".mk-grip"))return;
  var g=document.createElement("div");g.className="mk-grip";g.title="Przeci\u0105gnij, aby zmieni\u0107 wysoko\u015b\u0107 (podw\u00f3jny klik = domy\u015blna)";
  cw.appendChild(g);
  var drag=false,raf=0,want=null;
  function apply(){raf=0;if(want==null)return;window.__QBOT_CHART_WINH=want;if(window.__QBOT_RENDER_CHART)window.__QBOT_RENDER_CHART();
    try{window.dispatchEvent(new Event("resize"));}catch(e){}}
  function onMove(ev){if(!drag)return;var y=(ev.touches?ev.touches[0].clientY:ev.clientY);
    var svg=document.getElementById("chart");var w=(svg&&svg.getBoundingClientRect().width)||1000;
    var bottom=cw.getBoundingClientRect().bottom;
    var maxPx=Math.max(120,Math.min(window.innerHeight*0.5,window.innerHeight-360-80));
    var hpx=Math.max(90,Math.min(maxPx,bottom-y-14));
    var vbH=hpx*1100/w;want=Math.round(Math.max(WINH_MIN,Math.min(WINH_MAX,vbH-55)));
    if(!raf)raf=requestAnimationFrame(apply);ev.preventDefault();}
  function onUp(){if(!drag)return;drag=false;document.body.classList.remove("mk-resizing");
    try{if(want!=null)localStorage.setItem(LSH,String(want));}catch(e){}}
  g.addEventListener("mousedown",function(e){drag=true;document.body.classList.add("mk-resizing");e.preventDefault();});
  g.addEventListener("touchstart",function(e){drag=true;document.body.classList.add("mk-resizing");},{passive:true});
  if(window.__mkGripOff)window.__mkGripOff();
  window.addEventListener("mousemove",onMove);window.addEventListener("touchmove",onMove,{passive:false});
  window.addEventListener("mouseup",onUp);window.addEventListener("touchend",onUp);
  window.__mkGripOff=function(){window.removeEventListener("mousemove",onMove);window.removeEventListener("touchmove",onMove);
    window.removeEventListener("mouseup",onUp);window.removeEventListener("touchend",onUp);};
  g.addEventListener("dblclick",function(){want=null;window.__QBOT_CHART_WINH=null;try{localStorage.removeItem(LSH);}catch(e){}
    if(window.__QBOT_RENDER_CHART)window.__QBOT_RENDER_CHART();try{window.dispatchEvent(new Event("resize"));}catch(e){}});
}
/* ---- naglowek: tylko wybor trasy; zmiana trasy -> plan bez AI; chipy dat z pakietem ---- */
var PACKS=[];
function pickDate(list,snapD){var t=todayIso(),ds=(list||[]).map(function(x){return x.date;}).filter(function(x){return x>=t;}).sort();
  return ds[0]||(snapD&&snapD>=t?snapD:null)||savedDate()||tomorrowIso();}
function renderPackChips(){
  var hb=document.getElementById("f-history");if(!hb)return;
  var t=todayIso(),ds=PACKS.map(function(x){return x.date;}).filter(function(x){return x>=t;}).sort();
  hb.style.display="flex";
  hb.innerHTML='<span class="hist-label">Pakiety dnia</span>'+(ds.length?ds.map(function(d){return '<button type="button" class="hist-chip'+(d===ST.date?" active":"")+'" data-d="'+d+'">'+d.split("-").reverse().slice(0,2).join(".")+'</button>';}).join(""):'<span class="k" style="font-size:12px">brak</span>');
  hb.querySelectorAll(".hist-chip").forEach(function(b){b.onclick=function(){if(b.dataset.d===ST.date)return;ST.date=b.dataset.d;rememberDate(ST.date);ST.pack=null;ST.apply=null;ST.err=null;loadPack();runPlan(true);renderPackChips();};});
}
function loadPackList(cb){
  if(!ST.route){PACKS=[];if(cb)cb([]);return;}
  fetch("/api/report/day-packs?route_id="+encodeURIComponent(ST.route),{credentials:"same-origin",cache:"no-store"})
    .then(function(r){return r.json();}).catch(function(){return {items:[]};})
    .then(function(js){PACKS=(js&&js.items)||[];renderPackChips();if(cb)cb(PACKS);});
}
function startRoute(rid){
  if(!rid)return;ST.routeFlow=true;ST.first=false;ST.route=rid;ST.pack=null;ST.apply=null;ST.err=null;
  try{localStorage.setItem("qbot_report_last_route",rid);}catch(e){}
  var em=document.getElementById("f-empty");if(em)em.style.display="none";
  loadPackList(function(list){ST.date=pickDate(list,null);var fd=document.getElementById("f-date");if(fd)fd.value=ST.date;
    loadPack();runPlan(true);renderPackChips();});
}
/* zmiana trasy przechwycona przed oryginalnym handlerem (ktory wczytywal stary zapis z AI) */
document.addEventListener("change",function(e){if(e.target&&e.target.id==="f-route"){e.stopPropagation();startRoute(e.target.value);}},true);
/* belka: select trasy obok tytulu, reszta parametrow ukryta */
function setupHead(){
  var row=document.querySelector(".qhead-row"),fr=document.querySelector(".fld.route");
  if(row&&fr&&!row.querySelector(".fld.route")){fr.classList.add("mk-route");var tabs=document.getElementById("rtabs");row.insertBefore(fr,tabs||row.children[1]);}
  document.body.classList.add("mk-headlite");
}
setupHead();
/* start: gdy trasa ma zapis, pierwsze otwarcie obsluguje wrapper; gdy nie ma - startujemy sami */
(function waitSel(n){var s=document.getElementById("f-route");
  if(s&&s.value){setTimeout(function(){if(!ST.route)startRoute(s.value);else if(!PACKS.length)loadPackList();},2500);return;}
  if(n<40)setTimeout(function(){waitSel(n+1);},250);})(0);
window.__mkBuilt=function(){renderControls();render();decorateLoad();addGrip();renderPackChips();};
/* O trasie (organizator): odczyt zapisanego opisu, generowanie na zadanie */
var INTRO_ROUTE=null;

/* ---- Zaproszenia (organizator): grupa/adresy, notatka, podglad, wysylka, lista RSVP ---- */
var GROUPS=null;
function guestsRender(){
  var el=document.getElementById("mk-guestsec");if(!el)return;
  if(!ST.route||!ST.date){el.innerHTML='<div class="k">Wybierz tras\u0119 i dat\u0119 w Planie dnia.</div>';return;}
  var dd=ST.date.split("-").reverse().slice(0,2).join(".");
  var h='<div class="mkg-plan">Zapraszasz na <b>'+esc(dd)+'</b>, start <b>'+esc(ST.start)+'</b>'+(ST.n?', przerwy '+ST.n+' \u00d7 '+ST.m+' min':'')+
    ' <span class="k">\u2014 go\u015bcie zobacz\u0105 ten plan (godzin\u0119 i przerwy ustawiasz w Planie dnia)</span></div>';
  h+='<div class="ms-sub">Do kogo</div><div class="mkg-row"><select id="mkg-grp"><option value="">\u2014 grupa mailowa \u2014</option></select></div>'+
     '<textarea id="mkg-em" class="mkg-ta" rows="2" placeholder="albo adresy e-mail (przecinek / nowa linia)"></textarea>'+
     '<div class="ms-sub">Od Ciebie (opcjonalnie)</div><textarea id="mkg-note" class="mkg-ta" rows="3" placeholder="np. Zbi\u00f3rka 9:00 pod ko\u015bcio\u0142em, tempo spokojne, obiad w M\u0142ynie."></textarea>'+
     '<div class="mkg-row"><button type="button" class="mkp-btn" id="mkg-prev">Podgl\u0105d maila</button><button type="button" class="mkp-go" id="mkg-send">Wy\u015blij zaproszenia</button></div>'+
     '<div id="mkg-msg" class="k"></div><div class="ms-sub">Zaproszeni na '+esc(dd)+'</div><div id="mkg-list" class="k">wczytuj\u0119\u2026</div>';
  el.innerHTML=h;
  var sel=document.getElementById("mkg-grp");
  (GROUPS?Promise.resolve(GROUPS):fetch("/api/mail-groups",{credentials:"same-origin"}).then(function(r){return r.json();}).then(function(j){GROUPS=(j&&j.items)||[];return GROUPS;}).catch(function(){return [];}))
    .then(function(gs){gs.forEach(function(g){var o=document.createElement("option");o.value=g.id;o.textContent=g.name+" ("+((g.members||[]).length)+")";sel.appendChild(o);});});
  function emails(){return (document.getElementById("mkg-em").value||"").split(/[\s,;]+/).map(function(x){return x.trim();}).filter(function(x){return x.indexOf("@")>0;});}
  function qs(){return "route_id="+encodeURIComponent(ST.route)+"&date="+ST.date+"&time="+encodeURIComponent(ST.start)+"&long_stops="+ST.n+"&long_stop_min="+ST.m;}
  document.getElementById("mkg-prev").onclick=function(){window.open("/api/invites/preview?"+qs()+"&note="+encodeURIComponent(document.getElementById("mkg-note").value||""),"_blank");};
  document.getElementById("mkg-send").onclick=function(){
    var em=emails(),gid=sel.value,gname=gid?sel.options[sel.selectedIndex].textContent:"";
    if(!em.length&&!gid){document.getElementById("mkg-msg").textContent="Wybierz grup\u0119 albo wpisz adresy.";return;}
    if(!confirm("Wys\u0142a\u0107 zaproszenia na "+dd+" (start "+ST.start+")?\n"+(gid?"Grupa: "+gname+"\n":"")+(em.length?"Adresy: "+em.join(", "):"")))return;
    var b=this;b.disabled=true;document.getElementById("mkg-msg").textContent="wysy\u0142am\u2026";
    fetch("/api/invites/send",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({route_id:ST.route,date:ST.date,time:ST.start,long_stops:ST.n,long_stop_min:ST.m,emails:em,group_id:gid?+gid:null,note:document.getElementById("mkg-note").value||""})})
      .then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.detail||("HTTP "+r.status));return j;});})
      .then(function(j){b.disabled=false;var bad=(j.items||[]).filter(function(x){return !x.ok;});
        document.getElementById("mkg-msg").innerHTML='\u2714 wys\u0142ano: <b>'+j.wyslano+'</b>'+(bad.length?' \u00b7 <span class="mkx-err">b\u0142\u0119dy: '+bad.map(function(x){return esc(x.email)+" ("+esc(x.blad||"")+")";}).join(", ")+'</span>':'');
        document.getElementById("mkg-em").value="";loadList();})
      .catch(function(e){b.disabled=false;document.getElementById("mkg-msg").innerHTML='<span class="mkx-err">nie wys\u0142ano: '+esc(e.message)+'</span>';});
  };
  loadList();
}
function loadList(){
  var el=document.getElementById("mkg-list");if(!el)return;
  fetch("/api/invites?route_id="+encodeURIComponent(ST.route)+"&date="+ST.date,{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.json();}).then(function(j){
    var it=(j&&j.items)||[];if(!it.length){el.textContent="nikt jeszcze nie zaproszony";return;}
    var R={tak:"\u2714 jedzie",nie:"\u2716 nie jedzie",czeka:"\u2026 czeka"};
    var t=it.filter(function(x){return x.status==="tak"&&!x.revoked_at;}).length;
    var h='<div class="mkg-sum">jedzie: <b>'+t+'</b> z '+it.filter(function(x){return !x.revoked_at;}).length+'</div><table class="mkg-t">';
    it.forEach(function(x){var off=!!x.revoked_at,other=(x.start_time!==ST.start||x.long_stops!==ST.n||(ST.n&&x.long_stop_min!==ST.m));
      h+='<tr class="'+(off?"off":"")+'"><td>'+esc(x.email)+'</td><td class="st '+esc(x.status)+'">'+(off?"link wy\u0142\u0105czony":R[x.status]||x.status)+'</td>'+
        '<td class="k">'+(x.sent_at?"wys\u0142ano "+esc(String(x.sent_at).slice(5,16).replace("T"," ")):"nie wys\u0142ano")+(x.open_count?" \u00b7 otwar\u0107 "+x.open_count:"")+(other&&!off?' \u00b7 <span style="color:var(--warn)">inny plan ('+esc(x.start_time)+')</span>':'')+'</td>'+
        '<td>'+(off?"":'<button type="button" class="mkp-link" data-cp="'+esc(x.token)+'">link</button> <button type="button" class="mkp-link" data-rv="'+esc(x.token)+'">wy\u0142\u0105cz</button>')+'</td></tr>';});
    el.innerHTML=h+'</table><div class="k" style="margin-top:6px">Zmiana godziny lub przerw po wys\u0142aniu: wy\u015blij ponownie te same adresy \u2014 link zostaje ten sam, plan si\u0119 zaktualizuje.</div>';
    el.querySelectorAll("[data-cp]").forEach(function(b){b.onclick=function(){var u=location.origin+"/g/"+b.dataset.cp;try{navigator.clipboard.writeText(u);b.textContent="skopiowano";}catch(e){prompt("Link:",u);}};});
    el.querySelectorAll("[data-rv]").forEach(function(b){b.onclick=function(){if(!confirm("Wy\u0142\u0105czy\u0107 link tej osoby?"))return;
      fetch("/api/invites/revoke?token="+encodeURIComponent(b.dataset.rv),{method:"POST",credentials:"same-origin"}).then(loadList);};});
  }).catch(function(){el.textContent="nie uda\u0142o si\u0119 wczyta\u0107 listy";});
}
window.__mkGuestsRender=guestsRender;

/* ---- Sprzet: rower (po opisaniu w Garazu) + dobor ubioru dla BIEZACEGO planu ---- */
var GEAR_P=null,GEAR_KEY=null,GEAR_BUSY=false;
function gearParamsDiff(p){var pl=(p&&p.plan)||{};return !(pl.start===ST.start&&+pl.long_stops===ST.n&&(!ST.n||+pl.long_stop_min===ST.m));}
function gearRender(mb){
  mb=mb||document.querySelector("#mk-pane .multi-body");if(!mb)return;
  var key=ST.route+"|"+ST.date;
  var h='<div class="ms-sub">Rower</div><div class="k">Wyb\u00f3r Grizl / Monster Gravel pojawi si\u0119 tutaj po opisaniu obu rower\u00f3w w Gara\u017cu.</div>'+
        '<div class="ms-sub">Ubi\u00f3r na ten plan</div><div id="mkw-body"></div>';
  mb.innerHTML=h;
  if(GEAR_KEY!==key){GEAR_KEY=key;GEAR_P=undefined;
    fetch("/api/report/outfit?route_id="+encodeURIComponent(ST.route)+"&date="+ST.date,{credentials:"same-origin",cache:"no-store"})
      .then(function(r){return r.json();}).then(function(j){if(GEAR_KEY!==key)return;GEAR_P=(j&&j.zestawy)?j:null;gearBody();}).catch(function(){GEAR_P=null;gearBody();});}
  gearBody();
}
function gearBody(){
  var el=document.getElementById("mkw-body");if(!el)return;
  var dd=ST.date?ST.date.split("-").reverse().slice(0,2).join("."):"";
  var btn='<button type="button" class="mkp-go" id="mkw-go">'+(GEAR_BUSY?"Dobieram\u2026 (~15 s)":GEAR_P?"Dobierz ponownie":"Dobierz ubi\u00f3r dla tego planu")+'</button>';
  if(GEAR_P===undefined){el.innerHTML='<div class="k">wczytuj\u0119\u2026</div>';return;}
  if(!GEAR_P){el.innerHTML='<div class="mkp-empty">AI u\u0142o\u017cy 2 zestawy z Twojego gara\u017cu dla planu: '+esc(dd)+', start '+esc(ST.start)+(ST.n?', przerwy '+ST.n+' \u00d7 '+ST.m+' min':'')+
    '. Ka\u017cda rzecz z uzasadnieniem z pogody w czasie jazdy.<br>'+btn+'</div>';wireGo();return;}
  var p=GEAR_P,h='';
  if(gearParamsDiff(p))h+='<div class="mkp-rule p2">Propozycja dla innego planu (start '+esc((p.plan||{}).start)+((p.plan||{}).long_stops?', '+p.plan.long_stops+' \u00d7 '+p.plan.long_stop_min+' min':'')+') \u2014 dobierz ponownie dla bie\u017c\u0105cego.</div>';
  if(p.warunki_krotko)h+='<p class="mkw-w">'+esc(p.warunki_krotko)+'</p>';if(p.kontrola_uwagi&&p.kontrola_uwagi.length)h+='<p class="mkw-w" style="color:var(--warn)">\u26a0 Kontrola zestawu: '+p.kontrola_uwagi.map(esc).join(' \u00b7 ')+'</p>';if(p.z_historii)h+='<p class="mkw-w">\u21bb '+esc(p.z_historii)+'</p>';
  (p.zestawy||[]).forEach(function(z,i){
    var tp=z.tempo==="szybsza"?"szybsza jazda":(z.tempo==="spokojniejsza"?"spokojniejsza jazda":"");
    h+='<div class="mkw-set"><div class="mkw-t">'+(i===0?"A":"B")+' \u00b7 '+(tp?esc(tp)+' \u00b7 ':'')+esc(z.nazwa)+'</div>'+(z.kiedy?'<div class="k">'+esc(z.kiedy)+'</div>':'')+
      (z.po_co?'<div class="k" style="margin-top:4px"><b>Po co:</b> '+esc(z.po_co)+'</div>':'')+'<ul class="mkw-l">';
    (z.rzeczy||[]).forEach(function(it){h+='<li><b>'+esc(it.nazwa)+'</b> <span class="k">'+esc(it.kategoria)+(it.kolor?' \u00b7 '+esc(String(it.kolor).toLowerCase()):'')+'</span><div class="k">'+esc(it.dlaczego)+'</div>'+
      ((it.zamienniki&&it.zamienniki.length)?'<div class="k">zamiennie: '+it.zamienniki.map(function(a){return esc(a.nazwa)+(a.kolor?' ('+esc(String(a.kolor).toLowerCase())+')':'');}).join(", ")+'</div>':'')+'</li>';});
    h+='</ul>';
    if(z.do_kieszeni&&z.do_kieszeni.length)h+='<div class="mkw-sub">Do kieszeni</div><ul class="mkw-l">'+z.do_kieszeni.map(function(it){return '<li><b>'+esc(it.nazwa)+'</b><div class="k">'+esc(it.dlaczego)+'</div></li>';}).join("")+'</ul>';
    if(z.kolory)h+='<div class="mkw-z">\ud83c\udfa8 '+esc(z.kolory)+'</div>';
    if(z.zdejmij)h+='<div class="mkw-z">\u23f1 '+esc(z.zdejmij)+'</div>';if(z.slaby_punkt)h+='<div class="mkw-z">\u26a0 '+esc(z.slaby_punkt)+'</div>';
    h+='</div>';});
  h+='<div class="mkp-foot">'+esc(qTsLocal(p.created_at,true))+' \u00b7 z '+(p.kandydatow||"?")+' kandydat\u00f3w z gara\u017cu \u00b7 '+btn+'</div>';
  el.innerHTML=h;wireGo();
}
function wireGo(){var b=document.getElementById("mkw-go");if(!b)return;b.disabled=GEAR_BUSY;b.onclick=function(){
  if(GEAR_BUSY)return;GEAR_BUSY=true;gearBody();var key=GEAR_KEY;
  fetch("/api/report/outfit",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({route_id:ST.route,date:ST.date,time:ST.start,long_stops:ST.n,long_stop_min:ST.m})})
    .then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.detail||("HTTP "+r.status));return j;});})
    .then(function(j){GEAR_BUSY=false;if(GEAR_KEY===key)GEAR_P=j;gearBody();})
    .catch(function(e){GEAR_BUSY=false;gearBody();var el=document.getElementById("mkw-body");if(el)el.insertAdjacentHTML("afterbegin",'<div class="mkx-err">'+esc(e.message)+'</div>');});};}
window.__mkGearRender=gearRender;
window.__mkIntroLoad=function(){var rid=ST.route;if(!rid)return Promise.resolve();
  return fetch('/api/route-intro?route_id='+encodeURIComponent(rid),{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.json();})
    .then(function(j){INTRO_ROUTE=rid;window.__mkIntroData=(j&&j.tytul)?j:null;}).catch(function(){window.__mkIntroData=null;});};
window.__mkIntroGen=function(){var rid=ST.route;
  return fetch('/api/route-intro?route_id='+encodeURIComponent(rid),{method:'POST',credentials:'same-origin'}).then(function(r){
    if(!r.ok)return r.json().catch(function(){return {};}).then(function(j){throw new Error(j.detail||('HTTP '+r.status));});return r.json();})
    .then(function(j){INTRO_ROUTE=rid;window.__mkIntroData=j;});};
setInterval(function(){if(ST.route&&INTRO_ROUTE&&INTRO_ROUTE!==ST.route){INTRO_ROUTE=null;window.__mkIntroData=undefined;}},800);
/* mail z planu: zapisz biezacy plan jako raport (bez AI, tresci z pakietu) i zwroc snapshot_id */
window.__QBOT_ENSURE_SNAPSHOT=function(){
  if(!ST.route||!ST.date)return Promise.resolve(null);
  var u="/api/report/plan/save?"+q()+"&time="+encodeURIComponent(ST.start)+"&long_stops="+ST.n+"&long_stop_min="+ST.m;
  return fetch(u,{method:"POST",credentials:"same-origin"}).then(function(r){return r.ok?r.json():null;}).then(function(j){return (j&&j.snapshot_id)||null;});
};
})();
