/* qext2-stats.js (2026-10-18) — pola STATS v2 i INFO QExt2 narysowane na <canvas> dla makiety w QBocie.
   ŹRÓDŁO PRAWDY: /opt/qbot/qext2_deploy/app/src/main/kotlin/com/qext2/primary/statsv2/StatsV2Renderer.kt (stan 18.10.2026):
   render() = STATS v2, renderInfo() = INFO (TRASA + PRZEWYŻSZENIE + POGODA). Układ bazowy 480×760 skalowany do pola,
   te same moduły, współrzędne, kolory, ikony (ścieżki SVG z kodu), czcionka Saira Semi Condensed. Zmiana w QExt2 → popraw tutaj.
   API: QST.stats(canvas, W, H, d), QST.info(canvas, W, H, d, wx, scale, nowMs, dawnMs, duskMs). */
(function () {
"use strict";
var BW = 480, BH = 760;
var C = { BG: "#2A3038", CELL: "#14181D", LABEL: "#D5DCE3", UNIT: "#9AA5B1", SUB: "#C9D2DC", NONE: "#9AA3AE", WHITE: "#FFFFFF", PILL: "#111315",
  TRACK: "#465366", AMBER: "#F59E0B" };
var P_BAR = "M6,0 H31 V2 H6 Z";
var P_BOLT = "M18.502,16.002V16.502H19.002H27.227L19.499,33.671V22V21.5H18.999H10.773L14.957,12.205L18.502,4.329V16.002Z";
var P_CAD = "M19,7 A12,12,0,0,1,31,19 A12,12,0,0,1,19,31 A12,12,0,0,1,7,19 A12,12,0,0,1,19,7 Z M19,10 A9,9,0,0,0,10,19 A9,9,0,0,0,19,28 A9,9,0,0,0,28,19 A9,9,0,0,0,19,10 Z M20.1,20.1 L35.1,5.1 L32.9,2.9 L17.9,17.9 Z M12.3,27.9 L7.4,32.8 L5.2,30.6 L10.1,25.7 Z";
var P_GRADE = "M3,34 L3,32 L13,16 L19,22 L28,8 L35,20 L35,34 Z";
var P_GEL = "M12,5 H26 L24,10 V31 A3,3,0,0,1,21,34 H17 A3,3,0,0,1,14,31 V10 Z M17,15 H21 V27 H17 Z";
var P_DROP = "M19,4 C19,4 9,16 9,23 A10,10,0,0,0,29,23 C29,16 19,4 19,4 Z";
var P_FLAME = "M19,3 C21,10 28,13 28,23 A9,9,0,0,1,10,23 C10,18 13,15 15,13 C15,17 17,19 19,19 C18,13 19,8 19,3 Z";
var P_BARS = "M5,26 H12 V34 H5 Z M15.5,18 H22.5 V34 H15.5 Z M26,9 H33 V34 H26 Z";
var P_RING = "M19,4 A15,15,0,1,1,18.99,4 Z M19,7 A12,12,0,1,0,19.01,7 Z";
var P_BATT = "M15,3 H23 V6 H15 Z M10,6 H28 V35 H10 Z M13,9 V32 H25 V9 Z M15,22 H23 V30 H15 Z";
var P_ROUTE = "M247-167q-47-47-47-113v-327q-35-13-57.5-43.5T120-720q0-50 35-85t85-35q50 0 85 35t35 85q0 39-22.5 69.5T280-607v327q0 33 23.5 56.5T360-200q33 0 56.5-23.5T440-280v-400q0-66 47-113t113-47q66 0 113 47t47 113v327q35 13 57.5 43.5T840-240q0 50-35 85t-85 35q-50 0-85-35t-35-85q0-39 22.5-70t57.5-43v-327q0-33-23.5-56.5T600-760q-33 0-56.5 23.5T520-680v400q0 66-47 113t-113 47q-66 0-113-47Z";
var EVEN_ODD = [P_CAD, P_GEL, P_RING, P_BATT];
/* 22.10 v4: warianty z symulatora (window.QV) */
function qv(k, d) { return (typeof window !== "undefined" && window.QV) ? window.QV(k, d) : d; }
var EFC = { magenta: "#FF3DF5", bialy: "#FFFFFF", zolty: "#FACC15", cyjan: "#67E8F9" };
var FONT = "QSairaSemi, 'Roboto Condensed', 'Arial Narrow', sans-serif";

var c, sx = 1, sy = 1, s = 1;
function X(v) { return v * sx; } function Y(v) { return v * sy; } function F(v) { return v * s; }
function fmt1(v) { return (Math.round(v * 10) / 10).toFixed(1); }
function fmt2(v) { return (Math.round(v * 100) / 100).toFixed(2); }
function fmt0(v) { return String(Math.round(v)); }
function clock(ms) { var d = new Date(ms); return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2); }
function hm(sec) { sec = Math.floor(sec); return Math.floor(sec / 3600) + ":" + ("0" + Math.floor((sec % 3600) / 60)).slice(-2); }
function hmm(min) { var m = Math.round(min); return Math.floor(m / 60) + ":" + ("0" + (m % 60)).slice(-2); }
function R(l, t, r, b) { return { l: l, t: t, r: r, b: b }; }
function setF(size) { c.font = "600 " + size + "px " + FONT; }
function textW(t, size) { setF(size); return c.measureText(t).width; }
function fit(t, size, maxW) { var sz = size; while (sz > 10 && textW(t, sz) > maxW) sz -= 1; return sz; }
/* Android: drawText(t, x, cy - (ascent+descent)/2) — pionowo na środek metryk czcionki */
function text(t, x, cy, size, color, align) {
  setF(size); c.fillStyle = color; c.textAlign = align || "left"; c.textBaseline = "alphabetic";
  var m = c.measureText("Hg"), A = m.fontBoundingBoxAscent || size * 0.95, D = m.fontBoundingBoxDescent || size * 0.25;
  c.fillText(t, x, cy + (A - D) / 2);
}
function fbox(l, t, r, b, col) { c.fillStyle = col; c.fillRect(l, t, r - l, b - t); }
function rrect(l, t, r, b, rad) { c.beginPath(); if (c.roundRect) c.roundRect(l, t, r - l, b - t, rad); else c.rect(l, t, r - l, b - t); }
function circle(x, y, r, col) { c.fillStyle = col; c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.fill(); }
function line(x1, y1, x2, y2, col, w) { c.strokeStyle = col; c.lineWidth = w; c.beginPath(); c.moveTo(x1, y1); c.lineTo(x2, y2); c.stroke(); }

function icon(parts, x, y, size, color, material) {
  c.save(); c.translate(x, y);
  if (material) { c.scale(size / 960, size / 960); c.translate(0, 960); } else c.scale(size / 38, size / 38);
  c.fillStyle = color;
  parts.forEach(function (pd) { try { c.fill(new Path2D(pd), EVEN_ODD.indexOf(pd) >= 0 ? "evenodd" : "nonzero"); } catch (e) { } });
  c.restore();
}
function cell(r) { fbox(X(r.l), Y(r.t), X(r.r), Y(r.b), C.CELL); }
/* 22.10 pkt 9: mniejsze naglowki (24 -> 18 px), wiecej miejsca na wartosci */
function label(r, ic, name, unit, material) {   /* 22.10 v2: 21 px (24 bylo za duze, 18 za male) */
  var left = X(r.l) + F(10), top = Y(r.t) + F(5), hRow = F(25), x = left;
  if (ic) { icon(ic, x, top + F(2), F(20), "#F0F3F6", material); x += F(25); }
  text(name, x, top + hRow / 2, F(21), C.LABEL);
  x += textW(name, F(21)) + F(5);
  if (unit) text(unit, x, top + hRow / 2, F(19), C.UNIT);
  return top + hRow;
}
function rightLabel(r, parts) {
  var cy = Y(r.t) + F(5) + F(12.5), x = X(r.r) - F(10);
  parts.slice().reverse().forEach(function (p) { var z = F(p[1] * 0.9); text(p[0], x, cy, z, p[2], "right"); x -= textW(p[0], z) + F(5); });
}
function none(cx, cy, t) { text(t || "brak", cx, cy, F(26), C.NONE, "center"); }
function valueCell(r, ic, name, unit, value, size, color) {
  cell(r);
  var lb = label(r, ic, name, unit), cx = (X(r.l) + X(r.r)) / 2, cy = (lb + Y(r.b) - F(8)) / 2;
  if (value == null) { none(cx, cy); return; }
  text(value, cx, cy, fit(value, F(size), X(r.r) - X(r.l) - F(20)), color, "center");
}
function hex(col) { var n = parseInt(col.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function lum(col) { var rgb = hex(col).map(function (v) { var x = v / 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }); return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]; }
function barText(t, x, cy, size, segW, bg, align) {
  var tw = textW(t, size), pad = F(6), need = tw + 2 * pad + F(12);
  if (align === "center" && segW < tw + F(2)) return;
  if (segW >= need && lum(bg) >= 0.05) {
    setF(size); var m = c.measureText("Hg"), hgt = ((m.fontBoundingBoxAscent || size * 0.95) + (m.fontBoundingBoxDescent || size * 0.25)) * 0.82;
    var l = align === "left" ? x : align === "right" ? x - tw - 2 * pad : x - tw / 2 - pad;
    fbox(l, cy - hgt / 2, l + tw + 2 * pad, cy + hgt / 2, C.PILL);
    text(t, l + pad, cy, size, C.WHITE);
  } else {
    var col = lum(bg) > 0.18 ? C.PILL : C.WHITE, xx = align === "left" ? x + pad : align === "right" ? x - pad : x;
    text(t, xx, cy, size, col, align);
  }
}
function zoneColor(z) { return { 1: "#9CA3AF", 2: "#60A5FA", 3: "#4ADE80", 4: "#FACC15", 5: "#FB923C", 6: "#FF8C8C" }[z] || C.WHITE; }
function viColor(vi) { return vi == null || vi < 1.05 ? C.WHITE : vi < 1.10 ? "#FACC15" : "#FF8C8C"; }
function zoneColor5(np, cp) {
  if (!cp || cp <= 0) return "#9AA3AE";
  var q = np / cp; return q < 0.55 ? "#9AA3AE" : q < 0.75 ? "#6FA8FF" : q < 0.90 ? "#22C55E" : q < 1.05 ? "#EAB308" : q < 1.20 ? "#F97316" : "#EF4444";
}

/* ---------------- moduły STATS v2 ---------------- */
function drawNp(r, d) { valueCell(r, [P_BAR, P_BOLT], "NP", "W", d.np != null ? String(d.np) : null, 78, C.WHITE); if (d.np != null && d.npZone != null) rightLabel(r, [["Z" + d.npZone, 36, zoneColor(d.npZone)]]);   /* 22.10: strefa wieksza */ }
function drawIf(r, v) {
  cell(r);
  var lb = label(r, [P_BOLT], "IF", ""), l = X(r.l) + F(10), rr = X(r.r) - F(10), t = lb + F(6), b = Y(r.b) - F(8);
  if (v == null) { none((l + rr) / 2, (t + b) / 2); return; }
  var zones = [[0, 0.75], [0.75, 0.85], [0.85, 1.0], [1.0, 1.2]], cols = ["#4F6E80", "#F2C230", "#E9862B", "#E0563B"], wTot = rr - l;
  zones.forEach(function (z, i) { fbox(l + z[0] / 1.2 * wTot, t, l + z[1] / 1.2 * wTot - (i < 3 ? F(2) : 0), b, cols[i]); });
  var mx = l + Math.min(v, 1.2) / 1.2 * wTot;
  fbox(mx - F(4), t - F(4), mx + F(4), b + F(4), C.PILL); fbox(mx - F(2), t - F(4), mx + F(2), b + F(4), C.WHITE);
  /* 22.10 pkt 8: liczba zawsze po stronie z wiekszym miejscem -- nigdy na znaczniku */
  var txt = fmt2(v).replace(/^0/, ""), cy = (t + b) / 2, fs = F(42);
  var spL = mx - F(6) - l, spR = rr - (mx + F(6)), onLeft = spL >= spR, sp = Math.max(spL, spR);
  while (fs > F(22) && textW(txt, fs) + F(12) > sp) fs -= 1;
  if (onLeft) barText(txt, mx - F(6), cy, fs, sp, cols[0], "right"); else barText(txt, mx + F(6), cy, fs, sp, cols[0], "left");
}
function drawRsrv(r, v) {
  cell(r);
  var lb = label(r, [P_RING], "RSRV", "%"), l = X(r.l) + F(10), rr = X(r.r) - F(10), t = lb + F(6), b = Y(r.b) - F(8);
  if (v == null) { none((l + rr) / 2, (t + b) / 2); return; }
  var pct = Math.max(0, Math.min(100, v)), col = pct >= 40 ? "#2F7D4A" : pct >= 20 ? "#C9A227" : "#C2412D";
  fbox(l, t, rr, b, C.TRACK); var fx = l + (rr - l) * pct / 100; fbox(l, t, fx, b, col);
  var cy = (t + b) / 2;
  if (pct >= 40) barText(String(pct), l + F(4), cy, F(44), fx - l, col, "left"); else barText(String(pct), rr - F(4), cy, F(44), rr - fx, C.TRACK, "right");
}
function drawWindows(r, d) {
  cell(r);
  label(r, [P_BAR, P_BOLT], "PRZEBIEG", "NP / 5 min");
  if (d.winEf.some(function (e) { return e != null; })) rightLabel(r, [["EF", 18, C.WHITE]]);
  var l = X(r.l) + F(10), rr = X(r.r) - F(10), sumSize = F(44), sumBase = Y(r.b) - F(6), ct = Y(r.t) + F(31), cb = sumBase - sumSize * 0.72 - F(8);
  var all = d.winNp;
  if (!all.length) { none((l + rr) / 2, (ct + sumBase) / 2, "pierwsze okno po 5 min jazdy"); return; }
  var slots = 23, n = Math.min(all.length, slots), np = all.slice(-n), ef = d.winEf.slice(-n), gap = F(3), bw = (rr - l - gap * (slots - 1)) / slots;
  var mx = Math.max(50, Math.max.apply(null, np)) * 1.08, lastDone = d.winPartial ? n - 2 : n - 1, best = null;
  for (var i = 0; i <= Math.max(0, lastDone); i++) if (best == null || np[i] > np[best]) best = i;
  var xAt = function (k) { return rr - (n - k) * (bw + gap) + gap; };
  for (var k = 0; k < n; k++) {
    var x = xAt(k), hh = (cb - ct) * (np[k] / mx);
    c.globalAlpha = (d.winPartial && k === n - 1) ? 100 / 255 : 150 / 255;   /* 22.10 v3: przygaszone pod linia EF */ fbox(x, cb - hh, x + bw, cb, zoneColor5(np[k], d.cpW)); c.globalAlpha = 1;
    if (k === best && n > 1) { c.strokeStyle = C.WHITE; c.lineWidth = F(2); c.strokeRect(x, cb - hh, bw, hh); }
  }
  var efv = []; ef.forEach(function (e, kk) { if (e != null) efv.push([kk, e]); });
  if (efv.length >= 2) {
    var vals = efv.map(function (q) { return q[1]; }).concat(d.typEf != null ? [d.typEf] : []);
    var lo = Math.min.apply(null, vals) - 0.02, hi = Math.max.apply(null, vals) + 0.02;
    var yOf = function (e) { return ct + F(3) + (cb - ct - F(6)) * (1 - (e - lo) / (hi - lo)); };
    if (d.typEf != null) { var yy = yOf(d.typEf); c.lineJoin = "round"; for (var xx = l; xx < rr; xx += F(9)) line(xx, yy, Math.min(xx + F(5), rr), yy, C.SUB, F(3)); }
    c.beginPath(); efv.forEach(function (q, ii) { var px = xAt(q[0]) + bw / 2, py = yOf(q[1]); if (ii === 0) c.moveTo(px, py); else c.lineTo(px, py); });
    c.lineJoin = "round"; c.strokeStyle = "#000"; c.lineWidth = F(11); c.stroke(); c.strokeStyle = EFC[qv("ef", "magenta")] || "#FF3DF5"; c.lineWidth = F(5.5); c.stroke();   /* 22.10 v4: kolor linii EF (wariant) */
    efv.forEach(function (q) { var px = xAt(q[0]) + bw / 2, py = yOf(q[1]); circle(px, py, F(6), "#000"); circle(px, py, F(4.4), EFC[qv("ef", "magenta")] || "#FF3DF5"); });
  }
  var li = Math.max(0, lastDone), sb = sumBase;
  function grp(x, lab, value, unit, align) {
    var lw = textW(lab, F(22)) + F(5), vw = textW(value, sumSize), uw = unit ? F(5) + textW(unit, F(18)) : 0, total = lw + vw + uw;
    var x0 = align === "left" ? x : align === "right" ? x - total : x - total / 2;
    c.textAlign = "left"; c.textBaseline = "alphabetic";
    setF(F(22)); c.fillStyle = C.SUB; c.fillText(lab, x0, sb);
    setF(sumSize); c.fillStyle = C.WHITE; c.fillText(value, x0 + lw, sb);
    if (unit) { setF(F(18)); c.fillStyle = C.UNIT; c.fillText(unit, x0 + lw + vw + F(5), sb); }
  }
  grp(l, "5′", String(d.np5Now != null ? d.np5Now : np[li]), "W", "left");
  if (ef[li] != null) grp((l + rr) / 2, "EF", fmt2(ef[li]), d.typEf != null ? "(" + fmt2(d.typEf) + ")" : "", "center");
  if (best != null) grp(rr, "max", String(np[best]), "W", "right");
}
function drawXss(r, d) {
  cell(r); label(r, [P_BARS], "XSS", "");
  var l = X(r.l) + F(10), rr = X(r.r) - F(10), T = Y(r.t), v = d.xss;
  if (v == null) { none((l + rr) / 2, T + F(60)); return; }
  var vs = fmt0(v), plan = d.xssPlan;
  if (plan != null && plan > 0) {
    var vsz = F(52), ps = "/" + fmt0(plan), w = textW(vs, vsz) + F(4) + textW(ps, F(22)), x0 = (l + rr) / 2 - w / 2;
    text(vs, x0, T + F(55), vsz, C.WHITE); text(ps, x0 + textW(vs, vsz) + F(4), T + F(63), F(22), C.UNIT);
    var bt = T + F(79), bb = T + F(93);
    fbox(l, bt, rr, bb, C.TRACK); fbox(l, bt, l + (rr - l) * Math.max(0, Math.min(1, v / plan)), bb, v > plan ? "#22C55E" : "#2E7BFF");
  } else text(vs, (l + rr) / 2, T + F(62), fit(vs, F(66), rr - l), C.WHITE, "center");
}
/* 22.10 pkt 10: PLAN CZASU znow na cala szerokosc, duze liczby; jazda i postoje w jednym wierszu po prawej */
function drawPlan(r, d) {
  cell(r); label(r, null, "PLAN CZASU", "");
  if (d.planFromQbot) rightLabel(r, [["QBot", 20, C.SUB]]);
  else if (d.planRefEtaMs != null) rightLabel(r, [["ETA", 20, C.SUB], [clock(d.planRefEtaMs), 24, C.WHITE]]);
  var l = X(r.l) + F(12), rr = X(r.r) - F(12), T = Y(r.t), cy = T + F(55), dm = d.planDeltaMin;
  if (dm == null) { none((X(r.l) + X(r.r)) / 2, cy, "po 1. km z ETA"); return; }
  var sg = function (v) { return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v); };
  var st = sg(dm), col = dm >= 5 ? C.AMBER : dm <= -5 ? "#4ADE80" : C.WHITE;
  text(st, l, cy, F(62), col);
  var dd = d.planDriveDelta, ds = d.planStopDelta;
  var word = (dd != null && ds != null) ? "min" : dm > 0 ? "min za planem" : dm < 0 ? "min przed planem" : "min · zgodnie";
  text(word, l + textW(st, F(62)) + F(8), cy + F(8), F(24), C.UNIT);
  if (dd != null && ds != null) {
    var x = rr;
    [["postoje", ds], ["jazda", dd]].forEach(function (q) {
      var sv = sg(q[1]); text(sv, x, cy, F(42), q[1] >= 5 ? C.AMBER : C.WHITE, "right"); x -= textW(sv, F(42)) + F(6);
      text(q[0], x, cy + F(4), F(22), C.SUB, "right"); x -= textW(q[0], F(22)) + F(22);
    });
  }
}
function drawCamBat(r, d) {
  cell(r);
  label(r, [P_BATT], "CAM BAT", "");
  var cx = (X(r.l) + X(r.r)) / 2, cy = Y(r.t) + F(58);
  var b = d.camBat;
  if (b == null) { none(cx, cy, d.camOn ? "brak łącza" : "brak kamery"); return; }
  var col = b < 20 ? "#FF5252" : b < 35 ? C.AMBER : C.WHITE;
  var vs = String(b), wv = textW(vs, F(52)) + F(4) + textW("%", F(24)), x0 = cx - wv / 2;
  text(vs, x0, cy, F(52), col);
  text("%", x0 + textW(vs, F(52)) + F(4), cy + F(8), F(24), C.UNIT);
}
/* 22.10 pkt 9: TEMPO -- 3 ostatnie godziny zamiast 4, wieksze liczby */
function drawTempo(r, d) {
  cell(r); label(r, null, "TEMPO", "co godzinę");
  var T = Y(r.t), l = X(r.l) + F(12), rr = X(r.r) - F(10), all = d.tempo;
  if (!all.length) { none((l + rr) / 2, T + F(72), "po 5 min jazdy"); return; }
  if (all.length >= 2 && all[0][0] > 0) {
    var pct = Math.round((all[all.length - 1][0] - all[0][0]) * 100 / all[0][0]);
    rightLabel(r, [["moc od 1. h", 26, C.SUB], [(pct > 0 ? "+" : pct < 0 ? "−" : "") + Math.abs(pct) + "%", 32, pct <= -10 ? C.AMBER : C.WHITE]]);   /* 22.10: wieksze */
  }
  var start = Math.max(0, all.length - 3), shown = all.slice(start), colW = (rr - l) / 3;
  shown.forEach(function (hw, i) {
    var idx = start + i, x = l + colW * i, isNow = d.tempoPartial && idx === all.length - 1;
    text(isNow ? "teraz" : (idx + 1) + ". h", x, T + F(43), F(26), C.SUB);
    var ws = String(hw[0]); text(ws, x, T + F(72), F(46), zoneColor5(hw[0], d.cpW));   /* 22.10 v3: kolor strefy mocy */ text("W", x + textW(ws, F(46)) + F(3), T + F(78), F(22), C.UNIT);
    var ks = fmt1(hw[1]); text(ks, x, T + F(104), F(28), C.SUB); text("km/h", x + textW(ks, F(28)) + F(3), T + F(106), F(18), C.UNIT);
    if (i < shown.length - 1) fbox(x + colW - F(8), T + F(30), x + colW - F(6), T + F(116), C.BG);
  });
}
var GATE_COL = { READY: "#2E7BFF", ARMED: "#F2C230", SENDING: "#F2C230", WAIT: "#F2C230", OPENED: "#22C55E", ERROR: "#FF5252", NO_NET: "#FF5252", TOO_FAR: "#FF5252" };
function drawBrama(r, ui) {
  cell(r);
  var st = ui && ui.state, col = GATE_COL[st] || "#465366", off = !st || st === "FAR" || st === "NO_GPS";
  c.strokeStyle = col; c.lineWidth = F(4); c.setLineDash(off ? [F(10), F(7)] : []);
  rrect(X(r.l) + F(3), Y(r.t) + F(3), X(r.r) - F(3), Y(r.b) - F(3), F(6)); c.stroke(); c.setLineDash([]);
  label(r, null, "BRAMA", "");
  if (ui && ui.sub) rightLabel(r, [[ui.sub, 20, C.SUB]]);
  var main = (ui && ui.main) || "BRAMA";
  text(main, X(r.l) + F(16), Y(r.t) + F(60), fit(main, F(34), X(r.r) - X(r.l) - F(28)), off ? C.NONE : C.WHITE);
}
function drawLight(r, state, lu) {
  cell(r);
  if (lu && lu.controllable) { c.strokeStyle = "#2E7BFF"; c.lineWidth = F(4); rrect(X(r.l) + F(3), Y(r.t) + F(3), X(r.r) - F(3), Y(r.b) - F(3), F(6)); c.stroke(); }
  label(r, null, "ŚWIATŁO", "");
  if (lu && lu.battery) rightLabel(r, [[lu.battery, 20, C.SUB]]);
  var over = lu && lu.flash ? lu.flash : ((state === "OK" || state == null) && lu ? lu.mode : null);
  if (over) {
    text(over, X(r.l) + F(16), Y(r.t) + F(60), fit(over, F(34), X(r.r) - X(r.l) - F(48)), C.WHITE);
    var dc = state === "OK" ? "#4ADE80" : state === "SEARCHING" ? "#FF5252" : null;
    if (dc) circle(X(r.r) - F(20), Y(r.t) + F(60), F(7), dc);
    return;
  }
  var txt = "—", col = C.NONE, dot = null;
  if (state === "OK") { txt = "POŁĄCZONA"; col = C.WHITE; dot = "#4ADE80"; }
  else if (state === "SEARCHING") { txt = "BRAK"; col = "#FF8C8C"; dot = "#FF5252"; }
  else if (state === "NA") txt = "brak lampy";
  if (dot) circle(X(r.r) - F(20), Y(r.t) + F(20), F(7), dot);
  text(txt, X(r.l) + F(16), Y(r.t) + F(60), fit(txt, F(34), X(r.r) - X(r.l) - F(28)), col);
}
/* 22.10 v3: wspolny uklad kolumn ZASILANIE i CARB: rowne kolumny, podpis i liczba od tej samej krawedzi,
   jednostka na linii cyfr, opcjonalny dopisek pod spodem */
function miniCol(x, w, T, lab, dot, v, u, col, sub, ico, vs, ly, vy, sy) {
  text(lab, x, T + F(ly), F(19), C.UNIT);
  if (dot) circle(x + textW(lab, F(19)) + F(10), T + F(ly), F(6), dot);
  var vx = x;
  if (ico) { ico(vx, T + F(vy)); vx += F(48); }
  if (v == null) text("brak", vx, T + F(vy), F(26), C.NONE);
  else {
    var uw = u ? textW(u, F(20)) + F(4) : 0, sz = fit(v, F(vs), w - (vx - x) - uw - F(6));
    text(v, vx, T + F(vy), sz, col);
    if (u) text(u, vx + textW(v, sz) + F(3), T + F(vy) + (sz - F(20)) * 0.34, F(20), C.UNIT);
  }
  if (sub) text(sub, x, T + F(sy), F(20), C.SUB);
}
function cols(r, n) { var L = X(r.l), W = (X(r.r) - L) / n, out = []; for (var i = 0; i < n; i++) out.push({ x: L + W * i + F(14), w: W - F(22), sep: L + W * i }); return out; }
function colSep(x, T, t0, t1) { fbox(x - F(1), T + F(t0), x + F(1), T + F(t1), C.BG); }
/* 22.10 v4: ikony swiatel jak kontrolki na desce rozdzielczej (ISO 2575): korpus lampy "D" (luk z tylu, plaska szybka z przodu) + wiazka.
   STALE MOCNE = 4 dlugie poziome promienie (jak drogowe), STALE SLABE = 4 krotkie skosne w dol (jak mijania),
   MIGANIE = wiazka przerywana, WYLACZONA = sam obrys */
function lampIco(mode, x, cy, col) {
  var h = F(26), wB = F(14), top = cy - h / 2, xf = x + wB;
  c.beginPath(); c.moveTo(xf, top); c.lineTo(xf, top + h);
  c.bezierCurveTo(xf - wB * 1.35, top + h, xf - wB * 1.35, top, xf, top); c.closePath();
  if (mode === "OFF") { c.strokeStyle = C.NONE; c.lineWidth = F(2.5); c.stroke(); return; }
  c.fillStyle = col; c.fill();
  c.strokeStyle = col; c.lineWidth = F(3); c.lineCap = "round";
  var x0 = xf + F(5);
  [0.12, 0.37, 0.63, 0.88].forEach(function (f) {
    var y = top + h * f;
    c.beginPath();
    if (mode === "WEAK") { c.moveTo(x0, y); c.lineTo(x0 + F(12), y + F(5)); }
    else if (mode === "FLASH") { c.moveTo(x0, y); c.lineTo(x0 + F(6), y); c.moveTo(x0 + F(11), y); c.lineTo(x0 + F(17), y); }
    else { c.moveTo(x0, y); c.lineTo(x0 + F(18), y); }
    c.stroke();
  });
  c.lineCap = "butt";
}
function lampMode(t) { t = String(t || "").toUpperCase(); return /MIG/.test(t) ? "FLASH" : /S[ŁL]AB/.test(t) ? "WEAK" : /STA[ŁL]/.test(t) ? "STRONG" : /WY[ŁL]|OFF/.test(t) ? "OFF" : null; }
/* 22.10 v3: CARB (nizszy wiersz) -- trzy rowne kolumny CARB CEL | CARB SPAL. | WODA */
function drawFood(r, d) {
  cell(r);
  var T = Y(r.t), cs = cols(r, 3);
  miniCol(cs[0].x, cs[0].w, T, "CARB CEL", null, d.carbRate != null ? String(d.carbRate) : null, "g/h", C.WHITE, "", null, 44, 17, 55, 0);
  miniCol(cs[1].x, cs[1].w, T, "CARB SPAL.", null, d.carbSpent != null ? String(d.carbSpent) : null, "g", C.WHITE, "", null, 44, 17, 55, 0);
  miniCol(cs[2].x, cs[2].w, T, "WODA", null, d.fluidRate != null ? fmt1(d.fluidRate) : null, "l/h", C.WHITE, "", null, 44, 17, 55, 0);
  colSep(cs[1].sep, T, 8, 78); colSep(cs[2].sep, T, 8, 78);
}
/* 22.10 v3 pkt 11: VI i srednia kadencja -- podpis sredniej w dwoch linijkach (O nad KAD) */
function drawViKad(r, d) {
  cell(r);
  var l = X(r.l) + F(10), rr = X(r.r) - F(10), T = Y(r.t), H = Y(r.b) - T, y1 = T + H * 0.28, y2 = T + H * 0.74;
  text("VI", l, y1, F(22), C.LABEL);
  if (d.vi == null) text("brak", rr, y1, F(24), C.NONE, "right"); else text(fmt2(d.vi), rr, y1, fit(fmt2(d.vi), F(48), rr - l - F(40)), viColor(d.vi), "right");
  text("Ø", l + F(3), y2 - F(11), F(19), C.LABEL); text("KAD", l, y2 + F(11), F(19), C.LABEL);
  var kv = d.cadAvg != null ? String(d.cadAvg) : null;
  if (kv == null) text("brak", rr, y2, F(24), C.NONE, "right"); else text(kv, rr, y2, fit(kv, F(48), rr - l - F(46)), C.WHITE, "right");
  fbox(X(r.l) + F(8), T + H * 0.51 - F(1), X(r.r) - F(8), T + H * 0.51 + F(1), C.BG);
}
/* 22.10 v4 pkt 10: ZASILANIE -- kolumny nierowne: lampa 40% | Karoo 36% (duzy czas do wyczerpania, pod spodem %/h) | kamera 24% (mniej wazna, mniejsza);
   dotkniecie przelacza tryb lampy (niebieska ramka = aktywne) */
function drawPower(r, d) {
  cell(r);
  var lu = d.light, state = d.lightState, T = Y(r.t), L = X(r.l), Wt = X(r.r) - L;
  if (lu && lu.controllable) { c.strokeStyle = "#2E7BFF"; c.lineWidth = F(4); rrect(X(r.l) + F(3), Y(r.t) + F(3), X(r.r) - F(3), Y(r.b) - F(3), F(6)); c.stroke(); }
  var cam = d.camOn || d.camBat != null, fr = cam ? [0.40, 0.36, 0.24] : [0.5, 0.5], cs = [], acc = 0;
  fr.forEach(function (f) { cs.push({ x: L + Wt * acc + F(14), w: Wt * f - F(22), sep: L + Wt * acc }); acc += f; });
  var ok = lu && (state === "OK" || state == null), mode = ok ? lampMode(lu.flash || lu.mode) : null, bat = ok && lu.battery ? String(lu.battery).replace(/[^0-9]/g, "") : null;
  if (state === "SEARCHING") miniCol(cs[0].x, cs[0].w, T, "LAMPA", "#FF5252", "BRAK", "", "#FF8C8C", "", null, 40, 20, 60, 0);
  else if (!ok) miniCol(cs[0].x, cs[0].w, T, "LAMPA", null, "—", "", C.NONE, "", null, 40, 20, 60, 0);
  else miniCol(cs[0].x, cs[0].w, T, "LAMPA", "#4ADE80", bat || "—", bat ? "%" : "", C.WHITE, "", mode ? function (x, cy) { lampIco(mode, x, cy, "#FFFFFF"); } : null, 40, 20, 60, 0);
  miniCol(cs[1].x, cs[1].w, T, "KAROO", null, d.batLeftSec != null ? "~" + hm(d.batLeftSec) : null, "h", C.WHITE, d.batDrain != null ? fmt0(d.batDrain) + " %/h" : "", null, 40, 20, 60, 93);
  if (cam) { var cb = d.camBat; miniCol(cs[2].x, cs[2].w, T, "KAMERA", null, cb != null ? String(cb) : "brak", cb != null ? "%" : "", cb == null ? C.NONE : cb < 20 ? "#FF5252" : cb < 35 ? C.AMBER : C.WHITE, "", null, 30, 20, 60, 0); }
  for (var i = 1; i < cs.length; i++) colSep(cs[i].sep, T, 12, 96);
}
function drawBattery(r, d) {
  cell(r);
  var lb = label(r, [P_BATT], "BAT", ""), cx = (X(r.l) + X(r.r)) / 2, b = Y(r.b) - F(8), mid = (lb + b) / 2;
  if (d.batDrain == null) { none(cx, mid); return; }
  var v = fmt0(d.batDrain), vw = textW(v, F(46)) + F(4) + textW("%/h", F(22));
  text(v, cx - vw / 2, mid - F(10), F(46), C.WHITE); text("%/h", cx - vw / 2 + textW(v, F(46)) + F(4), mid - F(4), F(22), C.UNIT);
  if (d.batLeftSec != null) text("~" + hm(d.batLeftSec) + " h", cx, b - F(6), F(20), C.SUB, "center");
}

/* ---------------- INFO: TRASA, PRZEWYŻSZENIE, POGODA ---------------- */
function roadIcon(x, y, sz) {
  c.beginPath(); c.moveTo(x + sz * 0.31, y + sz * 0.05); c.lineTo(x + sz * 0.69, y + sz * 0.05); c.lineTo(x + sz, y + sz * 0.95); c.lineTo(x, y + sz * 0.95); c.closePath();
  var g = c.createLinearGradient(0, y, 0, y + sz); g.addColorStop(0, "#7A818C"); g.addColorStop(1, "#383D45"); c.fillStyle = g; c.fill();
  c.lineCap = "round";
  line(x + sz * 0.33, y + sz * 0.06, x + sz * 0.05, y + sz * 0.94, "#FFFFFF", sz * 0.045); line(x + sz * 0.67, y + sz * 0.06, x + sz * 0.95, y + sz * 0.94, "#FFFFFF", sz * 0.045);
  line(x + sz * 0.5, y + sz * 0.10, x + sz * 0.5, y + sz * 0.20, "#FFD43B", sz * 0.035);
  line(x + sz * 0.5, y + sz * 0.31, x + sz * 0.5, y + sz * 0.48, "#FFD43B", sz * 0.048);
  line(x + sz * 0.5, y + sz * 0.62, x + sz * 0.5, y + sz * 0.88, "#FFD43B", sz * 0.06);
  c.lineCap = "butt";
}
function emoji(e, x, cy, size) { c.font = (size * 0.92) + "px sans-serif"; c.textAlign = "left"; c.textBaseline = "middle"; c.fillStyle = "#fff"; c.fillText(e, x, cy); c.textBaseline = "alphabetic"; }
var C_ASF = "#F2F4F7", C_GRV = "#FFB300", C_BAD = "#FF2A2A";
function drawRoute(r, d) {
  cell(r); label(r, [P_ROUTE], "TRASA", "", true);
  var l = X(r.l) + F(10), rr = X(r.r) - F(10), T = Y(r.t), etaS = F(46), etaCy = T + F(30);
  if (d.etaMs != null) { var et = clock(d.etaMs); text(et, rr, etaCy, etaS, C.WHITE, "right"); text("ETA", rr - textW(et, etaS) - F(6), etaCy + F(6), F(20), C.SUB, "right"); }
  else text("ETA —", rr, etaCy, F(24), C.NONE, "right");
  var tx = l + F(100);
  if (d.twilightMs != null) { var lb = d.twilightDawn ? "świt" : "zmrok"; text(lb, tx, T + F(26), F(22), C.SUB); tx += textW(lb, F(22)) + F(6); text(clock(d.twilightMs), tx, T + F(24), F(38), C.WHITE); }   /* 22.10 pkt 13 */
  var vcy = T + F(80), x = l, done = fmt0(d.doneKm);
  text(done, x, vcy, F(58), C.WHITE); x += textW(done, F(58)) + F(8);
  var total = d.totalKm;
  if (total != null) { text("/", x, vcy + F(6), F(30), C.SUB); x += textW("/", F(30)) + F(8); var tt = fmt0(total); text(tt, x, vcy + F(6), F(40), C.WHITE); x += textW(tt, F(40)) + F(6); }
  text("km", x, vcy + F(10), F(22), C.UNIT); x += textW("km", F(22));
  var leftEnd = x;
  if (d.hasRoute && d.ahead && d.ahead.length) {
    var sum = function (col) { return d.ahead.filter(function (a) { return a[1] === col; }).reduce(function (q, a) { return q + a[0]; }, 0); };
    var parts = [["ROAD", sum(C_ASF)], ["\uD83E\uDEA8", sum(C_GRV)], ["\uD83D\uDCA9", sum(C_BAD)]];
    var k = 1, blockW = function (kk) { return parts.reduce(function (q, p) { return q + textW(fmt0(p[1]), F(36) * kk) + F(5) + F(32) * kk + F(16); }, 0) - F(16); };
    while (k > 0.7 && rr - blockW(k) < leftEnd + F(12)) k -= 0.05;
    var px = rr, ns = F(36) * k, isz = F(32) * k;
    parts.slice().reverse().forEach(function (p) {
      var v = fmt0(p[1]); text(v, px, vcy, ns, C.WHITE, "right"); px -= textW(v, ns) + F(5);
      if (p[0] === "ROAD") roadIcon(px - isz, vcy - isz / 2, isz); else emoji(p[0], px - isz, vcy, isz);
      px -= isz + F(16);
    });
  }
  var bt = T + Y(113), bb = bt + Y(34);
  fbox(l, bt, rr, bb, C.TRACK);
  if (d.hasRoute && total != null && total > 0) {
    var fx = l + (rr - l) * Math.max(0, Math.min(1, d.doneKm / total));
    fbox(l, bt, fx, bb, "#2E7BFF");
    if (d.ahead && d.ahead.length) {
      var s2 = Math.max(0.001, d.ahead.reduce(function (q, a) { return q + a[0]; }, 0)), sx2 = fx;
      d.ahead.forEach(function (a) { var ww = (rr - fx) * (a[0] / s2); fbox(sx2 + F(1), bt, sx2 + ww - F(1), bb, a[1]); sx2 += ww; });
    }
    (d.stopsKm || []).forEach(function (km) { var s0 = l + (rr - l) * Math.max(0, Math.min(1, km / total)); fbox(s0 - F(3), bt, s0 + F(3), bb, "#FF3DF5"); });
    var mr = (bb - bt) * 0.6, mx = Math.max(l + mr, Math.min(rr - mr, fx));
    circle(mx, (bt + bb) / 2, mr, C.PILL); circle(mx, (bt + bb) / 2, mr - F(3), "#39FF14");
  } else none((l + rr) / 2, (bt + bb) / 2, "brak trasy");
  var fcy = Y(r.b) - F(24), avg = d.avgGrossKmh != null ? fmt1(d.avgGrossKmh) : "—";
  text("Ø", l, fcy, F(22), C.SUB); var fx2 = l + textW("Ø", F(22)) + F(5);
  text(avg, fx2, fcy, F(38), C.WHITE); fx2 += textW(avg, F(38)) + F(4); text("km/h", fx2, fcy + F(4), F(20), C.UNIT);
  var jz = hm(d.movingSec), jw = textW("jazda ", F(22)) + textW(jz, F(38)), jx = (l + rr) / 2 - jw / 2 + F(10);
  text("jazda", jx, fcy, F(22), C.SUB); text(jz, jx + textW("jazda ", F(22)), fcy, F(38), C.WHITE);
  var st = hm(d.stopsSec); text(st, rr, fcy, F(38), C.AMBER, "right"); text("postoje", rr - textW(st, F(38)) - F(6), fcy, F(22), C.SUB, "right");
}
function drawAscent(r, d) {
  cell(r); label(r, [P_GRADE], "PRZEWYŻSZENIE", "m");
  var l = X(r.l) + F(10), rr = X(r.r) - F(10), b = Y(r.b) - F(8), t = b - F(44), dn = d.ascDone, lf = d.ascLeft;
  if (dn == null || lf == null || dn + lf <= 0) { none((l + rr) / 2, (t + b) / 2); return; }
  rightLabel(r, [["razem", 26, C.SUB], [String(dn + lf), 42, C.WHITE]]);   /* 22.10 v3 */
  var gap = F(2), gw = (rr - l - gap) * (dn / (dn + lf)), green = "#2F7D4A";
  fbox(l, t, l + gw, b, green); fbox(l + gw + gap, t, rr, b, C.TRACK);
  var cy = (t + b) / 2, sz = F(34), dT = "↑ " + dn, lT = String(lf);
  if (gw >= textW(dT, sz) + F(16)) { barText(dT, l + gw / 2, cy, sz, gw, green, "center"); barText(lT, l + gw + gap + (rr - l - gw - gap) / 2, cy, sz, rr - l - gw - gap, C.TRACK, "center"); }
  else { text(dT, l + gw + gap + F(6), cy, sz, C.WHITE); text(lT, rr - F(6), cy, sz, C.WHITE, "right"); }
}
function lerpS(xs, ys, q) {
  var n = xs.length; if (!n) return null; if (q <= xs[0]) return ys[0]; if (q >= xs[n - 1]) return ys[n - 1];
  var lo = 0, hi = n - 1; while (hi - lo > 1) { var m = (lo + hi) >> 1; if (xs[m] <= q) lo = m; else hi = m; }
  var dx = xs[hi] - xs[lo]; return dx <= 0 ? ys[lo] : ys[lo] + (ys[hi] - ys[lo]) * (q - xs[lo]) / dx;
}
function ser(wx, key) {
  var pts = wx.items.filter(function (w) { return w[key] != null; }).map(function (w) { return [wx.route ? (w.km || 0) : w.t, w[key]]; }).sort(function (a, b) { return a[0] - b[0]; });
  return { x: pts.map(function (p) { return p[0]; }), y: pts.map(function (p) { return p[1]; }) };
}
function valUnit(v, u, x, cy, vs, us, col, align) {
  var vw = textW(v, vs), uw = u ? F(3) + textW(u, us) : 0, x0 = align === "left" ? x : align === "right" ? x - vw - uw : x - (vw + uw) / 2;
  text(v, x0, cy, vs, col); if (u) text(u, x0 + vw + F(3), cy + F(3), us, C.UNIT);
}
function ylab(t, x, y, col, right) { var tw = textW(t, F(20)), x0 = right ? x - tw : x; c.fillStyle = "#14181D"; rrect(x0 - F(3), y - F(12), x0 + tw + F(3), y + F(12), F(3)); c.fill(); text(t, x0, y, F(20), col); }
function mixCol(cBase, cSide, k) { var a = hex(cSide), b = hex(cBase); return "rgb(" + [0, 1, 2].map(function (i) { return Math.max(0, Math.min(255, Math.round(a[i] + (b[i] - a[i]) * k))); }).join(",") + ")"; }
/* 22.10 pkt 12: wykresy pogody schodkami (10 odcinkow) zamiast plynnej linii */
var NB = 10;
function buckets(samples, key) {
  var n = samples.length - 1, out = [];
  for (var b = 0; b < NB; b++) {
    var i0 = Math.round(b * n / NB), i1 = Math.round((b + 1) * n / NB), sum = 0, k = 0;
    for (var i = i0; i <= i1; i++) { var v = samples[i][key]; if (v != null) { sum += v; k++; } }
    out.push({ x0: samples[i0].x, x1: samples[i1].x, v: k ? sum / k : null, t0: samples[i0].tMin });
  }
  return out;
}
function stepPath(samples, key, toY) {
  var first = true;
  buckets(samples, key).forEach(function (b) { if (b.v == null) return; var y = toY(b.v); if (first) { c.moveTo(b.x0, y); first = false; } else c.lineTo(b.x0, y); c.lineTo(b.x1, y); });
}
function drawWeather(r, d, wx, scale, nowMs, dawnMs, duskMs) {
  cell(r);
  var oy = r.t - 2, yy = function (v) { return Y(oy + v); }   /* 22.10 pkt 12: wykresy nizsze -> os X wyzej, wolny pas na dole */, route = wx ? wx.route : d.hasRoute;
  text("POGODA", X(10), yy(23), F(24), C.LABEL);
  var subTxt = route ? "na trasie" : "kolejne godziny";
  text(subTxt, X(10) + textW("POGODA", F(24)) + F(8), yy(25), F(18), C.UNIT);
  if (wx) {
    var age = wx.ageMin + (nowMs - wx.fetchedMs) / 60000, bcol = age > 30 ? "#F2C230" : wx.live ? "#39FF14" : "#F2F4F7", btx = "Q " + Math.round(age) + "′";
    var bx = X(10) + textW("POGODA", F(24)) + F(8) + textW(subTxt, F(18)) + F(10);
    c.fillStyle = bcol; rrect(bx, yy(11), bx + textW(btx, F(18)) + F(12), yy(35), F(4)); c.fill(); text(btx, bx + F(6), yy(23), F(18), "#111315");
  }
  var labs = route ? ["20 km", "50 km", "całość"] : ["1 h", "3 h", "całość"], rx = X(470);
  for (var i = 2; i >= 0; i--) {
    var t = labs[i], tw = textW(t, F(20));
    if (i === scale) { c.fillStyle = "#F2F4F7"; rrect(rx - tw - F(16), yy(9), rx, yy(37), F(4)); c.fill(); text(t, rx - tw - F(8), yy(23), F(20), "#111315"); }
    else text(t, rx - tw - F(4), yy(23), F(20), C.UNIT);
    rx -= tw + F(22);
  }
  var items = wx ? wx.items : [];
  if (!items.length) { none(X(240), yy(230), "pogoda: czekam na QBota"); return; }
  var since = (nowMs - wx.fetchedMs) / 60000, X0 = X(10), X1 = X(470), XN = X0 + F(38), W = X1 - XN, kmNow = d.doneKm, n = 80, samples = [], spanKm, spanMin;
  var S = { t: ser(wx, "t"), feels: ser(wx, "feels"), mm: ser(wx, "mm"), prob: ser(wx, "prob"), head: ser(wx, "head"), gust: ser(wx, "gust"), ws: ser(wx, "ws") };
  var L = function (k, q) { return lerpS(S[k].x, S[k].y, q); };
  if (route) {
    var lastKm = items[items.length - 1].km != null ? items[items.length - 1].km : kmNow, rest = Math.max(1, (d.totalKm != null ? d.totalKm : lastKm) - kmNow);
    spanKm = Math.min([20, 50, rest][scale], Math.max(1, rest));
    for (var j = 0; j <= n; j++) { var f = j / n, km = kmNow + spanKm * f; samples.push({ x: XN + W * f, tMin: (L("t", km) || 0) - since, km: km, feels: L("feels", km), mm: L("mm", km) || 0, prob: L("prob", km), head: L("head", km), gust: L("gust", km), ws: L("ws", km) }); }
    spanMin = Math.max(1, samples[n].tMin - samples[0].tMin);
  } else {
    spanKm = 0; spanMin = [60, 180, 360][scale];
    for (var j2 = 0; j2 <= n; j2++) { var f2 = j2 / n, tm = spanMin * f2, q = tm + since;                 samples.push({ x: XN + W * f2, tMin: tm, km: 0, feels: L("feels", q), mm: L("mm", q) || 0, prob: L("prob", q), head: L("head", q), gust: L("gust", q), ws: L("ws", q) }); }
  }
  var t0 = samples[0].tMin, showRain = samples.some(function (sm) { return sm.mm >= 0.1 || (sm.prob || 0) >= 30; });
  var clockAt = function (tMin) { return clock(nowMs + tMin * 60000); };
  var PT = yy(86), PB = yy(398);
  var isNight = function (tMin) { var ms = nowMs + tMin * 60000; if (dawnMs == null || duskMs == null) return false; return ms < dawnMs || (ms > duskMs && ms < dawnMs + 86400000); };
  var ns = null; c.globalAlpha = 150 / 255;
  samples.forEach(function (sm, ii) { var nt = isNight(sm.tMin); if (nt && ns == null) ns = sm.x; if ((!nt || ii === n) && ns != null) { fbox(ns, PT, sm.x, PB, "#1C2B4A"); ns = null; } });
  c.globalAlpha = 1;
  // temperatura
  text("TEMPERATURA", X(16), yy(58), F(24), C.LABEL); text("odcz. °C", X(16) + textW("TEMPERATURA", F(24)) + F(6), yy(60), F(20), C.UNIT);
  var TT = yy(98), TB = yy(showRain ? 170 : 212), fs = samples.filter(function (sm) { return sm.feels != null; }).map(function (sm) { return sm.feels; }), lo = 0, hi = 1;
  var ty = function (v) { return TB - (v - lo) / (hi - lo) * (TB - TT); };
  if (fs.length) {
    lo = Math.floor(Math.min.apply(null, fs)) - 1; hi = Math.ceil(Math.max.apply(null, fs)) + 1;
    var tl = [hi, (lo + hi) / 2, lo];
    tl.forEach(function (v) { line(X0, ty(v), X1, ty(v), "#2A3341", F(1.5)); });
    c.beginPath(); stepPath(samples, "feels", ty);
    c.lineJoin = "round"; c.strokeStyle = "#000"; c.lineWidth = F(11); c.stroke(); c.strokeStyle = "#FF8A00"; c.lineWidth = F(6.5); c.stroke();
    tl.forEach(function (v) { ylab(Math.round(v) + "°", X(14), ty(v), C.SUB); });
    var minS = null; samples.forEach(function (sm) { if (sm.feels != null && (minS == null || sm.feels < minS.feels)) minS = sm; });
    var idx = samples.indexOf(minS), where = route ? "km " + Math.round(minS.km) : "o " + clockAt(minS.tMin);
    text("min " + Math.round(minS.feels) + "° · " + where, X1, yy(60), F(22), C.SUB, "right");
    var lab = function (sm, al) { if (sm.feels == null) return; var y = ty(sm.feels); text(Math.round(sm.feels) + "°", sm.x + (al === "left" ? F(48) : al === "right" ? -F(48) : 0), y < TT + F(34) ? y + F(24) : y - F(22), F(26), C.WHITE, al); };
    lab(samples[0], "left"); lab(samples[n], "right");
    if (idx >= 9 && idx < n - 8) { circle(minS.x, ty(minS.feels), F(9), "#111315"); circle(minS.x, ty(minS.feels), F(6.5), "#FACC15"); lab(minS, "center"); }
  } else none(X(240), (TT + TB) / 2, "brak");
  var RT = yy(224), RB = yy(280), rMax = Math.max(2, Math.ceil(Math.max.apply(null, samples.map(function (sm) { return sm.mm; }))));
  if (showRain) {
    text("OPAD", X(16), yy(196), F(24), C.LABEL); text("mm/h", X(16) + textW("OPAD", F(24)) + F(6), yy(198), F(20), C.UNIT);
    var radarUntil = wx.radarUntilMin != null ? wx.radarUntilMin - since : null;
    if (radarUntil != null && radarUntil > 0) text("· radar " + Math.round(radarUntil) + "′", X(16) + textW("OPAD", F(24)) + textW("mm/h", F(20)) + F(14), yy(198), F(20), "#9CC7FF");
    line(X0, RT, X1, RT, "#2A3341", F(1.5)); line(X0, (RT + RB) / 2, X1, (RT + RB) / 2, "#2A3341", F(1.5));
    var bwid = W / (n + 1);
    buckets(samples, "mm").forEach(function (bk) { if (bk.v != null && bk.v > 0.05) fbox(bk.x0 + F(2), RB - Math.min(bk.v, rMax) / rMax * (RB - RT), bk.x1 - F(2), RB, (radarUntil != null && bk.t0 <= radarUntil) ? "#7FB2FF" : "#2E7BFF"); });
    line(X0, RB, X1, RB, "#465366", F(2));
    c.beginPath(); stepPath(samples, "prob", function (v) { return RB - v / 100 * (RB - RT); });
    c.strokeStyle = "#7FDBFF"; c.lineWidth = F(2.5); c.stroke();
    ylab(String(rMax), X(14), RT, C.SUB); ylab("0", X(14), RB, C.SUB); ylab("szansa 100%", X(466), RT, "#7FDBFF", true);   /* 22.10 v4: linia = szansa opadu */ ylab("0", X(466), RB, "#7FDBFF", true);
    var fr = samples.filter(function (sm) { return sm.mm >= 0.3; })[0];
    if (fr) text("deszcz za " + hmm(Math.max(0, fr.tMin)) + (route ? " · km " + Math.round(fr.km) : " · " + clockAt(fr.tMin)), X1, yy(198), F(22), "#7FDBFF", "right");
    else text("bez opadu", X1, yy(198), F(22), C.SUB, "right");
  }
  // wiatr
  var dw = showRain ? 0 : -66;
  text("WIATR", X(16), yy(306 + dw), F(24), C.LABEL); text("m/s", X(16) + textW("WIATR", F(24)) + F(6), yy(308 + dw), F(20), C.UNIT);
  var WT = yy(showRain ? 334 : 282), Y0 = yy(showRain ? 364 : 338);
  var hs = route ? samples.filter(function (sm) { return sm.head != null; }).map(function (sm) { return sm.head; }) : [];
  var wsv = route ? [] : samples.filter(function (sm) { return sm.ws != null; }).map(function (sm) { return sm.ws; });
  var wmax = route
    ? Math.max(4, Math.ceil(hs.length ? Math.max.apply(null, hs.map(Math.abs)) : 0))
    : Math.max(4, Math.ceil(wsv.length ? Math.max.apply(null, wsv) : 0)) / 2;
  var ky = (Y0 - WT) / wmax;
  line(X0, Y0 - wmax * ky, X1, Y0 - wmax * ky, "#2A3341", F(1.5)); line(X0, Y0 + wmax * ky, X1, Y0 + wmax * ky, "#2A3341", F(1.5));
  if (hs.length) {
    buckets(samples, "head").forEach(function (bk) {
      var v = bk.v; if (v == null || Math.abs(v) < 0.05) return;
      var k2 = Math.min(1, Math.abs(v) / wmax), col = v > 0 ? mixCol("#FF3B30", "#F29BC4", k2) : mixCol("#34C759", "#F3D3E2", k2);
      fbox(bk.x0 + F(1), v > 0 ? Y0 - v * ky : Y0, bk.x1 - F(1), v > 0 ? Y0 : Y0 - v * ky, col);
    });
    var mxh = Math.max.apply(null, hs);
            text([mxh > 0.5 ? "maks. czołowy " + Math.round(mxh) : null, samples[0].gust != null ? "porywy teraz " + Math.round(samples[0].gust) : null].filter(Boolean).join(" · "), X1, yy(308 + dw), F(22), C.SUB, "right");   /* 22.10 v4: bez maks. w plecy */
  }
  if (route) {
    line(X0, Y0, X1, Y0, "#C9D2DC", F(1.5));
    ylab("+" + wmax, X(14), Y0 - wmax * ky, "#F0A6CF"); ylab("−" + wmax, X(14), Y0 + wmax * ky, "#8FD18A");
  } else if (wsv.length) {
    var YB = Y0 + wmax * ky, topV = 2 * wmax;
    buckets(samples, "ws").forEach(function (bk) { if (bk.v != null && bk.v > 0.05) fbox(bk.x0 + F(1), YB - bk.v * ky, bk.x1 - F(1), YB, "#2E5F8F"); });
    c.beginPath(); stepPath(samples, "ws", function (v) { return YB - v * ky; });
    c.lineJoin = "miter"; c.strokeStyle = "#000"; c.lineWidth = F(8); c.stroke(); c.strokeStyle = "#9CC7FF"; c.lineWidth = F(4.5); c.stroke();
    line(X0, YB, X1, YB, "#C9D2DC", F(1.5));
    ylab(String(Math.round(topV)), X(14), Y0 - wmax * ky, C.SUB); ylab("0", X(14), YB, C.SUB);
    var mxS = samples.filter(function (sm) { return sm.ws != null; }).reduce(function (a, b) { return b.ws > a.ws ? b : a; }, samples.filter(function (sm) { return sm.ws != null; })[0]);
    text("teraz " + Math.round(samples[0].ws || 0) + (mxS ? " · maks. " + Math.round(mxS.ws) + " o " + clockAt(mxS.tMin) : "") + (samples[0].gust != null ? " · porywy " + Math.round(samples[0].gust) : ""), X1, yy(308 + dw), F(22), C.SUB, "right");
  }
  // oś X
  var ticks = [{ x: XN, top: "teraz", u: "", bot: clockAt(t0) }];
  if (route) {
    var pxKm = W / spanKm, stp = [5, 10, 20, 25, 50].filter(function (v) { return v * pxKm >= F(90); })[0] || 50, k = Math.ceil((kmNow + 0.01) / stp) * stp;
    while (k <= kmNow + spanKm + 0.01) { var nearest = samples.reduce(function (a, b) { return Math.abs(b.km - k) < Math.abs(a.km - k) ? b : a; }); ticks.push({ x: XN + W * (k - kmNow) / spanKm, top: String(Math.floor(k)), u: "km", bot: clockAt(nearest.tMin) }); k += stp; }
    if (scale === 2) ticks.push({ x: X1, top: String(Math.round(kmNow + spanKm)), u: "km", bot: "meta " + clockAt(samples[n].tMin), end: true });
  } else {
    var pxMin = W / spanMin, stm = [15, 30, 60, 120, 180].filter(function (v) { return v * pxMin >= F(90); })[0] || 180;
    var nd = new Date(nowMs), nowMin = nd.getHours() * 60 + nd.getMinutes(), mm = Math.ceil((nowMin + 1) / stm) * stm;
    while (mm - nowMin <= spanMin + 0.01) { var rel = mm - nowMin; ticks.push({ x: XN + W * rel / spanMin, top: clockAt(rel), u: "", bot: "+" + hmm(rel) }); mm += stm; }
  }
  var endT = ticks.filter(function (t2) { return t2.end; })[0], keep = [ticks[0]];
  ticks.slice(1).forEach(function (t2) { if (!t2.end && t2.x - XN >= F(150) && !(endT && endT.x - t2.x < F(150))) keep.push(t2); });
  if (keep.length > 2) { var lt = keep[keep.length - 1], pv = keep[keep.length - 2]; if (X1 - lt.x < F(30) && lt.x - pv.x < F(130)) keep.pop(); }
  if (endT) keep.push(endT);
  var sunTicks = [];
  [[dawnMs, "świt"], [duskMs, "zmrok"]].forEach(function (ev) {
    if (ev[0] == null) return;
    [ev[0], ev[0] + 86400000].forEach(function (e) {
      var rel = (e - nowMs) / 60000; if (rel <= t0 || rel > samples[n].tMin) return;
      var x = route ? samples.reduce(function (a, b) { return Math.abs(b.tMin - rel) < Math.abs(a.tMin - rel) ? b : a; }).x : XN + W * rel / spanMin;
      c.setLineDash([F(4), F(5)]); line(x, PT, x, PB, "#6B7685", F(2)); c.setLineDash([]);
      if (x - XN >= F(110) && !(endT && endT.x - x < F(110))) sunTicks.push({ x: x, top: ev[1], bot: clock(e) });
    });
  });
  sunTicks.forEach(function (st) { keep = keep.filter(function (t2, ix) { return t2.end || ix === 0 || Math.abs(t2.x - st.x) >= F(100); }); });
  keep.forEach(function (t2) { line(t2.x, TT - F(6), t2.x, TB, "#2A3341", F(1.5)); if (showRain) line(t2.x, RT - F(4), t2.x, RB, "#2A3341", F(1.5)); line(t2.x, WT - F(4), t2.x, Y0 + wmax * ky, "#2A3341", F(1.5)); });
  keep.forEach(function (t2, ix) {
    var al = ix === 0 ? "left" : t2.x > X1 - F(30) ? "right" : "center", xx = ix === 0 ? X0 + F(4) : t2.x;
    valUnit(t2.top, t2.u, xx, yy(416), F(32), F(22), C.WHITE, al); text(t2.bot, xx, yy(448), F(22), C.UNIT, al);
  });
  var nowDot = function (y) { circle(XN, y, F(9), "#111315"); circle(XN, y, F(6.5), "#39FF14"); };
  if (samples[0].feels != null && fs.length) nowDot(ty(samples[0].feels));
  if (showRain) nowDot(RB - Math.min(samples[0].mm, rMax) / rMax * (RB - RT));
  nowDot(route ? Y0 - (samples[0].head || 0) * ky : Y0 + wmax * ky - (samples[0].ws || 0) * ky);
  sunTicks.forEach(function (t2) { var al = t2.x > X1 - F(40) ? "right" : "center"; text(t2.top, t2.x, yy(416), F(22), C.SUB, al); text(t2.bot, t2.x, yy(448), F(20), C.SUB, al); });
}

/* ---------------- wejście ---------------- */
function prep(cv, W, H) {
  var dpr = Math.max(1, window.devicePixelRatio || 1);
  cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); cv.style.width = W + "px"; cv.style.height = H + "px";
  c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
  sx = W / BW; sy = H / BH; s = Math.min(sx, sy);
  fbox(0, 0, W, H, C.BG);
}
function stats(cv, W, H, d) {
  prep(cv, W, H);
  /* 22.10 (projekt 0.4.27): VI+KAD w 1. rzedzie | PLAN CZASU na cala szerokosc | BRAMA + ZASILANIE | CARB + woda na calej szerokosci */
  var g = 2, rows = [113, 136, 100, 86, 120, 108], y = 0, col3 = (BW - 2 * g) / 3;
  drawNp(R(0, y, col3, y + rows[0]), d);
  drawIf(R(col3 + g, y, 2 * col3 + g, y + rows[0]), d.ifv);
  drawViKad(R(2 * col3 + 2 * g, y, BW, y + rows[0]), d);
  y += rows[0] + g;
  drawWindows(R(0, y, BW, y + rows[1]), d); y += rows[1] + g;
  drawRsrv(R(0, y, col3, y + rows[2]), d.rsrv);
  drawXss(R(col3 + g, y, 2 * col3 + g, y + rows[2]), d);
  valueCell(R(2 * col3 + 2 * g, y, BW, y + rows[2]), [P_FLAME], "KCAL", "", d.kcal != null ? String(d.kcal) : null, 62, C.WHITE);
  y += rows[2] + g;
  drawPlan(R(0, y, BW, y + rows[3]), d); y += rows[3] + g;
  drawTempo(R(0, y, BW, y + rows[4]), d); y += rows[4] + g;
  var wGate = (BW - g) * 0.34;
  drawBrama(R(0, y, wGate, y + rows[5]), d.gate);
  drawPower(R(wGate + g, y, BW, y + rows[5]), d);
  y += rows[5] + g;
  drawFood(R(0, y, BW, BH), d);
}
function info(cv, W, H, d, wx, scale, nowMs, dawnMs, duskMs) {
  prep(cv, W, H);
  drawRoute(R(0, 0, BW, 201), d);
  drawAscent(R(0, 203, BW, 295), d);
  drawWeather(R(0, 297, BW, BH), d, wx, scale, nowMs, dawnMs, duskMs);
}
window.QST = { stats: stats, info: info };
})();
