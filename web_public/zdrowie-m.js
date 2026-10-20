/* zdrowie-m.js - MOBILE v1 (2026-10-16): Zdrowie na telefonie, wzorem Analizy trasy (raport-trasy-m.js).
   Wlacza sie na telefonie w pionie i w poziomie (ekran <=820px LUB dotyk i wysokosc <=500px); komputer bez zmian.
   Decyzja Michala 16.10: po wejsciu od razu DZIENNIK (dzis), pod nim LISTA DZIALOW (duze wiersze).
   Dotkniecie dzialu = dzial na caly ekran (nazwa dzialu w tytule, "< Zdrowie" nad tytulem); cofanie gestem od lewej
   (history.pushState/popstate). Pasek zakladek ukryty. Nie dubluje logiki: przelacza dzialy klikajac istniejace przyciski
   #tabs (jedzenie.js tab() - ladowanie danych dzialu zostaje tam). Linki z hashem (#suple, #serce...) otwieraja dzial,
   a gest wstecz wraca do Dziennika. Dok.: docs/FORMA_UI_LAYOUT.md (telefon). */
(function () {
  "use strict";
  var Q = "(max-width:820px),(pointer:coarse) and (max-height:500px)";
  if (!window.matchMedia || !window.matchMedia(Q).matches) return;
  var tabs = document.getElementById("tabs"), wrap = document.querySelector(".wrap"), h1 = document.querySelector(".head h1"), dni = document.getElementById("t-dni");
  if (!tabs || !wrap || !h1 || !dni) return;
  var TITLE = h1.textContent;
  var ICO = { analiza: "\ud83d\udca1", bilans: "\u2696\ufe0f", serce: "\u2764\ufe0f", suple: "\ud83d\udc8a", pasy: "\ud83d\udd25", weekend: "\ud83d\uddd3\ufe0f", menu: "\ud83e\udd66" };
  var SUB = { bilans: "bilans i waga", serce: "t\u0119tno, ci\u015bnienie, oddech", menu: "menu diety" };
  var CSS = [
    "body.zm #tabs{display:none!important}",
    "body.zm .hdr-streaks{flex-wrap:nowrap!important;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch;max-width:100%}",
    "body.zm .hdr-streaks::-webkit-scrollbar{display:none}",
    "body.zm .hdr-streaks .pill{flex:0 0 auto}",
    "body.zm:not(.zm-home) .hdr-streaks{display:none}",
    "#zm-back{display:none;align-items:center;gap:4px;margin:0 0 4px;padding:0 2px;min-height:40px;border:0;background:none;color:var(--accent-ink,var(--accent));font:inherit;font-size:15px;cursor:pointer}",
    "body.zm:not(.zm-home) #zm-back{display:inline-flex}",
    "#zm-list{margin:22px 0 0;border-top:1px solid var(--line)}",
    "body.zm:not(.zm-home) #zm-list{display:none}",
    ".zm-h{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:14px 4px 4px}",
    ".zm-row{display:flex;align-items:center;gap:12px;width:100%;min-height:54px;padding:6px 4px;border:0;border-bottom:1px solid var(--line);background:none;color:var(--ink);font:inherit;font-size:16px;text-align:left;cursor:pointer}",
    ".zm-row .ic{width:26px;text-align:center;font-size:18px;flex:0 0 26px}",
    ".zm-row .tx{display:flex;flex-direction:column;min-width:0}.zm-row .sb{font-size:13px;color:var(--muted);margin-top:1px}",
    ".zm-row .ch{margin-left:auto;color:var(--muted);font-size:22px}",
    /* tresc dzialow: nic nie rozjezdza strony w bok */
    "body.zm table.tb,body.zm table.qs-table,body.zm table.nt{display:block;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}",
    "body.zm canvas,body.zm svg{max-width:100%}",
    "body.zm .days{-webkit-overflow-scrolling:touch;scrollbar-width:none}body.zm .days::-webkit-scrollbar{display:none}",
    "body.zm .daychip{min-height:44px}",
    "body.zm .qbox{max-height:calc(100vh - 32px);overflow:auto}"
  ].join("\n");

  var st = document.createElement("style"); st.id = "zm-css"; st.textContent = CSS; document.head.appendChild(st);

  var back = document.createElement("button");
  back.type = "button"; back.id = "zm-back"; back.innerHTML = "\u2039 " + TITLE;
  wrap.insertBefore(back, wrap.firstChild);

  var list = document.createElement("div"); list.id = "zm-list";
  var h = '<div class="zm-h">Dzia\u0142y</div>', LBL = {};
  [].forEach.call(tabs.querySelectorAll("button[data-t]"), function (b) {
    var t = b.dataset.t; LBL[t] = b.textContent.trim();
    if (t === "dni") return;
    h += '<button type="button" class="zm-row" data-zm="' + t + '"><span class="ic">' + (ICO[t] || "\u2022") + '</span><span class="tx"><span>' + LBL[t] + '</span>'
      + (SUB[t] ? '<span class="sb">' + SUB[t] + '</span>' : '') + '</span><span class="ch">\u203a</span></button>';
  });
  list.innerHTML = h;
  dni.parentNode.insertBefore(list, dni.nextSibling);

  function btn(t) { return tabs.querySelector('button[data-t="' + t + '"]'); }
  function go(t, push) {
    if (!t || t === "dni") {
      if (!dni.hidden && document.body.classList.contains("zm-home")) return;
      var b = btn("dni"); if (b && dni.hidden) b.click();
      document.body.classList.add("zm-home"); h1.textContent = TITLE;
      return;
    }
    if (push) { try { history.pushState({ zm: t }, "", location.href); } catch (e) {} }
    var bt = btn(t); if (bt) bt.click();   /* jedzenie.js tab(): pokazuje dzial, laduje dane, ustawia #hash */
    document.body.classList.remove("zm-home"); h1.textContent = LBL[t] || TITLE;
    window.scrollTo(0, 0);
  }
  list.addEventListener("click", function (e) { var r = e.target.closest && e.target.closest("[data-zm]"); if (r) go(r.getAttribute("data-zm"), true); });
  back.addEventListener("click", function () { if (history.state && history.state.zm) history.back(); else go("dni", false); });
  window.addEventListener("popstate", function (e) { go(e.state && e.state.zm ? e.state.zm : "dni", false); });

  document.body.classList.add("zm");
  /* start: dzial z linku (#suple itp.) -> pod spodem wpis Dziennika, zeby gest wstecz wracal do Dziennika */
  var open = null;
  [].forEach.call(document.querySelectorAll('section[id^="t-"]'), function (s) { if (!s.hidden) open = s.id.slice(2); });
  if (open && open !== "dni") {
    var hs = location.hash;
    try { history.replaceState(null, "", "#dni"); history.pushState({ zm: open }, "", hs || ("#" + open)); } catch (e) {}
    document.body.classList.remove("zm-home"); h1.textContent = LBL[open] || TITLE;
  } else {
    document.body.classList.add("zm-home");
  }
})();
