/* qext2-kokpit2.js (2026-10-18) — pola KOKPIT 2 (nav + instr) QExt2 narysowane na <canvas> dla makiety w QBocie.
   ŹRÓDŁO PRAWDY: /opt/qbot/qext2_deploy/app/src/main/kotlin/com/qext2/primary/kokpit/Kokpit2.kt
   (Kokpit2NavRenderer, Kokpit2InstRenderer; stan pliku 18.10.2026) przeniesione 1:1: siatka 474×126, skala min(H/126, W/474),
   te same współrzędne, kolory, wzorce szerokości, progi Kokpit2Config (wartości domyślne), czcionki Saira Semi Condensed
   z assets QExt2 (/fonts/). Zmieniasz wygląd pola w QExt2 → popraw też tutaj.
   API: QK2.ready (Promise czcionek), QK2.nav(canvas, W, H, d, cfg), QK2.instr(canvas, W, H, d, cfg). */
(function () {
"use strict";
var CAP = 0.688;
var REG = "'Roboto Condensed','Arial Narrow',sans-serif";
var FONTS_OK = false;
var ready = (function () {
  if (!window.FontFace) return Promise.resolve();
  var a = new FontFace("QSairaSemi", "url(/fonts/SairaSemiCondensed-SemiBold.ttf)", { weight: "600" });
  var b = new FontFace("QSairaBold", "url(/fonts/SairaSemiCondensed-Bold.ttf)", { weight: "700" });
  return Promise.all([a.load(), b.load()]).then(function (f) { f.forEach(function (x) { document.fonts.add(x); }); FONTS_OK = true; })
    .catch(function () {});
})();

/* ---------- pędzel: odpowiednik Paint (textScaleX, letterSpacing, heavy = Bold) ---------- */
function P(ctx) { this.c = ctx; this.sx = 1; this.ls = 0; this.heavy = false; }
P.prototype.font = function (b, size) {
  if (this.heavy) return "700 " + size + "px QSairaBold, " + REG;
  return b ? "600 " + size + "px QSairaSemi, " + REG : "400 " + size + "px " + REG;
};
P.prototype.w = function (s, size, b) {
  if (b === undefined) b = true;
  this.c.font = this.font(b, size);
  return this.c.measureText(s).width * this.sx + this.ls * size * s.length;
};
P.prototype.t = function (s, x, base, size, color, b, align) {
  if (b === undefined) b = true;
  var c = this.c, tw = this.w(s, size, b);
  var x0 = align === "right" ? x - tw : align === "center" ? x - tw / 2 : x;
  c.save(); c.font = this.font(b, size); c.fillStyle = color; c.textAlign = "left"; c.textBaseline = "alphabetic";
  c.translate(x0, base); c.scale(this.sx, 1);
  if (!this.ls) c.fillText(s, 0, 0);
  else { var cx = 0; for (var i = 0; i < s.length; i++) { c.fillText(s[i], cx, 0); cx += c.measureText(s[i]).width + this.ls * size / this.sx; } }
  c.restore();
};
function fill(c, col) { c.fillStyle = col; c.fill(); }
function path(c, pts) { c.beginPath(); c.moveTo(pts[0], pts[1]); for (var i = 2; i < pts.length; i += 2) c.lineTo(pts[i], pts[i + 1]); c.closePath(); }
function f1(v) { return (Math.round(v * 10) / 10).toFixed(1); }
function clock(ms) { var d = new Date(ms); return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2); }
function rrect(c, l, t, r, b, rad) { c.beginPath(); if (c.roundRect) c.roundRect(l, t, r - l, b - t, rad); else c.rect(l, t, r - l, b - t); }
/* 22.10 projekt 0.4.27: warianty z symulatora (window.QV); w tescie dymnym (node) brak QV -> domyslny */
function qv(k, d) { return (typeof window !== "undefined" && window.QV) ? window.QV(k, d) : d; }
function hexLum(col) { var n = parseInt(String(col).slice(1), 16); if (isNaN(n)) return 0; var a = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(function (v) { var x = v / 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }); return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2]; }
var SPEED_COL = { zolty: "#F2C230", cyjan: "#67E8F9", bialy: "#FFFFFF" };

/* ============================== dolne pole: instr ============================== */
var I = { BG: "#14181D", UNIT: "#9AA5B1", NONE: "#9AA3AE", DIV: "#2A3038", TRACK: "#465366", DONE: "#2E7BFF", STOP: "#FF3DF5",
  POS: "#39FF14", GOOD: "#4ADE80", BAD: "#FF8C8C", SUB: "#C9D2DC", YEL: "#FACC15", ORANGE: "#FB923C", SPEED: "#F2C230", WHITE: "#FFFFFF", BLACK: "#000000" };
var DEC = 0.55, ZSX = 0.8;
var PZ = [[0.00, "#9AA3AE"], [0.55, "#6FA8FF"], [0.75, "#22C55E"], [0.90, "#EAB308"], [1.05, "#F97316"], [1.20, "#EF4444"]];
function trendCol(v) { return v > 0 ? I.GOOD : v < 0 ? I.BAD : I.SUB; }

