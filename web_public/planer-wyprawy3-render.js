/* planer-wyprawy3-render.js - KOPIA planer-wyprawy2-render.js dla Planera v3 z poprawionymi marginesami mapy (2026-10-07). */
/* AUTO-GENEROWANY przez scripts/build_planer2_mock.py z planer-wyprawy-render.js.
   NIE edytuj recznie - zmien zrodlo albo latki w skrypcie i uruchom ponownie. */
/* czas lokalny (strefa przegladarki) -- wspolne dla QBot lab */function qTsLocal(s,naiveUtc){if(!s)return"";var t=String(s).trim().replace(" ","T").replace(/\.\d+/,"");if(/[+-]\d\d$/.test(t))t+=":00";t=t.replace(/([+-]\d\d)(\d\d)$/,"$1:$2");if(!/(Z|[+-]\d\d:\d\d)$/i.test(t)){if(!naiveUtc)return t.slice(0,16).replace("T"," ");t+="Z";}var d=new Date(t);if(isNaN(d.getTime()))return String(s).slice(0,16);var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());}function qDateLocal(d){d=d||new Date();var p=function(n){return("0"+n).slice(-2);};return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
/* Planer wyprawy — Etap 3 — v28 (wiele dziennych GPX; XSS + ocena formy + kalendarz + wspolne atrakcje)
   Fix realnej przyczyny: Leaflet getLatLng() zwraca {lat,lng}, a kod czytal [lat,lon]
   -> haversine dawal NaN -> znacznik spadal na 0 km (start). Teraz konwersja + guard. */
(function () {
  "use strict";
  var STAGE_COLORS = ["#4cb4ff", "#ff7a1a", "#3ddc84", "#c77dff", "#ff5a6e", "#22d3ee"];   // v3: intensywne, czytelne na ciemnej i jasnej mapie
  var MIN_GAP_KM = 1.0;

  var map, baseLayers = [], cutMarkers = [];
  var mapStiffened = false;
  var coords = [], cumKm = [];
  var spine = [], totalKm = 0;
  var nDays = 2, cuts = [];
  var noclegiShown = false;
  var profilHover = null;
  var dniData = null, dostosowano = false, openDay = -1;
  var currentView = null;  // null = ALL, int = dzien
  var feasData = null, feasSeq = 0, feasTimer = null, feasDeparture = "";
  var LS_HIST = "qbot_planer_hist", LS_DRAFT = "qbot_planer_draft";
  var _PQ = new URLSearchParams(location.search);
  var IS_PRINT = _PQ.get("print") === "1";

  function haversine(a, b) {
    var R = 6371, toR = Math.PI / 180;
    var dLat = (b[0] - a[0]) * toR, dLon = (b[1] - a[1]) * toR;
    var la1 = a[0] * toR, la2 = b[0] * toR;
    var h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  function llArr(ll) { return [ll.lat, ll.lng]; }   // Leaflet {lat,lng} -> [lat,lon]

  function buildCumKm() {
    cumKm = [0];
    for (var i = 1; i < coords.length; i++) cumKm[i] = cumKm[i - 1] + haversine(coords[i - 1], coords[i]);
  }

  function kmToLatLng(km) {
    var best = spine[0], bd = Infinity;
    for (var i = 0; i < spine.length; i++) {
      var d = Math.abs(spine[i].k - km);
      if (d < bd) { bd = d; best = spine[i]; }
    }
    return [best.la, best.lo];
  }

  function nearestKmFull(ll) {
    var bk = null, bd = Infinity;
    for (var i = 0; i < spine.length; i++) {
      var d = haversine([spine[i].la, spine[i].lo], ll);
      if (d < bd) { bd = d; bk = spine[i].k; }
    }
    return bk;
  }
  // [lat,lon] -> km na trasie, przyciety do zakresu etapu; null jesli wejscie niepoprawne
  function latLngToKm(ll, r) {
    if (!ll || !isFinite(ll[0]) || !isFinite(ll[1])) return null;
    var k = nearestKmFull(ll);
    if (k == null) return null;
    if (k < r[0]) k = r[0];
    if (k > r[1]) k = r[1];
    return k;
  }

  function cutRange(i) {
    var lo = (i === 0 ? 0 : cuts[i - 1]) + MIN_GAP_KM;
    var hi = (i === cuts.length - 1 ? totalKm : cuts[i + 1]) - MIN_GAP_KM;
    if (hi < lo) hi = lo;
    return [lo, hi];
  }

  function stageBounds(i) {
    var s = (i === 0) ? 0 : cuts[i - 1];
    var e = (i === nDays - 1) ? totalKm : cuts[i];
    return [s, e];
  }

  function computeStage(i) {
    var b = stageBounds(i), s = b[0], e = b[1];
    var gain = 0, paved = 0, unpaved = 0, unknown = 0, glen = 0.05, moveS = 0;
    for (var j = 0; j < spine.length; j++) {
      var k = spine[j].k;
      if (k < s || k >= e) continue;
      var dg = spine[j].g || 0; if (dg > 0) gain += dg;
      moveS += spine[j].t || 0;
      if (spine[j].s === "paved") paved += glen;
      else if (spine[j].s === "unpaved") unpaved += glen;
      else unknown += glen;
    }
    var surf = paved + unpaved + unknown || 1;
    return { idx: i, from: s, to: e, distKm: e - s, gain: gain, moveH: moveS / 3600,
      pavedPct: 100 * paved / surf, unpavedPct: 100 * unpaved / surf, unknownPct: 100 * unknown / surf };
  }

  function _fitPadTop() { var h = 0; if (document.body.classList.contains("map-bg")) { var hd = document.querySelector("header"); if (hd) h = hd.offsetHeight; } return h + 10; }
  /* v3 (2026-10-07): marginesy z faktycznego ukladu - panel/okno sekcji (#pv-panel) i profil (#profil) */
  function _qRect(id) { var e = document.getElementById(id); if (!e) return null; var cs = getComputedStyle(e); if (cs.display === "none" || cs.visibility === "hidden") return null; var r = e.getBoundingClientRect(); return (r.width && r.height) ? r : null; }
  function _fitPadBottom() { var f = _qRect("profil"), m = _qRect("map"); return (f && m) ? Math.max(24, Math.round(m.bottom - f.top) + 18) : 24; }
  function _fitPadLeft() { var p = _qRect("pv-panel"), m = _qRect("map"); return (p && m) ? Math.max(24, Math.round(p.right - m.left) + 18) : 24; }
  function fitRoute(lls) { if (!map || !lls || !lls.length) return; try { map.invalidateSize(false); } catch (e) {} try { map.fitBounds(L.latLngBounds(lls), { paddingTopLeft: [_fitPadLeft(), _fitPadTop()], paddingBottomRight: [14, _fitPadBottom()] }); } catch (e) {} }
  window.__planerRefit = function () { try { if (map && currentView == null && coords.length) fitRoute(coords); } catch (e) {} };

  function drawStages() {
    baseLayers.forEach(function (l) { map.removeLayer(l); });
    baseLayers = [];
    var seg = [], stage = 0;
    for (var i = 0; i < coords.length; i++) {
      var km = cumKm[i];
      while (stage < nDays - 1 && km > cuts[stage]) {
        seg.push(coords[i]); addSeg(seg, stage); seg = [coords[i]]; stage++;
      }
      seg.push(coords[i]);
    }
    if (seg.length) addSeg(seg, stage);
  }
  function addSeg(pts, stage) {
    if (pts.length < 2) return;
    baseLayers.push(L.polyline(pts, { color: STAGE_COLORS[stage % STAGE_COLORS.length], weight: 5, opacity: .9 }).addTo(map));
  }

  function drawCutMarkers() {
    cutMarkers.forEach(function (m) { map.removeLayer(m); });
    cutMarkers = [];
    for (var i = 0; i < cuts.length; i++) (function (i) {
      var icon = L.divIcon({ className: "", html: '<div class="cutdot">' + (i + 1) + '</div>', iconSize: [24, 24], iconAnchor: [12, 12] });
      var m = L.marker(kmToLatLng(cuts[i]), { icon: icon, draggable: true, autoPan: true, zIndexOffset: 1000 }).addTo(map);
      m.on("drag", function () {
        var k = latLngToKm(llArr(m.getLatLng()), cutRange(i));
        if (k == null) return;
        cuts[i] = k; if (dostosowano) closePanels(); drawStages(); renderTable();
      });
      m.on("dragend", function () {
        var k = latLngToKm(llArr(m.getLatLng()), cutRange(i));
        if (k != null) cuts[i] = k;
        m.setLatLng(kmToLatLng(cuts[i]));
        markStale(); drawStages(); renderTable(); saveDraft(); refreshFeas(); renderTools();
      });
      cutMarkers.push(m);
    })(i);
  }

  function surfBar(p, u, k) {
    return '<span class="surf-wrap">' +
      '<span class="bar-surf">' +
      '<i style="width:' + p.toFixed(0) + '%;background:#7a7f83"></i>' +
      '<i style="width:' + u.toFixed(0) + '%;background:#9c6b3f"></i>' +
      '<i style="width:' + k.toFixed(0) + '%;background:#c9c2b2"></i></span>' +
      '<span class="surf-legend">' +
      '<span><i style="background:#7a7f83"></i>Asfalt ' + p.toFixed(0) + '%</span>' +
      '<span><i style="background:#9c6b3f"></i>Nieutwardzone ' + u.toFixed(0) + '%</span>' +
      '<span><i style="background:#c9c2b2"></i>Nieznane ' + k.toFixed(0) + '%</span>' +
      '</span></span>';
  }

  function hm(h) { var m = Math.round((h || 0) * 60); return Math.floor(m / 60) + "h" + ("0" + (m % 60)).slice(-2); }
  function dayTime(st) {
    var micro = 0.22 * st.distKm;                 // mikro-postoje (kanon)
    var nb = Math.round(st.distKm / 9.0);         // krotkie co ~9 km
    var stopsMin = micro + nb * 4.5 + 60;         // + min. 1h dlugich postojow/dzien
    return { total: (st.moveH || 0) + stopsMin / 60, move: st.moveH || 0 };
  }
  function xssTd(i) {
    var v = "\u2026";
    if (feasData && feasData.stages && feasData.stages[i] != null) {
      var x = feasData.stages[i].xss;
      v = (x == null) ? "b/d" : ('<b>' + Math.round(x) + '</b>');
    }
    return '<td class="num">' + v + '<div style="font-size:13px;color:var(--muted)">XSS</div></td>';
  }

  function renderEtapCards() {
    var box = document.getElementById("etap-cards"); if (!box) return;
    if (!nDays || !spine || spine.length < 2) { box.innerHTML = ""; return; }
    var html = "";
    for (var i = 0; i < nDays; i++) {
      var st = computeStage(i), c = STAGE_COLORS[i % STAGE_COLORS.length];
      var t = dayTime(st);
      var vnet = t.move > 0 ? st.distKm / t.move : 0, vbru = t.total > 0 ? st.distKm / t.total : 0;
      var xss = "\u2026";
      if (feasData && feasData.stages && feasData.stages[i] != null) { var x = feasData.stages[i].xss; xss = (x == null) ? "b/d" : Math.round(x); }
      html += '<div class="ecard' + (openDay === i ? " ec-open" : "") + '" data-day="' + i + '">' +
        '<div class="ec-head"><span class="dot" style="background:' + c + '"></span><b>Dzie\u0144 ' + (i + 1) + '</b>' +
          '<span class="ec-km">' + st.from.toFixed(0) + "\u2013" + st.to.toFixed(0) + ' km</span></div>' +
        '<div class="ec-main">' + st.distKm.toFixed(1) + ' km <span class="ec-sep">\u00b7</span> \u2191' + Math.round(st.gain) + ' m <span class="ec-sep">\u00b7</span> ' + hm(t.total) + '</div>' +
        '<div class="ec-surf">' + surfBar(st.pavedPct, st.unpavedPct, st.unknownPct) + '</div>' +
        '<div class="ec-pct">' +
          '<span><i style="background:#7a7f83"></i>Asfalt ' + st.pavedPct.toFixed(0) + '%</span>' +
          '<span><i style="background:#9c6b3f"></i>Nieutw. ' + st.unpavedPct.toFixed(0) + '%</span>' +
          '<span><i style="background:#c9c2b2"></i>? ' + st.unknownPct.toFixed(0) + '%</span></div>' +
        '<div class="ec-sub">ruch ' + hm(t.move) + ' + 1h post. <span class="ec-sep">\u00b7</span> netto ' + vnet.toFixed(1) + ' <span class="ec-sep">\u00b7</span> brutto ' + vbru.toFixed(1) + ' km/h <span class="ec-sep">\u00b7</span> XSS ' + xss + '</div>';
      if (dostosowano && openDay === i) { html += '<div class="ec-detail">' + dayPanelHTML(dniData ? dniData[i] : null) + '</div>'; }
      html += '</div>';
    }
    box.innerHTML = html;
    var cc = box.querySelectorAll(".ecard");
    for (var y = 0; y < cc.length; y++) cc[y].addEventListener("click", function (e) { if (e.target.closest(".ec-detail")) return; setView(parseInt(this.getAttribute("data-day"), 10)); });
  }
  window.__planerEtapCards = renderEtapCards;

  function renderTable() {
    var tb = document.getElementById("rows"), html = "";
    for (var i = 0; i < nDays; i++) {
      var st = computeStage(i), c = STAGE_COLORS[i % STAGE_COLORS.length];
      var t = dayTime(st);
      var vnet = t.move > 0 ? st.distKm / t.move : 0, vbrutto = t.total > 0 ? st.distKm / t.total : 0;
      html += '<tr class="day-row' + (openDay === i ? " day-open" : "") + '" data-day="' + i + '">' +
        '<td><span class="dot" style="background:' + c + '"></span>Dzie\u0144 ' + (i + 1) +
        ' <span style="color:var(--muted);font-size:14px">(' + st.from.toFixed(0) + "\u2013" + st.to.toFixed(0) + " km)</span></td>" +
        '<td class="num">' + st.distKm.toFixed(1) + " km</td>" +
        '<td class="num">' + Math.round(st.gain) + " m</td>" +
        "<td>" + surfBar(st.pavedPct, st.unpavedPct, st.unknownPct) + "</td>" +
        '<td class="num"><b>' + hm(t.total) + '</b>' +
        '<div style="font-size:13px;color:var(--muted)">ruch ' + hm(t.move) + " + 1h post.</div>" +
        '<div style="font-size:13px;color:var(--muted)">netto ' + vnet.toFixed(1) + " \u00b7 brutto " + vbrutto.toFixed(1) + " km/h</div></td>" + xssTd(i) + "</tr>";
      if (dostosowano && openDay === i) {
        html += '<tr class="day-panel"><td colspan="6">' + dayPanelHTML(dniData ? dniData[i] : null) + '</td></tr>';
      }
    }
    tb.innerHTML = html;
    var rr = tb.querySelectorAll(".day-row");
    for (var x = 0; x < rr.length; x++) rr[x].addEventListener("click", function () { toggleDay(parseInt(this.getAttribute("data-day"), 10)); });
    renderEtapCards();
  }

  function currentRouteId() { var s = document.getElementById("route"); return s ? s.value : ""; }

  function updateDayXss() {
    var el = document.getElementById("d-xss-val"); if (!el) return;
    var v = (feasData && feasData.stages && currentView != null && feasData.stages[currentView] != null) ? feasData.stages[currentView].xss : null;
    el.textContent = (v == null) ? "b/d" : Math.round(v);
  }

  function refreshFeas() {
    if (feasTimer) clearTimeout(feasTimer);
    feasTimer = setTimeout(doFetchFeas, 350);
  }
  function doFetchFeas() {
    var rid = currentRouteId();
    if (!rid || !totalKm) return;
    var body = { route_id: rid, cuts: cuts.slice(), mode: "normalny" };
    if (feasDeparture) body.departure = feasDeparture;
    var seq = ++feasSeq;
    fetch("/api/planer/wykonalnosc", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (seq !== feasSeq) return;
        feasData = (d && d.ok) ? d : null;
        renderTable(); renderOcena(); updateDayXss();
      }).catch(function () { feasData = null; renderTable(); renderOcena(); updateDayXss(); });
  }

  function ocenaColor(c) { return c === "red" ? "var(--bad)" : (c === "yellow" ? "var(--warn)" : "var(--good)"); }

  function ocenaComment(d) {
    if (d.label) return d.label;
    if (d.wall) return d.wall;
    if (d.color === "red") return "ryzyko \u015bciany metabolicznej";
    if (d.color === "yellow") return "powy\u017cej rekordu dnia";
    return "w zasi\u0119gu formy";
  }

  function renderOcena() {
    var box = document.getElementById("ocena-formy"); if (!box) return;
    
    box.style.display = "block";
    if (!feasData) { box.innerHTML = '<h3>Ocena formy</h3><p class="muted">Liczenie\u2026</p>'; return; }
    var f = feasData.feasibility;
    var hh = '<h3>Ocena formy</h3>';
    if (!f || (f.ok === false && f.reason === "brak_daty")) {
      var ctl0 = (f && f.form) ? f.form.ctl : null;
      hh += '<p>Ustaw <b>dat\u0119 wyprawy</b>, aby oceni\u0107 wykonalno\u015b\u0107.' + (ctl0 != null ? (' Dzi\u015b Twoje CTL \u2248 ' + Math.round(ctl0) + '.') : '') + '</p>';
      box.innerHTML = hh; return;
    }
    if (f.ok === false) { hh += '<p class="muted">' + esc(f.reason || "brak danych formy") + '</p>'; box.innerHTML = hh; return; }
    var wallsArr = f.walls || (f.simulation && f.simulation.days) || [];
    var ceil = f.ceilings || {};
    var form = f.form || {};
    hh += '<p style="font-size:16px">' + esc(f.verdict) + '</p>';
    hh += '<p class="muted" style="font-size:14px">\u015ar. ' + (f.avg_daily_xss != null ? Math.round(f.avg_daily_xss) : "b/d") + '/dzie\u0144 \u00b7 sufit tygodnia ~' + (ceil.week_avg != null ? Math.round(ceil.week_avg) : "?") + ' \u00b7 \u0142\u0105czny XSS ' + Math.round(f.total_xss) + ' \u00b7 CTL dzi\u015b ' + (form.ctl != null ? Math.round(form.ctl) : "b/d") + '</p>';
    hh += '<p class="muted" style="font-size:13px">Kolor = \u015bciana dnia: \u017c\u00f3\u0142ty &gt; rekord (' + (ceil.day_demonstrated != null ? Math.round(ceil.day_demonstrated) : "?") + '), czerwony &gt; metaboliczna (' + (ceil.day_metabolic != null ? Math.round(ceil.day_metabolic) : "?") + '). Glikogen zak\u0142adany do pe\u0142na.</p>';
    hh += '<div class="of-days">';
    wallsArr.forEach(function (d, i) {
      var st = computeStage(i);
      var km = st ? (st.from.toFixed(0) + "\u2013" + st.to.toFixed(0) + " km") : "";
      hh += '<div class="of-day"><span class="of-dot" style="background:' + ocenaColor(d.color) + '"></span>' +
        '<div class="of-body"><div class="of-h">Dzie\u0144 ' + (i + 1) + (km ? ' \u00b7 ' + km : '') + '</div>' +
        '<div class="of-c muted">' + Math.round(d.xss) + ' XSS \u00b7 ' + esc(ocenaComment(d)) + '</div></div></div>';
    });
    hh += '</div>';
    box.innerHTML = hh;
  }

  var tloRouteId = null;
  function renderTlo() {
    var bh = document.getElementById("tlo-historia");
    var bg = document.getElementById("tlo-geografia");
    if (!bh || !bg) return;
    
    bh.style.display = "block"; bg.style.display = "block";
    var rid = currentRouteId();
    if (!rid) return;
    if (tloRouteId === rid) return;
    tloRouteId = rid;
    bh.innerHTML = '<h3>T\u0142o historyczne</h3><p class="muted">\u0141adowanie\u2026</p>';
    bg.innerHTML = '<h3>T\u0142o geograficzno-przyrodnicze</h3><p class="muted">\u0141adowanie\u2026</p>';
    fetch("/api/planer/tlo?route_id=" + encodeURIComponent(rid))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || d.status !== "OK") {
          tloRouteId = null;
          bh.innerHTML = '<h3>T\u0142o historyczne</h3><p class="muted">Brak danych.</p>';
          bg.innerHTML = '<h3>T\u0142o geograficzno-przyrodnicze</h3><p class="muted">Brak danych.</p>';
          return;
        }
        var hh = '<h3>T\u0142o historyczne</h3>';
        if (d.historia_tytul) hh += '<p style="font-weight:650;font-size:17px;color:var(--ink);margin:0 0 .55em">' + esc(d.historia_tytul) + '</p>';
        if (Array.isArray(d.historia) && d.historia.length) {
          hh += '<ul style="margin:.2em 0 0;padding-left:1.2em">';
          d.historia.forEach(function (p) { hh += '<li style="margin:.28em 0">' + esc(p) + '</li>'; });
          hh += '</ul>';
        } else { hh += '<p class="muted">Brak danych.</p>'; }
        bh.innerHTML = hh;
        var gg = '<h3>T\u0142o geograficzno-przyrodnicze</h3>';
        if (d.geografia_tytul) gg += '<p style="font-weight:650;font-size:17px;color:var(--ink);margin:0 0 .55em">' + esc(d.geografia_tytul) + '</p>';
        var hasGeo = false;
        if (d.geografia_intro) { gg += '<p>' + esc(d.geografia_intro) + '</p>'; hasGeo = true; }
        if (Array.isArray(d.geografia) && d.geografia.length) {
          gg += '<ul style="margin:.5em 0 0;padding-left:1.2em">';
          d.geografia.forEach(function (p) { gg += '<li style="margin:.28em 0">' + esc(p) + '</li>'; });
          gg += '</ul>';
          hasGeo = true;
        }
        if (!hasGeo) gg += '<p class="muted">Brak danych.</p>';
        bg.innerHTML = gg;
      })
      .catch(function () {
        tloRouteId = null;
        bh.innerHTML = '<h3>T\u0142o historyczne</h3><p class="muted">B\u0142\u0105d \u0142adowania.</p>';
        bg.innerHTML = '<h3>T\u0142o geograficzno-przyrodnicze</h3><p class="muted">B\u0142\u0105d \u0142adowania.</p>';
      });
  }

  function addWyprawaToCalendar() {
    var wd = document.getElementById("wyprawa-data");
    var day = wd ? wd.value : "";
    if (!day) { alert("Najpierw ustaw date wyprawy."); return; }
    var sel = document.getElementById("route");
    var rid = sel ? sel.value : "";
    var title = (sel && sel.options[sel.selectedIndex]) ? sel.options[sel.selectedIndex].text : "Wyprawa";
    var endD = day;
    if (nDays > 1) { var dd = new Date(day); dd.setDate(dd.getDate() + (nDays - 1)); endD = qDateLocal(dd); }
    /* 2026-10-06: wpis typu "jazda" + trasa przypieta do 1. dnia (calendar_day_route). TRENER liczy wtedy wyprawe z trasy
       (km rozlozone na dni, czas i XSS z podobnych jazd), a wpis BEZ trasy na te same dni (np. reczny "Wyprawa ... 180 km")
       jest przez nia zastepowany. Wczesniej wpis byl zwyklym wydarzeniem i TRENER nie laczyl go z planem. */
    fetch("/api/calendar/entry", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ day: day, end_day: endD, kind: "event", event_type: "jazda", title: "Wyprawa: " + title,
                             note: "Z Planera wyprawy (" + nDays + " dni). " + (totalKm ? totalKm.toFixed(1) + " km" : "") }) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) { alert("Nie udalo sie dodac."); return; }
        if (!d.id || !rid) { alert("Dodano wyprawe do kalendarza (bez przypiecia trasy)."); return; }
        return fetch("/api/calendar/route", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ entry_id: d.id, day: day, route_id: rid, route_name: title }) })
          .then(function (r2) { alert(r2.ok ? "Dodano wyprawe do kalendarza z przypieta trasa (Trener ja uwzgledni)." : "Dodano wyprawe, ale nie udalo sie przypiac trasy."); });
      })
      .catch(function () { alert("Blad polaczenia z kalendarzem."); });
  }

  function resetCuts() {
    cuts = [];
    for (var i = 1; i < nDays; i++) cuts.push(totalKm * i / nDays);
    markStale();
  }

  function renderAll() {
    drawStages(); drawCutMarkers(); renderTable(); renderViewTabs(); refreshFeas();
    renderTools();
    var o = document.getElementById("noclegi-out"); o.innerHTML = ""; o.style.display = "none";
    noclegiShown = false;
    var b = document.getElementById("noclegi"); if (b) b.textContent = "\uD83D\uDECF NOCLEGI — baza w promieniu 3 km";
  }

  function esc(x) {
    return String(x == null ? "" : x).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function renderOpis(id) {
    var box = document.getElementById("opis"); if (!box) return;
    box.innerHTML = '<h3>Opis trasy</h3><p class="muted">\u0141adowanie\u2026</p>';
    fetch("/api/planer/opis?route_id=" + encodeURIComponent(id))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || d.status !== "OK" || !d.intro) {
          box.innerHTML = '<h3>Opis trasy</h3><p class="muted">Brak opisu dla tej trasy.</p>';
          return;
        }
        var html = '<h3>Opis trasy</h3><p>' + esc(d.intro) + '</p>';
        var more = "";
        if (d.charakterystyka && d.charakterystyka.length) {
          more += '<h4 style="margin:.8em 0 .3em">Charakterystyka</h4><ul style="margin-top:.2em">';
          d.charakterystyka.forEach(function (c) { more += '<li>' + esc(c) + '</li>'; });
          more += '</ul>';
        }
        if (d.top_atrakcje && d.top_atrakcje.length) {
          more += '<h4 style="margin:.9em 0 .3em">Najwa\u017cniejsze atrakcje</h4><ul style="margin-top:.2em">';
          d.top_atrakcje.forEach(function (a) {
            var kmTxt = (a.km != null) ? (" <span style=\"color:var(--muted)\">(" + a.km.toFixed(1) + " km)</span>") : "";
            more += '<li>' + esc(a.name) + kmTxt + '</li>';
          });
          more += '</ul>';
        }
        if (more) {
          html += '<button type="button" class="opis-toggle" style="background:none;' +
                  'border:none;color:#3f6f9a;cursor:pointer;padding:.4em 0;font:inherit">' +
                  '\u25be Rozwi\u0144 opis</button>' +
                  '<div class="opis-more" style="display:none">' + more + '</div>';
        }
        box.innerHTML = html;
        var btn = box.querySelector(".opis-toggle");
        var moreBox = box.querySelector(".opis-more");
        if (btn && moreBox) {
          btn.addEventListener("click", function () {
            var openNow = moreBox.style.display !== "none";
            moreBox.style.display = openNow ? "none" : "block";
            btn.innerHTML = openNow ? "\u25be Rozwi\u0144 opis" : "\u25b4 Zwi\u0144 opis";
          });
        }
      })
      .catch(function () { box.innerHTML = '<h3>Opis trasy</h3><p class="muted">Brak opisu.</p>'; });
  }

  var SURF_COL = { paved: "#7a7f83", unpaved: "#9c6b3f" };
  var SURF_PL = { paved: "Asfalt", unpaved: "Nieutwardzone" };

  function renderProfil(rangeFrom, rangeTo) {
    var box = document.getElementById("profil"); if (!box) return;
    if (!spine || spine.length < 2) { box.innerHTML = ""; return; }
    var full = (rangeFrom == null || rangeTo == null);
    var pts = full ? spine : spine.filter(function (p) { return p.k >= rangeFrom && p.k <= rangeTo; });
    if (pts.length < 2) { pts = spine; full = true; }

    var W = 900, H = 200, ML = 40, MR = 10, MT = 10, MB = 22;
    var PW = W - ML - MR, PH = H - MT - MB, BASE = MT + PH;
    var kmA = pts[0].k, kmB = pts[pts.length - 1].k, kmSpan = (kmB - kmA) || 1;

    var elev = [], acc = 0, eMin = 0, eMax = 0;
    for (var i = 0; i < pts.length; i++) {
      acc += (pts[i].g || 0); elev.push(acc);
      if (acc < eMin) eMin = acc; if (acc > eMax) eMax = acc;
    }
    var span = (eMax - eMin) || 1;
    function X(km) { return ML + (km - kmA) / kmSpan * PW; }
    function Y(h) { return MT + (1 - (h - eMin) / span) * PH; }

    var parts = [], cur = null;
    for (var j = 0; j < pts.length; j++) {
      var sv = pts[j].s || "unknown";
      if (!cur || cur.s !== sv) { cur = { s: sv, i0: j, i1: j }; parts.push(cur); }
      else cur.i1 = j;
    }
    var P = [];
    parts.forEach(function (pp) {
      var col = SURF_COL[pp.s] || "#c9c2b2";
      var d = "M " + X(pts[pp.i0].k).toFixed(1) + " " + BASE;
      for (var q = pp.i0; q <= pp.i1; q++) d += " L " + X(pts[q].k).toFixed(1) + " " + Y(elev[q]).toFixed(1);
      d += " L " + X(pts[pp.i1].k).toFixed(1) + " " + BASE + " Z";
      P.push('<path d="' + d + '" fill="' + col + '" fill-opacity="0.85"/>');
    });
    var line = "M " + X(pts[0].k).toFixed(1) + " " + Y(elev[0]).toFixed(1);
    for (var m = 1; m < pts.length; m++) line += " L " + X(pts[m].k).toFixed(1) + " " + Y(elev[m]).toFixed(1);
    P.push('<path d="' + line + '" fill="none" stroke="#3a3a3a" stroke-width="1"/>');

    var ax = "";
    var kmStep = kmSpan > 200 ? 50 : kmSpan > 80 ? 20 : kmSpan > 30 ? 10 : 5;
    for (var kk = Math.ceil(kmA / kmStep) * kmStep; kk <= kmB + 0.1; kk += kmStep) {
      var xx = X(kk).toFixed(1);
      ax += '<line x1="' + xx + '" y1="' + BASE + '" x2="' + xx + '" y2="' + (BASE + 4) + '" stroke="#999"/>';
      ax += '<text x="' + xx + '" y="' + (BASE + 15) + '" font-size="11" fill="#666" text-anchor="middle">' + Math.round(kk) + '</text>';
    }
    var gsp = span > 2000 ? 500 : span > 800 ? 200 : span > 300 ? 100 : 50;
    var gridLines = "";
    for (var gv = Math.floor(eMin / gsp) * gsp; gv <= Math.ceil(eMax / gsp) * gsp + 0.1; gv += gsp) {
      var gy = Y(gv);
      gridLines += '<line x1="' + ML + '" y1="' + gy.toFixed(1) + '" x2="' + (ML + PW) + '" y2="' + gy.toFixed(1) + '" stroke="#d8d2c4" stroke-width="1"/>';
      ax += '<text x="' + (ML - 4) + '" y="' + (gy + 3).toFixed(1) + '" font-size="10" fill="#666" text-anchor="end">' + gv + '</text>';
    }
    var cur2 = '<line id="pf-cur" x1="0" y1="' + MT + '" x2="0" y2="' + BASE + '" stroke="#b0403f" stroke-width="1" style="display:none"/>';
    var ttl = full ? "Profil: przewy\u017cszenia i nawierzchnia" : ("Profil dnia: " + Math.round(kmA) + "\u2013" + Math.round(kmB) + " km");

    box.innerHTML =
      '<div class="sec-h">' + ttl + '</div>' +
      '<div class="profil-wrap">' +
      '<svg id="pf-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' + gridLines + P.join("") + ax + cur2 + '</svg>' +
      '<div id="pf-tip" class="profil-tip"></div>' +
      '<span class="surf-legend2">' +
      '<span><i style="background:#7a7f83"></i>Asfalt</span>' +
      '<span><i style="background:#9c6b3f"></i>Nieutwardzone</span>' +
      '<span><i style="background:#c9c2b2"></i>Nieznane</span></span>' +
      '</div>';

    var svg = document.getElementById("pf-svg");
    var tip = document.getElementById("pf-tip");
    var curLine = document.getElementById("pf-cur");
    function nearest(km) { var best = 0, bd = Infinity; for (var n = 0; n < pts.length; n++) { var dd = Math.abs(pts[n].k - km); if (dd < bd) { bd = dd; best = n; } } return best; }
    function onMove(clientX) {
      var r = svg.getBoundingClientRect();
      var km = kmA + ((clientX - r.left) / r.width * W - ML) / PW * kmSpan;
      km = Math.max(kmA, Math.min(kmB, km));
      var idx = nearest(km), sp = pts[idx];
      curLine.setAttribute("x1", X(sp.k)); curLine.setAttribute("x2", X(sp.k)); curLine.style.display = "block";
      tip.style.display = "block";
      tip.style.left = Math.min(Math.max((X(sp.k) / W) * r.width, 4), r.width - 4) + "px";
      tip.innerHTML = sp.k.toFixed(1) + " km \u00b7 " + Math.round(elev[idx]) + " m \u00b7 " + (SURF_PL[sp.s] || "Nieznane");
      if (map) {
        if (!profilHover) profilHover = L.circleMarker([sp.la, sp.lo], { radius: 6, color: "#b0403f", weight: 2, fillColor: "#b0403f", fillOpacity: .85 }).addTo(map);
        else { profilHover.setLatLng([sp.la, sp.lo]); if (!map.hasLayer(profilHover)) profilHover.addTo(map); }
      }
    }
    function onLeave() { curLine.style.display = "none"; tip.style.display = "none"; if (profilHover && map && map.hasLayer(profilHover)) map.removeLayer(profilHover); }
    svg.addEventListener("mousemove", function (e) { onMove(e.clientX); });
    svg.addEventListener("mouseleave", onLeave);
    svg.addEventListener("touchstart", function (e) { if (e.touches[0]) onMove(e.touches[0].clientX); }, { passive: true });
    svg.addEventListener("touchmove", function (e) { if (e.touches[0]) onMove(e.touches[0].clientX); }, { passive: true });
    svg.addEventListener("touchend", onLeave);
  }

  function updateDostosujBtn() {
    var b = document.getElementById("dostosuj"); if (!b) return;
    if (dostosowano) { b.disabled = true; b.textContent = "\u2713 Dopasowano do podzia\u0142u"; }
    else { b.disabled = false; b.textContent = "DOSTOSUJ \u2014 opis i noclegi wg podzia\u0142u"; }
  }
  function closePanels() { dostosowano = false; dniData = null; openDay = -1; updateDostosujBtn(); }
  function markStale() { closePanels(); if (spine && spine.length > 1) renderProfil(); }

  function zoomToDay(a2, b2) {
    if (!map || !spine.length) return;
    var lls = [];
    for (var i = 0; i < spine.length; i++) if (spine[i].k >= a2 && spine[i].k <= b2) lls.push([spine[i].la, spine[i].lo]);
    if (lls.length > 1) fitRoute(lls);
  }

  function dayPanelHTML(d) {
    if (!d) return '<div class="day-panel-in muted">Brak danych \u2014 kliknij DOSTOSUJ.</div>';
    var h = '<div class="day-panel-in">';
    if (d.nocleg) {
      var cnt = (d.nocleg_count != null) ? (' \u00b7 <b>' + d.nocleg_count + '</b> potencjalnych miejsc (3 km)') : ' \u00b7 sprawdzam noclegi\u2026';
      h += '<div class="nocleg-info">\uD83D\uDECF Nocleg w okolicy: <b>' + d.nocleg + '</b>' + cnt + '</div>';
    }
    else h += '<div class="nocleg-info">\uD83C\uDFC1 Meta trasy \u2014 bez noclegu.</div>';
    if (d.opis && d.opis.intro) h += '<p>' + d.opis.intro + '</p>';
    if (d.opis && d.opis.punkty && d.opis.punkty.length) {
      h += '<ul>'; d.opis.punkty.forEach(function (p) { h += '<li>' + p + '</li>'; }); h += '</ul>';
    }
    return h + '</div>';
  }

  function toggleDay(i) {
    var st = computeStage(i);
    zoomToDay(st.from, st.to);
    renderProfil(st.from, st.to);
    if (dostosowano) { openDay = (openDay === i) ? -1 : i; renderTable(); }
  }

  function fetchNoclegiCounts() {
    if (!dniData) return;
    dniData.forEach(function (d, i) {
      if (!d.nocleg) return;
      var ll = kmToLatLng(d.km_to);
      fetch("/api/noclegi?lat=" + ll[0] + "&lon=" + ll[1] + "&radius_m=3000")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (res) {
          if (res && res.status === "OK") { d.nocleg_count = res.count; if (openDay === i) renderTable(); saveHist(); saveVersion(); }
        }).catch(function () {});
    });
  }

  function doDostosuj() {
    var b = document.getElementById("dostosuj");
    var sel = document.getElementById("route");
    if (!sel || !sel.value) return;
    if (b) { b.disabled = true; b.textContent = "Generuj\u0119 opis i noclegi\u2026"; }
    fetch("/api/planer/opis-dni", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route_id: sel.value, cuts: cuts })
    }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (res) {
        if (!res || res.status !== "OK" || !res.dni) { if (b) { b.disabled = false; b.textContent = "B\u0142\u0105d \u2014 spr\u00f3buj ponownie"; } return; }
        dniData = res.dni; dostosowano = true; openDay = -1;
        updateDostosujBtn(); renderTable();
        if (currentView != null) renderDayPanel(currentView);
        fetchNoclegiCounts(); saveDraft(); saveHist(); saveVersion();
      })
      .catch(function () { if (b) { b.disabled = false; b.textContent = "B\u0142\u0105d po\u0142\u0105czenia"; } });
  }

  /* --- pamiec ustawien (localStorage): historia 3 ostatnich + draft biezacej sesji --- */
  var _histCache = [];
  function _prefsGet(key) { return fetch("/api/prefs?key=" + encodeURIComponent(key)).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) { return d ? d.value : null; }).catch(function () { return null; }); }
  function _prefsSet(key, value) { try { fetch("/api/prefs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: key, value: value }) }).catch(function () {}); } catch (e) {} }
  function readHist() { return Array.isArray(_histCache) ? _histCache : []; }
  function writeHist(a) { _histCache = Array.isArray(a) ? a : []; _prefsSet("planer_hist", _histCache); }
  var _savedCache = [];
  function readSaved() { return Array.isArray(_savedCache) ? _savedCache : []; }
  function writeSaved(a) { _savedCache = Array.isArray(a) ? a : []; _prefsSet("planer_saved", _savedCache); }
  function currentDeparture() { var wd = document.getElementById("wyprawa-data"); return (wd && wd.value) || feasDeparture || ""; }
  function verName(e) {
    var noc = [];
    (e.dniData || []).forEach(function (d) { if (d && d.nocleg && d.nocleg !== "None") noc.push(d.nocleg); });
    var _vt = e.saved_at ? new Date(e.saved_at) : null;
    var dd = (_vt && !isNaN(_vt)) ? (("0" + (_vt.getMonth() + 1)).slice(-2) + "-" + ("0" + _vt.getDate()).slice(-2) + " " + ("0" + _vt.getHours()).slice(-2) + ":" + ("0" + _vt.getMinutes()).slice(-2)) : "";
    var tag = e.nDays + " dni";
    if (noc.length) tag += " \u00b7 " + noc[0] + (noc.length > 1 ? " \u2192 " + noc[noc.length - 1] : "");
    return tag + " \u00b7 " + dd;
  }
  function saveVersion() {
    var sel = document.getElementById("route"); if (!sel || !sel.value || !dniData) return;
    var name = ""; try { name = sel.options[sel.selectedIndex].text; } catch (e) {}
    var entry = { id: Date.now(), route_id: sel.value, route_name: name, nDays: nDays, cuts: cuts.slice(), dniData: dniData, departure: currentDeparture(), saved_at: new Date().toISOString() };
    var k = histKey(entry);
    var arr = readSaved().filter(function (e) { return histKey(e) !== k; });
    arr.unshift(entry);
    if (arr.length > 20) arr = arr.slice(0, 20);
    writeSaved(arr); renderTools();
  }
  function applySavedVersion(id) {
    var e = readSaved().filter(function (x) { return x.id === id; })[0]; if (!e) return;
    var sel = document.getElementById("route"); if (!sel) return;
    var ok = false; for (var i = 0; i < sel.options.length; i++) if (sel.options[i].value === e.route_id) { ok = true; break; }
    if (!ok) { alert("Trasa tej wersji nie jest dost\u0119pna na li\u015bcie."); return; }
    sel.value = e.route_id;
    loadRoute(e.route_id, { nDays: e.nDays, cuts: e.cuts, dniData: e.dniData, departure: e.departure });
    document.body.classList.remove("qaside-open");
  }
  function deleteSaved(id) { writeSaved(readSaved().filter(function (x) { return x.id !== id; })); renderTools(); }
  function changeDays(delta) {
    var n = nDays + delta; if (n < 1 || n > 6) return;
    nDays = n; var dv = document.getElementById("dval"); if (dv) dv.textContent = nDays;
    resetCuts(); renderAll(); setView(null); saveDraft();
  }
  function histKey(e) { return e.route_id + "|" + e.nDays + "|" + (e.cuts || []).map(function (c) { return (+c).toFixed(1); }).join(","); }
  function saveDraft() {
    var sel = document.getElementById("route"); if (!sel || !sel.value) return;
    _prefsSet("planer_draft", { route_id: sel.value, nDays: nDays, cuts: cuts.slice(), departure: currentDeparture() });
  }
  function saveHist() {
    var sel = document.getElementById("route"); if (!sel || !sel.value || !dniData) return;
    var name = ""; try { name = sel.options[sel.selectedIndex].text; } catch (e) {}
    var entry = { id: Date.now(), route_id: sel.value, route_name: name, nDays: nDays, cuts: cuts.slice(), dniData: dniData, departure: currentDeparture(), saved_at: new Date().toISOString() };
    var k = histKey(entry);
    var arr = readHist().filter(function (e) { return histKey(e) !== k; });
    arr.unshift(entry);
    if (arr.length > 3) arr = arr.slice(0, 3);
    writeHist(arr); renderHist();
  }
  function shortName(s) { s = String(s || ""); return s.length > 24 ? s.slice(0, 23) + "…" : s; }
  function renderHist() {
    var box = document.getElementById("planer-hist"); if (!box) return;
    var arr = readHist();
    if (!arr.length) { box.style.display = "none"; box.innerHTML = ""; return; }
    box.style.display = "flex";
    var h = '<span class="ph-label">Ostatnie</span>';
    arr.forEach(function (e) {
      var d = qTsLocal(e.saved_at, true).slice(5);
      var ttl = (e.route_name || e.route_id) + " · " + e.nDays + " dni";
      h += '<button type="button" class="ph-chip" data-id="' + e.id + '" title="' + esc(ttl) + '">' + d + "</button>";
    });
    box.innerHTML = h;
    Array.prototype.forEach.call(box.querySelectorAll(".ph-chip"), function (b) {
      b.onclick = function () { applyHist(parseInt(b.getAttribute("data-id"), 10)); };
    });
  }
  function applyHist(id) {
    var e = readHist().filter(function (x) { return x.id === id; })[0]; if (!e) return;
    var sel = document.getElementById("route"); if (!sel) return;
    var ok = false; for (var i = 0; i < sel.options.length; i++) if (sel.options[i].value === e.route_id) { ok = true; break; }
    if (!ok) { alert("Trasa tego wpisu nie jest dostępna na liście."); return; }
    sel.value = e.route_id;
    loadRoute(e.route_id, { nDays: e.nDays, cuts: e.cuts, dniData: e.dniData, departure: e.departure });
  }

  function loadRoute(id, restore) {
    renderOpis(id);
    var _wl = document.getElementById("wyp-link"); if (_wl) { _wl.href = "/planer-wyposazenia.html?route=" + encodeURIComponent(id); _wl.onclick = function(){ try{ this.href = "/planer-wyposazenia.html?route=" + encodeURIComponent(id) + "&days=" + (nDays||""); }catch(e){} }; }
    var _pl = document.getElementById("pog-link");
    if (_pl) {
      _pl.href = "/pogoda-wyprawy.html?route=" + encodeURIComponent(id);
      _pl.onclick = function () {
        try {
          var c = [];
          for (var ci = 0; ci < nDays - 1; ci++) c.push(computeStage(ci).to.toFixed(2));
          this.href = "/pogoda-wyprawy.html?route=" + encodeURIComponent(id) +
            "&days=" + (nDays || 1) +
            "&cuts=" + encodeURIComponent(c.join(",")) +
            "&start=" + encodeURIComponent(currentDeparture() || "") +
            "&time=" + encodeURIComponent(pgStart || "09:00");
        } catch (e) {}
      };
    }
    var _wr = document.getElementById("wyp-row"); if (_wr) { _wr.style.display = ""; }
    Promise.all([
      fetch("/api/routes/" + id + "/geometry").then(function (r) { return r.json(); }),
      fetch("/api/routes/" + id + "/spine").then(function (r) { return r.ok ? r.json() : { spine: [], summary: {} }; })
    ]).then(function (res) {
      coords = res[0].coordinates || [];
      spine = (res[1] && res[1].spine) || [];
      if (!spine.length) {
        var _ob = document.getElementById("opis");
        if (_ob) _ob.innerHTML = '<h3>Opis trasy</h3><p class="muted">Profil tej trasy nie jest jeszcze policzony w systemie \u2014 nie mo\u017cna pokaza\u0107 podzia\u0142u. Trasa potrzebuje policzonej warstwy 50 m (nawierzchnia + wysoko\u015bci).</p>';
        var _wrh = document.getElementById("wyp-row"); if (_wrh) _wrh.style.display = "none";
        return;
      }
      buildCumKm();
      totalKm = cumKm[cumKm.length - 1] || (res[1].summary && res[1].summary.distance_km) || 0;
      if (restore && restore.cuts && restore.cuts.length === (restore.nDays - 1)) {
        nDays = restore.nDays;
        cuts = restore.cuts.map(function (c) { c = +c; if (c < 0) c = 0; if (c > totalKm) c = totalKm; return c; });
        var dv = document.getElementById("dval"); if (dv) dv.textContent = nDays;
        if (restore.dniData) { dniData = restore.dniData; dostosowano = true; openDay = -1; }
        else { dniData = null; dostosowano = false; openDay = -1; }
        updateDostosujBtn();
      } else {
        resetCuts();
      }
      if (restore && restore.departure) {
        var _wdr = document.getElementById("wyprawa-data");
        if (_wdr) _wdr.value = restore.departure;
        feasDeparture = restore.departure;
      }
      // Termin z KALENDARZA jest nadrzedny - tam plan wyprawy jest juz ustalony.
      // Gdy trasa nie ma wydarzenia, zostawiamy to, co bylo w szkicu, a jak nic
      // nie bylo - dzisiejsza date.
      fetch("/api/planer/termin?route_id=" + encodeURIComponent(id),
            { credentials: "same-origin", cache: "no-store" })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (t) {
          var wdc = document.getElementById("wyprawa-data");
          if (!wdc || !t) return;
          if (t.source === "kalendarz" && t.start) {
            wdc.value = t.start;
            feasDeparture = t.start;
            if (t.days && t.days > 1 && typeof nDays !== "undefined" && !dostosowano) {
              nDays = t.days;
              var dv2 = document.getElementById("dval"); if (dv2) dv2.textContent = nDays;
            }
          } else if (!wdc.value && t.start) {
            wdc.value = t.start;
            feasDeparture = t.start;
          }
          refreshFeas();
        })
        .catch(function () {});
      renderAll();
      renderProfil();
      fitRoute(coords);
      setView(null);
      saveDraft();
    }).catch(function () {
      var _oc = document.getElementById("opis");
      if (_oc) _oc.innerHTML = '<h3>Opis trasy</h3><p class="muted">B\u0142\u0105d \u0142adowania trasy. Spr\u00f3buj ponownie.</p>';
    });
  }

  function renderViewTabs() {
    var el = document.getElementById("viewtabs"); if (!el) return;
    var h = '<button class="viewtab' + (currentView == null ? " on" : "") + '" data-v="all">ALL</button>';
    for (var i = 0; i < nDays; i++) {
      var st = computeStage(i);
      h += '<button class="viewtab' + (currentView === i ? " on" : "") + '" data-v="' + i + '">Dzie\u0144 ' + (i + 1) +
           '<span class="k">' + st.from.toFixed(0) + '\u2013' + st.to.toFixed(0) + ' km</span></button>';
    }
    el.innerHTML = h;
    Array.prototype.forEach.call(el.querySelectorAll(".viewtab"), function (b) {
      b.onclick = function () { var v = b.getAttribute("data-v"); setView(v === "all" ? null : parseInt(v, 10)); };
    });
    applyMapMode();
  }

  function dayMastHTML(i, title) {
    return '<div class="day-mast">'
      + '<div class="dl"><span class="l"></span><span class="d">\u2726 Dzie\u0144 ' + (i + 1) + ' \u2726</span><span class="l"></span></div>'
      + '<h1 id="dzien-mast-title">' + esc(title) + '</h1>'
      + '<div class="dl" style="margin-top:8px"><span class="l"></span><span class="d">\u25c6</span><span class="l"></span></div>'
      + '</div>';
  }

  function setView(v) {
    if (v != null && (v < 0 || v >= nDays)) v = null;
    currentView = v;
    document.body.classList.toggle("pv-day", v != null);
    renderViewTabs();
    var panel = document.getElementById("dzien-panel");
    var tbl = document.querySelector("table");
    var dost = document.getElementById("dostosuj");
    var opis = document.getElementById("opis");
    var hint = document.getElementById("hint");
    var mast = document.getElementById("dzien-masthead");
    if (v == null) {
      if (panel) { panel.style.display = "none"; panel.innerHTML = ""; }
      if (tbl) tbl.style.display = "";
      if (dost) dost.style.display = "";
      if (opis) opis.style.display = "";
      if (hint) hint.style.display = "";
      if (mast) { mast.style.display = "none"; mast.innerHTML = ""; }
      drawStages();
      if (coords.length) fitRoute(coords);
      renderProfil();
    } else {
      var st = computeStage(v);
      if (tbl) tbl.style.display = "none";
      if (dost) dost.style.display = "none";
      
      if (hint) hint.style.display = "none";
      if (panel) panel.style.display = "";
      if (mast && IS_PRINT) { mast.style.display = ""; mast.innerHTML = dayMastHTML(v, st.from.toFixed(0) + "\u2013" + st.to.toFixed(0) + " km"); }
      zoomToDay(st.from, st.to);
      renderProfil(st.from, st.to);
      renderDayPanel(v);
    }
    renderOcena();
    renderTlo();
  }

  function dayInterpHTML(i) {
    if (dniData && dniData[i] && dniData[i].opis && dniData[i].opis.intro) {
      var d = dniData[i], h = "";
      if (d.nocleg) h += '<p class="muted">\uD83D\uDECF Nocleg: <b>' + esc(d.nocleg) + '</b></p>';
      h += '<p>' + esc(d.opis.intro) + '</p>';
      if (d.opis.punkty && d.opis.punkty.length) {
        h += '<ul>'; d.opis.punkty.forEach(function (p) { h += '<li>' + esc(p) + '</li>'; }); h += '</ul>';
      }
      return h;
    }
    return '<p class="muted">Opis dnia generowany na \u017c\u0105danie.</p><button class="dbtn" id="d-genopis">Wygeneruj opis dnia</button>';
  }

  /* --- widok dnia: kategorie nawierzchni, profil podjazdu, pokrycie zaopatrzenia --- */
  var SCAT_LABEL = { 1: "Asfalt", 2: "Dobry szuter", 3: "Zwyk\u0142y gravel", 4: "Trudna / wolna", 5: "Ryzyko" };
  var SCAT_COLOR = { 1: "#7a7f83", 2: "#3f7a4d", 3: "#8bbf5a", 4: "#c9662a", 5: "#b0403f" };
  var dayOffset = 0, currentDayDist = 0, dayEle = [];

  var _climbData = [];
  function nf(n, d) { return (n == null) ? "\u2014" : Number(n).toFixed(d == null ? 1 : d).replace(".", ","); }
  function inclineColor(g) {
    if (g == null) return '#cccccc';
    if (g < -8) return '#2D58AF';
    if (g < -5) return '#4fc3f7';
    if (g < -2) return '#ffffff';
    if (g < 2) return '#58c597';
    if (g < 5) return '#079d78';
    if (g < 8) return '#e7e021';
    if (g < 11) return '#e59174';
    if (g < 14) return '#e7693a';
    if (g < 20) return '#c82425';
    return '#b222a3';
  }
  function climbLegend() {
    var items = [['<2', '#58c597'], ['2\u20135', '#079d78'], ['5\u20138', '#e7e021'], ['8\u201311', '#e59174'], ['11\u201314', '#e7693a'], ['14\u201320', '#c82425'], ['\u226520', '#b222a3']];
    return '<div class="climb-legend">' + items.map(function (it) { return '<span class="cl-item"><span class="cl-sw" style="background:' + it[1] + '"></span>' + it[0] + '%</span>'; }).join('') + '</div>';
  }
  function climbProfileSVG(segs, akm) {
    if (!segs || !segs.length) return '<div class="muted" style="font-size:14px">Brak segment\u00f3w profilu.</div>';
    var W = 340, padL = 8, padR = 8, padTop = 10, plotH = 40, baseY = padTop + plotH, axisY = baseY + 12;
    var innerW = W - padL - padR;
    var xs = [0], ys = [0], cum = 0, cx = 0, i;
    for (i = 0; i < segs.length; i++) {
      var L = segs[i].len_m || 0, g = (segs[i].grade == null ? 0 : segs[i].grade);
      cx += L; cum += g / 100 * L; xs.push(cx); ys.push(cum);
    }
    var totLen = cx || 1;
    var ymin = Math.min.apply(null, ys), ymax = Math.max.apply(null, ys), rng = (ymax - ymin) || 1;
    function X(m) { return padL + (m / totLen) * innerW; }
    function Y(v) { return baseY - ((v - ymin) / rng) * plotH; }
    var poly = '', line = 'M' + X(xs[0]).toFixed(1) + ' ' + Y(ys[0]).toFixed(1), labels = '';
    for (i = 0; i < segs.length; i++) {
      var x0 = X(xs[i]), x1 = X(xs[i + 1]), y0 = Y(ys[i]), y1 = Y(ys[i + 1]);
      poly += '<polygon points="' + x0.toFixed(1) + ',' + baseY + ' ' + x0.toFixed(1) + ',' + y0.toFixed(1) + ' ' + x1.toFixed(1) + ',' + y1.toFixed(1) + ' ' + x1.toFixed(1) + ',' + baseY + '" fill="' + inclineColor(segs[i].grade) + '" stroke="rgba(0,0,0,.12)" stroke-width=".4"/>';
      line += ' L' + x1.toFixed(1) + ' ' + y1.toFixed(1);
      if ((x1 - x0) >= 20) { var gg = segs[i].grade; labels += '<text x="' + ((x0 + x1) / 2).toFixed(1) + '" y="8" text-anchor="middle" font-size="7.5" fill="#8c8168">' + (gg == null ? '' : Math.round(gg) + '%') + '</text>'; }
    }
    var bkm = (akm != null) ? (akm + totLen / 1000) : null;
    var ax = '<text x="' + padL + '" y="' + axisY + '" font-size="8" fill="#8c8168">km ' + (akm != null ? nf(akm, 1) : '') + '</text><text x="' + (W - padR) + '" y="' + axisY + '" font-size="8" fill="#8c8168" text-anchor="end">km ' + (bkm != null ? nf(bkm, 1) : '') + '</text>';
    return '<svg class="climb-prof" viewBox="0 0 ' + W + ' ' + (axisY + 4) + '" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">' + poly + '<path d="' + line + '" fill="none" stroke="rgba(230,230,220,.5)" stroke-width="1"/>' + labels + ax + '</svg>';
  }

  function climbComment(cl) {
    if (!cl || !cl.count) return "Etap w zasadzie p\u0142aski \u2014 brak wyra\u017anych podjazd\u00f3w.";
    var list = cl.list || [], hardest = null;
    list.forEach(function (c) { if (!hardest || (c.max_pct || 0) > (hardest.max_pct || 0)) hardest = c; });
    var word = cl.count === 1 ? "podjazd" : (cl.count < 5 ? "podjazdy" : "podjazd\u00f3w");
    var s = "Na etapie " + cl.count + " " + word + ", \u0142\u0105cznie +" + Math.round(cl.ascent_m || 0) + " m.";
    if (hardest) s += " Najostrzejszy " + (hardest.a_km - dayOffset).toFixed(1) + "\u2013" + (hardest.b_km - dayOffset).toFixed(1) + " km, do " + (hardest.max_pct != null ? Math.round(hardest.max_pct) : "?") + "%.";
    if (cl.count >= 6) s += " Profil falisty \u2014 roz\u0142\u00f3\u017c si\u0142y.";
    return s;
  }

  function fillSurface(sf) {
    var e = document.getElementById("d-surface"); if (!e) return;
    var by = (sf && sf.by_cat) || [];
    if (!by.length) { e.innerHTML = '<h3>Nawierzchnia</h3><p class="muted">Brak danych nawierzchni.</p>'; return; }
    var asf = 0, rough = 0;
    by.forEach(function (c) { if (c.k === 1) asf += c.pct; if (c.k >= 3) rough += c.pct; });
    var bar = '<div class="scat-bar">';
    by.forEach(function (c) { bar += '<i style="width:' + c.pct + '%;background:' + (SCAT_COLOR[c.k] || "#999") + '" title="' + esc(SCAT_LABEL[c.k] || ("kat " + c.k)) + ' ' + c.pct + '%"></i>'; });
    bar += '</div>';
    var legend = '<div class="scat-legend">';
    by.forEach(function (c) { legend += '<span><i style="background:' + (SCAT_COLOR[c.k] || "#999") + '"></i>' + esc(SCAT_LABEL[c.k] || ("kat " + c.k)) + ' ' + c.pct + '% <b>(' + c.km + ' km)</b></span>'; });
    legend += '</div>';
    var risk = ((sf && sf.risk) || []).slice().sort(function (a, b) { return (b.km || 0) - (a.km || 0); });
    var comment;
    if (asf >= 70) comment = "Etap g\u0142\u00f3wnie asfaltowy (" + asf + "%) \u2014 szybko, zwyk\u0142e opony wystarcz\u0105.";
    else if (rough >= 50) comment = "Ponad po\u0142owa nieutwardzona (" + rough + "% szuter/grunt) \u2014 opony pod gravel, wolniejsze tempo.";
    else comment = "Nawierzchnia mieszana: " + asf + "% asfalt, reszta szuter/grunt.";
    if (risk.length) comment += " Najd\u0142u\u017cszy trudny odcinek " + (risk[0].a - dayOffset).toFixed(1) + "\u2013" + (risk[0].b - dayOffset).toFixed(1) + " km (" + risk[0].km + " km).";
    e.innerHTML = '<h3>Nawierzchnia</h3>' + bar + legend + '<p class="clim-comment">' + esc(comment) + '</p>';
  }

  function renderDayPanel(i) {
    var panel = document.getElementById("dzien-panel"); if (!panel) return;
    var st = computeStage(i), t = dayTime(st);
    dayOffset = st.from; currentDayDist = st.distKm; dayEle = [];
    var vnet = t.move > 0 ? st.distKm / t.move : 0, vbrutto = t.total > 0 ? st.distKm / t.total : 0;
    var sel = document.getElementById("route"); var rid = sel ? sel.value : "";
    var h = '<div class="dcards">';
    h += '<div class="dcard"><div class="lab">Dystans</div><div class="val">' + st.distKm.toFixed(1) + ' <small>km</small></div><div class="sub2">' + st.from.toFixed(0) + '\u2013' + st.to.toFixed(0) + ' km</div></div>';
    h += '<div class="dcard"><div class="lab">Przewy\u017cszenie</div><div class="val">' + Math.round(st.gain) + ' <small>m</small></div></div>';
    h += '<div class="dcard"><div class="lab">Czas jazdy</div><div class="val">' + hm(t.total) + '</div><div class="sub2">ruch ' + hm(t.move) + ' + 1h post.</div></div>';
    h += '<div class="dcard"><div class="lab">Pr\u0119dko\u015b\u0107</div><div class="val">' + vnet.toFixed(1) + ' <small>km/h</small></div><div class="sub2">brutto ' + vbrutto.toFixed(1) + ' km/h</div></div>';
    var _dxss = "\u2026";
    if (feasData && feasData.stages && feasData.stages[i] != null) {
      var _xv = feasData.stages[i].xss;
      _dxss = (_xv == null) ? "b/d" : String(Math.round(_xv));
    }
    h += '<div class="dcard"><div class="lab">Szac. XSS</div><div class="val" id="d-xss-val">' + _dxss + '</div><div class="sub2">obciazenie dnia</div></div>';
    h += '</div>';
    h += '<div class="dsec" id="d-surface"><h3>Nawierzchnia</h3><p class="muted">\u0141adowanie\u2026</p></div>';
    h += '<div class="dsec" id="d-interp"><h3>Interpretacja dnia</h3>' + dayInterpHTML(i) + '</div>';
    h += '<div class="dsec" id="d-climbs"><h3>Podjazdy</h3><p class="muted">\u0141adowanie\u2026</p></div>';
    h += '<div class="dsec" id="d-resupply"><h3>Zaopatrzenie</h3><p class="muted">\u0141adowanie\u2026</p></div>';
    h += '<div class="dsec" id="d-attr"><h3>Atrakcje</h3><p class="muted">\u0141adowanie\u2026</p></div>';
    h += '<div class="dsec" id="d-gpx"><h3>Ślad dnia</h3><button class="dbtn" id="d-gpx-btn">⬇ Pobierz GPX dnia ' + (i + 1) + '</button></div>';
    panel.innerHTML = h;

    var gen = document.getElementById("d-genopis"); if (gen) gen.onclick = doDostosuj;
    var _gx = document.getElementById("d-gpx-btn"); if (_gx) _gx.onclick = function () {
      var _nm = (sel && sel.options[sel.selectedIndex]) ? sel.options[sel.selectedIndex].text : "";
      window.open("/api/planer/dzien/gpx?route_id=" + encodeURIComponent(rid) + "&from=" + st.from.toFixed(1)
        + "&to=" + st.to.toFixed(1) + "&day=" + (i + 1) + "&name=" + encodeURIComponent(_nm), "_blank");
    };

    function fillErr() { ["d-surface", "d-climbs", "d-resupply", "d-attr"].forEach(function (id) { var el = document.getElementById(id); if (el) { var p = el.querySelector("p"); if (p) p.textContent = "B\u0142\u0105d \u0142adowania danych."; } }); }
    fetch("/api/planer/dzien?route_id=" + encodeURIComponent(rid) + "&from=" + st.from.toFixed(1) + "&to=" + st.to.toFixed(1))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || d.status === "ERROR" || !d.details) { fillErr(); return; }
        dayEle = (d.chart && d.chart.ele) || [];
        var _mt = document.getElementById("dzien-mast-title");
        if (_mt && d.day) {
          var _fp = d.day.from_place, _tp = d.day.to_place, _txt = "";
          if (_fp && _tp && _fp !== _tp) _txt = _fp + " \u2013 " + _tp;
          else if (_fp || _tp) _txt = (_fp || _tp);
          if (_txt) _mt.textContent = _txt;
        }
        fillSurface(d.details.surface);
        fillClimbs(d.details.climbs);
        fillResupply((d.details.poi || {}).resupply_points);
        fillAttr((d.details.poi || {}).attractions);
      }).catch(fillErr);
  }

  function fillClimbs(cl) {
    var e = document.getElementById("d-climbs"); if (!e) return;
    _climbData = (cl && cl.list) || [];
    var comment = climbComment(cl);
    if (!_climbData.length) { e.innerHTML = '<h3>Podjazdy</h3><p class="clim-comment">' + esc(comment) + '</p>'; return; }
    var h = '<h3>Podjazdy \u00b7 +' + Math.round(cl.ascent_m || 0) + ' m (' + cl.count + ')</h3>';
    h += '<p class="clim-comment">' + esc(comment) + '</p>';
    _climbData.forEach(function (c, idx) {
      h += '<div class="poi-row climb-row" data-i="' + idx + '">' +
           '<span class="poi-km">' + (c.a_km - dayOffset).toFixed(1) + '\u2013' + (c.b_km - dayOffset).toFixed(1) + '</span>' +
           '<span class="poi-name">+' + c.gain_m + ' m \u00b7 ' + (c.length_m / 1000).toFixed(1) + ' km</span>' +
           '<span class="poi-meta">\u2300 ' + (c.avg_pct != null ? c.avg_pct.toFixed(1) : "?") + '% \u00b7 max ' + (c.max_pct != null ? Math.round(c.max_pct) : "?") + '% \u25be</span></div>' +
           '<div class="climb-graph" style="display:none"></div>';
    });
    h += climbLegend();
    e.innerHTML = h;
    Array.prototype.forEach.call(e.querySelectorAll(".climb-row"), function (row) {
      row.onclick = function () {
        var gbox = row.nextElementSibling;
        if (!gbox || gbox.className.indexOf("climb-graph") < 0) return;
        if (gbox.style.display !== "none") { gbox.style.display = "none"; return; }
        if (!gbox.innerHTML) { var c = _climbData[parseInt(row.getAttribute("data-i"), 10)]; gbox.innerHTML = climbProfileSVG(c.segments, c.a_km - dayOffset); }
        gbox.style.display = "";
      };
    });
  }

  function fillResupply(pts) {
    var e = document.getElementById("d-resupply"); if (!e) return;
    var kms = ((pts) || []).map(function (p) { return p.km - dayOffset; }).filter(function (k) { return k >= -0.5; });
    kms.sort(function (a, b) { return a - b; });
    if (!kms.length) { e.innerHTML = '<h3>Zaopatrzenie</h3><p class="warn-line">\u26a0 Brak sklep\u00f3w na tym etapie \u2014 we\u017a zapasy na ca\u0142y dzie\u0144.</p>'; return; }
    var bounds = [0].concat(kms).concat([currentDayDist]);
    var maxGap = 0, big = [];
    for (var j = 1; j < bounds.length; j++) { var len = bounds[j] - bounds[j - 1]; if (len > maxGap) maxGap = len; if (len > 40) big.push([bounds[j - 1], bounds[j]]); }
    var uniq = 0, last = -99;
    for (var q = 0; q < kms.length; q++) { if (kms[q] - last > 0.3) { uniq++; last = kms[q]; } }
    var h = '<h3>Zaopatrzenie</h3>';
    if (maxGap <= 40) {
      h += '<p class="ok-line">\u2713 Zaopatrzenie regularne \u2014 sklepy rozsiane po trasie (' + uniq + ' punkt\u00f3w, najwi\u0119ksza przerwa ' + Math.round(maxGap) + ' km).</p>';
    } else {
      h += '<p class="warn-line">\u26a0 Uwaga na d\u0142u\u017csze odcinki bez sklepu \u2014 najwi\u0119ksza przerwa ' + Math.round(maxGap) + ' km (' + uniq + ' punkt\u00f3w \u0142\u0105cznie):</p>';
      big.forEach(function (gp) { h += '<div class="poi-row"><span class="poi-km">' + gp[0].toFixed(0) + '\u2013' + gp[1].toFixed(0) + ' km</span><span class="poi-name">bez sklepu (' + Math.round(gp[1] - gp[0]) + ' km)</span></div>'; });
    }
    e.innerHTML = h;
  }

  function fillAttr(att) {
    var e = document.getElementById("d-attr"); if (!e) return;
    var items = (att && att.items) || [];
    if (!items.length) { e.innerHTML = '<h3>Atrakcje</h3><p class="muted">Brak wyselekcjonowanych atrakcji.</p>'; return; }
    var h = '<h3>Atrakcje (' + items.length + ')</h3>';
    items.forEach(function (a, idx) {
      h += '<div class="poi-row attr-row" data-i="' + idx + '"><span class="poi-km">' + (a.km != null ? (a.km - dayOffset).toFixed(1) + ' km' : "") + '</span>' +
           '<span class="poi-name">' + (a.miejscowosc ? '<span class="attr-loc">' + esc(a.miejscowosc) + '</span>' : "") + esc(a.name || "") + (a.desc ? '<div class="poi-meta">' + esc(a.desc) + '</div>' : "") + '</span><span class="poi-meta">\u25be</span></div>' +
           '<div class="attr-detail" style="display:none"></div>';
    });
    e.innerHTML = h;
    Array.prototype.forEach.call(e.querySelectorAll(".attr-row"), function (row) {
      row.onclick = function () {
        var box = row.nextElementSibling;
        if (!box || box.className.indexOf("attr-detail") < 0) return;
        if (box.style.display !== "none") { box.style.display = "none"; return; }
        box.style.display = "";
        if (box.getAttribute("data-loaded")) return;
        box.setAttribute("data-loaded", "1");
        var a = items[parseInt(row.getAttribute("data-i"), 10)];
        function _shortDesc(x) {
          x = String(x || "").trim();
          return x.length > 420 ? x.slice(0, 417).replace(/\s+\S*$/, "") + "\u2026" : x;
        }
        function _renderAttr(res) {
          res = res || {};
          var photo = res.photo_url || a.image_url || "";
          var _ax = (a.extract && String(a.extract).length > 60) ? a.extract : "";
          var desc = _shortDesc(res.desc || _ax || "");
          var sourceUrl = res.desc_url || a.wiki || "";
          var m = '<div class="attr-media">';
          if (photo) m += '<img class="attr-photo" src="' + esc(photo) + '" alt="' + esc(a.name || "") + '">';
          m += '<div class="attr-text">';
          if (desc) {
            var source = "";
            if (sourceUrl) {
              var sourceName = sourceUrl.indexOf("wikipedia.org") >= 0 ? "Wikipedia" :
                               (sourceUrl.indexOf("google.com/maps") >= 0 ? "Google Maps" : "\u0179r\u00f3d\u0142o");
              source = ' <span class="attr-src">\u2014 <a href="' + esc(sourceUrl) + '" target="_blank" rel="noopener">' + sourceName + '</a></span>';
            }
            m += '<p class="attr-desc">' + esc(desc) + source + '</p>';
          } else if (sourceUrl) {
            m += '<p class="attr-desc"><a href="' + esc(sourceUrl) + '" target="_blank" rel="noopener">Zobacz opis \u017ar\u00f3d\u0142owy</a></p>';
          }
          m += '</div></div>';
          if (!photo && !desc && !sourceUrl) { box.style.display = "none"; box.innerHTML = ""; }
          else { box.innerHTML = m; }
        }
        function _attrMeta() { _renderAttr(null); }
        var needsRemote = a.place_id && (String(a.place_id).indexOf("google:") === 0 || !a.image_url);
        if (needsRemote) {
          box.innerHTML = '<p class="muted attr-loading">\u0141adowanie opisu i zdj\u0119cia\u2026</p>';
          fetch("/api/planer/atrakcja?place_id=" + encodeURIComponent(a.place_id)
                + "&name=" + encodeURIComponent(a.name || "")
                + (a.lat != null ? "&lat=" + a.lat : "")
                + (a.lon != null ? "&lon=" + a.lon : ""))
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (res) {
              if (!res || res.status !== "OK") { _attrMeta(); return; }
              _renderAttr(res);
            }).catch(_attrMeta);
        } else {
          _attrMeta();
        }
      };
    });
  }

  function initDays() {
    var db = document.getElementById("dostosuj"); if (db) db.onclick = doDostosuj; updateDostosujBtn();
    var wd0 = document.getElementById("wyprawa-data"); if (wd0) wd0.onchange = function () { feasDeparture = wd0.value || ""; refreshFeas(); };
    var wa0 = document.getElementById("wyprawa-add"); if (wa0) wa0.onclick = addWyprawaToCalendar;
    var wp0 = document.getElementById("wyprawa-pdf"); if (wp0) wp0.onclick = function () {
      var s = document.getElementById("route"); if (!s || !s.value) { alert("Wybierz trase"); return; }
      var nm = s.options[s.selectedIndex] ? s.options[s.selectedIndex].text : "";
      var u = "/wyprawa-oczekiwanie.html?route_id=" + encodeURIComponent(s.value)
            + "&cuts=" + encodeURIComponent(cuts.join(","))
            + "&date=" + encodeURIComponent(currentDeparture())
            + "&name=" + encodeURIComponent(nm) + "&_=" + Date.now();
      window.open(u, "_blank");
    };
  }

  function runNoclegiSearch() {
    var out = document.getElementById("noclegi-out");
    if (!cuts.length) { out.innerHTML = '<div class="nl"><p>Ustaw co najmniej 2 dni, aby pojawiły się punkty noclegowe.</p></div>'; return; }
    var html = "";
    for (var i = 0; i < cuts.length; i++)
      html += '<div class="nl" id="nl' + i + '"><h4>Nocleg ' + (i + 1) + " · po dniu " + (i + 1) + '</h4><p>~' + cuts[i].toFixed(1) + ' km · szukam w 3 km…</p></div>';
    out.innerHTML = html;
    for (var i = 0; i < cuts.length; i++) (function (i) {
      var ll = kmToLatLng(cuts[i]);
      var head = '<h4>Nocleg ' + (i + 1) + " · po dniu " + (i + 1) + "</h4>";
      fetch("/api/noclegi?lat=" + ll[0] + "&lon=" + ll[1] + "&radius_m=3000")
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var el = document.getElementById("nl" + i); if (!el) return;
          if (d.status !== "OK") {
            el.innerHTML = head + '<p>~' + cuts[i].toFixed(1) + ' km · błąd: ' + (d.error || d.status) + '</p>';
            return;
          }
          if (!d.count) {
            el.innerHTML = head + '<p>~' + cuts[i].toFixed(1) + ' km · brak bazy w 3 km</p><span class="pill" style="background:#f3e0e0;color:#b0403f">pusto — rozważ inny punkt</span>';
            return;
          }
          el.innerHTML = head + '<p>~' + cuts[i].toFixed(1) + " km · <b>" + d.count + "</b> obiektów w 3 km (Google)</p>" +
            '<span class="pill" style="background:#e8f1e9;color:#3f7a4d">✓ kwalifikuje się</span>';
        })
        .catch(function () {
          var el = document.getElementById("nl" + i); if (el) el.innerHTML = head + "<p>błąd połączenia</p>";
        });
    })(i);
  }
  function toggleNoclegi(show) {
    var out = document.getElementById("noclegi-out"), btn = document.getElementById("noclegi");
    noclegiShown = show;
    out.style.display = show ? "" : "none";
    btn.textContent = show ? "\uD83D\uDECF Schowaj noclegi" : "\uD83D\uDECF NOCLEGI — baza w promieniu 3 km";
    if (show && !out.querySelector(".nl")) runNoclegiSearch();
  }
  function openAnaliza() {
    var sel = document.getElementById("route");
    var rid = sel ? sel.value : "";
    if (!rid) { alert("Najpierw wybierz tras\u0119."); return; }
    if (!totalKm) { alert("Trasa nie jest jeszcze wczytana."); return; }
    var bounds = [0].concat(cuts.slice()).concat([totalKm]);
    var parts = [];
    for (var i = 0; i < bounds.length - 1; i++) parts.push(bounds[i].toFixed(1) + "-" + bounds[i + 1].toFixed(1));
    var url = "/raport-dzien.html?route_id=" + encodeURIComponent(rid) + "&days=" + encodeURIComponent(parts.join(","));
    window.open(url, "_blank");
  }
  function initPodziel() {
    var b = document.getElementById("podziel");
    if (b) b.onclick = openAnaliza;
  }

  function init() {
    map = L.map("map", { zoomSnap: 0 });
    var _qtl = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(map);
    if (window.qTilesAttach) window.qTilesAttach(map, _qtl, { dayGray: true });
    void 0;
    document.addEventListener("keydown", function (e) { if (map && (e.key === "Meta" || e.key === "Control")) map.scrollWheelZoom.enable(); });
    document.addEventListener("keyup", function (e) { if (map && (e.key === "Meta" || e.key === "Control")) void 0; });
    window.addEventListener("blur", function () { if (map) void 0; });
    if (false) {
      var _hd = document.querySelector("header");
      var _br = document.querySelector(".bar");
      if (_hd && _br && _br.parentNode !== _hd) _hd.appendChild(_br);
      var _h1 = _hd ? _hd.querySelector("h1") : null;
      var _route = document.getElementById("route");
      var _tf = _route ? _route.closest(".field") : null;
      if (_hd && _h1 && _tf && !_hd.querySelector(".menu-left")) {
        var _left = document.createElement("div"); _left.className = "menu-left";
        _h1.parentNode.insertBefore(_left, _h1);
        _left.appendChild(_h1); _left.appendChild(_tf);
      }
      var _vt = document.getElementById("viewtabs");
      if (_hd && _vt && _vt.parentNode !== _hd) _hd.appendChild(_vt);
      var _dj = document.getElementById("dostosuj");
      if (_hd && _dj && _dj.parentNode !== _hd) _hd.appendChild(_dj);
      var _wr0 = document.getElementById("wyp-row");
      if (_hd && _wr0 && _wr0.parentNode !== _hd) _hd.appendChild(_wr0);
    }
    initDays(); initPodziel(); toolsInit(); initMapBg();
    fetch("/api/routes/ready").then(function (r) { return r.json(); }).then(function (d) {
      var sel = document.getElementById("route");
      (d.routes || []).filter(function (r) { return (r.distance_km || 0) > 150; }).forEach(function (r) {
        var o = document.createElement("option");
        o.value = r.route_id; o.textContent = r.name + " · " + r.distance_km + " km";
        sel.appendChild(o);
      });
      sel.onchange = function () { loadRoute(sel.value); };
      if (IS_PRINT && _PQ.get("route")) {
        document.body.classList.add("print");
        var _dep = _PQ.get("departure") || ""; if (_dep) document.body.classList.add("pdf-forma");
        var _pr = _PQ.get("route");
        var _pc = (_PQ.get("cuts") || "").split(",").map(function (x) { return parseFloat(x); }).filter(function (x) { return !isNaN(x); });
        var _pn = parseInt(_PQ.get("nDays") || (_pc.length + 1), 10);
        var _ok = false; for (var _i = 0; _i < sel.options.length; _i++) if (sel.options[_i].value === _pr) _ok = true;
        if (_ok) { sel.value = _pr; loadRoute(_pr, { route_id: _pr, nDays: _pn, cuts: _pc, dniData: null, departure: _dep }); }
        else if (sel.value) loadRoute(sel.value);
        return;
      }
      Promise.all([_prefsGet("planer_hist"), _prefsGet("planer_draft"), _prefsGet("planer_saved")]).then(function (pr) {
        _histCache = Array.isArray(pr[0]) ? pr[0] : [];
        _savedCache = Array.isArray(pr[2]) ? pr[2] : [];
        if (!_savedCache.length && _histCache.length) { _savedCache = _histCache.slice(0, 20); _prefsSet("planer_saved", _savedCache); }
        if (!_histCache.length) { try { var _old = JSON.parse(localStorage.getItem(LS_HIST) || "[]"); if (Array.isArray(_old) && _old.length) { _histCache = _old; _prefsSet("planer_hist", _histCache); } } catch (e) {} }
        var _draft = (pr[1] && pr[1].route_id) ? pr[1] : null;
        if (!_draft) { try { var _od = JSON.parse(localStorage.getItem(LS_DRAFT) || "null"); if (_od && _od.route_id) _draft = _od; } catch (e) {} }
        renderHist();
        var _hist = readHist();
        function _inList(rid) { for (var i = 0; i < sel.options.length; i++) if (sel.options[i].value === rid) return true; return false; }
        var _t = null;
        if (_draft && _draft.route_id && _inList(_draft.route_id)) {
          _t = { route_id: _draft.route_id, nDays: _draft.nDays, cuts: _draft.cuts, dniData: null, departure: _draft.departure || "" };
          var _k = histKey({ route_id: _draft.route_id, nDays: _draft.nDays, cuts: _draft.cuts });
          var _m = _hist.filter(function (e) { return histKey(e) === _k; })[0];
          if (_m) { _t.dniData = _m.dniData; if (_m.departure) _t.departure = _m.departure; }
        } else if (_hist.length && _inList(_hist[0].route_id)) {
          var _e0 = _hist[0]; _t = { route_id: _e0.route_id, nDays: _e0.nDays, cuts: _e0.cuts, dniData: _e0.dniData, departure: _e0.departure || "" };
        }
        if (_t) { sel.value = _t.route_id; loadRoute(_t.route_id, _t); }
        else if (sel.value) loadRoute(sel.value);
      });
    });
  }
  function openWyprawaPdf() {
    var s = document.getElementById("route"); if (!s || !s.value) { alert("Wybierz trase"); return; }
    var nm = s.options[s.selectedIndex] ? s.options[s.selectedIndex].text : "";
    var u = "/wyprawa-oczekiwanie.html?route_id=" + encodeURIComponent(s.value)
          + "&cuts=" + encodeURIComponent(cuts.join(","))
          + "&date=" + encodeURIComponent(currentDeparture())
          + "&name=" + encodeURIComponent(nm) + "&_=" + Date.now();
    window.open(u, "_blank");
  }

  function toolsAddQbot(aq, status) {
    var s = document.getElementById("route"); var rid = s ? s.value : "";
    if (!rid) { alert("Wybierz trase"); return; }
    if (!confirm("Utworzy\u0107 " + nDays + " osobnych tras GPX i doda\u0107 je do QBot?")) return;
    aq.disabled = true;
    aq.textContent = "Dodaj\u0119 " + nDays + " tras\u2026";
    if (status) status.textContent = "Generowanie i rejestracja GPX-\u00f3w\u2026";
    fetch("/api/planer/dodaj-do-qbot", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route_id: rid, cuts: cuts.slice() })
    }).then(function (r) { return r.ok ? r.json() : null; }).then(function (res) {
      if (!res || res.status !== "OK") throw new Error((res && res.error) || "B\u0142\u0105d dodawania tras");
      aq.textContent = "\u2713 Dodano " + res.day_count + " tras do QBot";
      if (status) {
        status.innerHTML = (res.days || []).map(function (day) {
          return '<span style="display:block">Dzie\u0144 ' + day.day + ': ' + esc(day.name) + ' \u00b7 ' + Number(day.distance_km).toFixed(1) + ' km</span>';
        }).join("") + '<span style="display:block;margin-top:5px">Atrakcje: wsp\u00f3lna warstwa trasy wyprawowej, 0 nowych zapyta\u0144.</span>';
      }
    }).catch(function (err) {
      aq.disabled = false;
      aq.textContent = "\u2795 Dodaj wszystkie dni do QBot (" + nDays + " GPX)";
      if (status) status.textContent = "Nie uda\u0142o si\u0119: " + (err.message || err);
    });
  }

  function toolsMailPopulate() {
    fetch("/api/report/mail-recipients").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        var dl = document.getElementById("tw-mail-hist"); if (!dl || !j || !j.items) return;
        dl.innerHTML = j.items.map(function (x) { return '<option value="' + String(x).replace(/"/g, "&quot;") + '">'; }).join("");
      }).catch(function () {});
  }

  function toolsRsvpPopulate(rid) {
    var box = document.getElementById("tw-rsvp"); if (!box) return;
    if (!rid) { box.innerHTML = ""; return; }
    fetch("/api/wyprawa/rsvp-list?route_id=" + encodeURIComponent(rid))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.items || !j.items.length) { box.innerHTML = ""; return; }
        var icon = { yes: "\u2705", no: "\u274c", pending: "\u23f3" };
        var col = { yes: "#2f7a3a", no: "#c0392b", pending: "var(--muted)" };
        var lab = { yes: "wezmie udzia\u0142", no: "nie da rady", pending: "oczekuje" };
        var c = j.counts || {};
        var h = '<div class="qa-h" style="margin-top:14px">Zaproszenia <span style="color:var(--muted);font-weight:400">('
              + (c.yes || 0) + ' \u2705 / ' + (c.no || 0) + ' \u274c / ' + (c.pending || 0) + ' \u23f3)</span></div>';
        h += j.items.map(function (it) {
          var cc = col[it.status] || "var(--ink)";
          return '<div style="font-size:13px;padding:4px 0;border-bottom:1px solid var(--line)">'
               + (icon[it.status] || "") + ' ' + esc(it.email)
               + ' <span style="color:' + cc + '">\u00b7 ' + (lab[it.status] || it.status) + '</span></div>';
        }).join("");
        var nYes = c.yes || 0;
        h += '<div style="margin-top:9px">'
           + '<button id="tw-rsvp-group" ' + (nYes ? '' : 'disabled ')
           + 'style="width:100%;padding:8px 12px;border:1px solid var(--accent);border-radius:9px;'
           + 'background:' + (nYes ? 'var(--accent);color:#fff' : 'var(--panel);color:var(--muted)')
           + ';font:inherit;font-size:13px;font-weight:700;cursor:' + (nYes ? 'pointer' : 'default') + '">'
           + '\u2709 Zr\u00f3b grup\u0119 mailow\u0105 z potwierdzonych (' + nYes + ')</button>'
           + '<div id="tw-rsvp-gmsg" style="font-size:12px;color:var(--muted);margin-top:5px;min-height:15px"></div>'
           + '<div style="font-size:11.5px;color:var(--muted);margin-top:2px">'
           + 'Grupa aktualizuje si\u0119 sama, gdy kto\u015b zmieni odpowied\u017a. Adresy dopisane r\u0119cznie zostaj\u0105.</div>'
           + '</div>';
        box.innerHTML = h;
        var gb = document.getElementById("tw-rsvp-group");
        if (gb && nYes) gb.onclick = function () { toolsRsvpMakeGroup(rid, gb); };
      }).catch(function () {});
  }

  function toolsRsvpMakeGroup(rid, btn) {
    var msg = document.getElementById("tw-rsvp-gmsg");
    btn.disabled = true;
    if (msg) msg.textContent = "Tworz\u0119 grup\u0119\u2026";
    fetch("/api/mail-groups/import-rsvp", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route_id: rid })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        btn.disabled = false;
        if (!res.ok) throw new Error((res.j && res.j.detail) || "b\u0142\u0105d");
        var g = res.j.group || {}, sy = res.j.sync || {};
        if (msg) msg.innerHTML = '\u2713 Grupa \u201e' + esc(g.name || "") + '\u201d \u00b7 '
          + ((g.members || []).length) + ' adres\u00f3w'
          + ((sy.added || []).length ? ' (dodano ' + sy.added.length + ')' : '')
          + ' \u2014 edycja w Kalendarzu \u2192 \u2709 Grupy';
      }).catch(function (e) {
        btn.disabled = false;
        if (msg) msg.textContent = "Nie uda\u0142o si\u0119: " + (e.message || e);
      });
  }

  function renderTools() {
    var body = document.getElementById("tools-body"); if (!body) return;
    var sel = document.getElementById("route"); var rid = sel ? sel.value : "";
    var nm = (sel && sel.options[sel.selectedIndex]) ? sel.options[sel.selectedIndex].text : "";
    var h = '';
    h += '<div class="qa-h" style="margin-top:18px">Wersje <span class="muted" style="font-weight:400;font-size:12px">(auto po DOSTOSUJ)</span></div>';
    var _sv = readSaved();
    if (!_sv.length) { h += '<div class="muted" style="font-size:13px;margin-bottom:8px">Brak wersji. Zr\u00f3b DOSTOSUJ \u2014 zapisze si\u0119 sama.</div>'; }
    else {
      h += '<div class="tw-vers">';
      _sv.forEach(function (e) {
        h += '<div class="tw-ver"><button class="tw-ver-load" data-id="' + e.id + '">' + esc(verName(e)) + '<span class="tw-ver-sub muted">' + esc(e.route_name || e.route_id) + '</span></button>'
          + '<button class="tw-ver-del" data-id="' + e.id + '" title="Usu\u0144">\u00d7</button></div>';
      });
      h += '</div>';
    }
    h += '<div class="qa-h" style="margin-top:18px">Wyprawa</div>';
    h += '<button class="dbtn tw-full" id="tw-cal">\uD83D\uDCC5 Dodaj do kalendarza</button>';
    h += '<button class="dbtn tw-full" id="tw-pdf">\uD83D\uDCC4 Raport wyprawy (PDF)</button>';
    h += '<button class="dbtn tw-full" id="tw-send">\u2709 Wy\u015blij e-mailem</button>';
    h += '<div id="tw-send-box" style="display:none;margin:4px 0 6px">'
       + '<input type="email" id="tw-mail" list="tw-mail-hist" placeholder="adres e-mail odbiorcy" '
       + 'style="width:100%;font-size:15px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);box-sizing:border-box">'
       + '<datalist id="tw-mail-hist"></datalist>'
       + '<button class="dbtn tw-full" id="tw-send-go" style="margin-top:6px">Wy\u015blij</button>'
       + '<div class="muted" id="tw-send-msg" style="font-size:13px;margin-top:4px"></div></div>';
    h += '<div id="tw-rsvp" style="margin:2px 0 6px"></div>';
    h += '<div class="qa-h" style="margin-top:18px">Udost\u0119pnij dni</div>';
    h += '<button class="dbtn tw-full" id="tw-addqbot">\u2795 Dodaj wszystkie dni do QBot (' + nDays + ' GPX)</button>';
    h += '<div class="muted" id="tw-addqbot-status" style="font-size:13px;margin:4px 0 12px"></div>';
    body.innerHTML = h;
    var _dm = document.getElementById("dminus"); if (_dm) _dm.onclick = function () { changeDays(-1); };
    var _dp = document.getElementById("dplus"); if (_dp) _dp.onclick = function () { changeDays(1); };
    Array.prototype.forEach.call(body.querySelectorAll(".tw-ver-load"), function (b) { b.onclick = function () { applySavedVersion(parseInt(b.getAttribute("data-id"), 10)); }; });
    Array.prototype.forEach.call(body.querySelectorAll(".tw-ver-del"), function (b) { b.onclick = function (ev) { ev.stopPropagation(); deleteSaved(parseInt(b.getAttribute("data-id"), 10)); }; });
    toolsRsvpPopulate(rid);
    var bcal = document.getElementById("tw-cal"); if (bcal) bcal.onclick = addWyprawaToCalendar;
    var bpdf = document.getElementById("tw-pdf"); if (bpdf) bpdf.onclick = openWyprawaPdf;
    var bsend = document.getElementById("tw-send"); if (bsend) bsend.onclick = function () {
      var bx = document.getElementById("tw-send-box"); if (!bx) return;
      var show = bx.style.display === "none"; bx.style.display = show ? "" : "none";
      if (show) toolsMailPopulate();
    };
    var bgo = document.getElementById("tw-send-go"); if (bgo) bgo.onclick = function () {
      var m = document.getElementById("tw-send-msg");
      var mail = ((document.getElementById("tw-mail") || {}).value || "").trim();
      var s2 = document.getElementById("route");
      if (!s2 || !s2.value) { if (m) { m.style.color = "#c0392b"; m.textContent = "Wybierz tras\u0119."; } return; }
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(mail)) { if (m) { m.style.color = "#c0392b"; m.textContent = "Podaj poprawny adres e-mail."; } return; }
      var nm2 = s2.options[s2.selectedIndex] ? s2.options[s2.selectedIndex].text : "";
      bgo.disabled = true; var _old = bgo.textContent; bgo.textContent = "Wysy\u0142am\u2026";
      if (m) { m.style.color = "var(--muted)"; m.textContent = "Sk\u0142adam raport i wysy\u0142am (przy pierwszym razie do ~40 s)\u2026"; }
      var u = "/api/wyprawa/send-email?route_id=" + encodeURIComponent(s2.value)
            + "&cuts=" + encodeURIComponent(cuts.join(","))
            + "&to=" + encodeURIComponent(mail)
            + "&name=" + encodeURIComponent(nm2);
      fetch(u, { method: "POST" }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          bgo.disabled = false; bgo.textContent = _old;
          if (!res.ok || !res.j || res.j.status !== "ok") throw new Error((res.j && res.j.detail) || "b\u0142\u0105d wysy\u0142ki");
          if (m) { m.style.color = "#2f7a3a"; m.textContent = "\u2713 Wys\u0142ano do " + mail + " \u00b7 PDF + " + res.j.gpx_days + " GPX. Odbiorca dostanie przyciski Wezm\u0119 udzia\u0142 / Nie dam rady."; }
          toolsMailPopulate(); toolsRsvpPopulate(s2.value);
        }).catch(function (err) {
          bgo.disabled = false; bgo.textContent = _old;
          if (m) { m.style.color = "#c0392b"; m.textContent = "Nie uda\u0142o si\u0119: " + (err.message || err); }
        });
    };
    var baq = document.getElementById("tw-addqbot"); if (baq) baq.onclick = function () { toolsAddQbot(baq, document.getElementById("tw-addqbot-status")); };
    Array.prototype.forEach.call(body.querySelectorAll(".tw-gpx"), function (b) {
      b.onclick = function () {
        if (!rid) { alert("Wybierz trase"); return; }
        var u = "/api/planer/dzien/gpx?route_id=" + encodeURIComponent(rid)
              + "&from=" + b.getAttribute("data-from") + "&to=" + b.getAttribute("data-to")
              + "&day=" + b.getAttribute("data-day") + "&name=" + encodeURIComponent(nm);
        window.open(u, "_blank");
      };
    });
  }

  function applyMapMode() {
    if (typeof IS_PRINT !== "undefined" && IS_PRINT) { document.body.classList.remove("map-bg"); document.body.classList.remove("mb-all"); var _wp = document.querySelector(".wrap"); if (_wp) _wp.style.paddingTop = ""; return; }
    var allView = (currentView == null);
    var framed = allView && mapStiffened;
    document.body.classList.toggle("map-bg", !framed);
    document.body.classList.toggle("mb-all", !framed && allView);
    document.body.classList.toggle("mb-day", !framed && !allView);
    var _wrap = document.querySelector(".wrap"), _hdr = document.querySelector("header");
    if (_wrap) { if (!framed && _hdr) { requestAnimationFrame(function () { _wrap.style.paddingTop = _hdr.offsetHeight + "px"; }); } else { _wrap.style.paddingTop = ""; } }
    var btn = document.getElementById("map-bg-toggle");
    if (btn) {
      btn.style.display = allView ? "" : "none";
      btn.textContent = framed ? "\ud83d\uddfa Poka\u017c map\u0119 jako t\u0142o" : "\ud83d\udccc Usztywnij map\u0119 (edycja etap\u00f3w)";
    }
    if (map) { [60, 280, 550].forEach(function (ms) { setTimeout(function () { try { map.invalidateSize(false); } catch (e) {} }, ms); }); }
  }

  function initMapBg() {
    var mbt = document.getElementById("map-bg-toggle");
    if (mbt) mbt.onclick = function () { mapStiffened = !mapStiffened; applyMapMode(); };
    window.addEventListener("resize", applyMapMode);
    applyMapMode();
  }

  function toolsInit() {
    var tab = document.getElementById("tools-tab");
    var x = document.getElementById("tools-x");
    var bd = document.getElementById("tools-backdrop");
    if (tab) tab.onclick = function () { document.body.classList.toggle("qaside-open"); if (document.body.classList.contains("qaside-open")) renderTools(); };
    if (x) x.onclick = function () { document.body.classList.remove("qaside-open"); };
    if (bd) bd.onclick = function () { document.body.classList.remove("qaside-open"); };
  }

  window.__planerPrint = {
    ready: function () { return !!(spine && spine.length > 1); },
    nDays: function () { return nDays; },
    dostosuj: function () { try { doDostosuj(); } catch (e) {} },
    dniReady: function () { return !!dniData; },
    view: function (v) { setView(v); },
    expandAll: function () {
      var mb = document.querySelector(".opis-more"); if (mb) mb.style.display = "block";
      var tg = document.querySelector(".opis-toggle"); if (tg) tg.style.display = "none";
      Array.prototype.forEach.call(document.querySelectorAll(".climb-row, .attr-row"), function (r) {
        var box = r.nextElementSibling;
        if (box && getComputedStyle(box).display === "none") { try { r.click(); } catch (e) {} }
      });
      Array.prototype.forEach.call(document.querySelectorAll(".climb-row .poi-meta, .attr-row .poi-meta"), function (sp) {
        sp.textContent = sp.textContent.replace(/\s*\u25be\s*$/, "");
      });
    },
    snap: function () { var w = document.querySelector(".wrap"); return w ? w.innerHTML : ""; },
    snapBaked: function (d) {
      // jak snap(), ale #map w KOPII zastapione statycznym obrazkiem (d).
      // Zywa mapa nietknieta -> kolejny dzien moze wyzoomowac sie do swojego etapu.
      var w = document.querySelector(".wrap"); if (!w) return "";
      var clone = w.cloneNode(true);
      var m = clone.querySelector("#map");
      if (m) {
        m.innerHTML = "";
        if (d) { var img = new Image(); img.src = d; img.style.cssText = "width:100%;height:auto;display:block;border-radius:12px"; m.appendChild(img); }
        m.style.height = "auto";
      }
      return clone.innerHTML;
    },
    assemble: function (parts) {
      var html = parts.map(function (p, i) {
        return '<section class="print-sec"' + (i ? ' style="margin-top:28px;border-top:2px solid #d8ceb6;padding-top:20px"' : '') + '>' + p + '</section>';
      }).join("");
      document.body.innerHTML = '<div class="wrap">' + html + '</div>';
      document.body.classList.add("print");
    },
    cleanupDayUI: function () {
      var g = document.getElementById("d-gpx");
      if (g && g.closest) { var sc = g.closest(".dsec"); if (sc) sc.style.display = "none"; }
    }
  };
  /* ---------------- POGODA (zakladka w lewym menu) ----------------
     Prognoza: silnik METEO na osi 50 m (WBGT z cieniem, odczuwalna, opad, burza,
     wiatr wzgledem kierunku jazdy, slonce). Poza horyzontem prognozy: klimat ERA5.
     Kazdy dzien liczony osobno - jedno zapytanie na dzien, cache po stronie serwera. */
  var pgStart = "09:00", pgData = {}, pgLoading = {}, pgKeyLast = "", pgAll = false;

  function pgCuts() {
    var c = [];
    for (var i = 0; i < nDays - 1; i++) { try { c.push(computeStage(i).to.toFixed(2)); } catch (e) {} }
    return c.join(",");
  }
  function pgKey() { return currentRouteId() + "|" + currentDeparture() + "|" + pgStart + "|" + pgCuts(); }
  function pgDateFor(i) {
    var dep = currentDeparture(); if (!dep) return "";
    var d = new Date(dep + "T12:00:00"); d.setDate(d.getDate() + i);
    var m = d.getMonth() + 1, dd = d.getDate();
    return d.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (dd < 10 ? "0" : "") + dd;
  }
  function pgNum(v, nd) {
    if (v === null || v === undefined || v === "") return "b/d";
    return Number(v).toFixed(nd == null ? 1 : nd).replace(".", ",");
  }
  function pgMinTxt(m) {
    if (m == null) return "b/d";
    var h = Math.floor(m / 60), r = Math.round(m % 60);
    return h ? (h + " h " + r + " min") : (r + " min");
  }
  function pgWiatr(v) {
    if (v == null) return "b/d";
    if (v > 0.3) return pgNum(v) + " m/s z tyłu";
    if (v < -0.3) return pgNum(Math.abs(v)) + " m/s w czoło";
    return "bez składowej wzdłuż";
  }
  function pgCard(lab, val, sub, cls) {
    return '<div class="pg-card' + (cls ? " " + cls : "") + '"><div class="lab">' + lab + "</div>" +
      '<div class="val">' + val + "</div>" + (sub ? '<div class="sub">' + sub + "</div>" : "") + "</div>";
  }

  function pgAlertHTML(a) {
    var sev = String(a.severity || "").replace(/-/g, "");
    var t = [];
    if (a.km_od != null) t.push("km " + pgNum(a.km_od, 0) + "\u2013" + pgNum(a.km_do, 0));
    if (a.eta_od) t.push(a.eta_od + "\u2013" + a.eta_do);
    if (a.minuty != null) t.push(pgMinTxt(a.minuty));
    if (a.wbgt_max != null) t.push("WBGT " + pgNum(a.wbgt_max) + " \u00b0C");
    if (a.opad_max_mm != null) t.push("opad do " + pgNum(a.opad_max_mm) + " mm/h");
    if (a.prawdopod != null) t.push(a.prawdopod + "% szans");
    if (a.cape_max != null) t.push("CAPE " + Math.round(a.cape_max));
    if (a.porywy_max_ms != null) t.push("porywy " + pgNum(a.porywy_max_ms) + " m/s");
    if (a.utci_avg != null) t.push("odczuwalna " + pgNum(a.utci_avg) + " \u00b0C");
    if (a.kategoria) t.push(esc(a.kategoria));
    if (a.trend) t.push(esc(a.trend));
    if (a.powod) t.push(esc(a.powod));
    if (a.opis) t.push(esc(a.opis));
    return '<div class="pg-al ' + sev + '"><b>' + esc(a.severity || "") + " " + esc(a.typ || "") +
      "</b><span>" + t.join(" \u00b7 ") + "</span></div>";
  }

  function pgPrognozaHTML(d) {
    var p = d.podsumowanie || {}, sl = d.slonce || {}, h = "";
    var wetCls = ((p.opad_mm || 0) >= 0.5 || (p.opad_prob_max || 0) >= 40) ? "wet" : "";
    var hotCls = (p.wbgt_exceed != null && p.wbgt_exceed > 0) ? "hot" : "";

    h += '<div class="pg-cards">';
    h += pgCard("Temperatura", pgNum(p.temp_min) + "\u2013" + pgNum(p.temp_max) + " <small>\u00b0C</small>",
      "\u015brednio " + pgNum(p.temp_sr) + " \u00b0C");
    h += pgCard("Odczuwalna", pgNum(p.odczuwalna_min) + "\u2013" + pgNum(p.odczuwalna_max) + " <small>\u00b0C</small>",
      "temp + wilgotno\u015b\u0107 + wiatr + s\u0142o\u0144ce");
    h += pgCard("Wilgotno\u015b\u0107", pgNum(p.rh_min, 0) + "\u2013" + pgNum(p.rh_max, 0) + " <small>%</small>",
      "\u015brednio " + pgNum(p.rh_sr, 0) + "%");
    h += pgCard("Opad", pgNum(p.opad_mm) + " <small>mm</small>",
      "szansa do " + (p.opad_prob_max == null ? "b/d" : p.opad_prob_max + "%") +
      (p.minuty_deszczu ? " \u00b7 " + pgMinTxt(p.minuty_deszczu) + " w deszczu" : " \u00b7 sucho"), wetCls);
    h += pgCard("Wiatr", pgNum(p.wiatr_sr_ms) + " <small>m/s \u015br.</small>",
      pgWiatr(p.wiatr_wzdluz_sr_ms) + " \u00b7 w poprzek " + pgNum(p.wiatr_poprzek_sr_ms) +
      " \u00b7 porywy do " + pgNum(p.porywy_max_ms));
    h += pgCard("WBGT max", pgNum(p.wbgt_max) + " <small>\u00b0C</small>",
      "km " + pgNum(p.wbgt_km, 0) + " o " + (p.wbgt_eta || "?") +
      (p.wbgt_exceed > 0 ? " \u00b7 ponad limit o " + pgNum(p.wbgt_exceed) : " \u00b7 w limicie"), hotCls);
    h += pgCard("S\u0142o\u0144ce", (sl.wschod || "?") + "\u2013" + (sl.zachod || "?"),
      "dzie\u0144 " + pgNum(sl.dzien_h) + " h \u00b7 s\u0142o\u0144ca " + pgNum(sl.sloneczne_h) +
      " h" + (sl.uv_max != null ? " \u00b7 UV " + pgNum(sl.uv_max) : ""));
    h += pgCard("Na trasie", (p.eta_od || "?") + "\u2013" + (p.eta_do || "?"),
      pgMinTxt(p.minuty) + " \u00b7 " + pgNum(p.km_od, 0) + "\u2013" + pgNum(p.km_do, 0) + " km");
    h += "</div>";

    var al = d.alerty || [];
    if (al.length) { for (var i = 0; i < al.length; i++) h += pgAlertHTML(al[i]); }
    else h += '<div class="pg-al FLAGA" style="background:var(--good-bg);color:var(--good)"><b>brak alert\u00f3w</b>' +
      "<span>\u017caden pr\u00f3g upa\u0142u, deszczu, burzy ani zimna nie zosta\u0142 przekroczony</span></div>";

    var t = d.tabela_30min || [];
    if (t.length) {
      h += '<table class="pg-tab"><thead><tr><th>Godz.</th><th>km</th><th>Temp.</th><th>Odczuw.</th>' +
        "<th>Wilg.</th><th>WBGT</th><th>Opad</th><th>Wiatr wzd\u0142u\u017c</th><th>Burza</th></tr></thead><tbody>";
      for (var j = 0; j < t.length; j++) {
        var r = t[j], op = r.opad || {}, bu = r.burza || {}, oc = r.odczuwalna || {};
        var hot = (r.wbgt_max != null && r.wbgt_max >= 26) ? " class=\"hot\"" : "";
        var rain = ((op.mm || 0) >= 0.5 || (op.prob || 0) >= 40) ? " class=\"rainy\"" : "";
        h += "<tr><td>" + esc(r.okno || "") + "</td>" +
          "<td>" + pgNum(r.km_od, 0) + "\u2013" + pgNum(r.km_do, 0) + "</td>" +
          "<td>" + pgNum(r.temp_c) + "</td>" +
          "<td>" + pgNum(oc.srednia, 0) + "</td>" +
          "<td>" + pgNum(r.rh_pct, 0) + "%</td>" +
          "<td" + hot + ">" + pgNum(r.wbgt_max) + "</td>" +
          "<td" + rain + ">" + pgNum(op.mm) + " mm" + (op.prob != null ? " / " + op.prob + "%" : "") + "</td>" +
          "<td>" + (r.wiatr_wzdluz_ms == null ? "b/d" : pgNum(r.wiatr_wzdluz_ms)) + "</td>" +
          "<td>" + (bu.poziom ? esc(bu.poziom) : "\u2013") +
          (bu.porywy_ms != null ? " (" + pgNum(bu.porywy_ms) + ")" : "") + "</td></tr>";
      }
      h += "</tbody></table>";
    }
    var cav = d.caveats || [];
    if (cav.length) {
      h += '<div class="pg-caveats"><ul>';
      for (var k = 0; k < cav.length; k++) h += "<li>" + esc(cav[k]) + "</li>";
      h += "</ul></div>";
    }
    return h;
  }

  function pgKlimatHTML(d) {
    var k = d.klimat || {}, t = k.temp || {}, o = k.opad || {}, w = k.wiatr || {},
        r = k.rh || {}, po = k.podstawa || {}, h = "";
    h += '<p class="pg-note" style="margin:0 0 8px"><b>To nie jest prognoza.</b> ' +
      esc(d.powod_klimatu || "") + " Poni\u017cej klimat z ostatnich " + (po.lata || "?") +
      " lat (\u00b1" + (po.okno_dni || "?") + " dni wok\u00f3\u0142 tej daty, " +
      (po.obserwacji_dni || "?") + " dni obserwacji, ERA5).</p>";
    h += '<div class="pg-cards">';
    h += pgCard("Temp. maks.", pgNum(t.max_sr) + " <small>\u00b0C \u015br.</small>",
      "co 10. dzie\u0144 powy\u017cej " + pgNum(t.max_p90) + " \u00b7 rekord " + pgNum(t.max_rekord));
    h += pgCard("Temp. min.", pgNum(t.min_sr) + " <small>\u00b0C \u015br.</small>",
      "co 10. dzie\u0144 poni\u017cej " + pgNum(t.min_p10) + " \u00b7 rekord " + pgNum(t.min_rekord));
    h += pgCard("Ca\u0142a doba", pgNum(t.sr) + " <small>\u00b0C \u015br.</small>", "\u015brednia dobowa");
    h += pgCard("Szansa opadu", (o.szansa_dnia_z_opadem_pct == null ? "b/d" : o.szansa_dnia_z_opadem_pct + " <small>%</small>"),
      "dzie\u0144 z opadem \u2265 1 mm", (o.szansa_dnia_z_opadem_pct >= 35 ? "wet" : ""));
    h += pgCard("Opad dobowy", pgNum(o.mm_dobowe_sr) + " <small>mm \u015br.</small>",
      "co 10. dzie\u0144 powy\u017cej " + pgNum(o.mm_dobowe_p90) + " mm \u00b7 " +
      pgNum(o.godzin_opadu_sr) + " h padania");
    h += pgCard("Wilgotno\u015b\u0107", pgNum(r.sr, 0) + " <small>% \u015br.</small>", "p90 " + pgNum(r.p90, 0) + "%");
    h += pgCard("Wiatr", pgNum(w.max_dobowy_sr_ms) + " <small>m/s</small>",
      "maks. dobowy \u00b7 p90 " + pgNum(w.max_dobowy_p90_ms) + " \u00b7 porywy p90 " + pgNum(w.porywy_p90_ms));
    h += pgCard("S\u0142o\u0144ce", pgNum((k.slonce || {}).radiacja_mj_sr) + " <small>MJ/m\u00b2</small>",
      "dobowa suma promieniowania");
    h += "</div>";
    var uw = k.uwagi || [];
    if (uw.length) {
      h += '<div class="pg-caveats"><ul>';
      for (var i = 0; i < uw.length; i++) h += "<li>" + esc(uw[i]) + "</li>";
      h += "</ul></div>";
    }
    return h;
  }

  function pgDayHTML(i) {
    var st, c = STAGE_COLORS[i % STAGE_COLORS.length];
    try { st = computeStage(i); } catch (e) { return ""; }
    var d = pgData[i], h = '<div class="pg-day" data-day="' + i + '">';
    h += '<div class="pg-day-h"><span class="dot" style="background:' + c + '"></span>' +
      "<b>Dzie\u0144 " + (i + 1) + "</b>" +
      '<span class="pg-km">' + st.from.toFixed(0) + "\u2013" + st.to.toFixed(0) + " km \u00b7 " +
      pgDateFor(i) + "</span>";
    if (d && d.ok && d.tryb === "klimat") h += '<span class="pg-tag klimat">klimat</span>';
    else if (d && d.ok) h += '<span class="pg-tag">prognoza' + (d.cached ? " \u00b7 z cache" : "") + "</span>";
    else if (d && !d.ok) h += '<span class="pg-tag brak">brak danych</span>';
    h += '<button class="pg-btn pg-one" data-day="' + i + '"' + (pgLoading[i] || pgAll ? " disabled" : "") +
      ">" + (pgLoading[i] ? "licz\u0119\u2026" : (d ? "Przelicz" : "Policz")) + "</button></div>";
    if (pgLoading[i]) h += '<p class="pg-note" style="margin:0">Licz\u0119 pogod\u0119 dla tego dnia\u2026</p>';
    else if (!d) h += '<p class="pg-note" style="margin:0">Jeszcze nie policzone.</p>';
    else if (!d.ok) h += '<p class="pg-err">' + esc(d.powod || "Brak danych.") + "</p>";
    else if (d.tryb === "klimat") h += pgKlimatHTML(d);
    else h += pgPrognozaHTML(d);
    return h + "</div>";
  }

  function pgFetch(i, cb) {
    var url = "/api/planer/pogoda?route_id=" + encodeURIComponent(currentRouteId()) +
      "&start=" + encodeURIComponent(currentDeparture()) +
      "&day=" + (i + 1) +
      "&cuts=" + encodeURIComponent(pgCuts()) +
      "&start_time=" + encodeURIComponent(pgStart);
    pgLoading[i] = true; renderPogoda();
    fetch(url).then(function (r) { return r.json(); }).then(function (j) {
      pgData[i] = j; pgLoading[i] = false; renderPogoda(); if (cb) cb();
    }).catch(function (e) {
      pgData[i] = { ok: false, powod: "B\u0142\u0105d po\u0142\u0105czenia: " + e };
      pgLoading[i] = false; renderPogoda(); if (cb) cb();
    });
  }

  function pgFetchAll() {
    pgAll = true;
    var i = 0;
    (function step() {
      if (i >= nDays) { pgAll = false; renderPogoda(); return; }
      var k = i++;
      pgFetch(k, step);
    })();
  }

  function renderPogoda() {
    var box = document.getElementById("pogoda-panel"); if (!box) return;
    var rid = currentRouteId(), dep = currentDeparture();
    if (!rid) { box.innerHTML = '<p class="pg-note">Wybierz tras\u0119.</p>'; return; }
    if (!dep) { box.innerHTML = '<p class="pg-note">Ustaw <b>Dat\u0119 wyprawy</b> u g\u00f3ry \u2014 bez daty nie ma czego liczy\u0107.</p>'; return; }
    if (!nDays || !spine || spine.length < 2) { box.innerHTML = '<p class="pg-note">Poczekaj na za\u0142adowanie trasy.</p>'; return; }
    var key = pgKey();
    if (pgKeyLast && pgKeyLast !== key) { pgData = {}; pgLoading = {}; }
    pgKeyLast = key;

    var h = '<div class="pg-bar"><div><label>Godzina startu (ka\u017cdego dnia)</label>' +
      '<input type="time" id="pg-start" value="' + pgStart + '"></div>' +
      '<button class="pg-btn" id="pg-all" style="margin-left:0"' + (pgAll ? " disabled" : "") + ">" +
      (pgAll ? "licz\u0119\u2026" : "Policz wszystkie dni") + "</button></div>" +
      '<p class="pg-note">Prognoza si\u0119ga ok. 16 dni \u2014 dla dalszych dat liczony jest <b>klimat</b> ' +
      "(ERA5, 10 lat), jawnie oznaczony. Dane liczone na osi 50 m w momencie przejazdu (ETA z modelu czasu).</p>";
    for (var i = 0; i < nDays; i++) h += pgDayHTML(i);
    box.innerHTML = h;

    var si = document.getElementById("pg-start");
    if (si) si.onchange = function () {
      pgStart = this.value || "09:00"; pgData = {}; pgLoading = {}; renderPogoda();
    };
    var ab = document.getElementById("pg-all");
    if (ab) ab.onclick = function () { if (!pgAll) pgFetchAll(); };
    var ones = box.querySelectorAll(".pg-one");
    for (var y = 0; y < ones.length; y++) {
      ones[y].onclick = function () { pgFetch(parseInt(this.getAttribute("data-day"), 10)); };
    }
  }
  window.__planerPogoda = renderPogoda;


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

  document.addEventListener("DOMContentLoaded", init);
})();
