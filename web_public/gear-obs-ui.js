/* gear-obs-ui.js (2026-10-18, GEAR-OBS etap 2, docs/GEAR_OBS.md + DECISIONS GEAR-OBS).
   1) Okienko po zapisie uwagi (W czym jechalem / Uwagi do AI): QGearObs.watch(note_id) odpytuje /api/gear-obs/note/{id};
      pytanie AI -> pole odpowiedzi (POST /api/gear-obs/answer); gotowe -> zapisane obserwacje + "Cos zle odczytane? Dopisz wyjasnienie".
   2) Garaz: w oknie rzeczy (#gearModal, id z #m_id) sekcja "Obserwacje z jazd (AI)": co wiemy, obserwacje, propozycja zmiany
      oceny z audytu z przyciskami Zatwierdz / Odrzuc (POST /api/gear-obs/proposal). Audyt zmienia sie tylko po Zatwierdz. */
(function () {
"use strict";
var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
function jget(u) { return fetch(u, { credentials: "same-origin", cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }); }
function jpost(u, b) { return fetch(u, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })
  .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status)); return j; }); }); }
var WG = { slaba: "słaba", srednia: "średnia", mocna: "mocna" }, PW = { niska: "niska", srednia: "średnia", wysoka: "wysoka" };
var ASP = { woda: "woda", cieplo: "za ciepło", zimno: "zimno", wiatr: "wiatr", pot: "pot", komfort: "komfort", dopasowanie: "dopasowanie", trwalosc: "trwałość", inne: "inne" };
var css = document.createElement("style");
css.textContent =
  "#qgo{position:fixed;right:16px;bottom:16px;z-index:9999;width:min(420px,calc(100vw - 32px));max-height:70vh;overflow:auto;background:var(--card,#fff);color:var(--ink,#111);" +
  "border:1px solid var(--line,#ccc);border-radius:12px;box-shadow:0 8px 30px #0005;padding:12px 14px;font-size:14px;line-height:1.4}" +
  "#qgo .h{display:flex;justify-content:space-between;align-items:center;font-weight:700;margin-bottom:6px}#qgo .x{border:0;background:none;color:inherit;font-size:22px;line-height:1;cursor:pointer}" +
  "#qgo .o,.qgo-o{margin:5px 0;padding:6px 8px;border-radius:8px;background:var(--well,#8881)}#qgo .k,.qgo-k{color:var(--muted,#888);font-size:12.5px}" +
  "#qgo textarea{width:100%;box-sizing:border-box;font:inherit;margin:6px 0;border:1px solid var(--line,#ccc);border-radius:8px;padding:6px;background:var(--card,#fff);color:var(--ink,#111)}" +
  "#qgo button.b,.qgo-box button.b{font:inherit;padding:5px 12px;border-radius:8px;border:1px solid var(--line,#ccc);background:var(--card,#fff);color:var(--ink,#111);cursor:pointer;margin:4px 6px 0 0}" +
  "#qgo button.p,.qgo-box button.p{background:var(--accent,#e67e22);color:#fff;border-color:transparent}" +
  "@media(max-width:600px){#qgo{right:8px;left:8px;bottom:8px;width:auto}}" +
  ".qgo-box{margin:14px 0 4px;border:1px solid var(--line,#3334);border-radius:10px;padding:8px 12px}.qgo-box summary{cursor:pointer;font-weight:600}" +
  ".qgo-box summary .qgo-k{font-weight:400;margin-left:8px}" +
  ".qgo-top{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0}.qgo-cw{flex:1 1 320px}.qgo-top .qgo-prop{flex:1 1 280px;margin:0}" +
  ".qgo-row{display:flex;gap:8px;overflow-x:auto;padding:2px 0 6px;scroll-snap-type:x proximity}.qgo-row .qgo-o{flex:0 0 280px;margin:0;scroll-snap-align:start}.qgo-prop{margin:8px 0;padding:8px 10px;border-radius:8px;border:1px dashed var(--accent,#e67e22)}";
document.head.appendChild(css);

function nm(o) { return ((o.brand || "") + " " + (o.model || "")).trim() || ("#" + o.gear_id); }
function obsLine(o) {
  return '<div class="o"><b>' + esc(nm(o)) + "</b> — " + esc(o.opis) + '<div class="k">' + esc(ASP[o.aspekt] || o.aspekt || "") + " · waga " + esc(WG[o.waga] || o.waga) +
    (o.inne_przyczyny ? " · inne możliwe przyczyny: " + esc(o.inne_przyczyny) : "") + "</div></div>";
}