function routeBar(c, rb, l, r, top, bot, vw) {
  c.fillStyle = I.TRACK; c.fillRect(l, top, r - l, bot - top);
  var total = rb.totalKm; if (!total || total <= 0) return;
  var frac = Math.min(1, Math.max(0, rb.doneKm / total)), fx = l + (r - l) * frac;
  c.fillStyle = I.DONE; c.fillRect(l, top, fx - l, bot - top);
  var ahead = rb.ahead;
  if (ahead && ahead.length) {
    var sum = Math.max(0.001, ahead.reduce(function (a, x) { return a + x[0]; }, 0)), x = fx;
    ahead.forEach(function (a) { var ww = (r - fx) * (a[0] / sum); c.fillStyle = a[1]; c.fillRect(x + 0.5, top, ww - 1, bot - top); x += ww; });
  }
  (rb.stopsKm || []).forEach(function (km) { var sx = l + (r - l) * Math.min(1, Math.max(0, km / total)); c.fillStyle = I.STOP; c.fillRect(sx - 2.5, top, 5, bot - top); });
  var mx = Math.min(vw - 10, Math.max(10, fx)), my = (top + bot) / 2;
  c.beginPath(); c.arc(mx, my, 9, 0, 2 * Math.PI); c.fillStyle = I.POS; c.fill(); c.lineWidth = 2; c.strokeStyle = I.BLACK; c.stroke();
}
function heart(c, x, y, wd, color) {
  var k = wd / 38; c.beginPath();
  c.moveTo(x + 19 * k, y + 33 * k); c.lineTo(x + 5 * k, y + 18 * k);
  c.bezierCurveTo(x - 1 * k, y + 11 * k, x + 3 * k, y + 2 * k, x + 10 * k, y + 2 * k);
  c.bezierCurveTo(x + 14 * k, y + 2 * k, x + 17 * k, y + 5 * k, x + 19 * k, y + 8 * k);
  c.bezierCurveTo(x + 21 * k, y + 5 * k, x + 24 * k, y + 2 * k, x + 28 * k, y + 2 * k);
  c.bezierCurveTo(x + 35 * k, y + 2 * k, x + 39 * k, y + 11 * k, x + 33 * k, y + 18 * k);
  c.closePath(); fill(c, color);
}
function avgSym(c, x, y, sz, color) {
  c.strokeStyle = color; c.lineWidth = sz * 0.16; c.lineCap = "butt";
  c.beginPath(); c.arc(x + sz / 2, y + sz / 2, sz * 0.325, 0, 2 * Math.PI); c.stroke();
  c.beginPath(); c.moveTo(x + sz * 0.15, y + sz * 0.85); c.lineTo(x + sz * 0.85, y + sz * 0.15); c.stroke();
}
function bolt(c, x, y, h, color) { var k = h / 22; path(c, [x + 8 * k, y, x, y + 13 * k, x + 6 * k, y + 13 * k, x + 4 * k, y + 22 * k, x + 14 * k, y + 8 * k, x + 8 * k, y + 8 * k]); fill(c, color); }
function unitWWidth(p, zone) { var bh = 33; return bh * 14 / 22 - 1 + (zone != null ? p.w(String(zone + 1), bh / CAP) * ZSX : 0); }
function unitW(c, p, left, top, base, zone) {
  var bh = 33, zc = zone != null ? PZ[zone][1] : I.UNIT;
  bolt(c, left, top, bh, zc);
  if (zone != null) { p.sx = ZSX; p.t(String(zone + 1), left + bh * 14 / 22 - 1, top + bh, bh / CAP, zc); p.sx = 1; }
  p.t("W", left + unitWWidth(p, zone), base, 17, I.UNIT, false, "right");
}

