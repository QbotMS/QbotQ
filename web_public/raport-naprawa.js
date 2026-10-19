/* raport-naprawa.js - Naprawa trasy jako zakladka Analizy trasy (sesja zakladka-1910, 19.10.2026).
   Decyzja Michala: naprawa to kolejna zakladka z paska; panel z funkcjami po lewej, praca na mapie w podkladzie
   (window._qmap). Tylko komputer. Szkic naprawy (GET/PUT/DELETE /api/routes/{id}/repair/draft) rysowany zawsze:
   naprawiony przebieg fiolet, stary szary przerywany. W zakladce: kat. 4, odcinki, "Uwzglednij kwadraty",
   zakladki promieni, warianty (karty), Przyjmij / Zostaw oryginal / Szukaj dalej, bilans, Zapisz / Odrzuc szkic.
   Zapis = POST /repair/save (nowa trasa NAPRAWA n + pelne przeliczenie, postep w panelu).
   Dok.: docs/PROJEKT_NAPRAWA_TRAS.md */
(function(){
"use strict";
var DESK=function(){return !(window.matchMedia&&window.matchMedia("(max-width:900px),(hover:none) and (pointer:coarse)").matches);};
var CAT={1:["#4f7a2a","twarda szybka"],2:["#8fb35a","dobry gravel"],3:["#c8a24a","zwykły gravel"],4:["#e8742a","trudna/wolna"],5:["#a32d2d","ryzyko/niepewne"]};
var JOB={route_base:"przebieg",route_surface:"nawierzchnia",route_poi:"zaopatrzenie i atrakcje",route_elevation:"przewyższenia",route_shade:"cień",route_surface_context:"kontekst terenu",route_surface_category:"kategorie nawierzchni"};
var VIOLET="#6d28d9";
var S=null;          /* stan dla biezacej trasy */
var draftL=[], workL=[];
function f(x){return (Math.round((x||0)*100)/100).toFixed(2).replace(".",",");}
function kt(x){return String(x).replace(".",",");}
function esc(t){return String(t==null?"":t).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function map(){return window._qmap||null;}
function root(){return document.getElementById("nap-root");}
/* id trasy z magazynu tras = wartosc listy wyboru (DATA.route.id ma inny format - "nie znaleziona", test 19.10) */
function rid(){var sel=document.getElementById("f-route");return (sel&&sel.value)?String(sel.value):null;}
function api(path,opt){return fetch("/api/routes/"+encodeURIComponent(S.orig)+path,opt).then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.detail||r.status);return j;});});}
function isOpen(){return !!(window.__mk&&window.__mk.active&&window.__mk.active()==="naprawa");}
function risky(){return (S&&S.segs||[]).filter(function(s){return s.risky;});}
function key(s){return s.km_from+"-"+s.km_to+"-"+(S.kat4?4:5);}
function ckey(s){return key(s)+"|"+(S.sq[key(s)]?1:0);}
function cand(s){var h=S.hist[ckey(s)];return h&&h.length?h[S.hidx[ckey(s)]||0]:null;}
function detFor(s){return S.det.filter(function(d){return d.km_from<=s.km_to+1e-9&&d.km_to>=s.km_from-1e-9;})[0];}
function clear(arr){arr.forEach(function(l){try{l.remove();}catch(e){}});arr.length=0;}

