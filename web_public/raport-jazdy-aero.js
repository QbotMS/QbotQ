/* raport-jazdy-aero.js (2026-10-19): kafel "Aero (CdA)" w sekcji "Rower i napęd" raportu z jazdy (decyzja Michała).
   Dane: GET /api/forma/cda (Centrum CdA, fitmodel/cda.py summary) -- jazda z points (liczona), quality.excluded_rides (pominięta,
   z powodem), same_places (te same miejsca), bikes (typowe CdA roweru). Jazda bez wpisu: Centrum CdA liczy nowe jazdy w nocy.
   Wstawia się w <div id="rower-aero"> renderowany przez raport-jazdy2-dane.js. */
(function () {
"use strict";
var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
var f3 = function (x) { return x == null || isNaN(x) ? "—" : Number(x).toFixed(3).replace(".", ","); };
var pc = function (x) { return x == null || isNaN(x) ? null : (x > 0 ? "+" : "") + Math.round(100 * x).toString().replace("-", "−") + "%"; };
var CACHE = null;
function card(D, rk) {
  var link = ' <a href="/forma.html#cda" style="white-space:nowrap">Centrum CdA ›</a>';
  var p = (D.points || []).filter(function (x) { return x.id === rk; })[0];
  var ex = ((D.quality || {}).excluded_rides || []).filter(function (x) { return x.id === rk; })[0];
  if (!p && !ex) {
    return '<div class="it"><div class="h"><b>Aero (CdA)</b><span class="rate">jeszcze nie liczone</span></div>' +
      '<p>Centrum CdA nie ma tej jazdy: liczy jazdy z mocą od ' + esc(((D.quality || {}).since || "").split("-").reverse().join(".")) +
      ' (nowe — w nocy).' + link + '</p></div>';
  }
  if (!p) {
    return '<div class="it"><div class="h"><b>Aero (CdA)</b><span class="rate">pominięta</span></div>' +
      '<p>Ta jazda nie wchodzi do liczenia oporu: ' + esc(ex.reason || "brak danych") + '.' + link + '</p></div>';
  }
  var bk = (D.bikes || []).filter(function (b) { return b.bike === p.bike; })[0];
  var sp = ((D.same_places || {}).rides || []).filter(function (x) { return x.id === rk; })[0];
  var cls = { A: "good", B: "", C: "warn" }[p.q] || "";
  var num = f3(p.cda) + ' <small>m²' + (bk && bk.cda != null ? " · typowo " + esc(p.bike) + " " + f3(bk.cda) + " (" + pc(p.cda / bk.cda - 1) + ")" : "") + '</small>';
  var aw = Math.round(0.5 * 1.2 * p.cda * Math.pow(30 / 3.6, 3));
  var t = "Opór sylwetki z " + p.n + " płaskich, równych odcinków (wiatr policzony z jazdy" + (p.wind != null ? ": " + String(p.wind).replace(".", ",") + " m/s" : "") +
    "). Przy 30 km/h to ok. " + aw + " W na samo powietrze. ";
  if (p.q_why) t += "Słabsze strony: " + esc(p.q_why) + ". ";
  if (sp) {
    var a = pc(sp.asf), s = pc(sp.szu), parts = [];
    if (a) parts.push("asfalt " + a);
    if (s) parts.push("szuter " + s);
    if (parts.length) t += "W tych samych miejscach co inne jazdy: " + parts.join(", ") + " oporu" +
      (sp.szu != null && sp.szu >= 0.15 && (sp.asf == null || sp.asf < 0.05) ? " — ciężka droga?" : "") + ". ";
  }
  return '<div class="it"><div class="h"><b>Aero (CdA)</b>' + (p.q ? '<span class="rate ' + cls + '">jakość ' + esc(p.q) + "</span>" : "") +
    '</div><div class="num">' + num + "</div><p>" + t + link + "</p></div>";
}
function fill(el) {
  var sel = document.getElementById("ridesel"), rk = sel && sel.value;
  if (!rk || el.dataset.rk === rk) return;
  el.dataset.rk = rk;
  var go = function (D) { if (el.dataset.rk === rk) el.innerHTML = card(D, rk); };
  if (CACHE) { go(CACHE); return; }
  fetch("/api/forma/cda", { credentials: "same-origin", cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (D) { if (!D) return; CACHE = D; go(D); })
    .catch(function () {});
}
new MutationObserver(function () { var el = document.getElementById("rower-aero"); if (el) fill(el); })
  .observe(document.body, { childList: true, subtree: true });
})();
