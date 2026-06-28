# QBot Tool Registry Map

**Status:** zaktualizowany 2026-06-28 (audyt roboczy: 2026-06-27)
**Źródło:** `qbot3/tool_registry.py` + `tmp/dump_tool_descriptions.py` runtime dump z VPS
**Zakres:** **54 narzędzia** zarejestrowane w runtime (71 `_load_*` w pliku, część niezarejestrowana lub wyłączona). Publiczny MCP wystawia tylko `qbot_query`.

> **Uwaga 2026-06-28:** Poprzedni nagłówek podawał 68 narzędzi — to był szacunek z `def _load_*`. Runtime dump przez `tool_descriptions()` zwraca **54**. Różnica: część loaderów jest w pliku ale nie rejestrowana (możliwe flagi, duplikaty, legacy). Weryfikacja przez `tmp/dump_tool_descriptions.py`.

---

## 0. Model wykonania

```text
public MCP
└─ qbot_query
   └─ qbot3/adapters/mcp_adapter.py
      ├─ qbot_query_handler.handle_query() jeśli QBOT_QUERY_VNEXT_ENABLED=1
      │   (wąski fast-path dla prostych read-only; denylist eskaluje trasy/architekturę/multi-domain do Alberta)
      └─ qbot3.agent_runtime.orchestrate_query()
         └─ qbot3/tool_registry.py
            └─ 54 internal tools Alberta (stan 2026-06-28)
```

Narzędzia z tej mapy nie są publicznym API. Są rejestrem wewnętrznym używanym przez Alberta/orchestrator.

---

## 1. Warstwy danych i storage

### 1.1 PostgreSQL `qbot`

Główna baza runtime/QBot3.

**Typowe obszary:**

- trening / Garmin / wellness / fitmodel,
- artifacts,
- planning facts,
- memory,
- calendar/reminders,
- nutrition,
- route/surface/profile data.

**Moduły zależne:**

- `qbot3/db_introspection.py`,
- `qbot3/memory.py`,
- `qbot3/safety.py`,
- `qbot3/artifacts/store.py`,
- `qbot3/connectors/import_garmin_*.py`,
- `qbot3/connectors/import_withings_body.py`,
- `qbot3/connectors/import_xert_profile_snapshot.py`,
- `qbot3/tool_registry.py`,
- `qbot_api.py`,
- `qbot_query_handler.py`,
- `qbot_planning_memory.py`,
- `qbot_wellness_store.py`,
- `qbot_mcp_adapter.py`,
- `fitmodel/*`.

### 1.2 SQLite `data/garage.db`

Lokalna baza garażu i danych sprzętowo-planistycznych.

**Tabele potwierdzone:**

- `bikes`,
- `components`,
- `fitting`,
- `gear`,
- `memories`,
- `packing_items`,
- `packing_lists`,
- `reminders`,
- `reminders_fired`,
- `tires`,
- `trips`,
- `xert_snapshots`.

**Moduły zależne:**

- `qbot_query_handler.py`,
- `qbot_garage_tools.py`,
- legacy `db.py`.

### 1.3 SQLite `qbot_mcp_auth.db`

Baza OAuth/auth runtime.

**Tabele potwierdzone:**

- `oauth_codes`,
- `oauth_tokens`.

**Klasyfikacja:** runtime/auth, nie ruszać przy cleanup bez osobnego planu.

### 1.4 Filesystem artifacts

Artefakty QBot/Sandbox.

**Główne ścieżki:**

- `/opt/qbot/artifacts`,
- lokalne GPX/JSON/MD/CSV/FIT,
- projekty, np. `tuscany_2026`.

**Moduły:**

- `qbot3/artifacts/store.py`,
- `qbot3/artifacts/route_analyzer.py`,
- `qbot3/artifacts/gpx_splitter.py`.

---

## 2. Zależności zewnętrzne