/* ---------- start dla trasy ---------- */
function init(id){
  clear(draftL);clear(workL);
  S={id:id,orig:id,info:null,det:[],kat4:false,segs:null,allSegs:null,cur:null,hist:{},hidx:{},pick:{},sq:{},orig_keep:{},tiles:null,newBase:0,prog:null,saving:false};
  var me=S;
  fetch("/api/routes/"+encodeURIComponent(id)+"/repair-info").then(function(r){return r.json();}).then(function(info){
    if(S!==me)return; me.info=info; if(info.is_repair)me.orig=info.parent_route_id;
    chip();
    return fetch("/api/routes/"+encodeURIComponent(me.orig)+"/repair/draft").then(function(r){return r.json();});
  }).then(function(dj){
    if(S!==me||!dj)return; me.det=dj.detours||[]; me.kat4=!!dj.kat4;
    if(me.orig===me.id){loadGeom().then(function(){drawDraft();});}
    if(isOpen())render();
  }).catch(function(){});
}
function loadGeom(){
  var me=S;
  if(me.allSegs)return Promise.resolve();
  return fetch("/api/routes/"+encodeURIComponent(me.orig)+"/surface-segments?kat4=1").then(function(r){return r.json();}).then(function(j){if(S===me)me.allSegs=j.segments||[];}).catch(function(){});
}
function loadSegs(){
  var me=S;
  me.segs=null; render();
  return fetch("/api/routes/"+encodeURIComponent(me.orig)+"/surface-segments"+(me.kat4?"?kat4=1":"")).then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.detail||r.status);return j;});})
    .then(function(j){if(S!==me)return; me.segs=j.segments||[]; me.dist=j.distance_km; me.err=null; render();
      if(!me.tiles)loadTiles();})
    .catch(function(e){if(S===me){me.err=e.message;me.segs=[];render();}});
}
function loadTiles(){
  var me=S;
  fetch("/api/routes/"+encodeURIComponent(me.orig)+"/tiles?margin=0").then(function(r){return r.json();}).then(function(d){if(S!==me)return;me.tiles=d;me.newBase=(d.counts&&d.counts.new)||0;render();}).catch(function(){});
}

/* ---------- mapa ---------- */
function drawDraft(){
  clear(draftL); var m=map(); if(!m||!S||S.orig!==S.id||!S.det.length||!S.allSegs||!window.L)return;
  /* w trakcie pracy nad odcinkiem jego stary objazd ze szkicu NIE jest rysowany (nakladal sie na nowy wariant) */
  var curS=(isOpen()&&S.cur!=null)?risky()[S.cur]:null, curD=curS?detFor(curS):null;
  var dets=S.det.filter(function(d){return d!==curD;});
  var wins=dets.map(function(d){return [d.anchor_from_km,d.anchor_to_km];});
  S.allSegs.forEach(function(s){var mid=(s.km_from+s.km_to)/2;
    if(wins.some(function(w){return mid>=w[0]&&mid<=w[1];}))draftL.push(L.polyline(s.coordinates,{color:"#6f6a63",weight:5,dashArray:"9 7",opacity:.95,interactive:false}).addTo(m));});
  dets.forEach(function(d){
    draftL.push(L.polyline(d.coordinates,{color:"#fff",weight:10,opacity:.95,interactive:false}).addTo(m));
    draftL.push(L.polyline(d.coordinates,{color:VIOLET,weight:6,opacity:1,interactive:false}).addTo(m));});
}
function freePad(){var p=document.getElementById("mk-pane"),l=p?p.getBoundingClientRect().right:0;return {paddingTopLeft:[Math.max(40,l+20),90],paddingBottomRight:[60,40],maxZoom:16};}
function drawWork(fit){
  clear(workL); var m=map(); if(!m||!isOpen()||!S||S.cur==null)return;
  var s=risky()[S.cur]; if(!s)return; var c=cand(s);
  workL.push(L.polyline(s.coordinates,{color:"#ec4899",weight:14,opacity:.25,interactive:false}).addTo(m));
  var focus=null;
  if(c&&c.variants){
    var pick=S.pick[ckey(s)]||0;
    var win=[c.anchor_from_km,c.anchor_to_km];
    (S.allSegs||[]).forEach(function(x){var mid=(x.km_from+x.km_to)/2;if(mid>=win[0]&&mid<=win[1])workL.push(L.polyline(x.coordinates,{color:"#a32d2d",weight:4,dashArray:"8 8",opacity:.95,interactive:false}).addTo(m));});
    c.variants.forEach(function(v,i){if(i!==pick)workL.push(L.polyline(v.coordinates,{color:"#8a8277",weight:3,dashArray:"2 7",opacity:.95,interactive:false}).addTo(m));});
    var v=c.variants[pick];
    workL.push(L.polyline(v.coordinates,{color:"#fff",weight:11,opacity:.95,interactive:false}).addTo(m));
    focus=L.polyline(v.coordinates,{color:VIOLET,weight:7,opacity:1,interactive:false}).addTo(m);workL.push(focus);
    [[v.coordinates[0],"A"],[v.coordinates[v.coordinates.length-1],"B"]].forEach(function(z){workL.push(L.marker(z[0],{interactive:false,icon:L.divIcon({className:"",iconSize:[24,24],iconAnchor:[12,12],
      html:'<div style="width:24px;height:24px;border-radius:50%;background:#fff;border:3px solid '+VIOLET+';color:'+VIOLET+';font:700 12px system-ui;display:flex;align-items:center;justify-content:center">'+z[1]+'</div>'})}).addTo(m));});
    (c.tiles_new_piece||[]).forEach(function(t){workL.push(L.rectangle(t.bounds,{color:"#1a7f37",weight:3,dashArray:"6 4",fill:false,interactive:false}).addTo(m));});
    ((v.tiles&&v.tiles.lost_tiles)||[]).forEach(function(t){workL.push(L.rectangle(t.bounds,{color:"#a32d2d",weight:3,fill:false,interactive:false}).addTo(m));});
  }
  if(fit){try{var b=L.latLngBounds(s.coordinates);if(focus)b.extend(focus.getBounds());m.fitBounds(b,freePad());}catch(e){}}
}

