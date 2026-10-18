/* forma-cda.js — zakładka "Centrum CdA" w Formie. 2026-10-18.
   Dane: /api/forma/cda (qbot_web.py -> fitmodel/cda.py summary, tabela qbot_v2.ride_cda).
   Aero per rower (kanon dla QBota), opór toczenia, porównania w W przy wybranej prędkości,
   wykres CdA jazd (dymki, chipy rowerów, okres + własny zakres, przeciągnij = powiększ, dwuklik = cała skala), jakość danych. */
(function(){
"use strict";
const $ = s => document.querySelector(s);
const RHO = 1.2;
const COL = {Grail:"var(--blue,#4c8dd6)", Grizl:"#f4a261", Monster:"#9b7bd4", nieznany:"var(--muted)"};
const DASH = {Grail:"", Grizl:"6 4", Monster:"2 3", nieznany:"1 4"};
let D = null, SPEED = 30, PER = "90", ON = {}, ZOOM = null, loaded = false;

const fmt3 = v => v==null ? "—" : v.toFixed(3).replace(".", ",");
const fmt1 = v => v==null ? "—" : v.toFixed(1).replace(".", ",");
const dm = s => { if(!s) return ""; const p=s.split("-"); return p[2]+"."+p[1]; };
const dmy = s => { if(!s) return ""; const p=s.split("-"); return p[2]+"."+p[1]+"."+p[0]; };
const iso = d => d.toISOString().slice(0,10);
const watts = (dcda, kmh) => 0.5*RHO*dcda*Math.pow(kmh/3.6,3);
const esc = s => String(s==null?"":s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
const pill = st => {
  const m = {"pewne":["rgba(76,141,214,.18)","var(--blue,#4c8dd6)"], "niepewne":["rgba(244,162,97,.2)","var(--accent-ink,var(--accent))"],
             "możliwe":["rgba(244,162,97,.2)","var(--accent-ink,var(--accent))"], "bez różnicy":["var(--well)","var(--ink2)"],
             "za mało danych":["var(--well)","var(--muted)"]}[st] || ["var(--well)","var(--muted)"];
  return '<span style="font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:999px;background:'+m[0]+';color:'+m[1]+';white-space:nowrap">'+esc(st)+'</span>';
};

async function load(){
  if(loaded) return; loaded = true;
  $("#cda-bikes").innerHTML = '<div class="muted">ładuję…</div>';
  try{
    const r = await fetch("/api/forma/cda", {credentials:"same-origin", cache:"no-store"});
    if(!r.ok) throw new Error(r.status);
    D = await r.json();
  }catch(e){ $("#cda-bikes").innerHTML = '<div class="muted">błąd danych ('+esc(e.message||e)+')</div>'; loaded=false; return; }
  (D.bikes||[]).forEach(b => { ON[b.bike] = b.n_rides>0; });
  ON["nieznany"] = false;
  render();
}

function render(){
  $("#cda-upd").textContent = D.updated ? "przeliczone "+dmy(D.updated.slice(0,10))+", "+D.updated.slice(11,16) : "";
  bikes(); crr(); cmp(); aero(); chips(); chart(); quality();
}

function bikes(){
  const h = (D.bikes||[]).map(b => {
    const aw = b.cda!=null ? Math.round(watts(b.cda, SPEED)) : null;
    const m = (b.meters||[]).map(x => x.meter.replace("ant:","")+" od "+dm(x.from)).join(" → ");
    return '<div class="card" style="display:flex;flex-direction:column;gap:6px">'
      +'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><b style="font-size:16px">'+esc(b.bike)+'</b>'+pill(b.status)+'</div>'
      +'<div style="display:flex;align-items:baseline;gap:8px"><span class="muted" style="font-size:12.5px">CdA</span>'
      +'<span style="font-size:30px;font-weight:800;font-variant-numeric:tabular-nums">'+fmt3(b.cda)+'</span><span class="muted">m²</span></div>'
      +(b.cda!=null ? '<div style="font-size:13.5px;color:var(--ink2)">typowo '+fmt3(b.lo)+'–'+fmt3(b.hi)+' · powietrze przy '+SPEED+' km/h ≈ <b>'+aw+' W</b></div>' : '')
      +'<div class="muted" style="font-size:12.5px">'+b.n_rides+' jazd z '+'ostatnich 120 dni · '+b.n_windows+' odcinków · ostatnia jazda '+dmy(b.last_ride)+'</div>'
      +(m ? '<div class="muted" style="font-size:12.5px;border-top:1px solid var(--line);padding-top:6px">Miernik: '+esc(m)+'</div>' : '')
      +'</div>';
  }).join("");
  $("#cda-bikes").innerHTML = h || '<div class="muted">brak policzonych jazd</div>';
}

function crr(){
  const base = ((D.crr||[]).find(c => c.cat===1)||{}).crr;
  const src = s => s==="kotwica" ? "założony (kotwica)" : s==="liczony" ? "liczony z jazd" : '<span class="muted">'+esc(s)+'</span>';
  const rows = (D.crr||[]).map(c => '<tr><td>'+esc(c.label)+'</td><td class="num">'+(c.crr!=null?c.crr.toFixed(4).replace(".",","):"—")+'</td>'
    +'<td class="num">'+(c.crr!=null&&base!=null&&c.cat!==1?"+"+(c.crr-base).toFixed(4).replace(".",","):"—")+'</td>'
    +'<td>'+src(c.source)+'</td><td class="num">'+(c.n_windows||"—")+'</td>'
    +'<td class="num">'+(c.w25!=null?c.w25+" W":"—")+'</td></tr>').join("");
  $("#cda-crr").innerHTML = '<thead><tr><th>Nawierzchnia</th><th class="num">Crr</th><th class="num">vs asfalt</th><th>Skąd</th><th class="num">Odcinków</th><th class="num">Kosztuje przy 25 km/h</th></tr></thead><tbody>'+rows+'</tbody>';
}

function aero(){
  const host = $("#cda-aero"); if(!host) return;
  const A = (D.aero_field||[]).filter(a => !a.error);
  if(!A.length){ host.innerHTML = '<div class="muted">Brak jazd z zapisem pola AERO (zapis jest od QExt2 0.4.1, 17.10).</div>'; return; }
  host.innerHTML = A.slice().reverse().map(a => {
    const g = a.agree, diff = (a.field_cda_med!=null&&a.qbot_cda!=null) ? a.field_cda_med-a.qbot_cda : null;
    const ch = (a.changes||[]).map(c => '<span style="display:inline-block;margin:2px 10px 2px 0;font-variant-numeric:tabular-nums">km '+fmt1(c.km)+': <b style="color:'+(c.dw<0?"var(--blue,#4c8dd6)":"var(--accent-ink,var(--accent))")+'">'+(c.dw>0?"+":"")+String(c.dw).replace("-","−")+' W</b></span>').join("");
    return '<div style="border-bottom:1px solid var(--line);padding:10px 0">'
      +'<div style="display:flex;flex-wrap:wrap;gap:6px 16px;align-items:baseline"><b>'+dmy(a.d)+' · '+esc(a.bike||"?")+'</b>'
      +'<span class="muted" style="font-size:12.5px">pole pewne '+fmt1(a.share&&a.share["2"])+'% czasu · zbiera '+fmt1(a.share&&a.share["1"])+'% · brak warunków '+fmt1(a.share&&a.share["0"])+'%</span>'
      +'<a href="/raport-jazdy.html?ride='+encodeURIComponent(a.id)+'" style="font-size:12.5px">raport jazdy</a></div>'
      +'<div class="qs-tiles" style="margin:8px 0 6px">'
      +'<div class="qs-tile"><div class="v">'+a.n_changes+'</div><div class="l">wykrytych zmian</div></div>'
      +'<div class="qs-tile"><div class="v">'+fmt3(a.field_cda_med)+'</div><div class="l">CdA pola (mediana)</div><div class="s">QBot: '+fmt3(a.qbot_cda)+(diff!=null?' ('+(diff>0?"+":"")+fmt3(diff).replace("-","−")+')':'')+'</div></div>'
      +'<div class="qs-tile"><div class="v">'+(g&&g.r!=null?String(g.r).replace(".",","):"—")+'</div><div class="l">zgodność zmian</div><div class="s">'+(g?g.n+" wspólnych odcinków":"za mało wspólnych odcinków")+'</div></div>'
      +'</div>'
      +(ch?'<div style="font-size:13px">Zmiany pokazane przez pole: '+ch+'</div>':'<div class="muted" style="font-size:13px">Pole nie pokazało żadnej zmiany.</div>')
      +'</div>';
  }).join("") + '<div class="muted" style="font-size:12.5px;margin-top:8px">Zgodność zmian: 1 = pole idzie w górę i w dół razem z wyliczeniem QBota na tych samych 30-sekundowych odcinkach, 0 = brak związku. Różnica poziomu wynika m.in. z uproszczeń pola (stały opór toczenia 0,007, bez wiatru, masa +9 kg zamiast +14 kg).</div>';
}

function cmp(){
  const all = D.compare||[];
  const known = all.filter(c => c.d_cda!=null), few = all.filter(c => c.d_cda==null);
  const maxW = Math.max(10, ...known.map(c => Math.abs(watts(c.d_cda,SPEED))+2*Math.abs(watts(c.se,SPEED))));
  const pos = w => 50 + 50*Math.max(-1, Math.min(1, w/maxW));
  let h = known.map(c => {
    const w = watts(c.d_cda, SPEED), e = Math.abs(watts(c.se, SPEED));
    const col = w<0 ? "var(--blue,#4c8dd6)" : "var(--accent-ink,var(--accent))";
    const sign = (w>0?"+":"")+Math.round(w).toString().replace("-","−");
    return '<div style="display:grid;grid-template-columns:minmax(180px,2fr) minmax(160px,3fr) 76px 110px;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)">'
      +'<div><div style="font-weight:600">'+esc(c.item)+'</div><div class="muted" style="font-size:12.5px">'+esc(c.slot)+(c.bike?' · '+esc(c.bike):'')+' · '+c.n_with+' jazd z / '+c.n_without+' bez</div></div>'
      +'<div style="position:relative;height:20px;background:var(--well);border-radius:6px" title="przedział ±1 błąd">'
      +'<div style="position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--muted)"></div>'
      +'<div style="position:absolute;left:'+pos(w-e)+'%;width:'+(pos(w+e)-pos(w-e))+'%;top:7px;height:6px;border-radius:3px;background:'+col+';opacity:.35"></div>'
      +'<div style="position:absolute;left:'+pos(w)+'%;top:3px;width:14px;height:14px;margin-left:-7px;border-radius:50%;background:'+col+'"></div></div>'
      +'<div style="text-align:right;font-weight:800;font-size:17px;color:'+col+';font-variant-numeric:tabular-nums">'+sign+' W</div>'
      +'<div>'+pill(c.status)+'</div></div>';
  }).join("");
  if(!known.length) h = '<div class="muted" style="padding:10px 0">Jeszcze żadne porównanie nie ma po min. 5 jazd z daną rzeczą i bez niej.</div>';
  const fewH = few.length ? '<details style="margin-top:8px"><summary style="cursor:pointer;font-size:13.5px;color:var(--ink2)">Za mało danych: '+few.length+' rzeczy (potrzeba min. 5 jazd z i 5 bez)</summary>'
      +'<div style="font-size:13px;color:var(--ink2);line-height:1.6;margin-top:6px">'+few.map(c => esc(c.item)+' <span class="muted">('+c.n_with+'/'+c.n_without+')</span>').join(" · ")+'</div></details>' : '';
  const pos2 = '<div class="muted" style="font-size:12.5px;margin-top:8px">Pozycja (klamki / dolny chwyt / lemondka): '+esc((D.quality||{}).position||"")+'.</div>';
  $("#cda-cmp").innerHTML = '<div style="display:grid;grid-template-columns:minmax(180px,2fr) minmax(160px,3fr) 76px 110px;gap:12px;font-size:11.5px;color:var(--muted);padding-bottom:6px;border-bottom:1px solid var(--line)">'
    +'<span>Zmiana</span><span style="display:flex;justify-content:space-between"><span>mniej oporu</span><span>0</span><span>więcej oporu</span></span><span style="text-align:right">Watów</span><span>Pewność</span></div>'
    + h + fewH + pos2;
}

function chips(){
  const names = Object.keys(ON);
  $("#cda-chips").innerHTML = names.map(n => '<button type="button" class="tchip'+(ON[n]?' on':'')+'" data-b="'+esc(n)+'"><span class="tdot" style="background:'+COL[n]+'"></span>'+esc(n)+'</button>').join("");
  $("#cda-chips").querySelectorAll("button").forEach(b => b.addEventListener("click", () => { ON[b.dataset.b] = !ON[b.dataset.b]; chips(); chart(); }));
}

function range(){
  if(ZOOM) return ZOOM;
  const t = new Date();
  if(PER==="custom"){ const f=$("#cda-from").value, to=$("#cda-to").value; if(f&&to) return [f,to]; }
  if(PER==="30"||PER==="90"){ const f=new Date(t); f.setDate(f.getDate()-(+PER)); return [iso(f), iso(t)]; }
  if(PER==="sezon") return [t.getFullYear()+"-03-01", iso(t)];
  return [(D.quality&&D.quality.since)||"2026-01-01", iso(t)];
}

function chart(){
  const host = $("#cda-chart"); if(!host||!D) return;
  host.innerHTML = ""; host.style.position = "relative";
  const [a, b] = range();
  const pts = (D.points||[]).filter(p => ON[p.bike] && p.d>=a && p.d<=b);
  $("#cda-zoomreset").hidden = !ZOOM;
  if(!pts.length){ host.innerHTML = '<div class="muted" style="padding:20px 8px">brak jazd w tym okresie (albo wyłączone rowery)</div>'; return; }
  const t0 = Date.parse(a), t1 = Math.max(Date.parse(b), t0+86400000);
  const vs = pts.flatMap(p => [p.cda-p.se, p.cda+p.se]);
  let lo = Math.floor(Math.min(...vs)*20)/20, hi = Math.ceil(Math.max(...vs)*20)/20; if(hi-lo<0.1){ hi+=0.05; lo-=0.05; }
  const W = Math.max(320, Math.round(host.clientWidth||800)), H = 300, ml=48, mr=12, mt=10, mb=26, iw=W-ml-mr, ih=H-mt-mb;
  const X = d => ml + iw*(Date.parse(d)-t0)/(t1-t0), Y = v => mt + ih - ih*(v-lo)/(hi-lo);
  const NS="http://www.w3.org/2000/svg", svg=document.createElementNS(NS,"svg");
  svg.setAttribute("viewBox","0 0 "+W+" "+H); svg.style.cssText="width:100%;height:"+H+"px;display:block;touch-action:pan-y;user-select:none";
  svg.setAttribute("role","img"); svg.setAttribute("aria-label","CdA jazd w czasie");
  const mk=(t,at)=>{ const e=document.createElementNS(NS,t); for(const k in at) e.setAttribute(k,at[k]); svg.appendChild(e); return e; };
  for(let v=lo; v<=hi+1e-9; v+=0.05){ mk("line",{x1:ml,x2:ml+iw,y1:Y(v),y2:Y(v),stroke:"var(--line)","stroke-width":0.6});
    const tx=mk("text",{x:ml-6,y:Y(v)+3,"text-anchor":"end",fill:"var(--muted)","font-size":10.5}); tx.textContent=v.toFixed(2).replace(".",","); }
  const days=(t1-t0)/86400000, stepD = days>200?30:days>80?14:days>35?7:3;
  for(let t=t0; t<=t1; t+=stepD*86400000){ const d=iso(new Date(t)); const tx=mk("text",{x:X(d),y:H-8,"text-anchor":"middle",fill:"var(--muted)","font-size":10.5}); tx.textContent=dm(d); }
  const byBike = {};
  pts.forEach(p => (byBike[p.bike] = byBike[p.bike]||[]).push(p));
  Object.keys(byBike).forEach(k => {
    const s = byBike[k].sort((x,y)=>x.d<y.d?-1:1);
    if(s.length>=3){ // mediana krocząca z 5 jazd
      const md = s.map((p,i) => { const w=s.slice(Math.max(0,i-2), i+3).map(q=>q.cda).sort((x,y)=>x-y); return [p.d, w[Math.floor(w.length/2)]]; });
      mk("path",{d:md.map((m,i)=>(i?"L":"M")+X(m[0]).toFixed(1)+" "+Y(m[1]).toFixed(1)).join(" "),fill:"none",stroke:COL[k]||"var(--muted)","stroke-width":2.2,"stroke-dasharray":DASH[k]||""});
    }
    s.forEach(p => {
      mk("line",{x1:X(p.d),x2:X(p.d),y1:Y(p.cda-p.se),y2:Y(p.cda+p.se),stroke:COL[k]||"var(--muted)","stroke-width":1,opacity:.5});
      mk("circle",{cx:X(p.d),cy:Y(p.cda),r:Math.max(3,Math.min(7,2+Math.sqrt(p.n)/2.5)),fill:COL[k]||"var(--muted)",opacity:.9});
    });
  });
  const cur = mk("line",{x1:0,x2:0,y1:mt,y2:mt+ih,stroke:"var(--ink2)","stroke-width":0.8,visibility:"hidden"});
  const sel = mk("rect",{x:0,y:mt,width:0,height:ih,fill:"var(--accent)",opacity:.12,visibility:"hidden"});
  host.appendChild(svg);
  const tip = document.createElement("div");
  tip.style.cssText = "position:absolute;display:none;pointer-events:none;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:12.5px;line-height:1.45;box-shadow:0 4px 14px rgba(0,0,0,.25);z-index:5;max-width:280px";
  host.appendChild(tip);
  const toX = e => { const r=svg.getBoundingClientRect(); return (e.clientX-r.left)*W/r.width; };
  let drag = null;
  svg.addEventListener("pointerdown", e => { drag = toX(e); });
  svg.addEventListener("pointermove", e => {
    const x = toX(e);
    if(drag!=null && Math.abs(x-drag)>4){ sel.setAttribute("x",Math.min(x,drag)); sel.setAttribute("width",Math.abs(x-drag)); sel.setAttribute("visibility","visible"); tip.style.display="none"; return; }
    let best=null, bd=1e9; pts.forEach(p => { const dx=Math.abs(X(p.d)-x); if(dx<bd){bd=dx;best=p;} });
    if(!best || bd>40){ tip.style.display="none"; cur.setAttribute("visibility","hidden"); return; }
    cur.setAttribute("x1",X(best.d)); cur.setAttribute("x2",X(best.d)); cur.setAttribute("visibility","visible");
    const g = best.gear||{}, gl = Object.keys(g).map(k => esc(k==="wheels"?"koła":k)+": "+esc(g[k])).join("<br>");
    tip.innerHTML = "<b>"+dmy(best.d)+" · "+esc(best.bike)+"</b><br>CdA "+fmt3(best.cda)+" ± "+fmt3(best.se)
      +"<br>"+best.n+" odcinków · wiatr z jazdy "+fmt1(best.wind)+" m/s"+(best.spread!=null&&best.spread<0.3?" <span class=\"muted\">(mało kierunków)</span>":"")
      +(gl?"<div style=\"margin-top:4px;color:var(--ink2)\">"+gl+"</div>":"")
      +"<div style=\"margin-top:4px\"><a href=\"/raport-jazdy.html?ride="+encodeURIComponent(best.id)+"\" style=\"pointer-events:auto\">raport jazdy</a></div>";
    const r = host.getBoundingClientRect(), px = (X(best.d)/W)*r.width;
    tip.style.display="block"; tip.style.top="8px"; tip.style.left = (px>r.width/2 ? Math.max(0,px-tip.offsetWidth-14) : px+14)+"px";
  });
  const end = e => {
    if(drag==null) return; const x=toX(e), x0=drag; drag=null; sel.setAttribute("visibility","hidden");
    if(Math.abs(x-x0)>8){ const inv = px => iso(new Date(t0+(Math.max(ml,Math.min(ml+iw,px))-ml)/iw*(t1-t0))); ZOOM=[inv(Math.min(x,x0)), inv(Math.max(x,x0))]; chart(); }
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointerleave", () => { drag=null; sel.setAttribute("visibility","hidden"); tip.style.display="none"; cur.setAttribute("visibility","hidden"); });
  svg.addEventListener("dblclick", () => { ZOOM=null; chart(); });
}

function quality(){
  const q = D.quality||{};
  $("#cda-qtiles").innerHTML = [[q.rides_used, "jazd użytych"], [q.windows, "odcinków 30 s"], [q.rides_total, "jazd sprawdzonych"], [dmy(q.since), "dane od"]]
    .map(t => '<div class="qs-tile"><div class="v">'+esc(t[0]==null?"—":t[0])+'</div><div class="l">'+t[1]+'</div></div>').join("");
  const ex = (q.excluded||[]).map(x => '<tr><td>'+esc(x.reason)+'</td><td class="num">'+x.n+'</td></tr>').join("");
  $("#cda-excl").innerHTML = '<thead><tr><th>Dlaczego pominięte</th><th class="num">Jazd</th></tr></thead><tbody>'+(ex||'<tr><td class="muted" colspan="2">brak</td></tr>')+'</tbody>';
  const lst = (q.excluded_rides||[]).slice().reverse().map(x => '<div style="display:flex;gap:10px;font-size:13px;padding:3px 0;border-bottom:1px solid var(--line)"><span style="width:84px;color:var(--ink2)">'+dmy(x.d)+'</span><span style="width:80px">'+esc(x.bike||"?")+'</span><span>'+esc(x.reason)+'</span></div>').join("");
  $("#cda-exlist").innerHTML = lst;
  $("#cda-assume").innerHTML = (D.assumptions||[]).map(a => "<li>"+esc(a)+"</li>").join("");
}

function wire(){
  document.querySelectorAll("#cda-speed button").forEach(b => b.addEventListener("click", () => {
    SPEED = +b.dataset.v; document.querySelectorAll("#cda-speed button").forEach(x => x.classList.toggle("active", x===b)); if(D){ bikes(); cmp(); } }));
  document.querySelectorAll("#cda-per button").forEach(b => b.addEventListener("click", () => {
    PER = b.dataset.p; ZOOM = null; document.querySelectorAll("#cda-per button").forEach(x => x.classList.toggle("active", x===b));
    $("#cda-custom").style.display = PER==="custom" ? "" : "none"; if(PER!=="custom") chart(); }));
  $("#cda-go").addEventListener("click", () => { ZOOM=null; chart(); });
  $("#cda-zoomreset").addEventListener("click", () => { ZOOM=null; chart(); });
  window.addEventListener("resize", () => { if(D && !$("#p-cda").hidden) chart(); });
  const btn = document.querySelector('#tabs button[data-t="cda"]');
  if(btn) btn.addEventListener("click", () => setTimeout(load, 0));
  if(location.hash === "#cda") load();
}
if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire); else wire();
})();
