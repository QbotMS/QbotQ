/* qembed.js (2026-10-07) - strona osadzona w oknie innej strony QBota (?embed=1, np. Planer wyprawy v3):
   bez wspolnego menu serwisu i bez duzego naglowka, kolorystyka serwisu (ui2: dzien kremowa, noc grafitowa). */
(function () {
  try {
    if (!/[?&]embed=1\b/.test(location.search)) return;
    var h = document.documentElement; h.classList.add("qembed");
    var css = [
      "html.qembed{--qnav-rail:0px!important}",
      "html.qembed nav.qnav,html.qembed .qnav,html.qembed .qnav-burger,html.qembed .qnav-top,html.qembed .masthead{display:none!important}",
      "html.qembed body{padding-left:0!important;margin-left:0!important;background:transparent!important}",
      "html.qembed{--ink:#2a241c;--ink2:#6f6455;--muted:#9a9184;--line:#e6dfd0;--paper:#f8f4ec;--card:#fffdf8;--panel:#efe8da;--accent:#e8742a;--accent-bg:#fbe5d0;--good:#4f7a2a;--good-bg:#e9efd9;--bad:#a32d2d;--bad-bg:#fbe3e0;--warn:#8a6d00;--warn-bg:#f7efc4;--cold:#4a7fb5;--cold-bg:#e3ecf5;--rain:#4a7fb5}",
      "html.qembed.theme-dark{--ink:#f3efe8;--ink2:#b9c0cc;--muted:#8792a4;--line:#5a3a20;--paper:#141922;--card:#1f2631;--panel:#141922;--accent:#e8742a;--accent-bg:#4a2a0a;--good:#b7d38a;--good-bg:#25301a;--bad:#f09595;--bad-bg:#3a1c1c;--warn:#e6c95a;--warn-bg:#3a3110;--cold:#7fb0e0;--cold-bg:#1d2a3a;--rain:#7fb0e0}",
      "html.qembed .bar{padding-top:6px!important;padding-bottom:6px!important}",
      "html.qembed .wrap{padding-top:10px!important}"
    ].join("\n");
    var st = document.createElement("style"); st.textContent = css;
    (document.head || h).appendChild(st);
    // style wstawione pozniej przez strone - nasza regula ma byc ostatnia
    document.addEventListener("DOMContentLoaded", function () {
      document.head.appendChild(st);
      /* Pogoda wyprawy: po przeliczeniu przyciski dni - jeden dzien naraz (wiecej miejsca na dane) */
      var wrap = document.querySelector(".wrap"); if (!wrap || !/pogoda-wyprawy/.test(location.pathname)) return;
      var sel = 0, busy = false;
      function bar() {
        var days = [].slice.call(wrap.querySelectorAll(".day")); var b = document.getElementById("qe-days");
        if (!days.length) { if (b) b.remove(); return; }
        if (!b) { b = document.createElement("div"); b.id = "qe-days"; b.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin:0 0 12px"; wrap.insertBefore(b, wrap.firstChild); }
        if (sel >= days.length) sel = 0;
        var html = days.map(function (d, i) { return '<button type="button" data-i="' + i + '" style="font:inherit;font-size:13.5px;font-weight:600;padding:6px 12px;border-radius:8px;cursor:pointer;border:1px solid ' + (i === sel ? "var(--accent);background:var(--accent-bg);color:var(--accent)" : "var(--line);background:var(--card);color:var(--ink)") + '">Dzień ' + (i + 1) + '</button>'; }).join("");
        if (b.getAttribute("data-h") !== html) { b.innerHTML = html; b.setAttribute("data-h", html); }
        days.forEach(function (d, i) { d.style.display = i === sel ? "" : "none"; });
      }
      new MutationObserver(function () { if (busy) return; busy = true; try { bar(); } finally { busy = false; } }).observe(wrap, { childList: true, subtree: true });
      wrap.addEventListener("click", function (e) { var x = e.target.closest("#qe-days button"); if (!x) return; sel = parseInt(x.getAttribute("data-i"), 10) || 0; bar(); });
    });
  } catch (e) {}
})();
