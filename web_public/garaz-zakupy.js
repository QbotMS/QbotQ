/* garaz-zakupy.js (2026-10-13) — zakladka ZAKUPY: lista "Do kupienia" (priorytet) + "Kupione".
   Samodzielna zakladka (jak garaz-notatki.js): sama sie pokazuje i chowa.
   API: /api/zakupy/list|save|bought|unbought|delete; dane z linku: /api/garage/scrape (te same co reszta Garazu).
   Po "Kupione" przy rzeczy rowerowej: propozycja dodania do Garazu — otwiera ISTNIEJACE okno
   (Odziez / Sprzet / komponent Roweru) z linkiem, cena i data, i odpala tam "Zaciagnij dane".
   Etap 2 (2026-10-13): zapas rzeczy zuzywalnych (opakowanie + zuzycie dzienne albo powiazanie z Zdrowie > Suplementy),
   pasek zapasu, "Konczy sie", przyciski Kup ponownie (/rebuy) i +7 dni (/snooze). Dok.: docs/ZAKUPY.md */
(function(){
"use strict";
var $ = function(id){ return document.getElementById(id); };
var LOADED = false, D = {items:[], categories:[], priorities:[], bikes:[]}, PRIO = 2, BUY = null;
var OTHER = ["tabGear","tabEquip","tabExped","tabBike","tabFit","tabInstr","tabNotes"];
var ALL = [["tabGear","viewGear","toolbarGear"],["tabEquip","viewEquip","toolbarEquip"],
           ["tabExped","viewExped","toolbarExped"],["tabBike","viewBike","toolbarBike"],
           ["tabFit","viewFit","toolbarFit"],["tabInstr","viewInstr","toolbarInstr"],
           ["tabNotes","viewNotes","toolbarNotes"],["tabZakupy","viewZakupy","toolbarZakupy"]];
var TARGET_LBL = {gear:"Odzież", equip:"Sprzęt", bike:"Rower (komponent)"};

function show(){
  ALL.forEach(function(t){
    var on = (t[0] === "tabZakupy");
    var tb=$(t[0]), vw=$(t[1]), br=$(t[2]);
    if(tb) tb.classList.toggle("on", on);
    if(vw) vw.classList.toggle("on", on);
    if(br) br.style.display = on ? "" : "none";
  });
  if(!LOADED){ LOADED = true; load(); }
}
function hide(){
  var tb=$("tabZakupy"), vw=$("viewZakupy"), br=$("toolbarZakupy");
  if(tb) tb.classList.remove("on");
  if(vw) vw.classList.remove("on");
  if(br) br.style.display = "none";
}

function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]; }); }
function dd(s){ var m=String(s||"").match(/^(\d{4})-(\d\d)-(\d\d)/); return m ? m[3]+"."+m[2]+"."+m[1] : ""; }
function today(){ var d=new Date(), p=function(n){ return ("0"+n).slice(-2); };
  return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate()); }
function money(v, cur){ if(v==null) return ""; var n=Number(v);
  var s=(Math.round(n*100)%100===0) ? String(Math.round(n)) : n.toFixed(2).replace(".",",");
  return s+" "+((!cur||cur==="PLN")?"zł":cur); }
function bikeLabel(id){ for(var i=0;i<D.bikes.length;i++) if(D.bikes[i].id===id) return D.bikes[i].nickname||D.bikes[i].name; return ""; }

function postJSON(u,b){
  return fetch(u,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(b)}).then(function(r){
      return r.json().catch(function(){ return {}; }).then(function(j){
        if(!r.ok) throw new Error(j.detail || r.status); return j; }); });
}
function load(){
  fetch("/api/zakupy/list?_="+Date.now(),{credentials:"same-origin",cache:"no-store"})
    .then(function(r){ if(!r.ok) throw new Error(r.status); return r.json(); })
    .then(function(d){ D=d; render(); })
    .catch(function(e){ $("zakupyBody").innerHTML="<div class=\"empty\">błąd ładowania ("+esc(e.message)+")</div>"; });
}

