/* Forma > Serce (2026-10-12). Dane: GET /api/forma/heart (qbot_web.py -> qbot_heart.build_heart_data).
   Tetno spoczynkowe, tetno przy 140-180 W, cisnienie (Withings -> Garmin), EKG (zegarek). docs/SERCE.md */
(function () {
  "use strict";
  var root = document.getElementById("p-serce");
  if (!root) return;
  var DATA = null, RANGE = 180, loading = false;

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
      var an = x.an || {}, ni = an.n_irregular || 0;
      return '<tr class="hz-ecgrow" data-id="' + esc(x.id) + '" style="cursor:pointer"><td>' + dd(x.local) + "</td><td>" + hm(x.local) + "</td><td" + c + ">" + esc(x.label) + '</td><td class="num">' +
        (x.hr == null ? "—" : x.hr) + '</td><td class="num">' + (an.rmssd == null ? (x.hrv == null ? "—" : x.hrv) : num(an.rmssd)) +
        '</td><td class="num"' + (ni ? ' style="color:var(--bad);font-weight:600"' : "") + ">" + (x.an ? ni : "—") + "</td><td>" + sy +
        '</td><td><a href="/api/forma/ecg.pdf?id=' + encodeURIComponent(x.id) + '" download>PDF</a></td></tr>';
    }).join("") || '<tr><td colspan="8" class="muted">brak nagrań</td></tr>';

    root.innerHTML =
      '<div class="card" style="border-left:5px solid ' + (bad ? "var(--bad)" : "var(--accent)") + '">' +
      '<div class="cardhead"><p class="lbl"><span class="tip" tabindex="0" data-tip="Porównanie ostatnich 28 dni z Twoją normą z roku (mediana dni 29–365 wstecz). Progi: tętno spoczynkowe +3 uwaga / +5 wyraźnie; tętno przy mocy +5 / +8. Ciśnienie oceniane dla pomiarów domowych (próg 135/85). To sygnały do obserwacji, nie diagnoza.">Serce — co mówią dane</span></p>' +
      '<span class="sub">' + dd(d.today) + "</span></div>" + pts +
      (bad ? '<div style="font-size:13.5px;margin-top:8px;color:var(--ink2)">Coś odbiega od normy — pokaż lekarzowi serię ciśnienia i EKG.</div>' : "") +
      "</div>" +
      '<div class="s3grid">' + tiles + "</div>" +
      '<div class="card tight"><div class="cardhead"><p class="lbl"><span class="tip" tabindex="0" data-tip="Linia: tętno spoczynkowe z zegarka (dzień po dniu). Kropki: średnie tętno w jeździe przy mocy 140–180 W (od 15. do 120. minuty, min. 5 min w paśmie) — prawa oś. Przerywane linie: Twoja norma z roku.">Tętno spoczynkowe i tętno przy mocy</span></p>' +
      '<div class="seg" id="hz-rng"><button data-r="90">90 dni</button><button data-r="180" class="on">180 dni</button><button data-r="365">rok</button></div></div>' +
      '<div style="position:relative;width:100%;height:240px"><canvas id="hz-canvas"></canvas></div>' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin:10px 2px 2px">' +
      '<p class="lbl" style="margin:0"><span class="tip" tabindex="0" data-tip="Kropki: każdy pomiar ciśnienia (skurczowe i rozkurczowe), linia: średnia z dnia. Przerywane: próg dla pomiarów domowych 135/85. Znaczniki u góry: nagrania EKG (zielony = rytm zatokowy, czerwony = inny wynik).">Ciśnienie i EKG</span></p>' +
      '<button class="btn" id="hz-zoomreset" hidden style="font-size:12.5px;padding:3px 10px">Pokaż całość</button></div>' +
      '<div style="position:relative;width:100%;height:200px"><canvas id="hz-bp"></canvas></div>' +
      '<div class="muted" style="font-size:12px;margin-top:4px">Przeciągnij po wykresie, żeby powiększyć; dwuklik = całość.</div></div>' +
      '<div class="card"><div class="cardhead"><p class="lbl">Ciśnienie (Withings)</p><span class="sub">' + d.bp.all.length + " pomiarów</span></div>" +
      '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px">' +
      '<div style="font-size:13.5px">' + (bp ? "Seria " + dd(bp.from) + (bp.to !== bp.from ? "–" + dd(bp.to) : "") + ": <b>" + bp.days + " z 7 dni</b>" +
        " · rano " + bp.morning.n + " · wieczorem " + bp.evening.n + " pomiarów" + (bp.protocol_ok ? " · <b>seria pełna</b>" : " · seria w toku") : "Brak serii") + "</div>" +
      '<a class="btn" href="/api/forma/heart/report.pdf" download style="font-size:12.5px;padding:3px 10px" title="Podsumowanie (AI na danych QBota), tabela ciśnienia dzień po dniu, liczby z zegarka i strony EKG z serii">Raport dla lekarza (PDF)</a></div>' +
      '<div style="overflow-x:auto"><table class="qs-table"><tr><th>Data</th><th>Godz.</th><th class="num">Ciśnienie</th><th class="num">Tętno</th></tr>' +
      bpRows + "</table></div>" + bpSum + "</div>" +
      '<div class="card"><div class="cardhead"><p class="lbl">EKG (zegarek)</p><span class="sub">' + e.list.length + " nagrań</span></div>" +
      '<div style="overflow-x:auto"><table class="qs-table"><tr><th>Data</th><th>Godz.</th><th>Wynik</th><th class="num">Tętno</th>' +
      '<th class="num"><span class="tip" tabindex="0" data-tip="RMSSD policzone przez QBot z odstępów między uderzeniami w przebiegu EKG (bez uderzeń nieregularnych). Garmin podaje własną wartość – bywa inna.">HRV</span></th>' +
      '<th class="num"><span class="tip" tabindex="0" data-tip="Uderzenia przedwczesne lub wydłużone przerwy wykryte przez QBot w przebiegu (orientacyjnie, jedno odprowadzenie).">Nieregularne</span></th><th>Objawy</th><th></th></tr>' +
      ecgRows + "</table></div>" +
      '<div id="hz-ecgbox" style="margin-top:12px"></div><div class="muted" style="font-size:12px;margin-top:4px">Kliknij wiersz, żeby zobaczyć przebieg. PDF: zapis do pokazania lekarzowi.</div></div>' +
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
    root.querySelectorAll(".hz-ecgrow").forEach(function (tr) {
      tr.addEventListener("click", function (ev) { if (ev.target.tagName === "A") return; drawEcg(tr.dataset.id); });
    });
    if (e.last && e.last.id) drawEcg(e.last.id);
  }

  /* ---------- AI: kontekst do EKG (tylko gdy cos odstaje; liczone raz i pamietane) ---------- */
  function aiBox(a) {
    return '<div style="font-size:12px;font-weight:600;color:var(--ink2);margin-bottom:4px">Kontekst (AI na danych QBota: sen, trening, ciśnienie)</div>' +
      '<div style="font-size:14px;line-height:1.5">' + esc(a.komentarz || "") + "</div>" +
      '<div class="muted" style="font-size:11.5px;margin-top:4px">' + esc(a.at || "") + " · nie jest diagnozą</div>";
  }
  function showEcgAi(id, cached) {
    var el = document.getElementById("hz-ecgai"); if (!el) return;
    if (cached) { el.innerHTML = aiBox(cached); return; }
    el.innerHTML = '<div class="muted">Analizuję kontekst (sen, trening, ciśnienie)… kilka sekund</div>';
    fetch("/api/forma/ecg/ai?id=" + encodeURIComponent(id), {method: "POST", credentials: "same-origin"})
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { var e2 = document.getElementById("hz-ecgai"); if (e2 && j.ai) e2.innerHTML = aiBox(j.ai); else if (e2) e2.remove(); })
      .catch(function (err) { var e2 = document.getElementById("hz-ecgai"); if (e2) e2.innerHTML = '<div class="muted">Kontekst AI niedostępny (' + esc(err.message) + ").</div>"; });
  }

  /* ---------- przebieg EKG (qbot_ecg): wykres interaktywny jak pozostale ---------- */
  var ECH = null, EZ = null;
  function drawEcg(id) {
    var box = document.getElementById("hz-ecgbox"); if (!box) return;
    root.querySelectorAll(".hz-ecgrow").forEach(function (tr) { tr.style.background = tr.dataset.id === id ? "var(--well)" : ""; });
    box.innerHTML = '<div class="muted">ładuję przebieg…</div>';
    fetch("/api/forma/ecg?id=" + encodeURIComponent(id), {credentials: "same-origin"})
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        var an = d.analysis || {}, fs = d.sample_rate || 128, smp = d.samples || [];
        if (!smp.length) { box.innerHTML = '<div class="muted">Brak przebiegu dla tego nagrania.</div>'; return; }
        var med = smp.slice().sort(function (a, b) { return a - b; })[Math.floor(smp.length / 2)];
        var pts = smp.map(function (v, i) { return {x: i / fs, y: v - med}; });
        function yAt(t) { var i = Math.max(0, Math.min(smp.length - 1, Math.round(t * fs))); return smp[i] - med; }
        var irrT = (an.irregular || []).map(function (i) { return i.t_s; });
        function isIrr(t) { return irrT.some(function (x) { return Math.abs(x - t) < 0.03; }); }
        var rt = an.r_t || [];
        var rr = an.rr_ms || [];
        var norm = rt.filter(function (t) { return !isIrr(t); }).map(function (t) { return {x: t, y: yAt(t)}; });
        var odd = rt.filter(isIrr).map(function (t) { return {x: t, y: yAt(t)}; });
        var irrTxt = (an.irregular || []).map(function (i) { return num(i.t_s, 1) + " s: " + esc(i.label); }).join(" · ");
        box.innerHTML =
          '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">' +
          '<div style="font-size:13.5px"><b>' + dd(d.started_local) + " " + hm(d.started_local) + "</b> · " + esc(d.label) +
          (an.ok ? " · " + an.n_beats + " uderzeń · tętno " + num(an.hr_min) + "–" + num(an.hr_max) + " (śr. " + num(an.hr_mean) + ")" +
            " · HRV RMSSD " + num(an.rmssd) + " ms · SDNN " + num(an.sdnn) + " ms · pNN50 " + num(an.pnn50) + "%" +
            " · sygnał: " + esc(an.quality) : " · analiza: " + esc(an.error || "brak")) + "</div>" +
          '<div><button class="btn" id="hz-ezr" hidden style="font-size:12.5px;padding:3px 10px">Pokaż całość</button> ' +
          '<a class="btn" href="/api/forma/ecg.pdf?id=' + encodeURIComponent(d.detail_id) + '" download style="font-size:12.5px;padding:3px 10px">Pobierz PDF</a></div></div>' +
          '<div style="margin-top:8px">' + (d.interpretation || []).map(function (p) {
            return '<div class="s3row ' + p.status + '"><span class="i">' + ICON[p.status] + "</span><span>" + esc(p.text) + "</span></div>";
          }).join("") + "</div>" +
          (irrTxt ? '<div style="font-size:13px;color:var(--bad);margin-top:4px">' + irrTxt + "</div>" : "") +
          (d.ai_needed ? '<div id="hz-ecgai" class="card tight" style="margin-top:8px;background:var(--well)"></div>' : "") +
          '<div style="position:relative;width:100%;height:220px;margin-top:6px"><canvas id="hz-ecg"></canvas></div>' +
          '<div class="muted" style="font-size:12px">Przeciągnij, żeby powiększyć fragment (np. 3–4 uderzenia); dwuklik = całość. Najechanie na uderzenie pokazuje odstęp od poprzedniego.</div>';
        if (d.ai_needed) showEcgAi(d.detail_id, d.ai);
        if (!window.Chart) return;
        var ink2 = css("--ink2", "#888"), line = css("--line", "#ddd"), red = css("--bad", "#e5534b"), ink = css("--ink", "#ddd");
        if (ECH) ECH.destroy(); EZ = null;
        ECH = new Chart(document.getElementById("hz-ecg"), {
          type: "line",
          data: {datasets: [
            {label: "EKG (mV)", data: pts, borderColor: ink, borderWidth: 1.2, pointRadius: 0, pointHitRadius: 0, parsing: false, order: 3},
            {label: "uderzenie", data: norm, showLine: false, pointRadius: 3.5, pointStyle: "triangle", borderColor: ink2, backgroundColor: ink2, parsing: false, order: 1},
            {label: "nieregularne", data: odd, showLine: false, pointRadius: 6, pointStyle: "triangle", borderColor: red, backgroundColor: red, parsing: false, order: 0}
          ]},
          options: {
            responsive: true, maintainAspectRatio: false, animation: false,
            interaction: {mode: "nearest", axis: "x", intersect: false},
            plugins: {legend: {labels: {color: ink2, boxWidth: 12, font: {size: 11}}},
              tooltip: {filter: function (it) { return it.datasetIndex > 0; },
                callbacks: {title: function (it) { return it.length ? num(it[0].parsed.x, 2) + " s" : ""; },
                  label: function (it) {
                    var k = rt.findIndex(function (t) { return Math.abs(t - it.parsed.x) < 0.005; });
                    var ir = (an.irregular || []).filter(function (i) { return Math.abs(i.t_s - it.parsed.x) < 0.03; })[0];
                    var s1 = k > 0 && rr[k - 1] ? "odstęp " + rr[k - 1] + " ms (" + num(60000 / rr[k - 1]) + " ud./min)" : "pierwsze uderzenie";
                    return ir ? [s1, ir.label] : s1;
                  }}}},
            scales: {
              x: {type: "linear", min: 0, max: smp.length / fs, ticks: {color: ink2, stepSize: 1, callback: function (v) { return v + " s"; }}, grid: {color: line}},
              y: {ticks: {color: ink2}, grid: {color: line}, title: {display: true, text: "mV", color: ink2}}
            }
          }
        });
        var cv = document.getElementById("hz-ecg"), drag = null, full = smp.length / fs;
        function tv(ev) { var r = cv.getBoundingClientRect(); return Math.max(0, Math.min(full, ECH.scales.x.getValueForPixel(ev.clientX - r.left))); }
        function zoom(a, b) { ECH.options.scales.x.min = a; ECH.options.scales.x.max = b; ECH.update("none"); document.getElementById("hz-ezr").hidden = (a === 0 && b === full); }
        cv.addEventListener("mousedown", function (ev) { if (ev.button !== 0) return;
          var bx = document.createElement("div"); bx.style.cssText = "position:absolute;top:0;bottom:0;left:0;width:0;background:rgba(59,130,246,.15);border:1px solid rgba(59,130,246,.6);pointer-events:none;z-index:4";
          cv.parentNode.appendChild(bx); drag = {x0: ev.clientX, t0: tv(ev), bx: bx}; ev.preventDefault(); });
        document.addEventListener("mousemove", function (ev) { if (!drag) return; var r = cv.getBoundingClientRect();
          var a = Math.max(0, Math.min(drag.x0, ev.clientX) - r.left), b = Math.min(r.width, Math.max(drag.x0, ev.clientX) - r.left);
          drag.bx.style.left = a + "px"; drag.bx.style.width = Math.max(0, b - a) + "px"; });
        document.addEventListener("mouseup", function (ev) { if (!drag) return; var d0 = drag; drag = null; d0.bx.remove();
          var t1 = tv(ev), a = Math.min(d0.t0, t1), b = Math.max(d0.t0, t1);
          if (b - a > 0.3 && Math.abs(ev.clientX - d0.x0) > 8) zoom(a, b); });
        cv.addEventListener("dblclick", function () { zoom(0, full); });
        document.getElementById("hz-ezr").addEventListener("click", function () { zoom(0, full); });
      })
      .catch(function (err) { box.innerHTML = '<div class="muted">Nie udało się wczytać przebiegu: ' + esc(err.message) + "</div>"; });
  }

  /* ---------- wykresy: wspolna os dni, zoom, kursor (wzor: Trendy w forma2-data.js) ---------- */
  var CH = {}, ZOOM = null, HOVER = null, LABELS = [], BPDAY = {}, ECGDAY = {};
  var IDS = ["hz-canvas", "hz-bp"];

  function charts() { return IDS.map(function (k) { return CH[k]; }).filter(Boolean); }
  function setX(ch) {
    var x = ch.options.scales.x;
    if (ZOOM) { x.min = ZOOM.min; x.max = ZOOM.max; } else { delete x.min; delete x.max; }
  }
  function applyZoom() {
    charts().forEach(function (c) { setX(c); c.update("none"); });
    var b = document.getElementById("hz-zoomreset"); if (b) b.hidden = !ZOOM;
  }

  function avg(a) { return a.length ? Math.round(a.reduce(function (x, y) { return x + y; }, 0) / a.length) : null; }

  function drawChart() {
    var cv = document.getElementById("hz-canvas"), cb = document.getElementById("hz-bp");
    if (!cv || !cb || !window.Chart) return;
    ZOOM = null; HOVER = null;
    var cut = new Date(Date.now() - RANGE * 864e5).toISOString().slice(0, 10), todayIso = DATA.today;
    var rhr = DATA.rhr.series.filter(function (x) { return x.date >= cut; });
    var hrp = DATA.hrp.series.filter(function (x) { return x.date >= cut; });
    var bpl = DATA.bp.all.filter(function (x) { return x.local.slice(0, 10) >= cut; });
    var ecg = DATA.ecg.list.filter(function (x) { return x.local && x.local.slice(0, 10) >= cut; });
    /* ciagla os dni (bez dziur), zeby oba wykresy mialy ten sam dzien w tym samym miejscu */
    LABELS = [];
    for (var t = new Date(cut + "T12:00:00"); t.toISOString().slice(0, 10) <= todayIso; t = new Date(t.getTime() + 864e5)) LABELS.push(t.toISOString().slice(0, 10));
    var mapR = {}, mapH = {}; BPDAY = {}; ECGDAY = {};
    rhr.forEach(function (x) { mapR[x.date] = x.rhr; });
    hrp.forEach(function (x) { mapH[x.date] = x; });
    bpl.forEach(function (x) { var k = x.local.slice(0, 10); (BPDAY[k] = BPDAY[k] || []).push(x); });
    ecg.forEach(function (x) { var k = x.local.slice(0, 10); (ECGDAY[k] = ECGDAY[k] || []).push(x); });
    var red = css("--bad", "#e5534b"), blue = css("--blue", "#3b82f6"), ink2 = css("--ink2", "#888"), line = css("--line", "#ddd"),
        good = css("--good", "#3fa06a"), purple = css("--purple", "#9b6bd6");
    function L(f) { return LABELS.map(f); }

    var common = function (yScales, extraTip) {
      return {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: {mode: "index", intersect: false},
        plugins: {legend: {labels: {color: ink2, boxWidth: 12, font: {size: 11}}},
          tooltip: {filter: function (it) { return it.raw != null && !/^norma|^próg/.test(it.dataset.label); },
            callbacks: {title: function (it) { return it.length ? dd(it[0].label) : ""; }, afterBody: extraTip}}},
        scales: Object.assign({
          x: {ticks: {color: ink2, maxTicksLimit: 9, autoSkip: true, callback: function (v) { return dd(this.getLabelForValue(v)).slice(0, 5); }}, grid: {color: line}}
        }, yScales)
      };
    };

    var ds1 = [
      {label: "Tętno spoczynkowe", data: L(function (l) { return mapR[l] == null ? null : mapR[l]; }),
       borderColor: blue, backgroundColor: blue, borderWidth: 1.6, pointRadius: 0, pointHitRadius: 6, spanGaps: true, yAxisID: "y", tension: .25},
      {label: "Tętno przy 140–180 W", data: L(function (l) { return mapH[l] ? mapH[l].hr : null; }),
       borderColor: red, backgroundColor: red, showLine: false, pointRadius: 3.5, pointHoverRadius: 6, yAxisID: "y1"}
    ];
    if (DATA.rhr.norm != null) ds1.push({label: "norma spoczynkowe", data: L(function () { return DATA.rhr.norm; }),
      borderColor: blue, borderDash: [4, 4], borderWidth: 1, pointRadius: 0, yAxisID: "y"});
    if (DATA.hrp.norm != null) ds1.push({label: "norma przy mocy", data: L(function () { return DATA.hrp.norm; }),
      borderColor: red, borderDash: [4, 4], borderWidth: 1, pointRadius: 0, yAxisID: "y1"});

    var ds2 = [
      {label: "skurczowe", data: L(function (l) { return BPDAY[l] ? avg(BPDAY[l].map(function (m) { return m.sys; })) : null; }),
       borderColor: red, backgroundColor: red, borderWidth: 1.5, pointRadius: 4, pointHoverRadius: 6, spanGaps: true},
      {label: "rozkurczowe", data: L(function (l) { return BPDAY[l] ? avg(BPDAY[l].map(function (m) { return m.dia; })) : null; }),
       borderColor: purple, backgroundColor: purple, borderWidth: 1.5, pointRadius: 4, pointHoverRadius: 6, spanGaps: true},
      {label: "próg 135", data: L(function () { return 135; }), borderColor: red, borderDash: [4, 4], borderWidth: 1, pointRadius: 0},
      {label: "próg 85", data: L(function () { return 85; }), borderColor: purple, borderDash: [4, 4], borderWidth: 1, pointRadius: 0}
    ];

    charts().forEach(function (c) { c.destroy(); }); CH = {};
    CH["hz-canvas"] = new Chart(cv, {type: "line", data: {labels: LABELS.slice(), datasets: ds1},
      options: common({
        y: {position: "left", ticks: {color: blue}, grid: {color: line}, title: {display: true, text: "spoczynkowe", color: blue}},
        y1: {position: "right", ticks: {color: red}, grid: {drawOnChartArea: false}, title: {display: true, text: "przy mocy", color: red}}
      }, function (it) {
        var l = it.length && it[0].label, h = l && mapH[l];
        return h ? "jazda: " + h.w + " W średnio, " + h.min + " min w paśmie" : "";
      })});
    var vals = bpl.map(function (m) { return m.dia; }).concat(bpl.map(function (m) { return m.sys; }));
    CH["hz-bp"] = new Chart(cb, {type: "line", data: {labels: LABELS.slice(), datasets: ds2},
      options: common({
        y: {position: "left", suggestedMin: Math.min(70, Math.min.apply(null, vals.concat([70])) - 5),
            suggestedMax: Math.max(150, Math.max.apply(null, vals.concat([150])) + 5),
            ticks: {color: ink2}, grid: {color: line}, title: {display: true, text: "mmHg", color: ink2}},
        y1: {position: "right", display: true, ticks: {display: false}, grid: {drawOnChartArea: false}, title: {display: true, text: " ", color: ink2}}
      }, function (it) {
        var l = it.length && it[0].label, out = [];
        (BPDAY[l] || []).forEach(function (m) { out.push(hm(m.local) + "  " + m.sys + "/" + m.dia + (m.pulse ? " · tętno " + m.pulse : "")); });
        (ECGDAY[l] || []).forEach(function (e) { out.push("EKG " + hm(e.local) + ": " + e.label + (e.hr ? ", " + e.hr + " ud./min" : "")); });
        return out;
      })});
    var b = document.getElementById("hz-zoomreset"); if (b) b.hidden = true;
    alignSoon();
  }

  /* wyrownanie obszaru danych obu wykresow (rozne osie -> rozne marginesy) */
  var alT = null;
  function align() {
    var cs = charts().filter(function (c) { return c.chartArea; }); if (cs.length < 2) return;
    cs.forEach(function (c) { c.options.layout.padding = {left: 0, right: 0, top: 0, bottom: 0}; c.update("none"); });
    var Lf = Math.max.apply(null, cs.map(function (c) { return c.chartArea.left; })), Rr = Math.min.apply(null, cs.map(function (c) { return c.chartArea.right; }));
    cs.forEach(function (c) { c.options.layout.padding = {left: Math.max(0, Math.round(Lf - c.chartArea.left)), right: Math.max(0, Math.round(c.chartArea.right - Rr)), top: 0, bottom: 0}; c.update("none"); });
  }
  function alignSoon() { clearTimeout(alT); alT = setTimeout(align, 60); }
  window.addEventListener("resize", alignSoon);

  /* kursor + znaczniki EKG (plugin rejestrowany raz) */
  function regPlugin() {
    if (!window.Chart || !window.Chart.register) return setTimeout(regPlugin, 200);
    if (window._hzPlug) return; window._hzPlug = 1;
    window.Chart.register({id: "qhzcross", afterDatasetsDraw: function (ch) {
      var id = ch.canvas && ch.canvas.id; if (IDS.indexOf(id) < 0) return;
      var xA = ch.scales.x, a = ch.chartArea, c = ch.ctx; if (!xA || !a) return;
      if (id === "hz-bp") {
        LABELS.forEach(function (l, i) {
          if (!ECGDAY[l] || (xA.min != null && (i < xA.min || i > xA.max))) return;
          var x = xA.getPixelForValue(i), ok = ECGDAY[l].every(function (e) { return e.ok; });
          c.save(); c.fillStyle = ok ? css("--good", "#3fa06a") : css("--bad", "#e5534b");
          c.beginPath(); c.moveTo(x, a.top + 2); c.lineTo(x - 5, a.top + 11); c.lineTo(x + 5, a.top + 11); c.closePath(); c.fill();
          c.font = "600 9px system-ui"; c.textAlign = "center"; c.fillText("EKG", x, a.top + 21); c.restore();
        });
      }
      if (HOVER == null || (xA.min != null && (HOVER < xA.min || HOVER > xA.max))) return;
      var x = xA.getPixelForValue(HOVER);
      c.save(); c.strokeStyle = "rgba(148,163,184,.7)"; c.lineWidth = 1; c.setLineDash([3, 3]);
      c.beginPath(); c.moveTo(x, a.top); c.lineTo(x, a.bottom); c.stroke(); c.restore();
    }});
  }
  regPlugin();

  function idxOf(ch, ev) {
    var r = ch.canvas.getBoundingClientRect(), v = ch.scales.x.getValueForPixel(ev.clientX - r.left);
    return Math.max(0, Math.min(LABELS.length - 1, Math.round(v)));
  }
  function hover(src, ev) {
    var ch = CH[src.id]; if (!ch || !ch.scales.x) return;
    var i = idxOf(ch, ev); if (i === HOVER) return; HOVER = i;
    charts().forEach(function (c) {
      if (c === ch) { c.draw(); return; }
      var els = []; c.data.datasets.forEach(function (d, di) { if (c.isDatasetVisible(di) && d.data[i] != null && !/^norma|^próg/.test(d.label)) els.push({datasetIndex: di, index: i}); });
      try { var a = c.chartArea; c.setActiveElements(els); c.tooltip.setActiveElements(els, {x: c.scales.x.getPixelForValue(i), y: a.top + (a.bottom - a.top) / 2}); c.update("none"); } catch (e) { c.draw(); }
    });
  }
  var drag = null;
  document.addEventListener("mousemove", function (ev) {
    var t = ev.target;
    if (drag) {
      var r = drag.cv.getBoundingClientRect(), a = Math.max(0, Math.min(drag.x0, ev.clientX) - r.left), b2 = Math.min(r.width, Math.max(drag.x0, ev.clientX) - r.left);
      drag.box.style.left = a + "px"; drag.box.style.width = Math.max(0, b2 - a) + "px";
    }
    if (t && IDS.indexOf(t.id) >= 0) hover(t, ev);
  });
  document.addEventListener("mouseout", function (ev) {
    var t = ev.target; if (!t || IDS.indexOf(t.id) < 0) return; HOVER = null;
    charts().forEach(function (c) { try { c.setActiveElements([]); c.tooltip.setActiveElements([], {x: 0, y: 0}); c.update("none"); } catch (e) { c.draw(); } });
  });
  document.addEventListener("mousedown", function (ev) {
    var cv = ev.target; if (!cv || IDS.indexOf(cv.id) < 0 || ev.button !== 0) return; var ch = CH[cv.id]; if (!ch) return;
    var box = document.createElement("div");
    box.style.cssText = "position:absolute;top:0;bottom:0;left:0;width:0;background:rgba(59,130,246,.15);border:1px solid rgba(59,130,246,.6);pointer-events:none;z-index:4";
    cv.parentNode.appendChild(box); drag = {ch: ch, cv: cv, x0: ev.clientX, i0: idxOf(ch, ev), box: box}; ev.preventDefault();
  });
  document.addEventListener("mouseup", function (ev) {
    if (!drag) return; var d = drag; drag = null; d.box.remove();
    var i1 = idxOf(d.ch, ev), a = Math.min(d.i0, i1), b2 = Math.max(d.i0, i1);
    if (b2 - a >= 2 && Math.abs(ev.clientX - d.x0) > 8) { ZOOM = {min: a, max: b2}; applyZoom(); }
  });
  document.addEventListener("dblclick", function (ev) { if (ev.target && IDS.indexOf(ev.target.id) >= 0 && ZOOM) { ZOOM = null; applyZoom(); } });
  document.addEventListener("click", function (ev) { if (ev.target && ev.target.id === "hz-zoomreset") { ZOOM = null; applyZoom(); } });

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
