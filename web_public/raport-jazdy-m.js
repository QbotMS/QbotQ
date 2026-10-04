/* raport-jazdy-m.js - MOBILE v2.1 (2026-09-29): minimalistyczny widok raportu jazdy na telefonie.
   Wlacza sie na telefonie w pionie i w poziomie (ekran <=820px LUB dotyk i wysokosc <=500px) - obrot nie przelacza wersji.
   Komputer bez zmian. Nie duplikuje logiki: przenosi istniejace elementy (wybor jazdy, liczby, mapa)
   do prostego ekranu startowego i pokazuje jeden dzial naraz.
   Poziomy: start -> dzial (mapa / wykres / analiza / AI / ubior / z kim) -> "Wiecej opcji" wykresu.
   Na podstronach: menu i "wstecz" w dolnym lewym rogu (w zasiegu kciuka); dziala tez gest wstecz. */
(function(){
"use strict";
var Q="(max-width:820px),(pointer:coarse) and (max-height:500px)";
var MQ=window.matchMedia(Q);
if(!MQ.matches)return;
function $(id){return document.getElementById(id);}
var VIEW="home",SIZING=false;
var TOP="env(safe-area-inset-top,0px)";
var CSS=[
"body.m1{overflow:hidden}",
"body.m1 #pj,body.m1 #tl{display:none!important}",
"body.m1 #ws{left:0!important}",
"body.m1 .qnav-fab{z-index:1210!important}",
"body.m1:not(.m1-home) .qnav-fab{display:none!important}",
"#m1{position:fixed;inset:0;z-index:1100;overflow-y:auto;-webkit-overflow-scrolling:touch;background:var(--bg);padding:calc(8px + "+TOP+") calc(12px + env(safe-area-inset-right,0px)) calc(18px + env(safe-area-inset-bottom,0px)) calc(12px + env(safe-area-inset-left,0px));box-sizing:border-box}",
".m1-top{padding-left:54px;min-height:44px;display:flex;align-items:center}",
".m1-top select{width:100%;font:inherit;font-size:16px;min-height:44px;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:6px 10px;margin:0}",
"#m1-mapbox{position:relative;height:190px;border-radius:12px;overflow:hidden;margin:10px 0;border:1px solid var(--line);background:var(--well)}",
"#m1-mapbox #map{position:absolute;inset:0}",
".m1-mapx{position:absolute;right:8px;top:8px;z-index:800;width:44px;height:44px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink);font-size:20px;line-height:1}",
".m1-kk .kk{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:8px!important}",
".m1-kk .kk>*{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 10px;min-width:0}",
".m1-kk .kk .lbl{font-size:12px!important;color:var(--ink2)}.m1-kk .kk .v{font-size:18px!important}.m1-kk .kk .s{display:none}",
".m1-list{margin-top:14px;border-top:1px solid var(--line)}",
".m1-row{display:flex;align-items:center;gap:12px;width:100%;min-height:54px;padding:6px 4px;border:0;border-bottom:1px solid var(--line);background:none;color:var(--ink);font:inherit;font-size:16px;text-align:left;cursor:pointer}",
".m1-row .ic{width:26px;text-align:center;font-size:18px;flex:0 0 26px}",
".m1-row .tx{display:flex;flex-direction:column;min-width:0}.m1-row .sb{font-size:13px;color:var(--muted);margin-top:1px}",
".m1-row .ch{margin-left:auto;color:var(--muted);font-size:22px}",
"@media (orientation:landscape){#m1-mapbox{height:150px}.m1-kk .kk{grid-template-columns:repeat(6,minmax(0,1fr))!important}}",
"body.m1-home #ws{visibility:hidden;pointer-events:none}",
"body.m1-home #gearp,body.m1-home #sg,body.m1-map #gearp,body.m1-map #sg{display:none!important}",
/* dolny pasek: menu + wstecz */
"#m1-bar{display:none;position:fixed;z-index:1205;right:calc(12px + env(safe-area-inset-right,0px));bottom:calc(12px + env(safe-area-inset-bottom,0px));gap:8px;flex-direction:row-reverse}",
"body.m1:not(.m1-home) #m1-bar{display:flex}",
"#m1-bar button{width:48px;height:48px;border-radius:50%;border:1px solid var(--line);background:color-mix(in srgb,var(--card) 92%,transparent);color:var(--ink);font:inherit;font-size:22px;line-height:1;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 12px rgba(0,0,0,.35);padding:0;cursor:pointer}",
"#m1-bar svg{width:22px;height:22px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}",
/* mapa */
"body.m1-map #m1{overflow:hidden;padding:0}",
"body.m1-map #m1>:not(#m1-mapbox){display:none}",
"body.m1-map #m1-mapbox{position:fixed;inset:0;height:auto;margin:0;border-radius:0;border:0}",
"body.m1-map .m1-mapx{top:calc(12px + env(safe-area-inset-top,0px));right:calc(12px + env(safe-area-inset-right,0px))}",
".m1-mapx{border-radius:50%!important;display:flex;align-items:center;justify-content:center;padding:0;box-shadow:0 2px 10px rgba(0,0,0,.3)}.m1-mapx svg{width:22px;height:22px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}",
"body.m1-chart #m1,body.m1-dane #m1,body.m1-gear #m1{display:none}",
/* wykres */
"body.m1-chart #dock{top:calc(6px + "+TOP+")!important;bottom:0!important;left:0!important;right:0!important;border-radius:0!important;border:0!important;overflow-y:auto;padding:6px calc(10px + env(safe-area-inset-right,0px)) calc(70px + env(safe-area-inset-bottom,0px)) calc(10px + env(safe-area-inset-left,0px))!important;z-index:1100}",
"body.m1-chart #dock .dbar{flex-wrap:wrap!important;overflow:visible!important;margin:0 0 6px!important;padding:0!important}",
"body.m1-chart #grip{display:none}",
"body.m1-chart #dock .chip{min-height:40px}",
"body.m1-chart:not(.m1-advon) #dock .chip[data-l=spd],body.m1-chart:not(.m1-advon) #dock .chip[data-l=cad],body.m1-chart:not(.m1-advon) #dock .chip[data-l=dev],body.m1-chart:not(.m1-advon) #dock .chip[data-l=temp]{display:none}",
"body.m1-chart:not(.m1-advon) #dock .grp:has(#preset),body.m1-chart:not(.m1-advon) #dock .grp:has([data-r]),body.m1-chart:not(.m1-advon) #dock .grp:has([data-sc]),body.m1-chart:not(.m1-advon) #dock .grp:has([data-x]){display:none}",
"#m1-adv,#m1-rot{display:none}body.m1-chart #m1-adv{display:inline-block;min-height:40px}",
"#m1-rot{font-size:13px;color:var(--muted);margin:2px 0 6px}",
"@media (orientation:portrait){body.m1-chart #m1-rot{display:block}}",
"@media (orientation:landscape){body.m1-chart #dock .dbar,body.m1-chart #dock .mks{flex-wrap:nowrap!important;overflow-x:auto!important;scrollbar-width:none}body.m1-chart #dock .dbar::-webkit-scrollbar{display:none}body.m1-chart #dock{padding-right:calc(70px + env(safe-area-inset-right,0px))!important;padding-bottom:calc(6px + env(safe-area-inset-bottom,0px))!important}}",
"body.m1-chart #sg{top:auto!important;bottom:0!important;left:0!important;right:0!important;width:auto!important;max-height:55vh;overflow:auto;border-radius:14px 14px 0 0;z-index:1150;padding-bottom:calc(70px + env(safe-area-inset-bottom,0px))!important}",
/* analiza */
"body.m1-dane #dane{top:0;z-index:1100;padding-top:"+TOP+";padding-bottom:calc(76px + env(safe-area-inset-bottom,0px))}",
"body.m1-dane #dhd{display:none}",
/* ubior */
"body.m1-gear #ws{visibility:hidden;pointer-events:none}",
"body.m1-gear #gearp{display:block!important;position:fixed!important;top:0!important;left:0!important;right:0!important;bottom:0!important;width:auto!important;z-index:1150;border-radius:0;border:0;padding-top:calc(12px + "+TOP+")!important;padding-bottom:calc(80px + env(safe-area-inset-bottom,0px))!important}",
"body.m1-gear #gearp select,body.m1-gear #gearp textarea{font-size:16px}"
].join("\n");

function fire(){try{window.dispatchEvent(new Event("resize"));}catch(e){}}
function fit(){var f=$("fitbtn");if(f)f.click();}
function row(v,ic,t,sb){return '<button type="button" class="m1-row" data-m1="'+v+'"><span class="ic">'+ic+'</span><span class="tx"><span>'+t+'</span>'+(sb?'<span class="sb">'+sb+'</span>':'')+'</span><span class="ch">\u203a</span></button>';}
var ICO_MENU='<svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16"/></svg>';
var ICO_BACK='<svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg>';
var ICO_FIT='<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/><circle cx="12" cy="12" r="8"/></svg>';

function build(){
  var ws=$("ws"),map=$("map"),sel=$("ridesel"),k5=$("k5");
  if(!ws||!map||!sel||!k5||$("m1"))return false;
  var st=document.createElement("style");st.id="m1-css";st.textContent=CSS;document.head.appendChild(st);
  var m=document.createElement("div");m.id="m1";
  m.innerHTML='<div class="m1-top"><div class="m1-sel" style="flex:1;min-width:0"></div></div>'+
    '<div id="m1-mapbox"><button type="button" class="m1-mapx" id="m1-fit" aria-label="Wy\u015brodkuj tras\u0119">'+ICO_FIT+'</button></div>'+
    '<div class="m1-kk"></div>'+
    '<div class="m1-list">'+
      row("map","\ud83d\uddfa\ufe0f","Mapa","ca\u0142a trasa, kolor wed\u0142ug mocy")+
      row("chart","\ud83d\udcc8","Wykres","najlepiej w poziomie")+
      row("dane","\ud83d\udccb","Analiza","wysi\u0142ek, zapas, cia\u0142o, teren, rower")+
      row("ai","\u2728","Komentarz AI","")+
      row("gear","\ud83d\udc55","W czym jecha\u0142em","")+
      row("zk","\ud83d\udc65","Z kim jecha\u0142em","")+
    '</div>';
  document.body.appendChild(m);
  m.querySelector(".m1-sel").appendChild(sel);
  $("m1-mapbox").insertBefore(map,$("m1-mapbox").firstChild);
  m.querySelector(".m1-kk").appendChild(k5);
  var bar=document.createElement("div");bar.id="m1-bar";
  bar.innerHTML='<button type="button" id="m1-back" aria-label="Wstecz">'+ICO_BACK+'</button><button type="button" id="m1-menu" aria-label="Menu">'+ICO_MENU+'</button>';
  document.body.appendChild(bar);
  $("m1-fit").addEventListener("click",function(e){e.stopPropagation();fit();});
  $("m1-back").addEventListener("click",function(){if(history.state&&history.state.m1)history.back();else go("home",false);});
  $("m1-menu").addEventListener("click",function(){var f=document.querySelector(".qnav-fab");if(f)f.click();else document.body.classList.toggle("qnav-open");});
  var dbar=document.querySelector("#dock .dbar");
  if(dbar){
    var rt=document.createElement("div");rt.id="m1-rot";rt.textContent="Obr\u00f3\u0107 telefon poziomo, \u017ceby zobaczy\u0107 wi\u0119cej szczeg\u00f3\u0142\u00f3w.";
    dbar.parentNode.insertBefore(rt,dbar);
    var a=document.createElement("button");a.id="m1-adv";a.type="button";a.className="chip";a.textContent="Wi\u0119cej opcji \u25be";dbar.appendChild(a);
    a.addEventListener("click",function(){var on=document.body.classList.toggle("m1-advon");a.textContent=on?"Mniej opcji \u25b4":"Wi\u0119cej opcji \u25be";setTimeout(sizeChart,30);});}
  m.addEventListener("click",function(e){var r=e.target.closest&&e.target.closest("[data-m1]");if(r)go(r.getAttribute("data-m1"),true);});
  window.addEventListener("popstate",function(e){go(e.state&&e.state.m1?e.state.m1:"home",false);});
  var ori=function(){setTimeout(function(){if(VIEW==="chart")sizeChart();else{fire();if(VIEW==="map"||VIEW==="home")fit();}},250);};
  try{window.matchMedia("(orientation:landscape)").addEventListener("change",ori);}catch(e){window.addEventListener("orientationchange",ori);}
  document.body.classList.add("m1","m1-home");
  setTimeout(fire,60);
  return true;
}

function sizeChart(){
  if(SIZING)return;SIZING=true;
  var d=$("dock"),c=$("chart");
  if(d&&c){var top=c.getBoundingClientRect().top-d.getBoundingClientRect().top;
    var cs=getComputedStyle(d),pb=parseFloat(cs.paddingBottom)||0;
    var h=Math.max(160,Math.round(d.clientHeight-top-pb-6));
    d.style.setProperty("--dh",h+"px");fire();}
  SIZING=false;
}
function openSec(id){
  var el=$(id);if(!el)return;
  if(!el.classList.contains("open")){var h=el.querySelector(".dh");if(h)h.click();else el.classList.add("open");}
  setTimeout(function(){try{el.scrollIntoView({block:"start"});}catch(e){}},60);
}
function leave(){
  var cls=document.body.classList;
  if(cls.contains("m1-dane")){var mb=document.querySelector('#viewseg button[data-v="map"]');if(mb)mb.click();}
  if(cls.contains("m1-chart")){var d=$("dock");if(d)d.style.removeProperty("--dh");cls.remove("m1-advon");var a=$("m1-adv");if(a)a.textContent="Wi\u0119cej opcji \u25be";}
  if(cls.contains("m1-gear")){var g=$("gearp");if(g)g.style.display="none";}
  var sg=$("sg");if(sg&&sg.style.display==="block"){var x=$("sg-x");if(x)x.click();}
  cls.remove("qnav-open");
  ["m1-home","m1-map","m1-chart","m1-dane","m1-gear"].forEach(function(c){cls.remove(c);});
}
function go(v,push){
  if(v===VIEW&&push)return;
  leave();VIEW=v;var cls=document.body.classList;
  if(push&&v!=="home"){try{history.pushState({m1:v},"");}catch(e){}}
  if(v==="home"){cls.add("m1-home");var m=$("m1");if(m)m.scrollTop=0;setTimeout(function(){fire();fit();},80);return;}
  if(v==="map"){cls.add("m1-map");setTimeout(function(){fire();fit();},80);return;}
  if(v==="chart"){cls.add("m1-chart");setTimeout(sizeChart,40);setTimeout(sizeChart,300);return;}
  if(v==="gear"){cls.add("m1-gear");var g=$("gearp"),gb=$("gearbtn");if(g&&g.style.display!=="block"&&gb)gb.click();return;}
  cls.add("m1-dane");
  var db=document.querySelector('#viewseg button[data-v="dane"]');if(db)db.click();
  var dn=$("dane");if(dn)dn.scrollTop=0;
  if(v==="ai")setTimeout(function(){openSec("an");},120);
  if(v==="zk")setTimeout(function(){openSec("zk");},120);
}

(function wait(n){if(build())return;if(n<60)setTimeout(function(){wait(n+1);},100);})(0);
try{MQ.addEventListener("change",function(){location.reload();});}catch(e){}
})();