function filtered(){
  var q=($("zsearch").value||"").trim().toLowerCase(), g=$("zfilterGroup").value;
  return (D.items||[]).filter(function(it){
    if(g && String(it.category).indexOf(g)!==0) return false;
    if(q){ var h=[it.name,it.brand,it.shop,it.notes,it.category].join(" ").toLowerCase(); if(h.indexOf(q)<0) return false; }
    return true;
  });
}

function nfmt(x){ return String(Math.round(Number(x)*10)/10).replace(".",","); }
function stockLine(it){
  var f=it.forecast; if(!f) return "";
  var s="zostało ok. "+nfmt(f.remaining)+" z "+nfmt(f.pack)+" "+esc(f.unit);
  if(f.days_left!=null) s+=" · starczy do "+dd(f.end)+" ("+f.days_left+" dni)"; else s+=" · brak zużycia (suplement wyłączony?)";
  if(it.supplement_id){ var n=""; (D.supplements||[]).forEach(function(x){ if(x.id===it.supplement_id) n=x.name; });
    s+=" · wg Zdrowie → Suplementy"+(n?" ("+esc(n)+")":""); }
  if(it.snooze_until && it.snooze_until>today()) s+=" · przypomnienie od "+dd(it.snooze_until);
  if(it.refill_id) s+=" · dokupienie na liście";
  return s;
}
function stockHtml(it){
  var f=it.forecast; if(!f || it.status!=="bought") return "";
  var p=Math.max(0,Math.min(100,Math.round((f.pct||0)*100)));
  return "<div class=\"zk-stock\"><div class=\"zk-bar\"><i style=\"width:"+p+"%\""+(it.due?" class=\"low\"":"")+"></i></div>"+
    "<span>"+stockLine(it)+"</span></div>";
}
function rowHtml(it){
  var img = it.thumb ? "<img class=\"zk-ph\" src=\""+it.thumb+"\" alt=\"\">" : "<div class=\"zk-ph zk-noph\">&#128722;</div>";
  var title = (it.brand ? "<span class=\"zk-br\">"+esc(it.brand)+"</span> " : "")+esc(it.name);
  var meta = ["<span class=\"chip-q t\">"+esc(it.category)+"</span>"];
  if(it.bike_id) meta.push("<span class=\"chip-q\">"+esc(bikeLabel(it.bike_id))+"</span>");
  if(it.shop) meta.push(it.url ? "<a href=\""+esc(it.url)+"\" target=\"_blank\" rel=\"noopener\">"+esc(it.shop)+" &#8599;</a>" : esc(it.shop));
  if(it.qty>1) meta.push(it.qty+" szt.");
  if(it.status==="planned" && it.refill_of) meta.push("<span class=\"chip-q w\">dokupienie</span>");
  if(it.notes) meta.push("<span class=\"zk-note\">"+esc(it.notes.slice(0,80))+"</span>");
  var stock = stockHtml(it);
  var right, acts;
  if(it.status==="planned"){
    right = "<div class=\"zk-pr\">"+(it.price!=null ? money(it.price,it.currency) : "—")+"</div>"+
            (it.price_at ? "<div class=\"zk-sub\">cena z "+dd(it.price_at)+"</div>" : "");
    acts = "<button type=\"button\" class=\"btn\" data-a=\"buy\">Kupione</button>"+
           "<button type=\"button\" class=\"btn sec\" data-a=\"edit\">Edytuj</button>";
  } else {
    right = "<div class=\"zk-pr\">"+(it.paid_price!=null ? money(it.paid_price,it.currency) : "—")+"</div>"+
            "<div class=\"zk-sub\">kupione "+dd(it.bought_at)+"</div>";
    acts = (it.due ? "<button type=\"button\" class=\"btn\" data-a=\"rebuy\">Kup ponownie</button>"+
                     "<button type=\"button\" class=\"btn sec\" data-a=\"snooze\" title=\"Przypomnij za 7 dni\">+7 dni</button>"
           : (it.pack_units && !it.refill_id ? "<button type=\"button\" class=\"btn sec\" data-a=\"rebuy\">Kup ponownie</button>" : ""))+
           (it.garage_target ? "<button type=\"button\" class=\"btn sec\" data-a=\"garage\">Do Garażu</button>" : "")+
           "<button type=\"button\" class=\"btn sec\" data-a=\"back\" title=\"Wróć na listę do kupienia\">Cofnij</button>";
  }
  var pr = it.status==="planned" ? "<span class=\"prio p"+it.priority+"\">"+esc(it.priority_label)+"</span>" : "";
  if(it.due) pr = "<span class=\"prio p1\">Kończy się</span>";
  return "<div class=\"zk-row"+(it.status==="bought"?" done":"")+(it.due?" due":"")+"\" data-id=\""+it.id+"\">"+img+
    "<div class=\"zk-main\"><div class=\"zk-t\">"+pr+title+"</div><div class=\"zk-m\">"+meta.join(" · ")+"</div>"+stock+"</div>"+
    "<div class=\"zk-right\">"+right+"</div><div class=\"zk-act\">"+acts+"</div></div>";
}

