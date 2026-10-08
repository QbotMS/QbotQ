/* kalendarz3.js (2026-10-08) — zakladka "Kalendarz" strony TRENING (/trening.html): dawny Kalendarz (Miesiac) + Tydzien Trenera w jednym.
   Tydzien wybranego dnia POWIEKSZONY (karty dni z planem Trenera), reszta miesiaca SCISNIETA. Naglowek: 4 kafle tygodnia + 5. kafel
   z ostrzezeniami (zawsze na wierzchu); "Szczegoly tygodnia" (godziny, Popros Trenera, Weryfikacja AI) zwiniete.
   Panel dnia (klik w dzien): samopoczucie / wydarzenie / choroba / przypomnienie (edytor wpisow Kalendarza = port z kalendarz2-data.js:
   typy, kolory, wielodniowe, trasa dnia, raport mailem), + trening, edycja dnia (REST / brak czasu / choroba / delegacja / zwykly dzien).
   Klik w trening = okno treningu (zrobione / minimum / pomin / usun / godzina / czas / przenies / zamien). Wszystko przez istniejace API:
   /api/calendar*, /api/calendar/wx, /api/report/schedule*, /api/routes/ready, /api/mail-groups, /api/trener/*.
   Montaz: sekcja #p-kal w trening.html; trener.js go("kalendarz") ustawia body.tr-month i wola KAL3.refresh(). Dok.: docs/TRENER.md */
(function () {
"use strict";
var root = document.getElementById("p-kal"); if (!root) return;
/* 2026-10-08: kafle tygodnia szerokie wg tresci (Sesje ✓/plan bywa dlugie), kafel ostrzezen bierze reszte; nadpisuje grid z trening.html */
(function () { var st = document.createElement("style"); st.textContent =
  "#p-kal .tiles{display:flex;flex-wrap:wrap;gap:8px}#p-kal .tiles .tile{flex:0 1 auto;min-width:110px}#p-kal .tiles .tile.al{flex:1 1 320px}" +
  "@media(max-width:760px){#p-kal .tiles .tile{flex:1 1 40%}#p-kal .tiles .tile.al{flex:1 1 100%}#p-kal .tiles .tile .v{white-space:normal}}";
  document.head.appendChild(st); })();
var NOW = new Date();
function iso(d) { return d.getFullYear() + "-" + qPad2(d.getMonth() + 1) + "-" + qPad2(d.getDate()); }
function P(s) { return new Date(s + "T12:00:00"); }
function addD(d, n) { var x = new Date(d); x.setDate(x.getDate() + n); return x; }
function monday(d) { var x = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; }
function dm(d) { return qPad2(d.getDate()) + "." + qPad2(d.getMonth() + 1); }
function h1(v) { return (Math.round(v * 10) / 10).toString().replace(".", ","); }
var today = iso(NOW), Y = NOW.getFullYear(), M = NOW.getMonth(), SEL = today, BIG = iso(monday(NOW)), PANEL = false;  /* PANEL: panel dnia widoczny tylko po kliknieciu dnia */
var MON = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"];
var MONG = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września", "października", "listopada", "grudnia"];
var DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"], DNL = ["Niedziela", "Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota"];
var AIC = { rower: "🚲", sila: "🏋️", wiosl: "🚣", joga: "🧘" };
var ACT = [["rower", "🚲", "Rower"], ["sila", "🏋️", "Siła"], ["wiosl", "🚣", "Wioślarz"], ["joga", "🧘", "Joga"]];
var DEF = { rower: ["Rower spokojnie", "12:00", 60, 30], sila: ["Siła obwodowa", "10:00", 40, 15], wiosl: ["Wioślarz spokojnie", "16:00", 30, 15], joga: ["Joga", "09:00", 20, 10] };
var DTYPE = { rest: "😴 REST DAY", ill: "🤒 choroba", del: "🧳 delegacja", short: "⏱ brak czasu", trip: "🗺️ wyprawa", urlop: "🏖️ urlop" };
var FEEL_LABEL = { "-2": "fatalnie", "-1": "słabo", "0": "neutralnie", "1": "dobrze", "2": "świetnie" };
function isCyc(s) { s = String(s || ""); return s.indexOf("cycl") >= 0 || s.indexOf("biking") >= 0; }
function spIcon(s) { s = String(s || ""); return isCyc(s) ? "🚲" : s.indexOf("yoga") >= 0 ? "🧘" : s.indexOf("rowing") >= 0 ? "🚣" : s.indexOf("walk") >= 0 || s.indexOf("hik") >= 0 ? "🚶" : s.indexOf("strength") >= 0 ? "🏋️" : s.indexOf("run") >= 0 ? "🏃" : "🏅"; }
function evIcon(t) { return t === "jazda" ? "🚴" : t === "urlop" ? "🏖️" : t === "delegacja" ? "💼" : t === "rest" ? "😴" : "📅"; }
function evLabel(t) { return t === "jazda" ? "Jazda" : t === "urlop" ? "Urlop" : t === "delegacja" ? "Delegacja" : t === "rest" ? "Rest day" : "Wydarzenie"; }
function txt(s) { return (typeof QD !== "undefined" && QD.text) ? QD.text(s) : s; }
function $(id) { return document.getElementById(id); }

/* ---------- API ---------- */
function api(m, p, b) {
  return fetch("/api/trener" + p, { method: m, credentials: "same-origin", headers: b ? { "Content-Type": "application/json" } : {}, body: b ? JSON.stringify(b) : undefined })
    .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status)); return j; }); });
}
async function post(url, body) { var r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", body: JSON.stringify(body) }); if (!r.ok) { var t = ""; try { t = await r.text(); } catch (e) {} throw new Error(t || ("HTTP " + r.status)); } try { return await r.json(); } catch (e) { return {}; } }
var toastT = null;
function toast(msg, bad) { var el = $("k3-toast"); if (!el) { el = document.createElement("div"); el.id = "k3-toast"; document.body.appendChild(el); }
  el.className = bad ? "bad" : ""; el.textContent = msg; el.hidden = false; clearTimeout(toastT); toastT = setTimeout(function () { el.hidden = true; }, bad ? 5000 : 2500); }
function fail(e) { toast("Błąd: " + (e && e.message ? e.message : e), true); }

/* ---------- dane (cache do pierwszego zapisu) ---------- */
var WK = {}, CAL = {}, WXC = {}, SCH = {};
function invalidate() { WK = {}; CAL = {}; WXC = {}; SCH = {}; }
function loadWeek(k) { return WK[k] || (WK[k] = api("GET", "/week?start=" + k).catch(function () { return { sessions: [], meta: {} }; })); }
function loadCal(s, e) { var k = s + "|" + e; return CAL[k] || (CAL[k] = qJSON("/api/calendar?start=" + s + "&end=" + e)); }
function getJ(u) { return fetch(u, { credentials: "same-origin", cache: "no-store" }).then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; }); }
function loadWx(s, e) { var k = s + "|" + e; return WXC[k] || (WXC[k] = getJ("/api/calendar/wx?start=" + s + "&end=" + e)); }
function loadSch(s, e) { var k = s + "|" + e; return SCH[k] || (SCH[k] = getJ("/api/report/schedules?start=" + s + "&end=" + e)); }
var C = {}, W = {}, X = {}, entryRoutes = {}, sched = {}, RANGE = ["", ""];
function info(ds) { return (C.days || {})[ds] || {}; }
function rides(ds) { return (C.rides || {})[ds] || []; }
function ents(ds) { return (C.entries || []).filter(function (e) { return e.day <= ds && (e.end_day || e.day) >= ds; }); }
function findEntry(id) { return (C.entries || []).filter(function (e) { return e.id === id; })[0] || null; }
function wk(ds) { return W[iso(monday(P(ds)))] || {}; }
function sess(ds) { return (wk(ds).sessions || []).filter(function (x) { return x.day === ds; }).sort(function (a, b) { return String(a.start_time || "").localeCompare(String(b.start_time || "")); }); }
function sesById(id) { for (var k in W) { var s = (W[k].sessions || []).filter(function (x) { return x.id === id; })[0]; if (s) return s; } return null; }
function openSess(ds) { return sess(ds).filter(function (x) { return x.status !== "done"; }); }
/* wpis jazdy z Kalendarza, ktory Trener zamienil na trening (jak w trener-m.js: event z godzina / jazda / trasa dnia) */
function inPlan(e, ds) { if (e.kind !== "event") return false; var rid = ((wk(ds).meta || {}).route_entry_ids || []);
  if (!(e.event_type === "jazda" || rid.indexOf(e.id) >= 0 || (e.at_time && !e.event_type))) return false;
  return sess(ds).some(function (x) { return x.sport === "rower"; }); }
