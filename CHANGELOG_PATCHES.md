## 2026-06-13 — test 14 / item C: guard negacji Garmina w _resolve_intent

Plik: qbot_query_handler.py

Problem: zapytania z negacją aktywności/Garmina ("nie aktywność z Garmina",
"ale nie z Garmina") routowane jako garmin_activity_detail (bare keyword
"aktywność", linia ~402) — nie docierały do plannera (status != UNRECOGNIZED).
Po zdjęciu hijacku Garmina ujawnił się drugi: energy_day (bare "aktywność",
linia ~416).

Zmiana:
- Dodany _GARMIN_ACTIVITY_NEG_RE: r"\bnie\b[^.,;:!?]{0,20}(?:aktywno|garmin)|bez\s+garmin"
- Guard w pętli INTENT_KEYWORDS w _resolve_intent (wzorzec jak nutrition_range/xert):
  dla intentów ("garmin_activity_detail","energy_day") + dopasowanie negacji -> continue.

Efekt (zweryfikowane na żywym serwisie):
- 6 zapytań z negacją -> unrecognized. Z markerem trasy: is_route_domain_query=True -> planner.
  Bare negacja bez treści trasy -> planner_unavailable (poprawnie).
- Regresja OK: garmin z ID (detail/streams/export), energy_day (ile spaliłem/kroki/energia).

Backupy:
- qbot_query_handler.py.bak.1781374841  (patch 1: guard garmin_activity_detail)
- qbot_query_handler.py.bak.1781375715  (patch 2: +energy_day)
restart qbot-api: active.

Otwarte: brak realnego tekstu testu 14 (harness 25-testów poza serwerem) —
fix oparty na rekonstrukcjach + mechanizmie; do potwierdzenia oryginalnym zapytaniem.

---
2026-06-13 CONFIRM: test 14 real query verified end-to-end -> plan_routes tool_calls=['rwgps_route_last'], route 55567991, status OK, clean /routes/ link. PASS (routing + planner).
## 2026-06-13 — planner_routes: test 8 + test 24 (core/planner.py)

Backup: core/planner.py.bak.1781377766

TEST 8 (gravel/bagaz/ryzyko liczone z samych metadanych):
- Przyczyna: _is_metadata_only() lapalo "ostatnia trasa" jako metadane i ZAWEZALO
  toolset do {rwgps_route_last, rwgps_route_list} — model fizycznie nie mogl pobrac/
  analizowac, mimo ze _SYSTEM_PROMPT (pkt 7) kazal lancuch fetch->analiza.
- Fix: do _ANALYSIS dodane markery: gravel, bagaz, bagaż, ryzyk, sensown, fragment.
- e2e (live, gpt-5.4-mini): tool_calls = rwgps_route_last, rwgps_route_fetch,
  route_poi_analyze... — pobiera+analizuje. Regresja metadata-only: czyste
  "pokaz ostatnia trase" dalej meta=True. PASS.

TEST 24 (konflikt Garmin vs RWGPS niewykryty):
- Przyczyna: prompt wykrywal tylko terminologie Garmin-aktywnosc (aktywnosc/trening/
  przejazd); "trase z Garmina zaplanowana w RWGPS" nie pasowalo -> traktowane jak
  zwykla trasa RWGPS.
- Fix: deterministyczny guard _is_ambiguous_source() + _ambiguous_source_response()
  na poczatku _plan_routes_impl. garmin + rwgps jednoczesnie (i Garmin NIE negowany)
  -> clarify bez wolania LLM. Dodany import re.
- Negacja Garmina wyciszona (re): test 14 "nie aktywnosc z Garmina" -> amb=False,
  test 9 (brak garmin) -> amb=False. Zero regresji.
- e2e: plan_routes -> planner=ambiguous_source_guard, tool_calls=[]. PASS.

ODKRYTE (do osobnych sesji, NIE naprawione):
- Test 7 (rozklad nawierzchni asfalt/szuter/sciezki): rwgps_route_surface_analyze
  NIE istnieje w qbot3.tool_registry (sa tylko route_gpx_split, stage_gpx_analyze,
  import). To brak narzedzia, nie prompt — wymaga zbudowania surface-analizy.