function render(){
  var items=filtered(), plan=items.filter(function(x){ return x.status==="planned"; }),
      done=items.filter(function(x){ return x.status==="bought"; });
  var sum=0, nosum=0; plan.forEach(function(x){ if(x.price!=null && (!x.currency||x.currency==="PLN")) sum+=x.price*x.qty; else nosum++; });
  $("zcount").textContent = plan.length+" do kupienia"+(plan.length ? " · razem ok. "+money(sum,"PLN")+(nosum?" (+"+nosum+" bez ceny)":"") : "");
  var h = "<div class=\"secttl\">Do kupienia</div>";
  h += plan.length ? plan.map(rowHtml).join("") : "<div class=\"empty\">Lista pusta — dodaj coś przyciskiem „+ Dodaj do listy”.</div>";
  h += "<div class=\"secttl\">Kupione</div>";
  h += done.length ? done.map(rowHtml).join("") : "<div class=\"empty\">Nic jeszcze nie kupione.</div>";
  var body=$("zakupyBody"); body.innerHTML=h;
  body.querySelectorAll(".zk-row").forEach(function(r){
    var it=byId(Number(r.dataset.id));
    r.querySelectorAll("button[data-a]").forEach(function(b){
      b.addEventListener("click",function(e){ e.stopPropagation(); act(b.dataset.a, it); });
    });
    r.addEventListener("click",function(e){ if(e.target.closest("a")) return; openModal(it); });
  });
}
function byId(id){ for(var i=0;i<D.items.length;i++) if(D.items[i].id===id) return D.items[i]; return null; }

function act(a, it){
  if(a==="edit") openModal(it);
  else if(a==="buy") openBuy(it);
  else if(a==="garage") toGarage(it);
  else if(a==="rebuy") postJSON("/api/zakupy/rebuy",{id:it.id}).then(load).catch(function(e){ alert("Błąd: "+e.message); });
  else if(a==="snooze") postJSON("/api/zakupy/snooze",{id:it.id, days:7}).then(load).catch(function(e){ alert("Błąd: "+e.message); });
  else if(a==="back") postJSON("/api/zakupy/unbought",{id:it.id}).then(load).catch(function(e){ alert("Błąd: "+e.message); });
}

/* ---------- okno dodaj / edytuj ---------- */
function fillSelects(){
  var c=$("z_category"); c.innerHTML="<option value=\"\">— wybierz —</option>"+
    (D.categories||[]).map(function(x){ return "<option>"+esc(x)+"</option>"; }).join("");
  var b=$("z_bike_id"); b.innerHTML="<option value=\"\">— żaden —</option>"+
    (D.bikes||[]).map(function(x){ return "<option value=\""+x.id+"\">"+esc(x.nickname||x.name)+"</option>"; }).join("");
}
function fillSupl(){
  var s=$("z_supplement_id"); s.innerHTML="<option value=\"\">— wybierz suplement —</option>"+
    (D.supplements||[]).map(function(x){ return "<option value=\""+x.id+"\">"+esc(x.name)+(x.active?"":" (wyłączony)")+"</option>"; }).join("");
}
function syncMode(){ var supl=$("z_mode_supl").checked;
  $("z_perday_box").style.display=supl?"none":""; $("z_supl_box").style.display=supl?"":"none";
  $("z_perintake_box").style.display=supl?"":"none"; }
