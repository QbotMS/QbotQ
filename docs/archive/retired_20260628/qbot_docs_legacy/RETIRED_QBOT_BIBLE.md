# QBOT_BIBLE.md — Biblia QBot

Wersja: 2.0
Data: 2026-06-02
Status: zatwierdzony przez MS
Źródła: audyt OpenAI 2026-06-01/02, stan produkcyjny Q, QBOT_BIBLE v1.1, sesje Claude 2026-05-29–06-02.

---

## 0. Current State — Hybrid Runtime (2026-06-02)

QBot działa w architekturze hybrydowej:
- **Deterministic query handler** (`qbot_query_handler.py`) — keyword-based intent routing, 36 handlerów, ~50 intentów
- **QBot3/Albert** — LLM orchestrator (selektywny, nie główna ścieżka)
- **MCP bridge** (`qbot-mcp-bridge.service`, port 8000) — SSE bridge do ChatGPT
- **FastAPI** (`qbot-api.service`, port 8002) — główny entrypoint

### Serwisy

| Usługa | Stan | Port | Rola |
|---|---|---|---|
| `qbot-api.service` | active | 8002 | FastAPI — MCP, webhook, API |
| `qbot-mcp-bridge.service` | active | 8000 | MCP SSE bridge (ChatGPT) |
| `qbot-qlab-server.service` | active | 8899 | QLab/Gate HTTP server |
| `q365.service` | active | 8001 | osobna ścieżka |

### Publiczne MCP Tools

```
qbot.query          — jedyne wejście: natural language → intent → handler → odpowiedź
```

`qbot.action_execute` i `qbot.artifact_read` — zdefiniowane w kodzie, ale nie eksponowane w tools/list na porcie 8002.

### Query Handler — intenty (kompletna lista)

| Domena | Intenty |
|---|---|
| Nutrition | `daily_balance`, `nutrition_day`, `nutrition_intake_logs_list`, `nutrition_range` |
| Body | `weight_lookup`, `weight_trend`, `body_comp`, `body_measurements_range` |
| Sen | `sleep_day` |
| Wellness | `wellness_day` |
| Energia | `energy_day` |
| Trening | `training_recent` |
| Xert | `xert_status`, `xert_live_fetch` |
| Garaż | `garage_status`, `garage_search` |
| Trasy/RWGPS | `route_workflow_fetch`, `route_workflow_upload`, `route_workflow_list`, `route_climbs`, `rwgps_poi_push`, `route_poi_analyze`, `route_feasibility`, `tile_analysis` |
| Trip | `trips_status`, `trip_stages`, `trip_attractions`, `route_generate` |
| Artefakty | `artifact_search`, `artifact_read` |
| Pamięć | `memories_search` |
| Raporty | `daily_report`, `ride_report`, `report_diagnostic` |
| System | `qbot_help` |
| Multi-intent | `_handle_multi_intent` (cross-domain: nutrition+body, sleep+wellness itp.) |

---

## 1. Cel QBot

QBot to osobisty system operacyjno-asystencki MS. Zarządza danymi zdrowotnymi, treningowymi, żywieniowymi, sprzętowymi i podróżnymi.

Interfejsy: MCP (ChatGPT), Telegram, lokalne CLI.
Backend: PostgreSQL (schema `qbot_v2`), FastAPI, Python 3.12.

---

## 2. Architektura

```
input (ChatGPT MCP / Telegram / CLI)
  → qbot_query_handler._resolve_intent(question)     # keyword routing
  → _handle_<intent>(question)                        # deterministic handler
  → PostgreSQL qbot_v2.* / external API               # data source
  → _envelope(intent, answer, data, sources)          # structured response
```

Dla >1 domeny w pytaniu: `_detect_domains()` → `_handle_multi_intent()` → wywołuje wiele handlerów i scala.

### Zasada: deterministic-first

Router jest keyword-based (`INTENT_KEYWORDS`). LLM nie decyduje o routingu zapytań — jest opcjonalnym enrichmentem.
To świadoma decyzja: deterministyczny routing jest szybki (<50ms), debugowalny i nie halucynuje.

---

## 3. Dokumenty kanoniczne

```
/opt/qbot/docs/QBOT_BIBLE.md       — architektura, zasady, decyzje
/opt/qbot/docs/QBOT_KNOWHOW.md     — mapa plików, tabel, procedury, historia napraw
```

Zmiany wymagają zatwierdzenia MS.

---

## 4. Nutrition — architektura danych

### Ścieżki zapisu

| Ścieżka | Tabele docelowe | Walidacja |
|---|---|---|
| `meal_log_create()` (ChatGPT MCP) | `meal_logs` + `meal_log_items` + dual-write do `intake_logs` + `intake_items` | `_validate_and_fix_meal_items()` ✓ |
| `intake_log_create()` (QBot3) | `intake_logs` + `intake_items` | `_validate_and_fix_meal_items()` ✓ |
| `meal_from_template()` | przez `meal_log_create()` | ✓ |
| `plan_apply()` | przez `meal_log_create()` | ✓ |

### Walidacja itemów (`_validate_and_fix_meal_items`)

Auto-korekcje:
- Ujemne wartości → 0
- Sugar-type items (miód, cukier, syrop): protein/fat > 2g → 0
- Macro-kcal ratio > 2.0: skaluje makra proporcjonalnie w dół
- Duplicate field detection: identyczne niezerowe wartości (np. fiber=4 na 3 itemach) → zostawia pierwszy, zeruje resztę
- Macro-sum sanity: loguje ostrzeżenie gdy suma derived kcal >> suma reported kcal

