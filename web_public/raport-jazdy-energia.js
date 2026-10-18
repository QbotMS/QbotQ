/* raport-jazdy-energia.js (2026-10-18): karta "Energia na jeździe" w sekcji "Ciało tego dnia" raportu z jazdy.
   Dane: GET /api/ride-report/energia?ride= - te same fakty, które dostaje AI raportu
   (qbot3/rides/ride_report_facts.energy_block: wydatek, spalone węglowodany, jedzenie przed i w trakcie,
   glikogen start/meta wg modelu QBota, spadek mocy na ostatnich 25% jazdy).
   Wstawia się w <div id="cialo-energia"> renderowany przez raport-jazdy2-dane.js. */
(function () {
"use strict";
var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
var n = function (x, d) { return x == null || isNaN(x) ? "—" : Number(x).toLocaleString("pl-PL", { maximumFractionDigits: d || 0, minimumFractionDigits: d || 0 }); };
function card(e, f) {
  var lp = e.glikogen_meta_pct, rate = "", cls = "";
  if (lp != null) { if (lp >= 60) { rate = "zapas OK"; cls = "good"; } else if (lp >= 40) { rate = "zapas obniżony"; cls = "warn"; } else { rate = "zapas niski"; cls = "bad"; } }
  var num = e.glikogen_start_pct != null
    ? n(e.glikogen_start_pct) + "% → " + n(lp) + "% <small>glikogen start → meta</small>"
    : n(e.spalone_wegle_g) + " g <small>spalone węglowodany</small>";
  var t = "Spaliłeś ok. " + n(e.wydatek_kcal) + " kcal, z tego ~" + n(e.spalone_wegle_g) + " g węglowodanów. Zjadłeś " +
    n(e.zjedzone_przed_3h_wegle_g) + " g w 3 h przed startem i " + n(e.w_trakcie_wegle_g) + " g w trakcie" +
    (f.plan_wegle_g_h ? " (" + n(f.w_trakcie_wegle_g_h) + " g/h przy planie " + n(f.plan_wegle_g_h) + " g/h)" : "") + ". ";
  if (f.w_trakcie_plyny_l != null) t += "Wpisane płyny w trakcie: " + n(f.w_trakcie_plyny_l, 1) + " l. ";
  var k = e.koncowka;
  if (k && k.spadek_mocy_pct != null) {
    t += "Ostatnie 25% jazdy: moc " + (k.spadek_mocy_pct > 0 ? "−" : "+") + n(Math.abs(k.spadek_mocy_pct)) + "%" +
      (k.spadek_ef_pct != null ? ", moc na uderzenie serca " + (k.spadek_ef_pct > 0 ? "−" : "+") + n(Math.abs(k.spadek_ef_pct)) + "%" : "") +
      " wobec wcześniejszej części. ";
  }
  t += '<span style="color:var(--muted)">Szacunek modelu glikogenu QBota' + (e.pewnosc_startu ? " (pewność stanu startowego: " + esc(e.pewnosc_startu) + ")" : "") +
    ", pojemność " + n(e.pojemnosc_g) + " g.</span>";
  return '<div class="it"><div class="h"><b>Energia na jeździe</b>' + (rate ? '<span class="rate ' + cls + '">' + rate + "</span>" : "") +
    '</div><div class="num">' + num + "</div><p>" + t + "</p></div>";
}
function fill(el) {
  var sel = document.getElementById("ridesel"), rk = sel && sel.value;
  if (!rk || el.dataset.rk === rk) return;
  el.dataset.rk = rk;
  fetch("/api/ride-report/energia?ride=" + encodeURIComponent(rk), { credentials: "same-origin", cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { if (!j || el.dataset.rk !== rk) return; el.innerHTML = j.energia ? card(j.energia, j.jedzenie || {}) : ""; })
    .catch(function () {});
}
new MutationObserver(function () { var el = document.getElementById("cialo-energia"); if (el) fill(el); })
  .observe(document.body, { childList: true, subtree: true });
})();
