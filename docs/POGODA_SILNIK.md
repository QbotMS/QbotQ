# Jeden silnik pogodowy QBota — spis i plan (E0, 2026-10-14)

**Decyzja Michała (14.10.2026): jeden silnik pogodowy dla wszystkich modułów.**

## Stan wyjściowy — 6 równoległych ścieżek
| Ścieżka | Pliki | Źródło / wybór modelu | Mocne strony |
|---|---|---|---|
| Pogoda (punkt) | `qbot_pogoda*.py`, `qbot_radar*.py`, `qbot_eps_verif.py` | Open-Meteo, **model wg sprawdzalności (IMGW)** per parametr × doba; zespół ICON-EU-EPS; radar OPERA; mapy ICON-EU (DWD) | radar + ostrzeżenia, szansa z 40 wariantów, warunki drogi (lód, mgła, błoto, rosa), charakter dnia (CAPE/LI), weryfikacja |
| Silnik METEO tras (Analiza trasy, Planer) | `qbot3/routes/route_meteo_engine.py`, `route_weather_models.py`, `route_utci.py`, `ride_thermal.py`, `qbot_wbgt_tools.py`, `route_shade_*`, `route_climate.py`, `outfit_*` | Open-Meteo; **model = najdrobniejsza siatka sięgająca daty** + 6 modeli i rozrzut ECMWF ENS; ERA5 dla dat poza prognozą | UTCI (wiatr efektywny z pędem), „na rowerze” (kalibracja Karoo), WBGT Liljegren z cieniem (WorldCover), burze NO-GO, wiatr vs kierunek + osłona terenu, słońce/UV, klimat ERA5 |
| Trener | `qbot_trener_engine.py` (forecast, wx_bad), `qbot_trener_weather.py`, `qbot_trener_stats.py` | Open-Meteo (własne pobieranie) | okna jazdy, poranna korekta planu, progi z historii |
| Powiadomienia | `qbot_notif.live_weather` | Open-Meteo | — |
| Raport poranny / stare narzędzia | `event_morning_report.py`, `qbot_integration_tools.py`, `qbot_legacy_parity_tools.py`, `qbot_telegram_tools.py`, narzędzie Alberta `weather_forecast` | **OpenWeatherMap** | — |
| Planer: tabela modeli | `qbot_web.api_planer_pogoda`, `_pogoda_*` | przez silnik METEO tras | ocena zgodności modeli (Albert) |

## Znalezione i naprawione w E0
- **Godziny wartości „z poprzedniej godziny”** (Open-Meteo: opad, szansa opadu, porywy = przedział T−1..T):
  - silnik tras interpolował liniowo między pełnymi godzinami → opad ok. **30 min za wcześnie** (przejazd 14:30 dostawał pół deszczu z 13–14);
    teraz wartość godziny, w którą wypada przejazd (`_interval`, bez interpolacji) dla opadu, szansy opadu i porywów;
  - Pogoda: opad poprawiony wcześniej (b8ba5d4), porywy teraz też z T+1 dla godziny T..T+1.
  - Trener (sprawdzone i naprawione 14.10): `qbot_trener_engine.forecast` (okno 8–18 brało opad/szansę/porywy/kod z 7–17; z niego
    korzystają powiadomienia `live_weather`), `qbot_trener_weather.window_wx` (poranna korekta: godzina jazdy H..H+1 brała znacznik H),
    `qbot_trener_stats.weather_auto` (kalibracja progów z historii: opad/porywy w czasie jazd przesunięte o 1 h; przeliczy się przy
    najbliższym odświeżeniu cache `trainer_auto_cache.weather`).

## Plan
- **E1** — wydzielenie rdzenia (`qbot_wx`): pobieranie + cache + poprawne godziny + radar + zespół + ERA5; Pogoda pierwsza na rdzeniu.
- **E2** — silnik tras czyta dane z rdzenia (fizyka bez zmian); test zgodności stary/nowy na zapisanych trasach.
- **E3** — wspólna fizyka odczucia: UTCI + „na rowerze” + WBGT (lato) także dla punktu (Pogoda, Okno jazdy); warunki drogi i charakter dnia
  także dla tras. Jedna reguła wyboru modelu: sprawdzalność, a gdzie jej brak (zagranica, daleko w przód) — najdrobniejsza siatka + rozrzut.
