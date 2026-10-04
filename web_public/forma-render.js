/* czas lokalny (strefa przegladarki) -- wspolne dla QBot lab */function qTsLocal(s,naiveUtc){if(!s)return"";var t=String(s).trim().replace(" ","T").replace(/\.\d+/,"");if(/[+-]\d\d$/.test(t))t+=":00";t=t.replace(/([+-]\d\d)(\d\d)$/,"$1:$2");if(!/(Z|[+-]\d\d:\d\d)$/i.test(t)){if(!naiveUtc)return t.slice(0,16).replace("T"," ");t+="Z";}var d=new Date(t);if(isNaN(d.getTime()))return String(s).slice(0,16);var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());}function qDateLocal(d){d=d||new Date();var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
// Forma (ModelQ v2) — redesign v2 (v10). Zywe dane z /api/forma/data (qbot_v2.fitmodel_daily).
// Kafle: wartosc + Δ (1/7/30/90) + MINI-WYKRES z osia Y (max/srodek/min) i osia czasu + dymek
// (opis/interpretacja na hover). Wykres glowny: jeden SVG (bez CDN), przelaczalne serie,
// dynamiczne osie per-jednostka, gestsza os czasu, legenda z opisami.
// v10: interakcja jak w raporcie jazdy — kursor (pionowa linia + kropki), tooltip z wartosciami,
//      zoom przez przeciagniecie po X (zagniezdzalny), klik = reset do okna 7/30/90.

const M={
  ftp:{f:"cp_modelq_w",label:"FTP / CP",unit:"W",grp:"W",dir:"up",dec:0,col:"#4a9eff",
    desc:"Moc progowa (Functional Threshold / Critical Power) — orientacyjnie moc do utrzymania ~1 h.",
    interp:"Wyżej = mocniejszy silnik tlenowy. Wzrost w oknie = poprawa formy progowej."},
  ltp:{f:"ltp_modelq_w",label:"LTP",unit:"W",grp:"W",dir:"up",dec:0,col:"#b98cff",
    desc:"Próg tlenowy (dolny) — granica spokojnego wysiłku bez narastania zmęczenia.",
    interp:"Wyżej = szersza baza tlenowa, łatwiejsze długie jazdy w tempie."},
  wp:{f:"wprime_modelq_kj",label:"W'",unit:"kJ",grp:"kJ",dir:"up",dec:1,col:"#6d7cff",
    desc:"Zapas beztlenowy (anaerobic capacity) — „bak\" energii ponad progiem na ostre wysiłki.",
    interp:"Wyżej = więcej na zrywy, ataki i strome podjazdy powyżej FTP."},
  wkg:{f:"w_per_kg",label:"W/kg",unit:"W/kg",grp:"wkg",dir:"up",dec:2,col:"#4a9eff",dash:"2 3",
    desc:"Moc progowa na kilogram masy — kluczowa pod górę.",
    interp:"Wyżej = lepszy podjazdowiec. Rośnie od wzrostu FTP lub spadku masy."},
  ctl:{f:"ctl_xss",label:"CTL",unit:"",grp:"load",dir:"up",dec:1,col:"#38b25a",
    desc:"Przewlekłe obciążenie (fitness) — ok. 42-dniowa średnia dziennego XSS.",
    interp:"Wyżej = większa wytrenowana baza. Rośnie powoli, systematycznym treningiem."},
  atl:{f:"atl_plus",label:"ATL",unit:"",grp:"load",dir:"down",dec:1,col:"#f0863a",
    desc:"Ostre obciążenie (zmęczenie) — ok. 7-dniowa średnia dziennego XSS.",
    interp:"Wysokie = świeże zmęczenie. Spadek po odpoczynku = mniej zmęczenia."},
  tsb:{f:"tsb_plus",label:"TSB",unit:"",grp:"load",dir:"ctx",dec:1,col:"#9aa0a6",
    desc:"Bilans / świeżość = CTL − ATL.",
    interp:"Dodatnie = wypoczęty (dobry na akcent), ujemne = obciążony, ~0 = neutralnie."},
  atlp:{f:"atl_raw",label:"ATL surowe",unit:"",grp:"load",dir:"down",dec:1,col:"#f0863a",dash:"6 3",
    desc:"ATL powiększone o ukryte zmęczenie z subiektywnego kosztu jazdy (feel<0 lub choroba w dni jazdy).",
    interp:"Wyżej niż ATL = jazda kosztowała więcej niż mówią dane. Równe ATL w dni bez korekty."},
  tsbp:{f:"tsb_raw",label:"TSB surowe",unit:"",grp:"load",dir:"ctx",dec:1,col:"#9aa0a6",dash:"6 3",
    desc:"Świeżość z uwzględnieniem ukrytego zmęczenia = CTL − ATL+.",
    interp:"Niżej niż TSB = subiektyw dołożył zmęczenia. Równe TSB w dni bez korekty."},
  hrv:{f:"hrv_night",label:"HRV",unit:"ms",grp:"ms",dir:"up",dec:0,col:"#ef5a58",dash:"7 3",
    desc:"Zmienność rytmu serca w nocy (RMSSD).",
    interp:"Wyżej względem Twojej normy = lepsza regeneracja i gotowość układu nerwowego."},
  rhr:{f:"rhr",label:"RHR",unit:"bpm",grp:"bpm",dir:"down",dec:0,col:"#ef5a58",dash:"2 3",
    desc:"Tętno spoczynkowe.",
    interp:"Niżej zwykle = lepsza regeneracja. Skok w górę = zmęczenie, stres lub infekcja."},
  slp:{f:"sleep_score",label:"Sen (scoring)",unit:"",grp:"sscore",dir:"up",dec:0,col:"#23c1c1",dash:"9 3 2 3",
    desc:"Scoring snu (jakość 0–100) — miarodajniejszy niż sama długość: łączy czas, fazy i wybudzenia.",
    interp:"Wyżej = lepiej zregenerowany. Niski mimo długiego snu = sen płytki lub przerywany."},
  rdy:{f:"readiness_score",label:"Gotowość",unit:"",grp:"rdy",dir:"up",dec:2,col:"#9ccc3a",dash:"6 3",
    desc:"Wskaźnik gotowości ModelQ (z HRV + RHR + sen, z-score ~ −1…+1).",
    interp:"Wyżej = organizm bardziej gotów na mocny trening; ujemne = odpuść."},
  rdye:{f:"readiness_effective",label:"Gotowość (efekt.)",unit:"",grp:"rdy",dir:"up",dec:2,col:"#9ccc3a",dash:"2 5",
    desc:"Gotowość efektywna = obiektywna (HRV+RHR+sen) skorygowana Twoim samopoczuciem/chorobą z kalendarza.",
    interp:"Różni się od obiektywnej tylko w dni z wpisem. Feel −2..+2 rusza ją maks. ±0.30, choroba −0.30, łącznie do ±0.50. Nie zmienia CP/FTP/W'."},
  wgt:{f:"weight_kg",label:"Waga",unit:"kg",grp:"kg",dir:"ctx",dec:1,col:"#a1887f",
    desc:"Masa ciała (poranne pomiary / wellness).",
    interp:"Kontekst dla W/kg. Spadek podnosi W/kg pod górę; dla trwałości/gravelu to nie priorytet."},
  glyc:{f:"glycogen_pct",label:"Glikogen",unit:"%",grp:"pct",dir:"up",dec:0,col:"#e06fae",dash:"11 4",
    desc:"Szacowane zapełnienie zapasów węglowodanów (glikogenu).",
    interp:"Wyżej = lepiej dotankowany. Niski przed długą jazdą = ryzyko „ściany\"."}
};
const GROUPS={"g-power":["ftp","ltp","wp","wkg"],"g-load":["ctl","atl","atlp","tsb","tsbp"],"g-well":["hrv","rhr","slp","rdy","rdye","wgt","glyc"]};
const CHART_ORDER=["ftp","ltp","wp","wkg","ctl","atl","atlp","tsb","tsbp","hrv","rhr","slp","rdy","rdye","wgt","glyc"];
const GRPU={W:"W",kJ:"kJ",wkg:"W/kg",load:"pkt",ms:"ms",bpm:"bpm",h:"h",rdy:"score",pct:"%",sscore:"score",kg:"kg"};

let ROWS=[],N=0,LAT={},WIN=30,CHART_DAYS=90;
let ACTIVE=new Set(["ftp","ctl","atl","tsb"]);
let TREND=false;
let X0=0,X1=0;        // widoczne okno wykresu (indeksy do ROWS, wlacznie) — zmieniane zoomem
let LAYOUT=null;      // geometria ostatniego rysowania (do interakcji: kursor/tooltip/zoom)
let ACTS=null;        // 3 ostatnie aktywnosci (/api/forma/activities)

/* ---------- DZIS: konfigurowalny panel ---------- */
const DZIS_KEY="qdzis_widgets";
const DZIS_GROUPS=[["Moc",["ftp","ltp","wp","wkg"]],["Obci\u0105\u017cenie",["ctl","atl","atlp","tsb","tsbp"]],["Wellness",["hrv","rhr","slp","rdy","rdye","wgt","glyc"]]];
let DZIS={hero:true,event:true,keys:["ftp","ctl","atl","tsb","rdy","wgt"]};
try{const _dz=JSON.parse(localStorage.getItem(DZIS_KEY)||"null");if(_dz&&typeof _dz==="object"){DZIS.hero=_dz.hero!==false;DZIS.event=_dz.event!==false;if(Array.isArray(_dz.keys))DZIS.keys=_dz.keys.filter(k=>M[k]||k==="nut_balance"||k==="nut_body"||k==="event_prep");}}catch(e){}
let _dzSaveT=null;
function saveDzis(){try{localStorage.setItem(DZIS_KEY,JSON.stringify(DZIS));}catch(e){}if(_dzSaveT)clearTimeout(_dzSaveT);_dzSaveT=setTimeout(function(){fetch("/api/prefs",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify({key:"dzis",value:DZIS})}).catch(function(){});},400);}