| Zależność | Używana przez | Uwagi |
|---|---|---|
| Garmin Connect API | `garmin_live_fetch`, `wellness_day`, `sleep_day`, `garmin_workout_create`, importery Garmin | dane wellness/trening/sen/energia + workout write |
| Xert API | `xert_readiness`, import Xert snapshot | readiness/form/FTP/LTP/W′ |
| RWGPS API | `rwgps_*`, route tools | lista/fetch/import tras, GPX, POI |
| OpenWeatherMap | `weather_forecast`, route analysis | pogoda live / prognoza trasy |
| OSM / Overpass | surface/POI/stage tools | nawierzchnia, POI, tagi `surface/highway/tracktype` |
| Nominatim | stage endpoint analysis | reverse geocoding końcówek etapów |
| Google Places | POI open hours, opcjonalnie | fallback godzin otwarcia i POI |
| HikConnect | `gate_status` / `qbot_qlab_server.py` | GATE działa, ale powinien być w QTools |
| Hammerhead/Karoo | `hammerhead_sync_status`, zewnętrzny export FIT | powinno finalnie przejść do QTools |

---

## 3. Ryzyka ogólne

| Ryzyko | Status | Komentarz |
|---|---:|---|
| `qbot_qlab_server.py` trzyma GATE | wysokie | GATE jest potrzebne, ale siedzi w legacy QLab sidecarze. Przenieść do QTools. |
| `Q365` jako runtime | wysokie | Q365 to martwy byt; nie powinien hostować produkcji. |
| `safety=write` + `mode=read_only` | średnie | Część write tools ma mode `read_only`. Sprawdzić, czy `mode` jest ignorowane czy używane w plannerze. |
| `artifact_save` ma `safety=read` | średnie | Nazwa i opis mówią o zapisie artefaktu; safety wygląda niespójnie. |
| `rwgps_poi_push` ma `safety=read` | wysokie | Opis mówi o dodawaniu POI do RWGPS, domyślnie dry-run. Wymaga weryfikacji safety. |
| `tool_registry.py` zawiera logikę i DB connect | średnie | Registry nie jest czystym registry; ma bezpośrednie `psycopg` i logikę narzędzi. |
| `canonical_docs` czyta `/opt/qbot/docs/QBOT_BIBLE.md` | niskie | Po audycie 2026-06-28 plik jest stub-em z redirectem. Narzędzie zwróci stub-treść — niegroźne, ale może być mylące dla Alberta. |

---

# 4. Narzędzia pogrupowane (54 runtime, 2026-06-28)

## 4.1 Artifacts

**Wspólne zależności:** `qbot3.artifacts.store`, PostgreSQL `qbot_v2.artifacts` / artifact registry, filesystem `/opt/qbot/artifacts`.

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `artifact_save` | read / read_only | Zapisuje artefakt tekstowy lub binarny, rejestruje metadane, obsługuje `content`, `content_base64`, `filename`, `artifact_type`, `project_id`, `subdir`. | FS artifacts + PostgreSQL artifacts. **Niespójność:** safety=read mimo zapisu. |
| `artifact_search` | read / read_only | Wyszukuje artefakty po nazwie, tytule, `project_id`, `artifact_id`, typie i statusie. | PostgreSQL artifacts. |
| `artifacts_list` | read / read_only | Lista projektów albo artefaktów QBot Sandbox. | PostgreSQL artifacts/projects. |

## 4.2 Calendar / reminders

**Wspólne zależności:** `qbot_calendar_core`, `qbot_mcp_adapter`, PostgreSQL/QCal tables, reminder runtime.

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `calendar_snapshot` | read / read_only | Snapshot dnia: kalendarz, reminders, meals, wellness, health data. | Calendar DB + nutrition/wellness summary. |
| `qcal_events_range` | read / read_only | Surowe eventy QCal z zakresu dat. | PostgreSQL calendar/QCal tables. |
| `qcal_events_upcoming` | read / read_only | Nadchodzące eventy od dziś, status planned/active/confirmed. | PostgreSQL calendar/QCal tables. |
| `qcal_reminders_upcoming` | read / read_only | Nadchodzące pending reminders. | PostgreSQL/reminder tables lub reminder layer. |
| `calendar_event_add` | write / read_only | Dodaje event kalendarza; wymaga `date_start`, `title`. | `qbot_mcp_adapter._action_exec_event`; write path. **Sprawdzić mode.** |
| `reminder_add` | write / read_only | Dodaje reminder; wymaga `date`, `title`. | `qbot_mcp_adapter._action_exec_reminder`; write path. **Sprawdzić mode.** |

## 4.3 DB introspection

**Wspólne zależności:** `qbot3.db_introspection`, PostgreSQL `qbot`.