- **E4** — Trener, powiadomienia, raport poranny, Albert na rdzeniu; usunięcie OpenWeatherMap.

## E1 — rdzeń danych `qbot_wx.py` (2026-10-14, część 1)
`qbot_wx`: `forecast()` (klient Open-Meteo /forecast, wiatr m/s, czas Europe/Warsaw, cache 10 min po pełnym zapytaniu), `PREV_HOUR`
(wielkości z godziny poprzedzającej: opad, deszcz, przelotne, śnieg, szansa opadu, porywy, kod pogody), `next_hour()` (wartość dla godziny
T..T+1), `ens_prob()` (szansa ≥ 0,2 mm/h z ICON-EU-EPS dla godziny HH..HH+1). Na rdzeniu: `qbot_pogoda.conditions_point`, `model_point`,
`charakter_dni`, `qbot_pogoda_okno._ens_prob`. Zgodność przed/po sprawdzona na żywo (identyczne wyniki). Test bez sieci:
`tests/test_pogoda_conditions.py`. Dalej: radar/mapy/ERA5 (część 2), silnik tras (E2), Trener i reszta (E4).

## E1 cz. 2 / E2 — wspólny transport (2026-10-14)
`qbot_wx.get_url(url, timeout, ttl, ua)` — jedyna droga do Open-Meteo (prognoza, archiwum ERA5, zespół, poprzednie przebiegi, geokodowanie;
inne adresy odrzucane), cache po pełnym adresie (prognoza 10 min, archiwum 1 doba). Przepięte BEZ zmiany parametrów zapytań
(test zgodności przed/po: identyczne): silnik tras `route_meteo_engine._fetch_point_raw`, `route_weather_models._get` (6 modeli + ECMWF ENS),
`route_climate._get` (klimat ERA5), `route_xss_phys` (klimat wiatru), Trener `forecast`, `qbot_trener_weather.hourly`, `qbot_trener_stats.weather_auto`.
Radar (`qbot_radar`) i mapy modelu (`qbot_pogoda_map`, DWD) są częścią silnika jako pojedyncze źródła (bez zmian).
Zostało poza rdzeniem (E4): `qbot_wbgt_tools`, `gear_kit`, `qbot_pogoda_verif` (Previous Runs), `qbot_web` (archiwum, l. ~3214),
`mcp_server`, `qbot_integration_tools`, OpenWeatherMap (raport poranny, stare narzędzia).

## E3 — jedna reguła modelu w silniku tras (2026-10-14, decyzja Michała po porównaniu na 3 trasach)
W `route_meteo_engine` (jedno miejsce dla Analizy trasy, Planera, raportu Alberta, raportu kanonicznego i raportu z jazdy):
1. brak modelu od wołającego → **model kanoniczny** (`canonical_model`, najdrobniejsza siatka sięgająca daty), nie `best_match`
   (wcześniej Planer liczył kanonem, a pozostałe moduły best_match — ta sama trasa miała różną pogodę);
2. **Polska i 1–3 dni:** temperatura/wilgotność, wiatr, porywy i ilość opadu z modeli wg sprawdzalności (`qbot_pogoda_verif.przydzial`),
   **szansa opadu z zespołu ICON-EU-EPS** (`qbot_wx.ens_prob`; pojedynczy model może nie podawać szansy — w porównaniu HARMONIE dało 0%
   zamiast 22%); promieniowanie, ciśnienie, chmury, CAPE i kod pogody z kanonu.
Pole `model` w wyniku opisuje źródło każdej wielkości. Klucze cache z sufiksem `e3`.
Porównanie przed wdrożeniem (jutro 10:00): różnice do ok. 1,3 °C (temp./odczuwalna), do 1,5 m/s (porywy), WBGT do −1 °C.

**Uzupełnianie braków kanonu (2026-10-14):** HARMONIE KNMI jako model kanoniczny nie podaje ciśnienia, CAPE ani szansy opadu → WBGT wychodził
NaN na całej trasie, a burze (CAPE) były niewykrywalne — błąd istniał w Planerze od wejścia HARMONIE do kanonu. `_fetch_point_raw` uzupełnia
każdą wielkość z brakami z `best_match`; pole `model` wymienia uzupełnione wielkości.

