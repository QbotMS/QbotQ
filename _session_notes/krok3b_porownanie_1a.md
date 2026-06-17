## Profil etapu 7 - WYNIK: ROWNOWAZNE ✅

core.planner i Albert (tool `stage_gpx_analyze` / `route_profile`) daja identyczny wynik:
- `distance_km=54.953`
- `elevation_gain_m=851.8`
- `sanity_check.ok=true`
- `route_id=55567991`

Referencja `57.586 km` byla nieaktualna i odnosila sie do metadanych RWGPS API trasy planowanej, nie do GPX faktycznie przejechanej. Wynik `54.953 km / 851.8 m` jest prawidlowy i zgodny z sanity-checkiem. Czas baseline core.planner: `34.76 s`. Albert direct `orchestrate_query()` dla tego zapytania: `24.5 s`.

## POI etapu 2 - WYNIK: CORE.PLANNER ZEPSUTY, ALBERT (tool) DZIALA ⚠️

- core.planner (baseline `/mcp/`): `status=OK`, ale answer: "nie moze policzyc POI, bo dostep do GPX/geometry jest zablokowany".
  - `route_id=55444268`
  - czas: `29.83 s`
  - wniosek: core.planner ma wlasny bug dla tej intencji, niezalezny od Kroku 3b.
- Albert `orchestrate_query()`: `status=draft`, nie domyka sie w 1 wywolaniu.
  - wymaga dalszego zbadania, czy to kwestia petli/iteracji, czy realny problem dla tej klasy zapytan.
- Albert direct tool `route_poi_analyze`:
  - jako root: dziala i zwraca pelny wynik (`hard_resupply=9`, `soft_food_stop=23`, `water=20`, `attractions=53`).
  - jako `qbot`: `PermissionError` przy zapisie artefaktu.

### Zadanie 1 - permission bug

Sciezka z bledu:
- `/opt/qbot/artifacts/exports/rwgps/rwgps_55444268.gpx`

`find /opt/qbot/artifacts/projects/ -not -user qbot`:
- brak wynikow

Wniosek: aktualny blad zapisu dotyczy artefaktu eksportu GPX dla etapu 2, a nie katalogu `projects` (w tym przebiegu nie znaleziono tam obiektow spoza wlasciciela `qbot`).

## Wniosek ogolny dla 1a

- Profil etapu: Albert toolset jest rownowazny core.planner i gotowy do przełączenia w Kroku 3b/1b.
- POI: porownanie nierozstrzygniete na poziomie `orchestrate_query()`; core.planner jest juz zepsuty dla tej intencji, ale Albert direct tool dziala. Zanim zrobimy 1b dla tej intencji, trzeba zbadac multi-step w `orchestrate_query()` oraz naprawic permission bug.
- Pozostale `OPEN_DOMAIN_INTENTS` nie byly w tym przebiegu testowane.

## Rekomendacja dla 1b

- `rwgps_route_profile_sample`, `stage_gpx_analyze` - gotowe do przełączenia na Alberta.
- `route_poi_analyze` - wymaga dalszej diagnozy `orchestrate_query()` i osobnego fixu uprawnien przed przełączeniem.
- Pozostale intencje `OPEN_DOMAIN_INTENTS` - do osobnych testow porownawczych.