function el(t,c){const e=document.createElement(t);if(c)e.className=c;return e;}
function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function val(r,k){const v=r[M[k].f];return v===undefined?null:v;}
function colv(k){return ROWS.map(r=>val(r,k));}
function nnAt(k,idx){const v=colv(k);for(let i=idx;i<N;i++){if(v[i]!=null)return v[i];}for(let i=Math.min(idx,N-1);i>=0;i--){if(v[i]!=null)return v[i];}return null;}
function fmt(x,dec){return x==null?"—":(dec===0?Math.round(x):Math.round(x*Math.pow(10,dec))/Math.pow(10,dec));}
function fmtDay(d){if(!d)return "—";const p=String(d).split("-");return p.length>=3?p[2]+"."+p[1]:d;}

/* ---------- HERO ---------- */
const SPORTPL={cycling:"Kolarstwo",road_cycling:"Kolarstwo",gravel_cycling:"Gravel",mountain_biking:"MTB",virtual_ride:"Trener",indoor_cycling:"Rower stacj.",running:"Bieg",trail_running:"Bieg terenowy",treadmill_running:"Bieżnia",walking:"Marsz",hiking:"Wędrówka",swimming:"Pływanie",lap_swimming:"Pływanie",open_water_swimming:"Pływanie",strength_training:"Siłownia",cardio:"Cardio",yoga:"Joga"};
function sportLabel(x){return SPORTPL[x]||(x?String(x).replace(/_/g," "):"Aktywność");}
function actWhen(iso,date){
  let d=iso?new Date(iso):(date?new Date(date+"T00:00:00"):null);
  if(!d||isNaN(d))return "—";
  const t0=new Date();t0.setHours(0,0,0,0);const dd=new Date(d);dd.setHours(0,0,0,0);
  const diff=Math.round((t0-dd)/86400000);
  const hm=iso?(" "+String(d.getHours()).padStart(2,"0")+":"+String(d.getMinutes()).padStart(2,"0")):"";
  if(diff===0)return "dziś"+hm;
  if(diff===1)return "wczoraj"+hm;
  const p=String(date||"").split("-");return p.length>=3?(p[2]+"."+p[1]):("−"+diff+" dni");
}
function actAmount(a){
  if(a.distance_m!=null&&a.distance_m>50)return (Math.round(a.distance_m/100)/10)+" km";
  const s=a.duration_s||0;if(!s)return "—";
  const h=Math.floor(s/3600),m=Math.round((s%3600)/60);
  return h>0?(h+"h "+m+"m"):(m+" min");
}
function renderActs(){
  if(!Array.isArray(ACTS))return '<div class="acts-list"><div class="act muted">Ładowanie…</div></div>';
  if(!ACTS.length)return '<div class="acts-list"><div class="act muted">Brak aktywności.</div></div>';
  return '<div class="acts-list">'+ACTS.map(function(a){
    const place=a.name?esc(a.name):sportLabel(a.sport_type);
    const eid=a.external_id?esc(String(a.external_id)):"";
    const metr='<span class="act-m2"><span>'+actAmount(a)+'</span>'+(a.tss!=null?'<span class="act-tss">TSS '+Math.round(a.tss)+'</span>':'')+'</span>';
    const nameCell=eid
      ? '<span class="act-n lnk" data-eid="'+eid+'" data-name="'+place+'">'+place+' <span class="act-go">\u203a</span></span>'
      : '<span class="act-n">'+place+'</span>';
    return '<div class="act">'
      +'<div class="act-h"><span class="act-s">'+esc(sportLabel(a.sport_type))+'</span><span class="act-w">'+esc(actWhen(a.started_at,a.date))+'</span></div>'
      +'<div class="act-b">'+nameCell+metr+'</div>'
      +'</div>';
  }).join("")+'</div>';
}
function renderHero(){
  const box=document.getElementById("hero");if(!box)return;
  const tsb=nnAt("tsb",N-1),hrv=nnAt("hrv",N-1),rhr=nnAt("rhr",N-1);
  const day=N?ROWS[N-1].day:null;
  let stateHtml;
  if(tsb==null){
    stateHtml='<div class="hero" style="border-color:var(--line)"><div class="lab">Stan na dziś</div><div class="big">Brak danych</div></div>';
  }else{
    let stan,bg,bd,ink;
    if(tsb>=5){stan="Świeży";bg="var(--good-bg)";bd="var(--good)";ink="var(--good)";}
    else if(tsb<=-8){stan="Zmęczony";bg="var(--bad-bg)";bd="var(--bad)";ink="var(--bad)";}
    else{stan="Neutralny";bg="var(--accent-bg)";bd="var(--accent)";ink="var(--accent)";}
    const exp=tsb>=0?"Dodatnie TSB — ciało wypoczęte, dobry moment na akcent."
                    :"Ujemne TSB — kumulacja zmęczenia, rozważ lżejszy dzień.";
    const well=(hrv!=null?" HRV "+Math.round(hrv)+" ms":"")+(rhr!=null?" · RHR "+Math.round(rhr)+" bpm.":"");
    stateHtml='<div class="hero" style="background:'+bg+';border-color:'+bd+';color:'+ink+'">'
      +'<div class="lab">Stan na dziś ('+fmtDay(day)+')</div>'
      +'<div class="big">'+stan+' · TSB '+(tsb>0?"+":"")+(Math.round(tsb*10)/10)+'</div>'
      +'<div class="exp">'+exp+well+'</div></div>';
  }
  const actsHtml='<div class="hero hero-acts"><div class="lab">Ostatnie aktywności</div>'+renderActs()+'</div>';
  box.innerHTML='<div class="hero-split">'+stateHtml+actsHtml+'</div>';
  box.querySelectorAll("[data-eid]").forEach(function(a){a.onclick=function(){openRide(a.getAttribute("data-eid"),a.getAttribute("data-name")||"");};});
  const _hc=box.querySelector(".hero");
  if(_hc&&tsb!=null){const _bar=el("div","aibtns");
    const _b1=el("button","aibtn");_b1.type="button";_b1.textContent="Analiza";_b1.onclick=()=>runAnalyze("today",_b1);
    const _b2=el("button","aibtn");_b2.type="button";_b2.textContent="Doradca";_b2.onclick=()=>runAnalyze("coach",_b2);
    _bar.appendChild(_b1);_bar.appendChild(_b2);_hc.appendChild(_bar);}
}