`db_introspection.py` ma guardy: tylko `SELECT`, wymuszony `LIMIT`, timeout, denylist tabel sekretów, blokada `INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE`.

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `db_schema_list` | read / read_only | Lista schematów i tabel. Pierwszy krok przy nieznanej strukturze DB. | PostgreSQL information_schema. |
| `db_table_describe` | read / read_only | Kolumny i typy tabeli. | PostgreSQL information_schema. |
| `db_sample_rows` | read / read_only | Próbka wierszy z tabeli, limitowana. | PostgreSQL read-only SELECT. |
| `db_select_readonly` | read / read_only | Bezpieczny SELECT z limitem i blokadą write SQL. | PostgreSQL read-only SELECT. |

## 4.4 Docs

**Wspólne zależności:** lokalne pliki `docs/`, canonical docs, repo filesystem.

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `canonical_docs` | read / read_only | Czyta kanoniczne dokumenty QBot z excerpt matching. **Po audycie 2026-06-28:** QBOT_BIBLE.md w `/opt/qbot/docs/` to stub — zwróci redirect, nie treść. | Local docs. |
| `docs_list_qbot` | read / read_only | Lista plików dokumentacji QBot. | Local docs. |

## 4.5 Garage

**Wspólne zależności:** `qbot_garage_tools`, SQLite `data/garage.db`.

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `garage_status` | read / read_only | Status Garage DB: tabele, liczniki, seed status. | SQLite `data/garage.db`. |

## 4.6 Garmin / Training

**Wspólne zależności:** Garmin Connect API, `garmin_auth`, importery `qbot3/connectors/import_garmin_*`, PostgreSQL wellness/training/energy/body tables.

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `garmin_diagnostics` | read / read_only | Sprawdza stan synchronizacji Garmin w DB: tabele, liczność, ostatnie daty. | PostgreSQL `qbot_v2.sleep_daily`, `energy_daily`, `wellness_daily`, `training_sessions`. |
| `garmin_live_fetch` | read / read_only | Pobiera live wellness/energy z Garmin API dla daty; nie z cache DB. | Garmin API + auth. |
| `garmin_sync_status` | read / read_only | Ostatnia data danych Garmin, ostatni sync, rekordy z 7 dni. | PostgreSQL Garmin tables. |
| `garmin_workout_create` | write / read_only | Tworzy structured workout w Garmin Connect; obsługuje dry-run i confirm. | Garmin API + `qbot_garmin_workouts`. **Sprawdzić mode.** |

## 4.7 Memory

**Wspólne zależności:** `qbot3.memory`, PostgreSQL memory table.

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `memory_confirmed_fact_add` | write / read_only | Zapisuje potwierdzony fakt lub summary do memory. | PostgreSQL memory. **Sprawdzić mode.** |

## 4.8 Nutrition

**Wspólne zależności:** `qbot_nutrition_tools`, `qbot3.nutrition_write_resolver`, `qbot3.adapters.mcp_adapter`, PostgreSQL nutrition tables.

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `nutrition_template_list` | read / read_only | Lista zapisanych szablonów posiłków z kcal i makro. | Nutrition templates DB. |
| `nutrition_template_get` | read / read_only | Pobiera szablon po nazwie lub ID. | Nutrition templates DB. |
| `nutrition_write_resolve` | read / read_only | Rozwiązuje niejednoznaczne wpisy żywieniowe, arytmetykę, szablony, porcje. | Nutrition resolver + templates/foods. |
| `nutrition_day_summary` | read / read_only | Suma kcal/makro/posiłki dla daty. | Nutrition logs/items DB. |
| `nutrition_meal_list` | read / read_only | Lista posiłków zapisanych dla daty. | Nutrition logs/items DB. |
| `nutrition_log_add` | write / read_only | Dodaje wpis posiłku: kcal, makro, opcjonalny template. | Nutrition write path. **Sprawdzić mode.** |
| `nutrition_log_delete` | write / read_only | Usuwa wpis posiłku po `meal_id`. | `qbot3.adapters.mcp_adapter._execute_nutrition_delete`. **Sprawdzić mode.** |
| `nutrition_log_correct` | write / read_only | Koryguje wpis posiłku po `meal_id`, opcjonalnie item. | `qbot3.adapters.mcp_adapter._execute_nutrition_correct`. **Sprawdzić mode.** |

## 4.9 Planning

