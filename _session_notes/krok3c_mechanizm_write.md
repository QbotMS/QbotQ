# Krok 3c: mechanizm `_WRITE_TOOLS` + plan implementacji `route_poi_analyze_readonly`

## Struktura rejestracji narzedzia

Definicja `_load_route_poi_analyze_tool()` zwraca dict z polami:
- `callable`
- `category`
- `description`
- `args_schema`
- `safety`
- `mode`
- `status`
- `notes`

Konkret:
- `qbot3/tool_registry.py:1951-1980`

## Jak budowane jest `_WRITE_TOOLS`

`_WRITE_TOOLS` jest budowane dynamicznie podczas `_init_registry()`:

- `qbot3/tool_registry.py:2467-2474`
- jesli `spec.get("safety") == "write"` -> narzedzie trafia do `_WRITE_TOOLS`
- w przeciwnym razie trafia do `_READ_ONLY_TOOLS`

`qbot3/agent_runtime.py` pobiera liste przez:
- `from qbot3.tool_registry import list_write_tools`
- `write_tools = list_write_tools()`
- `if tool_name in write_tools: return {"status": "WRITE_DRAFT", ...}`

## Co powoduje draft

`WRITE_DRAFT` nie pochodzi z `qbot_route_tools.py`.
Pochodzi z runtime:

- `qbot3/agent_runtime.py:100-117`

Albert potem sprawdza:
- `qbot3/llm/albert.py:381`
- jesli tool zwroci `WRITE_DRAFT`, model dostaje instrukcje draftowe
- `qbot3/agent_runtime.py:275-280` przepisuje response na `status="draft"`

## Lista obecnych write-tools

Z `tool_registry.py` obecnie trafia do `_WRITE_TOOLS`:
- `nutrition_log_add`
- `nutrition_log_delete`
- `nutrition_log_correct`
- `garmin_workout_create`
- `calendar_event_add`
- `reminder_add`
- `planning_fact_add`
- `memory_confirmed_fact_add`
- `rwgps_route_import_gpx`

## Plan implementacji `route_poi_analyze_readonly`

1. Dodac nowa funkcje `_load_route_poi_analyze_readonly_tool` w `qbot3/tool_registry.py`.
2. Zrobic kopie `_load_route_poi_analyze_tool`, ale ustawic:
   - `safety: "read"`
   - `mode: "read_only"` albo inny read-only odpowiednik zgodny z konwencja registry
3. Zmienic opis, zeby jasno prowadzil Alberta:
   - uzywac dla zapytan informacyjnych o POI
   - nie jest to write-path
   - ma zwracac wynik natychmiast
4. Zarejestrowac loader w `_init_registry()` pod nazwa:
   - `route_poi_analyze_readonly`
5. Weryfikacja po implementacji:
   - samo `safety: "read"` wystarczy, zeby narzedzie trafilo do `_READ_ONLY_TOOLS` i nie bylo traktowane jako write przez `agent_runtime`
   - ale description musi explicite prowadzic Alberta, bo beda dwa narzedzia o nakladajacym sie celu:
     - `route_poi_analyze`
     - `route_poi_analyze_readonly`
   - ryzyko: bez mocnego opisu model moze dalej wybierac write-wersje albo mylic przeznaczenie

## Wniosek

Zmiana jest izolowana po stronie registry:
- nie trzeba zmieniac analyzera
- nie trzeba zmieniac `agent_runtime`
- kluczowa jest poprawna rejestracja w registry jako `read`, a nie `write`
