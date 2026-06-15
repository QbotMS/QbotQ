# Krok 3c: rozstrzygniecie H1/H2 dla `route_poi_analyze`

## Kluczowy fragment

`qbot_route_tools.py` dla `_tool_qbot_route_poi_analyze` nie zawiera literalnego `WRITE_DRAFT`.

Najwazniejsze miejsca:

- `qbot_route_tools.py:545-790` - caly `_tool_qbot_route_poi_analyze`
- `qbot3/artifacts/route_analyzer.py:1339-1385` - wynik analizy zwraca `status: "OK"` albo `status: "PARTIAL"` i pelne dane analizy (`chunks`, `missing_chunks`, `summary`, `water`, `soft_food_stop`, `hard_resupply`, `attractions`)
- `qbot3/tool_registry.py:1943-1949` - wrapper przepuszcza tylko `OK`/`PARTIAL`, usuwa `tool` i `safety_class`, potem robi `success_result(payload)`
- `qbot3/tool_registry.py:2447` i `qbot3/tool_registry.py:2471-2474` - `route_poi_analyze` ma `safety: "write"`, wiec trafia do `_WRITE_TOOLS`
- `qbot3/agent_runtime.py:100-117` - jesli tool jest w `write_tools`, runtime zwraca stub `WRITE_DRAFT`
- `qbot3/agent_runtime.py:275-280` - jesli `action_draft` istnieje, response dostaje `status = "draft"`

## Odpowiedzi na pytania z Zadania 4

1. Dla `poi etapu 2` path wykonywany w `orchestrate_query()` nie idzie do `_tool_qbot_route_poi_analyze` jako read-result. Runtime widzi `route_poi_analyze` jako write-tool i zwraca draft-stub z `action_type = "route_poi_analyze"`.
2. `status="WRITE_DRAFT"` powoduje warunek w `qbot3/agent_runtime.py:105-117`:
   - `if tool_name in write_tools: return {"status": "WRITE_DRAFT", ...}`
   - oraz pozniej `qbot3/llm/albert.py:381` ustawia `action_draft`, a `qbot3/agent_runtime.py:275-280` przemapowuje to na `status="draft"`.
3. Pelna analiza POI nie jest obecna w tym `WRITE_DRAFT`-owym wyniku. W `orchestrate_query("poi etapu 2")` widoczny jest tylko draft payload (`stage: 2`) i komunikat o koniecznosci `qbot.action_execute`. Pelne dane (`water`, `soft_food_stop`, `hard_resupply`, `attractions`) pojawiaja sie dopiero przy bezposrednim wywolaniu narzedzia albo w warstwie `route_analyzer`, nie w draft-stubie runtime.
4. Wniosek: to nie jest H1 ani H2. To `INNE`.

## Jednoznaczne rozstrzygniecie

**INNE**

Powod:
- `_tool_qbot_route_poi_analyze` / `route_analyzer` zwraca `OK` lub `PARTIAL`, nie `WRITE_DRAFT`.
- `WRITE_DRAFT` pochodzi z warstwy `qbot3/agent_runtime.py`, bo `route_poi_analyze` jest wpisane do `_WRITE_TOOLS` przez `qbot3/tool_registry.py:2447` i `qbot3/tool_registry.py:2471-2474`.
- Chunking istnieje, ale nie generuje `WRITE_DRAFT`; daje `chunks`, `missing_chunks`, `retry_chunk_id`, `retry_mode`, `PARTIAL` lub `OK`.

## Mechanizm chunkingu

`qbot3/artifacts/route_analyzer.py:1339-1385` pokazuje, ze chunking jest czescia analizy POI, ale jego wynikiem sa pola:
- `status`
- `analysis_status`
- `chunks`
- `missing_chunks`
- `summary`
- `water`
- `soft_food_stop`
- `hard_resupply`
- `attractions`

To nie jest drugi etap zatwierdzania draftu. To jest normalna analiza z mozliwym podzialem na chunki.

## Wniosek dla nastepnego kroku

Wersja read-only (`route_poi_analyze_readonly`) nie powinna mapowac `WRITE_DRAFT` na `OK` na bazie `qbot_route_tools.py`, bo sam analyzer nie zwraca `WRITE_DRAFT`. Trzeba bedzie rozdzielic:
- write-tool `route_poi_analyze` w runtime
- osobny read-only wrapper, ktory wywola analyzer poza write path
