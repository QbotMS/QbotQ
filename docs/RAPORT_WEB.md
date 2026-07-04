# RAPORT WEB (qbot-web) — architektura i gdzie co edytowac

Status zywy (weryfikuj zawsze): raport trasy jest serwowany publicznie przez
usluge qbot-web. Ten plik to instrukcja dla kazdej nowej sesji. Gdy dokument
rozjezdza sie z kodem — wygrywa zywy system.

## Usluga
- Kod: /opt/qbot/app/qbot_web.py  (FastAPI + StaticFiles, nasluch 0.0.0.0:30181, czysty HTTP)
- Web root: /opt/qbot/web/public/
- systemd: qbot-web.service (User=qbot). Pliki statyczne (.html/.js/.css) sa czytane
  z dysku NA BIEZACO — zmiana = zywa od razu, BEZ restartu. Zmiana w qbot_web.py
  (Python) wymaga: `systemctl restart qbot-web`.
- Publiczny adres: albert.cytr.us -> olga181.mikrus.xyz:30181 (HTTPS dokłada Cytrus; apka oddaje HTTP).

## Architektura raportu trasy (WAZNE — 4 role, 4 pliki)
Raport NIE jest juz jednym wypalanym plikiem HTML. Jest rozbity na warstwy;
kazda zmiana trafia do JEDNEJ z nich:

1. DANE (co sie liczy) -> `qbot_web.py`: funkcja `_build_report_data()` + endpoint
   `GET /api/report/data?route_id=&date=&time=&long_stops=&long_stop_min=`.
   Zwraca blok DATA (JSON): route / start / time / chart (ele, surface_cat = 5 kategorii,
   weather[wbgt,rain,mm,code,icon,w_along,w_cross,feels], wind gesty, eta). Liczone
   z bazy + silnikow: route_meteo_engine (pogoda+wiatr+odczuwalna), route_time_estimate v2
   (czas, postoje), surface coalesce (_load_surface_buckets/_coalesce_categories),
   _admin (lokalizacja startu, reverse-geocode+cache), _read_route_source (przewyzszenie).
   To JEDYNE zrodlo danych — kazda trasa liczona samodzielnie. REPO -> restart + commit.
   - Dlugie przerwy: `long_stops` = LICZBA, `long_stop_min` = minuty NA JEDNA przerwe;
     endpoint mnozy (total = liczba*min) i podaje do route_time_estimate jako
     planned_long_stops + planned_long_stop_min. "postoje auto" w DATA to mikro+krotkie
     (bez dlugich); dlugie osobno jako time.long_stops_min.
2. STRUKTURA + WYKRES (co widac, jak rysowane) -> `/opt/qbot/web/public/raport-render.js`.
   `window.renderReport(data, mount)` wstawia szkielet do `mount` i rysuje: hero,
   mape (Leaflet + `/api/routes/{id}/geometry`, kolor linii = nawierzchnia), wykres SVG
   (profil + nawierzchnia + wstega wiatru + WBGT + odczuwalna + deszcz + ikony + kursor).
   Obsluguje wielokrotne generowanie (niszczy poprzednia mape `window._qmap`). Poza repo -> zywe od razu.
3. STYLE (wyglad) -> `/opt/qbot/web/public/raport.css`. WSZYSTKIE style: zmienne :root,
   komponenty raportu (hero, startband, karty, mapa, wykres) ORAZ pasek formularza.
   Klasy z raport.css sa emitowane przez raport-render.js — kolor/rozmiar/ramke komponentu
   zmieniasz TU. Poza repo -> zywe od razu.
4. STRONA + FORMULARZ (wybor) -> `/opt/qbot/web/public/raport-trasy.html`. Cienki plik:
   sticky pasek u gory (trasa z `/api/routes/ready`, data, godzina, liczba dlugich przerw,
   czas 1 przerwy) + [Generuj] + `<div id="report">`. Po Generuj: fetch `/api/report/data`
   -> `renderReport(data, #report)`. Linkuje raport.css i raport-render.js. Poza repo -> zywe od razu.

Lista tras do dropdowna: `GET /api/routes/ready` (qbot_web.py) — trasy z policzona
nawierzchnia, DEDUPLIKOWANE po route_id (DISTINCT ON, najnowszy job).

`index.html` = kafelki QBot lab (jeden kafelek "Raport Trasy" -> /raport-trasy.html).
To NIE jest raport.

### Regula przy poprawkach (zeby nie bylo balaganu)
- wyglad (kolory, rozmiary, ramki) -> raport.css
- co widac / jak rysowane (nowy element, zmiana wykresu/mapy) -> raport-render.js
- co sie liczy (nowe pole danych, inna logika) -> `_build_report_data` w qbot_web.py (+restart +commit)
- pola formularza / wybor -> raport-trasy.html
Dodajesz nowy element wizualny? Zwykle DWA pliki: struktura w raport-render.js + styl
w raport.css. Nowa liczba w raporcie? qbot_web.py (policzyc) + raport-render.js (pokazac).

