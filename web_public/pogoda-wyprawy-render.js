/* Pogoda wyprawy - podstrona.
   Dane: GET /api/planer/pogoda (dzien po dniu). Rysowanie wlasne w SVG, bez bibliotek.
   Zasada: pokazujemy TAKZE niepewnosc - wstega zespolu na wykresie i rozrzut modeli
   pod nim. Jedna liczba bez kontekstu jest tu uznawana za bledna. */
(function () {
  "use strict";
  var q = new URLSearchParams(location.search);
  var RID = q.get("route") || "";
  var CUTS = q.get("cuts") || "";
  var NDAYS = Math.max(1, parseInt(q.get("days") || "1", 10) || 1);
  var $ = function (id) { return document.getElementById(id); };

  var dni = {};        // index -> odpowiedz API
  var laduje = {};     // index -> bool
  var trwa = false;    // liczenie wszystkich
  var rozwin = {};     // index -> czy tabela 30 min rozwinieta
  var META = null;     // nazwa/dystans trasy

  var KOL = {
    temp: "var(--accent)", feels: "var(--bad)", wbgt: "var(--warn)",
    opad: "var(--rain)", siatka: "var(--line)", tekst: "var(--muted)"
  };

  /* Skala barw dobrana do JAZDY, nie do estetyki: zielen tylko tam, gdzie naprawde
     jest komfortowo. Wczesniejsza skala malowala 29 C na zielono, wiec dzien z alarmem
     upalu wygladal na bezpieczny. */
  var SKALA_T = [
    [-5, [56, 78, 132]], [5, [74, 124, 170]], [14, [92, 152, 132]], [20, [104, 158, 96]],
    [25, [198, 172, 78]], [29, [204, 130, 58]], [33, [178, 78, 50]], [38, [140, 44, 44]]
  ];
  function kolorTemp(t) {
    if (t == null) return "#8c8168";
    var a = SKALA_T[0], b = SKALA_T[SKALA_T.length - 1];
    if (t <= a[0]) return "rgb(" + a[1].join(",") + ")";
    if (t >= b[0]) return "rgb(" + b[1].join(",") + ")";
    for (var i = 0; i < SKALA_T.length - 1; i++) {
      var p = SKALA_T[i], q = SKALA_T[i + 1];
      if (t >= p[0] && t <= q[0]) {
        var f = (t - p[0]) / (q[0] - p[0]);
        return "rgb(" + [0, 1, 2].map(function (k) {
          return Math.round(p[1][k] + (q[1][k] - p[1][k]) * f);
        }).join(",") + ")";
      }
    }
    return "#8c8168";
  }

  /* Kazdy osrodek ma wlasny, staly kolor -- inaczej legenda nic nie daje i nie da sie
     sprawdzic, o ktorym modelu mowi ocena. Kanon poznaje sie po rozmiarze i obwodce,
     nie po kolorze, bo kanon zmienia sie zaleznie od daty. */
  var KOL_MODEL = {
    icon_d2: "#4a90c2", icon_eu: "#69a85c", ecmwf_ifs025: "#c9772a",
    ecmwf_aifs025_single: "#9a6fb8", gfs_seamless: "#c9a227", ukmo_seamless: "#bd5548"
  };
  function kolorModelu(id) { return KOL_MODEL[id] || "#8c8168"; }

  function esc(x) {
    return String(x == null ? "" : x).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function n(v, nd) {
    if (v === null || v === undefined || v === "") return "b/d";
    return Number(v).toFixed(nd == null ? 1 : nd).replace(".", ",");
  }
  function minTxt(m) {
    if (m == null) return "b/d";
    var h = Math.floor(m / 60), r = Math.round(m % 60);
    return h ? (h + " h " + r + " min") : (r + " min");
  }
  function wiatrTxt(v) {
    if (v == null) return "b/d";
    if (v > 0.3) return n(v) + " m/s z tyłu";
    if (v < -0.3) return n(Math.abs(v)) + " m/s w czoło";
    return "bez składowej wzdłuż";
  }
  function dataDnia(i) {
    var s = $("startdate").value;
    if (!s) return "";
    var d = new Date(s + "T12:00:00");
    d.setDate(d.getDate() + i);
    var m = d.getMonth() + 1, dd = d.getDate();
    return d.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (dd < 10 ? "0" : "") + dd;
  }
  function hhmm2min(s) {
    if (!s) return null;
    var p = String(s).split(":");
    return parseInt(p[0], 10) * 60 + parseInt(p[1] || "0", 10);
  }

  /* ---------------- wykres dnia ----------------
     Geometria liczona osobno, bo potrzebuje jej i rysowanie, i kursor pod myszka. */
  function geoWykresu(s) {
    var W = 1000, H = 384, L = 46, R = 46;
    var cy0 = 14, cy1 = 34;            // pas zachmurzenia (gora)
    var y0 = 44, y1 = H - 84;          // pole temperatury
    var oy0 = y1 + 20, oy1 = y1 + 40;  // pas opadu
    var wy0 = H - 26, wy1 = H - 8;     // pas wiatru
    var kmA = s[0].km, kmB = s[s.length - 1].km;
    var kmSpan = Math.max(0.1, kmB - kmA);
    return {
      W: W, H: H, x0: L, x1: W - R, y0: y0, y1: y1, cy0: cy0, cy1: cy1,
      oy0: oy0, oy1: oy1, wy0: wy0, wy1: wy1, kmA: kmA, kmB: kmB, kmSpan: kmSpan,
      X: function (km) { return L + (km - kmA) / kmSpan * (W - R - L); }
    };
  }

  function najblizszy(s, km) {
    var best = s[0], bd = 1e9;
    for (var i = 0; i < s.length; i++) {
      var d = Math.abs(s[i].km - km);
      if (d < bd) { bd = d; best = s[i]; }
    }
    return best;
  }

  function chartSVG(d, idx) {
    var s = (d.seria || []).filter(function (x) { return x.temp_c != null; });
    if (s.length < 2) return "";
    var G = geoWykresu(s), X = G.X;

    var vals = [];
    s.forEach(function (p) {
      [p.temp_c, p.feels, p.wbgt].forEach(function (v) { if (v != null) vals.push(v); });
    });
    var zesp = ((d.modele || {}).zespol || {}).godziny || [];
    zesp.forEach(function (g) { vals.push(g.temp_p10); vals.push(g.temp_p90); });
    var lo = Math.floor(Math.min.apply(null, vals) - 1.5);
    var hi = Math.ceil(Math.max.apply(null, vals) + 1.5);
    if (hi - lo < 6) hi = lo + 6;
    var Y = function (v) { return G.y1 - (v - lo) / (hi - lo) * (G.y1 - G.y0); };

    var maxOpad = Math.max(1.0, Math.max.apply(null, s.map(function (p) { return p.opad_mm || 0; })));
    var g = [];

    // strefy alertow
    (d.alerty || []).forEach(function (a) {
      if (a.km_od == null || a.km_do == null) return;
      var kol = (a.typ === "deszcz") ? "var(--rain)" : (a.typ === "burza") ? "var(--warn)"
        : (a.typ === "zimno") ? "var(--cold)" : "var(--bad)";
      var op = (String(a.severity || "").indexOf("ALARM") >= 0) ? 0.15 : 0.09;
      g.push('<rect x="' + X(a.km_od).toFixed(1) + '" y="' + G.y0 + '" width="' +
        Math.max(1, X(a.km_do) - X(a.km_od)).toFixed(1) + '" height="' + (G.y1 - G.y0) +
        '" fill="' + kol + '" opacity="' + op + '"/>');
    });

    // PAS ZACHMURZENIA: im ciemniej, tym wiecej chmur
    g.push('<text x="' + G.x0 + '" y="' + (G.cy0 - 3) + '" font-size="10" fill="' + KOL.tekst +
      '">zachmurzenie</text>');
    g.push('<rect x="' + G.x0 + '" y="' + G.cy0 + '" width="' + (G.x1 - G.x0) + '" height="' +
      (G.cy1 - G.cy0) + '" fill="var(--panel)"/>');
    s.forEach(function (p, i) {
      if (p.chmury_pct == null) return;
      var nx = (i + 1 < s.length) ? X(s[i + 1].km) : G.x1;
      g.push('<rect x="' + X(p.km).toFixed(1) + '" y="' + G.cy0 + '" width="' +
        Math.max(1, nx - X(p.km)).toFixed(1) + '" height="' + (G.cy1 - G.cy0) +
        '" fill="#5b6670" opacity="' + (0.06 + 0.84 * (p.chmury_pct / 100)).toFixed(2) + '"/>');
    });

    // siatka + os temperatury
    var krok = (hi - lo) > 24 ? 5 : ((hi - lo) > 12 ? 2 : 1);
    for (var v = Math.ceil(lo / krok) * krok; v <= hi; v += krok) {
      g.push('<line x1="' + G.x0 + '" y1="' + Y(v).toFixed(1) + '" x2="' + G.x1 + '" y2="' +
        Y(v).toFixed(1) + '" stroke="' + KOL.siatka + '" stroke-width="1" opacity="0.7"/>');
      g.push('<text x="' + (G.x0 - 7) + '" y="' + (Y(v) + 4).toFixed(1) + '" text-anchor="end" ' +
        'font-size="11" fill="' + KOL.tekst + '">' + v + "</text>");
    }
    g.push('<text x="' + (G.x0 - 7) + '" y="' + (G.y0 - 6) + '" text-anchor="end" font-size="10" fill="' +
      KOL.tekst + '">°C</text>');

    // wstega zespolu
    if (zesp.length >= 2) {
      var pkt = [];
      zesp.forEach(function (gg) {
        var cel = hhmm2min(gg.godzina), b = null, bd = 1e9;
        s.forEach(function (p) {
          var dd = Math.abs((hhmm2min(p.eta) || 0) - cel);
          if (dd < bd) { bd = dd; b = p; }
        });
        if (b && bd <= 90) pkt.push({ km: b.km, p10: gg.temp_p10, p90: gg.temp_p90 });
      });
      if (pkt.length >= 2) {
        var gora = pkt.map(function (p, i) { return (i ? "L" : "M") + X(p.km).toFixed(1) + " " + Y(p.p90).toFixed(1); });
        var dol = pkt.slice().reverse().map(function (p) { return "L" + X(p.km).toFixed(1) + " " + Y(p.p10).toFixed(1); });
        g.push('<path d="' + gora.join(" ") + " " + dol.join(" ") + ' Z" fill="' + KOL.temp + '" opacity="0.14"/>');
      }
    }

    function linia(pole, kolor, sz, dash) {
      var dd = [];
      s.forEach(function (p) {
        if (p[pole] == null) return;
        dd.push((dd.length ? "L" : "M") + X(p.km).toFixed(1) + " " + Y(p[pole]).toFixed(1));
      });
      if (dd.length < 2) return;
      g.push('<path d="' + dd.join(" ") + '" fill="none" stroke="' + kolor + '" stroke-width="' + sz +
        '" stroke-linejoin="round" stroke-linecap="round"' + (dash ? ' stroke-dasharray="' + dash + '"' : "") + "/>");
    }
    linia("wbgt", KOL.wbgt, 1.8, "");
    linia("feels", KOL.feels, 1.6, "5 4");
    linia("temp_c", KOL.temp, 2.6, "");

    // wschod / zachod
    var sl = d.slonce || {};
    [["wschód", sl.wschod, "var(--warn)"], ["zachód", sl.zachod, "var(--cold)"]].forEach(function (it) {
      if (!it[1]) return;
      var cel = hhmm2min(it[1]), a = hhmm2min(s[0].eta), b = hhmm2min(s[s.length - 1].eta);
      if (cel == null || a == null || b == null || cel < a || cel > b) return;
      var best = null, bd = 1e9;
      s.forEach(function (p) {
        var dd = Math.abs((hhmm2min(p.eta) || 0) - cel);
        if (dd < bd) { bd = dd; best = p; }
      });
      if (!best) return;
      g.push('<line x1="' + X(best.km).toFixed(1) + '" y1="' + G.y0 + '" x2="' + X(best.km).toFixed(1) +
        '" y2="' + G.y1 + '" stroke="' + it[2] + '" stroke-width="1.4" stroke-dasharray="4 3"/>');
      g.push('<text x="' + (X(best.km) + 4).toFixed(1) + '" y="' + (G.y0 + 12) + '" font-size="10.5" fill="' +
        it[2] + '">' + it[0] + " " + it[1] + "</text>");
    });

    // postoje - pionowe znaczniki, bo przesuwaja cala reszte dnia
    ((d.postoje || {}).na_km || []).forEach(function (km) {
      if (km < G.kmA || km > G.kmB) return;
      g.push('<line x1="' + X(km).toFixed(1) + '" y1="' + G.y0 + '" x2="' + X(km).toFixed(1) + '" y2="' +
        G.y1 + '" stroke="var(--muted)" stroke-width="1" stroke-dasharray="2 4"/>');
      g.push('<text x="' + (X(km) + 3).toFixed(1) + '" y="' + (G.y1 - 4) + '" font-size="10" fill="' +
        KOL.tekst + '">postój</text>');
    });

    // PAS OPADU - zawsze widoczny, nawet gdy sucho
    var maxProb = Math.max.apply(null, s.map(function (p) { return p.opad_prob || 0; }));
    var opis = (maxOpad > 1.0)
      ? ("opad do " + n(maxOpad) + " mm/h" + (maxProb ? " · szansa do " + Math.round(maxProb) + "%" : ""))
      : (maxProb >= 10
        ? ("opad — sucho, ale szansa do " + Math.round(maxProb) + "% (słupki = ilość, tło = szansa)")
        : "opad — sucho, szansa poniżej 10%");
    g.push('<text x="' + G.x0 + '" y="' + (G.oy0 - 3) + '" font-size="10" fill="' + KOL.tekst +
      '">' + opis + "</text>");
    g.push('<rect x="' + G.x0 + '" y="' + G.oy0 + '" width="' + (G.x1 - G.x0) + '" height="' +
      (G.oy1 - G.oy0) + '" fill="var(--panel)" opacity="0.6"/>');
    // tlo = prawdopodobienstwo opadu (to ono generuje alert "deszcz", nawet przy 0 mm)
    s.forEach(function (p, i) {
      if (!p.opad_prob) return;
      var nx = (i + 1 < s.length) ? X(s[i + 1].km) : G.x1;
      g.push('<rect x="' + X(p.km).toFixed(1) + '" y="' + G.oy0 + '" width="' +
        Math.max(1, nx - X(p.km)).toFixed(1) + '" height="' + (G.oy1 - G.oy0) +
        '" fill="' + KOL.opad + '" opacity="' + (0.10 + 0.45 * (p.opad_prob / 100)).toFixed(2) + '"/>');
    });
    var szer = Math.max(1.5, (G.x1 - G.x0) / s.length * 0.9);
    s.forEach(function (p) {
      if (!p.opad_mm) return;
      var wys = Math.max(1.5, (p.opad_mm / maxOpad) * (G.oy1 - G.oy0));
      g.push('<rect x="' + (X(p.km) - szer / 2).toFixed(1) + '" y="' + (G.oy1 - wys).toFixed(1) +
        '" width="' + szer.toFixed(1) + '" height="' + wys.toFixed(1) + '" fill="' + KOL.opad + '"/>');
    });

    // os X
    var ileEt = Math.min(8, Math.max(3, Math.round((G.x1 - G.x0) / 130)));
    for (var e = 0; e <= ileEt; e++) {
      var kmE = G.kmA + (G.kmB - G.kmA) * e / ileEt;
      var bl = najblizszy(s, kmE);
      g.push('<text x="' + X(kmE).toFixed(1) + '" y="' + (G.oy1 + 14) + '" text-anchor="middle" ' +
        'font-size="11" fill="' + KOL.tekst + '">' + Math.round(kmE) + " km</text>");
      if (bl) g.push('<text x="' + X(kmE).toFixed(1) + '" y="' + (G.oy1 + 25) + '" text-anchor="middle" ' +
        'font-size="10.5" fill="' + KOL.tekst + '" opacity="0.8">' + esc(bl.eta || "") + "</text>");
    }

    // pas wiatru
    s.forEach(function (p, i) {
      if (p.wiatr_wzdluz_ms == null) return;
      var nx = (i + 1 < s.length) ? X(s[i + 1].km) : G.x1;
      var v = p.wiatr_wzdluz_ms;
      var kol = v > 0.3 ? "var(--good)" : (v < -0.3 ? "var(--bad)" : "var(--muted)");
      g.push('<rect x="' + X(p.km).toFixed(1) + '" y="' + G.wy0 + '" width="' +
        Math.max(1, nx - X(p.km)).toFixed(1) + '" height="' + (G.wy1 - G.wy0) + '" fill="' + kol +
        '" opacity="' + (0.2 + 0.6 * Math.min(1, Math.abs(v) / 5)).toFixed(2) + '"/>');
    });
    g.push('<text x="' + G.x0 + '" y="' + (G.wy0 - 3) + '" font-size="10" fill="' + KOL.tekst +
      '">wiatr wzdłuż trasy</text>');

    // kursor (sterowany myszka)
    g.push('<g class="kursor" style="display:none"><line x1="0" y1="' + G.cy0 + '" x2="0" y2="' +
      G.wy1 + '" stroke="var(--ink2)" stroke-width="1"/><circle cx="0" cy="0" r="4" ' +
      'fill="var(--card)" stroke="' + KOL.temp + '" stroke-width="2"/></g>');
    g.push('<rect class="lapacz" x="' + G.x0 + '" y="' + G.cy0 + '" width="' + (G.x1 - G.x0) +
      '" height="' + (G.wy1 - G.cy0) + '" fill="transparent" style="cursor:crosshair"/>');

    return '<div class="chart-wrap" id="cw' + idx + '">' +
      '<svg class="chart" viewBox="0 0 ' + G.W + " " + G.H + '" xmlns="http://www.w3.org/2000/svg" ' +
      'preserveAspectRatio="xMidYMid meet">' + g.join("") + "</svg>" +
      '<div class="tip"></div></div>';
  }

  /* kursor: pionowa linia + dymek z kompletem wartosci dla tego kilometra */
  function podepnijWykres(idx) {
    var wrap = document.getElementById("cw" + idx);
    if (!wrap) return;
    var d = dni[idx];
    var s = ((d || {}).seria || []).filter(function (x) { return x.temp_c != null; });
    if (s.length < 2) return;
    var svg = wrap.querySelector("svg"), tip = wrap.querySelector(".tip");
    var kur = wrap.querySelector(".kursor"), lap = wrap.querySelector(".lapacz");
    if (!svg || !tip || !kur || !lap) return;
    var G = geoWykresu(s);

    var vals = [];
    s.forEach(function (p) { [p.temp_c, p.feels, p.wbgt].forEach(function (v) { if (v != null) vals.push(v); }); });
    var zz = ((d.modele || {}).zespol || {}).godziny || [];
    zz.forEach(function (g) { vals.push(g.temp_p10); vals.push(g.temp_p90); });
    var lo = Math.floor(Math.min.apply(null, vals) - 1.5);
    var hi = Math.ceil(Math.max.apply(null, vals) + 1.5);
    if (hi - lo < 6) hi = lo + 6;
    var Y = function (v) { return G.y1 - (v - lo) / (hi - lo) * (G.y1 - G.y0); };

    function schowaj() { kur.style.display = "none"; tip.style.display = "none"; }

    function ruch(ev) {
      var r = svg.getBoundingClientRect();
      var cx = (ev.touches && ev.touches[0] ? ev.touches[0].clientX : ev.clientX) - r.left;
      var vx = cx / r.width * G.W;
      if (vx < G.x0 - 2 || vx > G.x1 + 2) { schowaj(); return; }
      var km = G.kmA + (vx - G.x0) / (G.x1 - G.x0) * G.kmSpan;
      var p = najblizszy(s, km);
      var px = G.X(p.km);
      kur.style.display = "";
      kur.setAttribute("transform", "translate(" + px.toFixed(1) + ",0)");
      var kolo = kur.querySelector("circle");
      if (kolo) kolo.setAttribute("cy", Y(p.temp_c).toFixed(1));

      var w = [];
      w.push("<b>km " + n(p.km, 1) + " · " + esc(p.eta || "") + "</b>");
      w.push("temperatura <b>" + n(p.temp_c) + " °C</b>");
      if (p.feels != null) w.push("odczuwalna <b>" + n(p.feels) + " °C</b>");
      if (p.wbgt != null) w.push("WBGT <b>" + n(p.wbgt) + " °C</b>");
      if (p.rh_pct != null) w.push("wilgotność " + n(p.rh_pct, 0) + "%");
      if (p.chmury_pct != null) w.push("zachmurzenie " + n(p.chmury_pct, 0) + "%");
      w.push("opad " + n(p.opad_mm) + " mm/h" + (p.opad_prob != null ? " (" + p.opad_prob + "%)" : ""));
      if (p.wiatr_ms != null) w.push("wiatr " + n(p.wiatr_ms) + " m/s, " + wiatrTxt(p.wiatr_wzdluz_ms));
      if (p.porywy_ms != null) w.push("porywy " + n(p.porywy_ms) + " m/s");
      if (p.surface) w.push("nawierzchnia: " + esc(p.surface));
      tip.innerHTML = w.join("<br>");
      tip.style.display = "block";
      var lewo = (px / G.W) * r.width;
      var szer = tip.offsetWidth || 190;
      tip.style.left = Math.max(2, Math.min(r.width - szer - 2, lewo + 14)) + "px";
      tip.style.top = "8px";
    }

    lap.addEventListener("mousemove", ruch);
    lap.addEventListener("touchstart", ruch, { passive: true });
    lap.addEventListener("touchmove", ruch, { passive: true });
    svg.addEventListener("mouseleave", schowaj);
  }

  function legendaHTML() {
    return '<div class="legend">' +
      '<span><i style="background:' + KOL.temp + '"></i>temperatura</span>' +
      '<span><i style="background:' + KOL.feels + '"></i>odczuwalna</span>' +
      '<span><i style="background:' + KOL.wbgt + '"></i>WBGT (obciążenie cieplne)</span>' +
      '<span><i style="background:' + KOL.opad + '"></i>opad w mm (słupki)</span>' +
      '<span><i class="band" style="background:' + KOL.opad + '"></i>szansa opadu (tło pasa)</span>' +
      '<span><i class="band" style="background:' + KOL.temp + '"></i>rozrzut zespołu p10–p90</span>' +
      '<span><i style="background:var(--good)"></i>wiatr z tyłu &nbsp;<i style="background:var(--bad)"></i>w czoło</span>' +
      '<span><i class="band" style="background:#5b6670;opacity:.7"></i>zachmurzenie (pas u góry)</span>' +
      "</div>";
  }

  /* ---------------- zgodnosc modeli: tekst, bez grafiki ----------------
     Wczesniej byly tu skale z kropkami. Wymagaly instrukcji obslugi, wiec zostaly
     zastapione zdaniami: co porownano, jak bardzo sie rozjezdza, co z tego wynika. */
  function modeleHTML(d) {
    var mo = d.modele || {};
    if (mo.status !== "OK") {
      return '<p class="note">Porównanie modeli niedostępne' +
        (mo.powod ? ": " + esc(mo.powod) : "") + ".</p>";
    }
    var por = mo.porownanie || {}, opis = por.modele_opis || {}, kan = mo.kanon || {};
    var hor = por.horyzont || {};
    var uzyte = por.modele_uzyte || Object.keys(opis);
    var h = "";

    // 1. czym policzono i co z czym porownano
    var nazwy = uzyte.map(function (k) {
      return esc((opis[k] || {}).nazwa || k) + " " + n((opis[k] || {}).siatka_km) + " km";
    }).join(", ");
    h += '<p class="note" style="margin:0 0 6px">Policzone modelem <b>' + esc(kan.nazwa || "?") +
      "</b> (" + n(kan.siatka_km) + " km" + (kan.dostawca ? ", " + esc(kan.dostawca) : "") + "). " +
      esc(kan.powod || "") + ".</p>";
    h += '<p class="note" style="margin:0 0 6px">Porównane z: ' + nazwy + ". " +
      (hor.opis ? esc(hor.opis) : "") + "</p>";

    // 2. jak bardzo sie rozjezdzaja - jedno zdanie z liczbami
    var pk = por.punkty || [];
    if (pk.length) {
      var kawalki = pk.map(function (w) {
        return esc(w.nazwa || "") + " " + n(w.temp_rozrzut) + " °C";
      }).join(", ");
      h += '<p class="note" style="margin:0 0 6px"><b>Rozstęp między modelami</b> (różnica ' +
        "między najcieplejszym a najzimniejszym w danym punkcie): " + kawalki +
        (por.rozrzut_max_c != null ? "; najwięcej " + n(por.rozrzut_max_c) + " °C" : "") + ".</p>";
    }

    // 3. zespol - osobna wielkosc, wiec osobne zdanie
    var z = mo.zespol;
    if (z && (z.godziny || []).length) {
      var w2 = z.godziny.map(function (g) {
        return esc(g.godzina) + " " + n(g.temp_p10) + "–" + n(g.temp_p90) + " °C";
      }).join(", ");
      h += '<p class="note" style="margin:0 0 6px"><b>Rozrzut zespołu</b> (' + z.czlonkow +
        " wariantów samego " + esc(z.model || "ECMWF") + ", czyli niepewność wewnątrz " +
        "jednej prognozy — co innego niż rozstęp wyżej): " + w2 + ".</p>";
    }

    // 4. ocena Alberta
    var oc = mo.ocena;
    if (oc && oc.wniosek) {
      h += '<div class="ocena"><span class="zg ' + esc(oc.zgoda || "") + '">zgodność ' +
        esc(oc.zgoda || "?") + "</span><p>" + esc(oc.wniosek) + "</p>" +
        '<div class="aut">ocena: Albert</div></div>';
    } else if (mo.ocena_powod) {
      h += '<p class="note">Albert nie wydał oceny: ' + esc(mo.ocena_powod) + "</p>";
    }
    return '<div class="mods">' + h + "</div>";
  }

  /* ---------------- karta dnia ---------------- */
  function alertHTML(a) {
    var t = [];
    if (a.km_od != null) t.push("km " + n(a.km_od, 0) + "–" + n(a.km_do, 0));
    if (a.eta_od) t.push(a.eta_od + "–" + a.eta_do);
    if (a.minuty != null) t.push(minTxt(a.minuty));
    if (a.wbgt_max != null) t.push("WBGT " + n(a.wbgt_max) + " °C");
    if (a.opad_max_mm != null && a.opad_max_mm > 0) t.push("opad do " + n(a.opad_max_mm) + " mm/h");
    if (a.prawdopod != null) t.push(a.prawdopod + "% szans");
    if (a.typ === "deszcz" && !(a.opad_max_mm > 0)) {
      t.push("modele nie prognozują konkretnej ilości — to ryzyko, nie zapowiedź opadu");
    }
    if (a.cape_max != null) t.push("CAPE " + Math.round(a.cape_max));
    if (a.porywy_max_ms != null) t.push("porywy " + n(a.porywy_max_ms) + " m/s");
    if (a.utci_avg != null) t.push("odczuwalna " + n(a.utci_avg) + " °C");
    if (a.kategoria) t.push(esc(a.kategoria));
    if (a.opis) t.push(esc(a.opis));
    return '<div class="al ' + esc(String(a.severity || "").replace(/-/g, "")) + '"><b>' +
      esc(a.severity || "") + " " + esc(a.typ || "") + "</b><span>" + t.join(" · ") + "</span></div>";
  }

  function kafle(d) {
    var p = d.podsumowanie || {}, sl = d.slonce || {};
    function k(lab, val, sub, cls) {
      return '<div class="card' + (cls ? " " + cls : "") + '"><div class="lab">' + lab +
        '</div><div class="val">' + val + "</div>" + (sub ? '<div class="sub">' + sub + "</div>" : "") + "</div>";
    }
    var wet = ((p.opad_mm || 0) >= 0.5 || (p.opad_prob_max || 0) >= 40) ? "wet" : "";
    var hot = (p.wbgt_exceed != null && p.wbgt_exceed > 0) ? "hot" : "";
    return '<div class="cards">' +
      k("Temperatura", n(p.temp_min) + "–" + n(p.temp_max) + " <small>°C</small>", "średnio " + n(p.temp_sr)) +
      k("Odczuwalna", n(p.odczuwalna_min) + "–" + n(p.odczuwalna_max) + " <small>°C</small>",
        "temp + wilgotność + wiatr + słońce") +
      k("Wilgotność", n(p.rh_min, 0) + "–" + n(p.rh_max, 0) + " <small>%</small>", "średnio " + n(p.rh_sr, 0) + "%") +
      k("Opad", (p.opad_mm > 0 ? n(p.opad_mm) + " <small>mm</small>"
        : (p.opad_prob_max >= 30 ? "0 <small>mm, ale " + p.opad_prob_max + "% szans</small>"
          : "0 <small>mm</small>")),
        (p.opad_mm > 0
          ? ("szansa do " + (p.opad_prob_max == null ? "b/d" : p.opad_prob_max + "%") +
            (p.minuty_deszczu ? " · " + minTxt(p.minuty_deszczu) + " w deszczu" : ""))
          : (p.opad_prob_max >= 30
            ? "modele nie prognozują ilości — możliwy przelotny deszcz"
            : "sucho")), wet) +
      k("Wiatr", n(p.wiatr_sr_ms) + " <small>m/s śr.</small>",
        wiatrTxt(p.wiatr_wzdluz_sr_ms) + " · porywy do " + n(p.porywy_max_ms)) +
      k("WBGT max", n(p.wbgt_max) + " <small>°C</small>",
        "km " + n(p.wbgt_km, 0) + " o " + (p.wbgt_eta || "?") +
        (p.wbgt_exceed > 0 ? " · ponad limit o " + n(p.wbgt_exceed) : " · w limicie"), hot) +
      k("Słońce", (sl.wschod || "?") + "–" + (sl.zachod || "?"),
        "dzień " + n(sl.dzien_h) + " h · słońca " + n(sl.sloneczne_h) + " h" +
        (sl.uv_max != null ? " · UV " + n(sl.uv_max) : "")) +
      k("Na trasie", (p.eta_od || "?") + "–" + (p.eta_do || "?"),
        minTxt(p.minuty) + " jazdy" +
        ((d.postoje && d.postoje.liczba) ? " + " + d.postoje.liczba + " × " +
          n(d.postoje.minut_kazdy, 0) + " min postoju" : "") +
        " · " + n(p.km_od, 0) + "–" + n(p.km_do, 0) + " km") +
      "</div>";
  }

  function tabela30(d, i) {
    var t = d.tabela_30min || [];
    if (!t.length) return "";
    if (!rozwin[i]) {
      return '<button class="foldbtn" data-fold="' + i + '">Pokaż tabelę co 30 minut (' +
        t.length + " wierszy) ▾</button>";
    }
    var h = '<button class="foldbtn" data-fold="' + i + '">Ukryj tabelę ▴</button>' +
      '<table class="t30"><thead><tr><th>Godz.</th><th>km</th><th>Temp.</th><th>Odczuw.</th>' +
      "<th>Wilg.</th><th>WBGT</th><th>Opad</th><th>Wiatr wzdłuż</th><th>Burza</th></tr></thead><tbody>";
    t.forEach(function (r) {
      var op = r.opad || {}, bu = r.burza || {}, oc = r.odczuwalna || {};
      h += "<tr><td>" + esc(r.okno || "") + "</td><td>" + n(r.km_od, 0) + "–" + n(r.km_do, 0) + "</td>" +
        "<td>" + n(r.temp_c) + "</td><td>" + n(oc.srednia, 0) + "</td><td>" + n(r.rh_pct, 0) + "%</td>" +
        '<td' + ((r.wbgt_max != null && r.wbgt_max >= 26) ? ' class="hot"' : "") + ">" + n(r.wbgt_max) + "</td>" +
        '<td' + (((op.mm || 0) >= 0.5 || (op.prob || 0) >= 40) ? ' class="rainy"' : "") + ">" +
        n(op.mm) + " mm" + (op.prob != null ? " / " + op.prob + "%" : "") + "</td>" +
        "<td>" + (r.wiatr_wzdluz_ms == null ? "b/d" : n(r.wiatr_wzdluz_ms)) + "</td>" +
        "<td>" + (bu.poziom ? esc(bu.poziom) : "–") + "</td></tr>";
    });
    return h + "</tbody></table>";
  }

  function klimatHTML(d) {
    var k = d.klimat || {}, t = k.temp || {}, o = k.opad || {}, w = k.wiatr || {},
      r = k.rh || {}, po = k.podstawa || {};
    function c(lab, val, sub, cls) {
      return '<div class="card' + (cls ? " " + cls : "") + '"><div class="lab">' + lab +
        '</div><div class="val">' + val + "</div>" + (sub ? '<div class="sub">' + sub + "</div>" : "") + "</div>";
    }
    var h = '<p class="note" style="margin:0 0 8px"><b>To nie jest prognoza.</b> ' +
      esc(d.powod_klimatu || "") + " Poniżej klimat z ostatnich " + (po.lata || "?") + " lat (±" +
      (po.okno_dni || "?") + " dni wokół tej daty, " + (po.obserwacji_dni || "?") + " dni obserwacji, ERA5).</p>";
    h += '<div class="cards">' +
      c("Temp. maks.", n(t.max_sr) + " <small>°C śr.</small>",
        "co 10. dzień powyżej " + n(t.max_p90) + " · rekord " + n(t.max_rekord)) +
      c("Temp. min.", n(t.min_sr) + " <small>°C śr.</small>",
        "co 10. dzień poniżej " + n(t.min_p10) + " · rekord " + n(t.min_rekord)) +
      c("Cała doba", n(t.sr) + " <small>°C śr.</small>", "średnia dobowa") +
      c("Szansa opadu", (o.szansa_dnia_z_opadem_pct == null ? "b/d" : o.szansa_dnia_z_opadem_pct + " <small>%</small>"),
        "dzień z opadem ≥ 1 mm", (o.szansa_dnia_z_opadem_pct >= 35 ? "wet" : "")) +
      c("Opad dobowy", n(o.mm_dobowe_sr) + " <small>mm śr.</small>",
        "co 10. dzień powyżej " + n(o.mm_dobowe_p90) + " mm · " + n(o.godzin_opadu_sr) + " h padania") +
      c("Wilgotność", n(r.sr, 0) + " <small>% śr.</small>", "p90 " + n(r.p90, 0) + "%") +
      c("Wiatr", n(w.max_dobowy_sr_ms) + " <small>m/s</small>",
        "maks. dobowy · p90 " + n(w.max_dobowy_p90_ms) + " · porywy p90 " + n(w.porywy_p90_ms)) +
      c("Słońce", n((k.slonce || {}).radiacja_mj_sr) + " <small>MJ/m²</small>", "dobowa suma promieniowania") +
      "</div>";
    if ((k.uwagi || []).length) {
      h += '<div class="caveats"><ul>';
      k.uwagi.forEach(function (u) { h += "<li>" + esc(u) + "</li>"; });
      h += "</ul></div>";
    }
    return h;
  }

  function dayHTML(i) {
    var d = dni[i];
    var h = '<div class="day" id="day' + i + '"><div class="day-h"><b>Dzień ' + (i + 1) + "</b>";
    if (d && d.ok) h += '<span class="km">' + n(d.od_km, 0) + "–" + n(d.do_km, 0) + " km · " + esc(d.data) + "</span>";
    else h += '<span class="km">' + esc(dataDnia(i)) + "</span>";
    if (d && d.ok && d.tryb === "klimat") h += '<span class="tag klimat">klimat</span>';
    else if (d && d.ok) h += '<span class="tag">prognoza</span>';
    else if (d && !d.ok) h += '<span class="tag brak">brak danych</span>';
    h += '<button class="day-btn" data-day="' + i + '"' + ((laduje[i] || trwa) ? " disabled" : "") + ">" +
      (laduje[i] ? "liczę…" : (d ? "Przelicz" : "Policz")) + "</button></div>";

    if (laduje[i]) return h + '<p class="note">Liczę pogodę dla tego dnia…</p></div>';
    if (!d) return h + '<p class="note">Jeszcze nie policzone.</p></div>';
    if (!d.ok) return h + '<p class="err">' + esc(d.powod || "Brak danych.") + "</p></div>";

    if (d.tryb === "klimat") return h + klimatHTML(d) + "</div>";

    h += kafle(d);
    h += '<div class="sec">Przebieg dnia</div>' + chartSVG(d, i) + legendaHTML();
    h += '<div class="sec">Ostrzeżenia</div>';
    if ((d.alerty || []).length) d.alerty.forEach(function (a) { h += alertHTML(a); });
    else h += '<div class="al OK"><b>brak ostrzeżeń</b><span>żaden próg upału, deszczu, burzy ani zimna nie został przekroczony</span></div>';
    h += '<div class="sec">Zgodność modeli</div>' + modeleHTML(d);
    h += '<div class="sec">Szczegóły</div>' + tabela30(d, i);
    if ((d.caveats || []).length) {
      h += '<div class="caveats"><ul>';
      d.caveats.forEach(function (c) { h += "<li>" + esc(c) + "</li>"; });
      h += "</ul></div>";
    }
    return h + "</div>";
  }

  /* ---------------- os wyprawy ---------------- */
  function oswHTML() {
    var maj = [], mij = [];
    for (var i = 0; i < NDAYS; i++) {
      var d = dni[i];
      if (d && d.ok && d.podsumowanie) { maj.push(d.podsumowanie.temp_max); mij.push(d.podsumowanie.temp_min); }
    }
    var lo = mij.length ? Math.min.apply(null, mij) : null;
    var hi = maj.length ? Math.max.apply(null, maj) : null;

    var h = '<div class="osw"><h3>Cała wyprawa</h3>' +
      '<p class="lead">Pasek pokazuje zakres temperatur dnia na tle całej wyprawy — ' +
      'położenie mówi, jak ciepły jest dzień na tle pozostałych, a kolor ile to znaczy ' +
      'dla jazdy. Kliknij dzień, żeby przejść do szczegółów.</p>' + skalaLegenda() +
      '<div class="osw-grid">';
    for (var j = 0; j < NDAYS; j++) {
      var dd = dni[j], p = (dd && dd.ok) ? (dd.podsumowanie || null) : null;
      h += '<div class="osw-day" data-goto="' + j + '"><div class="osw-lab"><b>Dzień ' + (j + 1) + "</b><span>" +
        esc(dataDnia(j)) + (dd && dd.ok ? " · " + n(dd.od_km, 0) + "–" + n(dd.do_km, 0) + " km" : "") +
        "</span></div>";
      h += '<div class="osw-bar">';
      if (p && lo != null && hi != null && hi > lo) {
        var a = (p.temp_min - lo) / (hi - lo) * 100, b = (p.temp_max - lo) / (hi - lo) * 100;
        var grad = "linear-gradient(90deg," + kolorTemp(p.temp_min) + "," + kolorTemp(p.temp_max) + ")";
        h += '<i style="left:' + a.toFixed(1) + "%;width:" + Math.max(3, b - a).toFixed(1) +
          "%;background:" + grad + '"></i><em>' + n(p.temp_min, 0) + "–" + n(p.temp_max, 0) + " °C</em>";
      } else if (dd && dd.ok && dd.tryb === "klimat") {
        var kt = (dd.klimat || {}).temp || {};
        h += '<em style="color:var(--ink2);text-shadow:none">klimat: ' + n(kt.min_sr, 0) + "–" +
          n(kt.max_sr, 0) + " °C</em>";
      } else {
        var pw = (dd && dd.powod) ? String(dd.powod) : "";
        if (pw.length > 90) pw = pw.slice(0, 88) + "…";
        h += '<em style="color:' + (dd ? "var(--bad)" : "var(--muted)") + ';text-shadow:none">' +
          (dd ? ("nie policzono" + (pw ? ": " + esc(pw) : " — spróbuj ponownie")) : "nie policzone") +
          "</em>";
      }
      h += "</div>";
      h += '<div class="osw-flags">';
      if (p) {
        var typy = {};
        (dd.alerty || []).forEach(function (a) {
          var sv = String(a.severity || "");
          // Deszcz z zerowa iloscia to RYZYKO, nie opad -- inaczej plakietka klamie.
          var klucz = (a.typ === "deszcz" && !(a.opad_max_mm > 0)) ? "ryzyko deszczu" : a.typ;
          if (!typy[klucz] || sv.indexOf("ALARM") >= 0) typy[klucz] = sv;
        });
        var ile = 0;
        Object.keys(typy).forEach(function (t) {
          var kl = (t === "ryzyko deszczu") ? "deszcz" : t;
          h += '<span class="flag ' + esc(kl) + '">' + esc(t) + "</span>"; ile++;
        });
        if (!ile) h += '<span class="flag ok">czysto</span>';
      } else if (dd && dd.ok && dd.tryb === "klimat") {
        h += '<span class="flag brak">bez prognozy</span>';
      }
      h += "</div></div>";
    }
    return h + "</div></div>";
  }

  function skalaLegenda() {
    var stops = SKALA_T.map(function (x) { return kolorTemp(x[0]); }).join(",");
    return '<div class="skala"><i style="background:linear-gradient(90deg,' + stops + ')"></i>' +
      "<span>chłodno 5°</span><span>komfort 20°</span><span>ciepło 25°</span>" +
      "<span>gorąco 29°</span><span>upał 33°+</span></div>";
  }

  /* ---------------- render + dane ---------------- */
  function render() {
    var h = oswHTML();
    for (var i = 0; i < NDAYS; i++) h += dayHTML(i);
    $("wrap").innerHTML = h;

    Array.prototype.forEach.call(document.querySelectorAll(".day-btn"), function (b) {
      b.onclick = function () { pobierz(parseInt(this.getAttribute("data-day"), 10), true); };
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-fold]"), function (b) {
      b.onclick = function () {
        var k = parseInt(this.getAttribute("data-fold"), 10);
        rozwin[k] = !rozwin[k]; render();
        var el = document.getElementById("day" + k); if (el) el.scrollIntoView({ block: "nearest" });
      };
    });
    for (var pi = 0; pi < NDAYS; pi++) podepnijWykres(pi);
    Array.prototype.forEach.call(document.querySelectorAll("[data-goto]"), function (b) {
      b.onclick = function () {
        var el = document.getElementById("day" + this.getAttribute("data-goto"));
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      };
    });
  }

  function pobierz(i, rebuild, cb) {
    if (!RID || !$("startdate").value) { return cb && cb(); }
    laduje[i] = true; render();
    var url = "/api/planer/pogoda?route_id=" + encodeURIComponent(RID) +
      "&start=" + encodeURIComponent($("startdate").value) +
      "&day=" + (i + 1) + "&cuts=" + encodeURIComponent(CUTS) +
      "&start_time=" + encodeURIComponent($("starttime").value || "09:00") +
      (rebuild ? "&rebuild=1" : "");
    fetch(url).then(function (r) { return r.json(); }).then(function (j) {
      dni[i] = j; laduje[i] = false; render(); if (cb) cb();
    }).catch(function (e) {
      dni[i] = { ok: false, powod: "Błąd połączenia: " + e };
      laduje[i] = false; render(); if (cb) cb();
    });
  }

  function pobierzWszystkie(rebuild) {
    if (trwa) return;
    trwa = true;
    $("msg").textContent = "Liczę dzień 1 z " + NDAYS + "…";
    var i = 0;
    (function krok() {
      if (i >= NDAYS) {
        trwa = false; $("msg").textContent = "Gotowe: " + NDAYS + (NDAYS === 1 ? " dzień." : " dni.");
        render(); return;
      }
      var k = i++;
      $("msg").textContent = "Liczę dzień " + (k + 1) + " z " + NDAYS + "…";
      pobierz(k, rebuild, krok);
    })();
  }

  function wyslij() {
    var to = ($("mailto").value || "").trim();
    if (!to) { $("msg").textContent = "Podaj adres e-mail."; return; }
    var gotowe = Object.keys(dni).filter(function (k) { return dni[k] && dni[k].ok; }).length;
    if (!gotowe) { $("msg").textContent = "Najpierw policz pogodę — nie ma czego wysyłać."; return; }
    $("send").disabled = true; $("msg").textContent = "Wysyłam raport…";
    fetch("/api/pogoda/mail", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        route_id: RID, start: $("startdate").value, cuts: CUTS,
        start_time: $("starttime").value || "09:00", days: NDAYS, to: to
      })
    }).then(function (r) { return r.json(); }).then(function (j) {
      $("send").disabled = false;
      $("msg").textContent = j && j.ok ? ("Wysłano na " + to + ".") :
        ("Nie wysłano: " + ((j && j.powod) || "nieznany błąd"));
    }).catch(function (e) {
      $("send").disabled = false; $("msg").textContent = "Nie wysłano: " + e;
    });
  }

  function start() {
    if (!RID) {
      $("route-name").textContent = "nie wybrano trasy";
      $("route-meta").textContent = "— otwórz przez planer wyprawy.";
      $("boot").textContent = "Brak trasy w adresie. Wróć do planera wyprawy i wejdź tu przyciskiem.";
      return;
    }
    var sd = q.get("start") || "";
    if (sd) $("startdate").value = sd;
    var tm = q.get("time") || "";
    if (tm) $("starttime").value = tm;

    fetch("/api/routes/ready").then(function (r) { return r.json(); }).then(function (d) {
      META = (d.routes || []).filter(function (x) { return x.route_id === RID; })[0] || null;
      $("route-name").textContent = META ? META.name : ("trasa " + RID);
      $("route-meta").textContent = (META && META.distance_km != null)
        ? ("· " + META.distance_km + " km · " + NDAYS + (NDAYS === 1 ? " dzień" : " dni")) : "";
      // Termin z KALENDARZA. Data w nazwie trasy to data jej utworzenia,
      // a nie planowanego wyjazdu - branie jej stad psulo prognoze.
      if (!$("startdate").value) {
        fetch("/api/planer/termin?route_id=" + encodeURIComponent(RID),
              { credentials: "same-origin", cache: "no-store" })
          .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
          .then(function (t) {
            if (t && t.start) $("startdate").value = t.start;
            if (t && t.source === "kalendarz" && t.event) {
              var mm = $("route-meta");
              if (mm) mm.textContent = (mm.textContent || "") + " · termin z kalendarza";
            }
            po();
          })
          .catch(function () { po(); });
        return;
      }
      po();
    }).catch(function () { $("route-name").textContent = "trasa " + RID; po(); });

    function po() {
      $("bar").style.display = "";
      $("calc").onclick = function () { pobierzWszystkie(false); };
      $("recalc").onclick = function () { pobierzWszystkie(true); };
      $("send").onclick = wyslij;
      $("starttime").onchange = function () { dni = {}; render(); };
      $("startdate").onchange = function () { dni = {}; render(); };
      render();
      if ($("startdate").value) pobierzWszystkie(false);
      else $("msg").textContent = "Ustaw datę startu, żeby policzyć pogodę.";
    }
  }

  document.addEventListener("DOMContentLoaded", start);
})();
