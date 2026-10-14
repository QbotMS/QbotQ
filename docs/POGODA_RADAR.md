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
