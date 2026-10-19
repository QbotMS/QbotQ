/* TARCZA DNIA -- WSPOLNY rysownik + dane (2026-10-19, sesja start-tarcza-1910; wyciagniete z dashboard.html bez zmiany logiki).
   Uzywaja: /dashboard.html ("Dzis", telefon) i /index.html (Start na komputerze). Style: /tarcza.css.
   API:  var T = QTarcza.mount(svgEl, {keyRise: el, keySet: el});
         T.draw()            - przerysuj (np. po zmianie danych w T.D)
         T.weekP             - Promise z /api/trener/week (tydzien pn-nd z dzisiaj)  -> dashboard: sekcja Trener
         T.domP / T.warunkiP - Promise z /api/pogoda/dom i godzinami /api/pogoda/warunki (48 h) -> dashboard: sekcja Pogoda
         QTarcza.tcol(t)     - kolor temperatury (legenda)
   TARCZA = zwykly zegar 12 h (12 na gorze), okno 12 h: 2 h wstecz + 10 h do przodu (szew = granica okna):
     pierscien = temperatura w kazdej godzinie (kolor + liczba; noc przyciemniona, mgla = kropki), luk na zewnatrz = opad,
     plakietki = wiatr (strzalka dokad wieje + m/s), znaczniki slonca (wschod pelny, zachod pusty),
     pas treningow (plan kontur / zrobione pelne), zielony luk = okno jedzenia 10-20, wskazowka godzinowa = teraz.
     Srodek: godzina + stan dnia, gotowosc, swiezosc, sen (punktacja Garmin), temp. teraz, nastepny trening.
   Dane: /api/forma/data, /api/trener/week, /api/pogoda/dom, /api/pogoda/okno?dzien=dzis (slonce), /api/pogoda/warunki.
   Klasy w SVG dla wariantow (tarcza.css): .disk (tlo), .hb / .hb.past (godziny temperatury), .seam (szew okna). */