function instrDraw(c, p, d, vw, ext, cfg) {
  var cx = vw / 2, base = 123 + ext, g = 9, lx0 = 6, rx = vw - 4;
  if (d.route) routeBar(c, d.route, 8, vw - 8, 6, 18, vw);
  c.fillStyle = I.DIV; c.fillRect(cx - 1, 24, 2, 126 + ext - 24);
  var capTop = 27, big = 52, bigBase = capTop + big * CAP;
  var z = d.hrZone, showZone = cfg.hr === "zone" && z != null;
  var hrTxt = showZone ? "Z" + z : (d.hr != null ? String(d.hr) : "—");
  var hrCol = (d.hr == null && !showZone) ? I.NONE : z === 5 ? I.BAD : z === 4 ? I.YEL : I.WHITE;
  var heartCol = d.hrDriftLevel === 2 ? I.BAD : d.hrDriftLevel === 1 ? I.ORANGE : I.WHITE;
  heart(c, lx0, capTop + (big * CAP - 20) / 2, 22, heartCol);
  p.t(hrTxt, lx0 + 26, bigBase, big, hrCol);
  var cv = d.cadence != null ? String(d.cadence) : "—";
  p.t(cv, rx, bigBase, big, d.cadence != null ? I.WHITE : I.NONE, true, "right");
  p.t("KAD", rx - p.w(cv, big) - 5, capTop + 15 * CAP, 15, I.UNIT, false, "right");
  /* 22.10: NP 5 i srednia wieksze (40 -> 46); podpisy NP 5 / znak sredniej i trojkaty przyspawane do pola
     (stale miejsce wg wzorca 888 / 88.8), nie do krawedzi biezacej liczby */
  var ref = 46, refBase = capTop + ref * CAP;
  var npTxt = d.cpe5W != null ? String(Math.round(d.cpe5W)) : "—";
  p.t(npTxt, cx - g, refBase, ref, d.cpe5W != null ? I.WHITE : I.NONE, true, "right");
  var ls = 19, lc = trendCol(d.cpTrend), lw = p.w("NP", ls, false), lRight = cx - g - Math.max(p.w(npTxt, ref), p.w("288", ref)) - 2;   /* 22.10 v3: blizej liczby, wzorzec 288 */
  p.t("NP", lRight, capTop + ls * CAP, ls, lc, false, "right");
  p.t("5", lRight - lw / 2, capTop + ls * CAP + ls * 0.85, ls, lc, false, "center");
  if (d.cpTrend) {
    var aw = 14, ah = 16, ax = lRight - lw - 4 - aw, ay = refBase - ref * CAP / 2 - ah / 2;
    if (d.cpTrend > 0) path(c, [ax + aw / 2, ay, ax + aw, ay + ah, ax, ay + ah]); else path(c, [ax, ay, ax + aw, ay, ax + aw / 2, ay + ah]);
    fill(c, lc);
  }
  var avTxt = d.avgSpeedKmh != null ? f1(d.avgSpeedKmh) : "—";
  p.t(avTxt, cx + g, refBase, ref, d.avgSpeedKmh != null ? I.WHITE : I.NONE);
  var sym = 24, sx0 = cx + g + Math.max(p.w(avTxt, ref), p.w("28.8", ref)) + 2, sy0 = refBase - ref * CAP / 2 - sym / 2;
  avgSym(c, sx0, sy0, sym, d.avgSpeedTrend === 0 ? I.SUB : trendCol(d.avgSpeedTrend));
  if (d.avgSpeedTrend) {
    var ax2 = sx0 + sym + 3, aw2 = 14, ah2 = 16, ay2 = sy0 + (sym - ah2) / 2;
    if (d.avgSpeedTrend > 0) path(c, [ax2 + aw2 / 2, ay2, ax2 + aw2, ay2 + ah2, ax2, ay2 + ah2]); else path(c, [ax2, ay2, ax2 + aw2, ay2, ax2 + aw2 / 2, ay2 + ah2]);
    fill(c, trendCol(d.avgSpeedTrend));
  }
  var wb = d.wbalPct, wTxt = wb != null ? String(wb) : "—";
  var wCol = wb == null ? I.NONE : cfg.wbal === "level" ? (wb > 50 ? I.WHITE : wb >= 20 ? I.YEL : I.BAD)
    : d.wbalTrend === "rising" ? I.GOOD : (d.wbalTrend === "falling" || d.wbalTrend === "plummeting") ? I.BAD : I.WHITE;
  (function () { var ww = p.w(wTxt, 52), r2 = p.w("88", 52); if (ww > r2) p.sx = r2 / ww; p.t(wTxt, lx0, base, 52, wCol); p.sx = 1; })();
  p.t("W′%", lx0, base - 52 * CAP - 7, 16, I.UNIT, false);
  p.t("BIEG", rx, base - 52 * CAP - 5, 15, I.UNIT, false, "right");
  if (d.gearFront != null && d.gearRear != null) {
    var x = rx, r1 = String(d.gearRear);
    p.t(r1, x, base, 52, I.WHITE, true, "right"); x -= p.w(r1, 52);
    p.t("×", x, base, 20, I.UNIT, true, "right"); x -= p.w("×", 20);
    p.t(String(d.gearFront), x, base, 36, "#AEB8C4", true, "right");
  } else p.t("—", rx, base, 52, I.NONE, true, "right");
  var v10 = d.speedKmh != null ? Math.round(d.speedKmh * 10) : null;
  var sInt = v10 != null ? String(Math.floor(v10 / 10)) : "—", sDec = v10 != null ? "." + (v10 % 10) : "";
  var pv = d.powerW != null ? String(d.powerW) : "—";
  var zone = null;
  if (d.powerW != null && d.cpW > 0) { var r = d.powerW / d.cpW; zone = 0; for (var kk = 0; kk < PZ.length; kk++) if (r >= PZ[kk][0]) zone = kk; }
  var uWRef = unitWWidth(p, 5);
  var wRightRef = lx0 + Math.max(p.w("88", 52), p.w("W′%", 16, false));
  var gearLeftRef = rx - p.w("52", 52) - p.w("×", 20) - p.w("52", 36);
  var xUnitW = wRightRef + 4, xUnitV = gearLeftRef - 2 - p.w("V", 22);
  p.heavy = true;
  var digVRef = function (sz) { return p.w("88", sz) + p.w(".8", sz * DEC); };
  var availW = (cx - g) - (xUnitW + uWRef + 4), availV = (xUnitV - 4) - (cx + g);
  var vs = (base - (capTop + big * CAP) - 3) / CAP;
  while (vs > 44 && Math.min(availV / digVRef(vs), availW / p.w("888", vs)) < 0.80) vs -= 1;
  vs += 10;
  var sxV0 = Math.max(0.70, Math.min(1, availV / digVRef(vs))), sxW0 = Math.max(0.70, Math.min(1, availW / p.w("888", vs)));
  var digV = function (sz) { return p.w(sInt, sz) + (sDec ? p.w(sDec, sz * DEC) : 0); };
  var sxV = Math.max(0.6, Math.min(sxV0, availV / digV(vs))), sxW = Math.max(0.6, Math.min(sxW0, availW / p.w(pv, vs)));
  var lsW = (sxW0 >= 1 && sxW >= sxW0) ? Math.min(0.10, Math.max(0, (availW - p.w("888", vs)) / (3 * vs))) : 0;
  var lsV = (sxV0 >= 1 && sxV >= sxV0) ? Math.min(0.10, Math.max(0, (availV - digVRef(vs)) / (3 * vs))) : 0;
  var top = base - vs * CAP;
  var pCol = d.powerW == null ? I.NONE : (cfg.power === "zones" && zone != null) ? PZ[zone][1] : d.powerColor;
  var spCol = d.speedKmh == null ? I.NONE : cfg.speed === "white" ? I.WHITE : (SPEED_COL[qv("predkosc", "cyjan")] || I.SPEED);   /* 22.10 pkt 5 */
  p.sx = sxW; p.ls = lsW;
  if (d.powerBg && d.powerW != null) { var pw0 = p.w(pv, vs); c.fillStyle = d.powerBg; rrect(c, cx - g - pw0 - 5, top - 5, cx - g + 4, base + 4, 8); c.fill(); }
  p.t(pv, cx - g, base, vs, pCol, true, "right");
  p.sx = sxV; p.ls = lsV;
  var xx = cx + g;
  p.t(sInt, xx, base, vs, spCol); xx += p.w(sInt, vs);
  if (sDec) { var ds = vs * DEC; p.t(sDec, xx, top + ds * CAP, ds, spCol); }
  p.sx = 1; p.ls = 0; p.heavy = false;
  unitW(c, p, xUnitW, top, base, zone);
  p.t("V", xUnitV, top + 22 * CAP, 22, I.UNIT, true);
  var kx = xUnitV + p.w("V", 22) + 1;
  p.t("km", kx, top + 11 * CAP, 11, I.UNIT, false);
  p.t("/h", kx, top + 22 * CAP, 11, I.UNIT, false);
}