function gridEnts(ds) { return ents(ds).filter(function (e) { return !inPlan(e, ds); }); }
function planEnts(ds) { return ents(ds).filter(function (e) { return inPlan(e, ds); }); }
function isIll(ds) { return ents(ds).some(function (e) { return e.kind === "illness"; }); }

/* ---------- male elementy ---------- */
function wxBad(f, ov) { var g = function (k, d) { return ov && ov[k] != null ? +ov[k] : d; }; return (f.wind != null && f.wind > g("wx.wind_ms", 8) + g("wx.forest_bonus_ms", 1)) || (f.rain_mmh != null && f.rain_mmh > g("wx.rain_mmh", 0.5)) || !!f.storm; }
function wxHTML(ds, full) {
  var r = (X.rides || {})[ds], f = (X.forecast || {})[ds], st = full ? ' style="font-size:13px;margin-top:4px;white-space:normal"' : "";
  if (r && (ds < today || !f)) return '<div class="wx"' + st + ' title="pogoda podczas jazdy">' + (r.icon || "") + " " + (r.wind != null ? qN(r.wind, 1) + " m/s" : "") + (r.feel_max != null ? " · " + Math.round(r.feel_max) + "°" : "") + (full ? " · podczas jazdy" : "") + "</div>";
  if (f) return '<div class="wx' + (wxBad(f, X.ov) ? " bad" : "") + '"' + st + ' title="prognoza 8–18">' + (f.icon || "") + " " + (f.wind != null ? qN(f.wind, 1) + " m/s" : "") + (f.gust != null && full ? " (porywy " + qN(f.gust, 1) + ")" : "") + (f.feel_max != null ? " · " + Math.round(f.feel_max) + "°" : "") + (full && f.rain_prob != null ? " · opad " + Math.round(f.rain_prob) + "%" : "") + (f.storm ? " · ⚡" : "") + "</div>";
  return "";
}
function rdHTML(ds) { var i = info(ds); if (!i.readiness_label) return ""; var c = i.readiness > 0.3 ? "var(--good)" : i.readiness > -0.3 ? "var(--ink2)" : "var(--bad)"; return '<span class="r" style="color:' + c + '">' + qEsc(i.readiness_label) + "</span>"; }
function slHTML(ds) { var i = info(ds), a = []; if (i.sleep_score) a.push("sen " + i.sleep_score); else if (i.sleep) a.push("sen " + qN(i.sleep, 1) + "h"); if (i.weight_kg) a.push(qN(i.weight_kg, 1) + " kg"); return a.length ? '<div class="sl"><span>' + a.join("</span><span>") + "</span></div>" : ""; }
function rideLn(r) { var cy = isCyc(r.sport); return '<div class="ln done">' + spIcon(r.sport) + " " + ((cy && r.dist_km) ? qN(r.dist_km, 0) + " km · " : "") + qHM(r.duration_s || 0) + (r.xss ? " · " + Math.round(r.xss) : "") + "</div>"; }
function entLn(e, full) {
  var ws = full ? ' style="white-space:normal;margin:3px 0"' : "", a = ' data-eid="' + e.id + '"' + ws;
  if (e.kind === "illness") return '<div class="ln ill"' + a + ">🤒 " + qEsc(e.title || "choroba") + "</div>";
  if (e.kind === "feel") return '<div class="ln gray"' + a + ">🙂 " + qEsc(FEEL_LABEL[String(e.feel)] || e.title || "") + (full && e.note ? " — " + qEsc(e.note) : "") + "</div>";
  if (e.kind === "reminder") return '<div class="ln gray"' + a + ">⏰ " + qEsc((e.at_time ? e.at_time.slice(0, 5) + " " : "") + (e.title || "przypomnienie")) + "</div>";
  return '<div class="ln ev ev-' + (e.event_type || "event") + '"' + a + ">" + evIcon(e.event_type) + " " + qEsc(txt(e.title || evLabel(e.event_type))) + "</div>";
}
/* dzien = plan Trenera polaczony z faktycznymi jazdami: {list: [{s, ride, st}], extra: [jazdy spoza planu]};
   st: done (✓ zrobione) | miss (✗ miniony, niezrobiony) | plan (przyszly) | skip (pominiety) */
function dayPlan(ds) {
  var w = wk(ds), rs = rides(ds).slice(), used = {}, acts = {};
  (w.activities || []).forEach(function (a) { if (String(a.date).slice(0, 10) === ds) acts[a.id] = a; });
  function rideFor(a) { if (!a) return null; for (var i = 0; i < rs.length; i++) if (!used[i] && rs[i].duration_s === a.duration_s) { used[i] = 1; return rs[i]; } return null; }
  var list = sess(ds).map(function (x) {
    var st = x.status === "done" ? "done" : x.status === "skip" ? "skip" : (ds < today ? "miss" : "plan");
    return { s: x, st: st, ride: st === "done" ? rideFor(acts[x.training_session_id]) : null };
  });
  /* dubel z Trenera: niezrobiony plan + zrobiony trening tej samej dyscypliny tego dnia -> zostaje tylko zrobiony */
  list = list.filter(function (it) { return !(it.st === "miss" && list.some(function (o) { return o.st === "done" && o.s.sport === it.s.sport; })); });
  return { list: list, extra: rs.filter(function (r, i) { return !used[i]; }) };
}
function realTxt(it) { var r = it.ride, x = it.s; if (r) return ((isCyc(r.sport) && r.dist_km) ? qN(r.dist_km, 0) + " km · " : "") + qHM(r.duration_s || 0) + (r.xss ? " · XSS " + Math.round(r.xss) : ""); return (x.real_min != null ? x.real_min : x.dur_min) + "′"; }
function dotsHTML(ds) { var dp = dayPlan(ds), h = "";
  dp.list.forEach(function (it) { if (it.st !== "skip") h += '<i class="' + (it.st === "done" ? "d" : it.st === "miss" ? "m" : "p") + '"></i>'; });
  dp.extra.forEach(function () { h += '<i class="d"></i>'; });
  gridEnts(ds).forEach(function (e) { h += '<i class="' + (e.kind === "illness" ? "x" : "e") + '"></i>'; }); return '<div class="dots">' + h + "</div>"; }