**Wspólne zależności:** `qbot_planning_memory`, PostgreSQL `qbot_planning_facts`.

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `planning_facts` | read / read_only | Lista faktów planowania, filtr po dacie/statusie/typie/tytule. | PostgreSQL planning facts. |
| `planning_fact_lookup` | read / read_only | Alias/lookup faktów planowania. | PostgreSQL planning facts. |
| `planning_fact_add` | write / read_only | Dodaje fakt planowania: title, type, date, JSON, confidence. | PostgreSQL planning facts. **Sprawdzić mode.** |
| `planning_fact_update` | write / read_only | Aktualizuje fakt po `fact_id`, patchuje JSON lub stage. | PostgreSQL planning facts. **Sprawdzić mode.** |

## 4.10 Routes / RWGPS / POI / GPX

**Wspólne zależności:** `qbot_route_tools`, `qbot_route_report_tool`, `qbot_route_analysis_tool`, `qbot_route_time_tools`, `qbot_pressure_tools`, `qbot_fuel_tools`, `tools.rwgps.route_find`, RWGPS API, OSM/Overpass, Nominatim, opcjonalnie Google Places, artifacts FS, PostgreSQL route tables.

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `rwgps_route_list` | read / read_only | Live lista tras RWGPS, bez cache DB. | RWGPS API. |
| `rwgps_route_last` | read / read_only | Ostatnia trasa RWGPS. | RWGPS API. |
| `rwgps_route_find` | read / read_only | Szuka trasy RWGPS po nazwie/hincie. | `tools.rwgps.route_find`, RWGPS API/cache. |
| `rwgps_route_fetch` | read / read_only | Pobiera surowe metadane trasy po ID. Nie do pełnej analizy. | RWGPS API. |
| `rwgps_artifact_status` | read / read_only | Sprawdza dostępne formaty artefaktów trasy: GPX/JSON/FIT/TCX. | RWGPS API. |
| `rwgps_route_import_gpx` | write / write | Importuje trasę do RWGPS z GPX albo resolved route; `confirm=true` wykonuje POST. | RWGPS API write + GPX. |
| `rwgps_route_surface_analyze` | read / read_only | Analiza nawierzchni RWGPS przez OSM/Overpass. | OSM/Overpass + route artifacts/cache. |
| `rwgps_poi_push` | read / read_only | Analizuje POI i może dodawać je do RWGPS; domyślnie dry-run. **Niespójność safety=read.** | RWGPS API + POI. |
| `route_plan_analysis` | read / read_only | Pełna analiza zaplanowanej trasy: nawierzchnia, podjazdy, pogoda, wiatr, forma. | Route analysis stack + weather + fitness DB. |
| `route_analysis` | read / read_only | Jednowarstwowa pełna analiza LLM sekcji A-F dla trasy. | Route context + Albert/LLM + route tools. |
| `route_report` | read / read_only | Orkiestrator raportu trasy: skrócony/pełny/grupa. | `qbot_route_report_tool` + route stack. |
| `route_profile_detail` | read / read_only | Szczegółowy profil 80 m: odcinki nawierzchni, wysokości, podjazdy. | Route artifacts/profile tables. |
| `route_time_estimate` | read / read_only | Szacunek czasu przejazdu na podstawie dystansu lub route_id i ostatnich jazd. | `qbot_route_time_tools`, training DB. |
| `route_fuel_plan` | read / read_only | Plan płynów/węgli B2/B3; mirror QExt2. | `qbot_fuel_tools`, body measurements, weather/time estimate. |
| `tire_pressure` | read / read_only | Kalkulator ciśnienia opon B5 dla zestawów kół. | `qbot_pressure_tools`, garage DB, body weight DB. |
| `route_stage_plan_analyze` | read / read_only | Analiza końcówek etapów, reverse geocoding, opcjonalnie noclegi. | `qbot3.artifacts.route_analyzer`, Nominatim, Overpass. |
| `stage_gpx_analyze` | read / read_only | Analizuje lokalny GPX etapu: dystans, przewyższenia, profile, climbs/descents. | Local GPX artifacts. |
| `route_gpx_split` | read / read_only | Dzieli GPX RWGPS na etapy i zapisuje pliki w sandboxie. **Nazwa read, ale zapisuje pliki.** | `qbot3.artifacts.gpx_splitter`, FS artifacts. |
| `route_artifact_enrich_dry_run` | read / read_only | Dry-run wzbogacenia nawierzchni z OSM/Overpass, bez zapisu do DB. | OSM/Overpass + GPX artifacts. |
| `route_poi_analyze_readonly` | read / read_only | Informacyjna analiza POI trasy/etapu, bez wymogu potwierdzenia. | OSM/Overpass/Google Places optional + artifacts. |
| `route_poi_analyze` | write / write | Analiza POI z zapisem/aktualizacją raportu artefaktów; wymaga write path. | POI stack + FS/PostgreSQL artifacts. |
| `ride_analysis` | read / read_only | Analiza już przejechanej jazdy z FIT; porównuje plan-wykonanie. | FIT files, Garmin/Hammerhead data, route plan. |

