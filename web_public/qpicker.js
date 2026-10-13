/* QPick - mini kalendarz QBota (2026-10-13). Uzycie: QPick.open(elementKotwica, {value: Date, onPick: function(Date){}, mode: "day"|"week"|"month"}).
   Klik w naglowek miesiaca = widok 12 miesiecy (z przewijaniem lat). Esc / klik obok = zamknij. Bez zaleznosci, style wstrzykiwane. */
(function () {
  "use strict";
  if (window.QPick) return;
  var MN = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"];
  var MS = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"];
  var css = ".qpk-pop{position:absolute;z-index:200;background:var(--card,#16181d);border:1px solid var(--line2,var(--line,#333));border-radius:12px;box-shadow:0 12px 34px rgba(0,0,0,.45);padding:10px;width:268px;font:inherit;color:var(--ink,#eee)}" +
    ".qpk-h{display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:6px}" +
    ".qpk-h button{border:1px solid var(--line,#333);background:var(--well,#222);color:var(--ink,#eee);border-radius:8px;min-width:30px;height:30px;cursor:pointer;font:inherit}" +
    ".qpk-h .t{flex:1;text-align:center;font-weight:700;cursor:pointer;border:none;background:none}.qpk-h .t:hover{color:var(--accent,#e67e22)}" +
    ".qpk-g{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;text-align:center;font-size:13px}" +
    ".qpk-g .w{color:var(--muted,#888);font-size:11px;padding:3px 0}" +
    ".qpk-g button{border:none;background:none;color:var(--ink,#eee);border-radius:8px;height:32px;cursor:pointer;font:inherit;font-variant-numeric:tabular-nums}" +
    ".qpk-g button:hover{background:var(--well,#222)}.qpk-g button.o{color:var(--muted,#888);opacity:.55}" +
    ".qpk-g button.td{outline:1px solid var(--accent,#e67e22)}.qpk-g button.sel{background:var(--accent,#e67e22);color:#111;font-weight:700}" +
    ".qpk-m{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.qpk-m button{border:1px solid var(--line,#333);background:var(--well,#222);color:var(--ink,#eee);border-radius:8px;height:38px;cursor:pointer;font:inherit}" +
    ".qpk-m button.sel{background:var(--accent,#e67e22);color:#111;font-weight:700;border-color:transparent}.qpk-m button.td{outline:1px solid var(--accent,#e67e22)}" +
    ".qpk-f{display:flex;justify-content:space-between;margin-top:8px}.qpk-f button{border:1px solid var(--line,#333);background:var(--well,#222);color:var(--ink,#eee);border-radius:8px;padding:4px 10px;cursor:pointer;font:inherit;font-size:12.5px}" +
    ".qpk-anchor{cursor:pointer;text-decoration:underline dotted;text-underline-offset:4px}.qpk-anchor:hover{color:var(--accent,#e67e22)}";
  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
  var pop = null, cleanup = null;
  function close() { if (pop) { pop.remove(); pop = null; } if (cleanup) { cleanup(); cleanup = null; } }
  function same(a, b) { return a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(); }
  function open(anchor, opt) {
    close(); opt = opt || {};
    var sel = opt.value ? new Date(opt.value) : new Date(), today = new Date(), vy = sel.getFullYear(), vm = sel.getMonth(), view = opt.mode === "month" ? "m" : "d";
    pop = document.createElement("div"); pop.className = "qpk-pop"; pop.setAttribute("role", "dialog"); pop.setAttribute("aria-label", "Wybierz datę");
    document.body.appendChild(pop);
    function pick(d) { close(); if (opt.onPick) opt.onPick(d); }
    function draw() {
      var h = "";
      if (view === "d") {
        h += "<div class='qpk-h'><button data-n='-1' aria-label='Poprzedni miesiąc'>‹</button><button class='t' data-v='m' title='Wybierz miesiąc'>" + MN[vm] + " " + vy + "</button><button data-n='1' aria-label='Następny miesiąc'>›</button></div><div class='qpk-g'>";
        ["pn", "wt", "śr", "cz", "pt", "sb", "nd"].forEach(function (w) { h += "<span class='w'>" + w + "</span>"; });
        var first = new Date(vy, vm, 1), off = (first.getDay() + 6) % 7, start = new Date(vy, vm, 1 - off);
        for (var i = 0; i < 42; i++) { var d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
          h += "<button data-d='" + d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate() + "' class='" + (d.getMonth() !== vm ? "o " : "") + (same(d, today) ? "td " : "") + (same(d, sel) ? "sel" : "") + "'>" + d.getDate() + "</button>"; }
        h += "</div>";
      } else {
        h += "<div class='qpk-h'><button data-y='-1' aria-label='Poprzedni rok'>‹</button><button class='t' data-v='d' title='Wróć do dni'>" + vy + "</button><button data-y='1' aria-label='Następny rok'>›</button></div><div class='qpk-m'>";
        MS.forEach(function (m, i) { h += "<button data-m='" + i + "' class='" + (vy === sel.getFullYear() && i === sel.getMonth() ? "sel " : "") + (vy === today.getFullYear() && i === today.getMonth() ? "td" : "") + "'>" + m + "</button>"; });
        h += "</div>";
      }
      h += "<div class='qpk-f'><button data-today='1'>Dziś</button><button data-x='1'>Zamknij</button></div>";
      pop.innerHTML = h;
      pop.querySelectorAll("button").forEach(function (b) { b.onclick = function (e) { e.stopPropagation(); var ds = b.dataset;
        if (ds.n) { vm += +ds.n; if (vm < 0) { vm = 11; vy--; } if (vm > 11) { vm = 0; vy++; } draw(); }
        else if (ds.y) { vy += +ds.y; draw(); }
        else if (ds.v) { view = ds.v; draw(); }
        else if (ds.m != null && ds.m !== undefined && b.dataset.m !== undefined) { vm = +ds.m; if (opt.mode === "month") pick(new Date(vy, vm, 1)); else { view = "d"; draw(); } }
        else if (ds.d) { var p = ds.d.split("-"); pick(new Date(+p[0], +p[1] - 1, +p[2])); }
        else if (ds.today) pick(new Date());
        else if (ds.x) close(); }; });
    }
    draw();
    var r = anchor.getBoundingClientRect(), left = r.left + window.scrollX + r.width / 2 - 134;
    left = Math.max(8 + window.scrollX, Math.min(left, window.scrollX + document.documentElement.clientWidth - 276));
    pop.style.left = left + "px"; pop.style.top = (r.bottom + window.scrollY + 6) + "px";
    function onDoc(e) { if (pop && !pop.contains(e.target) && e.target !== anchor) close(); }
    function onKey(e) { if (e.key === "Escape") close(); }
    setTimeout(function () { document.addEventListener("click", onDoc); }, 0); document.addEventListener("keydown", onKey);
    cleanup = function () { document.removeEventListener("click", onDoc); document.removeEventListener("keydown", onKey); };
  }
  /* podpiecie elementu: klik / Enter otwiera kalendarz */
  function attach(el, opt) {
    if (!el) return; el.classList.add("qpk-anchor"); el.setAttribute("role", "button"); el.tabIndex = 0; el.title = el.title || "Kliknij, aby wybrać datę";
    function go(e) { if (e) e.stopPropagation(); open(el, typeof opt === "function" ? opt() : opt); }
    el.addEventListener("click", go); el.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(e); } });
  }
  window.QPick = { open: open, close: close, attach: attach };
})();
