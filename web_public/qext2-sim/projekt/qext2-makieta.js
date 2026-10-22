/* qext2-makieta.js (2026-10-18, v3) — makieta pól QExt2 z SYMULACJĄ JAZDY: scenariusz = trasa (profil, kierunek, wiatr,
   pogoda) + zachowanie (moc docelowa, zmienność, czujniki); co sekundę symulacji liczona jest jazda: moc → prędkość
   (fizyka: opór toczenia, nachylenie, powietrze z wiatrem), tętno z opóźnieniem, W′ bal (Skiba), NP 5, średnie, okna
   PRZEBIEG, TEMPO, ETA, komunikaty z wyprzedzeniem trasy — i podawane do rysowania pól 1:1 z kodu QExt2:
   QK2 (/qext2-kokpit2.js: KOKPIT 2 nav + instr), QST (/qext2-stats.js: STATS v2, INFO). Mapa pod polami jest poglądowa. */
(function () {
"use strict";
function $(id) { return document.getElementById(id); }
function mulberry(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; var t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function hash(i) { var x = Math.sin(i * 12.9898 + 78.233) * 43758.5453; return x - Math.floor(x); }
function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
function todayAt(h, m) { var d = new Date(); d.setHours(h, m, 0, 0); return d.getTime(); }
function mmss(sec) { sec = Math.max(0, Math.round(sec)); return Math.floor(sec / 60) + ":" + ("0" + sec % 60).slice(-2); }
function kmTxt(km) { return km < 10 ? (Math.round(km * 10) / 10).toFixed(1).replace(".", ",") : String(Math.round(km)); }

/* 22.10 projekt 0.4.27: warianty z symulatora (window.QV) */
function qv(k, d) { return (typeof window !== "undefined" && window.QV) ? window.QV(k, d) : d; }

/* ---------------- scenariusze ---------------- */
var CP = 241, CEIL = 210, LTHR = 160, W0 = 18000, CASS = [10, 11, 12, 13, 15, 17, 19, 21, 24, 28, 32, 36, 40, 44, 52];
var SCEN = [
  { n: "Zwykła jazda", d: "Spokojna jazda w tlenie po mieszanej nawierzchni, lekki wiatr, plan dnia Trenera.", km0: 32, total: 80, pT: 175, var: 0.6,
    temp: 12, wx: "PARTLY", ws: 2.5, wFrom: 250, head: 60, msgs: ["surface", "water"], infoWx: "rainSoon", clock: [10, 0] },
  { n: "Podjazd + W′", d: "Za 0,6 km zaczyna się 3-kilometrowy podjazd 7–9%. Jedziesz za mocno — W′ spada, pojawia się BOMBA.", km0: 39.4, total: 80, pT: 225, var: 0.4,
    temp: 14, wx: "CLEAR", ws: 3, wFrom: 200, head: 30, climb: [40, 43], msgs: ["climb"], infoWx: "dry", clock: [11, 10] },
  { n: "Wiatr w twarz", d: "Długi odcinek prosto pod mocny wiatr: strzałka czerwona, wolniej, PLAN CZASU ucieka.", km0: 20, total: 80, pT: 195, var: 0.5,
    temp: 9, wx: "OVERCAST", ws: 9, wFrom: 80, head: 80, straight: true, msgs: ["surface"], infoWx: "head", clock: [9, 40] },
  { n: "Deszcz za 15′", d: "Radar QBota pokazuje deszcz za kwadrans; ostrzeżenie na żółtym pasku.", km0: 45, total: 80, pT: 180, var: 0.6,
    temp: 8, wx: "radar", ws: 4, wFrom: 300, head: 120, msgs: ["rain", "surface"], infoWx: "radar", clock: [13, 0] },
  { n: "Śnieg / mróz", d: "−7°, prognoza śniegu, zimny wiatr z boku.", km0: 18, total: 60, pT: 165, var: 0.5,
    temp: -7, wx: "snow", ws: 6, wFrom: 0, head: 70, msgs: ["climb", "water"], infoWx: "rainSoon", clock: [11, 30] },
  { n: "Burza i upał", d: "31°, burza za 15′, mocny wiatr, picie ważniejsze niż zwykle.", km0: 55, total: 90, pT: 185, var: 0.6,
    temp: 31, wx: "storm", ws: 8, wFrom: 160, head: 200, msgs: ["rain", "fuel"], infoWx: "radar", clock: [15, 20] },
  { n: "ETA zagrożone", d: "Do mety nie zdążysz przed zmrokiem/limitem: ETA czerwone, pole dynamiczne pokazuje wymaganą średnią.", km0: 52, total: 95, pT: 185, var: 0.5,
    temp: 10, wx: "PARTLY", ws: 5, wFrom: 270, head: 250, msgs: ["dusk"], deadline: -12, infoWx: "night", clock: [15, 40] },
  { n: "Stromy zjazd", d: "Za chwilę zjazd −10% po szutrze: krytyczny komunikat, toczenie bez pedałowania.", km0: 61.6, total: 80, pT: 150, var: 0.5,
    temp: 11, wx: "PARTLY", ws: 3, wFrom: 90, head: 140, descent: [62, 64.5], msgs: ["surface"], infoWx: "dry", clock: [12, 15] },
  { n: "Alarm mocy", d: "Za mocno ponad pułap tempa przez ponad 30 s: czerwone tło pod mocą, W′ leci w dół.", km0: 28, total: 80, pT: 300, var: 0.3,
    temp: 13, wx: "CLEAR", ws: 2.5, wFrom: 220, head: 40, msgs: ["surface"], infoWx: "dry", clock: [10, 20] },
  { n: "Brak czujników", d: "Pas HR się rozłączył: brak tętna, komunikat o czujniku; ŚWIATŁO szuka lampy.", km0: 25, total: 70, pT: 175, var: 0.6,
    temp: 12, wx: "PARTLY", ws: 4, wFrom: 250, head: 60, noHr: true, light: "SEARCHING", msgs: ["sensor"], infoWx: "dry", clock: [10, 0] },
  { n: "Bez trasy", d: "Jazda bez wgranej trasy, popołudnie: zamiast DTD/ETA — DOM (km do domu) i czas do zmroku; INFO pokazuje kolejne godziny.", km0: 14, total: 0, pT: 170, var: 0.6,
    temp: 12, wx: "PARTLY", ws: 4, wFrom: 250, head: 60, noRoute: true, msgs: ["noroute"], infoWx: "rainSoon", clock: [15, 50] },
  { n: "AERO", d: "Pole dynamiczne w trybie AERO: zmiana oporu powietrza po zmianie pozycji (W).", km0: 30, total: 80, pT: 190, var: 0.4,
    temp: 14, wx: "CLEAR", ws: 3, wFrom: 260, head: 70, aero: true, msgs: ["surface"], infoWx: "dry", clock: [10, 30] },
  { n: "Brama przy domu", d: "Ostatnie 1,5 km do domu: BRAMA gotowa w STATS v2.", km0: 78.5, total: 80, pT: 150, var: 0.5,
    temp: 11, wx: "OVERCAST", ws: 3, wFrom: 270, head: 10, gate: true, msgs: ["shop"], infoWx: "dry", clock: [14, 5] },
  { n: "Bez zasięgu", d: "Brak sieci: pogoda i wiatr z zapasu prognozy (znacznik P).", km0: 40, total: 80, pT: 180, var: 0.6,
    temp: 10, wx: "rainSoon", ws: 5, wFrom: 230, head: 90, cached: true, msgs: ["water"], infoWx: "rainSoon", clock: [12, 0] }
];
var MSG = {
  surface: function (s) { var n = nextSurface(s); return n ? { level: "info", lead: "za " + kmTxt(n.d) + " km", accent: n.name + " " + kmTxt(n.len) + " km" } : { level: "info", lead: "do mety", accent: kmTxt(s.total - s.km) + " km" }; },
  water: function (s) { var d = s.sc.total * 0.6 - s.km; return d > 0 && d < 2 ? { level: "info", lead: "woda " + kmTxt(d) + " km", accent: "źródło" } : MSG.surface(s); },
  shop: function (s) { var d = s.total - 0.9 - s.km; return d > 0 ? { level: "info", lead: "sklep " + kmTxt(d) + " km", accent: "Żabka do 23:00" } : { level: "info", lead: "meta", accent: "za " + kmTxt(s.total - s.km) + " km" }; },
  climb: function (s) { var c = nextClimb(s, 3); return c ? { level: "info", lead: "podjazd za " + kmTxt(c.d) + " km:", accent: Math.round(c.g) + "% " + kmTxt(c.len) + " km" } : MSG.surface(s); },
  rain: function () { return { level: "warn", lead: "za 15′", accent: "deszcz słaby" }; },   /* 22.10 pkt 2: sila slowem zamiast mm */
  fuel: function () { return { level: "warn", lead: "bilans −45 g", accent: "JEDZ" }; },
  dusk: function (s) { return { level: "warn", lead: "zmrok 17:34", accent: "meta po zmroku" }; },
  sensor: function () { return { level: "warn", lead: "", accent: "BRAK CZUJNIKA HR" }; },
  noroute: function () { return { level: "info", lead: "brak trasy", accent: "", none: true }; }
};

/* ---------------- trasa: profil, kierunek, nawierzchnia ---------------- */
function grade(s, km) {
  var sc = s.sc, g = 1.4 * Math.sin(km / 2.3) + 0.9 * Math.sin(km / 0.7 + 1);
  if (sc.climb && km >= sc.climb[0] && km <= sc.climb[1]) g = 8 + 1.3 * Math.sin(km * 4);
  if (sc.descent && km >= sc.descent[0] && km <= sc.descent[1]) g = -10 + 1.2 * Math.sin(km * 5);
  return g;
}
function heading(s, km) { var sc = s.sc; return sc.straight ? sc.head + 4 * Math.sin(km * 3) : sc.head + 40 * Math.sin(km / 6) + 22 * Math.sin(km / 1.7); }
function surfAt(s, km) { var f = km / (s.sc.total || 80); return f < 0.30 ? 0 : f < 0.52 ? 1 : f < 0.58 ? 2 : f < 0.80 ? 0 : 1; }   // 0 asfalt, 1 szuter, 2 trudny
var SURF_N = ["asfalt", "szuter", "trudny"], SURF_C = ["#F2F4F7", "#FFB300", "#FF2A2A"];
function nextSurface(s) { var cur = surfAt(s, s.km); for (var k = s.km; k < Math.min(s.total, s.km + 5); k += 0.1) if (surfAt(s, k) !== cur) { var t = surfAt(s, k), e = k; while (e < s.total && surfAt(s, e) === t) e += 0.1; return { d: k - s.km, name: SURF_N[t], len: e - k }; } return null; }
function nextClimb(s, look) { for (var k = s.km; k < Math.min(s.total, s.km + look); k += 0.05) if (grade(s, k) >= 4) { var e = k, sum = 0, n = 0; while (e < s.total && grade(s, e) >= 2) { sum += grade(s, e); n++; e += 0.05; } if (e - k >= 0.3) return { d: k - s.km, g: sum / n, len: e - k }; k = e; } return null; }
function nextDescent(s, look) { for (var k = s.km; k < Math.min(s.total, s.km + look); k += 0.05) if (grade(s, k) <= -6) return { d: k - s.km, g: grade(s, k) }; return null; }
function ascentLeft(s) { var a = 0; for (var k = s.km; k < s.total; k += 0.05) { var g = grade(s, k); if (g > 0) a += g / 100 * 50; } return Math.round(a); }
function ascentTotal(s) { var a = 0; for (var k = 0; k < s.total; k += 0.05) { var g = grade(s, k); if (g > 0) a += g / 100 * 50; } return Math.round(a); }

/* ---------------- fizyka ---------------- */
function speedFrom(P, gPct, headMps, surf) {
  var m = 112, g = 9.81, crr = [0.0075, 0.012, 0.018][surf], cda = 0.50, rho = 1.2, th = Math.atan(gPct / 100);
  function f(v) { var air = v + headMps; return v * m * g * (crr * Math.cos(th) + Math.sin(th)) + 0.5 * rho * cda * air * Math.abs(air) * v - P * 0.96; }
  var lo = 0.3, hi = 22; if (f(hi) < 0) return hi;
  if (f(lo) > 0) return lo;
  for (var i = 0; i < 40; i++) { var mid = (lo + hi) / 2; if (f(mid) > 0) hi = mid; else lo = mid; }
  return Math.min(lo, 15.3);   // hamowanie na zjeździe ~55 km/h
}

/* ---------------- stan symulacji ---------------- */
var S = null, view = "kokpit", infoScale = 0, speedX = 5, playing = true, curIdx = 0;
function start(i) {
  var sc = SCEN[i];
  S = { sc: sc, rnd: mulberry(1234 + i), km: 0, total: sc.total || 9999, t: 0, moving: 0, stops: 0, kj: 0, cho: 0, hr: 95, hrSum: 0, hrN: 0,
    noise: 0, burst: 0, w: W0 * (sc.wbal0 || 1), P: 0, v: 0, cad: 85, gearR: 17, over: 0, pw: [], hrs: [], vs: [], np5Hist: [], avgHist: [], wHist: [],
    winNp: [], winEf: [], tempo: [], aeroK: 0, clock0: todayAt(sc.clock[0], sc.clock[1]) };
  // dojazd do km startowego scenariusza (historia: średnie, okna, W′)
  var guard = 0; while (S.km < sc.km0 && guard++ < 20000) step(true);
  S.t0 = S.t;
  var planV = 22;
  S.deadline = sc.noRoute ? null : now() + (((S.total - S.km) / planV) * 60 + (sc.deadline != null ? sc.deadline : 35)) * 60000;
  S.planV = planV; S.planStartT = S.t; S.planStartKm = S.km;
  S.wxFetched = now() - 5 * 60000;
  S.wx = buildInfoWx();
  buildMap();
}
function now() { return S.clock0 + S.t * 1000; }
function step(fast) {
  var s = S, sc = s.sc, r = s.rnd;
  if (s.km >= s.total) { s.v = 0; s.P = 0; s.stops++; s.t++; return; }
  var gr = grade(s, s.km), hd = heading(s, s.km), rel = ((sc.wFrom + 180 - hd) % 360 + 360) % 360, hs = -sc.ws * Math.cos(rel * Math.PI / 180);
  s.rel = rel; s.hs = hs; s.gr = gr;
  // moc: cel scenariusza + nachylenie + zmienność (gravel: krótkie zrywy), toczenie na zjazdach
  s.noise = s.noise * 0.92 + (r() - 0.5) * 60 * sc.var;
  if (s.burst > 0) s.burst--; else if (r() < 0.02 * sc.var) s.burst = 4 + Math.floor(r() * 6);
  var P = sc.pT * (1 + 0.035 * clamp(gr, -4, 10)) + s.noise + (s.burst > 0 ? 110 : 0);
  if (gr < -4) P = r() < 0.15 ? 60 : 0;
  P = Math.max(0, Math.round(P));
  var v = speedFrom(P, gr, hs, surfAt(s, s.km));
  s.P = P; s.v = v; s.km = Math.min(s.total, s.km + v / 1000);
  if (v > 1) s.moving++; else s.stops++;
  s.t++;
  s.kj += P / 1000;
  var frac = clamp(0.3 + 0.6 * P / CP, 0.2, 1); s.cho += P / 0.23 / 4184 * frac / 4;
  // tętno z opóźnieniem, kadencja, bieg
  var hrT = Math.min(184, 70 + 0.38 * P + (s.t / 3600) * 2.5); s.hr += (hrT - s.hr) / 25;
  s.hrSum += s.hr; s.hrN++;
  s.cad = P < 10 ? 0 : Math.round(clamp(84 + (s.noise / 12) - Math.max(0, gr - 4) * 2, 60, 105));
  if (s.cad > 0) { var ideal = 40 * (s.cad / 60) * 2.15 / Math.max(1, v); var best = CASS[0]; CASS.forEach(function (c) { if (Math.abs(c - ideal) < Math.abs(best - ideal)) best = c; }); s.gearR = best; }
  // W′ bal (Skiba)
  if (P > CP) s.w -= (P - CP); else { var tau = 546 * Math.exp(-0.01 * (CP - P)) + 316; s.w += (W0 - s.w) * (1 - Math.exp(-1 / tau)); }
  s.w = clamp(s.w, 0, W0);
  s.over = P > CEIL ? s.over + 1 : 0;
  s.pw.push(P); s.hrs.push(s.hr); s.vs.push(v);
  if (s.pw.length > 3600 * 6) { s.pw.shift(); s.hrs.shift(); s.vs.shift(); }
  if (s.t % 30 === 0) { s.np5Hist.push(np(s.pw.slice(-300))); s.avgHist.push(avgV()); s.wHist.push(s.w); }
  if (s.moving > 0 && s.moving % 300 === 0 && v > 1) { var w5 = s.pw.slice(-300), h5 = s.hrs.slice(-300); var n5 = np(w5); s.winNp.push(n5); s.winEf.push(+(n5 / (h5.reduce(function (a, b) { return a + b; }, 0) / h5.length)).toFixed(2)); }
  if (s.moving > 0 && s.moving % 3600 === 0 && v > 1) { s.tempo.push([Math.round(avg(s.pw.slice(-3600))), avg(s.vs.slice(-3600)) * 3.6]); }
  if (sc.aero && s.t % 20 === 0) s.aeroK++;
}
function avg(a) { return a.length ? a.reduce(function (x, y) { return x + y; }, 0) / a.length : 0; }
function np(a) { if (a.length < 30) return Math.round(avg(a)); var r = [], sum = 0; for (var i = 0; i < a.length; i++) { sum += a[i]; if (i >= 30) sum -= a[i - 30]; if (i >= 29) r.push(Math.pow(sum / 30, 4)); } return Math.round(Math.pow(avg(r), 0.25)); }
function avgV() { return S.moving ? S.km / (S.moving / 3600) : 0; }

/* ---------------- dane do pól ---------------- */
function aheadSegs() {
  if (S.sc.noRoute) return null;
  var out = [], k = S.km, cur = surfAt(S, k), st = k;
  for (; k < S.total; k += 0.1) { var t = surfAt(S, k); if (t !== cur) { out.push([k - st, SURF_C[cur]]); cur = t; st = k; } }
  out.push([S.total - st, SURF_C[cur]]); return out;
}
function stopsKm() { return S.sc.noRoute ? [] : [S.total * 0.15, S.total * 0.42].filter(function (x) { return x < S.km; }); }
function etaMs() { if (S.sc.noRoute) return null; var v = Math.max(10, avgV()); return now() + (S.total - S.km) / v * 3600000; }
function weather() {
  var o = { rainNowMmH: null, rainSoon: null, sky: null }, wx = S.sc.wx, el = (S.t - S.t0) / 60;
  if (qv("pogoda", "przeglad") === "przeglad") {   /* 22.10 v3: przeglad wszystkich stanow pogody KOKPIT 2 co 3 s */
    var PW = [{ sky: "CLEAR" }, { sky: "PARTLY" }, { sky: "OVERCAST" }, { sky: "FOG" },
      { rainSoon: { radar: true, mmPerH: 1.2, minutes: 15, probPct: 0, kind: "RAIN" } },
      { rainSoon: { radar: true, mmPerH: 4.5, minutes: 8, probPct: 0, kind: "RAIN" } },
      { rainSoon: { probPct: 70, mmPerH: 9, minutes: 25, kind: "RAIN" } },
      { rainNowMmH: 1.4 }, { rainNowMmH: 5 }, { rainNowMmH: 12 },
      { rainSoon: { probPct: 70, minutes: 25, kind: "SNOW" } }, { rainSoon: { probPct: 80, minutes: 15, kind: "STORM" } }][Math.floor(Date.now() / 3000) % 12];
    return Object.assign(o, PW);
  }
  if (wx === "radar") o.rainSoon = { radar: true, mmPerH: 1.2, minutes: Math.max(1, Math.round(15 - el)), probPct: 0, kind: "RAIN" };
  else if (wx === "rainSoon") { o.rainSoon = { probPct: 60, minutes: Math.max(1, Math.round(40 - el)), kind: "RAIN" }; o.sky = "OVERCAST"; }
  else if (wx === "snow") o.rainSoon = { probPct: 70, minutes: Math.max(1, Math.round(25 - el)), kind: "SNOW" };
  else if (wx === "storm") o.rainSoon = { probPct: 80, minutes: Math.max(1, Math.round(15 - el)), kind: "STORM" };
  else o.sky = wx;
  if (o.rainSoon && S.sc.wx === "radar" && el >= 15) { o.rainNowMmH = 1.4; o.rainSoon = null; }
  if (o.rainSoon) o.rainSoon.cached = !!S.sc.cached;
  return o;
}
function message() {
  var s = S, sc = s.sc, wp = Math.round(s.w / W0 * 100);
  if (!sc.noRoute) {
    if (wp < 55) {
      if (s.P > CP) return { level: "crit", lead: "W′ " + wp + "%:", accent: "BOMBA " + mmss(s.w / (s.P - CP)) };
      return { level: "crit", lead: "W′ " + wp + "%:", accent: s.P < CP * 0.85 ? "ODBUDOWA " + mmss((W0 * 0.55 - s.w) / Math.max(5, (CP - s.P) * 0.6)) : "TRZYMASZ!" };
    }
    var dsc = nextDescent(s, 1.0);
    if (dsc) return { level: "crit", lead: dsc.d < 0.05 ? "teraz" : "za " + Math.round(dsc.d * 1000 / 10) * 10 + " m", accent: "zjazd " + Math.round(dsc.g).toString().replace("-", "−") + "% " + SURF_N[surfAt(s, s.km + dsc.d)] };
  }
  var list = sc.msgs; return MSG[list[Math.floor(s.t / 8) % list.length]](s);
}
function dynItem() {
  var s = S, sc = s.sc;
  if (sc.aero) { var a = [["−11", 1], ["−4", 0], ["+6", 1], ["···", -1], ["−9", 1]][s.aeroK % 5]; return { kind: "AERO", value: a[0], unit: "W", conf: a[1] }; }
  if (!sc.noRoute && S.deadline) {
    var eta = etaMs(), dl = S.deadline;
    if (dl - eta <= 10 * 60000) {
      var hLeft = (dl - now()) / 3600000, req = hLeft > 0 ? (s.total - s.km) / hLeft : 99;
      return { kind: "AVG", value: (Math.round(Math.min(req, 99.9) * 10) / 10).toFixed(1).replace(".", ","), unit: "km/h", warn: eta > dl ? 2 : 1 };
    }
  }
  var k = ["ATD", "WIND", "shop", "water"][Math.floor(s.t / 4) % 4];
  if (sc.noRoute) return { kind: "ASC", value: String(Math.round(ascentDone())), unit: "m" };
  if (k === "ATD") return { kind: "ATD", value: String(ascentLeft(s)), unit: "m" };
  if (k === "WIND") { var wk = 0; for (var q = s.km; q < s.total; q += 0.2) { var rel = ((sc.wFrom + 180 - heading(s, q)) % 360 + 360) % 360; if (-sc.ws * Math.cos(rel * Math.PI / 180) > 2) wk += 0.2; } return { kind: "WIND", value: String(Math.round(wk)), unit: "km" }; }
  if (k === "shop") return { kind: "shop", value: kmTxt(Math.max(0.1, s.total - 0.9 - s.km)), unit: "km" };
  return { kind: "water", value: kmTxt(Math.abs(s.sc.total * 0.6 - s.km) + 0.4), unit: "km" };
}
function ascentDone() { var a = 0; for (var k = 0; k < S.km; k += 0.05) { var g = grade(S, k); if (g > 0) a += g / 100 * 50; } return a; }
function trend(hist, thr) { if (hist.length < 21) return 0; var d = hist[hist.length - 1] - hist[hist.length - 21]; return d > thr ? 1 : d < -thr ? -1 : 0; }

function navData() {
  var s = S, sc = s.sc;
  return Object.assign({ msg: message(), doneKm: s.km, leftKm: sc.noRoute ? null : s.total - s.km, etaMs: etaMs(), deadlineMs: S.deadline,
    tempC: sc.temp, windMps: sc.ws, windRelDeg: Math.round(s.rel), windSignedMps: s.hs, windTotalMps: sc.ws, windCached: !!sc.cached,
    gradePct: qv("nachylenie", "przeglad") === "przeglad" ? [4, 7, 10, 13, 17, 22, -4, -7, -10, 1][Math.floor(Date.now() / 2500) % 10] : s.gr /* 22.10: przeglad kolorow tla */, dyn: dynItem(),
    camRec: qv("kamera", "brak") === "jest" && s.moving > 0 ? 2 : 0 /* 22.10: wariant kamera (2 = nagrywa) */,
    routeSrc: sc.noRoute ? null : (qv("trasa", "qbot") === "karoo" ? "K" : "Q") /* 22.10 pkt 3 */,
    homeKm: sc.noRoute ? Math.max(0.5, 3 + 9 * Math.abs(Math.sin(s.km / 9))) : null /* 22.10 pkt 7: przykladowe */,
    duskMs: todayAt(17, 34), nowMs: now() }, weather());
}
function instrData() {
  var s = S, sc = s.sc, zone = s.hr / LTHR, alarm = s.over >= 30;
  var vNow = avg(s.vs.slice(-60)) * 3.6, av = avgV();
  return { route: sc.noRoute ? null : { doneKm: s.km, totalKm: s.total, ahead: aheadSegs(), stopsKm: stopsKm() },
    hr: sc.noHr ? null : Math.round(s.hr), hrZone: sc.noHr ? null : (zone < 0.81 ? 1 : zone < 0.90 ? 2 : zone < 0.95 ? 3 : zone < 1.06 ? 4 : 5),
    hrDriftLevel: s.t > 7200 ? 1 : 0, cadence: s.cad, cpe5W: np(s.pw.slice(-300)), cpTrend: (function () { var n5 = np(s.pw.slice(-300)); if (s.npLast != null && n5 != null) { if (n5 - s.npLast > 0.5) s.npDir = 1; else if (n5 - s.npLast < -0.5) s.npDir = -1; } s.npLast = n5; return n5 ? (s.npDir || 0) : 0; })(),   /* 19.10: jak QExt2 FrameTrend (vs poprzednia ramka) */
    avgSpeedKmh: av, avgSpeedTrend: s.v < 1 ? 0 : vNow > av + 0.5 ? 1 : vNow < av - 0.5 ? -1 : 0,
    wbalPct: Math.round(s.w / W0 * 100), wbalTrend: (function () { var h = s.wHist; if (h.length < 2) return "steady"; var d = s.w - h[h.length - 2]; return d > 150 ? "rising" : d < -1500 ? "plummeting" : d < -150 ? "falling" : "steady"; })(),
    gearFront: 40, gearRear: s.gearR, speedKmh: s.v * 3.6, powerW: s.P, cpW: CP,
    powerColor: alarm ? "#000000" : s.P > CEIL ? "#FF8C8C" : s.P >= 0.95 * CEIL ? "#FACC15" : "#FFFFFF", powerBg: alarm ? "#FF5252" : 0 };
}
function statsData() {
  var s = S, sc = s.sc, npR = np(s.pw), ap = avg(s.pw), secs = s.moving, ifv = npR / CP;
  var tempo = s.tempo.slice(), part = (s.moving % 3600) >= 300;
  if (part) { var n = s.moving % 3600; tempo.push([Math.round(avg(s.pw.slice(-n))), avg(s.vs.slice(-n)) * 3.6]); }
  var planT = (s.km - s.planStartKm) / s.planV * 3600, real = s.t - s.planStartT, dm = Math.round((real - planT) / 60);
  var winNp = s.winNp.slice(), winEf = s.winEf.slice(), wp = (s.moving % 300) >= 60;
  if (wp) { var m = s.moving % 300; winNp.push(np(s.pw.slice(-m))); winEf.push(+(np(s.pw.slice(-m)) / avg(s.hrs.slice(-m))).toFixed(2)); }
  var gate = null;
  if (sc.gate) { var dist = s.total - s.km; gate = dist > 1.2 ? { state: "FAR", main: "BRAMA", sub: kmTxt(dist) + " km" } : dist > 0.25 ? { state: "READY", main: "OTWÓRZ", sub: Math.round(dist * 1000 / 10) * 10 + " m" } : { state: "OPENED", main: "OTWARTA", sub: "przed chwilą" }; }
  else gate = { state: "FAR", main: "BRAMA", sub: "daleko" };
  var lightS = sc.light || "OK";
  return { np: npR, npZone: (function () { var q = ifv; return q < 0.55 ? 1 : q < 0.75 ? 2 : q < 0.90 ? 3 : q < 1.05 ? 4 : q < 1.20 ? 5 : 6; })(),
    ifv: ifv, vi: ap > 0 ? npR / ap : null, rsrv: Math.round(clamp(100 - s.cho / 4.2 - (100 - s.w / W0 * 100) * 0.3, 3, 100)),
    xss: secs * npR * ifv / (CP * 36), xssPlan: 156, kcal: Math.round(s.kj / 0.23 / 4.184),
    winNp: winNp, winEf: sc.noHr ? winEf.map(function () { return null; }) : winEf, winPartial: wp, typEf: 1.32, cpW: CP, np5Now: np(s.pw.slice(-300)),
    planDeltaMin: sc.noRoute ? null : dm, planDriveDelta: sc.noRoute ? null : Math.round(dm * 0.7), planStopDelta: sc.noRoute ? null : dm - Math.round(dm * 0.7), planFromQbot: true,
    tempo: tempo, tempoPartial: part, gate: gate, lightState: lightS, light: lightS === "OK" ? { controllable: true, battery: "68%", mode: "MIGANIE" } : null,
    carbRate: 60, carbSpent: Math.round(s.cho), fluidRate: sc.temp > 25 ? 0.9 : 0.5, cadAvg: 84,
    batDrain: 9, batLeftSec: Math.max(0, Math.round((92 - s.t / 3600 * 9) / 9 * 3600)),
    camBat: qv("kamera", "brak") === "jest" ? Math.max(0, Math.round(87 - s.t / 3600 * 8)) : null /* 22.10: wariant kamera */,
    camOn: qv("kamera", "brak") === "jest" };
}
function buildInfoWx() {
  var sc = S.sc, route = !sc.noRoute, items = [], T0 = sc.temp, kind = sc.infoWx, sp = 22;
  if (route) {
    for (var km = Math.max(0, S.km - 5); km <= S.total + 0.01; km += 2.5) {
      var t = (km - S.km) / sp * 60 + 5, feels = T0 - 2 + 3 * Math.sin(km / 14) - (kind === "night" ? Math.max(0, km - S.km) / 12 : 0);
      var mm = 0, prob = 10;
      if (kind === "rainSoon") { var dt = t - 45; mm = dt > 0 && dt < 50 ? 1.6 * Math.sin(Math.PI * dt / 50) : 0; prob = dt > -20 && dt < 60 ? 65 : 15; }
      if (kind === "radar") { mm = t < 40 && t > 15 ? 1.2 + 0.6 * Math.sin(t / 6) : 0.1; prob = t < 50 ? 85 : 30; }
      var rel = ((sc.wFrom + 180 - heading(S, km)) % 360 + 360) % 360, head = -sc.ws * Math.cos(rel * Math.PI / 180);
      items.push({ km: km, t: t, feels: feels, mm: Math.max(0, mm), prob: prob, head: head, gust: Math.abs(head) + 3 + 2 * hash(km), ws: sc.ws + 1.5 * Math.sin(km / 8) /* przykladowe (auto) */ });
    }
  } else {
    for (var m = 0; m <= 420; m += 20) {
      var mm2 = kind === "rainSoon" && m > 40 && m < 100 ? 1.2 : 0;
      items.push({ t: m, feels: T0 - m / 60 * 0.4, mm: mm2, prob: mm2 ? 70 : 10, head: sc.ws * Math.cos(m / 90), gust: sc.ws + 3, ws: sc.ws + 0.8 * Math.sin(m / 60) /* przykladowe (auto) */ });
    }
  }
  return { items: items, route: route, fetchedMs: S.wxFetched, ageMin: 0, live: kind === "radar", radarUntilMin: kind === "radar" ? 70 : null };
}
function infoData() {
  var s = S, sc = s.sc, at = sc.noRoute ? 0 : ascentTotal(s);
  return { hasRoute: !sc.noRoute, doneKm: s.km, totalKm: sc.noRoute ? null : s.total, etaMs: etaMs(), twilightMs: todayAt(17, 34), twilightDawn: false,
    ahead: aheadSegs(), stopsKm: stopsKm(), ascDone: sc.noRoute ? null : Math.round(ascentDone()), ascLeft: sc.noRoute ? null : ascentLeft(s),
    avgGrossKmh: s.t ? s.km / (s.t / 3600) : null, movingSec: s.moving, stopsSec: s.stops + 12 * 60 };
}

/* ---------------- mapa (poglądowa, „heading-up” jak na Karoo) ---------------- */
var MAP = null;
function buildMap() {
  var pts = [], x = 0, y = 0, step = 0.025, tot = S.sc.noRoute ? S.km + 6 : S.total;
  for (var k = 0; k <= tot + 0.001; k += step) { pts.push([x, y]); var h = heading(S, k) * Math.PI / 180; x += Math.sin(h) * step * 1000; y += Math.cos(h) * step * 1000; }
  var feats = [], roads = [];
  for (var i = 0; i < pts.length; i += 12) {
    var p = pts[i], hh = heading(S, i * step) * Math.PI / 180, r1 = hash(i), r2 = hash(i + 7);
    if (r1 < 0.55) { var a = hh + Math.PI / 2 + (r2 - 0.5) * 0.9, L = 300 + r2 * 900; roads.push([p[0] - Math.sin(a) * L, p[1] - Math.cos(a) * L, p[0] + Math.sin(a) * L, p[1] + Math.cos(a) * L, r1 < 0.12 ? 7 : 4]); }
    if (r2 < 0.35) { var side = r1 < 0.5 ? 1 : -1, off = 120 + r1 * 400, cx = p[0] + Math.cos(hh) * off * side, cy = p[1] - Math.sin(hh) * off * side; feats.push([cx, cy, 80 + r2 * 260, r1 < 0.15 ? "#1d3550" : "#22372a"]); }
  }
  MAP = { pts: pts, step: step, feats: feats, roads: roads };
}
function drawMap(cv, W, H) {
  var dpr = Math.max(1, window.devicePixelRatio || 1);
  cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
  var c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.fillStyle = "#20252b"; c.fillRect(0, 0, W, H);
  var i = Math.min(MAP.pts.length - 1, Math.round(S.km / MAP.step)), p = MAP.pts[i], hd = heading(S, S.km) * Math.PI / 180, mpp = 3;
  c.save(); c.translate(W / 2, H * 0.62); c.rotate(-hd);
  function P(x, y) { return [(x - p[0]) / mpp, -(y - p[1]) / mpp]; }
  MAP.feats.forEach(function (f) { var q = P(f[0], f[1]); c.fillStyle = f[3]; c.beginPath(); c.ellipse(q[0], q[1], f[2] / mpp, f[2] / mpp * 0.6, f[0] % 3, 0, 2 * Math.PI); c.fill(); });
  c.lineCap = "round";
  MAP.roads.forEach(function (r) { var a = P(r[0], r[1]), b = P(r[2], r[3]); c.strokeStyle = r[4] > 5 ? "#5a636e" : "#3d444e"; c.lineWidth = r[4]; c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.stroke(); });
  function poly(from, to, col, w) { c.strokeStyle = col; c.lineWidth = w; c.lineJoin = "round"; c.beginPath(); for (var k = from; k <= to; k++) { var q = P(MAP.pts[k][0], MAP.pts[k][1]); if (k === from) c.moveTo(q[0], q[1]); else c.lineTo(q[0], q[1]); } c.stroke(); }
  var lo = Math.max(0, i - 400), hi = Math.min(MAP.pts.length - 1, i + 600);
  if (!S.sc.noRoute) { poly(i, hi, "#000", 11); poly(i, hi, "#FF8A00", 7); }
  poly(lo, i, "#000", 9); poly(lo, i, "#8a94a3", 5);
  c.restore();
  // pozycja: strzałka jak na Karoo
  c.save(); c.translate(W / 2, H * 0.62);
  c.beginPath(); c.moveTo(0, -16); c.lineTo(12, 13); c.lineTo(0, 6); c.lineTo(-12, 13); c.closePath();
  c.fillStyle = "#2E7BFF"; c.fill(); c.lineWidth = 3; c.strokeStyle = "#fff"; c.stroke(); c.restore();
  // skala
  c.fillStyle = "#cfd6de"; c.fillRect(14, H - 22, 200 / mpp, 3); c.font = "600 12px system-ui"; c.fillText("200 m", 14, H - 28);
}

/* ---------------- pętla ---------------- */
function draw() {
  var t = now();
  var hhmm = new Date(t).toTimeString().slice(0, 5);
  Array.prototype.forEach.call(document.querySelectorAll(".sbClock"), function (e) { e.textContent = hhmm; });
  // 18.10: trzy ekrany Karoo naraz (KOKPIT 2 z mapą | STATS v2 | INFO)
  var cfg = { hr: "zone", wbal: "trend", power: "pacing", speed: "yellow", wind: "headtail", windMin: 3, windShare: 0.7, etaGreen: 30, etaYellow: 10 };
  QK2.nav($("cvNav"), 478, 143, navData(), cfg);
  QK2.instr($("cvInstr"), 478, 143, instrData(), cfg);
  drawMap($("cvMap"), 480, 800 - 38 - 2 * 143);
  QST.stats($("cvStats"), 480, 762, statsData());
  QST.info($("cvInfo"), 480, 762, infoData(), S.wx, infoScale, t, todayAt(6, 58), todayAt(17, 34));
  var s = S;
  $("state").textContent = "czas jazdy " + Math.floor(s.t / 3600) + " h " + Math.floor(s.t % 3600 / 60) + " min" +
    " · km " + s.km.toFixed(2) + (s.sc.noRoute ? "" : " / " + s.total) + "\nmoc " + s.P + " W · " + (s.v * 3.6).toFixed(1) + " km/h · nachylenie " + s.gr.toFixed(1) +
    "% · wiatr " + (s.hs > 0 ? "w twarz " : "w plecy ") + Math.abs(s.hs).toFixed(1) + " m/s\ntętno " + Math.round(s.hr) + " · W′ " + Math.round(s.w / W0 * 100) + "% · NP jazdy " + np(s.pw) + " W";
}
function tick() { if (playing && S) { for (var i = 0; i < speedX; i++) step(); } if (S) draw(); }

function build() {
  SCEN.forEach(function (sc, i) {
    var b = document.createElement("button"); b.type = "button"; b.textContent = sc.n;
    b.onclick = function () { curIdx = i; start(i); sync(); draw(); };
    $("scen").appendChild(b);
  });
  Array.prototype.forEach.call($("sim").querySelectorAll("[data-x]"), function (b) { b.onclick = function () { speedX = +b.getAttribute("data-x"); sync(); }; });
  $("bPlay").onclick = function () { playing = !playing; sync(); };
  $("bRestart").onclick = function () { start(curIdx); draw(); };
  $("cvInfo").onclick = function () { infoScale = (infoScale + 1) % 3; draw(); };
  window.addEventListener("resize", fitScreens);
}
function sync() {
  Array.prototype.forEach.call($("scen").children, function (b, i) { b.classList.toggle("on", i === curIdx); });
  Array.prototype.forEach.call($("sim").querySelectorAll("[data-x]"), function (b) { b.classList.toggle("on", +b.getAttribute("data-x") === speedX); });
  $("bPlay").textContent = playing ? "⏸ pauza" : "▶ jedź";
  $("desc").textContent = SCEN[curIdx].d;
}
/* trzy ekrany obok siebie: zmniejsz, gdy brak miejsca (zoom), a w Garażu podaj wysokość ramce */
function fitScreens() {
  var sc = $("screens"), par = sc.parentNode, need = 3 * 500 + 2 * 16;
  var z = Math.max(0.4, Math.min(1, (par.clientWidth - 4) / need));
  sc.style.zoom = z;
  if (window.parent !== window) window.parent.postMessage({ qext2Height: document.documentElement.scrollHeight }, location.origin);
}
/* 18.10: dostep dla testu automatu (scripts/qext2_watch.py: czy nowe pola danych maja wartosci) */
window.__QEXT2_SIM = { navData: navData, instrData: instrData, statsData: statsData, infoData: infoData, wx: function () { return S.wx; } };
build(); start(0); sync(); draw(); fitScreens(); setTimeout(fitScreens, 300);
QK2.ready.then(function () { draw(); setInterval(tick, 1000); });
})();
