/* garaz-columns.js — wybor widocznych kolumn w tabelach Garazu.
   Wspolny mechanizm dla zakladek: odziez / sprzet / rower.
   Ustawienie zapisywane po stronie serwera (garage.db ui_prefs), wiec trzyma sie miedzy urzadzeniami. */
(function(){
"use strict";
const el = (t,c,h) => { const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.textContent=h; return e; };

/* Pelna lista pol dostepnych w kazdej tabeli.
   key = nazwa pola w bazie, label = etykieta, grupa = sekcja w liscie wyboru. */
const CATALOG = {
  gear: [
    {key:"category",   label:"Kategoria",     grupa:"Podstawowe"},
    {key:"brand",      label:"Marka",         grupa:"Podstawowe"},
    {key:"model",      label:"Model",         grupa:"Podstawowe"},
    {key:"size",       label:"Rozmiar",       grupa:"Podstawowe"},
    {key:"color_q",    label:"Kolor",         grupa:"Podstawowe"},
    {key:"color",      label:"Kolor producenta", grupa:"Podstawowe"},
    {key:"fabric",     label:"Materiał",      grupa:"Zastosowanie"},
    {key:"season",     label:"Sezon",         grupa:"Zastosowanie"},
    {key:"rating",     label:"Moja ocena",    grupa:"Zastosowanie"},
    {key:"weight_g",   label:"Waga",          grupa:"Zastosowanie", num:true},
    {key:"r_intensity",label:"Intensywność",  grupa:"Oceny 7", num:true},
    {key:"r_breath",   label:"Oddychalność",  grupa:"Oceny 7", num:true},
    {key:"r_dry",      label:"Szybkoschnięcie",grupa:"Oceny 7", num:true},
    {key:"r_insul",    label:"Izolacja",      grupa:"Oceny 7", num:true},
    {key:"r_wind",     label:"Wiatroszczelność",grupa:"Oceny 7", num:true},
    {key:"r_water",    label:"Wodoodporność", grupa:"Oceny 7", num:true},
    {key:"r_pack",     label:"Pakowność",     grupa:"Oceny 7", num:true},
    {key:"condition",  label:"Stan",          grupa:"Zakup i dane"},
    {key:"purchase_price",label:"Cena",       grupa:"Zakup i dane", num:true},
    {key:"purchase_date", label:"Data zakupu",grupa:"Zakup i dane"},
    {key:"sku",        label:"SKU",           grupa:"Zakup i dane"},
    {key:"ean",        label:"EAN",           grupa:"Zakup i dane"},
    {key:"notes",      label:"Notatki",       grupa:"Zakup i dane"}
  ],
  equip: [
    {key:"category",   label:"Kategoria",     grupa:"Podstawowe"},
    {key:"brand",      label:"Marka",         grupa:"Podstawowe"},
    {key:"model",      label:"Model",         grupa:"Podstawowe"},
    {key:"mount",      label:"Montaż",        grupa:"Podstawowe"},
    {key:"capacity_l", label:"Pojemność",     grupa:"Podstawowe", num:true},
    {key:"weight_g",   label:"Waga",          grupa:"Podstawowe", num:true},
    {key:"size",       label:"Rozmiar",       grupa:"Podstawowe"},
    {key:"color_q",    label:"Kolor",         grupa:"Podstawowe"},
    {key:"rating",     label:"Moja ocena",    grupa:"Zakup i dane"},
    {key:"status",     label:"Status",        grupa:"Zakup i dane"},
    {key:"condition",  label:"Stan",          grupa:"Zakup i dane"},
    {key:"purchase_price",label:"Cena",       grupa:"Zakup i dane", num:true},
    {key:"purchase_date", label:"Data zakupu",grupa:"Zakup i dane"},
    {key:"sku",        label:"SKU",           grupa:"Zakup i dane"},
    {key:"ean",        label:"EAN",           grupa:"Zakup i dane"},
    {key:"notes",      label:"Notatki",       grupa:"Zakup i dane"}
  ],
  bike: [
    {key:"bike_id",    label:"Rower",         grupa:"Podstawowe"},
    {key:"category",   label:"Kategoria",     grupa:"Podstawowe"},
    {key:"brand",      label:"Marka",         grupa:"Podstawowe"},
    {key:"model",      label:"Model",         grupa:"Podstawowe"},
    {key:"position",   label:"Pozycja",       grupa:"Podstawowe"},
    {key:"status",     label:"Status",        grupa:"Podstawowe"},
    {key:"weight_g",   label:"Waga",          grupa:"Podstawowe", num:true},
    {key:"mileage_km", label:"Przebieg",      grupa:"Podstawowe", num:true},
    {key:"spec",       label:"Specyfikacja",  grupa:"Zakup i dane"},
    {key:"serial_number",label:"Nr seryjny",  grupa:"Zakup i dane"},
    {key:"sku",        label:"SKU",           grupa:"Zakup i dane"},
    {key:"purchase_price",label:"Cena",       grupa:"Zakup i dane", num:true},
    {key:"purchase_date", label:"Data zakupu",grupa:"Zakup i dane"},
    {key:"notes",      label:"Notatki",       grupa:"Zakup i dane"}
  ]
};

const DEFAULTS = {
  gear:  ["category","brand","model","size","color_q","fabric","season","rating","weight_g","condition","purchase_price"],
  equip: ["category","brand","model","mount","capacity_l","weight_g","color_q","rating","status","purchase_price"],
  bike:  ["bike_id","category","brand","model","position","status","weight_g","mileage_km"]
};

const STATE = {};          // tabela -> lista widocznych kluczy
const ONCHANGE = {};       // tabela -> funkcja przerysowujaca

async function loadPrefs(tabela){
  try{
    const r = await fetch("/api/garage/prefs?key=kolumny_"+tabela+"&_="+Date.now(),
                          {credentials:"same-origin",cache:"no-store"});
    if(r.ok){
      const d = await r.json();
      if(Array.isArray(d.value) && d.value.length){
        const znane = new Set(CATALOG[tabela].map(c=>c.key));
        STATE[tabela] = d.value.filter(k=>znane.has(k));
        if(STATE[tabela].length) return;
      }
    }
  }catch(e){ /* brak ustawien = domyslne */ }
  STATE[tabela] = DEFAULTS[tabela].slice();
}

async function savePrefs(tabela){
  try{
    await fetch("/api/garage/prefs",{method:"POST",credentials:"same-origin",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({key:"kolumny_"+tabela, value:STATE[tabela]})});
  }catch(e){ /* zapis nieudany - ustawienie i tak dziala do konca sesji */ }
}

function buildPanel(tabela, wrapId){
  const wrap = document.getElementById(wrapId);
  if(!wrap) return;
  const box = wrap.querySelector(".colpick");
  box.innerHTML = "";
  const widoczne = new Set(STATE[tabela] || []);
  let grupa = null;
  CATALOG[tabela].forEach(col=>{
    if(col.grupa !== grupa){ grupa = col.grupa; box.appendChild(el("div","h",grupa)); }
    const lab = el("label");
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = widoczne.has(col.key); cb.dataset.key = col.key;
    cb.addEventListener("change", ()=>{
      const lista = CATALOG[tabela].filter(c=>{
        const i = box.querySelector('input[data-key="'+c.key+'"]');
        return i && i.checked;
      }).map(c=>c.key);
      if(!lista.length){ cb.checked = true; return; }   // zawsze co najmniej jedna kolumna
      STATE[tabela] = lista;
      savePrefs(tabela);
      if(ONCHANGE[tabela]) ONCHANGE[tabela]();
    });
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(col.label));
    box.appendChild(lab);
  });
  const foot = el("div","foot");
  const bDef = el("button",null,"Domyślne");
  bDef.addEventListener("click",()=>{ STATE[tabela]=DEFAULTS[tabela].slice(); savePrefs(tabela);
    buildPanel(tabela, wrapId); if(ONCHANGE[tabela]) ONCHANGE[tabela](); });
  const bAll = el("button",null,"Zaznacz wszystko");
  bAll.addEventListener("click",()=>{ STATE[tabela]=CATALOG[tabela].map(c=>c.key); savePrefs(tabela);
    buildPanel(tabela, wrapId); if(ONCHANGE[tabela]) ONCHANGE[tabela](); });
  foot.appendChild(bDef); foot.appendChild(bAll);
  box.appendChild(foot);
}

/* API dla modulow tabel */
window.QCols = {
  async init(tabela, wrapId, btnId, onChange){
    ONCHANGE[tabela] = onChange;
    await loadPrefs(tabela);
    buildPanel(tabela, wrapId);
    const wrap = document.getElementById(wrapId), btn = document.getElementById(btnId);
    if(btn && wrap){
      btn.addEventListener("click", e=>{
        e.stopPropagation();
        document.querySelectorAll(".colwrap.open").forEach(w=>{ if(w!==wrap) w.classList.remove("open"); });
        wrap.classList.toggle("open");
      });
      wrap.querySelector(".colpick").addEventListener("click", e=>e.stopPropagation());
    }
  },
  /* zwraca definicje widocznych kolumn, w kolejnosci z katalogu */
  columns(tabela){
    const widoczne = new Set(STATE[tabela] || DEFAULTS[tabela]);
    return CATALOG[tabela].filter(c=>widoczne.has(c.key));
  }
};

document.addEventListener("click", ()=>{
  document.querySelectorAll(".colwrap.open").forEach(w=>w.classList.remove("open"));
});
})();