/* ---------- okienko po zapisie uwagi ---------- */
var BOXT = null;
function box() { var b = document.getElementById("qgo"); if (!b) { b = document.createElement("div"); b.id = "qgo"; document.body.appendChild(b); } return b; }
function close() { clearTimeout(BOXT); var b = document.getElementById("qgo"); if (b) b.remove(); }
function head() { return '<div class="h">Uwaga o sprzęcie<button class="x" type="button" aria-label="Zamknij">×</button></div>'; }
function bindX(b) { var x = b.querySelector(".x"); if (x) x.onclick = close; }
function watch(id, t0) {
  t0 = t0 || Date.now(); clearTimeout(BOXT);
  var b = box();
  jget("/api/gear-obs/note/" + id).then(function (n) {
    if (!n.ok) { close(); return; }
    if (n.status === "przetwarzanie") {
      b.innerHTML = head() + '<div class="k">' + (Date.now() - t0 < 120000 ? "AI przypisuje uwagę do rzeczy z Garażu…" : "Trwa dłużej niż zwykle — wynik zobaczysz w Garażu przy rzeczy.") + "</div>";
      bindX(b);
      if (Date.now() - t0 < 120000) BOXT = setTimeout(function () { watch(id, t0); }, 3000);
      return;
    }
    render(b, n);
  }).catch(function () { if (Date.now() - t0 < 120000) BOXT = setTimeout(function () { watch(id, t0); }, 5000); });
}
function render(b, n) {
  var obs = n.obserwacje || [], h = head();
  if (n.status === "pytanie" && n.question) {
    h += "<div><b>Pytanie AI:</b> " + esc(n.question) + '</div><textarea rows="2" maxlength="600" id="qgo-a" placeholder="Twoja odpowiedź"></textarea>' +
      '<button type="button" class="b p" id="qgo-s">Odpowiedz</button><button type="button" class="b" id="qgo-c">Pomiń</button>';
    if (obs.length) h += '<div class="k" style="margin-top:8px">Już zapisane:</div>' + obs.map(obsLine).join("");
  } else if (n.status === "blad") {
    h += '<div class="k">Nie udało się przetworzyć uwagi: ' + esc(n.error || "") + "</div>";
  } else if (!obs.length) {
    h += '<div class="k">' + (n.status === "bez_rzeczy" ? "Brak zapisanego ubioru tej jazdy — AI nie ma do czego przypisać uwagi."
      : "Uwaga nie opisuje zdarzenia z konkretną rzeczą — nic nie zapisano przy rzeczach.") + "</div>";
  } else {
    h += '<div class="k">Zapisane jako obserwacje przy rzeczach (poszlaki — ocena z audytu bez zmian):</div>' + obs.map(obsLine).join("") +
      '<details style="margin-top:6px"><summary class="k" style="cursor:pointer">Coś źle odczytane? Dopisz wyjaśnienie</summary>' +
      '<textarea rows="2" maxlength="600" id="qgo-a" placeholder="np. chodziło o pot, nie o deszcz"></textarea><button type="button" class="b p" id="qgo-s">Popraw</button></details>';
  }
  b.innerHTML = h; bindX(b);
  var s = document.getElementById("qgo-s"), c = document.getElementById("qgo-c");
  if (c) c.onclick = close;
  if (s) s.onclick = function () {
    var a = (document.getElementById("qgo-a").value || "").trim(); if (!a) return; s.disabled = true;
    jpost("/api/gear-obs/answer", { note_id: n.id, answer: a }).then(function () { watch(n.id); if (GBOX) setTimeout(gLoad, 25000); })
      .catch(function (e) { s.disabled = false; alert("Nie zapisano: " + e.message); });
  };
}