function paintPrio(){ document.querySelectorAll("#z_priority button").forEach(function(b){ b.classList.toggle("on", Number(b.dataset.v)===PRIO); }); }
function syncBike(){ $("z_bike_box").style.display = ($("z_category").value==="Rower / części") ? "" : "none"; }
function setImg(url){
  var t=$("zThumb"); $("z_image_url").value=url||"";
  if(url){ t.src=url; t.style.display=""; } else { t.removeAttribute("src"); t.style.display="none"; }
}
function openModal(it){
  it=it||{}; fillSelects();
  $("zTitle").textContent = it.id ? "Edytuj pozycję" : "Dodaj do listy zakupów";
  $("z_id").value=it.id||"";
  $("z_url").value=it.url||""; $("z_name").value=it.name||""; $("z_brand").value=it.brand||"";
  $("z_category").value=it.category||""; $("z_qty").value=it.qty||1;
  $("z_price").value=(it.price!=null?it.price:""); $("z_currency").value=it.currency||"";
  $("z_bike_id").value=it.bike_id||""; $("z_notes").value=it.notes||"";
  PRIO=it.priority||2; paintPrio(); syncBike();
  fillSupl();
  $("z_pack_units").value=(it.pack_units!=null?it.pack_units:""); $("z_pack_unit").value=it.pack_unit||"";
  $("z_per_day").value=(it.per_day!=null?it.per_day:""); $("z_per_intake").value=(it.per_intake!=null?it.per_intake:"");
  $("z_supplement_id").value=it.supplement_id||""; $("z_lead_days").value=it.lead_days||"";
  $("z_lead_days").placeholder=String(D.lead_days||10);
  $("z_mode_supl").checked=!!it.supplement_id; $("z_mode_day").checked=!it.supplement_id; syncMode();
  $("z_opened_box").style.display=(it.status==="bought")?"":"none";
  $("z_opened_at").value=(it.status==="bought" ? (it.opened_at||it.bought_at||"") : "");
  $("zStockInfo").innerHTML = it.forecast ? stockLine(it) : "";
  setImg(it.image_url||""); if(it.thumb && !it.image_url){ $("zThumb").src=it.thumb; $("zThumb").style.display=""; }
  $("zUrlStatus").textContent = it.id ? "" : "Wklej link do produktu i kliknij „Pobierz dane” — QBot sam uzupełni pola.";
  $("zStatus").textContent="";
  var del=$("zDelete"); del.style.display=it.id?"":"none"; del.textContent="Usuń"; del.dataset.armed="";
  $("zakupyModal").classList.add("open"); document.body.classList.add("modal-open");
  setTimeout(function(){ (it.id ? $("z_name") : $("z_url")).focus(); }, 30);
}
function closeModal(){ $("zakupyModal").classList.remove("open"); document.body.classList.remove("modal-open"); }