function cls(base, ds, inM) { return base + (inM ? "" : " off") + (ds === today ? " t" : "") + (PANEL && ds === SEL ? " sel" : "") + (isIll(ds) ? " ill" : ""); }
function compactCell(d, inM) {
  var ds = iso(d), h = '<div class="n"><b>' + d.getDate() + "</b>" + (inM ? rdHTML(ds) : "") + "</div>" + wxHTML(ds);
  var dp = dayPlan(ds);
  dp.list.forEach(function (it) { var x = it.s, ic = AIC[x.sport] || "•";
    if (it.st === "done") h += '<div class="ln ok" data-sid="' + x.id + '" title="plan zrobiony: ' + qEsc(x.name) + '">✓' + ic + " " + realTxt(it) + "</div>";
    else if (it.st === "miss") h += '<div class="ln miss" data-sid="' + x.id + '" title="plan niezrobiony: ' + qEsc(x.name) + '">✗' + ic + " " + x.dur_min + "′</div>";
    else h += '<div class="ln ' + (it.st === "skip" ? "sk" : "p") + '" data-sid="' + x.id + '">' + ic + " " + (x.start_time ? x.start_time.slice(0, 5) + " " : "") + x.dur_min + "′</div>"; });
  dp.extra.forEach(function (r) { h += rideLn(r); });
  gridEnts(ds).forEach(function (e) { h += entLn(e); });
  return '<div class="' + cls("cd", ds, inM) + '" data-day="' + ds + '">' + h + slHTML(ds) + dotsHTML(ds) + "</div>";
}
function bigCell(d, inM) {
  var ds = iso(d), dmeta = ((wk(ds).meta || {}).days || {})[ds] || {}, n = 0;
  var h = '<div class="n"><b>' + DN[(d.getDay() + 6) % 7] + " " + d.getDate() + "</b>" + rdHTML(ds) + "</div>" + wxHTML(ds);
  /* plakietka typu dnia tylko, gdy nie wynika z wpisu Kalendarza widocznego ponizej (inaczej REST DAY bylby dwa razy) */
  var TYSRC = { rest: function (e) { return e.event_type === "rest"; }, ill: function (e) { return e.kind === "illness"; },
    del: function (e) { return e.event_type === "delegacja"; }, urlop: function (e) { return e.event_type === "urlop"; } };
  if (DTYPE[dmeta.type] && !(TYSRC[dmeta.type] && ents(ds).some(TYSRC[dmeta.type]))) h += '<span class="ty">' + DTYPE[dmeta.type] + "</span>";
  var dp = dayPlan(ds), pe = planEnts(ds), peDone = false;
  dp.list.forEach(function (it) { var x = it.s; n++;
    var plan = (x.start_time ? x.start_time.slice(0, 5) + " · " : "") + x.dur_min + "′" + (x.cut ? " (minimum)" : "") + (x.xss ? " · ~" + Math.round(x.xss) + " XSS" : "");
    var mark = it.st === "done" ? "✓ " : it.st === "miss" ? "✗ " : "";
    var sub = it.st === "done" ? "plan " + x.dur_min + "′ → zrobione " + realTxt(it) : it.st === "miss" ? "plan " + plan + " — niezrobione" : it.st === "skip" ? "pominięte · " + plan : plan;
    h += '<div class="ss ' + it.st + '" data-sid="' + x.id + '"><b>' + mark + (AIC[x.sport] || "") + " " + qEsc(x.name) + "</b><small>" + sub + "</small>" +
      (x.sport === "rower" && !peDone && pe.length ? (peDone = true, pe.map(function (e) { return '<small class="kal" data-eid="' + e.id + '">📅 z Kalendarza: ' + qEsc(txt(e.title || "jazda")) + (e.at_time ? " · " + e.at_time.slice(0, 5) : "") + "</small>"; }).join("")) : "") + "</div>"; });
  dp.extra.forEach(function (r) { n++; h += rideLn(r).replace("</div>", ' <small style="font-weight:400">· poza planem</small></div>'); });
  gridEnts(ds).forEach(function (e) { n++; h += entLn(e); });
  if (!n) h += '<div class="free">wolne</div>';
  return '<div class="' + cls("bd", ds, inM) + '" data-day="' + ds + '">' + h + slHTML(ds) + "</div>";
}

/* ---------- naglowek tygodnia ---------- */
function weekStats(k) {
  var w = W[k] || {}, ses = w.sessions || [], act = ses.filter(function (x) { return x.status !== "skip"; }), per = {}, linked = {}, nr = 0, km = 0, rx = 0;
  ses.forEach(function (x) { if (x.training_session_id) linked[x.training_session_id] = 1; });
  var extra = (w.activities || []).filter(function (a) { return !linked[a.id]; });
  var done = act.filter(function (x) { return x.status === "done"; }).reduce(function (a, x) { return a + (x.real_min != null ? +x.real_min : x.dur_min); }, 0) / 60 + extra.reduce(function (a, x) { return a + (x.duration_s || 0); }, 0) / 3600;
  for (var i = 0; i < 7; i++) rides(iso(addD(P(k), i))).forEach(function (r) { nr++; if (isCyc(r.sport)) km += (r.dist_km || 0); rx += (r.xss || 0); });
  act.forEach(function (x) { per[x.sport] = per[x.sport] || [0, 0]; per[x.sport][1]++; if (x.status === "done") per[x.sport][0]++; });
  return { w: w, meta: w.meta || {}, plan: act.reduce(function (a, x) { return a + (x.dur_min || 0); }, 0) / 60, done: done, xss: act.reduce(function (a, x) { return a + (+x.xss || 0); }, 0), per: per, target: (w.meta || {}).target_h, nr: nr, km: km, rx: rx };
}
var ASK = null, REV = null;
/* Akceptuj / Cofnij: decyzja dla zmiany; blizniaki (ta sama akcja tego tygodnia, utworzone w ciagu 10 s - duble z rownoleglych odczytow)
   sa potem AKCEPTOWANE (nigdy cofane drugi raz) */