## 4.11 System / operational status

**Wspólne zależności:** `qbot3.capabilities`, lokalne logi, env status, system/service sidecars.

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `status` | read / read_only | Status procesu QBot: hostname, PID, wersja Pythona. | Local runtime. |
| `readiness` | read / read_only | Ocena gotowości QBot: zasoby, blokery, overall status. | `qbot_operator_tools`. |
| `system_env_status` | read / read_only | Status env/connectors/API keys/DB connectivity bez sekretów. | Env + DB probe. |
| `system_logs_recent` | read / read_only | Ostatnie logi systemowe z `q-bot.log`. | Local logs. |
| `daily_report_status` | read / read_only | Status pipeline raportów dziennych: kanały, błędy, sleep wait. | Daily report pipeline + logs/DB. |
| `gate_status` | read / read_only | Status konfiguracji GATE/HikConnect; nie otwiera furtki. | Obecnie `qbot_qlab_server.py`/HikConnect. **Docelowo QTools.** |
| `hammerhead_sync_status` | read / read_only | Status pipeline Hammerhead/Karoo → Garmin: config, dedup, log, outgoing files. | Hammerhead sync files/logs. **Docelowo QTools.** |
| `llm_status` | read / read_only | Provider/model/fallback LLM, konfiguracja bez sekretów. | LLM provider config. |
| `mcp_tools_list` | read / read_only | Lista publicznych MCP tools. | MCP adapter; wyświetla tylko `qbot_query`. |

## 4.12 Weather / wellness / fitness

| Tool | Safety / mode | Opis | Zależności |
|---|---|---|---|
| `weather_forecast` | read / read_only | Live prognoza z OpenWeatherMap; lokalizacja, okres, godziny. | OpenWeatherMap API. |
| `wellness_day` | read / read_only | Live wellness Garmin dla daty; nie z cache DB. | Garmin API. |
| `sleep_day` | read / read_only | Live dane snu Garmin dla daty; nie z cache DB. | Garmin API. |
| `xert_readiness` | read / read_only | Live Xert readiness: FTP/LTP/W′/form. | Xert API. |

---

# 5. Podział docelowy QBot / QTools

## Zostaje w QBot

- `qbot_query`, Albert, routing intencji,
- route analysis/reporting,
- nutrition,
- planning/memory,
- calendar/reminders,
- Garmin/wellness jako dane asystenta,
- DB introspection read-only,
- docs/artifacts jako sandbox asystenta.

## Do QTools

- `GATE`: `/gate/status`, `/gate/open`, HikConnect direct,
- Hammerhead/Karoo → Garmin FIT export/transform/sync,
- ewentualne helpery QExt2, jeśli są runtime-operational i nie są asystentem.

## Nie używać produkcyjnie

- Q365 jako execution host,
- QLab/FIT export legacy w `qbot_qlab_server.py`, po migracji GATE.

---

# 6. Następne kroki techniczne

1. Zweryfikować `mode` dla write tools w plannerze/orchestratorze.
2. Poprawić safety dla `artifact_save`, `rwgps_poi_push`, ewentualnie `route_gpx_split`.
3. Rozbić `tool_registry.py`: registry powinno rejestrować, a nie trzymać logikę DB/API.
4. Sporządzić osobny `QBOT_DB_MAP.md` po odczycie schematów PostgreSQL, bez sekretów.
5. Wydzielić GATE do QTools przed wyłączeniem `qbot-qlab-server`.
6. Wydzielić Hammerhead/Karoo → Garmin export do QTools.
7. **Naprawić `canonical_docs`** — po audycie 2026-06-28 QBOT_BIBLE.md w `/opt/qbot/docs/` jest stubem; narzędzie powinno wskazywać na `docs/architecture/QBOT_ARCHITEKTURA_QBOT3.md` albo być zaktualizowane.
