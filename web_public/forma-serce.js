/* Forma > Serce (2026-10-12). Dane: GET /api/forma/heart (qbot_web.py -> qbot_heart.build_heart_data).
   Tetno spoczynkowe, tetno przy 140-180 W, cisnienie (Withings -> Garmin), EKG (zegarek). docs/SERCE.md */
(function () {
  "use strict";
  var root = document.getElementById("p-serce");
  if (!root) return;
  var DATA = null, RANGE = 180, chart = null, loading = false;

  function css(v, fb) { var x = getComputedStyle(document.documentElement).getPropertyValue(v).trim(); return x || fb; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function dd(iso) { if (!iso) return "—"; var p = iso.slice(0, 10).split("-"); return p[2] + "." + p[1] + "." + p[0]; }
  function hm(iso) { return iso && iso.length > 11 ? iso.slice(11, 16) : ""; }
  function num(x, n) { return x == null ? "—" : Number(x).toFixed(n || 0).replace(".", ","); }
  function sgn(x) { return x == null ? "" : (x > 0 ? "+" : "") + num(x, 1); }
  var ICON = {good: "✓", warn: "!", bad: "‼", info: "·"};

  function tile(cls, t, v, x, n) {
    return '<div class="s3it ' + cls + '"><div class="t">' + esc(t) + '</div><div class="s">' + v + '</div>' +
      '<div class="x">' + x + '</div>' + (n ? '<div class="n">' + n + "</div>" : "") + "</div>";
  }

  function render() {
    var d = DATA, r = d.rhr, h = d.hrp, bp = d.bp.summary, e = d.ecg;
    var pts = d.points.map(function (p) {
      return '<div class="s3row ' + p.status + '"><span class="i">' + ICON[p.status] + "</span><span>" + esc(p.text) + "</span></div>";
    }).join("");
    var bad = d.points.some(function (p) { return p.status === "bad"; });

    var tiles = "";
    tiles += tile(r.status, "Tętno spoczynkowe", r.recent == null ? "—" : num(r.recent) + " <small>ud./min</small>",
      "średnia 28 dni · norma " + num(r.norm) + " (" + sgn(r.delta) + ")",
      r.last ? "ostatnio " + r.last.rhr + " (" + dd(r.last.date) + ")" : "");
    tiles += tile(h.status, "Tętno przy " + h.band, h.recent == null ? "—" : num(h.recent) + " <small>ud./min</small>",
      "jazdy z 28 dni (" + (h.rides || 0) + ") · norma " + num(h.norm) + " (" + sgn(h.delta) + ")",
      "od 15. do 120. minuty jazdy");
    if (bp) {
      tiles += tile(bp.fresh ? bp.status : "info", "Ciśnienie", bp.sys + "/" + bp.dia,
        esc(bp.label), "seria " + dd(bp.from) + (bp.to !== bp.from ? "–" + dd(bp.to) : "") + " · " + bp.n + " pomiar(y)" +
        (bp.fresh ? "" : " · <b>za stare</b>"));
    } else {
      tiles += tile("info", "Ciśnienie", "—", "brak pomiarów", "zrób 7-dniową serię");
    }
    if (e.last) {
      tiles += tile(e.last.ok ? (e.fresh ? "good" : "info") : "bad", "EKG", esc(e.last.label.split(" (")[0]),
        "średnio " + e.last.hr + " ud./min" + (e.last.hrv != null ? " · HRV " + e.last.hrv + " ms" : ""),
        dd(e.last.local) + (e.fresh ? "" : " · <b>stare</b>"));
    } else {
      tiles += tile("info", "EKG", "—", "brak nagrań", "");
    }

    var bpRows = d.bp.all.slice().reverse().map(function (m) {
      var c = m.sys >= 135 || m.dia >= 85 ? ' style="color:var(--bad);font-weight:600"' : "";
      return "<tr><td>" + dd(m.local) + "</td><td>" + hm(m.local) + "</td><td class=\"num\"" + c + ">" + m.sys + "/" + m.dia +
        '</td><td class="num">' + (m.pulse == null ? "—" : m.pulse) + "</td></tr>";
    }).join("") || '<tr><td colspan="4" class="muted">brak pomiarów</td></tr>';
    var bpSum = "";
    if (bp && bp.days >= 2) {
      bpSum = '<div style="font-size:13.5px;margin:8px 2px 0;color:var(--ink2)">Średnia serii: <b>' + bp.sys + "/" + bp.dia + "</b>" +
        (bp.morning.n ? " · rano " + bp.morning.sys + "/" + bp.morning.dia + " (" + bp.morning.n + ")" : "") +
        (bp.evening.n ? " · wieczorem " + bp.evening.sys + "/" + bp.evening.dia + " (" + bp.evening.n + ")" : "") +
        (bp.dropped_first_day ? " · pominięty 1. dzień " + dd(bp.dropped_first_day) : "") + "</div>";
    }
    var ecgRows = e.list.slice().reverse().map(function (x) {
      var c = x.ok ? "" : ' style="color:var(--bad);font-weight:600"';
      var sy = (x.symptoms || []).length ? esc(x.symptoms.join(", ")) : "—";
      return "<tr><td>" + dd(x.local) + "</td><td>" + hm(x.local) + "</td><td" + c + ">" + esc(x.label) + '</td><td class="num">' +
        (x.hr == null ? "—" : x.hr) + '</td><td class="num">' + (x.hrv == null ? "—" : x.hrv) + "</td><td>" + sy + "</td></tr>";
    }).join("") || '<tr><td colspan="6" class="muted">brak nagrań</td></tr>';

    root.innerHTML =
      '<div class="card" style="border-left:5px solid ' + (bad ? "var(--bad)" : "var(--accent)") + '">' +
      '<div class="cardhead"><p class="lbl"><span class="tip" tabindex="0" data-tip="Porównanie ostatnich 28 dni z Twoją normą z roku (mediana dni 29–365 wstecz). Progi: tętno spoczynkowe +3 uwaga / +5 wyraźnie; tętno przy mocy +5 / +8. Ciśnienie oceniane dla pomiarów domowych (próg 135/85). To sygnały do obserwacji, nie diagnoza.">Serce — co mówią dane</span></p>' +
      '<span class="sub">' + dd(d.today) + "</span></div>" + pts +
      (bad ? '<div style="font-size:13.5px;margin-top:8px;color:var(--ink2)">Coś odbiega od normy — pokaż lekarzowi serię ciśnienia i EKG.</div>' : "") +
      "</div>" +
      '<div class="s3grid">' + tiles + "</div>" +
      '<div class="card tight"><div class="cardhead"><p class="lbl"><span class="tip" tabindex="0" data-tip="Linia: tętno spoczynkowe z zegarka (dzień po dniu). Kropki: średnie tętno w jeździe przy mocy 140–180 W (od 15. do 120. minuty, min. 5 min w paśmie) — prawa oś. Przerywane linie: Twoja norma z roku.">Tętno spoczynkowe i tętno przy mocy</span></p>' +
      '<div class="seg" id="hz-rng"><button data-r="90">90 dni</button><button data-r="180" class="on">180 dni</button><button data-r="365">rok</button></div></div>' +
      '<div style="position:relative;width:100%;height:260px"><canvas id="hz-canvas"></canvas></div></div>' +
      '<div class="card"><div class="cardhead"><p class="lbl">Ciśnienie (Withings)</p><span class="sub">' + d.bp.all.length + " pomiarów</span></div>" +
      '<div style="overflow-x:auto"><table class="qs-table"><tr><th>Data</th><th>Godz.</th><th class="num">Ciśnienie</th><th class="num">Tętno</th></tr>' +
      bpRows + "</table></div>" + bpSum + "</div>" +
      '<div class="card"><div class="cardhead"><p class="lbl">EKG (zegarek)</p><span class="sub">' + e.list.length + " nagrań</span></div>" +
      '<div style="overflow-x:auto"><table class="qs-table"><tr><th>Data</th><th>Godz.</th><th>Wynik</th><th class="num">Tętno</th><th class="num">HRV</th><th>Objawy</th></tr>' +
      ecgRows + "</table></div></div>" +
      '<details class="card"><summary style="cursor:pointer;font-weight:600">Kiedy i jak mierzyć</summary>' +
      '<div style="font-size:14px;line-height:1.55;margin-top:8px">' +
      "<p><b>Seria 7 dni</b>, potem kontrolnie 1 dzień w tygodniu. Pierwszy dzień QBot pomija (przyzwyczajenie), liczy średnią z dni 2–7.</p>" +
      "<p><b>Rano</b> — w ciągu godziny od wstania, po toalecie, przed kawą, śniadaniem i treningiem.<br>" +
      "<b>Wieczorem</b> — przed snem, min. 1 h po jedzeniu i kawie, min. 2 h po treningu.</p>" +
      "<p><b>Ciśnienie:</b> 5 min siedzenia, plecy oparte, stopy płasko, ręka na stole na wysokości serca, mankiet na gołym ramieniu, bez rozmowy. " +
      "2 pomiary w odstępie 1 minuty — oba się zapisują.</p>" +
      "<p><b>EKG:</b> rano zaraz po ciśnieniu (ta sama pozycja); w dni jazdy po powrocie, po 10–15 min siedzenia; " +
      "<b>zawsze od razu</b> przy kołataniu, nierównym biciu lub zawrotach głowy.</p>" +
      '<p style="color:var(--ink2)">Pilnie do lekarza: ból lub ucisk w klatce, omdlenie, EKG z migotaniem przedsionków albo ciśnienie ≥ 180/110.</p>' +
      "</div></details>";

    root.querySelectorAll("#hz-rng button").forEach(function (b) {
      b.addEventListener("click", function () {
        root.querySelectorAll("#hz-rng button").forEach(function (x) { x.classList.toggle("on", x === b); });
        RANGE = +b.dataset.r; drawChart();
      });
    });
    root.querySelectorAll("#hz-rng button").forEach(function (x) { x.classList.toggle("on", +x.dataset.r === RANGE); });
    drawChart();
  }

  function drawChart() {
    var cv = document.getElementById("hz-canvas");
    if (!cv || !window.Chart) return;
    var cut = new Date(Date.now() - RANGE * 864e5).toISOString().slice(0, 10);
    var rhr = DATA.rhr.series.filter(function (x) { return x.date >= cut; });
    var hrp = DATA.hrp.series.filter(function (x) { return x.date >= cut; });
    var labels = rhr.map(function (x) { return x.date; });
    hrp.forEach(function (x) { if (labels.indexOf(x.date) < 0) labels.push(x.date); });
    labels.sort();
    var mapR = {}, mapH = {};
    rhr.forEach(function (x) { mapR[x.date] = x.rhr; });
    hrp.forEach(function (x) { mapH[x.date] = x.hr; });
    var red = css("--bad", "#e5534b"), blue = css("--blue", "#3b82f6"), ink2 = css("--ink2", "#888"), line = css("--line", "#ddd");
    var ds = [
      {label: "Tętno spoczynkowe", data: labels.map(function (l) { return mapR[l] == null ? null : mapR[l]; }),
       borderColor: blue, backgroundColor: blue, borderWidth: 1.6, pointRadius: 0, spanGaps: true, yAxisID: "y", tension: .25},
      {label: "Tętno przy 140–180 W", data: labels.map(function (l) { return mapH[l] == null ? null : mapH[l]; }),
       borderColor: red, backgroundColor: red, showLine: false, pointRadius: 3.5, yAxisID: "y1"}
    ];
    if (DATA.rhr.norm != null) ds.push({label: "norma spoczynkowe", data: labels.map(function () { return DATA.rhr.norm; }),
      borderColor: blue, borderDash: [4, 4], borderWidth: 1, pointRadius: 0, yAxisID: "y"});
    if (DATA.hrp.norm != null) ds.push({label: "norma przy mocy", data: labels.map(function () { return DATA.hrp.norm; }),
      borderColor: red, borderDash: [4, 4], borderWidth: 1, pointRadius: 0, yAxisID: "y1"});
    if (chart) chart.destroy();
    chart = new Chart(cv, {
      type: "line",
      data: {labels: labels, datasets: ds},
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: {mode: "index", intersect: false},
        plugins: {legend: {labels: {color: ink2, boxWidth: 12, font: {size: 11}}},
          tooltip: {callbacks: {title: function (it) { return dd(it[0].label); }}}},
        scales: {
          x: {ticks: {color: ink2, maxTicksLimit: 8, callback: function (v) { return dd(this.getLabelForValue(v)).slice(0, 5); }}, grid: {color: line}},
          y: {position: "left", ticks: {color: blue}, grid: {color: line}, title: {display: true, text: "spoczynkowe", color: blue}},
          y1: {position: "right", ticks: {color: red}, grid: {drawOnChartArea: false}, title: {display: true, text: "przy mocy", color: red}}
        }
      }
    });
  }

  function load() {
    if (DATA || loading) return;
    loading = true;
    root.innerHTML = '<div class="muted">ładuję…</div>';
    fetch("/api/forma/heart?days=365", {credentials: "same-origin"})
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { DATA = j; render(); })
      .catch(function (err) { root.innerHTML = '<div class="card">Nie udało się wczytać danych serca: ' + esc(err.message) + "</div>"; })
      .finally(function () { loading = false; });
  }

  var btn = document.querySelector('#tabs button[data-t="serce"]');
  if (btn) btn.addEventListener("click", load);
  if (location.hash === "#serce") load();
})();
