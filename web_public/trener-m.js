/* trener-m.js — MOBILE (iPhone / iPad): osobny uklad strony Trenera, wzorzec jak Analiza trasy (raport-trasy-m.js).
   Wlacza sie przy ekranie <=820 px albo na dotyku bez myszy (iPad); komputer bez zmian (trener.js). Wymuszenie: ?full=1 (pelna) / ?m=1 (mobilna).
   2026-10-02 v3: ZAKLADKI u gory (Tydzien + dzialy rysowane przez trener.js: window.TRENER_CORE.go), DNI jako zwijane karty
   (podstawowe info: data, samopoczucie emotka, pogoda skrot, treningi w skrocie; po dotknieciu: pelna pogoda jak w Kalendarzu,
   samopoczucie z notatka, zajetosci, treningi), TRENING na caly ekran, EDYCJA DNIA (samopoczucie 🤒…😄 + notatka, REST / choroba /
   brak czasu / delegacja, dodaj trening). Samopoczucie = wpis Kalendarza kind=feel (-2..+2) przez /api/calendar/entry|edit|delete.
   Wstecz z treningu / edycji dnia: okragly przycisk w prawym dolnym rogu albo gest wstecz. Dok.: docs/TRENER.md */
(function () {
  "use strict";
  var Q = "(max-width:820px),(pointer:coarse) and (hover:none)";
  var FORCE = /[?&]m=1/.test(location.search);
  if (/[?&]full=1/.test(location.search) || !(FORCE || (window.matchMedia && window.matchMedia(Q).matches))) return;
  var panel = document.getElementById("p-trener"), root = document.getElementById("trener-root");
  if (!panel || !root) return;
  var CORE_OK = false;
  window.TRENER_M = { ready: function () { CORE_OK = true; } };

  // ---------- narzedzia ----------
  function api(m, p, b) {
    return fetch("/api/trener" + p, { method: m, credentials: "same-origin", headers: b ? { "Content-Type": "application/json" } : {}, body: b ? JSON.stringify(b) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status)); return j; }); });
  }
  function cpost(u, b) { return fetch(u, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }); }
  function esc(t) { return String(t == null ? "" : t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }
  var toastT = null;
  function toast(msg, bad) {
    var el = document.getElementById("tm-toast");
    if (!el) { el = document.createElement("div"); el.id = "tm-toast"; document.body.appendChild(el); }
    el.className = bad ? "bad" : ""; el.textContent = msg; el.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(function () { el.hidden = true; }, bad ? 5000 : 2500);
  }
  function fail(e) { toast("Błąd: " + (e && e.message ? e.message : e), true); }
  var DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"], DNL = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"];
  function D(t) { var p = String(t).slice(0, 10).split("-"); return Date.UTC(+p[0], +p[1] - 1, +p[2]); }
  function iso(ms) { return new Date(ms).toISOString().slice(0, 10); }
  function pl(ms) { var d = new Date(ms); return ("0" + d.getUTCDate()).slice(-2) + "." + ("0" + (d.getUTCMonth() + 1)).slice(-2); }
  var DAY = 864e5, WK = 7 * DAY;
  function todayMs() { var n = new Date(); return Date.UTC(n.getFullYear(), n.getMonth(), n.getDate()); }
  function monday(ms) { return ms - ((new Date(ms).getUTCDay() + 6) % 7) * DAY; }
  function tm(t) { var p = String(t || "").split(":"); return p.length < 2 ? null : (+p[0]) * 60 + (+p[1]); }
  function n1(v) { return v == null ? "—" : (Math.round(v * 10) / 10).toString().replace(".", ","); }
  var ACT = [["rower", "🚲", "Rower"], ["sila", "🏋️", "Siła"], ["wiosl", "🚣", "Wioślarz"], ["joga", "🧘", "Joga"]];
  var AIC = { rower: "🚲", sila: "🏋️", wiosl: "🚣", joga: "🧘" };
  var SCOL = { rower: "#2f9e5b", sila: "#e0802b", wiosl: "#2f7fd1", joga: "#8a63d2" };
  var SPIC = { cycling: "🚲", gravel_cycling: "🚲", yoga: "🧘", indoor_rowing: "🚣", strength_training: "🏋️", walking: "🚶" };
  var DTYPE = { rest: "😴 REST DAY", ill: "🤒 choroba", del: "🧳 delegacja", short: "⏱ brak czasu", trip: "🗺️ wyprawa", urlop: "🏖️ urlop" };
  var CALIC = { rest: "😴", delegacja: "🧳", urlop: "🏖️" }, KIC = { illness: "🤒", reminder: "⏰", event: "📅" };
  var FEEL_E = { "-2": "🤒", "-1": "😕", "0": "😐", "1": "🙂", "2": "😄" }, FEEL_L = { "-2": "fatalnie", "-1": "słabo", "0": "neutralnie", "1": "dobrze", "2": "świetnie" };
  var TABS = [["tydzien", "Tydzień"], ["czas", "Czas"], ["dostep", "Dostępność"], ["cele", "Cele"], ["sezon", "Sezon"], ["bilans", "Bilans i waga"], ["kalib", "Kalibracja"]];
  var DEF = { rower: ["Rower spokojnie", "12:00", 60, 30], sila: ["Siła obwodowa", "10:00", 40, 15], wiosl: ["Wioślarz spokojnie", "16:00", 30, 15], joga: ["Joga", "09:00", 20, 10] };

  var S = { wk: monday(todayMs()), data: null, wx: null, lines: null, ask: null, review: null, autoReview: false, opened: null, open: {}, view: "home", arg: null, tab: "tydzien" };

  // ---------- style ----------
  var css = document.createElement("style");
  css.textContent = [
    "body.tm .wrap{padding:calc(10px + env(safe-area-inset-top,0px)) calc(12px + env(safe-area-inset-right,0px)) calc(96px + env(safe-area-inset-bottom,0px)) calc(12px + env(safe-area-inset-left,0px))}",
    "body.tm .head{padding-left:52px;min-height:44px;align-items:center}",
    "body.tm #trener-root{display:none}body.tm.tm-sec #trener-root{display:block}body.tm.tm-sec #tm{display:none}",
    "body.tm #trener-root .tr-sub{display:none!important}",
    "#tm-tabs{position:sticky;top:0;z-index:50;display:flex;gap:6px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;padding:8px 0 10px;margin:0 0 6px;background:var(--bg)}",
    "#tm-tabs::-webkit-scrollbar{display:none}",
    "#tm-tabs button{flex:0 0 auto;min-height:40px;border:1px solid var(--line);background:var(--well);color:var(--ink);border-radius:999px;padding:6px 16px;font:inherit;font-size:15px;cursor:pointer;white-space:nowrap}",
    "#tm-tabs button.on{border-color:var(--accent);background:var(--accent-bg);color:var(--accent-ink);font-weight:700}",
    "#tm{font-size:16px}#tm button,#tm-view button{font:inherit;cursor:pointer;-webkit-tap-highlight-color:transparent}",
    ".tm-top{display:flex;align-items:center;gap:8px;margin-bottom:8px}.tm-top .tt{flex:1;min-width:0;text-align:center}",
    ".tm-top .tt b{display:block;font-size:17px}.tm-top .tt span{font-size:13px;color:var(--ink2)}",
    ".tm-rb{width:44px;height:44px;flex:0 0 44px;border-radius:50%;border:1px solid var(--line);background:var(--card);color:var(--ink);font-size:22px!important;line-height:1}",
    ".tm-acts{display:flex;gap:8px;margin-bottom:10px}.tm-acts button{flex:1}",
    ".tm-b{min-height:44px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:10px;padding:8px 12px;font-size:15px!important}",
    ".tm-b.pri{background:var(--accent);border-color:var(--accent);color:#fff}.tm-b.bad{color:var(--bad)}.tm-b:disabled{opacity:.5}",
    ".tm-bar{height:8px;border-radius:4px;background:var(--line);overflow:hidden;position:relative;margin:2px 0 10px}.tm-bar i{position:absolute;top:0;bottom:0;left:0}",
    ".tm-note{border-left:3px solid var(--accent);background:var(--accent-bg);border-radius:8px;padding:10px 12px;font-size:14.5px;line-height:1.45;margin:0 0 8px}",
    ".tm-note.w{border-color:var(--warn);background:var(--warn-bg)}.tm-note.b{border-color:var(--bad);background:var(--bad-bg)}",
    ".tm-note ul{margin:6px 0 8px 18px;padding:0}.tm-note .tm-b{margin-top:8px;margin-right:6px}",
    ".tm-sub{font-size:13px;color:var(--muted)}",
    ".tm-box{border:1px solid var(--line);border-radius:12px;background:var(--card);padding:12px;margin:0 0 10px}",
    ".tm-box textarea{display:block;width:100%;margin:8px 0;font:inherit;font-size:16px;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:8px;padding:8px 10px;resize:vertical}",
    "details.tm-box>summary{list-style:none;font-weight:700;min-height:28px;display:flex;align-items:center;justify-content:space-between}details.tm-box>summary::-webkit-details-marker{display:none}",
    "details.tm-box>summary::after{content:'▾';color:var(--muted)}details.tm-box:not([open])>summary::after{content:'▸'}",
    /* karty dni */
    ".tm-day{border:1px solid var(--line2);border-radius:14px;background:var(--card);margin:0 0 12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);scroll-margin-top:70px}",
    ".tm-day.today{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent)}.tm-day.past{opacity:.78}",
    ".tm-dhd{display:flex;align-items:stretch;gap:12px;width:100%;border:0;background:none;color:var(--ink);text-align:left;padding:10px 12px;min-height:64px}",
    ".tm-dt{flex:0 0 52px;border-radius:10px;background:var(--well);display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.1}",
    ".tm-dt b{font-size:15px;text-transform:uppercase}.tm-dt small{font-size:12.5px;color:var(--ink2)}",
    ".tm-day.we .tm-dt{background:var(--accent-bg)}.tm-day.today .tm-dt{background:var(--accent);color:#fff}.tm-day.today .tm-dt small{color:#fff}",
    ".tm-dm2{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px;justify-content:center}",
    ".tm-l1{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:16px;font-weight:700}.tm-l1 .fe{font-size:20px;line-height:1}",
    ".tm-l1 .td{font-size:12px;font-weight:700;color:#fff;background:var(--accent);border-radius:999px;padding:1px 8px}",
    ".tm-l1 .ty{font-size:12.5px;font-weight:600;color:var(--accent-ink);background:var(--accent-bg);border-radius:999px;padding:1px 8px}",
    ".tm-l2{font-size:13.5px;color:var(--ink2)}.tm-l2.bad{color:var(--bad);font-weight:700}",
    ".tm-l3{display:flex;gap:5px;flex-wrap:wrap}.tm-l3 i{font-style:normal;font-size:13px;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:6px;padding:1px 6px;background:var(--well);white-space:nowrap}",
    ".tm-l3 i.dn{background:var(--good-bg);border-color:var(--good)}.tm-l3 i.sk{opacity:.5;text-decoration:line-through}.tm-l3 .fr{font-size:13px;color:var(--muted)}",
    ".tm-ar{align-self:center;color:var(--muted);font-size:20px;flex:0 0 auto}",
    ".tm-dbody{border-top:1px dashed var(--line2);padding:8px 12px 12px;background:var(--well)}",
    ".tm-wx{font-size:14px;color:var(--ink2);margin:2px 0 6px;line-height:1.4}.tm-wx.bad{color:var(--bad);font-weight:700}.tm-wx .src{color:var(--muted);font-weight:400}",
    ".tm-feel{display:flex;gap:10px;align-items:flex-start;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 10px;margin:6px 0 0;font-size:14.5px}.tm-feel .fe{font-size:24px;line-height:1}",
    ".tm-it{display:flex;align-items:center;gap:10px;width:100%;min-height:52px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:10px;padding:8px 10px;margin:6px 0 0;text-align:left;font-size:15.5px!important}",
    ".tm-it .ic{font-size:22px;width:28px;text-align:center;flex:0 0 28px}.tm-it .tx{flex:1;min-width:0}.tm-it .tx small{display:block;font-size:13px;color:var(--muted)}",
    ".tm-it .ch{color:var(--muted);font-size:22px}.tm-it.ses{border-left:5px solid var(--accent)}.tm-it.skip{opacity:.5}.tm-it.skip .tx b{text-decoration:line-through}",
    ".tm-it.done{background:var(--good-bg);border-color:var(--good)}.tm-it.busy{min-height:38px;background:transparent;border-style:dashed;color:#c9544a;font-size:14px!important}",
    ".tm-it.cal{min-height:38px;background:var(--accent-bg);border-color:transparent;color:var(--accent-ink);font-size:14px!important}",
    ".tm-ed{margin-top:10px;width:100%}",
    ".tm-empty{color:var(--muted);font-size:14px;padding:6px 0 2px}",
    ".tm-row{display:flex;align-items:center;gap:12px;width:100%;min-height:56px;padding:6px 2px;border:0;border-bottom:1px solid var(--line);background:none;color:var(--ink);text-align:left;font-size:16px!important}",
    ".tm-row .ic{font-size:22px;width:30px;text-align:center}.tm-row .tx{flex:1;min-width:0}.tm-row .tx small{display:block;font-size:13px;color:var(--muted)}.tm-row .ch{color:var(--muted);font-size:22px}",
    ".tm-fg{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin:6px 0 8px}",
    ".tm-fg button{display:flex;flex-direction:column;align-items:center;gap:2px;min-height:72px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:12px;padding:6px 2px;font-size:12.5px!important}",
    ".tm-fg button span{font-size:30px;line-height:1.1}.tm-fg button.on{border:2px solid var(--accent);background:var(--accent-bg);font-weight:700}",
    ".tm-fin{min-height:44px;font:inherit;font-size:16px!important;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:10px;padding:6px 10px;width:100%}",
    "#tm-view{display:none;position:fixed;inset:0;z-index:1200;background:var(--bg);overflow-y:auto;-webkit-overflow-scrolling:touch;padding:calc(14px + env(safe-area-inset-top,0px)) calc(16px + env(safe-area-inset-right,0px)) calc(100px + env(safe-area-inset-bottom,0px)) calc(16px + env(safe-area-inset-left,0px));font-size:16px}",
    "body.tm-ov #tm-view{display:block}body.tm-ov{overflow:hidden}",
    ".tm-vh{display:flex;gap:12px;align-items:flex-start;margin-bottom:12px}.tm-vh .ic{font-size:34px}.tm-vh b{font-size:20px;display:block}",
    ".tm-det{white-space:pre-line;line-height:1.55;font-size:15.5px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:0 0 12px}",
    ".tm-g2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:0 0 12px}",
    ".tm-f{display:grid;grid-template-columns:110px 1fr;gap:8px 10px;align-items:center;margin:0 0 12px}.tm-f span{font-size:14px;color:var(--ink2)}",
    ".tm-f input,.tm-f select,.tm-rate input{min-height:44px;font:inherit;font-size:16px!important;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:10px;padding:6px 10px;width:100%}",
    ".tm-rate{margin:4px 0 12px}.tm-rate .st{display:flex;gap:4px;margin:4px 0 8px}.tm-rate .st button{border:0;background:none;font-size:36px!important;line-height:1;padding:0 4px}",
    ".tm-h3{font-size:14px;font-weight:700;color:var(--ink2);margin:14px 0 4px;text-transform:uppercase;letter-spacing:.03em}",
    "#tm-fab{display:none;position:fixed;z-index:1230;right:calc(14px + env(safe-area-inset-right,0px));bottom:calc(14px + env(safe-area-inset-bottom,0px));gap:10px;flex-direction:row-reverse}",
    "body.tm-ov #tm-fab{display:flex}",
    "#tm-fab button{width:52px;height:52px;border-radius:50%;border:1px solid var(--line);background:color-mix(in srgb,var(--card) 92%,transparent);color:var(--ink);font-size:24px;box-shadow:0 2px 12px rgba(0,0,0,.3);padding:0;cursor:pointer}",
    "body.tm-ov .qnav-fab{display:none!important}",
    "#tm-toast{position:fixed;left:12px;right:12px;bottom:calc(76px + env(safe-area-inset-bottom,0px));z-index:1300;background:var(--card);border:1px solid var(--good);color:var(--good);border-radius:12px;padding:10px 14px;font-size:15px;text-align:center;box-shadow:0 4px 16px rgba(0,0,0,.25)}",
    "#tm-toast.bad{border-color:var(--bad);color:var(--bad)}",
    "@media(max-width:820px){#tm-tabs{margin-left:-12px;margin-right:-12px;padding-left:12px;padding-right:12px}}",
    "@media(min-width:700px){#tm,#tm-view>div{max-width:720px;margin-left:auto;margin-right:auto}#tm-toast{max-width:520px;margin:0 auto}}"
  ].join("\n");
  document.head.appendChild(css);
  document.body.classList.add("tm");

  var tabs = document.createElement("div"); tabs.id = "tm-tabs";
  var tmEl = document.createElement("div"); tmEl.id = "tm";
  panel.insertBefore(tabs, root); panel.insertBefore(tmEl, root);
  var view = document.createElement("div"); view.id = "tm-view"; document.body.appendChild(view);
  var fab = document.createElement("div"); fab.id = "tm-fab";
  fab.innerHTML = "<button type='button' id='tm-back' aria-label='Wstecz'>‹</button>";
  document.body.appendChild(fab);
  document.getElementById("tm-back").onclick = function () { history.back(); };
  function drawTabs() {
    tabs.innerHTML = TABS.map(function (t) { return "<button type='button' data-tab='" + t[0] + "' class='" + (S.tab === t[0] ? "on" : "") + "'>" + t[1] + "</button>"; }).join("");
    tabs.querySelectorAll("[data-tab]").forEach(function (b) { b.onclick = function () { var t = b.dataset.tab; if (t === S.tab && t !== "tydzien") return;
      history.replaceState({ tm: t === "tydzien" ? "home" : "sec", arg: t }, ""); show(t === "tydzien" ? "home" : "sec", t); }; });
    var on = tabs.querySelector(".on"); if (on && on.scrollIntoView) on.scrollIntoView({ inline: "center", block: "nearest" });
  }

  // ---------- nawigacja ----------
  function enter(v, arg) { history.pushState({ tm: v, arg: arg }, ""); show(v, arg); }
  function show(v, arg) {
    var prev = S.view;
    S.view = v; S.arg = arg;
    if (v === "home") S.tab = "tydzien"; else if (v === "sec") S.tab = arg;
    document.body.classList.toggle("tm-ov", v === "ses" || v === "day");
    document.body.classList.toggle("tm-sec", v === "sec");
    if (v === "home" || v === "sec") drawTabs();
    if (v === "ses") drawSes(arg);
    else if (v === "day") drawDay(arg);
    else if (v === "sec") openSec(arg);
    else { if (prev === "sec") S.data = null; view.innerHTML = ""; drawHome(); }
  }
  window.addEventListener("popstate", function (e) { var st = e.state || {}; show(st.tm || "home", st.arg); });
  function backHome() { if (S.view === "ses" || S.view === "day") history.back(); else drawHome(); }

  // ---------- dane ----------
  function load() {
    var a = iso(S.wk), b = iso(S.wk + 6 * DAY);
    var wx = fetch("/api/calendar/wx?start=" + a + "&end=" + b, { credentials: "same-origin", cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    return Promise.all([api("GET", "/week?start=" + a), wx]).then(function (r) { S.data = r[0]; S.wx = r[1]; });
  }
  function reload() { return load().then(function () { if (S.view === "ses") drawSes(S.arg); else if (S.view === "day") drawDay(S.arg); else if (S.view === "home") drawHome(); }).catch(fail); }
  function sesById(id) { return ((S.data && S.data.sessions) || []).filter(function (x) { return x.id === id; })[0]; }
  function put(id, b) { return api("PUT", "/sessions/" + id, b).then(reload).catch(fail); }

  // ---------- samopoczucie ----------
  function dayFeels(ds) { return ((S.data && S.data.calendar) || []).filter(function (c) { return c.kind === "feel" && c.feel != null && String(c.day).slice(0, 10) === ds; }); }
  function feelMain(fs) { var m = fs.filter(function (c) { return c.source !== "trener"; }); m = m.length ? m : fs; return m.length ? m[m.length - 1] : null; }
  function feelMine(ds) { return dayFeels(ds).filter(function (c) { return c.source !== "trener"; }).pop(); }
  function feelSave(ds, v, note) {
    var mine = feelMine(ds);
    if (v === "del") return mine ? cpost("/api/calendar/delete", { id: mine.id }) : Promise.resolve();
    var nt = note !== undefined ? note : (mine ? mine.note : null), b = { feel: v, title: FEEL_L[v], note: nt || null };
    return mine ? cpost("/api/calendar/edit", Object.assign({ id: mine.id }, b)) : cpost("/api/calendar/entry", Object.assign({ day: ds, kind: "feel" }, b));
  }
  function feelHTML(fs) {
    return fs.map(function (c) { return "<div class='tm-feel'><span class='fe'>" + FEEL_E[c.feel] + "</span><span><b>Samopoczucie: " + esc(FEEL_L[c.feel]) + "</b>" +
      (c.title && c.title !== FEEL_L[c.feel] ? "<br>" + esc(c.title.replace(/^📝\s*/, "")) : "") + (c.note ? "<br><span class='tm-sub' style='font-size:14px'>" + esc(c.note) + "</span>" : "") +
      (c.source === "trener" ? "<br><span class='tm-sub'>z notatki Trenera</span>" : "") + "</span></div>"; }).join("");
  }

  // ---------- pogoda jak w Kalendarzu ----------
  function wxBad(w, ov) {
    if (!w) return false; var g = function (k, d) { return ov && ov[k] != null ? +ov[k] : d; };
    return (w.wind != null && w.wind > g("wx.wind_ms", 8) + g("wx.forest_bonus_ms", 1)) || (w.rain_mmh != null && w.rain_mmh > g("wx.rain_mmh", 0.5)) || !!w.storm;
  }
  function wxGet(ds) {
    var T = iso(todayMs()), j = S.wx || {}, fc = (j.forecast || {})[ds], rd = (j.rides || {})[ds], ov = j.ov || {};
    if (!fc && !rd) { var dm = ((S.data && S.data.meta && S.data.meta.days) || {})[ds] || {}; fc = dm.wx; ov = ((S.data && S.data.meta) || {}).ov || ov; }
    if (rd && (ds < T || !fc)) return { ride: rd };
    return fc ? { fc: fc, bad: wxBad(fc, ov) } : null;
  }
  function wxShort(ds) {
    var w = wxGet(ds); if (!w) return "";
    if (w.ride) { var r = w.ride; return "<span class='tm-l2'>" + (r.icon || "") + " " + n1(r.wind) + " m/s" + (r.feel_max != null ? " · " + Math.round(r.feel_max) + "°" : (r.temp_max != null ? " · " + Math.round(r.temp_max) + "°" : "")) + " · podczas jazdy</span>"; }
    var f = w.fc; return "<span class='tm-l2" + (w.bad ? " bad" : "") + "'>" + (f.icon || "") + " " + n1(f.wind) + " m/s" + (f.feel_max != null ? " · " + Math.round(f.feel_max) + "°" : "") + (f.rain_prob != null && f.rain_prob >= 30 ? " · opad " + Math.round(f.rain_prob) + "%" : "") + (f.storm ? " · ⚡" : "") + "</span>";
  }
  function wxLine(ds) {
    var w = wxGet(ds); if (!w) return "";
    if (w.ride) { var rd = w.ride;
      return "<div class='tm-wx'>" + (rd.icon || "") + " " + n1(rd.wind) + " m/s" + (rd.wind_max != null ? " (max " + n1(rd.wind_max) + ")" : "") +
        (rd.feel_max != null ? " · " + Math.round(rd.feel_min) + "…" + Math.round(rd.feel_max) + "°" : (rd.temp_max != null ? " · " + Math.round(rd.temp_max) + "°" : "")) +
        (rd.rain_mm ? " · opad " + n1(rd.rain_mm) + " mm" : "") + " <span class='src'>· podczas jazdy</span></div>"; }
    var fc = w.fc;
    return "<div class='tm-wx" + (w.bad ? " bad" : "") + "'>" + (fc.icon || "") + " " + n1(fc.wind) + " m/s" + (fc.gust != null ? " (porywy " + n1(fc.gust) + ")" : "") +
      (fc.feel_max != null ? " · odczuwalna " + Math.round(fc.feel_min) + "…" + Math.round(fc.feel_max) + "°" : "") +
      (fc.rain_prob != null ? " · opad " + (fc.rain_mmh ? n1(fc.rain_mmh) + " mm/h, " : "") + Math.round(fc.rain_prob) + "%" : "") + (fc.storm ? " · ⚡ burza" : "") +
      " <span class='src'>· prognoza 8–18</span></div>";
  }

  // ---------- TYDZIEN ----------
  function drawHome() {
    if (!S.data) { tmEl.innerHTML = "<div class='tm-empty'>Wczytuję…</div>"; load().then(drawHome).catch(function (e) { tmEl.innerHTML = "<div class='tm-note b'>Nie udało się wczytać tygodnia: " + esc(e.message) + "</div>"; }); return; }
    var j = S.data, meta = j.meta || {}, ses = j.sessions || [], T0 = todayMs(), past = S.wk + 6 * DAY < T0;
    if (S.opened !== S.wk) { S.opened = S.wk; S.open = {}; if (T0 >= S.wk && T0 <= S.wk + 6 * DAY) S.open[iso(T0)] = true; }
    var act = ses.filter(function (x) { return x.status !== "skip"; }), linked = {};
    ses.forEach(function (x) { if (x.training_session_id) linked[x.training_session_id] = 1; });
    var extra = (j.activities || []).filter(function (a) { return !linked[a.id]; });
    var plh = act.reduce(function (a, x) { return a + x.dur_min; }, 0) / 60, dnh = act.filter(function (x) { return x.status === "done"; }).reduce(function (a, x) { return a + (x.real_min != null ? +x.real_min : x.dur_min); }, 0) / 60
      + extra.reduce(function (a, x) { return a + (x.duration_s || 0); }, 0) / 3600;
    var h = "<div class='tm-top'><button class='tm-rb' data-w='-1' aria-label='Poprzedni tydzień'>‹</button><div class='tt'><b>Tydzień " + pl(S.wk) + "–" + pl(S.wk + 6 * DAY) + "</b><span>" +
      esc(meta.phase_name || "") + (meta.light ? " · lżejszy" : "") + "</span></div><button class='tm-rb' data-w='1' aria-label='Następny tydzień'>›</button></div>";
    if (meta.target_h) { var mx = meta.target_h * 1.6;
      h += "<div class='tm-sub' style='text-align:center'>plan " + n1(plh) + " h · zrobione " + n1(dnh) + " h · cel " + n1(meta.target_h) + " h</div><div class='tm-bar'><i style='width:" + Math.min(100, plh / mx * 100) + "%;background:rgba(47,158,91,.35)'></i><i style='width:" + Math.min(100, dnh / mx * 100) + "%;background:var(--good)'></i><i style='left:" + (meta.target_h * 0.75 / mx * 100) + "%;width:" + (meta.target_h * 0.5 / mx * 100) + "%;border-left:2px solid var(--good);border-right:2px solid var(--good)'></i></div>"; }
    h += "<div class='tm-acts'>" + (S.wk !== monday(T0) ? "<button class='tm-b' id='tm-now'>dziś</button>" : "") + "<button class='tm-b' id='tm-gen'" + (past ? " disabled" : "") + ">↻ przelicz tydzień</button></div>";
    h += "<div id='tm-al'>" + alertsHTML(j, meta, T0) + "</div>";
    if (!past) h += "<div class='tm-box' id='tm-ask'></div>";
    if (!past) h += "<details class='tm-box' id='tm-ai'" + (S.review ? " open" : "") + "><summary>🤖 Weryfikacja AI</summary><div id='tm-aib'></div></details>";
    for (var i = 0; i < 7; i++) h += dayHTML(i, j, meta, extra, T0);
    h += "<div class='tm-sub' style='margin:10px 2px'>Dotknij dnia, żeby rozwinąć; treningu — po szczegóły; „✎ Edytuj dzień” — samopoczucie, REST / choroba / brak czasu, dodaj trening. Pełna wersja: <a href='?full=1'>tutaj</a>. <a href='/cwiczenia.html'>Baza ćwiczeń →</a></div>";
    tmEl.innerHTML = h;
    wireHome(j);
    if (!past) { drawAsk(); drawReview(); }
    if (S.autoReview && !past) { S.autoReview = false; runReview(false); }
  }
  function alertsHTML(j, meta, T0) {
    var al = "", pc = j.pending_change, L = S.lines;
    if (pc) {
      var mine = L && L.change_id === pc.id, lines = mine ? (L.lines || []) : ((pc.payload && pc.payload.lines) || null), notes = mine ? (L.notes || []) : ((pc.payload && pc.payload.notes) || []);
      al += "<div class='tm-note'><b>Zmiany w tygodniu</b>" + (lines ? (lines.length ? "<ul>" + lines.map(function (l) { return "<li>" + esc(l) + "</li>"; }).join("") + "</ul>" : " — bez zmian w sesjach.") : " (" + esc(pc.action) + ") czekają na decyzję.") +
        (notes.length ? "<div class='tm-sub'>" + notes.map(esc).join("<br>") + "</div>" : "") + "<button class='tm-b pri' id='tm-ok'>Akceptuj</button><button class='tm-b' id='tm-un'>Cofnij</button></div>";
    }
    if (meta.readiness_today != null && meta.readiness_threshold != null && meta.readiness_today < meta.readiness_threshold && T0 >= S.wk && T0 <= S.wk + 6 * DAY)
      al += "<div class='tm-note w'>🫀 Gotowość dziś <b>" + meta.readiness_today.toFixed(2) + "</b> (próg " + meta.readiness_threshold.toFixed(2) + ") — dziś wersje minimum.<br><button class='tm-b' data-dact='short' data-day='" + iso(T0) + "'>dziś brak czasu / lżej</button></div>";
    (meta.season_notes || []).forEach(function (n) { al += "<div class='tm-note w'>🩺 " + esc(n) + "</div>"; });
    var wAck = 0;
    (j.warnings || []).forEach(function (w) {
      if (typeof w === "string") w = { text: w };
      if (w.acked) { wAck++; return; }
      al += "<div class='tm-note w'>⚠️ " + esc(w.text) + (w.session_id ? "<br><button class='tm-b' data-ack='" + esc(w.key) + "' data-sid='" + w.session_id + "'>rozumiem, zostaw</button>" : "") + "</div>";
    });
    if (wAck) al += "<div class='tm-sub' style='margin-bottom:8px'>wyciszone uwagi: " + wAck + "</div>";
    if (j.calendar_update) al += "<div class='tm-note'>🗓️ Plan zaktualizowany sam: " + esc(j.calendar_update.reason) + ".</div>";
    if (meta.error) al += "<div class='tm-note b'>Meta planu niedostępne: " + esc(meta.error) + "</div>";
    if (!(j.sessions || []).length && S.wk + 6 * DAY >= T0) al += "<div class='tm-note'>Brak planu na ten tydzień — dotknij <b>↻ przelicz tydzień</b>.</div>";
    return al;
  }
  function dayHTML(i, j, meta, extra, T0) {
    var ms = S.wk + i * DAY, ds = iso(ms), dm = (meta.days || {})[ds] || {}, open = !!S.open[ds], items = [], chips = [];
    var fs = dayFeels(ds), fm = feelMain(fs);
    (dm.busy || []).forEach(function (b) { items.push({ s: tm(b.a), h: "<div class='tm-it busy'><span class='ic'>🔒</span><span class='tx'>" + esc(b.label) + " " + b.a + "–" + b.b + "</span></div>" }); });
    (j.calendar || []).forEach(function (c) {
      var a = c.day, b = c.end_day || c.day; if (ds < a || ds > b) return;
      if (c.kind === "feel" || c.event_type === "rest" || c.kind === "illness" || c.event_type === "delegacja" || c.at_time) return;
      if ((meta.route_entry_ids || []).indexOf(c.id) >= 0) return;
      items.push({ s: -1, h: "<div class='tm-it cal'><span class='ic'>" + (CALIC[c.event_type] || KIC[c.kind] || "📅") + "</span><span class='tx'>" + esc(c.title || c.event_type || c.kind) + "</span></div>" });
    });
    (j.sessions || []).forEach(function (x) {
      if (x.day !== ds) return;
      var tag = (x.note || "").indexOf("dodane przez Ciebie") === 0 ? " · ＋ Twoje" : (x.status === "skip" && (x.note || "").indexOf("usunięte przez Ciebie") === 0 ? " · usunięte" : (x.source === "manual" ? " · ✎" : ""));
      var s0 = tm(x.start_time) || 0;
      chips.push({ s: s0, h: "<i class='" + (x.status === "done" ? "dn" : (x.status === "skip" ? "sk" : "")) + "' style='border-left-color:" + SCOL[x.sport] + "'>" + (x.status === "done" ? "✓" : "") + AIC[x.sport] + " " + (x.start_time || "") + " · " + x.dur_min + "′</i>" });
      items.push({ s: s0, h: "<button class='tm-it ses" + (x.status === "done" ? " done" : "") + (x.status === "skip" ? " skip" : "") + "' data-sid='" + x.id + "' style='border-left-color:" + SCOL[x.sport] + "'><span class='ic'>" + AIC[x.sport] + "</span><span class='tx'><b>" +
        (x.status === "done" ? "✓ " : "") + esc(x.name) + "</b><small>" + (x.start_time || "") + " · " + x.dur_min + "′" + (x.cut ? " (minimum)" : "") + tag + (x.rating ? " · " + "★".repeat(x.rating) : "") + "</small></span><span class='ch'>›</span></button>" });
    });
    extra.forEach(function (a) {
      if (String(a.date).slice(0, 10) !== ds) return;
      var s0 = a.started_at ? new Date(a.started_at).getHours() * 60 + new Date(a.started_at).getMinutes() : 0, km = a.distance_m ? (a.distance_m / 1000).toFixed(0) + " km" : n1((a.duration_s || 0) / 3600) + " h";
      chips.push({ s: s0, h: "<i class='dn' style='border-left-color:var(--good)'>✓" + (SPIC[a.sport_type] || "•") + " " + km + "</i>" });
      items.push({ s: s0, h: "<div class='tm-it done'><span class='ic'>" + (SPIC[a.sport_type] || "•") + "</span><span class='tx'><b>✓ " + esc(a.activity_name || a.sport_type) + "</b><small>" + (a.distance_m ? km + " · " : "") + n1((a.duration_s || 0) / 3600) + " h · poza planem</small></span></div>" });
    });
    items.sort(function (a, b) { return a.s - b.s; }); chips.sort(function (a, b) { return a.s - b.s; });
    var ty = DTYPE[dm.type];
    var hd = "<button class='tm-dhd' data-tog='" + ds + "' aria-expanded='" + open + "'><span class='tm-dt'><b>" + DN[i] + "</b><small>" + pl(ms) + "</small></span><span class='tm-dm2'>" +
      "<span class='tm-l1'>" + DNL[i] + (ms === T0 ? "<span class='td'>dziś</span>" : "") + (fm ? "<span class='fe' title='samopoczucie: " + esc(FEEL_L[fm.feel]) + "'>" + FEEL_E[fm.feel] + "</span>" : "") + (ty ? "<span class='ty'>" + ty + "</span>" : "") + "</span>" +
      wxShort(ds) + "<span class='tm-l3'>" + (chips.length ? chips.map(function (c) { return c.h; }).join("") : "<span class='fr'>wolne</span>") + "</span></span><span class='tm-ar'>" + (open ? "▾" : "▸") + "</span></button>";
    var bd = "";
    if (open) bd = "<div class='tm-dbody'>" + wxLine(ds) + feelHTML(fs) + (items.length ? items.map(function (x) { return x.h; }).join("") : "<div class='tm-empty'>wolne — brak treningów i zajętości</div>") +
      "<button class='tm-b tm-ed' data-ed='" + ds + "'>✎ Edytuj dzień" + (ms <= T0 ? " · samopoczucie" : "") + "</button></div>";
    return "<div class='tm-day" + (ms === T0 ? " today" : "") + (ms < T0 ? " past" : "") + (i >= 5 ? " we" : "") + "' data-day='" + ds + "'>" + hd + bd + "</div>";
  }
  function wireHome(j) {
    tmEl.querySelectorAll("[data-w]").forEach(function (b) { b.onclick = function () { S.wk += (+b.dataset.w) * WK; S.data = null; S.lines = null; S.review = null; S.ask = null; drawHome(); }; });
    var nb = document.getElementById("tm-now"); if (nb) nb.onclick = function () { S.wk = monday(todayMs()); S.data = null; S.lines = null; S.review = null; drawHome(); };
    var gb = document.getElementById("tm-gen"); if (gb) gb.onclick = function () { gb.disabled = true; gb.textContent = "liczę…";
      api("POST", "/week/generate", { start: iso(S.wk) }).then(function (r) { S.lines = r; S.autoReview = true; return load(); }).then(drawHome).catch(function (e) { fail(e); drawHome(); }); };
    var pc = j.pending_change;
    if (pc) {
      document.getElementById("tm-ok").onclick = function () { api("POST", "/week/accept", { id: pc.id }).then(function () { S.lines = null; return load(); }).then(drawHome).catch(fail); };
      document.getElementById("tm-un").onclick = function () { api("POST", "/week/undo", { id: pc.id }).then(function () { S.lines = null; toast("Cofnięto"); return load(); }).then(drawHome).catch(fail); };
    }
    tmEl.querySelectorAll("[data-dact]").forEach(function (b) { b.onclick = function () { dayAction(b.dataset.day, b.dataset.dact); }; });
    tmEl.querySelectorAll("[data-ack]").forEach(function (b) { b.onclick = function () {
      var x = sesById(+b.dataset.sid); if (!x) return; var ak = (x.acks || []).slice(); if (ak.indexOf(b.dataset.ack) < 0) ak.push(b.dataset.ack);
      api("PUT", "/sessions/" + x.id, { acks: ak }).then(function () { toast("OK — uwaga wyciszona"); return reload(); }).catch(fail); }; });
    tmEl.querySelectorAll("[data-tog]").forEach(function (b) { b.onclick = function () { var ds = b.dataset.tog; S.open[ds] = !S.open[ds]; var y = b.getBoundingClientRect ? b.getBoundingClientRect().top : 0;
      drawHome(); var nb2 = tmEl.querySelector("[data-tog='" + ds + "']"); if (nb2 && nb2.getBoundingClientRect) window.scrollBy(0, nb2.getBoundingClientRect().top - y); }; });
    tmEl.querySelectorAll("[data-sid].ses").forEach(function (b) { b.onclick = function () { enter("ses", +b.dataset.sid); }; });
    tmEl.querySelectorAll("[data-ed]").forEach(function (b) { b.onclick = function () { enter("day", b.dataset.ed); }; });
  }
  function dayAction(ds, a) {
    api("POST", "/week/action", { day: ds, action: a }).then(function (r) { S.lines = r; S.autoReview = true; return load(); })
      .then(function () { toast("Zapisano — możesz cofnąć"); backHome(); }).catch(fail);
  }

  // ---------- prosba do AI ----------
  function drawAsk() {
    var el = document.getElementById("tm-ask"); if (!el) return;
    var A = (S.ask && S.ask.wk === S.wk) ? S.ask : (S.ask = { wk: S.wk, text: "", res: null, busy: false });
    var h = "<b>💬 Poproś Trenera o zmianę</b><textarea id='tm-at' rows='3' maxlength='600' placeholder='np. Dziś siła bez nóg, a do tego 30–45′ roweru po południu (testuję Graila)'>" + esc(A.text) + "</textarea>" +
      "<button class='tm-b pri' id='tm-ag' style='width:100%'" + (A.busy ? " disabled" : "") + ">" + (A.busy ? "AI układa zmiany… (ok. 10 s)" : "Zaproponuj zmiany") + "</button>";
    if (A.res && !A.busy) {
      var r = A.res, ch = r.changes || [];
      h += "<div style='margin:10px 0 4px;font-size:15px'>" + esc(r.summary || "") + "</div>";
      if (ch.length) h += "<ul style='margin:4px 0 8px 18px;padding:0;font-size:15px;line-height:1.45'>" + ch.map(function (c) { return "<li>" + esc(c.line) + (c.warn ? "<br><span style='color:var(--warn)'>⚠ " + esc(c.warn) + "</span>" : "") + "</li>"; }).join("") + "</ul>" +
        "<div class='tm-g2' style='margin:0'><button class='tm-b pri' id='tm-ao'>✓ Zastosuj</button><button class='tm-b' id='tm-an'>✕ Odrzuć</button></div><div class='tm-sub' style='margin-top:6px'>Nic się nie zmieni bez „Zastosuj”. Potem możesz cofnąć.</div>";
      else h += "<button class='tm-b' id='tm-an' style='margin-top:6px'>wyczyść</button>";
      if ((r.rejected || []).length) h += "<div class='tm-sub' style='margin-top:6px'>Odrzucone przez bezpieczniki: " + r.rejected.map(esc).join(" · ") + "</div>";
    }
    el.innerHTML = h;
    var ta = document.getElementById("tm-at"); ta.oninput = function () { A.text = ta.value; };
    document.getElementById("tm-ag").onclick = function () {
      var t = (ta.value || "").trim(); if (!t || A.busy) return; ta.blur();
      A.text = t; A.busy = true; A.res = null; drawAsk();
      api("POST", "/week/ask", { start: iso(S.wk), text: t }).then(function (r) { A.busy = false; A.res = r; drawAsk(); })
        .catch(function (e) { A.busy = false; A.res = { summary: "Błąd: " + e.message, changes: [], rejected: [] }; drawAsk(); });
    };
    var no = document.getElementById("tm-an"); if (no) no.onclick = function () { A.res = null; drawAsk(); };
    var ok = document.getElementById("tm-ao"); if (ok) ok.onclick = function () {
      ok.disabled = true; ok.textContent = "zapisuję…";
      api("POST", "/week/ask/apply", { start: iso(S.wk), text: A.text, changes: A.res.changes }).then(function (r) {
        S.lines = r; S.ask = null; S.autoReview = true; toast("Zmiany zastosowane — możesz je cofnąć"); return load();
      }).then(drawHome).catch(function (e) { fail(e); ok.disabled = false; ok.textContent = "✓ Zastosuj"; });
    };
  }

  // ---------- weryfikacja AI ----------
  var SEVC = { "wysoka": ["🔴", "var(--bad)"], "średnia": ["🟠", "var(--warn)"], "niska": ["🔵", "var(--accent)"] };
  function drawReview(busy) {
    var el = document.getElementById("tm-aib"); if (!el) return;
    var r = S.review, h = "";
    if (busy) h = "<div class='tm-sub' style='margin:6px 0'>AI czyta plan, Kalendarz, pogodę i cele (ok. 10–15 s)…</div>";
    else if (r) {
      h = "<div style='margin:6px 0;font-size:15px'>" + esc(r.summary || "") + "</div>" + (r.issues || []).map(function (i) { var c = SEVC[i.severity] || SEVC["średnia"];
        return "<div class='tm-note' style='border-color:" + c[1] + "'><b>" + c[0] + " " + DN[(new Date(D(i.day)).getUTCDay() + 6) % 7] + " " + pl(D(i.day)) + ": " + esc(i.problem) + "</b>" + (i.why ? "<div class='tm-sub'>dlaczego: " + esc(i.why) + "</div>" : "") + (i.suggestion ? "<div>👉 " + esc(i.suggestion) + "</div>" : "") + "</div>"; }).join("") +
        (!(r.issues || []).length ? "<div class='tm-sub'>✓ AI nie widzi problemów.</div>" : "");
    } else h = "<div class='tm-sub' style='margin:6px 0'>AI przejrzy tydzień pod kątem rzeczy bez sensu (siła przy długiej jeździe, pogoda, Kalendarz). Tylko doradza.</div>";
    el.innerHTML = h + "<button class='tm-b' id='tm-rv' style='width:100%;margin-top:6px'" + (busy ? " disabled" : "") + ">" + (busy ? "sprawdzam…" : "sprawdź plan") + "</button>";
    document.getElementById("tm-rv").onclick = function () { runReview(true); };
  }
  function runReview(force) {
    var d = document.getElementById("tm-ai"); if (d) d.open = true;
    drawReview(true);
    api("POST", "/week/review", { start: iso(S.wk), force: !!force }).then(function (r) { S.review = r; drawReview(); })
      .catch(function (e) { S.review = { summary: "Błąd weryfikacji: " + e.message, issues: [] }; drawReview(); });
  }

  // ---------- TRENING na caly ekran ----------
  function drawSes(id) {
    var x = sesById(id);
    if (!x) { view.innerHTML = "<div><div class='tm-empty'>Tego treningu już nie ma w planie (plan się przeliczył).</div><button class='tm-b' id='tm-vb'>‹ wróć do tygodnia</button></div>"; document.getElementById("tm-vb").onclick = backHome; return; }
    var T0 = todayMs(), ms = D(x.day), fut = ms >= T0, canEd = fut && x.status === "plan", di = (new Date(ms).getUTCDay() + 6) % 7;
    var st = { plan: "w planie", done: "✓ zrobione", skip: "pominięte" }[x.status] || x.status;
    var det = x.details && x.details.text ? x.details.text : (x.sport === "rower" ? (x.is_long ? "Długa, równa jazda — jedz co 45 min, pij co 15 min." : "Jazda strefa " + (x.zone || 2) + ".") : "");
    var h = "<div><div class='tm-vh'><span class='ic'>" + AIC[x.sport] + "</span><div><b>" + esc(x.name) + "</b><span class='tm-sub' style='font-size:14px'>" + DNL[di] + " " + pl(ms) + " · " + (x.start_time || "—") + " · " + x.dur_min + "′" + (x.cut ? " (minimum)" : "") + " · " + st + (x.xss ? " · ~" + Math.round(x.xss) + " XSS" : "") + "</span></div></div>";
    h += wxLine(x.day);
    if (det || x.note) h += "<div class='tm-det'>" + esc(det) + (x.note ? (det ? "\n\n" : "") + "📝 " + esc(x.note) : "") + "</div>";
    if (x.sport === "sila" && x.details && x.details.engine) h += "<a class='tm-b pri' style='display:flex;justify-content:center;align-items:center;text-decoration:none;margin:0 0 12px' href='/sciaga.html?id=" + x.id + "'>📄 Ściąga z grafikami i PDF</a>";
    if (canEd) {
      h += "<div class='tm-g2'><button class='tm-b' data-sa='done'>✓ Zrobione</button>" + (x.min_min && x.min_min < x.dur_min ? "<button class='tm-b' data-sa='cut'>⏱ Minimum " + x.min_min + "′</button>" : "") +
        "<button class='tm-b' data-sa='skip'>✕ Pomiń</button><button class='tm-b bad' data-sa='del'>🗑 Usuń</button></div>";
      var days = [0, 1, 2, 3, 4, 5, 6].map(function (k) { var m2 = S.wk + k * DAY, d2 = iso(m2); return (m2 < T0 || d2 === x.day) ? "" : "<option value='" + d2 + "'>" + DNL[k] + " " + pl(m2) + (m2 === T0 ? " (dziś)" : "") + "</option>"; }).join("");
      h += "<div class='tm-f'><span>Godzina</span><input type='time' id='tm-st' value='" + esc(x.start_time || "") + "'><span>Czas (min)</span><input type='number' inputmode='numeric' min='5' max='600' step='5' id='tm-sd' value='" + x.dur_min + "'>" +
        "<span>Przenieś na</span><select id='tm-sm'><option value=''>— wybierz dzień —</option>" + days + "</select>" +
        "<span>Zamień na</span><select id='tm-ss'><option value=''>— wybierz —</option>" + ACT.filter(function (a) { return a[0] !== x.sport; }).map(function (a) { return "<option value='" + a[0] + "'>" + a[1] + " " + a[2] + "</option>"; }).join("") + "</select></div>";
    } else if (fut && x.status !== "plan") h += "<div class='tm-g2'><button class='tm-b' data-sa='undo'>↺ Przywróć do planu</button></div>";
    h += "<div class='tm-rate'><div class='tm-h3' style='margin-top:4px'>Oceń plan</div><div class='st'>" + [1, 2, 3, 4, 5].map(function (n) { return "<button type='button' data-rt='" + n + "' aria-label='" + n + "' style='color:" + ((x.rating || 0) >= n ? "var(--accent)" : "var(--line2)") + "'>★</button>"; }).join("") + "</div>" +
      "<input type='text' id='tm-rn' maxlength='300' placeholder='komentarz — co było nie tak / co dobre' value='" + esc(x.rating_note || "") + "'></div></div>";
    view.innerHTML = h; view.scrollTop = 0;
    view.querySelectorAll("[data-sa]").forEach(function (b) { b.onclick = function () {
      var a = b.dataset.sa;
      if (a === "done") put(x.id, { status: "done" });
      else if (a === "skip") put(x.id, { status: "skip" });
      else if (a === "undo") put(x.id, { status: "plan", cut: false, note: (x.note || "").indexOf("usunięte przez Ciebie") === 0 ? null : x.note });
      else if (a === "cut") put(x.id, { dur_min: x.min_min, cut: true });
      else if (a === "del") {
        if (!confirm("Usunąć „" + x.name + "” z planu?")) return;
        var p = (x.note || "").indexOf("dodane przez Ciebie") === 0 ? api("DELETE", "/sessions/" + x.id) : api("PUT", "/sessions/" + x.id, { status: "skip", note: "usunięte przez Ciebie" });
        p.then(function () { toast("Usunięto"); return load(); }).then(backHome).catch(fail);
      }
    }; });
    var stI = document.getElementById("tm-st"); if (stI) stI.onchange = function () { if (stI.value) put(x.id, { start_time: stI.value }); };
    var sd = document.getElementById("tm-sd"); if (sd) sd.onchange = function () { var v = +sd.value; if (v >= 5) put(x.id, { dur_min: v, min_min: Math.min(x.min_min || v, v) }); };
    var sm = document.getElementById("tm-sm"); if (sm) sm.onchange = function () { if (sm.value) api("PUT", "/sessions/" + x.id, { day: sm.value }).then(function () { toast("Przeniesione"); return load(); }).then(backHome).catch(fail); };
    var ss = document.getElementById("tm-ss"); if (ss) ss.onchange = function () { var k = ss.value; if (!k) return;
      put(x.id, { sport: k, name: DEF[k][0], zone: k === "rower" ? 2 : null, is_long: false, dur_min: k === "joga" ? Math.min(x.dur_min, 30) : Math.min(x.dur_min, k === "rower" ? 120 : 45), min_min: DEF[k][3] }); };
    function rate(n, note) { api("POST", "/rating", { session_id: x.id, rating: n, note: (note || "").trim() || null }).then(function () { toast(n ? "Ocena zapisana" : "Ocena usunięta"); return reload(); }).catch(fail); }
    var rn = document.getElementById("tm-rn");
    view.querySelectorAll("[data-rt]").forEach(function (b) { b.onclick = function () { var n = +b.dataset.rt; rate(x.rating === n ? 0 : n, rn.value); }; });
    rn.onchange = function () { if (x.rating) rate(x.rating, rn.value); else { rn.value = ""; rn.placeholder = "najpierw dotknij gwiazdek"; } };
  }

  // ---------- EDYCJA DNIA: samopoczucie + akcje + dodaj trening ----------
  function drawDay(ds) {
    var ms = D(ds), di = (new Date(ms).getUTCDay() + 6) % 7, T0 = todayMs(), fut = ms >= T0;
    var mine = feelMine(ds), tr = dayFeels(ds).filter(function (c) { return c.source === "trener"; });
    var h = "<div><div class='tm-vh'><span class='ic'>📅</span><div><b>" + DNL[di] + " " + pl(ms) + "</b><span class='tm-sub' style='font-size:14px'>edycja dnia — plan przeliczy się sam</span></div></div>" + wxLine(ds);
    if (ms <= T0) {
      h += "<div class='tm-h3'>Samopoczucie</div><div class='tm-fg'>" + [-2, -1, 0, 1, 2].map(function (v) { return "<button type='button' data-fv='" + v + "' class='" + (mine && +mine.feel === v ? "on" : "") + "'><span>" + FEEL_E[v] + "</span>" + FEEL_L[v] + "</button>"; }).join("") + "</div>" +
        "<input class='tm-fin' id='tm-fn' maxlength='300' placeholder='co czujesz? (opcjonalnie, np. ciężkie nogi, stres)' value='" + esc(mine && mine.note ? mine.note : "") + "'>" +
        "<div class='tm-sub' style='margin:6px 0 0'>" + (mine ? "Dotknij zaznaczonej buźki, żeby usunąć ocenę." : "Ocena trafia do Kalendarza i liczy się do gotowości / zmęczenia.") + "</div>" + (tr.length ? feelHTML(tr) : "");
    }
    if (fut) {
      var A = [["rest", "😴", "REST DAY", "dzień wolny — trener przełoży trening"], ["short", "⏱", "Brak czasu", "dziś wersje minimum"], ["ill", "🤒", "Choroba", "dzień pusty + 2 dni lżej"],
        ["del", "🧳", "Delegacja", "tylko krótka joga hotelowa"], ["clear", "↺", "Zwykły dzień", "usuń powyższe ustawienia dnia"]];
      h += "<div class='tm-h3'>Dzień</div><div class='tm-box' style='padding:0 12px'>" + A.map(function (a) { return "<button class='tm-row' data-da='" + a[0] + "'><span class='ic'>" + a[1] + "</span><span class='tx'>" + a[2] + "<small>" + a[3] + "</small></span><span class='ch'>›</span></button>"; }).join("") + "</div>" +
        "<div class='tm-h3'>Dodaj trening</div><div class='tm-box' style='padding:0 12px'>" + ACT.map(function (a) { var d = DEF[a[0]]; return "<button class='tm-row' data-add='" + a[0] + "'><span class='ic'>" + a[1] + "</span><span class='tx'>" + a[2] + "<small>" + d[1] + " · " + d[2] + "′ — godzinę i czas zmienisz potem</small></span><span class='ch'>＋</span></button>"; }).join("") + "</div>";
    }
    view.innerHTML = h + "</div>";
    view.querySelectorAll("[data-fv]").forEach(function (b) { b.onclick = function () {
      var v = +b.dataset.fv, del = mine && +mine.feel === v, fn = document.getElementById("tm-fn");
      feelSave(ds, del ? "del" : v, fn ? fn.value.trim() : undefined).then(function () { toast(del ? "Usunięto ocenę samopoczucia" : "Samopoczucie: " + FEEL_E[v] + " " + FEEL_L[v]); return reload(); }).catch(fail); }; });
    var fn = document.getElementById("tm-fn"); if (fn) fn.onchange = function () { var m = feelMine(ds); if (!m) { toast("Najpierw wybierz buźkę"); return; }
      feelSave(ds, +m.feel, fn.value.trim()).then(function () { toast("Notatka zapisana"); return reload(); }).catch(fail); };
    view.querySelectorAll("[data-da]").forEach(function (b) { b.onclick = function () { dayAction(ds, b.dataset.da); }; });
    view.querySelectorAll("[data-add]").forEach(function (b) { b.onclick = function () { var k = b.dataset.add, d = DEF[k];
      api("POST", "/sessions", { day: ds, sport: k, note: "dodane przez Ciebie", name: d[0], start_time: d[1], dur_min: d[2], min_min: d[3], zone: k === "rower" ? 2 : null })
        .then(function (r) { toast("Dodano"); return load().then(function () { history.replaceState({ tm: "ses", arg: r.id }, ""); show("ses", r.id); }); }).catch(fail); }; });
  }

  // ---------- zakladki dzialow (rysuje trener.js) ----------
  function openSec(sub) {
    window.scrollTo(0, 0);
    (function wait(n) {
      if (CORE_OK && window.TRENER_CORE && window.TRENER_CORE.go) window.TRENER_CORE.go(sub);
      else if (n < 100) setTimeout(function () { wait(n + 1); }, 100);
      else toast("Nie udało się wczytać działu", true);
    })(0);
  }

  history.replaceState({ tm: "home" }, "");
  drawTabs();
  drawHome();
})();
