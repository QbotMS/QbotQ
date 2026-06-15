# Krok 3c: rozstrzygniecie mechanizmu `write` przed implementacja

## Zadanie 1 - struktura rejestracji

`route_poi_analyze` ma w registry standardowy dict z polami:
- `callable`
- `category`
- `description`
- `args_schema`
- `safety`
- `mode`
- `status`
- `notes`

Kontekst:
- `qbot3/tool_registry.py:1951-1980`

## Zadanie 2 - jak budowane jest `_WRITE_TOOLS`

`_WRITE_TOOLS` jest budowane dynamicznie w `_init_registry()`:
- `qbot3/tool_registry.py:2467-2474`
- jesli `spec.get("safety") == "write"` -> narzedzie trafia do `_WRITE_TOOLS`
- inaczej trafia do `_READ_ONLY_TOOLS`

`agent_runtime.py` potem robi:
- `write_tools = list_write_tools()`
- `if tool_name in write_tools: return {"status": "WRITE_DRAFT", ...}`

Kontekst:
- `qbot3/agent_runtime.py:98-117`

## Zadanie 3 - lista obecnych write-tools

Runtime lista write-tools zawiera aktualnie 10 narzedzi:
- `nutrition_log_add`
- `nutrition_log_delete`
- `nutrition_log_correct`
- `garmin_workout_create`
- `calendar_event_add`
- `reminder_add`
- `planning_fact_add`
- `memory_confirmed_fact_add`
- `route_poi_analyze`
- `rwgps_route_import_gpx`

Kontekst:
- `qbot3/tool_registry.py:2440-2474`

## Zadanie 4 - rozstrzygniecie sprzecznosci

Runtime dowod:
- `lookup('route_poi_analyze')`:
  - `safety: write`
  - `mode: write`
  - `status: implemented`
- `list_write_tools()` zawiera `route_poi_analyze`
- `orchestrate_query("poi etapu 2")` z `QBOT3_ENABLED=1` nadal zwraca:
  - `status: draft`
  - `action_draft.action_type: route_poi_analyze`
  - kazdy `tool_result` ma `status: WRITE_DRAFT`

Wniosek:
- Sprzecznosc byla tylko w poprzednim opisie listy write-tools.
- `route_poi_analyze` faktycznie jest write-tool.
- `WRITE_DRAFT` pochodzi z `agent_runtime`, nie z `route_analyzer`.

## Co faktycznie robi `route_poi_analyze`

Sam analyzer zwraca:
- `status: OK`
- `status: PARTIAL`
- pelne dane analizy:
  - `chunks`
  - `missing_chunks`
  - `summary`
  - `hard_resupply`
  - `soft_food_stop`
  - `water`
  - `attractions`

To pokazuje, ze `route_poi_analyze` jest analityczny, ale runtime traktuje go jako write-draft, bo jest zarejestrowany jako `safety: write`.

## Plan implementacji `route_poi_analyze_readonly`

1. Dodac nowy loader `_load_route_poi_analyze_readonly_tool` w `qbot3/tool_registry.py`.
2. Zmienic w kopii:
   - `safety: "read"`
   - `mode: "read_only"`
   - description musi jawnie kierowac Alberta do read-only uzycia dla zapytan informacyjnych
3. Zarejestrowac loader w `_init_registry()` obok `route_poi_analyze`.
4. Zostawic oryginalny `route_poi_analyze` jako write-path do zapisow/aktualizacji raportu.
5. Po implementacji sprawdzic:
   - `route_poi_analyze_readonly` trafia do `_READ_ONLY_TOOLS`
   - `route_poi_analyze` zostaje w `_WRITE_TOOLS`
   - `orchestrate_query("poi etapu 2")` musi zaczac wybierac read-only wariant, inaczej problemem bedzie jeszcze prompt/description, a nie sama rejestracja

## Kluczowy wniosek

Zmiana jest izolowana po stronie registry.
To nie wymaga zmiany analyzera ani `agent_runtime`, tylko poprawnej drugiej rejestracji z `safety: read`.
