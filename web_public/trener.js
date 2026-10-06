/* TRENER (osobna strona /trener.html, wcześniej zakładka Formy) — Etap 4 (Czas, Bilans, statusy celów, pogoda auto) + Etap 3 (plan tygodnia) + Etap 2: Cele, Dostępność, Sezon, Kalibracja (zapis przez /api/trener), Tydzień = podgląd.
   Dane użytkownika wyłącznie z API (startują puste). Wartości auto: /api/trener/auto (liczone na żywo) albo domyślne.
   Dok.: docs/TRENER.md. Wzorzec UI: /trener-mock.html */
(function () {
  "use strict";
  var root = document.getElementById("trener-root");
  if (!root) return;

  // ---------- narzędzia ----------
  function api(m, p, b) {
    return fetch("/api/trener" + p, { method: m, credentials: "same-origin", headers: b ? { "Content-Type": "application/json" } : {}, body: b ? JSON.stringify(b) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status)); return j; }); });
  }
  function esc(t) { return String(t == null ? "" : t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
  var toastT = null;
  function toast(msg, bad) {
    var el = document.getElementById("tr-toast");
    if (!el) { el = document.createElement("div"); el.id = "tr-toast"; root.appendChild(el); }
    el.className = "tr-toast" + (bad ? " bad" : ""); el.textContent = msg; el.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(function () { el.hidden = true; }, bad ? 5000 : 2200);
  }
  function fail(e) { toast("Błąd: " + (e && e.message ? e.message : e), true); }
  var DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"];
  var MN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
  function D(t) { var p = String(t).slice(0, 10).split("-"); return Date.UTC(+p[0], +p[1] - 1, +p[2]); }
  function iso(ms) { return new Date(ms).toISOString().slice(0, 10); }
  function pl(ms) { var d = new Date(ms); return ("0" + d.getUTCDate()).slice(-2) + "." + ("0" + (d.getUTCMonth() + 1)).slice(-2); }
  var DAY = 864e5, WK = 7 * DAY;
  function todayMs() { var n = new Date(); return Date.UTC(n.getFullYear(), n.getMonth(), n.getDate()); }
  function monday(ms) { var dow = (new Date(ms).getUTCDay() + 6) % 7; return ms - dow * DAY; }
  function tm(t) { var p = String(t || "").split(":"); return p.length < 2 ? null : (+p[0]) * 60 + (+p[1]); }
  var ACT = [["rower", "🚲", "rower"], ["sila", "🏋️", "siła"], ["wiosl", "🚣", "wioślarz"], ["joga", "🧘", "joga"]];
  var AIC = { rower: "🚲", sila: "🏋️", wiosl: "🚣", joga: "🧘" }, ANM = { rower: "rower", sila: "siła", wiosl: "wioślarz", joga: "joga" };

  var S = { goals: [], rules: [], ov: {}, auto: null, sub: null, wk: null, weekData: null };

  // ---------- szkielet ----------
  var SUBS = [["tydzien", "Tydzień"], ["czas", "Czas"], ["dostep", "Dostępność"], ["cele", "Cele"], ["sezon", "Sezon"], ["bilans", "Bilans i waga"], ["kalib", "Kalibracja"]];
  root.innerHTML = "<div class='tr-sub'>" + SUBS.map(function (x) { return "<button data-sub='" + x[0] + "'>" + x[1] + "</button>"; }).join("") + "</div><div id='tr-body'></div>";
  var body = document.getElementById("tr-body");
  root.querySelectorAll("[data-sub]").forEach(function (b) { b.onclick = function () { go(b.dataset.sub); }; });
  function go(sub) {
    S.sub = sub;
    root.querySelectorAll("[data-sub]").forEach(function (b) { b.classList.toggle("on", b.dataset.sub === sub); });
    try { localStorage.setItem("qtrener_sub", sub); } catch (e) {}
    ({ tydzien: rWeek, czas: rTime, cele: rGoals, dostep: rAvail, sezon: rSeason, bilans: rBal, kalib: rCalib })[sub]();
  }
  window.TRENER_CORE = { go: go };   // wersja mobilna (trener-m.js) rysuje dzialy z menu "Wiecej" przez go()

  // ---------- reguły: zastosowanie w dniu ----------
  function ddmm(s) { var p = s.split("."); return (+p[1]) * 100 + (+p[0]); }
  function ruleApplies(r, ms) {
    if (r.active === false) return false;
    var p = r.period || { m: "all" };
    if (p.m === "all") return true;
    if (p.m === "once") return ms >= D(p.f) && ms <= D(p.t);
    var d = new Date(ms), k = (d.getUTCMonth() + 1) * 100 + d.getUTCDate(), f = ddmm(p.f), t = ddmm(p.t);
    return f <= t ? (k >= f && k <= t) : (k >= f || k <= t);
  }
  function daysTxt(d) { var out = [], i = 0; while (i < 7) { if (!d[i]) { i++; continue; } var j = i; while (j + 1 < 7 && d[j + 1] === d[i]) j++; var q = d[i] === 2 ? "?" : ""; out.push(j > i ? (DN[i] + "–" + DN[j] + q) : (DN[i] + q)); i = j + 1; } return out.length ? out.join(", ") : "— brak dni —"; }
  function winTxt(w) {
    var ac = (w.ac && w.ac.length && w.ac.length < 4) ? (" · " + ACT.filter(function (x) { return w.ac.indexOf(x[0]) >= 0; }).map(function (x) { return x[1] + " " + x[2]; }).join(", ")) : "";
    return daysTxt(w.d) + " " + (w.k === "h" ? ((w.a || "?") + "–" + (w.b || "?")) : (w.k === "all" ? "cały dzień" : "godziny zmienne (z Kalendarza)")) + ac;
  }
  function perTxt(p) { p = p || { m: "all" }; return p.m === "all" ? "cały rok" : (p.m === "yearly" ? ("co roku " + p.f + "–" + p.t) : ("jednorazowo " + p.f + " – " + p.t)); }
  var TY = { busy: "zajęte", flex: "elastyczne (trening w przerwie OK)", pref: "okno treningu" };

  // ======================= TYDZIEŃ (Etap 3: plan z silnika) =======================
  var CALIC = { rest: "😴", delegacja: "🧳", urlop: "🏖️" }, KIC = { illness: "🤒", feel: "🙂", reminder: "⏰", event: "📅" };
  var SPIC = { cycling: "🚲", gravel_cycling: "🚲", yoga: "🧘", indoor_rowing: "🚣", strength_training: "🏋️", walking: "🚶" };
  var SPORT_OF = { cycling: "rower", gravel_cycling: "rower", strength_training: "sila", indoor_rowing: "wiosl", yoga: "joga" };
  var SCOL = { rower: "#2f9e5b", sila: "#e0802b", wiosl: "#2f7fd1", joga: "#8a63d2" };
  var DTYPE = { rest: "😴 REST DAY", ill: "🤒 choroba", del: "🧳 delegacja", short: "⏱ brak czasu", trip: "🗺️ wyprawa", urlop: "🏖️ urlop" };
  var wkOpen = null, wkLines = null;
  // samopoczucie (Kalendarz kind=feel, -2..+2; etykiety jak w Kalendarzu). Emotka w naglowku dnia, pelna informacja w dymku.
  var FEEL_E = { "-2": "🤒", "-1": "😕", "0": "😐", "1": "🙂", "2": "😄" }, FEEL_L = { "-2": "fatalnie", "-1": "słabo", "0": "neutralnie", "1": "dobrze", "2": "świetnie" };
  function dayFeels(cal, ds) { return (cal || []).filter(function (c) { return c.kind === "feel" && c.feel != null && String(c.day).slice(0, 10) === ds; }); }
  function feelMain(fs) { var m = fs.filter(function (c) { return c.source !== "trener"; }); m = m.length ? m : fs; return m.length ? m[m.length - 1] : null; }
  function cpost(u, b) { return fetch(u, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }); }
  function feelSave(cal, ds, v, note) {
    var mine = dayFeels(cal, ds).filter(function (c) { return c.source !== "trener"; }).pop();
    if (v === "del") return mine ? cpost("/api/calendar/delete", { id: mine.id }) : Promise.resolve();
    v = +v; var nt = note !== undefined ? note : (mine ? mine.note : null), b = { feel: v, title: FEEL_L[v], note: nt || null };
    return mine ? cpost("/api/calendar/edit", Object.assign({ id: mine.id }, b)) : cpost("/api/calendar/entry", Object.assign({ day: ds, kind: "feel" }, b));
  }
  window.TRENER_FEEL = { E: FEEL_E, L: FEEL_L, dayFeels: dayFeels, main: feelMain, save: feelSave };
  function sdesc(x, meta) {
    var f = meta.ftp_w, L = meta.lthr_bpm;
    if (x.sport === "rower") {
      var z = x.zone || 2, P = [[0, .55], [.56, .75], [.76, .9], [.91, 1.05]][Math.min(3, z - 1)], H = [[0, .81], [.81, .89], [.9, .93], [.94, .99]][Math.min(3, z - 1)];
      return (x.is_long ? "Długa, równa jazda; jedz co 45 min, pij co 15 min. " : (z >= 3 ? "Akcent: długie wysiłki pod górę / niska kadencja, między nimi spokojnie. " : "Spokojna jazda. ")) +
        "Z" + z + (f ? ": " + Math.round(P[0] * f) + "–" + Math.round(P[1] * f) + " W" : "") + (L ? " · tętno " + (H[0] ? Math.round(H[0] * L) : "<") + "–" + Math.round(H[1] * L) + " bpm" : "");
    }
    if (x.sport === "sila") return "Przysiad z hantlami 3×10 · wykroki 3×8/noga · martwy ciąg rumuński 3×10 · wiosłowanie hantlem 3×10 · plank 3×40 s. Technika przed ciężarem.";
    if (x.sport === "joga") return "Biodra, tył uda, odcinek piersiowy — spokojnie, bez rozciągania na siłę.";
    return "Spokojnie, tempo rozmowy, 20–24 pociągnięcia/min.";
  }
  function wxBad(wx, ov) {
    if (!wx) return false; var g = function (k, d) { return ov && ov[k] != null ? ov[k] : d; };
    return (wx.wind != null && wx.wind > g("wx.wind_ms", 8) + g("wx.forest_bonus_ms", 1)) || (wx.rain_mmh != null && wx.rain_mmh > g("wx.rain_mmh", 0.5)) || wx.storm;
  }
  function rWeek() {
    if (S.wk == null) S.wk = monday(todayMs());
    body.innerHTML = "<div class='card'><div class='cardhead'><span style='display:flex;gap:8px;align-items:center'><button class='tr-btn' id='trw-p'>‹</button><b id='trw-t'></b><button class='tr-btn' id='trw-n'>›</button><button class='tr-btn sm' id='trw-now'>dziś</button></span><span style='display:flex;gap:6px;align-items:center'><span id='trw-ph' class='pill'></span><button class='tr-btn pri' id='trw-gen'>↻ przelicz tydzień</button></span></div>" +
      "<div class='g4' id='trw-sum' style='margin-bottom:8px'></div><div id='trw-tg'></div><div id='trw-al'></div><div id='trw-ask'></div><div id='trw-chg'></div><div id='trw-ai'></div></div>" +
      "<div class='tr-wkwrap'><div class='tr-week' id='trw-g'><div class='tr-empty'>Wczytuję…</div></div></div>" +
      "<div class='sub' style='margin-top:6px'>Przeciągnij trening na inny dzień (na telefonie: szczegóły → „przenieś na…”) · kliknij po szczegóły i akcje · menu ⋯ przy dniu: REST DAY / choroba / delegacja / brak czasu. Plan aktualizuje się sam po Twoich zmianach, zmianach w Kalendarzu, celach i dostępności — także kolejne tygodnie; Twoje ręczne treningi zostają. Zrobione z Garmina odhaczają się same. <a href='/cwiczenia.html'>Baza ćwiczeń →</a></div>";
    document.getElementById("trw-p").onclick = function () { S.wk -= WK; wkLines = null; rWeek(); };
    document.getElementById("trw-n").onclick = function () { S.wk += WK; wkLines = null; rWeek(); };
    document.getElementById("trw-now").onclick = function () { S.wk = monday(todayMs()); wkLines = null; rWeek(); };
    document.getElementById("trw-t").textContent = "Tydzień " + pl(S.wk) + "–" + pl(S.wk + 6 * DAY);
    var past = S.wk + 6 * DAY < todayMs();
    var gb = document.getElementById("trw-gen"); gb.disabled = past;
    gb.onclick = function () { gb.disabled = true; gb.textContent = "liczę…"; api("POST", "/week/generate", { start: iso(S.wk) }).then(function (j) { wkLines = j; S.autoReview = true; rWeek(); toast("Plan przeliczony — AI sprawdza…"); }).catch(function (e) { fail(e); rWeek(); }); };
    api("GET", "/week?start=" + iso(S.wk)).then(function (j) { drawWeek(j); }).catch(fail);
  }
  function drawWeek(j) {
    var meta = j.meta || {}, T0 = todayMs(), g = document.getElementById("trw-g"); if (!g) return;
    var ph = document.getElementById("trw-ph"); ph.textContent = (meta.phase_name || "—") + (meta.light ? " · tydzień lżejszy" : ""); ph.className = "pill good";
    var ses = j.sessions || [], act = ses.filter(function (x) { return x.status !== "skip"; });
    var pl_ = act.reduce(function (a, x) { return a + x.dur_min; }, 0) / 60, dn = act.filter(function (x) { return x.status === "done"; }).reduce(function (a, x) { return a + x.dur_min; }, 0) / 60;
    var linked = {}; ses.forEach(function (x) { if (x.training_session_id) linked[x.training_session_id] = 1; });
    var extra = (j.activities || []).filter(function (a) { return !linked[a.id]; });
    var exh = extra.reduce(function (a, x) { return a + (x.duration_s || 0); }, 0) / 3600;
    var xs = act.reduce(function (a, x) { return a + (x.xss || 0); }, 0), cnt = {};
    act.forEach(function (x) { cnt[x.sport] = cnt[x.sport] || [0, 0]; cnt[x.sport][0]++; if (x.status === "done") cnt[x.sport][1]++; });
    document.getElementById("trw-sum").innerHTML = "<div class='mini'><p class='lbl'>Plan / zrobione</p><div class='v'>" + pl_.toFixed(1) + " / " + (dn + exh).toFixed(1) + " h</div></div><div class='mini'><p class='lbl'>Obciążenie (plan)</p><div class='v'>~" + Math.round(xs) + " XSS</div></div><div class='mini'><p class='lbl'>Sesje ✓/plan</p><div class='v' style='font-size:14px'>" + (Object.keys(cnt).map(function (k) { return AIC[k] + " " + cnt[k][1] + "/" + cnt[k][0]; }).join(" · ") || "—") + "</div></div><div class='mini'><p class='lbl'>Cel z Sezonu</p><div class='v'>" + (meta.target_h != null ? meta.target_h + " h" : "—") + "</div></div>";
    var tg = document.getElementById("trw-tg");
    var chAdd = ses.filter(function (x) { return (x.note || "").indexOf("dodane przez Ciebie") === 0; }).length,
        chDel = ses.filter(function (x) { return x.status === "skip" && (x.note || "").indexOf("usunięte przez Ciebie") === 0; }).length,
        chEd = ses.filter(function (x) { return x.source === "manual" && (x.note || "").indexOf("dodane przez Ciebie") !== 0 && x.status !== "skip" && x.status !== "done"; }).length;
    if (meta.target_h) { var mx = meta.target_h * 1.6, lo = meta.target_h * 0.75, hi = meta.target_h * 1.25;
      tg.innerHTML = "<div style='position:relative;height:12px;border-radius:6px;background:var(--line);overflow:hidden;margin:4px 0'><i style='position:absolute;top:0;bottom:0;left:" + (lo / mx * 100) + "%;width:" + ((hi - lo) / mx * 100) + "%;background:var(--good-bg);border-left:2px solid var(--good);border-right:2px solid var(--good)'></i><i style='position:absolute;top:0;bottom:0;left:0;width:" + Math.min(100, pl_ / mx * 100) + "%;background:rgba(47,158,91,.35)'></i><i style='position:absolute;top:0;bottom:0;left:0;width:" + Math.min(100, (dn + exh) / mx * 100) + "%;background:var(--good)'></i></div><div class='sub' style='font-size:12px;margin-bottom:6px'>plan " + pl_.toFixed(1) + " h · zrobione " + (dn + exh).toFixed(1) + " h · cel " + meta.target_h + " h (widełki " + lo.toFixed(1) + "–" + hi.toFixed(1) + ") " + (pl_ + exh < lo ? "· <b style='color:var(--warn)'>mniej niż zwykle</b>" : (pl_ + exh > hi ? "· <b style='color:var(--warn)'>więcej niż zwykle</b>" : "· ✓ w widełkach")) +
        (chAdd || chDel || chEd ? " · Twoje zmiany: " + [chAdd ? "＋" + chAdd + " dodane" : "", chEd ? "✎" + chEd + " zmienione" : "", chDel ? "−" + chDel + " usunięte" : ""].filter(Boolean).join(", ") : "") + "</div>"; }
    var al = "";
    if (meta.readiness_today != null && meta.readiness_threshold != null && meta.readiness_today < meta.readiness_threshold && T0 >= S.wk && T0 <= S.wk + 6 * DAY)
      al += "<div class='tr-note' style='border-color:var(--warn);background:var(--warn-bg)'>🫀 Gotowość dziś <b>" + meta.readiness_today.toFixed(2) + "</b> (próg " + meta.readiness_threshold.toFixed(2) + ") — silnik ustawia dziś wersje minimum. <button class='tr-btn sm' data-dact='short' data-day='" + iso(T0) + "'>dziś brak czasu / lżej</button></div>";
    (meta.season_notes || []).forEach(function (n) { al += "<div class='tr-note' style='border-color:var(--warn);background:var(--warn-bg)'>🩺 " + esc(n) + " <a class='link' href='/forma.html#sezon'>Sezon →</a></div>"; });
    var wAck = 0;
    (j.warnings || []).forEach(function (w) {
      if (typeof w === "string") w = { text: w, key: null };
      if (w.acked) { wAck++; return; }
      al += "<div class='tr-note' style='border-color:var(--warn);background:var(--warn-bg);display:flex;justify-content:space-between;gap:8px;align-items:center'><span>⚠️ " + esc(w.text) + "</span>" + (w.session_id ? "<button class='tr-btn sm' data-ack='" + esc(w.key) + "' data-sid='" + w.session_id + "'>rozumiem, zostaw</button>" : "") + "</div>";
    });
    if (wAck) al += "<div class='sub' style='font-size:11px'>wyciszone uwagi: " + wAck + " (Twoje decyzje — trener i AI ich nie powtarzają)</div>";
    if (j.auto_planned) al += "<div class='sub'>🗓️ Ten tydzień zaplanował się automatycznie (trener planuje bieżący + 2 kolejne tygodnie).</div>";
    if (j.calendar_update) al += "<div class='tr-note'>🗓️ Plan zaktualizowany sam: " + esc(j.calendar_update.reason) + (j.calendar_update.weeks > 1 ? " (także kolejne tygodnie)" : "") + ". Zmiany tego tygodnia poniżej — możesz je cofnąć.</div>";
    if (meta.error) al += "<div class='tr-note' style='border-color:var(--bad)'>Meta planu niedostępne: " + esc(meta.error) + "</div>";
    if (!meta.has_weather && S.wk + 6 * DAY >= T0) al += "<div class='sub' style='font-size:12px'>Prognoza pogody niedostępna — plan bez pogody.</div>";
    document.getElementById("trw-al").innerHTML = al;
    var chg = document.getElementById("trw-chg"), pc = j.pending_change;
    if (wkLines && pc && wkLines.change_id === pc.id) {
      chg.innerHTML = "<div class='tr-note'><b>Zmiany w tygodniu:</b>" + (wkLines.lines.length ? "<ul style='margin:4px 0 6px 18px;padding:0'>" + wkLines.lines.map(function (l) { return "<li>" + esc(l) + "</li>"; }).join("") + "</ul>" : " bez zmian w sesjach.") + (wkLines.notes && wkLines.notes.length ? "<div class='sub'>" + wkLines.notes.map(esc).join("<br>") + "</div>" : "") + "<button class='tr-btn pri sm' id='trw-ok'>Akceptuj</button> <button class='tr-btn sm' id='trw-un'>Cofnij</button></div>";
    } else if (pc) {
      chg.innerHTML = "<div class='tr-note'>Ostatnia zmiana (" + esc(pc.action) + ") czeka na decyzję." + (pc.payload && pc.payload.notes && pc.payload.notes.length ? "<div class='sub'>" + pc.payload.notes.map(esc).join("<br>") + "</div>" : "") + " <button class='tr-btn pri sm' id='trw-ok'>Akceptuj</button> <button class='tr-btn sm' id='trw-un'>Cofnij</button></div>";
    } else chg.innerHTML = "";
    if (pc) {
      document.getElementById("trw-ok").onclick = function () { api("POST", "/week/accept", { id: pc.id }).then(function () { wkLines = null; rWeek(); }).catch(fail); };
      document.getElementById("trw-un").onclick = function () { api("POST", "/week/undo", { id: pc.id }).then(function () { wkLines = null; rWeek(); toast("Cofnięto"); }).catch(fail); };
    }
    if (!ses.length && !(j.activities || []).length && S.wk + 6 * DAY >= T0) chg.innerHTML += "<div class='tr-note'>Brak planu na ten tydzień — kliknij <b>↻ przelicz tydzień</b>. Silnik bierze Twoje cele, wpisy tygodnia, Kalendarz, gotowość i prognozę.</div>";
    var h = "";
    for (var i = 0; i < 7; i++) {
      var ms = S.wk + i * DAY, ds = iso(ms), dm = (meta.days || {})[ds] || {}, fut = ms >= T0, items = [];
      (dm.busy || []).forEach(function (b) { items.push({ s: tm(b.a), h: "<div class='tr-it busy'>" + esc(b.label) + " <span style='opacity:.8'>" + b.a + "–" + b.b + "</span></div>" }); });
      (j.calendar || []).forEach(function (c) { var a = c.day, b = c.end_day || c.day; if (ds < a || ds > b) return; if (c.event_type === "rest" || c.kind === "illness" || c.event_type === "delegacja") return;
        if (c.at_time) return;  // wydarzenia z godzina sa juz widoczne jako zajetosc albo (trasa) jako trening — bez dublowania
        if ((meta.route_entry_ids || []).indexOf(c.id) >= 0) return;  // wpis z trasa = trening w planie (dopasowany), nie osobny kafelek
        if (c.kind === "feel") return;  // samopoczucie = emotka w naglowku dnia (pelna informacja w dymku)
        items.push({ s: c.at_time ? tm(c.at_time) : -1, h: "<div class='tr-it cal'>" + (CALIC[c.event_type] || KIC[c.kind] || "📅") + " " + esc(c.title || c.event_type || c.kind) + (c.at_time ? " " + String(c.at_time).slice(0, 5) : "") + "</div>" }); });
      /* 2026-10-06: wykonanie vs plan na karcie zrobionej sesji (realny czas i obciazenie; oznaczenie od 10%) */
      var realLine = function (x) {
        if (x.status !== "done" || x.real_min == null) return "";
        var pm = +x.dur_min, rm = +x.real_min, px = x.xss != null ? +x.xss : null, rx = x.real_xss != null ? +x.real_xss : null;
        var p1 = pm ? (rm - pm) / pm : 0, p2 = (px != null && rx != null) ? (rx - px) / Math.max(px, 1) : null, p = p2 != null ? p2 : p1;
        var fl = (Math.abs(p1) >= 0.1 || (p2 != null && Math.abs(p2) >= 0.1)) ? (p > 0 ? "więcej niż plan" : "mniej niż plan") : "jak w planie";
        var hm2 = function (m) { m = Math.round(m); return m >= 60 ? Math.floor(m / 60) + ":" + String(m % 60).padStart(2, "0") : m + "′"; };
        return "<div style='font-size:11.5px;margin-top:3px;line-height:1.35'>realnie " + hm2(rm) + (rx != null ? " · obc. " + Math.round(rx) : "") + " <span style='opacity:.75'>(plan " + pm + "′" + (px != null ? " · " + Math.round(px) : "") + ")</span><br><b style='color:" + (fl === "jak w planie" ? "var(--good)" : "var(--warn)") + "'>" + fl + "</b></div>";
      };
      ses.forEach(function (x) {
        if (x.day !== ds) return; var op = wkOpen === x.id, canEd = fut && x.status === "plan";
        var hh = "<div class='tr-it plan tr-ses" + (x.status === "done" ? " done" : "") + "' data-sid='" + x.id + "' draggable='" + canEd + "' style='border-left-color:" + SCOL[x.sport] + (x.status === "skip" ? ";opacity:.5;text-decoration:line-through" : "") + (canEd ? ";cursor:grab" : "") + "'><div class='tr-sh' style='cursor:pointer'>" + (x.status === "done" ? "✓ " : (x.status === "skip" ? "✕ " : "")) + AIC[x.sport] + " " + esc(x.name) + "<br><span style='opacity:.8'>" + (x.start_time || "") + " · " + x.dur_min + "′" + (x.cut ? " min" : "") + ((x.note || "").indexOf("dodane przez Ciebie") === 0 ? " · ＋ Twoje" : (x.status === "skip" && (x.note || "").indexOf("usunięte przez Ciebie") === 0 ? " · usunięte" : (x.source === "manual" ? " · ✎" : ""))) + (x.rating ? " · <span style='color:var(--accent)' title='Twoja ocena planu'>" + "★".repeat(x.rating) + "</span>" : "") + "</span>" + realLine(x) + "</div>";
        if (op) {
          hh += "<div style='border-top:1px dashed var(--line);margin-top:4px;padding-top:4px;display:flex;flex-direction:column;gap:5px'><div style='white-space:pre-line'>" + esc(x.details && x.details.text ? x.details.text : sdesc(x, meta)) + (x.note ? "\n" + esc(x.note) : "") + "</div>" +
            (x.sport === "sila" && x.details && x.details.engine ? "<a class='tr-btn sm' style='align-self:flex-start;text-decoration:none' href='/sciaga.html?id=" + x.id + "'>📄 Ściąga z grafikami</a>" : "");
          if (canEd) hh += "<div class='tr-tog'><button data-sa='done'>✓ zrobione</button>" + (x.min_min && x.min_min < x.dur_min ? "<button data-sa='cut'>⏱ minimum " + x.min_min + "′</button>" : "") + "<button data-sa='skip'>✕ pomiń</button><button data-sa='del'>🗑 usuń</button></div><div class='tr-tt'>godz. <input type='time' data-st='1' value='" + (x.start_time || "") + "'> czas <input type='number' min='5' max='600' step='5' data-sd='1' value='" + x.dur_min + "' style='width:64px'>′ <select data-ss='1'><option value=''>zamień na…</option>" + ACT.filter(function (a) { return a[0] !== x.sport; }).map(function (a) { return "<option value='" + a[0] + "'>" + a[1] + " " + a[2] + "</option>"; }).join("") + "</select>" +
            "<select data-sm='1'><option value=''>przenieś na…</option>" + [0, 1, 2, 3, 4, 5, 6].map(function (k) { var m2 = S.wk + k * DAY, d2 = iso(m2); return (m2 < T0 || d2 === ds) ? "" : "<option value='" + d2 + "'>" + DN[k] + " " + pl(m2) + (m2 === T0 ? " (dziś)" : "") + "</option>"; }).join("") + "</select></div>";
          else if (fut && x.status !== "plan") hh += "<div class='tr-tog'><button data-sa='undo'>↺ przywróć do planu</button></div>";
          /* 2026-09-28: ocena planu 1-5 + komentarz (POST /api/trener/rating; ponowny klik tej samej gwiazdki = usun) */
          hh += "<div class='tr-rate' style='display:flex;align-items:center;gap:6px;flex-wrap:wrap'><span style='font-size:12px;color:var(--muted)'>Oceń plan:</span>" + [1, 2, 3, 4, 5].map(function (n) { return "<button type='button' data-rt='" + n + "' title='" + ["", "zły plan", "słaby", "w porządku", "dobry", "świetny"][n] + (x.rating === n ? " (kliknij, aby usunąć ocenę)" : "") + "' style='border:0;background:none;cursor:pointer;font-size:21px;line-height:1;padding:0 1px;color:" + ((x.rating || 0) >= n ? "var(--accent)" : "var(--line)") + "'>★</button>"; }).join("") + "<input type='text' data-rn='1' maxlength='300' placeholder='komentarz (opcjonalnie) — co było nie tak / co dobre' value='" + esc(x.rating_note || "") + "' style='flex:1;min-width:150px;font-size:12px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:6px;padding:3px 6px'></div>";
          hh += "</div>";
        }
        items.push({ s: tm(x.start_time) || 0, h: hh + "</div>" });
      });
      extra.forEach(function (a) { if (String(a.date).slice(0, 10) !== ds) return; var km = a.distance_m ? (a.distance_m / 1000).toFixed(0) + " km · " : ""; items.push({ s: a.started_at ? (new Date(a.started_at).getHours() * 60 + new Date(a.started_at).getMinutes()) : 0, h: "<div class='tr-it done'>✓ " + (SPIC[a.sport_type] || "•") + " " + esc(a.activity_name || a.sport_type) + "<br><span style='opacity:.8'>" + km + ((a.duration_s || 0) / 3600).toFixed(1) + " h · poza planem</span></div>" }); });
      items.sort(function (x, y) { return x.s - y.s; });
      var wx = dm.wx, bad = wxBad(wx, meta.ov);
      var fs = dayFeels(j.calendar, ds), fm = feelMain(fs);
      var ftip = fs.map(function (c) { return FEEL_E[c.feel] + " " + (c.title || FEEL_L[c.feel]) + (c.note ? " — " + c.note : "") + (c.source === "trener" ? " (z notatki Trenera)" : ""); }).join("\n");
      h += "<div class='tr-day" + (ms === T0 ? " today" : "") + "' data-day='" + ds + "'><div class='dh' style='display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px;align-items:center'><span style='flex:1 1 100%;white-space:nowrap'>" + DN[i] + " " + pl(ms) + (ms === T0 ? " · dziś" : "") +
        (fm ? " <span title='" + esc(ftip) + "' style='font-size:16px;cursor:help'>" + FEEL_E[fm.feel] + "</span>" : "") + "</span>" +
        (ms <= T0 ? "<select data-feel='" + ds + "' title='Samopoczucie' style='font-size:11px;border:1px solid var(--line);background:var(--card);color:var(--ink2);border-radius:5px;flex:1 1 auto;min-width:0;max-width:100%'><option value=''>" + (fm ? FEEL_E[fm.feel] : "☺") + " samopoczucie</option>" +
          [2, 1, 0, -1, -2].map(function (v) { return "<option value='" + v + "'>" + FEEL_E[v] + " " + FEEL_L[v] + "</option>"; }).join("") + (fs.some(function (c) { return c.source !== "trener"; }) ? "<option value='del'>✕ usuń ocenę</option>" : "") + "</select>" : "") +
        (fut ? "<select class='tr-dm' data-dm='" + ds + "' style='font-size:11px;border:1px solid var(--line);background:var(--card);color:var(--ink2);border-radius:5px'><option value=''>⋯</option><option value='rest'>😴 REST DAY</option><option value='ill'>🤒 choroba</option><option value='del'>🧳 delegacja</option><option value='short'>⏱ brak czasu</option><option value='clear'>↺ zwykły dzień</option></select>" : "") + "</div>" +
        (wx ? "<div class='tr-wx' style='font-size:11px;" + (bad ? "color:var(--bad);font-weight:700" : "color:var(--muted)") + "' title='wiatr " + wx.wind + " m/s, porywy " + wx.gust + " · odczuwalna " + wx.feel_min + "…" + wx.feel_max + " °C · opad " + wx.rain_mmh + " mm/h (" + wx.rain_prob + "%)'>" + wx.icon + " " + wx.wind + " m/s · " + Math.round(wx.feel_max) + "°</div>" : "") +
        (DTYPE[dm.type] ? "<div class='tr-it cal'>" + DTYPE[dm.type] + "</div>" : "") +
        (items.length ? items.map(function (x) { return x.h; }).join("") : "<div class='tr-empty' style='padding:4px 0'>wolne</div>") +
        (fut ? "<select data-add='" + ds + "' style='margin-top:auto;font-size:11px;border:1px solid var(--line);background:var(--card);color:var(--ink2);border-radius:5px'><option value=''>＋ dodaj</option>" + ACT.map(function (a) { return "<option value='" + a[0] + "'>" + a[1] + " " + a[2] + "</option>"; }).join("") + "</select>" : "") + "</div>";
    }
    g.innerHTML = h;
    // dotyk: pogoda w szczegolach po dotknieciu (brak najechania mysza)
    g.querySelectorAll(".tr-wx").forEach(function (w) { w.onclick = function () { toast(w.title); }; });
    // waski ekran (karty dni): raz na tydzien przewin do dzis
    if (window.matchMedia && window.matchMedia("(max-width:1099px)").matches && S.scrolledWk !== S.wk) {
      S.scrolledWk = S.wk;
      var td = g.querySelector(".tr-day.today"); if (td && td.scrollIntoView) setTimeout(function () { td.scrollIntoView({ block: "start", behavior: "smooth" }); }, 50);
    }
    drawAsk();
    if (S.autoReview) { S.autoReview = false; runReview(false); } else drawReview();
    function reload() { rWeek(); }
    function put(id, b) { return api("PUT", "/sessions/" + id, b).then(reload).catch(fail); }
    function rateSave(x, r, note) { return api("POST", "/rating", { session_id: x.id, rating: r, note: (note || "").trim() || null }).then(function () { x.rating = r || null; x.rating_note = r ? ((note || "").trim() || null) : null; drawWeek(j); }).catch(fail); }
    g.querySelectorAll(".tr-ses").forEach(function (el) {
      var id = +el.dataset.sid, x = ses.filter(function (q) { return q.id === id; })[0];
      el.querySelector(".tr-sh").onclick = function () { wkOpen = wkOpen === id ? null : id; drawWeek(j); };
      el.ondragstart = function (e) { e.dataTransfer.setData("text/plain", String(id)); };
      el.querySelectorAll("[data-sa]").forEach(function (b) { b.onclick = function () {
        var a = b.dataset.sa;
        if (a === "done") put(id, { status: "done" });
        else if (a === "skip") put(id, { status: "skip" });
        else if (a === "undo") put(id, { status: "plan", cut: false, note: (x.note || "").indexOf("usunięte przez Ciebie") === 0 ? null : x.note });
        else if (a === "cut") put(id, { dur_min: x.min_min, cut: true });
        else if (a === "del") {
          if (!confirm("Usunąć „" + x.name + "” z planu?")) return;
          if ((x.note || "").indexOf("dodane przez Ciebie") === 0) api("DELETE", "/sessions/" + id).then(reload).catch(fail);
          else put(id, { status: "skip", note: "usunięte przez Ciebie" });
        }
      }; });
      el.querySelectorAll("[data-rt]").forEach(function (b) { b.onclick = function (ev) { ev.stopPropagation(); var n = +b.dataset.rt, ni = el.querySelector("[data-rn]"); rateSave(x, x.rating === n ? 0 : n, ni ? ni.value : x.rating_note); }; });
      var rn = el.querySelector("[data-rn]"); if (rn) { rn.onclick = function (ev) { ev.stopPropagation(); }; rn.onchange = function () { if (x.rating) rateSave(x, x.rating, rn.value); else rn.placeholder = "najpierw kliknij gwiazdki"; }; }
      var st = el.querySelector("[data-st]"); if (st) st.onchange = function () { if (st.value) put(id, { start_time: st.value }); };
      var sd = el.querySelector("[data-sd]"); if (sd) sd.onchange = function () { var v = +sd.value; if (v > 0) put(id, { dur_min: v, min_min: Math.min(x.min_min || v, v) }); };
      var sm = el.querySelector("[data-sm]"); if (sm) sm.onchange = function () { if (sm.value) put(id, { day: sm.value }); };
      var ss = el.querySelector("[data-ss]"); if (ss) ss.onchange = function () { var k = ss.value; if (!k) return; put(id, { sport: k, name: ({ rower: "Rower spokojnie", sila: "Siła", wiosl: "Wioślarz spokojnie", joga: "Joga" })[k], zone: k === "rower" ? 2 : null, is_long: false, dur_min: k === "joga" ? Math.min(x.dur_min, 30) : Math.min(x.dur_min, k === "rower" ? 120 : 45), min_min: ({ rower: 30, sila: 15, wiosl: 15, joga: 10 })[k] }); };
    });
    g.querySelectorAll(".tr-day").forEach(function (el) {
      var ds = el.dataset.day; if (D(ds) < T0) return;
      el.ondragover = function (e) { e.preventDefault(); el.style.outline = "2px dashed var(--accent)"; };
      el.ondragleave = function () { el.style.outline = ""; };
      el.ondrop = function (e) { e.preventDefault(); el.style.outline = ""; var id = +e.dataTransfer.getData("text/plain"); var x = ses.filter(function (q) { return q.id === id; })[0]; if (!x || x.day === ds) return; put(id, { day: ds }); };
    });
    g.querySelectorAll("[data-feel]").forEach(function (sel) { sel.onchange = function () { var v = sel.value; if (!v) return;
      feelSave(j.calendar, sel.dataset.feel, v).then(function () { toast(v === "del" ? "Usunięto ocenę samopoczucia" : "Samopoczucie: " + FEEL_E[v] + " " + FEEL_L[v]); reload(); }).catch(fail); }; });
    g.querySelectorAll("[data-dm]").forEach(function (sel) { sel.onchange = function () { var a = sel.value; if (!a) return; dayAction(sel.dataset.dm, a); }; });
    document.querySelectorAll("#trw-al [data-dact]").forEach(function (b) { b.onclick = function () { dayAction(b.dataset.day, b.dataset.dact); }; });
    document.querySelectorAll("#trw-al [data-ack]").forEach(function (b) { b.onclick = function () {
      var sid = +b.dataset.sid, x = ses.filter(function (q) { return q.id === sid; })[0]; if (!x) return;
      var ak = (x.acks || []).slice(); if (ak.indexOf(b.dataset.ack) < 0) ak.push(b.dataset.ack);
      api("PUT", "/sessions/" + sid, { acks: ak }).then(function () { toast("OK — uwaga wyciszona"); reload(); }).catch(fail); }; });
    g.querySelectorAll("[data-add]").forEach(function (sel) { sel.onchange = function () { var k = sel.value; if (!k) return;
      api("POST", "/sessions", { day: sel.dataset.add, sport: k, note: "dodane przez Ciebie", name: ({ rower: "Rower spokojnie", sila: "Siła obwodowa", wiosl: "Wioślarz spokojnie", joga: "Joga" })[k], start_time: ({ rower: "12:00", sila: "10:00", wiosl: "16:00", joga: "09:00" })[k], dur_min: ({ rower: 60, sila: 40, wiosl: 30, joga: 20 })[k], min_min: ({ rower: 30, sila: 15, wiosl: 15, joga: 10 })[k], zone: k === "rower" ? 2 : null }).then(reload).catch(fail); }; });
  }
  function dayAction(ds, a) { api("POST", "/week/action", { day: ds, action: a }).then(function (j) { wkLines = j; S.autoReview = true; rWeek(); }).catch(function (e) { fail(e); rWeek(); }); }
  var SEVC = { "wysoka": ["🔴", "var(--bad)"], "średnia": ["🟡", "var(--warn)"], "niska": ["⚪", "var(--muted)"] };
  // Prosba do AI o zmiane planu (POST /week/ask -> propozycje; /week/ask/apply -> Twoje zmiany z Akceptuj / Cofnij)
  function drawAsk() {
    var el = document.getElementById("trw-ask"); if (!el) return;
    if (S.wk + 6 * DAY < todayMs()) { el.innerHTML = ""; return; }
    var A = (S.ask && S.ask.wk === S.wk) ? S.ask : (S.ask = { wk: S.wk, text: "", res: null, busy: false });
    var h = "<div class='tr-ask'><b>💬 Poproś Trenera o zmianę</b><textarea id='tra-txt' rows='2' maxlength='600' placeholder='np. Dziś siła bez nóg, a do tego 30–45′ roweru po południu (testuję Graila)'>" + esc(A.text) + "</textarea>" +
      "<div><button class='tr-btn pri sm' id='tra-go'" + (A.busy ? " disabled" : "") + ">" + (A.busy ? "AI układa zmiany…" : "Zaproponuj zmiany") + "</button>" + (A.res && !A.busy ? " <button class='tr-btn sm' id='tra-x'>wyczyść</button>" : "") + "</div>";
    if (A.busy) h += "<div class='sub' style='margin-top:4px'>AI czyta Twoją prośbę i plan tygodnia (ok. 10–15 s)…</div>";
    if (A.res && !A.busy) {
      var r = A.res, ch = r.changes || [];
      h += "<div class='sub' style='margin:6px 0 2px'>" + esc(r.summary || "") + "</div>";
      if (ch.length) h += "<ul class='tr-ask-l'>" + ch.map(function (c) { return "<li>" + esc(c.line) + (c.warn ? " <span style='color:var(--warn)'>⚠ " + esc(c.warn) + "</span>" : "") + "</li>"; }).join("") + "</ul>" +
        "<button class='tr-btn pri sm' id='tra-ok'>✓ Zastosuj</button> <button class='tr-btn sm' id='tra-no'>✕ Odrzuć</button>" +
        "<div class='sub' style='font-size:11px;margin-top:4px'>Nic się nie zmieni, dopóki nie klikniesz „Zastosuj”. Potem możesz cofnąć.</div>";
      if ((r.rejected || []).length) h += "<div class='sub' style='font-size:11px;margin-top:4px'>Odrzucone przez bezpieczniki: " + r.rejected.map(esc).join(" · ") + "</div>";
    }
    el.innerHTML = h + "</div>";
    var ta = document.getElementById("tra-txt");
    ta.oninput = function () { A.text = ta.value; };
    function ask() {
      var t = (ta.value || "").trim(); if (!t || A.busy) return;
      A.text = t; A.busy = true; A.res = null; drawAsk();
      api("POST", "/week/ask", { start: iso(S.wk), text: t }).then(function (r) { A.busy = false; A.res = r; drawAsk(); })
        .catch(function (e) { A.busy = false; A.res = { summary: "Błąd: " + e.message, changes: [], rejected: [] }; drawAsk(); });
    }
    ta.onkeydown = function (e) { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask(); };
    document.getElementById("tra-go").onclick = ask;
    var x = document.getElementById("tra-x"); if (x) x.onclick = function () { A.res = null; A.text = ""; drawAsk(); };
    var no = document.getElementById("tra-no"); if (no) no.onclick = function () { A.res = null; drawAsk(); };
    var ok = document.getElementById("tra-ok"); if (ok) ok.onclick = function () {
      ok.disabled = true; ok.textContent = "zapisuję…";
      api("POST", "/week/ask/apply", { start: iso(S.wk), text: A.text, changes: A.res.changes }).then(function (j) {
        wkLines = j; S.ask = null; S.autoReview = true; rWeek(); toast("Zmiany zastosowane — możesz je cofnąć");
      }).catch(function (e) { fail(e); ok.disabled = false; ok.textContent = "✓ Zastosuj"; });
    };
  }
  function drawReview(state, r) {
    var el = document.getElementById("trw-ai"); if (!el) return;
    if (S.wk + 6 * DAY < todayMs()) { el.innerHTML = ""; return; }
    var head = "<div style='display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:8px'><b>🤖 Weryfikacja AI</b><button class='tr-btn sm' id='trw-rv'>" + (state === "busy" ? "sprawdzam…" : "sprawdź plan") + "</button></div>";
    var h = "";
    if (state === "busy") h = "<div class='sub'>AI czyta plan, Kalendarz, pogodę i cele (ok. 10–15 s)…</div>";
    else if (r) {
      h = "<div class='sub' style='margin:4px 0'>" + esc(r.summary || "") + (r.cached ? " <span class='au'>(z pamięci)</span>" : "") + "</div>" +
        (r.issues || []).map(function (i) { var c = SEVC[i.severity] || SEVC["średnia"]; return "<div class='tr-note' style='border-color:" + c[1] + ";margin:4px 0'><b>" + c[0] + " " + DN[(new Date(D(i.day)).getUTCDay() + 6) % 7] + " " + pl(D(i.day)) + ": " + esc(i.problem) + "</b>" + (i.why ? "<div class='sub'>dlaczego: " + esc(i.why) + "</div>" : "") + (i.suggestion ? "<div class='sub'>👉 " + esc(i.suggestion) + "</div>" : "") + "</div>"; }).join("") +
        (!(r.issues || []).length ? "<div class='sub'>✓ AI nie widzi problemów w tym planie.</div>" : "") +
        "<div class='sub' style='font-size:11px'>AI tylko doradza — nic nie zmienia samo. Zmiany robisz przeciągając treningi albo menu ⋯.</div>";
    } else h = "<div class='sub'>Kliknij „sprawdź plan”, żeby AI przejrzało tydzień pod kątem rzeczy bez sensu (np. siła przy długiej jeździe, konflikt z Kalendarzem, pogoda).</div>";
    el.innerHTML = "<div style='border-top:1px solid var(--line);margin-top:10px;padding-top:6px'>" + head + h + "</div>";
    document.getElementById("trw-rv").onclick = function () { runReview(true); };
  }
  function runReview(force) {
    drawReview("busy");
    api("POST", "/week/review", { start: iso(S.wk), force: !!force }).then(function (r) { drawReview("done", r); }).catch(function (e) { drawReview("done", { summary: "Błąd weryfikacji: " + e.message, issues: [] }); });
  }

  // ======================= CZAS =======================
  function rTime() {
    body.innerHTML = "<div class='tr-empty'>Liczę…</div>";
    api("GET", "/time").then(function (t) {
      var free = t.free || [], mxf = Math.max.apply(null, free.map(function (f) { return f.free_min; }).concat([60]));
      var st = t.target_h > t.budget_h ? "<b style='color:var(--warn)'>powyżej Twojego limitu " + t.budget_h + " h</b>" : (t.free_h < t.target_h ? "<b style='color:var(--bad)'>wolnych okien mniej niż potrzeba</b>" : "✓ mieści się");
      var h = "<div class='card'><div class='cardhead'><h2>Ile czasu wygospodarować</h2><span class='sub'>tydzień od " + pl(D(t.week_start)) + " · " + esc(t.phase_name || "") + "</span></div>" +
        "<div class='g3'><div class='mini'><p class='lbl'>Optimum (Sezon)</p><div class='v'>" + t.target_h + " h</div></div><div class='mini'><p class='lbl'>Twój limit (Kalibracja)</p><div class='v'>" + t.budget_h + " h</div></div><div class='mini'><p class='lbl'>Wolne okna w tym tygodniu</p><div class='v'>" + t.free_h + " h</div></div></div>" +
        "<div class='sub' style='margin:8px 0'>" + st + ". Wolne okna = Twoje okna treningu (albo 9–20 / weekend 7–20, gdy ich nie ma) minus zajętości i dni REST / choroba / wyprawa.</div>" +
        free.map(function (f, i) { return "<div style='display:grid;grid-template-columns:70px 1fr 70px;gap:8px;align-items:center;font-size:12.5px;margin:3px 0'><span>" + DN[i] + " " + pl(D(f.day)) + "</span><div style='height:10px;border-radius:5px;background:var(--line);overflow:hidden'><i style='display:block;height:100%;width:" + Math.round(f.free_min / mxf * 100) + "%;background:var(--good)'></i></div><b style='text-align:right'>" + (f.free_min / 60).toFixed(1) + " h" + (DTYPE[f.type] ? " " + DTYPE[f.type].split(" ")[0] : "") + "</b></div>"; }).join("") + "</div>";
      var ms = t.months || [], mx = Math.max.apply(null, ms.map(function (m) { return m.h_max; }).concat([1]));
      h += "<div class='card'><div class='cardhead'><h2>Optimum w kolejnych miesiącach</h2><span class='sub'>h / tydzień, z Sezonu</span></div><div style='display:grid;grid-template-columns:repeat(" + ms.length + ",1fr);gap:4px;align-items:end;height:130px'>" +
        ms.map(function (m) { return "<div style='display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;font-size:10.5px;color:var(--muted)' title='" + m.h_min + "–" + m.h_max + " h'><b style='color:var(--ink)'>" + m.h_avg + "</b><i style='display:block;width:60%;height:" + Math.round(m.h_avg / mx * 90) + "%;background:var(--accent);border-radius:3px 3px 0 0'></i><span>" + MN[+m.month.slice(5) - 1] + "</span></div>"; }).join("") + "</div></div>";
      body.innerHTML = h;
    }).catch(function (e) { body.innerHTML = "<div class='tr-empty'>Błąd: " + esc(e.message) + "</div>"; });
  }

  // ======================= BILANS I WAGA =======================
  function rBal() {
    body.innerHTML = "<div class='tr-empty'>Liczę…</div>";
    Promise.all([api("GET", "/balance"), api("GET", "/labs")]).then(function (res) {
      var b = res[0], w = b.window || {}, labs = res[1].items || [];
      var src = w.source === "logs" ? "<span class='tr-st active'>z logów</span>" : (w.source === "weight" ? "<span class='tr-st paused'>z wagi</span>" : "<span class='tr-st'>brak danych</span>");
      function kc(v) { return v == null ? "—" : (v > 0 ? "+" : "") + v; }
      var h = "<div class='g3'><div class='card tight'><p class='lbl'>Bilans średnio (" + w.days + " dni)</p><div class='big' style='margin-top:4px'>" + kc(w.balance_kcal) + "<span class='u'>kcal/d</span></div><div class='delta'>" + src + " · logi w " + w.days_logged + " z " + w.days + " dni</div></div>" +
        "<div class='card tight'><p class='lbl'>Waga — trend 30 dni</p><div class='big' style='margin-top:4px'>" + (b.trend30.weight_slope_kg_wk == null ? "—" : kc(b.trend30.weight_slope_kg_wk)) + "<span class='u'>kg/tydz.</span></div><div class='delta'>≈ " + kc(b.trend30.balance_weight) + " kcal/d</div></div>" +
        "<div class='card tight'><p class='lbl'>Cel tempa</p><div class='big' style='margin-top:4px'>−" + b.target_loss_kg_wk + "<span class='u'>kg/tydz.</span></div><div class='delta'>≈ " + b.target_balance_kcal + " kcal/d · " + esc(b.target_source) + "</div></div></div>";
      var se = b.series || [], wv = se.map(function (x) { return x.weight; }).filter(function (x) { return x != null; });
      if (wv.length >= 2) {
        var lo = Math.min.apply(null, wv) - 0.5, hi = Math.max.apply(null, wv) + 0.5, W_ = 640, H_ = 130;
        function X(i) { return 30 + i * (W_ - 40) / Math.max(1, se.length - 1); } function Y(v) { return 10 + (hi - v) / (hi - lo) * (H_ - 30); }
        var dots = se.map(function (x, i) { return x.weight != null ? "<circle cx='" + X(i) + "' cy='" + Y(x.weight) + "' r='2.5' fill='var(--muted)'/>" : ""; }).join("");
        var line = se.map(function (x, i) { return x.weight_s != null ? (X(i) + "," + Y(x.weight_s)) : null; }).filter(Boolean).join(" ");
        h += "<div class='card'><div class='cardhead'><h2>Waga — 30 dni</h2><span class='sub'>kropki = pomiary · linia = średnia 7 dni</span></div><svg viewBox='0 0 " + W_ + " " + H_ + "' style='width:100%;height:auto'><text x='0' y='" + (Y(hi - 0.5) + 4) + "' font-size='10' fill='var(--muted)'>" + (hi - 0.5).toFixed(1) + "</text><text x='0' y='" + (Y(lo + 0.5) + 4) + "' font-size='10' fill='var(--muted)'>" + (lo + 0.5).toFixed(1) + "</text>" + dots + "<polyline points='" + line + "' fill='none' stroke='var(--purple)' stroke-width='2.5'/></svg></div>";
      }
      h += "<div class='card'><div class='cardhead'><h2>Skąd bierze się bilans</h2></div><div class='rows'>" +
        "<div class='r'><span class='w'>1.</span><span class='s'>Są wpisy jedzenia (≥70% dni w oknie) → bilans z logów: " + kc(w.balance_logs) + " kcal/d</span><span></span></div>" +
        "<div class='r'><span class='w'>2.</span><span class='s'>Mało wpisów → z wagi: nachylenie wagi (" + (w.weight_slope_kg_wk == null ? "—" : kc(w.weight_slope_kg_wk) + " kg/tydz.") + ") × 7700 kcal/kg = " + kc(w.balance_weight) + " kcal/d</span><span></span></div>" +
        "<div class='r'><span class='w'>3.</span><span class='s'>Wydatek średnio " + (w.expend_avg || "—") + " kcal/d (Garmin + ModelQ) → jedzenie wg wagi ≈ " + (w.intake_from_weight || "—") + " kcal/d" + (w.intake_log_avg ? " · wg logów " + w.intake_log_avg : "") + "</span><span></span></div>" +
        "</div><div class='sub' style='margin-top:6px'>Okno i źródło ustawiasz w Kalibracji → Waga i jedzenie. Waga z dnia na dzień skacze ±1–2 kg (woda, sól) — ufaj trendowi, nie pojedynczemu pomiarowi.</div></div>";
      h += "<div class='card'><div class='cardhead'><h2>Badania</h2><button class='tr-btn pri' id='trl-add'>＋ dodaj wynik</button></div><div id='trl-f'></div>" +
        (labs.length ? labs.map(function (l) { return "<div class='tr-rule' style='grid-template-columns:90px 1fr auto'><span class='sub'>" + esc(l.day) + "</span><div><b>" + esc(l.name) + "</b>: " + (l.value != null ? esc(l.value) : "—") + " " + esc(l.unit || "") + (l.ref_range ? " <span class='sub'>(norma " + esc(l.ref_range) + ")</span>" : "") + (l.note ? "<br><span class='sub'>" + esc(l.note) + "</span>" : "") + "</div><button class='tr-btn sm bad' data-ld='" + l.id + "'>usuń</button></div>"; }).join("") : "<div class='tr-empty'>Brak wyników. Tu możesz trzymać np. testosteron, SHBG, TSH, HbA1c — z datą, obok trendu wagi.</div>") + "</div>";
      body.innerHTML = h;
      document.getElementById("trl-add").onclick = function () {
        var f = document.getElementById("trl-f");
        f.innerHTML = "<div class='tr-box'><div class='tr-form'><span>Data</span><input type='date' id='trl-d' value='" + iso(todayMs()) + "'><span>Badanie</span><input class='tr-in' id='trl-n' placeholder='np. Testosteron całkowity'><span>Wynik</span><div class='tr-tt'><input class='tr-in' id='trl-v' style='width:110px' placeholder='np. 4,5'> <input class='tr-in' id='trl-u' style='width:110px' placeholder='jednostka'></div><span>Norma</span><input class='tr-in' id='trl-r' placeholder='np. 2,5–8,4'><span>Uwagi</span><input class='tr-in' id='trl-o'></div><div style='margin-top:8px'><button class='tr-btn pri' id='trl-s'>Zapisz</button> <button class='tr-btn' id='trl-c'>Anuluj</button></div></div>";
        document.getElementById("trl-c").onclick = function () { f.innerHTML = ""; };
        document.getElementById("trl-s").onclick = function () { api("POST", "/labs", { day: document.getElementById("trl-d").value, name: document.getElementById("trl-n").value, value: document.getElementById("trl-v").value, unit: document.getElementById("trl-u").value, ref_range: document.getElementById("trl-r").value, note: document.getElementById("trl-o").value }).then(function () { toast("Zapisano wynik"); rBal(); }).catch(fail); };
      };
      body.querySelectorAll("[data-ld]").forEach(function (x) { x.onclick = function () { if (!confirm("Usunąć wynik?")) return; api("DELETE", "/labs/" + x.dataset.ld).then(rBal).catch(fail); }; });
    }).catch(function (e) { body.innerHTML = "<div class='tr-empty'>Błąd: " + esc(e.message) + "</div>"; });
  }

  // ======================= CELE =======================
  var KINDS = [["trip", "🗺️", "wyprawa wielodniowa"], ["long_ride", "🚴", "długa jazda jednodniowa"], ["volume", "📏", "objętość (km / h)"], ["weight", "⚖️", "waga"], ["power", "⚡", "moc (FTP)"], ["habit", "🔁", "nawyk"], ["other", "📌", "inne"]];
  var KIC2 = {}; KINDS.forEach(function (k) { KIC2[k[0]] = k[1]; });
  var TF = {
    trip: [["km", "Dystans (km)", "n"], ["up_m", "Przewyższenie (m)", "n"], ["days", "Liczba dni", "n"], ["surface", "Nawierzchnia", "t"], ["bags", "Bagaż", "t"]],
    long_ride: [["km", "Dystans (km)", "n"], ["up_m", "Przewyższenie (m)", "n"]],
    volume: [["km", "km w okresie", "n"], ["h", "godzin w okresie", "n"]],
    weight: [["weight_kg", "Waga docelowa (kg)", "n"]],
    power: [["ftp_w", "FTP docelowe (W)", "n"]],
    habit: [["sport", "Aktywność", "s"], ["per_week", "Razy w tygodniu", "n"]],
    other: [["text", "Opis", "t"]]
  };
  var STN = { active: "aktywny", paused: "wstrzymany", done: "zakończony", dropped: "porzucony" };
  function goalSummary(g) {
    var t = g.target || {}, p = [];
    if (t.km) p.push(t.km + " km"); if (t.up_m) p.push(t.up_m + " m w górę"); if (t.days) p.push(t.days + " dni");
    if (t.h) p.push(t.h + " h"); if (t.weight_kg) p.push("→ " + t.weight_kg + " kg"); if (t.ftp_w) p.push("→ " + t.ftp_w + " W");
    if (t.sessions) p.push(t.sessions + " sesji"); if (t.wkg) p.push("→ " + t.wkg + " W/kg"); if (t.km_week) p.push((AIC[t.sport] || "") + " " + t.km_week + " km / tydz.");
    if (t.per_week) p.push((AIC[t.sport] || "") + " " + t.per_week + "× / tydz." + (t.min ? " po " + t.min + "′" : "")); if (t.start_time) p.push("start " + t.start_time); if (t.target_h) p.push("cel " + t.target_h + " h");
    if (t.surface) p.push(t.surface); if (t.bags) p.push(({ bez: "bez bagażu", lekki: "lekki bikepacking", pelny: "pełny bikepacking", sakwy: "sakwy" })[t.bags] || t.bags); if (t.text) p.push(t.text);
    if (g.kind === "volume" && t.sport && t.sport !== "rower") p.unshift(AIC[t.sport] || "");
    return p.join(" · ");
  }
  function rGoals(editId) {
    var h = "<div class='card'><div class='cardhead'><h2>Moje cele</h2><button class='tr-btn pri' id='trg-add'>＋ dodaj cel</button></div>";
    if (editId === "new") h += "<div id='trg-f'></div>";
    if (!S.goals.length && editId !== "new") h += "<div class='tr-empty'>Nie masz jeszcze celów. Dodaj pierwszy — wyprawę, wagę, kilometry albo nawyk.</div>";
    S.goals.forEach(function (g) {
      var dd = g.date_from ? Math.round((D(g.date_from) - todayMs()) / DAY) : null;
      h += "<div class='tr-goal'><span class='ic'>" + (KIC2[g.kind] || "📌") + "</span><div><div class='t'>" + esc(g.name) + "<span class='tr-pr " + g.priority + "'>" + g.priority + "</span></div><div class='m'>" +
        (g.date_from ? g.date_from + (g.date_to && g.date_to !== g.date_from ? " – " + g.date_to : "") : "bez terminu") + (goalSummary(g) ? " · " + esc(goalSummary(g)) : "") + (g.note ? "<br>" + esc(g.note) : "") + "</div></div>" +
        "<span style='text-align:right'><span class='tr-st " + g.status + "'>" + STN[g.status] + "</span>" + (dd != null && dd >= 0 && g.status === "active" ? "<div class='m' style='font-size:12px;color:var(--muted);margin-top:4px'>za " + dd + " dni</div>" : "") + "</span>" +
        "<div class='act'><button class='tr-btn sm' data-ge='" + g.id + "'>" + (editId === g.id ? "zamknij" : "edytuj") + "</button>" +
        (g.status === "active" ? "<button class='tr-btn sm' data-gs='" + g.id + "' data-v='paused'>wstrzymaj</button><button class='tr-btn sm' data-gs='" + g.id + "' data-v='done'>zakończ</button>" : "<button class='tr-btn sm' data-gs='" + g.id + "' data-v='active'>wznów</button>") +
        "<button class='tr-btn sm bad' data-gd='" + g.id + "'>usuń</button></div><div class='tr-gst' id='gst-" + g.id + "' style='grid-column:2/4'></div>" + (editId === g.id ? "<div id='trg-f' style='grid-column:1/-1'></div>" : "") + "</div>";
    });
    h += "</div><div class='tr-note'><b>Jak trener używa celów:</b> wyprawa lub długa jazda z datą ustawia szczyt formy w Sezonie (budowa → taper → wyprawa → regeneracja). Priorytet A = szczyt formy, B = trening „po drodze”.</div>";
    body.innerHTML = h;
    document.getElementById("trg-add").onclick = function () { rGoals(editId === "new" ? null : "new"); };
    body.querySelectorAll("[data-ge]").forEach(function (b) { b.onclick = function () { var id = +b.dataset.ge; rGoals(editId === id ? null : id); }; });
    body.querySelectorAll("[data-gs]").forEach(function (b) { b.onclick = function () { api("PUT", "/goals/" + b.dataset.gs, { status: b.dataset.v }).then(function () { return loadGoals(); }).then(function () { rGoals(); toast("Zapisano"); }).catch(fail); }; });
    body.querySelectorAll("[data-gd]").forEach(function (b) { b.onclick = function () { var g = S.goals.filter(function (x) { return x.id === +b.dataset.gd; })[0]; if (!confirm("Usunąć cel „" + (g ? g.name : "") + "”? Tego nie da się cofnąć.")) return; api("DELETE", "/goals/" + b.dataset.gd).then(loadGoals).then(function () { rGoals(); toast("Usunięto"); }).catch(fail); }; });
    var f = document.getElementById("trg-f"); if (f) goalForm(f, editId === "new" ? null : S.goals.filter(function (x) { return x.id === editId; })[0]);
    if (S.goals.length) api("GET", "/goals/status").then(function (st) {
      Object.keys(st).forEach(function (id) {
        var el = document.getElementById("gst-" + id), v = st[id]; if (!el || !v) return;
        var L = { g: ["🟢", "var(--good)"], y: ["🟡", "var(--warn)"], r: ["🔴", "var(--bad)"], n: ["⚪", "var(--muted)"] }[v.level] || ["⚪", "var(--muted)"];
        var h = "<div style='margin-top:6px;font-size:12.5px'><b style='color:" + L[1] + "'>" + L[0] + " " + esc(v.text || "") + "</b></div>";
        if (v.progress != null) h += "<div style='height:8px;border-radius:5px;background:var(--line);overflow:hidden;margin:4px 0'><i style='display:block;height:100%;width:" + Math.round(v.progress * 100) + "%;background:" + L[1] + "'></i></div>";
        (v.rows || []).forEach(function (r) {
          var ratio = (r.need && typeof r.have === "number") ? Math.max(0, Math.min(1, r.have / r.need)) : null;
          h += "<div style='display:grid;grid-template-columns:150px 1fr 130px;gap:2px 8px;align-items:center;font-size:12px;margin-top:3px'><span>" + esc(r.k) + "</span>" +
            (ratio != null ? "<div style='height:7px;border-radius:4px;background:var(--line);overflow:hidden'><i style='display:block;height:100%;width:" + Math.round(ratio * 100) + "%;background:" + (ratio >= 1 ? "var(--good)" : (ratio >= 0.5 ? "var(--warn)" : "var(--bad)")) + "'></i></div>" : "<span></span>") +
            "<b style='text-align:right'>" + esc(r.have) + (r.need != null ? " / " + esc(r.need) : "") + "</b>" + (r.note ? "<span style='grid-column:1/4;color:var(--muted);font-size:11px'>" + esc(r.note) + "</span>" : "") + "</div>";
        });
        el.innerHTML = h;
      });
    }).catch(function () {});
  }
  // ---------- edytor celu: inne pola dla kazdego rodzaju ----------
  var SURF = [["asfalt", "asfalt"], ["mieszana", "mieszana"], ["szuter", "szuter"], ["teren", "teren"]];
  var BAGS = [["bez", "bez bagażu"], ["lekki", "lekki bikepacking"], ["pelny", "pełny bikepacking"], ["sakwy", "sakwy"]];
  var PRI = [["A", "A — szczyt formy", "pod ten cel ustawiany jest szczyt formy (taper przed, regeneracja po)"], ["B", "B — ważny", "trening „po drodze”, bez osobnego szczytu"], ["C", "C — przy okazji", "tylko informacyjnie"]];
  function goalForm(el, g) {
    var d = g ? JSON.parse(JSON.stringify(g)) : { kind: "trip", name: "", priority: "B", date_from: "", date_to: "", target: {}, note: "" };
    d.target = d.target || {};
    if (!g && d.target.add_calendar == null) d.target.add_calendar = true;
    var pvT = null, lastPv = null;
    function loadRoutes(cb) {
      if (S.routes) return cb();
      fetch("/api/routes/ready", { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (j) { S.routes = (j.routes || []); cb(); }).catch(function () { S.routes = []; cb(); });
    }
    function T(k) { return d.target[k]; }
    function chips(key, opts, cur, attr) { return "<div class='tr-tog'>" + opts.map(function (o) { return "<button type='button' data-" + (attr || "tk") + "='" + key + "' data-v='" + o[0] + "' class='" + (String(cur) === String(o[0]) ? "on" : "") + "'>" + o[1] + "</button>"; }).join("") + "</div>"; }
    function num(key, unit, ph, w) { var v = T(key); return "<div class='tr-tt'><input class='tr-in' inputmode='decimal' data-n='" + key + "' value=\"" + esc(v == null ? "" : v) + "\" placeholder='" + (ph || "") + "' style='width:" + (w || 120) + "px'><span class='sub'>" + unit + "</span></div>"; }
    function row(label, html) { return "<span>" + label + "</span><div>" + html + "</div>"; }
    function nDays() { if (!d.date_from || !d.date_to) return null; var n = Math.round((D(d.date_to) - D(d.date_from)) / DAY) + 1; return n > 0 ? n : null; }
    function errors() {
      var e = [], today = iso(todayMs());
      if (!String(d.name || "").trim()) e.push("podaj nazwę");
      if (d.date_from && d.date_to && d.date_to < d.date_from) e.push("„do” jest przed „od”");
      if ((d.kind === "weight" || d.kind === "power") && !d.date_to) e.push("podaj termin „do kiedy”");
      if ((d.kind === "weight" || d.kind === "power") && d.date_to && d.date_to <= today) e.push("termin musi być w przyszłości");
      if (d.kind === "trip" && (!d.date_from || !d.date_to)) e.push("podaj termin od–do");
      if ((d.kind === "trip" || d.kind === "long_ride") && (d.date_to || d.date_from) && (d.date_to || d.date_from) < today) e.push("termin już minął — sprawdź rok");
      if (d.kind === "long_ride" && !d.date_from) e.push("podaj dzień jazdy");
      if (d.kind === "weight" && !T("weight_kg")) e.push("podaj wagę docelową");
      if (d.kind === "power" && !T("ftp_w") && !T("wkg")) e.push("podaj FTP albo W/kg");
      if (d.kind === "volume" && !T("km") && !T("h") && !T("sessions")) e.push("podaj wartość celu");
      if (d.kind === "volume" && (!d.date_from || !d.date_to)) e.push("wybierz okres");
      if (d.kind === "habit" && !T("per_week") && !T("km_week")) e.push("podaj ile w tygodniu");
      if (d.kind === "other" && !T("text")) e.push("opisz cel");
      return e;
    }
    function hint() {
      var n = nDays(), h = [];
      if (d.kind === "trip") {
        if (n) h.push("= " + n + " dni");
        if (n && T("km")) h.push("~" + Math.round(T("km") / n) + " km dziennie");
        if (n && T("up_m")) h.push("~" + Math.round(T("up_m") / n) + " m w górę dziennie");
      }
      if (d.kind === "long_ride" && T("km") && T("target_h")) h.push("średnio " + (T("km") / T("target_h")).toFixed(1) + " km/h");
      if (d.kind === "volume" && d.date_from && d.date_to) {
        var w = Math.max(1, (D(d.date_to) - D(d.date_from) + DAY) / WK);
        ["km", "h", "sessions"].forEach(function (k) { if (T(k)) h.push("= ~" + (T(k) / w).toFixed(k === "km" ? 0 : 1) + (k === "km" ? " km" : (k === "h" ? " h" : " sesji")) + " / tydz."); });
      }
      if (d.kind === "weight" && lastPv && lastPv.now && lastPv.now.weight_kg && T("weight_kg") && d.date_to) {
        var wk = (D(d.date_to) - todayMs()) / WK; if (wk > 0) h.push("teraz " + lastPv.now.weight_kg + " kg → potrzeba " + ((T("weight_kg") - lastPv.now.weight_kg) / wk).toFixed(2) + " kg/tydz.");
      }
      if (d.kind === "power" && lastPv && lastPv.now && lastPv.now.ftp_w) {
        var tgt = T("ftp_w") || (T("wkg") && lastPv.now.weight_kg ? Math.round(T("wkg") * lastPv.now.weight_kg) : null);
        h.push("teraz " + lastPv.now.ftp_w + " W" + (tgt ? " → cel " + tgt + " W (+" + (tgt - lastPv.now.ftp_w) + " W)" : ""));
      }
      return h.join(" · ");
    }
    function body_() {
      var k = d.kind, h = "";
      if (k === "trip") {
        h += row("Termin", "<div class='tr-tt'>od <input type='date' data-f='date_from' value='" + esc(d.date_from || "") + "'> do <input type='date' data-f='date_to' value='" + esc(d.date_to || "") + "'></div>");
        h += row("Trasa z QBota", "<div id='trg-route'>" + routeSel() + "</div><div class='sub' style='margin-top:3px'>wybór trasy wypełnia km, przewyższenie i nawierzchnię; możesz je poprawić ręcznie</div>");
        h += row("Dystans", num("km", "km", "np. 790")) + row("Przewyższenie", num("up_m", "m", "np. 15300"));
        h += row("Nawierzchnia", chips("surface", SURF, T("surface"))) + row("Bagaż", chips("bags", BAGS, T("bags")));
        h += row("Kalendarz", chips("add_calendar", [[true, "dodaj do Kalendarza"], [false, "nie dodawaj"]], T("add_calendar") !== false));
      } else if (k === "long_ride") {
        h += row("Dzień", "<div class='tr-tt'><input type='date' data-f='date_from' value='" + esc(d.date_from || "") + "'> start <input type='time' data-t='start_time' value='" + esc(T("start_time") || "") + "'></div>");
        h += row("Trasa z QBota", "<div id='trg-route'>" + routeSel() + "</div>");
        h += row("Dystans", num("km", "km", "np. 200")) + row("Przewyższenie", num("up_m", "m", "np. 1500"));
        h += row("Nawierzchnia", chips("surface", SURF, T("surface"))) + row("Docelowy czas jazdy", num("target_h", "h (opcjonalnie)", "np. 9"));
        h += row("Kalendarz", chips("add_calendar", [[true, "dodaj do Kalendarza"], [false, "nie dodawaj"]], T("add_calendar") !== false));
      } else if (k === "volume") {
        var y = (todayMs() >= firstWorkday(new Date().getFullYear())) ? new Date().getFullYear() + 1 : new Date().getFullYear(), per = T("period") || "";
        h += row("Okres", chips("period", [["sez" + y, "sezon " + y + " (bieżący)"], ["sez" + (y + 1), "sezon " + (y + 1)], ["year" + (y + 1), "rok kalendarzowy " + (y + 1)], ["season" + (y + 1), "jazda IV–IX " + (y + 1)], ["custom", "własny"]], per, "per") + (per === "custom" ? "<div class='tr-tt' style='margin-top:6px'>od <input type='date' data-f='date_from' value='" + esc(d.date_from || "") + "'> do <input type='date' data-f='date_to' value='" + esc(d.date_to || "") + "'></div>" : (d.date_from ? "<div class='sub' style='margin-top:3px'>" + d.date_from + " – " + d.date_to + "</div>" : "")));
        var sp = T("sport") || "rower";
        h += row("Aktywność", chips("sport", ACT.map(function (a) { return [a[0], a[1] + " " + a[2]]; }), sp, "sp"));
        var ms = sp === "rower" ? [["km", "km"], ["h", "godziny"]] : (sp === "wiosl" ? [["h", "godziny"], ["sessions", "sesje"]] : [["sessions", "sesje"], ["h", "godziny"]]);
        var m = T("metric") || ms[0][0];
        h += row("Miara", chips("metric", ms, m, "met")) + row("Cel", num(m, m === "km" ? "km" : (m === "h" ? "h" : "sesji"), m === "km" ? "np. 10000" : "np. 100"));
      } else if (k === "weight") {
        h += row("Do kiedy", "<input type='date' data-f='date_to' value='" + esc(d.date_to || "") + "'>") + row("Waga docelowa", num("weight_kg", "kg", "np. 90"));
      } else if (k === "power") {
        var pm = T("wkg") != null && T("ftp_w") == null ? "wkg" : "ftp";
        h += row("Do kiedy", "<input type='date' data-f='date_to' value='" + esc(d.date_to || "") + "'>") + row("Miara", chips("pmode", [["ftp", "FTP (W)"], ["wkg", "W/kg"]], pm, "pm"));
        h += row("Cel", pm === "wkg" ? num("wkg", "W/kg", "np. 3.0", 90) : num("ftp_w", "W", "np. 270"));
      } else if (k === "habit") {
        var hs = T("sport") || "sila";
        h += row("Aktywność", chips("sport", ACT.map(function (a) { return [a[0], a[1] + " " + a[2]]; }), hs, "sp"));
        if (hs === "rower") h += row("Miara", chips("hm", [["per_week", "razy / tydz."], ["km_week", "km / tydz."]], T("km_week") != null ? "km_week" : "per_week", "hm"));
        h += row("Ile", T("km_week") != null && hs === "rower" ? num("km_week", "km / tydz.", "np. 150") : num("per_week", "razy / tydz.", "np. 2", 80));
        if (hs === "joga") h += row("Jedna sesja", num("min", "min", "np. 20", 80));
        h += row("Od kiedy", "<div class='tr-tt'><input type='date' data-f='date_from' value='" + esc(d.date_from || "") + "'> do <input type='date' data-f='date_to' value='" + esc(d.date_to || "") + "'> <span class='sub'>(opcjonalnie)</span></div>");
      } else {
        h += row("Opis", "<input class='tr-in' data-t='text' value=\"" + esc(T("text") || "") + "\">") + row("Termin", "<input type='date' data-f='date_to' value='" + esc(d.date_to || "") + "'> <span class='sub'>(opcjonalnie)</span>");
      }
      return h;
    }
    function routeSel() {
      if (!S.routes) return "<span class='sub'>wczytuję trasy…</span>";
      if (!S.routes.length) return "<span class='sub'>brak policzonych tras</span>";
      return "<select data-route='1' style='max-width:420px'><option value=''>— bez trasy / wpiszę ręcznie —</option>" + S.routes.map(function (r) { return "<option value='" + esc(r.route_id) + "'" + (T("route_id") === r.route_id ? " selected" : "") + ">" + esc(r.name) + " · " + r.distance_km + " km</option>"; }).join("") + "</select>";
    }
    function preview() {
      clearTimeout(pvT);
      pvT = setTimeout(function () {
        var box = el.querySelector("#trg-pv"); if (!box) return;
        if (errors().length) { box.innerHTML = ""; return; }
        api("POST", "/goals/preview", payload()).then(function (v) {
          lastPv = v; var hb = el.querySelector("#trg-hint"); if (hb) hb.textContent = hint();
          var L = { g: ["🟢", "var(--good)"], y: ["🟡", "var(--warn)"], r: ["🔴", "var(--bad)"], n: ["⚪", "var(--muted)"] }[v.level] || ["⚪", "var(--muted)"];
          box.innerHTML = "<div class='tr-note' style='margin:8px 0 0'><b style='color:" + L[1] + "'>" + L[0] + " Ocena: " + esc(v.text || "") + "</b>" + (v.rows || []).filter(function (r) { return r.have != null || r.need != null; }).map(function (r) { return "<div class='sub' style='font-size:12px'>" + esc(r.k) + ": " + (r.have != null ? esc(r.have) : "—") + (r.need != null ? " / " + esc(r.need) : "") + (r.note ? " · " + esc(r.note) : "") + "</div>"; }).join("") + "</div>";
        }).catch(function () { box.innerHTML = ""; });
      }, 500);
    }
    function payload() {
      var t = JSON.parse(JSON.stringify(d.target));
      if (d.kind === "trip") { var n = nDays(); if (n) t.days = n; }
      var df = d.date_from || null, dt = d.date_to || null;
      if (d.kind === "long_ride") dt = df;
      if (d.kind === "weight" || d.kind === "power") df = null;
      return { kind: d.kind, name: d.name, priority: d.priority, date_from: df, date_to: dt, target: t, note: d.note || null };
    }
    function draw() {
      var aCount = S.goals.filter(function (x) { return x.priority === "A" && x.status === "active" && (!g || x.id !== g.id); }).length;
      var h = "<div class='tr-box'><div class='tr-form'>" +
        row("Rodzaj", "<div class='tr-tog'>" + KINDS.map(function (k) { return "<button type='button' data-k='" + k[0] + "' class='" + (d.kind === k[0] ? "on" : "") + "'>" + k[1] + " " + k[2] + "</button>"; }).join("") + "</div>") +
        row("Nazwa", "<input class='tr-in' data-f='name' value=\"" + esc(d.name) + "\" placeholder='np. Badlands, Waga 90 kg, 10 000 km'>") +
        row("Priorytet", "<div class='tr-tog'>" + PRI.map(function (p) { return "<button type='button' data-p='" + p[0] + "' class='" + (d.priority === p[0] ? "on" : "") + "' title='" + p[2] + "'>" + p[1] + "</button>"; }).join("") + "</div><div class='sub' style='margin-top:3px'>" + PRI.filter(function (p) { return p[0] === d.priority; })[0][2] + (d.priority === "A" && aCount >= 2 ? " · <b style='color:var(--warn)'>masz już " + aCount + " cele A — więcej szczytów formy w roku jest trudne</b>" : "") + "</div>") +
        body_() + row("Uwagi", "<input class='tr-in' data-f='note' value=\"" + esc(d.note || "") + "\">") + "</div>" +
        "<div id='trg-hint' class='sub' style='margin-top:8px;font-weight:600'>" + esc(hint()) + "</div>" +
        "<div id='trg-err' style='margin-top:4px;font-size:12px;color:var(--bad)'>" + errors().map(esc).join(" · ") + "</div><div id='trg-pv'></div>" +
        "<div style='margin-top:10px'><button class='tr-btn pri' data-x='save'" + (errors().length ? " disabled" : "") + ">Zapisz</button> <button class='tr-btn' data-x='cancel'>Anuluj</button></div></div>";
      el.innerHTML = h; wire(); preview();
    }
    function refresh() { var e = errors(); el.querySelector("#trg-err").innerHTML = e.map(esc).join(" · "); el.querySelector("[data-x=save]").disabled = !!e.length; el.querySelector("#trg-hint").textContent = hint(); preview(); }
    function wire() {
      el.querySelectorAll("[data-k]").forEach(function (b) { b.onclick = function () { if (d.kind === b.dataset.k) return; d.kind = b.dataset.k; d.target = { add_calendar: true }; d.date_from = ""; d.date_to = ""; lastPv = null; draw(); }; });
      el.querySelectorAll("[data-p]").forEach(function (b) { b.onclick = function () { d.priority = b.dataset.p; draw(); }; });
      el.querySelectorAll("[data-f]").forEach(function (i) { i.oninput = i.onchange = function () {
        d[i.dataset.f] = i.value;
        if (i.dataset.f === "date_from" && i.value) {
          var to = el.querySelector("[data-f=date_to]");
          if (to) { to.min = i.value; if (!to.value || to.value < i.value) { to.value = i.value; d.date_to = i.value; } }
        }
        refresh(); }; });
      var _fr = el.querySelector("[data-f=date_from]"), _to = el.querySelector("[data-f=date_to]");
      if (_fr && _to && _fr.value) _to.min = _fr.value;
      el.querySelectorAll("[data-t]").forEach(function (i) { i.oninput = i.onchange = function () { if (i.value === "") delete d.target[i.dataset.t]; else d.target[i.dataset.t] = i.value; refresh(); }; });
      el.querySelectorAll("[data-n]").forEach(function (i) { i.oninput = function () { var v = i.value.replace(",", ".").replace(/[^0-9.]/g, ""); if (v !== i.value.replace(",", ".")) i.value = v; if (v === "" || isNaN(+v)) delete d.target[i.dataset.n]; else d.target[i.dataset.n] = +v; refresh(); }; });
      el.querySelectorAll("[data-tk]").forEach(function (b) { b.onclick = function () { var v = b.dataset.v; d.target[b.dataset.tk] = v === "true" ? true : (v === "false" ? false : v); draw(); }; });
      el.querySelectorAll("[data-sp]").forEach(function (b) { b.onclick = function () { var keep = { add_calendar: d.target.add_calendar, period: d.target.period }; d.target = keep; d.target.sport = b.dataset.v; draw(); }; });
      el.querySelectorAll("[data-met]").forEach(function (b) { b.onclick = function () { ["km", "h", "sessions"].forEach(function (k) { delete d.target[k]; }); d.target.metric = b.dataset.v; draw(); }; });
      el.querySelectorAll("[data-pm]").forEach(function (b) { b.onclick = function () { if (b.dataset.v === "wkg") { delete d.target.ftp_w; d.target.wkg = d.target.wkg || null; } else { delete d.target.wkg; } draw(); }; });
      el.querySelectorAll("[data-hm]").forEach(function (b) { b.onclick = function () { if (b.dataset.v === "km_week") { delete d.target.per_week; d.target.km_week = d.target.km_week || null; } else { delete d.target.km_week; } draw(); }; });
      el.querySelectorAll("[data-per]").forEach(function (b) { b.onclick = function () {
        var v = b.dataset.v; d.target.period = v;
        if (v.indexOf("sez") === 0) { var ys = +v.slice(3); d.date_from = iso(firstWorkday(ys - 1)); d.date_to = iso(firstWorkday(ys) - DAY); }
        else if (v.indexOf("year") === 0) { var y = v.slice(4); d.date_from = y + "-01-01"; d.date_to = y + "-12-31"; }
        else if (v.indexOf("season") === 0) { var y2 = v.slice(6); d.date_from = y2 + "-04-01"; d.date_to = y2 + "-09-30"; }
        draw(); }; });
      var rs = el.querySelector("[data-route]");
      if (rs) rs.onchange = function () {
        var rid = rs.value; if (!rid) { delete d.target.route_id; refresh(); return; }
        d.target.route_id = rid;
        api("GET", "/route_summary?route_id=" + encodeURIComponent(rid)).then(function (r) {
          d.target.km = r.km; d.target.up_m = r.up_m; if (r.surface) d.target.surface = r.surface;
          if (!String(d.name || "").trim()) { var rr = S.routes.filter(function (x) { return x.route_id === rid; })[0]; if (rr) d.name = rr.name.replace(/^\[Q\]\s*/, "").split(" · ")[0]; }
          toast("Z trasy: " + r.km + " km, " + r.up_m + " m" + (r.surface ? ", " + r.surface : "")); draw();
        }).catch(fail);
      };
      el.querySelector("[data-x=cancel]").onclick = function () { rGoals(); };
      el.querySelector("[data-x=save]").onclick = function () {
        if (errors().length) return;
        var b = payload();
        (g ? api("PUT", "/goals/" + g.id, b) : api("POST", "/goals", b)).then(function (saved) {
          if ((d.kind === "trip" || d.kind === "long_ride") && d.target.add_calendar !== false && saved && saved.id) return api("POST", "/goals/" + saved.id + "/calendar", {}).catch(function () {});
        }).then(loadGoals).then(function () { rGoals(); toast("Zapisano cel"); }).catch(fail);
      };
    }
    draw();
    loadRoutes(function () { var r = el.querySelector("#trg-route"); if (r) { r.innerHTML = routeSel(); var rs = el.querySelector("[data-route]"); if (rs) wire(); } });
  }

  // ======================= DOSTĘPNOŚĆ =======================
  var ICONS = ["🚗", "⚽", "🏠", "💼", "🌅", "🛒", "📅", "🩺", "🧳", "🏫", "🛌", "🧒", "📌"];
  var TPL = {
    shop: { icon: "🛒", name: "Zakupy", kind: "busy", windows: [{ d: [0, 0, 0, 0, 0, 0, 0], k: "h", a: "15:00", b: "17:00", ac: [] }] },
    drive: { icon: "🚗", name: "Dowóz / odbiór", kind: "busy", windows: [{ d: [0, 0, 0, 0, 0, 0, 0], k: "h", a: "16:00", b: "17:00", ac: [] }] },
    meet: { icon: "📅", name: "Spotkanie stałe", kind: "busy", windows: [{ d: [0, 0, 0, 0, 0, 0, 0], k: "h", a: "10:00", b: "11:00", ac: [] }] },
    work: { icon: "🏠", name: "Praca z domu", kind: "flex", windows: [{ d: [1, 1, 1, 1, 1, 0, 0], k: "h", a: "08:00", b: "16:00", ac: [] }] },
    train: { icon: "🌅", name: "Okno treningu", kind: "pref", windows: [{ d: [1, 1, 1, 1, 1, 0, 0], k: "h", a: "12:00", b: "15:00", ac: ["rower"] }] }
  };
  function rAvail(editId, draft) {
    var h = "<div class='card'><div class='cardhead'><h2>Mój typowy tydzień</h2><span class='sub'>zajęte, elastyczne i okna treningu</span></div><div class='tr-gwrap'><div class='tr-grid' id='tra-grid'></div></div>" +
      "<div class='tr-lg'><span><i class='tr-sw' style='background:#b8433a'></i>zajęte</span><span><i class='tr-sw' style='background:rgba(214,168,60,.2);border:1.5px solid #d6a83c'></i>elastyczne</span><span><i class='tr-sw' style='border:1.5px dashed #c9544a'></i>zmienne (z Kalendarza)</span><span>okna:</span><span><i class='tr-sw a-rower'></i>rower</span><span><i class='tr-sw a-joga'></i>joga</span><span><i class='tr-sw a-wiosl'></i>wioślarz</span><span><i class='tr-sw a-sila'></i>siła</span></div></div>" +
      "<div class='card'><div class='cardhead'><h2>Wpisy tygodnia</h2><button class='tr-btn pri' id='tra-add'>＋ dodaj wpis</button></div>" +
      "<div class='tr-tpl'><span class='sub'>Szybko dodaj:</span>" + [["shop", "🛒 zakupy"], ["drive", "🚗 dowóz / odbiór"], ["meet", "📅 spotkanie stałe"], ["work", "🏠 praca z domu"], ["train", "🌅 okno treningu"]].map(function (t) { return "<button class='tr-btn sm' data-tpl='" + t[0] + "'>" + t[1] + "</button>"; }).join("") + "</div><div id='tra-list'></div></div>";
    body.innerHTML = h;
    drawGrid(document.getElementById("tra-grid"), draft && editId != null ? S.rules.map(function (r) { return r.id === editId ? draft : r; }).concat(editId === "new" ? [draft] : []) : S.rules);
    var list = document.getElementById("tra-list"), rows = S.rules.slice();
    if (editId === "new") rows.push(draft);
    if (!rows.length) list.innerHTML = "<div class='tr-empty'>Brak wpisów. Dodaj zajętości (np. dowóz dziecka, zakupy), pracę z domu i okna, w których najchętniej trenujesz.</div>";
    rows.forEach(function (r) {
      var isEd = (editId === "new" && r === draft) || (r.id != null && r.id === editId), rr = isEd ? draft : r;
      var m = [0, 0, 0, 0, 0, 0, 0]; (rr.windows || []).forEach(function (w) { w.d.forEach(function (v, i) { if (v === 1 || (v === 2 && !m[i])) m[i] = v; }); });
      var el = document.createElement("div"); el.className = "tr-rule";
      el.innerHTML = "<span class='ic'>" + esc(rr.icon) + "</span><div><div class='t'>" + esc(rr.name) + " <span class='sub'>· " + TY[rr.kind] + (rr.kind === "flex" && rr.max_min ? ", maks. " + rr.max_min + "′" : "") + "</span></div><div class='m'>" + (rr.windows || []).map(winTxt).join("<br>") + "<br>" + perTxt(rr.period) + (rr.note ? " · " + esc(rr.note) : "") + "</div></div>" +
        (r.id != null ? "<button class='tr-btn sm' data-re='" + r.id + "'>" + (isEd ? "zamknij" : "edytuj") + "</button>" : "<span></span>") +
        "<div class='wk'>" + m.map(function (v, i) { return "<span class='" + (v ? rr.kind : "") + (v === 2 ? " q" : "") + "'>" + DN[i] + (v === 2 ? "?" : "") + "</span>"; }).join("") + "</div>" + (isEd ? "<div class='ed'></div>" : "");
      list.appendChild(el);
      if (isEd) ruleForm(el.querySelector(".ed"), editId, draft);
    });
    document.getElementById("tra-add").onclick = function () { rAvail("new", { icon: "📌", name: "Nowy wpis", kind: "busy", windows: [{ d: [0, 0, 0, 0, 0, 0, 0], k: "h", a: "17:00", b: "19:00", ac: [] }], period: { m: "all" }, max_min: null, note: "" }); };
    body.querySelectorAll("[data-tpl]").forEach(function (b) { b.onclick = function () { var t = JSON.parse(JSON.stringify(TPL[b.dataset.tpl])); t.period = { m: "all" }; t.note = ""; t.max_min = t.kind === "flex" ? 90 : null; rAvail("new", t); }; });
    body.querySelectorAll("[data-re]").forEach(function (b) { b.onclick = function () { var id = +b.dataset.re; if (editId === id) rAvail(); else rAvail(id, JSON.parse(JSON.stringify(S.rules.filter(function (x) { return x.id === id; })[0]))); }; });
  }
  function drawGrid(g, rules) {
    var H0 = 360, H1 = 1320, SP = H1 - H0, h = "<div class='tr-grow tr-ghead'><span class='gd'></span><div class='tr-gtr'>";
    for (var x = 6; x <= 22; x += 2) h += "<span class='tr-gh' style='left:" + ((x * 60 - H0) / SP * 100) + "%;transform:translateX(" + (x === 6 ? "0" : (x === 22 ? "-100%" : "-50%")) + ")'>" + x + ":00</span>";
    h += "</div></div>";
    for (var d = 0; d < 7; d++) {
      h += "<div class='tr-grow'><span class='gd'>" + DN[d] + "</span><div class='tr-gtr'>";
      for (var y = 8; y < 22; y += 2) h += "<span class='tr-gl' style='left:" + ((y * 60 - H0) / SP * 100) + "%'></span>";
      rules.forEach(function (r) {
        if (r.active === false) return;
        (r.windows || []).forEach(function (w) {
          var v = w.d[d]; if (!v) return;
          var A = H0, B = H1; if (w.k === "h") { A = tm(w.a); B = tm(w.b); if (A == null || B == null) return; A = Math.max(H0, Math.min(H1, A)); B = Math.max(H0, Math.min(H1, B)); }
          var wd = (B - A) / SP * 100, st = "left:" + ((A - H0) / SP * 100) + "%;width:" + Math.max(0.8, wd) + "%", cl, lab, tt = (w.k === "h" ? (" " + w.a + "–" + w.b) : (w.k === "all" ? " cały dzień" : " godz. zmienne"));
          if (r.kind === "pref") { var ac = w.ac || []; cl = "lo pref " + (ac.length === 1 ? ("a-" + ac[0]) : "a-all"); lab = ac.length === 1 ? (AIC[ac[0]] + " " + ANM[ac[0]]) : (ac.length ? ac.map(function (k) { return AIC[k]; }).join("") : "✳ wszystkie"); }
          else { cl = "hi " + (w.k === "var" ? "var" : r.kind); lab = r.icon + " " + r.name + (w.k === "var" ? " ?" : ""); }
          var full = wd >= 14 ? (esc(lab) + "<span class='gt'>" + tt + "</span>") : (wd >= 6 ? esc(lab) : esc(lab.split(" ")[0]));
          h += "<span class='tr-gb " + cl + (v === 2 ? " q" : "") + "' style='" + st + "' title='" + esc(r.name + " · " + winTxt(w)) + "'>" + full + "</span>";
        });
      });
      h += "</div></div>";
    }
    g.innerHTML = h;
  }
  function ruleForm(el, editId, dr) {
    function re() { rAvail(editId, dr); }
    var h = "<div class='tr-box'><div class='tr-form'>";
    h += "<span>Ikona</span><div class='tr-tog'>" + ICONS.map(function (ic) { return "<button data-ic='" + ic + "' class='" + (ic === dr.icon ? "on" : "") + "'>" + ic + "</button>"; }).join("") + "</div>";
    h += "<span>Nazwa</span><input class='tr-in' data-f='name' value=\"" + esc(dr.name) + "\">";
    h += "<span>Rodzaj</span><div class='tr-tog'>" + Object.keys(TY).map(function (k) { return "<button data-ty='" + k + "' class='" + (k === dr.kind ? "on" : "") + "'>" + TY[k] + "</button>"; }).join("") + "</div>";
    h += "<span>Kiedy</span><div>";
    dr.windows.forEach(function (w, wi) {
      h += "<div class='tr-win'><div class='tr-tog'>" + w.d.map(function (v, i) { return "<button data-w='" + wi + "' data-d='" + i + "' class='" + (v === 1 ? "on" : (v === 2 ? "q" : "")) + "' style='min-width:38px'>" + DN[i] + (v === 2 ? "?" : "") + "</button>"; }).join("") + "</div>";
      h += "<div class='tr-tog'>" + [["h", "godziny"], ["all", "cały dzień"], ["var", "zmienne (z Kalendarza)"]].map(function (o) { return "<button data-wk='" + wi + "' data-k='" + o[0] + "' class='" + (w.k === o[0] ? "on" : "") + "'>" + o[1] + "</button>"; }).join("") + "</div>";
      if (dr.kind !== "busy") { var ac = w.ac || []; h += "<div class='tr-tog'><span class='sub' style='align-self:center;margin-right:4px'>Dla:</span><button data-wall='" + wi + "' class='" + (ac.length ? "" : "on") + "'>wszystkie</button>" + ACT.map(function (x) { return "<button data-wac='" + wi + "' data-a='" + x[0] + "' class='" + (ac.indexOf(x[0]) >= 0 ? "on" : "") + "'>" + x[1] + " " + x[2] + "</button>"; }).join("") + "</div>"; }
      if (w.k === "h") h += "<div class='tr-tt'>od <input type='time' data-wa='" + wi + "' value='" + esc(w.a) + "'> do <input type='time' data-wb='" + wi + "' value='" + esc(w.b) + "'></div>";
      if (dr.windows.length > 1) h += "<button class='tr-btn sm' data-xw='" + wi + "' style='align-self:flex-start'>× usuń okno</button>";
      h += "</div>";
    });
    h += "<button class='tr-btn sm' data-x='addw'>＋ dodaj okno (inne dni / godziny)</button><div class='sub' style='margin-top:4px'>Dni: klik = tak → czasem (?) → nie.</div></div>";
    if (dr.kind === "flex") h += "<span>Maks. trening w przerwie</span><div class='tr-tt'><input type='range' min='30' max='180' step='15' value='" + (dr.max_min || 90) + "' data-mx='1' style='width:200px'> <b id='tra-mx'>" + (dr.max_min || 90) + "′</b></div>";
    var p = dr.period || { m: "all" };
    h += "<span>Obowiązuje</span><div><div class='tr-tog'>" + [["all", "cały rok"], ["yearly", "co roku w okresie"], ["once", "jednorazowo"]].map(function (o) { return "<button data-pm='" + o[0] + "' class='" + (p.m === o[0] ? "on" : "") + "'>" + o[1] + "</button>"; }).join("") + "</div>";
    if (p.m === "yearly") h += "<div class='tr-tt' style='margin-top:6px'>od <input class='tr-in' style='width:70px' data-pf='1' placeholder='dd.mm' value='" + esc(p.f || "") + "'> do <input class='tr-in' style='width:70px' data-pt='1' placeholder='dd.mm' value='" + esc(p.t || "") + "'> <span class='sub'>np. rok szkolny 01.09–26.06</span></div>";
    if (p.m === "once") h += "<div class='tr-tt' style='margin-top:6px'>od <input type='date' data-pf='1' value='" + esc(p.f || "") + "'> do <input type='date' data-pt='1' value='" + esc(p.t || "") + "'></div>";
    h += "</div><span>Uwagi</span><input class='tr-in' data-f='note' value=\"" + esc(dr.note || "") + "\"></div>";
    h += "<div style='margin-top:10px'><button class='tr-btn pri' data-x='save'>Zapisz</button> <button class='tr-btn' data-x='cancel'>Anuluj</button>" + (editId !== "new" ? " <button class='tr-btn bad' data-x='del'>Usuń wpis</button>" : "") + "</div></div>";
    el.innerHTML = h;
    el.querySelectorAll("[data-ic]").forEach(function (b) { b.onclick = function () { dr.icon = b.dataset.ic; re(); }; });
    el.querySelectorAll("[data-ty]").forEach(function (b) { b.onclick = function () { dr.kind = b.dataset.ty; if (dr.kind === "busy") dr.windows.forEach(function (w) { w.ac = []; }); if (dr.kind === "flex" && !dr.max_min) dr.max_min = 90; re(); }; });
    el.querySelectorAll("[data-f]").forEach(function (i) { i.oninput = function () { dr[i.dataset.f] = i.value; }; });
    el.querySelectorAll("[data-d]").forEach(function (b) { b.onclick = function () { var w = dr.windows[+b.dataset.w], i = +b.dataset.d; w.d[i] = (w.d[i] + 1) % 3; re(); }; });
    el.querySelectorAll("[data-wk]").forEach(function (b) { b.onclick = function () { var w = dr.windows[+b.dataset.wk]; w.k = b.dataset.k; if (w.k === "h" && !w.a) { w.a = "12:00"; w.b = "14:00"; } re(); }; });
    el.querySelectorAll("[data-wall]").forEach(function (b) { b.onclick = function () { dr.windows[+b.dataset.wall].ac = []; re(); }; });
    el.querySelectorAll("[data-wac]").forEach(function (b) { b.onclick = function () { var w = dr.windows[+b.dataset.wac]; w.ac = w.ac || []; var k = w.ac.indexOf(b.dataset.a); if (k >= 0) w.ac.splice(k, 1); else w.ac.push(b.dataset.a); if (w.ac.length === 4) w.ac = []; re(); }; });
    el.querySelectorAll("[data-wa]").forEach(function (i) { i.onchange = function () { dr.windows[+i.dataset.wa].a = i.value; re(); }; });
    el.querySelectorAll("[data-wb]").forEach(function (i) { i.onchange = function () { dr.windows[+i.dataset.wb].b = i.value; re(); }; });
    el.querySelectorAll("[data-xw]").forEach(function (b) { b.onclick = function () { dr.windows.splice(+b.dataset.xw, 1); re(); }; });
    el.querySelector("[data-x=addw]").onclick = function () { dr.windows.push({ d: [0, 0, 0, 0, 0, 0, 0], k: "h", a: "12:00", b: "14:00", ac: [] }); re(); };
    var mx = el.querySelector("[data-mx]"); if (mx) mx.oninput = function () { dr.max_min = +mx.value; document.getElementById("tra-mx").textContent = mx.value + "′"; };
    el.querySelectorAll("[data-pm]").forEach(function (b) { b.onclick = function () { dr.period = { m: b.dataset.pm }; re(); }; });
    var pf = el.querySelector("[data-pf]"), pt = el.querySelector("[data-pt]");
    if (pf) pf.oninput = pf.onchange = function () { dr.period.f = pf.value; if (pt && pf.type === "date" && pf.value) { pt.min = pf.value; if (!pt.value || pt.value < pf.value) { pt.value = pf.value; dr.period.t = pf.value; } } };
    if (pt) pt.oninput = pt.onchange = function () { dr.period.t = pt.value; };
    if (pf && pt && pf.type === "date" && pf.value) pt.min = pf.value;
    el.querySelector("[data-x=cancel]").onclick = function () { rAvail(); };
    var del = el.querySelector("[data-x=del]");
    if (del) del.onclick = function () { if (!confirm("Usunąć wpis „" + dr.name + "”?")) return; api("DELETE", "/rules/" + editId).then(loadRules).then(function () { rAvail(); toast("Usunięto"); }).catch(fail); };
    el.querySelector("[data-x=save]").onclick = function () {
      var b = { icon: dr.icon, name: dr.name, kind: dr.kind, windows: dr.windows, period: dr.period || { m: "all" }, max_min: dr.kind === "flex" ? (dr.max_min || 90) : null, note: dr.note || null };
      (editId === "new" ? api("POST", "/rules", b) : api("PUT", "/rules/" + editId, b)).then(loadRules).then(function () { rAvail(); toast("Zapisano wpis"); }).catch(fail);
    };
  }

  // ======================= USTAWIENIA (nadpisania) =======================
  var saveQ = {}, saveT = null;
  function ovGet(k, def) { return Object.prototype.hasOwnProperty.call(S.ov, k) ? S.ov[k] : def; }
  function ovSet(k, v) { if (v === null) delete S.ov[k]; else S.ov[k] = v; saveQ[k] = v; clearTimeout(saveT); saveT = setTimeout(flush, 500); }
  function flush() { var q = saveQ; saveQ = {}; if (!Object.keys(q).length) return; api("POST", "/settings", { overrides: q }).then(function (j) { S.ov = j.overrides || {}; toast("Zapisano ustawienia"); }).catch(fail); }

  // ======================= SEZON (z serwera: /season) =======================
  var PH = { bz: ["Baza + siła", "#3f7fd0"], bd: ["Budowa", "#8a63d2"], tp: ["Taper", "#2aa198"], ev: ["Wyprawa", "#c9544a"], rg: ["Regeneracja", "#7f9c6b"], sz: ["Sezon — jazda", "#4f9d3a"], rt: ["Roztrenowanie", "#d99a2b"], lz: ["Totalny luz", "#9aa0a6"] };
  var PTXT = { bz: "siła 2–3× (obwód), wioślarz wg Mixu, długi las w weekend spokojnie", bd: "podjazdy, siła nóg, długa jazda, weekend sb+nd pod rząd", tp: "objętość −40%, krótkie akcenty, sprzęt i bagaż", ev: "wyprawa", rg: "luźno, joga 30–45′", sz: "jazda sezonowa, siła 1× podtrzymanie", rt: "wspomaganie zakończenia sezonu: spokojny rower, start siły, joga", lz: "totalny luz — bez planu, bez przypomnień" };
  var szSel = -1, SZ = null;
  function firstWorkday(prevYear) { var d = Date.UTC(prevYear, 11, 27); while ([0, 6].indexOf(new Date(d).getUTCDay()) >= 0) d += DAY; return d; }
  function rSeason() {
    body.innerHTML = "<div class='tr-empty'>Liczę sezon…</div>";
    api("GET", "/season").then(function (j) { SZ = j; drawSeason(); }).catch(function (e) { body.innerHTML = "<div class='tr-empty'>Błąd: " + esc(e.message) + "</div>"; });
  }
  function drawSeason() {
    var j = SZ, W = j.weeks, NW = W.length, mx = 35, T0 = todayMs();
    var h = "<div class='card'><div class='cardhead'><h2>Sezon · tydzień po tygodniu</h2><span class='sub'>sezon = od startu bazy (po świętach) do końca totalnego luzu</span></div><div class='tr-szwrap'>";
    h += "<div class='tr-szm' style='grid-template-columns:repeat(" + NW + ",1fr)'>" + W.map(function (w, i) { return "<span style='font-weight:700;color:var(--ink)'>" + (i === 0 || W[i - 1].season !== w.season ? "▸ " + w.season : "") + "</span>"; }).join("") + "</div>";
    h += "<div class='tr-szg' style='grid-template-columns:repeat(" + NW + ",1fr)'>";
    W.forEach(function (w, i) { var cur = T0 >= D(w.s) && T0 < D(w.s) + WK; h += "<div class='tr-szc" + (szSel === i ? " sel" : "") + (cur ? " now" : "") + "' data-w='" + i + "' title='" + pl(D(w.s)) + " · sezon " + w.season + " · " + esc(w.name) + " · " + w.h + " h" + (w.lt ? " · lżejszy" : "") + "'><span class='tr-sze'>" + w.ev.map(function (e) { return KIC2[e.kind] || ""; }).join("") + "</span><div class='tr-szb'><i style='height:" + (w.ph === "lz" ? 3 : Math.max(4, w.h / mx * 100)) + "%;background:" + PH[w.ph][1] + (w.lt ? ";opacity:.55" : "") + "'></i></div></div>"; });
    h += "</div><div class='tr-szm' style='grid-template-columns:repeat(" + NW + ",1fr)'>"; var lm = -1;
    W.forEach(function (w) { var m = new Date(D(w.s)).getUTCMonth(); h += "<span>" + (m !== lm ? MN[m] : "") + "</span>"; lm = m; });
    h += "</div></div><div class='tr-lg'>" + Object.keys(PH).map(function (p) { return "<span><i class='tr-sw' style='background:" + PH[p][1] + "'></i>" + PH[p][0] + "</span>"; }).join("") + "<span style='color:var(--muted)'>jaśniejszy = tydzień lżejszy · wysokość = godziny</span></div><div id='trs-det' style='margin-top:10px'></div></div>";
    // plan km z celow objetosci
    (j.volume || []).forEach(function (v) {
      var mxv = Math.max.apply(null, v.plan.map(function (p) { return p.value; }).concat([1])), u = v.unit === "km" ? "km" : (v.unit === "h" ? "h" : "sesji");
      h += "<div class='card'><div class='cardhead'><h2>📏 " + esc(v.name) + " — plan na miesiące</h2><span class='sub'>wg Twojego rytmu roku (2 lata jazd)</span></div><div style='display:grid;grid-template-columns:repeat(" + v.plan.length + ",1fr);gap:4px;align-items:end;height:120px'>" +
        v.plan.map(function (p) { return "<div style='display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;font-size:10.5px;color:var(--muted)'><b style='color:var(--ink)'>" + p.value + "</b><i style='display:block;width:60%;height:" + Math.round(p.value / mxv * 85) + "%;background:var(--accent);border-radius:3px 3px 0 0'></i><span>" + MN[+p.month.slice(5) - 1] + "</span></div>"; }).join("") + "</div><div class='sub' style='margin-top:4px'>" + u + " na miesiąc · z tego wynika minimalny budżet godzin w tygodniu w planie</div></div>";
    });
    // ustawienia sezonow
    var KEYS = [["start", "Start sezonu (baza)", "pierwszy dzień roboczy po świętach"], ["bz_end", "Koniec bazy", "auto: 10 tyg. przed pierwszą wyprawą A (albo koniec lutego)"], ["roz", "Start roztrenowania", "auto: 1.10 albo po regeneracji ostatniej A"], ["luz", "Start totalnego luzu", "auto: 12.12"]];
    h += "<div class='card'><div class='cardhead'><h2>Ustawienia sezonów</h2><span class='sub'>puste = auto · zmiana przelicza plan</span></div>";
    j.seasons.forEach(function (sb) {
      h += "<div class='tr-box' style='margin-top:8px'><b>Sezon " + sb.year + "</b> <span class='sub'>" + pl(D(sb.start)) + "." + sb.start.slice(0, 4) + " – " + pl(D(sb.end)) + "." + sb.end.slice(0, 4) + (sb.a_goals && sb.a_goals.length ? " · wyprawy A: " + sb.a_goals.map(esc).join(", ") : " · bez wyprawy A") + "</span><div class='tr-form' style='margin-top:6px'>";
      KEYS.forEach(function (k) {
        var key = "season." + sb.year + "." + k[0], auto = sb.auto[k[0]];
        h += "<span>" + k[1] + "</span><div class='tr-tt'><input type='date' data-sk2='" + key + "' value='" + sb[k[0]] + "'> " + (auto ? "<span class='sub'>auto — " + k[2] + "</span>" : "<button class='tr-btn sm' data-sr='" + key + "'>↺ auto</button>") + "</div>";
      });
      h += "</div></div>";
    });
    h += "</div><div class='card'><div class='cardhead'><h2>Zasady budowania sezonu</h2></div><div id='trs-par'></div></div>";
    body.innerHTML = h;
    var det = document.getElementById("trs-det");
    if (szSel >= 0 && W[szSel]) {
      var w = W[szSel];
      det.innerHTML = "<div class='tr-box'><b>Tydzień " + pl(D(w.s)) + "–" + pl(D(w.s) + 6 * DAY) + "</b> · sezon " + w.season + " · " + esc(w.name) + (w.lt ? " · lżejszy" : "") + (w.pre ? " · przed wyprawą B — lżej" : "") + "<br>Plan: ~" + w.h + " h" + (w.ev.length ? " · " + w.ev.map(function (e) { return (KIC2[e.kind] || "") + " " + esc(e.name); }).join(", ") : "") + "<div class='sub' style='margin-top:4px'>" + PTXT[w.ph] + "</div><button class='tr-btn sm' id='trs-x' style='margin-top:6px'>× zamknij</button></div>";
      document.getElementById("trs-x").onclick = function () { szSel = -1; drawSeason(); };
    } else {
      var phs = [], prev = null; W.forEach(function (w) { var key = w.ph + "|" + w.season; if (key !== prev) { phs.push({ ph: w.ph, y: w.season, a: D(w.s), n: 0, h: 0 }); prev = key; } var p = phs[phs.length - 1]; p.n++; p.h += w.h; p.b = D(w.s) + 6 * DAY; });
      det.innerHTML = phs.map(function (p) { return "<div class='tr-phr'><span class='tr-dot' style='background:" + PH[p.ph][1] + "'></span><span><b>" + PH[p.ph][0] + "</b> · sezon " + p.y + " · " + pl(p.a) + "–" + pl(p.b) + " · " + p.n + " tydz." + (p.ph === "lz" ? "" : " · śr. " + (p.h / p.n).toFixed(1) + " h/tydz.") + "</span></div>"; }).join("");
    }
    body.querySelectorAll(".tr-szc").forEach(function (el) { el.onclick = function () { szSel = +el.dataset.w; drawSeason(); }; });
    function save(key, val) { var o = {}; o[key] = val; api("POST", "/settings", { overrides: o }).then(function (r) { S.ov = r.overrides || {}; toast("Zapisano — sezon przeliczony"); rSeason(); }).catch(fail); }
    body.querySelectorAll("[data-sk2]").forEach(function (i) { i.onchange = function () { if (i.value) save(i.dataset.sk2, i.value); }; });
    body.querySelectorAll("[data-sr]").forEach(function (b) { b.onclick = function () { save(b.dataset.sr, null); }; });
    var par = document.getElementById("trs-par");
    par.innerHTML = [["season.taper_w", "Taper przed wyprawą A", 1, 3, 2, " tydz."], ["season.regen_w", "Regeneracja po wyprawie A", 1, 3, 2, " tydz."], ["season.light_every_w", "Tydzień lżejszy co", 3, 5, 4, " tydz."], ["season.volume", "Ogólna objętość", 1, 9, 5, ""]].map(function (x) { return sliderHTML({ k: x[0], n: x[1], min: x[2], max: x[3], st: 1, def: x[4], u: x[5] }); }).join("");
    par.querySelectorAll("[data-sk]").forEach(function (i) { i.onchange = function () { save(i.dataset.sk, +i.value); }; });
    par.querySelectorAll("[data-rs]").forEach(function (b) { b.onclick = function () { save(b.dataset.rs, null); }; });
  }

  // ======================= KALIBRACJA =======================
  function fmt(x, v) { if (x.lab) return x.lab[v - x.min]; var d = (x.st < 1) ? (x.st < 0.1 ? 2 : 1) : 0; return (+v).toFixed(d) + (x.u || ""); }
  function autoOf(x) { var a = S.auto && S.auto[x.k]; return a && a.value != null ? { v: a.value, why: a.note, live: true } : { v: x.def, why: x.why || "", live: false }; }
  function sliderHTML(x) {
    var A = autoOf(x), has = Object.prototype.hasOwnProperty.call(S.ov, x.k), v = has ? S.ov[x.k] : A.v;
    if (x.tog) return "<div class='tr-sl" + (has ? " chg" : "") + "'><span class='n'>" + x.n + "</span><span class='val'>" + (has ? "<span class='rs' data-rs='" + x.k + "'>auto ↺</span>" : "<span class='au'>" + (A.live ? "auto" : "domyślne") + "</span>") + "</span><div class='tr-tog'>" + x.tog.map(function (o, i) { return "<button data-tk='" + x.k + "' data-i='" + i + "' class='" + (i === v ? "on" : "") + "'>" + o + "</button>"; }).join("") + "</div>" + (A.why ? "<div class='why'>ⓘ " + esc(A.why) + "</div>" : "") + "</div>";
    return "<div class='tr-sl" + (has ? " chg" : "") + "'><span class='n'>" + x.n + "</span><span class='val'>" + fmt(x, v) + (has ? " <span class='au rs' data-rs='" + x.k + "'>auto " + fmt(x, A.v) + " ↺</span>" : " <span class='au'>" + (A.live ? "auto" : "domyślne") + "</span>") + "</span><input type='range' data-sk='" + x.k + "' min='" + x.min + "' max='" + x.max + "' step='" + x.st + "' value='" + v + "'><div class='ends'><span>" + (x.l ? x.l[0] : (x.lab ? x.lab[0] : fmt(x, x.min))) + "</span><span>" + (x.l ? x.l[1] : (x.lab ? x.lab[x.lab.length - 1] : fmt(x, x.max))) + "</span></div>" + (A.why ? "<div class='why'>ⓘ " + esc(A.why) + "</div>" : "") + "</div>";
  }
  var XBY = {};
  function wireSliders(el, redraw) {
    el.querySelectorAll("[data-sk]").forEach(function (i) {
      i.oninput = function () { var row = i.closest(".tr-sl"), x = XBY[i.dataset.sk] || { st: 1, u: "" }; row.classList.add("chg"); row.querySelector(".val").innerHTML = fmt(x, +i.value) + " <span class='au'>zapisuję…</span>"; };
      i.onchange = function () { ovSet(i.dataset.sk, +i.value); redraw(); };
    });
    el.querySelectorAll("[data-tk]").forEach(function (b) { b.onclick = function () { ovSet(b.dataset.tk, +b.dataset.i); redraw(); }; });
    el.querySelectorAll("[data-rs]").forEach(function (b) { b.onclick = function () { ovSet(b.dataset.rs, null); redraw(); }; });
  }
  var G = [
    { t: "Obciążenie", s: "Ile i jak szybko rośnie trening", x: [
      { k: "load.budget_h", n: "Budżet czasu w tygodniu (górna granica)", min: 2, max: 14, st: 0.5, def: 8, u: " h", why: "górna granica; optimum wynika z Sezonu" },
      { k: "load.progress", n: "Tempo progresji", min: 1, max: 5, st: 1, def: 3, lab: ["bardzo ostrożnie", "ostrożnie", "standard", "szybciej", "ambitnie"] },
      { k: "load.max_inc_pct", n: "Maks. wzrost obciążenia tydzień do tygodnia", min: 0, max: 15, st: 1, def: 7, u: " %" },
      { k: "load.min_rest_days", n: "Min. dni wolnych w tygodniu", min: 0, max: 3, st: 1, def: 1, u: "" },
      { k: "load.missed", n: "Odpuszczony trening", tog: ["odpuść", "przenieś, jeśli jest miejsce", "odrób zawsze"], def: 1 }] },
    { t: "Intensywność", s: "Rozkład wysiłku", x: [
      { k: "int.easy_pct", n: "Udział spokojnej jazdy (Z1–Z2)", min: 50, max: 95, st: 5, def: 80, u: " %" },
      { k: "int.hard_per_week", n: "Mocne akcenty w tygodniu", min: 0, max: 3, st: 1, def: 1, u: "×" },
      { k: "int.hard_gap_days", n: "Min. przerwa między mocnymi dniami", min: 1, max: 4, st: 1, def: 2, u: " dni" }] },
    { t: "Regeneracja", s: "Jak plan reaguje na zmęczenie — auto liczone z Twoich danych", x: [
      { k: "regen.sensitivity", n: "Czułość na gotowość dnia", min: 0, max: 10, st: 1, def: 5, u: "/10", l: ["ignoruj", "bardzo czuły"] },
      { k: "regen.min_pct", n: "Wersja minimum w najsłabsze dni", min: 0, max: 40, st: 5, def: 15, u: "% dni", l: ["nigdy", "często"] },
      { k: "regen.heavy_gap_h", n: "Przerwa po ciężkiej jeździe", min: 24, max: 96, st: 12, def: 48, u: " h" },
      { k: "adapt.xss_delta", n: "Reakcja na odchyłkę od planu", min: 5, max: 60, st: 5, def: 15, u: " obc.", why: "różnica obciążenia zrobionego treningu wobec planu, od której Trener sam przelicza resztę tygodnia (Telegram + Cofnij); oznaczenie na karcie od 10%" },
      { k: "regen.trip_rec_d", n: "Odpoczynek po wyprawie", min: 1, max: 6, st: 1, def: 3, u: " dni", why: "dni bez roweru/siły po wyprawie wielodniowej (joga ok)" },
      { k: "regen.after_illness", n: "Powrót po chorobie", tog: ["do powrotu HRV i gotowości do normy", "stała liczba tygodni"], def: 0, why: "sprawdzane codziennie" }] },
    { t: "Waga i jedzenie", s: "Tempo zmian i źródło bilansu", x: [
      { k: "food.loss_kg_wk", n: "Tempo spadku wagi", min: 0, max: 0.75, st: 0.05, def: 0.25, u: " kg/tydz.", l: ["utrzymanie", "0.75"] },
      { k: "food.no_deficit_over_h", n: "Bez deficytu w dni dłuższe niż", min: 1, max: 5, st: 0.5, def: 2.5, u: " h" },
      { k: "food.smooth_days", n: "Okno wygładzania wagi", min: 7, max: 28, st: 7, def: 14, u: " dni" },
      { k: "food.source", n: "Źródło bilansu", tog: ["tylko logi", "logi → waga", "tylko waga"], def: 1 }] },
    { t: "Mix dyscyplin w roku", s: "Ile sesji w tygodniu, miesiąc po miesiącu", wide: true, custom: "mix" },
    { t: "Joga — kiedy i jak długo", s: "Joga wstawiana według sytuacji", wide: true, custom: "yoga" },
    { t: "Pogoda i las", s: "Temperatura = odczuwalna z prognozy, nie termometr. Auto z Twoich jazd (2 lata) + pogoda historyczna", x: [
      { k: "wx.wind_ms", n: "💨 Wiatr średni — długa jazda", min: 4, max: 12, st: 0.5, def: 8, u: " m/s" },
      { k: "wx.gust_ms", n: "💨 Porywy — maks.", min: 8, max: 20, st: 1, def: 13, u: " m/s" },
      { k: "wx.forest_bonus_ms", n: "🌲 Las osłania — dodatek do progu", min: 0, max: 3, st: 0.5, def: 1, u: " m/s" },
      { k: "wx.cold_long_c", n: "🥶 Min. odczuwalna — długa jazda", min: -15, max: 10, st: 1, def: 0, u: " °C" },
      { k: "wx.cold_short_c", n: "🥶 Min. odczuwalna — krótka jazda", min: -20, max: 5, st: 1, def: -10, u: " °C" },
      { k: "wx.heat_c", n: "🥵 Upał — powyżej jazda rano", min: 24, max: 38, st: 1, def: 30, u: " °C" },
      { k: "wx.rain_mmh", n: "🌧️ Deszcz — maks. natężenie", min: 0, max: 5, st: 0.5, def: 0.5, u: " mm/h" },
      { k: "wx.rain_prob", n: "🌧️ Szansa opadu — maks.", min: 10, max: 90, st: 10, def: 40, u: " %" },
      { k: "wx.wet24_mm", n: "🟫 Mokro po deszczu (24 h)", min: 0, max: 30, st: 2, def: 10, u: " mm" },
      { k: "wx.snow_cm", n: "❄️ Śnieg — maks. pokrywa", min: 0, max: 30, st: 1, def: 10, u: " cm" },
      { k: "wx.snow_bike", n: "❄️ Przy śniegu / błocie proponuj rower", tog: ["szybszy (gravel)", "szersze opony (MTB)", "bez zmian"], def: 1 },
      { k: "wx.ice", n: "🧊 Oblodzenie (−2…+2 °C + opad / mokro)", tog: ["zostaję w domu", "tylko las, bez asfaltu", "pytaj mnie"], def: 2 },
      { k: "wx.storm", n: "⛈️ Burza", tog: ["zawsze omijam", "pytaj mnie"], def: 0 },
      { k: "wx.dusk", n: "🌇 Zmrok", tog: ["kończ przed zachodem", "z lampkami OK"], def: 0 },
      { k: "wx.fallback", n: "Gdy pogoda nie pasuje — najpierw", tog: ["przesuń godzinę", "przesuń dzień", "skróć", "zamień na dom"], def: 0 }] },
    { t: "Pilnowanie", s: "Telegram: plan tygodnia, przypomnienia, rozliczenie (wysyłka działa, gdy harmonogram na serwerze jest włączony)", x: [
      { k: "notify.week_plan", n: "Plan tygodnia na Telegram", tog: ["wył.", "pon 7:00", "ndz 20:00"], def: 2 },
      { k: "notify.day", n: "Przypomnienie w dniu treningu", tog: ["wył.", "rano", "2 h przed"], def: 1 },
      { k: "notify.review", n: "Rozliczenie tygodnia", tog: ["wył.", "ndz wieczór"], def: 1 },
      { k: "notify.tone", n: "Ton trenera", tog: ["łagodny", "rzeczowy", "wymagający"], def: 1 }] }
  ];
  G.forEach(function (g) { (g.x || []).forEach(function (x) { XBY[x.k] = x; }); });
  // domyślny Mix (sesji/tydz.) dla miesięcy I..XII
  var MIXD = { rower: [3, 3, 4, 4, 5, 5, 5, 5, 4, 4, 3, 3], sila: [3, 3, 2, 1, 1, 1, 1, 1, 1, 1, 2, 2], wiosl: [2, 2, 1, 0, 0, 0, 0, 0, 0, 0, 1, 2], joga: [2, 2, 2, 2, 3, 3, 3, 3, 2, 2, 2, 2], trenazer: [1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1] };
  var MIXR = [["rower", "🚲 Rower", 7], ["sila", "🏋️ Siła", 3], ["wiosl", "🚣 Wioślarz", 3], ["joga", "🧘 Joga (w tym krótkie)", 7], ["trenazer", "🏠 Trenażer (awaryjnie)", 3]];
  var YOGA = [["before_trip", "🌅", "Rano przed jazdą w dni bikepackingowe / wyprawy", 10, 20, 15], ["after_hard", "🔁", "Dzień po ciężkiej jeździe, gdy w planie jest coś innego", 10, 20, 15], ["rest_after_long", "🛋️", "Dzień wolny po długiej jeździe", 30, 45, 40], ["rest", "🛋️", "Zwykły dzień wolny", 20, 45, 30], ["low_form", "🤒", "Gorsza forma, niska gotowość, powrót po chorobie", 15, 30, 20], ["trip_work", "🧳", "Delegacja — tylko krótka", 10, 15, 15]];
  function rCalib() {
    var open = {}; try { open = JSON.parse(localStorage.getItem("qtrener_open") || "{}"); } catch (e) {}
    var wxs = S.auto && S.auto._weather;
    var h = "<div class='card'><div class='cardhead'><h2>Kalibracja trenera</h2><span class='sub'>zapis automatyczny · ↺ = powrót do auto</span></div>" + (wxs && wxs.computing ? "<div class='sub' style='margin-bottom:6px'>⏳ Liczę pogodę „auto” z historii jazd (ok. pół minuty) — odśwież zakładkę za chwilę.</div>" : "") + "<div class='tr-cal'>";
    G.forEach(function (g, gi) {
      h += "<details class='tr-grp" + (g.wide ? " wide" : "") + "' data-g='" + gi + "'" + (open[gi] || (gi === 0 && open[gi] === undefined) ? " open" : "") + "><summary><h3>" + g.t + " <span class='gc'></span></h3><p class='gs'>" + g.s + "</p></summary>";
      if (g.custom === "mix") {
        h += "<div class='tr-mx'><table class='tr-mxt'><tr><th></th>" + MN.map(function (m) { return "<th>" + m + "</th>"; }).join("") + "</tr>";
        MIXR.forEach(function (r) { h += "<tr><td class='rn'>" + r[1] + "</td>" + MN.map(function (m, mi) { var k = "mix." + r[0] + "." + (mi + 1), has = Object.prototype.hasOwnProperty.call(S.ov, k); return "<td><button data-mk='" + k + "' data-mx='" + r[2] + "' data-def='" + MIXD[r[0]][mi] + "' class='" + (has ? "man" : "au") + "'>" + (has ? S.ov[k] : MIXD[r[0]][mi]) + "</button></td>"; }).join("") + "</tr>"; });
        h += "</table></div><div class='sub' style='margin:6px 0'>Klik: auto → 0 → 1 → … → auto. Szare = domyślne dla okresu, kolorowe = Twoje.</div>";
      } else if (g.custom === "yoga") {
        YOGA.forEach(function (y) {
          var kon = "yoga." + y[0] + ".on", kmin = "yoga." + y[0] + ".min", on = ovGet(kon, 1), mn = ovGet(kmin, y[5]), ch = Object.prototype.hasOwnProperty.call(S.ov, kon) || Object.prototype.hasOwnProperty.call(S.ov, kmin);
          h += "<div class='tr-sl" + (ch ? " chg" : "") + "'><span class='n'>" + y[1] + " " + y[2] + "</span><span class='val'>" + (on ? mn + "′" : "wył.") + (ch ? " <span class='au rs' data-yr='" + y[0] + "'>auto ↺</span>" : " <span class='au'>domyślne</span>") + "</span><div class='tr-tog'><button data-yk='" + kon + "' data-i='1' class='" + (on ? "on" : "") + "'>wstawiaj</button><button data-yk='" + kon + "' data-i='0' class='" + (on ? "" : "on") + "'>nie</button></div><input type='range' data-ym='" + kmin + "' min='" + y[3] + "' max='" + y[4] + "' step='5' value='" + mn + "'" + (on ? "" : " disabled") + "><div class='ends'><span>" + y[3] + "′</span><span>" + y[4] + "′</span></div></div>";
        });
        h += sliderHTML({ k: "yoga.hard_xss", n: "„Ciężka jazda” = obciążenie powyżej", min: 60, max: 250, st: 10, def: 120, u: " XSS" }) + sliderHTML({ k: "yoga.long_h", n: "„Długa jazda” = dłużej niż", min: 1.5, max: 6, st: 0.5, def: 3, u: " h" });
        XBY["yoga.hard_xss"] = { st: 10, u: " XSS" }; XBY["yoga.long_h"] = { st: 0.5, u: " h" };
      } else h += g.x.map(sliderHTML).join("");
      h += "</details>";
    });
    h += "</div></div>";
    body.innerHTML = h;
    body.querySelectorAll("details.tr-grp").forEach(function (d) {
      var n = d.querySelectorAll(".tr-sl.chg").length + d.querySelectorAll(".tr-mxt button.man").length; d.querySelector(".gc").textContent = n ? "· zmienione: " + n : "";
      d.addEventListener("toggle", function () { open[d.dataset.g] = d.open; try { localStorage.setItem("qtrener_open", JSON.stringify(open)); } catch (e) {} });
    });
    wireSliders(body, rCalib);
    var pg = body.querySelectorAll("details.tr-grp")[G.map(function (g) { return g.t; }).indexOf("Pilnowanie")];
    if (pg) {
      pg.insertAdjacentHTML("beforeend", "<div class='tr-sl'><span class='n'>Podgląd wiadomości</span><span></span><div class='tr-tog'><button data-pv='plan'>🗓️ plan tygodnia</button><button data-pv='day'>💪 dziś</button><button data-pv='review'>📊 rozliczenie</button></div><pre id='tr-pv' style='grid-column:1/3;white-space:pre-wrap;font:inherit;font-size:12.5px;margin:6px 0 0;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px' hidden></pre></div>");
      pg.querySelectorAll("[data-pv]").forEach(function (b) { b.onclick = function () { api("GET", "/notify/preview?kind=" + b.dataset.pv + "&start=" + iso(monday(todayMs()))).then(function (j) { var p = document.getElementById("tr-pv"); p.hidden = false; p.textContent = j.text; }).catch(fail); }; });
    }
    body.querySelectorAll("[data-mk]").forEach(function (b) { b.onclick = function () { var k = b.dataset.mk, has = Object.prototype.hasOwnProperty.call(S.ov, k), v = has ? S.ov[k] : null, mx = +b.dataset.mx; ovSet(k, v === null ? 0 : (v >= mx ? null : v + 1)); rCalib(); }; });
    body.querySelectorAll("[data-yk]").forEach(function (b) { b.onclick = function () { ovSet(b.dataset.yk, +b.dataset.i); rCalib(); }; });
    body.querySelectorAll("[data-ym]").forEach(function (i) { i.onchange = function () { ovSet(i.dataset.ym, +i.value); rCalib(); }; });
    body.querySelectorAll("[data-yr]").forEach(function (b) { b.onclick = function () { ovSet("yoga." + b.dataset.yr + ".on", null); ovSet("yoga." + b.dataset.yr + ".min", null); rCalib(); }; });
  }

  // ---------- wczytanie ----------
  function loadGoals() { return api("GET", "/goals").then(function (j) { S.goals = j.items || []; }); }
  function loadRules() { return api("GET", "/rules").then(function (j) { S.rules = j.items || []; }); }
  body.innerHTML = "<div class='tr-empty'>Wczytuję…</div>";
  Promise.all([loadGoals(), loadRules(), api("GET", "/settings").then(function (j) { S.ov = j.overrides || {}; })]).then(function () {
    var s = null; try { s = localStorage.getItem("qtrener_sub"); } catch (e) {}
    if (window.TRENER_M) window.TRENER_M.ready();   // telefon / iPad: tydzien rysuje trener-m.js
    else go(SUBS.some(function (x) { return x[0] === s; }) ? s : "tydzien");
    api("GET", "/auto").then(function (j) { S.auto = j; if (S.sub === "kalib") rCalib(); }).catch(function () {});
  }).catch(function (e) { body.innerHTML = "<div class='tr-empty'>Nie udało się wczytać Trenera: " + esc(e.message) + "</div>"; });
})();