(function () {
"use strict";
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
function J(u) { return fetch(u, { credentials: "same-origin", cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
function f(x, d) { return (x == null || isNaN(x)) ? "–" : Number(x).toFixed(d || 0).replace(".", ",").replace("-", "−"); }
function sg(x, d) { return (x > 0 ? "+" : "") + f(x, d); }
function ymd(d) { return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }
function hm(s) { var p = String(s || "0:0").split(":"); return (+p[0]) + (+p[1] || 0) / 60; }
function mon(d) { var x = new Date(d + "T12:00:00"); x.setDate(x.getDate() - (x.getDay() + 6) % 7); return ymd(x); }
function x2(t) { return String(t || "").slice(0, 5); }
function titleOf(x) { return (x.title || (x.details && x.details.title) || x.name || "").replace(/\s+\d+[′']$/, ""); }
function hex(c) { c = c.replace("#", ""); if (c.length === 3) c = c.replace(/./g, "$&$&"); return [0, 2, 4].map(function (i) { return parseInt(c.substr(i, 2), 16); }); }

/* kolor temperatury z tokenow UI2 (czytane z elementu - dziala tez w zakresie .ui2-dark): <=0 niebieski, 10 bursztyn, 20 pomarancz, 30 czerwien */
function tcolFor(el) {
  var TST = null;
  return function (t) {
    if (!TST) { var cs = getComputedStyle(el || document.documentElement), v = function (n) { return cs.getPropertyValue(n).trim(); };
      TST = [[-5, hex(v("--purple"))], [3, hex(v("--blue"))], [11, hex(v("--amber"))], [20, hex(v("--accent"))], [30, hex(v("--bad"))]]; }
    if (t <= TST[0][0]) return "rgb(" + TST[0][1] + ")";
    for (var i = 1; i < TST.length; i++) if (t <= TST[i][0]) {
      var a = TST[i - 1], b = TST[i], k = (t - a[0]) / (b[0] - a[0]);
      return "rgb(" + [0, 1, 2].map(function (j) { return Math.round(a[1][j] + (b[1][j] - a[1][j]) * k); }) + ")";
    }
    return "rgb(" + TST[TST.length - 1][1] + ")";
  };
}

/* wschod / zachod slonca NA DZIS (przyblizenie NOAA, +-3 min; zaraz potem zastapione godzinami z /api/pogoda/okno?dzien=dzis) */
function sunTimes(day, lat, lon) {
  var rad = Math.PI / 180, d0 = new Date(day.getFullYear(), day.getMonth(), day.getDate(), 12);
  var N = Math.round((d0 - new Date(d0.getFullYear(), 0, 0)) / 864e5), g = 2 * Math.PI / 365 * (N - 1);
  var eq = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g) - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));
  var de = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g) - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
  var ha = Math.acos(Math.cos(90.833 * rad) / (Math.cos(lat * rad) * Math.cos(de)) - Math.tan(lat * rad) * Math.tan(de)) / rad;
  var tz = -d0.getTimezoneOffset();
  var fm = function (m) { m = Math.round(m + tz); return ("0" + Math.floor(m / 60)).slice(-2) + ":" + ("0" + (m % 60)).slice(-2); };
  return [fm(720 - 4 * (lon + ha) - eq), fm(720 - 4 * (lon - ha) - eq)];
}

var STW = { w_normie: ["w normie", "st-ok"], uwaga: ["uwaga", "st-warn"], zmeczony: ["zmęczony", "st-warn"], przeciazenie: ["przeciążenie", "st-bad"] };

function mount(svg, opt) {
  opt = opt || {};
  var C = 200, D = { godz: null, ses: null, acts: null, st: null };
  var NOW = new Date(), TODAY = ymd(NOW), NOWH = NOW.getHours() + NOW.getMinutes() / 60;
  var tcol = tcolFor(svg);
  /* ZEGAR 12-GODZINNY jak zwykly zegar (12 na gorze, 3 z prawej); okno 12 godzin: 2 h wstecz + 10 h do przodu */
  function A(h) { return ((h % 12) + 12) % 12 / 12 * 2 * Math.PI; }
  function P(h, r) { var a = A(h); return [C + r * Math.sin(a), C - r * Math.cos(a)]; }
  function arc(h0, h1, r) { var a = P(h0, r), b = P(h1, r), big = (h1 - h0) > 6 ? 1 : 0;
    return "M" + a[0].toFixed(2) + " " + a[1].toFixed(2) + " A" + r + " " + r + " 0 " + big + " 1 " + b[0].toFixed(2) + " " + b[1].toFixed(2); }
  function band(h0, h1, r0, r1) { var a = P(h0, r1), b = P(h1, r1), c = P(h1, r0), d = P(h0, r0), big = (h1 - h0) > 6 ? 1 : 0;
    return "M" + a.join(" ") + " A" + r1 + " " + r1 + " 0 " + big + " 1 " + b.join(" ") + " L" + c.join(" ") + " A" + r0 + " " + r0 + " 0 " + big + " 0 " + d.join(" ") + "Z"; }
  function clip(h0, h1, w0, w1) { var a = Math.max(h0, w0), b = Math.min(h1, w1); return b > a ? [a, b] : null; }
  function draw() {
    /* promienie: wiatr 189 | opad 168 | temperatura 140-164 | slonce 133-145 | treningi 125 (12/3/6/9) | okno jedzenia 113 | srodek do ~108 */
    var W0 = Math.floor(NOWH) - 2, W1 = W0 + 12;
    var s = '<defs><pattern id="fog" width="4" height="4" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.1" fill="var(--ink)"/></pattern></defs>';
    s += '<circle class="disk" cx="' + C + '" cy="' + C + '" r="172" fill="var(--card)"/>';
    for (var m = 0; m < 60; m++) { var big5 = m % 5 === 0, a = P(m / 5, big5 ? 172 : 174), b = P(m / 5, 177);
      if (big5) continue; s += '<line x1="' + a[0].toFixed(1) + '" y1="' + a[1].toFixed(1) + '" x2="' + b[0].toFixed(1) + '" y2="' + b[1].toFixed(1) + '" stroke="var(--muted)" stroke-opacity=".25" stroke-width="1"/>'; }
    var G = (D.godz || []).map(function (g) { var d = g.iso.slice(0, 10), hh = +g.iso.slice(11, 13); return { g: g, H: hh + (d === TODAY ? 0 : (d > TODAY ? 24 : -24)) }; })
      .filter(function (x) { return x.H >= W0 && x.H < W1; });
    G.forEach(function (x) { var g = x.g, h = x.H, past = h + 1 <= NOWH;
      s += '<path class="hb' + (past ? ' past' : '') + '" d="' + band(h + .03, h + .97, 140, 164) + '" fill="' + tcol(g.temp) + '" fill-opacity="' + (past ? .4 : 1) + '"/>';
      if (g.mgla) s += '<path d="' + band(h + .03, h + .97, 140, 164) + '" fill="url(#fog)" fill-opacity="' + (g.mgla > 1 ? .5 : .28) + '"/>';
      if (!g.dzien) s += '<path d="' + band(h + .03, h + .97, 140, 164) + '" fill="var(--card)" fill-opacity=".42"/>';   /* noc: przyciemniona godzina */
      var q = P(h + .5, 152);
      s += '<text class="tx" x="' + q[0].toFixed(1) + '" y="' + (q[1] + 5.5).toFixed(1) + '" text-anchor="middle"' + (past ? ' style="fill:var(--ink);fill-opacity:.8"' : '') + '>' + f(g.temp) + '°</text>';
      var mm = Math.max(g.opad || 0, g.snieg || 0);
      if (mm > 0.05) s += '<path d="' + arc(h + .06, h + .94, 168.5) + '" fill="none" stroke="var(--blue)" stroke-width="6" stroke-linecap="round" stroke-opacity="' + Math.min(1, .45 + mm / 3).toFixed(2) + '"/>';
      /* wiatr: plakietka na godzine - strzalka (dokad wieje) + sila m/s obok, zawsze poziomo, srodek na r=189 */
      var wq = P(h + .5, 189), L = 7 + Math.min(3, (g.wiatr || 0) * .8), r = (g.kier || 0) + 180, op = past ? .45 : 1;
      s += '<g transform="translate(' + wq[0].toFixed(1) + ' ' + wq[1].toFixed(1) + ')" opacity="' + op + '">'
        + '<g transform="translate(-12 0) rotate(' + r + ')"><path d="M0 ' + (-L) + ' L5.5 ' + (L * .6).toFixed(1) + ' L0 ' + (L * .25).toFixed(1) + ' L-5.5 ' + (L * .6).toFixed(1) + 'Z" fill="var(--ink)"/></g>'
        + '<text class="ws" x="-2" y="5.5" text-anchor="start">' + f(g.wiatr, 1) + '</text></g>';
    });
    /* szew okna (granica: 2 h wstecz | +10 h) */
    var z0 = P(W0, 136), z1 = P(W0, 208);
    s += '<line class="seam" x1="' + z0[0].toFixed(1) + '" y1="' + z0[1].toFixed(1) + '" x2="' + z1[0].toFixed(1) + '" y2="' + z1[1].toFixed(1) + '" stroke="var(--bg)" stroke-width="5"/>';
    /* wschod i zachod slonca: znaczniki (dziala tez latem, gdy dzien > 12 h) */
    (D.slonce || []).forEach(function (t, i) { var h = hm(t), q0 = P(h, 133), q1 = P(h, 145);
      s += '<line x1="' + q0[0].toFixed(1) + '" y1="' + q0[1].toFixed(1) + '" x2="' + q1[0].toFixed(1) + '" y2="' + q1[1].toFixed(1) + '" stroke="var(--card)" stroke-width="6"/><line x1="' + q0[0].toFixed(1) + '" y1="' + q0[1].toFixed(1) + '" x2="' + q1[0].toFixed(1) + '" y2="' + q1[1].toFixed(1) + '" stroke="var(--amber)" stroke-width="2.5" stroke-linecap="round"/>'
        + (i ? '<circle cx="' + q0[0].toFixed(1) + '" cy="' + q0[1].toFixed(1) + '" r="5" fill="var(--card)" stroke="var(--amber)" stroke-width="2.5"/>'   /* zachod: pusty krazek */
             : '<circle cx="' + q0[0].toFixed(1) + '" cy="' + q0[1].toFixed(1) + '" r="6" fill="var(--amber)"/><circle cx="' + q0[0].toFixed(1) + '" cy="' + q0[1].toFixed(1) + '" r="9.5" fill="none" stroke="var(--amber)" stroke-width="1.2" stroke-opacity=".6"/>');   /* wschod: pelne slonce z poswiata */
    });
    if (D.slonce && opt.keyRise) { opt.keyRise.textContent = "wschód " + D.slonce[0]; if (opt.keySet) opt.keySet.textContent = "zachód " + D.slonce[1]; }
    /* okno jedzenia (10:00-20:00) */
    s += '<circle cx="' + C + '" cy="' + C + '" r="113" fill="none" stroke="var(--well)" stroke-width="5" stroke-opacity=".6"/>';
    var ew = D.okno || [10, 20];
    s += '<path d="' + arc(ew[0], ew[1], 113) + '" fill="none" stroke="var(--good)" stroke-width="5" stroke-linecap="round" stroke-opacity=".9"/>';
    /* 12 / 3 / 6 / 9 */
    [[0, "12"], [3, "3"], [6, "6"], [9, "9"]].forEach(function (x) { var p = P(x[0], 125); s += '<text class="lbl" x="' + p[0].toFixed(1) + '" y="' + (p[1] + 6.5).toFixed(1) + '" text-anchor="middle">' + x[1] + '</text>'; });
    /* treningi: zrobione (pelne) i plan (kontur) - tylko w oknie 12 h */
    (D.acts || []).forEach(function (a) { var t = new Date(a.started_at), h0 = t.getHours() + t.getMinutes() / 60, c = clip(h0, h0 + Math.max(.25, (a.duration_s || 0) / 3600), W0, W1);
      if (c) s += '<path d="' + arc(c[0], c[1], 125) + '" fill="none" stroke="var(--accent)" stroke-width="13" stroke-linecap="round"/>'; });
    (D.ses || []).forEach(function (x) { if (x.status === "done") return; var h0 = hm(x.start_time), c = clip(h0, h0 + (x.dur_min || 30) / 60, W0, W1); if (!c) return;
      s += '<path d="' + arc(c[0] + .05, c[1] - .05, 125) + '" fill="none" stroke="var(--accent)" stroke-width="12" stroke-opacity=".22" stroke-linecap="round"/>'
        + '<path d="' + arc(c[0], c[1], 125) + '" fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-dasharray="5 3.5" stroke-linecap="round"/>'; });
    /* wskazowka godzinowa (minuty: cyfrowo w srodku) */
    var n0 = P(NOWH, 100), n1 = P(NOWH, 166);
    s += '<g class="sweep" style="transform-origin:' + C + 'px ' + C + 'px"><line x1="' + n0[0].toFixed(1) + '" y1="' + n0[1].toFixed(1) + '" x2="' + n1[0].toFixed(1) + '" y2="' + n1[1].toFixed(1) + '" stroke="var(--accent)" stroke-width="5" stroke-linecap="round"/>'
      + '<circle cx="' + n1[0].toFixed(1) + '" cy="' + n1[1].toFixed(1) + '" r="7" fill="var(--accent)" stroke="var(--card)" stroke-width="2.5"/></g>';
    /* srodek: godzina, stan dnia, 4 liczby, co dalej */
    var st = D.st || {}, nx = (D.ses || []).filter(function (x) { return x.status !== "done" && hm(x.start_time) >= NOWH - 0.5; })[0];
    var hhmm = ("0" + NOW.getHours()).slice(-2) + ":" + ("0" + NOW.getMinutes()).slice(-2);
    s += '<text class="c0 ' + (st.cls || "") + '" x="' + C + '" y="' + (C - 58) + '" text-anchor="middle">' + esc(hhmm + "  ·  " + (st.word || "–").toUpperCase()) + '</text>';
    var cell = function (x, y, v, l, cl) { return '<text class="cv ' + (cl || "") + '" x="' + x + '" y="' + y + '" text-anchor="middle">' + v + '</text>'
      + '<text class="cl" x="' + x + '" y="' + (y + 17) + '" text-anchor="middle">' + l + '</text>'; };
    var rc = st.r == null ? "" : (st.r > 0.5 ? "st-ok" : (st.r < -0.5 ? "st-bad" : "")),
        tc = st.tsb == null ? "" : (st.tsb > 15 ? "st-ok" : (st.tsb < -20 ? "st-bad" : (st.tsb < -5 ? "st-warn" : ""))),
        sc = st.ss == null ? "" : (st.ss >= 80 ? "st-ok" : (st.ss < 60 ? "st-bad" : ""));
    s += cell(C - 42, C - 14, st.r == null ? "–" : sg(st.r, 1), "gotowość", rc) + cell(C + 42, C - 14, st.tsb == null ? "–" : sg(st.tsb), "świeżość", tc);
    s += cell(C - 42, C + 38, st.ss == null ? "–" : f(st.ss), "sen", sc) + cell(C + 42, C + 38, D.tnow == null ? "–" : f(D.tnow) + "°", "teraz");
    s += '<line x1="' + C + '" y1="' + (C - 42) + '" x2="' + C + '" y2="' + (C + 58) + '" stroke="var(--muted)" stroke-opacity=".3"/>'
      + '<line x1="' + (C - 78) + '" y1="' + (C + 9) + '" x2="' + (C + 78) + '" y2="' + (C + 9) + '" stroke="var(--muted)" stroke-opacity=".3"/>';
    s += '<text class="c3" x="' + C + '" y="' + (C + 80) + '" text-anchor="middle">' + esc(nx ? x2(nx.start_time) + " " + titleOf(nx) : (st.note || "")) + '</text>';
    svg.innerHTML = s;
  }

  /* STAN DNIA (Forma) */
  J("/api/forma/data").then(function (d) {
    var S = d.series || [], s = S[S.length - 1] || {};
    var w = STW[s.day_status] || [String(s.day_status || "–").replace("_", " "), "st-na"];
    D.st = { r: s.readiness_effective, tsb: s.tsb_real, ss: s.sleep_score, cls: w[1], word: w[0], note: s.day_status_note ? s.day_status_note.split(";")[0] : "" };
    draw();
  }).catch(function () {});
  /* TRENER: sesje i jazdy dnia */
  var weekP = J("/api/trener/week?start=" + mon(TODAY)).then(function (w) {
    var S = (w.sessions || []).filter(function (x) { return !x.cut; });
    D.ses = S.filter(function (x) { return x.day === TODAY; }).map(function (x) { return { start_time: x.start_time, dur_min: x.dur_min, status: x.status, title: x.details && x.details.title, name: x.name }; });
    D.acts = (w.activities || []).filter(function (a) { return a.date === TODAY; });
    draw(); return w;
  });
  /* POGODA: dom -> slonce (obliczenie, potem dokladne z Okna jazdy) -> godziny 48 h */
  var domP = J("/api/pogoda/dom").then(function (p) {
    D.slonce = sunTimes(NOW, p.lat, p.lon); draw();
    J("/api/pogoda/okno?lat=" + p.lat + "&lon=" + p.lon + "&dzien=" + TODAY).then(function (o) { if (o && o.slonce && o.slonce[0]) { D.slonce = o.slonce; draw(); } }).catch(function () {});
    return p;
  });
  var warunkiP = domP.then(function (p) { return J("/api/pogoda/warunki?lat=" + p.lat + "&lon=" + p.lon + "&godziny=48"); }).then(function (a) {
    var G = a.godziny || []; D.godz = G;
    var n = G.filter(function (g) { return !g.przeszlosc; })[0] || G[G.length - 1] || {};
    D.tnow = n.temp; draw(); return G;
  });
  [weekP, domP, warunkiP].forEach(function (p) { p.catch(function () {}); });
  draw();
  setInterval(function () { NOW = new Date(); NOWH = NOW.getHours() + NOW.getMinutes() / 60; draw(); }, 60000);
  return { D: D, draw: draw, weekP: weekP, domP: domP, warunkiP: warunkiP, tcol: tcol };
}

window.QTarcza = { mount: mount, tcol: function (t) { return tcolFor(document.documentElement)(t); } };
})();