## Jak wdrazac (KANAL ODPORNY NA KORUPCJE)
Pliki maja nie-ASCII (polskie znaki, emoji). Te kanaly PSUJA tresc — NIE uzywac do
zapisu: heredoc z nie-ASCII (homoglify cyrylicy), dev_codex (parafrazuje).
Uzywaj `dev_write_file(path, content)` z DEV MCP — zapis BAJT-W-BAJT (content idzie
przez JSON MCP). Allowlist obejmuje /opt/qbot/web.
Wygodny wzorzec przy EDYCJI istniejacych plikow: skrypt `_tmp_*.py` (io.open + str.replace
z `assert s.count(old)==1`), uruchom `/opt/qbot/app/.venv/bin/python`, skrypt kasuje sie
sam (`os.remove(__file__)`). Nie nadpisuj wielkich plikow w calosci.

Po wdrozeniu ZAWSZE weryfikuj na zywo (bez dowodu nie ma sukcesu):
- HTTP 200 przez urllib do `http://127.0.0.1:30181/<plik>` (curl jest blokowany w dev_shell_exec)
- endpoint: JSON parsuje, pola obecne, wartosci sensowne (np. reakcja total_h na dlugie przerwy)
- render: grep kluczowych markerow w html/js

## Konwencje
- Wiatr ZAWSZE w m/s.
- Cache-bust: raport-trasy.html linkuje css/js z `?v=NNNN`; przy KAZDEJ zmianie .css/.js
  podbij token (inaczej przegladarka trzyma stara wersje). Aktualny token: 2026070305.
- Determinizm: liczby i grafika TYLKO z kodu (endpoint/generator). LLM daje wylacznie
  proze w wyznaczonych miejscach — nigdy liczb ani geometrii.
- Pliki .bak w /opt/qbot/web/public sa .gitignore; sprzataj przez SSH (`rm`), bo
  dev_shell_exec nie ma rm.

## Funkcje raportu — stan 2026-07-03 (po zmianach)
Elementy zaimplementowane w warstwach jw. (weryfikuj na zywo):

- Chip pogoda/wiatr w naglowku: DANE `_build_weather_head(weather, per)` -> `DATA.weather_head`
  (ikona nieba; odczuwalna ~C + komfort: zimno <6 / chlodno 6-12 / komfort 13-25 / goraco >=26;
  opady; wiatr KIERUNEK + m/s). Render `renderWx()` w raport-render.js, styl `.wxchip` w raport.css.
- Wersja trasy w naglowku: `route.version_modified` = `route_modified_at` ("YYYY-MM-DD HH:MM").
  Wybor wersji DETERMINISTYCZNY — lookupy route_base w qbot_web.py sortuja
  `ORDER BY route_modified_at DESC NULLS LAST LIMIT 1` (najnowsza).
- Wchlanianie krotkich odcinkow nawierzchni: `_absorb_short_surface(runs, min_km=0.3)` (qbot_web.py)
  — odcinek <300 m wchlaniany do sasiada o NAJBLIZSZEJ kategorii (remis -> dluzszy sasiad).
  Kategoria 5 (ryzyko) nietykalna: nigdy nie wchlaniana ani nie wchlania.
- Mapa B/W (jak StatsHunters): kafelki OSM `tile.openstreetmap.org` + filtr skali szarosci w CSS
  `#map.bw .leaflet-tile-pane{filter:grayscale(1) contrast(1.05)}`; element #map ma klase `bw`.
- Przyciski pod mapa (`.map-ctl`; struktura w raport-render.js, styl w raport.css):
  * "Wysrodkuj trase" -> `MAPX.fitAll()` (fitBounds calej trasy);
  * "Mapa: B/W <-> kolor" -> przelacza klase bw/color na #map. Tryb kolor:
    `#map.color .leaflet-tile-pane{opacity:.8;filter:contrast(.9)}` (80% krycia + kontrast -10%).
- Klik w segment nawierzchni na wykresie -> zoom mapy na ten odcinek (`MAPX.fitKm(a,b)`).
- Kolory nawierzchni (SCAT w raport-render.js; wspolne wykres + mapa + legenda):
  1 asfalt `#000000`, 2 dobry gravel/szuter `#2e7d32` (ciemnozielony), 3 zwykly gravel `#8bc34a`,
  4 trudna/wolna `#e07b1a`, 5 ryzyko `#c2452f`. Linia trasy z biala obwodka (7px bialy pod 4px kolor).
- Wiatr na wstedze: boczno-przedni = bladorozowy, boczno-tylny = zielony (legenda 2 wpisy);
  chmury bez deszczu = szare (poprawka `glyph()`).
- METEO wystawia wiatr otoczenia per segment: `wind_dir_deg` / `wind_speed_ms` (route_meteo_engine.py)
  — zasila chip naglowka.

## Historia / lekcja
Wczesniej raport byl JEDNYM wypalanym index.html z blokiem DATA i mapa w base64.
Dwa problemy: (a) podwojna rola pliku (raport = jednoczesnie szablon) -> rownolegle
sesje nadpisywaly sie nawzajem z backupow; (b) kazda trasa = osobny wypalony plik.
Przebudowa 2026-07-03: DANE -> endpoint /api/report/data, RENDER -> raport-render.js,
STYL -> raport.css, WYBOR -> raport-trasy.html. Stary przeplyw base64-mapowy i
korupcja przez heredoc: NIEAKTUALNE.