/* ---------- SZCZEGOLY JAZDY (prawy panel) ---------- */
function _rd(label,v){return (v==null||v==="")?"":'<div class="rd-r"><span class="rd-l">'+esc(label)+'</span><span class="rd-v">'+v+'</span></div>';}
function rideDetailHtml(a){
  const km=(a.distance_m!=null&&a.distance_m>50)?(Math.round(a.distance_m/100)/10+" km"):null;
  let dur=null;{const s=a.duration_s||0;if(s){const h=Math.floor(s/3600),m=Math.round((s%3600)/60);dur=h>0?(h+"h "+m+"m"):(m+" min");}}
  const ele=(a.elevation_m!=null)?(Math.round(a.elevation_m)+" m"):null;
  let h='<div class="rd">';
  h+=_rd("Dyscyplina",esc(sportLabel(a.sport_type)));
  h+=_rd("Kiedy",esc(actWhen(a.started_at,a.date)));
  h+=_rd("Dystans",km);
  h+=_rd("Czas",dur);
  h+=_rd("Przewy\u017cszenie",ele);
  h+=_rd("TSS",a.tss!=null?Math.round(a.tss):null);
  h+=_rd("Moc \u015br.",a.avg_power_w!=null?Math.round(a.avg_power_w)+" W":null);
  h+=_rd("NP",a.normalized_power_w!=null?Math.round(a.normalized_power_w)+" W":null);
  h+=_rd("Moc max",a.max_power_w!=null?Math.round(a.max_power_w)+" W":null);
  h+=_rd("IF",a.intensity_factor!=null?(Math.round(a.intensity_factor*100)/100):null);
  h+=_rd("HR \u015br.",a.avg_hr_bpm!=null?Math.round(a.avg_hr_bpm)+" bpm":null);
  h+=_rd("HR max",a.max_hr_bpm!=null?Math.round(a.max_hr_bpm)+" bpm":null);
  h+=_rd("Kadencja \u015br.",a.avg_cadence_rpm!=null?Math.round(a.avg_cadence_rpm)+" rpm":null);
  h+=_rd("Kalorie",a.calories!=null?Math.round(a.calories)+" kcal":null);
  h+='</div>';
  if(a.has_report){h+='<a class="rd-btn" href="/raport-jazdy.html?ride='+encodeURIComponent(a.external_id||"")+'" target="_blank" rel="noopener">Otw\u00f3rz raport trasy \u2197</a>';}
  return h;
}
let _openRideEid=null;
function openRide(eid,name){
  if(typeof asideShow!=="function")return;
  if(document.body.classList.contains("qaside-open")&&_openRideEid===eid){document.body.classList.remove("qaside-open");_openRideEid=null;return;}
  _openRideEid=eid;
  asideShow("Szczeg\u00f3\u0142y \u2014 "+name,'<span style="color:var(--muted)">\u0141adowanie\u2026</span>');
  fetch("/api/forma/activity?external_id="+encodeURIComponent(eid),{credentials:"same-origin"})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(j){const a=j&&j.activity;if(!a){asideShow("Szczeg\u00f3\u0142y \u2014 "+name,"Brak danych.");return;}asideShow("Szczeg\u00f3\u0142y \u2014 "+esc(a.activity_name||name),rideDetailHtml(a));})
    .catch(function(e){asideShow("Szczeg\u00f3\u0142y \u2014 "+name,'<span style="color:var(--bad)">B\u0142\u0105d: '+esc(e.message)+'</span>');});
}

