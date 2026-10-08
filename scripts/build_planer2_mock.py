# -*- coding: utf-8 -*-
"""MOCKUP Planer wyprawy v2 (uklad jak Analiza trasy).

Buduje /opt/qbot/web/public/planer-wyprawy2-render.js z ZYWEGO planer-wyprawy-render.js
przez latki tekstowe + nadpisania funkcji na koncu IIFE (ostatnia deklaracja wygrywa).
Dzieki temu logika (API, podzial, pogoda, forma, narzedzia) jest JEDNA - mockup zmienia
tylko uklad. Kazda latka musi trafic dokladnie tyle razy ile oczekiwano (assert):
gdy zrodlo sie zmieni, skrypt padnie glosno zamiast cicho zepsuc strone.

Uruchom:  .venv/bin/python3 scripts/build_planer2_mock.py
Strona:   /planer-wyprawy2.html  (statyka poza repo, zywa od razu)
"""
import pathlib

PUB = pathlib.Path("/opt/qbot/web/public")
SRC = PUB / "planer-wyprawy-render.js"
DST = PUB / "planer-wyprawy2-render.js"


def rep(s, old, new, count=1):
    n = s.count(old)
    assert n == count, "latka: oczekiwano %dx, jest %dx: %r" % (count, n, old[:80])
    return s.replace(old, new)


src = SRC.read_text(encoding="utf-8")

# 1. nowy uklad ma wlasna belke .qhead - nie przenosimy elementow do <header>
src = rep(src, 'if (!(typeof IS_PRINT !== "undefined" && IS_PRINT)) {', 'if (false) {')

# 2. mapa pelnoekranowa -> zoom kolkiem zawsze
src = rep(src, 'map.scrollWheelZoom.disable();', 'void 0;', 3)

# 3. forma / tlo / opis widoczne niezaleznie od wybranego dnia (osobne miejsca w ukladzie)
src = rep(src, 'if (currentView !== null) { box.style.display = "none"; return; }', '')
src = rep(src, 'if (currentView !== null) { bh.style.display = "none"; bg.style.display = "none"; return; }', '')
src = rep(src, 'if (opis) opis.style.display = "none";', '')

# 4. body.pv-day = wybrany dzien (CSS chowa karty etapow, pokazuje panel dnia)
src = rep(src, '    currentView = v;\n    renderViewTabs();',
          '    currentView = v;\n    document.body.classList.toggle("pv-day", v != null);\n    renderViewTabs();')

# 5. klik w karte etapu = przejscie do widoku dnia
src = rep(src, 'if (e.target.closest(".ec-detail")) return; toggleDay(',
          'if (e.target.closest(".ec-detail")) return; setView(')

# 6. NARZEDZIA: licznik dni -> Parametry; lista GPX -> widok dnia
i0 = src.index("h += '<div class=\"qa-h\">Podzia")
i1 = src.index("h += '<div class=\"qa-h\" style=\"margin-top:18px\">Wersje", i0)
src = src[:i0] + src[i1:]
g0 = src.index("Pobierz GPX dnia</div>';")
g0 = src.rindex("h += ", 0, g0)
g1 = src.index("body.innerHTML = h;", g0)
src = src[:g0] + src[g1:]

# 7. GPX w widoku dnia
a0 = src.index("h += '<div class=\"dsec\" id=\"d-attr\">")
a1 = src.index("\n", a0) + 1
src = (src[:a1]
       + "    h += '<div class=\"dsec\" id=\"d-gpx\"><h3>Ślad dnia</h3><button class=\"dbtn\" id=\"d-gpx-btn\">⬇ Pobierz GPX dnia ' + (i + 1) + '</button></div>';\n"
       + src[a1:])
src = rep(src, 'var gen = document.getElementById("d-genopis"); if (gen) gen.onclick = doDostosuj;',
          'var gen = document.getElementById("d-genopis"); if (gen) gen.onclick = doDostosuj;\n'
          '    var _gx = document.getElementById("d-gpx-btn"); if (_gx) _gx.onclick = function () {\n'
          '      var _nm = (sel && sel.options[sel.selectedIndex]) ? sel.options[sel.selectedIndex].text : "";\n'
          '      window.open("/api/planer/dzien/gpx?route_id=" + encodeURIComponent(rid) + "&from=" + st.from.toFixed(1)\n'
          '        + "&to=" + st.to.toFixed(1) + "&day=" + (i + 1) + "&name=" + encodeURIComponent(_nm), "_blank");\n'
          '    };')

# 8. nadpisania: dopasowanie mapy do paneli ukladu v2, bez trybow map-bg
OVR = r'''
  /* ===== MOCKUP v2: nadpisania (ostatnia deklaracja funkcji wygrywa) ===== */
  function _pvRect(id) { var e = document.getElementById(id); return (e && e.offsetParent !== null) ? e.getBoundingClientRect() : null; }
  function _fitPadTop() { return 16; }
  function _fitPadLeft() {
    var p = _pvRect("pv-panel"), m = _pvRect("map");
    return (p && m) ? Math.max(24, Math.round(p.right - m.left) + 18) : 24;
  }
  function _fitPadBottom() {
    var f = _pvRect("profil"), m = _pvRect("map");
    return (f && m) ? Math.max(24, Math.round(m.bottom - f.top) + 18) : 24;
  }
  function applyMapMode() {
    document.body.classList.remove("map-bg", "mb-all", "mb-day");
    if (map) { [60, 300].forEach(function (ms) { setTimeout(function () { try { map.invalidateSize(false); } catch (e) {} }, ms); }); }
  }
  window.__planerRefitAny = function () {
    try {
      if (!map) return;
      map.invalidateSize(false);
      if (currentView == null) { if (coords.length) fitRoute(coords); }
      else { var st = computeStage(currentView); zoomToDay(st.from, st.to); }
    } catch (e) {}
  };
'''
TAIL = '  document.addEventListener("DOMContentLoaded", init);\n})();'
src = rep(src, TAIL, OVR + "\n" + TAIL)

HEAD = ("/* AUTO-GENEROWANY przez scripts/build_planer2_mock.py z planer-wyprawy-render.js.\n"
        "   NIE edytuj recznie - zmien zrodlo albo latki w skrypcie i uruchom ponownie. */\n")
DST.write_text(HEAD + src, encoding="utf-8")
print("OK ->", DST, len(HEAD + src), "B")
