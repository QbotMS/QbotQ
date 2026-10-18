/* ZDROWIE > WEEKEND (2026-10-15, wersja 4). Dok.: qbot_food_weekend.py (opis calosci), docs/BROKUL.md.
   AI proponuje, Michal wybiera i koryguje wyjatkami, QBot uczy sie z ocen:
   Profil smaku (ankieta) -> propozycje (po 3 na posilek, dom / na miescie; ukladane w tle w czwartek) -> wybor
   ("inne" dla jednego posilku, "moja wersja") -> Zatwierdz -> lista zakupow (ilosci x liczba osob, zaznacz czego brak,
   do Notatek) + wybrane posilki w Zdrowie > Dni ("Zjadlem" + ocena). Wolane z jedzenie.js (window.qWeekendLoad). */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var W = null, PR = null, busy = false, survey = false;
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
  function P() { return W.plan; }
  function kindOf(d, s) { return ((P().modes || {})[d.day] === "miasto" && s.miasto) ? "miasto" : "dom"; }
  window.qWkRecipe = function (o, gdzie, n, home) { showRecipe(o, gdzie, n, home); };
  function skipped(d, s) { return !!((P().skip || {})[d.day + "|" + s.pora]); }
  function chosen(d, s, k) { var i = (P().choice || {})[d.day + "|" + s.pora + "|" + k] || 0; return Math.min(i, (s[k] || []).length - 1); }
  /* ilosci na 1 osobe -> x liczba osob (bez AI) */
  /* 17.10: ulamki liczone (1/2 x 2 = 1), waga sztuki po "x" bez skalowania (2 x 50 g -> 4 x 50 g), wynik jako ½ ¼ ¾ ⅓ ⅔ */
  function fmtQ(v) {
    if (Math.abs(v - Math.round(v)) < 0.02) return String(Math.round(v));
    var w = Math.floor(v + 1e-9), r = v - w, F = [[0.5, "½"], [0.25, "¼"], [0.75, "¾"], [1 / 3, "⅓"], [2 / 3, "⅔"]];
    for (var i = 0; i < F.length; i++) if (Math.abs(r - F[i][0]) < 0.03) return (w ? w : "") + F[i][1];
    return (Math.round(v * 10) / 10).toString().replace(".", ",");
  }
  /* 18.10: lista zakupow zsumowana ("175 g + 175 g" -> "350 g"), inne jednostki dopisane po " + " */
  function sumQ(arr) {
    var tot = {}, order = [], other = [];
    arr.forEach(function (q) { var m = String(q).match(/^\s*~?\s*([\d.,]+)\s*(g|kg|ml|l|szt\.?|sztuk[aię]?)\s*$/i);
      if (m) { var u = m[2].toLowerCase().replace(/\.$/, ""); if (u.indexOf("szt") === 0) u = "szt"; if (!(u in tot)) { order.push(u); tot[u] = 0; } tot[u] += parseFloat(m[1].replace(",", ".")); }
      else other.push(q); });
    return order.map(function (u) { return fmtQ(tot[u]) + " " + u; }).concat(other).join(" + ");
  }
  function scale(q, n) {
    if (!q || n === 1) return q || "";
    return String(q).replace(/([x×]\s*)?(\d+)\s*\/\s*(\d+)|([x×]\s*)?(\d+(?:[.,]\d+)?)/g, function (m, xa, a, b, xb, num) {
      if (xa || xb) return m;
      return fmtQ(a != null ? (+a / +b) * n : parseFloat(num.replace(",", ".")) * n);
    });
  }

  /* to samo co qbot_food_weekend.view */
  function view() {
    var shop = {}, order = [];
    var days = (P().days || []).map(function (d) {
      var ms = [];
      (d.slots || []).forEach(function (s) {
        var k = kindOf(d, s), opts = s[k] || []; if (!opts.length || skipped(d, s)) return;   /* 17.10: usuniety z menu */
        var o = opts[chosen(d, s, k)];
        ms.push(Object.assign({}, o, { pora: s.pora, gdzie: k }));
        if (k === "dom") (o.zakupy || []).forEach(function (z) {
          var p = String(z.produkt || "").trim(); if (!p) return;
          var kk = p.toLowerCase();
          if (!shop[kk]) { shop[kk] = { produkt: p, dzial: z.dzial || "inne", ilosci: [] }; order.push(kk); }
          if (z.ilosc) shop[kk].ilosci.push(z.ilosc);
        });
      });
      var sk = 0, sb = 0; ms.forEach(function (x) { sk += +x.kcal || 0; sb += +x.bialko_g || 0; });
      return Object.assign({}, d, { widok: ms, suma_kcal: Math.round(sk), suma_bialko: Math.round(sb) });
    });
    return { days: days, zakupy: order.map(function (k) { var e = shop[k]; return { produkt: e.produkt, dzial: e.dzial, ilosc: sumQ(e.ilosci.map(function (q) { return scale(q, W.portions || 1); })) }; }) };
  }
  function key(z) { return z.produkt.toLowerCase(); }

  /* ---------------- profil smaku: ANKIETA GUSTOW (pary "to czy to", skale lubie/obojetne/nie, pojedynczy wybor, "inne").
     Bada preferencje, nie wbija skladnikow -- AI traktuje odpowiedzi jako sygnaly gustu (qbot_food_weekend.SURVEY). */
  var LK = [["lubię", "👍"], ["obojętne", "😐"], ["nie lubię", "👎"]];
  function pairKey(p) { return p[0] + " | " + p[1]; }
  function profileSummary(a) {
    var like = [], dis = [], pr = [];
    PR.survey.forEach(function (q) {
      var v = a[q.key];
      if (q.type === "pairs" && v) q.options.forEach(function (p) { var c = v[pairKey(p)]; if (c && c !== "obojętne") pr.push(c); });
      if (q.type === "likert" && v) Object.keys(v).forEach(function (k) { if (v[k] === "lubię") like.push(k); if (v[k] === "nie lubię") dis.push(k); });
      if (q.type === "single" && v) pr.push(q.q.replace(/\?$/, "") + ": " + v);
    });
    return (pr.length ? "<b>Wybierasz:</b> " + esc(pr.join(", ")) + "<br>" : "") + (like.length ? "<b>👍</b> " + esc(like.join(", ")) + "<br>" : "") +
      (dis.length ? "<b>👎</b> " + esc(dis.join(", ")) + "<br>" : "") + (a.inne ? "<b>Inne:</b> " + esc(a.inne) : "");
  }
  function profileCard() {
    if (!PR) return "";
    var a = PR.answers || {};
    if (!survey) {
      return '<div class="card"><div class="ttl"><h2>🍜 Profil smaku</h2><button class="btn sm" id="wk-sv">' + (PR.saved ? "Zmień" : "Wypełnij ankietę") + '</button></div>' +
        '<p class="note">' + (PR.saved ? profileSummary(a) : 'Ankieta gustów (~2 min, same kliknięcia): kilka par „to czy to” i skale 👍 / 😐 / 👎. Na start: ' + profileSummary(a)) + '</p>' +
        '<p class="note">Zasada stała: kolacja i przekąska turbo proste (bez gotowania), śniadanie proste, obiad może być bardziej złożony. ' +
        'Oceny zjedzonych dań (w Dniach) uczą QBota dalej.</p></div>';
    }
    var h = '<div class="card"><h2>🍜 Ankieta gustów</h2><p class="note">Nie ma złych odpowiedzi — „obojętne” też jest informacją.</p>';
    PR.survey.forEach(function (q) {
      var v = a[q.key];
      h += '<div style="margin-top:14px"><div class="note" style="font-weight:600;color:var(--ink)">' + esc(q.q) + '</div>';
      if (q.type === "pairs") {
        v = v || {};
        q.options.forEach(function (p) {
          var c = v[pairKey(p)];
          h += '<div class="seg" role="group" style="margin-top:6px;display:flex;flex-wrap:wrap">' + [p[0], "obojętne", p[1]].map(function (o) {
            return '<button data-sp="' + q.key + '" data-pk="' + esc(pairKey(p)) + '" data-pv="' + esc(o) + '" class="' + (c === o ? "on" : "") + '">' + (o === "obojętne" ? "😐" : esc(o)) + '</button>'; }).join("") + '</div>';
        });
      } else if (q.type === "likert") {
        v = v || {};
        h += '<div class="kv" style="grid-template-columns:1fr auto">' + q.options.map(function (o) {
          return '<span>' + esc(o) + '</span><span class="seg" role="group">' + LK.map(function (l) {
            return '<button data-sl="' + q.key + '" data-lo="' + esc(o) + '" data-lv="' + l[0] + '" class="' + (v[o] === l[0] ? "on" : "") + '" aria-label="' + l[0] + '">' + l[1] + '</button>'; }).join("") + '</span>'; }).join("") + '</div>';
      } else {
        h += '<div class="chips">' + q.options.map(function (o) { return '<button class="btn sm' + (v === o ? " pri" : "") + '" data-ss="' + q.key + '" data-so="' + esc(o) + '">' + esc(o) + '</button>'; }).join("") + '</div>';
      }
      h += '</div>';
    });
    h += '<div style="margin-top:14px"><div class="note" style="font-weight:600;color:var(--ink)">Coś jeszcze? (opcjonalnie)</div>' +
      '<input id="wk-inne" type="text" maxlength="300" value="' + esc(a.inne || "") + '" placeholder="np. konjac kupuję gotowy; nie lubię ryb w panierce" style="width:100%"></div>' +
      '<div class="acts" style="margin-top:12px"><button class="btn pri" id="wk-sv-save">Zapisz profil</button><button class="btn" id="wk-sv-x">Anuluj</button></div>' +
      '<p class="note">Po zapisie: „Ułóż nowe propozycje” — albo poczekaj do czwartku, QBot ułoży je sam.</p></div>';
    return h;
  }

  /* ---------------- propozycje */
  function option(d, s, k, o, i, on) {
    var home = k === "dom";
    var h = '<div class="ent" style="' + (on ? "border-left:3px solid var(--accent);padding-left:8px;background:var(--accent-bg);border-radius:8px" : "padding-left:11px") + '">' +
      '<label style="display:flex;gap:8px;align-items:flex-start;cursor:pointer"><input type="radio" name="o-' + d.day + "-" + esc(s.pora) + '" data-ch="' +
      d.day + "|" + esc(s.pora) + "|" + k + "|" + i + '"' + (on ? " checked" : "") + ' style="margin-top:4px;accent-color:var(--accent)">' +
      '<span style="flex:1"><span class="eh"><span>' + (o.wlasna ? "✍️ " : "") + '<b data-rcp="' + d.day + "|" + esc(s.pora) + "|" + k + "|" + i +
      '" title="Pokaż przepis" style="cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px">' + esc(o.nazwa || "") + '</b>' +
      (home ? ' <span class="note">· ' + (o.czas_min ? n0(o.czas_min) + ' min' : '') + (o.thermomix ? ' · Thermomix' : '') + '</span>' : '') +
      '</span><span class="k">~' + n0(o.kcal) + ' kcal · ' + n0(o.bialko_g) + ' g B</span></span>' +
      (!home && o.zamow ? '<span class="note" style="display:block">Zamów: ' + esc(o.zamow) + '</span>' : '') +
      (o.uwagi ? '<span class="note" style="display:block">' + esc(o.uwagi) + '</span>' : '') + '</span></label>';
    if (home && ((o.skladniki || []).length || (o.kroki || []).length))
      h += '<button class="btn sm" data-rcp="' + d.day + "|" + esc(s.pora) + "|" + k + "|" + i + '" style="margin:4px 0 0 26px">📖 przepis (na ' + (W.portions || 1) + ' os.)</button>';
    return h + '</div>';
  }
  /* 17.10: okno z przepisem -- klik w nazwe posilku albo 📖 */
  function recipe(key) {
    var a = key.split("|"), dd = (P().days || []).filter(function (x) { return x.day === a[0]; })[0]; if (!dd) return;
    var ss = (dd.slots || []).filter(function (x) { return x.pora === a[1]; })[0]; if (!ss) return;
    var o = (ss[a[2]] || [])[+a[3]]; if (!o) return;
    showRecipe(o, (DNAME[dd.day] || dd.day) + " " + dd.date + " · " + ss.pora, W.portions || 1, a[2] === "dom");
  }
  /* 17.10: jedno okno przepisu -- Plan weekendu i karta Dnia w Dzienniku (window.qWkRecipe) */
  function showRecipe(o, gdzie, n, home) {
    n = n || 1;
    var h = "<div class='qbox' style='max-width:640px'><div class='ttl'><h2>" + (o.wlasna ? "✍️ " : "") + esc(o.nazwa || "") + "</h2><button class='btn sm' data-x='1' aria-label='Zamknij'>✕</button></div>" +
      "<p class='note' style='margin-top:0'>" + esc(gdzie || "") + " · ~" + n0(o.kcal) + " kcal · " + n0(o.bialko_g) + " g białka na osobę" +
      (home && o.czas_min ? " · " + n0(o.czas_min) + " min" : "") + (home && o.thermomix ? " · Thermomix" : "") + "</p>";
    if (!home) h += o.zamow ? "<p><b>Zamów:</b> " + esc(o.zamow) + "</p>" : "<p class='note'>Posiłek na mieście — bez przepisu.</p>";
    if ((o.skladniki || []).length) h += "<h3 style='margin:12px 0 4px;font-size:15px'>Składniki (na " + n + " os.)</h3><ul class='recs'>" +
      o.skladniki.map(function (x) { return "<li>" + esc(scale(x, n)) + "</li>"; }).join("") + "</ul>";
    if ((o.kroki || []).length) h += "<h3 style='margin:12px 0 4px;font-size:15px'>Przygotowanie</h3><ol class='recs'>" +
      o.kroki.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ol>";
    if (home && !(o.skladniki || []).length && !(o.kroki || []).length) h += "<p class='note'>Ta propozycja nie ma jeszcze rozpisanego przepisu — „🔄 inne” w Planie weekendu ułoży nowe z przepisem.</p>";
    if (o.uwagi) h += "<p class='note'>" + esc(o.uwagi) + "</p>";
    var ov = document.createElement("div"); ov.className = "qmodal"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-modal", "true"); ov.innerHTML = h + "</div>";
    function close() { document.removeEventListener("keydown", esck); ov.remove(); }
    function esck(e) { if (e.key === "Escape") close(); }
    ov.addEventListener("click", function (e) { if (e.target === ov || e.target.dataset.x) close(); });
    document.addEventListener("keydown", esck); document.body.appendChild(ov);
  }

  function day(d, vd) {
    var md = (P().modes || {})[d.day] || "dom", diff = vd.suma_kcal - (d.cel_kcal || 0);
    var h = '<div class="card"><div class="ttl"><h2>' + esc(DNAME[d.day] || d.day) + ' ' + esc(d.date) + ' · cel ~' + n0(d.cel_kcal) + ' kcal</h2>' +
      '<span class="seg" role="group" aria-label="Gdzie jem">' +
      '<button data-md="' + d.day + ':dom" class="' + (md === "dom" ? "on" : "") + '">🏠 W domu</button>' +
      '<button data-md="' + d.day + ':miasto" class="' + (md === "miasto" ? "on" : "") + '">🍽 Na mieście</button></span></div>';
    if ((d.treningi || []).length) h += '<p class="note">🚲 ' + esc(d.treningi.join("; ")) + (d.wegle_na_rower_g ? ' · na rower ~' + n0(d.wegle_na_rower_g) + ' g węgli' : '') + '</p>';
    (d.slots || []).forEach(function (s) {
      var k = kindOf(d, s), opts = s[k] || []; if (!opts.length) return;
      var c = chosen(d, s, k), id = d.day + "|" + esc(s.pora);
      if (skipped(d, s)) { h += '<div style="margin-top:12px" class="eh"><span class="note">' + (PORA[s.pora] || "•") + ' ' + esc(s.pora) + ' — 🚫 usunięty z menu (zjadłeś coś innego)</span>' +
        '<span class="acts"><button class="btn sm" data-sku="' + id + '">↩︎ przywróć</button></span></div>'; return; }
      h += '<div style="margin-top:12px"><div class="eh"><span class="note" style="font-weight:600;color:var(--ink)">' + (PORA[s.pora] || "•") + ' ' + esc(s.pora) +
        ' <span class="note">(' + (k === "dom" ? "w domu" : "na mieście") + ')</span></span>' +
        '<span class="acts"><button class="btn sm" data-rg="' + id + '|' + k + '" title="3 nowe propozycje tego posiłku">🔄 inne</button>' +
        '<button class="btn sm" data-sk="' + id + '" title="Usuń z menu dnia — np. zjadłeś coś innego">✕ usuń</button>' +
        (k === "dom" ? '<button class="btn sm" data-cw="' + id + '">✍️ moja wersja</button>' : '') + '</span></div>';
      if (k === "dom") h += '<div class="acts" data-cwbox="' + id + '" hidden style="margin:4px 0"><input type="text" maxlength="300" data-cin="' + id +
        '" placeholder="np. konjac po chińsku w sosie sojowym z kurczakiem/krewetkami" style="flex:1"><button class="btn" data-cgo="' + id + '">Ułóż</button></div>';
      opts.forEach(function (o, i) { h += option(d, s, k, o, i, i === c); });
      h += '</div>';
    });
    if (!(d.slots || []).length) h += '<p class="empty">Brak propozycji — „Ułóż nowe propozycje”.</p>';
    h += '<div class="kv" style="margin-top:12px"><span>Wybrane razem</span><span><b>~' + n0(vd.suma_kcal) + ' kcal</b> / cel ' + n0(d.cel_kcal) +
      ' <span class="note">(' + (diff >= 0 ? "+" : "") + n0(diff) + ')</span></span><span>Białko</span><span>~' + n0(vd.suma_bialko) + ' g / ' + n0(d.bialko_g) + ' g</span></div>';
    if (d.unikaj) h += '<p class="note">✋ ' + esc(d.unikaj) + '</p>';
    return h + '</div>';
  }

  function shopCard(v) {
    var ch = W.checked || {}, nc = v.zakupy.filter(function (z) { return ch[key(z)]; }).length, h = "";
    h += '<div class="card"><div class="ttl"><h2>🛒 Lista zakupów</h2><span class="acts"><span class="note">' + nc + ' do kupienia</span>' +
      '<button class="btn pri" id="wk-export"' + (nc ? '' : ' disabled') + '>📝 Do Notatek</button></span></div>' +
      '<p class="note">Z wybranych posiłków, na ' + (W.portions || 1) + ' os. Zaznacz to, czego <b>nie masz</b> w domu — tylko zaznaczone trafią do Notatek.</p>';
    if (!v.zakupy.length) h += '<p class="empty">Nic do kupienia.</p>';
    var by = {}; v.zakupy.forEach(function (z) { var d = DZ.indexOf(z.dzial) >= 0 ? z.dzial : "inne"; (by[d] = by[d] || []).push(z); });
    DZ.forEach(function (d) {
      if (!by[d]) return;
      h += '<div class="note" style="margin-top:10px;font-weight:600">' + esc(d) + '</div>';
      by[d].forEach(function (z) {
        var k = key(z), on = !!ch[k];
        h += '<label class="meal" style="cursor:pointer"><span class="nm" style="' + (on ? "" : "color:var(--ink2)") + '">' +
          '<input type="checkbox" data-k="' + esc(k) + '"' + (on ? " checked" : "") + ' style="margin-right:8px;width:18px;height:18px;vertical-align:-3px;accent-color:var(--accent)">' +
          '<b>' + esc(z.produkt) + '</b></span><span class="mx">' + esc(z.ilosc || "") + '</span></label>';
      });
    });
    return h + '<p class="note">W Notatkach: zaznacz tekst → „Lista kontrolna”.</p></div>';
  }

  function render() {
    var box = $("weekend"); if (!box) return;
    if (!W || !W.plan) { box.innerHTML = '<div class="dgrid"><div class="stack"><p class="empty">Brak propozycji. <button class="btn pri" id="wk-build">Ułóż propozycje</button></p></div><div class="stack">' + profileCard() + '</div></div>'; bind(); return; }
    var p = P(), v = view(), h = "";
    h += '<div class="ttl"><h2>Weekend ' + esc(W.weekend) + '</h2><span class="acts">' +
      '<span class="seg" role="group" aria-label="Liczba osób">' + [1, 2, 3].map(function (n) {
        return '<button data-por="' + n + '" class="' + (W.portions === n ? "on" : "") + '">' + n + (n === 1 ? " osoba" : " os.") + '</button>'; }).join("") + '</span>' +
      '<button class="btn" id="wk-build">Ułóż nowe propozycje</button></span></div>';
    h += '<p class="note">1) Wybierz po jednej propozycji na posiłek (🔄 inne / ✍️ moja wersja, jeśli nic nie pasuje). 2) Zatwierdź — powstanie lista zakupów, ' +
      'a posiłki trafią do <b>Dni</b> (tam „Zjadłem” i ocena). Kalorie posiłków to szacunek; cel dnia i paliwo na rower z planu QBota. Ułożone ' + esc(W.built_at) + '.</p>';
    if (p.error) h += '<p class="msg">Część propozycji się nie ułożyła (' + esc(p.error) + ').</p>';
    h += '<div class="dgrid"><div class="stack">' + (p.days || []).map(function (d, i) { return day(d, v.days[i]); }).join("") +
      '<div class="card">' + (p.confirmed_at ? '<p class="state ok">✅ Zatwierdzone ' + esc(p.confirmed_at) + ' — lista zakupów obok, posiłki w zakładce Dni.</p>'
        : '<button class="btn pri" id="wk-confirm" style="width:100%;padding:10px">✅ Zatwierdź wybór → lista zakupów i plan w Dniach</button>') + '</div>' +
      '</div><div class="stack">' + (p.confirmed_at ? shopCard(v) : '<div class="card"><h2>🛒 Lista zakupów</h2><p class="empty">Pojawi się po zatwierdzeniu wyboru.</p></div>') +
      profileCard() + '</div></div>';
    box.innerHTML = h; bind();
  }

  function exportList() {
    var v = view(), ch = W.checked || {}, by = {}, L = ["Zakupy na weekend " + W.weekend, ""];
    v.zakupy.forEach(function (z) { if (!ch[key(z)]) return; var d = DZ.indexOf(z.dzial) >= 0 ? z.dzial : "inne"; (by[d] = by[d] || []).push(z); });
    DZ.forEach(function (d) {
      if (!by[d]) return;
      L.push(d.charAt(0).toUpperCase() + d.slice(1) + ":");
      by[d].forEach(function (z) { L.push(z.produkt + (z.ilosc ? " — " + z.ilosc : "")); });
      L.push("");
    });
    var txt = L.join("\n").trim(), btn = $("wk-export");
    function done(msg) { if (btn) { btn.textContent = msg; setTimeout(function () { btn.textContent = "📝 Do Notatek"; }, 2500); } }
    if (navigator.share) {
      navigator.share({ title: "Zakupy na weekend " + W.weekend, text: txt }).then(function () { done("Wysłano ✓"); })
        .catch(function (e) { if (e && e.name !== "AbortError") copy(txt, done); });
    } else copy(txt, done);
  }
  function copy(txt, done) {
    (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(function () { done("Skopiowano — wklej w Notatkach"); })
      .catch(function () { window.prompt("Skopiuj listę:", txt); });
  }
  function save(u, b) { return post(u, Object.assign({ friday: W.friday }, b)).then(function (x) { if (x && x.plan) { W = x; render(); } }).catch(function () {}); }
  function slow(btn, u, b, label) {
    if (busy) return; busy = true; btn.disabled = true; btn.textContent = label || "Układam… (~20 s)";
    post(u, Object.assign({ friday: W.friday }, b)).then(function (x) { if (x && x.plan) W = x; render(); })
      .catch(function (e) { btn.disabled = false; alert("Nie udało się: " + e.message); render(); }).then(function () { busy = false; });
  }

  function bind() {
    var q = function (id, fn) { var e = $(id); if (e) e.onclick = fn; };
    q("wk-export", exportList);
    q("wk-build", function () { if (!W || !W.plan || confirm("Ułożyć wszystkie propozycje od nowa? Obecne wybory znikną.")) rebuild(); });
    q("wk-confirm", function () { P().confirmed_at = "teraz"; render(); save("/api/jedzenie/weekend/confirm", {}); });
    q("wk-sv", function () { survey = true; render(); });
    q("wk-sv-x", function () { survey = false; loadProfile(); });
    q("wk-sv-save", function () {
      PR.answers.inne = ($("wk-inne").value || "").trim();
      post("/api/jedzenie/weekend/profile", { answers: PR.answers }).then(function (x) { PR = x; survey = false; render(); });
    });
    function keepInne() { var inne = $("wk-inne"); if (inne) PR.answers.inne = inne.value; }
    document.querySelectorAll("#weekend [data-sp]").forEach(function (b) {
      b.onclick = function () { keepInne(); var m = PR.answers[b.dataset.sp] = PR.answers[b.dataset.sp] || {}; m[b.dataset.pk] = m[b.dataset.pk] === b.dataset.pv ? "" : b.dataset.pv; render(); };
    });
    document.querySelectorAll("#weekend [data-sl]").forEach(function (b) {
      b.onclick = function () { keepInne(); var m = PR.answers[b.dataset.sl] = PR.answers[b.dataset.sl] || {}; m[b.dataset.lo] = m[b.dataset.lo] === b.dataset.lv ? "" : b.dataset.lv; render(); };
    });
    document.querySelectorAll("#weekend [data-ss]").forEach(function (b) {
      b.onclick = function () { keepInne(); var a = PR.answers; a[b.dataset.ss] = a[b.dataset.ss] === b.dataset.so ? "" : b.dataset.so; render(); };
    });
    if (!W || !W.plan) return;
    document.querySelectorAll("#weekend [data-por]").forEach(function (x) {
      x.onclick = function () { var n = +x.dataset.por; if (n === W.portions) return; W.portions = n; render(); save("/api/jedzenie/weekend/portions", { n: n }); };
    });
    document.querySelectorAll("#weekend [data-md]").forEach(function (x) {
      x.onclick = function () {
        var a = x.dataset.md.split(":"); P().modes = P().modes || {};
        if (P().modes[a[0]] === a[1]) return;
        P().modes[a[0]] = a[1]; P().confirmed_at = null; render();
        save("/api/jedzenie/weekend/mode", { day: a[0], mode: a[1] });
      };
    });
    document.querySelectorAll("#weekend input[data-ch]").forEach(function (r) {
      r.onchange = function () {
        var a = r.dataset.ch.split("|"); P().choice = P().choice || {};
        P().choice[a[0] + "|" + a[1] + "|" + a[2]] = +a[3]; P().confirmed_at = null; render();
        save("/api/jedzenie/weekend/choice", { day: a[0], pora: a[1], kind: a[2], idx: +a[3] });
      };
    });
    document.querySelectorAll("#weekend [data-rcp]").forEach(function (b) {
      b.onclick = function (e) { e.preventDefault(); e.stopPropagation(); recipe(b.dataset.rcp); };
    });
    document.querySelectorAll("#weekend [data-sk],#weekend [data-sku]").forEach(function (b) {   /* 17.10: usun / przywroc posilek */
      b.onclick = function () { var u = !!b.dataset.sku, a = (b.dataset.sk || b.dataset.sku).split("|");
        if (!u && !confirm("Usunąć " + a[1] + " z menu tego dnia? Zniknie z sumy kcal i listy zakupów.")) return;
        var sk = P().skip = P().skip || {}; if (u) delete sk[a[0] + "|" + a[1]]; else sk[a[0] + "|" + a[1]] = true; render();
        save("/api/jedzenie/weekend/skip", { day: a[0], pora: a[1], undo: u }); };
    });
    document.querySelectorAll("#weekend [data-rg]").forEach(function (b) {
      b.onclick = function () { var a = b.dataset.rg.split("|"); slow(b, "/api/jedzenie/weekend/regen", { day: a[0], pora: a[1], kind: a[2] }); };
    });
    document.querySelectorAll("#weekend [data-cw]").forEach(function (b) {
      b.onclick = function () { var box = document.querySelector('#weekend [data-cwbox="' + b.dataset.cw + '"]'); if (box) { box.hidden = !box.hidden; var i = box.querySelector("input"); if (i) i.focus(); } };
    });
    document.querySelectorAll("#weekend [data-cgo]").forEach(function (b) {
      b.onclick = function () {
        var a = b.dataset.cgo.split("|"), inp = document.querySelector('#weekend input[data-cin="' + b.dataset.cgo + '"]');
        var t = (inp && inp.value || "").trim(); if (t) slow(b, "/api/jedzenie/weekend/custom", { day: a[0], pora: a[1], text: t });
      };
    });
    document.querySelectorAll("#weekend input[data-cin]").forEach(function (i) {
      i.onkeydown = function (e) { if (e.key === "Enter") { var b = document.querySelector('#weekend [data-cgo="' + i.dataset.cin + '"]'); if (b) b.click(); } };
    });
    document.querySelectorAll("#weekend input[data-k]").forEach(function (cb) {
      cb.onchange = function () {
        W.checked = W.checked || {}; if (cb.checked) W.checked[cb.dataset.k] = true; else delete W.checked[cb.dataset.k];
        render();
        post("/api/jedzenie/weekend/check", { friday: W.friday, key: cb.dataset.k, on: cb.checked }).catch(function () {});
      };
    });
  }

  function rebuild() {
    if (busy) return; busy = true;
    $("weekend").innerHTML = '<p class="empty">Układam propozycje na weekend wg profilu smaku… to trwa 1–2 minuty.</p>';
    post("/api/jedzenie/weekend/build", { friday: W && W.friday }).then(function (x) { W = x; render(); })
      .catch(function (e) { $("weekend").innerHTML = '<p class="msg">Nie udało się ułożyć: ' + esc(e.message) + '</p>'; })
      .then(function () { busy = false; });
  }
  function loadProfile() { return j("/api/jedzenie/weekend/profile").then(function (x) { PR = x; render(); }).catch(function () {}); }

  window.qWeekendLoad = function () {
    if (W || busy) { render(); return; }
    busy = true;
    $("weekend").innerHTML = '<p class="empty">Wczytuję propozycje na weekend… (jeśli nie były jeszcze ułożone, potrwa to 1–2 minuty)</p>';
    Promise.all([j("/api/jedzenie/weekend/profile").catch(function () { return null; }), j("/api/jedzenie/weekend")]).then(function (r) {
      PR = r[0]; W = r[1]; render();
    }).catch(function (e) { $("weekend").innerHTML = '<p class="msg">Nie udało się wczytać: ' + esc(e.message) + '</p>'; })
      .then(function () { busy = false; });
  };
})();
