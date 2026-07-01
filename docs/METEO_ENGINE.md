# METEO ENGINE — dokumentacja narzędzia (kontrakt)

> Pełna dokumentacja silnika METEO trasy. Stan: 2026-07-01, **gotowe i przetestowane**.
> Plik silnika: `qbot3/routes/route_meteo_engine.py`. Kontekst/decyzje projektu: `docs/PROJEKT_METEO.md`.
> Konwencja: po polsku, wiatr w m/s, temperatury °C, czasy lokalne (Europe/Warsaw). „Bez dowodu nie ma sukcesu".

## 1. Po co to jest
Jeden silnik liczy dla trasy w momencie przejazdu (ETA z modelu czasu) cztery zagrożenia pogodowe naraz,
z jednego przebiegu, jako jedno spójne źródło danych. Zamiast osobnych, sklejanych w izolacji sekcji —
jeden wynik z gotowymi alertami i osią czasu.

Cztery tryby (wszystkie aktywne):
- **UPAŁ** — WBGT (Liljegren) z cieniem wpiętym w radiację, vs limit zależny od nachylenia (ACGIH).
- **DESZCZ** — opad per segment, moknięcie ciągłe, trend wjeżdżasz/wychodzisz.
- **BURZA** — kod burzy z prognozy = twarde NO-GO; inaczej gradacja z CAPE + porywy; przy realnej burzy
  fakty do decyzji (ile trwa, gdzie przeczekać). Bez werdyktu „jedź/nie jedź".
- **ODCZUWALNA (UTCI)** — całoroczna temperatura odczuwalna (ciepło i zimno) z temperatury promieniowania
  i wiatru efektywnego (otoczenie + pęd jazdy). Alerty tylko dla ZIMNA (ciepło pokrywa WBGT).

## 2. Status i granice
- **Gotowe, samodzielne, przetestowane** na trasie 55798129. Testy offline: `tests/test_route_meteo_engine.py`
  (10), `tests/test_route_utci.py` (4).
- **NIE wpięte** do `tool_registry.py` ani do promptu Alberta (`_SYSTEM`). To celowe — silnik jest wewnętrznym
  klockiem do konsumpcji przez raport. Jeśli kiedyś zostanie wystawiony jako narzędzie Alberta, obowiązuje twarda
  reguła: zmiana rejestru narzędzi = wpis w `_SYSTEM` w tym samym commicie.
- QBot OSTRZEGA i podaje fakty; nie jest reżyserem mocy (rozpiska mocy = QExt2/Karoo).

## 3. Jak wywołać
```
from qbot3.routes.route_meteo_engine import run_meteo_engine
res = run_meteo_engine(route_id, date_str, start_time="08:00", mode="normalny")
```
- `route_id` (str) — identyfikator trasy (np. "55798129").
- `date_str` (str) — data "YYYY-MM-DD".
- `start_time` (str) — godzina startu "HH:MM" czasu lokalnego (Europe/Warsaw).
- `mode` (str) — tryb modelu czasu (przekazywany do `estimate_route_time_v2`).

Silnik sam: woła `estimate_route_time_v2`, ładuje ramki/cień/miejscowości z `qbot_v2`, pobiera Open-Meteo
w kilku punktach wzdłuż trasy (sieć, ~3 s). **Woła się RAZ na raport** — wynik jest jednym źródłem, nie
przeliczaj per sekcja.

Uruchomienie w skrypcie: najpierw załaduj `/opt/qbot/app/.env.local` do `os.environ` (PGHOST/PGPORT/PGUSER/
PGDATABASE/PGPASSWORD), potem wywołaj silnik.

## 4. Źródło danych
Open-Meteo (darmowe, bez klucza) — jedyne z darmową radiacją krótkofalową (potrzebną do WBGT/Tmrt).
Pobierane godzinowo: temperatura, wilgotność, wiatr + kierunek, ciśnienie, radiacja (shortwave + direct),
opad + prawdopodobieństwo, kod pogody (WMO), CAPE, porywy. Wiatr w m/s, czas UTC. Horyzont ~+14 dni
(WBGT/burza degradują się szybciej niż sama temperatura — twarde okno ~3 dni, dalej trend).

## 5. Kontrakt wyjścia
`run_meteo_engine` zwraca dict. Przy błędzie: `{"status": "ERROR", "error": "<po polsku>"}` — pokaż, nie zgaduj.
Przy sukcesie `status == "OK"` oraz:

- `route_id, date, start, mode` — echo wejścia.
- `n_segments, n_windows` — liczba segmentów (≈890) i okien 30-min.
- `peak` — `{wbgt_eff, km, eta, alert_level, teren}` (szczyt WBGT).
- `alerts` — lista, posortowana po `eta_od` (potem NO-GO/ALARM/FLAGA). Pola wspólne:
  `typ` ("upał"/"deszcz"/"burza"/"zimno"), `severity` ("FLAGA"/"ALARM"/"NO-GO"),
  `km_od, km_do, eta_od, eta_do, minuty`. Pola specyficzne:
  - **upał**: `wbgt_max, alert_level, powod` (np. "podjazd, odkryte").
  - **deszcz**: `opad_max_mm, prawdopod, trend` ("narasta (wjeżdżasz…)" / "słabnie (wychodzisz…)").
  - **burza**: `kod_burzy` (bool), `cape_max, porywy_max_ms, trend, porywy_silne`;
    przy realnej burzy dodatkowo `czekanie_min` (ile trwa wg prognozy; może być `null` = trwa poza horyzont)
    i `przeczekaj_w` `{miejscowosc, km}` (najbliższa miejscowość przed strefą).
  - **zimno**: `utci_min, kategoria` (10-stopniowa skala UTCI), `uwaga_zjazd` (bool — chłód podbity wiatrem
    pozornym zjazdu / wartość poza zakresem modelu).