/* ---------- panel ---------- */
function bilansHTML(){
  var rs=risky(),before=0,covered=0,dec=0;
  rs.forEach(function(s){before+=s.risky_km||0;var d=detFor(s);if(d){covered+=s.risky_km||0;dec++;}else if(S.orig_keep[key(s)])dec++;});
  var add=0,dr=0,lost=0,gained=0;S.det.forEach(function(d){add+=d.delta_km||0;dr+=d.risky_km||0;lost+=(d.tiles&&d.tiles.lost)||0;gained+=(d.tiles&&d.tiles.gained)||0;});
  var after=Math.max(0,before-covered+dr);
  var sq=S.tiles?(S.newBase+" → "+(S.newBase-lost+gained)):"—";
  return '<div class="nap-bil"><div><span>Długość</span><b>'+(Math.round(((S.dist||0)+add)*10)/10).toFixed(1).replace(".",",")+' km</b><i>'+(S.det.length?((add>=0?"+":"")+f(add)+" km"):"bez zmian")+'</i></div>'
    +'<div><span>Zła nawierzchnia</span><b>'+f(before)+' → '+f(after)+' km</b><i>'+(S.kat4?"kat. 4 i 5":"tylko kat. 5")+'</i></div>'
    +'<div><span>Nowe kwadraty</span><b>'+sq+'</b><i>'+(lost?("gubi "+lost):"bez strat")+'</i></div>'
    +'<div><span>Decyzje</span><b>'+dec+' z '+rs.length+'</b><i>'+S.det.length+' w szkicu</i></div></div>';
}
function variantsHTML(s){
  var h=S.hist[ckey(s)]||[],idx=S.hidx[ckey(s)]||0,c=h[idx];
  var o='<label class="nap-sq"><input type="checkbox" id="nap-sq"'+(S.sq[key(s)]?' checked':'')+'><span id="nap-sqt">Uwzględnij kwadraty</span></label>';
  if(h.length>1)o+='<div class="nap-tabs"><span>Propozycje:</span>'+h.map(function(x,i){return '<button type="button" class="nap-tab'+(i===idx?' on':'')+'" data-t="'+i+'">promień '+kt(x.buffer_km_used==null?"?":x.buffer_km_used)+' km</button>';}).join("")+'</div>';
  if(!c||c.loading)return o+'<div class="nap-note">Liczę warianty objazdu… (1–15 s'+(S.sq[key(s)]?', z kwadratami dłużej':'')+')</div>';
  if(c.error)return o+'<div class="nap-err">'+esc(c.error)+'</div>'+actionsHTML(false);
  var nsq=(c.tiles_new_piece||[]).length;
  o=o.replace('<span id="nap-sqt">Uwzględnij kwadraty</span>','<span id="nap-sqt">Uwzględnij kwadraty'+(nsq?(' — kawałek zbiera '+nsq+' '+(nsq===1?"nowy kwadrat":"nowe kwadraty")):' — kawałek nie zbiera nowych kwadratów')+'</span>');
  o+='<div class="nap-note">Zastępowany kawałek '+f(c.replaced_km)+' km (km '+kt(c.anchor_from_km)+'–'+kt(c.anchor_to_km)+') · zła nawierzchnia teraz '+f(s.risky_km)+' km</div>';
  var pick=S.pick[ckey(s)]||0;
  c.variants.forEach(function(v,i){
    var cf=v.confidence||{},bd=cf.breakdown||[],rk=cf.risky_km,tq=v.tiles||{};
    var sq=tq.required?(tq.lost?'<b class="bad">−'+tq.lost+' z '+tq.required+' kwadr.</b>':'<b class="ok">kwadraty '+tq.kept+'/'+tq.required+'</b>'):'kwadraty bez zmian';
    o+='<button type="button" class="nap-var'+(i===pick?' on':'')+'" data-v="'+i+'"><span class="nap-vh"><b>W'+(i+1)+'</b><span>'+f(v.distance_km)+' km · '+(v.delta_km>0?"+":"")+f(v.delta_km)+' km</span>'
      +'<b class="'+((rk||0)>=0.2?"bad":"ok")+'">zła '+(rk==null?"?":f(rk))+' km</b></span>'
      +'<span class="nap-bar">'+bd.map(function(b){return '<span style="flex:'+b.pct+' 1 0;background:'+((CAT[b.category]||["#999"])[0])+'"></span>';}).join("")+'</span>'
      +'<span class="nap-vf"><span>'+bd.map(function(b){return b.pct+'% kat. '+b.category;}).join(" · ")+'</span><span>'+sq+(tq.gained?' · +'+tq.gained+' nowe':'')+'</span></span>'
      +(v.spur_km?'<span class="nap-vf"><span>jedzie tą samą drogą tam i z powrotem: '+f(v.spur_km)+' km</span></span>':'')+'</button>';
  });
  return o+actionsHTML(true,pick);
}
function actionsHTML(ok,pick){
  return '<div class="nap-act">'+(ok?'<button type="button" class="nap-b pri" id="nap-acc">Przyjmij W'+((pick||0)+1)+'</button>':'')
    +'<button type="button" class="nap-b" id="nap-keep">Zostaw oryginał</button><button type="button" class="nap-b" id="nap-fur">Szukaj dalej</button></div>';
}
/* 19.10 powod-1910: powod ryzyka odcinka (z serwera: _category_reason). Krotko na liscie, calosc po rozwinieciu. */
function whyFull(s){var r=String(s.reason||"").trim();return r||"brak opisu nawierzchni dla tego miejsca";}
function whyShort(s){if(s.reason_short)return s.reason_short;var r=whyFull(s).replace(/^Kat\.\s*\d\s*\([^)]*\)\.\s*/,"").replace(/\s*W jeździe:.*$/,"").trim();
  return r.length>170?r.slice(0,167)+"…":r;}
