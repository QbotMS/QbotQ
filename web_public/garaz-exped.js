/* czas lokalny (strefa przegladarki) -- wspolne dla QBot lab */function qTsLocal(s,naiveUtc){if(!s)return"";var t=String(s).trim().replace(" ","T").replace(/\.\d+/,"");if(/[+-]\d\d$/.test(t))t+=":00";t=t.replace(/([+-]\d\d)(\d\d)$/,"$1:$2");if(!/(Z|[+-]\d\d:\d\d)$/i.test(t)){if(!naiveUtc)return t.slice(0,16).replace("T"," ");t+="Z";}var d=new Date(t);if(isNaN(d.getTime()))return String(s).slice(0,16);var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());}function qDateLocal(d){d=d||new Date();var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
/* garaz-exped.js — zakladka "Wyprawowy": rzeczy z gear o kategorii "Sprzet wyprawowy".
   Pelny modal (jak Odziez): wszystkie pola bazy + zaciaganie z linku (scrape),
   plus tryb ZESTAW (apteczka / narzedzia) ze skladem (nazwa/szt./notatka, min 3 wiersze). */
(function(){
"use strict";
var CAT = "Sprz\u0119t wyprawowy";
var $ = function(id){ return document.getElementById(id); };
var LOADED = false, ITEMS = [], CONDITIONS = [], CATS = [], SCRAPED_IMG = "", HAD_PHOTO = false;

var TABS = [["tabGear","viewGear","toolbarGear"],["tabEquip","viewEquip","toolbarEquip"],
            ["tabExped","viewExped","toolbarExped"],["tabBike","viewBike","toolbarBike"],
            ["tabFit","viewFit","toolbarFit"]];

function showExped(){
  TABS.forEach(function(t){
    var on = (t[0] === "tabExped");
    var tb = $(t[0]), vw = $(t[1]), br = $(t[2]);
    if(tb) tb.classList.toggle("on", on);
    if(vw) vw.classList.toggle("on", on);
    if(br) br.style.display = on ? "" : "none";
  });
  var box = $("tabSearch"); if(box) box.style.visibility = "hidden";
  if(!LOADED){ LOADED = true; load(); }
}
function hideExped(){
  var tb = $("tabExped"), vw = $("viewExped"), br = $("toolbarExped");
  if(tb) tb.classList.remove("on");
  if(vw) vw.classList.remove("on");
  if(br) br.style.display = "none";
}

function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]; }); }

function postJSON(u,b){
  return fetch(u,{method:"POST",credentials:"same-origin",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(b)})
    .then(function(r){ if(!r.ok) throw new Error(r.status); return r.json(); });
}

function load(){
  fetch("/api/garage/list?kind=wyprawowy&all=1&_="+Date.now(),{credentials:"same-origin",cache:"no-store"})
    .then(function(r){ if(!r.ok) throw new Error(r.status); return r.json(); })
    .then(function(d){ ITEMS = d.items || []; CONDITIONS = d.conditions || [];
                       CATS = d.exped_categories || []; render(); })
    .catch(function(e){ $("expedBody").innerHTML = '<div class="empty">błąd ładowania ('+e.message+')</div>'; });
}

function setCount(it){
  if(!it.is_set) return 0;
  try{ var a = JSON.parse(it.set_items||"[]"); return a.length||0; }catch(e){ return 0; }
}

function render(){
  var q = ($("xsearch") && $("xsearch").value || "").trim().toLowerCase();
  var rows = ITEMS.filter(function(it){
    if(!q) return true;
    var hay = [it.category,it.brand,it.model,it.size,it.notes,it.color].map(function(x){return x||"";}).join(" ").toLowerCase();
    return hay.indexOf(q) >= 0;
  });
  $("xcount").textContent = rows.length + (rows.length===1?" rzecz":" rzeczy");
  if(!rows.length){
    $("expedBody").innerHTML = '<div class="empty">Pusto. Dodaj pozycję przyciskiem „+ Dodaj sprzęt wyprawowy” albo z Plannera wyposażenia.</div>';
    return;
  }
  var h = '<table class="gt"><thead><tr>'
        + '<th>Kategoria</th><th>Marka</th><th>Model / nazwa</th><th>Rodzaj / rozmiar</th>'
        + '<th class="num">Szt.</th><th class="num">Waga</th><th>Notatki</th><th></th>'
        + '</tr></thead><tbody>';
  rows.forEach(function(it){
    var badge = it.is_set ? ' <span class="fab mer">zestaw · '+setCount(it)+' poz.</span>' : '';
    h += '<tr'+(it.active?"":' class="arch"')+'>'
      +  '<td>'+esc(it.category||"")+'</td>'
      +  '<td>'+esc(it.brand||"")+'</td>'
      +  '<td class="mdl">'+esc(it.model||"")+badge+'</td>'
      +  '<td>'+esc(it.size||"")+'</td>'
      +  '<td class="num">'+(it.qty!=null?it.qty:"")+'</td>'
      +  '<td class="num">'+(it.weight_g!=null?(it.weight_g+" g"):"")+'</td>'
      +  '<td>'+esc(it.notes||"")+'</td>'
      +  '<td class="gact"><button class="sec" data-edit="'+it.id+'">Edytuj</button>'
      +  '<button class="sec" data-arch="'+it.id+'">'+(it.active?"Archiwizuj":"Przywróć")+'</button></td>'
      +  '</tr>';
  });
  h += '</tbody></table>';
  $("expedBody").innerHTML = h;
  $("expedBody").querySelectorAll("[data-edit]").forEach(function(b){
    b.onclick = function(){ openModal(findIt(Number(b.getAttribute("data-edit")))); }; });
  $("expedBody").querySelectorAll("[data-arch]").forEach(function(b){
    b.onclick = function(){ toggle(Number(b.getAttribute("data-arch"))); }; });
}

