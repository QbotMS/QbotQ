/* kalendarz2-data.js v6 — siatka v2 + PELNY edytor dnia (modal):
   wydarzenia/typy, kolory, wielodniowe, choroba, samopoczucie, przypomnienia,
   trasa dnia, wysylka raportu mailem, edycja/usuwanie. */
(function(){
"use strict";
var CUR=new Date(); var YR=CUR.getFullYear(), MO=CUR.getMonth();
var MON=["Styczeń","Luty","Marzec","Kwiecień","Maj","Czerwiec","Lipiec","Sierpień","Wrzesień","Październik","Listopad","Grudzień"];
function localISO(d){return d.getFullYear()+"-"+qPad2(d.getMonth()+1)+"-"+qPad2(d.getDate());}
var today=localISO(CUR); var selDay=today;
function startEnd(y,m){var first=new Date(y,m,1),last=new Date(y,m+1,0);var dow=(first.getDay()+6)%7;var s=new Date(y,m,1-dow);var edow=(last.getDay()+6)%7;var e=new Date(y,m,last.getDate()+(6-edow));return [localISO(s),localISO(e)];}

var calData={},ridesMap={},entryRoutes={},sched={};
var ROUTES=null,MGROUPS=null,ED=null;

var FEEL_LABEL={"-2":"fatalnie","-1":"słabo","0":"neutralnie","1":"dobrze","2":"świetnie"};
var COLORS=[["","auto"],["#3f6f9a","niebieski"],["#3f7a4d","zielony"],["#a63d3d","czerwony"],["#c77c3a","pomarańcz"],["#7a5ea8","fiolet"],["#6b7076","szary"]];
var TYPES=[["jazda","🚴 Jazda"],["event","📅 Wydarzenie"],["rest","😴 Rest day"],["urlop","🏖️ Urlop"],["delegacja","💼 Delegacja"],["illness","🤒 Choroba"],["feel","😊 Samopoczucie"],["reminder","🔔 Przypomnienie"]];
function evClass(et){return et==="jazda"?"green":et==="urlop"?"green":et==="delegacja"?"purp":et==="rest"?"gray":"blue";}
function evIcon(et){return et==="jazda"?"🚴":et==="urlop"?"🏖️":et==="delegacja"?"💼":et==="rest"?"😴":"📅";}
function evLabel(et){return et==="jazda"?"Jazda":et==="urlop"?"Urlop":et==="delegacja"?"Delegacja":et==="rest"?"Rest day":"Wydarzenie";}

async function render(){
  var se=startEnd(YR,MO);
  var cal,rides;
  /* 2026-09-28: wykonane treningi z /api/calendar (training_sessions: WSZYSTKIE rodzaje, caly wyswietlany zakres, XSS ModelQ) - wczesniej /api/rides/ready = tylko 50 ostatnich jazd */
  try{ cal=await qJSON("/api/calendar?start="+se[0]+"&end="+se[1]); rides={rides:[]}; Object.keys(cal.rides||{}).forEach(function(dk){(cal.rides[dk]||[]).forEach(function(x){x.date=dk;rides.rides.push(x);});}); }
  catch(e){ q$("kg").innerHTML='<div class="kd">Błąd: '+qEsc(e.message)+'</div>'; return; }
  calData=cal.days||{};ridesMap={};var seen={};
  entryRoutes={};(cal.entry_routes||[]).forEach(function(x){entryRoutes[x.entry_id+"|"+x.day]={route_id:x.route_id,route_name:x.route_name};});
  (cal.entries||[]).forEach(function(e){var d=calData[e.day]=calData[e.day]||{};d._entries=d._entries||[];d._entries.push(e);
    if(e.end_day&&e.end_day!==e.day){var sd=new Date(e.day+"T12:00:00"),ed=new Date(e.end_day+"T12:00:00");for(var dd2=new Date(sd);dd2<=ed;dd2.setDate(dd2.getDate()+1)){var dk=localISO(dd2);calData[dk]=calData[dk]||{};calData[dk]._entries=calData[dk]._entries||[];if(dk!==e.day)calData[dk]._entries.push(e);}}
  });
  (rides.rides||[]).forEach(function(r){if(seen[r.ride_key])return;seen[r.ride_key]=1;ridesMap[r.date]=ridesMap[r.date]||[];ridesMap[r.date].push(r);});
  fetch("/api/report/schedules?start="+se[0]+"&end="+se[1],{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.ok?r.json():null;}).then(function(js){sched={};if(js)(js.items||[]).forEach(function(x){sched[x.entry_id+"|"+x.day]=x;});}).catch(function(){});
  q$("mo-label").textContent=MON[MO]+" "+YR;
  var kg=q$("kg");kg.innerHTML="";
  var d=new Date(se[0]+"T12:00:00");var end=new Date(se[1]+"T12:00:00");
  var wkR=0,wkKm=0,wkXss=0,moR=0,moKm=0,moXss=0;
  while(d<=end){
    var ds=localISO(d);var dd=calData[ds]||{};var rr=ridesMap[ds]||[];
    var inMonth=(d.getMonth()===MO);var isToday=(ds===today);
    var ents=dd._entries||[];
    var isIll=ents.some(function(e){return e.kind==="illness";});
    var cls="kd"+(inMonth?"":" off")+(isToday?" t":"")+(ds===selDay?" sel":"")+(isIll?" ill":"");
    var h='<div class="n"><b>'+d.getDate()+'</b>';
    var rl=dd.readiness_label;if(rl&&inMonth){var rc=dd.readiness>0.3?"var(--good)":dd.readiness>-0.3?"var(--ink2)":"var(--bad)";h+='<span class="f" style="color:'+rc+'">'+qEsc(rl)+'</span>';}
    h+='</div>';
    rr.forEach(function(r){var cy=isCyc(r.sport);var km=(cy&&r.dist_km)?qN(r.dist_km,0)+" km":"";var dur=r.duration_s?qHM(r.duration_s):"";h+='<div class="ride"'+(cy?'':' style="opacity:.85"')+'>'+spIcon(r.sport)+' '+km+(km&&dur?" · ":"")+dur+'</div>';});
    ents.forEach(function(e){
      if(e.kind==="illness")h+='<div data-id="'+e.id+'" class="ev red">🤒 '+qEsc(e.title||"choroba")+'</div>';
      else if(e.kind==="feel")h+='<div data-id="'+e.id+'" class="ev gray">😊 '+qEsc(e.title||(e.feel>0?"dobrze":e.feel<0?"słabo":"neutralnie"))+'</div>';
      else if(e.kind==="reminder")h+='<div data-id="'+e.id+'" class="ev gray">🔔 '+qEsc((e.at_time?e.at_time.slice(0,5)+" ":"")+(e.title||"przypomnienie"))+'</div>';
      else if(e.kind==="event")h+='<div data-id="'+e.id+'" class="ev '+evClass(e.event_type)+'">'+evIcon(e.event_type)+' '+qEsc(QD.text(e.title||evLabel(e.event_type)))+'</div>';
    });
    var slParts=[];if(dd.sleep_score)slParts.push("sen "+dd.sleep_score);else if(dd.sleep)slParts.push("sen "+qN(dd.sleep,1)+"h");if(dd.weight_kg)slParts.push(qN(dd.weight_kg,1)+" kg");
    if(slParts.length)h+='<div class="sl"><span>'+slParts.join("</span><span>")+'</span></div>';
    var div=document.createElement("div");div.className=cls;div.dataset.day=ds;div.innerHTML=h;div.querySelectorAll(".ev[data-id]").forEach(function(el){el.style.cursor="pointer";el.addEventListener("click",function(ev){ev.stopPropagation();var cell=this.closest(".kd");var dday=cell.dataset.day;document.querySelectorAll(".kd.sel").forEach(function(x){x.classList.remove("sel");});cell.classList.add("sel");selDay=dday;showDay(dday);var e=findEntry(parseInt(this.dataset.id,10));if(e)openEditor(dday,e);});});
    div.addEventListener("click",function(){document.querySelectorAll(".kd.sel").forEach(function(x){x.classList.remove("sel");});this.classList.add("sel");selDay=this.dataset.day;showDay(selDay);});
    kg.appendChild(div);
    if(inMonth){rr.forEach(function(r){moR++;if(isCyc(r.sport))moKm+=(r.dist_km||0);moXss+=(r.xss||0);});}
    rr.forEach(function(r){wkR++;if(isCyc(r.sport))wkKm+=(r.dist_km||0);wkXss+=(r.xss||0);});
    if(d.getDay()===0){var wk=document.createElement("div");wk.className="wk";
      if(wkR)wk.innerHTML='<b>'+wkR+' tren.</b><br>'+qN(wkKm,0)+' km<br>XSS '+qN(wkXss,0);
      kg.appendChild(wk);wkR=0;wkKm=0;wkXss=0;}
    d.setDate(d.getDate()+1);
  }
  loadWx(se);
  q$("ksum").innerHTML='<b>'+moR+'</b> treningów · <b>'+qN(moKm,0)+'</b> km rowerem · obciążenie XSS <b>'+qN(moXss,0)+'</b>';
  showDay(selDay);
}

/* ---------- POGODA na kafelkach (2026-09-28): prognoza jak w TRENER + pogoda z minionych jazd ---------- */
function wxBadCal(wx,ov){if(!wx)return false;var g=function(k,d){return ov&&ov[k]!=null?+ov[k]:d;};
  var rain=(wx.rain_mmh!=null?wx.rain_mmh:null);
  return (wx.wind!=null&&wx.wind>g("wx.wind_ms",8)+g("wx.forest_bonus_ms",1))||(rain!=null&&rain>g("wx.rain_mmh",0.5))||!!wx.storm;}
function loadWx(se){
  fetch("/api/calendar/wx?start="+se[0]+"&end="+se[1],{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.ok?r.json():null;}).then(function(j){
    if(!j)return;var fc=j.forecast||{},rd=j.rides||{},ov=j.ov||{};
    document.querySelectorAll("#kg .kd[data-day]").forEach(function(cell){
      var ds=cell.dataset.day,old=cell.querySelector(".wx");if(old)old.remove();
      var r=rd[ds],f=fc[ds],h="",tip="",bad=false;
      if(r&&(ds<today||!f)){
        h=r.icon+' <span class="wt">'+(r.wind!=null?qN(r.wind,1)+" m/s":"")+(r.feel_max!=null?" · "+Math.round(r.feel_max)+"°":(r.temp_max!=null?" · "+Math.round(r.temp_max)+"°":""))+'</span>';
        tip="pogoda podczas jazdy: wiatr śr. "+(r.wind!=null?r.wind:"—")+" m/s"+(r.wind_max!=null?" (max "+r.wind_max+")":"")+" · odczuwalna "+(r.feel_min!=null?r.feel_min:"—")+"…"+(r.feel_max!=null?r.feel_max:"—")+" °C · temp. "+(r.temp_min!=null?r.temp_min:"—")+"…"+(r.temp_max!=null?r.temp_max:"—")+" °C · opad "+(r.rain_mm!=null?r.rain_mm:"—")+" mm";
      }else if(f){
        bad=wxBadCal(f,ov);
        h=f.icon+' <span class="wt">'+(f.wind!=null?qN(f.wind,1)+" m/s":"")+(f.feel_max!=null?" · "+Math.round(f.feel_max)+"°":"")+'</span>';
        tip="prognoza 8–18: wiatr "+f.wind+" m/s, porywy "+f.gust+" · odczuwalna "+f.feel_min+"…"+f.feel_max+" °C · opad "+f.rain_mmh+" mm/h ("+f.rain_prob+"%)"+(f.storm?" · burza":"");
      }else return;
      var n=cell.querySelector(".n");var el=document.createElement("div");el.className="wx"+(bad?" bad":"")+(r&&(ds<today||!f)?" past":"");el.title=tip;el.innerHTML=h;
      if(n&&n.nextSibling)cell.insertBefore(el,n.nextSibling);else cell.appendChild(el);
    });
  }).catch(function(){});
}

/* rodzaje treningow z training_sessions.sport_type */
function isCyc(s){s=String(s||"");return s.indexOf("cycl")>=0||s.indexOf("biking")>=0;}
function spIcon(s){s=String(s||"");return isCyc(s)?"🚴🏻":s.indexOf("yoga")>=0?"🧘":s.indexOf("rowing")>=0?"🚣":s.indexOf("walk")>=0||s.indexOf("hik")>=0?"🚶":s.indexOf("strength")>=0?"🏋️":s.indexOf("run")>=0?"🏃":s.indexOf("swim")>=0?"🏊":"🏅";}
function spName(s){s=String(s||"");return isCyc(s)?"rower":s.indexOf("yoga")>=0?"joga":s.indexOf("rowing")>=0?"wioślarz":s.indexOf("walk")>=0?"spacer":s.indexOf("strength")>=0?"siła":s||"trening";}
function findEntry(id){for(var k in calData){var es=(calData[k]&&calData[k]._entries)||[];for(var i=0;i<es.length;i++)if(es[i].id===id)return es[i];}return null;}

function showDay(ds){
  var dp=q$("dp");if(!dp)return;var dd=calData[ds]||{};var rr=ridesMap[ds]||[];
  var dn=["niedziela","poniedziałek","wtorek","środa","czwartek","piątek","sobota"];
  var d=new Date(ds+"T12:00:00");
  dp.querySelector("div:first-child").textContent=dn[d.getDay()].charAt(0).toUpperCase()+dn[d.getDay()].slice(1)+", "+QD.dm(d);
  var sub=dp.querySelector(".sub");
  if(sub)sub.innerHTML='<div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 12px;font-size:14px;line-height:1.6"><span>gotowość <b>'+(typeof dd.readiness==="number"?(dd.readiness>0?"+":"")+qN(dd.readiness,2):"—")+'</b></span><span>sen <b>'+(dd.sleep_score||qN(dd.sleep,1)+'h')+'</b></span><span>HRV <b>'+qN(dd.hrv,0)+'</b></span>'+(dd.weight_kg?'<span>waga <b>'+qN(dd.weight_kg,1)+' kg</b></span>':'')+'</div>';
  var rows=dp.querySelector(".rows");if(rows){rows.innerHTML="";
    rr.forEach(function(r){var cy=isCyc(r.sport);rows.innerHTML+='<div class="r" style="grid-template-columns:1fr auto"><span class="w">'+spIcon(r.sport)+' '+(cy?'<a class="link" href="/raport-jazdy.html?ride='+encodeURIComponent(r.ride_key)+'">'+qEsc(r.name)+'</a>':qEsc(r.name||spName(r.sport)))+'</span><span class="s">'+((cy&&r.dist_km)?qN(r.dist_km,1)+" km · ":"")+(r.duration_s?qHM(r.duration_s):"")+(r.xss?" · XSS "+Math.round(r.xss):"")+'</span></div>';});
    if(!rr.length)rows.innerHTML+='<div class="r" style="grid-template-columns:1fr"><span class="w muted">dzień bez treningu</span></div>';
    var ents2=(calData[ds]||{})._entries||[];var seen={};ents2=ents2.filter(function(e){if(seen[e.id])return false;seen[e.id]=1;return true;});
    ents2.forEach(function(e){
      var ic=e.kind==="illness"?"🤒":e.kind==="feel"?"😊":e.kind==="reminder"?"🔔":evIcon(e.event_type);
      var lbl=e.kind==="feel"?("samopoczucie: "+(FEEL_LABEL[String(e.feel)]||e.title||"")):QD.text(e.title||(e.kind==="illness"?"choroba":e.kind==="reminder"?"przypomnienie":evLabel(e.event_type)));
      rows.innerHTML+='<div class="r kent" data-id="'+e.id+'" style="grid-template-columns:auto 1fr auto;cursor:pointer"><span>'+ic+'</span><span class="w">'+qEsc(lbl)+'</span><span class="s">✎</span></div>';
    });
    rows.querySelectorAll(".kent").forEach(function(el){el.addEventListener("click",function(){var e=findEntry(parseInt(this.dataset.id,10));if(e)openEditor(ds,e);});});
  }
  var acts=dp.querySelectorAll(".acts button");
  acts.forEach(function(b){var t=b.textContent;
    b.onclick=function(){
      if(t.indexOf("samopoczucie")>=0)openEditor(ds,null,"feel");
      else if(t.indexOf("wydarzenie")>=0)openEditor(ds,null,"event");
      else if(t.indexOf("choroba")>=0)openEditor(ds,null,"illness");
      else if(t.indexOf("przypomnij")>=0)openEditor(ds,null,"reminder");
    };
  });
}

/* ---------- MODAL EDYTORA ---------- */
function tkeyOf(){ if(ED.kind==="event")return ED.event_type||"event"; return ED.kind; }
function openEditor(day,entry,presetKind){
  ED={day:day,id:entry?entry.id:null,kind:entry?entry.kind:(presetKind==="event"?"event":presetKind),event_type:entry?(entry.event_type||""):"",entry:entry||null};
  if(!entry&&presetKind&&["rest","urlop","delegacja"].indexOf(presetKind)>=0){ED.kind="event";ED.event_type=presetKind;}
  renderEditor();
  q$("km-scrim").classList.add("on");q$("km").classList.add("on");
}
function closeEditor(){q$("km-scrim").classList.remove("on");q$("km").classList.remove("on");ED=null;}
function setType(tk){if(tk==="illness"||tk==="feel"||tk==="reminder"){ED.kind=tk;ED.event_type="";}else{ED.kind="event";ED.event_type=(tk==="event"?"":tk);}renderEditor();}

function sevOpts(sel){return ["lekka","średnia","ciężka"].map(function(s){return '<option'+(s===sel?" selected":"")+'>'+s+'</option>';}).join("");}
function offOpts(sel){sel=String(sel||"0");var o=[["0","o czasie"],["60","1 h przed"],["240","4 h przed"],["480","8 h przed"]];return o.map(function(x){return '<option value="'+x[0]+'"'+(x[0]===sel?" selected":"")+'>'+x[1]+'</option>';}).join("");}
function swatches(sel){return '<div class="km-sw" id="km-sw">'+COLORS.map(function(c){return '<button type="button" data-c="'+c[0]+'"'+(c[0]===sel?' class="on"':'')+' title="'+c[1]+'" style="'+(c[0]?("background:"+c[0]):"background:transparent;border-color:var(--line);color:var(--ink2);font-size:9px")+'">'+(c[0]?"":"auto")+'</button>';}).join("")+'</div>';}
function selColor(){var w=q$("km-sw");if(!w)return "";var on=w.querySelector("button.on");return on?on.dataset.c:"";}

function fieldsFor(tk){
  var e=ED.entry||{};
  if(tk==="feel"){var fv=(e.feel!=null?e.feel:0);
    return '<div style="text-align:center"><div style="font-size:20px;font-weight:700;margin-bottom:4px" id="km-fv">'+FEEL_LABEL[String(fv)]+'</div>'
      +'<input type="range" id="km-feel" min="-2" max="2" step="1" value="'+fv+'" style="width:100%">'
      +'<div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted)"><span>fatalnie</span><span>świetnie</span></div></div>'
      +'<label>Notatka</label><textarea id="km-note">'+qEsc(e.note||"")+'</textarea>';
  }
  if(tk==="illness"){
    return '<label>Opis</label><input type="text" id="km-title" maxlength="200" placeholder="np. katar, gorączka" value="'+qEsc(e.title||"")+'">'
      +'<div class="row2"><div><label>Nasilenie</label><select id="km-sev">'+sevOpts(e.severity)+'</select></div><div><label>Do (opcjonalnie)</label><input type="date" id="km-end" value="'+qEsc(e.end_day&&e.end_day!==e.day?e.end_day:"")+'"></div></div>'
      +'<label>Notatka</label><textarea id="km-note">'+qEsc(e.note||"")+'</textarea>';
  }
  if(tk==="reminder"){
    return '<label>Tytuł</label><input type="text" id="km-title" maxlength="200" placeholder="np. wymień łańcuch" value="'+qEsc(e.title||"")+'">'
      +'<div class="row2"><div><label>Godzina</label><input type="time" id="km-time" value="'+(e.at_time?e.at_time.slice(0,5):"")+'"></div><div><label>Przypomnij</label><select id="km-off">'+offOpts(e.remind_offsets)+'</select></div></div>'
      +'<label>Notatka</label><textarea id="km-note">'+qEsc(e.note||"")+'</textarea>';
  }
  if(tk==="jazda"){
    var _n=String(e.note||""),_mk=_n.match(/(?:^|\s·\s)([0-9]+(?:[.,][0-9]+)?)\s*km\s*$/),_km=_mk?_mk[1]:"",_nt=_mk?_n.slice(0,_mk.index).trim():_n;
    return '<label>Tytuł</label><input type="text" id="km-title" maxlength="200" placeholder="np. kółko z Adamem" value="'+qEsc(e.title||"")+'">'
      +'<div class="row2"><div><label>Start (opcjonalnie)</label><input type="time" id="km-time" value="'+(e.at_time?e.at_time.slice(0,5):"")+'"></div>'
      +'<div><label>Dystans km (opcjonalnie)</label><input type="text" inputmode="decimal" id="km-km" placeholder="np. 60" value="'+qEsc(_km)+'"></div></div>'
      +'<label>Do (dzień końcowy, opcjonalnie)</label><input type="date" id="km-end" value="'+qEsc(e.end_day&&e.end_day!==e.day?e.end_day:"")+'">'
      +'<label>Kolor</label>'+swatches(e.color||"")
      +'<label>Notatka</label><textarea id="km-note">'+qEsc(_nt)+'</textarea>'
      +'<div style="font-size:12px;color:var(--muted);margin-top:6px">Jazda liczy si\u0119 do prognozy formy; z dystansu szacuj\u0119 obci\u0105\u017cenie. Tras\u0119 mo\u017cesz przypi\u0105\u0107 po zapisaniu.</div>';
  }
  return '<label>Tytuł'+(tk==="rest"?" (opcjonalnie)":"")+'</label><input type="text" id="km-title" maxlength="200" placeholder="'+(tk==="urlop"?"Urlop":tk==="delegacja"?"Delegacja":tk==="rest"?"Rest day":"np. wyścig")+'" value="'+qEsc(e.title||"")+'">'
    +'<label>Do (dzień końcowy, opcjonalnie)</label><input type="date" id="km-end" value="'+qEsc(e.end_day&&e.end_day!==e.day?e.end_day:"")+'">'
    +'<label>Kolor</label>'+swatches(e.color||"")
    +'<label>Notatka</label><textarea id="km-note">'+qEsc(e.note||"")+'</textarea>';
}

function schedTxt(sc){var m={pending:"czeka 06:00",running:"wysyłam…",sent:"wysłano",partial:"część nie doszła",failed:"błąd"};return m[sc.status]||sc.status;}
function routeMailSection(){
  if(!(ED.id&&ED.kind==="event"))return (ED.kind==="event"?'<div class="km-sec"><div class="sh">Trasa / mail</div><div style="font-size:12.5px;color:var(--muted)">Zapisz wydarzenie, aby przypiąć trasę i wysyłkę maila.</div></div>':"");
  var rr=entryRoutes[ED.id+"|"+ED.day];
  var cur=rr?('<div class="km-cur">🧭 <b>'+qEsc(rr.route_name||rr.route_id)+'</b> <a class="link" href="/raport-trasy.html?route='+encodeURIComponent(rr.route_id)+'" target="_blank">analiza</a> <button type="button" id="km-rdet" class="km-x" style="width:24px;height:24px;font-size:12px">✕</button></div>'):'';
  var sc=sched[ED.id+"|"+ED.day];var mailst=sc?('<span class="km-mailst" style="color:var(--good)">'+schedTxt(sc)+'</span>'):'';
  return '<div class="km-sec"><div class="sh">Trasa dnia</div>'+cur+'<select id="km-route"><option value="">'+(rr?"— zmień trasę —":"— wybierz trasę —")+'</option></select></div>'
    +'<div class="km-sec"><div class="sh">Raport mailem (06:00)</div><select id="km-group"><option value="">— nie wysyłaj —</option></select> '+mailst+'</div>';
}

function renderEditor(){
  var tk=tkeyOf();var editing=!!ED.id;
  var chips=TYPES.map(function(t){
    var on=(t[0]===tk),dis=false;
    if(editing){var ek=ED.entry.kind;if(ek==="event"){dis=(["jazda","event","rest","urlop","delegacja"].indexOf(t[0])<0);}else{dis=(t[0]!==ek);}}
    return '<button type="button" data-tk="'+t[0]+'"'+(on?' class="on"':'')+(dis?' disabled':'')+'>'+t[1]+'</button>';
  }).join("");
  q$("km").innerHTML='<div class="km-head"><span class="kt">'+(editing?"Edytuj":"Dodaj")+' · '+qEsc(ED.day)+'</span><button class="km-x" id="km-x" type="button">✕</button></div>'
    +'<div class="km-body"><div class="km-types">'+chips+'</div><div id="km-fields">'+fieldsFor(tk)+'</div><div class="km-err" id="km-err"></div>'+routeMailSection()+'</div>'
    +'<div class="km-foot">'+(editing?'<button type="button" class="del" id="km-del">Usuń</button>':'')+'<button type="button" id="km-cancel">Anuluj</button><button type="button" class="save" id="km-save">Zapisz</button></div>';
  wireEditor();
}
function edErr(m){var e=q$("km-err");if(e)e.textContent=m||"";}
function wireEditor(){
  var m=q$("km");
  m.querySelectorAll(".km-types button").forEach(function(b){if(!b.disabled)b.onclick=function(){setType(b.dataset.tk);};});
  q$("km-x").onclick=closeEditor;q$("km-cancel").onclick=closeEditor;q$("km-save").onclick=saveEditor;
  var del=q$("km-del");if(del)del.onclick=deleteEditor;
  var fe=q$("km-feel");if(fe)fe.oninput=function(){q$("km-fv").textContent=FEEL_LABEL[String(fe.value)];};
  var sw=q$("km-sw");if(sw)sw.querySelectorAll("button").forEach(function(b){b.onclick=function(){sw.querySelectorAll("button").forEach(function(x){x.classList.remove("on");});b.classList.add("on");};});
  if(ED.id&&ED.kind==="event"){
    ensureRoutes().then(function(rts){var sel=q$("km-route");if(!sel)return;rts.forEach(function(r){var o=document.createElement("option");o.value=r.route_id;o.textContent=r.name+(r.distance_km?(" · "+r.distance_km+" km"):"");sel.appendChild(o);});sel.onchange=function(){if(sel.value)setRoute(sel.value,routeName(sel.value));};});
    var rdet=q$("km-rdet");if(rdet)rdet.onclick=function(){setRoute("",null);};
    ensureGroups().then(function(gs){var sel=q$("km-group");if(!sel)return;var sc=sched[ED.id+"|"+ED.day];gs.forEach(function(g){var o=document.createElement("option");o.value=g.id;o.textContent=g.name+" ("+(g.members?g.members.length:0)+")";if(sc&&sc.group_id===g.id)o.selected=true;sel.appendChild(o);});if(!gs.length){sel.disabled=true;sel.options[0].textContent="— brak grup —";}sel.onchange=function(){setSchedule(sel.value?parseInt(sel.value,10):null);};});
  }
}
async function post(url,body){var r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify(body)});if(!r.ok){var t="";try{t=await r.text();}catch(e){}throw new Error(t||("HTTP "+r.status));}try{return await r.json();}catch(e){return {};}}
async function saveEditor(){
  var tk=tkeyOf();var body={day:ED.day,kind:ED.kind};
  if(ED.kind==="event")body.event_type=ED.event_type||"";
  var t=q$("km-title");if(t)body.title=t.value.trim();
  var note=q$("km-note");if(note)body.note=note.value.trim();
  if(tk==="feel"){body.feel=parseInt(q$("km-feel").value,10);body.title=FEEL_LABEL[String(body.feel)];}
  if(tk==="illness"){var sv=q$("km-sev");if(sv)body.severity=sv.value;}
  if(tk==="reminder"){var tm=q$("km-time");if(tm&&tm.value)body.at_time=tm.value;var off=q$("km-off");if(off)body.remind_offsets=off.value;}
  if(tk==="jazda"){var _t=q$("km-time");if(_t&&_t.value)body.at_time=_t.value;
    var _k=q$("km-km");var _kv=_k?String(_k.value||"").trim().replace(".",","):"";
    if(_kv&&/^[0-9]+(,[0-9]+)?$/.test(_kv))body.note=((body.note||"")+(body.note?" · ":"")+_kv+" km");}
  var end=q$("km-end");if(end&&end.value)body.end_day=end.value;
  if(ED.kind==="event")body.color=selColor();
  try{
    if(ED.id){body.id=ED.id;await post("/api/calendar/edit",body);}
    else{await post("/api/calendar/entry",body);}
    closeEditor();await render();
  }catch(err){edErr("Nie zapisano: "+err.message);}
}
async function deleteEditor(){if(!ED.id)return;try{await post("/api/calendar/delete",{id:ED.id});closeEditor();await render();}catch(err){edErr("Nie usunięto: "+err.message);}}
async function setRoute(rid,nm){try{await post("/api/calendar/route",{entry_id:ED.id,day:ED.day,route_id:rid,route_name:nm});await render();var e=findEntry(ED.id);openEditor(ED.day,e||ED.entry);}catch(err){edErr(err.message);}}
async function setSchedule(gid){
  try{
    if(!gid){var sc=sched[ED.id+"|"+ED.day];if(sc)await fetch("/api/report/schedule/"+sc.id,{method:"DELETE",credentials:"same-origin"});}
    else await post("/api/report/schedule",{entry_id:ED.id,day:ED.day,group_id:gid,all_days:false});
    var se=startEnd(YR,MO);var js=null;try{var rr=await fetch("/api/report/schedules?start="+se[0]+"&end="+se[1],{credentials:"same-origin",cache:"no-store"});js=rr.ok?await rr.json():null;}catch(e){}
    sched={};if(js)(js.items||[]).forEach(function(x){sched[x.entry_id+"|"+x.day]=x;});
    var e=findEntry(ED.id);openEditor(ED.day,e||ED.entry);
  }catch(err){edErr(err.message);}
}
function ensureRoutes(){if(ROUTES)return Promise.resolve(ROUTES);return fetch("/api/routes/ready",{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.json();}).then(function(j){ROUTES=(j.routes||[]);return ROUTES;}).catch(function(){ROUTES=[];return ROUTES;});}
function routeName(rid){var x=(ROUTES||[]).find(function(r){return String(r.route_id)===String(rid);});return x?x.name:null;}
function ensureGroups(){if(MGROUPS)return Promise.resolve(MGROUPS);return fetch("/api/mail-groups",{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.json();}).then(function(j){MGROUPS=(j.items||[]);return MGROUPS;}).catch(function(){MGROUPS=[];return MGROUPS;});}

q$("btn-prev").addEventListener("click",function(){MO--;if(MO<0){MO=11;YR--;}render();});
q$("btn-next").addEventListener("click",function(){MO++;if(MO>11){MO=0;YR++;}render();});
q$("btn-today").addEventListener("click",function(){YR=CUR.getFullYear();MO=CUR.getMonth();selDay=today;render();});
q$("km-scrim").addEventListener("click",closeEditor);
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&ED)closeEditor();});
render();
})();