**Uzupełnianie braków kanonu (2026-10-14):** HARMONIE KNMI jako model kanoniczny nie podaje ciśnienia, CAPE ani szansy opadu → WBGT wychodził
NaN na całej trasie, a burze (CAPE) były niewykrywalne — błąd istniał w Planerze od wejścia HARMONIE do kanonu. `_fetch_point_raw` uzupełnia
każdą wielkość z brakami z `best_match`; pole `model` wymienia uzupełnione wielkości. Klucze cache punktów i tabeli cieplnej: sufiks `e3b`.

## E3.1 — odczucie dla punktu jak w silniku tras (2026-10-14)
`qbot_pogoda.conditions_point` → `_odczucie()`: **`odcz` = odczuwalna jak na trasie** (`apparent_temp_steadman` z temp. promieniowania — to samo co `per_segment.feels`), **`utci` = UTCI w jeździe** (`route_utci.utci_c`; temp. promieniowania z
`route_meteo_engine._thermal_solve` przy pełnym słońcu, wiatr efektywny = √(wiatr² + 5,6²) m/s, tj. pęd ~20 km/h), **`na_rowerze`** =
temp. do ubioru (`ride_thermal.route_delta` — kalibracja na czujniku Karoo — + `personal_offset` z „W czym jechałem”), **`wbgt`**.
Dawna odczuwalna Open-Meteo → `odcz_om`; Okno jazdy porównuje z progami Trenera właśnie ją (progi skalibrowane na niej — rekalibracja w E4).
Warunki (viz v2): kafel temperatury „na rowerze … · strefa ubioru · w jeździe od …”, linia przerywana = odczuwalna (jak na trasie), UTCI w jeździe w dymku, WBGT w dymku ≥ 18 °C.

## E3.2 — warunki drogi i charakter dnia na trasie (2026-10-14)
Jedna funkcja reguł drogi `qbot_pogoda.road_flags()` (oblodzenie 0–3, mgła, mokro/błoto, zapas rosy) — Pogoda (`conditions_point`, zgodność
przed/po identyczna) i silnik tras (`_road_at` dla każdego odcinka w chwili przejazdu; `_interp_n` — brak danych = None, nie 0). Nowe pola
`per_segment`: `lod`, `mgla`, `nawierzchnia`; alerty `oblodzenie` (FLAGA/ALARM), `mgla`, `bloto` w tym samym formacie co deszcz/burza
(Analiza trasy, Planer, Albert pokazują je bez zmian stron); `charakter` dnia (`charakter_dni`, CAPE + lifted index) w wyniku + alert
(FLAGA przelotne / ALARM burzowy) dla jazd dziś–pojutrze. Pobierane dodatkowo: punkt rosy, widoczność, temp. gruntu, śnieg. Cache `e3c`.

## E4.1 — Trener na wspólnym silniku (2026-10-14, decyzja Michała po porównaniu progów na 370 jazdach)
- `qbot_pogoda.odczucie_calc()` — JEDNA funkcja odczucia (odczuwalna jak trasa, UTCI w jeździe, WBGT) dla Pogody, historii jazd Trenera i Trenera.
- `qbot_trener_engine.forecast` (plan tygodnia + powiadomienia) i `qbot_trener_weather.hourly` (poranna korekta) budowane z
  `qbot_pogoda.conditions_point` (modele wg sprawdzalności, poprawne godziny, szansa z zespołu). `hourly` zachowuje surowy format
  Open-Meteo (gust/rain/prob = godzina poprzedzająca → wiersz T−1), więc `window_wx` i testy bez zmian. Do warunków doszła `pokrywa_cm`.
- Progi z historii (`qbot_trener_stats._weather_rides` → `_feels_hours`): nowa odczuwalna dla godzin jazd (ERA5: temp., wilgotność, wiatr,
  ciśnienie, promieniowanie). Porównanie 370 jazd: chłód długa 0 → −1 °C, upał 32 → 33 °C, reszta bez zmian. Cache progów przeliczony po wdrożeniu.
- Okno jazdy porównuje progi z nową odczuwalną (`odcz`); `odcz_om` zostaje tylko informacyjnie.