/* ---------- KAFELKI: mini-wykres z osia Y + osia czasu ---------- */
function trendLine(vals){
  const pts=[];vals.forEach((y,i)=>{if(y!=null)pts.push([i,y]);});
  if(pts.length<2)return null;
  const nn=pts.length;let sx=0,sy=0,sxx=0,sxy=0;
  pts.forEach(([x,y])=>{sx+=x;sy+=y;sxx+=x*x;sxy+=x*y;});
  const den=nn*sxx-sx*sx;if(den===0)return null;
  const b=(nn*sxy-sx*sy)/den,a=(sy-b*sx)/nn;
  return {a:a,b:b,x0:pts[0][0],x1:pts[pts.length-1][0]};
}
function miniChart(k){
  const m=M[k];
  const from=Math.max(0,N-1-WIN);
  const vals=colv(k).slice(from);
  const days=ROWS.slice(from).map(r=>r.day);
  const v=vals.filter(x=>x!=null);
  if(v.length<2) return '<div class="mini nodata">za mało danych w oknie '+WIN+'D</div>';
  const mn=Math.min(...v),mx=Math.max(...v),rg=(mx-mn)||1,mid=mn+rg/2;
  const n=vals.length,PADT=8,PADB=8,HH=100;
  let d="",st=false;
  vals.forEach((x,i)=>{if(x==null){st=false;return;}const px=(n<=1?0:i*100/(n-1));const py=HH-PADB-(x-mn)/rg*(HH-PADT-PADB);d+=(st?"L":"M")+px.toFixed(2)+" "+py.toFixed(2)+" ";st=true;});
  const dec=m.dec;
  let startDay=days[0];for(let i=0;i<vals.length;i++){if(vals[i]!=null){startDay=days[i];break;}}
  let trendSvg="";
  if(TREND){const tl=trendLine(vals);if(tl){const toY=function(yy){const p=HH-PADB-(yy-mn)/rg*(HH-PADT-PADB);return Math.max(1,Math.min(99,p));};const px0=(n<=1?0:tl.x0*100/(n-1)),px1=(n<=1?100:tl.x1*100/(n-1));trendSvg='<line x1="'+px0.toFixed(2)+'" y1="'+toY(tl.a+tl.b*tl.x0).toFixed(2)+'" x2="'+px1.toFixed(2)+'" y2="'+toY(tl.a+tl.b*tl.x1).toFixed(2)+'" stroke="'+m.col+'" stroke-width="1.5" stroke-dasharray="4 3" opacity="0.6" vector-effect="non-scaling-stroke"/>';}}
  const svg='<svg viewBox="0 0 100 100" preserveAspectRatio="none">'
    +'<line x1="0" y1="50" x2="100" y2="50" stroke="#ece7dc" stroke-width="1" vector-effect="non-scaling-stroke"/>'
    +trendSvg
    +'<path d="'+d+'" fill="none" stroke="'+m.col+'" stroke-width="2"'+(m.dash?' stroke-dasharray="'+m.dash+'"':'')+' vector-effect="non-scaling-stroke"/>'
    +'</svg>';
  const u=m.unit?('<span class="yu">'+esc(m.unit)+'</span>'):'';
  return '<div class="mini">'
    +'<div class="yax"><span>'+fmt(mx,dec)+'</span><span>'+fmt(mid,dec)+'</span><span>'+fmt(mn,dec)+'</span></div>'
    +'<div class="plotwrap"><div class="plot">'+svg+'</div>'
    +'<div class="xax"><span>'+fmtDay(startDay)+'</span>'+u+'<span>dziś</span></div></div>'
    +'</div>';
}
function tile(k){
  const m=M[k];
  const latest=nnAt(k,N-1);
  const past=nnAt(k,Math.max(0,N-1-WIN));
  let dcls="none",dtxt="—";
  if(latest!=null&&past!=null){
    const dv=latest-past,ar=dv>0?"▲":(dv<0?"▼":"■");
    let good="ctx";
    if(m.dir==="up")good=dv>0?"good":(dv<0?"bad":"ctx");
    else if(m.dir==="down")good=dv<0?"good":(dv>0?"bad":"ctx");
    const dvr=Math.round(dv*Math.pow(10,m.dec))/Math.pow(10,m.dec);
    dcls=good;dtxt=ar+" "+(dv>0?"+":"")+dvr;
  }
  let foot="Δ "+WIN+"D"+(m.dir==="down"?" · spadek = lepiej":(m.dir==="ctx"?" · kontekst":""));
  if(k==="wp"){const cf=(LAT.wprime_confidence&&LAT.wprime_confidence.value)||null;if(cf)foot="pewność: "+cf+" · "+foot;}
  const tip='<div class="tip"><b>'+esc(m.label)+(m.unit?" ["+esc(m.unit)+"]":"")+'</b><br>'+esc(m.desc)+'<br><i>'+esc(m.interp)+'</i></div>';
  return '<div class="tile" data-k="'+k+'">'+tip
    +'<div class="k">'+m.label+' <span class="qm">?</span></div>'
    +'<div class="vrow"><span class="v" style="color:'+m.col+'">'+fmt(latest,m.dec)+' <span class="u">'+m.unit+'</span></span>'
    +'<span class="delta '+dcls+'">'+dtxt+'</span></div>'
    +miniChart(k)
    +'</div>';
}
function renderCards(){for(const g in GROUPS){const box=document.getElementById(g);if(box)box.innerHTML=GROUPS[g].map(tile).join("");}}
/* ---------- POWIEKSZENIE KAFLA (klik) ---------- */
let _tzEl=null;
function _tzEnsure(){
  if(_tzEl)return _tzEl;
  _tzEl=el("div","tilez-back");
  _tzEl.innerHTML='<div class="tilez"><button class="tilez-x" type="button" aria-label="Zamknij">\u00d7</button><div class="tilez-body"></div></div>';
  document.body.appendChild(_tzEl);
  _tzEl.addEventListener("click",function(){_tzClose();});
  document.addEventListener("keydown",function(e){if(e.key==="Escape")_tzClose();});
  return _tzEl;
}
function _tzClose(){if(_tzEl)_tzEl.classList.remove("open");}
function openTileZoom(k){
  const m=M[k];if(!m)return;
  const latest=nnAt(k,N-1),past=nnAt(k,Math.max(0,N-1-WIN));
  let dcls="none",dtxt="\u2014";
  if(latest!=null&&past!=null){
    const dv=latest-past,ar=dv>0?"\u25b2":(dv<0?"\u25bc":"\u25a0");
    let good="ctx";
    if(m.dir==="up")good=dv>0?"good":(dv<0?"bad":"ctx");
    else if(m.dir==="down")good=dv<0?"good":(dv>0?"bad":"ctx");
    const dvr=Math.round(dv*Math.pow(10,m.dec))/Math.pow(10,m.dec);
    dcls=good;dtxt=ar+" "+(dv>0?"+":"")+dvr;
  }
  const box=_tzEnsure().querySelector(".tilez-body");
  box.innerHTML='<div class="tilez-k">'+esc(m.label)+(m.unit?' <span class="tilez-u">['+esc(m.unit)+']</span>':'')+'</div>'
    +'<div class="tilez-vrow"><span class="tilez-v" style="color:'+m.col+'">'+fmt(latest,m.dec)+' <span class="tilez-vu">'+esc(m.unit)+'</span></span>'
    +'<span class="delta '+dcls+'">'+dtxt+' <span class="tilez-dw">/ '+WIN+'D</span></span></div>'
    +'<div class="tilez-chart">'+miniChart(k)+'</div>'
    +'<div class="tilez-desc">'+esc(m.desc)+'</div>'
    +'<div class="tilez-interp"><i>'+esc(m.interp)+'</i></div>';
  _tzEl.classList.add("open");
}
if(!window._tzWired){window._tzWired=true;document.addEventListener("click",function(e){
  const t=e.target.closest?e.target.closest(".tile[data-k]"):null;
  if(t){const k=t.getAttribute("data-k");if(M[k])openTileZoom(k);}
});}
const NUT_WIDGETS=[["nut_balance","Bilans energetyczny"],["nut_body","Sk\u0142ad cia\u0142a"]];
function _hasNut(){return DZIS.keys.indexOf("nut_balance")>=0||DZIS.keys.indexOf("nut_body")>=0;}
function fillNut(){
  if(!window.QNut)return;
  const rdy=window.QNut.ready();
  const bal=document.getElementById("dz-nut-bal");if(bal)bal.innerHTML=rdy?window.QNut.balanceHTML():'<div class="lgempty">\u0141adowanie\u2026</div>';
  const bd=document.getElementById("dz-nut-body");if(bd)bd.innerHTML=rdy?window.QNut.bodyHTML():'<div class="lgempty">\u0141adowanie\u2026</div>';
}
let EVP=null;
function _evDM(d){return d?(d.slice(8,10)+"."+d.slice(5,7)):"";}
function _evWall(i){const w=(EVP&&EVP.walls)||[];const f=w.filter(x=>x.idx===i)[0];return f?(f.color||""):"";}
function renderEventPrep(){
  const box=document.getElementById("dzis-event");if(!box)return;
  if(!DZIS.event){box.innerHTML="";return;}
  if(!EVP){box.innerHTML="";return;}
  const t=EVP.target,e=EVP.event;
  if(!t&&!e){box.innerHTML='<div class="evp"><div class="evp-none">Brak nadchodz\u0105cych wydarze\u0144 w kalendarzu.</div></div>';return;}
  if(!t){
    box.innerHTML='<div class="evp"><div><div class="lab">Najbli\u017csze w kalendarzu</div>'
      +'<div class="evp-t">'+esc(e.title||"wydarzenie")+'</div>'
      +'<div class="evp-s">'+_evDM(e.day)+(e.days_until>0?(" \u00b7 za "+e.days_until+" dni"):" \u00b7 dzi\u015b")+'</div></div>'
      +'<div class="evp-none">Brak celu z policzonym obci\u0105\u017ceniem. Dodaj wypraw\u0119 z Planera, \u017ceby zobaczy\u0107 plan przygotowania.</div><div></div></div>';
    return;
  }
  const du=t.days_until;
  const when=_evDM(t.day)+((t.end_day&&t.end_day!==t.day)?("\u2013"+_evDM(t.end_day)):"");
  const km=(EVP.stages||[]).reduce((a,x)=>a+(x.dist_km||0),0);
  let meta=when;
  if(EVP.n_days)meta+=" \u00b7 "+EVP.n_days+" dni";
  if(km)meta+=" \u00b7 "+Math.round(km)+" km";
  if(EVP.total_xss)meta+=" \u00b7 ~"+Math.round(EVP.total_xss)+" XSS";
  let lim="";
  if(EVP.limits&&EVP.limits.length)lim='<div class="evp-lim">\u26a0 po drodze: '+EVP.limits.map(x=>esc(x.when+" "+x.label)).join(" \u00b7 ")+'</div>';
  let days="";
  (EVP.stages||[]).forEach((st,i)=>{
    days+='<div class="evp-d '+_evWall(i)+'"><span>'+_evDM(st.day)+'</span><b>'+(st.xss!=null?Math.round(st.xss):"\u2013")+'</b>XSS</div>';
  });
  const ttl=(du>0?("za "+du+" dni"):(du===0?"dzi\u015b start":"trwa"));
  let tp="";
  (EVP.taper||[]).slice(0,2).forEach(x=>{tp+="<li>"+esc(x)+"</li>";});
  box.innerHTML='<div class="evp">'
    +'<div><div class="lab">Najbli\u017cszy cel \u00b7 '+ttl+'</div>'
      +'<div class="evp-t" title="'+esc(t.title||"")+'">'+esc(t.title||"cel")+'</div>'
      +'<div class="evp-s">'+esc(meta)+'</div>'+lim+'</div>'
    +'<div><div class="lab">Planowane obci\u0105\u017cenie dni</div>'
      +'<div class="evp-days">'+days+'</div>'
      +(EVP.verdict?('<div class="evp-v" title="'+esc(EVP.verdict)+'">'+esc(EVP.verdict)+'</div>'):"")+'</div>'
    +'<div><div class="lab">Przygotowanie</div><ul class="evp-tp">'+tp+'</ul>'
      +'<button class="evp-btn" id="evp-ai" type="button">Plan przygotowania (AI)</button></div>'
    +'</div>';
  const b=document.getElementById("evp-ai");
  if(b)b.onclick=()=>runAnalyze("event",b);
}
function loadEventPrep(){
  return fetch("/api/forma/event-prep",{credentials:"same-origin",cache:"no-store"})
    .then(r=>r.ok?r.json():null).then(j=>{EVP=j;renderEventPrep();}).catch(()=>{});
}
function renderToday(){
  const hero=document.getElementById("hero");if(hero)hero.style.display=DZIS.hero?"":"none";
  renderEventPrep();
  const board=document.getElementById("dzis-board");
  const ks=DZIS.keys.filter(k=>M[k]);
  if(board)board.innerHTML=ks.length?ks.map(tile).join(""):((DZIS.hero||_hasNut())?"":'<div class="lgempty">Nic nie wybrano \u2014 kliknij \u201eDostosuj\u201d, aby doda\u0107 kafle.</div>');
  const nb=document.getElementById("dzis-nut");
  if(nb){
    let h="";
    if(DZIS.keys.indexOf("nut_balance")>=0)h+='<div class="nut-grpttl" style="margin-top:6px">Bilans energetyczny</div><div id="dz-nut-bal"></div>';
    if(DZIS.keys.indexOf("nut_body")>=0)h+='<div class="nut-grpttl" style="margin-top:10px">Sk\u0142ad cia\u0142a <span class="nut-grpsub">warto\u015b\u0107 i zmiana w oknie</span></div><div id="dz-nut-body"></div>';
    nb.innerHTML=h;fillNut();
  }
  window.renderTodayNut=fillNut;
}
function _dzChip(k,label,on){return '<span class="chip '+(on?"on":"off")+'" data-dz="'+k+'">'+esc(label)+'</span>';}
function renderDzisCust(){
  const box=document.getElementById("dzis-cust");if(!box)return;
  let h='<div class="dzrow"><span class="dzg">Panel</span>'+_dzChip("__hero__","Hero (stan na dzi\u015b)",DZIS.hero)+_dzChip("__event__","Najbli\u017cszy cel",DZIS.event)+'</div>';
  DZIS_GROUPS.forEach(g=>{h+='<div class="dzrow"><span class="dzg">'+esc(g[0])+'</span>';g[1].forEach(k=>{h+=_dzChip(k,M[k].label,DZIS.keys.indexOf(k)>=0);});h+='</div>';});
  h+='<div class="dzrow"><span class="dzg">\u017bywienie</span>'+NUT_WIDGETS.map(w=>_dzChip(w[0],w[1],DZIS.keys.indexOf(w[0])>=0)).join("")+'</div>';
  box.innerHTML=h;
  box.querySelectorAll("[data-dz]").forEach(c=>{c.onclick=()=>{const k=c.getAttribute("data-dz");if(k==="__hero__"){DZIS.hero=!DZIS.hero;}else if(k==="__event__"){DZIS.event=!DZIS.event;}else{const i=DZIS.keys.indexOf(k);if(i>=0)DZIS.keys.splice(i,1);else DZIS.keys.push(k);}saveDzis();renderDzisCust();renderToday();};});
}
function wireDzis(){
  const b=document.getElementById("dzis-edit"),box=document.getElementById("dzis-cust");
  if(b&&box)b.onclick=()=>{const show=(box.style.display==="none");box.style.display=show?"":"none";b.classList.toggle("active",show);if(show)renderDzisCust();};
}

