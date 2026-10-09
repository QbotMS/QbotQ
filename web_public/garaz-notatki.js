/* garaz-notatki.js (2026-10-09) — zakladka NOTATKI: jedna lista notatek warsztatowych,
   tagi = rowery (bike_notes.bike_ids). Tresc: prosty tekst z formatowaniem
   **pogrubienie**, "- " lista, "| a | b |" tabela, "## " naglowek. Samodzielna zakladka
   (jak garaz-exped.js): sama sie pokazuje i chowa. API: /api/bike-notes/list|save|delete. */
(function(){
"use strict";
var $ = function(id){ return document.getElementById(id); };
var LOADED = false, ITEMS = [], BIKES = [], SEL = new Set();
var OTHER = ["tabGear","tabEquip","tabExped","tabBike","tabFit","tabInstr"];
var ALL = [["tabGear","viewGear","toolbarGear"],["tabEquip","viewEquip","toolbarEquip"],
           ["tabExped","viewExped","toolbarExped"],["tabBike","viewBike","toolbarBike"],
           ["tabFit","viewFit","toolbarFit"],["tabInstr","viewInstr","toolbarInstr"],
           ["tabNotes","viewNotes","toolbarNotes"]];

function showNotes(){
  ALL.forEach(function(t){
    var on = (t[0] === "tabNotes");
    var tb=$(t[0]), vw=$(t[1]), br=$(t[2]);
    if(tb) tb.classList.toggle("on", on);
    if(vw) vw.classList.toggle("on", on);
    if(br) br.style.display = on ? "" : "none";
  });
  if(!LOADED){ LOADED = true; load(); }
}
function hideNotes(){
  var tb=$("tabNotes"), vw=$("viewNotes"), br=$("toolbarNotes");
  if(tb) tb.classList.remove("on");
  if(vw) vw.classList.remove("on");
  if(br) br.style.display = "none";
}

function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]; }); }
function inl(s){ return esc(s).replace(/\*\*(.+?)\*\*/g,"<b>$1</b>"); }
function cells(line){ var t=line.trim(); if(t[0]==="|") t=t.slice(1); if(t.slice(-1)==="|") t=t.slice(0,-1);
  return t.split("|").map(function(x){ return x.trim(); }); }

