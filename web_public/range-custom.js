/* range-custom.js (2026-10-13) — "własny" zakres dat obok predefiniowanych okresów (30 dni / 90 dni / rok…).
   Użycie: qRangeCustom(segEl, {cls:"on", init:()=>[odISO,doISO], active:bool, onApply:(a,b)=>{...}})
   - dokłada do grupy przycisk "własny…" i (po kliknięciu) pola od/do + "Pokaż";
   - kliknięcie gotowego okresu chowa pola (logikę okresów obsługuje strona);
   - po "Pokaż" zaznacza "własny" i woła onApply(a,b) z datami RRRR-MM-DD (a <= b).
   Używane: Forma (Trendy, Sezon), Zdrowie (Serce). Jedzenie i ModelQ mają własne pola od/do. */
(function () {
  "use strict";
  function iso(d) { var p = function (n) { return ("0" + n).slice(-2); }; return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()); }
  window.qRangeCustom = function (seg, o) {
    if (!seg || seg._qrc) return null;
    o = o || {};
    seg._qrc = 1;
    var cls = o.cls || "on";
    var btn = document.createElement("button");
    btn.type = "button"; btn.textContent = "własny…"; btn.title = "Własny zakres dat";
    btn.className = "qrc-btn";
    seg.appendChild(btn);
    var box = document.createElement("span");
    box.className = "qrc";
    box.style.cssText = "display:none;align-items:center;gap:6px;flex-wrap:wrap;margin:4px 0 4px 8px;font-size:13px;color:var(--ink2)";
    var inp = "padding:3px 6px;border:1px solid var(--line);border-radius:7px;background:var(--card,transparent);color:var(--ink);font:inherit;font-size:13px";
    box.innerHTML = 'od <input type="date" class="qrc-a" style="' + inp + '"> do <input type="date" class="qrc-b" style="' + inp + '">' +
      ' <button type="button" class="btn qrc-go" style="font-size:12.5px;padding:3px 10px">Pokaż</button><span class="qrc-msg" style="color:var(--bad)"></span>';
    seg.parentNode.insertBefore(box, seg.nextSibling);
    var A = box.querySelector(".qrc-a"), B = box.querySelector(".qrc-b"), M = box.querySelector(".qrc-msg");
    A.max = B.max = iso(new Date());
    function open() {
      var v = o.init ? (o.init() || []) : [];
      if (!A.value && v[0]) A.value = v[0];
      if (!B.value && v[1]) B.value = v[1];
      box.style.display = "inline-flex"; M.textContent = "";
    }
    btn.addEventListener("click", function () { open(); A.focus(); });
    seg.addEventListener("click", function (e) {
      var t = e.target.closest ? e.target.closest("button") : e.target;
      if (t && t !== btn && t.parentNode === seg) { box.style.display = "none"; btn.classList.remove(cls); }
    });
    function go() {
      var a = A.value, b = B.value || iso(new Date());
      if (!a) { M.textContent = "podaj datę początku"; return; }
      if (a > b) { M.textContent = "początek po końcu"; return; }
      M.textContent = "";
      Array.prototype.forEach.call(seg.querySelectorAll("button"), function (x) { x.classList.remove(cls); });
      btn.classList.add(cls);
      o.onApply && o.onApply(a, b);
    }
    box.querySelector(".qrc-go").addEventListener("click", go);
    [A, B].forEach(function (x) { x.addEventListener("keydown", function (e) { if (e.key === "Enter") go(); }); });
    if (o.active) { open(); Array.prototype.forEach.call(seg.querySelectorAll("button"), function (x) { x.classList.remove(cls); }); btn.classList.add(cls); }
    return {open: open, button: btn, box: box};
  };
})();