function findIt(id){ return ITEMS.filter(function(x){ return x.id===id; })[0] || {}; }

/* ---- sklad zestawu ---- */
function setRowHTML(name, qty, note){
  var st = "padding:6px 8px;border:1px solid var(--line);border-radius:7px;background:var(--paper);color:var(--ink);font-size:14px";
  return '<div class="setrow" style="display:flex;gap:6px;margin-bottom:6px;align-items:center">'
    + '<input class="sr-name" placeholder="nazwa" value="'+esc(name)+'" style="flex:2 1 0;min-width:0;'+st+'">'
    + '<input class="sr-qty" type="number" step="1" placeholder="szt." value="'+(qty!=null?esc(qty):"")+'" style="width:66px;'+st+'">'
    + '<input class="sr-note" placeholder="notatka" value="'+esc(note)+'" style="flex:2 1 0;min-width:0;'+st+'">'
    + '<button type="button" class="sr-del btn sec" style="padding:6px 10px">×</button>'
    + '</div>';
}
function bindSetRows(){
  $("xSetRows").querySelectorAll(".sr-del").forEach(function(b){
    b.onclick = function(){
      var r = b.closest(".setrow"); if(r) r.remove();
    };
  });
}
function fillSetRows(list){
  var arr = (list && list.length) ? list : [{},{},{}];   // domyslnie 3 wiersze
  $("xSetRows").innerHTML = arr.map(function(x){
    return setRowHTML(x.name||"", x.qty, x.note||"");
  }).join("");
  bindSetRows();
}
function collectSetItems(){
  var out = [];
  $("xSetRows").querySelectorAll(".setrow").forEach(function(r){
    var name = (r.querySelector(".sr-name").value||"").trim();
    if(!name) return;
    var qv = (r.querySelector(".sr-qty").value||"").trim();
    out.push({name:name, qty: qv===""?null:qv, note:(r.querySelector(".sr-note").value||"").trim()});
  });
  return out;
}
function toggleSetSection(on){
  $("xSetWrap").style.display = on ? "" : "none";
}

/* ---- modal ---- */
function fillCategorySelect(cur){
  var sel = $("x_category"); if(!sel) return;
  sel.innerHTML = "";
  if(!cur){
    var o0=document.createElement("option"); o0.value=""; o0.textContent="— wybierz —";
    sel.appendChild(o0);
  }
  var groups = {}, order = [];
  (CATS||[]).forEach(function(c){
    var sec = c.section || "Inne";
    if(!groups[sec]){ groups[sec] = []; order.push(sec); }
    groups[sec].push(c.name);
  });
  order.forEach(function(sec){
    var g = document.createElement("optgroup"); g.label = sec;
    groups[sec].forEach(function(n){
      var o=document.createElement("option"); o.value=n; o.textContent=n;
      if(n===cur) o.selected=true; g.appendChild(o);
    });
    sel.appendChild(g);
  });
  sel.value = cur || "";
}

function selOpts(sel, values, cur){
  sel.innerHTML="";
  (values||[]).forEach(function(v){
    var o=document.createElement("option"); o.value=v; o.textContent=v;
    if(v===cur) o.selected=true; sel.appendChild(o);
  });
}

