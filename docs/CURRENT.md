# QBot -- CURRENT (handoff sesji)


## Sesja 2026-07-09 -- mapa Leaflet w raporcie z jazdy (belka "Jazda")

Cel: interaktywna mapa trasy nad wykresem przebiegu, spieta z wykresem
(hover dwukierunkowy + zoom wykresu -> zoom mapy). Zrobione i potwierdzone na zywo
(zrzut Michala: mapa + kafle OSM + narysowana trasa 23496824503).

GLOWNE ODKRYCIE (przyczyna dlugiej serii "mapy nie widac"):
w `render(d)` jest `const L=d.load` -- lokalne L PRZESLANIALO globalny Leaflet `L`.
Blok mapy sprawdzal `L.map` = `d.load.map` (undefined) -> cichy `return`, zero bledu.
FIX: w bloku mapy uzywac `window.L` (const LF=window.L), nigdy golego `L`.

Po drodze naprawione/ustalone (szczegoly w docs/RAPORT_WEB.md, sekcja RAPORT Z JAZDY):
- Leaflet hostowany lokalnie /vendor/ (przegladarka Michala bez dostepu do unpkg/cdnjs);
  pobrany przez serwer z cdnjs.
- Wzorzec z analizy trasy: setView([srodek],zoom) NAJPIERW, fitBounds w setTimeout po
  invalidateSize (80/300/700 ms, allB.isValid()); window._qmapJazda.remove() przy re-render.
- Wysokosc mapy INLINE w JS (400px), nie z CSS -- odpornosc na stary HTML w cache.
- no-cache middleware (_no_cache_static) dla .html/.js/.css w qbot_web.py (_webauth_guard).
- Cache-buster ?v= w raport-jazdy.html podbijany przy kazdej zmianie JS (aktualnie v=32).
- /api/ride-report/data zwraca zapisany w1_json bez rebuild -> stare raporty bez lat/lon
  nie maja mapy (tylko 23496824503 ma 381 pkt); starych nie przebudowujemy.

Srodowisko: Michal na Safari (Chrome zamkniety -> Control Chrome bywa niedostepny).
Sondy konsolowe: (async()=>{...})() + alert(JSON.stringify(...)); bez top-level await.

PLIKI TEJ SESJI:
- Poza repo (zywe): /opt/qbot/web/public/raport-jazdy-render.js (blok mapy + sync),
  raport-jazdy.html (CSS .jmap, ?v=32).
- REPO (do commitu, root): qbot_web.py (middleware no-cache _no_cache_static),
  docs/RAPORT_WEB.md, docs/CURRENT.md, docs/DECISIONS.md, docs/TODO.md.
  UWAGA: qbot_web.py wymaga `systemctl restart qbot-web` (juz zrobione tej sesji).

Do zrobienia pozniej: sprzatniecie scripts/_tmp_*.py tej sesji (brak rm w DEV MCP,
przez Desktop Commander/SSH).
