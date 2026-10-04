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
    { href: "/trener.html", label: "Trener",
      icon: '<path d="M6.5 6.5v11M17.5 6.5v11"/><path d="M3.5 9v6M20.5 9v6"/><path d="M6.5 12h11"/>' },
    { href: "/kalendarz.html", label: "Kalendarz",
      icon: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M3 10h18M8 2v4M16 2v4"/>' },
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