function decide(path, pc, msg) {
  var k = BIG, t0 = Date.parse(pc.created_at || "") || 0, n = 0;
  function step(cur) { return api("POST", n === 0 ? path : "/week/accept", { id: cur.id }).then(function () { n++; return api("GET", "/week?start=" + k); }).then(function (w) {
    var nx = w && w.pending_change, t1 = nx ? (Date.parse(nx.created_at || "") || 0) : 0;
    if (nx && n < 8 && nx.action === pc.action && Math.abs(t1 - t0) < 10000) return step(nx); }); }
  step(pc).then(function () { toast(msg + (n > 1 ? " (+" + (n - 1) + " zdublowane zmiany zaakceptowane)" : "")); refresh(true); }).catch(function (e) { fail(e); refresh(true); });
}
function drawTop() {
  var k = BIG, st = weekStats(k), m = st.meta, a = P(k), b = addD(a, 6), past = iso(b) < today;
  $("k3-phase").textContent = m.phase_name ? ("Sezon — " + m.phase_name) : "Sezon";
  var gen = $("k3-gen"); gen.disabled = past; gen.textContent = "↻ przelicz tydzień";
  gen.onclick = function () { gen.disabled = true; gen.textContent = "liczę…"; api("POST", "/week/generate", { start: k }).then(function () { toast("Tydzień przeliczony — zaakceptuj albo cofnij"); refresh(true); }).catch(function (e) { fail(e); gen.disabled = false; gen.textContent = "↻ przelicz tydzień"; }); };
  var per = Object.keys(st.per).map(function (s) { return AIC[s] + " " + st.per[s][0] + "/" + st.per[s][1]; }).join(" · ") || "—";
  var al = "", pc = st.w.pending_change;
  if (pc) { var lines = (pc.payload && pc.payload.lines) || null;
    al += "<div><b>Zmiany w tygodniu czekają na decyzję</b>" + (lines && lines.length ? "<ul>" + lines.map(function (l) { return "<li>" + qEsc(l) + "</li>"; }).join("") + "</ul>" : "") + '<div class="acts"><button type="button" id="k3-ok">Akceptuj</button><button type="button" id="k3-un">Cofnij</button></div></div>'; }
  if (today >= k && today <= iso(b) && m.readiness_today != null && m.readiness_threshold != null && m.readiness_today < m.readiness_threshold) al += "<div>🫀 Gotowość dziś <b>" + m.readiness_today.toFixed(2) + "</b> (próg " + m.readiness_threshold.toFixed(2) + ") — dziś wersje minimum.</div>";
  (m.season_notes || []).forEach(function (n) { al += "<div>🩺 " + qEsc(n) + "</div>"; });
  (st.w.warnings || []).forEach(function (x) { if (typeof x === "string") x = { text: x }; if (x.acked) return; al += "<div>⚠️ " + qEsc(x.text) + (x.session_id ? ' <button type="button" class="k3-ack" data-ack="' + qEsc(x.key) + '" data-sid="' + x.session_id + '">rozumiem</button>' : "") + "</div>"; });
  if (st.w.calendar_update) al += "<div>🗓️ Plan zaktualizowany sam: " + qEsc(st.w.calendar_update.reason) + ".</div>";
  if (m.error) al += "<div>Meta planu niedostępne: " + qEsc(m.error) + "</div>";
  if (!(st.w.sessions || []).length && !past) al += "<div>Brak planu na ten tydzień — kliknij <b>↻ przelicz tydzień</b>.</div>";
  $("k3-tiles").innerHTML = '<div class="tile"><div class="l">Plan / zrobione</div><div class="v">' + h1(st.plan) + " / " + h1(st.done) + " h</div></div>" +
    '<div class="tile"><div class="l">Obciążenie (plan)</div><div class="v">~' + Math.round(st.xss) + " XSS</div></div>" +
    '<div class="tile"><div class="l">Sesje ✓/plan</div><div class="v"><small>' + per + "</small></div></div>" +
    '<div class="tile"><div class="l">Cel z Sezonu</div><div class="v">' + (st.target ? h1(st.target) + " h" : "—") + "</div></div>" +
    '<div class="tile al' + (al ? "" : " ok") + '">' + (al || "✓ bez uwag na tydzień " + dm(a) + "–" + dm(b)) + "</div>";
  if (pc) { $("k3-ok").onclick = function () { decide("/week/accept", pc, "Zaakceptowano"); };
    $("k3-un").onclick = function () { decide("/week/undo", pc, "Cofnięto"); }; }
  root.querySelectorAll(".k3-ack").forEach(function (bt) { bt.onclick = function () { var x = sesById(+bt.dataset.sid); if (!x) return; var ak = (x.acks || []).slice(); if (ak.indexOf(bt.dataset.ack) < 0) ak.push(bt.dataset.ack);
    api("PUT", "/sessions/" + x.id, { acks: ak }).then(function () { toast("Uwaga wyciszona"); refresh(true); }).catch(fail); }; });
  $("k3-moresum").textContent = "Szczegóły tygodnia " + dm(a) + "–" + dm(b) + ": godziny · Poproś Trenera · Weryfikacja AI";
  var h = "";
  if (st.target) { var mx = st.target * 1.6;
    h += '<div class="bar"><i style="width:' + Math.min(100, st.plan / mx * 100) + '%;background:rgba(47,158,91,.35)"></i><i style="width:' + Math.min(100, st.done / mx * 100) + '%;background:var(--good)"></i><i style="left:' + (st.target * 0.75 / mx * 100) + "%;width:" + (st.target * 0.5 / mx * 100) + '%;border-left:2px solid var(--good);border-right:2px solid var(--good)"></i></div>' +
      '<div class="sub">plan ' + h1(st.plan) + " h · zrobione " + h1(st.done) + " h · cel " + h1(st.target) + " h (widełki " + h1(st.target * 0.75) + "–" + h1(st.target * 1.25) + ")</div>"; }
  if (!past) h += '<div class="box" id="k3-ask"></div><div class="box" id="k3-rev"></div>';
  else h += '<div class="sub" style="margin-top:8px">Tydzień miniony — bez zmian planu.</div>';
  $("k3-morein").innerHTML = h;
  if (!past) { drawAsk(); drawRev(); }
}
function drawAsk() {
  var el = $("k3-ask"); if (!el) return;
  var A = (ASK && ASK.wk === BIG) ? ASK : (ASK = { wk: BIG, text: "", res: null, busy: false });
  var h = '<b>💬 Poproś Trenera o zmianę</b><textarea id="k3-at" rows="2" maxlength="600" placeholder="np. Dziś siła bez nóg, a do tego 30–45′ roweru po południu">' + qEsc(A.text) + "</textarea>" +
    '<button type="button" class="pri" id="k3-ag"' + (A.busy ? " disabled" : "") + ">" + (A.busy ? "AI układa zmiany… (ok. 10 s)" : "Zaproponuj zmiany") + "</button>";
  if (A.res && !A.busy) { var r = A.res, ch = r.changes || [];
    h += '<div style="margin:10px 0 4px">' + qEsc(r.summary || "") + "</div>";
    if (ch.length) h += "<ul>" + ch.map(function (c) { return "<li>" + qEsc(c.line) + (c.warn ? '<br><span style="color:var(--warn)">⚠ ' + qEsc(c.warn) + "</span>" : "") + "</li>"; }).join("") + '</ul><button type="button" class="pri" id="k3-ao">✓ Zastosuj</button> <button type="button" id="k3-an">✕ Odrzuć</button>';
    else h += '<button type="button" id="k3-an">wyczyść</button>';
    if ((r.rejected || []).length) h += '<div class="sub" style="margin-top:6px">Odrzucone przez bezpieczniki: ' + r.rejected.map(qEsc).join(" · ") + "</div>"; }
  el.innerHTML = h;
  var ta = $("k3-at"); ta.oninput = function () { A.text = ta.value; };
  $("k3-ag").onclick = function () { var t = (ta.value || "").trim(); if (!t || A.busy) return; A.text = t; A.busy = true; A.res = null; drawAsk();
    api("POST", "/week/ask", { start: BIG, text: t }).then(function (r) { A.busy = false; A.res = r; drawAsk(); }).catch(function (e) { A.busy = false; A.res = { summary: "Błąd: " + e.message, changes: [] }; drawAsk(); }); };
  var no = $("k3-an"); if (no) no.onclick = function () { A.res = null; drawAsk(); };
  var ok = $("k3-ao"); if (ok) ok.onclick = function () { ok.disabled = true; ok.textContent = "zapisuję…";
    api("POST", "/week/ask/apply", { start: BIG, text: A.text, changes: A.res.changes }).then(function () { ASK = null; toast("Zmiany zastosowane — możesz je cofnąć"); refresh(true); }).catch(function (e) { fail(e); ok.disabled = false; ok.textContent = "✓ Zastosuj"; }); };
}
var SEVC = { "wysoka": "🔴", "średnia": "🟠", "niska": "🔵" };
function drawRev(busy) {
  var el = $("k3-rev"); if (!el) return; var r = (REV && REV.wk === BIG) ? REV.res : null;
  var h = "<b>🤖 Weryfikacja AI</b>";
  if (busy) h += '<div class="sub" style="margin:6px 0">AI czyta plan, Kalendarz, pogodę i cele (ok. 10–15 s)…</div>';
  else if (r) h += '<div style="margin:6px 0">' + qEsc(r.summary || "") + "</div>" + (r.issues || []).map(function (i) { return '<div class="iss">' + (SEVC[i.severity] || "🟠") + " <b>" + qEsc(i.day || "") + ": " + qEsc(i.problem) + "</b>" + (i.why ? '<div class="sub">dlaczego: ' + qEsc(i.why) + "</div>" : "") + (i.suggestion ? "<div>👉 " + qEsc(i.suggestion) + "</div>" : "") + "</div>"; }).join("") + (!(r.issues || []).length ? '<div class="sub">✓ AI nie widzi problemów.</div>' : "");
  else h += '<div class="sub" style="margin:6px 0">AI przejrzy tydzień pod kątem rzeczy bez sensu (siła przy długiej jeździe, konflikt z Kalendarzem, pogoda). Tylko doradza.</div>';
  el.innerHTML = h + '<button type="button" id="k3-rv"' + (busy ? " disabled" : "") + ">" + (busy ? "sprawdzam…" : "sprawdź plan") + "</button>";
  $("k3-rv").onclick = function () { drawRev(true); api("POST", "/week/review", { start: BIG, force: true }).then(function (x) { REV = { wk: BIG, res: x }; drawRev(); }).catch(function (e) { REV = { wk: BIG, res: { summary: "Błąd weryfikacji: " + e.message, issues: [] } }; drawRev(); }); };
}

/* ---------- panel dnia ---------- */
function setPanel(on) { PANEL = !!on; var l = $("k3-lay"); if (l) l.classList.toggle("nodp", !PANEL);
  if (!PANEL) root.querySelectorAll("#k3-grid .sel").forEach(function (z) { z.classList.remove("sel"); }); }