function render(){
  var el=root(); if(!el||!S)return;
  if(!DESK()){el.innerHTML='<p class="nap-note">Naprawa trasy jest dostępna tylko na komputerze.</p>';return;}
  if(S.info&&S.info.is_repair){
    el.innerHTML='<div class="nap-ok"><b>To jest wersja naprawiona</b> trasy „'+esc(S.info.parent_name||S.info.parent_route_id)+'” ('+S.info.detours+' '+(S.info.detours===1?"objazd":"objazdy")+').</div>'
      +'<p class="nap-note">Naprawę edytujesz na oryginale — szkic czeka tam. Po zmianach zapiszesz kolejną wersję.</p>'
      +'<a class="nap-b pri" href="/raport-trasy.html?route='+encodeURIComponent(S.info.parent_route_id)+'">Otwórz oryginał i edytuj naprawę</a>';
    return;
  }
  if(S.segs===null){el.innerHTML='<p class="nap-note">Wczytuję odcinki…</p>';if(!S.loadingSegs){S.loadingSegs=true;loadGeom();loadSegs().then(function(){S.loadingSegs=false;});}return;}
  var rs=risky(),h='';
  h+='<label class="nap-k4"><input type="checkbox" id="nap-k4"'+(S.kat4?' checked':'')+'> Napraw też kat. 4 <span>(trudna/wolna)</span></label>';
  h+=bilansHTML();
  if(S.det.length||S.prog){
    h+='<div class="nap-save"><button type="button" class="nap-b sv" id="nap-save"'+((S.saving||!S.det.length)?' disabled':'')+'>Zapisz naprawioną trasę</button>'
      +'<button type="button" class="nap-b" id="nap-drop"'+((S.saving||!S.det.length)?' disabled':'')+'>Odrzuć szkic</button></div>'
      +(S.prog?'<div class="nap-prog">'+S.prog+'</div>':'<div class="nap-note">Nowa wersja „NAPRAWA” — oryginał zostaje. Do zapisu liczby w innych zakładkach dotyczą oryginału.</div>');
  }
  if(S.err)h+='<div class="nap-err">'+esc(S.err)+'</div>';
  h+='<div class="nap-sub">Odcinki do naprawy ('+rs.length+')</div>';
  if(!rs.length)h+='<p class="nap-note">Brak odcinków do naprawy'+(S.kat4?'':' w kat. 5 — możesz włączyć kat. 4')+'.</p>';
  rs.forEach(function(s,i){
    var d=detFor(s),st='<span class="todo">do decyzji</span>';
    if(d)st='<span class="ok">przyjęty '+esc(d.name)+' ('+(d.delta_km>=0?"+":"")+f(d.delta_km)+' km'+(d.tiles&&d.tiles.lost?', −'+d.tiles.lost+' kwadr.':'')+')</span>';
    else if(S.orig_keep[key(s)])st='<span class="orig">zostaje oryginał</span>';
    var c=s.category||5,cc=cand(s),nsq=cc&&cc.tiles_new_piece?cc.tiles_new_piece.length:0;
    h+='<div class="nap-seg'+(S.cur===i?' on':'')+'"><button type="button" class="nap-sh" data-i="'+i+'"><b>#'+s.segment_no+' · km '+kt(s.km_from)+'–'+kt(s.km_to)+'</b>'
      +'<span class="nap-pill k'+(c>=5?5:4)+'">kat. '+c+' · '+esc((CAT[c]||["",""])[1])+'</span>'+(nsq?'<span class="nap-pill sq">'+nsq+' nowe kw.</span>':'')
      +'<span class="nap-why">'+esc(whyShort(s))+'</span><span class="nap-st">'+st+'</span></button>';
    if(S.cur===i)h+='<div class="nap-body"><div class="nap-whyfull"><b>Dlaczego do naprawy:</b> '+esc(whyFull(s))+'</div>'+variantsHTML(s)+'</div>';
    h+='</div>';
  });
  el.innerHTML=h;
  wire();
}
function wire(){
  var el=root(); if(!el)return;
  var k4=document.getElementById("nap-k4"); if(k4)k4.onchange=function(){S.kat4=k4.checked;S.cur=null;S.hist={};S.hidx={};persist();S.segs=null;render();};
  el.querySelectorAll(".nap-sh").forEach(function(b){b.onclick=function(){var i=+b.dataset.i;if(S.cur===i){S.cur=null;render();drawWork();drawDraft();return;}selectSeg(i);};});
  el.querySelectorAll(".nap-tab").forEach(function(b){b.onclick=function(){var s=risky()[S.cur];S.hidx[ckey(s)]=+b.dataset.t;render();drawWork(true);};});
  el.querySelectorAll(".nap-var").forEach(function(b){b.onclick=function(){var s=risky()[S.cur];S.pick[ckey(s)]=+b.dataset.v;render();drawWork(true);};});
  var sq=document.getElementById("nap-sq"); if(sq)sq.onchange=function(){var s=risky()[S.cur];S.sq[key(s)]=sq.checked;if(!(S.hist[ckey(s)]||[]).length)loadCand(s);else{render();drawWork(true);}};
  var a=document.getElementById("nap-acc"); if(a)a.onclick=accept;
  var kp=document.getElementById("nap-keep"); if(kp)kp.onclick=keepOrig;
  var fu=document.getElementById("nap-fur"); if(fu)fu.onclick=further;
  var sv=document.getElementById("nap-save"); if(sv)sv.onclick=save;
  var dr=document.getElementById("nap-drop"); if(dr)dr.onclick=drop;
}
function selectSeg(i){
  S.cur=i; var s=risky()[i]; drawDraft();
  var d0=detFor(s); if(d0&&d0.squares&&S.sq[key(s)]===undefined)S.sq[key(s)]=true;   /* jak w przyjetym objezdzie */
  if(!(S.hist[ckey(s)]||[]).length)loadCand(s); else{render();drawWork(true);drawDraft();}
}
function loadCand(s,buf){
  var k=ckey(s),me=S; if(!S.hist[k])S.hist[k]=[];
  var slot={loading:true}; S.hist[k].push(slot); S.hidx[k]=S.hist[k].length-1; render(); drawWork(true);
  var url="/segments/candidate?km_from="+s.km_from+"&km_to="+s.km_to+(S.kat4?"&kat4=1":"")+(S.sq[key(s)]?"&squares=1":"")+(buf?"&buffer_km="+buf:"");
  api(url).then(function(j){if(!j.variants||!j.variants.length)throw new Error("brak wariantów objazdu");Object.assign(slot,j,{loading:false});me.pick[k]=0;})
    .catch(function(e){Object.assign(slot,{loading:false,error:"Nie udało się wyznaczyć objazdu: "+e.message,buffer_km_used:buf||null});})
    .then(function(){if(S===me&&risky()[S.cur]===s){render();drawWork(true);drawDraft();}});
}
var saveT=null;
function persist(){var me=S;clearTimeout(saveT);saveT=setTimeout(function(){
  api("/repair/draft",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({kat4:me.kat4,detours:me.det})})
    .then(function(){if(S===me)drawDraft();}).catch(function(e){if(S===me){me.err="Błąd zapisu szkicu: "+e.message;render();}});},250);}
