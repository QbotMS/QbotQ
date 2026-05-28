# Audyt architektury i funkcjonalności QBot

Data audytu: 2026-05-28  
Zakres: read-only, bez zmian w kodzie, bez restartów, bez commitów.

## Executive summary

- Publiczny MCP działa przez `qbot-api.service` na `127.0.0.1:8002` i jest wystawiany pod `https://qbot.cytr.us/mcp/` przez nginx.
- Aktualne publiczne `tools/list` pokazuje 5 narzędzi: `qbot.query`, `qbot.status`, `qbot.readiness`, `qbot.reminder_add`, `qbot.action_execute`.
- `qbot.query` jest routerem regułowym z LLM jako fallback do canonicalizacji, a nie czystym agentem LLM.
- `qbot.action_execute` jest jedynym publicznym executorem zapisów dla allowlisty 6 akcji.
- W repo widać niespójność architektury: `QBOT_MCP_URL` nadal domyślnie wskazuje na martwe `http://localhost:8000/mcp/`, a aktywny publiczny MCP działa na `8002`.

## Aktualna architektura

### Usługi i procesy

- `cron.service` aktywny.
- `nginx.service` aktywny.
- `qbot-api.service` aktywny, uruchamia FastAPI na `127.0.0.1:8002`.
- `qbot-qlab-server.service` aktywny, uruchamia QLab export HTTP server na `127.0.0.1:8899`.
- `q365.service` aktywny, nasłuchuje na `0.0.0.0:8001`.
- `qbot-backup.service` failed.
- `q-bot.service` loaded, ale inactive/dead.
- `qbot-mcp-bridge.service` inactive/dead.

### Porty

- `8002` - `qbot-api.service`, publiczny MCP i webhook proxy entrypoint.
- `8899` - `qbot-qlab-server.service`.
- `8898` - nginx static server dla map.
- `8001` - `q365.service`.
- `20181` - obecnie nie nasłuchuje.

### Nginx

- `/mcp/` proxy do `127.0.0.1:8002/mcp/`.
- `/telegram/webhook/` proxy do `127.0.0.1:8002/telegram/webhook/`.
- `/ride-readiness` proxy do `127.0.0.1:8002/ride-readiness`.
- `/gate/open` i `/gate/status` proxy do `127.0.0.1:8899`.
- `/.well-known/oauth-protected-resource` zwraca publiczny resource indicator dla `/mcp/`.

## Publiczne MCP tools

### Ustalony stan

Publiczny MCP jest obsługiwany bezpośrednio przez `qbot-api`, nie przez osobny upstream proxy-process.

### Lista tooli

1. `qbot.query`
   - opis: główne narzędzie do pytań o dane, zwraca structured answer + tables + provenance + missing_fields + limitations.
   - inputSchema: TAK
   - outputSchema: TAK
   - safety_class: `READ_ONLY`
   - mutuje dane: NIE
   - handler: `qbot_mcp_adapter.py` -> `_tool_qbot_query`, wewnętrznie `qbot_query_router.query`

2. `qbot.status`
   - opis: globalny smoke test QBot.
   - inputSchema: TAK
   - outputSchema: NIE
   - safety_class: `READ_ONLY`
   - mutuje dane: NIE
   - handler: `qbot_mcp_adapter.py` -> `_tool_qbot_operator_final_smoke_test` z `qbot_ops_tools.py`

3. `qbot.readiness`
   - opis: szczegółowy raport gotowości i blokad.
   - inputSchema: TAK
   - outputSchema: NIE
   - safety_class: `READ_ONLY`
   - mutuje dane: NIE
   - handler: `qbot_mcp_adapter.py` -> `_tool_qbot_readiness_report` z `qbot_operator_tools.py`

4. `qbot.reminder_add`
   - opis: bezpośredni wrapper do `qcal_reminder_add`.
   - inputSchema: TAK
   - outputSchema: TAK
   - safety_class: `WRITE_ONLY_ALLOWLIST`
   - mutuje dane: TAK
   - handler: `qbot_mcp_adapter.py` -> `_handle_reminder_add`, potem `_handle_action_execute`

5. `qbot.action_execute`
   - opis: uniwersalny executor dla action_draft z allowlisty.
   - inputSchema: TAK
   - outputSchema: TAK
   - safety_class: `WRITE_ONLY_ALLOWLIST`
   - mutuje dane: TAK
   - handler: `qbot_mcp_adapter.py` -> `_handle_action_execute`

### Upstream MCP

- Publiczny MCP nie wskazuje na osobny upstream backend.
- `qbot-api.py` sam wystawia `/mcp/`, `/mcp/health` i `/mcp/tools`.
- Lokalny klient MCP w `qbot_mcp_client.py` nadal domyślnie używa `QBOT_MCP_URL=http://localhost:8000/mcp/`, co jest niespójne z aktualnym listenem.

