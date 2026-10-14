# POGODA — RADAR opadu (krok 1 modułu Pogoda)

> Stan: 2026-10-14. Logika: `qbot_radar.py`. Wpięcie: `qbot_web.py` (pętla w tle + `/api/radar/*`).
> Testy offline: `tests/test_radar.py` (5). Konwencje: wiatr/ruch opadu w km/h tylko dla prędkości przesuwania się
> chmur (to nie wiatr przy ziemi — wiatr w raportach dalej w m/s), czasy lokalne Europe/Warsaw.

## Po co
Odpowiedź na: gdzie teraz pada, dokąd i jak szybko opad się przesuwa, czy idzie na mnie, kiedy przestanie.
Decyzja projektowa (2026-10-14, Michał): bez osadzania Windy; własny radar z otwartych danych.

## Źródło danych
- **EUMETNET OPERA**, kompozyt maksymalnej odbiciowości **DBZH**, co **5 min**, siatka **1 km**, opóźnienie ok. 10 min.
- Zawiera wszystkie 10 radarów IMGW (plbrz, plgdy, plgsa, plleg, plpas, plpoz, plram, plrze, plswi, pluzr).
- Publiczny zasobnik S3 CloudFerro, bez klucza: `https://s3.waw3-1.cloudferro.com/openradar-24h/RRRR/MM/DD/OPERA/COMP/`
  plik `OPERA@RRRRMMDDTHHMM@0@DBZH.tiff` (ok. 4 MB). Dokumentacja: eumetnet.github.io/openradardata-documentation.
- Licencja **CC BY 4.0** — podpis „EUMETNET OPERA” na mapie obowiązkowy (`qbot_radar.ATTR`).
- Kodowanie w pliku: **NaN = radar widzi, brak echa**; **-9999000 = brak pokrycia**. (Pomyłka tych dwóch dawała
  fałszywe „brak danych” — naprawione.)
- Odrzucone: RainViewer (od 01.01.2026 darmowe API bez prognozy, zoom ≤ 7), IMGW bezpośrednio (brak otwartego radaru).

## Jak działa
1. `sync()` (pętla `_radar_loop` w qbot-web co `EVERY_S`=300 s): pobiera brakujące klatki z ostatnich `KEEP_MIN`=120 min,
   przelicza na siatkę Web Mercator `BBOX` lon 11–27, lat 47,5–56,5 (piksel 1500 m merc ≈ 0,9 km), zapisuje
   `RRRRMMDDTHHMM.npz` (dBZ w uint8: 0 = brak pokrycia, (dBZ+32)*2) + `.png` (paleta radarowa, przezroczysta < 12 dBZ),
   kasuje starsze, przelicza ruch → `motion.json`. Zapis atomowy (tmp + os.replace; `.npz` ostatni = klatka gotowa).
   Cache: `/opt/qbot/artifacts/radar_cache` (env `QBOT_RADAR_CACHE`). Wyłączenie pętli: `QBOT_RADAR_LOOP=0`.
2. `motion()`: kafelki 128 px (≈120 km), krok 64. Trzy klatki: t-30, t-15, t. Korelacja **częściowo wybielona**
   (|X|^0,5) po odjęciu średniej i oknie Hanna. Kafelek przyjęty tylko gdy ruch w 1. i 2. połówce zgadza się
   (≤ `CONS_KMH`=15 km/h) — odrzuca szum i opad, który rośnie/zanika. Wektor = średnia połówek, waga = udział opadu.
3. `local_motion(lat, lon)`: ważona mediana kafelków w promieniu 200 km (inaczej cała mapa). Zwraca km/h, skąd/dokąd,
   liczbę kafelków, rozrzut.
4. `nowcast_point(lat, lon)`: historia w punkcie (koło 2 km) + prognoza co 5 min przez przesuwanie najnowszego
   obrazu wstecz wzdłuż ruchu. Promień niepewności rośnie: 2 km + 0,08 km/min (60 min ≈ 7 km). `udzial` = jaka
   część koła ma opad ≥ `DBZ_RAIN`=18 dBZ (≈0,5 mm/h). mm/h z Marshall-Palmer (Z=200R^1,6). Werdykt prostym
   językiem: „pada, przestanie ok. HH:MM” / „sucho, opad dojdzie ok. HH:MM” / „omija”.

## API (za bramką logowania)
- `GET /api/radar/meta` → `bounds` (rogi dla Leaflet imageOverlay), `klatki` [{id, t, iso}], `zrodlo`, stan ruchu.
- `GET /api/radar/frame/{id}.png` → warstwa klatki.
- `GET /api/radar/punkt?lat=&lon=&horyzont=120` → `historia`, `prognoza`, `ruch`, `werdykt`, `opoznienie_min`.