function showDay(ds) {
  var i = info(ds), d = P(ds), fut = ds >= today, h = '<div class="dph"><h3>' + DNL[d.getDay()] + ", " + d.getDate() + " " + MONG[d.getMonth()] + '</h3><button type="button" class="dpx" id="k3-dpx" aria-label="Zamknij panel dnia">✕</button></div>';
  h += '<div class="kv"><span>gotowość <b>' + (typeof i.readiness === "number" ? (i.readiness > 0 ? "+" : "") + qN(i.readiness, 2) : "—") + "</b></span><span>sen <b>" + (i.sleep_score || (i.sleep ? qN(i.sleep, 1) + "h" : "—")) + "</b></span><span>HRV <b>" + (i.hrv ? qN(i.hrv, 0) : "—") + "</b></span><span>waga <b>" + (i.weight_kg ? qN(i.weight_kg, 1) + " kg" : "—") + "</b></span></div>";
  h += wxHTML(ds, true);
  h += '<div class="grp"><div class="sh">Plan Trenera</div>'; var ss = sess(ds);
  var dpl = dayPlan(ds);
  if (ss.length) dpl.list.forEach(function (it) { var x = it.s, st = it.st === "done" ? "✓ zrobione " + realTxt(it) : it.st === "miss" ? "✗ niezrobione" : it.st === "skip" ? "pominięte" : ((x.start_time ? x.start_time.slice(0, 5) + " · " : "") + x.dur_min + "′");
    h += '<div class="row click st-' + it.st + '" data-sid="' + x.id + '"><span>' + (AIC[x.sport] || "") + " " + qEsc(x.name) + '</span><span class="s">' + st + " ›</span></div>"; });
  else h += '<div class="empty">brak zaplanowanych treningów</div>';
  h += '</div><div class="grp"><div class="sh">Wykonane</div>';
  if (rides(ds).length) rides(ds).forEach(function (r) { var cy = isCyc(r.sport); h += '<div class="row"><span>' + spIcon(r.sport) + " " + (cy ? '<a class="link" href="/raport-jazdy.html?ride=' + encodeURIComponent(r.ride_key) + '">' + qEsc(r.name) + "</a>" : qEsc(r.name || "")) + '</span><span class="s">' + ((cy && r.dist_km) ? qN(r.dist_km, 1) + " km · " : "") + qHM(r.duration_s || 0) + (r.xss ? " · " + Math.round(r.xss) : "") + "</span></div>"; });
  else h += '<div class="empty">' + (fut ? "dzień jeszcze przed Tobą" : "bez treningu") + "</div>";
  h += '</div><div class="grp"><div class="sh">Kalendarz</div>';
  var es = ents(ds); if (es.length) es.forEach(function (e) { h += entLn(e, true).replace(/<\/div>$/, inPlan(e, ds) ? ' <small>· w planie Trenera</small></div>' : "</div>"); }); else h += '<div class="empty">brak wpisów</div>';
  h += '</div><div class="acts"><button type="button" data-a="feel">😊 samopoczucie</button><button type="button" data-a="event">＋ wydarzenie</button><button type="button" data-a="illness">🤒 choroba</button><button type="button" data-a="reminder">🔔 przypomnij</button>' +
    (fut ? '<button type="button" data-a="add">＋ trening</button><button type="button" data-a="day">✎ ustaw dzień</button>' : "") + "</div>";
  var dp = $("k3-dp"); dp.innerHTML = h;
  $("k3-dpx").onclick = function () { setPanel(false); };
  dp.querySelectorAll("[data-a]").forEach(function (b) { b.onclick = function () { var a = b.dataset.a; if (a === "add") addModal(ds); else if (a === "day") dayModal(ds); else openEditor(ds, null, a); }; });
  bindItems(dp, ds);
}
function bindItems(scope, ds) {
  scope.querySelectorAll("[data-sid]").forEach(function (el) { el.onclick = function (ev) { ev.stopPropagation(); sesModal(+el.dataset.sid); }; });
  scope.querySelectorAll("[data-eid]").forEach(function (el) { el.onclick = function (ev) { ev.stopPropagation(); var e = findEntry(+el.dataset.eid); if (e) openEditor(ds || el.closest("[data-day]").dataset.day, e); }; });
}

/* ---------- rysowanie ---------- */
async function render() {
  var f = new Date(Y, M, 1, 12), l = new Date(Y, M + 1, 0, 12), m0 = monday(f), m1 = monday(l), s = iso(m0), e = iso(addD(m1, 6));
  if (SEL < s || SEL > e) SEL = (today >= s && today <= e) ? today : iso(f);
  BIG = iso(monday(P(SEL))); RANGE = [s, e];
  $("k3-lbl").textContent = MON[M] + " " + Y;
  var weeks = []; for (var x = m0; x <= m1; x = addD(x, 7)) weeks.push(iso(x));
  var res;
  /* tygodnie PO KOLEI: rownolegle GET /week robily wyscig w OPS.calendar_changed (duble zmian 'aktualizacja') */
  var wkSeq = weeks.reduce(function (pr, k) { return pr.then(function (acc) { return loadWeek(k).then(function (w) { acc.push(w); return acc; }); }); }, Promise.resolve([]));
  try { res = await Promise.all([loadCal(s, e), loadWx(s, e), loadSch(s, e), wkSeq]); }
  catch (err) { $("k3-grid").innerHTML = '<div class="empty">Błąd: ' + qEsc(err.message) + "</div>"; return; }
  C = res[0] || {}; X = res[1] || {}; W = {}; weeks.forEach(function (k, i) { W[k] = (res[3] || [])[i] || {}; });
  entryRoutes = {}; (C.entry_routes || []).forEach(function (r) { entryRoutes[r.entry_id + "|" + r.day] = { route_id: r.route_id, route_name: r.route_name }; });
  sched = {}; ((res[2] || {}).items || []).forEach(function (r) { sched[r.entry_id + "|" + r.day] = r; });
  var g = "", mR = 0, mKm = 0, mX = 0;
  weeks.forEach(function (k) { var a = P(k), big = (k === BIG), st = weekStats(k);
    g += '<div class="wrow' + (big ? " big" : "") + '"><div class="wlab" data-wk="' + k + '"><b>' + dm(a) + "–" + dm(addD(a, 6)) + "</b>" + (st.nr ? st.nr + " tren.<br>" + qN(st.km, 0) + " km<br>XSS " + qN(st.rx, 0) : "bez treningów") + "</div>";
    for (var i = 0; i < 7; i++) { var d = addD(a, i); g += big ? bigCell(d, d.getMonth() === M) : compactCell(d, d.getMonth() === M);
      if (d.getMonth() === M) rides(iso(d)).forEach(function (r) { mR++; if (isCyc(r.sport)) mKm += (r.dist_km || 0); mX += (r.xss || 0); }); }
    g += "</div>"; });
  var grid = $("k3-grid"); grid.innerHTML = g;
  $("k3-msum").innerHTML = "<b>" + mR + "</b> treningów · <b>" + qN(mKm, 0) + "</b> km rowerem · XSS <b>" + qN(mX, 0) + "</b>";
  drawTop(); if (PANEL) showDay(SEL); setPanel(PANEL);
  grid.querySelectorAll(".wrow.big [data-day]").forEach(function (el) { bindItems(el, el.dataset.day); });
  grid.querySelectorAll("[data-day]").forEach(function (el) { el.onclick = function () { var ds = el.dataset.day;
    if (PANEL && ds === SEL) { setPanel(false); return; }   /* ponowne klikniecie wybranego dnia chowa panel */
    SEL = ds; PANEL = true;
    if (iso(monday(P(ds))) === BIG) { grid.querySelectorAll(".sel").forEach(function (z) { z.classList.remove("sel"); }); el.classList.add("sel"); showDay(ds); setPanel(true); } else render();
    if (window.innerWidth <= 1300) setTimeout(function () { $("k3-dp").scrollIntoView({ behavior: "smooth", block: "start" }); }, 50); }; });
  grid.querySelectorAll("[data-wk]").forEach(function (el) { el.onclick = function () { SEL = el.dataset.wk; render(); }; });
}
function refresh(force) { if (force) invalidate(); return render(); }