/* ---------- WYKRES GLOWNY ---------- */
function renderChecks(){
  const box=document.getElementById("checks");if(!box)return;box.innerHTML="";
  CHART_ORDER.forEach(k=>{
    const m=M[k],on=ACTIVE.has(k);
    const c=el("span","chip "+(on?"on":"off"));
    c.innerHTML='<i style="background:'+m.col+'"></i>'+m.label+(m.unit?" ["+m.unit+"]":"");
    c.onclick=()=>{if(ACTIVE.has(k))ACTIVE.delete(k);else ACTIVE.add(k);renderChecks();drawChart();};
    box.appendChild(c);
  });
}
/* ---------- WYKRES: 3 tryby (znormalizowany / panele / wartosci) ---------- */
let CHART_MODE=(function(){try{return localStorage.getItem("qforma_chartmode")||"norm";}catch(e){return "norm";}})();
const _GCOL={gh:"rgba(128,128,128,.20)",gv:"rgba(128,128,128,.12)",ax:"#8b949e",cur:"#8b949e",base:"rgba(128,128,128,.22)"};
function _seriesScale(rows,k){let mn=Infinity,mx=-Infinity;rows.forEach(r=>{const v=val(r,k);if(v!=null){if(v<mn)mn=v;if(v>mx)mx=v;}});if(mn===Infinity)return null;return {mn:mn,mx:mx,rg:(mx-mn)||1};}
function _yv(yk,v){return yk.yBot-(v-yk.mn)/yk.rg*(yk.yBot-yk.yTop);}
function _lastIdx(rows,k){for(let i=rows.length-1;i>=0;i--){if(val(rows[i],k)!=null)return i;}return -1;}