- Test 6 (max_grade): stage_gpx_analyze/analyze_stage_gpx nie zwraca max_grade
  (zwraca gain/loss/profile_5km/climbs). Do dolozenia pola.
- BUG freshness: supersede ustawia status='superseded', ale enum qbot_v2.artifact_status
  nie ma tej wartosci -> "invalid input value for enum artifact_status". Supersede
  leci bledem po cichu. Do naprawy (ALTER TYPE ... ADD VALUE 'superseded' albo zmiana
  wartosci w kodzie na istniejaca).

Status restartu qbot-api: active.

---
## 2026-06-13 — test 7: rwgps_route_surface_analyze wpiety do plannera

Backupy: qbot3/tool_registry.py.bak.1781379115, modules/routes/manifest.py.bak.1781379115

Przyczyna: logika analizy nawierzchni istniala (scripts/analyze_rwgps_surface.py:
analyze_rwgps_surface_route — export GPX -> geometria -> Overpass -> breakdown),
ale NIE byla zarejestrowana jako tool w qbot3.tool_registry, wiec planner jej nie
widzial. Stad "brak rwgps_route_surface_analyze" + odpowiedz z samych metadanych.

Fix:
- qbot3/tool_registry.py: nowy _load_rwgps_route_surface_analyze_tool() (wrapper na
  analyze_rwgps_surface_route, args: route_id/project_id/refresh_overpass, zwraca
  TRIMMED summary: surface_breakdown, dominant_surface, practical_groups,
  highway_breakdown, tracktype, smoothness, overpass-coverage, recommendation,
  warnings — bez surowej geometrii). Dodany wpis do listy loaderow.
- modules/routes/manifest.py: "rwgps_route_surface_analyze" w planner_tools (15 narzedzi).

e2e (live, gpt-5.4-mini): tool_calls = rwgps_route_last, rwgps_route_surface_analyze.
Realny rozklad: asfalt 73.3% / kostka 4.4% / nieznana 22.2% / gravel 0% / track 2.2%,
paved 77.7%. Brak zbednego route_list. PASS.

restart qbot-api: active.

---
## 2026-06-13 — planner_routes blok: test 5 + test 6 + test 18

Backupy: core/planner.py.bak.1781380041,
         qbot3/artifacts/route_analyzer.py.bak.1781380041

TEST 5 (etykieta "URL API"):
- Pole z toola nazywa sie "url" (poprawne); "URL API" to inwencja modelu.
- Fix: linia w _SYSTEM_PROMPT — link nazywaj "Link do trasy"/"Link", nigdy "URL API"/"API".
- e2e (live, "pokaz ostatnia trase z rwgps"): answer = "Link: https://ridewithgps.com/...",
  brak "URL API". PASS.

TEST 6 (brak max_grade):
- analyze_stage_gpx liczyl gain/loss/climbs(avg_gradient) ale nie globalnego max grade.
- Fix: dodane wygladzone max_grade_pct (okno ~100m, redukcja szumu GPS) + max_grade_window_m
  w wyniku analyze_stage_gpx (qbot3/artifacts/route_analyzer.py).
- e2e (deterministic, stage_03 GPX): max_grade_pct=10.4, window=100, gain=892.4. PASS.

TEST 18 (niepelna deduplikacja tool-calli):
- Galaz reasoning (_run_openai_tool_loop): dodany _seen{}; identyczny (tool|args) read-only
  -> zwraca cache, NIE wykonuje ponownie, NIE dubluje w tool_log (log "dedup skip").
  Dedup tylko dla safety=read / mode=read_only (write nie dedupowane).
- Status: pętla zdrowa (2 live calle bez bledu, tool_calls bez duplikatow), logika
  ast.parse OK. Naturalny duplikat nie powtorzyl sie w sondzie -> dedup to siatka
  bezp. na exact-repeat. Galaz chat/gemini NIE ruszona (osobny follow-up jesli trzeba).

POBOCZNE (do osobnej sesji):
- stage_gpx_analyze: wrapper mapuje stage=N na /artifacts/projects/tuscany_2026/projects/,
  a pliki GPX leza w /artifacts/OLD/projects/tuscany_2026/projects/ -> stage=N daje
  MISSING_ARGS. Model dziala bo podaje file_path z artifact_search. Do wyrownania sciezki.

restart qbot-api: active.

---
