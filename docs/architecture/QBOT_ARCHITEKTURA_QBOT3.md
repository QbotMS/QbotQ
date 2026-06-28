# QBot — aktualna architektura QBot3

Stan ustalony na podstawie żywego VPS i kodu repo. Przy konflikcie między dokumentem a kodem wygrywa żywy system: kod, env, `tools/list`, logi i testy.

## Repo i usługi

- Repo: `/opt/qbot/app`
- Główne usługi: `qbot-api`, `qbot-mcp-bridge`, `qbot-dev-mcp`, `qbot-qlab-server`
- QExt2 jest osobnym projektem i nie jest częścią tego kanonu.

## Publiczny MCP

Aktywny publiczny handler MCP dla QBot3:

```text
qbot3/adapters/mcp_adapter.py
```

Aktualne publiczne `tools/list` wystawia:

```text
qbot_query
```

`qbot.action_execute` nadal istnieje w kodzie jako backend/legacy/admin/internal path, ale nie jest aktualnie publicznie listowany przez `tools/list`.

## Flow `qbot_query`

```text
qbot_query
→ qbot3/adapters/mcp_adapter.py
→ jeśli QBOT_QUERY_VNEXT_ENABLED=1:
   → qbot_query_handler.handle_query()
   → jeśli UNRECOGNIZED / ACTION_REQUIRED / error:
      → qbot3.agent_runtime.orchestrate_query()
→ jeśli QBOT_QUERY_VNEXT_ENABLED!=1:
   → qbot3.agent_runtime.orchestrate_query()
```

Produkcja ma `QBOT_QUERY_VNEXT_ENABLED=1`, więc nie zakładaj czystego Albert-only flow.

## Albert / QBot3 runtime

Główne pliki:

```text
qbot3/agent_runtime.py
qbot3/llm/albert.py
qbot3/tool_registry.py
qbot3/adapters/mcp_adapter.py
qbot3/safety.py
qbot3/write_router.py
```

Albert wykonuje tool-calling i może finalizować realne zapisy po stronie serwera przez dopuszczone write tools.

## Trasy

Nie istnieje aktualny `core/planner.py`.

Nie opisuj domeny tras jako obsługiwanej przez Planner v2. Aktualna obsługa tras idzie przez QBot3/Albert/tool registry oraz narzędzia trasowe, m.in. analiza planowanej trasy, profil szczegółowy, nawierzchnia, POI i analiza wykonanej jazdy/FIT.

### Nawierzchnia gravelowa — decyzja 2026-06-28

Głównym silnikiem nawierzchni jest `tools/rwgps/route_surface_engine.py` (`route_surface_engine_v1`): analiza po rzeczywistym śladzie GPX/TCX/JSON/RWGPS, nie po `route_frames`.

Parametry produkcyjne: surface sample 50 m, Overpass corridor 50/80 m, confidence match distance 25/50/80 m. Match 150 m nie jest normalnym źródłem surface, tylko debug/fallback z ostrzeżeniem.

Overpass fallback 2026-06-28: default global endpoints dla Polski to `overpass-api.de`, `overpass.private.coffee`, `maps.mail.ru/osm/tools/overpass`; można nadpisać przez `QBOT_OVERPASS_ENDPOINTS`. Produkcyjny default to `first_success`: chunk zatrzymuje się na pierwszym HTTP 200. Silnik fail-open raportuje `overpass_metrics.mode` i `quality_status`. Regionalne endpointy nie są defaultem.

Diagnostyka mirrorów: `QBOT_OVERPASS_PROBE_ALL=1` albo `analyze_route_surface(..., overpass_probe_all=True)` włącza tryb `probe_all`. Ten tryb odpytuje każdy endpoint dla każdego chunka i zapisuje `overpass_probe.endpoint_comparison`; nie używać jako defaultu runtime.

Metryki jakości 2026-06-28: wynik rozdziela jawne tagi OSM `surface` od inferencji. JSON zawiera `tagged_surface_pct`, `inferred_surface_pct`, `unknown_surface_pct`, `inference_sources_pct`, `inference_sources_m` oraz `problem_segments`. Segmenty mają `classification_source`, a `quality_status` rozróżnia `GOOD_TAGGED` i `GOOD_INFERRED`.

Geology context 2026-06-28: `geology_context` jest stałym etapem JSON i działa fail-open dla całej Europy. Bazowym providerem jest `EGDI`, który ma pokrywać dowolną trasę gravelową w Europie; krajowe providery są opcjonalnym enrichment/override po stronie krajowej, a `heuristic_region_v1` pozostaje ostatnim fallbackiem. Docelowy porządek: 1) EGDI, 2) national provider enrichment tam, gdzie kraj jest obsługiwany, 3) `heuristic_region_v1`. Nie modelujemy tego jako listy ręcznych krajowych wyjątków. Włochy i Hiszpania były tylko testami konkretnych krajów, nie granicą systemu. Geologia używa centroid+bbox+punkty kontrolne co 10 km, nigdy próbkowania surface 50 m. Segmenty mogą dostać `geology_material_hint`, `geology_hint_applied` i `risk_flags`, ale `surface_raw` nie jest nadpisywane.

