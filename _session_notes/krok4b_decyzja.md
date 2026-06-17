# Krok 4b decyzja

Data: 2026-06-15

## Decyzja
- Wybieram Opcję B.
- `qbot.action_execute` pozostaje w `tools/list`.

## Uzasadnienie
- Po tej sesji realne handlery mają:
  - `nutrition_log_add`
  - `nutrition_log_delete`
  - `nutrition_log_correct`
  - `calendar_event_add`
  - `reminder_add`
- Nadal istnieje 5 write tools na `WRITE_DRAFT`:
  - `memory_confirmed_fact_add`
  - `planning_fact_add`
  - `garmin_workout_create`
  - `route_poi_analyze`
  - `rwgps_route_import_gpx`
- To są nadal naturalne lub techniczne write-intenty, więc usunięcie `qbot.action_execute` z `tools/list` byłoby zbyt agresywne i mogłoby zostawić GPT bez ścieżki wykonania dla tych operacji.
- Stan jest stabilny: najczęstsze write flow idą jednowywołaniowo przez Alberta, a reszta nadal ma bezpieczny dwukrokowy fallback.