function scrape(){
  var u=$("z_url").value.trim();
  if(!/^https?:\/\//i.test(u)){ $("zUrlStatus").textContent="podaj adres zaczynający się od http(s)://"; return; }
  $("zUrlStatus").textContent="czytam stronę produktu… (kilka sekund)"; $("zScrape").disabled=true;
  postJSON("/api/garage/scrape",{url:u, categories:D.categories}).then(function(d){
    var f=d.fields||{}, got=[];
    function setE(id,v){ if(v!==null && v!==undefined && v!=="" && !$(id).value){ $(id).value=v; return true; } return false; }
    if(d.url && d.url!==u) $("z_url").value=d.url;
    if(setE("z_name", f.model)) got.push("nazwa");
    if(setE("z_brand", f.brand)) got.push("marka");
    if(f.category && !$("z_category").value){ $("z_category").value=f.category; if($("z_category").value) got.push("kategoria"); syncBike(); }
    if(f.price && !$("z_price").value){ $("z_price").value=f.price; $("z_currency").value=(f.currency||"PLN").toUpperCase(); got.push("cena"); }
    if(f.image && !$("z_image_url").value){ setImg(f.image); got.push("zdjęcie"); }
    var msg = got.length ? "pobrano: "+got.join(", ") : "nic nowego nie odczytałem z tej strony — uzupełnij ręcznie";
    if(f.currency && String(f.currency).toUpperCase()!=="PLN") msg+=" · cena w "+f.currency;
    if(d.js_page) msg+=" · strona ładowana skryptami (mniej danych)";
    if(d.llm_error) msg+=" · warstwa AI niedostępna";
    $("zUrlStatus").textContent=msg;
  }).catch(function(e){ $("zUrlStatus").textContent="nie udało się pobrać strony ("+e.message+")"; })
    .then(function(){ $("zScrape").disabled=false; });
}

function save(){
  var b={ id:$("z_id").value||null, url:$("z_url").value, name:$("z_name").value, brand:$("z_brand").value,
    category:$("z_category").value, priority:PRIO, qty:$("z_qty").value, price:$("z_price").value,
    currency:$("z_currency").value, image_url:$("z_image_url").value,
    bike_id:($("z_category").value==="Rower / części" ? $("z_bike_id").value : null), notes:$("z_notes").value,
    pack_units:$("z_pack_units").value, pack_unit:$("z_pack_unit").value, lead_days:$("z_lead_days").value,
    supplement_id:($("z_mode_supl").checked ? $("z_supplement_id").value : null),
    per_intake:($("z_mode_supl").checked ? $("z_per_intake").value : null),
    per_day:($("z_mode_supl").checked ? null : $("z_per_day").value) };
  if($("z_opened_box").style.display!=="none") b.opened_at=$("z_opened_at").value;
  if($("z_mode_supl").checked && b.pack_units && !b.supplement_id){ $("zStatus").textContent="wybierz suplement albo przełącz na zużycie dzienne"; return; }
  if(!b.name.trim()){ $("zStatus").textContent="podaj nazwę"; return; }
  if(!b.category){ $("zStatus").textContent="wybierz kategorię"; return; }
  $("zStatus").textContent="zapis…";
  postJSON("/api/zakupy/save", b).then(function(){ closeModal(); load(); })
    .catch(function(e){ $("zStatus").textContent="błąd: "+e.message; });
}
function del(){
  var bt=$("zDelete");
  if(!bt.dataset.armed){ bt.dataset.armed="1"; bt.textContent="Na pewno usunąć?"; return; }
  postJSON("/api/zakupy/delete",{id:Number($("z_id").value)}).then(function(){ closeModal(); load(); })
    .catch(function(e){ $("zStatus").textContent="błąd: "+e.message; });
}

/* ---------- Kupione ---------- */
function openBuy(it){
  BUY=it;
  $("zbName").textContent=(it.brand?it.brand+" ":"")+it.name;
  $("zb_price").value=(it.price!=null?it.price:""); $("zb_date").value=today();
  $("zbStep1").style.display=""; $("zbStep2").style.display="none"; $("zbStatus").textContent="";
  $("zbOk").style.display=""; $("zbCancel").textContent="Anuluj";
  $("zakupyBuyModal").classList.add("open"); document.body.classList.add("modal-open");
}
function closeBuy(){ $("zakupyBuyModal").classList.remove("open"); document.body.classList.remove("modal-open"); }
function confirmBuy(){
  $("zbStatus").textContent="zapis…";
  postJSON("/api/zakupy/bought",{id:BUY.id, paid_price:$("zb_price").value, bought_at:$("zb_date").value})
    .then(function(d){
      BUY=d.item; load();
      if(BUY.garage_target){
        $("zbStep1").style.display="none"; $("zbStep2").style.display="";
        $("zbTarget").textContent=TARGET_LBL[BUY.garage_target]||"";
        $("zbOk").style.display="none"; $("zbCancel").textContent="Nie teraz"; $("zbStatus").textContent="";
      } else closeBuy();
    }).catch(function(e){ $("zbStatus").textContent="błąd: "+e.message; });
}

/* ---------- Do Garazu: istniejace okno z wypelnionymi danymi ---------- */
function waitFor(cond, ms){
  return new Promise(function(res){ var t0=Date.now(); (function tick(){
    var ok=false; try{ ok=cond(); }catch(e){}
    if(ok || Date.now()-t0>ms) return res(ok); setTimeout(tick, 120); })(); });
}
function setV(id, v){ var e=$(id); if(e && v!==null && v!==undefined && v!=="") e.value=v; }
function toGarage(it){
  closeBuy();
  var T={gear:{tab:"tabGear", add:"gadd", p:"m_", scr:"mScrape", ready:function(){ return $("m_category").options.length>0 || !/ładowanie/.test($("garageBody").textContent); }},
         equip:{tab:"tabEquip", add:"eadd", p:"e_", scr:"eScrape", ready:function(){ return !/ładowanie/.test($("equipBody").textContent); }},
         bike:{tab:"tabBike", add:"badd", p:"c_", scr:"cScrape", ready:function(){ return !/ładowanie/.test($("bikeBody").textContent); }}}[it.garage_target];
  if(!T) return;
  $(T.tab).click();
  waitFor(T.ready, 8000).then(function(){
    $(T.add).click();
    var p=T.p;
    setV(p+"url", it.url); setV(p+"brand", it.brand); setV(p+"model", it.name);
    setV(p+"purchase_price", it.paid_price!=null ? it.paid_price : it.price);
    setV(p+"purchase_date", it.bought_at);
    if(it.garage_target==="bike" && it.bike_id) setV("c_bike_id", String(it.bike_id));
    if(it.url && $(T.scr)) $(T.scr).click();
  });
}

document.addEventListener("DOMContentLoaded",function(){
  var tb=$("tabZakupy"); if(!tb) return;
  tb.addEventListener("click", show);
  OTHER.forEach(function(id){ var b=$(id); if(b) b.addEventListener("click", hide); });
  $("zsearch").addEventListener("input", render);
  $("zfilterGroup").addEventListener("change", render);
  $("zadd").addEventListener("click", function(){ openModal(null); });
  $("zScrape").addEventListener("click", scrape);
  $("z_url").addEventListener("keydown", function(e){ if(e.key==="Enter"){ e.preventDefault(); scrape(); } });
  $("z_category").addEventListener("change", syncBike);
  $("z_mode_day").addEventListener("change", syncMode);
  $("z_mode_supl").addEventListener("change", syncMode);
  document.querySelectorAll("#z_priority button").forEach(function(b){
    b.addEventListener("click", function(){ PRIO=Number(b.dataset.v); paintPrio(); }); });
  $("zSave").addEventListener("click", save);
  $("zCancel").addEventListener("click", closeModal);
  $("zCancelX").addEventListener("click", closeModal);
  $("zDelete").addEventListener("click", del);
  $("zImgClr").addEventListener("click", function(){ setImg(""); });
  $("zbOk").addEventListener("click", confirmBuy);
  $("zbCancel").addEventListener("click", closeBuy);
  $("zbX").addEventListener("click", closeBuy);
  $("zbGarage").addEventListener("click", function(){ toGarage(BUY); });
  /* #zakupy w adresie: po starcie (garaz-search.js na starcie klika zakladke Rower) */
  window.addEventListener("load", function(){ if(/[#&]zakupy\b/.test(location.hash)) setTimeout(show, 0); });
});
})();