function openModal(it){
  it = it || {};
  $("xTitle").textContent = it.id ? "Edytuj sprzęt wyprawowy" : "Dodaj sprzęt wyprawowy";
  $("x_id").value = it.id||"";
  fillCategorySelect(it.category || "");
  selOpts($("x_condition"), CONDITIONS, it.condition || (it.id ? "Good" : "New"));
  $("x_brand").value = it.brand||"";
  $("x_model").value = it.model||"";
  $("x_size").value = it.size||"";
  $("x_color").value = it.color||"";
  $("x_weight_g").value = (it.weight_g!=null?it.weight_g:"");
  $("x_qty").value = (it.qty!=null?it.qty:"");
  $("x_purchase_date").value = it.purchase_date||"";
  $("x_purchase_price").value = (it.purchase_price!=null?it.purchase_price:"");
  $("x_ean").value = it.ean||"";
  $("x_sku").value = it.sku||"";
  $("x_notes").value = it.notes||"";
  $("x_url").value = it.url||"";
  // zestaw
  var isSet = !!it.is_set;
  $("x_is_set").checked = isSet;
  var parsed = [];
  try{ parsed = JSON.parse(it.set_items||"[]")||[]; }catch(e){ parsed = []; }
  fillSetRows(parsed);
  toggleSetSection(isSet);
  // zdjecie
  HAD_PHOTO = !!it.photo; SCRAPED_IMG = "";
  var t=$("xThumb");
  if(it.thumb){ t.src=it.thumb; t.style.display=""; } else { t.style.display="none"; t.removeAttribute("src"); }
  $("xPhotoDel").style.display = it.thumb ? "" : "none";
  $("xPhotoLbl").style.display = it.id ? "" : "none";
  $("xPhotoFile").value="";
  $("xPhotoStatus").textContent = it.id ? "" : "zapisz rzecz, potem dodasz zdjęcie";
  $("xUrlStatus").textContent="";
  $("xMeta").textContent = it.id
    ? ("ID "+it.id+" · dodano: "+(qTsLocal(it.created_at,true)||"—")+" · "+(it.active===0?"archiwum":"aktywne"))
    : "nowa pozycja";
  $("xStatus").textContent="";
  $("xDelete").style.display = it.id ? "" : "none";
  $("expedModal").classList.add("open");
  document.body.classList.add("modal-open");
}
function closeModal(){ $("expedModal").classList.remove("open"); document.body.classList.remove("modal-open"); }

function saveModal(){
  var isSet = $("x_is_set").checked;
  var b = {
    id: $("x_id").value||null,
    category: $("x_category").value || CAT,
    condition: $("x_condition").value,
    brand: $("x_brand").value,
    model: $("x_model").value,
    size: $("x_size").value,
    color: $("x_color").value,
    weight_g: $("x_weight_g").value,
    qty: $("x_qty").value,
    purchase_date: $("x_purchase_date").value,
    purchase_price: $("x_purchase_price").value,
    ean: $("x_ean").value,
    sku: $("x_sku").value,
    url: $("x_url").value,
    notes: $("x_notes").value,
    is_set: isSet ? 1 : 0,
    set_items: isSet ? collectSetItems() : null
  };
  if(!b.category){ $("xStatus").textContent="wybierz kategorię"; return; }
  if(!(b.brand||b.model)){ $("xStatus").textContent="podaj markę lub model"; return; }
  $("xStatus").textContent="zapis…";
  postJSON("/api/garage/save", b).then(function(res){
    if(SCRAPED_IMG && res && res.id && !HAD_PHOTO){
      $("xStatus").textContent="zapisano — pobieram zdjęcie ze strony…";
      return postJSON("/api/garage/photo/from-url",{id:Number(res.id), url:SCRAPED_IMG})
        .catch(function(){});
    }
  }).then(function(){ closeModal(); load(); })
    .catch(function(e){ $("xStatus").textContent="błąd zapisu ("+e.message+")"; });
}

