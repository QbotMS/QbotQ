# QBot — Kontekst projektu (auto-generowany)
_Wygenerowano: 2026-06-26 17:03:39 CEST. NIE edytuj recznie — plik tworzy scripts/build_context.py._
## Zakres
Pracujemy WYLACZNIE nad rdzeniem QBota (qbot-api, qbot-mcp, qbot-dev-mcp, qbot-qlab-server). QExt2 to OSOBNY projekt — nie mieszac.
## Stan na zywo
- Branch: main
- HEAD: 717b061 qbot-web: publiczny serwis HTML (Faza 1, port 30181)
- Uslugi: qbot-api=active, qbot-mcp-bridge=active, qbot-dev-mcp=active, qbot-qlab-server=active
## Architektura (skrot — kanon ponizej, ZAWSZE weryfikuj na zywo)
- Publiczny kanal MCP jest swiadomie 2-narzedziowy: qbot.query (odczyt) oraz qbot.action_execute (jedyny executor zapisow). Narzedzia domenowe sa internal, dostepne tylko przez action_execute.
- Aktywny handler MCP dla Claude: qbot3/adapters/mcp_adapter.py (handle_qbot3_mcp, QBOT3_ENABLED=1). app/qbot_mcp_adapter.py to ODDZIELNY adapter konektora ChatGPT — nie mylic.
- Routing (Claude/MCP): qbot.query -> qbot3/adapters/mcp_adapter.py; przy QBOT_QUERY_VNEXT_ENABLED=1 najpierw qbot_query_handler.handle_query (deterministyczny, keyword/intent: domeny zamkniete zywienie/kalendarz/przypomnienia). UNRECOGNIZED -> ALBERT (qbot3.agent_runtime.orchestrate_query) = natywny tool-calling agent LLM, narzedzia z qbot3/tool_registry.py.
- Domena TRAS: QBOT_ROUTES_VIA_ALBERT=1 => trasy obsluguje ALBERT, narzedzia: route_plan_analysis (analiza/podsumowanie ZAPLANOWANEJ trasy), route_profile_detail (SZCZEGOLOWY profil zaplanowanej trasy z ramek: nawierzchnia odcinkami + wysokosci po km + podjazdy) i ride_analysis (ocena WYKONANEJ jazdy/FIT). UWAGA: Planner v2 / core/planner.py dla tras NIE ISTNIEJE — wczesniejszy zapis byl bledny (kasowac przy edycji). Inne fronty (ChatGPT: qbot_mcp_adapter+qbot_query_router; Telegram) maja wlasny routing/rejestr.
- Kanon (czytaj zamiast zgadywac): docs/architecture/QBOT_ARCHITEKTURA_V2.md oraz PROJECT_STATE.md (repo root). Gdy dokument rozjezdza sie z kodem — wygrywa zywy system.
- WEB/RAPORT: publiczny raport trasy serwuje qbot-web (FastAPI, qbot_web.py, port 30181, root /opt/qbot/web/public). Jak modelowac i wdrazac raport HTML: docs/RAPORT_WEB.md. Wdrazaj przez dev_write_file (bajt-w-bajt), NIE heredoc/codex (psuja base64).
## Jak pracowac
- Po polsku, bezposrednio, bez spekulacji. Brak danych → sprawdz przez DEV MCP, nie zgaduj.
- OBOWIAZKOWO (twarda regula): kazda zmiana narzedzi (dodanie/zmiana/usuniecie w qbot3/tool_registry.py) LUB nowej domeny/intencji MUSI byc w TYM SAMYM kroku odzwierciedlona w prompcie Alberta (_SYSTEM w qbot3/llm/albert.py) — ktore narzedzie do czego i kiedy. Bez aktualnego promptu Albert nie wie ze narzedzie istnieje i myli intencje. Zmiana narzedzia bez aktualizacji promptu = NIEUKONCZONA. Opisy narzedzi trzymaj < 500 znakow (build_tools_spec obcina).
