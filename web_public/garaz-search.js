/* garaz-search.js (2026-10-01) — jedna wyszukiwarka w pasku zakladek dla WSZYSTKICH zakladek.
   Kazda zakladka ma wlasne pole (gsearch/esearch/xsearch/bsearch/isearch) obslugiwane przez jej skrypt;
   tu tylko pokazujemy pole aktywnej zakladki. Obserwator klasy "on" na przyciskach zakladek dziala
   PO kodzie przelaczania (mikrozadanie), wiec wygrywa z dawnymi ukrywaczami pola. Fitting: bez pola. */
(function(){
"use strict";
var MAP = {tabBike:"bsearch", tabGear:"gsearch", tabEquip:"esearch", tabExped:"xsearch", tabInstr:"isearch", tabFit:null};
function sync(){
  var box = document.getElementById("tabSearch"); if(!box) return;
  var act = null;
  Object.keys(MAP).forEach(function(t){ var b = document.getElementById(t); if(b && b.classList.contains("on")) act = t; });
  Object.keys(MAP).forEach(function(t){ var id = MAP[t]; if(!id) return;
    var i = document.getElementById(id); if(i) i.style.display = (t === act) ? "" : "none"; });
  box.style.visibility = (act && MAP[act]) ? "visible" : "hidden";
}
function init(){
  var mo = new MutationObserver(sync);
  Object.keys(MAP).forEach(function(t){ var b = document.getElementById(t);
    if(b) mo.observe(b, {attributes:true, attributeFilter:["class"]}); });
  var bike = document.getElementById("tabBike");
  if(bike) bike.click();          // Rower = pierwsza zakladka, otwierana na starcie
  sync();
}
if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
