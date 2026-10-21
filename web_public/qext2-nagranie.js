/* qext2-nagranie.js (21.10.2026, sesja demo-2110) — scenariusz „Nagranie (trailer)” w symulatorze QExt2 (Garaż > QExt2).
   Odtwarza /qext2-sim/demo-nagranie.json — TEN SAM plik, który gra tryb NAGRANIE na Karoo (QExt2 0.4.20,
   assets/demo_nagranie.json, RecDemo.kt); generator: scripts/qext2_demo_scenario.py. 60 klatek po 1 s, w pętli.
   Rysuje własne trzy ekrany tymi samymi funkcjami pól wybranego buildu (QK2: KOKPIT 2, QST: STATS v2 / INFO),
   więc działa z każdą wersją qext2-makieta.js (nie zmienia jej). Mapa poglądowa. Dok.: docs/wiki/qext2/tryb-demo.md */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  var D = null, on = false, timer = null, scale = 0;
  var SURF_C = { PAVED: "#F2F4F7", GRAVEL: "#FFB300", LOOSE: "#FF2A2A" };
  var CFG = { hr: "zone", wbal: "trend", power: "pacing", speed: "yellow", wind: "headtail", windMin: 3, windShare: 0.7, etaGreen: 30, etaYellow: 10 };

  function frame(now) { var f = D.frames; return f[Math.floor(now / 1000) % f.length]; }
  function total() { return D.static.totalKm; }
  function ahead(km) { return D.static.segments.filter(function (s) { return s.to > km; }).map(function (s) { return [s.to - Math.max(s.from, km), SURF_C[s.surface]]; }); }
  function stops(km) { return D.static.stopsKm.filter(function (x) { return x < km; }); }
  function eta(now, km) { return now + (total() - km) / D.static.avgKmh * 3600000; }
  function level(kind) { return kind === "WPRIME" || kind === "DESCENT" ? "crit" : kind === "RAIN" || kind === "FUEL" || kind === "DUSK" ? "warn" : "info"; }

  function nav(f, now) {
    var s = D.static;
    return { msg: { level: level(f.msg.kind), lead: f.msg.lead, accent: f.msg.accent }, doneKm: f.km, leftKm: total() - f.km, etaMs: eta(now, f.km), deadlineMs: null,
      tempC: s.tempC, windMps: s.windMps, windRelDeg: f.windRelDeg, windSignedMps: f.windSignedMps, windTotalMps: s.windMps, windCached: false,
      gradePct: f.grade, dyn: { kind: f.dyn.kind, value: f.dyn.value, unit: f.dyn.unit },
      rainNowMmH: null, rainSoon: { probPct: 60, minutes: 35, kind: "RAIN" }, sky: s.sky };
  }
  function instr(f) {
    var s = D.static, p = f.power, c = s.ceilingW, r = f.hr / s.lthr;
    return { route: { doneKm: f.km, totalKm: total(), ahead: ahead(f.km), stopsKm: stops(f.km) },
      hr: f.hr, hrZone: r < 0.81 ? 1 : r < 0.90 ? 2 : r < 0.95 ? 3 : r < 1.06 ? 4 : 5, hrDriftLevel: 0,
      cadence: f.cadence, cpe5W: f.np5, cpTrend: p > f.np5 + 5 ? 1 : p < f.np5 - 5 ? -1 : 0,
      avgSpeedKmh: s.avgKmh, avgSpeedTrend: f.speedKmh > s.avgKmh + 0.5 ? 1 : f.speedKmh < s.avgKmh - 0.5 ? -1 : 0,
      wbalPct: f.wbalPct, wbalTrend: f.wbalTrend === "stable" ? "steady" : f.wbalTrend,
      gearFront: s.gearFront, gearRear: f.rearCog, speedKmh: f.speedKmh, powerW: p, cpW: s.cpW,
      powerColor: f.alarm ? "#000000" : p > c ? "#FF8C8C" : p >= 0.95 * c ? "#FACC15" : "#FFFFFF", powerBg: f.alarm ? "#FF5252" : 0 };
  }
  function stats(f) {
    var s = D.static, ifv = f.np / s.cpW;
    return { np: f.np, npZone: ifv < 0.55 ? 1 : ifv < 0.75 ? 2 : ifv < 0.90 ? 3 : ifv < 1.05 ? 4 : ifv < 1.20 ? 5 : 6, ifv: ifv, vi: 1.06,
      rsrv: f.rsrv, xss: f.xss, xssPlan: s.xssPlan, kcal: f.kcal,
      winNp: s.winNp.concat([f.np5]), winEf: s.winEf.concat([1.40]), winPartial: true, typEf: s.typEf, cpW: s.cpW, np5Now: f.np5,
      planDeltaMin: -6, planDriveDelta: -4, planStopDelta: -2, planFromQbot: true, tempo: s.tempo, tempoPartial: true,
      gate: { state: "FAR", main: "BRAMA", sub: "za daleko · 38,2 km" }, lightState: "OK", light: { controllable: true, battery: "68%", mode: "MIGANIE" },
      carbRate: s.carbRate, carbSpent: Math.round(f.kcal * 0.55 / 4), fluidRate: s.fluidRate, cadAvg: s.cadAvg,
      batDrain: s.batDrain, batLeftSec: 6 * 3600 + 20 * 60 };
  }
  function info(f, now) {
    var s = D.static, mv = s.movingSecAtStart + f.t;
    return { hasRoute: true, doneKm: f.km, totalKm: total(), etaMs: eta(now, f.km), twilightMs: now + 160 * 60000, twilightDawn: false,
      ahead: ahead(f.km), stopsKm: stops(f.km), ascDone: f.ascDone, ascLeft: f.ascLeft,
      avgGrossKmh: f.km / ((mv + s.stopsSec) / 3600), movingSec: mv, stopsSec: s.stopsSec };
  }
  /* pogoda INFO: port 1:1 InfoDemo.wx z QExt2 (to samo, co na Karoo w trybie NAGRANIE) */
  function wx(now, kmNow) {
    var items = [], end = Math.max(total(), kmNow + 30);
    function g(d, c, w) { var x = (d - c) / w; return Math.exp(-x * x); }
    for (var km = kmNow; km <= end; km += 0.5) {
      var d = km - kmNow, t = d / 19.1 * 60;
      var hw = 5.5 * Math.sin(d / 6) + 2.5 * Math.sin(d / 1.9) + 1.0 * Math.cos(d / 13);
      var mm = 1.6 * g(d, 25, 5) + 0.9 * g(d, 85, 6); if (mm < 0.05) mm = 0;
      items.push({ km: km, t: t, feels: 11 - 4 * Math.max(0, d - 30) / Math.max(1, end - kmNow) - 1.6 * g(d, 25, 8), mm: mm,
        prob: Math.min(95, 10 + 80 * g(d, 25, 10) + 50 * g(d, 85, 10)), head: hw, gust: hw > 0 ? hw * 1.45 + 1.5 : 2 });
    }
    return { items: items, route: true, fetchedMs: now, ageMin: 0, live: false, radarUntilMin: 120 };
  }
  function map(cv, W, H, f) {
    var dpr = Math.max(1, window.devicePixelRatio || 1);
    cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
    var c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.fillStyle = "#20252b"; c.fillRect(0, 0, W, H);
    var m = f.km * 1000, y0 = H * 0.62;
    function x(dy) { return W / 2 + 46 * Math.sin((m + dy * 3) / 420) - 46 * Math.sin(m / 420); }
    c.lineCap = "round"; c.lineJoin = "round";
    [[11, "#000"], [7, "#FF8A00"]].forEach(function (s) { c.strokeStyle = s[1]; c.lineWidth = s[0]; c.beginPath();
      for (var dy = 0; dy <= y0 + 20; dy += 6) { if (dy === 0) c.moveTo(x(dy), y0 - dy); else c.lineTo(x(dy), y0 - dy); } c.stroke(); });
    [[9, "#000"], [5, "#8a94a3"]].forEach(function (s) { c.strokeStyle = s[1]; c.lineWidth = s[0]; c.beginPath();
      for (var dy = 0; dy >= -(H - y0); dy -= 6) { if (dy === 0) c.moveTo(x(dy), y0 - dy); else c.lineTo(x(dy), y0 - dy); } c.stroke(); });
    c.save(); c.translate(W / 2, y0); c.beginPath(); c.moveTo(0, -16); c.lineTo(12, 13); c.lineTo(0, 6); c.lineTo(-12, 13); c.closePath();
    c.fillStyle = "#2E7BFF"; c.fill(); c.lineWidth = 3; c.strokeStyle = "#fff"; c.stroke(); c.restore();
  }
  function draw() {
    if (!on) return;
    var now = Date.now(), f = frame(now), s0 = $("screens"), s1 = $("screensRec");
    if (s0 && s0.style.zoom) s1.style.zoom = s0.style.zoom;
    var hhmm = new Date(now).toTimeString().slice(0, 5);
    Array.prototype.forEach.call(s1.querySelectorAll(".sbClock"), function (e) { e.textContent = hhmm; });
    QK2.nav($("rcNav"), 478, 143, nav(f, now), CFG);
    QK2.instr($("rcInstr"), 478, 143, instr(f), CFG);
    map($("rcMap"), 480, 800 - 38 - 2 * 143, f);
    QST.stats($("rcStats"), 480, 762, stats(f));
    QST.info($("rcInfo"), 480, 762, info(f, now), wx(now, f.km), scale, now, now - 6 * 3600000, now + 160 * 60000);
    $("state").textContent = "NAGRANIE · klatka " + (f.t + 1) + "/" + D.frames.length + " · " + f.phase + "\nmoc " + f.power + " W · " + f.speedKmh.toFixed(1) +
      " km/h · nachylenie " + f.grade.toFixed(1) + "%\ntętno " + f.hr + " · W′ " + f.wbalPct + "% · km " + f.km.toFixed(2) + " / " + total();
  }
  function screens() {
    function dev(h, inner) { return '<div class="dev"><h3>' + h + '</h3><div class="karoo"><div class="scr"><div class="sbar"><span class="sbClock">12:00</span><span>' +
      inner[0] + "</span></div>" + inner[1] + "</div></div></div>"; }
    var d = document.createElement("div"); d.className = "screens"; d.id = "screensRec"; d.style.display = "none";
    d.innerHTML = dev("KOKPIT 2 (ekran z mapą) · NAGRANIE", ["mapa", '<canvas id="rcNav"></canvas><canvas id="rcInstr"></canvas><canvas id="rcMap"></canvas>']) +
      dev("STATS v2 · NAGRANIE", ["STATS", '<canvas id="rcStats"></canvas>']) + dev("INFO (dotknij — skala) · NAGRANIE", ["INFO", '<canvas id="rcInfo" style="cursor:pointer"></canvas>']);
    $("screens").parentNode.insertBefore(d, $("screens").nextSibling);
    $("rcInfo").onclick = function () { scale = (scale + 1) % 3; draw(); };
  }
  function setOn(v, btn) {
    on = v; $("screens").style.display = v ? "none" : ""; $("screensRec").style.display = v ? "" : "none";
    if (btn) btn.classList.toggle("on", v);
    if (v) { Array.prototype.forEach.call($("scen").children, function (b) { if (b !== btn) b.classList.remove("on"); });
      $("desc").textContent = "Tryb NAGRANIE na Karoo (QExt2 0.4.20): ten sam scenariusz 60 s w pętli. " + D.opis;
      draw(); if (!timer) timer = setInterval(draw, 1000); }
    else if (timer) { clearInterval(timer); timer = null; }
  }
  function init() {
    screens();
    var b = document.createElement("button"); b.type = "button"; b.textContent = "🎬 " + D.name;
    b.onclick = function (e) { e.stopPropagation(); setOn(true, b); };
    $("scen").appendChild(b);
    $("scen").addEventListener("click", function (e) { if (on && e.target !== b && e.target.tagName === "BUTTON") setOn(false, b); });
  }
  function ready(cb) { var n = 0; (function w() { if (window.QK2 && window.QST && $("scen") && $("scen").children.length) return cb(); if (n++ < 150) setTimeout(w, 200); })(); }
  fetch("/qext2-sim/demo-nagranie.json", { cache: "no-store", credentials: "same-origin" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { if (j && j.frames && j.frames.length) { D = j; ready(init); } })
    .catch(function () {});
})();
