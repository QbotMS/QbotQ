/* Zdrowie > Suplementy (2026-10-13): lista suplementow/lekow z wersjami dawek, przyjecia (kalendarz do recznej poprawy),
   regularnosc. Potwierdzanie: rano za wczoraj przyciskiem w Telegramie; tu wyjatki. API: /api/supl (qbot_supplements.py). */
(function () {
  "use strict";
  var root = document.getElementById("supl");
  if (!root) return;
  var D = null, EDIT = null;
  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function dd(iso) { return iso ? iso.slice(8, 10) + "." + iso.slice(5, 7) + "." + iso.slice(0, 4) : "—"; }
  function dose(x, u) { return x == null ? "" : String(x).replace(".", ",") + " " + (u || ""); }
  var DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"];
  function api(method, url, body) {
    return fetch(url, {method: method, credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: body ? JSON.stringify(body) : undefined})
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status)); return j; }); });
  }
  function load() {
    api("GET", "/api/supl?days=35").then(function (j) { D = j; render(); })
      .catch(function (e) { root.innerHTML = '<div class="card">Nie udało się wczytać: ' + esc(e.message) + "</div>"; });
  }

  function form(it) {
    var x = it || {name: "", dose: "", unit: "mg", kind: "suplement", slot: "dowolnie", days: null};
    var slots = Object.keys(D.slots).map(function (k) { return '<option value="' + k + '"' + (x.slot === k ? " selected" : "") + ">" + esc(D.slots[k]) + "</option>"; }).join("");
    var days = DN.map(function (n, i) { var on = !x.days || x.days.indexOf(i) >= 0; return '<label style="margin-right:6px"><input type="checkbox" data-d="' + i + '"' + (on ? " checked" : "") + "> " + n + "</label>"; }).join("");
    return '<div class="card" id="sp-form" style="background:var(--well)">' +
      '<p class="lbl">' + (it ? "Edytuj: " + esc(it.name) : "Dodaj suplement lub lek") + "</p>" +
      '<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:end">' +
      '<label>Nazwa<br><input id="sp-name" value="' + esc(x.name) + '" style="width:180px"></label>' +
      '<label>Dawka<br><input id="sp-dose" value="' + esc(x.dose == null ? "" : x.dose) + '" style="width:80px" inputmode="decimal"></label>' +
      '<label>Jednostka<br><input id="sp-unit" value="' + esc(x.unit || "") + '" style="width:70px"></label>' +
      '<label>Rodzaj<br><select id="sp-kind"><option value="suplement"' + (x.kind === "suplement" ? " selected" : "") + '>suplement</option><option value="lek"' + (x.kind === "lek" ? " selected" : "") + ">lek</option></select></label>" +
      '<label>Pora<br><select id="sp-slot">' + slots + "</select></label>" +
      '<label>Dawka obowiązuje od<br><input id="sp-from" type="date" value="' + D.today + '"></label></div>' +
      '<div style="margin-top:8px;font-size:13.5px">Dni: ' + days + "</div>" +
      '<div style="margin-top:10px"><button class="btn" id="sp-save">Zapisz</button> <button class="btn" id="sp-cancel">Anuluj</button>' +
      (it ? ' <span class="muted" style="font-size:12px">Zmiana dawki zapisze się jako nowa wersja od podanego dnia – wcześniejsze dni zostają z poprzednią.</span>' : "") +
      '</div><div id="sp-err" style="color:var(--bad);font-size:13px;margin-top:6px"></div></div>';
  }

  function render() {
    var reg = D.regularity || {}, per = reg.items || {};
    var rows = D.items.map(function (it) {
      var p = per[it.id] || {}, hist = it.versions.length > 1 ? it.versions.map(function (v) { return dose(v.dose, v.unit) + " od " + dd(v.from); }).join(" → ") : "";
      return '<tr style="' + (it.active ? "" : "opacity:.5") + '"><td><b>' + esc(it.name) + "</b>" + (it.kind === "lek" ? ' <span class="muted">(lek)</span>' : "") +
        (hist ? '<div class="muted" style="font-size:11.5px">' + esc(hist) + "</div>" : "") + "</td>" +
        '<td class="num">' + esc(dose(it.dose, it.unit)) + "</td><td>" + esc(D.slots[it.slot] || it.slot) + "</td>" +
        "<td>" + (it.days ? it.days.map(function (d) { return DN[d]; }).join(", ") : "codziennie") + "</td>" +
        '<td class="num">' + (p.pct == null ? "—" : p.pct + "%") + '<div class="muted" style="font-size:11px">' + (p.plan ? p.taken + "/" + p.plan + (p.none ? ", " + p.none + " niepotw." : "") : "") + "</div></td>" +
        '<td style="white-space:nowrap"><button class="btn sp-ed" data-id="' + it.id + '" style="padding:2px 8px;font-size:12px">Edytuj</button> ' +
        '<button class="btn sp-act" data-id="' + it.id + '" style="padding:2px 8px;font-size:12px">' + (it.active ? "Wstrzymaj" : "Wznów") + "</button> " +
        '<button class="btn sp-del" data-id="' + it.id + '" style="padding:2px 8px;font-size:12px">Usuń</button></td></tr>';
    }).join("") || '<tr><td colspan="6" class="muted">Brak – dodaj pierwszy.</td></tr>';

    /* kalendarz przyjec: wiersze = pozycje, kolumny = dni (bez dzisiaj - potwierdzasz jutro rano) */
    var first = D.items.reduce(function (m, it) { var f = it.versions.length ? it.versions[0].from : null; return f && (!m || f < m) ? f : m; }, null);
    var days = Object.keys(D.scheduled).sort().filter(function (d) { return first && d >= first; });   /* bez pustych dni sprzed listy */
    var act = D.items.filter(function (it) { return it.active; });
    var head = "<tr><th></th>" + days.map(function (d) {
      var wd = (new Date(d + "T12:00:00").getDay() + 6) % 7;
      return '<th class="sp-day" data-d="' + d + '" title="Kliknij: wszystkie wzięte tego dnia" style="cursor:pointer;font-size:11px;text-align:center;padding:2px 3px">' + d.slice(8, 10) + "<br>" + DN[wd] + "</th>";
    }).join("") + "</tr>";
    var body = act.map(function (it) {
      return "<tr><td style=\"white-space:nowrap;font-size:13px\">" + esc(it.name) + "</td>" + days.map(function (d) {
        if ((D.scheduled[d] || []).indexOf(it.id) < 0) return "<td></td>";
        var l = D.log[d + ":" + it.id], st = l ? l.status : null;
        var sym = st === "taken" ? "✓" : st === "skipped" ? "✗" : "·";
        var col = st === "taken" ? "var(--good)" : st === "skipped" ? "var(--bad)" : "var(--muted)";
        return '<td class="sp-cell" data-d="' + d + '" data-id="' + it.id + '" data-s="' + (st || "") + '" title="' + dd(d) + ": " + (st === "taken" ? "wzięte" : st === "skipped" ? "pominięte" : "niepotwierdzone") +
          ' – kliknij, żeby zmienić" style="cursor:pointer;text-align:center;font-weight:700;color:' + col + ';border:1px solid var(--line)">' + sym + "</td>";
      }).join("") + "</tr>";
    }).join("");

    root.innerHTML =
      '<div class="card"><div class="cardhead"><p class="lbl">Suplementy i leki</p><button class="btn" id="sp-add" style="font-size:12.5px;padding:3px 10px">+ Dodaj</button></div>' +
      '<div id="sp-formbox"></div>' +
      '<div style="overflow-x:auto"><table class="qs-table"><tr><th>Nazwa</th><th class="num">Dawka</th><th>Pora</th><th>Dni</th><th class="num">Regularność 35 dni</th><th></th></tr>' + rows + "</table></div>" +
      '<div class="muted" style="font-size:12.5px;margin-top:6px">Potwierdzasz rano za wczoraj przyciskiem „💊 Wczoraj wszystkie wzięte” w Telegramie. Lista trafia też do raportu dla lekarza (Serce).</div></div>' +
      '<div class="card"><div class="cardhead"><p class="lbl">Przyjęcia – ostatnie 35 dni</p><span class="sub">regularność: <b>' + (reg.pct == null ? "—" : reg.pct + "%") + "</b>" +
      ((reg.unconfirmed_days || []).length ? " · niepotwierdzone dni: " + reg.unconfirmed_days.length : "") + "</span></div>" +
      (days.length && act.length ? '<div style="overflow-x:auto"><table style="border-collapse:collapse">' + head + body + "</table></div>" +
        '<div class="muted" style="font-size:12px;margin-top:6px">✓ wzięte · ✗ pominięte · · niepotwierdzone. Kliknij kratkę: wzięte → pominięte → niepotwierdzone. Kliknij datę: wszystkie wzięte tego dnia.</div>'
        : '<div class="muted">Brak dni do potwierdzenia – pierwszy pojawi się jutro (za dziś).</div>') + "</div>";

    $("sp-add").onclick = function () { EDIT = null; $("sp-formbox").innerHTML = form(null); wireForm(); };
    root.querySelectorAll(".sp-ed").forEach(function (b) { b.onclick = function () { EDIT = D.items.filter(function (x) { return x.id === +b.dataset.id; })[0]; $("sp-formbox").innerHTML = form(EDIT); wireForm(); }; });
    root.querySelectorAll(".sp-act").forEach(function (b) { b.onclick = function () { var it = D.items.filter(function (x) { return x.id === +b.dataset.id; })[0]; api("PUT", "/api/supl/" + it.id, {active: !it.active}).then(load); }; });
    root.querySelectorAll(".sp-del").forEach(function (b) { b.onclick = function () { if (confirm("Usunąć z listy? Historia przyjęć zostanie.")) api("DELETE", "/api/supl/" + b.dataset.id).then(load); }; });
    root.querySelectorAll(".sp-cell").forEach(function (td) {
      td.onclick = function () { var nx = td.dataset.s === "" ? "taken" : td.dataset.s === "taken" ? "skipped" : null;
        api("POST", "/api/supl/log", {day: td.dataset.d, id: +td.dataset.id, status: nx}).then(load); };
    });
    root.querySelectorAll(".sp-day").forEach(function (th) { th.onclick = function () { api("POST", "/api/supl/log", {day: th.dataset.d, all: true}).then(load); }; });
  }

  function wireForm() {
    $("sp-cancel").onclick = function () { $("sp-formbox").innerHTML = ""; };
    $("sp-save").onclick = function () {
      var days = [].slice.call(document.querySelectorAll("#sp-form input[data-d]")).filter(function (c) { return c.checked; }).map(function (c) { return +c.dataset.d; });
      var b = {name: $("sp-name").value, dose: $("sp-dose").value.replace(",", "."), unit: $("sp-unit").value, kind: $("sp-kind").value,
               slot: $("sp-slot").value, days: days.length === 7 ? null : days, from: $("sp-from").value};
      if (!b.name.trim()) { $("sp-err").textContent = "Podaj nazwę."; return; }
      if (!days.length) { $("sp-err").textContent = "Zaznacz co najmniej jeden dzień."; return; }
      var p;
      if (EDIT) {
        var u = {name: b.name, kind: b.kind, slot: b.slot, days: b.days};
        if (String(EDIT.dose) !== String(b.dose) || (EDIT.unit || "") !== b.unit) { u.dose = b.dose; u.unit = b.unit; u.from = b.from; }
        p = api("PUT", "/api/supl/" + EDIT.id, u);
      } else {
        p = api("POST", "/api/supl", b);
      }
      p.then(load).catch(function (e) { $("sp-err").textContent = e.message; });
    };
  }

  var btn = document.querySelector('#tabs button[data-t="suple"]');
  if (btn) btn.addEventListener("click", function () { if (!D) load(); });
  if (location.hash === "#suple") load();
})();
