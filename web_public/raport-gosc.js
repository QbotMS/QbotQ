/* raport-gosc.js - strona goscia jazdy (/g/<token>). Dane WYLACZNIE z /api/guest/<token> (biala lista, bez AI).
   Przeklada je na format widoku raport-render.js; tryb goscia = window.__QBOT_GUEST (ustawiany w <head>). */
(function(){
"use strict";
var tok=(location.pathname.split("/g/")[1]||"").split("/")[0].split("?")[0];
var API="/api/guest/"+encodeURIComponent(tok);
var DNI=["niedziela","poniedzia\u0142ek","wtorek","\u015broda","czwartek","pi\u0105tek","sobota"];
var MIES=["stycznia","lutego","marca","kwietnia","maja","czerwca","lipca","sierpnia","wrze\u015bnia","pa\u017adziernika","listopada","grudnia"];
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function fmtDate(iso){var d=new Date(iso+"T12:00:00");return DNI[d.getDay()]+", "+d.getDate()+" "+MIES[d.getMonth()];}
function toData(g){
  var p=g.plan||{},ms=p.miejsce_startu||{};
  var st={date:p.data,time:p.start};Object.keys(ms).forEach(function(k){st[k]=ms[k];});
  var tm={};Object.keys(p.czas||{}).forEach(function(k){tm[k]=p.czas[k];});
  var pw=g.pogoda||{},nw=g.nawierzchnia||{},pj=g.podjazdy||{};
  return {
    route:{id:"gosc",name:(g.trasa||{}).nazwa,distance_km:(g.trasa||{}).dystans_km,ascent_m:(g.trasa||{}).przewyzszenie_m,source:"",version_modified:"",__geometry:(g.trasa||{}).geometria||[]},
    start:st,time:tm,chart:g.wykres||{},weather_head:pw.naglowek||null,alerts:g.alerty||[],
    details:{
      weather:{windows:pw.okna||[],peak:pw.szczyt||null,slonce:pw.slonce||null,ogolne:pw.ogolne||[],etapy:pw.etapy||[],caveats:pw.uwagi||[]},
      surface:{total_km:nw.total_km,by_cat:nw.udzial||[],risk:(nw.ryzyka||[]).map(function(r){return {a:r.a,b:r.b,km:r.km,k:r.k,comment:r.komentarz||""};})},
      climbs:{ascent_m:pj.suma_w_gore_m,count:(pj.lista||[]).length,list:pj.lista||[]},
      poi:{resupply:(g.zaopatrzenie||[]).map(function(x){return {area:x.rejon,q_km:x.km,picks:x.punkty||[],total:(x.punkty||[]).length};}),
           attractions:{enabled:true,items:g.atrakcje||[],total:(g.atrakcje||[]).length}},
      forma:{},strategia:null,sprzet:null
    }
  };
}
function paintRsvp(v){
  var y=document.getElementById("g-yes"),n=document.getElementById("g-no"),q=document.getElementById("g-rsvp-q");
  y.classList.toggle("on",v==="tak");n.classList.toggle("on",v==="nie");
  q.textContent=v==="tak"?"Jedziesz \u2713":v==="nie"?"Nie jedziesz":"Jedziesz?";
}
function rsvp(v){
  fetch(API+"/rsvp?status="+v,{method:"POST"}).then(function(r){return r.json();}).then(function(j){if(j&&j.ok)paintRsvp(j.rsvp);}).catch(function(){});
}
function head(g){
  var p=g.plan||{},pr=p.przerwy||{},fc=((g.pogoda||{}).prognoza_z||"");
  var parts=[fmtDate(p.data),"start "+esc(p.start)+(p.miejsce_startu&&p.miejsce_startu.miejscowosc?" \u00b7 "+esc(p.miejsce_startu.miejscowosc):"")];
  if(pr.liczba)parts.push("przerwy "+pr.liczba+" \u00d7 "+pr.min+" min");
  if(p.meta)parts.push("meta ~"+esc(p.meta));
  var fct="";try{var d=new Date(fc);fct=String(d.getHours()).padStart(2,"0")+":"+String(d.getMinutes()).padStart(2,"0");}catch(e){}
  document.getElementById("g-plan").innerHTML=parts.join(" \u00b7 ")+'<span class="g-note">plan organizatora \u2014 czasy z jego tempa'+(fct?" \u00b7 prognoza z "+fct:"")+'</span>';
  document.getElementById("g-gpx").href=API+"/gpx?pois=0";
  document.getElementById("g-gpx2").href=API+"/gpx?pois=1";
  paintRsvp((g.gosc||{}).rsvp);
  document.getElementById("g-yes").onclick=function(){rsvp("tak");};
  document.getElementById("g-no").onclick=function(){rsvp("nie");};
  document.title="Jazda "+fmtDate(p.data)+" \u2014 "+((g.trasa||{}).nazwa||"");
}
function fail(msg){
  var e=document.getElementById("g-empty");e.style.display="block";
  e.innerHTML='<div class="g-fail"><b>Nie mo\u017cna otworzy\u0107 zaproszenia</b><br>'+esc(msg)+'<br><span class="k">Popro\u015b organizatora o nowy link.</span></div>';
  var h=document.querySelector(".qh-right");if(h)h.style.display="none";
}
fetch(API,{cache:"no-store"}).then(function(r){
  if(!r.ok)return r.json().catch(function(){return {};}).then(function(j){throw new Error(j.detail||("HTTP "+r.status));});
  return r.json();
}).then(function(g){
  head(g);
  window.__mkIntroData=g.o_trasie||null;
  /* odpowiedz prosto z maila: /g/<token>?rsvp=tak|nie -> zapis + potwierdzenie, parametr usuwany z adresu */
  try{var _rv=new URLSearchParams(location.search).get("rsvp");
    if(_rv==="tak"||_rv==="nie"){rsvp(_rv);history.replaceState(null,"",location.pathname);
      var t=document.createElement("div");t.className="g-toast";t.textContent=_rv==="tak"?"Dzi\u0119ki! Zapisa\u0142em: jedziesz \u2713":"Zapisa\u0142em: tym razem nie jedziesz";
      document.body.appendChild(t);setTimeout(function(){t.classList.add("off");},4200);}}catch(e){}
  document.getElementById("g-empty").style.display="none";
  window.renderReport(toData(g),document.getElementById("report"));
  /* wysrodkuj trase PO ustabilizowaniu ukladu (panel lewy + wykres wskakuja chwile po renderze) */
  /* przywitanie: otworz "O trasie", jesli jest opis */
  if(g.o_trasie)(function op(n){if(window.__mk&&document.getElementById("mk-introsec")){window.__mk.toggle("otrasie");}else if(n<50)setTimeout(function(){op(n+1);},120);})(0);
  var tries=0;(function fit(){tries++;
    if(window.MAPX&&window.MAPX.ready&&window._qmap){
      [150,700,1600].forEach(function(ms){setTimeout(function(){try{window._qmap.invalidateSize();window.MAPX.fitAll();}catch(e){}},ms);});
    }else if(tries<60)setTimeout(fit,100);})();
}).catch(function(e){fail(e.message||String(e));});
})();
