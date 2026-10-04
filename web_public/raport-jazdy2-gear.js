/* raport-jazdy2-gear.js - "W czym jechalem": rower (z czujnikow), typ jazdy, odczucie i ubior z garazu
   dla wybranej jazdy. Zapis: /api/ride-gear/save (garage.db ride_gear_log). Opcjonalne - do nauki doboru ubioru. */
(function(){
"use strict";
var GROUPS=[["G\u00f3ra",["Termika \u2014 g\u00f3ra","Koszulka / bluza","Kamizelka","Kurtka","Deszczowa \u2014 g\u00f3ra"]],
            ["D\u00f3\u0142",["Termika \u2014 d\u00f3\u0142","Z wk\u0142adk\u0105","Bez wk\u0142adki","Deszczowa \u2014 d\u00f3\u0142"]],
            ["Dodatki",["R\u0119kawki","Nogawki","R\u0119kawiczki","Nakrycie g\u0142owy","Komin i chusta","Skarpety","Ochraniacze na buty","Buty"]]];
var TYPY=[["krotki","kr\u00f3tki trening"],["dluzsza","d\u0142u\u017csza jazda"],["wyprawa","wyprawa"]];
var ODCZ=[["zimno","za zimno"],["ok","w sam raz"],["cieplo","za ciep\u0142o"]];
var RIDES=null,OPT=null,STATE={},CUR=null;
function $(id){return document.getElementById(id);}
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
var css=document.createElement("style");
css.textContent="#gearp{top:64px;right:12px;bottom:calc(var(--dh,0px) + 110px);width:380px;padding:12px 14px;display:none;overflow:auto;font-size:14px}"+
 "#gearp .gh{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}#gearp .gh b{font-size:16px}"+
 "#gearp .gs{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:10px 0 4px}"+
 "#gearp .gr{display:flex;flex-wrap:wrap;gap:5px}#gearp .gr .chip.on{border-color:var(--accent);color:var(--accent-ink);font-weight:700}"+
 "#gearp .gl{display:grid;grid-template-columns:118px 1fr;gap:4px 8px;align-items:center}#gearp .gl label{font-size:12.5px;color:var(--ink2)}"+
 "#gearp select,#gearp textarea{font:inherit;font-size:13px;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:3px 6px;width:100%;box-sizing:border-box}"+
 "#gearp .gn{font-size:12px;color:var(--muted);margin-top:3px}#gearp .gok{color:var(--good,#2e7d32);font-weight:600}"+
 "#gearbtn.has::after{content:' \\2713';color:var(--good,#2e7d32);font-weight:700}"+
 "@media(max-width:820px){#gearp{left:8px;right:8px;width:auto}}";
document.head.appendChild(css);
var panel=document.createElement("div");panel.className="ov";panel.id="gearp";document.body.appendChild(panel);
function addBtn(){var row=document.querySelector("#pj .row"),an=$("anbtn");if(!row||$("gearbtn"))return;
  var b=document.createElement("button");b.className="btn";b.id="gearbtn";b.type="button";b.textContent="\ud83d\udc55 W czym jecha\u0142em";
  b.onclick=function(){if(panel.style.display==="block"){panel.style.display="none";return;}open();};
  row.insertBefore(b,an?an.nextSibling:null);}
function rideKey(){var s=$("ridesel");return s&&s.value&&/^[0-9A-Za-z_.:-]+$/.test(s.value)?s.value:null;}
function suggestType(k){var r=(RIDES||[]).filter(function(x){return String(x.ride_key)===String(k);})[0];if(!r)return null;
  var h=(+r.duration_s||0)/3600,km=+r.dist_km||0;return (h>=3.5||km>=80)?"dluzsza":"krotki";}
function load(k){CUR=k;OPT=null;STATE={};
  return fetch("/api/ride-gear/options?ride="+encodeURIComponent(k),{credentials:"same-origin",cache:"no-store"}).then(function(r){return r.json();}).then(function(j){
    if(CUR!==k)return;OPT=j;var sv=j.saved||{};
    Object.keys(sv).forEach(function(s){STATE[s]=sv[s];});
    var b=$("gearbtn");if(b)b.classList.toggle("has",Object.keys(sv).length>0);
    if(panel.style.display==="block")render();});}
function val(s){return (STATE[s]&&(STATE[s].value!=null?STATE[s].value:STATE[s].gear_id))||"";}
function setv(s,v,isGear){if(v===""||v==null){delete STATE[s];}else STATE[s]=isGear?{gear_id:+v}:{value:String(v)};}
function chips(slot,list,sugg){var cur=val(slot)||"";return '<div class="gr">'+list.map(function(t){return '<button type="button" class="chip'+(cur===t[0]?" on":"")+'" data-s="'+slot+'" data-v="'+t[0]+'">'+t[1]+(sugg===t[0]&&!cur?" ?":"")+'</button>';}).join("")+'</div>';}
function render(){
  if(!OPT){panel.innerHTML='<div class="gn">wczytuj\u0119\u2026</div>';return;}
  var k=CUR,byCat={};(OPT.slots||[]).forEach(function(s){byCat[s.slot]=s.items||[];});
  var det=OPT.detected_bike,rw=val("_rower")||(det?String(det.id):""),sug=suggestType(k);
  var h='<div class="gh"><b>W czym jecha\u0142em</b><button type="button" class="btn" id="gearx">\u00d7</button></div>'+
    '<div class="gn">Opcjonalne. Uczy system, w czym Ci dobrze przy danej pogodzie. Typ jazdy oddziela tygodniowe treningi od d\u0142ugich wyjazd\u00f3w.</div>';
  h+='<div class="gs">Rower</div><select id="g-rower"><option value="">\u2014</option>'+(OPT.bikes||[]).map(function(b){return '<option value="'+b.id+'"'+(String(b.id)===String(rw)?" selected":"")+'>'+esc(b.name)+'</option>';}).join("")+'</select>'+
     (det&&!val("_rower")?'<div class="gn">rozpoznany z czujnik\u00f3w: '+esc(det.z_czujnikow)+'</div>':'');
  h+='<div class="gs">Typ jazdy</div>'+chips("_typ",TYPY,sug)+(sug&&!val("_typ")?'<div class="gn">podpowied\u017a z czasu jazdy: '+(sug==="krotki"?"kr\u00f3tki trening":"d\u0142u\u017csza jazda")+' \u2014 kliknij, \u017ceby potwierdzi\u0107</div>':'');
  h+='<div class="gs">Odczucie termiczne</div>'+chips("_odczucie",ODCZ,null);
  GROUPS.forEach(function(g){h+='<div class="gs">'+g[0]+'</div><div class="gl">';
    g[1].forEach(function(cat){var its=byCat[cat]||[];if(!its.length)return;var cv=String(val(cat));
      h+='<label>'+esc(cat.replace("Bielizna termoaktywna \u2014 ","Termo ").replace(" (bez wk\u0142adki)",""))+'</label><select data-cat="'+esc(cat)+'"><option value="">\u2014</option>'+
        its.map(function(it){return '<option value="'+it.id+'"'+(String(it.id)===cv?" selected":"")+'>'+esc(it.label)+'</option>';}).join("")+'</select>';});
    h+='</div>';});
  h+='<div class="gs">Uwagi</div><textarea id="g-uw" rows="2" placeholder="np. rano zimno w d\u0142onie, od 12:00 za ciep\u0142o">'+esc(val("_uwagi"))+'</textarea>';
  h+='<div class="gr" style="margin-top:10px"><button type="button" class="btn" id="g-last">jak ostatnio</button><button type="button" class="btn pri" id="g-save">Zapisz</button><span class="gn" id="g-msg"></span></div>';
  panel.innerHTML=h;
  $("gearx").onclick=function(){panel.style.display="none";};
  $("g-rower").onchange=function(){setv("_rower",this.value,false);};
  panel.querySelectorAll(".chip[data-s]").forEach(function(c){c.onclick=function(){var s=c.dataset.s;setv(s,val(s)===c.dataset.v?"":c.dataset.v,false);render();};});
  panel.querySelectorAll("select[data-cat]").forEach(function(sl){sl.onchange=function(){setv(sl.dataset.cat,sl.value,true);};});
  $("g-uw").oninput=function(){setv("_uwagi",this.value.trim(),false);};
  $("g-last").onclick=function(){var L=OPT.last||{},n=0;Object.keys(L).forEach(function(s){if(s.charAt(0)==="_"||s==="wheels"||s==="cassette")return;if(L[s].gear_id){STATE[s]={gear_id:L[s].gear_id};n++;}});render();$("g-msg").textContent=n?"skopiowano "+n+" rzeczy z ostatniego wpisu":"brak wcze\u015bniejszego wpisu";};
  $("g-save").onclick=function(){
    if(!val("_rower")&&det)STATE["_rower"]={value:String(det.id)};
    var items={},all={};(OPT.slots||[]).forEach(function(s){all[s.slot]=1;});["_rower","_typ","_odczucie","_uwagi"].forEach(function(s){all[s]=1;});
    Object.keys(all).forEach(function(s){items[s]=STATE[s]||{};});
    var b=this;b.disabled=true;
    fetch("/api/ride-gear/save",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({ride:k,items:items})})
      .then(function(r){if(!r.ok)throw new Error("HTTP "+r.status);return r.json();}).then(function(j){b.disabled=false;panel.style.display="none";load(k);})
      .catch(function(){b.disabled=false;$("g-msg").textContent="nie zapisano";});};
}
function open(){var k=rideKey();if(!k)return;panel.style.display="block";if(k!==CUR||!OPT){load(k).then(render);render();}else render();}
fetch("/api/rides/ready",{credentials:"same-origin"}).then(function(r){return r.json();}).then(function(j){RIDES=j.rides||j||[];}).catch(function(){RIDES=[];});
(function wait(n){addBtn();var k=rideKey();if(k&&$("gearbtn")){load(k);var s=$("ridesel");s.addEventListener("change",function(){var kk=rideKey();if(kk)load(kk);});return;}
  if(n<80)setTimeout(function(){wait(n+1);},250);})(0);
})();
