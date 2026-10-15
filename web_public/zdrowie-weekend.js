/* ZDROWIE > WEEKEND (2026-10-15): plan dzien po dniu (sb, nd) z przelacznikiem Miasto/Dom + lista zakupow (odhaczanie).
   Miasto = sniadanie w domu, reszta na miescie; Dom = wszystkie posilki z domu. Posilki sumuja sie do celu kcal dnia.
   Dane: /api/jedzenie/weekend (qbot_food_weekend.py). Wolane z jedzenie.js przy wejsciu w zakladke (window.qWeekendLoad). */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var W = null, busy = false;
  var DZ = ["warzywa i owoce", "mięso i ryby", "nabiał i jajka", "pieczywo", "suche i przyprawy", "na rower", "inne"];
  var PORA = { "śniadanie": "☀️", "obiad": "🍽", "przekąska": "🍎", "kolacja": "🌙", "na rower": "🚲" };
  var DNAME = { sb: "Sobota", nd: "Niedziela" };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function n0(v) { return v == null || v === "" ? "–" : Math.round(+v).toLocaleString("pl-PL"); }
  function j(u, o) {
    return fetch(u, Object.assign({ credentials: "same-origin", cache: "no-store" }, o || {})).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (x) { if (!r.ok) throw new Error(x.detail || ("HTTP " + r.status)); return x; });
    });
  }
  function post(u, b) { return j(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }); }
  function key(z) { return (z.produkt || "") + "|" + (z.ilosc || ""); }
  function modes() { return (W && W.plan && W.plan.modes) || { sb: "miasto", nd: "miasto" }; }

  function meal(m) {
    var home = m.gdzie !== "miasto";
    var head = '<div class="eh"><span>' + (PORA[m.pora] || "•") + ' <b>' + esc(m.pora || "") + '</b> <span class="note">(' + (home ? "dom" : "miasto") + ')</span> · ' +
      esc(m.nazwa || "") + (home && m.czas_min ? ' <span class="note">· ' + n0(m.czas_min) + ' min</span>' : '') +
      '</span><span class="k">~' + n0(m.kcal) + ' kcal · ' + n0(m.bialko_g) + ' g B</span></div>';
    if (!home) return '<div class="ent">' + head + (m.zamow ? '<div class="note">Zamów: ' + esc(m.zamow) + '</div>' : '') + '</div>';
    return '<details class="ent"><summary style="cursor:pointer;list-style:none">' + head + '</summary>' +
      '<ul class="recs">' + (m.skladniki || []).map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + '</ul>' +
      ((m.kroki || []).length ? '<ol class="recs">' + m.kroki.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + '</ol>' : '') + '</details>';
  }

  function day(d) {
    var md = modes()[d.day] || d.tryb || "miasto", diff = (d.suma_kcal || 0) - (d.cel_kcal || 0);
    var h = '<div class="card"><div class="ttl"><h2>' + esc(DNAME[d.day] || d.day) + ' ' + esc(d.date) + ' · cel ~' + n0(d.cel_kcal) + ' kcal</h2>' +
      '<span class="seg" role="group" aria-label="Gdzie jem">' +
      '<button data-md="' + d.day + ':miasto" class="' + (md === "miasto" ? "on" : "") + '">🍽 Na mieście</button>' +
      '<button data-md="' + d.day + ':dom" class="' + (md === "dom" ? "on" : "") + '">🏠 W domu</button></span></div>';
    if ((d.treningi || []).length) h += '<p class="note">🚲 ' + esc(d.treningi.join("; ")) + (d.wegle_na_rower_g ? ' · na rower ~' + n0(d.wegle_na_rower_g) + ' g węgli' : '') + '</p>';
    (d.posilki || []).forEach(function (m) { h += meal(m); });
    if (!(d.posilki || []).length) h += '<p class="empty">Brak propozycji — „Ułóż od nowa”.</p>';
    h += '<div class="kv"><span>Razem</span><span><b>~' + n0(d.suma_kcal) + ' kcal</b> / cel ' + n0(d.cel_kcal) +
      ' <span class="note">(' + (diff >= 0 ? "+" : "") + n0(diff) + ')</span></span><span>Białko</span><span>~' + n0(d.suma_bialko) + ' g / ' + n0(d.bialko_g) + ' g</span></div>';
    if (d.unikaj) h += '<p class="note">✋ ' + esc(d.unikaj) + '</p>';
    return h + '</div>';
  }

  function render() {
    var box = $("weekend"); if (!box) return;
    if (!W || !W.plan) { box.innerHTML = '<p class="empty">Brak planu. <button class="btn pri" id="wk-build">Ułóż plan weekendu</button></p>'; bind(); return; }
    var p = W.plan, ch = W.checked || {}, h = "";
    var nz = (p.zakupy || []).length, nc = (p.zakupy || []).filter(function (z) { return ch[key(z)]; }).length;
    h += '<div class="ttl"><h2>Weekend ' + esc(W.weekend) + '</h2><span class="acts">' +
      '<span class="seg" role="group" aria-label="Liczba osób">' + [1, 2, 3].map(function (n) {
        return '<button data-por="' + n + '" class="' + (W.portions === n ? "on" : "") + '">' + n + (n === 1 ? " osoba" : " os.") + '</button>'; }).join("") + '</span>' +
      '<button class="btn" id="wk-build">Ułóż od nowa</button></span></div>';
    h += '<p class="note">Ułożone ' + esc(W.built_at) + '. Przełącz „Na mieście / W domu” dla każdego dnia — plan i lista zakupów ułożą się od nowa. ' +
      'Cel kalorii i paliwo na rower z planu QBota; kalorie posiłków to szacunek (na jedną porcję).</p>';
    if (p.error) h += '<p class="msg">AI nie odpowiedziało (' + esc(p.error) + ') — spróbuj „Ułóż od nowa”.</p>';
    h += '<div class="dgrid"><div class="stack">' + (p.days || []).map(day).join("") + '</div><div class="stack">';
    h += '<div class="card"><div class="ttl"><h2>🛒 Lista zakupów</h2><span class="note">' + nc + ' z ' + nz + ' w koszyku</span></div>';
    if (!nz) h += '<p class="empty">Nic do kupienia — oba dni na mieście bez jazdy.</p>';
    var by = {}; (p.zakupy || []).forEach(function (z) { var d = DZ.indexOf(z.dzial) >= 0 ? z.dzial : "inne"; (by[d] = by[d] || []).push(z); });
    DZ.forEach(function (d) {
      if (!by[d]) return;
      h += '<div class="note" style="margin-top:10px;font-weight:600">' + esc(d) + '</div>';
      by[d].forEach(function (z) {
        var k = key(z), on = !!ch[k];
        h += '<label class="meal" style="cursor:pointer"><span class="nm" style="' + (on ? "text-decoration:line-through;color:var(--muted)" : "") + '">' +
          '<input type="checkbox" data-k="' + esc(k) + '"' + (on ? " checked" : "") + ' style="margin-right:8px;width:18px;height:18px;vertical-align:-3px;accent-color:var(--accent)">' +
          '<b>' + esc(z.produkt) + '</b></span><span class="mx">' + esc(z.ilosc || "") + '</span></label>';
      });
    });
    h += '<p class="note">Składniki na wybraną liczbę osób. Okno 10–20 obowiązuje, chyba że trening ≥1,5 h.</p></div></div></div>';
    box.innerHTML = h; bind();
  }

  function bind() {
    var b = $("wk-build");
    if (b) b.onclick = function () { rebuild(W && W.portions || 1, modes()); };
    document.querySelectorAll("#weekend [data-por]").forEach(function (x) { x.onclick = function () { rebuild(+x.dataset.por, modes()); }; });
    document.querySelectorAll("#weekend [data-md]").forEach(function (x) {
      x.onclick = function () {
        var p = x.dataset.md.split(":"), m = Object.assign({}, modes());
        if (m[p[0]] === p[1]) return;
        m[p[0]] = p[1]; rebuild(W && W.portions || 1, m);
      };
    });
    document.querySelectorAll("#weekend input[data-k]").forEach(function (cb) {
      cb.onchange = function () {
        W.checked = W.checked || {}; if (cb.checked) W.checked[cb.dataset.k] = true; else delete W.checked[cb.dataset.k];
        render();
        post("/api/jedzenie/weekend/check", { friday: W.friday, key: cb.dataset.k, on: cb.checked }).catch(function () {});
      };
    });
  }

  function rebuild(por, md) {
    if (busy) return; busy = true;
    $("weekend").innerHTML = '<p class="empty">Układam plan weekendu i listę zakupów… to trwa ok. minuty.</p>';
    post("/api/jedzenie/weekend/build", { friday: W && W.friday, portions: por, modes: md }).then(function (x) { W = x; render(); })
      .catch(function (e) { $("weekend").innerHTML = '<p class="msg">Nie udało się ułożyć planu: ' + esc(e.message) + '</p>'; })
      .then(function () { busy = false; });
  }

  window.qWeekendLoad = function () {
    if (W || busy) { render(); return; }
    busy = true;
    $("weekend").innerHTML = '<p class="empty">Wczytuję plan weekendu… (jeśli nie był jeszcze ułożony, potrwa to ok. minuty)</p>';
    j("/api/jedzenie/weekend").then(function (x) { W = x; render(); })
      .catch(function (e) { $("weekend").innerHTML = '<p class="msg">Nie udało się wczytać: ' + esc(e.message) + '</p>'; })
      .then(function () { busy = false; });
  };
})();
