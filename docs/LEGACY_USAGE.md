# Licznik uzycia starej warstwy QBota (15.10.2026)

Cel: wyciac stary lacznik ChatGPT (`qbot_mcp_adapter.py`) i nieuzywane czesci warstwy sprzed Alberta (~21 tys. linii)
NA DOWODACH, nie na oko. Statycznie nie da sie stwierdzic, co jest wolane (Telegram, stare adresy qbot-api, cron).

- `qbot_legacy_usage.py`: na koncu 19 modulow starej warstwy `instrument(globals())` owija funkcje (i podmienia je w rejestrach modulu);
  `qbot_api.py` middleware zapisuje adresy HTTP. Zapis: `logs/legacy_usage.log` (ta sama nazwa najwyzej raz/h na proces).
- Testy i narzedzia audytu sie nie licza (pytest, run_test_file, audit_*, _tmp_*). Wylaczenie: `QBOT_LEGACY_USAGE=0`.
- Podglad: `.venv/bin/python3 qbot_legacy_usage.py` albo SETUP > Polaczenia > Status (pozycja "Stary QBot").
- Moduly: qbot_mcp_adapter, qbot_legacy_* (7), qbot_tool_registry, qbot_tools, qbot_orchestrator, qbot_llm_planner, qbot_query_router,
  qbot_query_processor, qbot_query_planner, qbot_external_llm_tools, qbot_operator_tools, qbot_ops_tools, qbot_roadmap_runner.

## 22.10.2026 -- decyzja
Wyciac lacznik ChatGPT + wszystko z listy, czego licznik nie zobaczyl; uzywane funkcje przeniesc tam, gdzie ich miejsce.
Potem usunac licznik (linie `_legacy_usage_instrument` i middleware) i sprawdzic na zywo Alberta, strone, Telegram.
