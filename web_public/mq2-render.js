/* czas lokalny (strefa przegladarki) -- wspolne dla QBot lab */function qTsLocal(s,naiveUtc){if(!s)return"";var t=String(s).trim().replace(" ","T").replace(/\.\d+/,"");if(/[+-]\d\d$/.test(t))t+=":00";t=t.replace(/([+-]\d\d)(\d\d)$/,"$1:$2");if(!/(Z|[+-]\d\d:\d\d)$/i.test(t)){if(!naiveUtc)return t.slice(0,16).replace("T"," ");t+="Z";}var d=new Date(t);if(isNaN(d.getTime()))return String(s).slice(0,16);var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());}function qDateLocal(d){d=d||new Date();var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
// ModelQ v2 — sygnatura + forma. Zywe dane z /api/modelq2/data
// (qbot_v2.modelq2_signature + modelq2_xert_bench). Linia = MQ2, kropki = Xert benchmark.
// Tabela okien 90/30/7/1 z data.windows (zawsze wzgledem DZIS). Przycisk AKTUALIZACJA -> POST /api/modelq2/recompute.

const SERIES = [
  {key:"tp",  label:"TP",  unit:"W",  color:"#2a78d6"},
  {key:"hie", label:"HIE", unit:"kJ", color:"#c77dff"},
  {key:"pp",  label:"PP",  unit:"W",  color:"#e8833a"},
  {key:"ltp", label:"LTP", unit:"W",  color:"#5dcaa5"},
];
// tryb formy (tylko MQ2 -- 3 systemy zsumowane): CTL/ATL/TSB razem
const FORMA = {key:"forma", label:"Forma (CTL/ATL/TSB)", unit:""};
let ACTIVE = "tp";
let CHART = null;

function el(tag, cls){ const e=document.createElement(tag); if(cls) e.className=cls; return e; }
function fmtDay(d){ if(!d) return "—"; const [y,m,dd]=d.split("-"); return dd+"."+m+"."+y; }

async function load(start, end){
  const today=document.getElementById("today");
  today.textContent="Ładowanie…";
  let data;
  try{
    const url="/api/modelq2/data?start="+start+"&end="+end;
    const r=await fetch(url);
    if(!r.ok) throw new Error("HTTP "+r.status);
    data=await r.json();
  }catch(e){
    today.textContent="Błąd ładowania danych: "+e.message;
    return;
  }
  window._MQDATA=data;
  renderToday(data);
  renderWindows(data);
  renderChips();
  renderChart(data);
}

function renderToday(data){
  const box=document.getElementById("today");
  box.innerHTML="";
  const l=data.latest;
  if(!l){ box.textContent="Brak danych sygnatury w wybranym zakresie."; return; }

  // karta 1: sygnatura
  const grid=el("div","metrics");
  const items=[
    ["TP (próg)", l.tp, "W"],
    ["HIE (W')", l.hie, "kJ"],
    ["PP (moc szczyt.)", l.pp, "W"],
    ["LTP", l.ltp, "W"],
  ];
  for(const [k,v,u] of items){
    const m=el("div","metric");
    m.innerHTML='<div class="k">'+k+'</div><div class="v">'+(v==null?"—":v)+' <span class="vs">'+u+'</span></div>';
    grid.appendChild(m);
  }
  box.appendChild(grid);

  // karta 2: forma (CTL/ATL/TSB) -- wlasna logika MQ2 (3-system)
  if(l.ctl!=null || l.atl!=null || l.tsb!=null){
    const fgrid=el("div","metrics");
    const tsbColor = (l.tsb==null) ? "" : (l.tsb>=5 ? "var(--success)" : (l.tsb<=-10 ? "var(--danger)" : "var(--ink)"));
    const fitems=[
      ["CTL (fitness)", l.ctl, "", "var(--ink)"],
      ["ATL (zmęczenie)", l.atl, "", "var(--ink)"],
      ["TSB (forma)", (l.tsb!=null && l.tsb>0?"+":"")+(l.tsb==null?"—":l.tsb), "", tsbColor],
    ];
    for(const [k,v,u,col] of fitems){
      const m=el("div","metric");
      m.innerHTML='<div class="k">'+k+'</div><div class="v" style="color:'+col+'">'+(v==null?"—":v)+'</div>';
      fgrid.appendChild(m);
    }
    box.appendChild(fgrid);
  }

  const day=el("div","note");
  day.textContent="Sygnatura i forma na dzień "+fmtDay(l.day)+".";
  box.appendChild(day);

  const a=data.agreement;
  if(a && a.n_common){
    const ag=el("div","agree");
    ag.innerHTML='Zgodność sygnatury z Xert ('+a.n_common+' wspólnych dni): '
      +'HIE <b>'+(a.hie_kj??"—")+' kJ</b> · TP <b>'+(a.tp_w??"—")+' W</b> · PP <b>'+(a.pp_w??"—")+' W</b>'+((a.ltp_w!=null)?(' · LTP <b>'+a.ltp_w+' W</b> ('+(a.n_ltp||0)+' dni)'):'');
    box.appendChild(ag);
  }
}

// Tabela porownawcza: wiersze = wskazniki, kolumny = okna. Kazda komorka: MQ2 / Xert.
function renderWindows(data){
  const box=document.getElementById("windowsTable");
  if(!box) return;
  const w=data.windows;
  if(!w){ box.textContent="Brak danych okresowych."; return; }
  const cols=[["90","90 dni"],["30","30 dni"],["7","7 dni"],["1","1 dzień"]];
  const rows=[
    ["TP","tp","W",false],
    ["HIE","hie","kJ",true],
    ["PP","pp","W",false],
    ["LTP","ltp","W",false],
  ];
  const fnum=(v,dp)=> v==null ? "—" : (dp ? (Math.round(v*10)/10) : Math.round(v));
  let h='<table class="cmp"><thead><tr><th>Wskaźnik</th>';
  for(const [,lab] of cols) h+='<th>'+lab+'</th>';
  h+='</tr><tr><th></th>';
  for(const _ of cols) h+='<th>MQ2&nbsp;/&nbsp;Xert</th>';
  h+='</tr></thead><tbody>';
  for(const [lab,key,unit,dp] of rows){
    h+='<tr><td class="metric-name">'+lab+' <span class="unit">'+unit+'</span></td>';
    for(const [k] of cols){
      const mq=w[k].mq[key], xt=w[k].xert[key];
      h+='<td><span class="mq">'+fnum(mq,dp)+'</span> <span class="xt">/ '+fnum(xt,dp)+'</span></td>';
    }
    h+='</tr>';
  }
  h+='</tbody></table>';
  h+='<div class="note">Wartość w oknie = <b>średnia</b> z danego okresu. <b>MQ2</b> — z dziennej sygnatury liczonej z Twoich danych 1&nbsp;Hz. <b>Xert</b> — z benchmarku: TP/HIE/PP tylko z dni z jazdą, LTP z dziennych snapshotów. „—" = brak jazdy w tym oknie.</div>';
  box.innerHTML=h;
}

function renderChips(){
  const box=document.getElementById("checks");
  box.innerHTML="";
  const all=[...SERIES, FORMA];
  for(const s of all){
    const c=el("div","chip"+(s.key===ACTIVE?" on":""));
    c.textContent=s.label+(s.unit?(" ("+s.unit+")"):"");
    c.onclick=()=>{ ACTIVE=s.key; renderChips(); if(window._MQDATA) renderChart(window._MQDATA); };
    box.appendChild(c);
  }
}

function renderChart(data){
  const mq=data.mq||[], xert=data.xert||[];
  // LTP: Xert ze snapshotow (dzienne, gestsze) zamiast z benchmarku
  const xertSrc=(ACTIVE==="ltp")?(data.xert_ltp||[]):xert;

  // wspolna os dni
  const daySet=new Set();
  mq.forEach(r=>daySet.add(r.day));
  if(ACTIVE!=="forma") xertSrc.forEach(r=>daySet.add(r.day));
  const labels=[...daySet].sort();

  let ds;
  if(ACTIVE==="forma"){
    // 3 linie MQ2: CTL / ATL / TSB (ta sama skala)
    const mkMap=(k)=>{ const m={}; mq.forEach(r=>{ m[r.day]=r[k]; }); return m; };
    const ctl=mkMap("ctl"), atl=mkMap("atl"), tsb=mkMap("tsb");
    ds=[
      {label:"CTL (fitness)", data:labels.map(d=>d in ctl?ctl[d]:null), borderColor:"#2e8b57",
       backgroundColor:"#2e8b57", borderWidth:2.5, pointRadius:0, tension:.25, spanGaps:true, yAxisID:"y"},
      {label:"ATL (zmęczenie)", data:labels.map(d=>d in atl?atl[d]:null), borderColor:"#e8833a",
       backgroundColor:"#e8833a", borderWidth:2, pointRadius:0, tension:.25, spanGaps:true, yAxisID:"y"},
      {label:"TSB (forma)", data:labels.map(d=>d in tsb?tsb[d]:null), borderColor:"#7d7d7d",
       backgroundColor:"#7d7d7d", borderWidth:1.5, pointRadius:0, tension:.25, spanGaps:true, borderDash:[5,3], yAxisID:"y1"},
    ];
  }else{
    const s=SERIES.find(x=>x.key===ACTIVE);
    const mqMap={}; mq.forEach(r=>{ mqMap[r.day]=r[ACTIVE]; });
    const xMap={};  xertSrc.forEach(r=>{ xMap[r.day]=r[ACTIVE]; });
    const btMap={}; xert.forEach(r=>{ if(r.bt) btMap[r.day]=r[ACTIVE]; });
    ds=[
      {label:"ModelQ v2 — "+s.label, data:labels.map(d=>d in mqMap?mqMap[d]:null), borderColor:s.color,
       backgroundColor:s.color, borderWidth:2, pointRadius:0, tension:.25, spanGaps:true},
      {label:"Xert (benchmark)", data:labels.map(d=>d in xMap?xMap[d]:null), borderColor:"#9aa3ab",
       backgroundColor:"#9aa3ab", showLine:false, pointRadius:3, pointStyle:"circle", spanGaps:false},
      {label:"Przebicie (Xert)", data:labels.map(d=>d in btMap?btMap[d]:null), borderColor:"#a63d3d",
       backgroundColor:"#a63d3d", showLine:false, pointRadius:6, pointStyle:"rectRot", spanGaps:false},
    ];
  }

  const unit = ACTIVE==="forma" ? "" : SERIES.find(x=>x.key===ACTIVE).unit;
  const ctx=document.getElementById("mqChart");
  if(CHART) CHART.destroy();
  CHART=new Chart(ctx,{
    type:"line",
    data:{labels, datasets:ds},
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:"index", intersect:false, axis:"x"},
      scales:(ACTIVE==="forma")?{
        x:{ticks:{maxRotation:0, autoSkip:true, maxTicksLimit:10}},
        y:{position:"left", title:{display:true, text:"CTL / ATL"}},
        y1:{position:"right", grid:{drawOnChartArea:false}, title:{display:true, text:"TSB (forma)"}}
      }:{
        x:{ticks:{maxRotation:0, autoSkip:true, maxTicksLimit:10}},
        y:{title:{display:true, text:unit}}
      },
      plugins:{
        legend:{labels:{boxWidth:12, font:{size:11}}},
        tooltip:{
          mode:"index", intersect:false,
          callbacks:{
            title:(items)=>{ if(!items.length) return ""; const d=items[0].label; const [y,m,dd]=d.split("-"); return dd+"."+m+"."+y; },
            label:(it)=>{ const v=it.parsed.y; if(v==null) return null; const u=(ACTIVE==="forma"||ACTIVE==="tsb")?"":( (ACTIVE==="hie")?" kJ":" W"); return it.dataset.label+": "+(Math.round(v*100)/100)+u; }
          }
        }
      }
    }
  });
}