function accept(){
  var s=risky()[S.cur],c=cand(s); if(!c||!c.variants)return;
  var i=S.pick[ckey(s)]||0,v=c.variants[i],cf=v.confidence||{};
  S.det=S.det.filter(function(d){return !(d.anchor_from_km<c.anchor_to_km&&d.anchor_to_km>c.anchor_from_km)&&!(d.km_from<=s.km_to&&d.km_to>=s.km_from);});
  S.det.push({name:"W"+(i+1),delta_km:v.delta_km,risky_km:cf.risky_km,orig_risky_km:s.risky_km,confidence:{risky_km:cf.risky_km,breakdown:cf.breakdown},
    tiles:v.tiles?{lost:v.tiles.lost,gained:v.tiles.gained,kept:v.tiles.kept,required:v.tiles.required}:null,coordinates:v.coordinates,distance_km:v.distance_km,source:v.source,
    anchor_from_km:(v.anchor_from_km!=null?v.anchor_from_km:c.anchor_from_km),anchor_to_km:(v.anchor_to_km!=null?v.anchor_to_km:c.anchor_to_km),km_from:s.km_from,km_to:s.km_to,squares:!!S.sq[key(s)]});
  S.det.sort(function(a,b){return a.anchor_from_km-b.anchor_from_km;}); delete S.orig_keep[key(s)]; persist();
  var rs=risky(),n=-1; for(var j=S.cur+1;j<rs.length;j++){if(!detFor(rs[j])&&!S.orig_keep[key(rs[j])]){n=j;break;}}
  if(n>=0)selectSeg(n); else{S.cur=null;render();drawWork();drawDraft();}
}
function keepOrig(){var s=risky()[S.cur];S.det=S.det.filter(function(d){return !(d.km_from<=s.km_to&&d.km_to>=s.km_from);});S.orig_keep[key(s)]=1;persist();render();drawWork();drawDraft();}
function further(){var s=risky()[S.cur],h=S.hist[ckey(s)]||[],mx=0.3;h.forEach(function(x){if(x.buffer_km_used>mx)mx=x.buffer_km_used;});loadCand(s,Math.min(6,Math.round((mx+1)*10)/10));}
function save(){
  if(!S.det.length)return; var lost=S.det.reduce(function(a,d){return a+((d.tiles&&d.tiles.lost)||0);},0);
  if(!confirm("Zapisać nową wersję trasy (NAPRAWA) z "+S.det.length+" objazdami?"+(lost?" Objazdy gubią "+lost+" nowych kwadratów.":"")+" Oryginał zostaje, szkic zostaje do dalszej edycji."))return;
  var me=S; me.saving=true; me.prog="Zapisuję nową wersję…"; render();
  api("/repair/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kat4:me.kat4,detours:me.det})})
    .then(function(j){me.newId=j.route_id;me.newTitle=j.title;me.pollT0=Date.now();
      if(j.precompute_started===false){me.saving=false;me.prog='<span class="bad">Zapisano „'+esc(j.title.split(" · ").pop())+'”, ale przeliczanie nie wystartowało: '+esc(j.precompute_error||"")+'</span> <button type="button" class="nap-b" id="nap-rerun">Uruchom przeliczanie</button>';render();wireRerun(me);return;}
      me.prog="Zapisano „"+esc(j.title.split(" · ").pop())+"” ("+f(j.distance_km)+" km). Przeliczam wszystko jak dla nowej trasy…";render();poll(me,j.route_id);})
    .catch(function(e){me.saving=false;me.prog='<span class="bad">Zapis nie powiódł się: '+esc(e.message)+'</span>';render();});
}
function wireRerun(me){var b=document.getElementById("nap-rerun");if(!b)return;b.onclick=function(){
  b.disabled=true;fetch("/api/routes/"+encodeURIComponent(me.newId)+"/repair/recompute",{method:"POST"}).then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.detail||r.status);return j;});})
    .then(function(){me.saving=true;me.pollT0=Date.now();me.prog="Przeliczam nową wersję…";render();poll(me,me.newId);})
    .catch(function(e){me.prog='<span class="bad">Nie udało się uruchomić: '+esc(e.message)+'</span>';render();});};}
