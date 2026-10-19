/* raport-jazdy-trend.js (2026-10-19, PRODUKCJA; wcześniej raport-jazdy-test-trend.js): kafle z trendem zamiast samych liczb.
   "Rano przed jazdą": HRV / tętno spoczynkowe / sen wobec normy 60 dni + 14-dniowy wykresik + ocena.
   "Gotowość i forma": stan PRZED jazdą (dzień wcześniej): świeżość, forma, zmęczenie z trendem + poranna gotowość.
     (Wcześniej kafel pokazywał świeżość PO jeździe -- to idzie do "Po jeździe".)
   "Zmiana formy": wszystkie 4 parametry modelu (próg, LTP, zapas W′, szczyt) -- jawnie "bez zmian" przy zerowej zmianie.
   Dane: /api/forma/data?start&end (fitmodel_daily: hrv_night, rhr, sleep_h, readiness_score, ctl_xss, atl_real, tsb_real)
   + dane raportu (modelq.current / ride_impact). Wywoływane z raport-jazdy-uklad.js po przeniesieniu kafli. */
(function () {
"use strict";
var isNum = function (v) { return typeof v === "number" && isFinite(v); };
var V = function (x) { return (x && typeof x === "object" && "value" in x) ? x.value : x; };
var n = function (v, d) { return isNum(v) ? v.toFixed(d == null ? 0 : d).replace(".", ",") : "—"; };
var sg = function (v, d) { return isNum(v) ? (v > 0 ? "+" : v < 0 ? "−" : "±") + n(Math.abs(v), d) : "—"; };
function iso(d) { return d.toISOString().slice(0, 10); }
function addD(s, k) { var d = new Date(s + "T12:00:00"); d.setDate(d.getDate() + k); return iso(d); }
function median(a) { a = a.filter(isNum).sort(function (x, y) { return x - y; }); if (!a.length) return null; var m = a.length >> 1; return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2; }
function avg(a) { a = a.filter(isNum); return a.length ? a.reduce(function (s, x) { return s + x; }, 0) / a.length : null; }
function title(it) { var b = it.querySelector(".h b"); if (!b) return ""; var t = ""; b.childNodes.forEach(function (c) { if (c.nodeType === 3) t += c.textContent; }); return t.trim(); }
function spark(vals, base, col) {
  return "";   /* v5: wykresiki wylaczone (decyzja Michala) -- zostaje sam trend w tekscie */
  var v = vals.map(function (x) { return isNum(x) ? x : null; }), ok = v.filter(isNum); if (ok.length < 2) return "";
  var lo = Math.min.apply(null, ok.concat(isNum(base) ? [base] : [])), hi = Math.max.apply(null, ok.concat(isNum(base) ? [base] : [])); if (hi === lo) { hi += 1; lo -= 1; }
  var W = 110, H = 26, x = function (i) { return 2 + i * (W - 4) / (v.length - 1); }, y = function (q) { return H - 3 - (q - lo) / (hi - lo) * (H - 6); };
  var d = "", pen = false; v.forEach(function (q, i) { if (q == null) { pen = false; return; } d += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(q).toFixed(1) + " "; pen = true; });
  var li = v.length - 1; while (li >= 0 && v[li] == null) li--;
  return '<svg width="' + W + '" height="' + H + '" style="vertical-align:middle">' + (isNum(base) ? '<line x1="0" x2="' + W + '" y1="' + y(base).toFixed(1) + '" y2="' + y(base).toFixed(1) + '" stroke="currentColor" stroke-dasharray="2 3" opacity=".35"/>' : "") +
    '<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.8"/>' + (li >= 0 ? '<circle cx="' + x(li).toFixed(1) + '" cy="' + y(v[li]).toFixed(1) + '" r="3" fill="' + col + '"/>' : "") + "</svg>";
}
function row(lab, now, ref, sp, verdict, cls) {
  var c = cls === "bad" ? "#e2655c" : cls === "warn" ? "#e9b44c" : cls === "good" ? "#5cc08a" : "var(--ink2)";
  return '<div style="display:grid;grid-template-columns:8em 5em 1fr;gap:8px;align-items:center;padding:4px 0;border-bottom:1px solid var(--line);font-size:13.5px">' +
    '<span style="color:var(--ink2)">' + lab + '</span><b style="font-size:15px">' + now + '</b><span><span style="color:' + c + '">' + verdict + '</span>' + (ref ? ' <span style="color:var(--ink2);font-size:12px">' + ref + '</span>' : "") + '</span>' + sp + '</div>';
}
function rate(t, cls) { return '<span class="rate ' + (cls || "") + '">' + t + '</span>'; }

function rano(it, S, day, D) {
  var prev = S.filter(function (r) { return r.day < day; }), today = S.filter(function (r) { return r.day === day; })[0] || {};
  var b60 = prev.slice(-60), last14 = S.filter(function (r) { return r.day <= day; }).slice(-14);
  var hrvN = median(b60.map(function (r) { return r.hrv_night; })), rhrN = median(b60.map(function (r) { return r.rhr; })), slN = median(b60.map(function (r) { return r.sleep_h; }));
  var hrv = today.hrv_night, rhr = today.rhr, sl = today.sleep_h;
  var hp = isNum(hrv) && isNum(hrvN) ? (hrv / hrvN - 1) * 100 : null, rd = isNum(rhr) && isNum(rhrN) ? rhr - rhrN : null;
  var s7 = avg(S.filter(function (r) { return r.day <= day; }).slice(-7).map(function (r) { return r.sleep_h; }));
  var short = 0; for (var i = last14.length - 1; i >= 0 && isNum(last14[i].sleep_h) && last14[i].sleep_h < 6.5; i--) short++;
  var bad = [];
  if (isNum(hp) && hp < -8) bad.push("HRV poniżej normy");
  if (isNum(rd) && rd >= 3) bad.push("tętno spoczynkowe podniesione");
  if (isNum(sl) && sl < 6.5) bad.push(short >= 2 ? short + ". krótka noc z rzędu" : "krótki sen");
  var cls = bad.length >= 2 ? "bad" : bad.length ? "warn" : "good", lab = bad.length >= 2 ? "niedoregenerowany" : bad.length ? "lekki sygnał" : "wypoczęty";
  var head = bad.length ? "Organizm " + (bad.length >= 2 ? "<b>nie był zregenerowany</b>" : "z lekkim sygnałem") + ": " + bad.join(", ") + "." : "Organizm <b>wypoczęty</b> — wszystkie sygnały w normie.";
  var col = "#f08ac0", ser = function (k) { return last14.map(function (r) { return r[k]; }); };
  it.innerHTML = '<div class="h"><b>Rano przed jazdą</b>' + rate(lab, cls) + '</div><p style="font-size:15px;margin:6px 0 8px">' + head + '</p>' +
    row("HRV", n(hrv) + ' <small>ms</small>', "norma " + n(hrvN), spark(ser("hrv_night"), hrvN, col), isNum(hp) ? sg(hp, 0) + "%" : "—", isNum(hp) ? (hp < -8 ? "bad" : hp < -3 ? "warn" : "good") : "") +
    row("Tętno spocz.", n(rhr), "norma " + n(rhrN), spark(ser("rhr"), rhrN, col), isNum(rd) ? sg(rd, 0) + " ud." : "—", isNum(rd) ? (rd >= 3 ? "bad" : rd >= 1.5 ? "warn" : "good") : "") +
    row("Sen", n(sl, 1) + ' <small>h</small>', "śr. 7 dni " + n(s7, 1) + " h", spark(ser("sleep_h"), slN, col), isNum(sl) ? (sl < 6.5 ? "krótko" : sl < 7 ? "trochę mało" : "OK") : "—", isNum(sl) ? (sl < 6.5 ? "bad" : sl < 7 ? "warn" : "good") : "") +
    '<p style="color:var(--ink2);font-size:12px;margin:6px 0 0">Norma = mediana z 60 dni przed jazdą.' +
    (function () { var w = V(((D.physio || {}).wellness)) || {}; return isNum(w.bb_start) ? " Bateria ciała rano " + w.bb_start + (isNum(w.bb_end) ? " → wieczorem " + w.bb_end : "") + "." : ""; })() + "</p>";
  return { bad: bad, cls: cls };
}
function gotowosc(it, S, day) {
  var prevDay = S.filter(function (r) { return r.day < day; }), p = prevDay[prevDay.length - 1] || {}, today = S.filter(function (r) { return r.day === day; })[0] || {};
  var w14 = prevDay.slice(-14), p7 = prevDay[prevDay.length - 8] || {}, p28 = prevDay[prevDay.length - 29] || {};
  var tsb = p.tsb_real, ctl = p.ctl_real != null ? p.ctl_real : p.ctl_xss, atl = p.atl_real, rdy = today.readiness_score;
  var dT = isNum(tsb) && isNum(p7.tsb_real) ? tsb - p7.tsb_real : null, dC = isNum(ctl) && isNum(p28.ctl_real != null ? p28.ctl_real : p28.ctl_xss) ? ctl - (p28.ctl_real != null ? p28.ctl_real : p28.ctl_xss) : null;
  var tc = isNum(tsb) ? (tsb > 5 ? "good" : tsb > -10 ? "" : "bad") : "", tl = isNum(tsb) ? (tsb > 5 ? "świeży" : tsb > -10 ? "w normie" : "zmęczony") : "—";
  var col = "#f08ac0", ser = function (k) { return w14.map(function (r) { return r[k]; }); };
  var head = "Treningowo <b>" + (isNum(tsb) ? (tsb > 5 ? "wypoczęty" : tsb > -10 ? "w normie" : "zmęczony") : "—") + "</b> (świeżość " + sg(tsb, 0) + (isNum(dT) ? ", " + (dT > 0 ? "rosła" : "spadała") + " przez tydzień" : "") + ")" +
    (isNum(rdy) ? "; poranna gotowość organizmu <b>" + (rdy > 0.3 ? "wysoka" : rdy > -0.3 ? "neutralna" : "niska") + "</b>." : ".");
  it.innerHTML = '<div class="h"><b>Gotowość i forma</b>' + rate(tl, tc) + '</div><p style="font-size:15px;margin:6px 0 8px">' + head + '</p>' +
    row("Świeżość", sg(tsb, 0), isNum(dT) ? "7 dni: " + sg(dT, 0) : "", spark(ser("tsb_real"), 0, col), tl, tc) +
    row("Forma", n(ctl, 0), isNum(dC) ? "28 dni: " + sg(dC, 0) : "", spark(w14.map(function (r) { return r.ctl_real != null ? r.ctl_real : r.ctl_xss; }), null, col), isNum(dC) ? (dC > 1 ? "rośnie" : dC < -1 ? "spada" : "stabilna") : "—", isNum(dC) ? (dC > 1 ? "good" : dC < -1 ? "warn" : "") : "") +
    row("Zmęczenie", n(atl, 0), "", spark(ser("atl_real"), null, col), "", "") +
    row("Gotowość rano", sg(rdy, 2), "", spark(prevDay.slice(-13).concat([today]).map(function (r) { return r.readiness_score; }), 0, col), isNum(rdy) ? (rdy > 0.3 ? "wysoka" : rdy > -0.3 ? "neutralna" : "niska") : "—", isNum(rdy) ? (rdy > 0.3 ? "good" : rdy > -0.3 ? "" : "bad") : "") +
    '<p style="color:var(--ink2);font-size:12px;margin:6px 0 0">Stan na koniec dnia przed jazdą (' + (p.day || "—").split("-").reverse().slice(0, 2).join(".") + '). Świeżość po tej jeździe — w „Po jeździe”. Gotowość rano = HRV, tętno spoczynkowe i sen z dnia jazdy.</p>';
  return { tsb: tsb, rdy: rdy };
}
function zmiana(it, D) {
  var mq = D.modelq || {}, ri = mq.ride_impact || {}, c = mq.current || {};
  var P = [["Próg (CP)", c.ftp_w, ri.ftp_delta != null ? ri.ftp_delta : ri.cp_delta, "W", 0.5, 0], ["LTP", c.ltp_w, ri.ltp_delta, "W", 0.5, 0],
           ["Zapas W′", c.wprime_kj, ri.wprime_delta, "kJ", 0.1, 1], ["Szczyt mocy", c.pp_w, ri.pp_delta, "W", 1, 0]];
  var moved = P.filter(function (q) { return isNum(q[2]) && Math.abs(q[2]) >= q[4]; });
  var lab = !moved.length ? "bez zmian" : moved.length === 1 ? "tylko " + moved[0][0].split(" ")[0].toLowerCase() : moved.length + " z 4 zmienione";
  var up = moved.length && moved.every(function (q) { return q[2] > 0; });
  var rows = P.map(function (q) {
    var ch = isNum(q[2]) && Math.abs(q[2]) >= q[4];
    return '<div style="display:grid;grid-template-columns:8em 6em 1fr;gap:8px;padding:4px 0;border-bottom:1px solid var(--line);font-size:13.5px' + (ch ? "" : ";color:var(--ink2)") + '">' +
      '<span>' + q[0] + '</span><b style="font-size:15px' + (ch ? "" : ";font-weight:500") + '">' + n(q[1], q[5]) + ' <small>' + q[3] + '</small></b>' +
      '<span style="color:' + (ch ? (q[2] > 0 ? "#5cc08a" : "#e9b44c") : "var(--ink2)") + '">' + (ch ? sg(q[2], q[5] || (Math.abs(q[2]) < 10 ? 1 : 0)) + " " + q[3] : "bez zmian") + '</span></div>';
  }).join("");
  var head = !moved.length ? "Ta jazda <b>nie zmieniła</b> parametrów modelu." : "Zmienił się " + (moved.length === 1 ? "<b>tylko " + moved[0][0] + "</b> (" + sg(moved[0][2], 1) + " " + moved[0][3] + "); reszta bez zmian." : moved.map(function (q) { return q[0] + " " + sg(q[2], 1) + " " + q[3]; }).join(", ") + ".");
  it.innerHTML = '<div class="h"><b>Zmiana formy</b>' + rate(lab, moved.length ? (up ? "good" : "warn") : "") + '</div><p style="font-size:15px;margin:6px 0 8px">' + head + '</p>' + rows +
    '<p style="color:var(--ink2);font-size:12px;margin:6px 0 0">ModelQ: wartości po tej jeździe i zmiana wobec dnia przed (' + String(ri.prev_day || "—").split("-").reverse().slice(0, 2).join(".") + '). ' + (isNum(c.wkg) ? "W/kg " + n(c.wkg, 2) + "." : "") + '</p>';
}
/* v6 (decyzja Michała): zakres CdA w tej jeździe -- najniższy i najwyższy odcinek (2 km, >=3 okna spełniające warunki), gdzie odnotowane */
function aeroZakres(dgrid) {
  var a = dgrid.querySelector("#rower-aero"); if (!a) return;
  var sel = document.getElementById("ridesel"), rk = sel && sel.value; if (!rk) return;
  var old = dgrid.querySelector("#rower-aero-zakres"); if (old && old.dataset.rk === rk) return; if (old) old.remove();
  /* v9: Aero i Zakres oporu w jednym kaflu (decyzja Michala) */
  var wrap = a.closest("#aero-merged");
  if (!wrap) { wrap = document.createElement("div"); wrap.id = "aero-merged"; wrap.className = "it"; wrap.style.gridColumn = "1/-1"; a.parentNode.insertBefore(wrap, a); wrap.appendChild(a); }
  var box = document.createElement("div"); box.id = "rower-aero-zakres"; box.dataset.rk = rk; box.style.cssText = "margin-top:12px;padding-top:10px;border-top:1px solid var(--line)";
  box.innerHTML = '<div class="h"><b>Zakres oporu w tej jeździe</b></div><p style="color:var(--ink2)">Liczę…</p>';
  wrap.appendChild(box);
  var km = function (b) { return '<span class="kmp" data-a="' + b.km_a + '" data-b="' + b.km_b + '" style="cursor:pointer;white-space:nowrap">km ' + n(b.km_a, 0) + "–" + n(b.km_b, 0) + ' ↗</span>'; };
  var li = function (b) { return '<div style="display:grid;grid-template-columns:5.5em 7em 1fr;gap:8px;padding:3px 0;border-bottom:1px solid var(--line);font-size:13.5px"><b>' + n(b.cda, 3) + '</b>' + km(b) + '<span style="color:var(--ink2)">' + b.surface + ' · ' + b.n + ' odc.</span></div>'; };
  fetch("/api/forma/cda/ride?external_id=" + encodeURIComponent(rk), { credentials: "same-origin", cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) {
      if (box.dataset.rk !== rk) return;
      if (!j || !j.ok) { box.innerHTML = '<div class="h"><b>Zakres oporu w tej jeździe</b></div><p style="color:var(--ink2)">' + ((j && j.reason) || "brak danych") + '.</p>'; return; }
      box.innerHTML = '<div class="h"><b>Zakres oporu w tej jeździe</b><span class="rate">różnica ≈ ' + j.w30_diff + ' W przy 30 km/h</span></div>' +
        '<div class="num">' + n(j.min.cda, 3) + ' – ' + n(j.max.cda, 3) + ' <small>m² · średnio ' + n(j.cda, 3) + '</small></div>' +
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:4px 18px;margin-top:6px">' +
        '<div><div style="font-size:12px;color:var(--ink2);margin-bottom:2px">najniższy opór</div>' + j.lowest.map(li).join("") + '</div>' +
        '<div><div style="font-size:12px;color:var(--ink2);margin-bottom:2px">najwyższy opór</div>' + j.highest.map(li).join("") + '</div></div>' +
        '<p style="color:var(--ink2);font-size:12px;margin:6px 0 0">Odcinki po ' + n(j.bin_km, 0) + ' km z co najmniej ' + j.min_n + ' pomiarami spełniającymi warunki (płasko, równa moc i kadencja, prosto) — ' + j.windows + ' pomiarów w całej jeździe. Klik km → mapa.</p>';
    })
    .catch(function () { box.innerHTML = '<div class="h"><b>Zakres oporu w tej jeździe</b></div><p style="color:var(--ink2)">Nie udało się pobrać.</p>'; });
}
/* v8: Paliwo -- co zjadl na rowerze wobec planu; spalone wegle z modelu glikogenu (te same fakty co AI raportu) */
function paliwo(dgrid) {
  var sel = document.getElementById("ridesel"), rk = sel && sel.value; if (!rk) return;
  var pal = null; dgrid.querySelectorAll(".dsec[data-new] .it").forEach(function (it) { if (title(it) === "Paliwo") pal = it; });
  if (!pal) return;
  var old = dgrid.querySelector("#jedz-jazda"); if (old && old.dataset.rk === rk) return; if (old) old.remove();
  var box = document.createElement("div"); box.id = "jedz-jazda"; box.dataset.rk = rk; box.className = "it"; box.style.gridColumn = "1/-1";
  box.innerHTML = '<div class="h"><b>Jedzenie na jeździe</b></div><p style="color:var(--ink2)">Pobieram…</p>';
  var row = pal.parentNode; row.parentNode.insertBefore(box, row.nextSibling);
  fetch("/api/ride-report/energia?ride=" + encodeURIComponent(rk), { credentials: "same-origin", cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) {
      if (box.dataset.rk !== rk) return;
      var e = (j && j.energia) || {}, f = (j && j.jedzenie) || {};
      /* spalone wegle: model glikogenu zamiast starego szacunku w kaflu Paliwo */
      if (isNum(e.spalone_wegle_g)) {
        var w = document.createTreeWalker(pal, NodeFilter.SHOW_TEXT), nodes = []; while (w.nextNode()) nodes.push(w.currentNode);
        nodes.forEach(function (nd) { if (/g spalonych/.test(nd.nodeValue)) nd.nodeValue = nd.nodeValue.replace(/~?\s*[\d.,]+\s*g spalonych/, "~" + e.spalone_wegle_g + " g spalonych"); });
        var sk = dgrid.querySelector('.dsec[data-new] [data-sk="Paliwo"]');
        if (sk) sk.innerHTML = "W skrócie: " + n(e.wydatek_kcal) + " kcal wydatku, <b>~" + e.spalone_wegle_g + " g węgli spalonych</b>, zjedzone w trakcie " + n(f.w_trakcie_wegle_g) + " g" +
          (isNum(e.glikogen_meta_pct) ? "; glikogen na mecie ~" + e.glikogen_meta_pct + "%." : ".");
      }
      var gh = f.w_trakcie_wegle_g_h, plan = f.plan_wegle_g_h, poz = f.w_trakcie_pozycje || [];
      if (!isNum(f.w_trakcie_wegle_g) && !poz.length) { box.innerHTML = '<div class="h"><b>Jedzenie na jeździe</b><span class="rate">brak wpisów</span></div><p>W Dzienniku nie ma nic zjedzonego w trakcie tej jazdy. Wpis zaczynający się od „Na rowerze:” trafia tu automatycznie.</p>'; return; }
      var ratio = isNum(gh) && isNum(plan) && plan > 0 ? gh / plan : null;
      var cls = ratio == null ? "" : ratio >= 0.9 ? "good" : ratio >= 0.6 ? "warn" : "bad";
      var lab = ratio == null ? "" : ratio >= 0.9 ? "wg planu" : ratio >= 0.6 ? "trochę mało" : "za mało";
      box.innerHTML = '<div class="h"><b>Jedzenie na jeździe</b>' + (lab ? '<span class="rate ' + cls + '">' + lab + '</span>' : "") + '</div>' +
        '<div class="num">' + n(f.w_trakcie_wegle_g) + ' g <small>węgli' + (isNum(gh) ? " · " + gh + " g/h" : "") + (isNum(plan) ? " · plan " + plan + " g/h (" + n(f.plan_wegle_razem_g) + " g)" : "") + '</small></div>' +
        (poz.length ? '<table class="tb"><tr class="h"><td>co</td><td>węgle</td><td>kcal</td></tr>' + poz.map(function (p) { return "<tr><td>" + String(p.co).replace(/[<>&]/g, "") + "</td><td>" + p.wegle_g + " g</td><td>" + p.kcal + "</td></tr>"; }).join("") + "</table>" : "") +
        '<p>' + (isNum(e.spalone_wegle_g) && isNum(f.w_trakcie_wegle_g) ? "Spaliłeś ~" + e.spalone_wegle_g + " g węgli, zjadłeś w trakcie " + f.w_trakcie_wegle_g + " g (" + Math.round(f.w_trakcie_wegle_g / e.spalone_wegle_g * 100) + "%). " : "") +
        (isNum(f.zjedzone_przed_3h_wegle_g) || isNum(e.zjedzone_przed_3h_wegle_g) ? "Przed startem (3 h): " + n(isNum(f.zjedzone_przed_3h_wegle_g) ? f.zjedzone_przed_3h_wegle_g : e.zjedzone_przed_3h_wegle_g) + " g. " : "") +
        (isNum(f.w_trakcie_plyny_l) ? "Płyny wpisane: " + n(f.w_trakcie_plyny_l, 1) + " l" + (isNum(f.w_trakcie_plyny_l_h) ? " (" + n(f.w_trakcie_plyny_l_h, 1) + " l/h, plan " + n(f.plan_picie_l_h, 1) + " l/h)" : "") + " — woda z bidonu zwykle niewpisana. " : "") +
        (isNum(f.dzien_kcal) ? "Cały dzień: " + n(f.dzien_kcal) + " kcal, " + n(f.dzien_wegle_g) + " g węgli." : "") + '</p>';
    })
    .catch(function () { box.innerHTML = '<div class="h"><b>Jedzenie na jeździe</b></div><p style="color:var(--ink2)">Nie udało się pobrać.</p>'; });
}
var CACHE = {};
window.__RJtrend = function (dgrid, D) {
  if (!D) return;
  var sel = document.getElementById("ridesel"), opt = sel && sel.options[sel.selectedIndex], day = opt && opt.dataset.date;
  var tiles = {}; dgrid.querySelectorAll(".dsec[data-new] .it").forEach(function (it) { tiles[title(it)] = it; });
  if (tiles["Zmiana formy"]) zmiana(tiles["Zmiana formy"], D);
  try { aeroZakres(dgrid); } catch (e) { console.error("aero", e); }
  try { paliwo(dgrid); } catch (e) { console.error("paliwo", e); }
  if (!day || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return;
  var key = day;
  var go = function (S) {
    var r = tiles["Rano przed jazdą"] ? rano(tiles["Rano przed jazdą"], S, day, D) : null, g = tiles["Gotowość i forma"] ? gotowosc(tiles["Gotowość i forma"], S, day) : null;
    var hd = dgrid.querySelector('[data-h="Przed jazdą"] div:last-child');
    if (hd && (r || g)) hd.innerHTML = (g && isNum(g.tsb) ? "Treningowo " + (g.tsb > 5 ? "<b>wypoczęty</b>" : g.tsb > -10 ? "w normie" : "<b>zmęczony</b>") + " (świeżość " + sg(g.tsb, 0) + ")" : "") +
      (r ? (r.bad.length ? ", ale organizm " + (r.bad.length >= 2 ? "<b>niedoregenerowany</b>" : "z lekkim sygnałem") + ": " + r.bad.join(", ") + "." : ", organizm wypoczęty.") : ".");
  };
  if (CACHE[key]) { go(CACHE[key]); return; }
  fetch("/api/forma/data?start=" + addD(day, -75) + "&end=" + day, { credentials: "same-origin", cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { if (!j || !Array.isArray(j.series)) return; CACHE[key] = j.series; go(j.series); })
    .catch(function () {});
};
})();
