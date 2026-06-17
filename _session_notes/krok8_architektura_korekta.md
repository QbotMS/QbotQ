# Korekta architektury: `core/planner.py` wciąż żywy dla domeny tras

**Data:** 2026-06-15
**Status:** `core/planner.py` NIE jest do usunięcia. `QBOT_ARCHITEKTURA_V2.md` sekcja 8 (`core/planner.py → DO USUNIĘCIA`) jest NIEAKTUALNA dla domeny tras i wymaga korekty w dokumencie projektowym poza repo, zarządzanym przez użytkownika w Claude Project. Ta notatka jest źródłem faktów dla tej korekty.

## Co jest faktycznie żywe

1. **Router v2** (`qbot_query_handler.py`, okolice linii 4838-4876): dla `intent` w `OPEN_DOMAIN_INTENTS` (`qbot_query_handler.py:555`, m.in. `rwgps_route_find`, `rwgps_route_profile_sample`, `route_poi_analyze`, `route_climbs`, `route_feasibility`, `rwgps_recent_routes` i inne) wykonuje:
   - `from core.planner import plan_routes`
   - `plan_routes(question=question)`
   - `return`
   Albert (`qbot3`) nie jest w tej ścieżce.

2. **`qbot_mcp_adapter.py`** (`~654-690`): drugi call site, gdzie przy `QBOT_QUERY_VNEXT_ENABLED=1`, `handle_query(...) == UNRECOGNIZED` i `is_route_domain_query(query)=True` kod również robi:
   - `from core.planner import plan_routes`
   - `plan_routes(query)`

3. **Runtime proof**: monkeypatch `core.planner.plan_routes` podczas `handle_mcp_request("profil etapu 3")` pokazał, że wrapper jest realnie wywoływany i jego wynik trafia do `structuredContent`.

## Co to znaczy dla "Albert-first"

Albert (`qbot3/agent_runtime.py`) ma kompletny toolset route. To jest poprawne i potwierdzone.

Jednak dla zapytań, które Router v2 klasyfikuje jako open-domain, `core/planner.py` odpowiada pierwszy i zwraca wynik. W praktyce Albert-first obowiązuje dla zapytań, które Router v2 nie klasyfikuje jako otwartą domenę, oraz dla `UNRECOGNIZED` bez route-keywords.

Dla typowych zapytań o trasy, takich jak:
- `profil etapu 3`
- `pokaż moje ostatnie trasy z RWGPS`
- `nawierzchnia trasy etap 2`

to nadal `core/planner.py` jest ścieżką aktywną.

## TODO - osobna, większa sesja

**Tytuł:** Dokończenie Kroku 3 dla domeny tras - przekierowanie `OPEN_DOMAIN_INTENTS` z `core/planner.py` do qbot3 Albert

Zakres na przyszłą sesję:

1. Test porównawczy dla reprezentatywnych intencji, np. `rwgps_route_profile_sample` i `route_poi_analyze`, aby sprawdzić równoważność wyniku Albert vs `core.planner.plan_routes()`.
2. Jeśli wyniki są akceptowalne, zmienić Router v2 w `qbot_query_handler.py`, aby dla `OPEN_DOMAIN_INTENTS` wołał Alberta zamiast `core.planner`.
3. Zaktualizować `qbot_mcp_adapter.py` analogicznie albo usunąć tę ścieżkę, jeśli Router v2 przestanie zwracać `UNRECOGNIZED` dla route queries.
4. Dopiero po pełnej weryfikacji end-to-end uznać `core/planner.py` za martwy i usuwać go bez regresji.
5. Zaktualizować acceptance testy, które patchują `core.planner.*`, po zmianach routera.

## Ryzyko jeśli zignorowane

Jeżeli ktoś usunie `core/planner.py` na podstawie nieaktualnej sekcji architektury, popsuje to obsługę profilu etapu, RWGPS route find/recent, POI analysis, nawierzchni, climbs i feasibility dla większości zapytań route trafiających w Router v2. To będzie regresja funkcjonalna, nie crashloop.

## Pliki diagnozy z tej sesji

- `_session_notes/krok8_planner_osiagalnosc.md` nie istnieje w tej chwili.

