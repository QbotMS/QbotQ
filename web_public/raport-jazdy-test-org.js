/* raport-jazdy-test-org.js (2026-10-19, v2 po uwagach Michała): STRONA TESTOWA nowego układu raportu z jazdy.
   Nie zmienia generatora (raport-jazdy2-dane.js): po każdym renderze przenosi gotowe kafle do nowych sekcji,
   dodaje zdanie "W skrócie" i usuwa dubel "Najlepsza moc w oknach" (jest w Krzywej mocy).
   v2: "Ciało i forma" = dawne Przed jazdą + Serce w trakcie + Po jeździe; Połowy jazdy obok Równości;
   w Prędkości: wiatr i pogoda pod netto/brutto, Aero obok (węższej) tabeli prędkości; w Technice Rower obok Zmian biegów.
   Tablica w liście kafli = jeden rząd obok siebie. Kafle bez przypisania -> sekcja "Inne" (nic nie ginie). */
(function () {
"use strict";
var V = function (x) { return (x && typeof x === "object" && "value" in x) ? x.value : x; };
var isNum = function (v) { return typeof v === "number" && isFinite(v); };
var n = function (v, d) { return isNum(v) ? v.toFixed(d == null ? 0 : d).replace(".", ",") : "—"; };
var NEW = [
  { t: "Ciało i forma", tiles: [{ h: "Przed jazdą" }, ["Rano przed jazdą", "Gotowość i forma"], { h: "W trakcie" }, ["Rozjazd tętno / moc", "Moc na uderzenie serca"],
    "HRV z jazdy",   /* 21.10.2026: kafel raport-jazdy-hrv.js */
    { h: "Po jeździe" }, ["Zmiana formy", "@jutro"]] },   /* v3: podsekcje ze zdaniem na poczatku kazdej */
  { t: "Wysiłek", tiles: [["Obciążenie", "Intensywność"], ["Równość", "Połowy jazdy"], "Czas w strefach"] },
  { t: "Moc i zrywy", tiles: ["#ride-curve", ["Minimum zapasu", "Bilans zapasu"], "Przebieg zapasu", "Największe zrywy"] },
  { t: "Prędkość i teren", tiles: [["Średnia w ruchu (netto)", "Średnia całkowita (brutto)"], ["Wiatr", "Pogoda"], ["Wobec Twojej tabeli prędkości", "Prędkość wg nawierzchni"],
    "#rower-aero", "Ile kosztowała nawierzchnia", "Moc i prędkość według wiatru", "Plan vs realny"] },
  { t: "Paliwo", tiles: [["Paliwo", "#cialo-energia"], "Jedzenie*"] },
  { t: "Technika", tiles: [["Kadencja", "Bez pedałowania"], ["Zmiany biegów", "Rower"], "Biegi", "Baterie do naładowania"] }
];
var DROP = ["Najlepsza moc w oknach"];
var OLD = ["Wysiłek", "Prędkość", "Zapas na zrywy", "Ciało tego dnia", "Warunki i teren", "Rower i napęd", "Krzywa mocy", "Jedzenie"];
var ROW = "grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:inherit;align-items:start";

function title(it) { var b = it.querySelector(".h b"); if (!b) return ""; var t = ""; b.childNodes.forEach(function (c) { if (c.nodeType === 3) t += c.textContent; }); return t.trim(); }
function data() { var a = window.__RJapi; try { return a && a.data ? a.data() : null; } catch (e) { return null; } }

function skrot(k, D) {
  if (!D) return "";
  var L = D.load || {}, sp = V(D.speed) || {}, ph = D.physio || {}, wl = V(ph.wellness) || {}, mq = D.modelq || {}, cur = mq.current || {},
      wp = D.wprime || {}, en = D.energy || {}, sub = V(en.substrate) || {}, dt = D.drivetrain || {}, cbg = V(dt.cad_by_grade) || {}, wi = V(D.wind) || {},
      sf = V(D.surface) || {}, tp = sf.types_pct || {}, ri = mq.ride_impact || {};
  var xss = V(L.xss), iff = V(L.if), vi = V(L.vi);
  if (k === "Przed jazdą") {
    var rr0 = isNum(wl.rhr) && isNum(wl.rhr_base) ? wl.rhr - wl.rhr_base : null, t0 = cur.tsb, z0 = (isNum(t0) && t0 < -10) || (rr0 != null && rr0 > 4) || (isNum(wl.sleep_h) && wl.sleep_h < 6.5);
    return "Start " + (z0 ? "<b>zmęczony</b>" : "<b>wypoczęty</b>") + ":" + (isNum(wl.sleep_h) ? " sen " + n(wl.sleep_h, 1) + " h," : "") + (rr0 != null ? " tętno spoczynkowe " + (rr0 > 0 ? "+" : "") + rr0 + " wobec normy," : "") + (isNum(t0) ? " świeżość " + n(t0, 0) + "." : "");
  }
  if (k === "W trakcie") {
    var d1 = V(ph.decoupling_pct), e1 = V(L.ef), a1 = V(L.ef_anchor);
    return (isNum(d1) ? "Serce " + (Math.abs(d1) < 5 ? "<b>stabilne</b>" : "<b>dryfowało</b>") + " (rozjazd " + n(d1, 1) + "%)" : "") +
      (isNum(e1) && isNum(a1) ? (e1 < a1 * 0.97 ? ", ale pracowało <b>ciężej niż zwykle</b> przy tej mocy (" + n(e1, 2) + " wobec normy " + n(a1, 2) + ")." : e1 >= a1 * 1.02 ? ", oszczędniej niż zwykle." : ", w normie.") : ".");
  }
  if (k === "Po jeździe") {
    var f2 = ri.ftp_delta, x2 = V(L.xss), t2 = cur.tsb;
    return "Próg w modelu " + (isNum(f2) && Math.abs(f2) >= 0.5 ? "<b>" + (f2 > 0 ? "+" : "") + n(f2, 0) + " W</b>" : "bez zmian") + (isNum(cur.ftp_w) ? " (" + n(cur.ftp_w, 0) + " W)" : "") +
      (isNum(t2) ? "; świeżość po jeździe " + (t2 > 0 ? "+" : "") + n(t2, 0) : "") + ((isNum(x2) && x2 >= 120) || (isNum(t2) && t2 < -15) ? " — jutro <b>lżej</b>." : ".");
  }
  if (k === "Ciało i forma-stare") {
    var rr = isNum(wl.rhr) && isNum(wl.rhr_base) ? wl.rhr - wl.rhr_base : null, tsb = cur.tsb, tired = (isNum(tsb) && tsb < -10) || (rr != null && rr > 4) || (isNum(wl.sleep_h) && wl.sleep_h < 6.5);
    var dec = V(ph.decoupling_pct), ef = V(L.ef), efa = V(L.ef_anchor), fd = ri.ftp_delta;
    return "Start " + (tired ? "<b>zmęczony</b>" : "<b>wypoczęty</b>") + (isNum(wl.sleep_h) ? " (sen " + n(wl.sleep_h, 1) + " h" + (rr != null ? ", tętno spocz. " + (rr > 0 ? "+" : "") + rr : "") + ")" : "") +
      (isNum(dec) ? "; w trakcie serce " + (Math.abs(dec) < 5 ? "stabilne" : "dryfowało") + (isNum(ef) && isNum(efa) && ef < efa * 0.97 ? ", ale ciężej niż zwykle przy tej mocy" : "") : "") +
      "; po jeździe próg " + (isNum(fd) && Math.abs(fd) >= 0.5 ? "<b>" + (fd > 0 ? "+" : "") + n(fd, 0) + " W</b>" : "bez zmian") + (isNum(tsb) ? ", świeżość " + n(tsb, 0) : "") + ".";
  }
  if (k === "Wysiłek" && isNum(xss)) return "Wysiłek <b>" + (xss < 40 ? "mały" : xss < 90 ? "średni" : xss < 150 ? "duży" : "bardzo duży") + "</b> (XSS " + Math.round(xss) + ")" +
    (isNum(iff) ? ", intensywność " + n(iff, 2) : "") + (isNum(vi) ? ", jazda " + (vi < 1.05 ? "równa" : "szarpana") : "") + (xss >= 90 ? " — jutro lżej." : ".");
  if (k === "Moc i zrywy") { var wm = V(wp.wbal_min_pct); return isNum(wm) ? "Zapas na zrywy: minimum <b>" + Math.round(wm) + "%</b>" + (wm > 60 ? " — prawie nieruszony." : wm > 30 ? " — sięgałeś, bez wypalenia." : " — zjechałeś do dna.") + " Rekordy okresu: w Krzywej mocy." : ""; }
  if (k === "Prędkość i teren" && isNum(sp.netto_kmh)) { var vs = (sp.vs_model_pct || {}).normalny, hard = tp["twarda szybka"];
    return "Netto <b>" + n(sp.netto_kmh, 1) + " km/h</b>" + (sp.poziom ? " — " + sp.poziom.toLowerCase() : "") + (isNum(vs) ? " (" + (vs > 0 ? "+" : "") + vs + "% wobec tabeli)" : "") +
      (isNum(wi.avg_tail_ms) ? ", wiatr wzdłuż trasy " + (wi.avg_tail_ms > 0 ? "+" : "") + n(wi.avg_tail_ms, 1) + " m/s" : "") + (isNum(hard) ? ", " + Math.round(hard) + "% twardej nawierzchni." : "."); }
  if (k === "Paliwo") { var wk = V(en.work_kj); return isNum(wk) ? "<b>" + Math.round(wk) + " kJ</b> pracy" + (isNum(sub.cho_pct) ? ", " + sub.cho_pct + "% z cukrów." : ".") : ""; }   /* v8: wegle spalone uzupelnia trend.js z modelu glikogenu */
  if (k === "Technika") { var cs = V(dt.coasting_min), gr = V(dt.grind_min);
    return isNum(cbg.plasko) ? "Kadencja " + Math.round(cbg.plasko) + " na płaskim" + (isNum(cbg.podgore) ? ", pod górę " + Math.round(cbg.podgore) : "") + (isNum(cs) ? "; " + Math.round(cs) + " min bez pedałowania" : "") + (isNum(gr) && gr > 0 ? ", " + Math.round(gr) + " min mielenia." : ".") : ""; }
  return "";
}
function jutro(D) {
  if (!D) return null;
  var xss = V((D.load || {}).xss), tsb = ((D.modelq || {}).current || {}).tsb;
  if (!isNum(xss) && !isNum(tsb)) return null;
  var lekko = (isNum(xss) && xss >= 120) || (isNum(tsb) && tsb < -15), ok = (isNum(xss) && xss < 80) && (!isNum(tsb) || tsb > -10);
  var rate = lekko ? "lżej" : ok ? "normalnie" : "spokojnie", cls = lekko ? "warn" : "good";
  var txt = lekko ? "Duże obciążenie" + (isNum(tsb) && tsb < -10 ? " przy ujemnej świeżości" : "") + " — jutro spokojnie albo wolne." :
    ok ? "Lekki dzień — jutro możesz jechać według planu." : "Umiarkowanie — jutro raczej spokojna jazda.";
  var d = document.createElement("div");
  d.innerHTML = '<div class="it"><div class="h"><b>Co to znaczy na jutro</b><span class="rate ' + cls + '">' + rate + '</span></div><p>' + txt +
    ' <span style="color:var(--ink2);font-size:12px">(szkic reguły: XSS ' + (isNum(xss) ? Math.round(xss) : "—") + ', świeżość ' + (isNum(tsb) ? n(tsb, 0) : "—") + ')</span></p></div>';
  return d.firstChild;
}

function reorg(dgrid) {
  var secs = [].slice.call(dgrid.querySelectorAll(":scope > .dsec"));
  var old = secs.filter(function (s) { var b = s.querySelector(".dh b"); return !s.dataset.new && b && OLD.indexOf(b.textContent.trim()) >= 0; });
  if (!old.length) return false;
  var pool = [], used = [];
  old.forEach(function (s) { s.querySelectorAll(".it").forEach(function (it) { if (!it.parentElement.closest(".it") && !it.closest("#ride-curve,#cialo-energia,#rower-aero")) pool.push(it); }); });
  ["#ride-curve", "#cialo-energia", "#rower-aero"].forEach(function (id) { var e = dgrid.querySelector(id); if (e) pool.push(e); });
  var D = data();
  function take(key) {
    if (key === "@jutro") { var j = jutro(D); return j ? [j] : []; }
    var got = [];
    pool.forEach(function (el) {
      if (used.indexOf(el) >= 0) return;
      var hit = key[0] === "#" ? ("#" + el.id === key) : (key.slice(-1) === "*" ? title(el).indexOf(key.slice(0, -1)) === 0 : title(el) === key);
      if (hit) { used.push(el); el.classList.remove("wt"); el.style.gridColumn = ""; got.push(el); }
    });
    return got;
  }
  var frag = document.createDocumentFragment();
  NEW.forEach(function (ns) {
    var box = document.createElement("div"); box.className = "nar";
    ns.tiles.forEach(function (key) {
      if (key && key.h) {   /* v3: naglowek podsekcji ze zdaniem */
        var hs = skrot(key.h, D), hd = document.createElement("div");
        hd.dataset.h = key.h; hd.style.cssText = "grid-column:1/-1;margin:6px 0 -2px;padding:7px 11px;border-left:3px solid #f08ac0;background:rgba(127,127,127,.07);border-radius:7px";
        hd.innerHTML = '<div style="font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink2);margin-bottom:2px">' + key.h + '</div><div style="font-size:14.5px">' + (hs || "") + '</div>';
        box.appendChild(hd); return;
      }
      if (Array.isArray(key)) {
        var els = []; key.forEach(function (k) { els = els.concat(take(k)); });
        if (!els.length) return;
        var row = document.createElement("div"); row.style.cssText = ROW; els.forEach(function (e) { row.appendChild(e); }); box.appendChild(row);
      } else {
        take(key).forEach(function (e) { if (key === "#ride-curve" || key === "#rower-aero" || key === "Biegi" || key === "Czas w strefach" || key.indexOf("Ile kosztowała") === 0 || key.indexOf("Prędkość wg") === 0) e.style.gridColumn = "1/-1"; box.appendChild(e); });
      }
    });
    if (!box.children.length) return;
    var sk = skrot(ns.t, D), sec = document.createElement("div");
    sec.className = "dsec"; sec.dataset.new = "1";
    sec.innerHTML = '<div class="dh"><b>' + ns.t + '</b><span class="chev">›</span></div><div class="db">' +
      (sk ? '<p data-sk="' + ns.t + '" style="margin:0 0 10px;padding:8px 11px;border-left:3px solid #f4a261;background:rgba(127,127,127,.08);border-radius:7px;font-size:14.5px">W skrócie: ' + sk + '</p>' : "") + '</div>';
    sec.querySelector(".db").appendChild(box);
    frag.appendChild(sec);
  });
  var rest = pool.filter(function (el) { return used.indexOf(el) < 0 && DROP.indexOf(title(el)) < 0; });
  if (rest.length) {
    var ib = document.createElement("div"); ib.className = "nar"; rest.forEach(function (e) { ib.appendChild(e); });
    var s2 = document.createElement("div"); s2.className = "dsec"; s2.dataset.new = "1";
    s2.innerHTML = '<div class="dh"><b>Inne</b><span class="chev">›</span></div><div class="db"></div>';
    s2.querySelector(".db").appendChild(ib); frag.appendChild(s2);
  }
  zonesFix(frag, D);
  dgrid.insertBefore(frag, old[0]);
  old.forEach(function (s) { s.remove(); });
  try { polish(dgrid); } catch (e) { console.error("polish", e); }
  try { if (window.__RJtrend) window.__RJtrend(dgrid, D); } catch (e) { console.error("trend", e); }   /* v4: kafle z trendem */
  return true;
}
/* v3: "Czas w strefach" -- wyzsze paski i czas (min / h:mm) na kazdym odcinku paska; wąskie odcinki: czas w dymku */
function zonesFix(root, D) {
  var mv = V(((D || {}).load || {}).dur_moving_s);
  root.querySelectorAll(".it").forEach(function (it) {
    if (title(it) !== "Czas w strefach") return;
    it.querySelectorAll(".zone").forEach(function (z) {
      z.style.height = "26px"; z.style.borderRadius = "7px"; z.style.overflow = "hidden"; z.style.display = "flex";
      [].forEach.call(z.children, function (seg) {
        var p = parseFloat(seg.style.width) || 0; if (!p) return;
        var m = isNum(mv) ? Math.round(p / 100 * mv / 60) : null;
        var lab = m == null ? Math.round(p) + "%" : (m >= 60 ? Math.floor(m / 60) + ":" + ("0" + (m % 60)).slice(-2) + " h" : m + " min");
        seg.title = lab + " (" + Math.round(p) + "%)";
        seg.style.cssText += ";display:flex;align-items:center;justify-content:center;font-size:11.5px;font-weight:600;color:#111;white-space:nowrap;overflow:hidden";
        seg.textContent = p >= 7 ? lab : "";
      });
    });
  });
}
/* wezsza tabela "Wobec Twojej tabeli predkosci" (byla rozciagnieta na cala szerokosc) */
/* v7: porzadki w kaflach (uwagi Michala 19.10) */
function polish(root) {
  root.querySelectorAll(".it").forEach(function (it) {
    var t = title(it), b = it.querySelector(".h b");
    if (t === "Minimum zapasu") { var sm = it.querySelector(".num small"); if (sm) sm.remove(); }
    if (t === "Bilans zapasu" && b) { b.childNodes.forEach(function (c) { if (c.nodeType === 3 && c.textContent.trim() === "Bilans zapasu") c.textContent = "Pojemność zapasu"; }); }
    if (t === "Rower") {
      var tb = it.querySelector("table.tb");
      if (tb && !tb.closest("details")) { var d = document.createElement("details"); d.innerHTML = "<summary>czujniki i baterie</summary>"; tb.parentNode.insertBefore(d, tb); d.appendChild(tb); }
    }
  });
  /* przecinek dziesietny w liczbach (tekst kafli; bez wykresow i skryptow) */
  var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: function (n) {
    var p = n.parentNode; if (!p || p.closest("svg,script,style,select,option")) return NodeFilter.FILTER_REJECT;
    return /\d\.\d/.test(n.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT; } });
  var nodes = []; while (w.nextNode()) nodes.push(w.currentNode);
  nodes.forEach(function (n) { n.nodeValue = n.nodeValue.replace(/(\d)\.(\d)/g, "$1,$2"); });
}
var st = document.createElement("style");
st.textContent = "#dgrid .dsec[data-new] .it table.tb{width:auto;min-width:60%}#aero-merged #rower-aero .it{background:none;border:0;padding:0;margin:0;box-shadow:none}";
document.head.appendChild(st);
var busy = false;
function run() {
  var dg = document.getElementById("dgrid"); if (!dg || busy) return;
  busy = true;
  try { if (reorg(dg) && window.__RJ3 && typeof window.__RJ3.after === "function") window.__RJ3.after(); } catch (e) { console.error("reorg", e); }
  busy = false;
}
new MutationObserver(function () { run(); }).observe(document.body, { childList: true, subtree: true });
})();
