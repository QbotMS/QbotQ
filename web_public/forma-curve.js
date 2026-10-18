/* forma-curve.js — zakładka "Krzywa mocy" w Forma & Wellness. 2026-10-18.
   Jak Strava: dwie krzywe do porównania (A i B), okresy: Ostatnie 6 tygodni / 3 miesiące / Cały rok / Własny / Brak,
   przełącznik W ↔ W/kg, oś czasu logarytmiczna 1 s … długość najdłuższej jazdy, dymek po najechaniu (obie wartości + data rekordu).
   Dane: /api/power/curve?start&end (qbot_web.py -> qbot_power_curve.py, tabela qbot_v2.ride_power_curve, liczona z 1 Hz). */
(function(){
"use strict";
const $ = s => document.querySelector(s);
const COL = {a:"#f4a261", b:"#4cc9f0"};
const KEY = [[5,"5 s"],[60,"1 min"],[300,"5 min"],[1200,"20 min"],[3600,"1 h"],[7200,"2 h"]];
let UNIT = "w", DATA = {a:null, b:null};

function iso(d){ const z=n=>String(n).padStart(2,"0"); return d.getFullYear()+"-"+z(d.getMonth()+1)+"-"+z(d.getDate()); }
function dmy(s){ if(!s) return ""; const p=s.split("-"); return p[2]+"."+p[1]+"."+p[0]; }
function fmtDur(s){
  if(s<60) return s+" s";
  if(s<3600){ const m=Math.floor(s/60), r=s%60; return r?(m+" min "+r+" s"):(m+" min"); }
  const h=Math.floor(s/3600), m=Math.round((s%3600)/60); return m?(h+" h "+m+" min"):(h+" h");
}
function fmtV(v){ return v==null?"—":(UNIT==="w"?Math.round(v)+" W":v.toFixed(2).replace(".",",")+" W/kg"); }

function options(sel, def){
  const y = new Date().getFullYear();
  const opts = [["none","Brak"],["6w","Ostatnie 6 tygodni"],["3m","Ostatnie 3 miesiące"]];
  for(let k=y;k>=2025;k--) opts.push(["y"+k,"Cały "+k]);
  opts.push(["custom","Niestandardowy zakres dat"]);
  sel.innerHTML="";
  opts.forEach(([v,t])=>{ const o=document.createElement("option"); o.value=v; o.textContent=t; if(v===def) o.selected=true; sel.appendChild(o); });
}
function rangeOf(side){
  const v=$("#pc-"+side).value, t=new Date();
  if(v==="none") return null;
  if(v==="6w"){ const f=new Date(t); f.setDate(f.getDate()-41); return [iso(f), iso(t)]; }
  if(v==="3m"){ const f=new Date(t); f.setMonth(f.getMonth()-3); return [iso(f), iso(t)]; }
  if(v[0]==="y"){ const y=v.slice(1); return [y+"-01-01", y+"-12-31"]; }
  const f=$("#pc-"+side+"-from").value, to=$("#pc-"+side+"-to").value;
  return (f&&to)?[f,to]:null;
}
async function loadSide(side){
  const cw=$("#pc-"+side+"-custom"); cw.style.display = $("#pc-"+side).value==="custom" ? "" : "none";
  const r=rangeOf(side);
  if(!r){ DATA[side]=null; draw(); return; }
  try{
    const res=await fetch("/api/power/curve?start="+r[0]+"&end="+r[1],{credentials:"same-origin",cache:"no-store"});
    if(!res.ok) throw new Error(res.status);
    DATA[side]=await res.json();
  }catch(e){ DATA[side]={points:[],rides:0,error:String(e.message||e)}; }
  draw();
}
function val(p){ return UNIT==="w"?p.w:p.wkg; }

function draw(){
  const host=$("#pc-chart"); if(!host) return;
  host.innerHTML=""; host.style.position="relative";
  const sides=["a","b"].filter(s=>DATA[s] && DATA[s].points && DATA[s].points.length);
  const note=$("#pc-note"), notes=[];
  ["a","b"].forEach(s=>{ const d=DATA[s]; if(!d) return;
    const lbl=$("#pc-"+s).selectedOptions[0].textContent;
    if(d.error) notes.push(lbl+": błąd ("+d.error+")");
    else notes.push(lbl+": "+d.rides+" jazd z pomiarem mocy"+(d.missing?(" · "+d.missing+" jazd jeszcze się dolicza — odśwież za chwilę"):"")); });
  note.textContent=notes.join(" · ");
  if(!sides.length){ host.appendChild(Object.assign(document.createElement("div"),{className:"empty",textContent:"brak danych mocy w wybranych okresach"})); table(); return; }
  const maxS=Math.max(...sides.map(s=>DATA[s].points[DATA[s].points.length-1].s));
  const maxV=Math.max(...sides.flatMap(s=>DATA[s].points.map(val).filter(v=>v!=null)));
  const W=Math.max(320,Math.round(host.clientWidth||800)), H=Math.round(Math.min(420,Math.max(260,W*0.42)));
  const ml=UNIT==="w"?52:46, mr=12, mt=10, mb=26, iw=W-ml-mr, ih=H-mt-mb;
  const step=UNIT==="w"?(maxV>1200?400:maxV>600?200:100):(maxV>12?4:maxV>6?2:1);
  const top=Math.ceil(maxV*1.03/step)*step;
  const lx=s=>ml+iw*Math.log(s)/Math.log(maxS), y=v=>mt+ih-ih*(v/top);
  const NS="http://www.w3.org/2000/svg", svg=document.createElementNS(NS,"svg");
  svg.setAttribute("viewBox","0 0 "+W+" "+H); svg.style.cssText="width:100%;height:"+H+"px;display:block;touch-action:pan-y";
  const mk=(t,a)=>{ const e=document.createElementNS(NS,t); for(const k in a) e.setAttribute(k,a[k]); svg.appendChild(e); return e; };
  for(let v=0; v<=top+1e-9; v+=step){
    mk("line",{x1:ml,x2:ml+iw,y1:y(v),y2:y(v),stroke:"var(--line)","stroke-width":v===0?1.2:0.6});
    const t=mk("text",{x:ml-6,y:y(v)+3,"text-anchor":"end",fill:"var(--muted)","font-size":10.5});
    t.textContent=UNIT==="w"?Math.round(v)+" W":String(v).replace(".",",");
  }
  [[1,"1 s"],[5,"5 s"],[15,"15 s"],[60,"1 min"],[300,"5 min"],[600,"10 min"],[1200,"20 min"],[3600,"1 h"],[7200,"2 h"],[10800,"3 h"],[14400,"4 h"],[18000,"5 h"],[21600,"6 h"],[28800,"8 h"]]
    .filter(([s])=>s<=maxS).forEach(([s,l])=>{
      mk("line",{x1:lx(s),x2:lx(s),y1:mt,y2:mt+ih,stroke:"var(--line)","stroke-width":0.5});
      const t=mk("text",{x:lx(s),y:H-8,"text-anchor":"middle",fill:"var(--muted)","font-size":10.5}); t.textContent=l; });
  sides.forEach(s=>{
    let dp=""; DATA[s].points.forEach(p=>{ const v=val(p); if(v==null) return; dp+=(dp?"L":"M")+lx(p.s).toFixed(1)+" "+y(v).toFixed(1)+" "; });
    mk("path",{d:dp,fill:"none",stroke:COL[s],"stroke-width":2.4,"stroke-linejoin":"round"});
  });
  // kursor + dymek
  const cur=mk("line",{x1:0,x2:0,y1:mt,y2:mt+ih,stroke:"var(--muted)","stroke-width":1,"stroke-dasharray":"3 3",visibility:"hidden"});
  const dots={}; sides.forEach(s=>{ dots[s]=mk("circle",{r:4.5,fill:COL[s],visibility:"hidden"}); });
  const tip=document.createElement("div");
  tip.style.cssText="position:absolute;pointer-events:none;display:none;background:var(--frame,#222);border:1px solid var(--line);border-radius:8px;padding:6px 8px;font-size:12px;line-height:1.45;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.25);z-index:5";
  const hit=mk("rect",{x:ml,y:mt,width:iw,height:ih,fill:"transparent"});
  const near=(pts,s)=>{ let b=null; pts.forEach(p=>{ if(val(p)==null) return; if(!b||Math.abs(Math.log(p.s)-Math.log(s))<Math.abs(Math.log(b.s)-Math.log(s))) b=p; }); return b; };
  function move(ev){
    const r=svg.getBoundingClientRect(), x=(ev.clientX-r.left)*W/r.width;
    if(x<ml||x>ml+iw){ out(); return; }
    const s=Math.exp((x-ml)/iw*Math.log(maxS));
    const ref=near(DATA[sides[0]].points,s); if(!ref) return;
    cur.setAttribute("x1",lx(ref.s)); cur.setAttribute("x2",lx(ref.s)); cur.setAttribute("visibility","visible");
    let html="<b>"+fmtDur(ref.s)+"</b>";
    ["a","b"].forEach(sd=>{ if(!dots[sd]) return;
      const p=DATA[sd].points.find(q=>q.s===ref.s);
      if(!p||val(p)==null){ dots[sd].setAttribute("visibility","hidden"); return; }
      dots[sd].setAttribute("cx",lx(p.s)); dots[sd].setAttribute("cy",y(val(p))); dots[sd].setAttribute("visibility","visible");
      const dt=UNIT==="w"?p.w_date:p.wkg_date, nm=UNIT==="w"?p.w_name:p.wkg_name;
      html+="<br><span style='color:"+COL[sd]+"'>●</span> "+fmtV(val(p))+" <span style='color:var(--muted)'>"+dmy(dt)+(nm?(" · "+String(nm).replace(/[<>&]/g,"")):"")+"</span>";
    });
    tip.innerHTML=html; tip.style.display="block";
    const px=lx(ref.s)*r.width/W, tw=tip.offsetWidth;
    tip.style.left=Math.min(Math.max(4,px+12), r.width-tw-4)+"px"; tip.style.top="8px";
  }
  function out(){ cur.setAttribute("visibility","hidden"); Object.values(dots).forEach(d=>d.setAttribute("visibility","hidden")); tip.style.display="none"; }
  hit.addEventListener("pointermove",move); hit.addEventListener("pointerdown",move); hit.addEventListener("pointerleave",out);
  host.appendChild(svg); host.appendChild(tip);
  table();
}

function table(){
  const t=$("#pc-table"); if(!t) return;
  const la=$("#pc-a").selectedOptions[0].textContent, lb=$("#pc-b").selectedOptions[0].textContent;
  const get=(s,d)=>{ const D=DATA[s]; if(!D||!D.points) return null; const p=D.points.find(q=>q.s===d); return p?val(p):null; };
  let h="<tr><th style='text-align:left'>Czas</th><th style='color:"+COL.a+"'>"+la+"</th><th style='color:"+COL.b+"'>"+lb+"</th><th>Różnica</th></tr>";
  KEY.forEach(([d,l])=>{
    const a=get("a",d), b=get("b",d);
    let diff="—"; if(a!=null&&b!=null&&b){ const pct=Math.round((a-b)/b*100); diff=(pct>0?"+":"")+pct+"%"; }
    h+="<tr><td>"+l+"</td><td>"+fmtV(a)+"</td><td>"+fmtV(b)+"</td><td>"+diff+"</td></tr>";
  });
  t.innerHTML=h;
}

function init(){
  if(!$("#pc-a")) return;
  options($("#pc-a"),"6w"); options($("#pc-b"),"y"+new Date().getFullYear());
  ["a","b"].forEach(s=>{
    $("#pc-"+s).addEventListener("change",()=>loadSide(s));
    $("#pc-"+s+"-from").addEventListener("change",()=>loadSide(s));
    $("#pc-"+s+"-to").addEventListener("change",()=>loadSide(s));
  });
  document.querySelectorAll("#pc-unit button").forEach(b=>b.addEventListener("click",()=>{
    document.querySelectorAll("#pc-unit button").forEach(x=>x.classList.remove("active"));
    b.classList.add("active"); UNIT=b.dataset.u; draw(); }));
  let lastW=0;
  new ResizeObserver(()=>{ const w=$("#pc-chart").clientWidth; if(w && Math.abs(w-lastW)>4){ lastW=w; draw(); } }).observe($("#pc-chart"));
  loadSide("a"); loadSide("b");
}
if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();
