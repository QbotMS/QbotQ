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
