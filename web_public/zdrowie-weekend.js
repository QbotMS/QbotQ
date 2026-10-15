/* ZDROWIE > WEEKEND (2026-10-15): plan jedzenia na weekend bez diety + lista zakupow (odhaczanie) + 2-3 proste posilki.
   Dane: /api/jedzenie/weekend (qbot_food_weekend.py). Wolane z jedzenie.js przy wejsciu w zakladke (window.qWeekendLoad). */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var W = null, busy = false;
  var DZ = ["warzywa i owoce", "mięso i ryby", "nabiał i jajka", "pieczywo", "suche i przyprawy", "na rower", "inne"];
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function n0(v) { return v == null || v === "" ? "–" : Math.round(+v).toLocaleString("pl-PL"); }
  function j(u, o) {
    return fetch(u, Object.assign({ credentials: "same-origin", cache: "no-store" }, o || {})).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (x) { if (!r.ok) throw new Error(x.detail || ("HTTP " + r.status)); return x; });
    });
  }
  function post(u, b) { return j(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }); }
  function key(z) { return (z.produkt || "") + "|" + (z.ilosc || ""); }

  function render() {
    var box = $("weekend"); if (!box) return;
    if (!W || !W.plan) { box.innerHTML = '<p class="empty">Brak planu. <button class="btn pri" id="wk-build">Ułóż plan weekendu</button></p>'; bind(); return; }
    var p = W.plan, ch = W.checked || {}, h = "";
    var nz = (p.zakupy || []).length, nc = (p.zakupy || []).filter(function (z) { return ch[key(z)]; }).length;
    h += '<div class="ttl"><h2>Weekend ' + esc(W.weekend) + '</h2><span class="acts">' +
      '<span class="seg" role="group" aria-label="Porcje">' + [1, 2, 3].map(function (n) {
        return '<button data-por="' + n + '" class="' + (W.portions === n ? "on" : "") + '">' + n + (n === 1 ? " osoba" : " os.") + '</button>'; }).join("") + '</span>' +
      '<button class="btn" id="wk-build">Ułóż od nowa</button></span></div>';
    h += '<p class="note">Ułożone ' + esc(W.built_at) + '. Kalorie dnia i paliwo na rower z planu QBota; kalorie posiłków to szacunek.</p>';
    if (p.error) h += '<p class="msg">AI nie odpowiedziało (' + esc(p.error) + ') — spróbuj „Ułóż od nowa”.</p>';
    h += '<div class="dgrid"><div class="stack">';
    /* zakupy */
    h += '<div class="card"><div class="ttl"><h2>🛒 Lista zakupów</h2><span class="note">' + nc + ' z ' + nz + ' w koszyku</span></div>';
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
    h += '</div>';
    /* posilki */
    h += '<div class="card"><h2>🍳 Do zrobienia w domu</h2>';
    (p.posilki || []).forEach(function (m) {
      h += '<details class="ent"><summary style="cursor:pointer;list-style:none"><div class="eh"><span><b>' + esc(m.nazwa) + '</b> <span class="note">· ' + esc(m.kiedy || "") +
        (m.czas_min ? " · " + n0(m.czas_min) + " min" : "") + '</span></span><span class="k">~' + n0(m.kcal) + ' kcal · ' + n0(m.bialko_g) + ' g B</span></div></summary>' +
        '<ul class="recs">' + (m.skladniki || []).map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + '</ul>' +
        '<ol class="recs">' + (m.kroki || []).map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + '</ol></details>';
    });
    if (!(p.posilki || []).length) h += '<p class="empty">Brak propozycji.</p>';
    h += '<p class="note">Kalorie i białko na jedną porcję, składniki na wybraną liczbę osób.</p></div>';
    h += '</div><div class="stack">';
    /* dni */
    (p.days || []).forEach(function (d) {
      h += '<div class="card"><div class="ttl"><h2>' + esc(d.day) + ' ' + esc(d.date) + '</h2><span class="k">cel ~' + n0(d.cel_kcal) + ' kcal</span></div>' +
        '<div class="kv"><span>Białko</span><span>~' + n0(d.bialko_g) + ' g</span>' +
        (d.wegle_na_rower_g ? '<span>Na rower</span><span>~' + n0(d.wegle_na_rower_g) + ' g węgli</span>' : '') + '</div>' +
        ((d.treningi || []).length ? '<p class="note">🚲 ' + esc(d.treningi.join("; ")) + '</p>' : '') +
        (d.zamawiaj ? '<p class="note">🍽 ' + esc(d.zamawiaj) + '</p>' : '') +
        (d.unikaj ? '<p class="note">✋ ' + esc(d.unikaj) + '</p>' : '') +
        (d.rower ? '<p class="note">🍬 ' + esc(d.rower) + '</p>' : '') + '</div>';
    });
    h += '<p class="note">Okno 10–20 obowiązuje, chyba że trening ≥1,5 h.</p></div></div>';
    box.innerHTML = h; bind();
  }

  function bind() {
    var b = $("wk-build");
    if (b) b.onclick = function () { rebuild(W && W.portions || 1); };
    document.querySelectorAll("#weekend [data-por]").forEach(function (x) { x.onclick = function () { rebuild(+x.dataset.por); }; });
    document.querySelectorAll("#weekend input[data-k]").forEach(function (cb) {
      cb.onchange = function () {
        W.checked = W.checked || {}; if (cb.checked) W.checked[cb.dataset.k] = true; else delete W.checked[cb.dataset.k];
        render();
        post("/api/jedzenie/weekend/check", { friday: W.friday, key: cb.dataset.k, on: cb.checked }).catch(function () {});
      };
    });
  }

  function rebuild(por) {
    if (busy) return; busy = true;
    $("weekend").innerHTML = '<p class="empty">Układam plan weekendu (lista zakupów i posiłki)… to trwa ok. minuty.</p>';
    post("/api/jedzenie/weekend/build", { friday: W && W.friday, portions: por }).then(function (x) { W = x; render(); })
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
