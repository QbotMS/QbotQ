/* garaz-audyt.js — sekcja "Ocena z audytu (dla doradcy ubioru)" w oknie edycji rzeczy Garazu.
   Czyta/zapisuje pola a_* przez /api/garage/audit (+ /save). Niezalezne od garaz-render.js:
   wykrywa otwarcie okna #gearModal i id z #m_id. Zapis: przycisk "Zapisz ocenę" albo razem z "Zapisz". */
(function(){
"use strict";
const $=s=>document.querySelector(s);
const L={
  st:{CORE:"Rdzeń",ROTATION:"Rotacja",SPECIAL:"Potrzebny specjalista",BACKUP:"Zapas",RETIRE_CANDIDATE:"Kandydat do wycofania",
      FIT_BLOCKED:"Fit blokuje (za ciasna)",OFF_BIKE:"Głównie poza rowerem",NEW:"Nowa / nietestowana"},
  fit:{OK:"OK",LEKKO_CIASNA:"Lekko ciasna",ZA_LUZNA:"Za luźna",BLOKUJE:"Za ciasna — blokuje"},
  use:{CZESTO:"Często",SPORADYCZNIE:"Sporadycznie",RZADKO:"Rzadko",NIGDY:"Nigdy"},
  eff:{"spokojnie":"Spokojnie","Z2":"Z2","Z2-Z3":"Z2–Z3"},
  rain:{brak_oczekiwan:"Nie oczekuję ochrony",nietestowany:"Nietestowana w deszczu",mzawka_przemaka:"Mżawka — przemaka",
        mzawka_sucho:"Mżawka — sucho",umiarkowany_przemaka_po_czasie:"Umiarkowany — przemaka po czasie",
        umiarkowany_sucho:"Umiarkowany — sucho",ulewa_sucho:"Ulewa — sucho"},
  wind:{mocna:"Mocna",umiarkowana:"Umiarkowana",czesciowa:"Częściowa",mala:"Mała"},
  pad:{"0":"Brak wkładki","<1":"< 1 h","1-2":"1–2 h","2-4":"2–4 h","4-6":"4–6 h",">6":"> 6 h"},
  carry:{czesto:"Często",sporadycznie:"Sporadycznie",rzadko:"Rzadko"}
};
const SEL=[["st","Status"],["fit","Fit"],["use","Noszenie w tym roku"],["eff","Wysiłek"],["rain","Najmocniejszy sprawdzony deszcz"],
           ["wind","Ochrona od wiatru"],["pad","Sprawdzona wkładka"],["carry","Wożona awaryjnie"]];
let CUR_ID=null, DIRTY=false, BOX=null, A_PEND=null;

function h(t,a,txt){const e=document.createElement(t);if(a)for(const k in a)e.setAttribute(k,a[k]);if(txt!=null)e.textContent=txt;return e;}
async function jget(u){const r=await fetch(u,{credentials:"same-origin",cache:"no-store"});if(!r.ok)throw new Error(r.status);return r.json();}
async function jpost(u,b){const r=await fetch(u,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});
  if(!r.ok){let m=r.status;try{m=(await r.json()).detail||m;}catch(e){}throw new Error(m);}return r.json();}

function build(){
  const anchor=$("#gearModal .mphoto"); if(!anchor||BOX)return;
  BOX=h("details",{class:"maudit",id:"mAudit"});
  BOX.style.cssText="margin:14px 0 4px;border:1px solid var(--line,#3334);border-radius:10px;padding:8px 12px";
  const sum=h("summary",null,"Ocena z audytu — dla doradcy ubioru"); sum.style.cssText="cursor:pointer;font-weight:600";
  const info=h("span",{id:"aInfo"},""); info.style.cssText="font-weight:400;color:var(--muted);margin-left:8px;font-size:13px";
  sum.appendChild(info); BOX.appendChild(sum);
  const g=h("div",{class:"mgrid"}); g.style.marginTop="10px";
  SEL.forEach(([k,lab])=>{const d=h("div",{class:"mf"});d.appendChild(h("label",null,lab));const s=h("select",{id:"a_"+k});
    s.appendChild(h("option",{value:""},"— nie podano —"));Object.keys(L[k]).forEach(v=>s.appendChild(h("option",{value:v},L[k][v])));d.appendChild(s);g.appendChild(d);});
  [["t_min","Temperatura zestawu od (°C)"],["t_max","do (°C)"]].forEach(([k,lab])=>{const d=h("div",{class:"mf"});d.appendChild(h("label",null,lab));
    d.appendChild(h("input",{id:"a_"+k,type:"number",min:"-20",max:"40",step:"1",placeholder:k==="t_min"?"-20 = bez granicy":"40 = bez granicy"}));g.appendChild(d);});
  [["wet","Mokra wychładza (postój / zjazd)"],["out","Nie proponuj do jazdy"]].forEach(([k,lab])=>{const d=h("div",{class:"mf"});
    const l=h("label",null,"");const c=h("input",{id:"a_"+k,type:"checkbox"});c.style.marginRight="6px";l.appendChild(c);l.appendChild(document.createTextNode(lab));d.appendChild(l);g.appendChild(d);});
  [["role","Rola (po co ta rzecz)",1],["pairs","Z czym zwykle łączysz",1],["note","Uwagi (wady, zalety, doświadczenia)",3],["src","Źródło oceny",1]].forEach(([k,lab,rows])=>{
    const d=h("div",{class:"mf full"});d.appendChild(h("label",null,lab));d.appendChild(rows>1?h("textarea",{id:"a_"+k,rows:String(rows)}):h("input",{id:"a_"+k}));g.appendChild(d);});
  BOX.appendChild(g);
  const f=h("div",null,""); f.style.cssText="display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap";
  const bs=h("button",{type:"button",class:"btn sec",id:"aSave"},"Zapisz ocenę");
  const bc=h("button",{type:"button",class:"btn sec",id:"aClear"},"Usuń ocenę");
  const msg=h("span",{id:"aMsg"},""); msg.style.cssText="font-size:13px;color:var(--muted)";
  f.appendChild(bs);f.appendChild(bc);f.appendChild(msg);BOX.appendChild(f);
  anchor.parentNode.insertBefore(BOX, anchor.nextSibling);
  BOX.addEventListener("input",()=>{DIRTY=true;}); BOX.addEventListener("change",()=>{DIRTY=true;});
  bs.addEventListener("click",()=>save(false)); bc.addEventListener("click",clear);
  const ms=$("#mSave"); if(ms) ms.addEventListener("click",()=>{ if(!DIRTY) return; if(CUR_ID) save(true);
    else { const x={}; KEYS.forEach(k=>x[k]=getv(k)); A_PEND=x; } }, true);
}
function setv(k,v){const e=$("#a_"+k);if(!e)return;if(e.type==="checkbox")e.checked=!!v;else e.value=(v==null?"":v);}
function getv(k){const e=$("#a_"+k);return e.type==="checkbox"?e.checked:e.value;}
const KEYS=["st","fit","use","eff","rain","wind","pad","carry","t_min","t_max","wet","out","role","pairs","note","src"];
function fill(a){KEYS.forEach(k=>setv(k,a?a[k]:null));$("#aInfo").textContent=a?("ocena z "+(a.date||"?")+(a.src?" · "+a.src:"")):"brak oceny";DIRTY=false;}
function enable(on){BOX.querySelectorAll("select,input,textarea,button").forEach(e=>e.disabled=!on);}

/* ---- parametry rzeczy: czesc ciala + dlugosc (kategoria mowi o rodzaju, parametry o kroju) ---- */
const PBODY={gora:"góra",dol:"dół"}, PLEN={bez:"bez rękawów",krotki:"krótki","34":"3/4",dlugi:"długi"};
const PLAY={chetnie:"chętnie",potrzeba:"w razie potrzeby",nie:"nie (tylko sama)"}, PSTY={kolarski:"kolarski",outdoor:"outdoorowy"};
const PCATS={"Termika":["body","len"],"Koszulki i bluzy kolarskie":["len","layer","style"],"Koszulki i bluzy techniczne":["len","layer","style"],
  "Kurtki i kamizelki":["len","style"],"Odzież deszczowa":["body","len","style"],"Spodnie i spodenki z wkładką":["len"],
  "Spodnie i spodenki bez wkładki":["len"],"Rękawki i nogawki":["body","len"]};
let PF=null, P_DIRTY=false, P_PEND=null;
/* nowa rzecz: po udanym POST /api/garage/save dopisz parametry do nadanego id */
(function(){ const of=window.fetch; if(!of||of._qbotParams) return;
  const nf=function(u,o){ const p=of.apply(this,arguments);
    try{ const url=typeof u==="string"?u:((u&&u.url)||"");
      if((P_PEND||A_PEND) && url.indexOf("/api/garage/save")>=0 && o && String(o.method||"").toUpperCase()==="POST"){
        const pend=P_PEND, apend=A_PEND; P_PEND=null; A_PEND=null;
        p.then(r=>{ if(!r.ok) return; r.clone().json().then(d=>{ const id=Number(d&&d.id); if(!id) return;
          if(pend) jpost("/api/garage/audit/params",{id:id,g_body:pend.g_body,g_len:pend.g_len,g_layer:pend.g_layer,g_style:pend.g_style})
            .catch(e=>alert("Nie zapisano parametrów rzeczy: "+e.message));
          if(apend) jpost("/api/garage/audit/save",{id:id,audit:apend})
            .catch(e=>alert("Nie zapisano oceny z audytu: "+e.message)); }).catch(()=>{}); }).catch(()=>{});
      } }catch(e){}
    return p; };
  nf._qbotParams=true; window.fetch=nf; })();
function pBuild(){
  const cs=$("#m_category"); if(!cs||PF) return;
  const anchor=cs.closest(".mf"); if(!anchor) return;
  const mk=(id,lab,opts)=>{const d=h("div",{class:"mf",id:id+"_w"});d.appendChild(h("label",null,lab));const s=h("select",{id:id});
    s.appendChild(h("option",{value:""},"— nie podano —"));Object.keys(opts).forEach(v=>s.appendChild(h("option",{value:v},opts[v])));
    s.addEventListener("change",()=>{P_DIRTY=true;});d.appendChild(s);return d;};
  const b=mk("m_g_body","Część ciała",PBODY), l=mk("m_g_len","Długość (rękawa / nogawki)",PLEN);
  const y=mk("m_g_layer","Warstwowanie (gilet, rękawki, baza)",PLAY), s=mk("m_g_style","Styl",PSTY);
  anchor.parentNode.insertBefore(s, anchor.nextSibling); anchor.parentNode.insertBefore(y, anchor.nextSibling);
  anchor.parentNode.insertBefore(l, anchor.nextSibling); anchor.parentNode.insertBefore(b, anchor.nextSibling);
  PF={b:b,l:l,y:y,s:s};
  cs.addEventListener("change",pVis);
  const ms=$("#mSave"); if(ms) ms.addEventListener("click",()=>{ if(!P_DIRTY) return; if(CUR_ID) pSave();
    else P_PEND={g_body:$("#m_g_body").value||null,g_len:$("#m_g_len").value||null,
      g_layer:$("#m_g_layer").value||null,g_style:$("#m_g_style").value||null}; }, true);
}
function pVis(){ if(!PF)return; const sp=PCATS[($("#m_category")||{}).value]||[];
  PF.b.style.display=sp.indexOf("body")>=0?"":"none"; PF.l.style.display=sp.indexOf("len")>=0?"":"none";
  PF.y.style.display=sp.indexOf("layer")>=0?"":"none"; PF.s.style.display=sp.indexOf("style")>=0?"":"none"; }
async function pOpen(){
  pBuild(); if(!PF) return; P_DIRTY=false;
  ["#m_g_body","#m_g_len","#m_g_layer","#m_g_style"].forEach(k=>{ $(k).value=""; $(k).disabled=false; });
  condLock(null); P_PEND=null;
  PF.l.title=PF.b.title="";
  pVis();
  if(!CUR_ID) return;
  try{ const d=await jget("/api/garage/audit/params?id="+CUR_ID+"&_="+Date.now());
    $("#m_g_body").value=d.g_body||""; $("#m_g_len").value=d.g_len||""; $("#m_g_layer").value=d.g_layer||""; $("#m_g_style").value=d.g_style||"";
    P_DIRTY=false; condLock(d); }catch(e){}
}
/* pole "Stan" = wynik pytania "Stan techniczny" z ankiety (nie edytujemy recznie, poza "Retired") */
function condLock(d){
  const cs=$("#m_condition"); if(!cs) return;
  const lab=cs.closest(".mf") ? cs.closest(".mf").querySelector("label") : null;
  const locked = d && d.s_cond!=null && d.condition!=="Retired";
  cs.disabled = !!locked;
  cs.title = locked ? "ustawiane z ankiety (Stan techniczny: "+(d.s_cond>0?"+":"")+d.s_cond+")" : "";
  if(lab) lab.textContent = locked ? "Stan (z ankiety)" : "Stan";
}
async function pSave(){
  try{ await jpost("/api/garage/audit/params",{id:CUR_ID,g_body:$("#m_g_body").value||null,g_len:$("#m_g_len").value||null,
    g_layer:$("#m_g_layer").value||null,g_style:$("#m_g_style").value||null}); P_DIRTY=false; }
  catch(e){ alert("Nie zapisano parametrów rzeczy: "+e.message); }
}

async function onOpen(){
  CUR_ID=Number(($("#m_id")||{}).value)||null; pOpen();
  build(); if(!BOX)return;
  CUR_ID=Number(($("#m_id")||{}).value)||null; $("#aMsg").textContent=""; DIRTY=false;
  if(!CUR_ID){fill(null);enable(true);A_PEND=null;$("#aSave").disabled=true;$("#aClear").disabled=true;
    $("#aInfo").textContent="zapisze się razem z rzeczą";return;}
  enable(false);$("#aInfo").textContent="wczytuję…";
  try{const d=await jget("/api/garage/audit?id="+CUR_ID+"&_="+Date.now());fill(d.audit);enable(true);}
  catch(e){$("#aInfo").textContent="błąd odczytu ("+e.message+")";}
}
async function save(silent){
  if(!CUR_ID)return; const a={}; KEYS.forEach(k=>a[k]=getv(k));
  if(!silent)$("#aMsg").textContent="zapis…";
  try{const d=await jpost("/api/garage/audit/save",{id:CUR_ID,audit:a});fill(d.audit);if(!silent)$("#aMsg").textContent="zapisano";}
  catch(e){$("#aMsg").textContent="błąd: "+e.message; if(silent)alert("Nie zapisano oceny z audytu: "+e.message);}
}
async function clear(){
  if(!CUR_ID||!confirm("Usunąć ocenę z audytu dla tej rzeczy? Doradca wróci do starych notatek."))return;
  try{const d=await jpost("/api/garage/audit/save",{id:CUR_ID,clear:true});fill(d.audit);$("#aMsg").textContent="usunięto";}
  catch(e){$("#aMsg").textContent="błąd: "+e.message;}
}
function watch(){
  const m=$("#gearModal"); if(!m)return;
  let was=m.classList.contains("open");
  new MutationObserver(()=>{const now=m.classList.contains("open");if(now&&!was)setTimeout(onOpen,0);was=now;}).observe(m,{attributes:true,attributeFilter:["class"]});
  /* po zamknieciu ankiety nad oknem edycji: odswiez Stan (ankieta moze go zmienic) */
  let svyWas=document.body.classList.contains("svy-open");
  new MutationObserver(()=>{const so=document.body.classList.contains("svy-open");
    if(svyWas&&!so&&m.classList.contains("open")&&CUR_ID) refreshCond(); svyWas=so;}).observe(document.body,{attributes:true,attributeFilter:["class"]});
}
async function refreshCond(){ try{ const d=await jget("/api/garage/audit/params?id="+CUR_ID+"&_="+Date.now());
  const cs=$("#m_condition"); if(cs&&d.condition) cs.value=d.condition; condLock(d); }catch(e){} }
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",watch);else watch();
})();