## E4.2 — Albert „pogoda w mieście X” na wspólnym silniku (2026-10-14)
`weather_forecast` (tool_registry) → `qbot_pogoda_albert.weather_city`: geokodowanie Open-Meteo przez `qbot_wx.get_url` (pierwszeństwo PL),
dalej `conditions_point` (najbliższe godziny) / `conditions_day` (jutro…+4, godz. 6–22, pewność); odczuwalna, „na rowerze”, szansa z zespołu,
warunki drogi, charakter dnia. Wpis w `_SYSTEM` Alberta. Zaproszenia gości: przed zmianą silnika sprawdzone — 0 aktywnych, brak ryzyka
fałszywych maili. Usunięty martwy `event_morning_report.py` (OpenWeatherMap; brak timera, crona i importów; kopia w artifacts).

## E4.2 krok 3 — stare narzędzia pogody na wspólnym silniku (2026-10-14)
`qbot_integration_tools`: `_tool_qbot_weather_current`, `_tool_qbot_weather_daily_report` (z niego korzysta `_tool_qbot_weather_forecast`)
i `_tool_qbot_weather_config_status` przepisane na `qbot_pogoda` (+ `_core_point`: lat/lon → geokodowanie → resolver lokalizacji QBota),
TE SAME POLA co wcześniej (+ `na_rowerze_c`, `gusts_mps`); opis warunków z kodu WMO po polsku. Usunięte (decyzja Michała — artefakt z początków
QBota, crony zakomentowane, ostatni log 28.06.2026): `daily_report.py`, `daily_report_adapter.py` (kopie w artifacts). Testy OWM w
`test_qbot3_acceptance.py` zastąpione `PogodaWspolnySilnik` (format na atrapie rdzenia, bez sieci).

## E4.3 — koniec OpenWeatherMap (2026-10-14)
- `tools/rwgps/route_weather.py` (Planer → Wyposażenie → pogoda, pogoda per pudełko w `qbot_route_tools`): tylko Open-Meteo przez `qbot_wx.get_url`;
  usunięte `_owm_key`, `_fetch_owm`, `OWM_URL`. **Poprawka godziny opadu** w `_fetch_open_meteo` (klucz godziny H = opad H..H+1, wartość z H+1) —
  dotyczy też raportu z jazdy (`ride_report_builder` korzysta z tej funkcji).
- `tools/feasibility.py` (`get_weather`): pogoda startu z `qbot_pogoda.conditions_point`, pola bez zmian.
- `qbot_config`: usunięte `WEATHER_API_KEY_NAMES`, `OPENWEATHERMAP_API_KEY`; martwe `_owm_*` w `qbot_integration_tools`; opisy (Telegram, router,
  rejestr v1, query_handler, qbot_web, Albert) bez OWM; usunięty ostatni test OWM. Zmienne środowiskowe OWM (jeśli są w .env) nic już nie robią.

## E4.4 — ostatnie ścieżki na wspólny transport (2026-10-14)
`qbot_wx.get_url`: `qbot_wbgt_tools._fetch_openmeteo` (WBGT, zgodność przed/po identyczna), `gear_kit` (zestaw na deszcz: opad i widoczność 7 dni),
`qbot_pogoda_verif._get` (tylko adresy Open-Meteo; archiwa IMGW bez zmian), archiwum opadu w `qbot_web` (suma przed jazdą).
Celowo poza rdzeniem: test łączności w `_tool_qbot_public_web_status` (pinguje Open-Meteo bezpośrednio). Stan: wszystkie moduły QBota biorą
pogodę z jednego silnika (rdzeń `qbot_wx` + `qbot_pogoda` + silnik tras), OpenWeatherMap usunięty.

## E4.5 — ostatnie własne pobieranie Open-Meteo (2026-10-14)
`qbot_pogoda_okno._get_json` (wschód/zachód słońca), `tools/rwgps/ride_verdict._fetch_hourly` (werdykt pogodowy po jeździe; + poprawka godziny opadu:
klucz H = opad H..H+1) i `mcp_server.py` (`get_weather`, ciśnienie w raporcie) — przez `qbot_wx.get_url` (w `mcp_server` pomocnik `_om_get` z interfejsem
httpx: `.json()`, `.raise_for_status()`). Poza rdzeniem celowo: test łączności `_tool_qbot_public_web_status`, archiwa IMGW w `qbot_pogoda_verif`.
