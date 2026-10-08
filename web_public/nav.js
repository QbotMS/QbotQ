/* QBot wspolny sidebar -- wstrzykiwany na kazdej stronie.
   Domyslnie waski rail (ikony). Rozsuniecie NACHODZI na tresc (nie przesuwa jej), stan nietrwaly.
   Menu podzielone: PRODUKCYJNE (gora) + TESTOWE (na dole, nad przelacznikiem motywu).
   Stopka: przelacznik motywu dzien/noc (klasa html.theme-dark, klucz qtheme). */
(function () {
  var PROD = [
    { href: "/index.html", label: "Start", alt: ["/"],
      icon: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>' },
    { href: "/forma.html", label: "Forma",
      icon: '<path d="M3 17l6-6 4 4 7-8"/><path d="M14 7h6v6"/>' },
    { href: "/trening.html", label: "Trening", alt: ["/trener.html", "/kalendarz.html"],
      icon: '<path d="M6.5 6.5v11M17.5 6.5v11"/><path d="M3.5 9v6M20.5 9v6"/><path d="M6.5 12h11"/>' },
    { href: "/raport-jazdy.html", label: "Raport jazdy",
      icon: '<circle cx="6" cy="17" r="3"/><circle cx="18" cy="17" r="3"/><path d="M6 17l4-8h5l3 8M10 9l2-4h3"/>' },
    { href: "/raport-trasy.html", label: "Analiza trasy",
      icon: '<path d="M9 4l-5 2v14l5-2 6 2 5-2V4l-5 2-6-2z"/><path d="M9 4v14M15 6v14"/>' },
    { href: "/planer-wyprawy.html", label: "Planer wyprawy",
      icon: '<circle cx="12" cy="12" r="9"/><path d="M16 8l-6 2-2 6 6-2 2-6z"/>' },
    { href: "/garaz.html", label: "Garaż",
      icon: '<path d="M3 21V9l9-6 9 6v12"/><path d="M8 21v-7h8v7"/>' }
  ];
  var TEST = [
    { href: "/mq2.html", label: "MQ2",
      icon: '<path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/>' },
    { href: "/naprawa-trasy.html", label: "Naprawa trasy",
      icon: '<path d="M14 6a4 4 0 0 0-5.5 5.2l-5 5a1.5 1.5 0 0 0 2.1 2.1l5-5A4 4 0 0 0 18 8l-2.5 2.5L13 8 15.5 5.5z"/>' }
  ];

  var BURGER = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg>';
  var MOON = '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>';
  var SUN = '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>';

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
  function qAuthBadge(foot) {
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
      } else if (j.kind === "owner" && foot) {
        var a = document.createElement("a");
        a.className = "qnav-link";
        a.href = "/auth/sessions";
        a.setAttribute("data-label", "Dost\u0119py tymczasowe");
        a.innerHTML = '<svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg><span class="qnav-label">Dost\u0119py tymczasowe</span>';
        a.addEventListener("click", function (e) { e.preventDefault(); document.body.classList.remove("qnav-expanded", "qnav-open"); qLockOpen(); });
        foot.insertBefore(a, foot.firstChild);
        if (/[?&]klodka=1\b/.test(location.search)) qLockOpen();
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
  function qLockOpen() {
    var ov = QL.ov;
    if (!ov) {
      ov = QL.ov = document.createElement("div"); ov.id = "qlock"; ov.className = "qmod";
      ov.innerHTML = '<div class="qlock-box" role="dialog" aria-modal="true" aria-label="Dostępy i konto">'
        + '<div class="qlock-h"><b>Dostępy tymczasowe</b><button type="button" class="qlock-x" aria-label="Zamknij">\u00d7</button></div>'
        + '<div class="qlock-body"><div class="qlock-req" hidden></div>'
        + '<div class="qlock-sec">Aktywne dostępy</div><p class="qlock-muted">Goście mają tylko podgląd przez 1 h. Zakończenie działa od razu.</p>'
        + '<div class="qlock-list"></div><button type="button" class="qlock-all" hidden>Zakończ wszystkie</button></div>'
        + '<div class="qlock-foot"><span>Wylogowanie dotyczy tej przeglądarki.</span><button type="button" class="qlock-out">Wyloguj</button></div></div>';
      document.body.appendChild(ov);
      ov.addEventListener("click", function (e) {
        if (e.target === ov) return qlClose();
        var t = e.target.closest ? e.target : null; if (!t) return;
        var b;
        if ((b = t.closest(".qlock-end"))) qlRevoke(b.getAttribute("data-id"));
        else if ((b = t.closest(".qlock-ok"))) qlDecide(b.getAttribute("data-id"), "approve");
        else if ((b = t.closest(".qlock-no"))) qlDecide(b.getAttribute("data-id"), "deny");
      });
      ov.addEventListener("keydown", function (e) {
        var i = e.target; if (e.key === "Enter" && i && i.matches && i.matches(".qlock-req input[data-id]")) qlDecide(i.getAttribute("data-id"), "approve");
      });
      ov.querySelector(".qlock-x").addEventListener("click", qlClose);
      ov.querySelector(".qlock-all").addEventListener("click", function () { qlRevoke("all"); });
      document.addEventListener("keydown", function (e) { if (e.key === "Escape" && ov.classList.contains("on")) qlClose(); });
      ov.querySelector(".qlock-out").addEventListener("click", function () {
        var b = this; b.disabled = true; b.textContent = "Wylogowuję…";
        var go = function () { location.href = "/login"; };
        fetch("/auth/logout", { method: "POST", credentials: "same-origin" }).then(go, go);
      });
    }
    ov.classList.add("on"); qlLoadReq(); qlLoadSes();
    if (!QL.timer) QL.timer = setInterval(function () { if (ov.classList.contains("on")) qlLoadReq(); }, 3000);
  }

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
  var BELL = '<svg viewBox="0 0 24 24"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>';
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
    function render() {
      var it = (DATA && DATA.items) || [];
      if (!it.length) { box.innerHTML = '<div class="qnc-empty">Brak powiadomień — wszystko w porządku.</div>'; return; }
      box.innerHTML = it.map(function (x, i) {
        return '<div class="qnc-it' + (x.unread ? " u" : "") + '"><div class="qnc-ic">' + qEsc(x.icon) + '</div><div class="qnc-tx">'
          + '<b>' + qEsc(x.title) + '</b>' + (x.body ? '<div class="qnc-b">' + qEsc(x.body).replace(/\n/g, "<br>") + '</div>' : "")
          + '<div class="qnc-f"><span>' + qEsc(x.when) + '</span>'
          + (x.url ? '<a href="' + qEsc(x.url) + '">przejdź</a>' : "")
          + (x.action ? '<button type="button" data-a="' + i + '">' + qEsc(x.action.label) + '</button>' : "")
          + (!x.live ? '<button type="button" class="qnc-x" data-d="' + x.id + '" title="Ukryj">ukryj</button>' : "")
          + '</div></div></div>';
      }).join("");
      box.querySelectorAll("button[data-a]").forEach(function (bt) {
        bt.onclick = function () { var a = it[+bt.dataset.a].action; bt.disabled = true;
          post(a.post, a.body).then(load).catch(function () { bt.disabled = false; bt.textContent = "nie udało się"; }); };
      });
      box.querySelectorAll("button[data-d]").forEach(function (bt) {
        bt.onclick = function () { bt.disabled = true; post("/api/notif/dismiss", { id: +bt.dataset.d }).then(load).catch(function () { bt.disabled = false; }); };
      });
    }
    /* 2026-10-08: wysuwany panel obok dzwonka (zamiast okna na srodku). Telefon: panel na cala szerokosc z lewej. */
    var pan = document.createElement("div"); pan.className = "qnc-pan"; pan.setAttribute("role", "dialog"); pan.setAttribute("aria-label", "Powiadomienia");
    pan.innerHTML = '<div class="qnc-h"><b>Powiadomienia</b><button type="button" class="qnc-close" aria-label="Zamknij">\u00d7</button></div>';
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
    window.addEventListener("resize", function () { if (md) place(); });
    b.addEventListener("click", function () {
      if (md) { shut(); return; }
      if (mob()) document.body.classList.remove("qnav-open");
      md = true; render(); place(); b.classList.add("active");
      requestAnimationFrame(function () { pan.classList.add("on"); });
      document.addEventListener("mousedown", outside, true); document.addEventListener("keydown", esc, true);
      load().then(function (j) { if (j && j.unread) post("/api/notif/read", {}).then(function () { paint(0); }).catch(function () {}); });
    });
    load();
    setInterval(function () { if (!document.hidden) load(); }, 120000);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) load(); });
  }

  function build() {
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
    qAuthBadge(foot);
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