function isoAgo(days){ const d=new Date(); d.setDate(d.getDate()-days); return qDateLocal(d); }
function isoToday(){ return qDateLocal(); }

document.querySelectorAll(".rng").forEach(b=>{
  b.onclick=()=>{
    document.querySelectorAll(".rng").forEach(x=>x.classList.remove("active"));
    b.classList.add("active");
    const days=parseInt(b.dataset.days,10);
    const s=isoAgo(days), e=isoToday();
    document.getElementById("start").value=s;
    document.getElementById("end").value=e;
    load(s,e);
  };
});
document.getElementById("apply").onclick=()=>{
  const s=document.getElementById("start").value||isoAgo(180);
  const e=document.getElementById("end").value||isoToday();
  load(s,e);
};

// AKTUALIZACJA: wymus przeliczenie sygnatury, potem przeladuj biezacy zakres.
(function(){
  const btn=document.getElementById("recompute");
  if(!btn) return;
  btn.onclick=async()=>{
    const st=document.getElementById("updstatus");
    btn.disabled=true;
    if(st) st.textContent="Przeliczam sygnaturę…";
    try{
      const r=await fetch("/api/modelq2/recompute",{method:"POST"});
      if(!r.ok) throw new Error("HTTP "+r.status);
      const j=await r.json();
      const sig=(j.stats&&j.stats.signature)||{};
      const pub=(j.stats&&j.stats.published_days)||0;
      const nr=(j.stats&&j.stats.new_rides_xss)||0;
      if(st) st.textContent="Gotowe ("+j.elapsed_s+" s): "+(sig.stored||0)+" dni sygnatury, opublikowano "+pub+(nr?(", nowe jazdy: "+nr):"")+".";
      const s=document.getElementById("start").value||isoAgo(180);
      const e=document.getElementById("end").value||isoToday();
      await load(s,e);
    }catch(err){
      if(st) st.textContent="Błąd aktualizacji: "+err.message;
    }finally{
      btn.disabled=false;
    }
  };
})();

(function(){
  const s=isoAgo(180), e=isoToday();
  document.getElementById("start").value=s;
  document.getElementById("end").value=e;
  load(s,e);
})();
