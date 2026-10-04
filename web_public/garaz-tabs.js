/* czas lokalny (strefa przegladarki) -- wspolne dla QBot lab */function qTsLocal(s,naiveUtc){if(!s)return"";var t=String(s).trim().replace(" ","T").replace(/\.\d+/,"");if(/[+-]\d\d$/.test(t))t+=":00";t=t.replace(/([+-]\d\d)(\d\d)$/,"$1:$2");if(!/(Z|[+-]\d\d:\d\d)$/i.test(t)){if(!naiveUtc)return t.slice(0,16).replace("T"," ");t+="Z";}var d=new Date(t);if(isNaN(d.getTime()))return String(s).slice(0,16);var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());}function qDateLocal(d){d=d||new Date();var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
/* garaz-tabs.js — zakladki Garazu: SPRZET (equipment) i ROWER (bikes/components/tires/fitting).
   Zakladka Odziez obsluguje garaz-render.js. Tu tylko przelaczanie widokow + dwie pozostale bazy. */
(function(){
"use strict";
const $ = s => document.querySelector(s);
const el = (t,c,h) => { const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.textContent=h; return e; };
async function getJSON(u){ const r=await fetch(u,{credentials:"same-origin",cache:"no-store"}); if(!r.ok) throw new Error(r.status); return r.json(); }
async function postJSON(u,b){ const r=await fetch(u,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}); if(!r.ok) throw new Error(r.status); return r.json(); }

const COLOR_HEX={BLACK:"#22252a",GREY:"#8b9199",WHITE:"#f4f2ec",BEIGE:"#d9c49a",BROWN:"#7a5236",
  GREEN:"#3f7a4d",OLIVE:"#6b7043",BLUE:"#3a6ea8",NAVY:"#26375e",RED:"#a6503d",
  ORANGE:"#d1762e",YELLOW:"#d9b02e",MULTI:"#b08fb0"};

/* ================= przelaczanie zakladek ================= */
let LOADED={equip:false, bike:false, fit:false, instr:false};
function switchTab(which){
  [["tabGear","viewGear","toolbarGear"],["tabEquip","viewEquip","toolbarEquip"],
   ["tabBike","viewBike","toolbarBike"],["tabFit","viewFit","toolbarFit"],
   ["tabInstr","viewInstr","toolbarInstr"]]
    .forEach(([tab,view,bar])=>{
      const on = tab==="tab"+which;
      $("#"+tab).classList.toggle("on", on);
      $("#"+view).classList.toggle("on", on);
      const b=$("#"+bar); if(b) b.style.display = on ? "" : "none";
    });
  // wyszukiwarka w pasku zakladek: pokazujemy te wlasciwa dla widoku
  const gs=$("#gsearch"), es=$("#esearch"), box=$("#tabSearch");
  if(gs) gs.style.display = (which==="Gear") ? "" : "none";
  if(es) es.style.display = (which==="Equip") ? "" : "none";
  if(box) box.style.visibility = (which==="Gear"||which==="Equip") ? "visible" : "hidden";
  if(which==="Equip" && !LOADED.equip){ LOADED.equip=true; eqLoad(); }
  if(which==="Bike" && !LOADED.bike){ LOADED.bike=true; bikeLoad(); }
  if(which==="Fit" && !LOADED.fit){ LOADED.fit=true; fitLoad(); }
  if(which==="Instr" && !LOADED.instr && window.QInstr){ LOADED.instr=true; QInstr.load(); }
}

/* ================= SPRZET ================= */
let EQ={items:[],categories:[],conditions:[],statuses:[],mounts:[],palette:[]};
let EQ_ALL=false, EQ_RATING=null, EQ_SCRAPED_IMG="", EQ_HAD_PHOTO=false, EQ_FILLED=false;
let EQ_SORT={key:"category",dir:1};

const EQ_COLS=[
  {key:"category",label:"Kategoria"},
  {key:"brand",label:"Marka"},
  {key:"model",label:"Model"},
  {key:"mount",label:"Montaż"},
  {key:"capacity_l",label:"Pojemność",num:true},
  {key:"weight_g",label:"Waga",num:true},
  {key:"color_q",label:"Kolor"},
  {key:"rating",label:"Ocena",num:true},
  {key:"status",label:"Status"},
  {key:"purchase_price",label:"Cena",num:true}
];

async function eqLoad(){
  try{
    EQ=await getJSON("/api/equipment/list?all="+(EQ_ALL?1:0)+"&_="+Date.now());
    if(!EQ_FILLED){
      const sel=$("#efilter");
      (EQ.categories||[]).forEach(c=>{ const o=el("option",null,c); o.value=c; sel.appendChild(o); });
      EQ_FILLED=true;
    }
    eqRender();
  }catch(e){ $("#equipBody").innerHTML=""; $("#equipBody").appendChild(el("div","empty","błąd ładowania ("+e.message+")")); }
}

function eqFiltered(){
  const q=$("#esearch").value.trim().toLowerCase(), cat=$("#efilter").value;
  return (EQ.items||[]).filter(it=>{
    if(cat && it.category!==cat) return false;
    if(q){ const hay=[it.brand,it.model,it.notes,it.size,it.sku].map(x=>(x||"")).join(" ").toLowerCase(); if(hay.indexOf(q)<0) return false; }
    return true;
  });
}

function eqCmp(a,b){
  const k=EQ_SORT.key; let r;
  if(["capacity_l","weight_g","rating","purchase_price","mileage_km"].indexOf(k)>=0){
    const av=a[k], bv=b[k];
    if(av==null&&bv==null) r=0; else if(av==null) return 1; else if(bv==null) return -1; else r=av-bv;
  } else {
    const av=a[k]||"", bv=b[k]||"";
    if(!av&&bv) return 1; if(av&&!bv) return -1;
    r=av.localeCompare(bv,"pl",{sensitivity:"base"});
  }
  return r*EQ_SORT.dir;
}

function cellColor(q){
  const c=el("td");
  if(!q){ c.textContent="—"; return c; }
  const d=el("span","dot"); d.style.background=COLOR_HEX[q]||"#bbb"; c.appendChild(d);
  c.appendChild(document.createTextNode(q)); return c;
}


function eqCellFor(it, key){
  switch(key){
    case "color_q":    return cellColor(it.color_q);
    case "capacity_l": return el("td","num", it.capacity_l!=null ? it.capacity_l+" l" : "—");
    case "weight_g":   return el("td","num", it.weight_g!=null ? it.weight_g+" g" : "—");
    case "purchase_price": return el("td","num", it.purchase_price!=null ? Math.round(it.purchase_price)+" zł" : "—");
    case "rating": {
      const c=el("td","num");
      if(it.rating!=null) c.appendChild(el("span","stars","★".repeat(it.rating))); else c.textContent="—";
      return c;
    }
    case "model":  return el("td","mdl", it.model||"—");
    case "notes":  { const c=el("td",null,(it.notes||"").slice(0,90)||"—"); c.style.fontSize="13px"; c.style.color="var(--muted)"; return c; }
    default:       return el("td",null, it[key]!=null && it[key]!=="" ? String(it[key]) : "—");
  }
}

function eqRender(){
  const body=$("#equipBody"); body.innerHTML="";
  const items=eqFiltered(); const total=(EQ.items||[]).length;
  $("#ecount").textContent = total ? (items.length===total ? total+" szt." : items.length+" / "+total+" szt.") : "";
  if(!items.length){
    body.appendChild(el("div","empty", total ? "Brak sprzętu dla tych filtrów."
      : "Pusto. Zacznij od toreb bikepackingowych — przycisk „+ Dodaj sprzęt”."));
    return;
  }
  items.sort(eqCmp);
  const AKT = (window.QCols ? QCols.columns("equip") : EQ_COLS);
  const table=el("table","gt"), thead=el("thead"), htr=el("tr");
  AKT.forEach(c=>{
    const th=el("th", c.num?"num":null); th.textContent=c.label;
    if(EQ_SORT.key===c.key) th.appendChild(el("span","ar", EQ_SORT.dir>0?"▲":"▼"));
    th.addEventListener("click",()=>{ if(EQ_SORT.key===c.key) EQ_SORT.dir=-EQ_SORT.dir; else { EQ_SORT.key=c.key; EQ_SORT.dir=1; } eqRender(); });
    htr.appendChild(th);
  });
  htr.appendChild(el("th","noclick",""));
  thead.appendChild(htr); table.appendChild(thead);
  const tb=el("tbody");
  items.forEach(it=>{
    const tr=el("tr", it.active?null:"arch"); tr.style.cursor="pointer";
    tr.addEventListener("click",()=>eqOpen(it));
    AKT.forEach(c=>tr.appendChild(eqCellFor(it, c.key)));
    const act=el("td"), box=el("div","gact");
    const be=el("button",null,"Edytuj"); be.addEventListener("click",e=>{e.stopPropagation();eqOpen(it);}); box.appendChild(be);
    const ba=el("button","sec", it.active?"Archiwum":"Przywróć");
    ba.addEventListener("click",async e=>{ e.stopPropagation();
      try{ await postJSON("/api/equipment/toggle",{id:it.id,active:it.active?0:1}); eqLoad(); }catch(x){} });
    box.appendChild(ba); act.appendChild(box); tr.appendChild(act);
    tb.appendChild(tr);
  });
  table.appendChild(tb); body.appendChild(table);
}

function fillSelect(sel, values, cur, placeholder){
  sel.innerHTML="";
  if(placeholder!=null){ const o=el("option",null,placeholder); o.value=""; sel.appendChild(o); }
  (values||[]).forEach(v=>{ const o=el("option",null,v); o.value=v; if(v===cur)o.selected=true; sel.appendChild(o); });
  if(placeholder!=null && !cur) sel.value="";
}
function eqPaintRating(){
  document.querySelectorAll("#eRating button").forEach(b=>{
    b.classList.toggle("on", EQ_RATING!=null && Number(b.dataset.v)<=EQ_RATING);
  });
}

function eqOpen(it){
  it=it||{};
  $("#eTitle").textContent = it.id ? "Edytuj sprzęt" : "Dodaj sprzęt";
  $("#e_id").value=it.id||"";
  fillSelect($("#e_category"), EQ.categories, it.category||"", it.id?null:"— wybierz —");
  fillSelect($("#e_status"), EQ.statuses, it.status||"uzywany", null);
  fillSelect($("#e_condition"), EQ.conditions, it.condition || (it.id?"Good":"New"), null);
  fillSelect($("#e_color_q"), EQ.palette, it.color_q||"", "— auto —");
  fillSelect($("#e_mount"), EQ.mounts, it.mount||"", "— nie podano —");
  ["brand","model","size","color","purchase_date","notes","ean","sku","url"].forEach(k=>{ $("#e_"+k).value=it[k]||""; });
  $("#e_capacity_l").value=(it.capacity_l!=null?it.capacity_l:"");
  $("#e_weight_g").value=(it.weight_g!=null?it.weight_g:"");
  $("#e_purchase_price").value=(it.purchase_price!=null?it.purchase_price:"");
  EQ_RATING=(it.rating!=null?Number(it.rating):null); eqPaintRating();
  EQ_HAD_PHOTO=!!it.photo; EQ_SCRAPED_IMG="";
  const t=$("#eThumb");
  if(it.thumb){ t.src=it.thumb; t.style.display=""; } else { t.style.display="none"; t.removeAttribute("src"); }
  t.dataset.full=it.photo||"";
  $("#ePhotoDel").style.display=it.thumb?"":"none";
  $("#ePhotoLbl").style.display=it.id?"":"none";
  $("#ePhotoFile").value="";
  $("#ePhotoStatus").textContent = it.id ? "" : "zapisz sprzęt, potem dodasz zdjęcie";
  $("#eMeta").textContent = it.id ? ("ID "+it.id+" · dodano: "+(qTsLocal(it.created_at,true)||"—")+" · "+(it.active===0?"archiwum":"aktywne")) : "nowa pozycja";
  $("#eStatus").textContent=""; $("#eUrlStatus").textContent="";
  const edb=$("#eDelete"); edb.style.display = it.id ? "" : "none";
  edb.textContent="Usuń"; edb.classList.remove("armed"); edb.dataset.armed="";
  document.body.classList.add("modal-open");
  $("#equipModal").classList.add("open");
}
function eqClose(){ $("#equipModal").classList.remove("open"); document.body.classList.remove("modal-open"); }

async function eqSave(){
  const b={id:$("#e_id").value||null, category:$("#e_category").value, status:$("#e_status").value,
    mount:$("#e_mount").value,
    condition:$("#e_condition").value, color_q:$("#e_color_q").value, rating:EQ_RATING,
    capacity_l:$("#e_capacity_l").value, weight_g:$("#e_weight_g").value,
    purchase_price:$("#e_purchase_price").value};
  ["brand","model","size","color","purchase_date","notes","ean","sku","url"].forEach(k=>{ b[k]=$("#e_"+k).value; });
  if(!b.category || !(b.brand||b.model)){ $("#eStatus").textContent="podaj kategorię oraz markę lub model"; return; }
  $("#eStatus").textContent="zapis…";
  let res;
  try{ res=await postJSON("/api/equipment/save", b); }
  catch(e){ $("#eStatus").textContent="błąd zapisu ("+e.message+")"; return; }
  if(EQ_SCRAPED_IMG && res && res.id && !EQ_HAD_PHOTO){
    $("#eStatus").textContent="zapisano — pobieram zdjęcie…";
    try{ await postJSON("/api/garage/photo/from-url",{id:Number(res.id), url:EQ_SCRAPED_IMG, entity:"equipment"}); }catch(e){}
  }
  eqClose(); eqLoad();
}

async function eqScrape(){
  const u=$("#e_url").value.trim();
  if(!/^https?:\/\//i.test(u)){ $("#eUrlStatus").textContent="podaj adres http(s)"; return; }
  $("#eUrlStatus").textContent="zaciąganie (czytam stronę)…";
  try{
    const d=await postJSON("/api/garage/scrape",{url:u, categories:EQ.categories});
    const f=d.fields||{};
    const setE=(id,v)=>{ const e=$(id); if(e && !e.value && v!=null && v!=="") e.value=v; };
    setE("#e_brand",f.brand); setE("#e_model",f.model); setE("#e_color",f.color);
    setE("#e_sku",f.sku); setE("#e_ean",f.ean); setE("#e_weight_g",f.weight_g);
    setE("#e_capacity_l",f.capacity_l);
    const cs=$("#e_category");
    let catSet=false;
    if(cs && !cs.value && f.category){
      for(let i=0;i<cs.options.length;i++){ if(cs.options[i].value===f.category){ cs.value=f.category; catSet=true; break; } }
    }
    const cur=(f.currency||"").toUpperCase(), plnOk=!cur||cur==="PLN";
    if(plnOk) setE("#e_purchase_price",f.price);
    EQ_SCRAPED_IMG=f.image||"";
    const got=[f.category&&"kategoria",f.brand&&"marka",f.model&&"model",f.color&&"kolor",
               f.capacity_l&&"pojemność",(f.price&&plnOk)&&"cena",f.weight_g&&"waga",f.sku&&"SKU",
               f.image&&"zdjęcie (pobiorę przy zapisie)"].filter(Boolean);
    let msg=got.length?("zaciągnięto: "+got.join(", ")):"nic nie odczytałem z tej strony";
    if(f.price&&!plnOk) msg+=" · cena "+f.price+" "+cur+" (inna waluta — nie wpisałem)";
    if(f.category && !catSet && !$("#e_category").value) msg+=" · kategorii nie dopasowałem — wybierz ręcznie";
    if(!f.weight_g) msg+=" · wagi brak na stronie — wpisz z metki lub zważ";
    $("#eUrlStatus").textContent=msg;
  }catch(e){ $("#eUrlStatus").textContent="błąd ("+e.message+")"; }
}

async function eqUploadPhoto(){
  const f=$("#ePhotoFile").files[0]; if(!f) return;
  const id=$("#e_id").value; if(!id){ $("#ePhotoStatus").textContent="najpierw zapisz sprzęt"; return; }
  const fd=new FormData(); fd.append("id",id); fd.append("file",f); fd.append("entity","equipment");
  $("#ePhotoStatus").textContent="wysyłanie…";
  try{
    const r=await fetch("/api/garage/photo",{method:"POST",credentials:"same-origin",body:fd});
    if(!r.ok) throw new Error(r.status);
    const d=await r.json(); const t=$("#eThumb");
    t.src=d.thumb; t.style.display=""; t.dataset.full=d.photo;
    $("#ePhotoDel").style.display=""; $("#ePhotoStatus").textContent="dodano"; eqLoad();
  }catch(e){ $("#ePhotoStatus").textContent="błąd ("+e.message+")"; }
}
async function eqDelPhoto(){
  const id=$("#e_id").value; if(!id) return;
  try{
    await postJSON("/api/garage/photo/delete",{id:Number(id), entity:"equipment"});
    const t=$("#eThumb"); t.style.display="none"; t.removeAttribute("src");
    $("#ePhotoDel").style.display="none"; $("#ePhotoStatus").textContent="usunięto"; eqLoad();
  }catch(e){ $("#ePhotoStatus").textContent="błąd usuwania"; }
}

/* ================= ROWER ================= */
let BIKE={bikes:[],components:[],tires:[],fitting:[],component_categories:[],statuses:[]};
let BIKE_ALL=false, C_SCRAPED_IMG="", C_HAD_PHOTO=false;
/* sortowanie po naglowkach (Komponenty, Opony) */
let BK_SORT={key:null,dir:1}, TR_SORT={key:null,dir:1};
const BK_NUM=["weight_g","mileage_km","purchase_price","weight_est_g"];
function cmpBy(get,num,dir){ return (a,b)=>{ let av=get(a), bv=get(b);
  if(num){ av=(av==null||av==="")?null:Number(av); bv=(bv==null||bv==="")?null:Number(bv);
    if(av==null&&bv==null) return 0; if(av==null) return 1; if(bv==null) return -1; return (av-bv)*dir; }
  av=String(av==null?"":av); bv=String(bv==null?"":bv);
  if(!av&&bv) return 1; if(av&&!bv) return -1;
  return av.localeCompare(bv,"pl",{sensitivity:"base",numeric:true})*dir; }; }
function sortTh(th,st,key,rerender){
  if(st.key===key) th.appendChild(el("span","ar",st.dir>0?"\u25B2":"\u25BC"));
  th.addEventListener("click",()=>{ if(st.key===key) st.dir=-st.dir; else { st.key=key; st.dir=1; } rerender(); }); }
function bkSortVal(c,k){ if(k==="bike_id") return bikeShort(c.bike_id); if(k==="category") return catPl(c.category); return c[k]; }

async function bikeLoad(){
  try{
    BIKE=await getJSON("/api/bike/config?all="+(BIKE_ALL?1:0)+"&_="+Date.now());
    bikeRender();
  }catch(e){ $("#bikeBody").innerHTML=""; $("#bikeBody").appendChild(el("div","empty","błąd ładowania ("+e.message+")")); }
}

function pill(status){
  const s=(status||"").toLowerCase();
  const cls = s==="zamontowany" ? "mount" : (s==="zapas" ? "spare" : "off");
  return el("span","pill "+cls, status||"—");
}


const CAT_PL={"aero bars":"lemondka","brakes":"hamulce","cassette":"kaseta","chain":"łańcuch","crankset":"korba","drivetrain":"napęd","shifters":"klamkomanetki","electronics":"elektronika","handlebar":"kierownica","pedals":"pedały","other":"inne","tires":"opony","bottle cages":"koszyki na bidon","rack":"bagażnik","saddle":"siodło","seatpost":"sztyca","spare parts":"części zapasowe","wheels":"koła","frame":"rama","fork":"widelec","stem":"mostek","headset":"stery","bottom bracket":"suport","mudguards":"błotniki","rotors":"tarcze","tubeless insert":"wkładki"};
const CAT_EN=Object.fromEntries(Object.entries(CAT_PL).map(([k,v])=>[v,k]));
function catPl(c){ return CAT_PL[c]||c||""; }
function catEn(t){ t=(t||"").trim(); return CAT_EN[t.toLowerCase()]||t; }

const BK_F=["name","nickname","brand","model","type","year","frame_size","color","weight_kg","purchase_date","purchase_price","notes"];
function bikeOpen(b){
  b=b||{};
  $("#bkTitle").textContent = b.id ? "Edytuj rower" : "Dodaj rower";
  $("#bk_id").value=b.id||"";
  BK_F.forEach(k=>{ $("#bk_"+k).value = (b[k]!=null ? b[k] : ""); });
  $("#bk_active").checked = b.id ? !!b.active : true;
  const db=$("#bkDelete"); db.style.display=b.id?"":"none"; db.textContent="Usuń"; db.classList.remove("armed"); db.dataset.armed="";
  $("#bkStatus").textContent=""; $("#bkPhotoStatus").textContent=""; $("#bkPhotoUrl").value="";
  const th=$("#bkThumb");
  if(b.photo){ th.src=b.photo; th.style.display=""; $("#bkPhotoDel").style.display=""; }
  else { th.removeAttribute("src"); th.style.display="none"; $("#bkPhotoDel").style.display="none"; }
  document.body.classList.add("modal-open"); $("#bikeModal").classList.add("open");
}
function bkPhotoShow(d){ const t=$("#bkThumb"); t.src=d.photo; t.style.display=""; $("#bkPhotoDel").style.display=""; }
async function bikeUploadPhoto(){
  const f=$("#bkPhotoFile").files[0]; if(!f) return;
  const id=$("#bk_id").value; if(!id){ $("#bkPhotoStatus").textContent="najpierw zapisz rower"; return; }
  const fd=new FormData(); fd.append("id",id); fd.append("file",f); fd.append("entity","bike");
  $("#bkPhotoStatus").textContent="wysyłanie…";
  try{ const r=await fetch("/api/garage/photo",{method:"POST",credentials:"same-origin",body:fd});
    if(!r.ok) throw new Error(r.status); bkPhotoShow(await r.json()); $("#bkPhotoStatus").textContent="dodano"; bikeLoad(); }
  catch(e){ $("#bkPhotoStatus").textContent="błąd ("+e.message+")"; }
  $("#bkPhotoFile").value="";
}
async function bikeFetchPhoto(){
  const id=$("#bk_id").value; if(!id){ $("#bkPhotoStatus").textContent="najpierw zapisz rower"; return; }
  const url=$("#bkPhotoUrl").value.trim(); if(!url){ $("#bkPhotoStatus").textContent="wklej link do zdjęcia"; return; }
  $("#bkPhotoStatus").textContent="pobieram…";
  try{ bkPhotoShow(await postJSON("/api/garage/photo/from-url",{id:Number(id), url:url, entity:"bike"}));
    $("#bkPhotoStatus").textContent="dodano"; $("#bkPhotoUrl").value=""; bikeLoad(); }
  catch(e){ $("#bkPhotoStatus").textContent="nie udało się pobrać ("+e.message+")"; }
}
async function bikeDelPhoto(){
  const id=$("#bk_id").value; if(!id) return;
  try{ await postJSON("/api/garage/photo/delete",{id:Number(id), entity:"bike"});
    const t=$("#bkThumb"); t.style.display="none"; t.removeAttribute("src");
    $("#bkPhotoDel").style.display="none"; $("#bkPhotoStatus").textContent="usunięto"; bikeLoad(); }
  catch(e){ $("#bkPhotoStatus").textContent="błąd usuwania"; }
}
function bikeClose(){ $("#bikeModal").classList.remove("open"); document.body.classList.remove("modal-open"); }
async function bikeSave(){
  const b={id:$("#bk_id").value||null, active:$("#bk_active").checked?1:0};
  BK_F.forEach(k=>{ b[k]=$("#bk_"+k).value; });
  if(!(b.name||"").trim() && !(b.model||"").trim()){ $("#bkStatus").textContent="Podaj nazwę albo model."; return; }
  $("#bkStatus").textContent="zapisuję…";
  try{ await postJSON("/api/bike/bike/save", b); bikeClose(); bikeLoad(); }
  catch(e){ $("#bkStatus").textContent="Błąd zapisu ("+e.message+")"; }
}
async function bikeDelete(btn){
  if(btn.dataset.armed!=="1"){
    btn.dataset.armed="1"; btn.classList.add("armed"); btn.textContent="Potwierdź usunięcie";
    setTimeout(()=>{ if(btn.dataset.armed==="1"){ btn.dataset.armed=""; btn.classList.remove("armed"); btn.textContent="Usuń"; } }, 6000);
    return;
  }
  try{
    const r=await postJSON("/api/bike/bike/delete",{id:$("#bk_id").value, confirm:true});
    if(r && r.ok===false && r.blocked){
      const p=[]; if(r.blocked.components) p.push(r.blocked.components+" części"); if(r.blocked.fitting) p.push(r.blocked.fitting+" wpisów fittingu");
      $("#bkStatus").textContent="Nie usunę: do roweru przypisane są "+p.join(" i ")+". Przenieś je albo odznacz „aktywny”.";
      btn.dataset.armed=""; btn.classList.remove("armed"); btn.textContent="Usuń"; return;
    }
    const f=$("#bfilterBike"); if(f && f.value===$("#bk_id").value) f.value="";
    bikeClose(); bikeLoad();
  }catch(e){ $("#bkStatus").textContent="Błąd usuwania ("+e.message+")"; }
}

function wheelById(id){ return (BIKE.components||[]).find(c=>String(c.id)===String(id)); }
function wheelLabel(w){ return [w.brand,w.model].filter(Boolean).join(" ")||("koło "+w.id); }
function tirePill(st){ const cls = st==="zamontowana"?"mount":(st==="wycofana"?"off":"spare"); return el("span","pill "+cls, st||"—"); }

function tireOpen(t){
  t=t||{};
  $("#tTitle").textContent = t.id ? "Edytuj oponę" : "Dodaj oponę";
  $("#t_id").value=t.id||"";
  ["brand","model","type","width_src","notes"].forEach(k=>{ $("#t_"+k).value=t[k]||""; });
  $("#t_width_mm").value=(t.width_mm!=null?t.width_mm:"");
  const ws=$("#t_wheel"); ws.innerHTML="";
  const o0=el("option",null,"— w garażu (nie zamontowana) —"); o0.value=""; ws.appendChild(o0);
  (BIKE.components||[]).filter(c=>c.category==="wheels").forEach(w=>{
    const o=el("option",null,bikeShort(w.bike_id)+" · "+wheelLabel(w)); o.value=String(w.id); ws.appendChild(o); });
  ws.value = t.wheel_id!=null ? String(t.wheel_id) : "";
  $("#t_position").value = (t.position==="tył" ? "tył" : "przód");
  const st=$("#t_status"); st.innerHTML="";
  (BIKE.tire_statuses||["w garażu","wycofana"]).forEach(v=>{ const o=el("option",null,v); o.value=v; st.appendChild(o); });
  st.value = (t.status && t.status!=="zamontowana") ? t.status : "w garażu";
  const db=$("#tDelete"); db.style.display = t.id ? "" : "none"; db.textContent="Usuń"; db.classList.remove("armed"); db.dataset.armed="";
  $("#tStatus").textContent="";
  tireSync();
  document.body.classList.add("modal-open");
  $("#tireModal").classList.add("open");
}
function tireClose(){ $("#tireModal").classList.remove("open"); document.body.classList.remove("modal-open"); }
function tireSync(){
  const wid=$("#t_wheel").value, on=!!wid, hint=$("#tHint");
  $("#t_status").disabled=on;
  if(!on){ hint.textContent="Bez koła opona leży w garażu (albo jest wycofana)."; return; }
  const pos=$("#t_position").value, id=$("#t_id").value;
  const occ=(BIKE.tires||[]).find(x=>String(x.wheel_id)===wid && x.position===pos && String(x.id)!==id);
  hint.textContent = "Status: zamontowana." + (occ ? " Na tym miejscu jest teraz "+[occ.brand,occ.model].filter(Boolean).join(" ")+" — po zapisie trafi do garażu." : "");
}
async function tireSave(){
  const b={id:$("#t_id").value||null, width_mm:$("#t_width_mm").value,
    wheel_id:$("#t_wheel").value||null, position:$("#t_position").value, status:$("#t_status").value};
  ["brand","model","type","width_src","notes"].forEach(k=>{ b[k]=$("#t_"+k).value; });
  if(!(b.brand||"").trim() && !(b.model||"").trim()){ $("#tStatus").textContent="Podaj markę albo model."; return; }
  $("#tStatus").textContent="zapisuję…";
  try{ await postJSON("/api/bike/tire/save", b); tireClose(); bikeLoad(); }
  catch(e){ $("#tStatus").textContent="Błąd zapisu ("+e.message+")"; }
}
async function tireDelete(btn){
  if(btn.dataset.armed!=="1"){
    btn.dataset.armed="1"; btn.classList.add("armed"); btn.textContent="Potwierdź usunięcie";
    setTimeout(()=>{ if(btn.dataset.armed==="1"){ btn.dataset.armed=""; btn.classList.remove("armed"); btn.textContent="Usuń"; } }, 6000);
    return;
  }
  try{ await postJSON("/api/bike/tire/delete",{id:$("#t_id").value, confirm:true}); tireClose(); bikeLoad(); }
  catch(e){ $("#tStatus").textContent="Błąd usuwania ("+e.message+")"; }
}

const DIMS_SPEC={stem:[["length_mm","Długość [mm]"],["angle_deg","Kąt [°]"],["stack_mm","Wys. zacisku [mm]"]],
 handlebar:[["bar_type","Typ: drop / flat"],["width_mm","Szerokość [mm]"],["reach_mm","Reach [mm]"],["drop_mm","Drop [mm]"],["rise_mm","Wznios [mm]"],["backsweep_deg","Backsweep [°]"],["flare_deg","Flare [°]"]],
 saddle:[["length_mm","Długość [mm]"],["width_mm","Szerokość [mm]"]],
 seatpost:[["offset_mm","Offset [mm]"],["travel_mm","Skok [mm]"],["length_mm","Długość [mm]"]],
 crankset:[["crank_mm","Długość ramienia [mm]"]],
 "aero bars":[["extension_mm","Wysięgniki [mm]"],["pad_angle_deg","Kąt podłokietników [°]"],["pad_stack_mm","Podłokietniki nad kierownicą [mm]"],["pad_setback_mm","Podłokietniki: przesunięcie od zacisku [mm]"]]};
function dimsCollect(){ const d={}; const box=$("#c_dims_box"); if(box) box.querySelectorAll("[data-dk]").forEach(i=>{ d[i.dataset.dk]=i.value; }); return d; }
function dimsRender(cat, vals){
  const box=$("#c_dims_box"); if(!box) return; box.innerHTML=""; const spec=DIMS_SPEC[cat];
  box.style.display=spec?"":"none"; if(!spec) return;
  box.appendChild(el("label",null,"Wymiary (używane w Fittingu)"));
  const g=el("div","dimsgrid");
  spec.forEach(([k,l])=>{ const w=el("div"); w.appendChild(el("span",null,l)); const i=el("input"); i.dataset.dk=k; i.value=(vals&&vals[k]!=null)?vals[k]:""; w.appendChild(i); g.appendChild(w); });
  box.appendChild(g);
}

function bikeShort(id){
  const b=(BIKE.bikes||[]).find(x=>String(x.id)===String(id));
  return b ? (b.nickname||b.model||b.name||("rower "+b.id)) : "—";
}

function bkCellFor(c, key){
  switch(key){
    case "bike_id":    return el("td",null, bikeShort(c.bike_id));
    case "category":   return el("td",null, catPl(c.category)||"—");
    case "status":     { const t=el("td"); t.appendChild(pill(c.status)); return t; }
    case "weight_g":   return el("td","num", c.weight_g!=null ? c.weight_g+" g" : "—");
    case "mileage_km": return el("td","num", c.mileage_km ? Math.round(c.mileage_km)+" km" : "—");
    case "purchase_price": return el("td","num", c.purchase_price!=null ? Math.round(c.purchase_price)+" zł" : "—");
    case "model":      return el("td","mdl", c.model||"—");
    case "notes":      { const t=el("td",null,(c.notes||"").slice(0,90)||"—"); t.style.fontSize="13px"; t.style.color="var(--muted)"; return t; }
    default:           return el("td",null, c[key]!=null && c[key]!=="" ? String(c[key]) : "—");
  }
}

function bikeRender(){
  const body=$("#bikeBody"); body.innerHTML="";
  const bf=$("#bfilterBike"), bsel=bf?bf.value:"";
  if(bf){ bf.innerHTML=""; const o0=el("option",null,"wszystkie rowery"); o0.value=""; bf.appendChild(o0);
    (BIKE.bikes||[]).forEach(b=>{ const o=el("option",null,bikeShort(b.id)); o.value=String(b.id); bf.appendChild(o); });
    bf.value=bsel; }
  const _qs=(($("#bsearch")||{}).value||"").trim().toLowerCase().split(/\s+/).filter(Boolean);
  const _hay=c=>[c.brand,c.model,c.spec,c.sku,c.serial_number,c.notes,c.category,catPl(c.category),c.position,c.status,c.wheel_pos]
                  .map(x=>String(x||"")).join(" ").toLowerCase();
  const COMPS=(BIKE.components||[]).filter(c=>(!bsel || String(c.bike_id)===bsel) && (!_qs.length || _qs.every(w=>_hay(c).includes(w))));
  $("#bcount").textContent=COMPS.length+" komponentów";

  { const grid=el("div","bikecards");
    (BIKE.bikes||[]).forEach(b=>{
      const card=el("div","bikecard"+(String(b.id)===bsel?" sel":"")+(b.active?"":" inact"));
      card.title="Kliknij, aby pokazać tylko części tego roweru (ponownie: wszystkie)";
      const img=el("div","bkimg");
      if(b.photo){ const im=el("img"); im.src=b.photo; im.alt=""; im.loading="lazy"; img.appendChild(im); }
      else img.appendChild(el("div","bkph","🚲"));
      const eb=el("button","bkedit","Edytuj"); eb.type="button";
      eb.addEventListener("click",e=>{ e.stopPropagation(); bikeOpen(b); }); img.appendChild(eb);
      card.appendChild(img);
      const txt=el("div","bktxt");
      const full=b.name||[b.brand,b.model].filter(Boolean).join(" ");
      txt.appendChild(el("h3", null, b.nickname||full));
      if(b.nickname) txt.appendChild(el("div","bkfull", full));
      const meta=[b.type, b.year, b.frame_size&&("rozm. "+b.frame_size),
                  b.weight_kg&&(b.weight_kg+" kg"), b.color, b.active?null:"nieaktywny"].filter(Boolean).join(" · ");
      txt.appendChild(el("div","meta", meta||"—"));
      if(b.odometer){ const o=b.odometer;
        const od=el("div","meta","🛞 "+Math.round(o.km).toLocaleString("pl-PL")+" km");
        od.style.fontWeight="600"; od.style.color="var(--ink)";
        od.title="Licznik: baza "+Math.round(o.baseline_km)+" km + "+o.added_km+" km z "+o.rides+" jazd ("+o.hours+" h) od "+String(o.baseline_at).slice(0,10);
        txt.appendChild(od); }
      card.appendChild(txt);
      card.addEventListener("click",()=>{ const f=$("#bfilterBike"); if(!f) return;
        f.value = (f.value===String(b.id)) ? "" : String(b.id); bikeRender(); });
      grid.appendChild(card);
    });
    body.appendChild(grid);
  }

  body.appendChild(el("div","secttl","Komponenty"));
  const AKT = (window.QCols ? QCols.columns("bike") : []);
  const table=el("table","gt"), thead=el("thead"), htr=el("tr");
  AKT.forEach(c=>{ const th=el("th", c.num?"num":null); th.textContent=c.label; sortTh(th,BK_SORT,c.key,bikeRender); htr.appendChild(th); });
  htr.appendChild(el("th","noclick",""));
  thead.appendChild(htr); table.appendChild(thead);
  if(BK_SORT.key){ const k=BK_SORT.key; COMPS.sort(cmpBy(c=>bkSortVal(c,k), BK_NUM.indexOf(k)>=0, BK_SORT.dir)); }
  const tb=el("tbody");
  COMPS.forEach(c=>{
    const tr=el("tr", c.active?null:"arch"); tr.style.cursor="pointer";
    tr.addEventListener("click",()=>compOpen(c));
    AKT.forEach(col=>tr.appendChild(bkCellFor(c, col.key)));
    const act=el("td"), box=el("div","gact");
    const be=el("button",null,"Edytuj"); be.addEventListener("click",e=>{e.stopPropagation();compOpen(c);}); box.appendChild(be);
    const ba=el("button","sec", c.active?"Wycofaj":"Przywróć");
    ba.addEventListener("click",async e=>{ e.stopPropagation();
      try{ await postJSON("/api/bike/component/toggle",{id:c.id,active:c.active?0:1}); bikeLoad(); }catch(x){} });
    box.appendChild(ba); act.appendChild(box); tr.appendChild(act);
    tb.appendChild(tr);
  });
  table.appendChild(tb); body.appendChild(table);

  { body.appendChild(el("div","secttl","Opony"));
    const addb=el("button","btn sec","+ Dodaj oponę"); addb.type="button"; addb.style.margin="0 0 8px";
    addb.addEventListener("click",()=>tireOpen(null)); body.appendChild(addb);
    const TIRES=(BIKE.tires||[]).filter(t=>{ if(!bsel || t.wheel_id==null) return true;
      const w=wheelById(t.wheel_id); return w && String(w.bike_id)===bsel; });
    const tt=el("table","gt"), th2=el("thead"), r2=el("tr");
    const trW=t=>(t.wheel_id!=null?wheelById(t.wheel_id):null);
    const TR_COLS=[["Rower",t=>{const w=trW(t); return w?bikeShort(w.bike_id):"";}],
      ["Koło",t=>{const w=trW(t); return w?wheelLabel(w):"w garażu";}],
      ["Pozycja",t=>t.position],["Marka",t=>t.brand],["Model",t=>t.model],
      ["Szerokość",t=>t.width_mm,true],["Typ",t=>t.type],["Status",t=>t.status]];
    TR_COLS.forEach((cc,i)=>{ const th=el("th",cc[2]?"num":null,cc[0]); sortTh(th,TR_SORT,i,bikeRender); r2.appendChild(th); });
    r2.appendChild(el("th","noclick",""));
    if(TR_SORT.key!=null){ const cc=TR_COLS[TR_SORT.key]; TIRES.sort(cmpBy(cc[1],!!cc[2],TR_SORT.dir)); }
    th2.appendChild(r2); tt.appendChild(th2);
    const tb2=el("tbody");
    TIRES.forEach(t=>{
      const w=t.wheel_id!=null?wheelById(t.wheel_id):null;
      const tr=el("tr", t.status==="wycofana"?"arch":null); tr.style.cursor="pointer";
      tr.addEventListener("click",()=>tireOpen(t));
      tr.appendChild(el("td",null, w?bikeShort(w.bike_id):"—"));
      const kc=el("td",null, w?wheelLabel(w):"w garażu"); if(!w) kc.style.color="var(--muted)"; tr.appendChild(kc);
      tr.appendChild(el("td",null, t.position||"—"));
      tr.appendChild(el("td",null, t.brand||"—"));
      tr.appendChild(el("td","mdl", t.model||"—"));
      tr.appendChild(el("td","num", t.width_mm!=null?Math.round(t.width_mm)+" mm":"—"));
      tr.appendChild(el("td",null, t.type||"—"));
      const sc=el("td"); sc.appendChild(tirePill(t.status)); tr.appendChild(sc);
      const act=el("td"), box=el("div","gact"), be=el("button",null,"Edytuj");
      be.addEventListener("click",e=>{ e.stopPropagation(); tireOpen(t); }); box.appendChild(be); act.appendChild(box); tr.appendChild(act);
      tb2.appendChild(tr);
    });
    tt.appendChild(tb2); body.appendChild(tt);
    if(!TIRES.length) body.appendChild(el("div","empty","brak opon"));
  }

}

function compOpen(c){
  c=c||{};
  $("#cTitle").textContent = c.id ? "Edytuj komponent" : "Dodaj komponent";
  $("#c_id").value=c.id||"";
  const dl=$("#compCats"); dl.innerHTML="";
  (BIKE.component_categories||[]).forEach(v=>{ const o=el("option"); o.value=catPl(v); dl.appendChild(o); });
  fillSelect($("#c_status"), BIKE.statuses, c.status||"zamontowany", null);
  { const s=$("#c_bike_id"); s.innerHTML="";
    (BIKE.bikes||[]).forEach(b=>{ const o=el("option",null,bikeShort(b.id)); o.value=String(b.id); s.appendChild(o); });
    { const o=el("option",null,"— na półce —"); o.value=""; s.appendChild(o); }
    const fb=$("#bfilterBike");
    const def=(c.id && c.bike_id==null) ? "" : (c.bike_id!=null ? c.bike_id : ((fb&&fb.value) || ((BIKE.bikes||[])[0]||{}).id));
    if(def!=null) s.value=String(def); }
  { const w=$("#c_wheel_id"); if(w){ w.innerHTML="";
    const o0=el("option",null,"— nie dotyczy —"); o0.value=""; w.appendChild(o0);
    (BIKE.components||[]).filter(x=>x.category==="wheels").forEach(x=>{
      const o=el("option",null,[x.brand,x.model].filter(Boolean).join(" ")+(x.bike_id?(" · "+bikeShort(x.bike_id)):" · na półce"));
      o.value=String(x.id); w.appendChild(o); });
    w.value=c.wheel_id?String(c.wheel_id):""; } }
  { const p=$("#c_wheel_pos"); if(p) p.value=c.wheel_pos||""; }
  { const ps=$("#c_position"), pv=c.position||"";
    if(ps && ps.tagName==="SELECT" && pv && ![...ps.options].some(o=>o.value===pv)){ const o=document.createElement("option"); o.value=o.textContent=pv; ps.appendChild(o); } }
  ["category","brand","model","position","spec","serial_number","sku","url","notes"].forEach(k=>{ $("#c_"+k).value=c[k]||""; });
  $("#c_category").value=catPl(c.category);
  { let _d={}; try{ _d=c.dims?JSON.parse(c.dims):{}; }catch(e){} dimsRender(c.category||"", _d); }
  $("#c_weight_g").value=(c.weight_g!=null?c.weight_g:"");
  $("#c_mileage_km").value=(c.mileage_km!=null?c.mileage_km:"");
  $("#c_purchase_price").value=(c.purchase_price!=null?c.purchase_price:"");
  C_HAD_PHOTO=!!c.photo; C_SCRAPED_IMG="";
  const ct=$("#cThumb");
  if(c.thumb){ ct.src=c.thumb; ct.style.display=""; } else { ct.style.display="none"; ct.removeAttribute("src"); }
  ct.dataset.full=c.photo||"";
  $("#cPhotoDel").style.display=c.thumb?"":"none";
  $("#cPhotoLbl").style.display=c.id?"":"none";
  $("#cPhotoFile").value="";
  $("#cPhotoStatus").textContent = c.id ? "" : "zapisz komponent, potem dodasz zdjęcie";
  $("#cUrlStatus").textContent="";
  const cdb=$("#cDelete"); cdb.style.display = c.id ? "" : "none";
  cdb.textContent="Usuń"; cdb.classList.remove("armed"); cdb.dataset.armed="";
  $("#cMeta").textContent = c.id ? ("ID "+c.id+" · dodano: "+(qTsLocal(c.created_at,true)||"—")+" · "+(c.active===0?"wycofany":"aktywny")) : "nowy komponent";
  $("#cStatus").textContent="";
  document.body.classList.add("modal-open");
  $("#compModal").classList.add("open");
}
function compClose(){ $("#compModal").classList.remove("open"); document.body.classList.remove("modal-open"); }

async function compSave(){
  const b={id:$("#c_id").value||null, status:$("#c_status").value,
    weight_g:$("#c_weight_g").value, mileage_km:$("#c_mileage_km").value,
    purchase_price:$("#c_purchase_price").value,
    bike_id:($("#c_bike_id").value||null), wheel_id:(($("#c_wheel_id")||{}).value||null), wheel_pos:(($("#c_wheel_pos")||{}).value||null)};
  ["category","brand","model","position","spec","serial_number","sku","url","notes"].forEach(k=>{ b[k]=$("#c_"+k).value; });
  b.category=catEn(b.category);
  { const box=$("#c_dims_box"); if(box && box.style.display!=="none") b.dims=dimsCollect(); }
  if(!b.category){ $("#cStatus").textContent="podaj kategorię"; return; }
  $("#cStatus").textContent="zapis…";
  let res;
  try{ res=await postJSON("/api/bike/component/save", b); }
  catch(e){ $("#cStatus").textContent="błąd zapisu ("+e.message+")"; return; }
  if(C_SCRAPED_IMG && res && res.id && !C_HAD_PHOTO){
    $("#cStatus").textContent="zapisano — pobieram zdjęcie…";
    try{ await postJSON("/api/garage/photo/from-url",{id:Number(res.id), url:C_SCRAPED_IMG, entity:"component"}); }catch(e){}
  }
  if(res && res.removed && res.removed.length) alert("Zdjęto z koła na półkę poprzednią część (ID "+res.removed.join(", ")+").");
  compClose(); bikeLoad();
}



async function compScrape(){
  const u=$("#c_url").value.trim();
  if(!/^https?:\/\//i.test(u)){ $("#cUrlStatus").textContent="podaj adres http(s)"; return; }
  $("#cUrlStatus").textContent="zaciąganie (czytam stronę)…";
  try{
    const d=await postJSON("/api/garage/scrape",{url:u, categories:(BIKE.component_categories||[])});
    const f=d.fields||{};
    const setE=(id,v)=>{ const e=$(id); if(e && !e.value && v!=null && v!=="") e.value=v; };
    setE("#c_brand",f.brand); setE("#c_model",f.model); setE("#c_weight_g",f.weight_g);
    setE("#c_sku",f.sku); setE("#c_category",f.category);
    const cur=(f.currency||"").toUpperCase(), plnOk=!cur||cur==="PLN";
    if(plnOk) setE("#c_purchase_price",f.price);
    C_SCRAPED_IMG=f.image||"";
    const got=[f.category&&"kategoria",f.brand&&"marka",f.model&&"model",f.weight_g&&"waga",
               (f.price&&plnOk)&&"cena",f.sku&&"SKU",
               f.image&&(C_HAD_PHOTO?"zdjęcie (jest już własne)":"zdjęcie (pobiorę przy zapisie)")].filter(Boolean);
    let msg=got.length?("zaciągnięto: "+got.join(", ")):"nic nie odczytałem z tej strony";
    if(f.price&&!plnOk) msg+=" · cena "+f.price+" "+cur+" (inna waluta — nie wpisałem)";
    if(!f.weight_g) msg+=" · wagi brak na stronie";
    if(d.js_page) msg+=" · strona ładowana JS (mniej danych)";
    $("#cUrlStatus").textContent=msg;
  }catch(e){ $("#cUrlStatus").textContent="błąd ("+e.message+")"; }
}

async function compUploadPhoto(){
  const f=$("#cPhotoFile").files[0]; if(!f) return;
  const id=$("#c_id").value; if(!id){ $("#cPhotoStatus").textContent="najpierw zapisz komponent"; return; }
  const fd=new FormData(); fd.append("id",id); fd.append("file",f); fd.append("entity","component");
  $("#cPhotoStatus").textContent="wysyłanie…";
  try{
    const r=await fetch("/api/garage/photo",{method:"POST",credentials:"same-origin",body:fd});
    if(!r.ok) throw new Error(r.status);
    const d=await r.json(); const t=$("#cThumb");
    t.src=d.thumb; t.style.display=""; t.dataset.full=d.photo;
    $("#cPhotoDel").style.display=""; $("#cPhotoStatus").textContent="dodano"; bikeLoad();
  }catch(e){ $("#cPhotoStatus").textContent="błąd ("+e.message+")"; }
}
async function compDelPhoto(){
  const id=$("#c_id").value; if(!id) return;
  try{
    await postJSON("/api/garage/photo/delete",{id:Number(id), entity:"component"});
    const t=$("#cThumb"); t.style.display="none"; t.removeAttribute("src");
    $("#cPhotoDel").style.display="none"; $("#cPhotoStatus").textContent="usunięto"; bikeLoad();
  }catch(e){ $("#cPhotoStatus").textContent="błąd usuwania"; }
}

/* ================= FITTING (osobna zakladka) ================= */
const FIT_FIELDS=[
  ["saddle_height_mm","Wysokość siodła","mm"],
  ["saddle_setback_mm","Setback siodła","mm"],
  ["saddle_tilt_deg","Kąt siodła","°"],
  ["reach_mm","Reach","mm"],
  ["stack_mm","Stack","mm"],
  ["drop_mm","Drop","mm"],
  ["handlebar_width_mm","Szerokość kierownicy","mm"],
  ["stem_length_mm","Długość mostka","mm"],
  ["stem_angle_deg","Kąt mostka","°"],
  ["crank_length_mm","Długość korby","mm"],
  ["shoe_size","Rozmiar buta",""],
  ["cleat_left","Bloki L",""],
  ["cleat_right","Bloki P",""]
];

async function fitLoad(){
  try{
    if(!BIKE.fitting || !BIKE.geometry){
      BIKE=await getJSON("/api/bike/config?_="+Date.now());
    }
    fitRender();
  }catch(e){ $("#fitBody").innerHTML=""; $("#fitBody").appendChild(el("div","empty","błąd ładowania ("+e.message+")")); }
}

function fitRender(){
  if(window.QFit){ QFit.render($("#fitBody"), BIKE, async()=>{ BIKE=await getJSON("/api/bike/config?_="+Date.now()); fitRender(); }); return; }
  const body=$("#fitBody"); body.innerHTML="";
  const list=BIKE.fitting||[];
  if(!list.length){ body.appendChild(el("div","empty","Brak zapisanego fittingu.")); return; }

  const bike=(BIKE.bikes||[])[0];
  if(bike){
    const head=el("div","bikecard");
    head.appendChild(el("h3", bike.name||"Rower"));
    head.appendChild(el("div","meta", "warianty ustawień: "+list.length));
    body.appendChild(head);
  }

  const grid=el("div","fitgrid");
  list.forEach(f=>{
    const box=el("div","fitbox");
    box.appendChild(el("h4", f.variant || ("wariant #"+f.id)));
    let any=false;
    FIT_FIELDS.forEach(([k,lab,u])=>{
      if(f[k]==null || f[k]==="") return;
      any=true;
      const row=el("div","fitrow");
      row.appendChild(el("span",null,lab));
      row.appendChild(el("span",null, u ? (f[k]+" "+u) : String(f[k])));
      box.appendChild(row);
    });
    if(!any) box.appendChild(el("div","note","brak wartości liczbowych"));
    if(f.date_set){
      const row=el("div","fitrow");
      row.appendChild(el("span",null,"Data ustawienia"));
      row.appendChild(el("span",null,f.date_set));
      box.appendChild(row);
    }
    if(f.fitter_name){
      const row=el("div","fitrow");
      row.appendChild(el("span",null,"Fitter"));
      row.appendChild(el("span",null,f.fitter_name));
      box.appendChild(row);
    }
    if(f.notes) box.appendChild(el("div","note", f.notes));
    grid.appendChild(box);
  });
  body.appendChild(grid);
}


/* ---------- usuwanie nieodwracalne (sprzet / komponent) ---------- */
async function hardDelete(opts){
  const id=$(opts.idSel).value; if(!id) return;
  const b=$(opts.btnSel), st=$(opts.statusSel);
  const nazwa=opts.name()||("#"+id);
  if(b.dataset.armed!=="1"){
    b.dataset.armed="1"; b.classList.add("armed"); b.textContent="Potwierdź usunięcie";
    st.textContent="usunięcie jest nieodwracalne — kliknij ponownie";
    setTimeout(()=>{ if(b.dataset.armed==="1"){ b.dataset.armed=""; b.classList.remove("armed"); b.textContent="Usuń"; st.textContent=""; } }, 6000);
    return;
  }
  if(!window.confirm("Usunąć na zawsze: "+nazwa+"?\n\nZniknie z bazy razem ze zdjęciem. Tego nie da się cofnąć.")){
    b.dataset.armed=""; b.classList.remove("armed"); b.textContent="Usuń"; st.textContent=""; return;
  }
  st.textContent="usuwanie…";
  try{
    await postJSON(opts.endpoint,{id:Number(id), confirm:true});
    opts.close(); opts.reload();
  }catch(e){ st.textContent="błąd usuwania ("+e.message+")"; }
}

function eqDelete(){
  return hardDelete({idSel:"#e_id", btnSel:"#eDelete", statusSel:"#eStatus",
    endpoint:"/api/equipment/delete", close:eqClose, reload:eqLoad,
    name:()=>[$("#e_brand").value,$("#e_model").value].filter(Boolean).join(" ")});
}
function compDelete(){
  return hardDelete({idSel:"#c_id", btnSel:"#cDelete", statusSel:"#cStatus",
    endpoint:"/api/bike/component/delete", close:compClose, reload:bikeLoad,
    name:()=>[$("#c_brand").value,$("#c_model").value].filter(Boolean).join(" ")});
}

window.QSwitchTab = switchTab;   // uzywane przez modul instrukcji

/* ================= start ================= */
document.addEventListener("DOMContentLoaded",function(){
  $("#tabGear").addEventListener("click",()=>switchTab("Gear"));
  $("#tabEquip").addEventListener("click",()=>switchTab("Equip"));
  $("#tabBike").addEventListener("click",()=>switchTab("Bike"));
  $("#tabFit").addEventListener("click",()=>switchTab("Fit"));
  if(window.QCols){
    QCols.init("equip","colWrapEquip","colBtnEquip", eqRender);
    QCols.init("bike","colWrapBike","colBtnBike", bikeRender);
  }

  $("#esearch").addEventListener("input", eqRender);
  $("#efilter").addEventListener("change", eqRender);
  $("#eadd").addEventListener("click",()=>eqOpen(null));
  $("#earch").addEventListener("click",function(){
    EQ_ALL=!EQ_ALL; this.classList.toggle("on",EQ_ALL);
    this.textContent=EQ_ALL?"Ukryj archiwum":"Pokaż archiwum"; eqLoad();
  });
  $("#eSave").addEventListener("click", eqSave);
  $("#eDelete").addEventListener("click", eqDelete);
  $("#eCancel").addEventListener("click", eqClose);
  $("#eCancelX").addEventListener("click", eqClose);
  $("#eScrape").addEventListener("click", eqScrape);
  $("#ePhotoFile").addEventListener("change", eqUploadPhoto);
  $("#ePhotoDel").addEventListener("click", eqDelPhoto);
  $("#eThumb").addEventListener("click",()=>{ const f=$("#eThumb").dataset.full; if(f){ $("#lightboxImg").src=f; document.body.classList.add("lb-open"); } });
  document.querySelectorAll("#eRating button").forEach(b=>{
    b.addEventListener("click",()=>{ EQ_RATING=Number(b.dataset.v); eqPaintRating(); });
  });
  $("#eRatingClr").addEventListener("click",()=>{ EQ_RATING=null; eqPaintRating(); });

  $("#badd").addEventListener("click",()=>compOpen(null));
  $("#barch").addEventListener("click",function(){
    BIKE_ALL=!BIKE_ALL; this.classList.toggle("on",BIKE_ALL);
    this.textContent=BIKE_ALL?"Ukryj wycofane":"Pokaż wycofane"; bikeLoad();
  });
  $("#cSave").addEventListener("click", compSave);
  $("#cDelete").addEventListener("click", compDelete);
  $("#cCancel").addEventListener("click", compClose);
  $("#cCancelX").addEventListener("click", compClose);
  $("#cScrape").addEventListener("click", compScrape);
  $("#cPhotoFile").addEventListener("change", compUploadPhoto);
  $("#cPhotoDel").addEventListener("click", compDelPhoto);
  $("#cThumb").addEventListener("click",()=>{ const f=$("#cThumb").dataset.full; if(f){ $("#lightboxImg").src=f; document.body.classList.add("lb-open"); } });
});
// filtr roweru w zakladce Rower
document.addEventListener("change",e=>{ if(e.target&&e.target.id==="bfilterBike") bikeRender(); });
document.addEventListener("input",e=>{ if(e.target&&e.target.id==="bsearch") bikeRender(); });
// wymiary czesci zaleza od kategorii
document.addEventListener("input",e=>{ if(e.target&&e.target.id==="c_category") dimsRender(catEn(e.target.value), dimsCollect()); });
// okno OPONY
document.addEventListener("change",e=>{ const i=e.target&&e.target.id; if(i==="t_wheel"||i==="t_position") tireSync(); else if(i==="bkPhotoFile") bikeUploadPhoto(); });
document.addEventListener("click",e=>{ const t=e.target; if(!t) return; const i=t.id;
  if(i==="tSave") tireSave(); else if(i==="tCancel"||i==="tCancelX") tireClose(); else if(i==="tDelete") tireDelete(t);
  else if(i==="bkAdd") bikeOpen(null); else if(i==="bkPhotoDel") bikeDelPhoto(); else if(i==="bkPhotoFetch") bikeFetchPhoto();
  else if(i==="bkSave") bikeSave(); else if(i==="bkCancel"||i==="bkCancelX") bikeClose(); else if(i==="bkDelete") bikeDelete(t);
  else if(t.classList&&t.classList.contains("modal-back")&&$("#bikeModal").classList.contains("open")) bikeClose();
  else if(t.classList&&t.classList.contains("modal-back")&&$("#tireModal").classList.contains("open")) tireClose(); });
})();
