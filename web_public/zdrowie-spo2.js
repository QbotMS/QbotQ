/* Zdrowie -> Serce: SpO2 nocne (2026-10-20, sesja spo2-2010). Kafel wniosku + noce (minuty spadkow) + noc minuta po minucie.
   Dane: GET /api/jedzenie/spo2 (qbot_food_api.py -> qbot_spo2.py). Wymaga Chart.js (ladowany w zdrowie.html). Dok.: docs/SPO2.md */
(function () {
  "use strict";
  var root = document.getElementById("spo2-box"); if (!root) return;
  var API = "/api/jedzenie/spo2";
  var LBL = {good: "spokojna", warn: "do obserwacji", bad: "niespokojna"};
  var ALL = [], VIEW = [], CH1 = null, CH2 = null, SEL = null, NIGHT = null, Z2 = null, done = false;
  var VIS1 = {drop: true, norm: true, alc: true}, VIS2 = {spo2: true, thr: true, p90: true};

  var st = document.createElement("style");
  st.textContent = ".sp2-big{font-size:28px;font-weight:600;line-height:1.1;margin-top:4px}.sp2-sub{font-size:14px;color:var(--ink2);margin-top:4px;font-variant-numeric:tabular-nums}" +
    ".sp2-good{color:var(--good)}.sp2-warn{color:var(--warn)}.sp2-bad{color:var(--bad)}.sp2-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px;vertical-align:1px}" +
    ".sp2-facts{margin:10px 0 0;padding:0;list-style:none;font-size:14px}.sp2-facts li{padding:5px 0;border-top:1px solid var(--line)}.sp2-facts li:first-child{border-top:0}" +
    ".sp2-how summary{cursor:pointer;color:var(--accent-ink);font-size:12.5px;margin-top:8px}.sp2-how p{font-size:12.5px;color:var(--ink2);line-height:1.5;margin:6px 0 0}" +
    ".sp2-rng{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:8px 0 10px}.sp2-rng button{appearance:none;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;padding:4px 10px;font:inherit;font-size:13px;cursor:pointer}" +
    ".sp2-rng button.on{background:var(--accent-bg);border-color:var(--accent);color:var(--accent-ink);font-weight:600}.sp2-rng input{font:inherit;font-size:13px;padding:3px 6px;border:1px solid var(--line);border-radius:8px;background:var(--well);color:var(--ink)}" +
    ".sp2-chips{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 8px}.sp2-chip{appearance:none;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:3px 10px;font:inherit;font-size:12.5px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}" +
    ".sp2-chip i{width:12px;height:4px;border-radius:2px;display:inline-block}.sp2-chip.on{color:var(--ink);background:var(--well);border-color:var(--line2)}.sp2-chip:not(.on) i{filter:grayscale(1);opacity:.5}" +
    ".sp2-ch{position:relative;height:250px}.sp2-ch.tall{height:290px}.sp2-hint{font-size:12px;color:var(--muted);margin-top:6px}" +
    ".sp2-zr{appearance:none;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;padding:3px 10px;font:inherit;font-size:12.5px;cursor:pointer}" +
    ".sp2-ns{font-size:13.5px;color:var(--ink2);font-variant-numeric:tabular-nums;margin:2px 0 8px}";
  document.head.appendChild(st);

  function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim() || "#888"; }
  function stc(s) { return s === "bad" ? css("--bad") : s === "warn" ? css("--warn") : s === "good" ? css("--good") : css("--line2"); }
  function ddmm(iso) { return iso.slice(8, 10) + "." + iso.slice(5, 7); }
  function ddmmyy(iso) { return ddmm(iso) + "." + iso.slice(0, 4); }
  function pl(x) { return String(x).replace(".", ","); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function get(u) { return fetch(u, {credentials: "same-origin"}).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }); }
  function $(id) { return document.getElementById(id); }

  function build() {
    root.innerHTML =
      "<div class='card' id='sp2-verd'><p class='muted'>ładuję SpO2…</p></div>" +
      "<div class='card' style='margin-top:12px'><div class='cardhead'><p class='lbl'><span class='tip' tabindex='0' data-tip='Każdy słupek to jedna noc: ile minut saturacja była co najmniej 4 punkty poniżej typowego poziomu tej nocy. Kolor: zielony spokojna, żółty do obserwacji, czerwony niespokojna — względem Twoich 60 poprzednich nocy.'>SpO2 nocne — minuty spadków</span></p></div>" +
      "<div class='sp2-rng' id='sp2-rng'><button data-d='30'>30 dni</button><button class='on' data-d='90'>90 dni</button><button data-d='0'>Całość</button>" +
      "<span style='margin-left:6px;font-size:12.5px;color:var(--muted)'>od</span><input type='date' id='sp2-a'><span style='font-size:12.5px;color:var(--muted)'>do</span><input type='date' id='sp2-b'></div>" +
      "<div class='sp2-chips' id='sp2-c1'></div><div class='sp2-ch'><canvas id='sp2-ch1'></canvas></div>" +
      "<div class='sp2-hint'>Kliknij słupek, żeby zobaczyć noc minuta po minucie. Przeciągnij, żeby powiększyć; dwuklik — całość.</div></div>" +
      "<div class='card' id='sp2-night' style='margin-top:12px'><p class='muted'>ładuję noc…</p></div>";
    $("sp2-rng").addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      root.querySelectorAll("#sp2-rng button").forEach(function (x) { x.classList.toggle("on", x === b); });
      $("sp2-a").value = $("sp2-b").value = ""; setRange(+b.dataset.d);
    });
    ["sp2-a", "sp2-b"].forEach(function (id) { $(id).addEventListener("change", function () {
      root.querySelectorAll("#sp2-rng button").forEach(function (x) { x.classList.remove("on"); });
      setRange(0, $("sp2-a").value, $("sp2-b").value); }); });
  }

  function renderVerdict(v, f) {
    var el = $("sp2-verd");
    if (!v || !v.status) { el.innerHTML = "<p class='muted'>" + esc((v && v.text) || "Brak danych SpO2") + "</p>"; return; }
    var L = v.last;
    var h = "<div class='cardhead'><p class='lbl'>SpO2 nocne (saturacja)</p><span class='sub'>ostatnia noc · " + ddmm(L.day) + " (" + L.start + "–" + L.end + ")</span></div>" +
      "<div class='sp2-big sp2-" + v.status + "'><span class='sp2-dot' style='background:" + stc(v.status) + "'></span>" + esc(v.label[0].toUpperCase() + v.label.slice(1)) + "</div>" +
      "<div class='sp2-sub'>" + L.drop_min + " min spadków (zwykle ~" + Math.round(L.norm) + ") · " + L.events + " spadków · najniżej " + L.min + "% · średnio " + pl(L.avg) + "%</div>";
    var it = [];
    if (v.trend_text) it.push("<li class='sp2-" + v.trend_level + "'>" + esc(v.trend_text) + "</li>");
    (f || []).forEach(function (x) { it.push("<li class='sp2-" + x.level + "'>" + esc(x.text) + "</li>"); });
    if (it.length) h += "<ul class='sp2-facts'>" + it.join("") + "</ul>";
    h += "<details class='sp2-how'><summary>Jak to liczę?</summary><p>Zegarek mierzy SpO2 co minutę w czasie snu. Dla każdej nocy biorę jej własny typowy poziom (medianę) i liczę minuty, w których saturacja spadła o 4 punkty lub więcej poniżej niego. " +
      "Noc porównuję z Twoimi 60 poprzednimi nocami: do 75% najgorszych wyników — spokojna, do 90% — do obserwacji, powyżej — niespokojna. Pojedyncze spadki są normalne (ruch, pozycja ciała). " +
      "Odczyty minutowe są od 01.06.2026 — starszych Garmin już nie oddaje.</p></details>";
    el.innerHTML = h;
  }

  function chips(id, defs, vis, redraw) {
    var c = $(id);
    c.innerHTML = defs.map(function (d) { return "<button class='sp2-chip" + (vis[d.k] ? " on" : "") + "' data-k='" + d.k + "'><i style='background:" + d.col + "'></i>" + d.t + "</button>"; }).join("");
    c.onclick = function (e) { var b = e.target.closest(".sp2-chip"); if (!b) return; vis[b.dataset.k] = !vis[b.dataset.k]; b.classList.toggle("on"); redraw(); };
  }

  function dragZoom(cv, getCh, onZoom) {
    var d0 = null;
    cv.addEventListener("mousedown", function (e) { d0 = {x0: e.clientX}; });
    cv.addEventListener("mouseup", function (e) {
      var ch = getCh(); if (!d0 || !ch) return;
      var r = cv.getBoundingClientRect(), xs = ch.scales.x;
      var a = xs.getValueForPixel(Math.min(d0.x0, e.clientX) - r.left), b = xs.getValueForPixel(Math.max(d0.x0, e.clientX) - r.left);
      if (Math.abs(e.clientX - d0.x0) > 8 && b - a >= 2) onZoom(Math.round(a), Math.round(b));
      d0 = null;
    });
    cv.addEventListener("dblclick", function () { onZoom(null, null); });
  }

  function drawNights() {
    var ds = [];
    if (VIS1.drop) ds.push({type: "bar", label: "Minuty spadków", data: VIEW.map(function (n) { return n.drop_min; }),
      backgroundColor: VIEW.map(function (n) { return stc(n.status); }),
      borderColor: VIEW.map(function (n) { return SEL === n.day ? css("--ink") : "transparent"; }), borderWidth: 2, order: 2});
    if (VIS1.norm) ds.push({type: "line", label: "Twoja norma", data: VIEW.map(function (n) { return n.norm; }), borderColor: css("--ink2"),
      borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, tension: .2, order: 1});
    if (VIS1.alc) ds.push({type: "line", label: "Alkohol", data: VIEW.map(function (n) { return n.alcohol ? -2 : null; }),
      showLine: false, pointStyle: "triangle", pointRadius: 6, pointBackgroundColor: css("--accent"), borderColor: css("--accent"), order: 0});
    if (CH1) CH1.destroy();
    CH1 = new Chart($("sp2-ch1"), {data: {labels: VIEW.map(function (n) { return ddmm(n.day); }), datasets: ds}, options: {
      responsive: true, maintainAspectRatio: false, animation: false, interaction: {mode: "index", intersect: false},
      plugins: {legend: {display: false}, tooltip: {callbacks: {
        title: function (it) { var n = VIEW[it[0].dataIndex]; return ddmmyy(n.day) + " · " + (LBL[n.status] || "bez oceny"); },
        label: function () { return null; },
        afterBody: function (it) { var n = VIEW[it[0].dataIndex]; var a = [
          n.drop_min + " min spadków (norma ~" + (n.norm == null ? "–" : Math.round(n.norm)) + ")",
          n.events + " spadków, najniżej " + n.min + "%, średnio " + pl(n.avg) + "%",
          "pomiar " + n.start + "–" + n.end + (n.below90 ? ", poniżej 90%: " + n.below90 + " min" : "")];
          if (n.alcohol) a.push("🍷 alkohol dzień wcześniej");
          if (n.tss_prev) a.push("jazda dzień wcześniej: TSS " + n.tss_prev);
          if (n.hrv) a.push("HRV rano " + Math.round(n.hrv) + " ms" + (n.score ? ", ocena snu " + n.score : ""));
          return a; }}}},
      scales: {x: {grid: {display: false}, ticks: {color: css("--muted"), maxRotation: 0, autoSkip: true, maxTicksLimit: 12}},
        y: {min: -4, grid: {color: css("--line")}, ticks: {color: css("--muted"), callback: function (v) { return v < 0 ? "" : v; }}, title: {display: true, text: "min", color: css("--muted")}}},
      onClick: function (e, els) { if (els && els.length) loadNight(VIEW[els[0].index].day); }
    }});
  }

  function setRange(days, a, b) {
    var last = ALL.length ? ALL[ALL.length - 1].day : null;
    if (a || b) VIEW = ALL.filter(function (n) { return (!a || n.day >= a) && (!b || n.day <= b); });
    else if (!days || !last) VIEW = ALL.slice();
    else { var cut = new Date(Date.parse(last) - days * 864e5).toISOString().slice(0, 10); VIEW = ALL.filter(function (n) { return n.day > cut; }); }
    drawNights();
  }

  function drawNight() {
    var d = NIGHT, el = $("sp2-night"); if (!d) return;
    var n = ALL.find(function (x) { return x.day === d.day; }) || {};
    if (!el.dataset.built) {
      el.innerHTML = "<div class='cardhead' style='display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap'><p class='lbl' id='sp2-nt'></p><button class='sp2-zr' id='sp2-zr' hidden>Pokaż całą noc</button></div>" +
        "<div class='sp2-ns' id='sp2-ns'></div><div class='sp2-chips' id='sp2-c2'></div><div class='sp2-ch tall'><canvas id='sp2-ch2'></canvas></div>" +
        "<div class='sp2-hint'>Na czerwono — minuty spadku (≥ 4 pkt poniżej typowego poziomu nocy). Przeciągnij, żeby powiększyć; dwuklik — całość.</div>";
      el.dataset.built = "1";
      chips("sp2-c2", [{k: "spo2", t: "SpO2", col: css("--accent")}, {k: "thr", t: "Próg spadku", col: css("--bad")}, {k: "p90", t: "90%", col: css("--muted")}], VIS2, drawNight);
      dragZoom($("sp2-ch2"), function () { return CH2; }, function (a, b) { Z2 = a == null ? null : {min: a, max: b}; drawNight(); });
      $("sp2-zr").onclick = function () { Z2 = null; drawNight(); };
    }
    $("sp2-nt").innerHTML = "SpO2 — noc " + ddmmyy(d.day) + (n.status ? " · <span class='sp2-" + n.status + "'>" + LBL[n.status] + "</span>" : "");
    $("sp2-ns").textContent = d.start + "–" + d.end + " · " + d.n + " odczytów · typowo " + pl(d.med) + "% · najniżej " + d.min + "% · " +
      d.events + " spadków, " + d.drop_min + " min" + (d.below90 ? " · poniżej 90%: " + d.below90 + " min" : "");
    $("sp2-zr").hidden = !Z2;
    var lab = d.series.map(function (p) { return p[0]; }), val = d.series.map(function (p) { return p[1]; });
    var bad = css("--bad"), acc = css("--accent"), ds = [];
    if (VIS2.spo2) ds.push({label: "SpO2", data: val, borderColor: acc, borderWidth: 1.6, pointRadius: 0, tension: .15,
      segment: {borderColor: function (c) { return (val[c.p0DataIndex] <= d.thr || val[c.p1DataIndex] <= d.thr) ? bad : acc; }}});
    if (VIS2.thr) ds.push({label: "Próg spadku", data: val.map(function () { return d.thr; }), borderColor: bad, borderDash: [5, 4], borderWidth: 1, pointRadius: 0});
    if (VIS2.p90) ds.push({label: "90%", data: val.map(function () { return 90; }), borderColor: css("--muted"), borderDash: [2, 4], borderWidth: 1, pointRadius: 0});
    if (CH2) CH2.destroy();
    CH2 = new Chart($("sp2-ch2"), {type: "line", data: {labels: lab, datasets: ds}, options: {
      responsive: true, maintainAspectRatio: false, animation: false, interaction: {mode: "index", intersect: false},
      plugins: {legend: {display: false}, tooltip: {callbacks: {
        title: function (it) { return it[0].label; },
        label: function (c) { return c.dataset.label === "SpO2" ? "SpO2 " + c.parsed.y + "%" + (c.parsed.y <= d.thr ? " — spadek" : "") : null; }}}},
      scales: {x: {min: Z2 ? Z2.min : undefined, max: Z2 ? Z2.max : undefined, grid: {display: false}, ticks: {color: css("--muted"), maxRotation: 0, autoSkip: true, maxTicksLimit: 10}},
        y: {min: Math.min(88, d.min - 1), max: 100, grid: {color: css("--line")}, ticks: {color: css("--muted"), callback: function (v) { return v + "%"; }}}}
    }});
  }

  function loadNight(day) {
    SEL = day; Z2 = null; drawNights();
    get(API + "?day=" + day).then(function (d) { NIGHT = d; drawNight(); })
      .catch(function (e) { $("sp2-night").innerHTML = "<p class='muted'>Nie udało się wczytać nocy (" + esc(e.message) + ").</p>"; delete $("sp2-night").dataset.built; });
  }

  function load() {
    if (done) return; done = true;
    if (typeof Chart === "undefined") { setTimeout(function () { done = false; load(); }, 300); return; }
    build();
    get(API + "?days=400").then(function (s) {
      ALL = s.nights || [];
      renderVerdict(s.verdict, s.factors);
      chips("sp2-c1", [{k: "drop", t: "Minuty spadków", col: css("--good")}, {k: "norm", t: "Twoja norma", col: css("--ink2")}, {k: "alc", t: "Alkohol dzień wcześniej", col: css("--accent")}], VIS1, drawNights);
      dragZoom($("sp2-ch1"), function () { return CH1; }, function (a, b) {
        if (a == null) { var on = root.querySelector("#sp2-rng button.on"); setRange(on ? +on.dataset.d : 90); return; }
        VIEW = VIEW.slice(a, b + 1); drawNights(); });
      setRange(90);
      if (ALL.length) loadNight(ALL[ALL.length - 1].day);
    }).catch(function (e) { done = false; $("sp2-verd").innerHTML = "<p class='muted'>Nie udało się wczytać SpO2: " + esc(e.message) + "</p>"; });
  }
  var btn = document.querySelector('#tabs button[data-t="serce"]'); if (btn) btn.addEventListener("click", load);
  if (location.hash === "#serce") load();
})();
