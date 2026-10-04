/* forma-stats.js — zakładka "Statystyki" w Forma & Wellness. v3
   Dane: /api/stats/rides (qbot_web.py). Okresy: tydzień/miesiąc kalendarzowy, YTD, własny.
   Wykres SVG: słupki grupowane, przełączane serie, oś Y lewa/prawa (max 2 jednostki). */
(function(){
"use strict";
const $ = s => document.querySelector(s);
const el = (t,c,h) => { const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.textContent=h; return e; };

const SPORT_PL = {cycling:"kolarstwo", gravel_cycling:"gravel", yoga:"joga",
  indoor_rowing:"wioślarz", walking:"spacer", strength_training:"siłownia"};
const spl = s => SPORT_PL[s] || s || "—";

const METRICS = [
  {id:"distance", lbl:"Dystans",       unit:"km",   col:"#3a86ff", val:b=>(b.distance_m||0)/1000},
  {id:"moving",   lbl:"Czas ruchu",    unit:"h",    col:"#2a9d8f", val:b=>(b.moving_s||0)/3600},
  {id:"elapsed",  lbl:"Czas całk.",    unit:"h",    col:"#7fb069", val:b=>(b.elapsed_s||0)/3600},
  {id:"elev",     lbl:"Przewyższenie", unit:"m",    col:"#e76f51", val:b=>(b.elevation_m||0)},
  {id:"count",    lbl:"Aktywności",    unit:"szt.", col:"#9d6b9e", val:b=>(b.count||0)}
];
let ACTIVE = new Set(["distance"]);
let LASTD = null;

let CUR = {preset:"30d", from:null, to:null, sport:""};

function iso(d){ const z=n=>String(n).padStart(2,"0"); return d.getFullYear()+"-"+z(d.getMonth()+1)+"-"+z(d.getDate()); }
function rangeFor(p){
  const today = new Date();
  if(p==="7d"){ const f=new Date(today); f.setDate(f.getDate()-((f.getDay()+6)%7)); const t=new Date(f); t.setDate(t.getDate()+6); return [iso(f), iso(t)]; }
  if(p==="30d"){ const f=new Date(today.getFullYear(),today.getMonth(),1); const t=new Date(today.getFullYear(),today.getMonth()+1,0); return [iso(f), iso(t)]; }
  if(p==="ytd"){ return [today.getFullYear()+"-01-01", iso(today)]; }
  return [CUR.from, CUR.to];
}

function fmtKm(m){ const km=(m||0)/1000; return km>=100 ? Math.round(km)+" km" : (Math.round(km*10)/10)+" km"; }
function fmtM(m){ return Math.round(m||0).toLocaleString("pl-PL")+" m"; }
function fmtH(s){
  s = s||0;
  const h = Math.floor(s/3600), min = Math.round((s%3600)/60);
  if(h>=100) return h+" h";
  return h>0 ? (h+" h "+String(min).padStart(2,"0")+" min") : (min+" min");
}
function fmtVal(v, unit){
  if(unit==="h"){ const h=Math.floor(v), m=Math.round((v-h)*60); return h>0?(h+"h"+(m?String(m).padStart(2,"0"):"")):(m+"min"); }
  if(unit==="km") return (v>=100?Math.round(v):Math.round(v*10)/10)+" km";
  if(unit==="m") return Math.round(v).toLocaleString("pl-PL")+" m";
  return Math.round(v)+" "+unit;
}
function bucketLabel(key, gran){
  if(gran==="month"){ const [y,m]=key.split("-");
    const N=["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"];
    return N[Number(m)-1]+" '"+y.slice(2); }
  if(gran==="week") return "tydz. "+key.slice(5);
  return key.slice(5);
}
function niceMax(v){
  if(v<=0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for(const k of [1,2,2.5,5,10]){ if(v <= k*p) return k*p; }
  return 10*p;
}

async function load(){
  const [from,to] = rangeFor(CUR.preset);
  if(!from || !to) return;
  let u = "/api/stats/rides?start="+from+"&end="+to;
  if(CUR.sport) u += "&sport="+encodeURIComponent(CUR.sport);
  let d;
  try{
    const r = await fetch(u,{credentials:"same-origin",cache:"no-store"});
    if(!r.ok) throw new Error(r.status);
    d = await r.json();
  }catch(e){
    $("#qs-tiles").innerHTML=""; $("#qs-tiles").appendChild(el("div","empty","błąd ładowania ("+e.message+")"));
    return;
  }
  LASTD = d;
  render(d);
}

function tile(label, value, sub){
  const t = el("div","qs-tile");
  t.appendChild(el("div","l",label));
  t.appendChild(el("div","v",value));
  if(sub) t.appendChild(el("div","s",sub));
  return t;
}

function toggleMetric(id){
  const m = METRICS.find(x=>x.id===id);
  if(ACTIVE.has(id)){
    if(ACTIVE.size>1) ACTIVE.delete(id);
  }else{
    const units = new Set([...ACTIVE].map(a=>METRICS.find(x=>x.id===a).unit));
    if(!units.has(m.unit) && units.size>=2){
      // max 2 jednostki — zdejmij serie najstarszej jednostki
      const firstUnit = METRICS.find(x=>ACTIVE.has(x.id)).unit;
      [...ACTIVE].forEach(a=>{ if(METRICS.find(x=>x.id===a).unit===firstUnit) ACTIVE.delete(a); });
    }
    ACTIVE.add(id);
  }
  if(LASTD) render(LASTD);
}

function metricPills(){
  const box = $("#qs-metrics"); box.innerHTML="";
  METRICS.forEach(m=>{
    const b = el("button",null,m.lbl);
    b.type="button";
    b.style.borderRadius="999px";
    if(ACTIVE.has(m.id)){ b.classList.add("active"); b.style.borderColor=m.col; b.style.color=m.col; }
    const dot=el("span"); dot.style.cssText="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:"+m.col+(ACTIVE.has(m.id)?"":";opacity:.35");
    b.prepend(dot);
    b.addEventListener("click",()=>toggleMetric(m.id));
    box.appendChild(b);
  });
}

function drawChart(d){
  const host = $("#qs-chart"); host.innerHTML="";
  host.style.cssText="display:block;height:auto;padding:8px 4px";
  const xl=$("#qs-xlab"); if(xl) xl.innerHTML="";
  const B = d.buckets||[];
  if(!B.length){ host.appendChild(el("div","empty","brak aktywności w tym okresie")); return; }
  const act = METRICS.filter(m=>ACTIVE.has(m.id));
  const units = [...new Set(act.map(m=>m.unit))]; // max 2
  const maxU = {};
  units.forEach(u=>{
    const vals = [];
    act.filter(m=>m.unit===u).forEach(m=>B.forEach(b=>vals.push(m.val(b))));
    maxU[u] = niceMax(Math.max(...vals, 0));
  });
  const W=760, H=230, ml=52, mr=(units.length>1?52:14), mt=10, mb=26;
  const iw=W-ml-mr, ih=H-mt-mb;
  const NS="http://www.w3.org/2000/svg";
  const svg=document.createElementNS(NS,"svg");
  svg.setAttribute("viewBox","0 0 "+W+" "+H);
  svg.style.cssText="width:100%;height:auto;display:block";
  const line=(x1,y1,x2,y2,col,wd)=>{ const l=document.createElementNS(NS,"line");
    l.setAttribute("x1",x1);l.setAttribute("y1",y1);l.setAttribute("x2",x2);l.setAttribute("y2",y2);
    l.setAttribute("stroke",col);l.setAttribute("stroke-width",wd||1);svg.appendChild(l); };
  const text=(x,y,s,anchor,col,size)=>{ const t=document.createElementNS(NS,"text");
    t.setAttribute("x",x);t.setAttribute("y",y);t.setAttribute("text-anchor",anchor||"middle");
    t.setAttribute("fill",col||"var(--muted)");t.setAttribute("font-size",size||10);
    t.textContent=s;svg.appendChild(t); return t; };
  // siatka + oś lewa (jednostka 1) i prawa (jednostka 2)
  const TICKS=4;
  for(let i=0;i<=TICKS;i++){
    const y = mt + ih - ih*i/TICKS;
    line(ml,y,ml+iw,y,"var(--line)",i===0?1.2:0.6);
    text(ml-6,y+3, fmtVal(maxU[units[0]]*i/TICKS, units[0]), "end", act.find(m=>m.unit===units[0]).col);
    if(units.length>1) text(ml+iw+6,y+3, fmtVal(maxU[units[1]]*i/TICKS, units[1]), "start", act.find(m=>m.unit===units[1]).col);
  }
  // słupki grupowane
  const n=B.length, slot=iw/n, gpad=Math.min(6, slot*0.15);
  const bw=Math.max(2,(slot-2*gpad)/act.length);
  B.forEach((b,bi)=>{
    act.forEach((m,mi)=>{
      const v=m.val(b), hpx=ih*(v/maxU[m.unit]);
      const x=ml+bi*slot+gpad+mi*bw, y=mt+ih-hpx;
      const r=document.createElementNS(NS,"rect");
      r.setAttribute("x",x); r.setAttribute("y",y);
      r.setAttribute("width",Math.max(1,bw-1)); r.setAttribute("height",Math.max(0,hpx));
      r.setAttribute("fill",m.col); r.setAttribute("opacity","0.85"); r.setAttribute("rx","1.5");
      const tt=document.createElementNS(NS,"title");
      tt.textContent=bucketLabel(b.label,d.granularity)+" — "+m.lbl+": "+fmtVal(v,m.unit)
        +"\n"+b.count+" akt. · "+fmtKm(b.distance_m)+" · ruch "+fmtH(b.moving_s)
        +" · całk. "+fmtH(b.elapsed_s)+" · ↑ "+fmtM(b.elevation_m);
      r.appendChild(tt); svg.appendChild(r);
    });
    // etykiety X (max ~14, co k-ta)
    const k=Math.ceil(n/14);
    if(bi%k===0) text(ml+bi*slot+slot/2, H-8, bucketLabel(b.label,d.granularity));
  });
  host.appendChild(svg);
}

function render(d){
  const T = d.totals || {};
  const tiles = $("#qs-tiles"); tiles.innerHTML="";
  tiles.appendChild(tile("Aktywności", String(T.count||0), CUR.sport?spl(CUR.sport):"wszystkie rodzaje"));
  tiles.appendChild(tile("Dystans", fmtKm(T.distance_m)));
  tiles.appendChild(tile("Czas ruchu", fmtH(T.moving_s)));
  tiles.appendChild(tile("Czas całkowity", fmtH(T.elapsed_s), "z przerwami"));
  tiles.appendChild(tile("Przewyższenie", fmtM(T.elevation_m), "wg Garmin"));
  const sel = $("#qs-sport");
  if(sel.options.length<=1 && (d.sports||[]).length){
    d.sports.forEach(s=>{ const o=el("option",null,spl(s)); o.value=s; sel.appendChild(o); });
  }
  $("#qs-chartttl").textContent = "Podokresy: "+granPL(d.granularity)+" · kliknij serie, by włączyć/wyłączyć (max 2 jednostki naraz)";
  metricPills();
  drawChart(d);
  fillTable($("#qs-bysport"), ["Rodzaj","Akt.","Dystans","Czas ruchu","Czas całk.","Przewyższenie"],
    (d.by_sport||[]).map(s=>[spl(s.sport), s.count, fmtKm(s.distance_m), fmtH(s.moving_s), fmtH(s.elapsed_s), fmtM(s.elevation_m)]));
  fillTable($("#qs-table"), [granPL(d.granularity,true),"Akt.","Dystans","Czas ruchu","Czas całk.","Przewyższenie"],
    (d.buckets||[]).slice().reverse().map(b=>[bucketLabel(b.label,d.granularity), b.count, fmtKm(b.distance_m), fmtH(b.moving_s), fmtH(b.elapsed_s), fmtM(b.elevation_m)]));
}

function granPL(g, head){
  if(g==="day") return head?"Dzień":"dziennie";
  if(g==="week") return head?"Tydzień":"tygodniowo";
  return head?"Miesiąc":"miesięcznie";
}

function fillTable(tbl, heads, rows){
  tbl.innerHTML="";
  const tr=el("tr"); heads.forEach((h,i)=>tr.appendChild(el("th",i>0?"num":null,h)));
  const th=el("thead"); th.appendChild(tr); tbl.appendChild(th);
  const tb=el("tbody");
  rows.forEach(r=>{ const t=el("tr"); r.forEach((c,i)=>t.appendChild(el("td",i>0?"num":null,String(c)))); tb.appendChild(t); });
  tbl.appendChild(tb);
}

function init(){
  const wrap = document.querySelector('.qtab-panel[data-qtab="Statystyki"]');
  if(!wrap) return;
  // pasek pigułek serii nad wykresem (tworzony raz)
  if(!$("#qs-metrics")){
    const bar = el("div","qs-ctl"); bar.id="qs-metrics"; bar.style.margin="8px 8px 0";
    const card = $("#qs-chart").parentElement;
    card.insertBefore(bar, $("#qs-chart"));
  }
  wrap.querySelectorAll(".qs-ctl button[data-p]").forEach(b=>{
    b.addEventListener("click",()=>{
      wrap.querySelectorAll(".qs-ctl button[data-p]").forEach(x=>x.classList.remove("active"));
      b.classList.add("active");
      CUR.preset = b.dataset.p;
      $("#qs-custom").style.display = CUR.preset==="custom" ? "" : "none";
      if(CUR.preset!=="custom") load();
    });
  });
  $("#qs-go").addEventListener("click",()=>{
    CUR.from = $("#qs-from").value; CUR.to = $("#qs-to").value;
    if(CUR.from && CUR.to) load();
  });
  $("#qs-sport").addEventListener("change",e=>{ CUR.sport=e.target.value; load(); });
  const [f,t]=rangeFor("30d"); $("#qs-from").value=f; $("#qs-to").value=t;
  load();
}
if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();
