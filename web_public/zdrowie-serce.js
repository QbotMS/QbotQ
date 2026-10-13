/* Zdrowie -> Serce: dodatki do forma-serce.js (2026-10-12): HRV (norma z roku vs 28 dni, wykres) i serce a jedzenie/waga.
   Dane: GET /api/jedzenie/heart_plus (qbot_food_api.py). docs/BROKUL.md */
(function () {
  "use strict";
  var root = document.getElementById("serce-plus"); if (!root) return;
  var done = false;
  function n1(v) { return v == null ? "–" : (Math.round(v * 10) / 10).toLocaleString("pl-PL"); }
  function sg(v) { return v == null ? "–" : (v > 0 ? "+" : "") + n1(v); }
  function dm(iso) { return iso.slice(8, 10) + "." + iso.slice(5, 7); }
  function chart(s, norm) {
    if (s.length < 10) return "";
    var W = 900, H = 200, pl = 36, pr = 12, pt = 10, pb = 22, ys = s.map(function (p) { return p[1]; }), y0 = Math.floor(Math.min.apply(null, ys) - 3), y1 = Math.ceil(Math.max.apply(null, ys) + 3);
    var t0 = Date.parse(s[0][0]), t1 = Date.parse(s[s.length - 1][0]);
    function X(d) { return pl + (Date.parse(d) - t0) / Math.max(1, t1 - t0) * (W - pl - pr); } function Y(v) { return pt + (y1 - v) / (y1 - y0) * (H - pt - pb); }
    var ma = s.map(function (p, i) { var a = s.slice(Math.max(0, i - 6), i + 1); return [p[0], a.reduce(function (z, q) { return z + q[1]; }, 0) / a.length]; });
    var g = "<svg viewBox='0 0 " + W + " " + H + "' style='width:100%;height:auto;display:block' role='img' aria-label='HRV nocne'>";
    for (var v = Math.ceil(y0 / 10) * 10; v <= y1; v += 10) g += "<line x1='" + pl + "' x2='" + (W - pr) + "' y1='" + Y(v).toFixed(1) + "' y2='" + Y(v).toFixed(1) + "' stroke='var(--line)'/><text x='" + (pl - 4) + "' y='" + (Y(v) + 3.5).toFixed(1) + "' font-size='10' text-anchor='end' fill='var(--muted)'>" + v + "</text>";
    s.forEach(function (p) { g += "<circle cx='" + X(p[0]).toFixed(1) + "' cy='" + Y(p[1]).toFixed(1) + "' r='1.6' fill='#a78bfa' opacity='.45'/>"; });
    g += "<path d='M" + ma.map(function (p) { return X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1); }).join(" L") + "' fill='none' stroke='#a78bfa' stroke-width='2'/>";
    if (norm) g += "<line x1='" + pl + "' x2='" + (W - pr) + "' y1='" + Y(norm).toFixed(1) + "' y2='" + Y(norm).toFixed(1) + "' stroke='#a78bfa' stroke-dasharray='5 4' opacity='.8'/>";
    [0, Math.floor(s.length / 2), s.length - 1].forEach(function (i) { g += "<text x='" + X(s[i][0]).toFixed(1) + "' y='" + (H - 6) + "' font-size='10' text-anchor='middle' fill='var(--muted)'>" + dm(s[i][0]) + "</text>"; });
    return g + "</svg>";
  }
  function load() {
    if (done) return; done = true;
    root.innerHTML = "<div class='muted'>ładuję HRV…</div>";
    fetch("/api/jedzenie/heart_plus", { credentials: "same-origin" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(function (x) {
      var h = x.hrv, L = x.links, cs = L.cisnienie, hd = L.hrv_po_deficycie;
      var col = { good: "var(--good)", warn: "var(--accent)", bad: "var(--bad)" }[h.status] || "var(--muted)";
      var out = "<div class='card'><div class='cardhead'><p class='lbl'><span class='tip' tabindex='0' data-tip='HRV nocne z zegarka. Linia: średnia 7 dni; przerywana: Twoja norma z roku (mediana dni 29–365 wstecz). Spadek o ponad 7% = uwaga, ponad 12% = wyraźnie.'>HRV (zmienność rytmu serca)</span></p>" +
        "<span class='sub'>ostatnie 28 dni: <b style='color:" + col + "'>" + n1(h.recent) + " ms</b> · norma " + n1(h.norm) + " (" + sg(h.pct) + "%)</span></div>" + chart(h.series, h.norm) + "</div>";
      var rows = [], al = L.alkohol || {};
      if (al.n) rows.push("🍷 Noc po alkoholu (" + al.n + " wieczorów w roku): HRV <b>" + sg(al.hrv) + " ms</b>, tętno spocz. <b>" + sg(al.rhr) + " bpm</b>, sen <b>" + sg(al.sen) + " pkt</b> vs Twoja norma" + (al.ostatni ? " <span class='muted'>(ostatnio " + dm(al.ostatni) + ")</span>" : "") + ". Te noce są wyłączone z analiz zależności.");
      else rows.push("🍷 Alkohol: brak wpisów w ostatnim roku – gdy wpiszesz (np. „piwo 0,5”), QBot policzy koszt takiego wieczoru i wyłączy noc po nim z analiz.");
      if (hd.n_duzy >= 3) rows.push("Dzień po <b>dużym deficycie</b> (> 700 kcal) HRV średnio <b>" + sg(hd.duzy) + " ms</b> od Twojej normy, po pozostałych dniach " + sg(hd.inne) + " ms <span class='muted'>(n " + hd.n_duzy + " / " + hd.n_inne + ")</span>.");
      else rows.push("HRV a deficyt: za mało zamkniętych dni z dużym deficytem (" + hd.n_duzy + ").");
      if (cs.sol.n_a >= 3 && cs.sol.n_b >= 3) rows.push("Ciśnienie rano po dniu z <b>dużą ilością soli z diety</b> (≥ 8 g): skurczowe średnio <b>" + cs.sol.a + "</b> vs " + cs.sol.b + " po pozostałych.");
      if (cs.deficyt.n_a >= 3 && cs.deficyt.n_b >= 3) rows.push("Ciśnienie rano po <b>deficycie</b> > 500 kcal: " + cs.deficyt.a + " vs " + cs.deficyt.b + ".");
      if (cs.pomiary_rano < 6) rows.push("Ciśnienie a sól, deficyt i wagę: za mało pomiarów (" + cs.pomiary_wszystkie + " w bazie, rano " + cs.pomiary_rano + "). Seria 7 dni ciśnienia rano da pierwszą odpowiedź – dieta daje ~10 g soli dziennie (norma 5 g).");
      out += "<div class='card'><div class='cardhead'><p class='lbl'>Serce a jedzenie i waga</p></div>" + rows.map(function (r) { return "<div class='s3row info'><span class='i'>·</span><span>" + r + "</span></div>"; }).join("") + "</div>";
      root.innerHTML = out;
    }).catch(function (e) { done = false; root.innerHTML = "<div class='card'>Nie udało się wczytać HRV: " + e.message + "</div>"; });
  }
  var btn = document.querySelector('#tabs button[data-t="serce"]'); if (btn) btn.addEventListener("click", load);
  if (location.hash === "#serce") load();
})();