`route_frames` 80 m zostają jako legacy/fallback dla profilu, pogody, debug i agregacji. WEB, qbot.query, Telegram i MCP mają docelowo konsumować ten sam wynik `route_surface_analysis_v1`; WEB jest rendererem, nie źródłem prawdy.

Refinementy: Valhalla tylko jako fallback/refinement; landcover jako contextual refinement; `geology_context` jako europejski etap fail-open z próbkowaniem centroid+bbox+punkty kontrolne 5-10 km, nigdy co 50 m. Bazą jest EGDI, krajowe źródła są enrichmentem, a heuristic zostaje ostatnim fallbackiem.

## Runtime prompt QBot

`QBOT_INSTRUCTIONS.md` jest runtime promptem QBot używanym przez `qgpt_client.py`.

Nie mylić go z instrukcjami pracy Claude w repo. Instrukcje pracy Claude są w `CLAUDE.md`.

## Zasada dla nowych narzędzi

Każda zmiana w `qbot3/tool_registry.py` albo dodanie domeny/intencji wymaga jednoczesnej aktualizacji `_SYSTEM` w `qbot3/llm/albert.py`.

Bez tego Albert może nie wiedzieć, że narzędzie istnieje albo kiedy go używać.

## Testy i znane rozjazdy

`tests/test_qbot3_acceptance.py` jest częściowo historyczny względem aktualnego runtime:

- referuje `core.planner`, którego nie ma,
- oczekuje dwóch publicznych MCP tools,
- aktualne `tools/list` zwraca tylko `qbot_query`.

Nie traktuj tego pliku jako jedynego acceptance gate do czasu jego aktualizacji.

## Dokumenty historyczne

- `docs/architecture/QBOT_ARCHITEKTURA_V2.md` — historyczne / częściowo nieaktualne.
- `PROJECT_STATE.md` — historyczny handoff.
- `QBOT_CURRENT_STATE.md` — deprecated redirect.

## 2026-06-28 — VNEXT jako wąski fast-path, Albert jako ścieżka dla złożonych zapytań

Intencja zmiany: ograniczyć przechwytywanie zapytań przez `query_vnext`, bo keywordowy router potrafił błędnie klasyfikować pytania architektoniczne, trasowe i wielodomenowe przed Albertem.

Decyzja runtime:
- `qbot3/adapters/mcp_adapter.py` nadal może użyć `qbot_query_handler.py`, ale tylko jako wąski, jednoznaczny fast-path dla prostych zapytań read-only.
- Wszystkie zapisy, `ACTION_REQUIRED`, `UNRECOGNIZED`, zapytania trasowe, architektoniczne, analityczne, wielodomenowe oraz intencje spoza jawnej allowlisty VNEXT mają być kierowane do `qbot3.agent_runtime.orchestrate_query()`.
- VNEXT nie jest warstwą decyzyjną QBot3. Decyzje dla nieprostych przypadków podejmuje Albert/QBot3.

Ślad implementacji:
- `qbot3/adapters/mcp_adapter.py`: dodano denylistę/eskalację przed VNEXT, allowlistę `_QBOT_QUERY_VNEXT_FAST_PATH_INTENTS`, `_classify_vnext_escalation()` i `_should_accept_vnext_result()`.
- Cel: ograniczyć keyword hijack bez usuwania szybkiej ścieżki dla prostych odczytów.


### 2026-06-28 — doprecyzowanie po testach publicznego `qbot.query`

Intencja zmiany: VNEXT ma być tylko wąskim fast-pathem dla prostych read-only zapytań; nie może przejmować write, tras, architektury, analiz, wielodomenowych i niepewnych zapytań.

Decyzja runtime:
- Najpierw działa denylista/eskalacja w `qbot3/adapters/mcp_adapter.py`, dopiero potem allowlista prostych intentów VNEXT.
- Pytania o `VNEXT`, `query_vnext`, `QBot3`, Alberta, runtime, routing, migrację i architekturę idą bezpośrednio do Alberta/QBot3 jako diagnostyka/architektura, bez pośredniego `artifact_search`.
- Pytania mieszające żywienie z trasą/jazdą i oceną przygotowania idą do Alberta/QBot3 jako przypadek wielodomenowy.
- Zapisy nadal są blokowane przed VNEXT i kierowane do Alberta/QBot3 jako `ACTION_REQUIRED`.

Jawne powody eskalacji: `ESCALATED_ARCHITECTURE`, `ESCALATED_ROUTE`, `ESCALATED_MULTIDOMAIN`, `ANALYSIS_REQUIRED`, `ACTION_REQUIRED`.
