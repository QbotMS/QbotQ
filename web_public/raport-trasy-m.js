/* raport-trasy-m.js - MOBILE v2 (2026-09-29): minimalistyczna Analiza trasy na telefonie.
   Wlacza sie na telefonie w pionie i w poziomie (ekran <=820px LUB dotyk i wysokosc <=500px); komputer bez zmian.
   Nie przenosi elementow raportu (raport-trasy2.js szuka ich w #report) - tylko je pozycjonuje klasami na <body>.
   Poziomy: start (mapa + liczby + lista dzialow) -> dzial na caly ekran (mapa / profil / sekcje z paska ikon)
   -> "Wiecej dzialow". Na podstronach menu i wstecz w prawym dolnym rogu; dziala gest wstecz. */
(function(){
"use strict";
var Q="(max-width:820px),(pointer:coarse) and (max-height:500px)";
var MQ=window.matchMedia(Q);
if(!MQ.matches)return;
function $(id){return document.getElementById(id);}
var rep=$("report"),VIEW="home",SEC=null,MORE=false,PREV_WINH;
var ST="env(safe-area-inset-top,0px)",SB="env(safe-area-inset-bottom,0px)",SL="env(safe-area-inset-left,0px)",SR="env(safe-area-inset-right,0px)";
var PRIMARY=["plan","pogoda","forma","strategia","zaopatrzenie","przewyzszenia","nawierzchnia"];
/* strona dla gosci (raport-gosc.html): tylko dzialy dostepne gosciom, bez menu QBota */
var G=!!window.__QBOT_GUEST;if(G)PRIMARY=["pogoda","nawierzchnia","przewyzszenia","zaopatrzenie","atrakcje"];
var CSS=[
"body.t1 #mk-rail,body.t1 #mk-hexp-btn,body.t1 .map-ctl,body.t1 .leaflet-control-zoom,body.t1 .mk-grip{display:none!important}",
"body.t1 .qnav-fab{z-index:1215!important}",
"body.t1.g-page .qhead .qh-title,body.t1.g-page #rtabs{display:none!important}",
"body.t1.g-page .qhead-row{flex-wrap:wrap!important;gap:6px 8px!important;padding:6px 12px!important;align-items:center}",
"html body.t1.g-page .qhead .qh-right{display:flex!important;flex-wrap:wrap;gap:6px;width:100%;margin:0!important}",
"body.t1.g-page .g-rsvp{display:flex;align-items:center;gap:6px;flex-wrap:wrap}",
"body.t1.g-page .g-btn{min-height:40px;font-size:15px;display:inline-flex;align-items:center}",
"body.t1.g-page .g-plan{font-size:14px}",
"body.t1.g-page #g-gpx,body.t1.g-page #g-gpx2{display:none!important}",
"body.t1:not(.t1-home) .qnav-fab{display:none!important}",
"html body.t1 .mapwrap{left:0!important;right:0!important;top:0!important;bottom:0!important}",
"#t1-fit{position:absolute;top:10px;right:10px;z-index:1000;width:44px;height:44px;border-radius:50%;border:1px solid var(--line);background:var(--card);color:var(--ink);display:flex;align-items:center;justify-content:center;padding:0;box-shadow:0 2px 10px rgba(0,0,0,.3);cursor:pointer}",
"#t1-fit svg,#t1-bar svg,.t1-row .ic svg{width:22px;height:22px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}",
"body.t1-map #t1-fit{top:calc(12px + "+ST+");right:calc(12px + "+SR+")}",
/* start */
"html body.t1-home .mapwrap{border-radius:12px;overflow:hidden;border:1px solid var(--line);z-index:1!important}",
"html body.t1-home .chartwrap{display:none!important}",
"html body.t1-home header{position:fixed!important;bottom:auto!important;max-height:none!important;overflow:visible!important;width:auto!important;min-width:0!important;max-width:none!important;border-radius:12px!important;padding:8px 12px!important;display:block!important;z-index:1160!important}",
"html body.t1-home header>*:not(.statsrow):not(.wxchip){display:none!important}",
"html body.t1-home header>.statsrow{margin-top:0!important}html body.t1-home header>.wxchip{margin-top:6px!important}",
"#t1{display:none;position:fixed;z-index:1165;bottom:0;overflow-y:auto;-webkit-overflow-scrolling:touch;padding-bottom:calc(16px + "+SB+");box-sizing:border-box}",
"body.t1-home #t1{display:block}",
"@media (orientation:landscape){html body.t1-home header>.wxchip{display:none!important}}",
".t1-row{display:flex;align-items:center;gap:12px;width:100%;min-height:54px;padding:6px 4px;border:0;border-bottom:1px solid var(--line);background:none;color:var(--ink);font:inherit;font-size:16px;text-align:left;cursor:pointer}",
".t1-row .ic{--tc:var(--ink2);width:30px;height:30px;flex:0 0 30px;border-radius:9px;display:flex;align-items:center;justify-content:center;color:var(--tc);background:color-mix(in srgb,var(--tc) 18%,transparent)}",
".t1-row .ic svg{width:18px;height:18px}",
".t1-row .tx{display:flex;flex-direction:column;min-width:0}.t1-row .sb{font-size:13px;color:var(--muted);margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
".t1-row .cn{min-width:20px;height:20px;padding:0 6px;border-radius:10px;background:#ff8f5a;color:#11151b;font-size:12px;font-weight:800;line-height:20px;text-align:center;margin-left:auto}",
".t1-row .ch{margin-left:auto;color:var(--muted);font-size:22px}.t1-row .cn+.ch{margin-left:8px}",
".t1-more{color:var(--ink2)}",
/* dolny pasek */
"#t1-bar{display:none;position:fixed;z-index:1220;right:calc(12px + "+SR+");bottom:calc(12px + "+SB+");gap:8px;flex-direction:row-reverse}",
"body.t1:not(.t1-home) #t1-bar{display:flex}",
"#t1-bar button{width:48px;height:48px;border-radius:50%;border:1px solid var(--line);background:color-mix(in srgb,var(--card) 92%,transparent);color:var(--ink);display:flex;align-items:center;justify-content:center;box-shadow:0 2px 12px rgba(0,0,0,.35);padding:0;cursor:pointer}",
/* mapa */
"body.t1-map .qhead,body.t1-map #r-topbar,html body.t1-map header,html body.t1-map .chartwrap{display:none!important}",
/* profil */
"body.t1-chart .qhead,body.t1-chart #r-topbar,html body.t1-chart header{display:none!important}",
"body.t1-chart .mapwrap,body.t1-sec .mapwrap{visibility:hidden}",
"html body.t1-chart .chartwrap{display:block!important;position:fixed!important;top:0!important;left:0!important;right:0!important;bottom:0!important;width:auto!important;margin:0!important;border-radius:0!important;border:0!important;padding:calc(10px + "+ST+") calc(10px + "+SR+") calc(80px + "+SB+") calc(10px + "+SL+")!important;overflow:auto;z-index:1150!important}",
"#t1-rot{display:none;font-size:13px;color:var(--muted);margin:0 0 8px}",
"@media (orientation:portrait){body.t1-chart #t1-rot{display:block}}",
"@media (orientation:landscape){html body.t1-chart .chartwrap{padding-right:calc(72px + "+SR+")!important;padding-bottom:calc(8px + "+SB+")!important}}",
/* sekcja */
"body.t1-sec .qhead,body.t1-sec #r-topbar,html body.t1-sec .chartwrap{display:none!important}",
"html body.t1-sec header{position:fixed!important;top:0!important;left:0!important;right:0!important;bottom:0!important;width:auto!important;min-width:0!important;max-width:none!important;max-height:none!important;overflow-y:auto!important;border-radius:0!important;border:0!important;z-index:1180!important;padding:calc(10px + "+ST+") calc(14px + "+SR+") calc(84px + "+SB+") calc(14px + "+SL+")!important;display:block!important}",
"html body.t1-sec header>.statsrow,html body.t1-sec header>.wxchip,html body.t1-sec header>.cardextra{display:none!important}",
"html body.t1-sec.t1-sec-plan header>#mk-plan{display:block!important;margin:0 0 12px!important}",
"html body.t1-sec.t1-sec-plan header>.cardextra{display:flex!important;margin:0 0 12px!important}",
"body.t1-sec #mk-pane .mk-top{padding-left:0!important;position:static}",
"body.t1-sec #mk-pane .mk-x{display:none}",
"body.t1-sec #mk-pane select,body.t1-sec #mk-pane input,body.t1-sec #mk-pane textarea,body.t1-sec #mk-plan select,body.t1-sec #mk-plan input{font-size:16px!important}"
,
"#t1-mode{display:none;position:absolute;z-index:1000;top:calc(12px + "+ST+");left:calc(12px + "+SL+");height:44px;padding:0 16px;border-radius:22px;border:1px solid var(--line);background:var(--card);color:var(--ink);font:inherit;font-size:15px;font-weight:600;align-items:center;gap:8px;box-shadow:0 2px 10px rgba(0,0,0,.3);cursor:pointer}",
"body.t1-map #t1-mode{display:flex}",
"#t1-modep{display:none;position:absolute;z-index:1001;top:calc(62px + "+ST+");left:calc(12px + "+SL+");width:min(310px,calc(100% - 24px));max-height:calc(100% - 150px);overflow-y:auto;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:14px;padding:8px;box-shadow:0 6px 24px rgba(0,0,0,.4);box-sizing:border-box}",
"body.t1-map.t1-modeopen #t1-modep{display:block}",
"#t1-modep .mo{display:flex;align-items:center;gap:10px;width:100%;min-height:46px;padding:0 10px;border:1px solid transparent;border-radius:10px;background:none;color:var(--ink);font:inherit;font-size:16px;text-align:left;cursor:pointer}",
"#t1-modep .mo.on{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 14%,transparent);font-weight:600}",
"#t1-modep .mo .dot{width:10px;height:10px;border-radius:50%;border:2px solid var(--muted);flex:0 0 10px}#t1-modep .mo.on .dot{border-color:var(--accent);background:var(--accent)}",
"#t1-modep .lg{border-top:1px solid var(--line);margin-top:6px;padding:8px 6px 2px}",
"#t1-modep .lg-h{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:6px}",
"#t1-modep .li{display:flex;align-items:center;gap:10px;font-size:14px;margin:5px 0}#t1-modep .li i{flex:0 0 26px;height:6px;border-radius:3px}",
"#t1-modep .nt,#t1-legp .nt{font-size:12.5px;color:var(--muted);margin-top:6px;line-height:1.4}",
"#t1-leg{display:none;position:absolute;z-index:1000;left:calc(12px + "+SL+");bottom:calc(12px + "+SB+");height:44px;padding:0 16px;border-radius:22px;border:1px solid var(--line);background:var(--card);color:var(--ink);font:inherit;font-size:15px;font-weight:600;align-items:center;gap:8px;box-shadow:0 2px 10px rgba(0,0,0,.3);cursor:pointer}",
"body.t1-map #t1-leg{display:flex}",
"#t1-legp{display:none;position:absolute;z-index:1001;left:calc(12px + "+SL+");bottom:calc(64px + "+SB+");width:min(300px,calc(100% - 24px));max-height:calc(100% - 150px);overflow-y:auto;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:14px;padding:10px 12px;box-shadow:0 6px 24px rgba(0,0,0,.4);box-sizing:border-box}",
"body.t1-map.t1-legopen #t1-legp{display:block}",
"#t1-legp .lg-h{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:6px}",
"#t1-legp .li{display:flex;align-items:center;gap:10px;font-size:14px;margin:5px 0}#t1-legp .li i{flex:0 0 26px;height:6px;border-radius:3px}",
"#t1-legp .li svg{flex:0 0 26px;height:18px}",
".t1-warr{background:none;border:0}.t1-warr svg{display:block;filter:drop-shadow(0 0 1.5px rgba(0,0,0,.8))}",
".t1-trv{background:none;border:0}.t1-trv svg{display:block;filter:drop-shadow(0 0 1px rgba(0,0,0,.6))}",
".t1-se{background:none;border:0}.t1-se span{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font:800 11px/1 -apple-system,system-ui,sans-serif;letter-spacing:.04em;padding:4px 7px;border-radius:9px;color:#fff;white-space:nowrap;border:1.5px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.55)}",
].join("\n");

var ICO={menu:'<svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16"/></svg>',
 back:'<svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg>',
 fit:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/><circle cx="12" cy="12" r="8"/></svg>',
 map:'<svg viewBox="0 0 24 24"><path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14"/></svg>',
 chart:'<svg viewBox="0 0 24 24"><path d="M3 18l5-7 4 4 4-8 5 11"/></svg>',
 more:'<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>',
 gpx:'<svg viewBox="0 0 24 24"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>'};

function isLand(){return window.innerWidth>window.innerHeight;}
function hd(){return rep&&rep.querySelector("header");}
function mw(){return document.querySelector(".mapwrap");}
function setI(el,p,v){if(el)el.style.setProperty(p,v,"important");}
function clrI(el){if(!el)return;["top","left","right","bottom","width","height","min-height"].forEach(function(p){el.style.removeProperty(p);});}
function inval(){try{if(window._qmap)window._qmap.invalidateSize();}catch(e){}}
function fitMine(){var m=window._qmap;if(!m||!window.L)return;var b=null;
  try{m.eachLayer(function(l){if(l instanceof L.Polyline&&!(l instanceof L.Polygon)&&l.getBounds){var lb=l.getBounds();if(lb&&lb.isValid()){b=b?b.extend(lb):L.latLngBounds(lb.getSouthWest(),lb.getNorthEast());}}});
    if(b)m.fitBounds(b,{padding:[18,18]});}catch(e){}}
function tabs(){return [].slice.call(document.querySelectorAll("#mk-rail .mk-tab"));}
function tabInfo(t){var lb=t.querySelector(".lb"),cn=t.querySelector(".mk-cnt"),ic=t.querySelector(".ic");
  var name=(lb?lb.textContent:t.textContent).trim();
  return {id:t.getAttribute("data-id"),name:name,cnt:cn?cn.textContent.trim():"",icon:ic?ic.innerHTML.replace(/<span class="mk-cnt"[^<]*<\/span>/,""):"",tc:getComputedStyle(t).getPropertyValue("--tc")};}
function row(attr,icon,tc,name,sub,cnt,extra){return '<button type="button" class="t1-row'+(extra||"")+'" '+attr+'><span class="ic"'+(tc?' style="--tc:'+tc+'"':'')+'>'+icon+'</span><span class="tx"><span>'+name+'</span>'+(sub?'<span class="sb">'+sub+'</span>':'')+'</span>'+(cnt?'<span class="cn">'+cnt+'</span>':'')+'<span class="ch">\u203a</span></button>';}
function planSub(){var d=$("mkp-d"),s=$("mkp-stv");var a=[];if(d&&d.value){var p=d.value.split("-");a.push(p[2]+"."+p[1]);}if(s&&s.textContent.trim())a.push("start "+s.textContent.trim());return a.join(" \u00b7 ");}

function renderList(){
  var box=$("t1");if(!box)return;
  var ts=tabs().map(tabInfo),by={};ts.forEach(function(t){by[t.id]=t;});
  var h=row('data-v="map"',ICO.map,"#7fb0e0","Mapa","ca\u0142a trasa na ekranie")+row('data-v="chart"',ICO.chart,"#9aa0a6","Profil i pogoda","najlepiej w poziomie");
  PRIMARY.forEach(function(id){var t=by[id];if(t)h+=row('data-sec="'+id+'"',t.icon,t.tc,t.name,id==="plan"?planSub():"",t.cnt);});
  var rest=ts.filter(function(t){return PRIMARY.indexOf(t.id)<0;});
  if(rest.length){
    h+=row('data-v="more"',ICO.more,"",MORE?"Mniej dzia\u0142\u00f3w":"Wi\u0119cej dzia\u0142\u00f3w",MORE?"":rest.map(function(t){return t.name;}).join(", "),"", " t1-more");
    if(MORE)rest.forEach(function(t){h+=row('data-sec="'+t.id+'"',t.icon,t.tc,t.name,"",t.cnt);});
  }
  if(G&&$("g-gpx")){h+=row('data-v="gpx"',ICO.gpx,"#7fb0e0","Pobierz GPX","do nawigacji / licznika")+row('data-v="gpx2"',ICO.gpx,"#7fb0e0","GPX z punktami (POI)","sklepy, woda, atrakcje");}
  if(box.__h!==h){box.innerHTML=h;box.__h=h;}
}

function layout(){
  if(VIEW!=="home")return;
  var H=hd(),M=mw(),T=$("t1");if(!H||!M||!T)return;
  var tb=$("r-topbar"),qh=document.querySelector(".qhead");
  var top=Math.round((tb&&tb.offsetParent!==null?tb:qh).getBoundingClientRect().bottom)+8;
  var W=window.innerWidth,Hh=window.innerHeight;setI(M,"min-height","0");
  if(isLand()){
    var half=Math.round(W/2);
    setI(M,"top",top+"px");setI(M,"left","calc(12px + "+SL+")");setI(M,"right",(W-half+6)+"px");setI(M,"bottom","calc(12px + "+SB+")");setI(M,"height","auto");
    setI(H,"top",top+"px");setI(H,"left",(half+6)+"px");setI(H,"right","calc(12px + "+SR+")");
    var hb=Math.round(H.getBoundingClientRect().bottom);
    setI(T,"top",(hb+4)+"px");setI(T,"left",(half+6)+"px");setI(T,"right","calc(12px + "+SR+")");
  }else{
    var mh=Math.max(130,Math.min(220,Math.round((Hh-top)*0.32)));
    setI(M,"top",top+"px");setI(M,"left","12px");setI(M,"right","12px");setI(M,"bottom","auto");setI(M,"height",mh+"px");
    setI(H,"top",(top+mh+8)+"px");setI(H,"left","12px");setI(H,"right","12px");
    var hb2=Math.round(H.getBoundingClientRect().bottom);
    setI(T,"top",(hb2+4)+"px");setI(T,"left","12px");setI(T,"right","12px");
  }
  inval();
}
function ensureFit(){ensureMode();var M=mw();if(M&&!M.querySelector("#t1-fit")){var old=$("t1-fit");if(old)old.remove();
  var b=document.createElement("button");b.type="button";b.id="t1-fit";b.setAttribute("aria-label","Wy\u015brodkuj tras\u0119");b.innerHTML=ICO.fit;
  b.addEventListener("click",function(e){e.stopPropagation();fitMine();});M.appendChild(b);}}

/* --- tryb kolorowania trasy na pelnej mapie (nawierzchnia / wiatr / profil) + legenda --- */
var DATA=null,GEO=null,MODE="surf",OV=null,GEO_P=null;
var MODES=[["surf","Nawierzchnia"],["wind","Pogoda / wiatr"],["grade","Profil (nachylenie)"]];
var LEG={surf:[["#1565c0","twarda, szybka / asfalt"],["#2e7d32","dobry gravel / szuter"],["#8bc34a","zwyk\u0142y gravel / grunt"],["#e07b1a","trudna / wolna"],["#c2452f","ryzyko / niepewne"]],
 wind:[["#9ecae1","s\u0142aby, poni\u017cej 2 m/s"],["#4292c6","2\u20134 m/s"],["#e0a72e","4\u20136 m/s"],["#e07b1a","6\u20138 m/s"],["#c2452f","powy\u017cej 8 m/s"]],
 grade:[["#3f6f9a","zjazd (poni\u017cej \u22124%)"],["#9aa0a6","p\u0142asko (\u22124\u20132%)"],["#e0c341","2\u20134%"],["#e07b1a","4\u20136%"],["#c2452f","6\u20139%"],["#7a1f1f","powy\u017cej 9%"]]};
var NOTE={surf:"Kolor wed\u0142ug kategorii nawierzchni z analizy trasy.",wind:"Kolor = si\u0142a wiatru, strza\u0142ki = kierunek; prognoza na planowan\u0105 godzin\u0119 przejazdu danego odcinka.",grade:"Nachylenie liczone na odcinkach ok. 200 m."};
function modeName(m){for(var i=0;i<MODES.length;i++)if(MODES[i][0]===m)return MODES[i][1];return m;}
function ensureMode(){var M=mw();if(!M||M.querySelector("#t1-mode"))return;
  var o=$("t1-mode");if(o)o.remove();var op=$("t1-modep");if(op)op.remove();
  var b=document.createElement("button");b.type="button";b.id="t1-mode";b.innerHTML='<span id="t1-mode-l">'+modeName(MODE)+'</span><span>\u25be</span>';
  b.addEventListener("click",function(e){e.stopPropagation();document.body.classList.remove("t1-legopen");document.body.classList.toggle("t1-modeopen");});
  var p=document.createElement("div");p.id="t1-modep";p.addEventListener("click",function(e){e.stopPropagation();var t=e.target.closest&&e.target.closest(".mo");if(t)applyMode(t.getAttribute("data-m"));});
  var lb=document.createElement("button");lb.type="button";lb.id="t1-leg";lb.innerHTML='Legenda <span>\u25b4</span>';
  lb.addEventListener("click",function(e){e.stopPropagation();document.body.classList.remove("t1-modeopen");document.body.classList.toggle("t1-legopen");});
  var lp=document.createElement("div");lp.id="t1-legp";lp.addEventListener("click",function(e){e.stopPropagation();});
  var ol=$("t1-leg");if(ol)ol.remove();var olp=$("t1-legp");if(olp)olp.remove();
  M.appendChild(b);M.appendChild(p);M.appendChild(lb);M.appendChild(lp);renderModeP();}
function renderModeP(){var p=$("t1-modep");if(!p)return;
  var h=MODES.map(function(m){return '<button type="button" class="mo'+(m[0]===MODE?' on':'')+'" data-m="'+m[0]+'"><span class="dot"></span>'+m[1]+'</button>';}).join("");
  p.innerHTML=h;var l=$("t1-mode-l");if(l)l.textContent=modeName(MODE);renderLeg();}
function arrSvg(f){return '<svg viewBox="0 0 20 20" width="18" height="18"><path d="M10 2 L16 16 L10 12.5 L4 16 Z" fill="'+f+'" stroke="#ffffff" stroke-width="1.5" stroke-linejoin="round"/></svg>';}
var ARR_SVG=arrSvg("#9aa0a6");
var CHEV_SVG='<svg viewBox="0 0 20 20" width="16" height="16"><path d="M6 4 L14 10 L6 16" fill="none" stroke="#ffffff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 4 L14 10 L6 16" fill="none" stroke="#1c2024" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
var W_TAIL="#3f9a4d",W_SIDE="#9aa0a6",W_HEAD="#c2452f";
function renderLeg(){var p=$("t1-legp");if(!p)return;
  var h='<div class="lg-h">Legenda \u00b7 '+modeName(MODE)+'</div>'+LEG[MODE].map(function(x){return '<div class="li"><i style="background:'+x[0]+'"></i>'+x[1]+'</div>';}).join("");
  if(MODE==="wind")h+='<div class="lg-h" style="margin-top:10px">Strza\u0142ki: kierunek wiatru</div>'+
    '<div class="li">'+arrSvg(W_TAIL)+'w plecy lub boczny w plecy</div>'+
    '<div class="li">'+arrSvg(W_SIDE)+'boczny</div>'+
    '<div class="li">'+arrSvg(W_HEAD)+'czo\u0142owy (w twarz)</div>';
  h+='<div class="lg-h" style="margin-top:10px">Trasa</div><div class="li">'+CHEV_SVG+'kierunek jazdy</div>'+
    '<div class="li"><i style="background:#2e7d32;height:14px;border-radius:7px"></i>START</div><div class="li"><i style="background:#1c2024;height:14px;border-radius:7px;border:1px solid #fff"></i>META</div>';
  p.innerHTML=h+'<div class="nt">'+NOTE[MODE]+'</div>';}
function hav(a,b){var R=6371,d2=Math.PI/180,dLa=(b[0]-a[0])*d2,dLo=(b[1]-a[1])*d2,la1=a[0]*d2,la2=b[0]*d2;var x=Math.pow(Math.sin(dLa/2),2)+Math.cos(la1)*Math.cos(la2)*Math.pow(Math.sin(dLo/2),2);return 2*R*Math.asin(Math.sqrt(x));}
function getGeo(cb){if(GEO)return cb(GEO);if(!DATA||!DATA.route)return;
  if(!GEO_P){GEO_P=(DATA.route.__geometry?Promise.resolve({coordinates:DATA.route.__geometry}):fetch("/api/routes/"+encodeURIComponent(DATA.route.id)+"/geometry").then(function(r){return r.ok?r.json():Promise.reject(r.status);}))
    .then(function(d){var co=d.coordinates||[];if(!co.length)throw "brak";var cum=[0];for(var i=1;i<co.length;i++)cum[i]=cum[i-1]+hav(co[i-1],co[i]);
      var kmT=(DATA.chart&&DATA.chart.km_total)||cum[cum.length-1]||1,sc=kmT/(cum[cum.length-1]||1);for(var j=0;j<cum.length;j++)cum[j]*=sc;GEO={co:co,cum:cum};return GEO;});}
  GEO_P.then(cb).catch(function(){});}
function smooth(a,w){var n=a.length,o=new Array(n),hh=(w-1)>>1;for(var q=0;q<n;q++){var s=0,c=0;for(var r=q-hh;r<=q+hh;r++){if(r>=0&&r<n){s+=a[r];c++;}}o[q]=s/c;}return o;}
function nearest(arr,km){var lo=0,hi=arr.length-1;while(hi-lo>1){var m=(lo+hi)>>1;if(arr[m][0]<km)lo=m;else hi=m;}return (Math.abs(arr[lo][0]-km)<=Math.abs(arr[hi][0]-km))?lo:hi;}
function classifier(m){var C=(DATA&&DATA.chart)||{};
  if(m==="wind"){var WD=C.wind||[];if(!WD.length)return null;var AL=smooth(WD.map(function(p){return p[1];}),5),CR=smooth(WD.map(function(p){return p[2];}),5);
    return function(km){var i=nearest(WD,km),v=Math.hypot(AL[i]||0,CR[i]||0);if(v<2)return "#9ecae1";if(v<4)return "#4292c6";if(v<6)return "#e0a72e";if(v<8)return "#e07b1a";return "#c2452f";};}
  if(m==="grade"){var E=C.ele||[];if(E.length<2)return null;
    var eleAt=function(km){if(km<=E[0][0])return E[0][1];if(km>=E[E.length-1][0])return E[E.length-1][1];var i=nearest(E,km);var j=(E[i][0]<km)?i+1:i-1;if(j<0||j>=E.length)return E[i][1];var a=E[Math.min(i,j)],b=E[Math.max(i,j)];return a[1]+(b[1]-a[1])*((km-a[0])/((b[0]-a[0])||1));};
    return function(km){var g=(eleAt(km+0.1)-eleAt(km-0.1))/2;if(g<-4)return "#3f6f9a";if(g<2)return "#9aa0a6";if(g<4)return "#e0c341";if(g<6)return "#e07b1a";if(g<9)return "#c2452f";return "#7a1f1f";};}
  return null;}
function applyMode(m){MODE=m||"surf";renderModeP();document.body.classList.remove("t1-modeopen");
  var map=window._qmap;if(OV&&map){try{map.removeLayer(OV);}catch(e){}}OV=null;
  if(MODE==="surf"||!map||!window.L)return;
  var want=MODE;getGeo(function(g){if(want!==MODE)return;var f=classifier(MODE);if(!f)return;var co=g.co,cum=g.cum,grp=L.layerGroup(),cur=null,pts=[];
    function flush(){if(pts.length>1){L.polyline(pts,{color:"#ffffff",weight:7,opacity:1,lineCap:"round",lineJoin:"round",interactive:false}).addTo(grp);L.polyline(pts,{color:cur,weight:4.5,opacity:1,lineCap:"round",lineJoin:"round",interactive:false}).addTo(grp);}}
    for(var i=0;i<co.length;i++){var c=f(cum[i]);if(c!==cur){if(cur!==null){pts.push(co[i]);flush();}cur=c;pts=[co[i]];}else pts.push(co[i]);}
    flush();if(MODE==="wind")windArrows(grp,co,cum);if(OV&&map){try{map.removeLayer(OV);}catch(e){}}OV=grp.addTo(map);});}
/* kierunek jazdy: szewrony wzdluz trasy + START / META (zawsze, niezaleznie od trybu) */
var TRV=null;
function drawTravel(){getGeo(function(g){var map=window._qmap;if(!map||!window.L)return;if(TRV){try{map.removeLayer(TRV);}catch(e){}}
  var co=g.co,cum=g.cum,kmT=cum[cum.length-1]||1,step=Math.max(2,Math.min(8,kmT/25)),grp=L.layerGroup(),j=0;
  for(var km=step;km<kmT-step/2;km+=step){while(j<cum.length-1&&cum[j]<km)j++;var k=j;while(k<cum.length-1&&cum[k]<cum[j]+0.12)k++;var i0=Math.max(0,j-1);if(k===i0)continue;
    var deg=Math.round(brg(co[i0],co[k])-90);
    L.marker(co[j],{interactive:false,keyboard:false,zIndexOffset:-100,icon:L.divIcon({className:"t1-trv",iconSize:[16,16],iconAnchor:[8,8],html:'<div style="transform:rotate('+deg+'deg)">'+CHEV_SVG+'</div>'})}).addTo(grp);}
  var a=co[0],b=co[co.length-1],loop=hav(a,b)<0.3;
  function lab(ll,t,bg){L.marker(ll,{interactive:false,keyboard:false,zIndexOffset:500,icon:L.divIcon({className:"t1-se",iconSize:[0,0],iconAnchor:[0,0],html:'<span style="background:'+bg+'">'+t+'</span>'})}).addTo(grp);}
  if(loop)lab(a,"START / META","#2e7d32");else{lab(b,"META","#1c2024");lab(a,"START","#2e7d32");}
  TRV=grp.addTo(map);});}
var DIR16={N:0,NNE:22.5,NE:45,ENE:67.5,E:90,ESE:112.5,SE:135,SSE:157.5,S:180,SSW:202.5,SW:225,WSW:247.5,W:270,WNW:292.5,NW:315,NNW:337.5};
function brg(a,b){var d2=Math.PI/180,la1=a[0]*d2,la2=b[0]*d2,dl=(b[1]-a[1])*d2;var y=Math.sin(dl)*Math.cos(la2),x=Math.cos(la1)*Math.sin(la2)-Math.sin(la1)*Math.cos(la2)*Math.cos(dl);return (Math.atan2(y,x)/d2+360)%360;}
function windArrows(grp,co,cum){
  var WD=(DATA&&DATA.chart&&DATA.chart.wind)||[];if(WD.length<2||co.length<3)return;
  var AL=smooth(WD.map(function(p){return p[1];}),5),CR=smooth(WD.map(function(p){return p[2];}),5);
  var kmT=cum[cum.length-1]||1,step=Math.max(1,Math.min(5,kmT/40)),pts=[],j=0;
  for(var km=step/2;km<kmT;km+=step){while(j<cum.length-1&&cum[j]<km)j++;var k=j;while(k<cum.length-1&&cum[k]<cum[j]+0.1)k++;var i0=Math.max(0,j-1);
    if(k===i0)continue;var th=brg(co[i0],co[k])*Math.PI/180,w=nearest(WD,km),al=AL[w]||0,cr=CR[w]||0;if(Math.hypot(al,cr)<0.3)continue;
    pts.push({ll:co[j],ue:Math.sin(th),un:Math.cos(th),al:al,cr:cr});}
  if(!pts.length)return;
  /* znak skladowej bocznej nie jest opisany w danych - wybieramy wariant zgodny z kierunkiem wiatru z naglowka pogody,
     a gdy go brak: ten, dla ktorego kierunek wiatru jest najbardziej spojny wzdluz calej trasy */
  function dirs(sg){return pts.map(function(p){var ve=p.al*p.ue+sg*p.cr*(-p.un),vn=p.al*p.un+sg*p.cr*p.ue;return Math.atan2(ve,vn);});}
  function coh(a){var sx=0,sy=0;a.forEach(function(t){sx+=Math.sin(t);sy+=Math.cos(t);});return Math.hypot(sx,sy)/a.length;}
  var A=dirs(1),B=dirs(-1),pick=coh(A)>=coh(B)?A:B;
  var wh=DATA.weather_head||{},from=DIR16[String(wh.wind_dir||"").toUpperCase()];
  if(from!=null){var to=(from+180)*Math.PI/180;function dev(a){var s=0;a.forEach(function(t){s+=1-Math.cos(t-to);});return s;}pick=dev(A)<=dev(B)?A:B;}
  pts.forEach(function(p,n){var deg=Math.round(pick[n]*180/Math.PI);
    var th=Math.atan2(Math.abs(p.cr),Math.abs(p.al))*180/Math.PI,f=th>65?W_SIDE:(p.al>0?W_TAIL:W_HEAD);
    L.marker(p.ll,{interactive:false,keyboard:false,icon:L.divIcon({className:"t1-warr",iconSize:[18,18],iconAnchor:[9,9],html:'<div style="transform:rotate('+deg+'deg)">'+arrSvg(f)+'</div>'})}).addTo(grp);});
}
document.addEventListener("click",function(e){var lp=$("t1-legp"),lb=$("t1-leg");if(document.body.classList.contains("t1-legopen")&&!((lp&&lp.contains(e.target))||(lb&&lb.contains(e.target))))document.body.classList.remove("t1-legopen");if(!document.body.classList.contains("t1-modeopen"))return;var p=$("t1-modep"),b=$("t1-mode");if((p&&p.contains(e.target))||(b&&b.contains(e.target)))return;document.body.classList.remove("t1-modeopen");},true);
(function hook(n){var o=window.renderReport;if(typeof o!=="function"){if(n<50)setTimeout(function(){hook(n+1);},100);return;}if(o.__t1)return;
  var w=function(d){DATA=d;GEO=null;GEO_P=null;OV=null;TRV=null;var r=o.apply(this,arguments);setTimeout(function(){ensureMode();drawTravel();if(MODE!=="surf")applyMode(MODE);},1500);return r;};w.__t1=1;window.renderReport=w;})(0);

function sizeChart(){
  var svg=$("chart"),cw=document.querySelector(".chartwrap");if(!svg||!cw)return;
  var w=svg.getBoundingClientRect().width||1000,cs=getComputedStyle(cw);
  var avail=cw.clientHeight-(svg.getBoundingClientRect().top-cw.getBoundingClientRect().top)-(parseFloat(cs.paddingBottom)||0)-8;
  var want=Math.round(Math.max(60,Math.min(360,avail*1100/w-55)));
  window.__QBOT_CHART_WINH=want;try{if(window.__QBOT_RENDER_CHART)window.__QBOT_RENDER_CHART();}catch(e){}
}
/* strona gosci otwiera pierwsza sekcje sama - na starcie telefonu ma byc zamknieta */
function closePane(){if(!document.body.classList.contains("mk-open"))return;var x=document.querySelector("#mk-pane .mk-x");if(x)x.click();else{var on=document.querySelector(".mk-tab.on");if(on)on.click();}}
function leave(){
  var c=document.body.classList;
  if(VIEW==="chart"){window.__QBOT_CHART_WINH=PREV_WINH;try{if(window.__QBOT_RENDER_CHART)window.__QBOT_RENDER_CHART();}catch(e){}}
  if(VIEW==="sec"){var x=document.querySelector("#mk-pane .mk-x");if(document.body.classList.contains("mk-open")){if(x)x.click();else{var on=document.querySelector(".mk-tab.on");if(on)on.click();}}}
  if(VIEW==="home"){clrI(hd());clrI(mw());}
  c.remove("qnav-open");c.remove("t1-modeopen");c.remove("t1-legopen");
  ["t1-home","t1-map","t1-chart","t1-sec","t1-sec-plan"].forEach(function(k){c.remove(k);});
}
function go(v,push,sec){
  if(push&&v===VIEW&&sec===SEC)return;
  leave();VIEW=v;SEC=sec||null;var c=document.body.classList;
  if(push&&v!=="home"){try{history.pushState({t1:v,sec:SEC},"");}catch(e){}}
  if(v==="home"){c.add("t1-home");closePane();renderList();var T=$("t1");if(T)T.scrollTop=0;setTimeout(function(){layout();fitMine();},60);setTimeout(fitMine,700);return;}
  if(v==="map"){c.add("t1-map");setTimeout(function(){inval();fitMine();},80);return;}
  if(v==="chart"){c.add("t1-chart");PREV_WINH=window.__QBOT_CHART_WINH;setTimeout(sizeChart,60);setTimeout(sizeChart,350);return;}
  c.add("t1-sec");if(sec==="plan")c.add("t1-sec-plan");
  var t=document.querySelector('.mk-tab[data-id="'+sec+'"]');
  if(t&&!(t.classList.contains("on")&&c.contains("mk-open")))t.click();
  var H=hd();if(H)H.scrollTop=0;
}

function build(){
  if($("t1"))return true;
  if(!rep||!hd()||!mw()||!tabs().length)return false;
  var st=document.createElement("style");st.id="t1-css";st.textContent=CSS;document.head.appendChild(st);
  var T=document.createElement("div");T.id="t1";document.body.appendChild(T);
  T.addEventListener("click",function(e){var r=e.target.closest&&e.target.closest(".t1-row");if(!r)return;
    var v=r.getAttribute("data-v"),s=r.getAttribute("data-sec");
    if(v==="more"){MORE=!MORE;renderList();return;}
    if(v==="gpx"||v==="gpx2"){var a=$(v==="gpx"?"g-gpx":"g-gpx2");if(a)a.click();return;}
    if(v)go(v,true);else if(s)go("sec",true,s);});
  var bar=document.createElement("div");bar.id="t1-bar";
  bar.innerHTML='<button type="button" id="t1-back" aria-label="Wstecz">'+ICO.back+'</button>'+(G?'':'<button type="button" id="t1-menu" aria-label="Menu">'+ICO.menu+'</button>');
  document.body.appendChild(bar);
  $("t1-back").addEventListener("click",function(){if(history.state&&history.state.t1)history.back();else go("home",false);});
  if($("t1-menu"))$("t1-menu").addEventListener("click",function(){var f=document.querySelector(".qnav-fab");if(f)f.click();else document.body.classList.toggle("qnav-open");});
  var cw=document.querySelector(".chartwrap");
  if(cw&&!$("t1-rot")){var r=document.createElement("div");r.id="t1-rot";r.textContent="Obr\u00f3\u0107 telefon poziomo, \u017ceby zobaczy\u0107 wi\u0119cej szczeg\u00f3\u0142\u00f3w.";cw.insertBefore(r,cw.firstChild);}
  window.addEventListener("popstate",function(e){var s=e.state||{};go(s.t1||"home",false,s.sec);});
  window.addEventListener("resize",function(){if(VIEW==="home")setTimeout(layout,50);else if(VIEW==="map")inval();});
  try{window.matchMedia("(orientation:landscape)").addEventListener("change",function(){setTimeout(function(){if(VIEW==="chart")sizeChart();else if(VIEW==="home"){layout();fitMine();}else if(VIEW==="map"){inval();fitMine();}},300);});}catch(e){}
  try{if(window.ResizeObserver)new ResizeObserver(function(){if(VIEW==="home")layout();}).observe(hd());}catch(e){}
  document.body.classList.add("t1");
  ensureFit();go("home",false);
  return true;
}
/* raport renderuje sie po wybraniu trasy (i ponownie po zmianie) - odswiez szkielet */
function refresh(){
  if(!build())return;
  ensureFit();
  var cw=document.querySelector(".chartwrap");
  if(cw&&!cw.querySelector("#t1-rot")){var r=document.createElement("div");r.id="t1-rot";r.textContent="Obr\u00f3\u0107 telefon poziomo, \u017ceby zobaczy\u0107 wi\u0119cej szczeg\u00f3\u0142\u00f3w.";cw.insertBefore(r,cw.firstChild);}
  try{if(window.ResizeObserver&&hd()&&!hd().__t1ro){hd().__t1ro=1;new ResizeObserver(function(){if(VIEW==="home")layout();}).observe(hd());}}catch(e){}
  if(VIEW==="home"){closePane();renderList();layout();setTimeout(fitMine,300);}
}
if(rep){new MutationObserver(function(){setTimeout(refresh,400);setTimeout(refresh,1500);}).observe(rep,{childList:true});}
(function wait(n){refresh();if(!$("t1")&&n<150)setTimeout(function(){wait(n+1);},200);})(0);
setInterval(function(){if(VIEW==="home"&&$("t1"))renderList();},5000);
try{MQ.addEventListener("change",function(){location.reload();});}catch(e){}
})();