/* ============================== górne pole: nav ============================== */
var N = { BG: "#14181D", MSG_INFO: "#1E2731", MSG_WARN: "#FFC21A", MSG_CRIT: "#8B0A1A", LBL: "#AEB8C4", UNIT: "#9AA5B1", NONE: "#9AA3AE",
  WHITE: "#FFFFFF", BLACK: "#000000", RED: "#FF8C8C", GREEN: "#4ADE80", BLUE: "#60A5FA", ORANGE: "#FB923C" };
function Item(width, draw) { this.width = width; this.draw = draw; }
function G(items, ref, inner) { this.items = items; this.ref = ref; this.inner = inner; }
function gw(g, inner) { return g.reduce(function (a, it) { return a + it.width; }, 0) + inner * (g.length - 1); }
function drawG(g, x0, inner) { var x = x0; g.forEach(function (it, i) { if (i > 0) x += inner; it.draw(x); x += it.width; }); }
function rowGap(gs, vw) { return ((vw - 16) - gs.reduce(function (a, g) { return a + g.ref; }, 0)) / Math.max(1, gs.length - 1); }
function row(gs, vw) {
  var gap = rowGap(gs, vw), x = 8;
  gs.forEach(function (g, i) { if (i === gs.length - 1) drawG(g.items, vw - 8 - gw(g.items, g.inner), g.inner); else { drawG(g.items, x, g.inner); x += g.ref + gap; } });
}
/* 0.4.26 (osmo-2110): kropka kamery DJI Osmo miedzy wx a wind; czerwona+REC=nagrywa, szara=polaczona, brak=brak kamery */
function recDot(c, p, st, gs, vw, base, vs) {
  if (!st || st <= 0 || gs.length < 4) return;
  var gap = rowGap(gs, vw);
  var wxEnd = 8 + gs[0].ref + gap + gs[1].ref + gap + gw(gs[2].items, gs[2].inner);
  var windStart = vw - 8 - gw(gs[3].items, gs[3].inner);
  var free = windStart - wxEnd;
  if (free < 22) return;
  var cy = base - vs * CAP / 2;
  var col = st === 2 ? "#EF4444" : "#6B7280";
  var r = 8;
  var withText = st === 2 && free >= 74;
  var total = 2 * r + (withText ? 5 + p.w("REC", 18) : 0);
  var x = (wxEnd + windStart) / 2 - total / 2;
  c.beginPath(); c.arc(x + r, cy, r, 0, 2 * Math.PI); c.fillStyle = col; c.fill();
  if (withText) p.t("REC", x + 2 * r + 5, cy + 18 * CAP / 2, 18, col);
}
function navTxt(p, s, size, color, base, b) { if (b === undefined) b = true; return new Item(p.w(s, size, b), function (x) { p.t(s, x, base, size, color, b); }); }
function vlabel(p, s, base, capH) {
  return new Item(10, function (x) {
    var ls = 12, lc = ls * CAP, top = base - capH, ys = [top + lc, (top + base) / 2 + lc / 2, base];
    s.slice(0, 3).split("").forEach(function (ch, i) { p.t(ch, x + 5, ys[i], ls, N.LBL, true, "center"); });
  });
}
function msUnit(c, p, x, base, capH) {
  var top = base - capH, k = capH / 28;
  c.strokeStyle = N.LBL; c.lineWidth = 2 * k; c.lineCap = "round";
  c.beginPath(); c.moveTo(x + 8 * k, top + 24.5 * k); c.lineTo(x + 15.5 * k, top + 3.5 * k); c.stroke();
  var fs = 16 * k;
  p.t("m", x + 5.5 * k, top + 11 * k, fs, N.LBL, true, "center");
  p.t("s", x + 16.3 * k, top + 25.5 * k, fs, N.LBL, true, "center");
}
function gradeColor(g) {
  return g <= -8 ? "#3B4BA8" : g <= -5 ? "#5B9BE0" : g <= -2 ? "#2DD4BF" : g < 1 ? "#9AA5B1" : g < 2 ? "#86EFAC" : g < 5 ? "#22C55E"
    : g < 8 ? "#EAB308" : g < 11 ? "#FDBA74" : g < 14 ? "#F97316" : g < 20 ? "#EF4444" : "#A855F7";
}
function arrow(c, cx, cy, sz, deg, color) {
  var k = sz / 28, a = deg * Math.PI / 180, ca = Math.cos(a), sa = Math.sin(a), out = [];
  [[0, -13], [10, -1], [3.5, -1], [3.5, 13], [-3.5, 13], [-3.5, -1], [-10, -1]].forEach(function (q) { var x = q[0] * k, y = q[1] * k; out.push(cx + x * ca - y * sa, cy + x * sa + y * ca); });
  path(c, out); fill(c, color);
}
function tri(c, x, base, wI, hI, g, color) {
  var hh = hI * (0.35 + (Math.min(15, Math.abs(g)) / 15) * 0.65);
  if (g >= 0) path(c, [x, base, x + wI, base, x + wI, base - hh]); else path(c, [x, base - hh, x, base, x + wI, base]);
  fill(c, color);
}
function thermo(c, x, base, wI, hI, color) {
  var cx = x + wI / 2, tube = wI * 0.42, bulbR = wI * 0.36, bulbCy = base - bulbR, top = base - hI;
  c.strokeStyle = color; c.lineWidth = 2; c.lineCap = "round";
  rrect(c, cx - tube / 2, top, cx + tube / 2, bulbCy, tube / 2); c.stroke();
  c.fillStyle = color; c.beginPath(); c.arc(cx, bulbCy, bulbR, 0, 2 * Math.PI); c.fill();
  c.fillRect(cx - tube * 0.2, top + hI * 0.35, tube * 0.4, bulbCy - (top + hI * 0.35));
  for (var k = 1; k <= 3; k++) { var yy = top + hI * (0.15 + 0.15 * k); c.beginPath(); c.moveTo(cx + tube / 2 + 1, yy); c.lineTo(cx + tube / 2 + 3, yy); c.stroke(); }
}
function drop(c, x, base, wI, hI, color) {
  var top = base - hI, cx = x + wI / 2;
  c.beginPath(); c.moveTo(cx, top); c.quadraticCurveTo(x + wI, top + hI * 0.62, cx, base); c.quadraticCurveTo(x, top + hI * 0.62, cx, top); c.closePath(); fill(c, color);
}
function sun(c, cx, cy, r, color) {
  c.fillStyle = color; c.beginPath(); c.arc(cx, cy, r, 0, 2 * Math.PI); c.fill();
  c.strokeStyle = color; c.lineWidth = r * 0.28; c.lineCap = "round";
  for (var k = 0; k < 8; k++) { var a = Math.PI / 4 * k, ca = Math.cos(a), sa = Math.sin(a); c.beginPath(); c.moveTo(cx + ca * r * 1.35, cy + sa * r * 1.35); c.lineTo(cx + ca * r * 1.85, cy + sa * r * 1.85); c.stroke(); }
}
function cloud(c, x, y, w, h, color) {
  c.fillStyle = color;
  [[0.30, 0.62, 0.36], [0.55, 0.45, 0.45], [0.78, 0.64, 0.32]].forEach(function (q) { c.beginPath(); c.arc(x + w * q[0], y + h * q[1], h * q[2], 0, 2 * Math.PI); c.fill(); });
  c.fillRect(x + w * 0.28, y + h * 0.62, w * 0.52, h * 0.36);
}
function fog(c, x, base, wI, hI, color) { c.strokeStyle = color; c.lineWidth = hI * 0.11; c.lineCap = "round"; for (var k = 0; k <= 2; k++) { var yy = base - hI * (0.2 + 0.28 * k); c.beginPath(); c.moveTo(x + wI * 0.08, yy); c.lineTo(x + wI * 0.92, yy); c.stroke(); } }
function snow(c, x, base, sz, color) {
  c.strokeStyle = color; c.lineWidth = sz * 0.12; c.lineCap = "round";
  var sx = x + sz / 2, sy = base - sz / 2, rr = sz * 0.45;
  for (var k = 0; k <= 2; k++) { var a = (90 + 60 * k) * Math.PI / 180, dx = rr * Math.cos(a), dy = rr * Math.sin(a); c.beginPath(); c.moveTo(sx - dx, sy - dy); c.lineTo(sx + dx, sy + dy); c.stroke(); }
}
function storm(c, x, base, wI, hI, color) {
  cloud(c, x, base - hI * 0.95, wI, hI * 0.6, N.UNIT);
  var bx = x + wI * 0.45, by = base - hI * 0.5, bh = hI * 0.55;
  path(c, [bx + bh * 0.25, by, bx - bh * 0.15, by + bh * 0.55, bx + bh * 0.08, by + bh * 0.55, bx - bh * 0.1, by + bh, bx + bh * 0.35, by + bh * 0.38, bx + bh * 0.12, by + bh * 0.38]);
  fill(c, color);
}
/* 22.10 (decyzja Michala): sygnalizator kamery w pasku komunikatow, przy lewej krawedzi: kropka + REC w pionie
   (czerwone = nagrywa, szare = polaczona); pasek komunikatu zwezony o te kilka pikseli. Zwraca x poczatku tekstu. */
