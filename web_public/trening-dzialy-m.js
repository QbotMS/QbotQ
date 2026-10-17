/* trening-dzialy-m.js (2026-10-17): Trening na telefonie w ukladzie jak Zdrowie (zdrowie-m.js) i Analiza trasy.
   Decyzja Michala 17.10: naglowek z zakladkami zostaje TYLKO w Formie; reszta stron na telefonie = glowny widok + lista dzialow pod nim.
   Tutaj: od razu Kalendarz, pod nim lista dzialow (Cele, Plan). Dotkniecie = dzial na caly ekran, nazwa dzialu w tytule,
   "< Trening" nad tytulem, cofanie gestem od lewej. Ukrywa zdublowane zakladki: pas w naglowku (.tr-sub, trener.js)
   i pigulki #tm-tabs (trener-m.js). Nie dubluje logiki: przelacza dzial klikajac ukryte przyciski #tm-tabs
   (trener-m.js robi replaceState + show), a wpis historii dodaje pushState przed kliknieciem.
   Dziala tylko gdy wlaczony jest tryb telefonu trener-m.js (body.tm); komputer bez zmian. */
(function () {
  "use strict";
  if (!document.body.classList.contains("tm")) return;
  var wrap = document.querySelector(".wrap"), h1 = document.querySelector(".head h1"), kal = document.getElementById("p-kal");
  if (!wrap || !h1 || !kal) return;
  var TITLE = h1.textContent;
  var ROWS = [["cele", "\ud83c\udfaf", "Cele", ""], ["sezon", "\ud83d\udcc8", "Plan", "sezon"]];
  var LBL = { kalendarz: "Kalendarz" }; ROWS.forEach(function (r) { LBL[r[0]] = r[2]; });
  var CSS = [
    "body.tm .head .tr-sub,body.tm #tm-tabs{display:none!important}",
    "#qml-back{display:none;align-items:center;gap:4px;margin:0 0 4px;padding:0 2px;min-height:40px;border:0;background:none;color:var(--accent-ink,var(--accent));font:inherit;font-size:15px;cursor:pointer}",
    "body.tm:not(.tr-month):not(.tm-ov) #qml-back{display:inline-flex}",
    "#qml-list{margin:22px 0 0;border-top:1px solid var(--line)}",
    "body.tm:not(.tr-month) #qml-list{display:none}",
    ".qml-h{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:14px 4px 4px}",
    ".qml-row{display:flex;align-items:center;gap:12px;width:100%;min-height:54px;padding:6px 4px;border:0;border-bottom:1px solid var(--line);background:none;color:var(--ink);font:inherit;font-size:16px;text-align:left;cursor:pointer}",
    ".qml-row .ic{width:26px;text-align:center;font-size:18px;flex:0 0 26px}",
    ".qml-row .tx{display:flex;flex-direction:column;min-width:0}.qml-row .sb{font-size:13px;color:var(--muted);margin-top:1px}",
    ".qml-row .ch{margin-left:auto;color:var(--muted);font-size:22px}"
  ].join("\n");
  var st = document.createElement("style"); st.id = "qml-css"; st.textContent = CSS; document.head.appendChild(st);

  var back = document.createElement("button"); back.type = "button"; back.id = "qml-back"; back.innerHTML = "\u2039 " + TITLE;
  wrap.insertBefore(back, wrap.firstChild);
  var list = document.createElement("div"); list.id = "qml-list";
  list.innerHTML = '<div class="qml-h">Dzia\u0142y</div>' + ROWS.map(function (r) {
    return '<button type="button" class="qml-row" data-qml="' + r[0] + '"><span class="ic">' + r[1] + '</span><span class="tx"><span>' + r[2] + '</span>'
      + (r[3] ? '<span class="sb">' + r[3] + '</span>' : '') + '</span><span class="ch">\u203a</span></button>';
  }).join("");
  kal.parentNode.insertBefore(list, kal.nextSibling);

  function open(t) {
    var b = document.querySelector('#tm-tabs [data-tab="' + t + '"]'); if (!b) return;
    try { history.pushState(history.state, "", location.href); } catch (e) {}   /* nowy wpis; trener-m.js zastapi go dzialem */
    b.click();
  }
  list.addEventListener("click", function (e) { var r = e.target.closest && e.target.closest("[data-qml]"); if (r) open(r.getAttribute("data-qml")); });
  back.addEventListener("click", function () { history.back(); });

  function paint() {
    var home = document.body.classList.contains("tr-month");
    var sub = (location.hash || "").replace("#", "");
    h1.textContent = home ? TITLE : (LBL[sub] || TITLE);
  }
  /* trener.js go() przelacza klase tr-month PRZED zmiana #hash - tytul liczony chwile po zmianie */
  new MutationObserver(function () { setTimeout(paint, 0); }).observe(document.body, { attributes: true, attributeFilter: ["class"] });
  window.addEventListener("popstate", function () { setTimeout(paint, 0); });
  paint();
})();