## Action types i możliwości zapisu

### Allowlista

- `nutrition_log_add`
- `qcal_reminder_add`
- `qcal_event_add`
- `qcal_event_update`
- `qcal_event_cancel`
- `planning_fact_add`

### Walidacja

- `confirm` musi być `true`.
- `idempotency_key` jest wymagany.
- `action_type` musi być na allowliście.
- `payload_json` musi być obiektem.
- Wymagane pola są sprawdzane per action_type.

### `dry_run`

- Zwraca `DRY_RUN`.
- Nie wykonuje zapisu.

### Idempotency i audit

- `nutrition_log_add` sprawdza `nutrition_write_audit`.
- QCal actions sprawdzają `qcal_write_audit`.
- Stale audit entries mogą zostać usunięte, jeśli rekord już nie jest aktywny.

### Realne zapisy

- `nutrition_log_add` zapisuje do nutrition store i aktualizuje daily summary.
- `qcal_reminder_add` zapisuje do `reminders`.
- `qcal_event_add` zapisuje do `calendar_events`.
- `qcal_event_update` aktualizuje `calendar_events`.
- `qcal_event_cancel` ustawia `calendar_events.status='cancelled'`.
- `planning_fact_add` zapisuje do `qbot_planning_facts`.

## QBot query

### Jak działa

- Najpierw działa `classify_intent()`, która dopasowuje wzorce tekstowe i regexy.
- Potem działa `canonicalize_query_intent()`, która może użyć LLM przez `qgpt_json()`.
- Jeśli canonicalizer zwróci match, router może użyć forced readers.
- Dla write intents router nie zapisuje, tylko generuje `action_draft`.

### Intenty i domeny

Obsługiwane obszary:

- nutrition
- training
- routes / RWGPS
- garage
- weather
- wellness
- calendar / QCal
- planning facts
- artifacts
- status / readiness

### Reader selection

- Reader mapping jest w `_INTENT_TO_READERS`.
- `scope` może ograniczać wybór domen.
- Dla niektórych intentów canonicalizer może wymusić konkretną listę readerów.

### Action draft

- Dla write intents tworzy draft z:
  - `action_type`
  - `writer_capability`
  - `requires_confirm`
  - `idempotency_key`
  - `payload`
- Draft jest tylko propozycją; zapis następuje dopiero przez `qbot.action_execute`.

### Główne funkcje

- `classify_intent()`
- `canonicalize_query_intent()`
- `_llm_classify_intent()`
- `query()`
- `_handle_write_draft()`
- `_tool_qbot_query()`

## Telegram

### Aktualna architektura

- Gateway do Telegrama jest w `qbot_qcal_telegram.py`.
- Token i allowlist chatów są czytane z:
  - `TELEGRAM_TOKEN` / `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_ALLOWED_CHAT_IDS` / `TELEGRAM_ALLOWED_CHAT_ID`

### Wejście publiczne

- Webhook trafia do nginx i dalej do `qbot-api` na `8002`.
- `qbot_telegram_client.py` obsługuje też API Telegrama i ustawianie webhooka.

### Co potrafi

- Odpowiada na `/today`, `/reminders`, `/help`, `/start`, `/status`.
- Natural language przechodzi przez `qbot.query`.
- Jeśli `action_draft` jest na allowliście, tworzy pending action i wymaga potwierdzenia.

### Ograniczenia

- Tylko 3 akcje zapisowe są dozwolone przez Telegram: `nutrition_log_add`, `qcal_reminder_add`, `qcal_event_add`.
- Potwierdzenie jest wymagane.
- Telegram nie ma arbitralnego dostępu do publicznych tooli.

## QCal/reminders/calendar

### Funkcje zapisu

- `qcal_event_add_controlled()`
- `qcal_event_update_controlled()`
- `qcal_event_cancel_controlled()`
- `reminder_create()`

### Parser przypomnień

- Draft parsing i date resolution siedzą w `qbot_query_router.py`.
- Telegram korzysta z `qbot.query`, a nie z osobnego „centrum decyzyjnego”.

### Tabele

- `calendar_days`
- `calendar_daily_snapshots`
- `calendar_events`
- `reminders`
- `reminder_channels`
- `import_jobs`

### Jak sprawdzić zapis

- `qcal_write_audit`
- `calendar_events`
- `reminders`
- `calendar_daily_snapshots`

## DB/audit

### Istotne tabele