## Weryfikacja (2026-10-14 08:20)
Ruch z radaru vs wiatr 700 hPa (Open-Meteo) — zgodne kierunkiem i prędkością:
Warszawa 51 km/h z W (wiatr 44 z 286°), Gdańsk 57 z W (59 z 255°), Poznań 53 z W (58 z 282°), Białystok 51 z W.
Pokrycie Polski 100%. Pobranie+przeliczenie klatki < 1 s, PNG ≈ 100 kB, npz ≈ 200 kB (2 h ≈ 7 MB).

## Uczciwe granice
- Przesuwanie obrazu zakłada stały kształt i siłę opadu: front ~1–2 h, przelotne opady/burze ~30–60 min.
  Prognoza > 60 min oznaczona `radar-orientacyjnie`.
- Radar nie widzi opadu, który dopiero powstanie → dalszy horyzont z modelu (ICON-D2) — następny etap.
- Jeden wektor na punkt (bez rotacji/wzrostu komórek).

## Następne etapy (zatwierdzone 2026-10-14)
- Strona **Pogoda → zakładka Radar**: mapa Leaflet, animacja, strzałka ruchu, karta „u Ciebie”.
  Pozycja edytowalna: **moja (dom) / przeglądarka / zadana** (klik, miejscowość, start trasy z kalendarza).
- Jedna oś czasu: radar 0–1 h (do 2–3 h przy froncie) → model ICON-D2, ze znacznikiem źródła i ostrzeżeniem przy rozjeździe.
- Bez nowych wiadomości Telegram. Albert: narzędzie radaru osobno, z wpisem w `_SYSTEM`.

## Strona `pogoda.html` (2026-10-14, krok 1 na żywo)
Układ jak Analiza trasy (decyzja Michała po mockupie): mapa pod całą stroną; lewy panel z paskiem ikon (☂ U Ciebie — na żywo;
◷ Okno jazdy, ★ Weekend, ≋ Warunki — „wkrótce”), rozwijany do pół ekranu; dolny pasek = warstwy mapy (Opad; reszta „wkrótce”)
+ oś czasu z odtwarzaniem: klatki radaru 2 h + prognoza radaru +10…+60 min (ostatni obraz przesunięty wzdłuż ruchu).
Pozycja: Moja = `/api/pogoda/dom` (najczęstszy start jazd, jak pogoda Trenera) / Przeglądarka (geolokalizacja) / Klik na mapie;
zapamiętywana w localStorage `qpogoda_pos`. Wykres osi punktu (Chart.js, dymki, klikalne etykiety): radar było / radar prognoza /
model ICON / szansa %. Werdykt radaru + zdanie z modelu („kolejny opad ok. HH:MM” / „sucho do HH:MM”) + ostrzeżenie, gdy radar
i model różnią się w najbliższej godzinie. Podkład: OSM + `qmap-tiles.js` (noc). Odświeżanie klatek co 2 min.
- `GET /api/pogoda/dom`, `GET /api/pogoda/model?lat=&lon=&godziny=12` (`qbot_pogoda.py`, Open-Meteo `icon_seamless`,
  minutely_15, cache 10 min). Samo `icon_d2` dawało 14.10.2026 HTTP 400 „No data is available for this location”.
- Mockup kroków 1–4: `pogoda-mockup.html` (dane przykładowe oznaczone).

## Mapa modelu (2026-10-14) — `qbot_pogoda_map.py`
DWD **ICON-EU** (opendata.dwd.de, bez limitu; wybrany, bo wygrywa najwięcej parametrów w sprawdzalności). Przebiegi 00/12 UTC,
kroki co 1 h do +24 i co 3 h do +60. Parametry: T_2M, TOT_PREC (opad godzinowy z różnicy), U/V_10M, VMAX_10M, T_G, TD_2M.
Warstwy PNG (siatka Mercator 6 km, dwuliniowo): opad, temp, wiatr, porywy, lod (grunt ≤ 0,5°C i opad 6 h lub szron),
mgla (przybliżenie T−Td i słaby wiatr — ICON-EU nie ma widzialności). Cache `/opt/qbot/artifacts/pogoda_model/<run>/`,
2 ostatnie przebiegi. Pętla w qbot-web co 20 min (`QBOT_POGODA_MAP_LOOP=0` wyłącza). API: `/api/pogoda/mapa/meta`,
`/api/pogoda/mapa/{warstwa}/{run}_{krok}.png`. Biblioteka: `eccodes` + `eccodeslib` (pip). DWD: długość 336,5 = −23,5.
Strona: dolne zakładki Opad/Temperatura/Wiatr/Porywy/Mgła/Oblodzenie; oś Opadu: radar → radar +2 h → model do +60 h.
Transfer ~260 MB na przebieg (~520 MB/dobę).

