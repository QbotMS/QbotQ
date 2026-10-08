/* qmap-tiles.js (2026-10-07) - ciemna mapa CARTO Dark Matter w motywie nocnym, w dziennym OSM jak dotad.
   Klucz z serwera (/api/config/map <- zmienna CARTO_BASEMAP_KEY). Klucz jest z natury publiczny (przegladarka wysyla go
   do CARTO); chroni go ograniczenie referera ustawione w CARTO (albert.cytr.us, qbot.cytr.us).
   Czytelnosc (v2): podklad bez napisow (dark_nolabels) rozjasniony filtrem + osobna warstwa samych napisow
   (dark_only_labels) NAD sladem trasy, rozjasniona do jasnych nazw miejscowosci.
   Bez klucza albo przy bledach CARTO (np. odrzucony referer) strona sama wraca do OSM.
   Warunki CARTO: podpis "© OpenStreetMap, © CARTO" musi byc widoczny - dodawany automatycznie przy ciemnej mapie.
   2026-10-07 (wybor uzytkownika po porownaniu /mapy-test.html): tryby CIEMNA i CZARNA = CARTO Voyager @2x (kafle Retina 512 px,
   ostre) z tym samym filtrem nocnym co wczesniej; KOLOR i SZARA bez zmian (OSM). Bez klucza / przy bledach CARTO -> OSM jak dotad.
   Uzycie na stronie: po utworzeniu warstwy kafli -> if(window.qTilesAttach)window.qTilesAttach(map, warstwa); */
