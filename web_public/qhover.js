/* qhover.js (2026-10-16) - wspolny, natychmiastowy dymek dla WSZYSTKICH wykresow SVG w QBot Lab.
   Regula: kazdy wykres ma byc interaktywny. Elementy SVG z <title> (slupki, kropki, pasy stref) dostaja:
   dymek przy kursorze (zamiast wolnej natywnej podpowiedzi), podswietlenie elementu, obsluge dotyku (tap = dymek).
   Laduje go nav.js na kazdej stronie. Wykresy z wlasnym dymkiem (np. Bilans, Obciazenie i forma) nie maja <title> - bez konfliktu.
   Dokumentacja: docs/FORMA_UI_LAYOUT.md (sekcja Wykresy). */
(function () {
  "use strict";
  if (window.__qhover) return; window.__qhover = 1;
  var tip = null, cur = null;
  function ensure() {
    if (tip) return tip;
    tip = document.createElement("div"); tip.className = "qhover-tip"; tip.setAttribute("role", "tooltip");
    tip.style.cssText = "position:fixed;z-index:9999;display:none;max-width:320px;pointer-events:none;background:var(--card,#1b1f27);color:var(--ink,#e8eaed);" +
      "border:1px solid var(--line,#3a3f4b);border-radius:8px;padding:6px 9px;font:12.5px/1.45 system-ui,sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.28);white-space:pre-line";
    document.body.appendChild(tip); return tip;
  }
  function target(el) {
    for (var x = el; x && x.nodeType === 1 && x.tagName !== "svg" && x.tagName !== "SVG"; x = x.parentNode) {
      var t = x.querySelector && x.querySelector(":scope > title");   /* swiezy <title> (wykres przerysowany) ma pierwszenstwo */
      if (t) { x.__qtip = t.textContent; t.remove(); return x; }
      if (x.__qtip != null) return x;
    }
    return null;
  }
  function inSvg(el) { return el && el.closest && el.closest("svg"); }
  function place(ev) {
    var t = ensure(), w = t.offsetWidth || 200, h = t.offsetHeight || 40, x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + w > window.innerWidth - 6) x = ev.clientX - w - 14;
    if (y + h > window.innerHeight - 6) y = ev.clientY - h - 14;
    t.style.left = Math.max(4, x) + "px"; t.style.top = Math.max(4, y) + "px";
  }
  function show(el, ev) {
    if (cur && cur !== el) hide();
    cur = el; var t = ensure(); t.textContent = el.__qtip; t.style.display = "block"; place(ev);
    if (el.__qop == null) { el.__qop = el.getAttribute("opacity"); el.__qsw = el.getAttribute("stroke-width"); }
    var tag = el.tagName.toLowerCase();
    if (tag === "circle") el.setAttribute("stroke-width", String((+el.__qsw || 1) + 1.5));
    else if (tag === "rect" || tag === "path") el.style.filter = "brightness(1.35)";
  }
  function hide() {
    if (tip) tip.style.display = "none";
    if (cur) { cur.style.filter = ""; if (cur.__qsw != null) cur.setAttribute("stroke-width", cur.__qsw); else cur.removeAttribute("stroke-width"); cur = null; }
  }
  document.addEventListener("mouseover", function (ev) { if (!inSvg(ev.target)) return; var el = target(ev.target); if (el) show(el, ev); else if (cur) hide(); }, true);
  document.addEventListener("mousemove", function (ev) { if (cur && tip && tip.style.display === "block") place(ev); }, true);
  document.addEventListener("mouseout", function (ev) { if (cur && (!ev.relatedTarget || !cur.contains(ev.relatedTarget))) hide(); }, true);
  document.addEventListener("touchstart", function (ev) { var p = ev.touches && ev.touches[0]; if (!p || !inSvg(ev.target)) { hide(); return; }
    var el = target(ev.target); if (el) show(el, p); else hide(); }, { passive: true, capture: true });
  window.addEventListener("scroll", hide, true);
})();
