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
- Determinizm: liczby i grafika TYLKO z kodu (endpoint/generator). LLM daje wylacznie
  proze w wyznaczonych miejscach — nigdy liczb ani geometrii.
- Pliki .bak w /opt/qbot/web/public sa .gitignore; sprzataj przez SSH (`rm`), bo
  dev_shell_exec nie ma rm.

## Historia / lekcja
Wczesniej raport byl JEDNYM wypalanym index.html z blokiem DATA i mapa w base64.
Dwa problemy: (a) podwojna rola pliku (raport = jednoczesnie szablon) -> rownolegle
sesje nadpisywaly sie nawzajem z backupow; (b) kazda trasa = osobny wypalony plik.
Przebudowa 2026-07-03: DANE -> endpoint /api/report/data, RENDER -> raport-render.js,
STYL -> raport.css, WYBOR -> raport-trasy.html. Stary przeplyw base64-mapowy i
korupcja przez heredoc: NIEAKTUALNE.