function drawChart(){
  const host=document.getElementById("chartbox");if(!host)return;
  if(N){ if(X1<=0||X1>N-1)X1=N-1; if(X0<0)X0=0; if(X0>=X1)X0=Math.max(0,X1-1); }
  const rows=ROWS.slice(X0,X1+1);
  const xN=rows.length;
  const activeK=CHART_ORDER.filter(k=>ACTIVE.has(k));
  const W=900, PT=14, PB=30;
  let H, PL, PR, yk={};

  if(!activeK.length){
    H=200;PL=8;PR=8;
    host.innerHTML='<svg class="csvg" style="height:'+H+'px" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none"><text x="'+(W/2)+'" y="'+(H/2)+'" fill="'+_GCOL.ax+'" font-size="13" text-anchor="middle">Włącz przynajmniej jedną serię (klik w etykiety wyżej)</text></svg>';
    LAYOUT={W:W,H:H,PT:PT,PB:PB,PL:PL,PR:PR,xN:xN,rows:rows,activeK:activeK,yk:yk,mode:CHART_MODE};mountChart(host);
    const leg0=document.getElementById("chartlegend");if(leg0)leg0.innerHTML='<div class="lgempty">Włącz serię, aby zobaczyć jej skalę i opis.</div>';
    return;
  }

  const xf=i=>PL+(xN<=1?0:i*(W-PL-PR)/(xN-1));
  const dayTicks=(yBottom)=>{
    const nx=Math.max(2,Math.min(9,xN));const xidx=[];
    for(let j=0;j<nx;j++){const ii=Math.round(j*(xN-1)/(nx-1));if(xidx[xidx.length-1]!==ii)xidx.push(ii);}
    let o="";xidx.forEach(i=>{const x=xf(i).toFixed(1);o+='<line x1="'+x+'" y1="'+PT+'" x2="'+x+'" y2="'+yBottom+'" stroke="'+_GCOL.gv+'" stroke-width="1"/>';o+='<text x="'+x+'" y="'+(H-8)+'" fill="'+_GCOL.ax+'" font-size="10" text-anchor="middle">'+fmtDay(rows[i].day)+'</text>';});
    return o;
  };
  const pathFor=(k)=>{const yki=yk[k];let d="",st=false;rows.forEach((r,i)=>{const v=val(r,k);if(v==null){st=false;return;}d+=(st?"L":"M")+xf(i).toFixed(1)+" "+_yv(yki,v).toFixed(1)+" ";st=true;});return d;};
  const endLabel=(k)=>{const li=_lastIdx(rows,k);if(li<0)return "";const v=val(rows[li],k);const x=Math.min(W-2,xf(li)+3);const y=_yv(yk[k],v);const lab=M[k].label.replace(/\s*\(.*\)/,"");return '<text x="'+x.toFixed(1)+'" y="'+(y-3).toFixed(1)+'" fill="'+M[k].col+'" font-size="10" font-weight="700">'+esc(lab)+'</text>';};

  let s="";

  if(CHART_MODE==="panels"){
    PL=6;PR=64;
    const bandH=58,gap=14;
    H=PT+PB+activeK.length*bandH+(activeK.length-1)*gap;
    s='<svg class="csvg" style="height:'+H+'px" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">';
    s+=dayTicks(H-PB);
    activeK.forEach((k,idx)=>{
      const top=PT+idx*(bandH+gap),bot=top+bandH;
      const sc=_seriesScale(rows,k)||{mn:0,mx:1,rg:1};
      yk[k]={mn:sc.mn,rg:sc.rg,yTop:top+6,yBot:bot-2};
      s+='<line x1="'+PL+'" y1="'+bot.toFixed(1)+'" x2="'+(W-PR)+'" y2="'+bot.toFixed(1)+'" stroke="'+_GCOL.base+'" stroke-width="1"/>';
      s+='<text x="'+(W-PR+6)+'" y="'+(top+9).toFixed(1)+'" fill="'+_GCOL.ax+'" font-size="9">'+fmt(sc.mx,M[k].dec)+'</text>';
      s+='<text x="'+(W-PR+6)+'" y="'+(bot).toFixed(1)+'" fill="'+_GCOL.ax+'" font-size="9">'+fmt(sc.mn,M[k].dec)+'</text>';
      const dk=M[k].dash?(' stroke-dasharray="'+M[k].dash+'"'):'';
      s+='<path d="'+pathFor(k)+'" fill="none" stroke="'+M[k].col+'" stroke-width="2"'+dk+'/>';
      s+='<text x="'+(PL+2)+'" y="'+(top+9).toFixed(1)+'" fill="'+M[k].col+'" font-size="11" font-weight="700">'+esc(M[k].label)+(M[k].unit?' ['+esc(M[k].unit)+']':'')+'</text>';
    });
    s+='</svg>';
  } else if(CHART_MODE==="norm"){
    PL=40;PR=64;H=340;const yTop=PT,yBot=H-PB;
    activeK.forEach(k=>{const sc=_seriesScale(rows,k)||{mn:0,mx:1,rg:1};yk[k]={mn:sc.mn,rg:sc.rg,yTop:yTop,yBot:yBot};});
    s='<svg class="csvg" style="height:'+H+'px" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">';
    for(let g=0;g<=4;g++){const y=yTop+g*(yBot-yTop)/4;const pct=100-g*25;s+='<line x1="'+PL+'" y1="'+y+'" x2="'+(W-PR)+'" y2="'+y+'" stroke="'+_GCOL.gh+'" stroke-width="1"/>';s+='<text x="'+(PL-6)+'" y="'+(y+3)+'" fill="'+_GCOL.ax+'" font-size="10" text-anchor="end">'+pct+'%</text>';}
    s+=dayTicks(yBot);
    activeK.forEach(k=>{const dk=M[k].dash?(' stroke-dasharray="'+M[k].dash+'"'):'';s+='<path d="'+pathFor(k)+'" fill="none" stroke="'+M[k].col+'" stroke-width="2"'+dk+'/>';});
    activeK.forEach(k=>{s+=endLabel(k);});
    s+='</svg>';
  } else {
    const axisW=38;
    const grpOrder=[],grpMembers={};
    activeK.forEach(k=>{const g=M[k].grp;if(!grpMembers[g]){grpMembers[g]=[];grpOrder.push(g);}grpMembers[g].push(k);});
    const grpScale={};
    grpOrder.forEach(g=>{let a=[];grpMembers[g].forEach(k=>rows.forEach(r=>{const v=val(r,k);if(v!=null)a.push(v);}));if(a.length){const mn=Math.min(...a),mx=Math.max(...a);grpScale[g]={mn:mn,mx:mx,rg:(mx-mn)||1};}});
    const sideg={};let L=0,R=0;grpOrder.forEach((g,i)=>{if(!grpScale[g])return;if(i%2===0){sideg[g]={s:"L",i:L++};}else{sideg[g]={s:"R",i:R++};}});
    H=340;PL=8+L*axisW;PR=8+R*axisW;const yTop=PT,yBot=H-PB;
    activeK.forEach(k=>{const g=M[k].grp;const sc=grpScale[g];if(sc)yk[k]={mn:sc.mn,rg:sc.rg,yTop:yTop,yBot:yBot};});
    s='<svg class="csvg" style="height:'+H+'px" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">';
    for(let g=0;g<=4;g++){const y=yTop+g*(yBot-yTop)/4;s+='<line x1="'+PL+'" y1="'+y+'" x2="'+(W-PR)+'" y2="'+y+'" stroke="'+_GCOL.gh+'" stroke-width="1"/>';}
    s+=dayTicks(yBot);
    grpOrder.forEach(g=>{const sc=grpScale[g];if(!sc)return;const pos=sideg[g];const col=(grpMembers[g].length===1)?M[grpMembers[g][0]].col:_GCOL.ax;const xa=(pos.s==="L")?(3+pos.i*axisW):(W-PR+4+pos.i*axisW);const mid=sc.mn+sc.rg/2;s+='<text x="'+xa+'" y="'+(yTop+8)+'" fill="'+col+'" font-size="10">'+fmt(sc.mx,1)+'</text>';s+='<text x="'+xa+'" y="'+((yTop+yBot)/2)+'" fill="'+col+'" font-size="10">'+fmt(mid,1)+'</text>';s+='<text x="'+xa+'" y="'+yBot+'" fill="'+col+'" font-size="10">'+fmt(sc.mn,1)+'</text>';s+='<text x="'+xa+'" y="'+(yTop-3)+'" fill="'+col+'" font-size="9">'+(GRPU[g]||"")+'</text>';});
    activeK.forEach(k=>{const dk=M[k].dash?(' stroke-dasharray="'+M[k].dash+'"'):'';s+='<path d="'+pathFor(k)+'" fill="none" stroke="'+M[k].col+'" stroke-width="2"'+dk+'/>';});
    s+='</svg>';
  }

  host.innerHTML=s;
  LAYOUT={W:W,H:H,PT:PT,PB:PB,PL:PL,PR:PR,xN:xN,rows:rows,activeK:activeK,yk:yk,mode:CHART_MODE};
  mountChart(host);

  const leg=document.getElementById("chartlegend");
  if(leg){
    const zoomed=(X0>0||X1<N-1);
    let zinfo="";
    if(zoomed && rows.length){zinfo='<div class="lgempty">🔍 zoom: '+esc(rows[0].day||"")+' → '+esc(rows[rows.length-1].day||"")+' ('+rows.length+' dni) · kliknij wykres, aby zresetować</div>';}
    leg.innerHTML=zinfo+'<div class="lgpills">'+activeK.map(k=>{
      const m=M[k],latest=nnAt(k,N-1),u=m.unit?(" "+esc(m.unit)):"";
      const tip='<span class="lgtip"><b>'+esc(m.label)+(m.unit?" ["+esc(m.unit)+"]":"")+'</b>'+esc(m.desc)+' <i>'+esc(m.interp)+'</i></span>';
      return '<span class="lgpill"><span class="sw" style="background:'+m.col+'"></span><b>'+esc(m.label)+'</b><span class="pv">'+fmt(latest,m.dec)+u+'</span>'+tip+'</span>';
    }).join("")+'</div>';
  }
}
let _ovl=null,_tip=null,_sel=null,_drag=null;
function _ensureStyle(){
  if(document.getElementById("forma-cx-style"))return;
  const st=document.createElement("style");st.id="forma-cx-style";
  st.textContent="#chartbox{position:relative;background:var(--chart-bg,transparent);border-radius:10px;border:1px solid var(--chart-border,transparent)}"
    +".fx-ovl{position:absolute;left:0;top:0;width:100%;height:340px;pointer-events:none;overflow:visible}"
    +".fx-tip{position:absolute;pointer-events:none;display:none;background:#1c2024;color:#f6f2ea;border-radius:9px;padding:8px 10px;font-size:11px;line-height:1.5;box-shadow:0 8px 22px rgba(0,0,0,.30);z-index:30;min-width:140px;white-space:nowrap}"
    +".fx-tip .cth{font-weight:700;color:#fff;margin-bottom:4px}"
    +".fx-tip .ctr{display:flex;align-items:center;gap:6px}"
    +".fx-tip .cs{width:9px;height:9px;border-radius:2px;display:inline-block;flex:0 0 auto}"
    +".fx-tip .cl{color:#c3ccd4}"
    +".fx-tip .cv{margin-left:auto;font-weight:600;color:#fff;padding-left:12px}"
    +".fx-sel{position:absolute;top:0;height:340px;background:rgba(63,111,154,.15);border-left:1px solid var(--accent);border-right:1px solid var(--accent);pointer-events:none;display:none;z-index:20}"+".lgpills{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}"+".lgpill{position:relative;display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border:1px solid #ccc;border-radius:999px;font-size:12px;background:var(--card,#fff);color:var(--ink,#1c2024);cursor:help}"+".lgpill .sw{width:10px;height:10px;border-radius:3px;flex:0 0 auto}"+".lgpill .pv{color:var(--muted,#7a838c);font-weight:600}"+".lgpill .lgtip{position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);width:250px;background:#1c2024;color:#f6f2ea;border-radius:9px;padding:9px 11px;font-size:11.5px;line-height:1.45;box-shadow:0 8px 22px rgba(0,0,0,.32);display:none;z-index:60;white-space:normal;text-align:left}"+".lgpill .lgtip b{display:block;color:#fff;margin-bottom:3px}"+".lgpill .lgtip i{color:#c3ccd4;font-style:italic}"+".lgpill:hover .lgtip{display:block}";
  document.head.appendChild(st);
}
function mountChart(host){
  _ensureStyle();
  if(!host._fxwired){
    host.style.position="relative";
    host.addEventListener("mousemove",_onMove);
    host.addEventListener("mouseleave",_onLeave);
    host.addEventListener("mousedown",_onDown);
    host._fxwired=true;
  }
  const NS="http://www.w3.org/2000/svg";
  _ovl=document.createElementNS(NS,"svg");_ovl.setAttribute("class","fx-ovl");
  _ovl.setAttribute("viewBox","0 0 "+LAYOUT.W+" "+LAYOUT.H);_ovl.setAttribute("preserveAspectRatio","none");
  _ovl.style.height=LAYOUT.H+"px";
  host.appendChild(_ovl);
  _sel=el("div","fx-sel");_sel.style.height=LAYOUT.H+"px";host.appendChild(_sel);
  _tip=el("div","fx-tip");host.appendChild(_tip);
}
function _box(){return document.getElementById("chartbox").getBoundingClientRect();}
function _pxIdx(clientX){
  const r=_box();const {PL,PR,xN,W}=LAYOUT;
  if(xN<=1)return 0;
  const ux=(clientX-r.left)/r.width*W;
  return Math.max(0,Math.min(xN-1,Math.round((ux-PL)/(W-PL-PR)*(xN-1))));
}
function _xfPx(i){return LAYOUT.PL+(LAYOUT.xN<=1?0:i*(LAYOUT.W-LAYOUT.PL-LAYOUT.PR)/(LAYOUT.xN-1));}
function _showHover(i){
  if(!LAYOUT||!_ovl)return;const rows=LAYOUT.rows,activeK=LAYOUT.activeK,W=LAYOUT.W,yk=LAYOUT.yk;if(!rows[i])return;
  const ux=_xfPx(i);
  let o='<line x1="'+ux.toFixed(1)+'" y1="'+LAYOUT.PT+'" x2="'+ux.toFixed(1)+'" y2="'+(LAYOUT.H-LAYOUT.PB)+'" stroke="'+_GCOL.cur+'" stroke-width="1" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"/>';
  activeK.forEach(k=>{const v=val(rows[i],k);if(v==null||!yk[k])return;o+='<circle cx="'+ux.toFixed(1)+'" cy="'+_yv(yk[k],v).toFixed(1)+'" r="3.2" fill="'+M[k].col+'" stroke="#fff" stroke-width="1" vector-effect="non-scaling-stroke"/>';});
  _ovl.innerHTML=o;
  let html='<div class="cth">'+esc(rows[i].day||"—")+'</div>';
  if(activeK.length){activeK.forEach(k=>{const v=val(rows[i],k),m=M[k];html+='<div class="ctr"><span class="cs" style="background:'+m.col+'"></span><span class="cl">'+esc(m.label)+'</span><span class="cv">'+(v==null?"—":fmt(v,m.dec)+(m.unit?" "+esc(m.unit):""))+'</span></div>';});}
  else{html+='<div class="ctr"><span class="cl">włącz serię</span></div>';}
  _tip.innerHTML=html;_tip.style.display="block";
  const r=_box();const pxLeft=ux/W*r.width,tw=_tip.offsetWidth;
  let lx=pxLeft+14;if(lx+tw>r.width)lx=pxLeft-14-tw;if(lx<2)lx=2;
  _tip.style.left=lx+"px";_tip.style.top="6px";
}
function _clearHover(){if(_ovl)_ovl.innerHTML="";if(_tip)_tip.style.display="none";}
function _updSel(clientX){const r=_box();let x=clientX-r.left;x=Math.max(0,Math.min(r.width,x));const a=Math.min(_drag.x0,x),b=Math.max(_drag.x0,x);_sel.style.left=a+"px";_sel.style.width=(b-a)+"px";}
function _onMove(e){if(_drag){_updSel(e.clientX);return;}if(!LAYOUT||LAYOUT.xN<=1)return;_showHover(_pxIdx(e.clientX));}
function _onLeave(){if(_drag)return;_clearHover();}
function _onDown(e){
  if(!LAYOUT||LAYOUT.xN<=1)return;
  const r=_box();_drag={x0:Math.max(0,Math.min(r.width,e.clientX-r.left))};
  _clearHover();_sel.style.display="block";_sel.style.left=_drag.x0+"px";_sel.style.width="0px";
  const mv=e2=>_updSel(e2.clientX);
  const up=e2=>{
    const r2=_box();const x1=Math.max(0,Math.min(r2.width,e2.clientX-r2.left));
    const moved=Math.abs(x1-_drag.x0);_sel.style.display="none";
    if(moved>=8){
      const a=Math.min(_drag.x0,x1),b=Math.max(_drag.x0,x1);
      const {PL,PR,xN,W}=LAYOUT;
      const f=px=>{const ux=px/r2.width*W;return Math.max(0,Math.min(xN-1,Math.round((ux-PL)/(W-PL-PR)*(xN-1))));};
      const i0=f(a),i1=f(b);
      if(i1>i0){const nx0=X0+i0,nx1=X0+i1;if(nx1-nx0>=1){X0=nx0;X1=nx1;drawChart();}}
    }else{X1=N-1;X0=Math.max(0,N-CHART_DAYS);drawChart();}
    _drag=null;window.removeEventListener("mousemove",mv);window.removeEventListener("mouseup",up);
  };
  window.addEventListener("mousemove",mv);window.addEventListener("mouseup",up);
}

