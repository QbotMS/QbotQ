/* QBot wspolny sidebar -- wstrzykiwany na kazdej stronie.
   2026-10-08: ikony dwutonowe (kontur + wypelnienie .qi-f/.qi-fo + pomaranczowy akcent .qi-a/.qi-as, style w nav.css).
   Domyslnie waski rail (ikony). Rozsuniecie NACHODZI na tresc (nie przesuwa jej), stan nietrwaly.
   Menu podzielone: PRODUKCYJNE (gora) + TESTOWE (na dole, nad przelacznikiem motywu).
   Stopka: przelacznik motywu dzien/noc (klasa html.theme-dark, klucz qtheme). */
(function () {
  var PROD = [
    { href: "/index.html", label: "Start", alt: ["/"],
      icon: '<path class="qi-fo" d="M5.5 10.2 12 4.7l6.5 5.5V20h-13z"/><path d="M3 11.4 12 3.8l9 7.6"/><path d="M5.5 10v10h13V10"/><path d="M10 20v-4.6c0-.5.4-.9.9-.9h2.2c.5 0 .9.4.9.9V20"/><path d="M16.2 6.6V4.4h1.9v3.8"/><circle class="qi-a" cx="12" cy="10.6" r="1.3"/>' },
    { href: "/forma.html", label: "Forma",
      icon: '<path d="M3.5 3.5v17h17"/><path class="qi-fo" d="M6.5 17.5 10 12.5l3.2 2.4L19 8v10.5H6.5z"/><path d="M6.5 17.5 10 12.5l3.2 2.4L19 8"/><circle cx="10" cy="12.5" r=".9"/><circle cx="13.2" cy="14.9" r=".9"/><circle class="qi-a" cx="19" cy="8" r="2"/>' },
    { href: "/trening.html", label: "Trening", alt: ["/trener.html", "/kalendarz.html"],
      icon: '<path d="M8.7 12h6.6"/><rect class="qi-f" x="5.2" y="6.5" width="3.5" height="11" rx="1.2"/><rect class="qi-f" x="15.3" y="6.5" width="3.5" height="11" rx="1.2"/><path d="M3 9.2v5.6M21 9.2v5.6"/><rect class="qi-a" x="10.8" y="11" width="2.4" height="2" rx=".5"/>' },
    { href: "/raport-jazdy.html", label: "Raport jazdy",
      icon: '<circle class="qi-f" cx="5.6" cy="16.4" r="3.9"/><circle class="qi-f" cx="18.4" cy="16.4" r="3.9"/><path d="M5.6 16.4 9 8.8l2.6 7.6H5.6"/><path d="M9 8.8h6.3M15.3 8.8l-3.7 7.6M15.3 8.8l3.1 7.6"/><path d="M7.4 7.3h3.2M14.4 6.3h2.2l-.9 2.5"/><circle class="qi-a" cx="11.6" cy="16.4" r="1.4"/>' },
    { href: "/raport-trasy.html", label: "Analiza trasy",
      icon: '<path class="qi-f" d="M3 6.2 8.6 4l6.8 2.2L21 4v13.8L15.4 20l-6.8-2.2L3 20z"/><path d="M8.6 4v13.8M15.4 6.2V20" stroke-opacity=".55"/><path d="M5.3 16.2c1.6-.4 2.3-2.6 4.3-3.1s2.8 1 4.6.2" stroke-dasharray="1.4 1.7"/><path class="qi-a" d="M17.6 6.6a2.3 2.3 0 0 1 2.3 2.3c0 1.7-2.3 4-2.3 4s-2.3-2.3-2.3-4a2.3 2.3 0 0 1 2.3-2.3z"/>' },
    { href: "/planer-wyprawy.html", label: "Planer wyprawy",
      icon: '<circle class="qi-f" cx="12" cy="12" r="9"/><path d="M12 3.6v1.7M12 18.7v1.7M3.6 12h1.7M18.7 12h1.7" stroke-opacity=".6"/><path class="qi-a" d="M16 8 13.3 13.3 10.7 10.7z"/><path d="M8 16 10.7 10.7 13.3 13.3z"/><circle cx="12" cy="12" r=".8"/>' },
    { href: "/garaz.html", label: "Garaż",
      icon: '<path class="qi-f" d="M3.5 9.6 12 4l8.5 5.6V20.5h-17z"/><path d="M7 20.5v-8h10v8"/><path d="M7 14.8h10M7 17.6h10" stroke-opacity=".6"/><circle class="qi-a" cx="12" cy="9" r="1.2"/>' }
  ];
  var TEST = [
    { href: "/mq2.html", label: "MQ2",
      icon: '<circle class="qi-fo" cx="12" cy="12" r="9.5"/><path class="qi-a" d="M13.2 4.5 7 13.1h4.6l-.8 6.4 6.2-8.6h-4.6z"/><path d="M13.2 4.5 7 13.1h4.6l-.8 6.4 6.2-8.6h-4.6z"/>' },
    { href: "/naprawa-trasy.html", label: "Naprawa trasy",
      icon: '<path class="qi-f" d="M14.8 6.2a4.1 4.1 0 0 0-5.5 5.2l-5.6 5.6a1.6 1.6 0 1 0 2.3 2.3l5.6-5.6a4.1 4.1 0 0 0 5.2-5.5l-2.4 2.4-2.3-.6-.6-2.3z"/><circle class="qi-a" cx="5.4" cy="5.4" r="1.4"/><path d="M8 5.4h2.2" stroke-dasharray="1 1.5"/><circle cx="18.6" cy="18.6" r="1.2"/>' }
  ];

  var BURGER = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg>';
  var MOON = '<path class="qi-f" d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/><circle class="qi-a" cx="17.5" cy="5" r="1"/><circle class="qi-a" cx="20.3" cy="8.4" r=".7"/>';
  var SUN = '<circle class="qi-f" cx="12" cy="12" r="4.2"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/><circle class="qi-a" cx="12" cy="12" r="1.4"/>';

  function norm(p) { p = (p || "").replace(/\/+$/, ""); return p === "" ? "/" : p; }
  var path = norm(location.pathname);

  function isActive(it) {
    var hrefs = [it.href].concat(it.alt || []);
    for (var i = 0; i < hrefs.length; i++) {
      var h = norm(hrefs[i].replace(/\?.*$/, ""));
      if (h === path) return true;
      if (h === "/index.html" && path === "/") return true;
    }
    return false;
  }

  function isDark() { return document.documentElement.classList.contains("theme-dark"); }

  function makeLink(it, onNavigate) {
    var li = document.createElement("li");
    var a = document.createElement("a");
    a.className = "qnav-link" + (isActive(it) ? " active" : "");
    a.href = it.href;
    a.setAttribute("data-label", it.label);
    a.innerHTML = '<svg viewBox="0 0 24 24">' + it.icon + '</svg><span class="qnav-label">' + it.label + '</span>';
    if (onNavigate) a.addEventListener("click", onNavigate);
    li.appendChild(a);
    return li;
  }

  // [QR-DEMO] 2026-10-07: plakietka trybu demo + wylogowanie; wlasciciel: link "Dostepy tymczasowe"
  function qAuthBadge() {
    if (!window.fetch) return;
    fetch("/auth/demo/whoami", { credentials: "same-origin" }).then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (j) {
      if (!j) return;
      if (j.kind === "demo") {
        var bar = document.createElement("div");
        bar.className = "qdemo-bar";
        bar.style.cssText = "position:fixed;top:0;left:50%;transform:translateX(-50%);z-index:9999;background:#f59e0b;color:#1a1200;font:600 13px system-ui,sans-serif;padding:6px 12px;border-radius:0 0 10px 10px;box-shadow:0 2px 10px rgba(0,0,0,.3);display:flex;gap:10px;align-items:center";
        var txt = document.createElement("span");
        var out = document.createElement("button");
        out.type = "button";
        out.textContent = "Wyloguj";
        out.style.cssText = "border:0;border-radius:6px;padding:3px 10px;background:#1a1200;color:#fff;cursor:pointer;font:600 12px system-ui,sans-serif";
        var end = Date.now() + j.expires_in * 1000;
        function tick() {
          var s = Math.max(0, Math.round((end - Date.now()) / 1000));
          if (s <= 0) { location.href = "/login"; return; }
          txt.textContent = "Tryb demo \u2014 tylko podgl\u0105d \u00b7 zosta\u0142o " + Math.ceil(s / 60) + " min";
        }
        tick();
        setInterval(tick, 30000);
        out.addEventListener("click", function () {
          var back = function () { location.href = "/login"; };
          fetch("/auth/demo/logout", { method: "POST", credentials: "same-origin" }).then(back, back);
        });
        bar.appendChild(txt);
        bar.appendChild(out);
        document.body.appendChild(bar);
      } else if (j.kind === "owner") {
        // 2026-10-08: Dostepy tymczasowe przeniesione do SETUP > Dostepy (bez klodki w menu). Link z Telegrama ?klodka=1 -> tam.
        if (/[?&]klodka=1\b/.test(location.search) && norm(location.pathname) !== "/setup.html") { location.replace("/setup.html#dostepy"); return; }
        qLogoutBtn();
      }
    }).catch(function () {});
  }

  /* 2026-10-07: KLODKA = okno nakladane na dowolnym ekranie (bez ramki/iframe):
     1) PROSBY O DOSTEP (zdalne logowanie gosci): /api/auth/requests - lista BEZ kodu; zatwierdzenie wymaga wpisania kodu,
        ktory podaje gosc (POST /api/auth/requests/decide, serwer porownuje; 3 bledy = odrzucenie). Odswiezanie co 3 s, gdy okno otwarte.
     2) AKTYWNE DOSTEPY: /api/auth/sessions + konczenie (POST /api/auth/sessions/revoke, id albo "all").
     3) WYLOGUJ: POST /auth/logout -> /login.
     Link z Telegrama .../?klodka=1 otwiera okno od razu. Zamykanie: x, klik w tlo, Esc. Styl: nav.css sekcja OKNO KLODKI. */
  var QL = { ov: null, csrfS: "", csrfR: "", timer: null, note: {} };
  function qlEsc(t) { return String(t == null ? "" : t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function qlHM(iso) { try { var d = new Date(iso); return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2); } catch (e) { return ""; } }
  function qlJSON(url, body) {
    return fetch(url, body ? { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : { credentials: "same-origin", cache: "no-store" }).then(function (r) { return r.json(); });
  }
  function qlLoadReq() {
    var box = QL.ov.querySelector(".qlock-req");
    qlJSON("/api/auth/requests").then(function (j) {
      QL.csrfR = j.csrf || ""; var R = j.requests || [];
      if (!R.length) { box.innerHTML = ""; box.hidden = true; return; }
      box.hidden = false;
      var keep = {}; [].forEach.call(box.querySelectorAll("input[data-id]"), function (i) { keep[i.getAttribute("data-id")] = i.value; });
      var focus = document.activeElement && document.activeElement.getAttribute && document.activeElement.getAttribute("data-id");
      box.innerHTML = '<div class="qlock-sec">Prośby o dostęp</div>' + R.map(function (x) {
        var id = qlEsc(x.id), n = QL.note[x.id] || "";
        return '<div class="qlock-rq"><div class="qlock-rq-h"><b>' + qlEsc(x.device) + '</b><span>od ' + qlEsc(qlHM(x.created_at)) + ' · zostało ' + Math.max(0, x.left_s) + ' s</span></div>'
          + '<div class="qlock-rq-a"><input data-id="' + id + '" maxlength="9" autocomplete="off" spellcheck="false" placeholder="kod od gościa, np. ABC-123">'
          + '<button type="button" class="qlock-ok" data-id="' + id + '">Zatwierdź</button><button type="button" class="qlock-no" data-id="' + id + '">Odrzuć</button></div>'
          + (n ? '<div class="qlock-note">' + qlEsc(n) + '</div>' : '') + '</div>';
      }).join("");
      [].forEach.call(box.querySelectorAll("input[data-id]"), function (i) { var k = i.getAttribute("data-id"); if (keep[k]) i.value = keep[k]; if (k === focus) i.focus(); });
    }).catch(function () {});
  }
  function qlDecide(id, decision) {
    var inp = QL.ov.querySelector('.qlock-req input[data-id="' + id + '"]');
    var code = inp ? inp.value : "";
    if (decision === "approve" && code.replace(/[^A-Za-z0-9]/g, "").length < 6) { QL.note[id] = "Wpisz 6-znakowy kod, który widzi gość na swoim ekranie."; qlLoadReq(); return; }
    qlJSON("/api/auth/requests/decide", { id: id, decision: decision, code: code, csrf: QL.csrfR }).then(function (j) {
      var st = j.status;
      QL.note[id] = st === "bad_code" ? "Kod się nie zgadza (zostało prób: " + j.tries_left + ")." :
        st === "denied_bad_code" ? "3 błędne kody — prośba odrzucona." : st === "gone" ? "Prośba wygasła albo już obsłużona." : "";
      if (st === "APPROVED" || st === "DENIED") delete QL.note[id];
      qlLoadReq(); qlLoadSes();
    }).catch(function () { QL.note[id] = "Błąd połączenia."; qlLoadReq(); });
  }
  function qlLoadSes() {
    var L = QL.ov.querySelector(".qlock-list"), all = QL.ov.querySelector(".qlock-all");
    qlJSON("/api/auth/sessions").then(function (j) {
      QL.csrfS = j.csrf || ""; var S = j.sessions || [];
      all.hidden = S.length < 2;
      if (!S.length) { L.innerHTML = '<div class="qlock-muted">Brak aktywnych dostępów.</div>'; return; }
      L.innerHTML = S.map(function (x) {
        return '<div class="qlock-row"><div><b>do ' + qlEsc(qlHM(x.expires_at)) + '</b><span>' + qlEsc(x.device || "nieznane urządzenie") + '</span></div>'
          + '<button type="button" class="qlock-end" data-id="' + qlEsc(x.id) + '">Zakończ</button></div>';
      }).join("");
    }).catch(function () { L.innerHTML = '<div class="qlock-muted">Nie udało się pobrać listy.</div>'; });
  }
  function qlRevoke(id) { qlJSON("/api/auth/sessions/revoke", { id: id, csrf: QL.csrfS }).then(qlLoadSes, qlLoadSes); }
  function qlClose() { if (QL.ov) QL.ov.classList.remove("on"); if (QL.timer) { clearInterval(QL.timer); QL.timer = null; } }
  /* 2026-10-08: WYLOGUJ w prawym gornym rogu (wlasciciel): obok przycisku dzien/noc (#themebtn) w naglowku strony,
     a gdy strona go nie ma - plywajacy w rogu ekranu. POST /auth/logout -> /login. */
  var LOGOUT = '<svg viewBox="0 0 24 24"><path class="qi-fo" d="M5 3h4v18H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/><circle class="qi-a" cx="6.5" cy="12" r="1"/></svg>';
  function qLogout(b) {
    if (b) { b.disabled = true; }
    var go = function () { location.href = "/login"; };
    fetch("/auth/logout", { method: "POST", credentials: "same-origin" }).then(go, go);
  }
  function qLogoutBtn() {
    if (document.getElementById("qlogout")) return;
    var b = document.createElement("button");
    b.type = "button"; b.id = "qlogout"; b.title = "Wyloguj"; b.setAttribute("aria-label", "Wyloguj"); b.innerHTML = LOGOUT;
    b.addEventListener("click", function () { if (confirm("Wylogować z QBota w tej przeglądarce?")) qLogout(b); });
    // gdzie: (1) obok #themebtn, jesli ten stoi w prawym gornym rogu ekranu; (2) telefon - w gornym pasku
    // wysunietego menu (na stronach z mapa gorny pasek ekranu jest zajety: wybor trasy/jazdy, styl mapy);
    // (3) komputer - plywajacy w prawym gornym rogu.
    var tb = document.getElementById("themebtn"), r = tb ? tb.getBoundingClientRect() : null;
    var mob = window.matchMedia("(max-width:820px),(pointer:coarse) and (max-height:500px)").matches;
    var top = document.querySelector(".qnav-top");
    if (tb && tb.parentNode && r.width > 0 && r.right > window.innerWidth - 220 && r.top < 140) { b.className = "themebtn qlogout-head"; tb.parentNode.insertBefore(b, tb.nextSibling); }
    else if (mob && top) { b.className = "qnav-logout"; top.appendChild(b); }
    else { b.className = "qlogout-fix"; document.body.appendChild(b); }
  }

  function qlHTML(modal) {
    return '<div class="qlock-box"' + (modal ? ' role="dialog" aria-modal="true" aria-label="Dostępy i konto"' : '') + '>'
      + (modal ? '<div class="qlock-h"><b>Dostępy tymczasowe</b><button type="button" class="qlock-x" aria-label="Zamknij">\u00d7</button></div>' : '')
      + '<div class="qlock-body"><div class="qlock-req" hidden></div>'
      + '<div class="qlock-sec">Aktywne dostępy</div><p class="qlock-muted">Goście mają tylko podgląd przez 1 h. Zakończenie działa od razu.</p>'
      + '<div class="qlock-list"></div><button type="button" class="qlock-all" hidden>Zakończ wszystkie</button></div>'
      + '<div class="qlock-foot"><span>Wylogowanie dotyczy tej przeglądarki.</span><button type="button" class="qlock-out">Wyloguj</button></div></div>';
  }
  function qlWire(ov, modal) {
    ov.addEventListener("click", function (e) {
      if (modal && e.target === ov) return qlClose();
      var t = e.target.closest ? e.target : null; if (!t) return;
      var b;
      if ((b = t.closest(".qlock-end"))) qlRevoke(b.getAttribute("data-id"));
      else if ((b = t.closest(".qlock-ok"))) qlDecide(b.getAttribute("data-id"), "approve");
      else if ((b = t.closest(".qlock-no"))) qlDecide(b.getAttribute("data-id"), "deny");
    });
    ov.addEventListener("keydown", function (e) {
      var i = e.target; if (e.key === "Enter" && i && i.matches && i.matches(".qlock-req input[data-id]")) qlDecide(i.getAttribute("data-id"), "approve");
    });
    var x = ov.querySelector(".qlock-x"); if (x) x.addEventListener("click", qlClose);
    ov.querySelector(".qlock-all").addEventListener("click", function () { qlRevoke("all"); });
    if (modal) document.addEventListener("keydown", function (e) { if (e.key === "Escape" && ov.classList.contains("on")) qlClose(); });
    ov.querySelector(".qlock-out").addEventListener("click", function () { this.textContent = "Wylogowuję…"; qLogout(this); });
  }
  function qLockOpen() {
    var ov = QL.ov;
    if (!ov || ov.classList.contains("qlock-inline")) {
      ov = QL.ov = document.createElement("div"); ov.id = "qlock"; ov.className = "qmod";
      ov.innerHTML = qlHTML(true); document.body.appendChild(ov); qlWire(ov, true);
    }
    ov.classList.add("on"); qlLoadReq(); qlLoadSes();
    if (!QL.timer) QL.timer = setInterval(function () { if (ov.classList.contains("on")) qlLoadReq(); }, 3000);
  }
  /* SETUP > Dostepy: ta sama tresc osadzona w stronie (bez okna). Prosby o dostep odswiezane co 3 s, gdy karta widoczna. */
  window.qLockMount = function (el) {
    if (QL.ov && QL.ov.classList.contains("qlock-inline") && el.contains(QL.ov)) { qlLoadReq(); qlLoadSes(); return; }
    var ov = document.createElement("div"); ov.className = "qmod qlock-inline"; ov.innerHTML = qlHTML(false);
    el.appendChild(ov); QL.ov = ov; qlWire(ov, false); qlLoadReq(); qlLoadSes();
    if (QL.timer) clearInterval(QL.timer);
    QL.timer = setInterval(function () { if (QL.ov === ov && ov.offsetParent && !document.hidden) qlLoadReq(); }, 3000);
  };

  /* 2026-10-08: qModal(tytul, element[, przyZamknieciu]) - wspolne okno nakladane w stylu okna klodki (nav.css .qmod).
     Element jest wkladany do tresci okna; po zamknieciu (x, klik w tlo, Esc) wywolywane przyZamknieciu(element) - np. odlozenie go na miejsce. */
  window.qModal = function (title, el, onClose) {
    var ov = document.createElement("div"); ov.className = "qmod on";
    ov.innerHTML = '<div class="qlock-box" role="dialog" aria-modal="true"><div class="qlock-h"><b></b>'
      + '<button type="button" class="qlock-x" aria-label="Zamknij">\u00d7</button></div><div class="qlock-body"></div></div>';
    ov.querySelector(".qlock-h b").textContent = title;
    ov.setAttribute("aria-label", title);
    ov.querySelector(".qlock-body").appendChild(el);
    document.body.appendChild(ov);
    var done = false;
    function key(e) { if (e.key === "Escape") { e.stopPropagation(); close(); } }
    function close() { if (done) return; done = true; document.removeEventListener("keydown", key, true); try { if (onClose) onClose(el); } catch (e) {} ov.remove(); }
    ov.addEventListener("click", function (e) { if (e.target === ov) close(); });
    ov.querySelector(".qlock-x").addEventListener("click", close);
    document.addEventListener("keydown", key, true);
    return { close: close, el: ov };
  };


  /* 2026-10-08: CENTRUM POWIADOMIEN - dzwonek pod przyciskiem menu (na telefonie kropka tez na przycisku menu).
     Dane: /api/notif (qbot_notif.py: zadania przy rowerze, trasy do potwierdzenia, brak swiezych danych,
     wiadomosci Trenera). Pomaranczowa kropka z liczba = nieprzeczytane; otwarcie okna oznacza je jako przeczytane. */
  var BELL = '<svg viewBox="0 0 24 24"><path class="qi-f" d="M6 8.5a6 6 0 0 1 12 0c0 6.5 2.8 8.5 2.8 8.5H3.2S6 15 6 8.5"/><path d="M10.3 20.5a1.94 1.94 0 0 0 3.4 0"/><path d="M12 2.5v.8"/><path class="qi-as" d="M8.6 8.3a3.4 3.4 0 0 1 2.2-2.9"/></svg>';
  function qEsc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function qBell(top, fab, closeExpanded) {
    var b = document.createElement("button");
    b.type = "button"; b.className = "qnav-link qnav-bell"; b.setAttribute("data-label", "Powiadomienia");
    b.setAttribute("aria-label", "Powiadomienia");
    b.innerHTML = '<span class="qnav-bico">' + BELL + '<span class="qnav-badge" hidden></span></span><span class="qnav-label">Powiadomienia</span>';
    top.parentNode.insertBefore(b, top.nextSibling);
    var dot = document.createElement("span"); dot.className = "qnav-fabdot"; dot.hidden = true; fab.appendChild(dot);
    var badge = b.querySelector(".qnav-badge"), DATA = null, md = null;
    function paint(n) {
      var t = n > 99 ? "99+" : String(n);
      badge.hidden = !n; badge.textContent = t; dot.hidden = !n; dot.textContent = t;
      b.setAttribute("aria-label", n ? "Powiadomienia: " + n + " nowych" : "Powiadomienia");
    }
    function load() {
      return fetch("/api/notif", { credentials: "same-origin", cache: "no-store" })
        .then(function (r) { if (!r.ok) throw r.status; return r.json(); })
        .then(function (j) { DATA = j; paint(j.unread || 0); if (md) render(); return j; })
        .catch(function (e) { if (e === 401 || e === 403) b.style.display = "none"; });
    }
    function post(url, body) {
      return fetch(url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
        .then(function (r) { if (!r.ok) throw r.status; return r.json(); });
    }
    var box = document.createElement("div"); box.className = "qnc";
    var HIST = null;
    function renderHist() {
      if (!HIST) { box.innerHTML = '<div class="qnc-empty">wczytuję historię\u2026</div>'; return; }
      var it = HIST.items || [];
      box.innerHTML = '<div class="qnc-hh">Wszystkie powiadomienia z ' + HIST.days + ' dni, także usunięte</div>' + (it.length ? it.map(function (x) {
        return '<div class="qnc-it qnc-hi"><div class="qnc-ic">' + qEsc(x.icon) + '</div><div class="qnc-tx"><b>' + qEsc(x.title) + '</b>'
          + (x.body ? '<div class="qnc-b">' + qEsc(x.body).replace(/\n/g, "<br>") + '</div>' : "")
          + '<div class="qnc-f"><span>' + qEsc(x.when) + '</span><span class="qnc-st">' + qEsc(x.status) + '</span>'
          + (x.url ? '<a href="' + qEsc(x.url) + '">przejdź</a>' : "") + '</div></div></div>';
      }).join("") : '<div class="qnc-empty">Historia jest pusta.</div>');
    }
    function render() {
      if (HIST !== null) { renderHist(); return; }
      var it = (DATA && DATA.items) || [];
      if (!it.length) { box.innerHTML = '<div class="qnc-empty">Brak powiadomień — wszystko w porządku.</div>'; return; }
      box.innerHTML = it.map(function (x, i) {
        return '<div class="qnc-it' + (x.unread ? " u" : "") + '"><button type="button" class="qnc-del" data-d="' + x.id + '" title="Usuń z listy (zostaje w historii)" aria-label="Usuń">\u00d7</button><div class="qnc-ic">' + qEsc(x.icon) + '</div><div class="qnc-tx">'
          + '<b>' + qEsc(x.title) + '</b>' + (x.body ? '<div class="qnc-b">' + qEsc(x.body).replace(/\n/g, "<br>") + '</div>' : "")
          + '<div class="qnc-f"><span>' + qEsc(x.when) + '</span>'
          + (x.url ? '<a href="' + qEsc(x.url) + '">przejdź</a>' : "")
          + (x.action ? '<button type="button" data-a="' + i + '">' + qEsc(x.action.label) + '</button>' : "")
          + '</div></div></div>';
      }).join("");
      box.querySelectorAll("button[data-a]").forEach(function (bt) {
        bt.onclick = function () { var a = it[+bt.dataset.a].action; bt.disabled = true;
          post(a.post, a.body).then(load).catch(function () { bt.disabled = false; bt.textContent = "nie udało się"; }); };
      });
      box.querySelectorAll("button[data-d]").forEach(function (bt) {
        bt.onclick = function () { bt.disabled = true; var row = bt.closest(".qnc-it"); if (row) row.style.opacity = ".35";
          post("/api/notif/dismiss", { id: +bt.dataset.d }).then(load).catch(function () { bt.disabled = false; if (row) row.style.opacity = ""; }); };
      });
    }
    /* 2026-10-08: wysuwany panel obok dzwonka (zamiast okna na srodku). Telefon: panel na cala szerokosc z lewej. */
    var pan = document.createElement("div"); pan.className = "qnc-pan"; pan.setAttribute("role", "dialog"); pan.setAttribute("aria-label", "Powiadomienia");
    pan.innerHTML = '<div class="qnc-h"><b>Powiadomienia</b><span class="qnc-hb"><button type="button" class="qnc-histbtn">Historia</button>'
      + '<button type="button" class="qnc-close" aria-label="Zamknij">\u00d7</button></span></div>';
    pan.appendChild(box); document.body.appendChild(pan);
    function mob() { return window.matchMedia("(max-width:820px),(pointer:coarse) and (max-height:500px)").matches; }
    function place() {
      if (mob()) { pan.style.left = ""; pan.style.top = ""; return; }
      var nv = b.closest(".qnav"), nr = nv ? nv.getBoundingClientRect() : { right: 56 }, br = b.getBoundingClientRect();
      pan.style.left = Math.round(nr.right + 8) + "px"; pan.style.top = Math.max(8, Math.round(br.top - 4)) + "px";
    }
    function shut() { if (!md) return; md = null; pan.classList.remove("on"); b.classList.remove("active");
      document.removeEventListener("mousedown", outside, true); document.removeEventListener("keydown", esc, true); }
    function outside(e) { if (!pan.contains(e.target) && !b.contains(e.target)) shut(); }
    function esc(e) { if (e.key === "Escape") { e.stopPropagation(); shut(); } }
    pan.querySelector(".qnc-close").addEventListener("click", shut);
    var hb = pan.querySelector(".qnc-histbtn"), ht = pan.querySelector(".qnc-h b");
    hb.addEventListener("click", function () {
      if (HIST !== null) { HIST = null; hb.textContent = "Historia"; ht.textContent = "Powiadomienia"; render(); return; }
      HIST = false; hb.textContent = "\u2190 Bieżące"; ht.textContent = "Historia"; render();
      fetch("/api/notif/history", { credentials: "same-origin", cache: "no-store" }).then(function (r) { return r.json(); })
        .then(function (j) { if (HIST === null) return; HIST = j; render(); })
        .catch(function () { if (HIST === null) return; box.innerHTML = '<div class="qnc-empty">Nie udało się wczytać historii.</div>'; });
    });
    window.addEventListener("resize", function () { if (md) place(); });
    b.addEventListener("click", function () {
      if (md) { shut(); return; }
      HIST = null; hb.textContent = "Historia"; ht.textContent = "Powiadomienia";
      if (mob()) document.body.classList.remove("qnav-open");
      md = true; render(); place(); b.classList.add("active");
      requestAnimationFrame(function () { pan.classList.add("on"); });
      document.addEventListener("mousedown", outside, true); document.addEventListener("keydown", esc, true);
      load().then(function (j) { if (j && j.unread) post("/api/notif/read", {}).then(function () { paint(0); }).catch(function () {}); });
    });
    load();
    setInterval(function () { if (!document.hidden) load(); }, 120000);
    window.addEventListener("qnotif-refresh", load); /* SETUP > Powiadomienia zmienione */
    document.addEventListener("visibilitychange", function () { if (!document.hidden) load(); });
  }

  function build() {
    if (window.self !== window.top) { document.documentElement.classList.add("qframe"); return; } // 2026-10-08: strona w ramce (SETUP) - bez menu
    var nav = document.createElement("nav");
    nav.className = "qnav";

    // gora: burger + marka
    var top = document.createElement("div");
    top.className = "qnav-top";
    var burger = document.createElement("button");
    burger.className = "qnav-burger";
    burger.setAttribute("aria-label", "Menu");
    burger.innerHTML = BURGER;
    var brand = document.createElement("div");
    brand.className = "qnav-brand";
    brand.textContent = "QBot";
    top.appendChild(burger);
    top.appendChild(brand);

    function closeExpanded() { document.body.classList.remove("qnav-expanded", "qnav-open"); }

    // obszar produkcyjny
    var ulProd = document.createElement("ul");
    ulProd.className = "qnav-items qnav-prod";
    PROD.forEach(function (it) { ulProd.appendChild(makeLink(it, closeExpanded)); });

    // obszar testowy (na dole, nad przelacznikiem motywu)
    var testWrap = document.createElement("div");
    testWrap.className = "qnav-test";
    var testLabel = document.createElement("div");
    testLabel.className = "qnav-sec-label";
    testLabel.textContent = "Testowe";
    var ulTest = document.createElement("ul");
    ulTest.className = "qnav-items qnav-test-items";
    TEST.forEach(function (it) { ulTest.appendChild(makeLink(it, closeExpanded)); });
    testWrap.appendChild(testLabel);
    testWrap.appendChild(ulTest);

    // stopka: przelacznik motywu
    var foot = document.createElement("div");
    foot.className = "qnav-foot";
    var themeBtn = document.createElement("button");
    themeBtn.type = "button";
    themeBtn.className = "qnav-link qnav-theme";
    themeBtn.innerHTML = '<svg viewBox="0 0 24 24"></svg><span class="qnav-label"></span>';
    foot.appendChild(themeBtn);
    // 2026-10-08: SETUP (zebatka) - w stopce menu nad przelacznikiem dzien/noc, /setup.html (zakladka Powiadomienia)
    foot.insertBefore(makeLink({ href: "/setup.html", label: "Setup", icon: '<path class="qi-f" d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-2.82 1.16V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-2.82-1.16l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 3.17 14H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.16-2.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9.9 3.17V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 2.82 1.16l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 20.83 10H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/><circle cx="12" cy="12" r="3.2"/><circle class="qi-a" cx="12" cy="12" r="1.3"/>' }, closeExpanded).firstChild, themeBtn);

    function paintTheme() {
      var d = isDark();
      themeBtn.querySelector("svg").innerHTML = d ? SUN : MOON;
      var lbl = d ? "Tryb dzienny" : "Tryb nocny";
      themeBtn.querySelector(".qnav-label").textContent = lbl;
      themeBtn.setAttribute("data-label", lbl);
    }
    themeBtn.addEventListener("click", function () {
      var d = !isDark();
      document.documentElement.classList.toggle("theme-dark", d);
      try { localStorage.setItem("qtheme", d ? "dark" : "light"); } catch (e) {}
      paintTheme();
    });

    nav.appendChild(top);
    nav.appendChild(ulProd);
    nav.appendChild(testWrap);
    nav.appendChild(foot);

    var backdrop = document.createElement("div");
    backdrop.className = "qnav-backdrop";
    var fab = document.createElement("button");
    fab.className = "qnav-fab";
    fab.setAttribute("aria-label", "Otworz menu");
    fab.innerHTML = BURGER;

    document.body.appendChild(nav);
    document.body.appendChild(backdrop);
    document.body.appendChild(fab);
    document.body.classList.add("qnav-body");
    paintTheme();
    qAuthBadge();
    try { qBell(top, fab, closeExpanded); } catch (e) {}

    function isMobile() { return window.matchMedia("(max-width:820px),(pointer:coarse) and (max-height:500px)").matches; }

    burger.addEventListener("click", function () {
      if (isMobile()) {
        document.body.classList.toggle("qnav-open");
      } else {
        document.body.classList.toggle("qnav-expanded");
      }
    });
    fab.addEventListener("click", function () { document.body.classList.toggle("qnav-open"); });
    backdrop.addEventListener("click", function () {
      document.body.classList.remove("qnav-open", "qnav-expanded");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();

/* 2026-10-07: zakladki strony w jednym wierszu z tytulem (styl: nav.css, sekcja PAS NAGLOWKA).
   Bierze .tabs / .tabbar stojace tuz za .head i wstawia je za <h1>. Wezly sa przenoszone (id i obsluga klikniec zostaja). */
(function () {
  function qHeadTabs() {
    var h = document.querySelector(".head"), h1 = h && h.querySelector("h1");
    if (!h1) return;
    var t = h.nextElementSibling;
    if (t && (t.classList.contains("tabs") || t.classList.contains("tabbar"))) h1.insertAdjacentElement("afterend", t);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", qHeadTabs); else qHeadTabs();
})();
