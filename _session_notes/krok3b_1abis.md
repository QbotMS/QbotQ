# Krok 3b/1a-bis: permission fix + diagnoza `route_poi_analyze` `WRITE_DRAFT`

## A. Permission fix (WYKONANE)

Naprawiono ownership (`root:root` -> `qbot:qbot`) dla plikow blokujacych zapis procesu qbot. To ten sam wzorzec co znana lekcja z memory (`/opt/qbot/artifacts/projects/ ... chown qbot:qbot`), tutaj w innych katalogach:

`exports/rwgps/`:
- `rwgps_55256628.gpx`
- `rwgps_55257604.gpx`
- `rwgps_55395125.gpx`
- `rwgps_55444268.gpx`

`reports/`:
- `poi_analysis_55444268_00_85.md`
- `poi_analysis_55444268_00_85.json`

Weryfikacja: `find .../exports/rwgps/ -not -user qbot` i `find .../reports/ -not -user qbot` zwracaja pusto. `route_poi_analyze` jako `qbot` teraz dziala do konca, bez `PermissionError`.

## B. `route_poi_analyze` = `WRITE_DRAFT` - POTWIERDZONE

To nie jest blad LLM/promptu. Kod jednoznacznie klasyfikuje `route_poi_analyze` jako write-action:

- `qbot3/llm/albert.py`: traktuje status `WRITE_DRAFT` z wyniku narzedzia jako sygnal do zbudowania `action_draft`
- `qbot3/agent_runtime.py` ok. linii 276: `if action_draft: response["status"] = "draft"`
- `orchestrate_query("poi etapu 2")` zwraca:
  - `status: "draft"`
  - `tool_results[*].status: "WRITE_DRAFT"`
  - `action_draft.action_type: "route_poi_analyze"`
  - answer zawiera dopisek `_action_draft gotowy. Wykonaj qbot.action_execute z action_type='route_poi_analyze'._`

To jest swiadoma decyzja z Kroku 4 (`recent_updates`: `route_poi_analyze` jako jeden z "5 pozostalych WRITE_DRAFT" - stabilny, dwukrokowy flow).

## Wplyw na Krok 3b

Przelaczenie Router v2 dla `route_poi_analyze` (intent `OPEN_DOMAIN`) na Alberta daloby inna semantyke niz dzisiejszy `core.planner`:

- `core.planner`: zwraca wynik analizy POI bezposrednio, gdy dziala
- Albert: zwraca draft i wymaga dodatkowego `qbot.action_execute`, zeby dostac wynik

To nie znaczy, ze Albert jest gorszy. To sa dwa rozne kontrakty: `read-result` vs `propose-then-confirm`. Otwarte pytanie UX dla GPT/user-facing: czy dwukrokowy flow dla "pokaz mi POI etapu 2" jest akceptowalny, czy `route_poi_analyze` powinno miec inna sciezke w Albercie dla czysto read-only zapytan.

## Status decyzji dla 1b

- `profil etapu` (`rwgps_route_profile_sample` / `stage_gpx_analyze`): rownowazne, gotowe do przełączenia w 1b
- `route_poi_analyze`: wymaga decyzji architektonicznej przed przelaczeniem:
  - (a) zaakceptowac draft-flow jako nowy standard
  - (b) dodac wariant read-only albo flage kontekstowa w tool_registry
  - (c) zostawic `route_poi_analyze` na `core.planner`, a inne intencje `OPEN_DOMAIN` przelaczyc osobno

## Pozostale nieprzetestowane intencje `OPEN_DOMAIN_INTENTS`

`rwgps_route_find`, `route_climbs`, `route_surface`, `route_feasibility`, `rwgps_recent_routes` - bez zmian od 1a, wciaz nieprzetestowane.