### Spójność radar → model (2026-10-14, po zgłoszeniu Michała: duży rozjazd ostatniej klatki radaru i pierwszej modelu)
- Przebiegi ICON-EU 00/06/12/18 UTC (świeższy model); opad modelu rysowany w **skali radaru** (mm/h → dBZ, ta sama paleta i próg).
- **Korekta położenia** `qbot_pogoda_map.korekta()`: korelacja fazowa pola opadu modelu (krok z aktualną godziną) i aktualnego radaru
  (siatka 6 km) → przesunięcie; strona przesuwa mapę modelu z wagą malejącą do 0 po 6 h. **Bezpiecznik:** korekta tylko gdy zgodność
  (korelacja pól log(1+mm/h)) rośnie o ≥ 0,05, przesunięcie ≤ 200 km i opad ≥ 2% pola (test 14.10: 09:05 → 68 km, 09:10 → 4 km bez
  poprawy — bez bezpiecznika mapa by skakała). API `/api/pogoda/mapa/korekta`.
- **Płynne przejście:** przez 2 h po końcu prognozy radaru jego obraz wygasa, a model narasta.

### Szansa opadu z zespołu ICON-EU-EPS (2026-10-14)
Powód: nawet świeży przebieg deterministyczny zgadzał się z radarem na „teraz” tylko w ~33% (06 UTC, 09:15) — ostre plamy opadu
z jednego przebiegu sugerowały pewność, której nie ma. Decyzja Michała: na zakładce Opad po radarze pokazujemy **szansę opadu**:
odsetek z 40 wariantów ICON-EU-EPS z opadem ≥ 0,2 mm/h (`qbot_pogoda_map.eps_build`, warstwa `szansa`, ~8 MB/krok, siatka
ikosaedryczna ~20 km → najbliższa komórka, indeks `eps_idx.npz`). Bez korekty położenia i bez przygaszania (niepewność wyraża
prawdopodobieństwo). Deterministyczne warstwy temp/wiatr/porywy/mgła/lód bez zmian. Do zrobienia: sprawdzalność szansy (czy 60% ≈ 6 na 10).

### Charakter dnia: przelotne / burzowe / stabilnie (2026-10-14)
Powód: 14.10 ulewa (39 dBZ) z komórek, które wyrosły na miejscu — radar 50 min wcześniej czysty. Przesuwanie obrazu nie przewiduje
powstawania chmur. `qbot_pogoda.charakter_dni()` — Open-Meteo CAPE + lifted index, godz. 8–20: przelotne gdy CAPE ≥ 150 J/kg i LI ≤ 1,5;
burzowe gdy CAPE ≥ 600 i LI ≤ −1 (kalibracja 11–16.10.2026: 14.10 CAPE 210 / LI 0,3; inne dni CAPE ≤ 80, LI ≥ 0,4). Okno godzin:
CAPE ≥ 100 i LI ≤ 2. API `/api/pogoda/charakter?lat=&lon=`; chip w ☂ pod „Opad — radar” (dziś i jutro, tylko gdy niestabilnie);
linia w `weather_now` (Albert). Progi do weryfikacji na kolejnych dniach.

### Warunki godzina po godzinie — wizualizacja (2026-10-14)
Zamiast 7 pasków kratek: `web/public/pogoda-punkt-viz.js` (`wxPointViz`) w języku Analizy trasy (`raport-pogoda-viz.js`, wspólne elementy
przez `window.wxVizKit`): kafelki (temperatura/odczuwalna, niebo, wiatr/porywy, deszcz mm + szansa, „Uwaga” tylko przy mgle/lodzie/błocie),
ikony nieba (noc: księżyc, `is_day`), temperatura + odczuwalna na tle stref ubioru, słupki szansy deszczu z zespołu, strzałki wiatru
(dokąd wieje, kolor wg porywów 8/13 m/s), ikonki ryzyka na drodze. `conditions_point` dostał `chmury`, `dzien`, `szansa` (zespół).
NAPRAWA: commit b8ba5d4 (godzina opadu) przypadkowo wyciął pole `wiatr` z wiersza (komentarz w środku linii) — Okno jazdy i Warunki
liczyły bez średniego wiatru od b8ba5d4 do tej poprawki.
