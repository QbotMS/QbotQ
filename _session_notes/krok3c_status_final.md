# Krok 3c - status końcowy sesji (2026-06-15)

## Zrealizowane
- `route_poi_analyze_readonly`: nowe narzędzie w `tool_registry`, `safety="read"`, NIE w `_WRITE_TOOLS`, Albert poprawnie je WYBIERA dla `"poi etapu 2"` (description tuning zadziałał - LLM odróżnia write vs readonly).
- Direct call: zwraca pełną analizę POI (`hard_resupply=9`, `soft_food_stop=23`, `water=20`, `attractions=53` dla etapu 2) - status `OK`.
- Acceptance suite: `66/0/1`, bez regresji.
- Permission fix (z 1a-bis): `exports/rwgps` + `reports`, commit `9e8cd03`.

## NIE zrealizowane / BLOKER
- `orchestrate_query("poi etapu 2")` END-TO-END nie domyka się - 12x wywołanie tego samego narzędzia, `status="partial"`, brak finalnej odpowiedzi z danymi. Root cause: TOP_PRIORITY w `TODO_aktywne.md` (truncation `[:4000]` w `albert.py`, hipoteza).
- `route_poi_analyze_readonly` jest FUNKCJONALNIE poprawne (dane są liczone prawidłowo), ale UX END-TO-END przez `qbot.query` jest ZEPSUTY dla tej intencji DOPÓKI TOP_PRIORITY nie jest naprawiony.

## Co to znaczy dla Kroku 3b/1b
NIE przełączać Router v2 na Alberta dla ŻADNEJ intencji `OPEN_DOMAIN` (włącznie z profilem etapu, mimo że 1a wykazało "równoważność wyników") DOPÓKI TOP_PRIORITY nie jest zbadany i naprawiony - profil etapu może mieć ten sam problem pętli dla większych wyników (wiele segmentów). `core.planner.plan_routes()` ZOSTAJE jedynym handlerem dla `OPEN_DOMAIN_INTENTS` do tego czasu - to NIE jest regresja, to status quo (działa od dawna).

## Kolejność następnej sesji
1. TOP_PRIORITY (truncation/pętla) - patrz `TODO_aktywne.md`
2. Po naprawie: re-test profil etapu I poi etapu PRZEZ `orchestrate_query` end-to-end
3. Krok 3b/1b: przełączenie Router v2 (dopiero po 1-2)

## Stan repo
Branch `feature/router-v2-planner-v2-and-fixes`, ostatni commit `676493b`. Serwis `qbot-api`: `active`, `NRestarts=0`. Acceptance: `66/0/1`.
