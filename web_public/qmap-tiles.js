/* qmap-tiles.js (2026-10-07) - ciemna mapa CARTO Dark Matter w motywie nocnym, w dziennym OSM jak dotad.
   Klucz z serwera (/api/config/map <- zmienna CARTO_BASEMAP_KEY). Klucz jest z natury publiczny (przegladarka wysyla go
   do CARTO); chroni go ograniczenie referera ustawione w CARTO (albert.cytr.us, qbot.cytr.us).
   Czytelnosc (v2): podklad bez napisow (dark_nolabels) rozjasniony filtrem + osobna warstwa samych napisow
   (dark_only_labels) NAD sladem trasy, rozjasniona do jasnych nazw miejscowosci.
   Bez klucza albo przy bledach CARTO (np. odrzucony referer) strona sama wraca do OSM.
   Warunki CARTO: podpis "© OpenStreetMap, © CARTO" musi byc widoczny - dodawany automatycznie przy ciemnej mapie.
   Uzycie na stronie: po utworzeniu warstwy kafli -> if(window.qTilesAttach)window.qTilesAttach(map, warstwa); */
(function () {
  "use strict";
  var OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  var C_BASE = "https://basemaps.cartocdn.com/rastertiles/dark_nolabels/{z}/{x}/{y}{r}.png?key=";
  var C_LAB = "https://basemaps.cartocdn.com/rastertiles/dark_only_labels/{z}/{x}/{y}{r}.png?key=";
  var F_BASE = "brightness(1.45) contrast(1.15)";   // drogi, rzeki, lasy wyrazniejsze; tlo nadal ciemne
  var F_LAB = "brightness(1.9) contrast(1.1)";      // nazwy miejscowosci jasne, prawie biale
  /* 2026-10-07: domyslny tryb nocny = ciemne B/W z kafli OSM (teren, lasy, zabudowa zostaja; CARTO pokazywalo za malo).
     Odwrocenie jasnosci: tlo ciemne, napisy jasne. window.QMAP_NIGHT = "carto" wlacza wariant CARTO. */
  var F_NIGHT = "grayscale(1) invert(1) contrast(1.0) brightness(1.25) sepia(0.35) hue-rotate(180deg) saturate(1.6)";   // 2026-10-07: wariant F (wybor uzytkownika): tlo ~#141518, napisy ~#fefeff, drobne ~#d4e6ff (zmierzone)
  /* "czarna" = tryb B/W w nocy: ciemniejsza i neutralna (tlo ~#131313). Regula z !important nadpisuje filtr B/W strony
     (Raport z jazdy: styl inline na tilePane, Analiza trasy: klasa .bw na #map). */
  try { var _st = document.createElement("style"); _st.textContent = "html.qmap-night #map.bw .leaflet-tile-pane,html.qmap-night .leaflet-tile-pane[style*=\"grayscale\"]{filter:grayscale(1) brightness(0.7) contrast(1.1)!important}"; document.head.appendChild(_st); } catch (e) {}
  var A_OSM = "&copy; OpenStreetMap";
  var A_CARTO = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>, &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>';
  var cfgP = null, KEY = null, BROKEN = false, maps = [];
  var F_DAYGRAY = "grayscale(1) contrast(.95) brightness(1.05)";   // "szara" - domyslna w dzien (strony z opcja dayGray)
  var NIGHT_COLOR = false;   // noc + przycisk "kolor" = zwykla kolorowa mapa (bez odwrocenia)

  function cfg() {
    if (!cfgP) cfgP = fetch("/api/config/map", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; })
      .then(function (j) { KEY = (j && j.carto_key) || null; return KEY; });
    return cfgP;
  }
  function dark() { return document.documentElement.classList.contains("theme-dark"); }
  function want() {
    if (!dark() || NIGHT_COLOR) return "osm";
    if (window.QMAP_NIGHT === "carto" && KEY && !BROKEN) return "carto";
    return "osmdark";
  }
  function filt(layer, f) { try { var c = layer.getContainer && layer.getContainer(); if (c) c.style.filter = f || ""; } catch (e) {} }
  function labPane(map) {
    var p = map.getPane("qLabels");
    if (!p) { p = map.createPane("qLabels"); p.style.zIndex = 450; p.style.pointerEvents = "none"; }  // nad trasa (400), pod znacznikami (600)
    return "qLabels";
  }

  function apply(m) {
    var w = want();
    if (m.mode === w) return;
    var ac = m.map.attributionControl;
    if (w === "carto" && !ac) {   // strona mogla wylaczyc podpisy - przy CARTO sa obowiazkowe
      ac = L.control.attribution({ prefix: false, position: "bottomright" }).addTo(m.map);
      m.map.attributionControl = ac;
    }
    if (ac) {
      ac.removeAttribution(A_OSM); ac.removeAttribution(A_CARTO);
      ac.addAttribution(w === "carto" ? A_CARTO : A_OSM);
    }
    m.mode = w; m.errs = 0;
    if (w === "carto") {
      m.layer.setUrl(C_BASE + encodeURIComponent(KEY));
      filt(m.layer, F_BASE);
      if (!m.labels) {
        m.labels = L.tileLayer(C_LAB + encodeURIComponent(KEY), { maxZoom: 19, pane: labPane(m.map) });
        m.labels.on("tileerror", function () { onErr(m); });
        m.labels.on("add", function () { filt(m.labels, F_LAB); });
      }
      if (!m.map.hasLayer(m.labels)) m.labels.addTo(m.map);
      filt(m.labels, F_LAB);
    } else {
      m.layer.setUrl(OSM);
      filt(m.layer, w === "osmdark" ? F_NIGHT : ((m.opt.dayGray && !dark()) ? F_DAYGRAY : ""));
      if (m.labels && m.map.hasLayer(m.labels)) m.map.removeLayer(m.labels);
    }
    document.documentElement.classList.toggle("qmap-carto", w === "carto");
    document.documentElement.classList.toggle("qmap-night", w !== "osm");
    try { document.dispatchEvent(new Event("qmapchange")); } catch (e) {}
  }
  function onErr(m) { if (m.mode === "carto" && ++m.errs >= 8) { BROKEN = true; maps.forEach(apply); } }

  window.qTilesNightColor = function (on) { NIGHT_COLOR = !!on; maps.forEach(apply); };
  window.qTilesIsNightColor = function () { return NIGHT_COLOR; };
  window.qTilesAttach = function (map, layer, opt) {
    if (!map || !layer) return;
    var m = { map: map, layer: layer, mode: "osm", errs: 0, labels: null, opt: opt || {} };
    if (m.opt.dayGray && !dark()) filt(layer, F_DAYGRAY);
    maps.push(m);
    layer.on("tileerror", function () { onErr(m); });
    cfg().then(function () { apply(m); });
  };

  try {
    new MutationObserver(function () { maps.forEach(apply); })
      .observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  } catch (e) {}
})();
