/* raport-jazdy3-rail.js - Raport z jazdy v3 (2026-10-06): ikony jako prawa kolumna lewego panelu jazdy;
   klik ikony otwiera panel sekcji nad mapa - od lewego panelu do ramki "slad" (mechanika jak Analiza trasy).
   Lewy panel: kluczowe liczby (ws.js #k5) + dodatkowe dane jazdy (#k5x) + werdykt AI.
   Tresc sekcji: ten sam generator co dotad (raport-jazdy2-dane.js przez daneRender w raport-jazdy2-ws.js).
   Haczyki w ws.js: window.__RJ3 (after, padL), window.__RJapi (fit, inval, data). */
(function(){
"use strict";
/* telefon: do czasu etapu 2 zostaje dotychczasowy widok mobilny (v2) - wylacz haczyki v3 */
if(window.matchMedia("(max-width:820px),(pointer:coarse) and (max-height:500px)").matches){try{delete window.__RJ3;}catch(e){window.__RJ3=undefined;}document.body.classList.remove("rj3");return;}
var $=function(i){return document.getElementById(i);};
var V=function(x){return (x&&typeof x==="object"&&"value" in x)?x.value:x;};
var isNum=function(v){return typeof v==="number"&&isFinite(v);};
function n(v,d){return isNum(v)?v.toFixed(d==null?0:d):"—";}
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
var SV=function(p){return '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+p+'</svg>';};
var SECS=[
 {k:"an",id:"an",lab:"Podsumowanie AI",c:"#7fc8d8",i:'<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>'},
 {k:"wys",t:"Wysiłek",lab:"Wysiłek",c:"#f07878",i:'<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>'},
 {k:"pred",t:"Prędkość",lab:"Prędkość",c:"#6fb3ec",i:'<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>'},
 {k:"zap",t:"Zapas na zrywy",lab:"Zapas na zrywy",c:"#a99bf0",i:'<rect x="2" y="7" width="16" height="10" rx="2"/><path d="M22 11v2"/><path d="M6 11v2"/><path d="M10 11v2"/>'},
 {k:"cialo",t:"Ciało tego dnia",lab:"Ciało tego dnia",c:"#f08ac0",i:'<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>'},
 {k:"war",t:"Warunki i teren",lab:"Warunki i teren",c:"#e0a44a",i:'<path d="M12 2v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="M20 12h2"/><path d="m19.07 4.93-1.41 1.41"/><path d="M15.95 12.65a4 4 0 0 0-5.93-4.13"/><path d="M13 22H7a5 5 0 1 1 4.9-6H13a3 3 0 0 1 0 6Z"/>'},
 {k:"rower",t:"Rower i napęd",lab:"Rower i napęd",c:"#f0975a",i:'<circle cx="18.5" cy="17.5" r="3.5"/><circle cx="5.5" cy="17.5" r="3.5"/><circle cx="15" cy="5" r="1"/><path d="M12 17.5V14l-3-3 4-3 2 3h2"/>'},
 {k:"jedz",t:"Jedzenie",lab:"Jedzenie",c:"#4cc9b0",i:'<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/>'},
 {sep:1},
 {k:"odc",lab:"Odcinek (zaznacz na wykresie)",c:"#e8742a",i:'<path d="M3 12h18"/><path d="M7 7v10"/><path d="M17 7v10"/>'}
];
var BY={};SECS.forEach(function(s){if(s.k)BY[s.k]=s;});
var cur=null,dane=$("dane"),dgrid=$("dgrid"),dhd=$("dhd"),pj=$("pj"),ws=$("ws"),rail,odc,main;
window.__RJ3=window.__RJ3||{};
var MOB=window.matchMedia("(max-width:820px),(pointer:coarse) and (max-height:500px)");

/* --- lewy panel: [dane jazdy | ikony] --- */
main=document.createElement("div");main.className="pjmain";
while(pj.firstChild)main.appendChild(pj.firstChild);pj.appendChild(main);
main.insertAdjacentHTML("beforeend",'<div class="pjsep"></div><div class="kk" id="k5x"></div><div id="pjv" class="empty"><b>Werdykt</b>…</div>'
  +'<div class="pjbtns"><button type="button" id="zkbtn" class="pjzk" title="Z kim jechałem">'+SV('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>')+'<span>Z kim jechałem</span></button>'
  +'<button type="button" id="ubbtn" class="pjzk pjub" title="Ubiór / rower">'+SV('<path d="M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"/>')+'<span>Ubiór / rower</span></button></div>');
/* 2026-10-08: "Ubior / rower" - W czym jechalem (raport-jazdy2-gear.js #gearp) + rower po jezdzie do zrobienia, w oknie qModal */
document.getElementById("ubbtn").addEventListener("click",function(){var G=window.__RJgear;if(!G||!window.qModal)return;var p=G.panel,mo=null;
  p.classList.add("inmod");
  var md=window.qModal("Ubiór / rower",p,function(el){if(mo)mo.disconnect();el.classList.remove("inmod");el.style.display="none";document.body.appendChild(el);});
  G.open();if(window.MutationObserver){mo=new MutationObserver(function(){if(p.style.display==="none")md.close();});mo.observe(p,{attributes:true,attributeFilter:["style"]});}});
/* 2026-10-08: "Z kim jechalem" - zamiast sekcji w kolumnie ikon: przycisk pod werdyktem, otwiera okno nakladane (nav.js qModal,
   wyglad jak okno dostepow). Formularz #zk (ws.js, z obsluga zapisu) jest na czas okna przenoszony do niego i potem wraca. */
document.getElementById("zkbtn").addEventListener("click",function(){var z=$("zk");if(!z||!window.qModal)return;
  var home=z.parentNode,nxt=z.nextSibling;z.classList.add("inmod");z.style.display="";
  window.qModal("Z kim jechałem",z,function(el){el.classList.remove("inmod");if(home&&home.isConnected)home.insertBefore(el,(nxt&&nxt.parentNode===home)?nxt:null);});
  setTimeout(function(){var i=$("zk-in");if(i)i.focus();},50);});
rail=document.createElement("div");rail.id="rail";
rail.innerHTML=SECS.map(function(s){if(s.sep)return '<div class="sep"></div>';return '<button type="button" data-k="'+s.k+'" title="'+s.lab+'" aria-label="'+s.lab+'" style="--c:'+s.c+'">'+SV(s.i)+'</button>';}).join("");
pj.appendChild(rail);
/* przyciski mapy na mapie (pod ramka "slad") */
var mc=document.createElement("div");mc.className="ov";mc.id="mapctl";["bwbtn","fitbtn"].forEach(function(i){var b=$(i);if(b)mc.appendChild(b);});ws.appendChild(mc);if(window.qMapCtl)window.qMapCtl(mc);/* 2026-10-07: prawy dolny rog mapy (qmap-tiles.js) */
rail.addEventListener("click",function(e){var b=e.target.closest("button[data-k]");if(!b)return;var k=b.dataset.k,s=BY[k];
  if(s.act==="gear"){var g=$("gearbtn");if(g)g.click();return;}
  if(cur===k)close();else open(k);});

/* --- dodatkowe dane jazdy + werdykt AI --- */
function kt(l,v,s){return '<div><p class="lbl">'+l+'</p><div class="v">'+v+'</div><div class="s">'+(s||"&nbsp;")+'</div></div>';}
var VK=null;
function extras(){var api=window.__RJapi,D=api&&api.data?api.data():null,box=$("k5x");if(!D||!box)return;
  var L=D.load||{},sp=V(D.speed)||{},we=D.weather||{},wi=V(D.wind)||{},sf=V(D.surface)||{},dt=D.drivetrain||{};
  var tc=V(we.temp_c)||{},ap=V(we.apparent_c)||{},ww=V(we.wind_ms)||{},cbg=V(dt.cad_by_grade)||{},tp=sf.types_pct||{};
  var ta=isNum(tc.avg)?tc.avg:tc.mean,aa=isNum(ap.avg)?ap.avg:ap.mean,hard=tp["twarda szybka"];
  box.innerHTML=
    kt("praca",n(V(L.kj))+" <small>kJ</small>",isNum(V(L.kj_h))?n(V(L.kj_h))+" kJ/h":"")+
    kt("postoje",isNum(sp.stop_s)?Math.round(sp.stop_s/60)+" <small>min</small>":"—",isNum(sp.postoje_model_min)?"typowo ~"+Math.round(sp.postoje_model_min):"")+
    kt("kadencja",isNum(cbg.plasko)?Math.round(cbg.plasko)+"":"—",isNum(cbg.plasko)?"na płaskim":"")+
    kt("temperatura",isNum(ta)?n(ta)+" <small>°C</small>":"—",isNum(aa)?"odczuwalna "+n(aa):"")+
    kt("wiatr",isNum(ww.avg)?n(ww.avg,1)+" <small>m/s</small>":"—",isNum(wi.avg_tail_ms)?"wzdłuż trasy "+(wi.avg_tail_ms>0?"+":"")+n(wi.avg_tail_ms,1):"")+
    kt("nawierzchnia",isNum(hard)?Math.round(hard)+"<small>%</small>":"—",isNum(hard)?"twarda szybka":"");
  var rk=$("ridesel")&&$("ridesel").value;if(!rk||VK===rk)return;VK=rk;var pv=$("pjv");pv.className="empty";pv.innerHTML="<b>Werdykt</b>…";
  fetch("/api/ride-report/w2?ride="+encodeURIComponent(rk),{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.ok?r.json():null;}).then(function(j){
    if(VK!==rk)return;if(j&&j.verdict){pv.className="";pv.innerHTML="<b>Werdykt</b>"+esc(j.verdict);}else pv.innerHTML="<b>Werdykt</b>Brak analizy AI — ikona ⓘ pozwala ją wygenerować.";}).catch(function(){});}

/* --- Odcinek: kontener z podpowiedzia + okienko #sg przeniesione do panelu --- */
odc=document.createElement("div");odc.id="odcwrap";odc.style.display="none";
odc.innerHTML='<p class="hint" id="odchint">Przeciągnij po wykresie na dole (od km do km), żeby zaznaczyć odcinek. Tu pojawią się jego liczby, <b>Komentarz AI</b> i <b>Do porównania</b>. Dwuklik na zaznaczeniu przybliża wykres; klik w wykres albo Esc wraca do całej jazdy.</p>';
dane.appendChild(odc);
var sg=$("sg");if(sg)odc.appendChild(sg);
if(sg&&window.MutationObserver){new MutationObserver(function(){var vis=sg.style.display==="block";$("odchint").style.display=vis?"none":"";if(vis&&cur!=="odc")open("odc");if(!vis&&cur==="odc")close();/* 2026-10-08: zdjete zaznaczenie zamyka okno Odcinek */}).observe(sg,{attributes:true,attributeFilter:["style"]});}

/* --- geometria: dol panelu nad wykresem, prawa krawedz przy ramce "slad" --- */
var dock=$("dock");
function geo(){if(dock)document.body.style.setProperty("--dockh",dock.offsetHeight+"px");
  if(MOB.matches){dane.style.left="";dane.style.width="";return;}
  var wr=ws.getBoundingClientRect(),pr=pj.getBoundingClientRect(),tl=$("tl"),tr=tl&&tl.offsetParent?tl.getBoundingClientRect():null;
  var left=Math.round(pr.right-wr.left+10),right=tr?Math.round(tr.left-wr.left-10):Math.round(wr.width-12);
  var w=Math.max(420,right-left);dane.style.left=left+"px";dane.style.width=w+"px";dane.style.setProperty("--danew",w+"px");
  var mcx=$("mapctl");if(mcx&&tr)mcx.style.top=Math.round(tr.bottom-wr.top+8)+"px";
  document.body.classList.toggle("rj3-narrow",w<700);}
try{if(window.ResizeObserver){var rfT=null,ro=new ResizeObserver(function(){geo();padCalc();/* 2026-10-08: okno sekcji zmienilo rozmiar (np. komentarz AI) -> mapa dopasowuje sie ponownie */if(cur){clearTimeout(rfT);rfT=setTimeout(refit,120);}});if(dock)ro.observe(dock);ro.observe(pj);ro.observe(dane);var tlx=$("tl");if(tlx)ro.observe(tlx);}}catch(e){}
window.addEventListener("resize",function(){geo();padCalc();});

function secEl(s){if(!s)return null;if(s.id)return $(s.id);var hit=null;dgrid.querySelectorAll(".dsec").forEach(function(d){var b=d.querySelector(".dh b");if(b&&b.textContent.trim()===s.t)hit=d;});return hit;}
function apply(){
  var s=BY[cur],none=$("rj3none");if(none)none.remove();
  dane.classList.toggle("odc-fit",cur==="odc");   /* 2026-10-08: okno Odcinek szerokie i wysokie tylko na tyle, ile maja dane */
  if(cur==="odc"){dgrid.style.display="none";odc.style.display="";}
  else{odc.style.display="none";dgrid.style.display="";var el=secEl(s);
    dgrid.querySelectorAll(".dsec").forEach(function(d){d.style.display=(d===el)?"":"none";});
    if(!el)dgrid.insertAdjacentHTML("afterbegin",'<div id="rj3none">Brak danych dla tej jazdy w tej sekcji.</div>');}
  dhd.innerHTML='<div class="rj3h"><b style="--c:'+s.c+'"><i>'+SV(s.i)+'</i>'+s.lab.replace(/ \(.*\)$/,"")+'</b><button type="button" id="rj3x" aria-label="zamknij">×</button></div>';
  $("rj3x").onclick=close;dane.scrollTop=0;
}
function marks(){rail.querySelectorAll("button[data-k]").forEach(function(b){var k=b.dataset.k,s=BY[k];b.classList.toggle("on",k===cur);
  if(s.t||s.id)b.classList.toggle("off",!secEl(s));});}
/* 2026-10-08: lewy margines dopasowania mapy = prawa krawedz NAJDALSZEGO widocznego panelu (panel jazdy albo otwarte okno sekcji, np. Odcinek) */
function padCalc(){var mr=$("map").getBoundingClientRect(),x=0;[pj,dane].forEach(function(e){if(!e||MOB.matches&&e===dane)return;var c=getComputedStyle(e),r=e.getBoundingClientRect();if(c.display!=="none"&&c.visibility!=="hidden"&&r.width>0&&r.height>0)x=Math.max(x,r.right);});window.__RJ3.padL=Math.max(80,Math.round(x-mr.left+20));}
window.__RJ3.pad=padCalc;
function refit(){var api=window.__RJapi;if(!api)return;padCalc();api.inval();api.fit();}
function open(k){cur=k;geo();dane.style.display="flex";document.body.classList.add("rj3-open");apply();marks();setTimeout(refit,60);
  try{history.replaceState(null,"",location.pathname+location.search+"#"+k);}catch(e){}}
function close(){cur=null;dane.style.display="none";document.body.classList.remove("rj3-open");marks();setTimeout(refit,60);
  try{history.replaceState(null,"",location.pathname+location.search);}catch(e){}}

/* po kazdym przeliczeniu sekcji (zmiana jazdy) */
/* Zapas na zrywy: "Bilans zapasu" obok "Minimum zapasu" (dwa male kafle w jednym rzedzie), wykres i tabela pod spodem */
function zapFix(){var s=secEl(BY.zap);if(!s)return;var its=[].slice.call(s.querySelectorAll(".nar>.it"));var t=function(e){var b=e.querySelector(".h b");return b?b.textContent.trim():"";};
  var mn=its.filter(function(e){return t(e)==="Minimum zapasu";})[0],bl=its.filter(function(e){return t(e)==="Bilans zapasu";})[0];
  if(mn&&bl){mn.parentNode.insertBefore(bl,mn.nextSibling);mn.classList.remove("wt");bl.classList.remove("wt");}}
window.__RJ3.after=function(){zapFix();if(cur)apply();marks();extras();padCalc();};
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&cur&&cur!=="odc")close();});
geo();padCalc();
var h0=(location.hash||"").slice(1);if(BY[h0]&&!BY[h0].act)setTimeout(function(){open(h0);},400);
})();
