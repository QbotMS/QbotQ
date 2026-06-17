TODO: planning_fact_update/add jako narzedzia Alberta - osobne zadanie

TODO refs for later cleanup: `qbot_mcp_adapter.py` nadal zawiera trzy stare
wywolania `core.planner.plan_routes()`, a `qbot_query_handler.py` nadal ma
jeden routing do `plan_routes()` i jeden import `set_active_provider`.

Stan z 2026-06-15:
- `grep -n "from core\\.planner|core\\.planner" qbot3/adapters/mcp_adapter.py`
  -> brak wynikow.
- `rg -n "plan_routes|core\\.planner" .`
  -> trafienia nadal sa w testach, helperach patchujacych, `qbot_query_handler.py`,
  `qbot_mcp_adapter.py`, `core/planner.py` i notatkach diagnostycznych.
