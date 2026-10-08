/* qdate.js (2026-10-07) -- JEDYNE miejsce formatu dat DO WYSWIETLANIA w QBot Lab.
   Decyzja uzytkownika: DD.MM (krotko) i DD.MM.RRRR (pelna), godzina po spacji: DD.MM.RRRR HH:MM.
   Daty TECHNICZNE (zapytania do API, obliczenia, pola <input type=date>) zostaja ISO RRRR-MM-DD -- ich NIE formatujemy.
   Wejscie: "RRRR-MM-DD", "RRRR-MM-DD HH:MM[:SS]", "RRRR-MM-DDTHH:MM...", "MM-DD", obiekt Date (czas lokalny).
   Uzycie:  QD.dm("2026-10-06") -> "06.10"     QD.dmy(...) -> "06.10.2026"
            QD.dmyt("2026-10-06 15:31") -> "06.10.2026 15:31"   QD.dmt(...) -> "06.10 15:31"
            QD.text("Jazda 2026-10-06 OK") -> "Jazda 06.10.2026 OK"  (zamienia daty ISO w gotowym tekscie z serwera) */
(function () {
  "use strict";
  function p2(n) { return (n < 10 ? "0" : "") + n; }
  function parts(x) {
    if (x == null || x === "") return null;
    if (x instanceof Date) return isNaN(x) ? null : { y: x.getFullYear(), m: x.getMonth() + 1, d: x.getDate(), h: x.getHours(), mi: x.getMinutes(), t: true };
    var s = String(x), r = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/);
    if (r) return { y: +r[1], m: +r[2], d: +r[3], h: r[4] != null ? +r[4] : null, mi: r[5] != null ? +r[5] : null, t: r[4] != null };
    r = s.match(/^(\d{2})-(\d{2})$/);
    if (r) return { y: null, m: +r[1], d: +r[2], h: null, mi: null, t: false };
    return null;
  }
  function raw(x) { return x == null ? "" : String(x); }
  var QD = {
    dm: function (x) { var p = parts(x); return p ? p2(p.d) + "." + p2(p.m) : raw(x); },
    dmy: function (x) { var p = parts(x); return p ? p2(p.d) + "." + p2(p.m) + (p.y ? "." + p.y : "") : raw(x); },
    dmt: function (x) { var p = parts(x); return p ? QD.dm(x) + (p.t ? " " + p2(p.h) + ":" + p2(p.mi) : "") : raw(x); },
    dmyt: function (x) { var p = parts(x); return p ? QD.dmy(x) + (p.t ? " " + p2(p.h) + ":" + p2(p.mi) : "") : raw(x); },
    text: function (s) {
      return raw(s).replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, function (_, y, m, d) { return d + "." + m + "." + y; });
    }
  };
  window.QD = QD;
})();
