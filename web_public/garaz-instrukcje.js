/* czas lokalny (strefa przegladarki) -- wspolne dla QBot lab */function qTsLocal(s,naiveUtc){if(!s)return"";var t=String(s).trim().replace(" ","T").replace(/\.\d+/,"");if(/[+-]\d\d$/.test(t))t+=":00";t=t.replace(/([+-]\d\d)(\d\d)$/,"$1:$2");if(!/(Z|[+-]\d\d:\d\d)$/i.test(t)){if(!naiveUtc)return t.slice(0,16).replace("T"," ");t+="Z";}var d=new Date(t);if(isNaN(d.getTime()))return String(s).slice(0,16);var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());}function qDateLocal(d){d=d||new Date();var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
/* garaz-instrukcje.js — zakladka INSTRUKCJE: zasady bikepackingowe z kwalifikatorami.
   Kwalifikatory (sezon / pogoda / typ wyprawy / priorytet) sluza pozniej generatorowi
   wyposazenia do doboru rzeczy pod konkretna wyprawe. */
(function(){
"use strict";
const $ = s => document.querySelector(s);
const el = (t,c,h) => { const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.textContent=h; return e; };
async function getJSON(u){ const r=await fetch(u,{credentials:"same-origin",cache:"no-store"}); if(!r.ok) throw new Error(r.status); return r.json(); }
async function postJSON(u,b){ const r=await fetch(u,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}); if(!r.ok) throw new Error(r.status); return r.json(); }

/* wartosci w bazie sa bez ogonkow (spojnie z sezonami sprzetu) - tu ladne etykiety */
const ET_SEZON   = {zima:"zima", przejsciowy:"przejściowy", lato:"lato"};
const ET_POGODA  = {snieg:"śnieg", deszcz:"deszcz", upal:"upał", zimno:"zimno"};
const ET_TYP     = {lekko:"lekko", ciezko:"ciężko"};
const IKONA_POG  = {snieg:"❄", deszcz:"☔", upal:"☀", zimno:"🌡"};

let INS = {items:[], seasons:[], weather:[], trip_types:[], priorities:[1,2,3]};
let INS_ALL = false;
let SEL = {season:new Set(), weather:new Set(), trip_type:new Set()};
let PRIO = 2;

async function insLoad(){
  try{
    INS = await getJSON("/api/instructions/list?all="+(INS_ALL?1:0)+"&_="+Date.now());
    insRender();
  }catch(e){
    const b=$("#instrBody"); b.innerHTML="";
    b.appendChild(el("div","empty","błąd ładowania ("+e.message+")"));
  }
}

function chipsy(csv, slownik, klasa){
  const box = el("span","chipset");
  const lista = String(csv||"").split(",").filter(Boolean);
  if(!lista.length){ box.appendChild(el("span","chip-off","—")); return box; }
  lista.forEach(v=>box.appendChild(el("span","chip-q "+(klasa||""), slownik[v]||v)));
  return box;
}

function insFiltered(){
  const q = ($("#isearch") ? $("#isearch").value.trim().toLowerCase() : "");
  const fs = $("#ifilterSeason").value, fw = $("#ifilterWeather").value;
  return (INS.items||[]).filter(it=>{
    if(fs && !String(it.season||"").split(",").includes(fs)) return false;
    if(fw && !String(it.weather||"").split(",").includes(fw)) return false;
    if(q){
      const hay = [it.title, it.body].map(x=>(x||"")).join(" ").toLowerCase();
      if(hay.indexOf(q)<0) return false;
    }
    return true;
  });
}

function insRender(){
  const body = $("#instrBody"); body.innerHTML="";
  const items = insFiltered(), total = (INS.items||[]).length;
  $("#icount").textContent = total ? (items.length===total ? total+" szt." : items.length+" / "+total+" szt.") : "";
  if(!items.length){
    body.appendChild(el("div","empty", total
      ? "Brak instrukcji dla tych filtrów."
      : "Pusto. Dodaj pierwszą zasadę przyciskiem „+ Dodaj instrukcję”."));
    return;
  }
  const tab = el("table","gt"), th = el("thead"), tr0 = el("tr");
  ["Prio","Instrukcja","Sezon","Pogoda","Wyprawa",""].forEach(h=>{
    tr0.appendChild(el("th","noclick",h));
  });
  th.appendChild(tr0); tab.appendChild(th);
  const tb = el("tbody");
  items.forEach(it=>{
    const tr = el("tr", it.active?null:"arch");
    tr.style.cursor="pointer";
    tr.addEventListener("click",()=>insOpen(it));

    const tdP = el("td");
    tdP.appendChild(el("span","prio p"+(it.priority||2), String(it.priority||2)));
    tr.appendChild(tdP);

    const tdT = el("td");
    tdT.appendChild(el("div","instr-t", it.title||"—"));
    if(it.body) tdT.appendChild(el("div","instr-b", it.body.slice(0,120)));
    tr.appendChild(tdT);

    const t1=el("td"); t1.appendChild(chipsy(it.season, ET_SEZON)); tr.appendChild(t1);
    const t2=el("td"); t2.appendChild(chipsy(it.weather, ET_POGODA, "w")); tr.appendChild(t2);
    const t3=el("td"); t3.appendChild(chipsy(it.trip_type, ET_TYP, "t")); tr.appendChild(t3);

    const act=el("td"), box=el("div","gact");
    const be=el("button",null,"Edytuj");
    be.addEventListener("click",e=>{e.stopPropagation();insOpen(it);});
    box.appendChild(be);
    const ba=el("button","sec", it.active?"Wyłącz":"Włącz");
    ba.addEventListener("click",async e=>{ e.stopPropagation();
      try{ await postJSON("/api/instructions/toggle",{id:it.id, active: it.active?0:1}); insLoad(); }catch(x){} });
    box.appendChild(ba);
    act.appendChild(box); tr.appendChild(act);
    tb.appendChild(tr);
  });
  tab.appendChild(tb); body.appendChild(tab);
}

/* ---------- okno dodawania / edycji ---------- */
function budujPrzelaczniki(pole, slownik, wartosci){
  const box = $("#i_"+pole); box.innerHTML="";
  (wartosci||[]).forEach(v=>{
    const b = el("button",null, slownik[v]||v);
    b.type="button"; b.dataset.v=v;
    b.addEventListener("click",()=>{
      if(SEL[pole].has(v)) SEL[pole].delete(v); else SEL[pole].add(v);
      malujPrzelaczniki(pole);
    });
    box.appendChild(b);
  });
  malujPrzelaczniki(pole);
}
function malujPrzelaczniki(pole){
  document.querySelectorAll("#i_"+pole+" button").forEach(b=>{
    b.classList.toggle("on", SEL[pole].has(b.dataset.v));
  });
}
function malujPrio(){
  document.querySelectorAll("#i_priority button").forEach(b=>{
    b.classList.toggle("on", Number(b.dataset.v)===PRIO);
  });
}

function insOpen(it){
  it = it||{};
  $("#iTitle").textContent = it.id ? "Edytuj instrukcję" : "Dodaj instrukcję";
  $("#i_id").value = it.id||"";
  $("#i_text").value = it.title||"";
  $("#i_body").value = it.body||"";
  SEL.season    = new Set(String(it.season||"").split(",").filter(Boolean));
  SEL.weather   = new Set(String(it.weather||"").split(",").filter(Boolean));
  SEL.trip_type = new Set(String(it.trip_type||"").split(",").filter(Boolean));
  PRIO = Number(it.priority||2);
  budujPrzelaczniki("season", ET_SEZON, INS.seasons);
  budujPrzelaczniki("weather", ET_POGODA, INS.weather);
  budujPrzelaczniki("trip_type", ET_TYP, INS.trip_types);
  malujPrio();
  $("#iMeta").textContent = it.id
    ? ("ID "+it.id+" · dodano: "+(qTsLocal(it.created_at,true)||"—")+" · "+(it.active===0?"wyłączona":"aktywna"))
    : "nowa instrukcja";
  const del = $("#iDelete");
  del.style.display = it.id ? "" : "none";
  del.textContent = "Usuń"; del.classList.remove("armed"); del.dataset.armed="";
  $("#iStatus").textContent="";
  $("#instrModal").classList.add("open");
  document.body.classList.add("modal-open");
  setTimeout(()=>$("#i_text").focus(), 50);
}
function insClose(){
  $("#instrModal").classList.remove("open");
  document.body.classList.remove("modal-open");
}

async function insSave(){
  const b = {
    id: $("#i_id").value||null,
    title: $("#i_text").value,
    body: $("#i_body").value,
    season: Array.from(SEL.season),
    weather: Array.from(SEL.weather),
    trip_type: Array.from(SEL.trip_type),
    priority: PRIO
  };
  if(!b.title.trim()){ $("#iStatus").textContent="wpisz treść instrukcji"; return; }
  $("#iStatus").textContent="zapis…";
  try{ await postJSON("/api/instructions/save", b); insClose(); insLoad(); }
  catch(e){ $("#iStatus").textContent="błąd zapisu ("+e.message+")"; }
}

async function insDelete(){
  const id = $("#i_id").value; if(!id) return;
  const b = $("#iDelete"), st = $("#iStatus");
  if(b.dataset.armed!=="1"){
    b.dataset.armed="1"; b.classList.add("armed"); b.textContent="Potwierdź usunięcie";
    st.textContent="usunięcie jest nieodwracalne — kliknij ponownie";
    setTimeout(()=>{ if(b.dataset.armed==="1"){ b.dataset.armed=""; b.classList.remove("armed"); b.textContent="Usuń"; st.textContent=""; } }, 6000);
    return;
  }
  if(!window.confirm("Usunąć tę instrukcję na zawsze?")){
    b.dataset.armed=""; b.classList.remove("armed"); b.textContent="Usuń"; st.textContent=""; return;
  }
  try{ await postJSON("/api/instructions/delete",{id:Number(id), confirm:true}); insClose(); insLoad(); }
  catch(e){ st.textContent="błąd usuwania ("+e.message+")"; }
}

/* udostepniamy przelacznikowi zakladek */
window.QInstr = { load: insLoad };

document.addEventListener("DOMContentLoaded", function(){
  const t = $("#tabInstr");
  if(t) t.addEventListener("click", ()=>{
    if(window.QSwitchTab) QSwitchTab("Instr");
  });
  $("#iadd").addEventListener("click", ()=>insOpen(null));
  $("#iarch").addEventListener("click", function(){
    INS_ALL=!INS_ALL; this.classList.toggle("on",INS_ALL);
    this.textContent = INS_ALL ? "Ukryj wyłączone" : "Pokaż wyłączone"; insLoad();
  });
  $("#isearch").addEventListener("input", insRender);
  $("#ifilterSeason").addEventListener("change", insRender);
  $("#ifilterWeather").addEventListener("change", insRender);
  $("#iSave").addEventListener("click", insSave);
  $("#iCancel").addEventListener("click", insClose);
  $("#iCancelX").addEventListener("click", insClose);
  $("#iDelete").addEventListener("click", insDelete);
  document.querySelectorAll("#i_priority button").forEach(b=>{
    b.addEventListener("click",()=>{ PRIO=Number(b.dataset.v); malujPrio(); });
  });
  $("#i_text").addEventListener("keydown", e=>{
    if(e.key==="Enter" && (e.metaKey||e.ctrlKey)) insSave();
  });
});
})();
