# route_time_estimate v2 — model czasu przejazdu

> Dokumentacja narzędzia. Stan: 2026-06-30. Kod: `qbot_route_time_tools.py`
> (funkcja `estimate_route_time_v2` + wrapper `_tool_route_time_estimate`).
> Wpięcie: `qbot3/tool_registry.py` (`_load_route_time_estimate_tool`),
> prompt: `qbot3/llm/albert.py` (instrukcja route_time). Stary B4: `archive/qbot_route_time_tools.B4.*.py`.

## 1. Po co to jest (problem)
Stary model (B4) liczył czas jako `dystans / średnia_prędkość_z_10_jazd`. Wady udowodnione:
- `duration_s` w bazie to czas **ruchu** → B4 **całkowicie ignorował postoje**;
- mieszał asfalt, szuter, podjazdy i zjazdy w **jedną średnią** → na pagórkowatej/szutrowej trasie mylił się systematycznie;
- podawał jedną liczbę z fałszywą pewnością.

v2 liczy **prędkość ruchu per segment** (nawierzchnia × nachylenie) + **osobny model stopów**, i podaje **czas ruchu oraz całkowity osobno** wraz z profilem czasu zegarowego.

## 2. Jak działa

### 2.1 Prędkość ruchu — empiryczna tabela
Prędkość moving brana z tabeli **nawierzchnia × kubełek nachylenia** (`SPEED_TABLE` w kodzie).
- Nachylenie: **grade wygładzony oknem 200 m** (spójnie z kalibracją; `route_elevation_engine.smooth_elevation(200)`).
- Nawierzchnia: **binarna** utwardzona/nieutwardzona (mapowanie w `surface_class`); „nieznana" = błąd Overpass, liczona jako średnia obu.
- **Poziom** = percentyl wg trybu (to samo źródło, różne percentyle):
  - `normalny` (domyślny) = **mediana** — nieobciążony,
  - `sport` = asfalt p75 / szuter mediana,
  - `wyscig` = asfalt p90 / szuter p75.

Źródło: **7 jazd referencyjnych** (~128 tys. sekund 1 Hz, jazdy >70 km z ostatnich 3 mies.), prędkość z `activity_record`, dopasowanie sekunda→trasa **po pozycji (lat/lon)**, nawierzchnia z `route_surface_engine`, grade z `route_elevation_engine`.

### 2.2 Stopy
- **Mikro (<2 min)**: `0.22 min/km`, rozsiane proporcjonalnie (auto).
- **Krótkie (2–20 min)**: `~dystans/9 × 4.5 min` (auto).
- **Długie (≥20 min, obiad/zwiedzanie)**: **WKŁAD UŻYTKOWNIKA** — `planned_long_stops` (liczba) + `planned_long_stop_min` (łączny czas). NIE są zgadywane.

Dowód, że długich NIE da się przewidzieć z trasy (95 jazd >50 km): przy tym samym dystansie/czasie ruchu liczba obiadów wahała się **0–3** (Suchedniów 106 km/5 h → 0; Castagneto 90 km/5,2 h → 3). To decyzja „planu dnia", nie własność trasy.

### 2.3 Wyjście
- `moving_h`, `total_h` — **osobno**,
- `stops` — rozbicie (mikro/krótkie/długie),
- `profile` — profil czasu zegarowego per segment (km, grade, nawierzchnia, v_kmh, ETA jeśli podano `start_time`),
- `analysis` — tekst dla raportu/Alberta, `warning` — np. % nieznanej nawierzchni.

## 3. Dlaczego takie decyzje (z dowodów)
- **Mediana, nie p75**, jako domyślny poziom: p75 zawyżał prędkość → systematyczny bias −12% („mówi 5 h, jedziesz 7 h"). Mediana: bias ~0, błąd symetryczny.
- **Grade po pozycji, nie po liczniku**: dopasowanie po odometrze skaziło zjazdy (artefakt: szuter w dół „14 km/h"); po pozycji zjazdy wychodzą realnie szybkie (~25 km/h).
- **Długie postoje = użytkownik**: patrz 2.2.
- **„Nieznana" nawierzchnia = błąd Overpass**, nie kategoria modelu.
- **Wiatr/pogoda poza modelem** — liczy moduł meteo (bierze prędkość per segment stąd); inaczej dublowalibyśmy karę.

## 4. Kontrakt (wejście/wyjście)
```
estimate_route_time_v2(route_id, mode="normalny",
                       planned_long_stops=0, planned_long_stop_min=0.0,
                       start_time=None, segments=None) -> dict
```
- `route_id` — wymagane (czyta segmenty z bazy); albo `segments` wprost (testy/analizator).
- `mode` — `normalny`/`sport`/`wyscig`.
- `start_time` — `HH:MM` lub ISO (dla ETA).
- brak danych kanonicznych → `status=NEEDS_INPUT` (BEZ fallbacku — stary B4 wywalony).

## 5. Dokładność
Część toczna (ruch + mikro + krótkie): **nieobciążona, ~±15%** (na 6 h ≈ ±50 min). Długie postoje wg deklaracji użytkownika. Walidacja in-sample (7 jazd, mediana + użytkownik długie): suma total −6%, 5/7 jazd w ±15%.

## 6. Źródła danych
- `qbot_v2.activity_record` — 1 Hz (prędkość, pozycja, wysokość, moc, temp) — baza kalibracji.
- `qbot_v2.route_frames` — segmenty zaplanowanej trasy (nawierzchnia + wysokości; grade 200 m przeliczany).
- `qbot_v2.route_elevation_samples` — DEM 50 m + wygładzanie 200 m (kanon przewyższeń; preferowane źródło docelowe).
- `qbot_v2.route_surface_segments` — kanon nawierzchni.
- Artefakty kalibracji: `/opt/qbot/artifacts/analysis/exec_elev_*.json`, `exec_surface_segments.json`.

## 7. Ograniczenia i TODO
- **Resolver** czyta dziś `route_frames` (grade przeliczany 200 m). Do weryfikacji przy docelowym schemacie uploadu „nowych zasad"; jeśli kanon to `route_elevation_samples`, przełączyć źródło w `_load_route_segments`.
- **Overpass / nieznana nawierzchnia** — osobny problem jakości (część tras ma dużo „nieznana").
- **Rekalibracja**: tabela wygenerowana z danych; automat rekalibracji (okno 30 dni) — TODO.
- **Wpięcie w `route_analysis_run`** (ETA per segment do raportu/meteo) — TODO.

## 8. Zasady spójności (wiążące)
- Grade liczony **oknem 200 m** — tym samym, co kalibracja.
- Czas RUCHU i CAŁKOWITY zawsze **osobno**.
- Każda zmiana narzędzia = **aktualizacja promptu Alberta** w tym samym kroku (zrobione przy wpięciu v2).
- Wiatr w m/s; pogoda poza tym modelem.

## 9. Jak rekalibrować tabelę prędkości
Tabela `SPEED_TABLE` powstaje z danych: dla jazd referencyjnych zebrać (prędkość × nawierzchnia × grade 200 m, dopasowanie po pozycji), policzyć percentyle per nawierzchnia×kubełek, scalić podjazdy ≥6% (paved+unpaved), wygładzić cienkie strome zjazdy asfaltu, wstawić wartości dla trybów (mediana / p75 / p90). Po zmianie tabeli — zweryfikować na jazdach referencyjnych (czas ruchu vs realny `duration_s`).