## Archiwum raportow (historia, 2026-07-04)
Kazde wygenerowanie `/api/report/data` zapisuje pelny blok DATA do
`qbot_v2.route_report_snapshots` (tabela: sql/route_report_snapshots_v1.sql).
Retencja: 4 najnowsze NA TRASE (route_id), starsze kasowane automatycznie
(`_save_report_snapshot` w qbot_web.py). Zapisujemy DANE, nie wyrenderowany HTML -
zmiana wygladu (raport-render.js/raport.css) automatycznie obejmuje tez stare zapisy.

- `GET /api/report/history?route_id=` -> lista ostatnich zapisow (id + kiedy + parametry).
- `GET /api/report/snapshot/{id}` -> dokladny zapisany blok DATA (bez liczenia od nowa).
- Front (raport-trasy.html): pasek "Historia" (`#f-history`, styl `.hist-bar`/`.hist-chip`
  w raport.css) + `localStorage.qbot_report_last_route` - po wejsciu na strone / zmianie
  trasy w dropdownie automatycznie doladowuje NAJNOWSZY zapis danej trasy (bez klikania
  Generuj). Klik Generuj zawsze liczy swiezy raport i dopisuje do archiwum.
- Szczegoly decyzji: docs/DECISIONS.md, wpis 2026-07-04.

## Wysylka raportu mailem (uproszczona wersja + zrzuty, 2026-07-04)
`POST /api/report/send-email?route_id=&date=&time=&long_stops=&long_stop_min=&to=` liczy
raport (jak `/api/report/data`, zapisuje tez snapshot), robi zrzuty PNG mapy i wykresu
przez headless Chromium (Playwright) i wysyla mailem (sekcje tekstowe jedna pod druga +
2 obrazki inline + GPX w zalaczniku). Nowy "cichy" plik `raport-print.html` (bez
formularza) renderuje dane przez ten sam `raport-render.js`/`raport.css` co normalny
raport - zrzut = dokladnie to co widac w interaktywnym raporcie. Sygnal gotowosci kafli
mapy: `window.__QBOT_MAP_READY` (ustawiany w raport-render.js). SMTP = to samo konto
Gmail co poranny raport (`qbot_config`). Playwright/Chromium zainstalowane w
`/opt/qbot/app/.ms-playwright` (PLAYWRIGHT_BROWSERS_PATH w systemd unit qbot-web -
katalog `/root/.cache` nie jest widoczny dla usera `qbot`). Szczegoly: docs/DECISIONS.md,
wpis 2026-07-04 (2).

## Kwadraty (StatsHunters) — warstwa kafli na mapie (2026-07-03)
Nakladka explorer-tiles (z14, jak VeloViewer/Squadrats): ktore kwadraty trasa
zdobywa (nowe), ktore juz masz, plus otoczka kontekstu.

- DANE: endpoint `GET /api/routes/{route_id}/tiles?margin=N` (qbot_web.py). Liczy kafle
  z14 z geometrii trasy (interpolacja ~90 m, by nie przeskoczyc kafla ~1,5 km), pobiera
  posiadane ze StatsHunters przez `tools/tile_store.fetch_tiles` (share w env
  STATSHUNTERS_SHARE_ID; cache 24h w /opt/qbot/artifacts/tiles). Statusy: new (trasa, nie
  masz) / keep (trasa, masz) / owned (otoczka, masz) / empty (otoczka, wolne). margin =
  szerokosc pasa otoczki w kaflach (domyslnie 3). Zwraca bounds [[S,W],[N,E]] + counts.
  REPO -> restart qbot-web + commit.
- RENDER: raport-render.js, funkcja setupTiles w initMap. Osobny pane "tiles" (zIndex 350,
  pod linia trasy). L.rectangle per kafel: new zielony, keep niebieski, owned szary (lekki
  fill), empty sam obrys. Przycisk "Kwadraty: wl/wyl" w pasku .map-ctl (obok Wysrodkuj /
  Mapa B-W) + licznik span.map-ctl-info. Poza repo -> zywe od razu.
- STYL: raport.css, klasa .map-ctl-info (wyszarzony licznik).

UWAGA (dwa uklady kafli): tools/tile_store.py uzywa slippy z14 (zgodne ze StatsHunters).
tools/gpx_history_loader.py uzywa INNEJ siatki 0,01 stopnia — NIE mieszac; do tej warstwy
tylko tile_store + SH.

UWAGA (cache Cloudflare): raport-trasy.html laduje raport-render.js i raport.css z `?v=DATA`.
Edge cache'uje po pelnym URL, wiec KAZDA zmiana js/css wymaga PODBICIA `?v=` w
raport-trasy.html — inaczej Cloudflare poda stare bajty (twardy reload NIE pomaga). To bylo
zrodlo objawu "zmiany nie widac na mapie".