/* ---------- okna (wspolna ramka .km) ---------- */
function mOpen(html) { $("km").innerHTML = html; $("km-scrim").classList.add("on"); $("km").classList.add("on"); }
var ED = null;
function closeEditor() { $("km-scrim").classList.remove("on"); $("km").classList.remove("on"); ED = null; }
function mHead(t) { return '<div class="km-head"><span class="kt">' + t + '</span><button class="km-x" id="km-x" type="button" aria-label="Zamknij">✕</button></div>'; }

/* trening: szczegoly i akcje (jak w Trenerze) */
function sesModal(id) {
  var x = sesById(id); if (!x) { toast("Tego treningu już nie ma w planie", true); return; }
  var fut = x.day >= today, canEd = fut && x.status === "plan", d = P(x.day);
  var st = { plan: "w planie", done: "✓ zrobione", skip: "pominięte" }[x.status] || x.status;
  var det = x.details && x.details.text ? x.details.text : "";
  var h = mHead((AIC[x.sport] || "") + " " + qEsc(x.name)) + '<div class="km-body"><div class="sub">' + DNL[d.getDay()] + " " + dm(d) + " · " + (x.start_time || "—") + " · " + x.dur_min + "′" + (x.cut ? " (minimum)" : "") + " · " + st + (x.xss ? " · ~" + Math.round(x.xss) + " XSS" : "") + "</div>";
  if (det || x.note) h += '<div class="det">' + qEsc(det) + (x.note ? (det ? "\n\n" : "") + "📝 " + qEsc(x.note) : "") + "</div>";
  if (x.sport === "sila" && x.details && x.details.engine) h += '<p><a class="link" href="/sciaga.html?id=' + x.id + '">📄 Ściąga z grafikami i PDF</a></p>';
  if (canEd) {
    var days = ""; for (var k = 0; k < 7; k++) { var dd = addD(monday(d), k), di = iso(dd); if (di >= today && di !== x.day) days += '<option value="' + di + '">' + DNL[dd.getDay()] + " " + dm(dd) + "</option>"; }
    h += '<div class="g2"><button type="button" data-sa="done">✓ Zrobione</button>' + (x.min_min && x.min_min < x.dur_min ? '<button type="button" data-sa="cut">⏱ Minimum ' + x.min_min + "′</button>" : "") + '<button type="button" data-sa="skip">✕ Pomiń</button><button type="button" class="bad" data-sa="del">🗑 Usuń</button></div>' +
      '<div class="row2"><div><label>Godzina</label><input type="time" id="k3-st" value="' + qEsc(x.start_time || "") + '"></div><div><label>Czas (min)</label><input type="text" inputmode="numeric" id="k3-sd" value="' + x.dur_min + '"></div></div>' +
      '<label>Przenieś na</label><select id="k3-sm"><option value="">— wybierz dzień —</option>' + days + "</select>" +
      '<label>Zamień na</label><select id="k3-ss"><option value="">— wybierz —</option>' + ACT.filter(function (a) { return a[0] !== x.sport; }).map(function (a) { return '<option value="' + a[0] + '">' + a[1] + " " + a[2] + "</option>"; }).join("") + "</select>";
  } else if (fut && x.status !== "plan") h += '<div class="g2"><button type="button" data-sa="undo">↺ Przywróć do planu</button></div>';
  h += '<div class="km-err" id="km-err"></div></div><div class="km-foot"><button type="button" id="km-cancel">Zamknij</button></div>';
  mOpen(h);
  $("km-x").onclick = closeEditor; $("km-cancel").onclick = closeEditor;
  function put(b, msg) { api("PUT", "/sessions/" + x.id, b).then(function () { toast(msg || "Zapisano"); closeEditor(); refresh(true); }).catch(function (e) { edErr(e.message); }); }
  $("km").querySelectorAll("[data-sa]").forEach(function (b) { b.onclick = function () { var a = b.dataset.sa;
    if (a === "done") put({ status: "done" }, "Zrobione");
    else if (a === "skip") put({ status: "skip" }, "Pominięte");
    else if (a === "undo") put({ status: "plan", cut: false, note: (x.note || "").indexOf("usunięte przez Ciebie") === 0 ? null : x.note }, "Przywrócone");
    else if (a === "cut") put({ dur_min: x.min_min, cut: true }, "Wersja minimum");
    else if (a === "del") { if (!confirm("Usunąć „" + x.name + "” z planu?")) return;
      var p = (x.note || "").indexOf("dodane przez Ciebie") === 0 ? api("DELETE", "/sessions/" + x.id) : api("PUT", "/sessions/" + x.id, { status: "skip", note: "usunięte przez Ciebie" });
      p.then(function () { toast("Usunięto"); closeEditor(); refresh(true); }).catch(function (e) { edErr(e.message); }); } }; });
  var stI = $("k3-st"); if (stI) stI.onchange = function () { if (stI.value) put({ start_time: stI.value }, "Godzina zmieniona"); };
  var sd = $("k3-sd"); if (sd) sd.onchange = function () { var v = parseInt(sd.value, 10); if (v >= 5) put({ dur_min: v, min_min: Math.min(x.min_min || v, v) }, "Czas zmieniony"); };
  var sm = $("k3-sm"); if (sm) sm.onchange = function () { if (sm.value) put({ day: sm.value }, "Przeniesione"); };
  var ss = $("k3-ss"); if (ss) ss.onchange = function () { var k = ss.value; if (!k) return;
    put({ sport: k, name: DEF[k][0], zone: k === "rower" ? 2 : null, is_long: false, dur_min: k === "joga" ? Math.min(x.dur_min, 30) : Math.min(x.dur_min, k === "rower" ? 120 : 45), min_min: DEF[k][3] }, "Zamienione"); };
}
function addModal(ds) {
  var d = P(ds), h = mHead("＋ Trening · " + DNL[d.getDay()] + " " + dm(d)) + '<div class="km-body"><div class="list">' +
    ACT.map(function (a) { var x = DEF[a[0]]; return '<button type="button" class="li" data-add="' + a[0] + '"><span class="ic">' + a[1] + "</span><span>" + a[2] + "<small>" + x[1] + " · " + x[2] + "′ — godzinę i czas zmienisz potem</small></span></button>"; }).join("") +
    '</div><div class="km-err" id="km-err"></div></div><div class="km-foot"><button type="button" id="km-cancel">Anuluj</button></div>';
  mOpen(h); $("km-x").onclick = closeEditor; $("km-cancel").onclick = closeEditor;
  $("km").querySelectorAll("[data-add]").forEach(function (b) { b.onclick = function () { var k = b.dataset.add, x = DEF[k];
    api("POST", "/sessions", { day: ds, sport: k, note: "dodane przez Ciebie", name: x[0], start_time: x[1], dur_min: x[2], min_min: x[3], zone: k === "rower" ? 2 : null })
      .then(function (r) { toast("Dodano"); invalidate(); render().then(function () { if (r && r.id) sesModal(r.id); else closeEditor(); }); }).catch(function (e) { edErr(e.message); }); }; });
}
function dayModal(ds) {
  var d = P(ds), A = [["rest", "😴", "REST DAY", "dzień wolny — Trener przełoży trening"], ["short", "⏱", "Brak czasu", "dziś wersje minimum"], ["ill", "🤒", "Choroba", "dzień pusty + 2 dni lżej"], ["del", "🧳", "Delegacja", "tylko krótka joga hotelowa"], ["clear", "↺", "Zwykły dzień", "usuń powyższe ustawienia dnia"]];
  var h = mHead("✎ Ustaw dzień · " + DNL[d.getDay()] + " " + dm(d)) + '<div class="km-body"><div class="sub">Plan Trenera przeliczy się sam; zmianę możesz cofnąć.</div><div class="list">' +
    A.map(function (a) { return '<button type="button" class="li" data-da="' + a[0] + '"><span class="ic">' + a[1] + "</span><span>" + a[2] + "<small>" + a[3] + "</small></span></button>"; }).join("") +
    '</div><div class="km-err" id="km-err"></div></div><div class="km-foot"><button type="button" id="km-cancel">Anuluj</button></div>';
  mOpen(h); $("km-x").onclick = closeEditor; $("km-cancel").onclick = closeEditor;
  $("km").querySelectorAll("[data-da]").forEach(function (b) { b.onclick = function () { api("POST", "/week/action", { day: ds, action: b.dataset.da }).then(function () { toast("Zapisano — możesz cofnąć"); closeEditor(); refresh(true); }).catch(function (e) { edErr(e.message); }); }; });
}