### DB constraints

```sql
qbot_v2.intake_items:    CHECK (kcal>=0 AND protein_g>=0 AND carbs_g>=0 AND fat_g>=0 AND fiber_g>=0)
qbot_v2.meal_log_items:  CHECK (kcal>=0 AND protein_g>=0 AND carbs_g>=0 AND fat_g>=0 AND fiber_g>=0)
```

### Daily summary compute

`daily_summary_compute(date)` sumuje z `intake_items` (preferowane) lub `meal_log_items` (fallback).
Carbs total = meals.carbs + fueling_events.carbs.
⚠️ Jeśli fueling_events duplikują carbs z meals, będzie podwójne liczenie. Fueling events to ON-BIKE gels, nie regular meals.

### Nutrition range — bilans

Balance jest liczony spójnie: `QBot_intake (nutrition_daily_summary.kcal_total) - expenditure (daily_summary.expenditure_total)`.
Fallback do Garmin `balance_kcal` tylko gdy brak QBot intake.

### Date resolver

Obsługiwane formaty: `2026-06-01`, `01.06.2026`, `1 czerwca 2026`, `wczoraj`, `dzisiaj`.

---

## 5. Body Composition

Źródło: Garmin Index Scale → connector `import_garmin_body.py` → `qbot_v2.body_measurements`.
Cron: 07:30 daily.

Pola: `weight_kg`, `body_fat_pct`, `muscle_mass_kg`, `bone_mass_kg`, `body_water_pct`, `bmi`.

Intenty: `weight_lookup`, `weight_trend`, `body_comp`, `body_measurements_range`.

---

## 6. Garmin Connectors

| Connector | Cron | Tabela |
|---|---|---|
| `import_garmin_sleep.py` | */15 5-8 | `qbot_v2.sleep_daily` |
| `import_garmin_energy.py` | */15 5-8 + co 2h 9-23 | `qbot_v2.energy_daily` + `qbot_v2.daily_summary` |
| `import_garmin_training.py` | */15 9-23 | `qbot_v2.training_sessions` |
| `import_garmin_body.py` | 07:30 | `qbot_v2.body_measurements` |
| Hammerhead→Garmin sync | */10 | activity upload |

---

## 7. Trasy / RWGPS

Workflow: `pobierz trasę [id]` → fetch z RWGPS → przetwórz → zapis do `/opt/qbot/artifacts/routes/`.
Upload: `wyślij trasę [id] potwierdź` → upload z nową nazwą `[oryginalna] | QBot YYYY-MM-DD HH:MM`.
Climbs: min 100m długości, min 5m gain, min 1% grade. Kategorie: lekki/średni/trudny.
POI: OSM Geofabrik → cache JSON → selekcja → Google Places verify → opcjonalny push do RWGPS.

---

## 8. Telegram

Telegram jest interfejsem do QBot — natural language przechodzi przez `qbot.query`.
Write intents generują `action_draft` → InlineKeyboard → potwierdzenie MS → `qbot.action_execute`.

Komendy bezpośrednie: `/today`, `/reminders`, `/help`, `/start`, `/status`.

---

## 9. Bezpieczeństwo zapisów

Każda mutacja wymaga:
- `action_type` z allowlisty
- `confirm=true`
- `idempotency_key`
- audit trail

Allowlista: `nutrition_log_add`, `qcal_reminder_add`, `qcal_event_add`, `qcal_event_update`, `qcal_event_cancel`, `planning_fact_add`, `decisions_log_add`, `qbot_doc_append`, `qbot_doc_replace_section`, `qbot_doc_update`.

---

## 10. Rzeczy zakazane

- Dodawanie publicznych MCP tooli bez zgody MS
- Patchowanie kodu po omacku
- Uznawanie zapisu za wykonany bez śladu w DB/logach
- Wykonywanie zapisu bez `confirm=true`
- Mieszanie QBot z QExt2/Karoo
- Powtarzanie tej samej naprawy bez wpisu do KNOWHOW

## 11. Artifact Shelves

Artefakty sa skladowane w /opt/qbot/artifacts/ z podziałem na polki:

| Polka      | Sciezka                              | Zapis QBot        | Cel                        |
|------------|--------------------------------------|-------------------|----------------------------|
| wip/       | artifacts/wip/<project>/<subdir>/    | swobodny          | dane robocze, tymczasowe   |
| export/    | artifacts/export/<project>/<subdir>/ | confirm=true      | GPX gotowe do eksportu     |
| canonical/ | artifacts/canonical/<project>/<sub>/ | confirm=true      | potwierdzone zrodlo prawdy |
| old/       | artifacts/old/                       | zablokowany       | archiwum (kosz)            |

### qbot_artifact_put — pole shelf

Nowe obowiazkowe pole w payloadzie:
  shelf: wip | export | canonical   (domyslnie: wip)

Bez shelf lub shelf=wip — zapis swobodny.
shelf=export lub shelf=canonical — wymaga confirm=true, inaczej BLOCKED.

Odpowiedz sukcesu zawiera: artifact_path, shelf, relative_path.

### artifact_search — shelf filter

Pytania naturalne:
  artefakty canonical tuscany  ->  filtruje file_path LIKE /artifacts/canonical/%
  artefakty wip                ->  filtruje file_path LIKE /artifacts/wip/%
  shelf:export                 ->  explicit filter

Wyswietlane pole polka: <shelf> w kazdym wyniku.