/* ---------- ANALIZA LLM (na zadanie) ---------- */
function _asideEls(){
  let a=document.getElementById("qaside");
  if(!a){
    a=el("div","qaside");a.id="qaside";
    a.innerHTML='<div class="qaside-head"><span class="qaside-title">Analiza AI</span><button class="qaside-x" type="button" aria-label="Zamknij">\u00d7</button></div><div class="qaside-body"><div class="qa-h"></div><div class="qa-tx"></div></div>';
    const bd=el("div","qaside-backdrop");
    const tab=el("button","qaside-tab");tab.type="button";tab.textContent="Analiza AI";
    document.body.appendChild(a);document.body.appendChild(bd);document.body.appendChild(tab);
    a.querySelector(".qaside-x").onclick=()=>document.body.classList.remove("qaside-open");
    bd.onclick=()=>document.body.classList.remove("qaside-open");
    tab.onclick=()=>{if(document.body.classList.contains("qaside-has")){document.body.classList.add("qaside-open");}else{runAnalyze("today");}};
  }
  return {head:a.querySelector(".qa-h"),tx:a.querySelector(".qa-tx")};
}
function asideShow(title,html){
  const e=_asideEls();e.head.textContent=title;e.tx.innerHTML=html;
  document.body.classList.add("qaside-has");document.body.classList.add("qaside-open");
}
async function runAnalyze(mode,btn){
  _openRideEid=null;
  const payload={mode:mode};
  if(mode==="chart"){
    if(!N)return;
    const rows=ROWS.slice(X0,X1+1);if(!rows.length)return;
    const activeK=CHART_ORDER.filter(k=>ACTIVE.has(k));
    if(!activeK.length){asideShow("Analiza wykresu","W\u0142\u0105cz przynajmniej jedn\u0105 seri\u0119 (klik w etykiety nad wykresem).");return;}
    payload.start=rows[0].day;payload.end=rows[rows.length-1].day;payload.series=activeK;
  }
  const hd=mode==="chart"?"Analiza wykresu":(mode==="coach"?"Doradca \u2014 najbli\u017csza jazda i 7 dni":(mode==="event"?"Plan przygotowania do celu":"Analiza \u2014 stan na dzi\u015b"));
  asideShow(hd,'<span style="color:var(--muted)">Analizuj\u0119\u2026</span>');
  if(btn)btn.disabled=true;
  try{
    const r=await fetch("/api/forma/analyze",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify(payload)});
    const j=await r.json().catch(()=>null);
    if(!r.ok)throw new Error((j&&j.detail)||("HTTP "+r.status));
    const title=(mode==="chart")?(hd+" ("+esc(payload.start)+" \u2192 "+esc(payload.end)+")"):hd;
    asideShow(title,esc(j&&j.text?j.text:"(pusto)").replace(/\n/g,"<br>"));
  }catch(e){
    asideShow("Analiza",'<span style="color:var(--bad)">B\u0142\u0105d: '+esc(e.message)+'</span>');
  }finally{
    if(btn)btn.disabled=false;
  }
}