function recStrip(c, p, d, h) {
  if (!(d.camRec > 0)) return 8;
  var col = d.camRec === 2 ? "#EF4444" : "#6B7280", ls = 11, tot = 10 + 3 + 3 * ls, top = (h - tot) / 2;
  c.beginPath(); c.arc(13, top + 5, 5, 0, 2 * Math.PI); c.fillStyle = col; c.fill();
  ["R", "E", "C"].forEach(function (ch, i) { p.t(ch, 13, top + 13 + ls * CAP + i * ls, ls, col, true, "center"); });
  return 26;
}
function drawMsg(c, p, d, vw, h) {
  var m = d.msg, lvl = m.level || "info", crit = lvl === "crit", warn = lvl === "warn";
  var bg = crit ? N.MSG_CRIT : warn ? N.MSG_WARN : N.MSG_INFO, fg = warn ? N.BLACK : N.WHITE;
  c.fillStyle = bg; c.fillRect(0, 0, vw, h);
  var x = recStrip(c, p, d, h), right = vw - 8, leadCol = (crit || warn) ? fg : m.none ? N.UNIT : N.WHITE;
  var s0 = Math.min(40, 31 * h / 41), lead = m.lead || "", accent = m.accent || "";
  var total = function (sz) { return (lead ? p.w(lead, sz, false) + sz * 0.3 : 0) + (accent ? p.w(accent, sz) : 0); };
  var s = s0;
  if (x + total(s) > right && lead && accent && !/\d/.test(lead)) lead = "";
  while (s > 26 && x + total(s) > right) s -= 1;
  while (x + total(s) > right && accent.length > 2) accent = accent.slice(0, -2) + "…";
  var base = h / 2 + s * CAP / 2;
  if (lead) { p.t(lead, x, base, s, leadCol, false); x += p.w(lead, s, false) + s * 0.3; }
  if (accent) p.t(accent, x, base, s, fg);
}
function gDst(p, d, base, vs) {
  var capH = vs * CAP, d10 = Math.floor(Math.max(0, d.doneKm) * 10), dDec = "." + (d10 % 10), dds = vs * 0.55;
  return new G([vlabel(p, "DST", base, capH), navTxt(p, String(Math.floor(d10 / 10)), vs, N.WHITE, base),
    new Item(p.w(dDec, dds), function (x) { p.t(dDec, x, base - capH + dds * CAP, dds, N.WHITE); })], 10 + 2 + p.w("888", vs) + 2 + p.w(".8", dds), 2);
}
function gTemp(c, p, d, base, vs) {
  var capH = vs * CAP;
  return new G([new Item(16, function (x) { thermo(c, x, base, 16, capH, N.LBL); }),
    d.tempC != null ? navTxt(p, Math.round(d.tempC) + "°", vs, N.WHITE, base) : navTxt(p, "—", vs, N.NONE, base)], 16 + 4 + p.w("-18°", vs), 4);
}
/* 22.10 pkt 1+2: bez opadu wieksza ikona nieba; opad = 1-3 kropelki (slaby <2,5 / umiarkowany <7,6 / ulewa mm/h) + minuty zamiast mm */
function rainLevel(mm) { return mm == null ? 1 : mm < 2.5 ? 1 : mm < 7.6 ? 2 : 3; }
function drops(c, x, base, n, col) { for (var i = 0; i < n; i++) drop(c, x + i * 17, base - (i % 2) * 4, 15, 24, col); }
function gWx(c, p, d, base, vs) {
  var capH = vs * CAP, wx = [], rn = d.rainNowMmH, rs = d.rainSoon;
  if (rn != null && rn >= 0.1) {
    var n1 = rainLevel(rn);
    wx.push(new Item(17 * n1, function (x) { drops(c, x, base, n1, N.BLUE); }));
    wx.push(navTxt(p, "teraz", 22, N.BLUE, base, false));
  } else if (rs && (rs.radar || (rs.probPct >= 30 && rs.kind !== "FOG"))) {
    var cl = rs.kind === "STORM" ? N.RED : rs.kind === "SNOW" ? "#BFDBFE" : N.BLUE;
    if (rs.kind === "STORM") wx.push(new Item(34, function (x) { storm(c, x, base, 34, 32, cl); }));
    else if (rs.kind === "SNOW") wx.push(new Item(30, function (x) { snow(c, x, base, 30, cl); }));
    else { var n2 = rainLevel(rs.mmPerH); wx.push(new Item(17 * n2, function (x) { drops(c, x, base, n2, cl); })); }
    wx.push(navTxt(p, rs.minutes + "′", 34, cl, base));
    if (!rs.radar) wx.push(navTxt(p, rs.probPct + "%", 18, cl, base, false));
  } else if (d.sky) {
    /* 22.10 (uwaga Michala): bez kamery ikona nieba wypelnia cala kolumne pogody (srodek) -- bez pustej dziury przed wiatrem;
       z kamera ikona przy lewej, obok kropka REC */
    var ref0 = 30 + 4 + p.w("88%", 36) + 4 + p.w("88′", 20), cam = false;   /* REC w pasku komunikatow -> ikona zawsze na srodku kolumny */
    var iw = d.sky === "CLEAR" ? 44 : 66, slot = cam ? iw : ref0, ox = (slot - iw) / 2;
    if (d.sky === "CLEAR") wx.push(new Item(slot, function (x) { sun(c, x + ox + 22, base - capH / 2, 11, "#FACC15"); }));
    else if (d.sky === "PARTLY") wx.push(new Item(slot, function (x) { sun(c, x + ox + 20, base - capH / 2 - 2, 9, "#FACC15"); cloud(c, x + ox + 8, base - capH * 0.92, 58, capH * 1.0, "#E5E7EB");   /* 22.10 v3: chmurka nizej */ }));
    else if (d.sky === "FOG") wx.push(new Item(slot, function (x) { fog(c, x + ox, base, 66, capH * 1.15, N.UNIT); }));
    else wx.push(new Item(slot, function (x) { cloud(c, x + ox, base - capH * 1.0, 66, capH * 1.1, "#C9D2DC"); }));
  }
  if (rs && rs.cached && wx.length) wx.push(navTxt(p, "P", 13, N.UNIT, base, false));
  return new G(wx, 30 + 4 + p.w("88%", 36) + 4 + p.w("88′", 20), 4);
}
function gWind(c, p, d, base, vs, cfg) {
  var capH = vs * CAP, wm = d.windMps, ref = 32 + 4 + p.w("88", vs) + 4 + 20 * capH / 28;
  if (wm == null) return new G([navTxt(p, "wiatr —", 20, N.NONE, base, false)], ref, 4);
  var hs = d.windSignedMps, wcol = N.WHITE;
  if (hs != null && cfg.wind !== "white") {
    var tot = Math.max(d.windTotalMps != null ? d.windTotalMps : Math.abs(hs), Math.abs(hs));
    wcol = (hs >= cfg.windMin && hs >= cfg.windShare * tot) ? N.RED : (hs <= -cfg.windMin && -hs >= cfg.windShare * tot) ? N.GREEN : N.WHITE;
  }
  var wg = [];
  if (d.windRelDeg != null) wg.push(new Item(32, function (x) { arrow(c, x + 16, base - capH / 2, 32, d.windRelDeg, wcol); }));
  wg.push(navTxt(p, String(Math.round(wm)), vs, N.WHITE, base));
  wg.push(new Item(20 * capH / 28, function (x) { msUnit(c, p, x, base, capH); }));
  if (d.windCached) wg.push(navTxt(p, "P", 13, N.UNIT, base, false));
  return new G(wg, ref, 4);
}
/* 22.10 pkt 6 (decyzja: od +-3%): cala kratka nachylenia w kolorze nachylenia, cyfry kontrastowe */
function gGrade(c, p, d, base, vs) {
  var capH = vs * CAP, gr = d.gradePct, ref = 26 + 4 + p.w("-18", vs) + 4 + p.w("%", 20, false);
  if (gr == null) return new G([new Item(26, function (x) { tri(c, x, base, 26, capH, 3, N.NONE); }), navTxt(p, "—", vs, N.NONE, base)], ref, 4);
  var shade = Math.abs(gr) >= 3, bg = gradeColor(gr), fg = shade ? (hexLum(bg) > 0.3 ? N.BLACK : N.WHITE) : N.WHITE, g = [];
  if (shade) g.push(new Item(0, function (x) { c.fillStyle = bg; rrect(c, x - 6, base - capH - 9, x + 600, base + 10, 6); c.fill(); }));
  g.push(new Item(26, function (x) { tri(c, x, base, 26, capH, gr, shade ? fg : bg); }));
  g.push(navTxt(p, String(Math.round(gr)), vs, fg, base));
  g.push(navTxt(p, "%", 20, shade ? fg : N.UNIT, base, false));
  return new G(g, ref, 4);
}
/* 22.10 pkt 3: plakietka zrodla trasy: Q = trase zna QBot (pogoda, nawierzchnia, punkty, plan), K = tylko Karoo (Komoot, ad hoc) */
function srcBadge(c, p, src, base, capH) {
  return new Item(18, function (x) {
    var q = src === "Q", t = base - capH;
    c.fillStyle = q ? "#F2F4F7" : N.BG; rrect(c, x, t, x + 18, base, 4); c.fill();
    if (!q) { c.strokeStyle = N.UNIT; c.lineWidth = 2; rrect(c, x + 1, t + 1, x + 17, base - 1, 4); c.stroke(); }
    p.t(src, x + 9, base - (capH - 16 * CAP) / 2, 16, q ? N.BLACK : N.LBL, true, "center");
  });
}
/* 22.10 pkt 7: bez trasy zamiast DTD -- DOM (km w linii prostej do domu z QBot SETUP > Uzytkownik) */
function gDtd(c, p, d, base, vs) {
  var capH = vs * CAP, ref = 18 + 3 + 10 + 3 + p.w("888", vs);
  if (d.leftKm == null && d.homeKm != null) return new G([vlabel(p, "DOM", base, capH), navTxt(p, String(Math.round(d.homeKm)), vs, N.WHITE, base)], ref, 3);
  var g = [];
  if (d.routeSrc) g.push(srcBadge(c, p, d.routeSrc, base, capH));
  g.push(vlabel(p, "DTD", base, capH));
  g.push(d.leftKm != null ? navTxt(p, String(Math.round(d.leftKm)), vs, N.WHITE, base) : navTxt(p, "—", vs, N.NONE, base));
  return new G(g, ref, 3);
}
function sunDown(c, x, base, s, col) {
  var cy = base - s * 0.22, r = s * 0.32;
  c.fillStyle = col; c.beginPath(); c.arc(x + s * 0.4, cy, r, Math.PI, 2 * Math.PI); c.closePath(); c.fill();   /* polowka slonca nad horyzontem */
  c.fillStyle = col; c.fillRect(x, cy, s * 0.8, s * 0.09);
  path(c, [x + s * 0.66, base - s * 0.95, x + s, base - s * 0.95, x + s * 0.83, base - s * 0.62]); c.fill();
}
function clockIco(c, x, base, s, col) {
  var cx = x + s / 2, cy = base - s / 2;
  c.strokeStyle = col; c.lineWidth = s * 0.11; c.lineCap = "round";
  c.beginPath(); c.arc(cx, cy, s * 0.44, 0, 2 * Math.PI); c.stroke();
  c.beginPath(); c.moveTo(cx, cy - s * 0.28); c.lineTo(cx, cy); c.lineTo(cx + s * 0.22, cy + s * 0.1); c.stroke();
}
/* 22.10 pkt 7: bez trasy zamiast ETA -- czas do zmroku (gdy <= 3 h, wariant DOM + zmrok) albo zegar */
function gEta(c, p, d, base, vs, cfg) {
  var capH = vs * CAP, eta = d.etaMs, dl = d.deadlineMs, col = N.WHITE, ref = 10 + 2 + p.w("88:88", vs);
  if (eta == null && d.leftKm == null && d.nowMs != null) {
    var left = d.duskMs != null ? (d.duskMs - d.nowMs) / 60000 : null;
    if (qv("bez_trasy", "dom_zmrok") === "dom_zmrok" && left != null && left > 0 && left <= 180) {
      var hmTxt = Math.floor(left / 60) + ":" + ("0" + Math.floor(left % 60)).slice(-2);
      return new G([new Item(24, function (x) { sunDown(c, x, base, 24, N.ORANGE); }), navTxt(p, hmTxt, vs, N.ORANGE, base)], ref, 3);
    }
    return new G([new Item(22, function (x) { clockIco(c, x, base - 2, 22, N.LBL); }), navTxt(p, clock(d.nowMs), vs, N.WHITE, base)], ref, 3);
  }
  if (eta != null && dl != null) col = eta > dl ? N.RED : (dl - eta >= cfg.etaGreen * 60000) ? N.GREEN : (dl - eta <= cfg.etaYellow * 60000) ? "#FACC15" : N.WHITE;
  return new G(eta != null ? [vlabel(p, "ETA", base, capH), navTxt(p, clock(eta), vs, col, base)] : [vlabel(p, "ETA", base, capH), navTxt(p, "—", vs, N.NONE, base)], ref, 2);
}
/* 22.10 pkt 4: ikony zamiast etykiet w polu dynamicznym (sklep = koszyk, jedzenie = sztucce, srednia = O, aero = sylwetka) */
function icoBasket(c, x, base, s, col) {
  var top = base - s * 0.62;
  path(c, [x, top, x + s, top, x + s * 0.84, base, x + s * 0.16, base]); fill(c, col);
  c.strokeStyle = col; c.lineWidth = s * 0.1; c.lineCap = "round";
  c.beginPath(); c.arc(x + s / 2, top, s * 0.32, Math.PI, 2 * Math.PI); c.stroke();
  c.fillStyle = N.BG; for (var i = 0; i < 3; i++) c.fillRect(x + s * (0.3 + 0.2 * i) - s * 0.04, top + s * 0.12, s * 0.08, s * 0.34);
}
function icoFood(c, x, base, s, col) {
  var top = base - s, fx = x + s * 0.3, kx = x + s * 0.75;
  c.strokeStyle = col; c.lineCap = "round"; c.lineWidth = s * 0.11;
  c.beginPath(); c.moveTo(fx, top + s * 0.4); c.lineTo(fx, base); c.stroke();
  [-0.14, 0, 0.14].forEach(function (o) { c.beginPath(); c.moveTo(fx + o * s, top); c.lineTo(fx + o * s, top + s * 0.36); c.stroke(); });
  c.beginPath(); c.moveTo(fx - 0.15 * s, top + s * 0.38); c.lineTo(fx + 0.15 * s, top + s * 0.38); c.stroke();
  c.beginPath(); c.moveTo(kx, top + s * 0.5); c.lineTo(kx, base); c.stroke();
  c.fillStyle = col; c.beginPath(); c.moveTo(kx - s * 0.06, top + s * 0.56); c.quadraticCurveTo(kx - s * 0.08, top, kx + s * 0.12, top); c.lineTo(kx + s * 0.07, top + s * 0.56); c.closePath(); c.fill();
}
function icoAero(c, x, base, s, col) {
  var r = s * 0.2, y = base - r;
  c.strokeStyle = col; c.fillStyle = col; c.lineWidth = s * 0.09; c.lineCap = "round";
  c.beginPath(); c.arc(x + r, y, r, 0, 2 * Math.PI); c.stroke();
  c.beginPath(); c.arc(x + s * 1.2 - r, y, r, 0, 2 * Math.PI); c.stroke();
  c.beginPath(); c.moveTo(x + r, y); c.lineTo(x + s * 0.55, y); c.lineTo(x + s * 1.2 - r, y - s * 0.05); c.stroke();
  c.beginPath(); c.moveTo(x + s * 0.4, y - s * 0.45); c.lineTo(x + s * 0.95, y - s * 0.35); c.stroke();
  c.beginPath(); c.arc(x + s * 1.05, y - s * 0.42, s * 0.11, 0, 2 * Math.PI); c.fill();
}
function gDyn(c, p, d, base, vs) {
  var aero = d.dyn && d.dyn.kind === "AERO", ds = vs, capH = ds * CAP, us = 16, ic = 30;   /* 22.10: wartosci jak ETA */
  var ref = aero ? ic * 1.2 + 3 + p.w("−88", ds) + 3 + p.w("W", us, false) + 3 + 12
    : ic + 3 + p.w("88,8", ds) + 3 + p.w("km/h", us, false);
  var di = d.dyn; if (!di) return new G([], ref, 3);
  var col = di.warn === 2 ? N.RED : di.warn === 1 ? "#FACC15" : N.WHITE, g = [];
  if (di.kind === "ATD" || di.kind === "ASC") g.push(vlabel(p, di.kind, base, capH));
  else if (di.kind === "WIND") g.push(new Item(24, function (x) { arrow(c, x + 12, base - capH / 2, 24, 180, N.RED); }));
  else if (di.kind === "water") g.push(new Item(18, function (x) { drop(c, x, base, 18, 22, N.BLUE); }));
  else if (di.kind === "AVG") g.push(new Item(ic, function (x) { avgSym(c, x, base - ic + 2, ic - 2, N.LBL); }));
  else if (di.kind === "AERO") g.push(new Item(ic * 1.2, function (x) { icoAero(c, x, base, ic, N.LBL); }));
  else if (di.kind === "shop") g.push(new Item(ic, function (x) { icoBasket(c, x, base, ic, N.LBL); }));
  else g.push(new Item(ic, function (x) { icoFood(c, x, base, ic, N.LBL); }));
  g.push(navTxt(p, di.value, ds, col, base));
  g.push(navTxt(p, di.unit, us, N.UNIT, base, false));
  if (di.conf != null && di.conf >= 0) g.push(new Item(12, function (x) { c.fillStyle = di.conf === 1 ? "#4ADE80" : "#FACC15"; c.beginPath(); c.arc(x + 6, base - capH / 2, 5, 0, 2 * Math.PI); c.fill(); }));
  return new G(g, ref, 3);
}

