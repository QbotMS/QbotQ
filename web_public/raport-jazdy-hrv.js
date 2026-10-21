/* raport-jazdy-hrv.js (21.10.2026, sesja hrv-e4-2110, TODO [HRV-JAZDA] Etap 4, makieta zaakceptowana 21.10):
   kafel "HRV z jazdy" w raporcie z jazdy, zaraz po "Moc na uderzenie serca" (raport wlasciwy i strona testowa).
   Dane: GET /api/ride-report/hrv?ride= (qbot_web.py; wynik fitmodel/hrv_ride.py, tabela qbot_v2.hrv_ride_result).
   Jazda bez pasa Polar H10 = brak kafla. Prog pokazywany tylko przy pewnosci sredniej/wysokiej (niska = ekstrapolacja).
   Dok.: docs/HRV_JAZDA.md, wiki forma/hrv-z-jazdy. */
(function () {
"use strict";
var f = function (x, k) { return x == null || isNaN(x) ? "—" : Number(x).toLocaleString("pl-PL", { minimumFractionDigits: k || 0, maximumFractionDigits: k || 0 }); };
var CONF = { wysoka: "pewność wysoka", srednia: "pewność średnia" };

function chart(w, dur) {
  var W = 640, H = 210, L = 34, R = 40, T = 10, B = 26, pw = W - L - R, ph = H - T - B;
  var x = function (t) { return L + pw * t / dur; };
  var ya = function (a) { return T + ph * (1 - (Math.min(1.8, Math.max(0.3, a)) - 0.3) / 1.5); };
  var yp = function (p) { return T + ph * (1 - Math.min(350, Math.max(0, p)) / 350); };
  var s = '<svg viewBox="0 0 ' + W + " " + H + '" style="width:100%;height:auto;display:block" role="img" aria-label="α1 i moc w czasie jazdy">';
  [0.5, 0.75, 1.0, 1.5].forEach(function (a) {
    s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + ya(a) + '" y2="' + ya(a) + '" stroke="currentColor" stroke-opacity="' + (a === 0.75 ? 0.55 : 0.12) + '"' + (a === 0.75 ? ' stroke-dasharray="5 4"' : "") + "/>";
    s += '<text x="' + (L - 4) + '" y="' + (ya(a) + 4) + '" font-size="10" text-anchor="end" fill="currentColor" opacity="0.6">' + f(a, 2) + "</text>";
  });
  s += '<text x="' + (W - R - 2) + '" y="' + (ya(0.75) - 4) + '" font-size="10" text-anchor="end" fill="currentColor" opacity="0.7">próg tlenowy α1 = 0,75</text>';
  var pts = w.filter(function (r) { return r[2] != null; }).map(function (r) { return x(r[0]) + "," + yp(r[2]); }).join(" ");
  s += '<polyline points="' + pts + '" fill="none" stroke="#9aa4b2" stroke-width="1.2" opacity="0.55"/>';
  [0, 100, 200, 300].forEach(function (p) { s += '<text x="' + (W - R + 4) + '" y="' + (yp(p) + 4) + '" font-size="10" fill="#9aa4b2">' + p + " W</text>"; });
  w.forEach(function (r) {
    var st = r[3] === 1;
    s += '<circle cx="' + x(r[0]) + '" cy="' + ya(r[1]) + '" r="' + (st ? 4 : 1.8) + '" fill="' + (st ? "#16a34a" : "#60a5fa") + '" opacity="' + (st ? 1 : 0.55) + '"/>';
  });
  for (var t = 0; t <= dur; t += 15) s += '<text x="' + x(t) + '" y="' + (H - 8) + '" font-size="10" text-anchor="middle" fill="currentColor" opacity="0.6">' + t + " min</text>";
  return s + "</svg>" +
    '<p style="font-size:13px;color:var(--muted);margin:6px 0 0">● zielone = okna równej jazdy (z nich liczony próg) · niebieskie = pozostałe okna (postoje, zrywy, zmiana tętna) · szara linia = moc</p>';
}

function card(h) {
  var ok = h.ltp_w && CONF[h.conf_ltp];
  var weak = (h.artifact_pct || 0) > 5;
  var rate = weak ? ["bad", "słaby sygnał"] : ok ? ["good", CONF[h.conf_ltp]] : ["warn", "bez progu"];
  var num, t = "";
  if (ok) {
    num = f(h.ltp_w) + " W" + (h.ltp_hr ? " · " + f(h.ltp_hr) + " ud./min" : "") +
      " <small>próg tlenowy z HRV" + (h.source === "test_schodkowy" ? " (test schodkowy)" : h.source === "swieza_czesc" ? " (świeża część jazdy)" : "") + "</small>";
    if (h.ltp_modelq_w) {
      var d = h.ltp_w - h.ltp_modelq_w, pc = 100 * d / h.ltp_modelq_w;
      t += "ModelQ: " + f(h.ltp_modelq_w) + " W – " + (Math.abs(pc) < 3 ? "zgodnie (różnica " + f(Math.abs(d)) + " W). " :
        "HRV pokazuje o " + f(Math.abs(d)) + " W " + (d < 0 ? "mniej" : "więcej") + " (" + (d < 0 ? "−" : "+") + f(Math.abs(pc)) + "%). ");
    }
    if (h.ltp_all_w && h.source === "swieza_czesc" && CONF[h.conf_all]) t += "Z całej jazdy " + f(h.ltp_all_w) + " W. ";
  } else {
    num = h.near ? "α1 " + f(h.near.a1_min, 2) + "–" + f(h.near.a1_max, 2) + " <small>przy " + f(h.near.p_min) + "–" + f(h.near.p_max) +
      " W · okolice progu tlenowego</small>" : "— <small>za mało danych do progu</small>";
    t += "Równej jazdy " + (h.n_steady || 0) + " okn" + ((h.n_steady || 0) === 1 ? "o" : "a") +
      " – za mało, by wiarygodnie wyznaczyć próg (potrzeba kilku odcinków 5–8 min w różnym tempie). ";
    if (h.near) t += "W tych oknach α1 jest blisko 0,75 przy ok. " + f((h.near.p_min + h.near.p_max) / 2) + " W" +
      (h.near.hr ? " i tętnie ok. " + f(h.near.hr) + " ud./min" : "") + (h.ltp_modelq_w ? " (próg tlenowy ModelQ: " + f(h.ltp_modelq_w) + " W)" : "") + ". ";
  }
  if (h.drift_a1 != null) {
    t += h.drift_a1 <= -0.05 ? "W drugiej połowie α1 przy tej samej mocy niższe o " + f(-h.drift_a1, 2) + " – zmęczenie. " :
      h.drift_a1 >= 0.05 ? "W drugiej połowie α1 przy tej samej mocy wyższe – bez oznak zmęczenia. " :
      "α1 przy tej samej mocy stabilne przez całą jazdę – bez oznak zmęczenia. ";
  }
  if (h.warmup_a1 != null) {
    t += "Rozgrzewka: α1 " + f(h.warmup_a1, 2);
    if (h.warm_norm && h.warm_n >= 10) {
      var dw = h.warmup_a1 - h.warm_norm;
      t += Math.abs(dw) < 0.1 ? " – w normie. " : dw < 0 ? " – poniżej Twojej normy (" + f(h.warm_norm, 2) + "): organizm mniej świeży. " :
        " – powyżej Twojej normy (" + f(h.warm_norm, 2) + "). ";
    } else {
      t += " (Twoja norma powstanie po ok. 10 jazdach z pasem; jest " + (h.warm_n || 0) + "). ";
    }
  }
  t += (weak ? "Sygnał słaby: " : "Sygnał z pasa: ") + f(h.artifact_pct, 2) + "% błędnych uderzeń" +
    (weak ? " – zwilż elektrody, sprawdź pasek. " : ". ");
  if (h.battery_pct != null && h.battery_pct >= 0 && h.battery_pct <= 20) t += "Bateria pasa " + h.battery_pct + "% (CR2025). ";
  t += '<span style="color:var(--muted)">Pomiar porównawczy – nie zmienia ModelQ (okres próbny).</span>';
  var dur = Math.max(15, Math.ceil((h.dur_min || 60) / 15) * 15);
  return '<div class="h"><b>HRV z jazdy</b><span class="rate ' + rate[0] + '">' + rate[1] + "</span></div>" +
    '<div class="num">' + num + "</div><p>" + t + "</p>" +
    (h.windows && h.windows.length ? '<details><summary style="cursor:pointer">Pokaż α1 w czasie jazdy</summary>' + chart(h.windows, dur) + "</details>" : "");
}

var cache = {};
function place() {
  var sel = document.getElementById("ridesel"), rk = sel && sel.value;
  if (!rk) return;
  var have = document.getElementById("rj-hrv");
  if (have && have.dataset.rk === rk && document.body.contains(have)) return;
  var anchor = null;
  document.querySelectorAll(".it .h b").forEach(function (b) { if (!anchor && b.textContent.indexOf("Moc na uderzenie serca") === 0) anchor = b.closest(".it"); });
  if (!anchor) return;
  if (have) have.remove();
  var go = function (h) {
    if (!h || document.getElementById("rj-hrv") || (sel.value !== rk)) return;
    var el = document.createElement("div");
    el.className = "it"; el.id = "rj-hrv"; el.dataset.rk = rk; el.style.gridColumn = "1/-1";
    el.innerHTML = card(h);
    anchor.insertAdjacentElement("afterend", el);
  };
  if (rk in cache) { go(cache[rk]); return; }
  cache[rk] = null;
  fetch("/api/ride-report/hrv?ride=" + encodeURIComponent(rk), { credentials: "same-origin", cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { cache[rk] = j && j.hrv; go(cache[rk]); })
    .catch(function () {});
}
new MutationObserver(place).observe(document.body, { childList: true, subtree: true });
})();