/* ---------- EDYTOR WPISOW KALENDARZA (port z kalendarz2-data.js v6) ---------- */
var ROUTES = null, MGROUPS = null;
var COLORS = [["", "auto"], ["#3f6f9a", "niebieski"], ["#3f7a4d", "zielony"], ["#a63d3d", "czerwony"], ["#c77c3a", "pomarańcz"], ["#7a5ea8", "fiolet"], ["#6b7076", "szary"]];
var TYPES = [["jazda", "🚴 Jazda"], ["event", "📅 Wydarzenie"], ["rest", "😴 Rest day"], ["urlop", "🏖️ Urlop"], ["delegacja", "💼 Delegacja"], ["illness", "🤒 Choroba"], ["feel", "😊 Samopoczucie"], ["reminder", "🔔 Przypomnienie"]];
function tkeyOf() { if (ED.kind === "event") return ED.event_type || "event"; return ED.kind; }
function openEditor(day, entry, presetKind) {
  ED = { day: day, id: entry ? entry.id : null, kind: entry ? entry.kind : (presetKind === "event" ? "event" : presetKind), event_type: entry ? (entry.event_type || "") : "", entry: entry || null };
  if (!entry && presetKind && ["rest", "urlop", "delegacja"].indexOf(presetKind) >= 0) { ED.kind = "event"; ED.event_type = presetKind; }
  renderEditor(); $("km-scrim").classList.add("on"); $("km").classList.add("on");
}
function setType(tk) { if (tk === "illness" || tk === "feel" || tk === "reminder") { ED.kind = tk; ED.event_type = ""; } else { ED.kind = "event"; ED.event_type = (tk === "event" ? "" : tk); } renderEditor(); }
function sevOpts(sel) { return ["lekka", "średnia", "ciężka"].map(function (s) { return "<option" + (s === sel ? " selected" : "") + ">" + s + "</option>"; }).join(""); }
function offOpts(sel) { sel = String(sel || "0"); return [["0", "o czasie"], ["60", "1 h przed"], ["240", "4 h przed"], ["480", "8 h przed"]].map(function (x) { return '<option value="' + x[0] + '"' + (x[0] === sel ? " selected" : "") + ">" + x[1] + "</option>"; }).join(""); }
function swatches(sel) { return '<div class="km-sw" id="km-sw">' + COLORS.map(function (c) { return '<button type="button" data-c="' + c[0] + '"' + (c[0] === sel ? ' class="on"' : "") + ' title="' + c[1] + '" style="' + (c[0] ? ("background:" + c[0]) : "background:transparent;border-color:var(--line);color:var(--ink2);font-size:9px") + '">' + (c[0] ? "" : "auto") + "</button>"; }).join("") + "</div>"; }
function selColor() { var w = $("km-sw"); if (!w) return ""; var on = w.querySelector("button.on"); return on ? on.dataset.c : ""; }
function fieldsFor(tk) {
  var e = ED.entry || {};
  if (tk === "feel") { var fv = (e.feel != null ? e.feel : 0);
    return '<div style="text-align:center"><div style="font-size:20px;font-weight:700;margin-bottom:4px" id="km-fv">' + FEEL_LABEL[String(fv)] + '</div><input type="range" id="km-feel" min="-2" max="2" step="1" value="' + fv + '" style="width:100%"><div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted)"><span>fatalnie</span><span>świetnie</span></div></div><label>Notatka</label><textarea id="km-note">' + qEsc(e.note || "") + "</textarea>"; }
  if (tk === "illness") return '<label>Opis</label><input type="text" id="km-title" maxlength="200" placeholder="np. katar, gorączka" value="' + qEsc(e.title || "") + '"><div class="row2"><div><label>Nasilenie</label><select id="km-sev">' + sevOpts(e.severity) + '</select></div><div><label>Do (opcjonalnie)</label><input type="date" id="km-end" value="' + qEsc(e.end_day && e.end_day !== e.day ? e.end_day : "") + '"></div></div><label>Notatka</label><textarea id="km-note">' + qEsc(e.note || "") + "</textarea>";
  if (tk === "reminder") return '<label>Tytuł</label><input type="text" id="km-title" maxlength="200" placeholder="np. wymień łańcuch" value="' + qEsc(e.title || "") + '"><div class="row2"><div><label>Godzina</label><input type="time" id="km-time" value="' + (e.at_time ? e.at_time.slice(0, 5) : "") + '"></div><div><label>Przypomnij</label><select id="km-off">' + offOpts(e.remind_offsets) + '</select></div></div><label>Notatka</label><textarea id="km-note">' + qEsc(e.note || "") + "</textarea>";
  if (tk === "jazda") { var _n = String(e.note || ""), _mk = _n.match(/(?:^|\s·\s)([0-9]+(?:[.,][0-9]+)?)\s*km\s*$/), _km = _mk ? _mk[1] : "", _nt = _mk ? _n.slice(0, _mk.index).trim() : _n;
    return '<label>Tytuł</label><input type="text" id="km-title" maxlength="200" placeholder="np. kółko z Adamem" value="' + qEsc(e.title || "") + '"><div class="row2"><div><label>Start (opcjonalnie)</label><input type="time" id="km-time" value="' + (e.at_time ? e.at_time.slice(0, 5) : "") + '"></div><div><label>Dystans km (opcjonalnie)</label><input type="text" inputmode="decimal" id="km-km" placeholder="np. 60" value="' + qEsc(_km) + '"></div></div><label>Do (dzień końcowy, opcjonalnie)</label><input type="date" id="km-end" value="' + qEsc(e.end_day && e.end_day !== e.day ? e.end_day : "") + '"><label>Kolor</label>' + swatches(e.color || "") + '<label>Notatka</label><textarea id="km-note">' + qEsc(_nt) + '</textarea><div style="font-size:12px;color:var(--muted);margin-top:6px">Jazda liczy się do prognozy formy; z dystansu szacuję obciążenie. Trasę możesz przypiąć po zapisaniu.</div>'; }
  return '<label>Tytuł' + (tk === "rest" ? " (opcjonalnie)" : "") + '</label><input type="text" id="km-title" maxlength="200" placeholder="' + (tk === "urlop" ? "Urlop" : tk === "delegacja" ? "Delegacja" : tk === "rest" ? "Rest day" : "np. wyścig") + '" value="' + qEsc(e.title || "") + '"><label>Do (dzień końcowy, opcjonalnie)</label><input type="date" id="km-end" value="' + qEsc(e.end_day && e.end_day !== e.day ? e.end_day : "") + '"><label>Kolor</label>' + swatches(e.color || "") + '<label>Notatka</label><textarea id="km-note">' + qEsc(e.note || "") + "</textarea>";
}
function schedTxt(sc) { return ({ pending: "czeka 06:00", running: "wysyłam…", sent: "wysłano", partial: "część nie doszła", failed: "błąd" })[sc.status] || sc.status; }
function routeMailSection() {
  if (!(ED.id && ED.kind === "event")) return (ED.kind === "event" ? '<div class="km-sec"><div class="sh">Trasa / mail</div><div style="font-size:12.5px;color:var(--muted)">Zapisz wydarzenie, aby przypiąć trasę i wysyłkę maila.</div></div>' : "");
  var rr = entryRoutes[ED.id + "|" + ED.day];
  var cur = rr ? ('<div class="km-cur">🧭 <b>' + qEsc(rr.route_name || rr.route_id) + '</b> <a class="link" href="/raport-trasy.html?route=' + encodeURIComponent(rr.route_id) + '" target="_blank">analiza</a> <button type="button" id="km-rdet" class="km-x" style="width:24px;height:24px;font-size:12px">✕</button></div>') : "";
  var sc = sched[ED.id + "|" + ED.day], mailst = sc ? ('<span class="km-mailst" style="color:var(--good)">' + schedTxt(sc) + "</span>") : "";
  return '<div class="km-sec"><div class="sh">Trasa dnia</div>' + cur + '<select id="km-route"><option value="">' + (rr ? "— zmień trasę —" : "— wybierz trasę —") + '</option></select></div><div class="km-sec"><div class="sh">Raport mailem (06:00)</div><select id="km-group"><option value="">— nie wysyłaj —</option></select> ' + mailst + "</div>";
}
function renderEditor() {
  var tk = tkeyOf(), editing = !!ED.id;
  var chips = TYPES.map(function (t) { var on = (t[0] === tk), dis = false;
    if (editing) { var ek = ED.entry.kind; if (ek === "event") dis = (["jazda", "event", "rest", "urlop", "delegacja"].indexOf(t[0]) < 0); else dis = (t[0] !== ek); }
    return '<button type="button" data-tk="' + t[0] + '"' + (on ? ' class="on"' : "") + (dis ? " disabled" : "") + ">" + t[1] + "</button>"; }).join("");
  $("km").innerHTML = mHead((editing ? "Edytuj" : "Dodaj") + " · " + qEsc(ED.day)) + '<div class="km-body"><div class="km-types">' + chips + '</div><div id="km-fields">' + fieldsFor(tk) + '</div><div class="km-err" id="km-err"></div>' + routeMailSection() + "</div>" +
    '<div class="km-foot">' + (editing ? '<button type="button" class="del" id="km-del">Usuń</button>' : "") + '<button type="button" id="km-cancel">Anuluj</button><button type="button" class="save" id="km-save">Zapisz</button></div>';
  wireEditor();
}
function edErr(m) { var e = $("km-err"); if (e) e.textContent = m || ""; }
function wireEditor() {
  var m = $("km");
  m.querySelectorAll(".km-types button").forEach(function (b) { if (!b.disabled) b.onclick = function () { setType(b.dataset.tk); }; });
  $("km-x").onclick = closeEditor; $("km-cancel").onclick = closeEditor; $("km-save").onclick = saveEditor;
  var del = $("km-del"); if (del) del.onclick = deleteEditor;
  var fe = $("km-feel"); if (fe) fe.oninput = function () { $("km-fv").textContent = FEEL_LABEL[String(fe.value)]; };
  var sw = $("km-sw"); if (sw) sw.querySelectorAll("button").forEach(function (b) { b.onclick = function () { sw.querySelectorAll("button").forEach(function (x) { x.classList.remove("on"); }); b.classList.add("on"); }; });
  if (ED.id && ED.kind === "event") {
    ensureRoutes().then(function (rts) { var sel = $("km-route"); if (!sel) return; rts.forEach(function (r) { var o = document.createElement("option"); o.value = r.route_id; o.textContent = r.name + (r.distance_km ? (" · " + r.distance_km + " km") : ""); sel.appendChild(o); }); sel.onchange = function () { if (sel.value) setRoute(sel.value, routeName(sel.value)); }; });
    var rdet = $("km-rdet"); if (rdet) rdet.onclick = function () { setRoute("", null); };
    ensureGroups().then(function (gs) { var sel = $("km-group"); if (!sel) return; var sc = sched[ED.id + "|" + ED.day]; gs.forEach(function (g) { var o = document.createElement("option"); o.value = g.id; o.textContent = g.name + " (" + (g.members ? g.members.length : 0) + ")"; if (sc && sc.group_id === g.id) o.selected = true; sel.appendChild(o); }); if (!gs.length) { sel.disabled = true; sel.options[0].textContent = "— brak grup —"; } sel.onchange = function () { setSchedule(sel.value ? parseInt(sel.value, 10) : null); }; });
  }
}
async function saveEditor() {
  var tk = tkeyOf(), body = { day: ED.day, kind: ED.kind };
  if (ED.kind === "event") body.event_type = ED.event_type || "";
  var t = $("km-title"); if (t) body.title = t.value.trim();
  var note = $("km-note"); if (note) body.note = note.value.trim();
  if (tk === "feel") { body.feel = parseInt($("km-feel").value, 10); body.title = FEEL_LABEL[String(body.feel)]; }
  if (tk === "illness") { var sv = $("km-sev"); if (sv) body.severity = sv.value; }
  if (tk === "reminder") { var tm = $("km-time"); if (tm && tm.value) body.at_time = tm.value; var off = $("km-off"); if (off) body.remind_offsets = off.value; }
  if (tk === "jazda") { var _t = $("km-time"); if (_t && _t.value) body.at_time = _t.value; var _k = $("km-km"), _kv = _k ? String(_k.value || "").trim().replace(".", ",") : "";
    if (_kv && /^[0-9]+(,[0-9]+)?$/.test(_kv)) body.note = ((body.note || "") + (body.note ? " · " : "") + _kv + " km"); }
  var end = $("km-end"); if (end && end.value) body.end_day = end.value;
  if (ED.kind === "event") body.color = selColor();
  try { if (ED.id) { body.id = ED.id; await post("/api/calendar/edit", body); } else await post("/api/calendar/entry", body); closeEditor(); toast("Zapisano"); refresh(true); }
  catch (err) { edErr("Nie zapisano: " + err.message); }
}
async function deleteEditor() { if (!ED.id) return; try { await post("/api/calendar/delete", { id: ED.id }); closeEditor(); toast("Usunięto"); refresh(true); } catch (err) { edErr("Nie usunięto: " + err.message); } }
async function setRoute(rid, nm) { var id = ED.id, day = ED.day; try { await post("/api/calendar/route", { entry_id: id, day: day, route_id: rid, route_name: nm }); invalidate(); await render(); var e = findEntry(id); if (e) openEditor(day, e); } catch (err) { edErr(err.message); } }
async function setSchedule(gid) { var id = ED.id, day = ED.day;
  try { if (!gid) { var sc = sched[id + "|" + day]; if (sc) await fetch("/api/report/schedule/" + sc.id, { method: "DELETE", credentials: "same-origin" }); }
    else await post("/api/report/schedule", { entry_id: id, day: day, group_id: gid, all_days: false });
    invalidate(); await render(); var e = findEntry(id); if (e) openEditor(day, e); } catch (err) { edErr(err.message); } }