/* ---------- WIRING ---------- */
function wire(){
  wireDzis();
  document.querySelectorAll("#winsel button[data-w]").forEach(b=>b.onclick=()=>{
    document.querySelectorAll("#winsel button[data-w]").forEach(x=>x.classList.remove("active"));
    b.classList.add("active");WIN=parseInt(b.dataset.w,10);renderCards();renderToday();
  });
  const tb=document.getElementById("trendbtn");
  if(tb)tb.onclick=()=>{TREND=!TREND;tb.classList.toggle("active",TREND);renderCards();renderToday();};
  document.querySelectorAll("#rng button").forEach(b=>b.onclick=()=>{
    document.querySelectorAll("#rng button").forEach(x=>x.classList.remove("active"));
    b.classList.add("active");CHART_DAYS=parseInt(b.dataset.days,10);X1=N-1;X0=Math.max(0,N-CHART_DAYS);drawChart();
  });
  const _cb=document.getElementById("chartbox");
  if(_cb && !document.getElementById("chartmode")){
    const _bar=el("div","rng");_bar.id="chartmode";_bar.style.marginBottom="8px";
    [["norm","Znormalizowany"],["panels","Panele"],["abs","Wartości"]].forEach(mm=>{
      const _b=el("button");_b.type="button";_b.dataset.mode=mm[0];_b.textContent=mm[1];if(mm[0]===CHART_MODE)_b.classList.add("active");
      _b.onclick=()=>{CHART_MODE=mm[0];try{localStorage.setItem("qforma_chartmode",CHART_MODE);}catch(e){}document.querySelectorAll("#chartmode button").forEach(x=>x.classList.remove("active"));_b.classList.add("active");drawChart();};
      _bar.appendChild(_b);
    });
    _cb.parentNode.insertBefore(_bar,_cb);
  }
  const _ab=document.getElementById("chart-analyze");
  if(_ab)_ab.onclick=()=>runAnalyze("chart",_ab);
}

/* ---------- WSKAZNIKI ZRODEL DANYCH (naglowek) ---------- */
const SOURCES=[
  {name:"ModelQ", keys:["ftp","ctl","atl"]},
  {name:"Wellness", keys:["hrv","rhr","slp"]},
  {name:"Waga", keys:["wgt"]},
  {name:"Glikogen", keys:["glyc"]},
];
function _daysAgo(dstr){
  if(!dstr)return null;const p=String(dstr).split("-");if(p.length<3)return null;
  const d=new Date(+p[0],+p[1]-1,+p[2]);const now=new Date();now.setHours(0,0,0,0);
  return Math.round((now-d)/86400000);
}
function _srcLatestDay(keys){
  for(let i=ROWS.length-1;i>=0;i--){const r=ROWS[i];for(const k of keys){if(val(r,k)!=null)return r.day;}}
  return null;
}
function renderSources(){
  const box=document.getElementById("qsrc");if(!box)return;
  box.innerHTML=SOURCES.map(sc=>{
    const day=_srcLatestDay(sc.keys),age=_daysAgo(day);
    let cls="bad",txt="brak danych";
    if(age!=null){cls=age<=1?"ok":(age<=3?"warn":"bad");txt="ostatnie: "+day+" ("+(age<=0?"dziś":(age===1?"wczoraj":age+" dni temu"))+")";}
    return '<span class="src"><span class="dot '+cls+'"></span>'+esc(sc.name)+'<span class="st">'+esc(sc.name)+' — '+esc(txt)+'</span></span>';
  }).join("");
}

async function boot(){
  wire();
  loadEventPrep();
  let data;
  try{
    const end=qDateLocal();
    const s=new Date();s.setDate(s.getDate()-100);const start=qDateLocal(s);
    const r=await fetch("/api/forma/data?start="+start+"&end="+end);
    if(!r.ok) throw new Error("HTTP "+r.status);
    data=await r.json();
  }catch(e){
    const b=document.getElementById("hero");if(b)b.innerHTML='<div class="hero" style="border-color:var(--bad);color:var(--bad)"><div class="lab">Błąd</div><div class="big">Nie udało się załadować danych</div><div class="exp">'+e.message+'</div></div>';
    return;
  }
  ROWS=data.series||[];N=ROWS.length;LAT=data.latest||{};
  X1=N-1;X0=Math.max(0,N-CHART_DAYS);
  renderHero();renderCards();renderChecks();drawChart();_asideEls();renderSources();renderToday();
  fetch("/api/forma/activities?n=3",{credentials:"same-origin"}).then(function(r){return r.ok?r.json():null;}).then(function(j){ACTS=(j&&j.activities)||[];renderHero();}).catch(function(){ACTS=[];renderHero();});
  fetch("/api/prefs?key=dzis",{credentials:"same-origin"}).then(function(r){return r.ok?r.json():null;}).then(function(pj){var v=pj&&pj.value;if(v&&typeof v==="object"){if(typeof v.hero==="boolean")DZIS.hero=v.hero;if(typeof v.event==="boolean")DZIS.event=v.event;if(Array.isArray(v.keys))DZIS.keys=v.keys.filter(function(k){return M[k]||k==="nut_balance"||k==="nut_body"||k==="event_prep";});renderToday();var cb=document.getElementById("dzis-cust");if(cb&&cb.style.display&&cb.style.display!=="none")renderDzisCust();}}).catch(function(){});
}
boot();
