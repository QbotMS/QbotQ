/* 2026-10-07: geometria trasy pobierana raz na strone (mapa + drugi odbiorca brali ja osobno) */
function _qGeo(id){var c=window.__qGeoC||(window.__qGeoC={});if(!c[id])c[id]=fetch("/api/routes/"+encodeURIComponent(id)+"/geometry").then(function(r){return r.ok?r.json():null;}).catch(function(){delete c[id];return null;});return c[id];}
window._qGeo=_qGeo;
/* QBot — render raportu trasy (jedno zrodlo wygladu).
   renderReport(data, mount): wstawia szkielet do `mount` i rysuje hero+mape+wykres.
   Dane (DATA) pochodza z /api/report/data. Ten plik NIE liczy danych - tylko rysuje. */
(function(){
"use strict";
let DATA=null;
let VIEW=null;

const SKELETON=`
<div class="rtopbar" id="r-topbar"><span class="rtb-name" id="r-name">—</span><span class="rtb-sub"><span class="when" id="r-when">—</span><span class="rtb-dot">·</span><span class="where" id="r-where">—</span></span><span class="meta" id="r-meta">—</span></div>
<header>
  <div class="wxchip" id="r-wx"></div>
  <div class="statsrow"><div class="hero" id="r-hero"></div><div class="breakstrip" id="r-break">—</div></div>
  <div class="cardextra" id="r-extra"></div>
</header>
<div class="r-tabpanel" data-rtab="mapa">
<div class="sec-h">Mapa trasy</div>
<div class="mapwrap"><div id="map" class="bw"></div><div class="map-ctl"><button type="button" id="mc-fit">Wyśrodkuj trasę</button><button type="button" id="mc-bw">Mapa: B/W</button></div></div>
<div class="map-note" id="r-mapnote"></div>
<div class="sec-h">Profil · wiatr · pogoda</div>
<div class="chartwrap" id="chartwrap">
  <svg id="chart" viewBox="0 0 1100 175" preserveAspectRatio="xMidYMid meet"></svg>
  <div class="chart-tip" id="chart-tip"></div>
</div>
</div>
<div class="r-tabpanel" data-rtab="szczegoly">
<div class="sec-h">Szczegóły trasy</div>
<div class="multi" id="r-multi">
  <nav class="multi-nav" id="multi-nav"></nav>
  <div class="multi-pane" id="multi-pane"></div>
</div>
</div>
<footer id="r-foot">—</footer>
<button type="button" class="qaside-tab qa-tab-legenda" data-qa="legenda" aria-label="Legenda">Legenda</button>
<button type="button" class="qaside-tab qa-tab-alerty" data-qa="alerty" aria-label="Alerty">Alerty</button>
<div class="qaside-backdrop"></div>
<aside class="qaside" id="report-aside" data-sec="legenda">
  <div class="qaside-head"><span class="qaside-title" id="qaside-title">Legenda</span><button class="qaside-x" type="button" aria-label="Zamknij">×</button></div>
  <div class="qaside-body">
    <div class="qaside-sec" data-sec="alerty"><div class="qa-h">Alerty dla trasy <span class="ad-count" id="r-alerts-count"></span></div><div class="alerts" id="r-alerts"></div></div>
    <div class="qaside-sec" data-sec="legenda"><div class="qa-h">Legenda</div><div class="chart-legend" id="chart-legend"></div><div class="chart-hint">Pas środka = wiatr: nad osią czołowy, pod — w plecy. Najedź po szczegóły. Zaznacz fragment wykresu = zoom wykresu i mapy; klik = cała trasa.</div></div>
  </div>
</aside>`;

const DNI=["niedziela","poniedziałek","wtorek","środa","czwartek","piątek","sobota"];
const MIES=["stycznia","lutego","marca","kwietnia","maja","czerwca","lipca","sierpnia","września","października","listopada","grudnia"];
const nf=(n,d=1)=>(n==null?"—":Number(n).toFixed(d).replace(".",","));
function hm(h){if(h==null)return "—";const m=Math.round(h*60);return (m/60|0)+" h "+String(m%60).padStart(2,"0");}
function pad2(n){return String(n).padStart(2,"0");}
const SCAT={1:"#1565c0",2:"#2e7d32",3:"#8bc34a",4:"#e07b1a",5:"#c2452f"};
const SLAT={1:"twarda szybka / asfalt",2:"dobry gravel / szuter",3:"zwykły gravel / grunt",4:"trudna / wolna",5:"ryzyko / niepewne"};
const ICO_PL={sun:"słonecznie",partcloud:"częśc. zachmurzenie",cloud:"zachmurzenie",rain:"deszcz/mżawka",storm:"burza",snow:"śnieg",fog:"mgła"};
const WIND_HEAD="#c2452f", WIND_TAIL="#3f7a4d", WIND_SIDE_TAIL="#9ccc5a", WIND_SIDE_HEAD="#eaa6c6";
const FEELS_COL="#2f7fd1";

function render(){
  if(DATA.day_mode){renderDayHead();return;}
  const r=DATA.route,s=DATA.start,t=DATA.time;
  document.getElementById("r-name").textContent=r.name||"(bez nazwy)";
  let when=(s.date||"");
  try{const d=new Date(s.date+"T"+(s.time||"00:00"));when=DNI[d.getDay()]+", "+d.getDate()+" "+MIES[d.getMonth()]+" "+d.getFullYear();}catch(e){}
  document.getElementById("r-when").textContent=when;
  const loc=[s.gmina,s.powiat,s.wojewodztwo].filter(Boolean).join(" · ");
  document.getElementById("r-where").textContent="start: "+(s.miejscowosc||"b/d")+(loc?" · "+loc:"");
  let metaTime="—";try{const [H,M]=(s.time||"0:0").split(":").map(Number);const fin=H*60+M+Math.round(t.total_h*60);metaTime=pad2(Math.floor(fin/60)%24)+":"+pad2(fin%60);}catch(e){}
  document.getElementById("r-hero").innerHTML=[
    {v:nf(r.distance_km,1),u:"km",l:"Dystans"},{v:"+"+Math.round(r.ascent_m),u:"m",l:"Podjazdy"},
    {v:hm(t.total_h),u:"",sub:(s.time||"—")+" → ~"+metaTime,l:"Czas (z postojami)"}
  ].map(m=>`<div class="m"><div><span class="v mono">${m.v}</span>${m.u?' <span class="u">'+m.u+'</span>':''}</div>${m.sub?'<div class="sub mono">'+m.sub+'</div>':''}<div class="l">${m.l}</div></div>`).join("");
  const longtxt=t.long_stops_min?hm(t.long_stops_min/60):"brak";
  document.getElementById("r-break").innerHTML=`<span><b>w ruchu</b> ${hm(t.moving_h)}</span><span><b>śr. brutto</b> ${t.speed_gross_kmh!=null?nf(t.speed_gross_kmh,1)+" km/h":"—"} (z postoj.)</span><span><b>śr. netto</b> ${t.speed_net_kmh!=null?nf(t.speed_net_kmh,1)+" km/h":"—"} (jazda)</span><span><b>postoje auto</b> ~${hm(t.stops_auto_min/60)} (${t.stops_count}×)</span><span><b>długie</b> ${longtxt}</span><span><b>dokładność</b> ±${t.accuracy_pct}%</span>`;
  (function(){var C=DATA.chart||{},seg=C.surface_cat||[];var tot=0,asf=0;seg.forEach(function(g){var L=(g.b-g.a);if(L>0){tot+=L;if(g.k===1)asf+=L;}});var ex=document.getElementById("r-extra");if(!ex)return;var HX="";if(tot>0){var ap=Math.round(asf/tot*100),up=100-ap;HX+='<div class="cx-sec"><div class="cx-h">Nawierzchnia</div>'+'<div class="cx-bar"><span class="cx-asf" style="width:'+ap+'%"></span><span class="cx-unp" style="width:'+up+'%"></span></div>'+'<div class="cx-legend"><span><i class="d asf"></i>asfalt '+ap+'%</span><span><i class="d unp"></i>nieutwardzone '+up+'%</span></div></div>';}var gs=t.speed_gross_kmh,nt=t.speed_net_kmh;HX+='<div class="cx-sec"><div class="cx-h">Pr\u0119dko\u015b\u0107</div><div class="cx-rows">'+'<div><span class="cx-k">brutto</span><span class="cx-v mono">'+(gs!=null?nf(gs,1)+" km/h":"\u2014")+'</span><span class="cx-note">z postojami</span></div>'+'<div><span class="cx-k">netto</span><span class="cx-v mono">'+(nt!=null?nf(nt,1)+" km/h":"\u2014")+'</span><span class="cx-note">jazda</span></div></div></div>';var _fm=(DATA.details&&DATA.details.forma)||DATA.forma||{};var xv=(_fm.vs_route&&_fm.vs_route.xss!=null)?Math.round(_fm.vs_route.xss):null;HX+='<div class="cx-sec"><div class="cx-h">Obci\u0105\u017cenie</div><div class="cx-xss"><span class="cx-v mono">'+(xv!=null?"~"+xv:"\u2014")+'</span><span class="cx-note">szac. XSS trasy</span></div></div>';ex.innerHTML=HX;})();
  document.getElementById("r-meta").innerHTML=`Źródło geometrii: <b>${r.source}</b> · ID trasy: <span class="mono">${r.id}</span>`+(r.version_modified?` · wersja z <b>${r.version_modified}</b>`:"");
  document.getElementById("r-foot").textContent="DATA = kontrakt generatora QBot (kod), nie model. WBGT = wskaźnik obciążenia cieplnego.";
}

function renderWx(){
  const wh=DATA.weather_head, el=document.getElementById("r-wx");
  if(!el)return;
  if(!wh){el.style.display="none";return;}
  const ico=`<svg class="wxi" viewBox="-9 -9 18 18" width="22" height="22">${glyph(wh.icon,0,0,6)}</svg>`;
  const p=[];
  if(wh.feels!=null)p.push("odczuwalna ~"+nf(wh.feels,0)+"°C");
  if(wh.comfort)p.push(wh.comfort);
  if(wh.precip_pl)p.push(wh.precip_pl);
  if(wh.wind_dir&&wh.wind_ms!=null)p.push("wiatr "+wh.wind_dir+" "+nf(wh.wind_ms,1)+" m/s");
  el.innerHTML=ico+"<span>"+p.join(" · ")+"</span>";
}
function cloud(cx,cy,s,col){return `<g fill="${col}"><ellipse cx="${cx}" cy="${cy+s*0.15}" rx="${s}" ry="${s*0.55}"/><circle cx="${cx-s*0.5}" cy="${cy}" r="${s*0.5}"/><circle cx="${cx+s*0.5}" cy="${cy-s*0.05}" r="${s*0.45}"/><circle cx="${cx}" cy="${cy-s*0.35}" r="${s*0.55}"/></g>`;}
function sun(cx,cy,s,col){let r="";for(let i=0;i<8;i++){const a=i*Math.PI/4;r+=`<line x1="${(cx+Math.cos(a)*s*0.95).toFixed(1)}" y1="${(cy+Math.sin(a)*s*0.95).toFixed(1)}" x2="${(cx+Math.cos(a)*s*1.4).toFixed(1)}" y2="${(cy+Math.sin(a)*s*1.4).toFixed(1)}" stroke="${col}" stroke-width="1.8" stroke-linecap="round"/>`;}return `<g>${r}<circle cx="${cx}" cy="${cy}" r="${s*0.72}" fill="${col}"/></g>`;}
function rain(cx,cy,s){let d="";for(let i=-1;i<=1;i++){const dx=cx+i*s*0.45;d+=`<line x1="${dx.toFixed(1)}" y1="${(cy+s*0.7).toFixed(1)}" x2="${(dx-s*0.18).toFixed(1)}" y2="${(cy+s*1.15).toFixed(1)}" stroke="#3f6f9a" stroke-width="1.8" stroke-linecap="round"/>`;}return cloud(cx,cy-s*0.15,s*0.82,"#9aa3ad")+d;}
function partcloud(cx,cy,s){return sun(cx-s*0.45,cy-s*0.4,s*0.5,"#e0a72e")+cloud(cx+s*0.2,cy+s*0.12,s*0.7,"#9aa3ad");}
function storm(cx,cy,s){return cloud(cx,cy-s*0.15,s*0.82,"#7a838c")+`<path d="M${cx-s*0.1} ${cy+s*0.45} l${-s*0.28} ${s*0.55} h${s*0.28} l${-s*0.18} ${s*0.5} l${s*0.6} ${-s*0.78} h${-s*0.3} l${s*0.24} ${-s*0.45} z" fill="#e0a72e"/>`;}
function snow(cx,cy,s){return cloud(cx,cy-s*0.15,s*0.82,"#9aa3ad")+`<text x="${cx}" y="${cy+s*1.15}" font-size="${s*0.9}" text-anchor="middle" fill="#3f6f9a">❄</text>`;}
function glyph(name,cx,cy,s){if(name==="sun"||name==="partcloud")return {sun,partcloud}[name](cx,cy,s,"#e0a72e");if(name==="cloud")return cloud(cx,cy,s,"#9aa3ad");const f={rain,storm,snow}[name];return f?f(cx,cy,s):cloud(cx,cy,s,"#9aa3ad");}

function windCat(al,cr){
  if(al==null) return null;
  const c=Math.abs(cr||0), mag=Math.hypot(al,c);
  if(mag<0.5) return null;
  const theta=Math.atan2(c,Math.abs(al))*180/Math.PI;
  if(theta>65) return null;
  return {head:al<0, side:theta>35, along:Math.abs(al), theta:theta};
}

function renderChart(){
  if(DATA.day_mode){renderDayChart();return;}
  const C=DATA.chart, svg=document.getElementById("chart");
  if(!C||!C.ele||!C.ele.length){document.getElementById("chartwrap").style.display="none";return;}
  const W=1100,ML=44,MR=28,PW=W-ML-MR,kmT=C.km_total;
  const _V0=(VIEW&&VIEW.a!=null)?Math.max(0,VIEW.a):0,_V1=(VIEW&&VIEW.b!=null)?Math.min(kmT,VIEW.b):kmT,_VS=(_V1-_V0)||kmT;
  const _KMSTEPS=[0.2,0.5,1,2,5,10,20,25,50], kmStep=_KMSTEPS.find(function(st){return _VS/st<=9;})||50;
  const _kdec=kmStep<1?1:0;
  const _PSC=(typeof window!=="undefined"&&window.__QBOT_PRINT_MODE)?2.6:1;
  const ICO_CY=10, WIN_Y=30,WIN_H=((typeof window!=="undefined"&&window.__QBOT_CHART_WINH)?window.__QBOT_CHART_WINH:120)*_PSC, BASE=WIN_Y+WIN_H, AX_Y=BASE;
  const x=km=>ML+((km-_V0)/_VS)*PW, yf=f=>BASE-f*WIN_H;
  const eMin=C.ele_min,eMax=C.ele_max,EFRAC=0.56;
  const yE=v=>BASE-((v-eMin)/((eMax-eMin)||1))*(EFRAC*WIN_H);
  const yZero=yf(0.66), WHALF=0.075*WIN_H;
  const yWlo=yf(0.80), yWhi=yf(0.98);
  const ws=C.weather.map(w=>w.wbgt);const fs=C.weather.map(w=>w.feels).filter(v=>v!=null);const wMin=Math.min(...ws,...fs),wMax=Math.max(...ws,...fs);
  const yW=v=>yWlo-((v-wMin)/((wMax-wMin)||1))*(yWlo-yWhi);
  const eleAt=km=>{const E=C.ele;if(km<=E[0][0])return E[0][1];if(km>=E[E.length-1][0])return E[E.length-1][1];for(let i=1;i<E.length;i++){if(E[i][0]>=km){const[k0,v0]=E[i-1],[k1,v1]=E[i];return v0+(v1-v0)*((km-k0)/((k1-k0)||1));}}return E[E.length-1][1];};
  const ptsBetween=(a,b)=>{const out=[[a,eleAt(a)]];for(const q of C.ele){if(q[0]>a&&q[0]<b)out.push(q);}out.push([b,eleAt(b)]);return out;};
  const surfAt=km=>{const A=C.surface_cat||[];for(const s of A){if(km>=s.a&&km<=s.b)return s;}return A[A.length-1];};
  const wxAt=km=>{for(const w of C.weather){if(km>=w.a&&km<=w.b)return w;}return km<C.weather[0].a?C.weather[0]:C.weather[C.weather.length-1];};
  const wmid=C.weather.map(w=>[(w.a+w.b)/2,w.wbgt]);
  const wbgtAt=km=>{if(km<=wmid[0][0])return wmid[0][1];if(km>=wmid[wmid.length-1][0])return wmid[wmid.length-1][1];for(let i=1;i<wmid.length;i++){if(wmid[i][0]>=km){const[k0,v0]=wmid[i-1],[k1,v1]=wmid[i];return v0+(v1-v0)*((km-k0)/((k1-k0)||1));}}return wmid[wmid.length-1][1];};
  const yCurve=km=>yW(wbgtAt(km));

  let P=[];
  P.push(`<defs><pattern id="rain-s" width="11" height="11" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="11" stroke="#5a86ad" stroke-width="1" stroke-opacity="0.5"/></pattern><pattern id="rain-m" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="#3f6f9a" fill-opacity="0.12"/><line x1="0" y1="0" x2="0" y2="6" stroke="#3f6f9a" stroke-width="1.4" stroke-opacity="0.7"/></pattern><pattern id="rain-h" width="3.6" height="3.6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="3.6" height="3.6" fill="#2f6ea0" fill-opacity="0.28"/><line x1="0" y1="0" x2="0" y2="3.6" stroke="#1c4468" stroke-width="1.6" stroke-opacity="0.95"/></pattern><clipPath id="pclip"><rect x="${ML}" y="0" width="${PW}" height="${BASE+1}"/></clipPath></defs>`);

  for(let k=Math.ceil(_V0/kmStep-1e-9)*kmStep;k<=_V1+1e-6;k+=kmStep){if(k<_V0-1e-6)continue;const gx=x(k).toFixed(1);P.push(`<line x1="${gx}" y1="${WIN_Y}" x2="${gx}" y2="${BASE}" stroke="var(--c-grid)" stroke-width="1"/>`);}

  P.push(`<text x="6" y="${yf(0.24)}" transform="rotate(-90 6 ${yf(0.24)})" font-size="10" fill="var(--c-axislbl)" text-anchor="middle" letter-spacing=".08em">WYS. m</text>`);
  P.push(`<text x="6" y="${yZero}" transform="rotate(-90 6 ${yZero})" font-size="10" fill="var(--c-axislbl)" text-anchor="middle" letter-spacing=".08em">WIATR m/s</text>`);
  P.push(`<text x="${W-4}" y="${(yWlo+yWhi)/2}" transform="rotate(90 ${W-4} ${(yWlo+yWhi)/2})" font-size="10" fill="var(--c-temp)" text-anchor="middle" letter-spacing=".08em">temp °C</text>`);

  P.push('<g clip-path="url(#pclip)">');
  (C.surface_cat||[]).forEach(sg=>{const pts=ptsBetween(sg.a,sg.b);let d="M "+x(sg.a).toFixed(1)+" "+BASE;for(const q of pts)d+=" L "+x(q[0]).toFixed(1)+" "+yE(q[1]).toFixed(1);d+=" L "+x(sg.b).toFixed(1)+" "+BASE+" Z";P.push(`<path d="${d}" fill="${SCAT[sg.k]||'#ccc'}" fill-opacity="0.9"/>`);});
  P.push('</g>');
  let dp="M "+x(C.ele[0][0]).toFixed(1)+" "+yE(C.ele[0][1]).toFixed(1);
  for(let i=1;i<C.ele.length;i++)dp+=" L "+x(C.ele[i][0]).toFixed(1)+" "+yE(C.ele[i][1]).toFixed(1);
  P.push(`<path d="${dp}" fill="none" stroke="var(--c-ele)" stroke-width="1.3" clip-path="url(#pclip)"/>`);
  P.push(`<text x="${ML-4}" y="${yE(eMax)+3}" font-size="9" fill="var(--c-axislbl)" text-anchor="end">${Math.round(eMax)}</text>`);
  P.push(`<text x="${ML-4}" y="${yE(eMin)-1}" font-size="9" fill="var(--c-axislbl)" text-anchor="end">${Math.round(eMin)}</text>`);

  const WD=C.wind||[];
  const wSmooth=(a,w)=>{const n=a.length,o=new Array(n),hh=(w-1)>>1;for(let q=0;q<n;q++){let s=0,c=0;for(let r=q-hh;r<=q+hh;r++){if(r>=0&&r<n){s+=a[r];c++;}}o[q]=s/c;}return o;};
  const AL=wSmooth(WD.map(p=>p[1]),5), CR=wSmooth(WD.map(p=>p[2]),5);
  const WMAX=Math.max(0.5,...WD.map(p=>Math.abs(p[1])));
  const wH=al=>Math.min(WHALF,Math.abs(al)/WMAX*WHALF);
  const wpt=WD.map((p,idx)=>{const wc=windCat(AL[idx],CR[idx]);if(!wc)return{x:x(p[0]),y:yZero,col:null,side:0};const h=wH(AL[idx]);return{x:x(p[0]),y:wc.head?yZero-h:yZero+h,col:wc.side?(wc.head?WIND_SIDE_HEAD:WIND_SIDE_TAIL):(wc.head?WIND_HEAD:WIND_TAIL),side:wc.head?1:-1};});
  [[WHALF,WMAX]].forEach(([off,val])=>{
    P.push(`<line x1="${ML}" y1="${(yZero-off).toFixed(1)}" x2="${W-MR}" y2="${(yZero-off).toFixed(1)}" stroke="var(--c-windline)" stroke-width="0.8" stroke-dasharray="2 3"/>`);
    P.push(`<line x1="${ML}" y1="${(yZero+off).toFixed(1)}" x2="${W-MR}" y2="${(yZero+off).toFixed(1)}" stroke="var(--c-windline)" stroke-width="0.8" stroke-dasharray="2 3"/>`);
    P.push(`<text x="${W-MR-2}" y="${(yZero-off-2).toFixed(1)}" font-size="9" fill="var(--c-axmut)" text-anchor="end">±${nf(val,1)} m/s</text>`);
  });
  let ri=0;
  while(ri<wpt.length){
    if(wpt[ri].col==null){ri++;continue;}
    let rj=ri;while(rj+1<wpt.length&&wpt[rj+1].col===wpt[ri].col&&wpt[rj+1].side===wpt[ri].side)rj++;
    const xl=(ri>0)?(wpt[ri-1].x+wpt[ri].x)/2:wpt[ri].x;
    const xr=(rj<wpt.length-1)?(wpt[rj].x+wpt[rj+1].x)/2:wpt[rj].x;
    const yl=(ri>0&&wpt[ri-1].col!=null&&wpt[ri-1].side===wpt[ri].side)?(wpt[ri-1].y+wpt[ri].y)/2:yZero;
    const yr=(rj<wpt.length-1&&wpt[rj+1].col!=null&&wpt[rj+1].side===wpt[ri].side)?(wpt[rj].y+wpt[rj+1].y)/2:yZero;
    let d=`M ${xl.toFixed(1)} ${yZero.toFixed(1)} L ${xl.toFixed(1)} ${yl.toFixed(1)}`;
    for(let k=ri;k<=rj;k++)d+=` L ${wpt[k].x.toFixed(1)} ${wpt[k].y.toFixed(1)}`;
    d+=` L ${xr.toFixed(1)} ${yr.toFixed(1)} L ${xr.toFixed(1)} ${yZero.toFixed(1)} Z`;
    P.push(`<path d="${d}" fill="${wpt[ri].col}" fill-opacity="0.9" clip-path="url(#pclip)"/>`);
    ri=rj+1;
  }
  P.push(`<line x1="${ML}" y1="${yZero}" x2="${W-MR}" y2="${yZero}" stroke="var(--c-wind0)" stroke-width="1"/>`);
  P.push(`<text x="${ML-4}" y="${(yZero-WHALF+3).toFixed(1)}" font-size="9" fill="#c2452f" text-anchor="end">czoło</text>`);
  P.push(`<text x="${ML-4}" y="${(yZero+WHALF).toFixed(1)}" font-size="9" fill="#3f7a4d" text-anchor="end">plecy</text>`);

  const rainPat=mm=>mm>=2?"rain-h":(mm>=0.5?"rain-m":(mm>0?"rain-s":null));
  C.weather.forEach(w=>{const pat=rainPat(w.mm);if(!pat)return;const mid=(w.a+w.b)/2;const d="M "+x(w.a).toFixed(1)+" "+WIN_Y+" L "+x(w.b).toFixed(1)+" "+WIN_Y+" L "+x(w.b).toFixed(1)+" "+yCurve(w.b).toFixed(1)+" L "+x(mid).toFixed(1)+" "+yCurve(mid).toFixed(1)+" L "+x(w.a).toFixed(1)+" "+yCurve(w.a).toFixed(1)+" Z";P.push(`<path d="${d}" fill="url(#${pat})" clip-path="url(#pclip)"/>`);});

  const wpts=[[C.weather[0].a,C.weather[0].wbgt]].concat(C.weather.map(w=>[(w.a+w.b)/2,w.wbgt])).concat([[C.weather[C.weather.length-1].b,C.weather[C.weather.length-1].wbgt]]);
  let wp="M "+x(wpts[0][0]).toFixed(1)+" "+yW(wpts[0][1]).toFixed(1);
  for(let i=1;i<wpts.length;i++)wp+=" L "+x(wpts[i][0]).toFixed(1)+" "+yW(wpts[i][1]).toFixed(1);
  P.push(`<path d="${wp}" fill="none" stroke="#d98a2b" stroke-width="2" clip-path="url(#pclip)"/>`);
  wpts.forEach(p=>{P.push(`<circle cx="${x(p[0]).toFixed(1)}" cy="${yW(p[1]).toFixed(1)}" r="2.3" fill="#d98a2b" clip-path="url(#pclip)"/>`);});
  const fpts=[[C.weather[0].a,C.weather[0].feels]].concat(C.weather.map(w=>[(w.a+w.b)/2,w.feels])).concat([[C.weather[C.weather.length-1].b,C.weather[C.weather.length-1].feels]]).filter(pp=>pp[1]!=null);
  if(fpts.length){
    let fp="M "+x(fpts[0][0]).toFixed(1)+" "+yW(fpts[0][1]).toFixed(1);
    for(let i=1;i<fpts.length;i++)fp+=" L "+x(fpts[i][0]).toFixed(1)+" "+yW(fpts[i][1]).toFixed(1);
    P.push(`<path d="${fp}" fill="none" stroke="${FEELS_COL}" stroke-width="1.8" clip-path="url(#pclip)"/>`);
    fpts.forEach(pp=>P.push(`<circle cx="${x(pp[0]).toFixed(1)}" cy="${yW(pp[1]).toFixed(1)}" r="2" fill="${FEELS_COL}" clip-path="url(#pclip)"/>`));
  }
  P.push(`<text x="${W-MR+4}" y="${(yW(wMax)+3).toFixed(1)}" font-size="9" fill="var(--c-temp)" text-anchor="start">${nf(wMax,1)}</text>`);
  P.push(`<text x="${W-MR+4}" y="${(yW(wMin)+3).toFixed(1)}" font-size="9" fill="var(--c-temp)" text-anchor="start">${nf(wMin,1)}</text>`);

  P.push('<g clip-path="url(#pclip)">');
  C.weather.forEach(w=>{const cx=x((w.a+w.b)/2);P.push(glyph(w.icon,cx,ICO_CY,6.5));if(w.rain!=null)P.push(`<text x="${cx.toFixed(1)}" y="${(ICO_CY+17).toFixed(1)}" font-size="9.5" fill="var(--c-time)" text-anchor="middle">${w.rain}%</text>`);});
  P.push('</g>');

  for(let k=Math.ceil((_V0+1e-6)/kmStep)*kmStep;k<_V1-1e-6;k+=kmStep){if(k<=_V0+1e-6)continue;P.push(`<text x="${x(k).toFixed(1)}" y="${AX_Y+12}" font-size="10" fill="var(--c-km)" text-anchor="middle">${nf(k,_kdec)}</text>`);}
  P.push(`<text x="${x(_V0).toFixed(1)}" y="${AX_Y+12}" font-size="10" fill="var(--c-km)" text-anchor="middle">${nf(_V0,_kdec)}</text>`);
  P.push(`<text x="${x(_V1).toFixed(1)}" y="${AX_Y+12}" font-size="10" fill="var(--c-km)" text-anchor="middle">${nf(_V1,_kdec)}</text>`);
  P.push(`<text x="2" y="${AX_Y+12}" font-size="9" fill="var(--c-axmut)" text-anchor="start">km</text>`);
  C.eta.forEach(([k,tt])=>{if(tt.endsWith(":00")||tt.endsWith(":30")){const _fw=tt.endsWith(":00")?"700":"400";P.push(`<text x="${x(k).toFixed(1)}" y="${AX_Y+24}" font-size="10" font-weight="${_fw}" fill="var(--c-time)" text-anchor="middle">${tt}</text>`);}});
  P.push(`<text x="2" y="${AX_Y+24}" font-size="9" fill="var(--c-axmut)" text-anchor="start">czas</text>`);
  (function(){
    var S=(DATA.details&&DATA.details.weather&&DATA.details.weather.slonce)||null;
    if(!S||!C.eta||C.eta.length<2)return;
    var EM=C.eta.map(function(e){var q=String(e[1]).split(":");return [e[0],(+q[0])*60+(+q[1])];});
    for(var i=1;i<EM.length;i++){while(EM[i][1]<EM[i-1][1])EM[i][1]+=1440;}
    var t0=EM[0][1],t1=EM[EM.length-1][1];
    var kmAt=function(mm){if(mm<t0||mm>t1)return null;for(var j=1;j<EM.length;j++){if(EM[j][1]>=mm){var k0=EM[j-1][0],m0=EM[j-1][1],k1=EM[j][0],m1=EM[j][1];return k0+(k1-k0)*((mm-m0)/((m1-m0)||1));}}return null;};
    [["\u2600","wsch\u00f3d",S.wschod,"#c2871a"],["\u263D","zach\u00f3d",S.zachod,"#5d6b96"]].forEach(function(it){
      if(!it[2])return;
      var q=String(it[2]).split(":"),mm=(+q[0])*60+(+q[1]);
      var km=kmAt(mm);if(km==null)km=kmAt(mm+1440);
      if(km==null||km<_V0-1e-6||km>_V1+1e-6)return;
      var px=x(km),gx=px.toFixed(1),lft=(px>(ML+PW*0.72));
      P.push('<line x1="'+gx+'" y1="'+WIN_Y+'" x2="'+gx+'" y2="'+BASE+'" stroke="'+it[3]+'" stroke-width="1.2" stroke-dasharray="4 3" stroke-opacity="0.85" clip-path="url(#pclip)"/>');
      P.push('<text x="'+(lft?(px-4):(px+4)).toFixed(1)+'" y="'+(WIN_Y+11)+'" font-size="10" fill="'+it[3]+'" text-anchor="'+(lft?"end":"start")+'" clip-path="url(#pclip)">'+it[0]+' '+it[1]+' '+it[2]+'</text>');
    });
  })();

  P.push(`<rect id="sel-band" x="0" y="${WIN_Y-2}" width="0" height="${BASE-WIN_Y+2}" fill="#3f6f9a" fill-opacity="0.14" stroke="#3f6f9a" stroke-opacity="0.55" stroke-width="1" style="display:none;pointer-events:none"/>`);
  P.push(`<line id="cur-line" x1="0" x2="0" y1="${WIN_Y-2}" y2="${BASE}" stroke="#1c2024" stroke-width="1" stroke-dasharray="3 3" style="display:none"/>`);
  P.push(`<circle id="cur-e" r="3.5" fill="#3f6f9a" stroke="#fff" stroke-width="1.5" style="display:none"/>`);
  P.push(`<circle id="cur-w" r="3.2" fill="#d98a2b" stroke="#fff" stroke-width="1.5" style="display:none"/>`);
  P.push(`<circle id="cur-f" r="3" fill="${FEELS_COL}" stroke="#fff" stroke-width="1.5" style="display:none"/>`);
  svg.setAttribute("viewBox","0 0 1100 "+(BASE+25));
  svg.innerHTML=P.join("");

  document.getElementById("chart-legend").innerHTML=
    '<div class="lg-grp"><div class="lg-h">Nawierzchnia</div><div class="lg-items">'+
    [1,2,3,4,5].map(k=>`<span class="it"><span class="sw" style="background:${SCAT[k]}"></span>${SLAT[k]}</span>`).join("")+
    `<span class="it"><span class="sw" style="background:var(--c-ele)"></span>wysokość</span>`+
    '</div></div>'+
    '<div class="lg-grp"><div class="lg-h">Wiatr</div><div class="lg-items">'+
    `<span class="it"><span class="sw" style="background:${WIND_HEAD}"></span>czołowy</span>`+
    `<span class="it"><span class="sw" style="background:${WIND_TAIL}"></span>w plecy</span>`+
    `<span class="it"><span class="sw" style="background:${WIND_SIDE_HEAD}"></span>boczny od czoła</span>`+
    `<span class="it"><span class="sw" style="background:${WIND_SIDE_TAIL}"></span>boczny w plecy</span>`+
    '</div></div>'+
    '<div class="lg-grp"><div class="lg-h">Pogoda</div><div class="lg-items">'+
    `<span class="it"><span class="sw" style="background:#d98a2b"></span>WBGT</span>`+
    `<span class="it"><span class="sw" style="background:${FEELS_COL}"></span>odczuwalna</span>`+
    `<span class="it"><span class="sw" style="background:repeating-linear-gradient(45deg,rgba(90,134,173,.7) 0 1px,transparent 1px 6px)"></span>deszcz słaby</span>`+
    `<span class="it"><span class="sw" style="background:repeating-linear-gradient(45deg,rgba(63,111,154,.75) 0 1.4px,transparent 1.4px 4px),rgba(63,111,154,.12)"></span>deszcz umiark.</span>`+
    `<span class="it"><span class="sw" style="background:repeating-linear-gradient(45deg,rgba(28,68,104,.95) 0 1.6px,transparent 1.6px 3px),rgba(47,110,160,.28)"></span>deszcz silny</span>`+
    '</div></div>';

  const ETA=C.eta.map(([k,tt])=>{const[H,M]=tt.split(":").map(Number);return[k,H*60+M];});
  try{const[H,M]=DATA.start.time.split(":").map(Number);ETA.push([kmT,H*60+M+Math.round(DATA.time.total_h*60)]);}catch(e){}
  const etaAt=km=>{let mm;if(km<=ETA[0][0])mm=ETA[0][1];else if(km>=ETA[ETA.length-1][0])mm=ETA[ETA.length-1][1];else{for(let i=1;i<ETA.length;i++){if(ETA[i][0]>=km){const[k0,m0]=ETA[i-1],[k1,m1]=ETA[i];mm=m0+(m1-m0)*((km-k0)/((k1-k0)||1));break;}}}mm=Math.round(mm);return pad2(Math.floor(mm/60)%24)+":"+pad2(mm%60);};
  const windAt=km=>{if(!WD.length)return null;if(km<=WD[0][0])return[WD[0][1],WD[0][2]];if(km>=WD[WD.length-1][0])return[WD[WD.length-1][1],WD[WD.length-1][2]];for(let i=1;i<WD.length;i++){if(WD[i][0]>=km){const[k0,a0,c0]=WD[i-1],[k1,a1,c1]=WD[i],t=(km-k0)/((k1-k0)||1);return[a0+(a1-a0)*t,c0+(c1-c0)*t];}}return[WD[WD.length-1][1],WD[WD.length-1][2]];};
  const windTxt=km=>{const w=windAt(km);if(!w)return "—";const wc=windCat(w[0],w[1]);if(!wc)return "bez wpływu (boczny)";const d=wc.side?(wc.head?"boczno-przedni":"boczno-tylny"):(wc.head?"czołowy":"w plecy");return d+" "+nf(wc.along,1)+" m/s";};
  const tip=document.getElementById("chart-tip"),wrap=document.getElementById("chartwrap");
  const cl=svg.querySelector("#cur-line"),ce=svg.querySelector("#cur-e"),cw=svg.querySelector("#cur-w"),cf=svg.querySelector("#cur-f");
  function move(clientX,clientY){
    const rect=svg.getBoundingClientRect(),wrapRect=wrap.getBoundingClientRect();
    let km=_V0+((clientX-rect.left)/rect.width*W-ML)/PW*_VS;km=Math.max(_V0,Math.min(_V1,km));
    const vx=x(km),ev=eleAt(km),wx=wxAt(km),sf=surfAt(km);
    cl.setAttribute("x1",vx);cl.setAttribute("x2",vx);cl.style.display="block";
    ce.setAttribute("cx",vx);ce.setAttribute("cy",yE(ev));ce.style.display="block";
    cw.setAttribute("cx",vx);cw.setAttribute("cy",yW(wx.wbgt));cw.style.display="block";
    if(wx.feels!=null){cf.setAttribute("cx",vx);cf.setAttribute("cy",yW(wx.feels));cf.style.display="block";}else{cf.style.display="none";}
    tip.style.display="block";
    tip.innerHTML=`<b>km ${nf(km,1)}</b> · <span class="k">~${etaAt(km)}</span><br><span class="k">wys.</span> <b>${Math.round(ev)} m</b> · <b>${sf?SLAT[sf.k]:'—'}</b>${sf&&sf.reason?`<br><span class="k" style="white-space:normal;display:inline-block;max-width:240px;font-size:11px">${sf.reason}</span>`:''}<br><span class="k">wiatr:</span> <b>${windTxt(km)}</b><br><span class="k">WBGT</span> <b>${nf(wx.wbgt,1)}°C</b> · <span class="k">odczuw.</span> <b style="color:${FEELS_COL}">${wx.feels!=null?nf(wx.feels,1)+"°C":"—"}</b> · ${ICO_PL[wx.icon]||wx.icon}${wx.rain!=null?` <span class="k">· ryzyko ${wx.rain}%</span>`:""}${wx.mm>0?` <span class="k">· ${nf(wx.mm,1)} mm</span>`:""}`;
    let left=(clientX-wrapRect.left);left=Math.max(60,Math.min(wrapRect.width-60,left));
    tip.style.left=left+"px";tip.style.top=(clientY-wrapRect.top)+"px";
    if(window.MAPX&&window.MAPX.ready)window.MAPX.markAtKm(km);
  }
  function hide(){cl.style.display="none";ce.style.display="none";cw.style.display="none";tip.style.display="none";if(window.MAPX&&window.MAPX.ready)window.MAPX.clearMark();}
  const band=svg.querySelector("#sel-band");
  function kmAt(cx){const rect=svg.getBoundingClientRect();let km=_V0+((cx-rect.left)/rect.width*W-ML)/PW*_VS;return Math.max(_V0,Math.min(_V1,km));}
  function bandTo(a,b){if(!band)return;const xa=x(Math.min(a,b)),xb=x(Math.max(a,b));band.setAttribute("x",xa.toFixed(1));band.setAttribute("width",Math.max(0,xb-xa).toFixed(1));band.style.display="block";}
  function bandHide(){if(band)band.style.display="none";}
  let selecting=false,kmStart=0;
  function selStart(cx){selecting=true;kmStart=kmAt(cx);}
  function selMove(cx){if(selecting)bandTo(kmStart,kmAt(cx));}
  function selEnd(cx){if(!selecting)return;selecting=false;const kmEnd=(cx!=null)?kmAt(cx):kmStart;const a=Math.min(kmStart,kmEnd),b=Math.max(kmStart,kmEnd);bandHide();if((b-a)>=0.3){VIEW={a:a,b:b};if(window.MAPX&&window.MAPX.ready&&window.MAPX.fitKm)window.MAPX.fitKm(a,b);renderChart();}else{VIEW=null;if(window.MAPX&&window.MAPX.ready&&window.MAPX.fitAll)window.MAPX.fitAll();renderChart();}}
  svg.addEventListener("mousemove",e=>{move(e.clientX,e.clientY);selMove(e.clientX);});
  svg.addEventListener("mousedown",e=>{selStart(e.clientX);});
  svg.addEventListener("mouseup",e=>{selEnd(e.clientX);});
  svg.addEventListener("mouseleave",e=>{hide();selEnd(e.clientX);});
  svg.addEventListener("touchstart",e=>{if(e.touches[0]){move(e.touches[0].clientX,e.touches[0].clientY);selStart(e.touches[0].clientX);}},{passive:true});
  svg.addEventListener("touchmove",e=>{if(e.touches[0]){move(e.touches[0].clientX,e.touches[0].clientY);selMove(e.touches[0].clientX);}},{passive:true});
  svg.addEventListener("touchend",e=>{hide();selEnd(e.changedTouches&&e.changedTouches[0]?e.changedTouches[0].clientX:null);});
}

function initMap(){
  if(DATA.day_mode){initDayMap();return;}
  if(window._qmap){try{window._qmap.remove();}catch(e){}window._qmap=null;}
  window.MAPX=null;
  const map=window._qmap=L.map("map",{scrollWheelZoom:true,zoomSnap:0.25,zoomDelta:0.5}).setView([52.2,21.0],7);
  const _tl=L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}).addTo(map);
  if(window.qTilesAttach)window.qTilesAttach(map,_tl);
  if(window.qMapCtl){var _mc=document.querySelector(".map-ctl");if(_mc)window.qMapCtl(_mc,map);}  // 2026-10-07: przyciski w prawym dolnym rogu (qmap-tiles.js)
  // --- Kwadraty (StatsHunters z14) + przycisk w pasku mapy ---
  (function setupTiles(){
    if(window.__QBOT_PRINT_MODE) return;
    var DEFAULT_ON = true;
    map.createPane("tiles");
    map.getPane("tiles").style.zIndex = 350;   // pod linia trasy (overlayPane=400)
    var grp = L.layerGroup([], {pane:"tiles"});
    var COL = {
      new:   {color:"#1a7f37", fill:"#2ea043", fo:0.38},
      keep:  {color:"#1f6feb", fill:"#388bfd", fo:0.22},
      owned: {color:"#8b949e", fill:"#8b949e", fo:0.12}
    };
    var ctl = document.querySelector(".map-ctl");
    var btn = document.getElementById("mc-tiles");
    var cnt = document.getElementById("tiles-cnt");
    if(ctl && !btn){
      btn = document.createElement("button");
      btn.type = "button"; btn.id = "mc-tiles";
      cnt = document.createElement("span");
      cnt.id = "tiles-cnt"; cnt.className = "map-ctl-info";
      ctl.appendChild(btn); ctl.appendChild(cnt);
    }
    var on = DEFAULT_ON;
    function paint(){ if(!btn) return; btn.textContent = "Kwadraty: " + (on ? "wł" : "wył"); if(on){ grp.addTo(map); } else { map.removeLayer(grp); } }
    if(btn){ btn.onclick = function(){ on = !on; paint(); }; }
    paint();
    (window.__QBOT_GUEST?Promise.reject("gosc"):fetch("/api/routes/"+encodeURIComponent(DATA.route.id)+"/tiles?margin=3"))
      .then(function(r){ return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function(d){
        (d.tiles||[]).forEach(function(t){
          if(t.status==="empty"||t.status==="owned") return;   // 2026-10-07: tylko kwadraty tej trasy (nowe / masz) - bez pustych i zdobytych poza trasa
          var s = COL[t.status]; if(!s) return;
          L.rectangle(t.bounds,{pane:"tiles",color:s.color,weight:1,fillColor:s.fill,fillOpacity:s.fo,interactive:false}).addTo(grp);
        });
        if(cnt) cnt.textContent = d.counts ? ("+"+d.counts.new+" nowych / "+d.counts.keep+" masz") : "";
        if(d.tile_error && cnt) cnt.textContent = "SH: "+d.tile_error;
        if(on) grp.addTo(map);
      })
      .catch(function(err){ if(cnt) cnt.textContent="kafle niedostępne: "+err; if(btn){ on=false; paint(); btn.disabled=true; } });
  })();
  setTimeout(function(){try{map.invalidateSize();}catch(e){}},60);
  (function(){var mapEl=document.getElementById("map");if(mapEl&&document.documentElement.classList.contains("theme-dark")){mapEl.classList.remove("bw");mapEl.classList.add("color");}var bF=document.getElementById("mc-fit"),bB=document.getElementById("mc-bw");if(bF)bF.onclick=function(){if(window.MAPX&&window.MAPX.fitAll)window.MAPX.fitAll();};if(bB){var _qLab=function(){var dk=document.documentElement.classList.contains("theme-dark"),nc=window.qTilesIsNightColor&&window.qTilesIsNightColor(),b=mapEl.classList.contains("bw");bB.textContent=dk?["Mapa: ciemna","Mapa: czarna","Mapa: szara","Mapa: kolor"][nc?(b?2:3):(b?1:0)]:(b?"Mapa: B/W":"Mapa: kolor");};bB.onclick=function(){var dk=document.documentElement.classList.contains("theme-dark");if(dk){var nc=window.qTilesIsNightColor&&window.qTilesIsNightColor(),b=mapEl.classList.contains("bw");/* noc: kolor -> szara -> ciemna -> czarna -> kolor */var st=nc?(b?2:3):(b?1:0);st=({3:2,2:0,0:1,1:3})[st];var nb=(st===1||st===2);mapEl.classList.toggle("bw",nb);mapEl.classList.toggle("color",!nb);if(window.qTilesNightColor)window.qTilesNightColor(st>=2);_qLab();return;}if(mapEl.classList.contains("bw")){mapEl.classList.remove("bw");mapEl.classList.add("color");}else{mapEl.classList.remove("color");mapEl.classList.add("bw");}_qLab();};document.addEventListener("qmapchange",_qLab);_qLab();}})();
  function hav(a,b){const R=6371,d2=Math.PI/180;const dLa=(b[0]-a[0])*d2,dLo=(b[1]-a[1])*d2,la1=a[0]*d2,la2=b[0]*d2;const x=Math.sin(dLa/2)**2+Math.cos(la1)*Math.cos(la2)*Math.sin(dLo/2)**2;return 2*R*Math.asin(Math.sqrt(x));}
  const surf=(DATA.chart&&DATA.chart.surface_cat)||[];
  const surfAt=km=>{for(const b of surf){if(km>=b.a&&km<=b.b)return b.k;}return surf.length?surf[surf.length-1].k:0;};
  ((DATA.route&&DATA.route.__geometry)?Promise.resolve({ok:true,json:function(){return {coordinates:DATA.route.__geometry};}}):_qGeo(DATA.route.id).then(function(j){return {ok:!!j,json:function(){return j;}};}))
    .then(r=>r.ok?r.json():Promise.reject(r.status))
    .then(d=>{if(!d.coordinates||!d.coordinates.length)throw "brak geometrii";
      const co=d.coordinates;const cum=[0];for(let i=1;i<co.length;i++)cum[i]=cum[i-1]+hav(co[i-1],co[i]);
      const kmT=(DATA.chart&&DATA.chart.km_total)||d.distance_km||cum[cum.length-1]||1;
      const scf=kmT/(cum[cum.length-1]||1);for(let i=0;i<cum.length;i++)cum[i]*=scf;
      let all=[];
      if(surf.length){let cur={c:surfAt(cum[0]),pts:[co[0]]};for(let i=1;i<co.length;i++){const c=surfAt(cum[i]);cur.pts.push(co[i]);if(c!==cur.c){all.push(cur);cur={c,pts:[co[i]]};}}all.push(cur);}
      else{all=[{c:"grunt",pts:co}];}
      let bounds=null;
      all.forEach(sg=>{L.polyline(sg.pts,{color:"#ffffff",weight:7,opacity:1,lineCap:"round",lineJoin:"round",interactive:false}).addTo(map);const pl=L.polyline(sg.pts,{color:SCAT[sg.c]||"#3f6f9a",weight:4,opacity:1,lineCap:"round",lineJoin:"round",interactive:false}).addTo(map);bounds=bounds?bounds.extend(pl.getBounds()):pl.getBounds();});
      L.circleMarker(co[0],{radius:7,color:"#fff",weight:2,fillColor:"#3f7a4d",fillOpacity:1}).addTo(map).bindTooltip("start");
      if(bounds)map.fitBounds(bounds,(window.__QBOT_PRINT_MODE?{padding:[20,20]}:(window.qFitPad?window.qFitPad(map):{paddingTopLeft:[320,100],paddingBottomRight:[40,230]})));
      window.__QBOT_MAP_READY=false;
      _tl.once("load",function(){window.__QBOT_MAP_READY=true;});
      setTimeout(function(){window.__QBOT_MAP_READY=true;},4000);
      document.getElementById("r-mapnote").textContent="Kolor trasy = nawierzchnia (jak na wykresie)"+(d.distance_km!=null?" · "+nf(d.distance_km,1)+" km":"");
      function latlonAtKm(km){km=Math.max(0,Math.min(kmT,km));if(km<=cum[0])return co[0];for(let i=1;i<cum.length;i++){if(cum[i]>=km){const t=(km-cum[i-1])/((cum[i]-cum[i-1])||1),a=co[i-1],b=co[i];return [a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t];}}return co[co.length-1];}
      let mark=null;
      window.MAPX={ready:true,fitAll:function(){if(bounds)map.fitBounds(bounds,(window.__QBOT_PRINT_MODE?{padding:[20,20]}:(window.qFitPad?window.qFitPad(map):{paddingTopLeft:[320,100],paddingBottomRight:[40,230]})));},markAtKm:function(km){const ll=latlonAtKm(km);if(!mark){mark=L.circleMarker(ll,{radius:6,color:"#fff",weight:2,fillColor:"#1c2024",fillOpacity:1,interactive:false}).addTo(map);}else{mark.setLatLng(ll);mark.setStyle({opacity:1,fillOpacity:1});}},fitKm:function(a,b){try{var pts=[latlonAtKm(a)];for(var i=0;i<co.length;i++){if(cum[i]>=a&&cum[i]<=b)pts.push(co[i]);}pts.push(latlonAtKm(b));map.fitBounds(L.latLngBounds(pts),Object.assign(window.qFitPad?window.qFitPad(map,30):{padding:[30,30]},{maxZoom:16}));}catch(e){}},clearMark:function(){if(mark)mark.setStyle({opacity:0,fillOpacity:0});}};
      /* 2026-10-08: mapa SAMA dopasowuje sie ponownie, gdy zmieni sie to, co na nia nachodzi (gorny pasek z nazwa trasy
         zawija sie do 2 wierszy po wczytaniu danych, panel, wykres) - dopoki uzytkownik sam nie przesunie/przyblizy mapy.
         "Wysrodkuj trase" przywraca automatyke. */
      if(!window.__QBOT_PRINT_MODE&&window.ResizeObserver){var _um=false,_rt=null,_mce=map.getContainer();
        ["mousedown","wheel","touchstart"].forEach(function(ev){_mce.addEventListener(ev,function(e){if(!(e.target.closest&&e.target.closest(".leaflet-control")))_um=true;},{passive:true});});
        var _fb=document.getElementById("mc-fit");if(_fb)_fb.addEventListener("click",function(){_um=false;});
        var _ro=new ResizeObserver(function(){if(_um)return;clearTimeout(_rt);_rt=setTimeout(function(){if(!_um&&window.MAPX)window.MAPX.fitAll();},150);});
        [".qhead","#r-topbar","header","#chartwrap"].forEach(function(s){var e=document.querySelector(s);if(e)_ro.observe(e);});}
      map.on("click",function(e){
        var cp=map.latLngToContainerPoint(e.latlng),best=-1,bestD=Infinity;
        for(var i=0;i<co.length;i++){var p=map.latLngToContainerPoint(L.latLng(co[i][0],co[i][1])),dx=p.x-cp.x,dy=p.y-cp.y,d=dx*dx+dy*dy;if(d<bestD){bestD=d;best=i;}}
        if(best>=0&&Math.sqrt(bestD)<=18){var km=cum[best],sg=null;for(var j=0;j<surf.length;j++){if(km>=surf[j].a&&km<=surf[j].b){sg=surf[j];break;}}if(sg){window.MAPX.fitKm(sg.a,sg.b);return;}}
        if(bounds)map.fitBounds(bounds,(window.__QBOT_PRINT_MODE?{padding:[20,20]}:(window.qFitPad?window.qFitPad(map):{paddingTopLeft:[320,100],paddingBottomRight:[40,230]})));
      });
    })
    .catch(err=>{document.getElementById("r-mapnote").textContent="Nie udało się wczytać geometrii trasy ("+err+").";});
}

const ALERT_SEV={"NO-GO":{c:"#c2452f",l:"NO-GO"},"ALARM":{c:"#e07b1a",l:"ALARM"},"FLAGA":{c:"#e0a72e",l:"FLAGA"}};
const ALERT_TYP={"upał":"UPAŁ","upal":"UPAŁ","deszcz":"DESZCZ","burza":"BURZA","zimno":"ZIMNO"};
function alertDetail(a){
  const t=a.typ;
  if(t==="upał"||t==="upal"){let s="WBGT do "+nf(a.wbgt_max,1)+"°C";if(a.powod)s+=" · "+a.powod;return s;}
  if(t==="deszcz"){let s="do "+nf(a.opad_max_mm,1)+" mm";if(a.prawdopod!=null)s+=" · ryzyko "+a.prawdopod+"%";if(a.trend)s+=" · "+a.trend;return s;}
  if(t==="burza"){let s="";if(a.przeczekaj_w&&a.przeczekaj_w.miejscowosc)s="przeczekaj w "+a.przeczekaj_w.miejscowosc+" (km "+nf(a.przeczekaj_w.km,1)+")";if(a.czekanie_min!=null)s+=(s?" · ":"")+"~"+a.czekanie_min+" min oczekiwania";return s||(a.opis||"");}
  if(t==="zimno"){let s="odczuwalna ~"+nf(a.utci_avg,1)+"°C";if(a.kategoria)s+=" · "+a.kategoria;return s;}
  return a.opis||a.powod||"";
}
function renderAlerts(){
  if(DATA.day_mode){var _t=document.querySelector(".qa-tab-alerty");if(_t)_t.classList.add("qa-off");return;}
  const el=document.getElementById("r-alerts");if(!el)return;
  const A=(DATA.alerts||[]);
  var _cnt=document.getElementById("r-alerts-count");if(_cnt)_cnt.textContent=A.length?("· "+A.length):"· brak";
  var _tab=document.querySelector(".qa-tab-alerty");if(_tab)_tab.classList.toggle("qa-off",!A.length);
  if(!A.length){el.innerHTML='<div class="alert-empty">Brak alertów pogodowych dla tej trasy.</div>';return;}
  el.innerHTML=A.map(function(a){
    const sv=ALERT_SEV[a.severity]||{c:"#7a838c",l:a.severity||"?"};
    const typ=ALERT_TYP[a.typ]||String(a.typ||"?").toUpperCase();
    const det=alertDetail(a);
    return '<div class="alert" style="border-left-color:'+sv.c+'">'+
      '<div class="alert-top"><span class="sev" style="background:'+sv.c+'">'+sv.l+'</span>'+
      '<span class="atyp">'+typ+'</span>'+
      '<span class="arange">km '+nf(a.km_od,1)+'–'+nf(a.km_do,1)+((a.eta_od||a.eta_do)?(' · '+(a.eta_od||"?")+'–'+(a.eta_do||"?")):'')+(a.minuty!=null?' · ~'+a.minuty+' min':'')+'</span></div>'+
      (det?'<div class="adet">'+det+'</div>':'')+
    '</div>';
  }).join("");
}
const MULTI=[{id:"nawierzchnia",label:"Nawierzchnia"},{id:"przewyzszenia",label:"Przewyższenia"},{id:"pogoda",label:"Pogoda"},{id:"forma",label:"Forma"},{id:"strategia",label:"Strategia jazdy"},{id:"zaopatrzenie",label:"Zaopatrzenie"},{id:"atrakcje",label:"Atrakcje"},{id:"sprzet",label:"Sprzęt"},{id:"udostepnij",label:"Udostępnij"}];
function _num(v,d){return v==null?"—":nf(v,d);}
function surfaceHTML(s){
  if(!s)return '<p class="multi-placeholder">Brak danych nawierzchni.</p>';
  var bars=(s.by_cat||[]).map(function(c){return '<div class="sbar"><span class="sbar-lab">'+(SLAT[c.k]||c.k)+'</span><span class="sbar-track"><span class="sbar-fill" style="width:'+c.pct+'%;background:'+(SCAT[c.k]||"#999")+'"></span></span><span class="sbar-val">'+nf(c.km,1)+' km · '+c.pct+'%</span></div>';}).join("");
  var risk=(s.risk&&s.risk.length)?('<div class="ms-sub">Odcinki ryzyka (kat. 5)</div><ul class="ms-list">'+s.risk.map(function(r){return '<li><b>km '+nf(r.a,1)+'–'+nf(r.b,1)+'</b> <span class="k">('+nf(r.km,1)+' km)</span>'+(r.comment?'<div class="risk-cmt">'+r.comment+'</div>':'')+'</li>';}).join("")+'</ul>'):'<div class="ms-ok">Brak odcinków ryzyka (kat. 5).</div>';
  return '<div class="ms-sum">Łącznie '+nf(s.total_km,1)+' km</div>'+bars+risk;
}
function inclineColor(g){
  if(g==null)return '#cccccc';
  if(g<-8)return '#2D58AF';
  if(g<-5)return '#4fc3f7';
  if(g<-2)return '#ffffff';
  if(g<2)return '#58c597';
  if(g<5)return '#079d78';
  if(g<8)return '#e7e021';
  if(g<11)return '#e59174';
  if(g<14)return '#e7693a';
  if(g<20)return '#c82425';
  return '#b222a3';
}
function hatchDefsSVG(){
  // deseny nawierzchni nieutwardzonej: siatka rombow (jak RouteGraph),
  // ciemna na jasnym polu / biala na ciemnym
  function pat(id,col,w){
    return '<pattern id="'+id+'" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
      +'<line x1="0" y1="0" x2="0" y2="10" stroke="'+col+'" stroke-width="'+w+'"/>'
      +'<line x1="0" y1="0" x2="10" y2="0" stroke="'+col+'" stroke-width="'+w+'"/></pattern>';
  }
  return '<svg class="climb-defs" width="0" height="0" aria-hidden="true"><defs>'
    +pat("qhchD","rgba(0,0,0,.50)",1.7)
    +pat("qhchL","rgba(255,255,255,.80)",1.7)
    +'</defs></svg>';
}
function hatchOn(hex){
  // jasnosc pola decyduje o kolorze deseniu (ciemny na zoltym, bialy na czerwonym)
  var h=String(hex||"#cccccc").replace("#","");
  if(h.length===3)h=h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
  var r=parseInt(h.substr(0,2),16),g=parseInt(h.substr(2,2),16),b=parseInt(h.substr(4,2),16);
  if(isNaN(r)||isNaN(g)||isNaN(b))return "qhchD";
  return (0.299*r+0.587*g+0.114*b)>140?"qhchD":"qhchL";
}
function isUnpavedCat(k){return k!=null&&k>1;}
function climbProfileSVG(segs,akm){
  if(!segs||!segs.length)return '';
  // dwa warianty plotna: waski (telefon) i szeroki (desktop). Czcionki dobrane tak,
  // by po przeskalowaniu do szerokosci kolumny mialy mniej wiecej rozmiar tekstu zakladki.
  var narrow=(typeof window!=="undefined"&&window.innerWidth<=640);
  var W=narrow?420:900, padTop=narrow?12:18, plotH=narrow?46:88;
  var fG=narrow?9:13, fA=narrow?8:12, minLab=narrow?16:24;
  var padL=10,padR=10,baseY=padTop+plotH,axisY=baseY+(narrow?11:15);
  var innerW=W-padL-padR;
  var xs=[0],ys=[0],cum=0,cx=0,i;
  for(i=0;i<segs.length;i++){
    var L=segs[i].len_m||0,g=(segs[i].grade==null?0:segs[i].grade);
    cx+=L;cum+=g/100*L;xs.push(cx);ys.push(cum);
  }
  var totLen=cx||1;
  var ymin=Math.min.apply(null,ys),ymax=Math.max.apply(null,ys),rng=(ymax-ymin)||1;
  function X(m){return padL+(m/totLen)*innerW;}
  function Y(v){return baseY-((v-ymin)/rng)*plotH;}
  var poly='',hatch='',line='M'+X(xs[0]).toFixed(1)+' '+Y(ys[0]).toFixed(1),labels='';
  for(i=0;i<segs.length;i++){
    var x0=X(xs[i]),x1=X(xs[i+1]),y0=Y(ys[i]),y1=Y(ys[i+1]);
    var col=inclineColor(segs[i].grade);
    var pts=x0.toFixed(1)+','+baseY+' '+x0.toFixed(1)+','+y0.toFixed(1)+' '+x1.toFixed(1)+','+y1.toFixed(1)+' '+x1.toFixed(1)+','+baseY;
    poly+='<polygon points="'+pts+'" fill="'+col+'" stroke="rgba(0,0,0,.12)" stroke-width=".4"/>';
    // desen TYLKO w polu nachylenia - ta sama figura, wiec odciety na krzywej
    if(isUnpavedCat(segs[i].sk))hatch+='<polygon points="'+pts+'" fill="url(#'+hatchOn(col)+')"/>';
    line+=' L'+x1.toFixed(1)+' '+y1.toFixed(1);
    if((x1-x0)>=minLab){var gg=segs[i].grade;labels+='<text class="cp-g" x="'+((x0+x1)/2).toFixed(1)+'" y="'+(padTop-4)+'" text-anchor="middle" font-size="'+fG+'">'+(gg==null?'':Math.round(gg)+'%')+'</text>';}
  }
  var bkm=(akm!=null)?(akm+totLen/1000):null;
  var ax='<text class="cp-ax" x="'+padL+'" y="'+axisY+'" font-size="'+fA+'">km '+(akm!=null?nf(akm,1):'')+'</text>'
        +'<text class="cp-ax" x="'+(W-padR)+'" y="'+axisY+'" font-size="'+fA+'" text-anchor="end">km '+(bkm!=null?nf(bkm,1):'')+'</text>';
  return '<svg class="climb-prof" viewBox="0 0 '+W+' '+(axisY+4)+'" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">'+poly+hatch+'<path d="'+line+'" fill="none" stroke="#3a3a3a" stroke-width="1.2"/>'+labels+ax+'</svg>';
}
function climbUnpavedPct(segs){
  if(!segs||!segs.length)return null;
  var tot=0,unp=0;
  for(var i=0;i<segs.length;i++){
    var L=segs[i].len_m||0;if(L<=0)continue;
    if(segs[i].sk==null)continue;
    tot+=L;if(isUnpavedCat(segs[i].sk))unp+=L;
  }
  if(tot<=0)return null;
  return Math.round(unp/tot*100);
}
function climbLegend(){
  var items=[['<2','#58c597'],['2\u20135','#079d78'],['5\u20138','#e7e021'],['8\u201311','#e59174'],['11\u201314','#e7693a'],['14\u201320','#c82425'],['\u226520','#b222a3']];
  var grad='<div class="climb-legend">'+items.map(function(it){return '<span class="cl-item"><span class="cl-sw" style="background:'+it[1]+'"></span>'+it[0]+'%</span>';}).join('')+'</div>';
  var surf='<div class="climb-legend"><span class="cl-item"><span class="cl-sw cl-hatch"></span>kreskowanie = nawierzchnia nieutwardzona (przewaga na danych 100 m)</span></div>';
  return grad+surf;
}
function chainHTML(ch){
  if(!ch||!ch.verdict)return '';
  return '<div class="chain-box"><div class="chain-h">Ca\u0142a trasa (podjazdy \u0142\u0105cznie)</div><div class="chain-v">'+ch.verdict+'</div></div>';
}
function climbsHTML(c){
  if(!c)return '<p class="multi-placeholder">Brak danych przewy\u017csze\u0144.</p>';
  var sum=chainHTML(c.chain)+'<div class="ms-sum">Podjazdy <b>+'+_num(c.ascent_m,0)+' m</b> \u00b7 Zjazdy <b>\u2212'+_num(c.descent_m,0)+' m</b> \u00b7 <b>'+(c.count||0)+'</b> podjazd\u00f3w</div>';
  if(!c.list||!c.list.length)return sum+'<div class="ms-ok">Trasa p\u0142aska \u2014 brak wydzielonych podjazd\u00f3w.</div>';
  var cards=c.list.map(function(x){
    var up=climbUnpavedPct(x.segments);
    var uptxt=(up==null)?'':(' \u00b7 nieutwardzone '+up+'%');
    var badge='';
    if(x.score!=null){
      var cls='cs'+(x.score>=0?'p':'m')+Math.abs(x.score);
      badge='<span class="climb-score '+cls+'" title="'+(x.score_why||'')+'">'+(x.score>0?'+':'')+x.score+' '+(x.score_label||'')+'</span> \u00b7 ';
    }else if(x.severity){
      badge=x.severity+' \u00b7 ';
    }
    var chip=(x.chain_mode)?('<span class="chain-pill '+(x.chain_mode==="atak"?"cp-atak":"cp-tempo")+'" title="plan na ten podjazd z symulacji ca\u0142ej trasy: W\u2032 na wej\u015bciu '+x.chain_wbal_in+'%, minimum w trakcie '+x.chain_wbal_min+'%">'+x.chain_mode.toUpperCase()+' \u00b7 W\u2032 '+x.chain_wbal_in+'\u2192'+x.chain_wbal_min+'%</span> \u00b7 '):'';
    var why=(x.score_why)?('<div class="climb-why">'+x.score_why+'</div>'):'';
    var hd='<div class="climb-hd">'+badge+chip+'<b>#'+x.i+'</b> \u00b7 km '+nf(x.a_km,1)+'\u2013'+nf(x.b_km,1)+' \u00b7 '+Math.round(x.length_m)+' m \u00b7 +'+nf(x.gain_m,0)+' m \u00b7 \u015br '+_num(x.avg_pct,1)+'% / max '+_num(x.max_pct,1)+'%'+uptxt+'</div>';
    return '<div class="climb-card">'+hd+why+climbProfileSVG(x.segments,x.a_km)+'</div>';
  }).join("");
  return hatchDefsSVG()+sum+cards+climbLegend();
}
function rainSummary(windows){
  if(!windows||!windows.length)return null;
  var best=windows[0];
  for(var i=1;i<windows.length;i++){if((windows[i].opad_mm||0)>(best.opad_mm||0))best=windows[i];}
  var mm=best.opad_mm||0;
  if(mm<=0.05)return "Bez istotnych opadów w prognozie.";
  var bits=["do "+nf(mm,1)+" mm"];
  if(best.opad_prob!=null)bits.push("~"+best.opad_prob+"%");
  if(best.km_od!=null&&best.km_do!=null)bits.push("km "+Math.round(best.km_od)+"–"+Math.round(best.km_do));
  if(best.okno)bits.push("ok. "+best.okno);
  return "Opady: "+bits.join(", ")+".";
}
function darkMinutes(S){
  try{
    var s=DATA.start,t=DATA.time;if(!s||!t||!s.time||t.total_h==null)return null;
    var p=String(s.time).split(":"),st=(+p[0])*60+(+p[1]);
    var en=st+Math.round(Number(t.total_h)*60);
    var toM=function(v){if(!v)return null;var q=String(v).split(":");return (+q[0])*60+(+q[1]);};
    var sr=toM(S.wschod),ss=toM(S.zachod);
    if(sr==null||ss==null)return null;
    var dark=0;
    if(st<sr)dark+=Math.min(en,sr)-st;
    if(en>ss)dark+=en-Math.max(st,ss);
    return Math.max(0,Math.round(dark));
  }catch(e){return null;}
}
function sunHTML(S){
  if(!S||(!S.wschod&&!S.zachod))return '';
  var bits=[];
  if(S.wschod)bits.push('\u2600 wsch\u00f3d <b>'+S.wschod+'</b>');
  if(S.zachod)bits.push('\u263D zach\u00f3d <b>'+S.zachod+'</b>');
  if(S.dzien_h!=null)bits.push('d\u0142ugo\u015b\u0107 dnia <b>'+nf(S.dzien_h,1)+' h</b>');
  var d=darkMinutes(S);
  if(d!=null)bits.push(d>0?('jazda po ciemku <b>~'+d+' min</b>'):'ca\u0142a jazda za dnia');
  return '<div class="ms-sub" style="margin-top:0">'+bits.join(' \u00b7 ')+'</div>';
}
function weatherHTML(w){
  if(!w)return '<p class="multi-placeholder">Brak danych pogody.</p>';
  var pk=w.peak?('<div class="ms-sum">Peak WBGT <b>'+nf(w.peak.wbgt_eff,1)+' °C</b> @ km '+nf(w.peak.km,1)+' ('+(w.peak.eta||"")+')'+(w.peak.teren?' · '+w.peak.teren:'')+'</div>'):'';
  var rs=rainSummary(w.windows);
  var rain=rs?('<div class="ms-sub" style="margin-top:0"><b>'+rs+'</b></div>'):'';
  var og=(w.ogolne&&w.ogolne.length)?('<ul class="wx-pts">'+w.ogolne.map(function(x){return '<li>'+x+'</li>';}).join("")+'</ul>'):'';
  var et=(w.etapy&&w.etapy.length)?('<div class="ms-sub">Etapy trasy</div><ul class="wx-etapy">'+w.etapy.map(function(e){return '<li><b>'+(e.naglowek||"")+'</b><div class="wx-etap-t">'+(e.tekst||"")+'</div></li>';}).join("")+'</ul>'):'';
  var viz=(typeof window.wxDayViz==="function")?window.wxDayViz(w,(typeof DATA!=="undefined"&&DATA)?DATA.chart:null):"";
  return viz+pk+sunHTML(w.slonce)+rain+og+et;
}
function resupplyHTML(p){
  if(!p) return '<p class="multi-placeholder">Brak POI dla tej trasy.</p>';
  var out='';
  var rs=p.resupply||[];
  out+='<div class="ms-sub">Zaopatrzenie i jedzenie <span class="k">(kluczowe punkty Q1/Q2/Q3)</span></div>';
  out+=rs.map(function(a){
    var hd='<div class="poi-area"><b>'+a.area+'</b> <span class="k">~km '+nf(a.q_km,0)+' \u00b7 kandydat\u00f3w w rejonie: '+a.total+'</span></div>';
    if(!a.picks||!a.picks.length) return hd+'<div class="poi-none k">brak (\u22641 km od trasy, w tym odcinku)</div>';
    var lis=a.picks.map(function(it){
      var loc=it.miejscowosc?' \u00b7 '+it.miejscowosc:'';
      var dd=(it.dist_m!=null)?' \u00b7 '+it.dist_m+' m od trasy':'';
      var hh=it.hours?' \u00b7 '+it.hours:'';
      var tag=(it.cat==='hard_resupply')?'sklep':'jedzenie';
      var oc=(it.off_center_km!=null&&Math.abs(it.off_center_km)>=1.5)?' <span class="k">('+(it.off_center_km>0?'+':'')+it.off_center_km+' km od \u015brodka)</span>':'';
      return '<li><span class="poi-tag">'+tag+'</span><b>km '+nf(it.km,1)+'</b>'+oc+' \u00b7 '+(it.name||'?')+'<span class="k">'+loc+dd+hh+'</span></li>';
    }).join('');
    return hd+'<ul class="ms-list">'+lis+'</ul>';
  }).join('');
  return out;
}
function attFetchBtnHTML(force){
  return '<div class="att-fetch-wrap" style="margin-top:10px"><button type="button" id="att-fetch" class="dlbtn" data-force="'+(force?'1':'0')+'">⬇ Pobierz atrakcje</button> <span id="att-status" class="k"></span></div>';
}
function _reportDataURL(){
  var g=function(id){var e=document.getElementById(id);return e?e.value:'';};
  var rid=g('f-route')||(DATA&&DATA.route&&DATA.route.id)||'';
  var nlong=parseInt(g('f-nlong')||'0',10)||0;
  var lmin=g('f-longmin')||'30';
  return '/api/report/data?route_id='+encodeURIComponent(rid)+'&date='+encodeURIComponent(g('f-date'))+'&time='+encodeURIComponent(g('f-time'))+'&long_stops='+nlong+'&long_stop_min='+lmin;
}
function _refreshAtrakcjePane(){
  var body=document.querySelector('#multi-pane .multi-body');
  var poi=DATA&&DATA.details?DATA.details.poi:null;
  if(body){ body.innerHTML=attractionsHTML(poi); wireAtrakcje(); }
}
function wireAtrakcje(){
  var b=document.getElementById('att-fetch'); if(!b)return;
  if(window.__QBOT_GUEST){b.style.display='none';return;}
  b.onclick=async function(){
    var st=document.getElementById('att-status');
    var force=(b.dataset&&b.dataset.force==='1');
    b.disabled=true; if(st)st.textContent=force?'Odświeżam z Google… to potrwa kilkanaście sekund.':'Pobieram atrakcje… to potrwa kilkanaście sekund (Wikipedia/Google).';
    try{
      var res=await fetch('/api/report/attractions/fetch?route_id='+encodeURIComponent(DATA.route.id)+(force?'&force=1':''),{method:'POST'});
      var j=await res.json().catch(function(){return null;});
      if(!res.ok){ throw new Error((j&&j.detail)||('HTTP '+res.status)); }
      if(j&&(j.status==='PUBLISHED'||j.status==='CACHED_KEPT')){
        if(st)st.textContent='Pobrano — odświeżam…';
        try{ var rd=await fetch(_reportDataURL()).then(function(r){return r.json();}); if(rd&&rd.details&&rd.details.poi){
          DATA.details=DATA.details||{};
          DATA.details.poi=rd.details.poi;
        } }catch(_){}
        _refreshAtrakcjePane();
      }else{
        var ss=(j&&j.source_status)||{}, sm=(j&&j.summary)||{};
        var srcTotal=(ss.wikipedia||0)+(ss.google||0)+(ss.wikidata||0)+(ss.osm||0);
        b.disabled=false;
        if(st)st.textContent='Znaleziono '+srcTotal+' źródeł, ale '+(sm.candidates||0)+' przeszło próg jakości — nic nie opublikowano dla tej trasy.';
      }
    }catch(e){ b.disabled=false; if(st)st.textContent='Błąd pobierania: '+(e&&e.message?e.message:e); }
  };
}
function _attrEsc(v){return String(v==null?'':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function _attrHttp(v){v=String(v||'').trim();return /^https?:\/\//i.test(v)?v:'';}
function attractionsHTML(p){
  if(!p) return '<p class="multi-placeholder">Brak danych POI dla tej trasy.</p>';
  var out='';
  var en=p.attractions?p.attractions.enabled:undefined;
  var raw=p.attractions?p.attractions.raw_total:undefined;
  if(en===false) return '<p class="multi-placeholder">Atrakcje nie są jeszcze pobrane dla tej trasy.</p>'+attFetchBtnHTML();
  var at=p.attractions||{items:[]};
  out+='<div class="ms-sub" style="margin-top:10px">Atrakcje <span class="k">(\u22642 km'+(at.total?', \u0142\u0105cznie '+at.total:'')+')</span></div>';
  if(!at.items||!at.items.length){ out+='<div class="poi-none k">'+((raw&&raw>0)?('pobrano '+raw+' atrakcji, ale żadna nie przeszła progu jakości'):'włączone, ale nie znaleziono atrakcji przy trasie')+'</div>'+attFetchBtnHTML(); }
  else out+='<ul class="ms-list">'+at.items.map(function(it){
    var loc=it.miejscowosc?' \u00b7 '+_attrEsc(it.miejscowosc):'';
    var dd=(it.dist_m!=null)?' \u00b7 '+it.dist_m+' m':'';
    var extract=String(it.extract||'').trim(); if(extract.length>360)extract=extract.slice(0,357).replace(/\s+\S*$/,'')+'…';
    var image=_attrHttp(it.image_url), wiki=_attrHttp(it.wiki);
    return '<li class="attr-card">'+(image?'<img class="attr-photo" loading="lazy" src="'+_attrEsc(image)+'" alt="">':'')+
      '<div class="attr-body"><b>km '+nf(it.km,1)+'</b> \u00b7 <strong>'+_attrEsc(it.name||'?')+'</strong><span class="k">'+loc+dd+'</span>'+
      (it.desc?'<div class="poi-desc">'+_attrEsc(it.desc)+'</div>':'')+
      (extract?'<div class="attr-extract">'+_attrEsc(extract)+'</div>':'')+
      (wiki?'<a class="attr-source" href="'+_attrEsc(wiki)+'" target="_blank" rel="noopener noreferrer">Źródło i pełny opis ↗</a>':'')+'</div></li>';
  }).join('')+'</ul>';
  out+='<div class="k" style="margin-top:8px">Pobrać atrakcje ponownie z Google (pobiera na nowo, kosztuje):</div>'+attFetchBtnHTML(true);
  return out;
}
var SURF_PL_PRESS={asfalt:"asfalt",szuter_gladki:"g\u0142adki szuter",szuter_luzny:"lu\u017any szuter",techniczny:"techniczny"};
function sprzetHTML(sp){
  if(!sp)return '<p class="multi-placeholder">Brak danych sprz\u0119towych.</p>';
  var out='';
  if(sp.tire){
    var mm=(sp.tire.front_mm!=null)?(sp.tire.front_mm===sp.tire.rear_mm?nf(sp.tire.front_mm,0)+' mm':nf(sp.tire.front_mm,0)+'/'+nf(sp.tire.rear_mm,0)+' mm'):'';
    out+='<div class="ms-sub">Opony</div><div class="spq"><b>'+(sp.tire.tire||"\u2014")+'</b>'+(mm?' \u00b7 '+mm:'')+'<div class="k">'+(sp.tire.wheelset||"")+'</div>'+(sp.tire.reason?'<div class="spq-why">'+sp.tire.reason+'</div>':'')+'</div>';
  }
  if(sp.pressure){
    var pr=sp.pressure;
    out+='<div class="ms-sub">Ci\u015bnienie <span class="k">(punkt startowy \u00b7 model '+(pr.model||"")+', '+_num(pr.rider_kg,0)+' kg)</span></div>';
    out+='<div class="press-main">Zalecane ('+(pr.surface_desc||SURF_PL_PRESS[pr.surface]||pr.surface)+'): <b>prz\u00f3d '+nf(pr.front_bar,1)+' bar</b> ('+pr.front_psi+' psi) \u00b7 <b>ty\u0142 '+nf(pr.rear_bar,1)+' bar</b> ('+pr.rear_psi+' psi)</div>';
    if(pr.all){
      var order=["asfalt","szuter_gladki","szuter_luzny","techniczny"];
      var rows=order.filter(function(k){return pr.all[k];}).map(function(k){var v=pr.all[k];return '<tr'+(k===pr.surface?' class="press-cur"':'')+'><td>'+(SURF_PL_PRESS[k]||k)+'</td><td>'+nf(v.front_bar,1)+' bar \u00b7 '+v.front_psi+' psi</td><td>'+nf(v.rear_bar,1)+' bar \u00b7 '+v.rear_psi+' psi</td></tr>';}).join("");
      out+='<table class="press-tab"><thead><tr><th>nawierzchnia</th><th>prz\u00f3d</th><th>ty\u0142</th></tr></thead><tbody>'+rows+'</tbody></table>';
    }
  }
  if(sp.hydration){
    var h=sp.hydration;
    out+='<div class="ms-sub">Nawodnienie</div><div class="spq">Zapotrzebowanie <b>~'+nf(h.demand_l,1)+' l</b> \u00b7 najd\u0142u\u017csza luka zaopatrzenia <b>~'+nf(h.gap_km,1)+' km</b>'+(h.rec?'<div class="spq-why">'+h.rec+'</div>':'')+'</div>';
  }
  out+='<div class="ms-sub">Ubi\u00f3r</div>';
  var cl=sp.clothing;
  function _ubiorUL(rz){return '<ul class="ubior-list">'+(rz||[]).map(function(it){var tb=(it.tryb&&/zabierz/i.test(it.tryb))?'<span class="ubior-tryb zabierz">zabierz</span>':'<span class="ubior-tryb">na sobie</span>';return '<li>'+tb+'<b>'+(it.typ||it.item||'')+'</b>'+(it.przyklad?' \u2014 <span class="k">'+it.przyklad+'</span>':'')+(it.uwaga?'<div class="ubior-uw">'+it.uwaga+'</div>':'')+'</li>';}).join('')+'</ul>';}
  if(cl&&typeof cl==="object"){
    if(cl.opis)out+='<div class="spq-why" style="margin-bottom:5px">'+cl.opis+'</div>';
    if(cl.zestawy&&cl.zestawy.length){
      out+=cl.zestawy.map(function(z,i){return '<div class="ubior-zestaw"><div class="ubior-zestaw-tt" style="font-weight:600;margin:9px 0 3px">'+(z.nazwa||('Zestaw '+(i+1)))+'</div>'+_ubiorUL(z.rzeczy)+'</div>';}).join('');
    } else if(cl.rzeczy&&cl.rzeczy.length){ out+=_ubiorUL(cl.rzeczy); }
  } else if(cl){ out+='<div class="spq">'+cl+'</div>'; }
  else { out+='<p class="multi-placeholder" style="margin:4px 0">Dob\u00f3r ubioru \u2014 generuje Albert (od\u015bwie\u017c, je\u015bli pusto).</p>'; }
  return out;
}
function formaHTML(f){
  if(!f||!f.source)return '<p class="multi-placeholder">Brak danych o formie.</p>';
  var glik=(f.glikogen_pct==null||f.glikogen_pct===0)?null:f.glikogen_pct;
  var rows=[
    ['FTP', _num(f.ftp,0)+' W'],
    ['W/kg (~'+_num(f.mass,0)+' kg)', _num(f.w_kg,2)],
    ['LTP (pr\u00f3g tlenowy)', f.ltp!=null?_num(f.ltp,0)+' W':'\u2014'],
    ['W\u2032 (zapas beztlenowy)', f.w_prime_kj!=null?_num(f.w_prime_kj,1)+' kJ':'\u2014'],
    ['Peak power', f.peak_w!=null?_num(f.peak_w,0)+' W':'\u2014'],
    ['Obci\u0105\u017cenie / zm\u0119czenie (CTL / ATL)', (f.training_load!=null?_num(f.training_load,0):'\u2014')+' / '+(f.recovery_load!=null?_num(f.recovery_load,0):'\u2014')],
    ['Glikogen', glik!=null?(_num(glik,0)+'% '+(f.glikogen_day?'<span class="k">(stan '+f.glikogen_day+')</span>':'')):'b/d']
  ];
  var tab='<table class="forma-tab"><tbody>'+rows.map(function(r){return '<tr><td>'+r[0]+'</td><td>'+r[1]+'</td></tr>';}).join('')+'</tbody></table>';
  var head='<div class="ms-sum">Forma <span class="k">('+f.source+(f.snapshot?' \u00b7 '+f.snapshot:'')+')</span></div>';
  var vr=f.vs_route||{};
  var vrows=[
    ['Obci\u0105\u017cenie (szac. XSS)', vr.xss!=null?'~'+vr.xss:'\u2014'],
    ['Zapotrzebowanie w\u0119gli', (vr.cho_g!=null?'~'+vr.cho_g+' g':'\u2014')+(vr.cho_g_h!=null?' ('+vr.cho_g_h+' g/h)':'')],
    ['Zapotrzebowanie p\u0142yn\u00f3w', vr.fluid_l!=null?'~'+_num(vr.fluid_l,1)+' l':'\u2014'],
    ['Rezerwa W\u2032 na podjazdach', vr.wprime_txt||'\u2014']
  ];
  var vtab='<table class="forma-tab"><tbody>'+vrows.map(function(r){return '<tr><td>'+r[0]+'</td><td>'+r[1]+'</td></tr>';}).join('')+'</tbody></table>';
  var wy='';
  var wd=f.wykonalnosc_dane||null,wo=f.wykonalnosc||null;
  if(wo&&wo.werdykt){
    var wl=(wd&&wd.walls&&wd.walls[0])?wd.walls[0]:{};
    var cc=(wd&&wd.ceilings)?wd.ceilings:{};
    var COL={green:'#3f7a4d',yellow:'#c2871a',red:'#c2452f'};
    var dot=wl.color?('<span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:'+(COL[wl.color]||'#888')+';margin-right:6px"></span>'):'';
    var wrows=[
      ['Obci\u0105\u017cenie tej trasy (szac. XSS)', vr.xss!=null?('~'+vr.xss+(wl.label?' \u00b7 '+wl.label:'')):'\u2014'],
      ['Tw\u00f3j rekord jednego dnia', cc.day_demonstrated!=null?('~'+Math.round(cc.day_demonstrated)+' XSS'):'\u2014'],
      ['\u015aciana metaboliczna (1 dzie\u0144)', cc.day_metabolic!=null?('~'+Math.round(cc.day_metabolic)+' XSS'):'\u2014'],
      ['Forma na dzie\u0144 jazdy (prognoza CTL)', (wd&&wd.projected_ctl!=null)?_num(wd.projected_ctl,1):'\u2014'],
      ['Zapas/zm\u0119czenie po je\u017adzie (TSB)', (wd&&wd.simulation&&wd.simulation.tsb_end!=null)?_num(wd.simulation.tsb_end,1):'\u2014']
    ];
    var wtab='<table class="forma-tab"><tbody>'+wrows.map(function(r){return '<tr><td>'+r[0]+'</td><td>'+r[1]+'</td></tr>';}).join('')+'</tbody></table>';
    var pts=(wo.punkty&&wo.punkty.length)?('<ul class="wx-pts">'+wo.punkty.map(function(z){return '<li>'+z+'</li>';}).join('')+'</ul>'):'';
    wy='<div class="ms-sub">Wykonalno\u015b\u0107'+((wd&&wd.departure)?(' <span class="k">(na '+wd.departure+')</span>'):'')+'</div>'
      +'<div class="ms-sum">'+dot+wo.werdykt+'</div>'+pts+wtab;
  }
  return head+tab+'<div class="ms-sub">Ta trasa kontra forma</div>'+vtab+wy;
}
function strategiaHTML(s){
  if(!s)return '<p class="multi-placeholder">Brak strategii (generuje ją Albert \u2014 od\u015bwie\u017c, je\u015bli pusto).</p>';
  var out='';
  if(s.calosc)out+='<div class="strat-all">'+s.calosc+'</div>';
  var et=s.etapy||[];
  if(et.length){
    out+=et.map(function(e){
      return '<div class="strat-card"><div class="strat-hd"><b>'+(e.tytul||'Etap')+'</b>'+(e.zakres_km?' <span class="k">km '+e.zakres_km+'</span>':'')+'</div>'+
        (e.opis?'<div class="strat-op">'+e.opis+'</div>':'')+
        (e.moc?'<div class="strat-fp"><span class="strat-tag">moc</span> '+e.moc+'</div>':'')+
        '<div class="strat-fp"><span class="strat-tag">\u017cywienie</span> '+(e.zywienie||'\u2014')+'</div>'+
        '<div class="strat-fp"><span class="strat-tag">pojenie</span> '+(e.pojenie||'\u2014')+'</div></div>';
    }).join('');
  }
  return out;
}
function shMailDatalist(){ return '<datalist id="sh-mail-hist"></datalist>'; }
async function shMailPopulate(){
  try{
    var r=await fetch("/api/report/mail-recipients"); if(!r.ok)return;
    var j=await r.json(); var dl=document.getElementById("sh-mail-hist");
    if(dl&&j&&j.items){ dl.innerHTML=j.items.map(function(x){return '<option value="'+String(x).replace(/"/g,"&quot;")+'">';}).join(""); }
  }catch(e){}
}
function udostepnijHTML(){
  return '<div class="ms-sub">Wyślij mailem</div>'+
    '<div class="share-mail"><input type="email" id="sh-mail" list="sh-mail-hist" placeholder="adres e-mail odbiorcy">'+
    '<button type="button" class="dlbtn dlbtn3" id="sh-mail-go">Wyślij mailem</button></div>'+
    '<div class="dlmsg" id="sh-mail-msg"></div>'+
    '<div class="ms-sub" style="margin-top:18px">Pobierz GPX</div>'+
    '<div class="share-row" id="sh-gpx"></div>'+
    '<div class="ms-sub" style="margin-top:18px">Wyślij na urządzenie</div>'+
    '<div class="share-row"><button type="button" class="dlbtn dlbtn3" id="sh-karoo">📤 Wyślij na Karoo</button>'+
    '<span class="dlmsg" id="sh-karoo-msg"></span></div>'+shMailDatalist();
}
function wireUdostepnij(){
  shMailPopulate();
  var r=DATA.route,s=DATA.start;
  var q="route_id="+encodeURIComponent(r.id)+"&date="+encodeURIComponent(s.date||"")+"&time="+encodeURIComponent(s.time||"");
  var gpxEl=document.getElementById("sh-gpx");
  if(gpxEl){
    gpxEl.innerHTML='<a class="dlbtn" href="/api/report/gpx?'+q+'&pois=1" download>⬇ GPX z POI (Karoo)</a>'+
                    '<a class="dlbtn dlbtn2" href="/api/report/gpx?'+q+'&pois=0" download>⬇ GPX trasy</a>';
  }
  var kb=document.getElementById("sh-karoo");
  if(kb)kb.onclick=async function(){
    var m=document.getElementById("sh-karoo-msg");
    if(!confirm("Utworzyć trasę z POI na Twoim koncie Karoo (Hammerhead)?"))return;
    kb.disabled=true;m.textContent=" wysyłam…";
    try{const res=await fetch("/api/report/push-karoo?"+q,{method:"POST"});const j=await res.json();
      if(res.ok&&j.ok){m.innerHTML=' ✔ wysłano ('+j.poi_count+' POI) — <a href="https://dashboard.hammerhead.io/" target="_blank">otwórz Karoo</a>';}
      else{m.textContent=" ✖ błąd: "+((j&&(j.detail||j.error))||res.status);kb.disabled=false;}
    }catch(e){m.textContent=" ✖ błąd sieci";kb.disabled=false;}
  };
  var mb=document.getElementById("sh-mail-go");
  if(mb)mb.onclick=async function(){
    var m=document.getElementById("sh-mail-msg");
    var inp=document.getElementById("sh-mail");
    var addr=(inp.value||"").trim();
    m.classList.remove("err");
    if(!addr||addr.indexOf("@")<1){m.classList.add("err");m.textContent="Podaj poprawny adres e-mail.";return;}
    var sid=DATA.snapshot_id;
    if(!sid&&typeof window.__QBOT_ENSURE_SNAPSHOT==="function"){m.textContent="Zapisuj\u0119 plan\u2026";try{sid=await window.__QBOT_ENSURE_SNAPSHOT();if(sid)DATA.snapshot_id=sid;}catch(e){sid=null;}}
    if(!sid){m.classList.add("err");m.textContent="Brak zapisanego raportu do wysłania — odśwież/wygeneruj ponownie.";return;}
    mb.disabled=true;m.textContent="Wysyłam (liczenie zrzutów, do ok. minuty)…";
    try{const res=await fetch("/api/report/send-email?snapshot_id="+encodeURIComponent(sid)+"&to="+encodeURIComponent(addr),{method:"POST"});
      const j=await res.json();
      if(res.ok&&j.status==="ok"){m.textContent="✔ Wysłano na "+j.to+".";shMailPopulate();}
      else{m.classList.add("err");m.textContent="✖ Błąd: "+((j&&j.detail)||res.status);}
    }catch(e){m.classList.add("err");m.textContent="✖ Błąd sieci.";}
    mb.disabled=false;
  };
}
function multiContent(id,label){
  var D=DATA.details||{};
  if(id==="nawierzchnia")return surfaceHTML(D.surface);
  if(id==="przewyzszenia")return climbsHTML(D.climbs);
  if(id==="pogoda")return weatherHTML(D.weather);
  if(id==="zaopatrzenie")return resupplyHTML(D.poi);
  if(id==="atrakcje")return attractionsHTML(D.poi);
  if(id==="forma")return formaHTML(D.forma);
  if(id==="strategia")return strategiaHTML(D.strategia);
  if(id==="sprzet")return sprzetHTML(D.sprzet);
  if(id==="udostepnij")return udostepnijHTML();
  return '<p class="multi-placeholder">Sekcja „'+label+'” — wkrótce (Batch 2).</p>';
}
const DAY_SECTIONS=["nawierzchnia","przewyzszenia","zaopatrzenie","atrakcje"];
window.__QBOT_RENDER_CHART=function(){try{renderChart();}catch(e){}};
function renderMulti(){
  const nav=document.getElementById("multi-nav"),pane=document.getElementById("multi-pane");
  if(!nav||!pane)return;
  var items=DATA.day_mode?MULTI.filter(function(m){return DAY_SECTIONS.indexOf(m.id)>=0;}):MULTI;
  if(window.__QBOT_GUEST_SECTIONS)items=items.filter(function(m){return window.__QBOT_GUEST_SECTIONS.indexOf(m.id)>=0;});
  nav.innerHTML=items.map((m,i)=>`<button type="button" class="multi-item${i===0?" active":""}" data-id="${m.id}">${m.label}</button>`).join("");
  function show(id){
    const m=items.find(x=>x.id===id)||items[0];
    pane.innerHTML=`<div class="multi-head">${m.label}</div><div class="multi-body">${multiContent(m.id,m.label)}</div>`;
    nav.querySelectorAll(".multi-item").forEach(b=>b.classList.toggle("active",b.dataset.id===id));
    if(m.id==="udostepnij")wireUdostepnij();if(m.id==="atrakcje")wireAtrakcje();
  }
  nav.querySelectorAll(".multi-item").forEach(b=>b.onclick=function(){show(b.dataset.id);});
  show(items[0].id);
}
function renderDayHead(){
  var r=DATA.route||{},dy=DATA.day||{};
  var nm=document.getElementById("r-name");if(nm)nm.textContent=r.name||"(dzie\u0144)";
  var w=document.getElementById("r-when");if(w)w.textContent="Analiza odcinka dnia";
  var wh=document.getElementById("r-where");if(wh)wh.textContent="km "+nf(dy.km_from,1)+"\u2013"+nf(dy.km_to,1);
  var wx=document.getElementById("r-wx");if(wx)wx.style.display="none";
  var hero=document.getElementById("r-hero");
  if(hero)hero.innerHTML=[{v:nf(dy.dist_km,1),u:"km",l:"Dystans dnia"},{v:"+"+Math.round(dy.ascent_m||0),u:"m",l:"Podjazdy"}]
    .map(function(m){return '<div class="m"><div><span class="v mono">'+m.v+'</span> <span class="u">'+m.u+'</span></div><div class="l">'+m.l+'</div></div>';}).join("");
  var br=document.getElementById("r-break");if(br)br.style.display="none";
  var meta=document.getElementById("r-meta");if(meta)meta.innerHTML='ID trasy: <span class="mono">'+(r.id||"")+'</span> \u00b7 analiza dnia (bez pogody)';
  var ft=document.getElementById("r-foot");if(ft)ft.textContent="Analiza dnia \u2014 profil, nawierzchnia, zaopatrzenie, atrakcje. Pe\u0142ny raport (z pogod\u0105) po DODAJ DO QBOT.";
}

function renderDayChart(){
  var C=DATA.chart, svg=document.getElementById("chart"), wrap=document.getElementById("chartwrap");
  if(!C||!C.ele||!C.ele.length){if(wrap)wrap.style.display="none";return;}
  var W=900,H=312,ML=44,MR=20,MT=14,MB=26,PW=W-ML-MR,PH=H-MT-MB,BASE=MT+PH,kmT=C.km_total||1;
  var eMin=C.ele_min,eMax=C.ele_max,span=(eMax-eMin)||1;
  var X=function(km){return ML+(km/kmT)*PW;}, YE=function(v){return MT+(1-(v-eMin)/span)*PH;};
  var eleAt=function(km){var E=C.ele;if(km<=E[0][0])return E[0][1];if(km>=E[E.length-1][0])return E[E.length-1][1];for(var i=1;i<E.length;i++){if(E[i][0]>=km){var k0=E[i-1][0],v0=E[i-1][1],k1=E[i][0],v1=E[i][1];return v0+(v1-v0)*((km-k0)/((k1-k0)||1));}}return E[E.length-1][1];};
  var ptsBetween=function(a,b){var out=[[a,eleAt(a)]];for(var q=0;q<C.ele.length;q++){if(C.ele[q][0]>a&&C.ele[q][0]<b)out.push(C.ele[q]);}out.push([b,eleAt(b)]);return out;};
  var P=[];
  var gsp=span>2000?500:span>800?200:span>300?100:50;
  for(var gv=Math.floor(eMin/gsp)*gsp;gv<=Math.ceil(eMax/gsp)*gsp+0.1;gv+=gsp){var gy=YE(gv);P.push('<line x1="'+ML+'" y1="'+gy.toFixed(1)+'" x2="'+(ML+PW)+'" y2="'+gy.toFixed(1)+'" stroke="#efe7d8"/>');P.push('<text x="'+(ML-4)+'" y="'+(gy+3).toFixed(1)+'" font-size="9" fill="#7a838c" text-anchor="end">'+gv+'</text>');}
  (C.surface_cat||[]).forEach(function(sg){var pts=ptsBetween(sg.a,sg.b);var d="M "+X(sg.a).toFixed(1)+" "+BASE;for(var q=0;q<pts.length;q++)d+=" L "+X(pts[q][0]).toFixed(1)+" "+YE(pts[q][1]).toFixed(1);d+=" L "+X(sg.b).toFixed(1)+" "+BASE+" Z";P.push('<path d="'+d+'" fill="'+(SCAT[sg.k]||"#ccc")+'" fill-opacity="0.85"/>');});
  var dp="M "+X(C.ele[0][0]).toFixed(1)+" "+YE(C.ele[0][1]).toFixed(1);
  for(var i=1;i<C.ele.length;i++)dp+=" L "+X(C.ele[i][0]).toFixed(1)+" "+YE(C.ele[i][1]).toFixed(1);
  P.push('<path d="'+dp+'" fill="none" stroke="var(--c-ele)" stroke-width="1.3"/>');
  P.push('<text x="'+(ML-4)+'" y="'+(YE(eMax)+3).toFixed(1)+'" font-size="9" fill="#7a838c" text-anchor="end">'+Math.round(eMax)+'</text>');
  var kmStep=kmT>80?20:kmT>30?10:5;
  for(var k=0;k<=kmT+0.1;k+=kmStep){var gx=X(k).toFixed(1);P.push('<line x1="'+gx+'" y1="'+BASE+'" x2="'+gx+'" y2="'+(BASE+4)+'" stroke="#999"/>');P.push('<text x="'+gx+'" y="'+(BASE+15)+'" font-size="10" fill="#666" text-anchor="middle">'+Math.round(k)+'</text>');}
  P.push('<line id="pf-cur" x1="0" y1="'+MT+'" x2="0" y2="'+BASE+'" stroke="#c2452f" stroke-width="1" style="display:none"/>');
  svg.innerHTML=P.join("");
  var off=(DATA.day&&DATA.day.km_from)||0, curL=document.getElementById("pf-cur");
  function move(cx){var r=svg.getBoundingClientRect();var km=((cx-r.left)/r.width*W-ML)/PW*kmT;km=Math.max(0,Math.min(kmT,km));curL.setAttribute("x1",X(km));curL.setAttribute("x2",X(km));curL.style.display="block";if(window.MAPX&&window.MAPX.ready)window.MAPX.markAtKm(km+off);}
  function hide(){curL.style.display="none";if(window.MAPX&&window.MAPX.ready)window.MAPX.clearMark();}
  svg.addEventListener("mousemove",function(e){move(e.clientX);});
  svg.addEventListener("mouseleave",hide);
  svg.addEventListener("touchmove",function(e){if(e.touches[0])move(e.touches[0].clientX);},{passive:true});
  var leg=document.getElementById("chart-legend");
  if(leg)leg.innerHTML=[1,2,3,4,5].map(function(kk){return '<span class="it"><span class="sw" style="background:'+SCAT[kk]+'"></span>'+((typeof SLAT!=="undefined"&&SLAT[kk])||kk)+'</span>';}).join("");
}

function initDayMap(){
  if(window._qmap){try{window._qmap.remove();}catch(e){}window._qmap=null;}
  window.MAPX=null;
  var map=window._qmap=L.map("map",{scrollWheelZoom:true,zoomSnap:0.25,zoomDelta:0.5}).setView([52.2,21.0],7);
  var _tl2=L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}).addTo(map);
  if(window.qTilesAttach)window.qTilesAttach(map,_tl2);
  if(window.qMapCtl){var _mc2=document.querySelector(".map-ctl");if(_mc2)window.qMapCtl(_mc2,map);}
  var a0=(DATA.day&&DATA.day.km_from)||0, b0=(DATA.day&&DATA.day.km_to)||1e9;
  function hav(p,q){var R=6371,tr=Math.PI/180,dLa=(q[0]-p[0])*tr,dLo=(q[1]-p[1])*tr,la1=p[0]*tr,la2=q[0]*tr;var h=Math.sin(dLa/2)*Math.sin(dLa/2)+Math.cos(la1)*Math.cos(la2)*Math.sin(dLo/2)*Math.sin(dLo/2);return 2*R*Math.asin(Math.sqrt(h));}
  _qGeo(DATA.route.id).then(function(d){
    if(!d.coordinates||!d.coordinates.length)return;
    var co=d.coordinates,cum=[0];for(var i=1;i<co.length;i++)cum[i]=cum[i-1]+hav(co[i-1],co[i]);
    var seg=[];for(var j=0;j<co.length;j++){if(cum[j]>=a0&&cum[j]<=b0)seg.push(co[j]);}
    if(seg.length<2)seg=co;
    L.polyline(seg,{color:"#ffffff",weight:7,opacity:1,interactive:false}).addTo(map);
    var pl=L.polyline(seg,{color:"#3f6f9a",weight:4,opacity:1,interactive:false}).addTo(map);
    var bounds=pl.getBounds();map.fitBounds(bounds,{padding:[16,16]});
    function latlonAtKm(km){if(km<=cum[0])return co[0];if(km>=cum[cum.length-1])return co[co.length-1];for(var i2=1;i2<cum.length;i2++){if(cum[i2]>=km){var t=(km-cum[i2-1])/((cum[i2]-cum[i2-1])||1);return[co[i2-1][0]+(co[i2][0]-co[i2-1][0])*t,co[i2-1][1]+(co[i2][1]-co[i2-1][1])*t];}}return co[co.length-1];}
    var mark=null;
    window.MAPX={ready:true,
      fitAll:function(){map.fitBounds(bounds,{padding:[16,16]});},
      markAtKm:function(km){var ll=latlonAtKm(km);if(!mark){mark=L.circleMarker(ll,{radius:6,color:"#fff",weight:2,fillColor:"#c2452f",fillOpacity:1,interactive:false}).addTo(map);}else{mark.setLatLng(ll);mark.setStyle({opacity:1,fillOpacity:1});}},
      fitKm:function(a,b){try{var pts=[latlonAtKm(a)];for(var i3=0;i3<co.length;i3++){if(cum[i3]>=a&&cum[i3]<=b)pts.push(co[i3]);}pts.push(latlonAtKm(b));map.fitBounds(L.latLngBounds(pts),Object.assign(window.qFitPad?window.qFitPad(map,30):{padding:[30,30]},{maxZoom:16}));}catch(e){}},
      clearMark:function(){if(mark)mark.setStyle({opacity:0,fillOpacity:0});}};
    var bF=document.getElementById("mc-fit");if(bF)bF.onclick=function(){window.MAPX.fitAll();};
  }).catch(function(){});
}

window.renderReport=function(data, mount){
  DATA=data;VIEW=null;
  mount.innerHTML=SKELETON;
  render();
  renderWx();
  renderChart();
  initMap();
  renderAlerts();
  renderMulti();
};
})();