function ensureRoutes() { if (ROUTES) return Promise.resolve(ROUTES); return getJ("/api/routes/ready").then(function (j) { ROUTES = (j.routes || []); return ROUTES; }); }
function routeName(rid) { var x = (ROUTES || []).filter(function (r) { return String(r.route_id) === String(rid); })[0]; return x ? x.name : null; }
function ensureGroups() { if (MGROUPS) return Promise.resolve(MGROUPS); return getJ("/api/mail-groups").then(function (j) { MGROUPS = (j.items || []); return MGROUPS; }); }

/* ---------- start ---------- */
/* panel dnia: domyslnie schowany (siatka na cala szerokosc), pokazuje sie po kliknieciu dnia; ✕ / Esc / ponowne klikniecie chowa */
$("k3-bp").onclick = function () { M--; if (M < 0) { M = 11; Y--; } render(); };
$("k3-bn").onclick = function () { M++; if (M > 11) { M = 0; Y++; } render(); };
$("k3-bt").onclick = function () { Y = NOW.getFullYear(); M = NOW.getMonth(); SEL = today; render(); };
$("km-scrim").addEventListener("click", closeEditor);
document.addEventListener("keydown", function (e) { if (e.key !== "Escape") return; if ($("km").classList.contains("on")) closeEditor(); else if (PANEL && document.body.classList.contains("tr-month")) setPanel(false); });
var started = false;
window.KAL3 = { refresh: function (force) { if (!started) { started = true; return render(); } return refresh(force); } };
})();
