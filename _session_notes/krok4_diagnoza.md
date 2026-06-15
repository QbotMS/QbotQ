# Krok 4 diagnoza

Data: 2026-06-15

## (a) Write tools z real handlerem w `_execute_single_tool`
- `nutrition_log_add`
- `nutrition_log_delete`
- `nutrition_log_correct`

## (b) Write tools nadal na `WRITE_DRAFT` w `_execute_single_tool`
- `calendar_event_add` - RYZYKO: wysokie; naturalna sesja GPT często prosi o dodanie wydarzenia lub przypomnienia, więc bez `action_execute` łatwo o ślepy zaułek.
- `garmin_workout_create` - RYZYKO: średnie; użytkownik może chcieć realnie utworzyć trening, ale to rzadszy flow niż kalendarz.
- `memory_confirmed_fact_add` - RYZYKO: wysokie; naturalne zapisy faktów/konfirmacji są częste i user-facing.
- `planning_fact_add` - RYZYKO: średnie/wysokie; pojawia się przy planowaniu i notatkach planistycznych.
- `reminder_add` - RYZYKO: wysokie; bardzo naturalna intencja użytkownika, często wyrażana zwykłym językiem.
- `route_poi_analyze` - RYZYKO: niskie/średnie; bardziej specjalistyczne, ale nadal user-facing przy analizie tras.
- `rwgps_route_import_gpx` - RYZYKO: niskie/średnie; import GPX jest techniczny, ale to realny write flow dla tras.

## Wniosek
- Lista (b) jest niepusta i zawiera kilka częstych, naturalnych write-intentów.
- Pełne usunięcie `qbot.action_execute` z `tools/list` jest teraz ryzykowne, bo dla części narzędzi Albert nadal kończy na `WRITE_DRAFT`.
- Zakres bezpieczny na tę sesję: tylko wąska zmiana tekstu `WRITE_DRAFT` w `_execute_single_tool`, bez usuwania `qbot.action_execute` z `tools/list`.

## GPT instructions
- W `/opt/qbot/app` nie znalazłem pliku `*GPT_INSTRUKCJE*` ani równoważnego pliku instrukcji do aktualizacji.
- Do ręcznego wklejenia w UI ChatGPT:
  - Używaj wyłącznie `qbot.query` jako głównego wejścia.
  - Albert sam rozpoznaje intent, wykonuje odczyty i finalizuje obsługę zapisów tam, gdzie ma realne handlery.
  - Nie zakładaj dwukrokowego flow z `qbot.action_execute` jako wymogu dla użytkownika.
  - Jeśli odpowiedź wskazuje na brak wsparcia, podaj to wprost zamiast odsyłać do narzędzia niedostępnego w schemacie.