function scrapeNow(){
  var u=($("x_url").value||"").trim();
  if(!/^https?:\/\//i.test(u)){ $("xUrlStatus").textContent="podaj adres http(s)"; return; }
  $("xUrlStatus").textContent="zaciąganie (czytam stronę)…";
  postJSON("/api/garage/scrape",{url:u, categories:(CATS||[]).map(function(c){return c.name;})}).then(function(d){
    var f=d.fields||{}, src=d.sources||{};
    var setE=function(id,val){ var e=$(id); if(e && !e.value && val!=null && val!=="") e.value=val; };
    setE("x_brand",f.brand); setE("x_model",f.model); setE("x_color",f.color);
    setE("x_sku",f.sku); setE("x_ean",f.ean); setE("x_weight_g",f.weight_g);
    var cur=(f.currency||"").toUpperCase();
    var plnOk = !cur || cur==="PLN" || cur==="ZŁ";
    if(plnOk) setE("x_purchase_price",f.price);
    SCRAPED_IMG=f.image||"";
    var SRC={struktura:"", llm:" (odczytane)", domena:" (z domeny — sprawdź!)"};
    var tag=function(k){ return SRC[src[k]]||""; };
    var got=[];
    if(f.brand) got.push("marka"+tag("brand"));
    if(f.model) got.push("model"+tag("model"));
    if(f.color) got.push("kolor"+tag("color"));
    if(f.price&&plnOk) got.push("cena"+tag("price"));
    if(f.weight_g) got.push("waga"+tag("weight_g"));
    if(f.sku) got.push("SKU"+tag("sku"));
    if(f.ean) got.push("EAN"+tag("ean"));
    if(f.image) got.push(HAD_PHOTO ? "zdjęcie (masz już własne)" : "zdjęcie produktu (pobiorę przy zapisie)");
    var msg = got.length ? ("zaciągnięto: "+got.join(", ")) : "nic nie odczytałem z tej strony";
    if(f.price&&!plnOk) msg+=" · cena "+f.price+" "+cur+" (inna waluta — nie wpisałem)";
    if(!f.weight_g) msg+=" · wagi brak na stronie — wpisz z metki";
    if(d.js_page) msg+=" · strona ładowana JS (mniej danych)";
    if(d.llm_error) msg+=" · warstwa AI niedostępna";
    $("xUrlStatus").textContent=msg;
  }).catch(function(e){ $("xUrlStatus").textContent="błąd ("+e.message+")"; });
}

function uploadPhoto(){
  var f=$("xPhotoFile").files[0]; if(!f) return;
  var id=$("x_id").value; if(!id){ $("xPhotoStatus").textContent="najpierw zapisz rzecz"; return; }
  var fd=new FormData(); fd.append("id",id); fd.append("file",f); fd.append("entity","gear");
  $("xPhotoStatus").textContent="wysyłanie…";
  fetch("/api/garage/photo",{method:"POST",credentials:"same-origin",body:fd})
    .then(function(r){ if(!r.ok) throw new Error(r.status); return r.json(); })
    .then(function(res){
      var t=$("xThumb"); if(res.thumb){ t.src=res.thumb; t.style.display=""; }
      $("xPhotoDel").style.display=""; $("xPhotoStatus").textContent="zapisano zdjęcie";
      load();
    }).catch(function(e){ $("xPhotoStatus").textContent="błąd zdjęcia ("+e.message+")"; });
}
function deletePhoto(){
  var id=$("x_id").value; if(!id) return;
  postJSON("/api/garage/photo/delete",{id:Number(id), entity:"gear"}).then(function(){
    var t=$("xThumb"); t.style.display="none"; t.removeAttribute("src");
    $("xPhotoDel").style.display="none"; $("xPhotoStatus").textContent="usunięto zdjęcie";
    load();
  }).catch(function(){});
}
function deleteItem(){
  var id=$("x_id").value; if(!id) return;
  if(!window.confirm("Usunąć trwale tę pozycję? Tego nie da się cofnąć.")) return;
  postJSON("/api/garage/delete",{id:Number(id), confirm:true}).then(function(){
    closeModal(); load();
  }).catch(function(e){ $("xStatus").textContent="błąd usuwania ("+e.message+")"; });
}

function toggle(id){
  var it = findIt(id); if(!it || it.id==null) return;
  postJSON("/api/garage/toggle",{id:id, active: it.active?0:1}).then(function(){ load(); }).catch(function(){});
}

document.addEventListener("DOMContentLoaded", function(){
  var tb = $("tabExped"); if(!tb) return;
  tb.addEventListener("click", showExped);
  ["tabGear","tabEquip","tabBike","tabFit"].forEach(function(id){
    var b = $(id); if(b) b.addEventListener("click", hideExped);
  });
  var s = $("xsearch"); if(s) s.addEventListener("input", render);
  var a = $("xadd"); if(a) a.addEventListener("click", function(){ openModal({}); });
  // modal
  var mk=function(id,fn){ var e=$(id); if(e) e.addEventListener("click", fn); };
  mk("xCancel", closeModal); mk("xCancelX", closeModal); mk("xSave", saveModal);
  mk("xScrape", scrapeNow); mk("xDelete", deleteItem); mk("xPhotoDel", deletePhoto);
  var pf=$("xPhotoFile"); if(pf) pf.addEventListener("change", uploadPhoto);
  var setAdd=$("xSetAdd"); if(setAdd) setAdd.addEventListener("click", function(){
    $("xSetRows").insertAdjacentHTML("beforeend", setRowHTML("", null, "")); bindSetRows();
  });
  var chk=$("x_is_set"); if(chk) chk.addEventListener("change", function(){ toggleSetSection(chk.checked); });
});
})();
