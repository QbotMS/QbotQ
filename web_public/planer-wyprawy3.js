/* planer-wyprawy3.js (2026-10-07) - Planer wyprawy v3: uklad jak Raport z jazdy v3.
   Logika planera bez zmian: planer-wyprawy2-render.js (te same identyfikatory DOM).
   Lewy panel: parametry + "Cala trasa" + karty etapow | pasek ikon. Klik ikony: panel zwija sie do ikon,
   obok okno sekcji (do malej mapy po prawej; Wyposazenie - caly ekran), profil chowa sie, trasa przesuwa sie
   w wolne miejsce. Ikony: zestaw TRASA albo DZIEN (wybrany etap, body.pv-day).
   v2: przyciski mapy (wysrodkuj, styl mapy, kwadraty), zapisana wersja wyprawy wczytywana bez przeliczen,
   pogoda dnia tylko dla dnia, zaopatrzenie w opisie dnia, GPX dnia w Narzedziach, "Udostepnij" -> "Narzedzia". */
(function () {
  "use strict";
  var $ = function (i) { return document.getElementById(i); };
  var SV = function (p) { return '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + p + '</svg>'; };
  var IC = {
    split: '<circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12"/><path d="M20 4 8.12 15.88"/><circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/>',
    activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    cloud: '<path d="M12 2v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="M20 12h2"/><path d="m19.07 4.93-1.41 1.41"/><path d="M15.95 12.65a4 4 0 0 0-5.93-4.13"/><path d="M13 22H7a5 5 0 1 1 4.9-6H13a3 3 0 0 1 0 6Z"/>',
    radar: '<path d="M19.07 4.93A10 10 0 0 0 6.99 3.34"/><path d="M2.29 9.62A10 10 0 1 0 21.31 8.35"/><path d="M16.24 7.76A6 6 0 1 0 8.23 16.67"/><path d="M17.99 11.66A6 6 0 0 1 15.77 16.67"/><circle cx="12" cy="12" r="2"/><path d="m13.41 10.59 5.66-5.66"/>',
    book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    landmark: '<line x1="3" x2="21" y1="22" y2="22"/><line x1="6" x2="6" y1="18" y2="11"/><line x1="10" x2="10" y1="18" y2="11"/><line x1="14" x2="14" y1="18" y2="11"/><line x1="18" x2="18" y1="18" y2="11"/><polygon points="12 2 20 7 4 7"/>',
    layers: '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    mountain: '<path d="m8 3 4 8 5-5 5 15H2L8 3z"/>',
    pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
    pack: '<path d="M4 10a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z"/><path d="M8 10h8"/><path d="M8 18h8"/><path d="M8 22v-6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v6"/><path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/>',
    tools: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    chev: '<path d="m9 18 6-6-6-6"/>',
    shirt: '<path d="M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"/>'
  };
  var NARZ = "Narzędzia: wersje, kalendarz, PDF, GPX, e-mail";
  var TRIP = [
    { k: "forma", ic: "activity", c: "#f07878", lab: "Ocena formy", s: ["forma"] },
    { k: "pogoda", ic: "cloud", c: "#e0a44a", lab: "Pogoda (dzień po dniu)", s: ["pogoda"] },
    { k: "monitor", ic: "radar", c: "#d9a6f0", lab: "Monitor pogody przed wyjazdem", s: ["frame"], url: "monitor" },
    { k: "opis", ic: "book", c: "#7fc8d8", lab: "Opis trasy", s: ["opis"] },
    { k: "tlo", ic: "landmark", c: "#c9b98f", lab: "Tło historyczne i przyrodnicze", s: ["tlo"] },
    { k: "ubior", ic: "shirt", c: "#c9b98f", lab: "Ubiór na wyprawę", s: ["ubior"] },
    { k: "wyp", ic: "pack", c: "#f0975a", lab: "Wyposażenie", s: ["frame"], url: "wyp", full: true },
    null,
    { k: "narz", ic: "tools", c: "#b9c0cc", lab: NARZ, s: ["udost"] }
  ];
  var DAY = [
    { k: "d-opis", ic: "book", c: "#7fc8d8", lab: "Opis dnia, nocleg i zaopatrzenie", s: ["dzien"], ds: "d-interp d-resupply", cards: true },
    { k: "d-teren", ic: "mountain", c: "#a4c56f", lab: "Nawierzchnia i podjazdy dnia", s: ["dzien"], ds: "d-surface d-climbs" },
    { k: "d-atrakcje", ic: "pin", c: "#f08ac0", lab: "Atrakcje dnia", s: ["dzien"], ds: "d-attr" },
    { k: "d-pogoda", ic: "cloud", c: "#e0a44a", lab: "Pogoda dnia", s: ["pogoda"], dayOnly: true },
    null,
    { k: "d-narz", ic: "tools", c: "#b9c0cc", lab: NARZ, s: ["dzien", "udost"], ds: "d-gpx" }
  ];
  var ALL = {}; TRIP.concat(DAY).forEach(function (x) { if (x) ALL[x.k] = x; });
  var body = document.body, rail = $("pl-rail"), winb = $("pl-winb"), cur = null;

  function isDay() { return body.classList.contains("pv-day"); }
  function dayNo() { var on = document.querySelector("#viewtabs .viewtab.on"); var v = on && on.getAttribute("data-v"); return (v && v !== "all") ? (parseInt(v, 10) + 1) : null; }
  function buildRail() {
    var set = isDay() ? DAY : TRIP, d = dayNo();
    var h = '<button type="button" id="pl-expand" class="pl-exp" title="Pokaż panel wyprawy" aria-label="Pokaż panel wyprawy">' + SV(IC.chev) + '</button>';
    h += '<div class="pl-tag">' + (isDay() && d ? "D" + d : "TRASA") + '</div>';
    set.forEach(function (x) {
      if (!x) { h += '<div class="pl-sep"></div>'; return; }
      h += '<button type="button" class="pl-ic' + (cur === x.k ? " on" : "") + '" data-k="' + x.k + '" title="' + x.lab + '" aria-label="' + x.lab + '" style="--c:' + x.c + '">' + SV(IC[x.ic]) + '</button>';
    });
    rail.innerHTML = h;
  }
  /* przesuniecie trasy w wolne miejsce: po zmianie ukladu (bez animacji, ale z zapasem na przeliczenie) */
  var STAGE_COLORS = ["#4cb4ff", "#ff7a1a", "#3ddc84", "#c77dff", "#ff5a6e", "#22d3ee"];   // jak w logice planera (kolory dni)
  function vis(id) { var e = $(id); if (!e) return null; var cs = getComputedStyle(e); if (cs.display === "none") return null; var r = e.getBoundingClientRect(); return (r.width && r.height) ? r : null; }
  /* dopasowanie: cala trasa albo wybrany dzien, do czesci mapy niezaslonietej panelem/oknem, profilem i przyciskami mapy */
  function myFit() {
    var m = (window.qTilesMaps && window.qTilesMaps()[0]) || null; if (!m || typeof L === "undefined") return;
    var d = isDay() ? dayNo() : null, col = d ? STAGE_COLORS[(d - 1) % STAGE_COLORS.length] : null, b = null;
    m.eachLayer(function (l) {
      if (!(l instanceof L.Polyline) || l instanceof L.Polygon || !l.options || (l.options.weight || 0) < 3) return;
      if (col && String(l.options.color).toLowerCase() !== col) return;
      var lb = l.getBounds(); if (!lb.isValid()) return; b = b ? b.extend(lb) : L.latLngBounds(lb.getSouthWest(), lb.getNorthEast());
    });
    if (!b) return;
    try { m.invalidateSize(false); } catch (e) {}
    var mr = vis("map"), pv = vis("pv-panel"), pf = vis("profil"), mc = vis("pl-mapctl");
    if (!mr) return;
    var phone = window.matchMedia && window.matchMedia("(max-width: 820px)").matches;
    var padL = phone ? 16 : (pv ? Math.max(24, Math.round(pv.right - mr.left) + 24) : 24);
    var padB = phone ? (pv ? Math.max(24, Math.round(mr.bottom - pv.top) + 16) : 24) : (pf ? Math.max(24, Math.round(mr.bottom - pf.top) + 24) : 24);
    var padT = mc ? Math.round(mc.bottom - mr.top) + (phone ? 8 : 12) : 24;
    m.fitBounds(b, { paddingTopLeft: [padL, padT], paddingBottomRight: [24, padB] });
  }
  window.__planerRefitAny = myFit;
  function refit() { [150, 500].forEach(function (ms) { setTimeout(function () { try { myFit(); } catch (e) {} }, ms); }); }
  function frameUrl(x) {
    var sel = $("route"), rid = sel ? sel.value : "", n = ($("dval") || {}).textContent || "", dt = ($("wyprawa-data") || {}).value || "";
    if (x.url === "wyp") return "/planer-wyposazenia.html?route=" + encodeURIComponent(rid) + "&days=" + encodeURIComponent(n) + "&embed=1";
    return "/pogoda-wyprawy.html?route=" + encodeURIComponent(rid) + "&days=" + encodeURIComponent(n) + "&start=" + encodeURIComponent(dt) + "&embed=1";
  }
  function open(k) {
    var x = ALL[k]; if (!x) return;
    cur = k;
    body.classList.add("pl-open");
    body.classList.toggle("pl-full", !!x.full);
    $("pl-wint").innerHTML = '<span style="color:' + x.c + ';display:inline-flex">' + SV(IC[x.ic]) + '</span>' + x.lab.replace(/:.*$/, "").replace(/,.*$/, "") + (isDay() && dayNo() ? ' <small>· Dzień ' + dayNo() + '</small>' : "");
    [].forEach.call(winb.querySelectorAll(".pl-s"), function (s) { s.style.display = (x.s.indexOf(s.getAttribute("data-s")) >= 0) ? "" : "none"; });
    winb.setAttribute("data-ds", x.ds || "");
    winb.classList.toggle("pl-cards", !!x.cards);
    winb.removeAttribute("data-pgday");
    if (x.s.indexOf("pogoda") >= 0) { try { window.__planerPogoda && window.__planerPogoda(); } catch (e) {} setTimeout(pgButtons, 50); }
    if (x.k === "forma") loadForma();
    if (x.k === "ubior") loadUbior(0);
    if (x.s.indexOf("frame") >= 0) { var f = $("pl-frame"), u = frameUrl(x); if (f.getAttribute("src") !== u) f.setAttribute("src", u); }
    winb.scrollTop = 0;
    buildRail(); refit();
  }
  function close() {
    cur = null; body.classList.remove("pl-open", "pl-full"); winb.removeAttribute("data-pgday"); buildRail(); refit();
  }
  rail.addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (!b) return;
    if (b.id === "pl-expand") { close(); return; }
    var k = b.getAttribute("data-k"); if (!k) return;
    if (cur === k) close(); else open(k);
  });
  $("pl-winx").onclick = close;
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && cur) close(); });

  /* "Cala trasa" = widok calosci (przycisk ALL z ukrytych zakladek planera) */
  $("pl-all").onclick = function () { var a = document.querySelector('#viewtabs .viewtab[data-v="all"]'); if (a) a.click(); };
  function routeName() { var sel = $("route"); return (sel && sel.options[sel.selectedIndex]) ? sel.options[sel.selectedIndex].text : ""; }
  function syncAll() {
    var t = routeName(), n = ($("dval") || {}).textContent || "";
    $("pl-allsub").textContent = (t ? t.replace(/^\[Q\]\s*/, "").replace(/ · \d{4}-\d{2}-\d{2} · #\d+/, "") : "wybierz trasę") + (n ? " · " + n + " dni" : "");
    $("pl-all").classList.toggle("on", !isDay());
    var d = dayNo();
    [].forEach.call(document.querySelectorAll("#etap-cards .ecard"), function (c) { c.classList.toggle("on", isDay() && d != null && parseInt(c.getAttribute("data-day"), 10) === d - 1); });
  }
  var lastDay = null;
  function onView() {
    var nd = isDay() ? dayNo() : null;
    if (nd !== lastDay) {
      var wasDay = lastDay != null, nowDay = nd != null;
      lastDay = nd;
      if (cur && (wasDay !== nowDay)) close(); else if (cur) open(cur); else buildRail();
      refit();
    }
    syncAll();
  }
  new MutationObserver(onView).observe(body, { attributes: true, attributeFilter: ["class"] });
  var vt = $("viewtabs"); if (vt) new MutationObserver(onView).observe(vt, { childList: true, subtree: true, attributes: true });
  var _etT = null;
  var et = $("etap-cards"); if (et) new MutationObserver(function () { syncAll(); clearTimeout(_etT); _etT = setTimeout(refit, 300); }).observe(et, { childList: true });
  var dv = $("dval"); if (dv) new MutationObserver(syncAll).observe(dv, { childList: true, characterData: true, subtree: true });

  /* zapisana wersja wyprawy (podzial + opisy dni + noclegi z DOSTOSUJ) - wczytaj zamiast liczyc od nowa */
  function useSaved() {
    var dost = $("dostosuj"); if (!dost || dost.disabled) return;          // juz dopasowane (wersja/szkic wczytany)
    var nm = routeName(); if (!nm) return;
    var hit = [].filter.call(document.querySelectorAll("#tools-body .tw-ver-load"), function (b) {
      var sub = b.querySelector(".tw-ver-sub"); return sub && sub.textContent.trim() === nm.trim();
    })[0];
    if (hit) hit.click();
  }
  var rs = $("route");
  if (rs) rs.addEventListener("change", function () { setTimeout(syncAll, 300); [2500, 5000].forEach(function (ms) { setTimeout(useSaved, ms); }); });
  setTimeout(useSaved, 4000);

  /* przyciski mapy: wysrodkuj, styl mapy (kolor/szara/ciemna/czarna), kwadraty trasy */
  var mc = document.createElement("div"); mc.id = "pl-mapctl";
  mc.innerHTML = '<button type="button" id="pl-fit">Wyśrodkuj trasę</button><button type="button" id="pl-style">Mapa</button><button type="button" id="pl-sq">Kwadraty: wł</button><span id="pl-sqn"></span>';
  document.body.appendChild(mc);
  function theMap() { var ms = window.qTilesMaps ? window.qTilesMaps() : []; return ms[0] || null; }
  function isPhone() { return !!(window.matchMedia && window.matchMedia("(max-width: 820px)").matches); }
  function styleLab() {
    var m = theMap(), st = (m && window.qTilesState) ? window.qTilesState(m) : null, ph = isPhone();
    $("pl-style").textContent = ph ? ("Mapa: " + (st || "—")) : ("Mapa: " + (st || "—"));
    $("pl-fit").textContent = ph ? "Środek" : "Wyśrodkuj trasę";
    $("pl-sq").textContent = (ph ? "Kw.: " : "Kwadraty: ") + (sqOn ? "wł" : "wył");
  }
  $("pl-fit").onclick = function () { myFit(); };
  $("pl-style").onclick = function () { var m = theMap(); if (m && window.qTilesCycle) window.qTilesCycle(m); styleLab(); };
  document.addEventListener("qmapchange", styleLab);
  var sqOn = true, sqGrp = null, sqRid = null;
  var COL = { "new": { color: "#1a7f37", fill: "#2ea043", fo: 0.38 }, keep: { color: "#1f6feb", fill: "#388bfd", fo: 0.22 } };
  function loadSquares() {
    var m = theMap(), rid = rs ? rs.value : ""; if (!m || !rid || typeof L === "undefined") return;
    if (!sqGrp) { if (!m.getPane("plsq")) { m.createPane("plsq"); m.getPane("plsq").style.zIndex = 350; } sqGrp = L.layerGroup([], { pane: "plsq" }); }
    if (sqRid === rid) { if (sqOn) sqGrp.addTo(m); return; }
    sqRid = rid; sqGrp.clearLayers(); $("pl-sqn").textContent = "";
    fetch("/api/routes/" + encodeURIComponent(rid) + "/tiles?margin=3", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (!d || sqRid !== rid) return;
      (d.tiles || []).forEach(function (t) { var s = COL[t.status]; if (!s) return; L.rectangle(t.bounds, { pane: "plsq", color: s.color, weight: 1, fillColor: s.fill, fillOpacity: s.fo, interactive: false }).addTo(sqGrp); });
      if (d.counts) $("pl-sqn").textContent = "+" + d.counts["new"] + " nowych / " + d.counts.keep + " masz";
      if (sqOn) sqGrp.addTo(m);
    }).catch(function () {});
  }
  $("pl-sq").onclick = function () {
    sqOn = !sqOn; styleLab();
    var m = theMap(); if (!m || !sqGrp) { loadSquares(); return; }
    if (sqOn) sqGrp.addTo(m); else m.removeLayer(sqGrp);
  };
  if (rs) rs.addEventListener("change", function () { setTimeout(loadSquares, 1500); });
  setTimeout(function () { loadSquares(); styleLab(); }, 2500);

  /* wysokosc profilu -> dol panelu */
  var pf = $("profil");
  function geo() { if (pf && pf.offsetHeight) document.documentElement.style.setProperty("--pfh", pf.offsetHeight + "px"); }
  try { if (window.ResizeObserver && pf) new ResizeObserver(geo).observe(pf); } catch (e) {}
  geo();
  buildRail(); syncAll();
  /* --- pogoda: po przeliczeniu przyciski dni obok "Policz wszystkie dni"; klik = prognoza tego dnia --- */
  var pgPanel = $("pogoda-panel"), pgSel = 0;
  function pgButtons() {
    if (!pgPanel) return;
    var days = [].slice.call(pgPanel.querySelectorAll(".pg-day")), bar = $("pl-pgdays");
    if (!days.length) { if (bar) bar.remove(); return; }
    var btn = [].filter.call(pgPanel.querySelectorAll("button"), function (b) { return /Policz wszystkie dni/i.test(b.textContent); })[0];
    if (!bar) { bar = document.createElement("div"); bar.id = "pl-pgdays"; if (btn && btn.parentNode) btn.parentNode.insertBefore(bar, btn.nextSibling); else pgPanel.insertBefore(bar, pgPanel.firstChild); }
    if (isDay() && dayNo()) pgSel = dayNo() - 1;
    if (pgSel >= days.length) pgSel = 0;
    var html = days.map(function (d, i) { return '<button type="button" data-i="' + i + '" class="' + (i === pgSel ? "on" : "") + '">Dzień ' + (i + 1) + '</button>'; }).join("");
    if (bar.getAttribute("data-h") !== html) { bar.innerHTML = html; bar.setAttribute("data-h", html); }
    winb.setAttribute("data-pgday", String(pgSel));
  }
  if (pgPanel) {
    new MutationObserver(function () { if (!pgPanel.__busy) { pgPanel.__busy = true; try { pgButtons(); } finally { pgPanel.__busy = false; } } }).observe(pgPanel, { childList: true, subtree: true });
    pgPanel.addEventListener("click", function (e) { var b = e.target.closest("#pl-pgdays button"); if (!b) return; pgSel = parseInt(b.getAttribute("data-i"), 10) || 0; var bar = $("pl-pgdays"); if (bar) bar.removeAttribute("data-h"); pgButtons(); });
  }
  /* --- atrakcje dnia: jedna otwarta naraz (szczegol obok listy) --- */
  winb.addEventListener("click", function (e) {
    var row = e.target.closest("#d-attr .attr-row"); if (!row) return;
    [].forEach.call(document.querySelectorAll("#d-attr .attr-row"), function (r) { r.classList.toggle("on", r === row); if (r !== row) { var n = r.nextElementSibling; if (n && n.classList.contains("attr-detail")) n.style.display = "none"; } });
  }, true);


  /* --- Ocena formy v3: /api/planer/forma-plus (sciany + forma na start z planu TRENERA + tydzien przed + porownanie z jazdami) --- */
  function esc(x) { return String(x == null ? "" : x).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function n0(v) { return (v == null || isNaN(v)) ? "—" : Math.round(v); }
  function sg(v) { return (v == null || isNaN(v)) ? "—" : (v > 0 ? "+" : "") + Math.round(v); }
  function cutsNow() {
    var ks = [].map.call(document.querySelectorAll("#etap-cards .ecard .ec-km"), function (e) { var m = (e.textContent || "").match(/(\d+)\s*[–-]\s*(\d+)/); return m ? +m[2] : null; });
    return ks.slice(0, Math.max(0, ks.length - 1)).filter(function (x) { return x != null; });
  }
  var fmSeq = 0;
  function loadForma() {
    var box = $("pl-forma"); if (!box) return;
    var rid = rs ? rs.value : "", dep = ($("wyprawa-data") || {}).value || "";
    if (!rid) { box.innerHTML = '<p class="muted">Wybierz trasę.</p>'; return; }
    box.innerHTML = '<p class="muted">Liczę ocenę formy…</p>';
    var seq = ++fmSeq;
    fetch("/api/planer/forma-plus", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route_id: rid, cuts: cutsNow(), departure: dep || null, mode: "normalny" }) })
      .then(function (r) { return r.ok ? r.json() : null; }).then(function (d) { if (seq === fmSeq) renderForma(d); })
      .catch(function () { if (seq === fmSeq) box.innerHTML = '<p class="muted">Błąd pobierania oceny formy.</p>'; });
  }
  function renderForma(d) {
    var box = $("pl-forma"); if (!d || !d.ok) { box.innerHTML = '<p class="muted">Brak danych oceny formy.</p>'; return; }
    var f = d.feasibility || {}, p = d.plus || {}, td = p.today || {}, st = p.start, ce = f.ceilings || {}, sim = (p.sim && p.sim.days) || [];
    var col = { green: "var(--good)", yellow: "var(--warn)", red: "var(--bad)" };
    var head = (f.verdict || "").split(".")[0];
    var h = '<div class="fm-verd" style="border-color:' + (/przeladowany/i.test(head) ? "var(--bad)" : (/ambitny/i.test(head) ? "var(--warn)" : "var(--good)")) + '"><b>' + esc(head || "Ocena formy") + '</b>' +
      (f.departure ? '<span>wyjazd ' + esc(f.departure) + ' · za ' + n0(f.days_ahead) + ' dni</span>' : '<span>ustaw datę wyprawy, by policzyć formę na start</span>') + '</div>';
    h += '<div class="fm-tiles">' +
      '<div class="fm-t"><div class="lab">Forma dziś</div><div class="val">' + n0(td.ctl) + ' <small>CTL</small></div><div class="sub">świeżość ' + sg(td.tsb) + ' · zmęczenie ' + n0(td.atl) + '</div></div>' +
      (st ? '<div class="fm-t"><div class="lab">Forma na start</div><div class="val">' + n0(st.ctl) + ' <small>CTL</small></div><div class="sub">świeżość ' + sg(st.tsb) + ' · ' + esc(st.source) + (st.planned_xss ? ' (' + n0(st.planned_xss) + ' XSS)' : '') + '</div></div>' : '') +
      '<div class="fm-t"><div class="lab">Wyprawa</div><div class="val">' + n0(f.total_xss) + ' <small>XSS</small></div><div class="sub">średnio ' + n0(f.avg_daily_xss) + '/dzień · sufit tygodnia ~' + n0(ce.week_avg) + '</div></div>' +
      '<div class="fm-t"><div class="lab">Twoje ściany</div><div class="val">' + n0(ce.day_demonstrated) + ' <small>rekord</small></div><div class="sub">metaboliczna ~' + n0(ce.day_metabolic) + ' XSS/dzień</div></div></div>';
    var stg = p.stages || [];
    if (stg.length) {
      h += '<div class="fm-h">Dni wyprawy</div><table class="fm-tab"><tr><th>dzień</th><th>XSS</th><th>ściana</th><th>świeżość rano</th><th>na tle Twoich jazd (365 dni)</th></tr>';
      stg.forEach(function (s, i) {
        var w = (f.walls || [])[i] || {}, sd = sim[i] || {};
        h += '<tr><td>Dzień ' + s.day + '</td><td><b>' + n0(s.xss) + '</b></td><td><span style="color:' + (col[w.color] || "inherit") + '">● ' + esc(w.label || "—") + '</span></td><td>' + sg(sd.tsb_morning) + '</td><td>' +
          (s.harder_rides === 0 ? '<b>najcięższa jazda roku</b>' : (s.harder_rides + ' z ' + s.rides_365 + ' jazd było równie lub bardziej obciążających')) + '</td></tr>';
      });
      h += '</table>';
    }
    if ((p.summary || []).length) h += '<div class="fm-h">Podsumowanie</div><ul class="fm-ul">' + p.summary.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join("") + '</ul>';
    var wb = p.week_before || [];
    h += '<div class="fm-2"><div><div class="fm-h">Tydzień przed wyjazdem (TRENER)</div>' + (wb.length ? '<ul class="fm-ul">' + wb.map(function (w) { return '<li>' + esc(w.day.slice(5).split("-").reverse().join(".")) + ' · ' + esc(w.name) + (w.dur_min ? ' · ' + w.dur_min + '′' : '') + (w.xss != null ? ' · ' + n0(w.xss) + ' XSS' : '') + (w.status === "done" ? ' ✓' : '') + '</li>'; }).join("") + '</ul>' : '<p class="muted">Brak sesji w planie TRENERA.</p>') + '</div>';
    var tp = p.top || [];
    h += '<div><div class="fm-h">Twoje najcięższe jazdy (365 dni)</div>' + (tp.length ? '<ul class="fm-ul">' + tp.map(function (t) { return '<li>' + esc(t.date) + ' · ' + (t.km != null ? n0(t.km) + ' km · ' : '') + '<b>' + n0(t.xss) + '</b> XSS</li>'; }).join("") + '</ul>' : '<p class="muted">Brak danych.</p>') + '</div></div>';
    box.innerHTML = h;
  }

  /* --- Ubior na wyprawe: /api/planer/ubior (jeden modulowy zestaw na wszystkie dni) --- */
  function hoursNow() { var e = document.querySelector("#etap-cards .ecard .ec-sub"); var m = e && (e.textContent || "").match(/ruch\s*(\d+)h(\d+)/); return m ? (+m[1] + (+m[2]) / 60) : 0; }
  var ubSeq = 0;
  function loadUbior(regen) {
    var box = $("pl-ubior"); if (!box) return;
    var rid = rs ? rs.value : "", dep = ($("wyprawa-data") || {}).value || "", n = +(($("dval") || {}).textContent || 1);
    if (!rid || !dep) { box.innerHTML = '<p class="muted">Ustaw trasę i datę wyprawy.</p>'; return; }
    box.innerHTML = '<p class="muted">' + (regen ? "Dobieram ubiór z Twojej szafy (AI, ok. 30–60 s)…" : "Wczytuję…") + '</p>';
    var seq = ++ubSeq;
    var q = "?route_id=" + encodeURIComponent(rid) + "&start=" + encodeURIComponent(dep) + "&days=" + n + "&hours=" + hoursNow().toFixed(2) + "&style=lekko&regen=" + (regen ? 1 : 0);
    fetch("/api/planer/ubior" + q, { method: "POST", credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (seq === ubSeq) renderUbior(d); }).catch(function () { if (seq === ubSeq) box.innerHTML = '<p class="muted">Błąd połączenia.</p>'; });
  }
  function renderUbior(d) {
    var box = $("pl-ubior");
    var btn = '<button type="button" class="dbtn" id="pl-ub-go">' + (d && d.ok ? "Dobierz ponownie (AI)" : "Dobierz ubiór na wyprawę (AI)") + '</button>';
    if (!d || !d.ok || !(d.zestawy || []).length) {
      box.innerHTML = '<p class="muted">' + (d && d.ok && !(d.zestawy || []).length ? "Zapisany dobór jest w starym formacie — dobierz ponownie." : esc((d && !d.brak && d.blad) || "AI ułoży 2 zestawy z Twojego garażu na całą wyprawę — jedna garderoba na wszystkie dni, modułowo.")) + '</p>' + btn;
      $("pl-ub-go").onclick = function () { loadUbior(1); }; return;
    }
    var dd = (((d.warunki || {}).wyprawa || {}).dzien_po_dniu) || [], h = '';
    if (dd.length) h += '<div class="ub-strip">' + dd.map(function (x, i) { return '<span><b>Dzień ' + (i + 1) + '</b> ' + n0(x.tmin) + '–' + n0(x.tmax) + ' °C · ' + (x.precip_mm != null ? (+x.precip_mm).toFixed(1) : "—") + ' mm · do ' + (x.wind_max_ms != null ? (+x.wind_max_ms).toFixed(1) : "—") + ' m/s</span>'; }).join("") + '</div>';
    if (d.warunki_krotko) h += '<p class="ub-w">' + esc(d.warunki_krotko) + '</p>';
    if ((d.kontrola_uwagi || []).length) h += '<p class="ub-w" style="color:var(--warn)">⚠ Kontrola zestawu: ' + d.kontrola_uwagi.map(esc).join(" · ") + '</p>';
    if (d.z_historii) h += '<p class="ub-w">↻ ' + esc(d.z_historii) + '</p>';
    h += '<div class="ub-sets">' + d.zestawy.map(function (z, i) {
      var tp = z.tempo === "szybsza" ? "szybsza jazda" : (z.tempo === "spokojniejsza" ? "spokojniejsza jazda" : "");
      var x = '<div class="ub-set"><div class="ub-t">' + (i === 0 ? "A" : "B") + ' · ' + (tp ? esc(tp) + ' · ' : '') + esc(z.nazwa || "") + '</div>' + (z.kiedy ? '<div class="ub-k">' + esc(z.kiedy) + '</div>' : '') +
        (z.po_co ? '<div class="ub-k"><b>Po co:</b> ' + esc(z.po_co) + '</div>' : '') + '<ul class="ub-l">' +
        (z.rzeczy || []).map(function (it) { return '<li><b>' + esc(it.nazwa) + '</b> <span class="ub-k">' + esc(it.kategoria || "") + (it.kolor ? ' · ' + esc(String(it.kolor).toLowerCase()) : '') + '</span><div class="ub-k">' + esc(it.dlaczego || "") + '</div>' +
          ((it.zamienniki || []).length ? '<div class="ub-k">zamiennie: ' + it.zamienniki.map(function (a) { return esc(a.nazwa) + (a.kolor ? ' (' + esc(String(a.kolor).toLowerCase()) + ')' : ''); }).join(", ") + '</div>' : '') + '</li>'; }).join("") + '</ul>';
      if ((z.do_kieszeni || []).length) x += '<div class="ub-sub">W torbie / kieszeni</div><ul class="ub-l">' + z.do_kieszeni.map(function (it) { return '<li><b>' + esc(it.nazwa) + '</b><div class="ub-k">' + esc(it.dlaczego || "") + '</div></li>'; }).join("") + '</ul>';
      if ((z.na_zmiane || []).length) x += '<div class="ub-sub">Na zmianę (zapas)</div><ul class="ub-l">' + z.na_zmiane.map(function (it) { return '<li><b>' + esc(it.nazwa) + '</b> <span class="ub-ile">×' + it.ile + '</span></li>'; }).join("") + '</ul>';
      if (z.kolory) x += '<div class="ub-z">🎨 ' + esc(z.kolory) + '</div>';
      if (z.zdejmij) x += '<div class="ub-z">⏱ ' + esc(z.zdejmij) + '</div>';
      if (z.slaby_punkt) x += '<div class="ub-z">⚠ ' + esc(z.slaby_punkt) + '</div>';
      return x + '</div>';
    }).join("") + '</div>';
    h += '<div class="ub-foot">' + (d.zapisany ? "Zapisany dobór" : "Nowy dobór") + (d.created_at ? " · " + esc(d.created_at.slice(0, 16).replace("T", " ")) : "") + ' · z ' + n0(d.kandydatow) + ' kandydatów z garażu · zestaw A trafia do listy Wyposażenia · ' + btn + '</div>';
    box.innerHTML = h; $("pl-ub-go").onclick = function () { loadUbior(1); };
  }
  var h0 = (location.hash || "").slice(1); if (ALL[h0] && TRIP.indexOf(ALL[h0]) >= 0) setTimeout(function () { open(h0); }, 1500);
})();
