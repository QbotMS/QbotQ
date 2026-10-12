/* JEDZENIE (2026-10-12) - strona /jedzenie.html. Dane i zapis: /api/jedzenie/* (qbot_food_api.py). Dok.: docs/BROKUL.md
   Zakladki: Dni (karta dnia: Brokul, lodowka, wpisy poza dieta, okno, zamkniecie) | Pasy | Bilans i waga | Menu Brokula. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var S = { days: null, sel: null, today: null, tab: "dni", loaded: {} };
  var DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"];

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function n0(v) { return v == null ? "–" : Math.round(v).toLocaleString("pl-PL"); }
  function n1(v) { return v == null ? "–" : (Math.round(v * 10) / 10).toLocaleString("pl-PL"); }
  function dm(iso) { return iso ? iso.slice(8, 10) + "." + iso.slice(5, 7) : ""; }
  function dmy(iso) { return iso ? dm(iso) + "." + iso.slice(0, 4) : ""; }
  function wd(iso) { var d = new Date(iso + "T12:00:00"); return DN[(d.getDay() + 6) % 7]; }
  function j(u, o) {
    return fetch(u, Object.assign({ credentials: "same-origin", cache: "no-store" }, o || {})).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (x) { if (!r.ok) throw new Error(x.detail || ("HTTP " + r.status)); return x; });
    });
  }
  function post(u, b) { return j(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }); }

  /* ------------------------------------------------------------ zakladki */
  function tab(t) {
    S.tab = t;
    document.querySelectorAll("#tabs button").forEach(function (b) { b.setAttribute("aria-selected", b.dataset.t === t ? "true" : "false"); });
    ["dni", "pasy", "bilans", "menu"].forEach(function (k) { $("t-" + k).hidden = k !== t; });
    try { history.replaceState(null, "", "#" + t); } catch (e) {}
    if (t === "pasy") loadPasy();
    if (t === "bilans" && !S.loaded.bilans) loadBilans();
    if (t === "menu" && !S.loaded.menu) loadMenu();
  }
  document.querySelectorAll("#tabs button").forEach(function (b) { b.onclick = function () { tab(b.dataset.t); }; });

  /* ------------------------------------------------------------ naglowek: pasy */
  function loadHeader() {
    return j("/api/jedzenie/streaks").then(function (x) {
      S.streaks = x;
      var s = x.streaks, fr = (s.food.freezes || 0) + (s.window.freezes || 0) + (s.train.freezes || 0);
      $("hs").innerHTML = [["🔥", "Jedzenie", s.food.n, "dni"], ["🕗", "Okno", s.window.n, "dni"], ["💪", "Trening", s.train.n, "dni"], ["📉", "Redukcja", s.reduce.n, "tyg."]]
        .map(function (p) { return "<span class='pill' title='" + p[1] + "'>" + p[0] + " <b>" + p[2] + "</b> " + p[3] + "</span>"; }).join("") +
        (fr ? "<span class='pill' title='Mrożenia ratujące pas'>❄️ <b>" + fr + "</b></span>" : "");
      if (S.tab === "pasy") renderPasy();
    }).catch(function () {});
  }

  /* ------------------------------------------------------------ DNI */
  function loadDays(keepSel) {
    return j("/api/jedzenie/days").then(function (x) {
      S.days = x.days; S.today = x.today; S.ctx = { balance: x.balance, calib: x.calib };
      if (!keepSel || !S.days.some(function (d) { return d.day === S.sel; })) S.sel = x.today;
      renderStrip(); renderDay();
    }).catch(function (e) { $("dayview").innerHTML = "<p class='msg'>Nie udało się wczytać dni: " + esc(e.message) + "</p>"; });
  }
  function dayObj(iso) { return (S.days || []).filter(function (d) { return d.day === iso; })[0]; }
  function renderStrip() {
    $("daystrip").innerHTML = S.days.map(function (d) {
      var fut = d.day > S.today, cls = fut ? "fut" : (d.closed ? "ok" : "open");
      return "<button class='daychip" + (d.day === S.today ? " today" : "") + "' role='listitem' data-d='" + d.day + "'" + (d.day === S.sel ? " aria-current='true'" : "") + ">" +
        "<i class='" + cls + "'></i>" + d.weekday + " " + dm(d.day) + "<small>" + (fut ? (d.has_diet ? "menu" : "plan") : (d.closed ? "zamknięty" : "otwarty")) + (d.has_diet ? " · 🥦" : "") + "</small></button>";
    }).join("");
    $("daystrip").querySelectorAll(".daychip").forEach(function (b) { b.onclick = function () { S.sel = b.dataset.d; renderStrip(); renderDay(); }; });
    var cur = $("daystrip").querySelector("[aria-current=true]"); if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: "nearest", inline: "center" });
  }
  function refreshDay(iso) {
    return j("/api/jedzenie/day?day=" + iso).then(function (d) {
      S.days = S.days.map(function (x) { return x.day === iso ? d : x; }); renderStrip(); if (S.sel === iso) renderDay(); loadHeader();
    });
  }
  function act(btn, u, b, days) {
    var box = btn && btn.closest(".card"); if (box) box.classList.add("busy");
    return post(u, b).then(function () { return Promise.all((days || [S.sel]).map(refreshDay)); })
      .catch(function (e) { alert(e.message); }).then(function () { if (box) box.classList.remove("busy"); });
  }

  var MK = { pewne: ["", "c-p"], "średnie": ["~", "c-s"], zgrubne: ["?", "c-z"] };
  function itemsTable(e) {
    var sc = e.scale || 1;
    return "<table class='items'>" + (e.items || []).map(function (it) {
      var m = MK[it.conf] || ["", ""];
      return "<tr><td class='k'>" + n0((it.kcal || 0) * sc) + "</td><td class='c " + m[1] + "' title='" + esc(it.conf || "") + "'>" + m[0] + "</td><td>" +
        esc(it.short || it.name) + (it.src && /^(historia|etykieta|poprawka|Open)/.test(it.src) ? " <span class='muted'>(" + esc(it.src) + ")</span>" : "") + "</td></tr>";
    }).join("") + "</table>";
  }
  function entryHTML(e, d) {
    var raw = e.kind === "quick" ? "" : "<div class='raw'>" + esc(e.raw_text || "zdjęcie") + "</div>";
    var tm = e.eaten_time ? " · " + esc(e.eaten_time.slice(0, 5)) : "";
    if (e.status === "asking") {
      return "<div class='ent'><div class='eh'><span><b>#" + e.id + "</b>" + tm + " · " + esc(e.question || "Ile?") + "</span></div>" + raw +
        "<div class='acts' style='margin-top:6px'>" + (e.options || []).map(function (o, i) {
          var k = (o.items || []).reduce(function (a, b) { return a + (b.kcal || 0); }, 0);
          return "<button class='btn sm' data-a='opt' data-id='" + e.id + "' data-i='" + i + "'>" + esc(o.label) + " · " + n0(k) + " kcal</button>";
        }).join("") + "<button class='btn sm' data-a='del' data-id='" + e.id + "'>Usuń</button></div></div>";
    }
    if (e.status !== "logged") {
      return "<div class='ent'><div class='eh'><span><b>#" + e.id + "</b> · liczenie w toku</span></div>" + raw + "<div class='acts'><button class='btn sm' data-a='del' data-id='" + e.id + "'>Usuń</button></div></div>";
    }
    var sc = e.scale || 1;
    return "<div class='ent'><div class='eh'><span><b>#" + e.id + "</b>" + tm + (Math.abs(sc - 1) > 1e-6 ? " · ×" + n1(sc) : "") + "</span><span class='k'>" + n0(e.kcal) + " kcal</span></div>" + raw + itemsTable(e) +
      "<div class='acts'><button class='btn sm' data-a='down' data-id='" + e.id + "' title='Zmniejsz o 25%'>−25%</button><button class='btn sm' data-a='up' data-id='" + e.id + "' title='Zwiększ o 25%'>+25%</button>" +
      "<input id='fx-" + e.id + "' placeholder='poprawka, np. „makaron 600 g”' style='flex:1;min-width:150px'><button class='btn sm' data-a='fix' data-id='" + e.id + "'>Popraw</button>" +
      "<input type='date' id='mv-" + e.id + "' value='" + d.day + "' style='width:140px' aria-label='Przenieś na dzień'><button class='btn sm' data-a='move' data-id='" + e.id + "'>Przenieś</button>" +
      "<button class='btn sm' data-a='del' data-id='" + e.id + "'>Usuń</button></div></div>";
  }
  function mealRow(m, d, fridge) {
    var mx = n0(m.kcal) + " kcal · B " + n0(m.protein_g) + " · W " + n0(m.carbs_g) + " · T " + n0(m.fat_g);
    var seg;
    if (fridge) {
      seg = "<div class='seg'><button data-a='m' data-id='" + m.id + "' data-s='eaten' data-ed='" + d.day + "' class='" + (m.status === "eaten" ? "on g" : "") + "'>✅ Zjadłem " + dm(d.day) + "</button>" +
        "<button data-a='m' data-id='" + m.id + "' data-s='discarded' class='" + (m.status === "discarded" ? "on b" : "") + "'>🗑 Wyrzucone</button>" +
        "<button data-a='m' data-id='" + m.id + "' data-s='fridge' class='" + (m.status === "fridge" ? "on" : "") + "'>📦 W lodówce</button></div>";
    } else {
      seg = "<div class='seg'>" + [["eaten", "✅ Zjadłem", "g"], ["skipped", "❌ Nie", "b"], ["fridge", "📦 Później", ""]].map(function (o) {
        var on = m.status === o[0];
        return "<button data-a='m' data-id='" + m.id + "' data-s='" + (on ? "pending" : o[0]) + "' class='" + (on ? "on " + o[2] : "") + "' aria-pressed='" + on + "'>" + o[1] + "</button>";
      }).join("") + "</div>";
    }
    return "<div class='meal'><div class='nm'><b>" + esc(m.meal_type) + (fridge ? " z " + dm(m.day) : "") + "</b> · " + esc(m.name) + "<div class='mx'>" + mx + "</div></div>" + seg + "</div>";
  }
  function renderDay() {
    var d = dayObj(S.sel); if (!d) { $("dayview").innerHTML = "<p class='empty'>Brak danych dla tego dnia.</p>"; return; }
    var fut = d.day > S.today, H = [];
    var L = [];
    if (d.has_diet) {
      var pend = d.meals.filter(function (m) { return m.status === "pending"; }).length;
      L.push("<div class='card'><div class='ttl'><h2>🥦 Brokuł</h2><span class='sub'>" + n0(d.brokul_kcal) + " kcal</span></div>" +
        d.meals.map(function (m) { return mealRow(m, d, false); }).join("") +
        (pend >= 2 && !fut ? "<div class='acts' style='margin-top:8px'><button class='btn sm' data-a='all' data-v='eaten'>✅ Wszystkie zjedzone</button><button class='btn sm' data-a='all' data-v='fridge'>📦 Wszystkie na później</button></div>" : "") + "</div>");
    }
    if (d.fridge.length) L.push("<div class='card'><div class='ttl'><h2>📦 Z lodówki</h2><span class='sub'>dieta z wcześniejszych dni</span></div>" + d.fridge.map(function (m) { return mealRow(m, d, true); }).join("") + "</div>");
    if (!fut || d.entries.length) {
      var qs = d.has_diet
        ? [["snack", "🥨 Przekąska"], ["sweet", "🍫 Słodycze"], ["out_s", "🍽 Na mieście S"], ["out_m", "🍽 M"], ["out_l", "🍽 L"]]
        : [["bf_s", "🍳 Śniadanie S"], ["bf_m", "🍳 M"], ["bf_l", "🍳 L"], ["ln_s", "🍲 Obiad S"], ["ln_m", "🍲 M"], ["ln_l", "🍲 L"], ["dn_s", "🌙 Kolacja S"], ["dn_m", "🌙 M"], ["dn_l", "🌙 L"], ["snack", "🥨 Przekąska"], ["sweet", "🍫 Słodycze"]];
      L.push("<div class='card'><div class='ttl'><h2>🍴 " + (d.has_diet ? "Poza dietą" : "Zjedzone") + "</h2><span class='sub'>" + (d.entries.length ? d.entries.length + " wpis(y)" : "") + "</span></div>" +
        (d.entries.length ? d.entries.map(function (e) { return entryHTML(e, d); }).join("") : (d.has_diet && d.none ? "<p class='empty'>✔ Nic poza dietą.</p>" : "<p class='empty'>Jeszcze nic. Wpisz poniżej albo napisz do bota na Telegramie.</p>")) +
        "<div class='add' style='margin-top:10px'><textarea id='addtxt' placeholder='Co zjadłeś? Np. „2 pączki i duża latte”, „pizza margherita cała”, „4 kabanosy z Biedronki”'></textarea>" +
        "<div class='row'><button class='btn pri' data-a='add'>Dodaj i policz</button><span class='sub'>QBot policzy kcal i makra (z Twojej historii, jeśli już to jadłeś).</span></div><div id='addmsg' class='msg'></div></div>" +
        "<div class='chips'><span class='lbl2'>Szybko, gdy nie pamiętasz szczegółów (zgrubny szacunek):</span>" +
        (d.has_diet ? "<button class='btn sm" + (d.none ? " pri" : "") + "' data-a='none'>" + (d.none ? "✔ Nic poza dietą" : "Nic poza dietą") + "</button>" : "") +
        qs.map(function (q) { return "<button class='btn sm' data-a='quick' data-c='" + q[0] + "'>" + q[1] + "</button>"; }).join("") + "</div></div>");
    }
    // prawa kolumna
    var t = d.totals.kcal || 0, pct = d.target ? Math.min(100, t / d.target * 100) : 0, over = t > d.target;
    var R = [];
    R.push("<div class='card'><div class='ttl'><h2>" + (d.day === S.today ? "Dziś" : wd(d.day) + " " + dm(d.day)) + "</h2><span class='state " + (fut ? "" : (d.closed ? "ok" : "open")) + "'>" +
      (fut ? "plan" : (d.closed ? "🔒 zamknięty" : "⏳ otwarty")) + "</span></div>" +
      "<div class='big2'>" + n0(t) + " <span class='sub' style='font-size:16px'>/ " + n0(d.target) + " kcal</span></div>" +
      "<div class='meter' role='progressbar' aria-valuenow='" + Math.round(t) + "' aria-valuemax='" + d.target + "' aria-label='Zjedzone względem celu'><i class='" + (over ? "over" : "") + "' style='width:" + pct.toFixed(1) + "%'></i></div>" +
      "<div class='sub'>" + (over ? "ponad cel o " + n0(t - d.target) + " kcal" : "zostało " + n0(d.target - t) + " kcal") + "</div>" +
      "<div class='kv'><span>Białko</span><span>" + n0(d.totals.protein_g) + " g</span><span>Węglowodany</span><span>" + n0(d.totals.carbs_g) + " g</span><span>Tłuszcz</span><span>" + n0(d.totals.fat_g) + " g</span>" +
      "<span>Spalanie</span><span>" + n0(d.expend) + " kcal" + (d.expend_src === "prognoza" ? " (prognoza)" : "") + "</span><span>Cel bilansu</span><span>" + n0(S.ctx.balance) + " kcal</span>" +
      (d.brokul_kcal ? "<span>Dokładka do Brokuła</span><span>" + (d.extra >= 150 ? n0(d.extra) + " kcal" : "nie trzeba") + "</span>" : "") + "</div>" +
      (d.sessions.length ? "<div class='note'>🚲 " + d.sessions.map(function (s) { return esc(s.name) + " " + s.dur_min + "′" + (s.start_time ? " o " + s.start_time.slice(0, 5) : ""); }).join("; ") + "</div>" : "") +
      (!fut && !d.closed ? "<div class='note'>Do zamknięcia: " + [d.pending ? "potwierdź posiłki Brokuła" : "", (!d.entries.length && !d.none) ? (d.has_diet ? "dopisz jedzenie poza dietą albo kliknij „Nic poza dietą”" : "dopisz, co zjadłeś") : ""].filter(Boolean).join("; ") +
        ". Termin pasa: " + dm(d.deadline.slice(0, 10)) + " 12:00.</div>" : "") + "</div>");
    if (!fut) {
      var w = d.window, wtxt = { ok: "✔ dotrzymane", broken: "✖ złamane", exempt: "zwolnione", pending: "do potwierdzenia" }[w.state] || w.state;
      R.push("<div class='card'><div class='ttl'><h2>🕗 Okno 10–20</h2><span class='state " + (w.state === "ok" ? "ok" : "") + "'>" + wtxt + "</span></div>" +
        (w.detail ? "<div class='note'>" + esc(w.detail) + "</div>" : "") +
        (w.state !== "exempt" ? "<div class='acts' style='margin-top:8px'><button class='btn" + (w.state === "ok" ? " pri" : "") + "' data-a='win' data-v='1'" + (d.late ? " disabled" : "") + ">🕗 Dotrzymane</button>" +
          "<button class='btn" + (w.state === "broken" ? " pri" : "") + "' data-a='win' data-v='0'" + (d.late ? " disabled" : "") + ">✖ Złamane</button></div>" +
          (d.late ? "<div class='note'>Termin minął (12:00 następnego dnia).</div>" : "<div class='note'>Przed 10:00 tylko czarna kawa, po 20:00 nic. Zwolnione: trening ≥1,5 h, delegacja, urlop, wyprawa.</div>") : "") + "</div>");
    }
    $("dayview").innerHTML = "<div class='dgrid'><div class='stack'>" + L.join("") + "</div><div class='stack'>" + R.join("") + "</div></div>";
    wireDay(d);
  }
  function wireDay(d) {
    var V = $("dayview");
    V.querySelectorAll("[data-a]").forEach(function (b) {
      var a = b.dataset.a; if (b.tagName === "INPUT") return;
      b.onclick = function () {
        var id = +b.dataset.id;
        if (a === "m") return act(b, "/api/jedzenie/brokul", { id: id, status: b.dataset.s, eaten_day: b.dataset.ed || null }, uniq([d.day]));
        if (a === "all") return act(b, "/api/jedzenie/brokul/all", { day: d.day, action: b.dataset.v });
        if (a === "win") return act(b, "/api/jedzenie/window", { day: d.day, ok: b.dataset.v === "1" });
        if (a === "none") return act(b, "/api/jedzenie/none", { day: d.day, value: !d.none });
        if (a === "quick") return act(b, "/api/jedzenie/quick", { day: d.day, code: b.dataset.c });
        if (a === "up" || a === "down") return act(b, "/api/jedzenie/entry/scale", { id: id, dir: a });
        if (a === "opt") return act(b, "/api/jedzenie/entry/option", { id: id, idx: +b.dataset.i });
        if (a === "del") { if (!confirm("Usunąć wpis #" + id + "?")) return; return act(b, "/api/jedzenie/entry/delete", { id: id }); }
        if (a === "fix") { var v = ($("fx-" + id).value || "").trim(); if (!v) return $("fx-" + id).focus(); b.textContent = "Poprawiam…"; return act(b, "/api/jedzenie/entry/fix", { id: id, text: v }); }
        if (a === "move") { var nd = $("mv-" + id).value; if (!nd || nd === d.day) return; return act(b, "/api/jedzenie/entry/move", { id: id, day: nd }, uniq([d.day, nd]).filter(function (x) { return !!dayObj(x); })); }
        if (a === "add") {
          var tx = ($("addtxt").value || "").trim(); if (!tx) return $("addtxt").focus();
          b.disabled = true; b.textContent = "Liczę… (kilka sekund)"; $("addmsg").textContent = "";
          return post("/api/jedzenie/entry", { day: d.day, text: tx }).then(function (r) {
            return refreshDay(d.day).then(function () { var m = $("addmsg"); if (m) { m.className = "msg ok"; m.textContent = r.entry && r.entry.status === "asking" ? "Wybierz porcję przy wpisie #" + r.entry.id + "." : "Dodane (#" + r.entry.id + ")."; } });
          }).catch(function (e) { $("addmsg").className = "msg"; $("addmsg").textContent = e.message; b.disabled = false; b.textContent = "Dodaj i policz"; });
        }
      };
    });
    var ta = $("addtxt"); if (ta) ta.onkeydown = function (ev) { if ((ev.metaKey || ev.ctrlKey) && ev.key === "Enter") V.querySelector("[data-a=add]").click(); };
  }
  function uniq(a) { return a.filter(function (x, i) { return x && a.indexOf(x) === i; }); }

  /* ------------------------------------------------------------ PASY */
  function loadPasy() { return loadHeader().then(renderPasy); }
  function calGrid(days) {
    if (!days.length) return "<p class='empty'>Jeszcze brak dni.</p>";
    var first = new Date(days[0][0] + "T12:00:00"), lead = (first.getDay() + 6) % 7, cells = [];
    for (var i = 0; i < lead; i++) cells.push("<i class='none'></i>");
    days.forEach(function (x) { cells.push("<i class='" + x[1] + "' title='" + wd(x[0]) + " " + dm(x[0]) + ": " + ({ ok: "zaliczony", fail: "niezaliczony", frozen: "uratowany mrożeniem", neutral: "neutralny / w toku" }[x[1]] || x[1]) + "'></i>"); });
    return "<div class='cal' aria-label='Mapa dni'>" + cells.join("") + "</div>";
  }
  function renderPasy() {
    var x = S.streaks; if (!x) return;
    var s = x.streaks, nx = x.next;
    var D = [["food", "🔥", "Jedzenie", "dni", "dzień uczciwie zamknięty (przekroczenie nie zrywa)"], ["window", "🕗", "Okno 10–20", "dni", "okno dotrzymane; trening ≥1,5 h, delegacja, urlop = neutralnie"],
      ["train", "💪", "Trening", "dni", "zgodnie z planem Trenera; odpoczynek też się liczy, choroba = neutralnie"], ["reduce", "📉", "Redukcja", "tyg.", "tydzień: ≥2 ważenia, ≥5 zamkniętych dni, bilans w widełkach celu"]];
    var html = "<div class='s4'>" + D.map(function (p) {
      var v = s[p[0]], to = nx[p[0]], pct = to ? Math.min(100, v.n / to * 100) : 100;
      return "<div class='card sk'><div class='e'>" + p[1] + "</div><div class='n'>" + v.n + "<small>" + p[3] + "</small></div><div class='t'>" + p[2] + " · " + p[4] + "</div>" +
        "<div class='meter' style='margin-top:8px'><i style='width:" + pct.toFixed(0) + "%'></i></div><div class='sub' style='font-size:12.5px'>" + (to ? "do " + to + " " + p[3] + ": jeszcze " + (to - v.n) : "") +
        (v.freezes ? " · ❄️ " + v.freezes : "") + (v.used ? " · uratowane " + v.used + "×" : "") + "</div>" +
        (p[0] === "reduce" ? "<div class='wkrow'>" + v.days.map(function (w) { return "<i class='" + w[1] + "' title='tydzień od " + dm(w[0]) + "'></i>"; }).join("") + "</div>" +
          (v.current ? "<div class='note'>Ten tydzień (od " + dm(v.current.week) + "): ważenia " + v.current.weighings + "/2, zamknięte dni " + v.current.days + "/5" +
            (v.current.avg_balance != null ? ", bilans " + n0(v.current.avg_balance) + " kcal/dz (cel " + n0(v.current.target) + ")" : "") + "</div>" : "")
          : calGrid(v.days)) + "</div>";
    }).join("") + "</div>";
    html += "<div class='legend'><span><i style='background:var(--good)'></i>zaliczony</span><span><i style='background:var(--bad)'></i>niezaliczony</span><span><i style='background:var(--blue)'></i>uratowany mrożeniem</span><span><i style='background:var(--line2)'></i>neutralny / w toku</span></div>";
    html += "<div class='card' style='margin-top:12px'><p class='note' style='margin:0'>Zasady: dzień zamykasz do 12:00 następnego dnia. Za każde 7 dni pasa dostajesz 1 mrożenie (maks. 2) – ratuje pas przy jednym gorszym dniu. Kamienie milowe: " + x.milestones.join(", ") + ".</p></div>";
    $("pasy").innerHTML = html;
  }

  /* ------------------------------------------------------------ BILANS */
  function loadBilans() {
    S.loaded.bilans = true;
    j("/api/jedzenie/balance?days=42").then(renderBilans).catch(function (e) { S.loaded.bilans = false; $("bilans").innerHTML = "<p class='msg'>" + esc(e.message) + "</p>"; });
  }
  function balChart(ser) {
    var W = 900, H = 260, pl = 44, pr = 10, pt = 12, pb = 26, n = ser.length;
    var mx = Math.max.apply(null, ser.map(function (x) { return Math.max(x.expend || 0, x.intake || 0, x.target || 0); })) * 1.08;
    var bw = (W - pl - pr) / n;
    function X(i) { return pl + i * bw; } function Y(v) { return pt + (1 - v / mx) * (H - pt - pb); }
    var s = "<svg viewBox='0 0 " + W + " " + H + "' style='width:100%;min-width:620px;height:auto;display:block;color:inherit' role='img' aria-label='Bilans dzienny: zjedzone, spalone, cel'>";
    for (var v = 0; v <= mx; v += 1000) s += "<line x1='" + pl + "' x2='" + (W - pr) + "' y1='" + Y(v).toFixed(1) + "' y2='" + Y(v).toFixed(1) + "' stroke='var(--line)'/><text x='" + (pl - 5) + "' y='" + (Y(v) + 4).toFixed(1) + "' font-size='11' text-anchor='end' fill='var(--muted)'>" + v + "</text>";
    ser.forEach(function (x, i) {
      if (x.intake != null) s += "<rect x='" + (X(i) + bw * 0.18).toFixed(1) + "' y='" + Y(x.intake).toFixed(1) + "' width='" + (bw * 0.64).toFixed(1) + "' height='" + (Y(0) - Y(x.intake)).toFixed(1) + "' rx='2' fill='" + (x.closed ? "var(--accent)" : "none") + "' stroke='var(--accent)' stroke-width='1.2'><title>" + dm(x.day) + ": zjedzone " + n0(x.intake) + ", spalone " + n0(x.expend) + ", cel " + n0(x.target) + (x.closed ? "" : " (dzień otwarty)") + "</title></rect>";
      if (i % 7 === 0 || i === n - 1) s += "<text x='" + (X(i) + bw / 2).toFixed(1) + "' y='" + (H - 8) + "' font-size='11' text-anchor='middle' fill='var(--muted)'>" + dm(x.day) + "</text>";
    });
    function ln(k, col, dash) { return "<path d='" + ser.map(function (x, i) { return (i ? "L" : "M") + (X(i) + bw / 2).toFixed(1) + " " + Y(x[k]).toFixed(1); }).join(" ") + "' fill='none' stroke='" + col + "' stroke-width='1.8'" + (dash ? " stroke-dasharray='" + dash + "'" : "") + "/>"; }
    s += ln("expend", "var(--blue)") + ln("target", "var(--good)", "6 4");
    return s + "</svg><div class='legend'><span><i style='background:var(--accent)'></i>zjedzone (dzień zamknięty)</span><span><i style='border:1px solid var(--accent)'></i>zjedzone (otwarty)</span><span><i style='background:var(--blue)'></i>spalone</span><span><i style='background:var(--good)'></i>cel dnia</span></div>";
  }
  function wchart(ch) {
    var W = 640, H = 210, pl = 34, pr = 10, pt = 18, pb = 14;
    var pts = ch.plan.concat(ch.meas).concat(ch.forecast || []);
    var ts = pts.map(function (p) { return Date.parse(p[0]); }), t0 = Math.min.apply(null, ts), t1 = Math.max.apply(null, ts);
    var ys = pts.map(function (p) { return p[1]; }), y0 = Math.floor(Math.min.apply(null, ys) - 1.5), y1 = Math.ceil(Math.max.apply(null, ys) + 1.5);
    function X(d) { return pl + (Date.parse(d) - t0) / Math.max(1, t1 - t0) * (W - pl - pr); }
    function Y(v) { return pt + (y1 - v) / Math.max(1, y1 - y0) * (H - pt - pb); }
    function ln(a, off) { return a.map(function (p, i) { return (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1] + (off || 0)).toFixed(1); }).join(" "); }
    var band = ln(ch.plan, ch.band) + " " + ch.plan.slice().reverse().map(function (p) { return "L" + X(p[0]).toFixed(1) + " " + Y(p[1] - ch.band).toFixed(1); }).join(" ") + " Z";
    var s = "<svg viewBox='0 0 " + W + " " + H + "' style='width:100%;max-width:760px;height:auto;display:block;color:inherit' role='img' aria-label='Waga: plan, ważenia, prognoza'>";
    for (var v = y0 + (y0 % 2 ? 1 : 0); v <= y1; v += 2) s += "<line x1='" + pl + "' x2='" + (W - pr) + "' y1='" + Y(v).toFixed(1) + "' y2='" + Y(v).toFixed(1) + "' stroke='var(--line)'/><text x='" + (pl - 4) + "' y='" + (Y(v) + 3.5).toFixed(1) + "' font-size='10' text-anchor='end' fill='var(--muted)'>" + v + "</text>";
    s += "<path d='" + band + "' fill='var(--good)' opacity='.13'/><path d='" + ln(ch.plan) + "' fill='none' stroke='var(--good)' stroke-width='2' stroke-dasharray='6 4'/>";
    if (ch.forecast) s += "<path d='" + ln(ch.forecast) + "' fill='none' stroke='var(--warn)' stroke-width='1.6' stroke-dasharray='2 4'/>";
    if (ch.meas.length > 1) s += "<path d='" + ln(ch.meas) + "' fill='none' stroke='currentColor' stroke-width='1.4' opacity='.8'/>";
    ch.meas.forEach(function (p) { s += "<circle cx='" + X(p[0]).toFixed(1) + "' cy='" + Y(p[1]).toFixed(1) + "' r='2.6' fill='currentColor'><title>" + dm(p[0]) + ": " + n1(p[1]) + " kg</title></circle>"; });
    ch.plan.slice(1).forEach(function (p, i, a) { var x = X(p[0]); s += "<circle cx='" + x.toFixed(1) + "' cy='" + Y(p[1]).toFixed(1) + "' r='4' fill='var(--good)'/><text x='" + x.toFixed(1) + "' y='" + (Y(p[1]) - 8).toFixed(1) + "' font-size='10' text-anchor='" + (i === a.length - 1 ? "end" : "middle") + "' fill='var(--muted)'>" + p[1] + " kg · " + dm(p[0]) + "</text>"; });
    var tx = X(ch.today).toFixed(1);
    s += "<line x1='" + tx + "' x2='" + tx + "' y1='" + pt + "' y2='" + (H - pb) + "' stroke='var(--muted)' stroke-dasharray='2 3'/><text x='" + tx + "' y='" + (pt - 6) + "' font-size='10' text-anchor='middle' fill='var(--muted)'>dziś</text>";
    return s + "</svg><div class='legend'><span>– – plan z korytarzem ±1 kg</span><span>● ważenia</span><span>··· prognoza przy obecnym tempie</span></div>";
  }
  function renderBilans(x) {
    var h = "<div class='card'><div class='ttl'><h2>Bilans dzienny (42 dni)</h2><span class='sub'>cel bilansu " + n0(x.balance_target) + " kcal/dz" + (x.calib ? " · kalibracja " + n0(-x.calib) : "") + "</span></div><div class='chartbox'>" + balChart(x.series) + "</div></div>";
    var g = x.goal;
    h += "<div class='g2' style='margin-top:12px'><div class='card'><div class='ttl'><h2>⚖️ " + esc(g ? g.name : "Waga") + "</h2></div>" +
      (g ? "<div class='state " + (g.level === "g" ? "ok" : "open") + "'>" + esc(g.text) + "</div>" + (g.chart ? wchart(g.chart) : "") +
        "<div class='kv'>" + (g.rows || []).map(function (r) { return "<span>" + esc(r.k) + "</span><span>" + esc(r.have == null ? "" : r.have) + (r.need != null ? " / " + esc(r.need) : "") + "</span>"; }).join("") + "</div>"
        : "<p class='empty'>Brak celu wagi w Trenerze.</p>") + "</div>";
    var dsc = x.discrepancy || {};
    h += "<div class='stack'><div class='card'><div class='ttl'><h2>Waga vs jedzenie</h2></div><p class='note' style='margin-top:0'>" + esc(x.discrepancy_line) + "</p>" +
      (dsc.ready ? "<div class='kv'><span>Bilans z wpisów</span><span>" + n0(dsc.logged_bal) + " kcal/dz</span><span>Bilans z wagi</span><span>" + n0(dsc.actual_bal) + " kcal/dz</span><span>Rozbieżność</span><span>" + n0(dsc.disc) + " kcal/dz</span></div>" : "") +
      "<p class='note'>Porównuje to, co wynika z zapisanego jedzenia, z tym, co pokazuje waga (prawdziwe ważenia). Duża rozbieżność = coś umyka albo Garmin myli się co do spalania. QBot sam koryguje o nią cel dnia.</p></div>" +
      "<div class='card'><div class='ttl'><h2>Tygodnie</h2></div>" + (x.weeks.length ? "<table class='tb'><tr><th>Tydzień od</th><th class='r'>Zamknięte dni</th><th class='r'>Śr. bilans</th></tr>" +
        x.weeks.slice().reverse().map(function (w) { var ok = w.avg_balance >= x.balance_target - 300 && w.avg_balance <= x.balance_target + 250; return "<tr><td>" + dm(w.week) + "</td><td class='r'>" + w.days + "</td><td class='r' style='color:var(--" + (ok ? "good" : "bad") + ")'>" + n0(w.avg_balance) + "</td></tr>"; }).join("") + "</table>"
        : "<p class='empty'>Jeszcze brak zamkniętych dni z pełnym spalaniem.</p>") + "</div></div></div>";
    $("bilans").innerHTML = h;
  }

  /* ------------------------------------------------------------ MENU */
  function loadMenu() {
    S.loaded.menu = true;
    j("/api/jedzenie/menu").then(renderMenu).catch(function (e) { S.loaded.menu = false; $("menu").innerHTML = "<p class='msg'>" + esc(e.message) + "</p>"; });
  }
  function renderMenu(x) {
    var by = {};
    x.meals.forEach(function (m) { (by[m.day] = by[m.day] || []).push(m); });
    var h = "<div class='card'><div class='ttl'><h2>🥦 Dieta od Brokuła</h2><span class='sub'>" + (x.order_end ? "zamówienie do " + wd(x.order_end) + " " + dmy(x.order_end) : "brak zamówienia") + "</span></div>" +
      "<div class='note' style='margin-top:0'>" + (x.session_alive ? "Połączenie z Brokułem działa" : "⚠️ Sesja Brokuła nie działa – <a href='" + x.access_url + "'>wklej nowe ciasteczka</a>") +
      (x.last_import ? " · ostatni import " + dm(x.last_import.slice(0, 10)) + " " + x.last_import.slice(11, 16) : "") + "</div></div>";
    if (x.fridge.length) h += "<div class='card' style='margin-top:12px'><div class='ttl'><h2>📦 Lodówka</h2></div>" + x.fridge.map(function (m) { return "<div class='meal'><div class='nm'><b>" + esc(m.meal_type) + " z " + dm(m.day) + "</b> · " + esc(m.name) + "<div class='mx'>" + n0(m.kcal) + " kcal</div></div><span></span></div>"; }).join("") + "</div>";
    Object.keys(by).sort().forEach(function (d) {
      var ms = by[d], tot = ms.reduce(function (a, m) { return a + (m.kcal || 0); }, 0);
      h += "<div class='card' style='margin-top:12px'><div class='ttl'><h2>" + wd(d) + " " + dm(d) + "</h2><span class='sub'>" + n0(tot) + " kcal</span></div><div class='chartbox'><table class='tb'>" +
        "<tr><th>Posiłek</th><th class='r'>kcal</th><th class='r'>B</th><th class='r'>W</th><th class='r'>cukry</th><th class='r'>T</th><th class='r'>nas.</th><th class='r'>sól</th></tr>" +
        ms.map(function (m) {
          return "<tr><td><b>" + esc(m.meal_type) + "</b> · " + esc(m.name) + (m.ingredients || m.allergen_notice ? "<details class='sk2'><summary>skład i alergeny</summary><p>" + esc(m.ingredients || "") + "</p><p>" + esc(m.allergen_notice || "") + "</p></details>" : "") +
            "</td><td class='r'>" + n0(m.kcal) + "</td><td class='r'>" + n1(m.protein_g) + "</td><td class='r'>" + n1(m.carbs_g) + "</td><td class='r'>" + n1(m.sugars_g) + "</td><td class='r'>" + n1(m.fat_g) + "</td><td class='r'>" + n1(m.sat_fat_g) + "</td><td class='r'>" + n1(m.salt_g) + "</td></tr>";
        }).join("") + "</table></div></div>";
    });
    if (!x.meals.length) h += "<div class='card' style='margin-top:12px'><p class='empty'>Brak menu na najbliższe dni – zamówienie się skończyło albo import jeszcze nie przeszedł.</p></div>";
    $("menu").innerHTML = h;
  }

  /* ------------------------------------------------------------ start */
  var h0 = (location.hash || "").replace("#", "");
  loadHeader();
  loadDays(false);
  tab(["dni", "pasy", "bilans", "menu"].indexOf(h0) >= 0 ? h0 : "dni");
})();
