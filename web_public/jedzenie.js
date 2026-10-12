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
    document.querySelectorAll("#tabs button").forEach(function (b) { b.classList.toggle("on", b.dataset.t === t); b.setAttribute("aria-pressed", b.dataset.t === t ? "true" : "false"); });
    ["dni", "analiza", "pasy", "bilans", "menu"].forEach(function (k) { $("t-" + k).hidden = k !== t; });
    try { history.replaceState(null, "", "#" + t + (t === "dni" && S.sel ? "=" + S.sel : "")); } catch (e) {}
    if (t === "analiza") loadAnaliza();
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
        .map(function (p) { return "<span class='pill' title='Passa: " + p[1] + "'><span class='e'>" + p[0] + "</span><b>" + p[2] + "</b><span class='u'>" + p[3] + "</span></span>"; }).join("") +
        (fr ? "<span class='pill' title='Mrożenia ratujące passę'><span class='e'>❄️</span><b>" + fr + "</b></span>" : "");
      if (S.tab === "pasy") renderPasy();
    }).catch(function () {});
  }

  /* ------------------------------------------------------------ DNI */
  function loadDays(keepSel, start) {
    return j("/api/jedzenie/days" + (start ? "?start=" + start : "")).then(function (x) {
      S.days = x.days; S.today = x.today; S.ctx = { balance: x.balance, calib: x.calib };
      if (S.want && S.days.some(function (d) { return d.day === S.want; })) { S.sel = S.want; S.want = null; }
      else if (!keepSel || !S.days.some(function (d) { return d.day === S.sel; })) S.sel = x.today;
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
    $("daystrip").querySelectorAll(".daychip").forEach(function (b) { b.onclick = function () { S.sel = b.dataset.d; renderStrip(); renderDay(); try { history.replaceState(null, "", "#dni=" + S.sel); } catch (e) {} }; });
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
    var t = d.totals.kcal || 0, pct = d.target ? Math.min(100, t / d.target * 100) : 0, diff = t - d.target, past = d.day < S.today;
    /* ocena symetryczna: za duzo = czerwony, za malo o >300 kcal (za mocny deficyt) = pomarancz, +-150 = w celu */
    var cls = diff > 150 ? "over" : (past && diff < -300 ? "under" : "");
    var real = past && d.expend_src === "realne", bl = t - d.expend, plan = S.ctx.balance - (S.ctx.calib || 0);
    var verdict = real ? "bilans " + (bl > 0 ? "+" : "") + n0(bl) + " kcal (zjedzone " + n0(t) + " − spalone " + n0(d.expend) + ") · plan " + n0(plan) +
        (diff > 150 ? " → " + n0(diff) + " ponad plan" : diff < -300 ? " → deficyt za mocny o " + n0(-diff) : diff < -150 ? " → " + n0(-diff) + " poniżej planu" : " → w planie")
      : (diff > 150 ? "ponad cel o " + n0(diff) + " kcal" : "zostało " + n0(-diff) + " kcal");
    var balTxt = "";
    var R = [];
    R.push("<div class='card'><div class='ttl'><h2>" + (d.day === S.today ? "Dziś" : wd(d.day) + " " + dm(d.day)) + "</h2><span class='state " + (fut ? "" : (d.closed ? "ok" : "open")) + "'>" +
      (fut ? "plan" : (d.closed ? "🔒 zamknięty" : "⏳ otwarty")) + "</span></div>" +
      "<div class='big2'>" + n0(t) + " <span class='sub' style='font-size:16px'>/ " + n0(d.target) + " kcal" + (real ? " (cel = spalone " + n0(d.expend) + " " + n0(plan) + " plan)" : "") + "</span></div>" +
      "<div class='meter' role='progressbar' aria-valuenow='" + Math.round(t) + "' aria-valuemax='" + d.target + "' aria-label='Zjedzone względem celu'><i class='" + cls + "' style='width:" + pct.toFixed(1) + "%'></i></div>" +
      "<div class='sub' style='color:var(--" + (cls === "over" ? "bad" : cls === "under" ? "warn" : "ink2") + ")'>" + verdict + balTxt + "</div>" +
      "<div class='kv'><span>Białko</span><span>" + n0(d.totals.protein_g) + " g</span><span>Węglowodany</span><span>" + n0(d.totals.carbs_g) + " g</span><span>Tłuszcz</span><span>" + n0(d.totals.fat_g) + " g</span>" +
      "<span>Spalanie</span><span>" + n0(d.expend) + " kcal" + (d.expend_src === "prognoza" ? " (prognoza" + (d.so_far != null ? "; Garmin do " + d.so_far_at + ": " + n0(d.so_far) : "") + ")" : "") + "</span>" +
      (d.expend_parts ? "<span class='muted'>  w tym</span><span class='muted'>spoczynek " + n0(d.expend_parts.bmr) + " + ruch " + n0(d.expend_parts.neat) + " + trening " + n0(d.expend_parts.train) + "</span>" : "") + "<span>Cel bilansu</span><span>" + n0(S.ctx.balance) + " kcal</span>" +
      (d.brokul_kcal ? "<span>Dokładka do Brokuła</span><span>" + (d.extra >= 150 ? n0(d.extra) + " kcal" : "nie trzeba") + "</span>" : "") + "</div>" +
      (d.sessions.length ? "<div class='note'>" + d.sessions.map(function (s) { return ({ rower: "🚲", sila: "🏋️", wiosl: "🚣", joga: "🧘" }[s.sport] || "•") + " " + esc(s.name) + " " + s.dur_min + "′" + (s.start_time ? " o " + s.start_time.slice(0, 5) : ""); }).join("; ") + "</div>" : "") +
      (!fut && !d.closed ? "<div class='note'>Do zamknięcia: " + [d.pending ? "potwierdź posiłki Brokuła" : "", (!d.entries.length && !d.none) ? (d.has_diet ? "dopisz jedzenie poza dietą albo kliknij „Nic poza dietą”" : "dopisz, co zjadłeś") : ""].filter(Boolean).join("; ") +
        ". Termin passy: " + dm(d.deadline.slice(0, 10)) + " 12:00.</div>" : "") + "</div>");
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

  /* ------------------------------------------------------------ PASSA (zakladka 'pasy') */
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
    html += "<div class='card' style='margin-top:12px'><p class='note' style='margin:0'>Zasady passy: dzień zamykasz do 12:00 następnego dnia. 💪 Trening liczy się od pierwszego dnia w Trenerze, pozostałe od 10.10.2026. Za każde 7 dni pasa dostajesz 1 mrożenie (maks. 2) – ratuje passę przy jednym gorszym dniu. Kamienie milowe: " + x.milestones.join(", ") + ".</p></div>";
    $("pasy").innerHTML = html;
  }

  /* ------------------------------------------------------------ ANALIZA */
  var A = { day: null };
  function loadAnaliza(day) {
    var t = new Date(), loc = t.getFullYear() + "-" + ("0" + (t.getMonth() + 1)).slice(-2) + "-" + ("0" + t.getDate()).slice(-2);
    A.day = day || A.day || S.sel || S.today || loc;  /* wejscie prosto w #analiza: dni jeszcze sie wczytuja */
    $("analiza").classList.add("busy");
    j("/api/jedzenie/analysis?day=" + A.day).then(renderAnaliza).catch(function (e) { $("analiza").innerHTML = "<p class='msg'>" + esc(e.message) + "</p>"; })
      .then(function () { $("analiza").classList.remove("busy"); });
  }
  function shiftDay(iso, n) { var d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }
  function jpill(ok, txt) { return "<span class='jg " + (ok ? "ok" : "high") + "'>" + txt + "</span>"; }
  function renderAnaliza(x) {
    var t = x.today, w = x.week, nm = t.norms, pr = t.projected;
    var h = "<div class='wknav' style='margin-bottom:10px'><button class='btn' data-ad='-1' aria-label='Poprzedni dzień'>‹</button><b>" + wd(t.day) + " " + dm(t.day) +
      (t.day === S.today ? " · dziś" : "") + "</b><button class='btn' data-ad='1' aria-label='Następny dzień'>›</button></div>";
    var left = t.left_kcal;
    h += "<div class='g2'><div class='card'><div class='ttl'><h2>Co jeszcze zjeść</h2><span class='sub'>cel ~" + n0(t.target) + " kcal</span></div>" +
      "<div class='big2'>" + (left >= 0 ? "zostaje ~" + n0(left) : "ponad o ~" + n0(-left)) + " <span class='sub' style='font-size:15px'>kcal</span></div>" +
      "<div class='note'>Liczone z tym, co już zjedzone (" + n0(t.eaten.kcal) + " kcal)" + (t.pending_meals.length ? " i z zaplanowanym Brokułem: " + esc(t.pending_meals.join(", ")) + " (" + n0(t.pending.kcal) + " kcal)" : "") + ".</div>" +
      "<ul class='recs'>" + t.recs.map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("") + "</ul>" +
      "<table class='nt'><tr><td>Białko</td><td class='r'>" + n0(pr.protein_g) + " / " + nm.protein_g + " g</td><td class='r'>" + jpill(pr.protein_g >= nm.protein_g * 0.9, pr.protein_g >= nm.protein_g * 0.9 ? "ok" : "za mało") + "</td></tr>" +
      "<tr><td>Węglowodany</td><td class='r'>" + n0(pr.carbs_g) + " / ~" + nm.carbs_g + " g</td><td class='r'><span class='muted'>reszta kcal</span></td></tr>" +
      "<tr><td>Tłuszcz</td><td class='r'>" + n0(pr.fat_g) + " / min. " + nm.fat_min_g + " g</td><td class='r'>" + jpill(pr.fat_g >= nm.fat_min_g, pr.fat_g >= nm.fat_min_g ? "ok" : "za mało") + "</td></tr>" +
      "<tr><td>Cukry (dieta)</td><td class='r'>" + n0(t.sugars_diet) + " / maks. " + nm.sugars_max_g + " g</td><td class='r'>" + jpill(t.sugars_diet < nm.sugars_max_g * 0.9, t.sugars_diet < nm.sugars_max_g * 0.9 ? "ok" : "limit") + "</td></tr>" +
      "<tr><td>Nasycone (dieta)</td><td class='r'>" + n0(t.sat_diet) + " / maks. " + nm.sat_max_g + " g</td><td class='r'>" + jpill(t.sat_diet <= nm.sat_max_g, t.sat_diet <= nm.sat_max_g ? "ok" : "za dużo") + "</td></tr>" +
      "<tr><td>Sól (dieta)</td><td class='r'>" + n1(t.salt_diet) + " / maks. 5 g</td><td class='r'>" + jpill(t.salt_diet <= 5, t.salt_diet <= 5 ? "ok" : "za dużo") + "</td></tr></table>" +
      "<div class='note'>Cukry, sól i nasycone znamy tylko z Brokuła (jedzenie spoza diety ma kcal i makra).</div></div>";
    var av = w.avg;
    h += "<div class='card'><div class='ttl'><h2>Tydzień " + dm(w.from) + "–" + dm(w.to) + "</h2><span class='sub'>zamknięte " + w.closed + "/" + w.n + " dni</span></div>" +
      (w.closed ? "<table class='nt'><tr><td>Średnio zjedzone</td><td class='r'>" + n0(av.kcal) + " kcal (cel ~" + n0(av.target) + ")</td></tr>" +
        "<tr><td>Średni bilans</td><td class='r'>" + n0(w.avg_balance) + " kcal/dz (cel " + n0(w.balance_target) + ")</td></tr>" +
        "<tr><td>Białko</td><td class='r'>" + n0(av.protein_g) + " g/dz (cel 160)</td></tr><tr><td>Węgle / tłuszcz</td><td class='r'>" + n0(av.carbs_g) + " / " + n0(av.fat_g) + " g/dz</td></tr>" +
        "<tr><td>Dni ze słodyczami</td><td class='r'>" + w.sweets_days + "</td></tr><tr><td>Okno: dotrzymane / złamane</td><td class='r'>" + w.window_ok + " / " + w.window_broken + "</td></tr>" +
        "<tr><td>Dni ponad cel</td><td class='r'>" + w.over_target_days + "</td></tr></table>" : "<p class='empty'>Brak zamkniętych dni w tym tygodniu.</p>") +
      (w.recs.length ? "<ul class='recs'>" + w.recs.map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("") + "</ul>" : "<p class='note'>Bez uwag na ten tydzień.</p>") + "</div></div>";
    var ai = x.ai;
    h += "<div class='card' style='margin-top:12px'><div class='ttl'><h2>Zalecenia AI</h2><span class='sub'>" + (ai ? "z " + dm(ai.created_at.slice(0, 10)) + " " + ai.created_at.slice(11, 16) : "") + "</span></div>" +
      (ai ? [["dzis", "Dziś"], ["tydzien", "Tydzień"], ["weekend", "Weekend"]].filter(function (k) { return (ai[k[0]] || []).length; }).map(function (k) {
        return "<p class='lbl' style='margin-top:6px'>" + k[1] + "</p><ul class='recs'>" + ai[k[0]].map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("") + "</ul>"; }).join("")
        : "<p class='note' style='margin-top:0'>AI pisze zalecenia na podstawie liczb powyżej (nie zmienia ich). Zapisuje się raz na dzień.</p>") +
      "<button class='btn pri' id='aibtn'>" + (ai ? "Napisz od nowa" : "Napisz zalecenia AI") + "</button> <span id='aimsg' class='sub'></span></div>";
    $("analiza").innerHTML = h;
    $("analiza").querySelectorAll("[data-ad]").forEach(function (b) { b.onclick = function () { loadAnaliza(shiftDay(A.day, +b.dataset.ad)); }; });
    $("aibtn").onclick = function () { var b = $("aibtn"); b.disabled = true; b.textContent = "AI pisze… (kilka sekund)";
      post("/api/jedzenie/analysis/ai", { day: A.day }).then(function () { loadAnaliza(A.day); }).catch(function (e) { $("aimsg").textContent = e.message; b.disabled = false; b.textContent = "Spróbuj ponownie"; }); };
  }

  /* ------------------------------------------------------------ BILANS I WAGA: jeden wspolny wykres (2026-10-12) */
  var DAYMS = 864e5;
  var B = { range: 90, start: null, end: null, goal: false, zoom: null, data: null, body: null,
    on: { burn: true, intake: true, def: true, target: true, weight: true, plan: true, forecast: true,
          fat: false, muscle: false, bone: false, fatp: false, water: false } };
  /* kolory dobrane tak, zeby sie nie mylily: spalanie szarosci, zjedzone biala kreska, deficyt zielony / nadwyzka czerwony */
  var BS = { burn: ["spalone: spoczynek + aktywne", "#64748b"], intake: ["zjedzone (kreska)", "var(--ink)"], def: ["deficyt / nadwyżka", "#22c55e"],
    target: ["cel jedzenia", "#facc15"], weight: ["waga", "#a78bfa"], plan: ["plan redukcji 99→95→90", "#38bdf8"],
    forecast: ["prognoza przy obecnym tempie", "#f97316"], fat: ["tłuszcz kg", "#f472b6"], muscle: ["mięśnie kg", "#22d3ee"],
    bone: ["kości kg", "#cbd5e1"], fatp: ["tłuszcz %", "#fb7185"], water: ["woda %", "#60a5fa"] };
  var BTIP = { plan: "Planowana ścieżka wagi do celów 99 kg (31.12), 95 kg (31.03), 90 kg (30.06) z korytarzem ±1 kg – jeśli waga jest w pasie, idziesz zgodnie z planem.",
    forecast: "Gdzie będzie waga, jeśli utrzyma się tempo z ostatnich 30 dni.", burn: "Ciemna część: spoczynek (BMR, Garmin). Jaśniejsza: aktywne (ruch + treningi). Dziś i dni przyszłe: prognoza (jaśniejsze).",
    def: "Zielone = deficyt (część spalania niepokryta jedzeniem). Czerwone = nadwyżka (zjedzone ponad spalone).", intake: "Biała kreska = ile zjedzono (dni z wpisami)." };
  function loadBilans() {
    S.loaded.bilans = true;
    var q = B.start ? "start=" + B.start + "&end=" + (B.end || S.today || "") : "days=" + (B.goal ? 60 : B.range);
    $("bilans").classList.add("busy");
    Promise.all([j("/api/jedzenie/balance?" + q), B.body ? Promise.resolve(B.body) : j("/api/jedzenie/body?days=730").catch(function () { return { points: [] }; })])
      .then(function (r) { B.data = r[0]; B.body = r[1]; B.zoom = null; renderBilans(); })
      .catch(function (e) { S.loaded.bilans = false; $("bilans").innerHTML = "<p class='msg'>" + esc(e.message) + "</p>"; })
      .then(function () { $("bilans").classList.remove("busy"); });
  }
  function T(iso) { return Date.parse(iso + "T12:00:00"); }
  function domain() {
    var x = B.data, ch = x.goal && x.goal.chart, a = T(x.start), b = T(x.end);
    if (B.goal && ch) b = Math.max(b, T(ch.plan[ch.plan.length - 1][0]));
    return B.zoom || [a - DAYMS / 2, b + DAYMS / 2];
  }
  function bchart() {
    var x = B.data, ch = x.goal && x.goal.chart, dm0 = domain(), t0 = dm0[0], t1 = dm0[1];
    var anyK0 = B.on.fat || B.on.muscle || B.on.bone, anyP0 = B.on.fatp || B.on.water;
    var W = 980, H = 340, pl = 46, pr = 50 + (anyK0 ? 42 : 0) + (anyP0 ? 44 : 0), pt = 18, pb = 24;
    function X(t) { return pl + (t - t0) / (t1 - t0) * (W - pl - pr); }
    var vis = function (iso) { var t = T(iso); return t >= t0 && t <= t1; };
    var ser = x.series.filter(function (d) { return vis(d.day); });
    var body = (B.body.points || []).filter(function (p) { return vis(p.date); });
    var kmax = 1000; ser.forEach(function (d) { if (B.on.burn && d.expend) kmax = Math.max(kmax, d.expend); if (B.on.intake && d.intake != null) kmax = Math.max(kmax, d.intake); if (B.on.target && d.target) kmax = Math.max(kmax, d.target); });
    kmax *= 1.08;
    function YK(v) { return pt + (1 - v / kmax) * (H - pt - pb); }
    var wv = [];
    if (B.on.weight) body.forEach(function (p) { wv.push(p.weight); });
    var planPts = ch ? ch.plan.map(function (p) { return [T(p[0]), p[1]]; }) : [];
    function planAt(t) { for (var i = 1; i < planPts.length; i++) if (t <= planPts[i][0]) { var a = planPts[i - 1], b = planPts[i]; return a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0]); } return null; }
    if (B.on.plan && ch) [t0, t1].concat(planPts.map(function (p) { return p[0]; })).forEach(function (t) { if (t >= t0 && t <= t1) { var v = planAt(t); if (v != null) wv.push(v + 1, v - 1); } });
    var fc = ch && ch.forecast ? ch.forecast.map(function (p) { return [T(p[0]), p[1]]; }) : null;
    function fcAt(t) { if (!fc || t < fc[0][0] || t > fc[1][0]) return null; return fc[0][1] + (fc[1][1] - fc[0][1]) * (t - fc[0][0]) / (fc[1][0] - fc[0][0]); }
    if (B.on.forecast && fc) [Math.max(t0, fc[0][0]), Math.min(t1, fc[1][0])].forEach(function (t) { var v = fcAt(t); if (v != null) wv.push(v); });
    var w0 = wv.length ? Math.floor(Math.min.apply(null, wv) - 1) : 90, w1 = wv.length ? Math.ceil(Math.max.apply(null, wv) + 1) : 110;
    function YW(v) { return pt + (w1 - v) / Math.max(1, w1 - w0) * (H - pt - pb); }
    var CK = { fat: "fat_kg", muscle: "muscle_kg", bone: "bone_kg" }, CP = { fatp: "fat_pct", water: "water_pct" };
    var anyK = B.on.fat || B.on.muscle || B.on.bone, anyP = B.on.fatp || B.on.water;
    var cv = []; body.forEach(function (p) { Object.keys(CK).forEach(function (k) { if (B.on[k] && p[CK[k]] != null) cv.push(p[CK[k]]); }); });
    var pv = []; body.forEach(function (p) { Object.keys(CP).forEach(function (k) { if (B.on[k] && p[CP[k]] != null) pv.push(p[CP[k]]); }); });
    var p0 = pv.length ? Math.floor(Math.min.apply(null, pv) - 1) : 0, p1 = pv.length ? Math.ceil(Math.max.apply(null, pv) + 1) : 1;
    function YP(v) { return pt + (p1 - v) / Math.max(1, p1 - p0) * (H - pt - pb); }
    var c0 = cv.length ? Math.floor(Math.min.apply(null, cv) - 2) : 0, c1 = cv.length ? Math.ceil(Math.max.apply(null, cv) + 2) : 1;
    function YC(v) { return pt + (c1 - v) / Math.max(1, c1 - c0) * (H - pt - pb); }
    var s = "<svg id='bsvg' viewBox='0 0 " + W + " " + H + "' style='width:100%;min-width:640px;height:auto;display:block;color:inherit;user-select:none' role='img' aria-label='Bilans i waga'>";
    for (var v = 0; v <= kmax; v += 1000) s += "<line x1='" + pl + "' x2='" + (W - pr) + "' y1='" + YK(v).toFixed(1) + "' y2='" + YK(v).toFixed(1) + "' stroke='var(--line)'/><text x='" + (pl - 5) + "' y='" + (YK(v) + 4).toFixed(1) + "' font-size='11' text-anchor='end' fill='var(--muted)'>" + v + "</text>";
    var days = (t1 - t0) / DAYMS, step = Math.max(1, Math.round(days / 9)), first = new Date(t0 + DAYMS / 2); first.setHours(12, 0, 0, 0);
    for (var t = first.getTime(), k = 0; t <= t1; t += DAYMS, k++) if (k % step === 0) { var dd = new Date(t), iso = dd.getFullYear() + "-" + ("0" + (dd.getMonth() + 1)).slice(-2) + "-" + ("0" + dd.getDate()).slice(-2);
      s += "<text x='" + X(t).toFixed(1) + "' y='" + (H - 7) + "' font-size='11' text-anchor='middle' fill='var(--muted)'>" + dm(iso) + "</text>"; }
    var bw = Math.max(1, (W - pl - pr) / days * 0.7), todayIso = S.today || x.end;
    ser.forEach(function (d) {
      var cx = X(T(d.day)), x0 = (cx - bw / 2).toFixed(1), fut = d.expend_src !== "realne", op = fut ? " opacity='.45'" : "";
      var tot = d.expend, rst = d.rest != null ? Math.min(d.rest, tot) : null;
      if (B.on.burn && tot) {
        if (rst != null) s += "<rect x='" + x0 + "' y='" + YK(rst).toFixed(1) + "' width='" + bw.toFixed(1) + "' height='" + (YK(0) - YK(rst)).toFixed(1) + "' fill='#334155'" + op + "/>" +
          "<rect x='" + x0 + "' y='" + YK(tot).toFixed(1) + "' width='" + bw.toFixed(1) + "' height='" + (YK(rst) - YK(tot)).toFixed(1) + "' fill='#64748b'" + op + "/>";
        else s += "<rect x='" + x0 + "' y='" + YK(tot).toFixed(1) + "' width='" + bw.toFixed(1) + "' height='" + (YK(0) - YK(tot)).toFixed(1) + "' fill='#64748b'" + op + "/>";
      }
      if (d.intake != null && tot) {
        if (B.on.def) {
          if (d.intake < tot) s += "<rect x='" + x0 + "' y='" + YK(tot).toFixed(1) + "' width='" + bw.toFixed(1) + "' height='" + (YK(d.intake) - YK(tot)).toFixed(1) + "' fill='#22c55e' opacity='.75'/>";
          else s += "<rect x='" + x0 + "' y='" + YK(d.intake).toFixed(1) + "' width='" + bw.toFixed(1) + "' height='" + (YK(tot) - YK(d.intake)).toFixed(1) + "' fill='#ef4444' opacity='.8'/>";
        }
        if (B.on.intake) s += "<line x1='" + (cx - bw / 2 - 1.5).toFixed(1) + "' x2='" + (cx + bw / 2 + 1.5).toFixed(1) + "' y1='" + YK(d.intake).toFixed(1) + "' y2='" + YK(d.intake).toFixed(1) + "' stroke='currentColor' stroke-width='2.2'" + (d.closed ? "" : " stroke-dasharray='2 2'") + "/>";
      }
    });
    function path(pts, Y) { return pts.length > 1 ? "M" + pts.map(function (p) { return X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1); }).join(" L") : ""; }
    if (B.on.target) s += "<path d='" + path(ser.map(function (d) { return [T(d.day), d.target]; }), YK) + "' fill='none' stroke='" + BS.target[1] + "' stroke-width='1.6' stroke-dasharray='6 4'/>";
    if (B.on.plan && ch) {
      var pp = [], ts = [t0].concat(planPts.map(function (p) { return p[0]; })).concat([t1]).filter(function (t) { return t >= Math.max(t0, planPts[0][0]) && t <= t1; }).sort(function (a, b) { return a - b; });
      ts.forEach(function (t) { var v = planAt(t); if (v != null) pp.push([t, v]); });
      if (pp.length > 1) {
        s += "<path d='" + path(pp.map(function (p) { return [p[0], p[1] + 1]; }), YW) + " L" + pp.slice().reverse().map(function (p) { return X(p[0]).toFixed(1) + " " + YW(p[1] - 1).toFixed(1); }).join(" L") + " Z' fill='#38bdf8' opacity='.10'/>";
        s += "<path d='" + path(pp, YW) + "' fill='none' stroke='" + BS.plan[1] + "' stroke-width='1.6' stroke-dasharray='3 4' opacity='.85'/>";
      }
      planPts.slice(1).forEach(function (p) { if (p[0] >= t0 && p[0] <= t1) s += "<circle cx='" + X(p[0]).toFixed(1) + "' cy='" + YW(p[1]).toFixed(1) + "' r='4' fill='#38bdf8'><title>etap: " + p[1] + " kg</title></circle><text x='" + X(p[0]).toFixed(1) + "' y='" + (YW(p[1]) - 8).toFixed(1) + "' font-size='10' text-anchor='middle' fill='var(--muted)'>" + p[1] + " kg</text>"; });
    }
    if (B.on.forecast && fc) { var a = Math.max(t0, fc[0][0]), b = Math.min(t1, fc[1][0]); if (b > a) s += "<path d='" + path([[a, fcAt(a)], [b, fcAt(b)]], YW) + "' fill='none' stroke='" + BS.forecast[1] + "' stroke-width='1.6' stroke-dasharray='2 4'/>"; }
    if (B.on.weight && body.length) {
      s += "<path d='" + path(body.map(function (p) { return [T(p.date), p.weight]; }), YW) + "' fill='none' stroke='" + BS.weight[1] + "' stroke-width='1.8'/>";
      body.forEach(function (p) { s += "<circle cx='" + X(T(p.date)).toFixed(1) + "' cy='" + YW(p.weight).toFixed(1) + "' r='3' fill='" + BS.weight[1] + "'/>"; });
    }
    function compSeries(k, key, Y, dash) { if (!B.on[k]) return;
      ["normal", "athlete"].forEach(function (m) { var a2 = body.filter(function (p) { return p[key] != null && p.mode === m; }).map(function (p) { return [T(p.date), p[key]]; });
        s += "<path d='" + path(a2, Y) + "' fill='none' stroke='" + BS[k][1] + "' stroke-width='1.6'" + (dash ? " stroke-dasharray='4 3'" : "") + "/>"; });
      body.forEach(function (p) { if (p[key] == null) return; s += "<circle cx='" + X(T(p.date)).toFixed(1) + "' cy='" + Y(p[key]).toFixed(1) + "' r='2.6' fill='" + (p.suspect.length ? "var(--card)" : BS[k][1]) + "' stroke='" + BS[k][1] + "'/>"; }); }
    Object.keys(CK).forEach(function (k) { compSeries(k, CK[k], YC, false); });
    Object.keys(CP).forEach(function (k) { compSeries(k, CP[k], YP, true); });
    var wt = []; for (var q = w0; q <= w1; q += Math.max(1, Math.round((w1 - w0) / 5))) wt.push(q);
    if (B.on.weight || B.on.plan || B.on.forecast) wt.forEach(function (q) { s += "<text x='" + (W - pr + 5) + "' y='" + (YW(q) + 3.5).toFixed(1) + "' font-size='10.5' fill='" + BS.weight[1] + "'>" + q + "</text>"; });
    if (anyK) [c0, (c0 + c1) / 2, c1].forEach(function (q) { s += "<text x='" + (W - pr + 46) + "' y='" + (YC(q) + 3.5).toFixed(1) + "' font-size='10.5' fill='#22d3ee'>" + Math.round(q) + " kg</text>"; });
    if (anyP) [p0, (p0 + p1) / 2, p1].forEach(function (q) { s += "<text x='" + (W - pr + (anyK ? 90 : 46)) + "' y='" + (YP(q) + 3.5).toFixed(1) + "' font-size='10.5' fill='#fb7185'>" + Math.round(q) + "%</text>"; });
    if ((anyK || anyP) && B.body["break"] && T(B.body["break"]) >= t0 && T(B.body["break"]) <= t1) { var bx = X(T(B.body["break"])).toFixed(1); s += "<line x1='" + bx + "' x2='" + bx + "' y1='" + pt + "' y2='" + (H - pb) + "' stroke='var(--muted)' stroke-dasharray='3 3'/><text x='" + bx + "' y='" + (pt + 12) + "' font-size='10' text-anchor='end' fill='var(--muted)'>tryb sportowca →&#160;</text>"; }
    var tt = T(S.today || x.end); if (tt >= t0 && tt <= t1) { var tx = X(tt).toFixed(1); s += "<line x1='" + tx + "' x2='" + tx + "' y1='" + pt + "' y2='" + (H - pb) + "' stroke='var(--muted)' stroke-dasharray='2 3'/><text x='" + tx + "' y='" + (pt - 5) + "' font-size='10' text-anchor='middle' fill='var(--muted)'>dziś</text>"; }
    s += "<line id='bcur' x1='0' x2='0' y1='" + pt + "' y2='" + (H - pb) + "' stroke='var(--muted)' stroke-dasharray='2 3' visibility='hidden'/>";
    s += "<rect id='bsel' x='0' y='" + pt + "' width='0' height='" + (H - pt - pb) + "' fill='rgba(59,130,246,.15)' stroke='rgba(59,130,246,.6)' visibility='hidden'/>";
    s += "<rect id='bhit' x='" + pl + "' y='" + pt + "' width='" + (W - pl - pr) + "' height='" + (H - pt - pb) + "' fill='transparent' style='cursor:crosshair'/></svg>";
    B.g = { W: W, pl: pl, pr: pr, t0: t0, t1: t1, planAt: planAt, fcAt: fcAt };
    return s;
  }
  function tAt(ev) { var svg = $("bsvg"), r = svg.getBoundingClientRect(), g = B.g, xv = (ev.clientX - r.left) / r.width * g.W; return g.t0 + (xv - g.pl) / (g.W - g.pl - g.pr) * (g.t1 - g.t0); }
  function isoOf(t) { var d = new Date(t); d.setHours(12, 0, 0, 0); return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }
  function wireB() {
    var svg = $("bsvg"), tip = $("btip"), cur = $("bcur"), sel = $("bsel"), wrap = $("bwrap"); if (!svg) return;
    var drag = null;
    function pxOf(t) { var g = B.g; return g.pl + (t - g.t0) / (g.t1 - g.t0) * (g.W - g.pl - g.pr); }
    function hide() { tip.style.display = "none"; cur.setAttribute("visibility", "hidden"); }
    svg.addEventListener("mouseleave", function () { hide(); });
    svg.addEventListener("mousedown", function (ev) { if (ev.button) return; drag = { t: tAt(ev), x: ev.clientX }; ev.preventDefault(); });
    window.addEventListener("mouseup", function up(ev) {
      if (!drag) return; var d = drag; drag = null; sel.setAttribute("visibility", "hidden");
      if (Math.abs(ev.clientX - d.x) > 8) { var a = Math.min(d.t, tAt(ev)), b = Math.max(d.t, tAt(ev)); if (b - a >= 2 * DAYMS) { B.zoom = [a, b]; renderBilans(); } return; }
      var iso = isoOf(tAt(ev)); if (iso >= "2026-10-10" && iso <= (S.today || iso)) { S.want = iso; tab("dni"); loadDays(true, iso < shiftDay(S.today, -6) ? iso : null); }
    }, { once: false });
    svg.addEventListener("dblclick", function () { if (B.zoom) { B.zoom = null; renderBilans(); } });
    svg.addEventListener("mousemove", function (ev) {
      var t = tAt(ev), r = svg.getBoundingClientRect(), g = B.g;
      if (drag) { var a = pxOf(Math.min(drag.t, t)), b = pxOf(Math.max(drag.t, t)); sel.setAttribute("x", a); sel.setAttribute("width", Math.max(0, b - a)); sel.setAttribute("visibility", "visible"); return; }
      if (t < g.t0 || t > g.t1) return hide();
      var iso = isoOf(t), d = B.data.series.filter(function (q) { return q.day === iso; })[0], p = (B.body.points || []).filter(function (q) { return q.date === iso; })[0];
      var cx = pxOf(T(iso)); cur.setAttribute("x1", cx); cur.setAttribute("x2", cx); cur.setAttribute("visibility", "visible");
      var L = ["<b>" + wd(iso) + " " + dm(iso) + "." + iso.slice(0, 4) + "</b>" + (d && d.closed ? " 🔒" : "")];
      if (d) { L.push("spalone: <b>" + n0(d.expend) + "</b>" + (d.rest != null ? " = spoczynek " + n0(d.rest) + " + aktywne " + n0(d.active) : "") + (d.expend_src === "prognoza" ? " (prognoza)" : ""));
        L.push("zjedzone: " + (d.intake != null ? "<b>" + n0(d.intake) + "</b>" + (d.closed ? "" : " (dzień otwarty)") : "brak wpisów") + " · cel " + n0(d.target));
        if (d.intake != null) { var bl = d.intake - d.expend; L.push((bl < 0 ? "deficyt" : "nadwyżka") + ": <b style='color:" + (bl < 0 ? "#22c55e" : "#ef4444") + "'>" + (bl > 0 ? "+" : "") + n0(bl) + " kcal</b>"); } }
      if (p) { L.push("waga: <b>" + n1(p.weight) + " kg</b>" + (p.mode === "athlete" ? " · tryb sportowca" : ""));
        if (p.fat_pct != null) L.push("tłuszcz " + n1(p.fat_pct) + "% (" + n1(p.fat_kg) + " kg) · mięśnie " + n1(p.muscle_kg) + " kg");
        if (p.water_pct != null || p.bone_kg != null) L.push("woda " + n1(p.water_pct) + "% · kości " + n1(p.bone_kg) + " kg");
        if (p.suspect.length) L.push("⚠️ pomiar podejrzany: " + p.suspect.join(", ")); }
      var pv = g.planAt(T(iso)); if (pv != null && B.on.plan) L.push("plan redukcji: " + n1(pv) + " kg (±1)");
      var fv = g.fcAt(T(iso)); if (fv != null && B.on.forecast && iso > (S.today || "")) L.push("prognoza: " + n1(fv) + " kg");
      tip.innerHTML = L.join("<br>");
      var px = cx / g.W * r.width, left = px + 14; if (left + 230 > wrap.clientWidth) left = px - 240;
      tip.style.left = Math.max(0, left) + "px"; tip.style.top = "10px"; tip.style.display = "block";
    });
  }
  function renderBilans() {
    var x = B.data, g = x.goal;
    var rb = "<div class='rng'>" + [45, 90, 180, 365].map(function (d) { return "<button class='btn" + (!B.start && !B.goal && B.range === d ? " on" : "") + "' data-r='" + d + "'>" + (d === 365 ? "rok" : d + " dni") + "</button>"; }).join("") +
      (g && g.chart ? "<button class='btn" + (B.goal ? " on" : "") + "' data-goal='1'>do celu (" + dm(g.chart.plan[g.chart.plan.length - 1][0]) + "." + g.chart.plan[g.chart.plan.length - 1][0].slice(0, 4) + ")</button>" : "") +
      "<span class='sub' style='margin-left:6px'>od</span><input type='date' id='bfrom' value='" + (B.start || x.start) + "'><span class='sub'>do</span><input type='date' id='bto' value='" + (B.end || x.end) + "'><button class='btn" + (B.start ? " on" : "") + "' id='bgo'>Pokaż</button>" +
      (B.zoom ? "<button class='btn' id='bunzoom'>↺ cała skala</button>" : "") + "</div>";
    var grp = [["kcal", ["burn", "intake", "def", "target"]], ["waga", ["weight", "plan", "forecast"]], ["skład ciała", ["fat", "muscle", "bone", "fatp", "water"]]];
    var tg = grp.map(function (gg) { return "<div class='toggles'><span class='sub' style='align-self:center;min-width:78px'>" + gg[0] + ":</span>" + gg[1].map(function (k) {
      return "<button class='tg" + (B.on[k] ? " on" : "") + "' data-s='" + k + "' aria-pressed='" + B.on[k] + "'" + (BTIP[k] ? " title='" + BTIP[k] + "'" : "") + "><i style='background:" + BS[k][1] + "'></i>" + BS[k][0] + "</button>"; }).join("") + "</div>"; }).join("");
    var h = "<div class='card'><div class='ttl'><h2>Bilans i waga</h2><span class='sub'>cel bilansu wg budżetu tygodnia" + (x.calib ? " · kalibracja " + n0(-x.calib) : "") + "</span></div>" + rb + tg +
      "<div class='chwrap chartbox' id='bwrap'>" + bchart() + "<div class='tip2' id='btip'></div></div>" +
      "<div class='legend'><span><i style='background:#334155'></i>spoczynek</span><span><i style='background:#64748b'></i>aktywne</span><span><i style='background:#22c55e'></i>deficyt</span><span><i style='background:#ef4444'></i>nadwyżka</span><span>▬ zjedzone (przerywana = dzień otwarty)</span><span>jaśniejsze słupki = prognoza</span></div>" +
      "<div class='legend' style='margin-top:4px'><span>osie: lewa kcal · prawa kg wagi" + (B.on.fat || B.on.muscle || B.on.bone ? " · kg składu" : "") + (B.on.fatp || B.on.water ? " · % składu" : "") + "</span><span>przeciągnij = powiększ · dwuklik = cała skala · klik = otwórz dzień</span></div></div>";
    var bs = B.body && B.body.summary, cur = bs && (bs.athlete || bs.normal), lastc = (B.body.points || []).filter(function (p) { return p.fat_pct != null; }).slice(-1)[0];
    h += "<div class='g2' style='margin-top:12px'><div class='card'><div class='ttl'><h2>⚖️ " + esc(g ? g.name : "Waga") + "</h2></div>" +
      (g ? "<div class='state " + (g.level === "g" ? "ok" : "open") + "'>" + esc(g.text) + "</div><div class='kv'>" + (g.rows || []).map(function (r) { return "<span>" + esc(r.k) + "</span><span>" + esc(r.have == null ? "" : r.have) + (r.need != null ? " / " + esc(r.need) : "") + "</span>"; }).join("") + "</div>" : "<p class='empty'>Brak celu wagi.</p>") +
      "<p class='lbl' style='margin-top:12px'>Skład ciała (Withings)</p>" + (lastc ? "<div class='kv'><span>Ostatni (" + dm(lastc.date) + ")</span><span>" + n1(lastc.fat_pct) + "% · " + n1(lastc.fat_kg) + " kg tłuszczu · " + n1(lastc.muscle_kg) + " kg mięśni</span>" +
        (cur ? "<span>Średnia z 3 (" + (bs.athlete ? "tryb sportowca" : "tryb zwykły") + ")</span><span>" + n1(cur.last3_fat_pct) + "% · " + n1(cur.last3_fat_kg) + " kg · " + n1(cur.last3_muscle_kg) + " kg</span>" : "") +
        (cur && cur.d_fat_kg != null ? "<span>Zmiana " + dm(cur.first) + "–" + dm(cur.last) + "</span><span>tłuszcz " + (cur.d_fat_kg > 0 ? "+" : "") + n1(cur.d_fat_kg) + " kg · mięśnie " + (cur.d_muscle_kg > 0 ? "+" : "") + n1(cur.d_muscle_kg) + " kg</span>" : "") + "</div>" : "<p class='empty'>Brak pomiarów składu.</p>") +
      "<p class='note'>Bioimpedancja: ufaj trendowi z 3–4 tygodni. Od 12.10.2026 tryb sportowca – osobna seria.</p></div>";
    var dsc = x.discrepancy || {};
    h += "<div class='stack'><div class='card'><div class='ttl'><h2>Waga vs jedzenie</h2></div><p class='note' style='margin-top:0'>" + esc(x.discrepancy_line) + "</p>" +
      (dsc.ready ? "<div class='kv'><span>Bilans z wpisów</span><span>" + n0(dsc.logged_bal) + " kcal/dz</span><span>Bilans z wagi</span><span>" + n0(dsc.actual_bal) + " kcal/dz</span><span>Rozbieżność</span><span>" + n0(dsc.disc) + " kcal/dz</span></div>" : "") + "</div>" +
      "<div class='card'><div class='ttl'><h2>Tygodnie (pn–nd)</h2></div>" + (x.weeks.length ? "<table class='tb'><tr><th>Tydzień od</th><th class='r'>Zamknięte dni</th><th class='r'>Śr. bilans</th></tr>" +
        x.weeks.slice().reverse().map(function (w) { var ok = w.avg_balance >= x.balance_target - 300 && w.avg_balance <= x.balance_target + 250; return "<tr><td>" + dm(w.week) + "</td><td class='r'>" + w.days + "</td><td class='r' style='color:var(--" + (ok ? "good" : "bad") + ")'>" + n0(w.avg_balance) + "</td></tr>"; }).join("") + "</table>"
        : "<p class='empty'>Jeszcze brak zamkniętych dni z pełnym spalaniem.</p>") + "</div></div></div>";
    $("bilans").innerHTML = h;
    $("bilans").querySelectorAll("[data-r]").forEach(function (b) { b.onclick = function () { B.range = +b.dataset.r; B.start = B.end = null; B.goal = false; loadBilans(); }; });
    var gb = $("bilans").querySelector("[data-goal]"); if (gb) gb.onclick = function () { B.goal = !B.goal; B.start = B.end = null; loadBilans(); };
    $("bgo").onclick = function () { var a = $("bfrom").value, b = $("bto").value; if (!a) return; B.start = a; B.end = b || null; B.goal = false; loadBilans(); };
    var uz = $("bunzoom"); if (uz) uz.onclick = function () { B.zoom = null; renderBilans(); };
    $("bilans").querySelectorAll("[data-s]").forEach(function (b) { b.onclick = function () { B.on[b.dataset.s] = !B.on[b.dataset.s]; renderBilans(); }; });
    wireB();
  }

  /* ------------------------------------------------------------ MENU (tygodniami) */
  function loadMenu(week) {
    S.loaded.menu = true;
    $("menu").classList.add("busy");
    j("/api/jedzenie/menu" + (week ? "?week=" + week : "")).then(renderMenu).catch(function (e) { S.loaded.menu = false; $("menu").innerHTML = "<p class='msg'>" + esc(e.message) + "</p>"; })
      .then(function () { $("menu").classList.remove("busy"); });
  }
  var JL = { protein_g: "białko", fat_g: "tłuszcz", sugars_g: "cukry", sat_fat_g: "nasycone", salt_g: "sól" };
  function judgePills(jd) { if (!jd) return ""; return Object.keys(JL).map(function (k) { var v = jd[k]; return "<span class='jg " + v + "'>" + JL[k] + (v === "ok" ? " ✓" : v === "high" ? " ↑" : " ↓") + "</span>"; }).join(" "); }
  function renderMenu(x) {
    var h = "<div class='card'><div class='ttl'><h2>🥦 Dieta od Brokuła</h2><span class='sub'>" + (x.order_end ? "zamówienie do " + wd(x.order_end) + " " + dmy(x.order_end) : "brak zamówienia") + "</span></div>" +
      "<div class='wknav'><button class='btn' data-w='" + (x.prev || "") + "'" + (x.prev ? "" : " disabled") + " aria-label='Poprzedni tydzień'>‹</button><b>" + dm(x.week) + " – " + dm(x.week_end) + "</b>" +
      "<button class='btn' data-w='" + (x.next || "") + "'" + (x.next ? "" : " disabled") + " aria-label='Następny tydzień'>›</button>" +
      "<span class='note' style='margin:0'>" + (x.session_alive ? "Połączenie z Brokułem działa" : "⚠️ Sesja Brokuła nie działa – <a href='" + x.access_url + "'>wklej nowe ciasteczka</a>") +
      (x.last_import ? " · import " + dm(x.last_import.slice(0, 10)) + " " + x.last_import.slice(11, 16) : "") + " · historia od " + dm(x.history_from) + "</span></div></div>";
    var av = x.week_avg, nm = x.norms;
    if (av) {
      h += "<div class='card' style='margin-top:12px'><div class='ttl'><h2>Podsumowanie tygodnia</h2><span class='sub'>" + x.n_days + " dni diety · średnio na dzień</span></div>" +
        "<div class='chartbox'><table class='tb'><tr><th></th><th class='r'>kcal</th><th class='r'>B</th><th class='r'>W</th><th class='r'>T</th><th class='r'>cukry</th><th class='r'>nas.</th><th class='r'>sól</th><th>vs normy</th></tr>" +
        Object.keys(x.days).sort().map(function (d) { var v = x.days[d]; return "<tr><td>" + wd(d) + " " + dm(d) + "</td><td class='r'>" + n0(v.kcal) + "</td><td class='r'>" + n0(v.protein_g) + "</td><td class='r'>" + n0(v.carbs_g) + "</td><td class='r'>" + n0(v.fat_g) + "</td><td class='r'>" + n0(v.sugars_g) + "</td><td class='r'>" + n0(v.sat_fat_g) + "</td><td class='r'>" + n1(v.salt_g) + "</td><td>" + judgePills(x.days_judge[d]) + "</td></tr>"; }).join("") +
        "<tr style='font-weight:700'><td>średnio</td><td class='r'>" + n0(av.kcal) + "</td><td class='r'>" + n0(av.protein_g) + "</td><td class='r'>" + n0(av.carbs_g) + "</td><td class='r'>" + n0(av.fat_g) + "</td><td class='r'>" + n0(av.sugars_g) + "</td><td class='r'>" + n0(av.sat_fat_g) + "</td><td class='r'>" + n1(av.salt_g) + "</td><td>" + judgePills(x.week_judge) + "</td></tr></table></div>" +
        "<div class='note'>Normy: białko ~" + nm.protein_g + " g, tłuszcz min. " + nm.fat_min_g + " g, cukry maks. 10% kcal, nasycone maks. 10% kcal, sól maks. " + nm.salt_max_g + " g. Sama dieta, bez jedzenia spoza niej.</div></div>";
    }
    if (x.fridge.length) h += "<div class='card' style='margin-top:12px'><div class='ttl'><h2>📦 Lodówka</h2></div>" + x.fridge.map(function (m) { return "<div class='meal'><div class='nm'><b>" + esc(m.meal_type) + " z " + dm(m.day) + "</b> · " + esc(m.name) + "<div class='mx'>" + n0(m.kcal) + " kcal</div></div><span></span></div>"; }).join("") + "</div>";
    var by = {};
    x.meals.forEach(function (m) { (by[m.day] = by[m.day] || []).push(m); });
    var ST = { eaten: "✅", skipped: "❌", fridge: "📦", discarded: "🗑", pending: "" };
    Object.keys(by).sort().forEach(function (d) {
      var ms = by[d], tot = ms.reduce(function (a, m) { return a + (m.kcal || 0); }, 0);
      h += "<div class='card' style='margin-top:12px'><div class='ttl'><h2>" + wd(d) + " " + dm(d) + "</h2><span class='sub'>" + n0(tot) + " kcal</span></div><div class='chartbox'><table class='tb'>" +
        "<tr><th>Posiłek</th><th class='r'>kcal</th><th class='r'>B</th><th class='r'>W</th><th class='r'>cukry</th><th class='r'>T</th><th class='r'>nas.</th><th class='r'>sól</th></tr>" +
        ms.map(function (m) {
          return "<tr><td>" + (ST[m.status] ? ST[m.status] + " " : "") + "<b>" + esc(m.meal_type) + "</b> · " + esc(m.name) + (m.ingredients || m.allergen_notice ? "<details class='sk2'><summary>skład i alergeny</summary><p>" + esc(m.ingredients || "") + "</p><p>" + esc(m.allergen_notice || "") + "</p></details>" : "") +
            "</td><td class='r'>" + n0(m.kcal) + "</td><td class='r'>" + n1(m.protein_g) + "</td><td class='r'>" + n1(m.carbs_g) + "</td><td class='r'>" + n1(m.sugars_g) + "</td><td class='r'>" + n1(m.fat_g) + "</td><td class='r'>" + n1(m.sat_fat_g) + "</td><td class='r'>" + n1(m.salt_g) + "</td></tr>";
        }).join("") + "</table></div></div>";
    });
    if (!x.meals.length) h += "<div class='card' style='margin-top:12px'><p class='empty'>Brak menu w tym tygodniu (QBot zapisuje menu od 12.10.2026; panel Brokuła nie udostępnia starszych).</p></div>";
    $("menu").innerHTML = h;
    $("menu").querySelectorAll("[data-w]").forEach(function (b) { b.onclick = function () { if (b.dataset.w) loadMenu(b.dataset.w); }; });
  }

  /* ------------------------------------------------------------ start */
  var h0 = (location.hash || "").replace("#", ""), hd = null;
  var m0 = /^dni=(\d{4}-\d{2}-\d{2})$/.exec(h0);
  if (m0) { hd = m0[1]; h0 = "dni"; S.want = hd; }
  loadHeader();
  var t0 = new Date(), lim = new Date(t0.getFullYear(), t0.getMonth(), t0.getDate() - 6, 12);
  loadDays(false, hd && new Date(hd + "T12:00:00") < lim ? hd : null);
  tab(["dni", "analiza", "pasy", "bilans", "menu"].indexOf(h0) >= 0 ? h0 : "dni");
})();
