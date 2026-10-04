/* czas lokalny (strefa przegladarki) -- wspolne dla QBot lab */function qTsLocal(s,naiveUtc){if(!s)return"";var t=String(s).trim().replace(" ","T").replace(/\.\d+/,"");if(/[+-]\d\d$/.test(t))t+=":00";t=t.replace(/([+-]\d\d)(\d\d)$/,"$1:$2");if(!/(Z|[+-]\d\d:\d\d)$/i.test(t)){if(!naiveUtc)return t.slice(0,16).replace("T"," ");t+="Z";}var d=new Date(t);if(isNaN(d.getTime()))return String(s).slice(0,16);var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());}function qDateLocal(d){d=d||new Date();var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
/* garaz-render.js — serwis Garaz: baza rzeczy (tabela + filtry) i okno dodaj/edytuj.
   Zrodla: /api/garage/list, /save, /toggle, /photo, /photo/delete, /photo/from-url, /scrape. */
(function(){
"use strict";
const $ = s => document.querySelector(s);
const el = (t,c,h) => { const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.textContent=h; return e; };
async function getJSON(u){ const r=await fetch(u,{credentials:"same-origin",cache:"no-store"}); if(!r.ok) throw new Error(r.status); return r.json(); }
async function postJSON(u,b){ const r=await fetch(u,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}); if(!r.ok) throw new Error(r.status); return r.json(); }

let DATA={items:[],categories:[],conditions:[],seasons:[],fabrics:[],palette:[]};
let SHOW_ALL=false, SCRAPED_IMG="", HAD_PHOTO=false;
let SORT={key:"category",dir:1};
let SEASON_SEL=new Set(), RATING_SEL=null;

const SEASON_SHORT={zima:"Z", przejsciowy:"P", lato:"L"};
const COLOR_HEX={BLACK:"#22252a",GREY:"#8b9199",WHITE:"#f4f2ec",BEIGE:"#d9c49a",BROWN:"#7a5236",
  GREEN:"#3f7a4d",OLIVE:"#6b7043",BLUE:"#3a6ea8",NAVY:"#26375e",RED:"#a6503d",
  ORANGE:"#d1762e",YELLOW:"#d9b02e",MULTI:"#b08fb0"};

const COLS=[
  {key:"category",label:"Kategoria"},
  {key:"brand",label:"Marka"},
  {key:"model",label:"Model"},
  {key:"size",label:"Rozmiar"},
  {key:"color_q",label:"Kolor"},
  {key:"fabric",label:"Materiał"},
  {key:"season",label:"Sezon"},
  {key:"rating",label:"Ocena",num:true},
  {key:"weight_g",label:"Waga",num:true},
  {key:"condition",label:"Stan"},
  {key:"purchase_price",label:"Cena",num:true}
];

function debounce(fn,ms){ let t; return function(){ clearTimeout(t); t=setTimeout(fn,ms); }; }

async function load(){
  try{
    DATA=await getJSON("/api/garage/list?all="+(SHOW_ALL?1:0)+"&_="+Date.now());
    populateFilters();
    render();
  }catch(e){ const b=$("#garageBody"); b.innerHTML=""; b.appendChild(el("div","empty","błąd ładowania ("+e.message+")")); }
}

function distinct(items,key){ const s=new Set(); items.forEach(i=>{ const v=i[key]; if(v) s.add(v); }); return Array.from(s); }

function fillSel(sel, values, placeholder){
  const cur=sel.value; sel.innerHTML="";
  const o0=el("option",null,placeholder); o0.value=""; sel.appendChild(o0);
  values.forEach(v=>{ const o=el("option",null,v); o.value=v; sel.appendChild(o); });
  sel.value = values.indexOf(cur)>=0 ? cur : "";
}
let FILLED=false;
function populateFilters(){
  const items=DATA.items||[], order=DATA.categories||[];
  const cats=distinct(items,"category").sort((a,b)=>{ const ia=order.indexOf(a),ib=order.indexOf(b); return (ia<0?99:ia)-(ib<0?99:ib); });
  const _bm={}; distinct(items,"brand").forEach(b=>{ const k=String(b).trim().toLowerCase(); if(!_bm[k]) _bm[k]=b; });
  const brands=Object.values(_bm).sort((a,b)=>a.localeCompare(b,"pl",{sensitivity:"base"}));
  const colors=distinct(items,"color_q").sort();
  const fabrics=(DATA.fabrics||[]).filter(f=>items.some(i=>i.fabric===f));
  fillSel($("#gfilter"), cats, "wszystkie kategorie");
  fillSel($("#gfilterBrand"), brands, "wszystkie marki");
  fillSel($("#gfilterColor"), colors, "wszystkie kolory");
  fillSel($("#gfilterFabric"), fabrics, "każdy materiał");
  FILLED=true;
}

function getFiltered(){
  const q=$("#gsearch").value.trim().toLowerCase();
  const cat=$("#gfilter").value, br=$("#gfilterBrand").value;
  const col=$("#gfilterColor").value, sez=$("#gfilterSeason").value;
  const fab=$("#gfilterFabric").value;
  return (DATA.items||[]).filter(it=>{
    if(cat && it.category!==cat) return false;
    if(br && String(it.brand||"").trim().toLowerCase()!==String(br).trim().toLowerCase()) return false;
    if(col && String(it.color_q||"").toLowerCase()!==String(col).toLowerCase()) return false;
    if(fab && it.fabric!==fab) return false;
    if(sez && !String(it.season||"").split(",").includes(sez)) return false;
    if(q){ const hay=[it.brand,it.model,it.size,it.color,it.color_q,it.notes,it.sku,it.ean].map(x=>(x||"")).join(" ").toLowerCase(); if(hay.indexOf(q)<0) return false; }
    return true;
  });
}

function cmp(a,b){
  const k=SORT.key; let r;
  if(k==="category"){
    const order=DATA.categories||[]; const ia=order.indexOf(a.category), ib=order.indexOf(b.category);
    r=(ia<0?99:ia)-(ib<0?99:ib);
    if(r===0) r=(a.model||"").localeCompare(b.model||"","pl",{sensitivity:"base"});
  } else if(["weight_g","purchase_price","rating","capacity_l","r_intensity","r_breath",
             "r_dry","r_insul","r_wind","r_water","r_pack"].indexOf(k)>=0){
    const av=(k==="rating"?a.ocena:a[k]), bv=(k==="rating"?b.ocena:b[k]);
    if(av==null&&bv==null) r=0; else if(av==null) return 1; else if(bv==null) return -1; else r=av-bv;
  } else {
    const av=a[k]||"", bv=b[k]||"";
    if(!av&&bv) return 1; if(av&&!bv) return -1;
    r=av.localeCompare(bv,"pl",{sensitivity:"base"});
  }
  return r*SORT.dir;
}

function td(t){ return el("td",null,(t==null||t==="")?"—":t); }
function tdn(t){ return el("td","num",(t==null||t==="")?"—":t); }
function tdColor(q){
  const c=el("td");
  if(!q){ c.textContent="—"; return c; }
  const d=el("span","dot"); d.style.background=COLOR_HEX[q]||"#bbb"; c.appendChild(d);
  c.appendChild(document.createTextNode(q)); return c;
}
function tdFabric(f){
  const c=el("td");
  if(!f){ c.textContent="—"; return c; }
  const b=el("span","fab"+(f.indexOf("merino")===0?" mer":""), f);
  c.appendChild(b); return c;
}
function tdSeason(s){
  const c=el("td"); const set=new Set(String(s||"").split(","));
  if(!s){ c.textContent="—"; return c; }
  const box=el("span","sez");
  ["zima","przejsciowy","lato"].forEach(k=>{ const b=el("b",set.has(k)?"on":null,SEASON_SHORT[k]); box.appendChild(b); });
  c.appendChild(box); return c;
}
function tdOcena(it){
  const c=el("td","num"), v=it.ocena;
  if(v==null){ c.textContent="—"; c.title="brak ankiety (Dopasowanie)"; return c; }
  if(v===0){ const s=el("span",null,"0"); s.style.color="var(--bad)"; s.style.fontWeight="700"; c.title="Dopasowanie poniżej 0 — nie do jazdy"; c.appendChild(s); return c; }
  const s=el("span","stars","★".repeat(Math.round(v))); c.appendChild(s);
  const n=el("span",null," "+v); n.style.fontSize="12px"; n.style.color="var(--muted)"; c.appendChild(n);
  c.title=(it.s_status==="ok"?"z ankiety":"z ocen wstępnych AI"); return c;
}
function tdStars(v){
  const c=el("td","num");
  if(v==null){ c.textContent="—"; return c; }
  const s=el("span","stars","★".repeat(v)); c.appendChild(s); return c;
}


/* komorka tabeli zaleznie od pola (wybor kolumn: garaz-columns.js) */
function cellFor(it, key){
  switch(key){
    case "color_q":  return tdColor(it.color_q);
    case "fabric":   return tdFabric(it.fabric);
    case "season":   return tdSeason(it.season);
    case "rating":   return tdOcena(it);
    case "weight_g": return tdn(it.weight_g!=null ? it.weight_g+" g" : "");
    case "purchase_price": return tdn(it.purchase_price!=null ? Math.round(it.purchase_price)+" zł" : "");
    case "model":    { const c=td(it.model); c.className="mdl"; return c; }
    case "notes":    { const c=td((it.notes||"").slice(0,90)); c.style.fontSize="13px"; c.style.color="var(--muted)"; return c; }
    case "r_intensity": case "r_breath": case "r_dry": case "r_insul":
    case "r_wind": case "r_water": case "r_pack":
      return tdn(it[key]==null ? "" : String(it[key]));
    default:         return td(it[key]);
  }
}

function render(){
  const body=$("#garageBody"); body.innerHTML="";
  const items=getFiltered(); const total=(DATA.items||[]).length;
  $("#gcount").textContent = items.length===total ? (total+" szt.") : (items.length+" / "+total+" szt.");
  if(!items.length){ body.appendChild(el("div","empty","Brak rzeczy dla tych filtrów.")); return; }
  items.sort(cmp);

  const AKT = (window.QCols ? QCols.columns("gear") : COLS);
  const table=el("table","gt"), thead=el("thead"), htr=el("tr");
  AKT.forEach(c=>{
    const th=el("th", c.num?"num":null); th.textContent=c.label;
    if(SORT.key===c.key) th.appendChild(el("span","ar", SORT.dir>0?"▲":"▼"));
    th.addEventListener("click",()=>{ if(SORT.key===c.key) SORT.dir=-SORT.dir; else { SORT.key=c.key; SORT.dir=1; } render(); });
    htr.appendChild(th);
  });
  htr.appendChild(el("th","noclick",""));
  thead.appendChild(htr); table.appendChild(thead);

  const tb=el("tbody");
  items.forEach(it=>{
    const tr=el("tr", it.active?null:"arch");
    tr.style.cursor="pointer";
    tr.addEventListener("click",()=>openModal(it));
    AKT.forEach(c=>tr.appendChild(cellFor(it, c.key)));
    const act=el("td"), box=el("div","gact");
    const be=el("button",null,"Edytuj"); be.addEventListener("click",e=>{e.stopPropagation();openModal(it);}); box.appendChild(be);
    const bo=el("button","sec","Ocena"); bo.title="Ankieta ocen tej rzeczy"; bo.addEventListener("click",e=>{e.stopPropagation();svyOpenOne(it);}); box.appendChild(bo);
    act.appendChild(box); tr.appendChild(act);
    tb.appendChild(tr);
  });
  table.appendChild(tb); body.appendChild(table);
}

async function toggle(it){
  try{ await postJSON("/api/garage/toggle",{id:it.id, active: it.active?0:1}); load(); }catch(e){}
}

function selOpts(sel, values, cur){
  sel.innerHTML="";
  (values||[]).forEach(v=>{ const o=el("option",null,v); o.value=v; if(v===cur)o.selected=true; sel.appendChild(o); });
}
function selOptsCat(sel, values, cur){
  sel.innerHTML="";
  if(!cur){ const o=el("option",null,"— wybierz —"); o.value=""; sel.appendChild(o); }
  (values||[]).forEach(v=>{ const o=el("option",null,v); o.value=v; if(v===cur)o.selected=true; sel.appendChild(o); });
  if(!cur) sel.value="";
}
function selOptsColorQ(cur){
  const sel=$("#m_color_q"); sel.innerHTML="";
  const o0=el("option",null,"— auto —"); o0.value=""; sel.appendChild(o0);
  (DATA.palette||[]).forEach(v=>{ const o=el("option",null,v); o.value=v; if(v===cur)o.selected=true; sel.appendChild(o); });
  sel.value = cur || "";
}

function paintSeason(){
  document.querySelectorAll("#mSeason button").forEach(b=>{
    b.classList.toggle("on", SEASON_SEL.has(b.dataset.s));
  });
}
function paintRating(){
  document.querySelectorAll("#mRating button").forEach(b=>{
    b.classList.toggle("on", RATING_SEL!=null && Number(b.dataset.v)<=RATING_SEL);
  });
}

function openModal(it){
  it=it||{};
  $("#mTitle").textContent = it.id ? "Edytuj rzecz" : "Dodaj rzecz";
  $("#m_id").value = it.id||"";
  selOptsCat($("#m_category"), DATA.categories, it.category||"");
  selOpts($("#m_condition"), DATA.conditions, it.condition || (it.id ? "Good" : "New"));
  selOptsColorQ(it.color_q||"");
  (function(){ const s=$("#m_fabric"); s.innerHTML="";
    const o0=el("option",null,"— nie podano —"); o0.value=""; s.appendChild(o0);
    (DATA.fabrics||[]).forEach(v=>{ const o=el("option",null,v); o.value=v; if(v===it.fabric)o.selected=true; s.appendChild(o); });
    s.value=it.fabric||""; })();
  $("#m_brand").value=it.brand||"";
  $("#m_model").value=it.model||"";
  $("#m_size").value=it.size||"";
  $("#m_color").value=it.color||"";
  $("#m_purchase_date").value=it.purchase_date||"";
  $("#m_purchase_price").value=(it.purchase_price!=null?it.purchase_price:"");
  $("#m_weight_g").value=(it.weight_g!=null?it.weight_g:"");
  $("#m_ean").value=it.ean||"";
  $("#m_sku").value=it.sku||"";
  $("#m_notes").value=it.notes||"";
  $("#m_url").value=it.url||"";
  SEASON_SEL=new Set(String(it.season||"").split(",").filter(Boolean)); paintSeason();
  RATING_SEL=(it.rating!=null?Number(it.rating):null); paintRating();
  HAD_PHOTO=!!it.photo;
  const t=$("#mThumb"), hasImg=!!it.thumb;
  if(hasImg){ t.src=it.thumb; t.style.display=""; } else { t.style.display="none"; t.removeAttribute("src"); }
  t.dataset.full=it.photo||"";
  $("#mPhotoDel").style.display=hasImg?"":"none";
  $("#mPhotoLbl").style.display=it.id?"":"none";
  $("#mPhotoFile").value="";
  $("#mPhotoStatus").textContent = it.id ? "" : "zapisz rzecz, potem dodasz zdjęcie";
  SCRAPED_IMG=""; $("#mGrabPhoto").style.display="none"; $("#mUrlStatus").textContent="";
  const sez = it.season ? (" · sezon: "+it.season+(it.season_src==="llm"?" (wywnioskowany)":"")) : "";
  const fab = it.fabric ? (" · materiał: "+it.fabric+(it.fabric_src==="llm"?" (wywnioskowany)":"")) : "";
  $("#mMeta").textContent = it.id
    ? ("ID "+it.id+" · dodano: "+(qTsLocal(it.created_at,true)||"—")+" · SKU: "+(it.sku||"—")+" · EAN: "+(it.ean||"—")+sez+fab+" · "+(it.active===0?"archiwum":"aktywne"))
    : "nowa pozycja";
  $("#mStatus").textContent="";
  MODAL_IT = it.id ? it : null; RATE_AFTER=false;
  const rb=$("#mRate"); if(rb){ rb.style.display=""; rb.textContent = it.id ? "Ankieta" : "Zapisz i oceń"; }
  const ab=$("#mArch"); if(ab){ ab.style.display = it.id ? "" : "none"; ab.textContent = it.active===0 ? "Przywróć" : "Archiwum"; }
  const delBtn=$("#mDelete");
  delBtn.style.display = it.id ? "" : "none";
  delBtn.textContent="Usuń"; delBtn.classList.remove("armed"); delBtn.dataset.armed="";
  $("#gearModal").classList.add("open");
  document.body.classList.add("modal-open");
}
let MODAL_IT=null, RATE_AFTER=false;
function rateFromModal(){ if(MODAL_IT){ svyOpenOne(MODAL_IT); return; } RATE_AFTER=true; $("#mSave").click(); }
async function archFromModal(){ if(!MODAL_IT) return; const it=MODAL_IT; closeModal(); await toggle(it); }
function closeModal(){ $("#gearModal").classList.remove("open"); document.body.classList.remove("modal-open"); }

async function saveModal(){
  const b={
    id:$("#m_id").value||null,
    category:$("#m_category").value,
    condition:$("#m_condition").value,
    brand:$("#m_brand").value,
    model:$("#m_model").value,
    size:$("#m_size").value,
    color:$("#m_color").value,
    color_q:$("#m_color_q").value,
    fabric:$("#m_fabric").value,
    purchase_date:$("#m_purchase_date").value,
    purchase_price:$("#m_purchase_price").value,
    weight_g:$("#m_weight_g").value,
    ean:$("#m_ean").value,
    sku:$("#m_sku").value,
    url:$("#m_url").value,
    notes:$("#m_notes").value,
    season:Array.from(SEASON_SEL),
    rating:RATING_SEL
  };
  if(!b.category || !(b.brand||b.model)){ $("#mStatus").textContent="podaj kategorię oraz markę lub model"; return; }
  $("#mStatus").textContent="zapis…";
  let res;
  try{ res=await postJSON("/api/garage/save", b); }
  catch(e){ $("#mStatus").textContent="błąd zapisu ("+e.message+")"; return; }
  // automat: jesli zaciagnalismy zdjecie ze strony, a rzecz go nie ma - pobierz
  if(SCRAPED_IMG && res && res.id && !HAD_PHOTO){
    $("#mStatus").textContent="zapisano — pobieram zdjęcie ze strony…";
    try{ await postJSON("/api/garage/photo/from-url",{id:Number(res.id), url:SCRAPED_IMG}); }
    catch(e){ /* zdjecie opcjonalne - nie blokuje zapisu */ }
  }
  closeModal(); await load();
  if(RATE_AFTER && res && res.id){ const n=(DATA.items||[]).find(x=>Number(x.id)===Number(res.id)); if(n) svyOpenOne(n); }
  RATE_AFTER=false;
}

async function scrapeNow(){
  const u=$("#m_url").value.trim();
  if(!/^https?:\/\//i.test(u)){ $("#mUrlStatus").textContent="podaj adres http(s)"; return; }
  $("#mUrlStatus").textContent="zaciąganie (czytam stronę)…";
  try{
    const d=await postJSON("/api/garage/scrape",{url:u});
    const f=d.fields||{}, src=d.sources||{};
    const setE=(id,val)=>{ const e=$(id); if(e && !e.value && (val!==null&&val!==undefined&&val!=="")) e.value=val; };
    setE("#m_brand",f.brand); setE("#m_model",f.model); setE("#m_color",f.color);
    setE("#m_sku",f.sku); setE("#m_ean",f.ean); setE("#m_weight_g",f.weight_g);
    const catSel=$("#m_category");
    if(catSel && !catSel.value && f.category){
      for(let i=0;i<catSel.options.length;i++){ if(catSel.options[i].value===f.category){ catSel.value=f.category; break; } }
    }
    const cur=(f.currency||"").toUpperCase();
    const plnOk=!cur||cur==="PLN"||cur==="ZŁ";
    if(plnOk) setE("#m_purchase_price",f.price);
    SCRAPED_IMG=f.image||"";
    $("#mGrabPhoto").style.display=(SCRAPED_IMG && $("#m_id").value && HAD_PHOTO)?"":"none";
    const SRC_LBL={struktura:"", llm:" (odczytane)", domena:" (z domeny — sprawdź!)"};
    const tag=k=>SRC_LBL[src[k]]||"";
    const got=[];
    if(f.category) got.push("kategoria"+tag("category"));
    if(f.brand) got.push("marka"+tag("brand"));
    if(f.model) got.push("model"+tag("model"));
    if(f.color) got.push("kolor"+tag("color"));
    if(f.price&&plnOk) got.push("cena"+tag("price"));
    if(f.weight_g) got.push("waga"+tag("weight_g"));
    if(f.sku) got.push("SKU"+tag("sku"));
    if(f.ean) got.push("EAN"+tag("ean"));
    if(f.image) got.push(HAD_PHOTO ? "zdjęcie (jest już własne — użyj przycisku, by podmienić)" : "zdjęcie produktu (pobiorę przy zapisie)");
    let msg=got.length?("zaciągnięto: "+got.join(", ")):"nic nie odczytałem z tej strony";
    if(f.price&&!plnOk) msg+=" · cena "+f.price+" "+cur+" (inna waluta — nie wpisałem)";
    if(!f.weight_g) msg+=" · wagi brak na stronie — wpisz z metki";
    if(d.image_note && String(d.image_note).indexOf("brak packshotu")===0) msg+=" · uwaga: nie znalazłem zdjęcia samego produktu (może być z modelem)";
    if(d.js_page) msg+=" · strona ładowana JS (mniej danych)";
    if(d.llm_error) msg+=" · warstwa AI niedostępna";
    $("#mUrlStatus").textContent=msg;
  }catch(e){ $("#mUrlStatus").textContent="błąd ("+e.message+")"; }
}

async function uploadPhoto(){
  const f=$("#mPhotoFile").files[0]; if(!f) return;
  const id=$("#m_id").value; if(!id){ $("#mPhotoStatus").textContent="najpierw zapisz rzecz"; return; }
  const fd=new FormData(); fd.append("id",id); fd.append("file",f);
  $("#mPhotoStatus").textContent="wysyłanie…";
  try{
    const r=await fetch("/api/garage/photo",{method:"POST",credentials:"same-origin",body:fd});
    if(!r.ok) throw new Error(r.status);
    const d=await r.json(); const t=$("#mThumb");
    t.src=d.thumb; t.style.display=""; t.dataset.full=d.photo;
    $("#mPhotoDel").style.display=""; $("#mPhotoStatus").textContent="dodano"; load();
  }catch(e){ $("#mPhotoStatus").textContent="błąd ("+e.message+")"; }
}
async function delPhoto(){
  const id=$("#m_id").value; if(!id) return;
  $("#mPhotoStatus").textContent="usuwanie…";
  try{
    await postJSON("/api/garage/photo/delete",{id:Number(id)});
    const t=$("#mThumb"); t.style.display="none"; t.removeAttribute("src"); t.dataset.full="";
    $("#mPhotoDel").style.display="none"; $("#mPhotoStatus").textContent="usunięto"; load();
  }catch(e){ $("#mPhotoStatus").textContent="błąd usuwania"; }
}
async function grabPhotoFromUrl(){
  const id=$("#m_id").value; if(!id||!SCRAPED_IMG) return;
  $("#mUrlStatus").textContent="pobieranie zdjęcia…";
  try{
    const d=await postJSON("/api/garage/photo/from-url",{id:Number(id), url:SCRAPED_IMG});
    const t=$("#mThumb"); t.src=d.thumb; t.style.display=""; t.dataset.full=d.photo;
    $("#mPhotoDel").style.display=""; $("#mUrlStatus").textContent="zdjęcie pobrane ze strony"; load();
  }catch(e){ $("#mUrlStatus").textContent="błąd zdjęcia ("+e.message+")"; }
}
function openLightbox(src){ if(!src) return; $("#lightboxImg").src=src; document.body.classList.add("lb-open"); }


/* ---------- Ankieta ocen v2 (-2..+2 + n/d; Dopasowanie obowiazkowe, stala waga) ---------- */
let SVY_LIST=[], SVY_IDX=0, SVY_VALS={};
function svyDef(){ return (DATA.survey&&DATA.survey.length) ? DATA.survey : []; }
function svyKeys(){ return svyDef().map(q=>q.col); }
function svyRated(it){ return !!(DATA.survey_weights||{})[it.category]; }
function svyOpen(){
  const lst=(DATA.items||[]).filter(i=>i.active && svyRated(i)).slice();
  lst.sort((a,b)=>{
    const sa=a.s_status==="ok"?1:0, sb=b.s_status==="ok"?1:0;
    if(sa!==sb) return sa-sb;
    const oa=(DATA.categories||[]).indexOf(a.category), ob=(DATA.categories||[]).indexOf(b.category);
    return (oa<0?99:oa)-(ob<0?99:ob);
  });
  SVY_LIST=lst; if(!SVY_LIST.length) return;
  SVY_IDX=0; document.body.classList.add("svy-open"); svyShow();
}
function svyOpenOne(it){ if(!it||!it.id) return; SVY_LIST=[it]; SVY_IDX=0; document.body.classList.add("svy-open"); svyShow(); }
function svyClose(){ document.body.classList.remove("svy-open"); load(); }
function svyShow(){
  const it=SVY_LIST[SVY_IDX];
  if(!it){ svyClose(); return; }
  SVY_VALS={};
  svyKeys().forEach(k=>{ SVY_VALS[k]=(it[k]==null? null : Number(it[k])); });
  $("#svyProg").textContent=(SVY_IDX+1)+" / "+SVY_LIST.length;
  $("#svyName").textContent=[it.brand,it.model].filter(Boolean).join(" ")||("#"+it.id);
  const bits=[it.category, it.size&&("rozm. "+it.size), it.color_q, it.season].filter(Boolean);
  $("#svySub").textContent=bits.join(" · ");
  $("#svyNote").textContent=(it.notes||"").slice(0,220);
  const img=$("#svyImg");
  if(it.thumb){ img.src=it.thumb; img.style.display=""; } else { img.style.display="none"; img.removeAttribute("src"); }
  svyBadge(it); svyRows();
}
function svyBadge(it){
  const st = it.s_status==="ok" ? "zatwierdzone" : (svyKeys().some(k=>it[k]!=null) ? "wstępne (AI) — sprawdź" : "brak ocen");
  const oc = it.ocena==null ? "Ocena: — (brak Dopasowania)" : ("Ocena: "+(it.ocena===0?"0 — nie pasuje":it.ocena));
  $("#svyMsg").textContent=st+" · "+oc;
}
function svyRows(){
  const box=$("#svyRows"); box.innerHTML="";
  const it=SVY_LIST[SVY_IDX]; const W=((DATA.survey_weights||{})[it.category])||{};
  svyDef().forEach(q=>{
    const k=q.col, row=el("div","svy-row");
    const lab=el("div","lab"); lab.appendChild(el("div","svy-q",q.label));
    lab.appendChild(el("div","svy-w", W[k] ? ("waga "+W[k]+"%"+(k==="s_fit"?" · obowiązkowe":"")) : "nie wchodzi do Oceny"));
    lab.appendChild(el("div","svy-h", q.hint));
    row.appendChild(lab);
    const sc=el("div","svy-scale");
    [-2,-1,0,1,2].forEach(v=>{
      const bt=el("button",null,(v>0?"+":"")+v);
      if(SVY_VALS[k]===v) bt.classList.add("on");
      bt.addEventListener("click",()=>{ SVY_VALS[k]=v; svyRows(); });
      sc.appendChild(bt);
    });
    if(k!=="s_fit"){
      const nd=el("button","nd","n/d");
      if(SVY_VALS[k]===null||SVY_VALS[k]===undefined){ nd.classList.add("on");
        nd.style.cssText="background:var(--accent);border-color:var(--accent);color:#fff;font-weight:700"; }
      nd.addEventListener("click",()=>{ SVY_VALS[k]=null; svyRows(); });
      sc.appendChild(nd);
    }
    row.appendChild(sc); box.appendChild(row);
  });
}
async function svySave(status){
  const it=SVY_LIST[SVY_IDX]; if(!it) return;
  if(status==="ok" && (SVY_VALS.s_fit===null||SVY_VALS.s_fit===undefined)){ $("#svyMsg").textContent="Dopasowanie jest obowiązkowe"; return false; }
  const vals={}; svyKeys().forEach(k=>{ vals[k]=SVY_VALS[k]; });
  try{
    const r=await postJSON("/api/garage/audit/survey", {id:it.id, vals:vals, status:status});
    svyKeys().forEach(k=>{ it[k]=SVY_VALS[k]; });
    it.s_status=r.s_status; it.ocena=r.ocena;
  }catch(e){ $("#svyMsg").textContent="błąd zapisu ("+e.message+")"; return false; }
  return true;
}
async function svyNext(){
  const ok=await svySave("ok"); if(ok===false) return;
  if(SVY_IDX+1>=SVY_LIST.length){ svyClose(); return; }
  SVY_IDX++; svyShow();
}
function svySkip(){ if(SVY_IDX+1>=SVY_LIST.length){ svyClose(); return; } SVY_IDX++; svyShow(); }
function svyPrev(){ if(SVY_IDX>0){ SVY_IDX--; svyShow(); } }


/* usuwanie nieodwracalne: dwa kroki + potwierdzenie systemowe */
async function deleteItem(){
  const id=$("#m_id").value; if(!id) return;
  const b=$("#mDelete");
  const nazwa=[$("#m_brand").value,$("#m_model").value].filter(Boolean).join(" ")||("#"+id);
  if(b.dataset.armed!=="1"){
    b.dataset.armed="1"; b.classList.add("armed"); b.textContent="Potwierdź usunięcie";
    $("#mStatus").textContent="usunięcie jest nieodwracalne — kliknij ponownie";
    setTimeout(()=>{ if(b.dataset.armed==="1"){ b.dataset.armed=""; b.classList.remove("armed"); b.textContent="Usuń"; $("#mStatus").textContent=""; } }, 6000);
    return;
  }
  if(!window.confirm("Usunąć na zawsze: "+nazwa+"?\n\nZniknie z bazy razem ze zdjęciem i wpisami w logu jazd. Tego nie da się cofnąć.")){
    b.dataset.armed=""; b.classList.remove("armed"); b.textContent="Usuń"; $("#mStatus").textContent=""; return;
  }
  $("#mStatus").textContent="usuwanie…";
  try{
    const d=await postJSON("/api/garage/delete",{id:Number(id), confirm:true});
    closeModal(); load();
    console.log("usunieto", d);
  }catch(e){ $("#mStatus").textContent="błąd usuwania ("+e.message+")"; }
}

document.addEventListener("DOMContentLoaded",function(){
  $("#gsearch").addEventListener("input", debounce(render,180));
  ["#gfilter","#gfilterBrand","#gfilterColor","#gfilterFabric","#gfilterSeason"].forEach(s=>$(s).addEventListener("change", render));
  $("#gadd").addEventListener("click",()=>openModal(null));
  $("#garch").addEventListener("click",function(){
    SHOW_ALL=!SHOW_ALL; this.classList.toggle("on",SHOW_ALL);
    this.textContent=SHOW_ALL?"Ukryj archiwum":"Pokaż archiwum"; load();
  });
  document.querySelectorAll("#mSeason button").forEach(b=>{
    b.addEventListener("click",()=>{ const s=b.dataset.s; if(SEASON_SEL.has(s)) SEASON_SEL.delete(s); else SEASON_SEL.add(s); paintSeason(); });
  });
  document.querySelectorAll("#mRating button").forEach(b=>{
    b.addEventListener("click",()=>{ RATING_SEL=Number(b.dataset.v); paintRating(); });
  });
  $("#mRatingClr").addEventListener("click",()=>{ RATING_SEL=null; paintRating(); });
  $("#mSave").addEventListener("click", saveModal);
  $("#mDelete").addEventListener("click", deleteItem);
  $("#mCancel").addEventListener("click", closeModal);
  $("#mCancelX").addEventListener("click", closeModal);
  $("#mBack").addEventListener("click", closeModal);
  $("#mScrape").addEventListener("click", scrapeNow);
  $("#mGrabPhoto").addEventListener("click", grabPhotoFromUrl);
  $("#mPhotoFile").addEventListener("change", uploadPhoto);
  $("#mPhotoDel").addEventListener("click", delPhoto);
  $("#mThumb").addEventListener("click",()=>openLightbox($("#mThumb").dataset.full));
  $("#lightbox").addEventListener("click",()=>document.body.classList.remove("lb-open"));
  if(window.QCols){ QCols.init("gear","colWrapGear","colBtnGear", render); }
  $("#gsurvey").addEventListener("click", svyOpen);
  if($("#mArch")) $("#mArch").addEventListener("click", archFromModal);
  if($("#mRate")) $("#mRate").addEventListener("click", rateFromModal);
  $("#svyX").addEventListener("click", svyClose);
  $("#svyBack").addEventListener("click", svyClose);
  $("#svyNext").addEventListener("click", svyNext);
  $("#svySkip").addEventListener("click", svySkip);
  $("#svyPrev").addEventListener("click", svyPrev);
  load();
});
})();