- `tabela_30min` — agregacja co 30 min, wiersz:
  `{okno, km_od, km_do, wbgt_max, alert_level, wiatr_wzdluz_ms, opad{mm,prob},
    burza{poziom,cape,porywy_ms}, odczuwalna{od,do,kat}}`.
  (`odczuwalna.od/do` = zakres UTCI w oknie; `kat` = kategoria najzimniejszego segmentu.)
- `per_segment` — 1 wpis/segment (pełna rozdzielczość, ~890): `km, eta, grade_pct, teren, surface,
  wbgt_eff, limit, exceed, tau, opad_mm, opad_prob, burza, cape, gust_ms, tmrt, utci, utci_kat,
  wind_eff_ms, wind_oob, wind_tail_ms, wind_cross_ms`.
- `caveats` — lista uczciwych zastrzeżeń (ACGIH zaklada aklimatyzację; WBGT liczony wiatrem otoczenia;
  burza = kod+CAPE, czas przybliżony, miejscowość = ogólne schronienie, decyzja użytkownika; UTCI = wiatr
  efektywny przycięty do 17 m/s z flagą, standardowy ubiór → wartość poglądowa). **Pokaż je w raporcie.**

## 6. Progi i definicje (regulowalne, stałe na górze pliku)
- **UPAŁ**: limit WBGT wg nachylenia — podjazd (>3%) 23°C / płasko 25°C / zjazd (<−3%) 28°C (ACGIH).
  Powaga z przekroczenia limitu × długość ciągłego okna (pasma 0–2/2–4/4–6/>6°C); poziom ekstremalny → ALARM od razu.
- **DESZCZ**: bramka moknięcia opad ≥0,5 mm i prawdopodobieństwo ≥40% (lub brak danych o prawd.).
  Powaga: ≥7,6 mm/h ALARM; ≥2,5 mm/h FLAGA/(≥90 min ALARM); ≥0,5 mm/h i ≥60 min FLAGA.
- **BURZA**: kod WMO 95/96/99 = NO-GO; CAPE ≥2500 ALARM, ≥1000 FLAGA; poryw ≥17 m/s podbija FLAGA→ALARM.
- **ODCZUWALNA/ZIMNO** (z UTCI): <−27°C ALARM od razu; <−13°C ALARM(≥15 min)/FLAGA; <0°C ALARM(≥60)/FLAGA(≥30);
  <9°C FLAGA(≥60 min). Wiatr efektywny = wiatr otoczenia (wektor vs kierunek jazdy) złożony z pędem jazdy
  (v_kmh z modelu czasu, prosto w twarz); zakres UTCI 0,5–17 m/s → przycięcie z flagą `wind_oob`
  (zwykle na szybkich zjazdach).

## 7. Zależności (moduły)
- `qbot_wbgt_tools.py`: `wbgt_liljegren_k`, `mean_radiant_temp_c` (Tmrt≈Tg z solvera kuli), `wbgt_level`,
  `cos_solar_zenith`, stałe. Solver Liljegren zweryfikowany bit-w-bit vs thermofeel.
- `qbot3/routes/route_utci.py`: `utci_c` (wielomian Bröde 2012, 210 wsp., rozłożony bit-w-bit z pythermalcomfort;
  ciśnienie pary kanoniczne `log(tk)` — poprawniejsze niż pythermalcomfort 4.0.2), `utci_category`, `utci_valid`.
- `qbot_route_time_tools.estimate_route_time_v2` (km/ETA/grade/surface/v_kmh per segment).
- `qbot3/routes/route_shade_resolver.segment_tau` (cień → fdir_eff).
- `tools/rwgps/route_weather._rel_wind` (składowa wzdłużna/boczna wiatru vs kierunek jazdy).
- Dane `qbot_v2`: `route_frames` (mid_lat/mid_lon), `route_shade_layer` + `route_axis_segments`,
  `route_poi_layer` (miejscowości).

## 8. Commity (jako qbot, bez push)
- `route_utci` — kalkulator UTCI + testy: `db2f625`.
- `qbot_wbgt_tools` — `mean_radiant_temp_c` (Tmrt): `8f8a906`.
- Silnik z trybami UPAŁ/DESZCZ/BURZA: `0b334e2`, `02ec5ae`, `db66ceb`, `428a17f`.
- Silnik + tryb ODCZUWALNA/UTCI + alerty zimna + kolumna odczuwalna + testy: `ebb7d40`.

## 9. Świadome ograniczenia (uczciwie)
- Wiatr pozorny jazdy stosowany TYLKO do UTCI, NIE do WBGT (WBGT liczony wiatrem otoczenia — zachowawczo).
- UTCI zakłada standardowy ubiór → bezwzględna liczba jest poglądowa, kierunek i wkład słońca/wiatru pewne.
- Cień = klasy WorldCover przy drodze (route_shade_layer) + azymut słońca. Cień od rzeźby terenu (DEM) — TODO
  (na płaskim Mazowszu ~0; istotne w górach). Patrz `docs/PROJEKT_METEO.md`.
- Prognoza: twarde okno ~3 dni; dalej trend z malejącą pewnością.

## 10. Weryfikacja (jak sprawdzić na żywo)
Trasa testowa 55798129 (~71 km, płaskie Mazowsze). Załaduj `.env.local`, wywołaj silnik, sprawdź realny wynik
(alerty + kilka wierszy tabeli + kolumna odczuwalna), nie deklaracje. Testy: `dev_run_tests tests.test_route_meteo_engine`
i `tests.test_route_utci`.
