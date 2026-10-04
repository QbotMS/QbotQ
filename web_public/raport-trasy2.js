/* czas lokalny (strefa przegladarki) -- wspolne dla QBot lab */function qTsLocal(s,naiveUtc){if(!s)return"";var t=String(s).trim().replace(" ","T").replace(/\.\d+/,"");if(/[+-]\d\d$/.test(t))t+=":00";t=t.replace(/([+-]\d\d)(\d\d)$/,"$1:$2");if(!/(Z|[+-]\d\d:\d\d)$/i.test(t)){if(!naiveUtc)return t.slice(0,16).replace("T"," ");t+="Z";}var d=new Date(t);if(isNaN(d.getTime()))return String(s).slice(0,16);var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());}function qDateLocal(d){d=d||new Date();var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
/* raport-trasy2.js - Analiza trasy v2: szczegoly w lewym panelu mapy (wdrozone 2026-09-23 z mockupu). */
/* raport-mock.js v2 -- MOCKUP: Szczegoly trasy w lewym panelu mapy (wzor: Planer wyprawy).
   - zakladki pionowe doklejone do prawej krawedzi lewego panelu
   - otwarta sekcja: panel na ~pol okna, wykres schowany, trasa przesunieta w prawo
   - klik w wiersz z "km X" / "km X-Y" (ryzyko, podjazd, zaopatrzenie, atrakcja) -> zaznaczenie na mapie
   Nie zmienia raport-render.js. */
(function(){
"use strict";
var rep=document.getElementById("report");
var active=null, GEO=null, HL=null, rid=null;
var SV=function(p){return '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+p+'</svg>';};
var ICONS={
 goscie:["#9ad07a",SV('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>')],
 otrasie:["#7fc8d8",SV('<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>')],
 plan:["#e8742a",SV('<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>')],
 alerty:["#ff8f5a",SV('<path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>')],
 legenda:["#c9b98f",SV('<path d="M3 5h.01"/><path d="M3 12h.01"/><path d="M3 19h.01"/><path d="M8 5h13"/><path d="M8 12h13"/><path d="M8 19h13"/>')],
 nawierzchnia:["#e0a44a",SV('<path d="M5 21 9 3"/><path d="M19 21 15 3"/><path d="M12 5v2"/><path d="M12 11v2"/><path d="M12 17v2"/>')],
 przewyzszenia:["#8cc265",SV('<path d="m8 3 4 8 5-5 5 15H2L8 3z"/>')],
 pogoda:["#6fb3ec",SV('<path d="M12 2v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="M20 12h2"/><path d="m19.07 4.93-1.41 1.41"/><path d="M15.95 12.65a4 4 0 0 0-5.93-4.13"/><path d="M13 22H7a5 5 0 1 1 4.9-6H13a3 3 0 0 1 0 6Z"/>')],
 forma:["#f07878",SV('<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>')],
 strategia:["#a99bf0",SV('<circle cx="12" cy="12" r="10"/><path d="m16.24 7.76-2.12 6.36-6.36 2.12 2.12-6.36z"/>')],
 zaopatrzenie:["#4cc9b0",SV('<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/>')],
 atrakcje:["#f08ac0",SV('<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>')],
 sprzet:["#f0975a",SV('<circle cx="18.5" cy="17.5" r="3.5"/><circle cx="5.5" cy="17.5" r="3.5"/><circle cx="15" cy="5" r="1"/><path d="M12 17.5V14l-3-3 4-3 2 3h2"/>')],
 udostepnij:["#9fb0c8",SV('<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.59 13.51 6.83 3.98"/><path d="m15.41 6.51-6.82 3.98"/>')]
};

/* przechwyc dane raportu (id trasy) */
var _orig=window.renderReport;
if(typeof _orig==="function"){
  window.renderReport=function(d,m){try{window.__mkLastD=d;rid=d&&d.route&&d.route.id;GEO=null;
    if(d&&d.route&&d.route.__geometry){var co=d.route.__geometry,cum=[0];for(var i=1;i<co.length;i++)cum[i]=cum[i-1]+hav(co[i-1],co[i]);GEO={co:co,cum:cum,kmT:cum[cum.length-1]};}
    else if(rid)loadGeo(rid);}catch(e){}return _orig.apply(this,arguments);};
}
function hav(a,b){var R=6371,r=Math.PI/180,dLa=(b[0]-a[0])*r,dLo=(b[1]-a[1])*r,x=Math.pow(Math.sin(dLa/2),2)+Math.cos(a[0]*r)*Math.cos(b[0]*r)*Math.pow(Math.sin(dLo/2),2);return 2*R*Math.asin(Math.sqrt(x));}
function loadGeo(id){
  fetch("/api/routes/"+encodeURIComponent(id)+"/geometry",{credentials:"same-origin"}).then(function(r){return r.ok?r.json():null;}).then(function(d){
    if(!d||!d.coordinates||!d.coordinates.length)return;
    var co=d.coordinates,cum=[0];for(var i=1;i<co.length;i++)cum[i]=cum[i-1]+hav(co[i-1],co[i]);
    GEO={co:co,cum:cum,kmT:cum[cum.length-1]};
  }).catch(function(){});
}
function llAt(km){var c=GEO.co,u=GEO.cum;km=Math.max(0,Math.min(GEO.kmT,km));for(var i=1;i<u.length;i++){if(u[i]>=km){var t=(km-u[i-1])/((u[i]-u[i-1])||1);return [c[i-1][0]+(c[i][0]-c[i-1][0])*t,c[i-1][1]+(c[i][1]-c[i-1][1])*t];}}return c[c.length-1];}
function ptsBetween(a,b){var out=[llAt(a)];for(var i=0;i<GEO.co.length;i++){if(GEO.cum[i]>a&&GEO.cum[i]<b)out.push(GEO.co[i]);}out.push(llAt(b));return out;}

/* wolna czesc mapy = na prawo od panelu */
function padOpts(){
  if(window.matchMedia&&window.matchMedia("(max-width:820px)").matches){var _tb=document.getElementById("r-topbar"),_hd=rep&&rep.querySelector("header");var _t=_tb?_tb.getBoundingClientRect().bottom:90;var _b=_hd?Math.max(0,window.innerHeight-_hd.getBoundingClientRect().top):220;return {paddingTopLeft:[20,_t+15],paddingBottomRight:[20,_b+15],maxZoom:15};} /* MOBILE v1 analiza trasy */
  var hd=rep&&rep.querySelector("header"),rail=document.getElementById("mk-rail");
  var left=0;if(hd){left=hd.getBoundingClientRect().right;}if(rail){left=Math.max(left,rail.getBoundingClientRect().right);}
  var nav=0;try{nav=parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--qnav-rail"))||56;}catch(e){nav=56;}
  var chartH=0;var cw=rep&&rep.querySelector(".chartwrap");if(cw&&!document.body.classList.contains("mk-open")){chartH=Math.max(0,window.innerHeight-cw.getBoundingClientRect().top);}
  return {paddingTopLeft:[Math.max(40,left-nav+30),90],paddingBottomRight:[40,chartH+30],maxZoom:15};
}
function fitRoute(){
  var m=window._qmap;if(!m||!GEO)return;
  try{m.fitBounds(L.latLngBounds(GEO.co),padOpts());}catch(e){}
}
function clearHL(){if(HL&&window._qmap){try{window._qmap.removeLayer(HL);}catch(e){}}HL=null;document.querySelectorAll(".mk-sel").forEach(function(x){x.classList.remove("mk-sel");});}
var HLC="#ec4899";
function ctxBounds(a,b){
  var len=(b!=null&&b>a)?(b-a):0,pad=Math.max(4,len*1.5);
  var lo=Math.max(0,a-pad),hi=Math.min(GEO.kmT,(b!=null?b:a)+pad);
  return L.latLngBounds(ptsBetween(lo,hi));
}
function showKm(a,b){
  var m=window._qmap;if(!m||!GEO||typeof L==="undefined")return false;
  clearHL();HL=L.layerGroup().addTo(m);
  if(b!=null&&b>a){
    var pts=ptsBetween(a,b);
    L.polyline(pts,{color:HLC,weight:18,opacity:.28,lineCap:"round",lineJoin:"round",interactive:false}).addTo(HL);
    L.polyline(pts,{color:"#ffffff",weight:6,opacity:1,lineCap:"butt",interactive:false}).addTo(HL);
    L.polyline(pts,{color:HLC,weight:6,opacity:1,dashArray:"10 8",lineCap:"butt",interactive:false}).addTo(HL);
    [pts[0],pts[pts.length-1]].forEach(function(p,i){L.circleMarker(p,{radius:7,color:"#fff",weight:2.5,fillColor:i?"#1c2024":HLC,fillOpacity:1,interactive:false}).addTo(HL);});
  }else{
    var p=llAt(a);
    L.circleMarker(p,{radius:18,color:HLC,weight:2,dashArray:"4 4",fillColor:HLC,fillOpacity:.18,interactive:false}).addTo(HL);
    L.circleMarker(p,{radius:7,color:"#fff",weight:2.5,fillColor:HLC,fillOpacity:1,interactive:false}).addTo(HL);
  }
  try{m.fitBounds(ctxBounds(a,b),Object.assign(padOpts(),{maxZoom:13}));}catch(e){}
  return true;
}
function num(s){return parseFloat(String(s).replace(",","."));}
var KMRE=/km\s*(\d+(?:[.,]\d+)?)(?:\s*[\u2013\u2014-]\s*(\d+(?:[.,]\d+)?))?/;

/* zakladki (rail) */
function placeRail(){
  var hd=rep&&rep.querySelector("header"),rail=document.getElementById("mk-rail");
  if(!hd||!rail)return;
  var r=hd.getBoundingClientRect();
  if(!document.body.classList.contains("rtab-mapa")||r.width<10){rail.style.display="none";return;}
  rail.style.display="flex";rail.style.left=(r.right-50)+"px";rail.style.top=(r.top+10)+"px";
}
function build(){
  if(!rep)return;
  var hd=rep.querySelector("header"),nav=rep.querySelector("#multi-nav"),pane=rep.querySelector("#multi-pane");
  if(!hd||!nav||!pane||document.getElementById("mk-pane"))return;
  var tb=document.querySelector('.rtab[data-rtab="szczegoly"]');if(tb)tb.style.display="none";
  var mt=document.querySelector('.rtab[data-rtab="mapa"]');if(mt)mt.textContent="Mapa";
  if(mt&&!mt.classList.contains("active"))mt.click();
  var old=document.getElementById("mk-rail");if(old)old.remove();
  var rail=document.createElement("div");rail.id="mk-rail";
  /* organizator: alerty w Planie dnia; gosc: osobna ikona Alerty. Legenda zawsze na koncu */
  var specs=[{id:"otrasie",label:"O trasie"}].concat(window.__QBOT_GUEST?[{id:"alerty",label:"Alerty"}]:[{id:"plan",label:"Plan dnia"},{id:"goscie",label:"Zaproszenia"}]);
  var srcs=specs.concat([].slice.call(nav.querySelectorAll(".multi-item")).map(function(x){return {id:x.dataset.id,label:x.textContent};})).concat([{id:"legenda",label:"Legenda"}]);
  srcs.forEach(function(src){src.dataset={id:src.id};src.textContent=src.label;
    var b=document.createElement("button");b.type="button";b.className="mk-tab";
    b.dataset.id=src.dataset.id;b.title=src.textContent;b.setAttribute("aria-label",src.textContent);
    var IC=ICONS[src.dataset.id]||["#9fb0c8",SV('<circle cx="12" cy="12" r="3"/>')];b.style.setProperty("--tc",IC[0]);
    b.innerHTML='<span class="ic">'+IC[1]+'</span><span class="lb">'+src.textContent+'</span>';
    b.onclick=function(){toggle(src.dataset.id);};
    rail.appendChild(b);
  });
  document.body.appendChild(rail);
  var pw=document.createElement("div");pw.id="mk-pane";
  pw.innerHTML='<div class="mk-top"><span class="mk-ttl" id="mk-ttl"></span><button type="button" class="mk-x" title="Zamknij (Esc)">×</button></div><div class="mk-hint">Kliknij wiersz z kilometrem, aby pokazać go na mapie.</div>';
  pw.appendChild(pane);
  var spec=document.createElement("div");spec.id="mk-spec";
  var as=rep.querySelector("#report-aside");
  var pi=document.createElement("div");pi.className="qaside-sec";pi.setAttribute("data-sec","otrasie");pi.id="mk-introsec";spec.appendChild(pi);
  var ps=document.createElement("div");ps.className="qaside-sec";ps.setAttribute("data-sec","plan");ps.id="mk-plansec";spec.appendChild(ps);
  var pg=document.createElement("div");pg.className="qaside-sec";pg.setAttribute("data-sec","goscie");pg.id="mk-guestsec";spec.appendChild(pg);
  if(as){["alerty","legenda"].forEach(function(k){var sec=as.querySelector('.qaside-sec[data-sec="'+k+'"]');if(sec)spec.appendChild(sec);});}
  pw.appendChild(spec);hd.appendChild(pw);
  rep.querySelectorAll(".qaside-tab").forEach(function(t){t.style.display="none";});
  var n=rep.querySelectorAll("#r-alerts .alert").length;
  var ab=rail.querySelector('.mk-tab[data-id="alerty"]')||rail.querySelector('.mk-tab[data-id="plan"]');
  if(ab){if(n){var bd=document.createElement("span");bd.className="mk-cnt";bd.textContent=n;bd.title="alerty pogodowe";ab.querySelector(".ic").appendChild(bd);}else if(ab.dataset.id==="alerty")ab.classList.add("mk-dim");}
  sunBox();
  pw.querySelector(".mk-x").onclick=function(){toggle(null);};
  pw.addEventListener("click",function(e){
    var t=e.target;if(t.closest("a,button,input,select,label,textarea"))return;
    var row=t.closest(".ms-list li,.climb-card,.wx-etapy li,.strat-card,.alert");if(!row||!pw.contains(row))return;
    var src=row.querySelector(".climb-hd")||row;var mm=KMRE.exec(src.textContent||"");if(!mm)return;
    var a=num(mm[1]),b=mm[2]!=null?num(mm[2]):null;
    if(showKm(a,b))row.classList.add("mk-sel");
  });
  active=null;document.body.classList.remove("mk-open");document.body.classList.remove("mk-spec");
  setTimeout(placeRail,50);setTimeout(placeRail,400);
  if(window.__mkBuilt)try{window.__mkBuilt();}catch(e){}
  var ro=window.__mkReopen;window.__mkReopen=null;if(ro)setTimeout(function(){toggle(ro);},0);
}
var CWRE=/~?(\d+)\s*W przy ([\d.,]+)\s*km\/h\s*\((\d+)%\s*osiagalnego\s*~?(\d+)\s*W,\s*~?([\d.,]+)\s*min\)(?:,\s*crux\s*~?(\d+)\s*W)?(?:;\s*min\.\s*([\d.,]+)\s*km\/h\s*=\s*(\d+)\s*rpm\s*na\s*([\d\/]+))?(?:\s*\(kaseta\s*([\d-]+)\))?/;
function fmtClimbs(root){
  (root||document).querySelectorAll(".climb-why").forEach(function(el){
    if(el.dataset.mkf)return;var m=CWRE.exec(el.textContent||"");if(!m)return;el.dataset.mkf="1";
    var c=function(x){return String(x).replace(".",",");};
    var h='<span>potrzebna moc</span><b>~'+m[1]+' W \u00b7 '+m[3]+'% Twoich mo\u017cliwo\u015bci (~'+m[4]+' W przez ~'+c(m[5])+' min)</b>';
    if(m[6])h+='<span>najtrudniejszy fragment</span><b>~'+m[6]+' W</b>';
    h+='<span>pr\u0119dko\u015b\u0107</span><b>~'+c(m[2])+' km/h'+(m[7]?' \u00b7 minimum '+c(m[7])+' km/h':'')+'</b>';
    if(m[9])h+='<span>prze\u0142o\u017cenie</span><b>'+m[9]+(m[8]?' \u2192 '+m[8]+' rpm':'')+(m[10]?' (kaseta '+m[10]+')':'')+'</b>';
    el.className="mk-cw";el.innerHTML=h;
  });
}

/* O trasie: opis AI (raz na trase). Dane: window.__mkIntroData (gosc) albo window.__mkIntroLoad() (organizator). */
function introHTML(it){
  var e=function(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});};
  var km=function(x){return (x==null?"":String(x).replace(".",","));};
  var h='<div class="mki-t">'+e(it.tytul)+'</div><p class="mki-p">'+e(it.wprowadzenie)+'</p>';
  if(it.czego_sie_spodziewac&&it.czego_sie_spodziewac.length)h+='<div class="ms-sub">Czego si\u0119 spodziewa\u0107</div><ul class="mki-l">'+it.czego_sie_spodziewac.map(function(x){return '<li>'+e(x)+'</li>';}).join("")+'</ul>';
  if(it.warto_zobaczyc&&it.warto_zobaczyc.length)h+='<div class="ms-sub">Warto zobaczy\u0107</div><ul class="ms-list">'+it.warto_zobaczyc.map(function(x){return '<li><b>km '+km(x.km)+'</b> \u00b7 <b>'+e(x.nazwa)+'</b><div class="k">'+e(x.dlaczego)+'</div></li>';}).join("")+'</ul>';
  return h;
}
function renderIntro(){
  var el=document.getElementById("mk-introsec");if(!el)return;
  var it=window.__mkIntroData;
  if(it===undefined&&typeof window.__mkIntroLoad==="function"){el.innerHTML='<div class="k">wczytuj\u0119 opis trasy\u2026</div>';
    window.__mkIntroLoad().then(renderIntro,renderIntro);return;}
  if(!it){
    if(typeof window.__mkIntroGen==="function"){
      el.innerHTML='<div class="mkp-empty">Ta trasa nie ma jeszcze opisu. AI przygotuje wprowadzenie: gdzie le\u017cy trasa, jaki to region, czego si\u0119 spodziewa\u0107 i co warto zobaczy\u0107 (~30 s, raz na tras\u0119; opis zobacz\u0105 te\u017c zaproszeni go\u015bcie).<br><button type="button" class="mkp-go" id="mki-gen">Wygeneruj opis trasy</button></div>';
      var b=document.getElementById("mki-gen");b.onclick=function(){b.disabled=true;b.textContent="Generuj\u0119\u2026 (~30 s)";window.__mkIntroGen().then(renderIntro,function(err){b.disabled=false;b.textContent="Spr\u00f3buj ponownie";el.insertAdjacentHTML("beforeend",'<div class="mkx-err">'+String(err&&err.message||err).slice(0,120)+'</div>');});};
    }else el.innerHTML='<div class="k">Brak opisu trasy.</div>';
    return;}
  var h=introHTML(it);
  if(typeof window.__mkIntroGen==="function")h+='<div class="mkp-foot">'+(it.aktualny===false?'<b style="color:var(--warn)">Trasa zmieni\u0142a si\u0119 od napisania opisu.</b> ':'')+'Opis AI '+qTsLocal(it.created_at,true)+' \u00b7 <button type="button" class="mkp-link" id="mki-re">napisz od nowa</button></div>';
  el.innerHTML=h;
  var re=document.getElementById("mki-re");if(re)re.onclick=function(){if(!confirm("Napisa\u0107 opis od nowa (nowy przebieg AI)?"))return;window.__mkIntroData=null;el.innerHTML='<div class="k">generuj\u0119\u2026 (~30 s)</div>';window.__mkIntroGen().then(renderIntro,renderIntro);};
  markRows();
}
window.__mkIntroRender=renderIntro;

/* Slonce: wschod/zachod + ostrzezenie, gdy start przed wschodem albo meta po zachodzie (plan z danych renderu) */
function _hm2m(s){var p=String(s||"").split(":");return p.length>1?(+p[0])*60+(+p[1]):null;}
function sunInfo(d){
  var sl=d&&d.details&&d.details.weather&&d.details.weather.slonce;if(!sl||!sl.wschod||!sl.zachod)return null;
  var st=_hm2m(d.start&&d.start.time),th=d.time&&d.time.total_h,meta=(st!=null&&th!=null)?Math.round(st+th*60):null;
  var w=_hm2m(sl.wschod),z=_hm2m(sl.zachod),warn=[];
  if(st!=null&&st<w)warn.push("start przed wschodem ("+sl.wschod+")");
  if(meta!=null&&meta>z){var hh=String(Math.floor(meta/60)%24).padStart(2,"0")+":"+String(meta%60).padStart(2,"0");warn.push("meta ~"+hh+" po zachodzie ("+sl.zachod+")");}
  return {wschod:sl.wschod,zachod:sl.zachod,warn:warn,zapas:(meta!=null?z-meta:null)};
}
function sunBox(){
  var d=window.__mkLastD,ex=document.getElementById("r-extra");if(!ex||!d)return;
  var si=sunInfo(d),old=document.getElementById("mk-sun");if(old)old.remove();if(!si)return;
  var b=document.createElement("div");b.className="cx-sec"+(si.warn.length?" mk-sunwarn":"");b.id="mk-sun";
  var zp=(si.zapas!=null&&si.zapas>=0)?'<span class="cx-note">'+(si.zapas>=60?Math.floor(si.zapas/60)+" h "+String(si.zapas%60).padStart(2,"0")+" min":si.zapas+" min")+' zapasu do zmroku</span>':'';
  b.innerHTML='<div class="cx-h">S\u0142o\u0144ce</div><div class="mk-sunrow">\u2600\ufe0e wsch: <b>'+si.wschod+'</b> \u00b7 zach: <b>'+si.zachod+'</b></div>'+
    (si.warn.length?'<div class="mk-sunw">\u26a0 '+si.warn.join(" \u00b7 ")+' \u2014 we\u017a o\u015bwietlenie</div>':zp);
  ex.insertBefore(b,ex.firstChild);
}
window.__mkSunInfo=function(){return sunInfo(window.__mkLastD);};
function markRows(){
  var pw=document.getElementById("mk-pane");if(!pw)return;
  pw.querySelectorAll(".ms-list li,.climb-card,.wx-etapy li,.strat-card,.alert").forEach(function(r){
    var s=r.querySelector(".climb-hd")||r;if(KMRE.test(s.textContent||""))r.classList.add("mk-km");
  });
}
function toggle(id){
  clearHL();
  if(!id||id===active){active=null;document.body.classList.remove("mk-open");document.body.classList.remove("mk-spec");}
  else{
    active=id;document.body.classList.add("mk-open");
    var isSpec=(id==="alerty"||id==="legenda"||id==="plan"||id==="otrasie"||id==="goscie");
    document.body.classList.toggle("mk-spec",isSpec);
    document.querySelectorAll("#mk-spec .qaside-sec").forEach(function(x){x.classList.toggle("on",x.getAttribute("data-sec")===id);});
    var t=document.getElementById("mk-ttl");
    if(isSpec){if(t)t.textContent=(id==="alerty"?"Alerty dla trasy":id==="plan"?"Plan dnia":id==="otrasie"?"O trasie":id==="goscie"?"Zaproszenia":"Legenda");if(id==="otrasie")renderIntro();if(id==="goscie"&&window.__mkGuestsRender)window.__mkGuestsRender();if(id==="plan"&&window.__mkPlanRender)window.__mkPlanRender();}
    else{var src=rep.querySelector('#multi-nav .multi-item[data-id="'+id+'"]');if(src)src.click();if(t&&src)t.textContent=src.textContent;
      var _mb=document.querySelector("#mk-pane .multi-body");
      if(id==="strategia"&&_mb&&window.__mkStrategy)window.__mkStrategy(_mb);
      if(id==="przewyzszenia"&&_mb)fmtClimbs(_mb);
      if(id==="forma"&&_mb&&window.__mkForma)window.__mkForma(_mb);
      if(id==="sprzet"&&_mb&&window.__mkGearRender){window.__mkGearRender(_mb);}
      else if(id==="sprzet"){var mb=document.querySelector("#mk-pane .multi-body");if(mb&&!mb.querySelector(".mk-park")){var pk=document.createElement("div");pk.className="mk-park";pk.innerHTML='<b>Zaparkowane</b> \u2014 ubi\u00f3r i opony do osobnej dyskusji. Tre\u015b\u0107 poni\u017cej to obecna wersja (generowana przez AI).';mb.insertBefore(pk,mb.firstChild);}}}
    var hd=rep.querySelector("header");if(hd)hd.scrollTop=0;
    markRows();
  }
  document.querySelectorAll(".mk-tab").forEach(function(b){b.classList.toggle("on",b.dataset.id===active);});
  placeRail();
  setTimeout(function(){
    try{window.dispatchEvent(new Event("resize"));}catch(e){}
    setTimeout(function(){placeRail();if(active)fitRoute();else if(window.MAPX&&window.MAPX.fitAll)window.MAPX.fitAll();},60);
  },20);
}
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&active)toggle(null);});
window.__mk={toggle:toggle,active:function(){return active;},markRows:markRows,showKm:showKm};
window.addEventListener("resize",function(){setTimeout(placeRail,30);});
if(rep){new MutationObserver(function(){setTimeout(build,0);}).observe(rep,{childList:true});}
try{if(window.ResizeObserver){new ResizeObserver(function(){placeRail();}).observe(document.body);}}catch(e){}
setInterval(placeRail,1000);
setTimeout(build,300);
})();