- `tool_calls`
- `calendar_days`
- `calendar_daily_snapshots`
- `calendar_events`
- `reminders`
- `reminder_channels`
- `import_jobs`
- `food_items`
- `meal_logs`
- `meal_log_items`
- `hydration_events`
- `fueling_events`
- `nutrition_daily_summary`
- `meal_templates`
- `nutrition_day_plans`
- `nutrition_day_plan_meals`
- `qbot_wellness_daily`
- `qbot_sleep_daily`
- `qbot_nutrition_daily`
- `qbot_wellness_notes`
- `qbot_import_runs`
- `qbot_plans`
- `qbot_artifacts`
- `qbot_memory`
- `qbot_planning_facts`
- `telegram_conversations`
- `telegram_conversation_turns`
- `telegram_pending_actions`
- `nutrition_write_audit`
- `qcal_write_audit`

### Najważniejsze kolumny

- `reminders`: `id`, `date`, `time`, `timezone`, `title`, `message`, `reminder_type`, `status`, `recurrence_rule`, `related_entity_type`, `related_entity_id`, `channel`, `metadata_json`, `created_at`, `updated_at`
- `calendar_events`: `id`, `date_start`, `date_end`, `event_type`, `title`, `description`, `status`, `source`, `external_ref`, `metadata_json`, `affects_training`, `affects_nutrition`, `affects_health_advice`, `created_at`, `updated_at`
- `qbot_planning_facts`: `id`, `date`, `channel`, `source_query_text`, `source_query_hash`, `fact_type`, `status`, `confidence`, `title`, `fact_json`, `related_event_id`, `related_training_session_id`, `valid_from`, `valid_until`, `created_at`, `updated_at`

## Mapa plików i funkcji

- `qbot_api.py`: publiczne MCP endpointy.
- `qbot_mcp_adapter.py`: mapowanie tooli, safety, dispatch, write executor.
- `qbot_query_router.py`: intent routing, canonicalization, draft generation, planning facts.
- `qbot_calendar_core.py`: event/reminder CRUD i snapshot builder.
- `qbot_qcal_telegram.py`: Telegram gateway i pending confirm flow.
- `qbot_telegram_client.py`: Telegram Bot API helper.
- `qbot_mcp_client.py`: lokalny klient MCP.
- `qbot_config.py`: `QBOT_MCP_URL`.
- `api_db.py`: bootstrap SQL files.
- `qbot_planning_memory.py`: planning facts.

## Co działa

- Publiczny MCP `/mcp/` działa lokalnie na `8002`.
- `tools/list` zwraca 5 tooli.
- `qbot.query` działa dla czytania i draftów zapisów.
- `qbot.action_execute` wykonuje allowlistowane zapisy.
- Telegram ma działający flow confirm/decline.
- QCal zapisuje i audytuje zmiany.

## Co nie jest potwierdzone

- Dokładne miejsce i polityka przechowywania Telegram webhook secret.
- Przyczyna `public_mcp_reachable: false`.
- Czy publiczny MCP ma pozostać przy 5 toolach, czy wrócić do 2.
- Czy `q365.service` ma być utrzymywany jako osobna produkcyjna ścieżka.

## Długi techniczne

- `QBOT_MCP_URL` wskazuje na `8000`, mimo że aktywny publiczny MCP działa na `8002`.
- Publiczny MCP ma 5 tooli, co przeczy wcześniejszej zasadzie „dwóch publicznych tooli”.
- W working tree są zmiany i backupy wokół `qbot_mcp_adapter.py`.
- `qbot-backup.service` jest failed.
- W repo są liczne `.bak` i stare backupy konfiguracyjne, które zaciemniają obraz architektury.

## Rekomendacje do `QBOT_BIBLE.md`

- Ustalić i opisać prawdziwy publiczny MCP: `qbot-api` + nginx `/mcp/`.
- Zdefiniować granicę między `qbot.query` i `qbot.action_execute`.
- Opisać confirm, dry_run, idempotency i audit jako obowiązkowy wzorzec zapisu.
- Opisać, że `qbot.query` jest rule-first, z LLM fallback tylko do canonicalizacji.

## Rekomendacje do `QBOT_KNOWHOW.md`

- Dodać mapę portów i usług.
- Dodać mapę tabel DB i audit tables.
- Dodać flow Telegram: webhook -> `qbot-api` -> `qbot.query` -> pending action -> writer.
- Dodać procedurę weryfikacji zapisów przez audit i target table.
- Dodać ostrzeżenie, że `QBOT_MCP_URL` nie może wskazywać martwego `8000`.

## Pytania do MS

- Czy publiczny MCP ma zostać zredukowany do 2 narzędzi?
- Czy `QBOT_MCP_URL` powinien zostać naprawiony na `127.0.0.1:8002/mcp/`?
- Czy `qbot-api` ma być jedynym publicznym MCP entrypointem?
- Gdzie ma formalnie żyć Telegram webhook secret?
- Czy chcesz, żebym przygotował na tej bazie `QBOT_BIBLE.md` i `QBOT_KNOWHOW.md`?