(function () {
  "use strict";
  var OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  var C_BASE = "https://basemaps.cartocdn.com/rastertiles/dark_nolabels/{z}/{x}/{y}{r}.png?key=";
  var C_LAB = "https://basemaps.cartocdn.com/rastertiles/dark_only_labels/{z}/{x}/{y}{r}.png?key=";
  var VOY = "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png?key=";   // Retina zawsze (@2x), tryby ciemna/czarna
  var F_BASE = "brightness(1.45) contrast(1.15)";   // drogi, rzeki, lasy wyrazniejsze; tlo nadal ciemne
  var F_LAB = "brightness(1.9) contrast(1.1)";      // nazwy miejscowosci jasne, prawie biale
  /* 2026-10-07: domyslny tryb nocny = ciemne B/W z kafli OSM (teren, lasy, zabudowa zostaja; CARTO pokazywalo za malo).
     Odwrocenie jasnosci: tlo ciemne, napisy jasne. window.QMAP_NIGHT = "carto" wlacza wariant CARTO. */
  var F_NIGHT = "grayscale(1) invert(1) contrast(1.0) brightness(3.27) sepia(0.35) hue-rotate(180deg) saturate(1.6)";   // 2026-10-07: wariant F (wybor uzytkownika): tlo ~#141518, napisy ~#fefeff, drobne ~#d4e6ff (zmierzone)
  /* "czarna" = tryb B/W w nocy: ciemniejsza i neutralna (tlo ~#131313). Regula z !important nadpisuje filtr B/W strony
     (Raport z jazdy: styl inline na tilePane, Analiza trasy: klasa .bw na #map). */
  try { var _st = document.createElement("style"); _st.textContent = "html.qmap-night #map.bw .leaflet-tile-pane,html.qmap-night .leaflet-tile-pane[style*=\"grayscale\"]{filter:grayscale(1) brightness(0.38)!important}"; document.head.appendChild(_st); } catch (e) {}
  var A_OSM = "&copy; OpenStreetMap";
  var A_CARTO = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>, &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>';
  var cfgP = null, KEY = null, BROKEN = false, maps = [];
  var F_DAYGRAY = "grayscale(1) contrast(.95) brightness(1.05)";   // "szara" - domyslna w dzien (strony z opcja dayGray)   // "szara" - domyslna w dzien (strony z opcja dayGray)
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
    return (KEY && !BROKEN) ? "voyager" : "osmdark";
  }
  /* 2026-10-07: filtr na KAZDYM kaflu (Safari/iOS nie rysowal filtra nalozonego na kontener warstwy) */
  try { var _fs = document.createElement("style"); _fs.textContent = ".leaflet-layer.qf img.leaflet-tile{filter:var(--qf)}"; document.head.appendChild(_fs); } catch (e) {}
  function filt(layer, f) {
    try {
      layer._qf = f || "";   // zapamietany - nakladany ponownie po utworzeniu warstwy (zdarzenia add/load)
      var c = layer.getContainer && layer.getContainer(); if (!c) return;
      c.style.filter = "";
      if (f) { c.style.setProperty("--qf", f); c.classList.add("qf"); } else { c.style.removeProperty("--qf"); c.classList.remove("qf"); }
    } catch (e) {}
  }
  function labPane(map) {
    var p = map.getPane("qLabels");
    if (!p) { p = map.createPane("qLabels"); p.style.zIndex = 450; p.style.pointerEvents = "none"; }  // nad trasa (400), pod znacznikami (600)
    return "qLabels";
  }

  var ST_F = null;
  function stF(st) {
    if (!ST_F) ST_F = { kolor: "", szara: F_DAYGRAY, ciemna: F_NIGHT, czarna: F_NIGHT + " grayscale(1) brightness(0.38)" };
    return ST_F[st] || "";
  }
  function apply(m) {
    if (m.opt && m.opt.dayGray) {   // strony bez wlasnego przycisku (Planer, Naprawa trasy): styl per mapa, domyslnie noc=ciemna, dzien=szara
      var st = m.st || (dark() ? "ciemna" : "szara");
      var vy = (st === "ciemna" || st === "czarna") && KEY && !BROKEN, wv = vy ? "voyager" : "osm";
      if (m.labels && m.map.hasLayer(m.labels)) m.map.removeLayer(m.labels);
      if (m.mode !== wv) {
        seturl(m, vy ? VOY + encodeURIComponent(KEY) : OSM); m.mode = wv; m.errs = 0;
        var acv = m.map.attributionControl;
        if (vy && !acv) { acv = L.control.attribution({ prefix: false, position: "bottomright" }).addTo(m.map); m.map.attributionControl = acv; attrLast(acv); }
        if (acv) { acv.removeAttribution(A_OSM); acv.removeAttribution(A_CARTO); acv.addAttribution(vy ? A_CARTO : A_OSM); }
      }
      filt(m.layer, stF(st)); tone(m, st === "ciemna" || st === "czarna");
      try { document.dispatchEvent(new Event("qmapchange")); } catch (e) {}
      return;
    }
    var w = want(); tone(m, w !== "osm");
    if (m.mode === w) return;
    var ac = m.map.attributionControl;
    if ((w === "carto" || w === "voyager") && !ac) {   // strona mogla wylaczyc podpisy - przy CARTO sa obowiazkowe
      ac = L.control.attribution({ prefix: false, position: "bottomright" }).addTo(m.map);
      m.map.attributionControl = ac; attrLast(ac);
    }
    if (ac) {
      ac.removeAttribution(A_OSM); ac.removeAttribution(A_CARTO);
      ac.addAttribution(w === "carto" || w === "voyager" ? A_CARTO : A_OSM);
    }
    m.mode = w; m.errs = 0;
    if (w === "carto") {
      seturl(m, C_BASE + encodeURIComponent(KEY));
      filt(m.layer, F_BASE);
      if (!m.labels) {
        m.labels = L.tileLayer(C_LAB + encodeURIComponent(KEY), { maxZoom: 19, pane: labPane(m.map) });
        m.labels.on("tileerror", function () { onErr(m); });
        m.labels.on("add", function () { filt(m.labels, F_LAB); });
      }
      if (!m.map.hasLayer(m.labels)) m.labels.addTo(m.map);
      filt(m.labels, F_LAB);
    } else if (w === "voyager") {
      seturl(m, VOY + encodeURIComponent(KEY));
      filt(m.layer, F_NIGHT);
      if (m.labels && m.map.hasLayer(m.labels)) m.map.removeLayer(m.labels);
    } else {
      seturl(m, OSM);
      filt(m.layer, w === "osmdark" ? F_NIGHT : ((m.opt.dayGray && !dark()) ? F_DAYGRAY : ""));
      if (m.labels && m.map.hasLayer(m.labels)) m.map.removeLayer(m.labels);
    }
    document.documentElement.classList.toggle("qmap-carto", w === "carto");
    document.documentElement.classList.toggle("qmap-night", w !== "osm");
    try { document.dispatchEvent(new Event("qmapchange")); } catch (e) {}
  }
  /* 2026-10-07: zmiana podkladu = zdjecie i ponowne dodanie warstwy. Samo setUrl() przy ulamkowym zoomie (Planer, fitBounds)
     wywoluje redraw() Leafleta 1.9 bez zaokraglenia -> adresy kafli typu /9.2046/325/198 (OSM ich nie zna). */
  function seturl(m, url) {
    var mp = m.map, ly = m.layer;
    if (!mp.hasLayer(ly)) { ly.setUrl(url, true); return; }
    mp.removeLayer(ly); ly.setUrl(url, true); mp.addLayer(ly);
  }
  function onErr(m) { if ((m.mode === "carto" || m.mode === "voyager") && ++m.errs >= 8) { BROKEN = true; maps.forEach(apply); } }

  function byMap(map) { return maps.filter(function (x) { return x.map === map; })[0] || null; }
  window.qTilesMaps = function () { return maps.map(function (x) { return x.map; }); };
  window.qTilesState = function (map) { var m = byMap(map); return m ? (m.st || (dark() ? "ciemna" : "szara")) : null; };
  window.qTilesCycle = function (map) {   // kolor -> szara -> ciemna -> czarna -> kolor
    var m = byMap(map); if (!m) return null;
    var o = ["kolor", "szara", "ciemna", "czarna"], c = m.st || (dark() ? "ciemna" : "szara");
    m.st = o[(o.indexOf(c) + 1) % 4]; apply(m); return m.st;
  };
  window.qTilesNightColor = function (on) { NIGHT_COLOR = !!on; maps.forEach(apply); };
  window.qTilesIsNightColor = function () { return NIGHT_COLOR; };
  window.qTilesAttach = function (map, layer, opt) {
    if (!map || !layer) return;
    var m = { map: map, layer: layer, mode: "osm", errs: 0, labels: null, opt: opt || {} };
    if (m.opt.dayGray && !dark()) filt(layer, F_DAYGRAY);
    maps.push(m); zoomOpts(map); zoomBR(m);
    layer.on("tileerror", function () { onErr(m); });
    layer.on("add load", function () { if (layer._qf != null) filt(layer, layer._qf); });
    cfg().then(function () { apply(m); });
  };

  /* === 2026-10-07 PRZYCISKI MAPY (wszystkie strony z mapa, tylko komputer > 820 px) ===
     Przyciski strony (Wysrodkuj, Mapa, Kwadraty...) + przybliz/oddal w JEDNYM stosie w prawym dolnym rogu mapy (kontrolki Leafleta
     bottomright: od dolu podpis, +/-, przyciski). Kolory wg tonu MAPY: klasa .qm-dark na kontenerze mapy, gdy podklad ciemny.
     Strona przekazuje swoj kontener: if(window.qMapCtl)window.qMapCtl(element[, map]). Telefon: bez zmian (uklad stron). */
  function DESK() { return !!(window.matchMedia && window.matchMedia("(min-width: 821px)").matches); }
  try { var _cs = document.createElement("style"); _cs.textContent = ".qmap-ctl{display:flex;flex-direction:column;align-items:flex-end;gap:6px;margin-bottom:6px!important;clear:both}.qmap-ctl>*{position:static!important;inset:auto!important;transform:none!important;background:none!important;box-shadow:none!important;border:0!important;padding:0!important;margin:0!important;max-width:none!important;width:auto!important;display:flex!important;flex-direction:column!important;flex-wrap:nowrap!important;align-items:flex-end!important;gap:6px!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important}.qmap-ctl button,.leaflet-control-zoom.qmap-zoom a{background:rgba(255,253,248,.96)!important;color:#2a241c!important;border:1px solid #d9cfbd!important;box-shadow:0 2px 8px rgba(0,0,0,.18)!important}.qmap-ctl button{font-family:inherit;font-size:14px!important;font-weight:500;line-height:1.2;padding:8px 13px!important;border-radius:10px!important;cursor:pointer;white-space:nowrap;min-height:0!important}.qmap-ctl span{font-size:12px}.leaflet-control-zoom.qmap-zoom{border:0!important;box-shadow:none!important;background:none!important;display:flex;flex-direction:column;gap:6px;margin-bottom:6px!important}.leaflet-control-zoom.qmap-zoom a{width:36px!important;height:36px!important;line-height:34px!important;font-size:20px!important;border-radius:10px!important;text-decoration:none}.qm-dark .qmap-ctl{color:#e9e4da}.qm-dark .qmap-ctl button,.qm-dark .leaflet-control-zoom.qmap-zoom a{background:rgba(18,20,26,.92)!important;color:#e9e4da!important;border-color:#5a3a20!important}.qmap-ctl button:hover,.leaflet-control-zoom.qmap-zoom a:hover{filter:brightness(1.12)}"; document.head.appendChild(_cs); } catch (e) {}
  var pendCtl = [];
  function attrLast(ac) { try { var n = ac.getContainer(); n.parentNode.appendChild(n); } catch (e) {} }   // podpis zawsze na samym dole rogu, pod +/- i przyciskami
  function tone(m, isDark) { try { m.map.getContainer().classList.toggle("qm-dark", !!isDark); } catch (e) {} }
  function placeCtl(map, el) {
    var C = L.Control.extend({ options: { position: "bottomright" }, onAdd: function () {
      var d = L.DomUtil.create("div", "qmap-ctl"); d.appendChild(el);
      L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d); return d; } });
    new C().addTo(map);
  }
  /* 2026-10-08 DOPASOWANIE MAPY POD NAKLADKI (wszystkie strony): qFitPad(map[, margines]) -> opcje dla map.fitBounds.
     Skanuje WIDOCZNE elementy fixed/absolute nachodzace na mape (panele, okna sekcji, wykres, legenda) w chwili wywolania
     i zwraca marginesy tak, zeby trasa/odcinek wypelnialy WOLNA czesc mapy (nie wchodzily pod otwarte okno).
     Pomija: elementy wewnatrz mapy (kontrolki Leafleta), przodkow mapy, menu, okno klodki, male elementy (< 15000 px2). */
  window.qFitPad = function (map, base) {
    base = base == null ? 20 : base;
    var c = map.getContainer(), m = c.getBoundingClientRect(), mcx = (m.left + m.right) / 2, mcy = (m.top + m.bottom) / 2;
    var pl = base, pt = base, pr = base, pb = base, seen = [], all = document.body.querySelectorAll("*");
    for (var i = 0; i < all.length; i++) {
      var e = all[i];
      if (c.contains(e) || e.contains(c) || (e.closest && e.closest(".qmod,.qnav"))) continue;
      var dup = false; for (var j = 0; j < seen.length; j++) if (seen[j].contains(e)) { dup = true; break; }
      if (dup) continue;
      var cs = getComputedStyle(e);
      /* nakladki: fixed/absolute/sticky oraz relative z jawnym z-index (np. pasek z nazwa trasy w Analizie trasy lezy nad mapa) */
      if ((cs.position !== "fixed" && cs.position !== "absolute" && cs.position !== "sticky" && !(cs.position === "relative" && cs.zIndex !== "auto")) || cs.display === "none" || cs.visibility === "hidden" || +cs.opacity === 0) continue;
      var r = e.getBoundingClientRect(), ix = Math.min(r.right, m.right) - Math.max(r.left, m.left), iy = Math.min(r.bottom, m.bottom) - Math.max(r.top, m.top);
      if (ix <= 0 || iy <= 0 || ix * iy < 15000) continue;
      seen.push(e);
      var cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2;
      /* panel boczny: po ktorej stronie sie ZACZYNA (lewa krawedz w lewej polowie mapy = panel z lewej) */
      if (iy > m.height * 0.3 && ix < m.width * 0.6) { if (r.left < mcx) pl = Math.max(pl, r.right - m.left + base); else pr = Math.max(pr, m.right - r.left + base); }
      else if (ix > m.width * 0.3) { if (cy >= mcy) pb = Math.max(pb, m.bottom - r.top + base); else pt = Math.max(pt, r.bottom - m.top + base); }
    }
    var minW = m.width * 0.25, minH = m.height * 0.25;   // zawsze zostaw min. 25% mapy na trase
    if (m.width - pl - pr < minW) { var k = (m.width - minW) / (pl + pr); pl *= k; pr *= k; }
    if (m.height - pt - pb < minH) { var k2 = (m.height - minH) / (pt + pb); pt *= k2; pb *= k2; }
    return { paddingTopLeft: [Math.round(pl), Math.round(pt)], paddingBottomRight: [Math.round(pr), Math.round(pb)] };
  };

  /* 2026-10-07 PRECYZJA I PLYNNOSC ZOOMU (wszystkie mapy): przyblizenie co 0.1 poziomu (zamiast pelnych poziomow = 2x),
     wiec "Cala trasa"/fitBounds wypelnia ekran prawie dokladnie; kolko/gladzik wolniej (120 px na poziom), +/- co pol poziomu.
     Strona z zoomSnap 0 (Planer = calkiem plynnie) zostaje przy swoim. */
  function zoomOpts(map) {
    var o = map.options;
    if (o.zoomSnap !== 0) o.zoomSnap = 0.1;
    o.zoomDelta = 0.5; o.wheelPxPerZoomLevel = 120;
  }
  function zoomBR(m) {
    if (!DESK() || m.zoomBR) return; m.zoomBR = true;
    if (m.map.zoomControl) { try { m.map.removeControl(m.map.zoomControl); } catch (e) {} m.map.zoomControl = null; }
    [].forEach.call(m.map.getContainer().querySelectorAll(".leaflet-control-zoom"), function (z) { z.parentNode.removeChild(z); });
    var z = L.control.zoom({ position: "bottomright", zoomInTitle: "Przybliż", zoomOutTitle: "Oddal" }).addTo(m.map);
    z.getContainer().classList.add("qmap-zoom");
    while (pendCtl.length) placeCtl(m.map, pendCtl.shift());
  }
  window.qMapCtl = function (el, map) {
    if (!el || !DESK()) return;
    if (!map) { var f = maps[0]; map = f && f.map; }
    if (!map) { pendCtl.push(el); return; }
    var m = byMap(map); if (m && !m.zoomBR) zoomBR(m);
    placeCtl(map, el);
  };

  try {
    new MutationObserver(function () { maps.forEach(apply); })
      .observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  } catch (e) {}
})();