function poll(me,id){
  fetch("/api/routes/"+encodeURIComponent(id)+"/precompute-status").then(function(r){return r.json();}).then(function(j){
    if(S!==me)return; var jobs=j.jobs||[],ok=jobs.filter(function(x){return x.status==="complete";}).length;
    /* 19.10 przelicz-1910: proces nie zglosil startu w 40 s -> nie czekamy w nieskonczonosc */
    if(!j.state&&!ok&&Date.now()-(me.pollT0||0)>40000){me.saving=false;me.prog='<span class="bad">Przeliczanie nie wystartowało.</span> <button type="button" class="nap-b" id="nap-rerun">Uruchom przeliczanie</button>';render();wireRerun(me);return;}
    if(j.failed){me.saving=false;me.prog='<span class="bad">Przeliczanie zakończyło się błędem — szczegóły na Telegramie.</span>';render();return;}
    if(j.done&&j.state!=="running"){me.saving=false;me.prog='Gotowe: <a href="/raport-trasy.html?route='+encodeURIComponent(id)+'"><b>otwórz '+esc((me.newTitle||"").split(" · ").pop())+'</b></a> → Udostępnij → Karoo';render();return;}
    me.prog="Przeliczam nową wersję: "+ok+" z "+(jobs.length||7)+" kroków"+(j.state==="running"&&!ok?" (profil nawierzchni)":"")+"…";render();
    setTimeout(function(){poll(me,id);},4000);
  }).catch(function(){setTimeout(function(){poll(me,id);},6000);});
}
function drop(){if(!confirm("Odrzucić szkic naprawy? Zapisane wersje NAPRAWA zostają."))return;S.det=[];S.orig_keep={};persist();render();drawWork();clear(draftL);}

