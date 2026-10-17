/* pogoda-m.js - MOBILE v1 (2026-10-17): Pogoda na telefonie w ukladzie jak Zdrowie / Trening / Analiza trasy.
   Decyzja Michala 17.10: BEZ MAPY NA STARCIE, mapa jako dzial. Start = panel "Teraz i dzis" (pozycja, zdjecie, dane)
   + lista dzialow: Mapa, Prognoza godzinowa, Okno jazdy, Gdzie w weekend, Sprawdzalnosc modeli.
   Dzial = caly ekran; u gory (obok przycisku menu, na pasie z nav.css) "< Pogoda" + nazwa dzialu; cofanie gestem od lewej.
   Mapa = mapa na caly ekran + os czasu (Opad/Temperatura/... + odtwarzanie), bez wykresu.
   Prognoza godzinowa = dolny pasek (wykres) na caly ekran. Okno / Weekend / Sprawdzalnosc = lewy panel jako strona.
   Nie dubluje logiki: dzialy przelacza klikajac ukryte przyciski #rail (openSec w pogoda.html), uklad mapy i paska
   przelicza zdarzenie resize (Leaflet + setDock). Ladowany przez nav.js (rejestr warstw telefonu). Komputer bez zmian. */
(function () {
  "use strict";
  var Q = "(max-width:820px),(pointer:coarse) and (max-height:500px)";
  if (!window.matchMedia || !window.matchMedia(Q).matches) return;
  function start() {
    var lp = document.getElementById("lp"), rail = document.getElementById("rail");
    if (!lp || !rail || document.getElementById("pm-list")) return;
    var SB = "env(safe-area-inset-bottom,0px)", ST = "env(safe-area-inset-top,0px)";
    var ROWS = [["map", "\ud83d\uddfa\ufe0f", "Mapa", "radar i warstwy, o\u015b czasu"], ["godz", "\ud83d\udcca", "Prognoza godzinowa", "opad, temperatura, wiatr"],
      ["okno", "\ud83d\udeb4", "Okno jazdy", "przesun\u0105\u0107 czy mokn\u0105\u0107?"], ["weekend", "\u2b50", "Gdzie w weekend", ""], ["spr", "\u2705", "Sprawdzalno\u015b\u0107 modeli", ""]];
    var LBL = {}; ROWS.forEach(function (r) { LBL[r[0]] = r[2]; });
    var CSS = [
      "html:has(body.pm),body.pm{height:auto!important;overflow:auto!important}",
      "body.pm{background:var(--paper)}",
      "body.pm #rail,body.pm #lp .ttl .x,body.pm #grip,body.pm #dock .dhint{display:none!important}",
      "body.pm #lp{position:static!important;inset:auto!important;width:auto!important;min-width:0!important;max-height:none!important;height:auto!important;margin:0 12px 24px!important;transform:none!important;background:transparent!important;border:0!important;box-shadow:none!important;-webkit-backdrop-filter:none!important;backdrop-filter:none!important}",
      "body.pm #lp .body{overflow:visible!important;max-height:none!important;height:auto!important;padding:0!important}",
      "body.pm:not(.pm-home) #lp .ttl{display:none!important}",
      "body.pm:not(.pm-map) #map,body.pm:not(.pm-map) #mapctl{visibility:hidden!important;pointer-events:none!important}",
      "body.pm.pm-map #lp,body.pm.pm-godz #lp{display:none!important}",
      "body.pm:not(.pm-map):not(.pm-godz) #dock{display:none!important}",
      "body.pm.pm-map #dock .dchart{display:none!important}",
      "body.pm.pm-map #dock{left:8px!important;right:8px!important;bottom:calc(8px + " + SB + ")!important;height:auto!important}",
      "body.pm.pm-godz #dock{top:calc(68px + " + ST + ")!important;bottom:calc(8px + " + SB + ")!important;left:8px!important;right:8px!important;height:auto!important;overflow:auto!important}",
      "body.pm.pm-map #mapctl{position:fixed!important;top:calc(70px + " + ST + ")!important;right:10px!important;left:auto!important;bottom:auto!important;display:flex!important;flex-direction:column!important;gap:6px!important;z-index:1050!important}",
      "body.pm.pm-map .leaflet-top{top:calc(60px + " + ST + ")!important}",
      "#pm-list{margin:22px 0 24px;border-top:1px solid var(--line)}",
      "body.pm:not(.pm-home) #pm-list{display:none}",
      ".pm-h{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:14px 4px 4px}",
      ".pm-row{display:flex;align-items:center;gap:12px;width:100%;min-height:54px;padding:6px 4px;border:0;border-bottom:1px solid var(--line);background:none;color:var(--ink);font:inherit;font-size:16px;text-align:left;cursor:pointer}",
      ".pm-row .ic{width:26px;text-align:center;font-size:18px;flex:0 0 26px}",
      ".pm-row .tx{display:flex;flex-direction:column;min-width:0}.pm-row .sb{font-size:13px;color:var(--muted);margin-top:1px}",
      ".pm-row .ch{margin-left:auto;color:var(--muted);font-size:22px}",
      "#pm-bar{display:none;position:fixed;z-index:1391;top:calc(10px + " + ST + ");left:calc(64px + env(safe-area-inset-left,0px));right:12px;height:44px;align-items:center;gap:10px;min-width:0}",
      "body.pm:not(.pm-home) #pm-bar{display:flex}",
      "#pm-bar button{flex:0 0 auto;min-height:40px;border:0;background:none;color:var(--accent-ink,var(--accent));font:inherit;font-size:15px;padding:0 2px;cursor:pointer}",
      "#pm-bar b{font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--ink)}"
    ].join("\n");
    var st = document.createElement("style"); st.id = "pm-css"; st.textContent = CSS; document.head.appendChild(st);

    var list = document.createElement("div"); list.id = "pm-list";
    list.innerHTML = '<div class="pm-h">Dzia\u0142y</div>' + ROWS.map(function (r) {
      return '<button type="button" class="pm-row" data-pm="' + r[0] + '"><span class="ic">' + r[1] + '</span><span class="tx"><span>' + r[2] + '</span>'
        + (r[3] ? '<span class="sb">' + r[3] + '</span>' : '') + '</span><span class="ch">\u203a</span></button>';
    }).join("");
    lp.parentNode.insertBefore(list, lp.nextSibling);
    var bar = document.createElement("div"); bar.id = "pm-bar";
    bar.innerHTML = '<button type="button" id="pm-back">\u2039 Pogoda</button><b id="pm-t"></b>';
    document.body.appendChild(bar);

    function sec(s) { var b = rail.querySelector('.rt[data-s="' + s + '"]'); if (b && !b.classList.contains("on")) b.click(); }
    function relayout() { setTimeout(function () { try { window.dispatchEvent(new Event("resize")); } catch (e) {} }, 60); }
    function go(v) {
      var B = document.body.classList;
      B.remove("pm-home", "pm-map", "pm-godz", "pm-sec");
      if (v === "map" || v === "godz") { sec("radar"); B.add("pm-" + v); }
      else if (LBL[v]) { sec(v); B.add("pm-sec"); }
      else { v = "home"; sec("radar"); B.add("pm-home"); }
      document.getElementById("pm-t").textContent = LBL[v] || "";
      window.scrollTo(0, 0); relayout();
    }
    list.addEventListener("click", function (e) {
      var r = e.target.closest && e.target.closest("[data-pm]"); if (!r) return;
      var v = r.getAttribute("data-pm");
      try { history.pushState({ pm: v }, "", location.href); } catch (x) {}
      go(v);
    });
    document.getElementById("pm-back").addEventListener("click", function () { if (history.state && history.state.pm) history.back(); else go("home"); });
    window.addEventListener("popstate", function (e) { go(e.state && e.state.pm ? e.state.pm : "home"); });
    document.body.classList.add("pm");
    go(history.state && history.state.pm ? history.state.pm : "home");
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