function prep(cv, W, H) {
  var dpr = Math.max(1, window.devicePixelRatio || 1);
  cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
  cv.style.width = W + "px"; cv.style.height = H + "px";
  var c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); return c;
}
function navRender(cv, W, H, d, cfg) {
  var c = prep(cv, W, H), p = new P(c);
  c.fillStyle = N.BG; c.fillRect(0, 0, W, H);
  var k = Math.min(H / 126, W / 474), vw = W / k, ext = Math.max(0, H / k - 126);
  c.save(); c.scale(k, k); drawMsg(c, p, d, vw, 41 + ext); c.restore();
  c.save(); c.translate(0, H - 126 * k); c.scale(k, k);
  var gsTop = [gDst(p, d, 76, 42), gTemp(c, p, d, 76, 42), gWx(c, p, d, 76, 42), gWind(c, p, d, 76, 42, cfg)];
  row(gsTop, vw);
  /* 22.10: kropka REC przeniesiona do paska komunikatow (recStrip) */
  var vs = 46, build = function (v) { return [gDtd(c, p, d, 122, v), gEta(c, p, d, 122, v, cfg), gDyn(c, p, d, 122, v), gGrade(c, p, d, 122, v)]; };
  var gs = build(vs);
  while (vs > 38 && rowGap(gs, vw) < 8) { vs -= 1; gs = build(vs); }
  row(gs, vw);
  c.restore();
}
function instrRender(cv, W, H, d, cfg) {
  var c = prep(cv, W, H), p = new P(c);
  c.fillStyle = I.BG; c.fillRect(0, 0, W, H);
  var k = Math.min(H / 126, W / 474);
  c.save(); c.scale(k, k); instrDraw(c, p, d, W / k, Math.max(0, H / k - 126), cfg); c.restore();
}
window.QK2 = { ready: ready, nav: navRender, instr: instrRender, fontsOk: function () { return FONTS_OK; } };
})();