/* prosty, bezpieczny renderer: najpierw escape, potem znaczniki */
function md(text){
  var L = String(text||"").replace(/\r/g,"").split("\n"), out = [], i = 0;
  while(i < L.length){
    var s = L[i], t = s.trim();
    if(!t){ i++; continue; }
    if(t[0]==="|"){
      var rows=[]; while(i<L.length && L[i].trim()[0]==="|"){ rows.push(L[i]); i++; }
      var h="<table class=\"nt-tab\">";
      rows.forEach(function(r,k){
        var c=cells(r);
        if(c.every(function(x){ return /^:?-{2,}:?$/.test(x); })) return;
        var tag = (k===0) ? "th" : "td";
        h += "<tr>"+c.map(function(x){ return "<"+tag+">"+inl(x)+"</"+tag+">"; }).join("")+"</tr>";
      });
      out.push(h+"</table>"); continue;
    }
    if(/^\s*[-*] /.test(s)){
      var li=[]; while(i<L.length && /^\s*[-*] /.test(L[i])){
        var sub = /^\s{2,}/.test(L[i]);
        li.push("<li"+(sub?" class=\"sub\"":"")+">"+inl(L[i].replace(/^\s*[-*] /,""))+"</li>"); i++; }
      out.push("<ul>"+li.join("")+"</ul>"); continue;
    }
    var m = t.match(/^(#{1,4})\s+(.*)$/);
    if(m){ out.push("<div class=\"nt-h\">"+inl(m[2])+"</div>"); i++; continue; }
    out.push("<p>"+inl(t)+"</p>"); i++;
  }
  return out.join("");
}

function bikeLabel(b){ return b ? (b.nickname || b.name) : "?"; }
function bikeById(id){ for(var k=0;k<BIKES.length;k++) if(BIKES[k].id===id) return BIKES[k]; return null; }
function ids(n){ return String(n.bike_ids||"").split(",").filter(Boolean).map(Number); }
function dd(s){ var m=String(s||"").match(/^(\d{4})-(\d\d)-(\d\d)/); return m ? m[3]+"."+m[2]+"."+m[1] : ""; }

function postJSON(u,b){
  return fetch(u,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(b)}).then(function(r){ if(!r.ok) throw new Error(r.status); return r.json(); });
}
function load(){
  fetch("/api/bike-notes/list?_="+Date.now(),{credentials:"same-origin",cache:"no-store"})
    .then(function(r){ if(!r.ok) throw new Error(r.status); return r.json(); })
    .then(function(d){ ITEMS=d.items||[]; BIKES=d.bikes||[]; fillFilter(); render(); })
    .catch(function(e){ $("notesBody").innerHTML="<div class=\"empty\">błąd ładowania ("+esc(e.message)+")</div>"; });
}
function fillFilter(){
  var f=$("nfilterBike"), cur=f.value;
  f.innerHTML="<option value=\"\">wszystkie rowery</option><option value=\"0\">ogólne (bez roweru)</option>"+
    BIKES.filter(function(b){ return b.active; })
      .map(function(b){ return "<option value=\""+b.id+"\">"+esc(bikeLabel(b))+"</option>"; }).join("");
  f.value=cur;
}
function render(){
  var body=$("notesBody"), q=($("nsearch").value||"").trim().toLowerCase(), fb=$("nfilterBike").value;
  var list=ITEMS.filter(function(n){
    var I=ids(n);
    if(fb==="0" && I.length) return false;
    if(fb && fb!=="0" && I.indexOf(Number(fb))<0) return false;
    if(q && ((n.title||"")+" "+(n.body||"")).toLowerCase().indexOf(q)<0) return false;
    return true;
  });
  $("ncount").textContent = ITEMS.length ? (list.length===ITEMS.length ? ITEMS.length+" szt." : list.length+" / "+ITEMS.length+" szt.") : "";
  if(!list.length){ body.innerHTML="<div class=\"empty\">"+(ITEMS.length?"Brak notatek dla tego filtra.":"Pusto. Dodaj pierwszą notatkę przyciskiem „+ Dodaj notatkę”.")+"</div>"; return; }
  body.innerHTML = list.map(function(n){
    var I=ids(n);
    var tags = I.length ? I.map(function(id){ return "<span class=\"nt-tag\">"+esc(bikeLabel(bikeById(id)))+"</span>"; }).join("")
                        : "<span class=\"nt-tag gen\">ogólna</span>";
    return "<div class=\"nt-card\" data-id=\""+n.id+"\"><div class=\"nt-head\"><div class=\"nt-t\">"+esc(n.title)+"</div>"+
      "<div class=\"nt-tags\">"+tags+"</div><span class=\"nt-d\">"+dd(n.updated_at)+"</span>"+
      "<button type=\"button\" class=\"btn sec nt-ed\">Edytuj</button></div>"+
      "<div class=\"nt-body\">"+md(n.body)+"</div></div>";
  }).join("");
  Array.prototype.forEach.call(body.querySelectorAll(".nt-ed"),function(b){
    b.addEventListener("click",function(){
      var id=Number(b.closest(".nt-card").dataset.id);
      openModal(ITEMS.filter(function(n){ return n.id===id; })[0]);
    });
  });
}

/* ---------- okno ---------- */
function paintBikes(){
  var box=$("n_bikes"); box.innerHTML="";
  BIKES.forEach(function(b){
    if(!b.active && !SEL.has(b.id)) return;
    var x=document.createElement("button"); x.type="button"; x.textContent=bikeLabel(b);
    x.classList.toggle("on", SEL.has(b.id));
    x.addEventListener("click",function(){ if(SEL.has(b.id)) SEL.delete(b.id); else SEL.add(b.id); paintBikes(); });
    box.appendChild(x);
  });
}
function openModal(n){
  n=n||{};
  $("nTitle").textContent = n.id ? "Edytuj notatkę" : "Dodaj notatkę";
  $("n_id").value=n.id||""; $("n_title").value=n.title||""; $("n_body").value=n.body||"";
  SEL=new Set(ids(n)); paintBikes();
  $("nMeta").textContent = n.id ? ("ID "+n.id+" · dodano "+dd(n.created_at)+" · zmieniono "+dd(n.updated_at)) : "nowa notatka · bez wybranego roweru = ogólna";
  var del=$("nDelete"); del.style.display=n.id?"":"none"; del.textContent="Usuń"; del.dataset.armed=""; del.classList.remove("armed");
  $("nStatus").textContent="";
  $("notesModal").classList.add("open"); document.body.classList.add("modal-open");
  setTimeout(function(){ $("n_title").focus(); },50);
}
function closeModal(){ $("notesModal").classList.remove("open"); document.body.classList.remove("modal-open"); }
function save(){
  var b={id:$("n_id").value||null, title:$("n_title").value, body:$("n_body").value, bike_ids:Array.from(SEL)};
  if(!b.title.trim()){ $("nStatus").textContent="wpisz tytuł"; return; }
  $("nStatus").textContent="zapis…";
  postJSON("/api/bike-notes/save",b).then(function(){ closeModal(); load(); })
    .catch(function(e){ $("nStatus").textContent="błąd zapisu ("+e.message+")"; });
}
function del(){
  var id=$("n_id").value; if(!id) return;
  var b=$("nDelete"), st=$("nStatus");
  if(b.dataset.armed!=="1"){
    b.dataset.armed="1"; b.classList.add("armed"); b.textContent="Potwierdź usunięcie";
    st.textContent="usunięcie jest nieodwracalne — kliknij ponownie";
    setTimeout(function(){ if(b.dataset.armed==="1"){ b.dataset.armed=""; b.classList.remove("armed"); b.textContent="Usuń"; st.textContent=""; } },6000);
    return;
  }
  postJSON("/api/bike-notes/delete",{id:Number(id),confirm:true}).then(function(){ closeModal(); load(); })
    .catch(function(e){ st.textContent="błąd usuwania ("+e.message+")"; });
}

document.addEventListener("DOMContentLoaded",function(){
  var tb=$("tabNotes"); if(!tb) return;
  tb.addEventListener("click", showNotes);
  OTHER.forEach(function(id){ var b=$(id); if(b) b.addEventListener("click", hideNotes); });
  $("nsearch").addEventListener("input", render);
  $("nfilterBike").addEventListener("change", render);
  $("nadd").addEventListener("click", function(){ openModal(null); });
  $("nSave").addEventListener("click", save);
  $("nCancel").addEventListener("click", closeModal);
  $("nCancelX").addEventListener("click", closeModal);
  $("nDelete").addEventListener("click", del);
});
})();
