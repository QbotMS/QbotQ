/* Zdrowie -> Serce, NOWY UKLAD (2026-10-20, sesja spo2-2010). Zastepuje forma-serce.js + zdrowie-serce.js + zdrowie-spo2.js w zdrowie.html.
   Poziom 1: werdykt (AI + punkty QBota) i 6 kafli. Wspolna os czasu (6 paneli, jeden kursor, zoom, znaczniki alkoholu).
   Poziom 2: szczegoly JEDNEGO kafla (cisnienie+PDF+jak mierzyc, EKG+przebieg+AI, oddech w nocy minuta po minucie...).
   Dane: /api/forma/heart (qbot_heart), /api/jedzenie/heart_plus, /api/jedzenie/hrr, /api/jedzenie/spo2 (qbot_spo2), /api/jedzenie/alcohol,
   /api/forma/heart/ai, /api/forma/ecg, /api/forma/ecg/ai. Dok.: docs/SERCE.md, docs/SPO2.md, wiki zdrowie/serce.md */
(function () {
  "use strict";
  var sec = document.getElementById("t-serce"); if (!sec) return;
  var H, P, R, S, ALC = {}, NIGHTS = {}, CH = null, NCH = null, ECH = null, SEL = "rhr", RANGE = {d: 90}, ZOOM = null, NIGHT = null, NZ = null, done = false;
  var VIS = {rhr: true, hrv: true, bp: true, br: true, hrp: true, hrr: true, alc: true};
  var NV = {spo2: true, bv: true, resp: true, hr: false};

  var st = document.createElement("style");
  st.textContent =
    "#sz .sz-sum ul{margin:6px 0 0;padding:0;list-style:none;font-size:14px}#sz .sz-sum li{padding:5px 0;border-top:1px solid var(--line);display:flex;gap:8px}#sz .sz-sum li:first-child{border-top:0}" +
    "#sz .sz-sum li i{flex:0 0 8px;height:8px;border-radius:50%;margin-top:7px}#sz .sz-more{background:none;border:0;padding:0;font:inherit;font-size:12.5px;color:var(--accent-ink);cursor:pointer;margin-top:4px}" +
    "#sz .sz-ai{font-size:15px;line-height:1.55;margin:4px 0 6px}" +
    "#sz .sz-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:12px}" +
    "#sz .sz-tile{appearance:none;text-align:left;font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:14px;padding:11px 13px;cursor:pointer}" +
    "#sz .sz-tile:hover{border-color:var(--line2)}#sz .sz-tile.on{border:2px solid var(--accent);padding:10px 12px}" +
    "#sz .sz-tile .n{font-size:12.5px;color:var(--ink2)}#sz .sz-tile .v{font-size:24px;font-weight:600;margin-top:3px;font-variant-numeric:tabular-nums;line-height:1.15}" +
    "#sz .sz-tile .v small{font-size:13px;color:var(--muted);font-weight:500;margin-left:3px}#sz .sz-tile .s{font-size:12.5px;margin-top:3px}" +
    "#sz .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:1px}" +
    "#sz .c-good{color:var(--good)}#sz .c-warn{color:var(--warn)}#sz .c-bad{color:var(--bad)}#sz .c-info{color:var(--ink2)}" +
    "#sz .sz-rng{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:8px 0}#sz .sz-rng button,#sz .sz-btn{appearance:none;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;padding:4px 10px;font:inherit;font-size:13px;cursor:pointer;text-decoration:none;display:inline-block}" +
    "#sz .sz-rng button.on{background:var(--accent-bg);border-color:var(--accent);color:var(--accent-ink);font-weight:600}#sz .sz-rng input{font:inherit;font-size:13px;padding:3px 6px;border:1px solid var(--line);border-radius:8px;background:var(--well);color:var(--ink)}" +
    "#sz .sz-chips{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 8px}#sz .sz-chip{appearance:none;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:3px 10px;font:inherit;font-size:12.5px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}" +
    "#sz .sz-chip i{width:12px;height:4px;border-radius:2px;display:inline-block}#sz .sz-chip.on{color:var(--ink);background:var(--well);border-color:var(--line2)}#sz .sz-chip:not(.on) i{filter:grayscale(1);opacity:.5}" +
    "#sz .sz-chw{position:relative;height:460px}#sz .sz-hint{font-size:12px;color:var(--muted);margin-top:6px}" +
    "#sz .sz-det h2{margin:0 0 4px}#sz .sz-lead{font-size:14px;color:var(--ink2);margin-bottom:10px}" +
    "#sz .sz-kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:8px 0 12px}#sz .sz-kv div{background:var(--well);border-radius:10px;padding:8px 10px}" +
    "#sz .sz-kv b{display:block;font-size:18px;font-variant-numeric:tabular-nums}#sz .sz-kv span{font-size:12px;color:var(--ink2)}" +
    "#sz .sz-facts{margin:6px 0 0;padding:0;list-style:none;font-size:14px}#sz .sz-facts li{padding:5px 0;border-top:1px solid var(--line)}#sz .sz-facts li:first-child{border-top:0}" +
    "#sz table.sz-tb{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums;margin-top:8px}#sz table.sz-tb th{text-align:left;font-weight:500;color:var(--ink2);border-bottom:1px solid var(--line);padding:5px 6px}" +
    "#sz table.sz-tb td{border-bottom:1px solid var(--line);padding:6px}#sz .sz-tbw{overflow-x:auto}#sz tr.sz-ecg{cursor:pointer}#sz tr.sz-ecg.on{background:var(--well)}" +
    "#sz .sz-nch{position:relative;height:280px;margin-top:6px}#sz .sz-ech{position:relative;height:220px;margin-top:6px}" +
    "#sz details.sz-how summary{cursor:pointer;font-weight:600;margin-top:12px}#sz details.sz-how p{font-size:14px;line-height:1.55;margin:6px 0}" +
    "#sz .muted{color:var(--muted);font-size:13px}#sz .sz-aibox{background:var(--well);border-radius:10px;padding:8px 10px;margin-top:8px;font-size:14px;line-height:1.5}" +
    "@media(max-width:600px){#sz .sz-chw{height:520px}#sz .sz-tile .v{font-size:21px}}";
  document.head.appendChild(st);

  function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim() || "#888"; }
  function lv(s) { return s === "bad" ? "bad" : s === "warn" ? "warn" : s === "good" ? "good" : "info"; }
  function col(s) { return css({good: "--good", warn: "--warn", bad: "--bad"}[lv(s)] || "--muted"); }
  function pl(x, d) { if (x == null) return "–"; var v = d == null ? x : Math.round(x * Math.pow(10, d)) / Math.pow(10, d); return String(v).replace(".", ","); }
  function sg(x, d) { return x == null ? "–" : (x > 0 ? "+" : "") + pl(x, d == null ? 1 : d); }
  function dm(iso) { return iso.slice(8, 10) + "." + iso.slice(5, 7); }
  function dmy(iso) { return dm(iso) + "." + iso.slice(0, 4); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function get(u, opt) { return fetch(u, Object.assign({credentials: "same-origin"}, opt || {})).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }); }
  function $(id) { return document.getElementById(id); }
  function iso(d) { return d.toISOString().slice(0, 10); }
  function addDays(s, n) { return iso(new Date(Date.parse(s) + n * 864e5)); }
  function avgEvH() { var n = S.nights.slice(-30), a = n.map(function (x) { return x.events / (x.n / 60); }); return a.length ? a.reduce(function (s, v) { return s + v; }, 0) / a.length : null; }

  function build() {
    sec.innerHTML = "<div id='sz'><div class='card sz-sum' id='sz-sum'><p class='muted'>ładuję…</p></div><div class='sz-tiles' id='sz-tiles'></div>" +
      "<div class='card' style='margin-top:12px'><div class='cardhead'><p class='lbl'><span class='tip' tabindex='0' data-tip='Wszystkie pomiary serca na jednej osi dni: tętno spoczynkowe z normą, HRV z pasem normy (60 nocy), ciśnienie (średnia dnia), noce (minuty spadków SpO2, kolor = ocena; trójkąt = oddech szybszy niż norma), tętno przy mocy i HRR60 z jazd. Przerywane pionowe linie: alkohol.'>Wspólna oś czasu</span></p><span class='sub'>jeden kursor dla wszystkich paneli</span></div>" +
      "<div class='sz-rng' id='sz-rng'><button data-d='90' class='on'>90 dni</button><button data-d='180'>180 dni</button><button data-d='365'>rok</button>" +
      "<span style='margin-left:6px;font-size:12.5px;color:var(--muted)'>od</span><input type='date' id='sz-ra'><span style='font-size:12.5px;color:var(--muted)'>do</span><input type='date' id='sz-rb'><button id='sz-zr' hidden>Pokaż całość</button></div>" +
      "<div class='sz-chips' id='sz-chips'></div><div class='sz-chw'><canvas id='sz-tl'></canvas></div>" +
      "<div class='sz-hint'>Najedź, żeby zobaczyć wszystkie wartości dnia. Przeciągnij — powiększenie, dwuklik — całość. Kliknij dzień z nocą — otworzy się „Oddech w nocy”.</div></div>" +
      "<div class='card sz-det' id='sz-det' style='margin-top:12px'></div></div>";
    $("sz-rng").addEventListener("click", function (e) { var b = e.target.closest("button[data-d]"); if (!b) return;
      sec.querySelectorAll("#sz-rng button[data-d]").forEach(function (x) { x.classList.toggle("on", x === b); });
      $("sz-ra").value = $("sz-rb").value = ""; RANGE = {d: +b.dataset.d}; ZOOM = null; loadAlc().then(draw); });
    ["sz-ra", "sz-rb"].forEach(function (id) { $(id).addEventListener("change", function () {
      sec.querySelectorAll("#sz-rng button[data-d]").forEach(function (x) { x.classList.remove("on"); });
      RANGE = {a: $("sz-ra").value || undefined, b: $("sz-rb").value || undefined, d: 365}; ZOOM = null; loadAlc().then(draw); }); });
    $("sz-zr").onclick = function () { ZOOM = null; draw(); };
  }

  /* ================= poziom 1 ================= */
  function summary() {
    var pts = (H.points || []).filter(function (p) { return !/^(Talia|BMI)/.test(p.text); }).concat(H.nexus || []);
    var ord = {bad: 0, warn: 1, info: 2, good: 3};
    pts.sort(function (a, b) { return ord[lv(a.status)] - ord[lv(b.status)]; });
    var top = pts.filter(function (p) { return lv(p.status) !== "good"; }), ok = pts.filter(function (p) { return lv(p.status) === "good"; });
    var nw = top.filter(function (p) { return lv(p.status) !== "info"; }).length;
    var head = nw === 0 ? "Serce w normie — nic nie wymaga uwagi." : nw === 1 ? "Jedna rzecz do obserwacji, reszta w normie." : nw + " rzeczy do obserwacji, reszta w normie.";
    function li(p) { return "<li><i style='background:" + col(p.status) + "'></i><span>" + esc(p.text) + "</span></li>"; }
    $("sz-sum").innerHTML = "<div class='cardhead'><p class='lbl'><span class='tip' tabindex='0' data-tip='Porównanie ostatnich 28 dni z Twoją normą z roku. Progi: tętno spoczynkowe +3 uwaga / +5 wyraźnie; tętno przy mocy +5 / +8; ciśnienie domowe 135/85; oddech w nocy: spadki SpO2 na godzinę (próg lekarski 5/h). Sygnały do obserwacji, nie diagnoza. Talia, waga i BMI — w zakładce Ciało.'>Serce — co mówią dane</span></p><span class='sub'>" + dmy(H.today) + "</span></div>" +
      "<div style='font-size:17px;font-weight:600;margin-top:4px'>" + head + "</div><div class='sz-ai' id='sz-ai'><span class='muted'>Łączna analiza AI…</span></div>" +
      "<ul>" + top.map(li).join("") + "</ul>" +
      (ok.length ? "<button class='sz-more' id='sz-okm'>+ " + ok.length + " w normie — pokaż</button><ul id='sz-okl' hidden>" + ok.map(li).join("") + "</ul>" : "");
    var b = $("sz-okm"); if (b) b.onclick = function () { var l = $("sz-okl"); l.hidden = !l.hidden; b.textContent = (l.hidden ? "+ " : "− ") + ok.length + " w normie — " + (l.hidden ? "pokaż" : "ukryj"); };
    loadAi();
  }
  function showAi(a) { var el = $("sz-ai"); if (!el) return; el.innerHTML = a ? (a.zdania || []).map(esc).join(" ") + " <span class='muted' style='font-size:11.5px;white-space:nowrap'>· AI na danych QBota, " + esc(a.at || "") + ", nie diagnoza</span>" : "<span class='muted'>Łączna analiza AI niedostępna.</span>"; }
  function loadAi() {
    get("/api/forma/heart/ai").then(function (j) { if (j.ai) return showAi(j.ai);
      $("sz-ai").innerHTML = "<span class='muted'>Łączna analiza AI… kilka sekund</span>";
      return get("/api/forma/heart/ai", {method: "POST"}).then(function (k) { showAi(k.ai); }); }).catch(function () { showAi(null); });
  }

  function tiles() {
    var V = S.verdict || {}, L = V.last || {}, s7 = P.hrv.status7 || {}, bp = H.bp.summary, e = H.ecg.last || {};
    var T = [
      {k: "rhr", n: "Tętno spoczynkowe", v: pl(H.rhr.recent, 0), u: "ud./min", st: H.rhr.delta >= 5 ? "bad" : H.rhr.delta >= 3 ? "warn" : "good", s: sg(H.rhr.delta) + " vs norma " + pl(H.rhr.norm, 0) + " (28 dni)"},
      {k: "hrv", n: "HRV · 7 nocy", v: pl(s7.avg7, 0), u: "ms", st: s7.level, s: (s7.label || "–") + " (" + pl(s7.lo, 0) + "–" + pl(s7.hi, 0) + ")"},
      {k: "bp", n: "Ciśnienie · seria", v: bp ? bp.sys + "/" + bp.dia : "–", u: "", st: bp ? (bp.fresh ? bp.status : "info") : "info", s: bp ? bp.label + " · " + dm(bp.to) + (bp.fresh ? "" : " · stare") : "zrób 7-dniową serię"},
      {k: "br", n: "Oddech w nocy", v: L.day ? (V.label || "–") : "–", u: "", st: V.status, s: L.day ? L.drop_min + " min spadków · " + pl(L.resp, 1) + " oddechu/min" : "brak danych"},
      {k: "fit", n: "Serce w wysiłku", v: pl(H.hrp.recent, 0), u: "przy " + H.hrp.band, st: H.hrp.delta >= 8 ? "bad" : H.hrp.delta >= 5 ? "warn" : "good", s: sg(H.hrp.delta) + " vs norma · HRR60 " + pl(R.recent, 0) + " (norma " + pl(R.norm, 0) + ")"},
      {k: "ecg", n: "EKG · ostatnie", v: e.local ? dm(e.local.slice(0, 10)) : "–", u: "", st: e.local ? (e.ok ? (H.ecg.fresh ? "good" : "info") : "bad") : "info", s: e.label || "brak nagrań"}
    ];
    $("sz-tiles").innerHTML = T.map(function (t) {
      return "<button class='sz-tile" + (t.k === SEL ? " on" : "") + "' data-k='" + t.k + "'><div class='n'>" + t.n + "</div><div class='v'>" + esc(t.v) + (t.u ? "<small>" + esc(t.u) + "</small>" : "") + "</div>" +
        "<div class='s c-" + lv(t.st) + "'><span class='dot' style='background:" + col(t.st) + "'></span>" + esc(t.s) + "</div></button>"; }).join("");
    $("sz-tiles").onclick = function (ev) { var b = ev.target.closest(".sz-tile"); if (!b) return; SEL = b.dataset.k; tiles(); detail(); $("sz-det").scrollIntoView({behavior: "smooth", block: "nearest"}); };
  }

  /* ================= wspolna os czasu ================= */
  var PANELS = [{k: "rhr", t: "Tętno spocz.", w: 2}, {k: "hrv", t: "HRV", w: 2}, {k: "bp", t: "Ciśnienie", w: 2}, {k: "br", t: "Oddech w nocy", w: 2}, {k: "hrp", t: "Tętno przy mocy", w: 1.5}, {k: "hrr", t: "HRR60", w: 1.5}];
  function labels() { var end = RANGE.b || H.today, start = RANGE.a || addDays(end, -(RANGE.d || 90) + 1), out = []; for (var d = start; d <= end; d = addDays(d, 1)) out.push(d); return out; }
  var vlines = {id: "szv", afterDatasetsDraw: function (ch) { if (!VIS.alc) return; var x = ch.scales.x, a = ch.chartArea, ctx = ch.ctx; ctx.save(); ctx.strokeStyle = css("--accent"); ctx.setLineDash([3, 3]); ctx.globalAlpha = .6;
    ch.data.labels.forEach(function (d, i) { if (ALC[d] && i >= x.min && i <= x.max) { var px = x.getPixelForValue(i); ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke(); } }); ctx.restore(); }};
  var plabels = {id: "szl", afterDraw: function (ch) { var ctx = ch.ctx; ctx.save(); ctx.font = "11px system-ui,sans-serif"; ctx.fillStyle = css("--ink2");
    PANELS.forEach(function (p) { var sc = ch.scales["y_" + p.k]; if (sc && VIS[p.k]) ctx.fillText(p.t, ch.chartArea.left + 4, sc.top + 11); }); ctx.restore(); }};
  function draw() {
    var L = labels(), idx = {}; L.forEach(function (d, i) { idx[d] = i; });
    function arr() { return L.map(function () { return null; }); }
    var rhr = arr(), hrv = arr(), hlo = arr(), hhi = arr(), h7 = arr(), sys = arr(), dia = arr(), br = arr(), brc = [], hrp = arr(), hrr = arr(), resp = arr();
    H.rhr.series.forEach(function (x) { if (x.date in idx) rhr[idx[x.date]] = x.rhr; });
    P.hrv.series.forEach(function (x) { if (x[0] in idx) hrv[idx[x[0]]] = x[1]; });
    P.hrv.band.forEach(function (x) { if (x[0] in idx) { h7[idx[x[0]]] = x[1]; hlo[idx[x[0]]] = x[2]; hhi[idx[x[0]]] = x[3]; } });
    var bpd = {}; (H.bp.all || []).forEach(function (x) { var d = x.local.slice(0, 10); (bpd[d] = bpd[d] || []).push(x); });
    Object.keys(bpd).forEach(function (d) { if (d in idx) { var a = bpd[d]; sys[idx[d]] = Math.round(a.reduce(function (s, x) { return s + x.sys; }, 0) / a.length); dia[idx[d]] = Math.round(a.reduce(function (s, x) { return s + x.dia; }, 0) / a.length); } });
    L.forEach(function (d, i) { var n = NIGHTS[d]; brc.push(n ? col(n.status) : "transparent"); if (n) { br[i] = n.drop_min; if ((n.resp_delta || 0) >= 1) resp[i] = n.drop_min + 6; } });
    H.hrp.series.forEach(function (x) { if (x.date in idx) hrp[idx[x.date]] = x.hr; });
    R.rides.forEach(function (x) { if (x.day in idx) hrr[idx[x.day]] = x.hrr60; });
    var c1 = css("--bad"), c2 = "#a78bfa", c3 = css("--warn"), c4 = css("--accent"), c5 = css("--ink2"), ds = [];
    function y(k) { return "y_" + k; }
    if (VIS.rhr) { ds.push({type: "line", label: "Tętno spocz.", data: rhr, yAxisID: y("rhr"), borderColor: c1, backgroundColor: c1, borderWidth: 1.4, pointRadius: 0, spanGaps: true, tension: .2, u: " ud./min"});
      ds.push({type: "line", label: "norma", data: L.map(function () { return H.rhr.norm; }), yAxisID: y("rhr"), borderColor: c1, borderDash: [4, 4], borderWidth: 1, pointRadius: 0, hideTip: true}); }
    if (VIS.hrv) { ds.push({type: "line", label: "hi", data: hhi, yAxisID: y("hrv"), borderWidth: 0, pointRadius: 0, fill: "+1", backgroundColor: "rgba(167,139,250,.18)", spanGaps: true, hideTip: true});
      ds.push({type: "line", label: "lo", data: hlo, yAxisID: y("hrv"), borderWidth: 0, pointRadius: 0, spanGaps: true, hideTip: true});
      ds.push({type: "line", label: "HRV 7 nocy", data: h7, yAxisID: y("hrv"), borderColor: c2, borderWidth: 1.8, pointRadius: 0, spanGaps: true, u: " ms"});
      ds.push({type: "line", label: "HRV noc", data: hrv, yAxisID: y("hrv"), showLine: false, pointRadius: 1.5, pointBackgroundColor: c2, borderColor: c2, u: " ms"}); }
    if (VIS.bp) { ds.push({type: "line", label: "skurczowe", data: sys, yAxisID: y("bp"), showLine: false, pointRadius: 3, pointBackgroundColor: c3, borderColor: c3, u: " mmHg"});
      ds.push({type: "line", label: "rozkurczowe", data: dia, yAxisID: y("bp"), showLine: false, pointRadius: 3, pointStyle: "rectRot", pointBackgroundColor: c5, borderColor: c5, u: " mmHg"}); }
    if (VIS.br) { ds.push({type: "bar", label: "minuty spadków SpO2", data: br, yAxisID: y("br"), backgroundColor: brc, u: " min"});
      ds.push({type: "line", label: "oddech szybszy niż norma", data: resp, yAxisID: y("br"), showLine: false, pointStyle: "triangle", pointRadius: 5, pointBackgroundColor: c3, borderColor: c3, hideVal: true}); }
    if (VIS.hrp) ds.push({type: "line", label: "tętno przy " + H.hrp.band, data: hrp, yAxisID: y("hrp"), showLine: false, pointRadius: 2.5, pointBackgroundColor: c4, borderColor: c4, u: " ud./min"});
    if (VIS.hrr) ds.push({type: "line", label: "HRR60", data: hrr, yAxisID: y("hrr"), showLine: false, pointRadius: 2.5, pointBackgroundColor: c5, borderColor: c5, u: " ud./min"});
    var scales = {x: {min: ZOOM ? ZOOM.a : undefined, max: ZOOM ? ZOOM.b : undefined, grid: {display: false}, ticks: {color: css("--muted"), maxRotation: 0, autoSkip: true, maxTicksLimit: 10, callback: function (v) { return dm(L[v]); }}}};
    PANELS.forEach(function (p) { var on = VIS[p.k]; scales[y(p.k)] = {display: on, stack: "v", stackWeight: on ? p.w : 0.0001, offset: true, position: "left", grid: {color: css("--line")}, ticks: {color: css("--muted"), maxTicksLimit: 3, font: {size: 10}}, border: {display: true, color: css("--line2")}}; });
    if (CH) CH.destroy();
    CH = new Chart($("sz-tl"), {data: {labels: L, datasets: ds}, plugins: [vlines, plabels], options: {
      responsive: true, maintainAspectRatio: false, animation: false, interaction: {mode: "index", intersect: false},
      plugins: {legend: {display: false}, tooltip: {filter: function (it) { return !it.dataset.hideTip && it.raw != null; }, callbacks: {
        title: function (it) { var d = L[it[0].dataIndex]; return dmy(d) + (ALC[d] ? " · 🍷 alkohol" : ""); },
        label: function (it) { return it.dataset.hideVal ? " " + it.dataset.label : " " + it.dataset.label + ": " + pl(it.raw, 1) + (it.dataset.u || ""); },
        afterBody: function (it) { var n = NIGHTS[L[it[0].dataIndex]]; return n ? ["noc: " + ({good: "spokojna", warn: "do obserwacji", bad: "niespokojna"}[n.status] || "bez oceny") + (n.resp ? ", oddech " + pl(n.resp, 1) + "/min" : "")] : []; }}}},
      scales: scales,
      onClick: function (e, els) { var i = els && els.length ? els[0].index : CH.scales.x.getValueForPixel(e.x); var d = L[Math.round(i)]; if (d && NIGHTS[d]) { SEL = "br"; tiles(); detail(d); $("sz-det").scrollIntoView({behavior: "smooth", block: "nearest"}); } }
    }});
    $("sz-zr").hidden = !ZOOM;
  }
  function dragZoom(cv, getCh, on) {
    var x0 = null;
    cv.addEventListener("mousedown", function (e) { x0 = e.clientX; });
    cv.addEventListener("mouseup", function (e) { var ch = getCh(); if (x0 == null || !ch) return; var r = cv.getBoundingClientRect(), xs = ch.scales.x;
      var a = xs.getValueForPixel(Math.min(x0, e.clientX) - r.left), b = xs.getValueForPixel(Math.max(x0, e.clientX) - r.left);
      if (Math.abs(e.clientX - x0) > 8 && b - a > 0) on(a, b); x0 = null; });
    cv.addEventListener("dblclick", function () { on(null, null); });
  }
  function chips() {
    var D = [{k: "rhr", t: "Tętno spocz.", c: css("--bad")}, {k: "hrv", t: "HRV", c: "#a78bfa"}, {k: "bp", t: "Ciśnienie", c: css("--warn")},
      {k: "br", t: "Oddech w nocy", c: css("--good")}, {k: "hrp", t: "Tętno przy mocy", c: css("--accent")}, {k: "hrr", t: "HRR60", c: css("--ink2")}, {k: "alc", t: "Alkohol", c: css("--accent")}];
    $("sz-chips").innerHTML = D.map(function (d) { return "<button class='sz-chip" + (VIS[d.k] ? " on" : "") + "' data-k='" + d.k + "'><i style='background:" + d.c + "'></i>" + d.t + "</button>"; }).join("");
    $("sz-chips").onclick = function (e) { var b = e.target.closest(".sz-chip"); if (!b) return; VIS[b.dataset.k] = !VIS[b.dataset.k]; b.classList.toggle("on"); draw(); };
  }

  /* ================= poziom 2 ================= */
  function kv(items) { return "<div class='sz-kv'>" + items.map(function (x) { return "<div><b>" + x[0] + "</b><span>" + x[1] + "</span></div>"; }).join("") + "</div>"; }
  function facts(a) { a = a.filter(Boolean); return a.length ? "<ul class='sz-facts'>" + a.map(function (f) { return "<li" + (f.l ? " class='c-" + f.l + "'" : "") + ">" + esc(f.t) + "</li>"; }).join("") + "</ul>" : ""; }
  function moreTable(head, rows, show) {
    var id = "m" + Math.random().toString(36).slice(2, 7);
    return "<div class='sz-tbw'><table class='sz-tb'><tr>" + head.map(function (h) { return "<th>" + h + "</th>"; }).join("") + "</tr>" + rows.slice(0, show).join("") +
      (rows.length > show ? "<tbody id='" + id + "' hidden>" + rows.slice(show).join("") + "</tbody>" : "") + "</table></div>" +
      (rows.length > show ? "<button class='sz-more' data-more='" + id + "' data-n='" + (rows.length - show) + "'>pokaż starsze (" + (rows.length - show) + ")</button>" : "");
  }
  function hours(min) { return min == null ? "–" : Math.floor(min / 60) + " h " + String(min % 60).padStart(2, "0") + " min"; }
  function detail(nightDay) {
    var el = $("sz-det"), h = "";
    if (SEL === "rhr") {
      var al = P.links.alkohol || {};
      h = "<h2>Tętno spoczynkowe</h2><div class='sz-lead'>Rano, w spoczynku. Wzrost o 3+ ud./min ponad normę z roku to typowy sygnał zmęczenia lub początku choroby.</div>" +
        kv([[pl(H.rhr.last.rhr, 0), "ostatnio (" + dm(H.rhr.last.date) + ")"], [pl(H.rhr.last7, 1), "średnia 7 dni"], [pl(H.rhr.recent, 1), "średnia 28 dni"], [pl(H.rhr.norm, 0), "norma z roku"]]) +
        facts([al.n ? {t: "🍷 Noc po alkoholu (" + al.n + " wieczorów w roku): tętno " + sg(al.rhr) + " ud./min, HRV " + sg(al.hrv) + " ms, sen " + sg(al.sen) + " pkt vs norma" + (al.ostatni ? " (ostatnio " + dm(al.ostatni) + ")" : "") + ". Te noce są wyłączone z analiz zależności."}
          : {t: "🍷 Alkohol: brak wpisów w ostatnim roku."}]);
    } else if (SEL === "hrv") {
      var s7 = P.hrv.status7 || {}, dd = P.links.hrv_po_deficycie || {}, sl = H.sleep || {}, sk = sl.skin_temp;
      h = "<h2>HRV — zmienność rytmu serca</h2><div class='sz-lead'>Średnia 7 nocy w porównaniu z Twoją normą z 60 nocy (pas na wykresie). Metoda QBota; spadki zgodne z oceną Garmina.</div>" +
        kv([[pl(s7.hrv, 0) + " ms", "ostatnia noc"], [pl(s7.avg7, 1) + " ms", "średnia 7 nocy"], [pl(s7.lo, 0) + "–" + pl(s7.hi, 0), "norma (ms)"], [esc(s7.label || "–"), "status"],
            [hours(sl.sleep7_min), "sen · średnia 7 dni"], [hours(sl.sleep_norm_min), "sen · wcześniej"], [sk ? sg(sk.temp, 1) + " °C" : "–", "temp. skóry vs norma"]]) +
        facts([dd.n_duzy >= 3 ? {t: "Dzień po dużym deficycie (> 700 kcal): HRV " + sg(dd.duzy) + " ms od normy, po pozostałych " + sg(dd.inne) + " ms (n " + dd.n_duzy + "/" + dd.n_inne + ")."} : null,
               sk && sk.signal ? {t: sk.text, l: "warn"} : null]);
    } else if (SEL === "bp") {
      var b = H.bp.summary, cs = P.links.cisnienie || {}, rows = (H.bp.all || []).slice().reverse().map(function (x) {
        var c = x.sys >= 135 || x.dia >= 85 ? " class='c-bad'" : ""; return "<tr><td>" + dmy(x.local.slice(0, 10)) + "</td><td>" + x.local.slice(11, 16) + "</td><td" + c + ">" + x.sys + "/" + x.dia + "</td><td>" + (x.pulse == null ? "–" : x.pulse) + "</td></tr>"; });
      var links = [];
      if (cs.sol && cs.sol.n_a >= 3 && cs.sol.n_b >= 3) links.push({t: "Ciśnienie rano po dniu z dużą ilością soli z diety (≥ 8 g): skurczowe średnio " + cs.sol.a + " vs " + cs.sol.b + " po pozostałych."});
      if (cs.deficyt && cs.deficyt.n_a >= 3 && cs.deficyt.n_b >= 3) links.push({t: "Ciśnienie rano po deficycie > 500 kcal: " + cs.deficyt.a + " vs " + cs.deficyt.b + "."});
      if (cs.pomiary_rano != null && cs.pomiary_rano < 6) links.push({t: "Ciśnienie a sól, deficyt i wagę: za mało pomiarów (" + cs.pomiary_wszystkie + " w bazie, rano " + cs.pomiary_rano + ")."});
      h = "<h2>Ciśnienie</h2><div class='sz-lead'>" + (b ? "Seria " + dmy(b.from) + "–" + dmy(b.to) + ": " + b.days + " z 7 dni, " + b.n + " pomiarów" + (b.protocol_ok ? " · seria pełna" : " · seria w toku") + (b.dropped_first_day ? " · pominięty 1. dzień" : "") : "Brak serii — zrób 7-dniową serię.") + "</div>" +
        (b ? kv([[b.sys + "/" + b.dia, "średnia serii"], [b.morning && b.morning.n ? b.morning.sys + "/" + b.morning.dia : "–", "rano (" + (b.morning ? b.morning.n : 0) + ")"], [b.evening && b.evening.n ? b.evening.sys + "/" + b.evening.dia : "–", "wieczorem (" + (b.evening ? b.evening.n : 0) + ")"], [esc(b.label), "ocena (próg 135/85)"]]) : "") +
        facts((H.nexus || []).map(function (n) { return {t: n.text, l: lv(n.status) === "info" ? "" : lv(n.status)}; }).concat(links)) +
        "<p style='margin-top:10px'><a class='sz-btn' href='/api/forma/heart/report.pdf' download>Raport dla lekarza (PDF)</a></p>" +
        moreTable(["Data", "Godz.", "Ciśnienie", "Tętno"], rows, 6) +
        "<details class='sz-how'><summary>Kiedy i jak mierzyć</summary>" +
        "<p><b>Seria 7 dni</b>, potem kontrolnie 1 dzień w tygodniu. Pierwszy dzień QBot pomija (przyzwyczajenie), liczy średnią z dni 2–7.</p>" +
        "<p><b>Rano</b> — w ciągu godziny od wstania, po toalecie, przed kawą, śniadaniem i treningiem.<br><b>Wieczorem</b> — przed snem, min. 1 h po jedzeniu i kawie, min. 2 h po treningu.</p>" +
        "<p><b>Ciśnienie:</b> 5 min siedzenia, plecy oparte, stopy płasko, ręka na stole na wysokości serca, mankiet na gołym ramieniu, bez rozmowy. 2 pomiary w odstępie 1 minuty — oba się zapisują.</p>" +
        "<p><b>EKG:</b> rano zaraz po ciśnieniu (ta sama pozycja); w dni jazdy po powrocie, po 10–15 min siedzenia; <b>zawsze od razu</b> przy kołataniu, nierównym biciu lub zawrotach głowy.</p>" +
        "<p style='color:var(--ink2)'>Pilnie do lekarza: ból lub ucisk w klatce, omdlenie, EKG z migotaniem przedsionków albo ciśnienie ≥ 180/110.</p></details>";
    } else if (SEL === "br") { return nightDetail(nightDay);
    } else if (SEL === "fit") {
      var rr = R.rides.slice().reverse().map(function (x) { return "<tr><td>" + dmy(x.day) + "</td><td>" + pl(x.hrr60, 1) + "</td><td>" + pl(x.hrr30, 1) + "</td><td>" + x.n + "</td></tr>"; });
      h = "<h2>Serce w wysiłku</h2><div class='sz-lead'>Z jazd: tętno przy stałej mocy " + H.hrp.band + " (od 15. do 120. minuty; niżej = lepiej) i spadek tętna w 60 s po mocnym akcencie — HRR60 (więcej = lepiej).</div>" +
        kv([[pl(H.hrp.recent, 1), "tętno przy mocy · 28 dni (" + (H.hrp.rides || 0) + " jazd)"], [pl(H.hrp.norm, 1), "norma (" + sg(H.hrp.delta) + ")"], [pl(R.recent, 1), "HRR60 · 28 dni (" + R.n_recent + " jazd)"], [pl(R.norm, 1), "norma HRR60"]]) +
        "<div class='muted'>Tętno przy mocy rośnie też po spadku formy i w chłodzie. Wyraźnie wolniejszy HRR60 niż norma = zmęczenie lub początek choroby.</div>" +
        moreTable(["Jazda", "HRR60", "HRR30", "Akcenty"], rr, 6);
    } else if (SEL === "ecg") {
      var ls = (H.ecg.list || []).slice().reverse().map(function (x) { var an = x.an || {}, ni = an.n_irregular || 0;
        return "<tr class='sz-ecg' data-id='" + esc(x.id) + "'><td>" + dmy(x.local.slice(0, 10)) + "</td><td>" + x.local.slice(11, 16) + "</td><td class='" + (x.ok ? "c-good" : "c-bad") + "'>" + esc(x.label) + "</td><td>" + (x.hr || "–") + "</td><td>" +
          (an.rmssd == null ? (x.hrv == null ? "–" : x.hrv) : pl(an.rmssd, 0)) + "</td><td" + (ni ? " class='c-bad'" : "") + ">" + (x.an ? ni : "–") + "</td><td>" + ((x.symptoms || []).length ? esc(x.symptoms.join(", ")) : "–") + "</td><td>" +
          (x.id ? "<a href='/api/forma/ecg.pdf?id=" + encodeURIComponent(x.id) + "' download>PDF</a>" : "") + "</td></tr>"; });
      h = "<h2>EKG z zegarka</h2><div class='sz-lead'>Kliknij wiersz, żeby zobaczyć przebieg. HRV — RMSSD liczone przez QBota z przebiegu; nieregularne — uderzenia przedwczesne lub wydłużone przerwy (orientacyjnie, jedno odprowadzenie).</div>" +
        moreTable(["Data", "Godz.", "Wynik", "Tętno", "HRV", "Nieregularne", "Objawy", ""], ls, 8) + "<div id='sz-ecgbox' style='margin-top:12px'></div>";
    }
    el.innerHTML = h;
    el.querySelectorAll("[data-more]").forEach(function (b) { b.onclick = function () { var t = $(b.dataset.more); t.hidden = !t.hidden; b.textContent = t.hidden ? "pokaż starsze (" + b.dataset.n + ")" : "zwiń"; }; });
    if (SEL === "ecg") { el.querySelectorAll("tr.sz-ecg").forEach(function (tr) { tr.onclick = function (ev) { if (ev.target.tagName === "A") return; drawEcg(tr.dataset.id); }; }); if (H.ecg.last && H.ecg.last.id) drawEcg(H.ecg.last.id); }
  }

  function nightDetail(day) {
    var V = S.verdict || {}, el = $("sz-det"), last = V.last || {};
    day = day || last.day;
    var n = NIGHTS[day] || {};
    var tx = [V.trend_text ? {t: V.trend_text, l: V.trend_level} : null, V.breath_text ? {t: V.breath_text} : null, V.resp_text ? {t: V.resp_text, l: V.resp_level} : null, V.bb_text ? {t: V.bb_text, l: V.bb_level} : null]
      .concat((S.factors || []).map(function (f) { return {t: f.text, l: f.level}; }));
    el.innerHTML = "<h2>Oddech w nocy</h2><div class='sz-lead'>SpO2 co minutę, wahania oddechu i tempo oddechu z zegarka — ocena względem Twoich 60 poprzednich nocy. Średnio " + pl(avgEvH(), 1) + " spadku SpO2 na godzinę (lekarze zaczynają się interesować od 5/h).</div>" +
      facts(tx) +
      "<details class='sz-how'><summary>Jak to liczę?</summary><p>Dla każdej nocy biorę jej typowy poziom SpO2 (medianę) i liczę minuty, w których saturacja spadła o 4 punkty lub więcej. Noc porównuję z Twoimi 60 poprzednimi: do 75% najgorszych — spokojna, do 90% — do obserwacji, wyżej — niespokojna. " +
      "Wahania oddechu to osobny czujnik Garmina — gdy pokrywa się ze spadkami SpO2, to prawdziwe zmiany oddechu. Tempo oddechu o 1/min powyżej normy to wczesny sygnał choroby. Odczyty minutowe są od 01.06.2026.</p></details>" +
      (n.day ? "<div class='cardhead' style='margin-top:14px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:baseline'><p class='lbl'>Noc " + dmy(day) + " · <span class='c-" + lv(n.status) + "'>" + ({good: "spokojna", warn: "do obserwacji", bad: "niespokojna"}[n.status] || "bez oceny") + "</span></p><button class='sz-btn' id='sz-nzr' hidden>Pokaż całą noc</button></div>" +
      kv([[n.drop_min + " min", "spadki SpO2 (" + n.events + ") · najniżej " + n.min + "%"], [n.bv_min != null ? n.bv_min + " min" : "–", "wahania oddechu"],
          [n.resp != null ? pl(n.resp, 1) + "/min" : "–", "tempo oddechu (norma " + pl(n.resp_norm, 1) + ")"], [n.stress != null ? n.stress : "–", "stres w nocy"],
          [n.bb_gain != null ? "+" + n.bb_gain : "–", "Body Battery w nocy"], [n.hr_min != null ? n.hr_min : "–", "najniższe tętno"], [n.restless_h != null ? pl(n.restless_h, 1) : "–", "niespokojne momenty / h"]]) +
      "<div class='sz-chips' id='sz-nchips'></div><div class='sz-nch'><canvas id='sz-nc'></canvas></div>" +
      "<div class='sz-hint'>Czerwona linia — minuty spadku SpO2; pomarańczowe pasy — wahania oddechu (Garmin); linia przerywana — tempo oddechu (prawa oś); „Tętno” — tętno w nocy co 2 min. Inną noc wybierzesz na wspólnej osi czasu.</div>" : "<p class='muted'>Brak odczytów tej nocy.</p>");
    if (!n.day) return;
    $("sz-nchips").innerHTML = [["spo2", "SpO2", css("--accent")], ["bv", "Wahania oddechu", css("--warn")], ["resp", "Tempo oddechu", css("--ink2")], ["hr", "Tętno", css("--bad")]].map(function (c) {
      return "<button class='sz-chip" + (NV[c[0]] ? " on" : "") + "' data-k='" + c[0] + "'><i style='background:" + c[2] + "'></i>" + c[1] + "</button>"; }).join("");
    $("sz-nchips").onclick = function (e) { var b = e.target.closest(".sz-chip"); if (!b) return; NV[b.dataset.k] = !NV[b.dataset.k]; b.classList.toggle("on"); drawNight(); };
    dragZoom($("sz-nc"), function () { return NCH; }, function (a, b) { NZ = a == null ? null : {a: Math.round(a), b: Math.round(b)}; drawNight(); });
    $("sz-nzr").onclick = function () { NZ = null; drawNight(); };
    get("/api/jedzenie/spo2?day=" + day).then(function (d) { NIGHT = d; NZ = null; drawNight(); }).catch(function () { var c = $("sz-nc"); if (c) c.parentNode.innerHTML = "<p class='muted'>Nie udało się wczytać nocy.</p>"; });
  }
  function drawNight() {
    var d = NIGHT; if (!d || !$("sz-nc")) return;
    var lab = d.series.map(function (p) { return p[0]; }), val = d.series.map(function (p) { return p[1]; }), rmap = {};
    (d.resp_series || []).forEach(function (r) { rmap[r[0]] = r[1]; });
    var hmap = {}; (d.hr_series || []).forEach(function (r) { hmap[r[0]] = r[1]; });
    var hrs = lab.map(function (t) { return hmap[t] != null ? hmap[t] : null; });
    var resp = lab.map(function (t) { return rmap[t] != null ? rmap[t] : null; }), bad = css("--bad"), acc = css("--accent"), wrn = css("--warn"), ds = [];
    if (NV.spo2) ds.push({label: "SpO2", data: val, yAxisID: "y", borderColor: acc, borderWidth: 1.6, pointRadius: 0, tension: .15, segment: {borderColor: function (c) { return (val[c.p0DataIndex] <= d.thr || val[c.p1DataIndex] <= d.thr) ? bad : acc; }}});
    if (NV.hr) ds.push({label: "tętno", data: hrs, yAxisID: "y3", borderColor: bad, borderWidth: 1, pointRadius: 0, spanGaps: true, borderDash: [1, 2]});
    if (NV.resp) ds.push({label: "oddech", data: resp, yAxisID: "y2", borderColor: css("--ink2"), borderDash: [4, 3], borderWidth: 1.2, pointRadius: 0, spanGaps: true});
    var bands = {id: "szb", beforeDatasetsDraw: function (ch) { if (!NV.bv) return; var x = ch.scales.x, a = ch.chartArea, ctx = ch.ctx; ctx.save();
      (d.bv_segments || []).forEach(function (s) { var i0 = lab.findIndex(function (t) { return t >= s.start; }), i1 = lab.findIndex(function (t) { return t >= s.end; }); if (i0 < 0) return; if (i1 < 0) i1 = lab.length - 1;
        var p0 = x.getPixelForValue(i0), p1 = x.getPixelForValue(i1); ctx.fillStyle = wrn; ctx.globalAlpha = s.level === 2 ? .35 : .18; ctx.fillRect(p0, a.top, Math.max(2, p1 - p0), a.bottom - a.top); }); ctx.restore(); }};
    if (NCH) NCH.destroy();
    NCH = new Chart($("sz-nc"), {type: "line", data: {labels: lab, datasets: ds}, plugins: [bands], options: {
      responsive: true, maintainAspectRatio: false, animation: false, interaction: {mode: "index", intersect: false},
      plugins: {legend: {display: false}, tooltip: {callbacks: {label: function (c) { return c.dataset.label === "SpO2" ? " SpO2 " + c.parsed.y + "%" + (c.parsed.y <= d.thr ? " — spadek" : "") : c.dataset.label === "tętno" ? " tętno " + c.parsed.y + " ud./min" : " oddech " + pl(c.parsed.y, 1) + "/min"; }}}},
      scales: {x: {min: NZ ? NZ.a : undefined, max: NZ ? NZ.b : undefined, grid: {display: false}, ticks: {color: css("--muted"), maxRotation: 0, autoSkip: true, maxTicksLimit: 9}},
        y: {min: Math.min(88, d.min - 1), max: 100, grid: {color: css("--line")}, ticks: {color: css("--muted"), callback: function (v) { return v + "%"; }}},
        y2: {position: "right", display: NV.resp, min: 8, max: 24, grid: {display: false}, ticks: {color: css("--muted"), maxTicksLimit: 4}},
        y3: {position: "right", display: NV.hr, grid: {display: false}, ticks: {color: bad, maxTicksLimit: 4}}}}});
    $("sz-nzr").hidden = !NZ;
  }

  /* ---------- EKG: przebieg + kontekst AI (jak w dawnym forma-serce.js) ---------- */
  function drawEcg(id) {
    var box = $("sz-ecgbox"); if (!box) return;
    $("sz-det").querySelectorAll("tr.sz-ecg").forEach(function (tr) { tr.classList.toggle("on", tr.dataset.id === id); });
    box.innerHTML = "<div class='muted'>ładuję przebieg…</div>";
    get("/api/forma/ecg?id=" + encodeURIComponent(id)).then(function (d) {
      var an = d.analysis || {}, fs = d.sample_rate || 128, smp = d.samples || [];
      if (!smp.length) { box.innerHTML = "<div class='muted'>Brak przebiegu dla tego nagrania.</div>"; return; }
      var med = smp.slice().sort(function (a, b) { return a - b; })[Math.floor(smp.length / 2)], full = smp.length / fs;
      var pts = smp.map(function (v, i) { return {x: i / fs, y: v - med}; });
      function yAt(t) { var i = Math.max(0, Math.min(smp.length - 1, Math.round(t * fs))); return smp[i] - med; }
      var irrT = (an.irregular || []).map(function (i) { return i.t_s; });
      function isIrr(t) { return irrT.some(function (x) { return Math.abs(x - t) < 0.03; }); }
      var rt = an.r_t || [], rr = an.rr_ms || [];
      var norm = rt.filter(function (t) { return !isIrr(t); }).map(function (t) { return {x: t, y: yAt(t)}; }), odd = rt.filter(isIrr).map(function (t) { return {x: t, y: yAt(t)}; });
      var lt = d.started_local || "";
      box.innerHTML = "<div style='display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap'><div style='font-size:13.5px'><b>" + (lt ? dmy(lt.slice(0, 10)) + " " + lt.slice(11, 16) : "") + "</b> · " + esc(d.label) +
        (an.ok ? " · " + an.n_beats + " uderzeń · tętno " + pl(an.hr_min, 0) + "–" + pl(an.hr_max, 0) + " (śr. " + pl(an.hr_mean, 0) + ") · HRV RMSSD " + pl(an.rmssd, 0) + " ms · SDNN " + pl(an.sdnn, 0) + " ms · pNN50 " + pl(an.pnn50, 0) + "% · sygnał: " + esc(an.quality) : " · analiza: " + esc(an.error || "brak")) + "</div>" +
        "<div><button class='sz-btn' id='sz-ezr' hidden>Pokaż całość</button> <a class='sz-btn' href='/api/forma/ecg.pdf?id=" + encodeURIComponent(d.detail_id) + "' download>Pobierz PDF</a></div></div>" +
        facts((d.interpretation || []).map(function (p) { return {t: p.text, l: lv(p.status) === "info" ? "" : lv(p.status)}; })) +
        ((an.irregular || []).length ? "<div class='c-bad' style='font-size:13px;margin-top:4px'>" + an.irregular.map(function (i) { return pl(i.t_s, 1) + " s: " + esc(i.label); }).join(" · ") + "</div>" : "") +
        (d.ai_needed ? "<div class='sz-aibox' id='sz-ecgai'></div>" : "") +
        "<div class='sz-ech'><canvas id='sz-ecg'></canvas></div><div class='sz-hint'>Przeciągnij, żeby powiększyć fragment (np. 3–4 uderzenia); dwuklik = całość. Najechanie na uderzenie pokazuje odstęp od poprzedniego.</div>";
      if (d.ai_needed) ecgAi(d.detail_id, d.ai);
      var ink2 = css("--ink2"), ink = css("--ink"), red = css("--bad");
      if (ECH) ECH.destroy();
      ECH = new Chart($("sz-ecg"), {type: "line", data: {datasets: [
        {label: "EKG (mV)", data: pts, borderColor: ink, borderWidth: 1.2, pointRadius: 0, pointHitRadius: 0, parsing: false, order: 3},
        {label: "uderzenie", data: norm, showLine: false, pointRadius: 3.5, pointStyle: "triangle", borderColor: ink2, backgroundColor: ink2, parsing: false, order: 1},
        {label: "nieregularne", data: odd, showLine: false, pointRadius: 6, pointStyle: "triangle", borderColor: red, backgroundColor: red, parsing: false, order: 0}]},
        options: {responsive: true, maintainAspectRatio: false, animation: false, interaction: {mode: "nearest", axis: "x", intersect: false},
          plugins: {legend: {display: false}, tooltip: {filter: function (it) { return it.datasetIndex > 0; }, callbacks: {title: function (it) { return it.length ? pl(it[0].parsed.x, 2) + " s" : ""; },
            label: function (it) { var k = rt.findIndex(function (t) { return Math.abs(t - it.parsed.x) < 0.005; }); var ir = (an.irregular || []).filter(function (i) { return Math.abs(i.t_s - it.parsed.x) < 0.03; })[0];
              var s1 = k > 0 && rr[k - 1] ? "odstęp " + rr[k - 1] + " ms (" + pl(60000 / rr[k - 1], 0) + " ud./min)" : "pierwsze uderzenie"; return ir ? [s1, ir.label] : s1; }}}},
          scales: {x: {type: "linear", min: 0, max: full, ticks: {color: ink2, stepSize: 1, callback: function (v) { return v + " s"; }}, grid: {color: css("--line")}}, y: {ticks: {color: ink2}, grid: {color: css("--line")}, title: {display: true, text: "mV", color: ink2}}}}});
      function zoom(a, b) { ECH.options.scales.x.min = a; ECH.options.scales.x.max = b; ECH.update("none"); $("sz-ezr").hidden = (a === 0 && b === full); }
      dragZoom($("sz-ecg"), function () { return ECH; }, function (a, b) { if (a == null || b - a < 0.3) zoom(0, full); else zoom(Math.max(0, a), Math.min(full, b)); });
      $("sz-ezr").onclick = function () { zoom(0, full); };
    }).catch(function (err) { box.innerHTML = "<div class='muted'>Nie udało się wczytać przebiegu: " + esc(err.message) + "</div>"; });
  }
  function ecgAi(id, cached) {
    function show(a) { var el = $("sz-ecgai"); if (el) el.innerHTML = "<div style='font-size:12px;font-weight:600;color:var(--ink2)'>Kontekst (AI na danych QBota: sen, trening, ciśnienie)</div>" + esc(a.komentarz || "") + "<div class='muted' style='font-size:11.5px'>" + esc(a.at || "") + " · nie jest diagnozą</div>"; }
    if (cached) return show(cached);
    $("sz-ecgai").innerHTML = "<span class='muted'>Analizuję kontekst… kilka sekund</span>";
    get("/api/forma/ecg/ai?id=" + encodeURIComponent(id), {method: "POST"}).then(function (j) { if (j.ai) show(j.ai); else { var e = $("sz-ecgai"); if (e) e.remove(); } })
      .catch(function (err) { var e = $("sz-ecgai"); if (e) e.innerHTML = "<span class='muted'>Kontekst AI niedostępny (" + esc(err.message) + ").</span>"; });
  }

  function loadAlc() { var L = labels(); return get("/api/jedzenie/alcohol?start=" + L[0] + "&end=" + L[L.length - 1]).then(function (a) { ALC = {}; (a.days || []).forEach(function (d) { ALC[d] = true; }); }).catch(function () { ALC = {}; }); }
  function load() {
    if (done) return; done = true;
    if (typeof Chart === "undefined") { done = false; setTimeout(load, 300); return; }
    build();
    Promise.all([get("/api/forma/heart?days=365"), get("/api/jedzenie/heart_plus"), get("/api/jedzenie/hrr?days=365"), get("/api/jedzenie/spo2?days=400")]).then(function (r) {
      H = r[0]; P = r[1]; R = r[2]; S = r[3]; NIGHTS = {};
      (S.nights || []).forEach(function (n) { NIGHTS[n.day] = n; });
      summary(); tiles(); chips(); detail();
      dragZoom($("sz-tl"), function () { return CH; }, function (a, b) { ZOOM = a == null ? null : {a: Math.round(a), b: Math.round(b)}; draw(); });
      return loadAlc().then(draw);
    }).catch(function (e) { done = false; $("sz-sum").innerHTML = "<p class='muted'>Nie udało się wczytać Serca: " + esc(e.message) + "</p>"; });
  }
  var btn = document.querySelector('#tabs button[data-t="serce"]'); if (btn) btn.addEventListener("click", load);
  if (location.hash === "#serce") load();
})();
