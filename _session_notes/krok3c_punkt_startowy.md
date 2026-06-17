# Krok 3c: route_poi_analyze_readonly - punkt startowy

**Decyzja:** opcja 1a (`route_poi_analyze_readonly` w `tool_registry`), podjeta 2026-06-15 (`krok3b_decyzja_poi_readonly.md`).

## PIERWSZE ZADANIE TEJ SESJI

Zrozumiec dlaczego `_tool_qbot_route_poi_analyze` zwraca `status="WRITE_DRAFT"` mimo `safety_class="READ_ONLY"`.

1. Znajdz definicje `_tool_qbot_route_poi_analyze` w `qbot_route_tools.py` i przeczytaj cala funkcje.
2. Znajdz wszystkie miejsca, gdzie ta funkcja lub funkcje, ktore wywoluje, zwracaja `status="WRITE_DRAFT"`.
3. Rozstrzygnij jedna z dwoch hipotez:
   - H1: `WRITE_DRAFT` jest zwracane zawsze dla tego narzedzia, np. po skompletowaniu analizy i zapisaniu raportu.
   - H2: `WRITE_DRAFT` jest czescia logiki chunkingu (`retry_chunk_id` / `retry_mode` / `merge_artifact_ids`) i wymaga wieloetapowego przeplywu.

## Jesli H1

- Dodac w `qbot3/tool_registry.py` `route_poi_analyze_readonly` jako kopie `route_poi_analyze`, ale z mapowaniem poprawnego wyniku na `status="OK"` przed zwrotem do Alberta.
- Albert ma uzywac tego narzedzia dla zapytan informacyjnych o POI.
- Oryginalne `route_poi_analyze` pozostaje dla wariantu zapisu / aktualizacji raportu.
- Walidacja: acceptance suite oraz smoke `poi etapu 2` przez `orchestrate_query` bez `draft`.

## Jesli H2

- Stop po Zadaniu 1.
- Opisac mechanike chunkingu.
- Nie implementowac w tej sesji bez osobnej decyzji projektowej.

## Audyt pozostalych WRITE_DRAFT

Po rozstrzygnieciu H1/H2 dla POI:
- `memory_confirmed_fact_add`
- `planning_fact_add`
- `garmin_workout_create`
- `rwgps_route_import_gpx`

Dla kazdego sprawdzic, czy `WRITE_DRAFT` jest zamierzone i czy ma sens jako write flow.

## Po POI

Krok 3b/1b: przelaczenie Router v2 dla OPEN_DOMAIN_INTENTS:
- profil etapu
- POI przez `route_poi_analyze_readonly`

Pozostale intencje:
- `rwgps_route_find`
- `route_climbs`
- `route_surface`
- `route_feasibility`
- `rwgps_recent_routes`

Te testowac osobno, analogicznie do 1a.
