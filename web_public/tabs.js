/* QBot wewnetrzne zakladki tresci -- buduje gorny pasek z <section data-qtab="...">.
   Pamieta wybrana zakladke w URL (#slug) + localStorage per strona. Wielokrotnego uzytku. */
(function () {
  function slug(s) {
    var map = { "ą":"a","ć":"c","ę":"e","ł":"l","ń":"n","ó":"o","ś":"s","ź":"z","ż":"z" };
    return (s || "").toLowerCase()
      .replace(/[ąćęłńóśźż]/g, function (c) { return map[c] || c; })
      .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  }

  function init() {
    var panels = [].slice.call(document.querySelectorAll("[data-qtab]"));
    if (!panels.length) return;

    var order = [], seen = {};
    panels.forEach(function (p) {
      var n = p.getAttribute("data-qtab");
      p.classList.add("qtab-panel");
      p.setAttribute("data-qslug", slug(n));
      if (!seen[n]) { seen[n] = 1; order.push(n); }
    });

    var bar = document.createElement("div");
    bar.className = "qtabs-bar";
    var btns = {};
    order.forEach(function (n) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "qtabs-btn";
      b.textContent = n;
      var sl = slug(n);
      b.setAttribute("data-qslug", sl);
      b.addEventListener("click", function () { select(sl, true); });
      bar.appendChild(b);
      btns[sl] = b;
    });
    var mount = document.getElementById("qtabs-mount");
    if (mount) { mount.appendChild(bar); }
    else { panels[0].parentNode.insertBefore(bar, panels[0]); }

    var key = "qtabs:" + location.pathname;

    function select(sl, save) {
      if (!btns[sl]) sl = slug(order[0]);
      panels.forEach(function (p) { p.hidden = (p.getAttribute("data-qslug") !== sl); });
      order.forEach(function (n) { btns[slug(n)].classList.toggle("active", slug(n) === sl); });
      if (save) {
        try { history.replaceState(null, "", "#" + sl); } catch (e) { location.hash = sl; }
        try { localStorage.setItem(key, sl); } catch (e) {}
      }
    }

    var initial = (location.hash || "").replace(/^#/, "");
    if (!btns[initial]) { try { initial = localStorage.getItem(key) || ""; } catch (e) { initial = ""; } }
    if (!btns[initial]) initial = slug(order[0]);
    select(initial, false);

    window.addEventListener("hashchange", function () {
      var h = (location.hash || "").replace(/^#/, "");
      if (btns[h]) select(h, false);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