/* ---------- Garaz: sekcja w oknie rzeczy ---------- */
var GBOX = null, GID = null;
function gOpen() {
  var idEl = document.getElementById("m_id"); GID = Number(idEl && idEl.value) || null;
  if (GBOX) { GBOX.remove(); GBOX = null; }
  if (!GID) return;
  var au = document.getElementById("mAudit"), ph = document.querySelector("#gearModal .mphoto"); if (!au && !ph) return;
  GBOX = document.createElement("details"); GBOX.className = "qgo-box";
  GBOX.innerHTML = '<summary>Obserwacje z jazd (AI)<span class="qgo-k" id="qgo-gi">wczytuję…</span></summary><div id="qgo-gb"></div>';
  if (au) au.parentNode.insertBefore(GBOX, au); else ph.parentNode.insertBefore(GBOX, ph.nextSibling);   /* 18.10: NAD Ocena z audytu */
  gLoad();
}
function gLoad() {
  var id = GID; if (!id || !GBOX) return;
  jget("/api/gear-obs/gear/" + id).then(function (d) { if (id === GID && GBOX) gRender(d); })
    .catch(function () { var i = document.getElementById("qgo-gi"); if (i) i.textContent = "nie udało się wczytać"; });
}
function gRender(d) {
  var i = document.getElementById("qgo-gi"), b = document.getElementById("qgo-gb"), obs = d.obserwacje || [], p = d.propozycja, czeka = p && d.proposal_status === "czeka";
  if (!i || !b) return;
  i.textContent = obs.length ? (obs.length + " obs. · pewność " + (PW[d.pewnosc] || d.pewnosc || "—") + (czeka ? " · propozycja zmiany oceny" : "")) : "brak";
  if (czeka) GBOX.open = true;
  var h = "";
  h += '<div class="qgo-top">';
  if (d.co_wiemy) h += '<div class="qgo-cw"><b>Co wiemy:</b> ' + esc(d.co_wiemy) + "</div>";
  if (p) h += '<div class="qgo-prop"><b>Propozycja zmiany oceny z audytu</b> (' + esc(czeka ? "czeka na Ciebie" : d.proposal_status) + "):<div>" +
    esc(p.etykieta || p.pole) + ": <b>" + esc(p.z_txt || "—") + "</b> → <b>" + esc(p.na_txt || p.na) + "</b></div>" +
    '<div class="qgo-k">' + esc(p.dlaczego || "") + (p.n_obs ? " (obserwacji: " + p.n_obs + ")" : "") + "</div>" +
    (czeka ? '<button type="button" class="b p" data-dec="zatwierdz">Zatwierdź</button><button type="button" class="b" data-dec="odrzuc">Odrzuć</button>' : "") + "</div>";
  h += "</div>";
  if (!obs.length) h += '<div class="qgo-k" style="margin:8px 0">Brak obserwacji. Powstają z uwag w „W czym jechałem” (raport jazdy) i „Uwag do AI” (Analiza trasy).</div>';
  if (obs.length) h += '<div class="qgo-row">';
  obs.forEach(function (o) {
    h += '<div class="qgo-o"><div class="qgo-k">' + esc(o.obs_date || "") + " · " + (o.source === "po_jezdzie" ? "po jeździe" : "przed jazdą") + " · " + esc(ASP[o.aspekt] || o.aspekt || "") +
      " · " + (o.wynik === "pozytywny" ? "✓" : o.wynik === "negatywny" ? "✗" : "•") + " waga " + esc(WG[o.waga] || o.waga) + "</div><div>" + esc(o.opis) + "</div>" +
      (o.inne_przyczyny ? '<div class="qgo-k">inne możliwe przyczyny: ' + esc(o.inne_przyczyny) + "</div>" : "") +
      '<div class="qgo-k">Twoja uwaga: „' + esc(o.uwaga) + "”" + (o.answer ? " · wyjaśnienie: „" + esc(o.answer) + "”" : "") +
      ' · <a href="#" data-fix="' + o.note_id + '">popraw</a></div></div>';
  });
  if (obs.length) h += "</div>";
  b.innerHTML = h;
  b.querySelectorAll("[data-dec]").forEach(function (x) { x.onclick = function () {
    if (x.dataset.dec === "zatwierdz" && !confirm("Zmienić ocenę z audytu: " + (p.etykieta || p.pole) + " → " + (p.na_txt || p.na) + "?")) return;
    x.disabled = true;
    jpost("/api/gear-obs/proposal", { gear_id: GID, decision: x.dataset.dec }).then(gLoad).catch(function (e) { x.disabled = false; alert(e.message); }); }; });
  b.querySelectorAll("[data-fix]").forEach(function (a) { a.onclick = function (ev) {
    ev.preventDefault();
    var t = prompt("Wyjaśnienie do tej uwagi (AI przeczyta ją jeszcze raz):"); if (!t || !t.trim()) return;
    jpost("/api/gear-obs/answer", { note_id: +a.dataset.fix, answer: t.trim() }).then(function () { watch(+a.dataset.fix); setTimeout(gLoad, 25000); })
      .catch(function (e) { alert(e.message); }); }; });
}
(function () {
  var m = document.getElementById("gearModal"); if (!m) return;
  var was = m.classList.contains("open");
  new MutationObserver(function () { var now = m.classList.contains("open"); if (now && !was) setTimeout(gOpen, 60); was = now; })
    .observe(m, { attributes: true, attributeFilter: ["class"] });
})();
window.QGearObs = { watch: function (id) { watch(id); } };
})();