/* etykieta trasy NAPRAWA (plywajaca, poza ukladem strony) */
function chip(){
  var bar=document.getElementById("repair-bar"); if(!bar)return;
  if(S&&S.info&&S.info.is_repair){var i=S.info,d=(i.distance_km!=null&&i.parent_distance_km!=null)?(i.distance_km-i.parent_distance_km):null;
    bar.innerHTML='<div class="rb-ok"><b>Wersja naprawiona</b><span>z „'+esc(i.parent_name||i.parent_route_id)+'”</span><span>'+i.detours+(i.detours===1?" objazd":" objazdy")+(d!=null?' · '+(d>=0?"+":"")+f(d)+' km':'')+'</span><a href="/raport-trasy.html?route='+encodeURIComponent(i.parent_route_id)+'">oryginał</a></div>';}
  else bar.innerHTML="";
}

/* wywolania z raport-render.js */
window.QNaprawa={
  html:function(){return '<div id="nap-root"><p class="nap-note">Wczytuję…</p></div>';},
  open:function(){if(!S||S.id!==rid())init(rid());setTimeout(function(){render();drawWork(true);},0);}
};
var lastId=null,wasOpen=false;
setInterval(function(){
  var id=rid(); if(id&&id!==lastId){lastId=id;init(id);}
  var o=isOpen(); if(wasOpen&&!o){clear(workL);if(S){S.cur=null;}drawDraft();} wasOpen=o;
  if(S&&S.det.length&&S.allSegs&&map()&&(!draftL.length||!map().hasLayer(draftL[0])))drawDraft();   /* mapa pozniej / przerysowana */
},600);
})();
