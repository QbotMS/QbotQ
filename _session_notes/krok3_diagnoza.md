# Krok 3 diagnoza - Albert-first routes

Data diagnozy: 2026-06-15

## 1) Co zawiera `plan_routes()` i jego toolset

`core/planner.py` nie buduje osobnego route-routera. Wrapper:

```python
def plan_routes(question: str) -> dict[str, Any]:
    return _normalize_route_links(_plan_routes_impl(question))
```

Toolset jest skladany w `_load_route_tools()` przez:

```python
from qbot3.tool_registry import tool_descriptions, lookup
from modules.routes.manifest import MANIFEST
allowed_names = set(MANIFEST.get("planner_tools", []))
filtered = [t for t in all_tools if t["name"] in allowed_names]
```

Aktualny allowlist route plannera z `modules/routes/manifest.py`:

```python
"planner_tools": [
    "rwgps_route_find", "rwgps_route_list", "rwgps_route_fetch",
    "rwgps_route_last", "rwgps_route_import_gpx",
    "route_poi_analyze", "route_stage_plan_analyze", "stage_gpx_analyze",
    "rwgps_route_surface_analyze",
    "artifact_search", "artifacts_list", "artifact_save",
    "planning_facts", "planning_fact_lookup", "weather_forecast",
],
```

W praktyce `plan_routes()` korzysta z tooli:

- `rwgps_route_find`
- `rwgps_route_list`
- `rwgps_route_fetch`
- `rwgps_route_last`
- `rwgps_route_import_gpx`
- `route_poi_analyze`
- `route_stage_plan_analyze`
- `stage_gpx_analyze`
- `rwgps_route_surface_analyze`
- `artifact_search`
- `artifacts_list`
- `artifact_save`
- `planning_facts`
- `planning_fact_lookup`
- `weather_forecast`

## 2) Co juz istnieje w `qbot3/tool_registry.py`

Potwierdzone loaderi i sygnatury:

```python
def _load_planning_fact_lookup_tool() -> dict[str, Any]:
    return _load_planning_facts_tool()
```

```python
def _load_rwgps_route_fetch_tool() -> dict[str, Any]:
```

```python
def _load_route_stage_plan_analyze_tool() -> dict[str, Any]:
```

```python
def _load_stage_gpx_analyze_tool() -> dict[str, Any]:
```

```python
def _load_rwgps_route_surface_analyze_tool() -> dict[str, Any]:
```

```python
def _resolve_stage_from_planning_facts(
    project_id: str | None, stage: int
) -> dict[str, Any] | None:
```

```python
def _load_route_poi_analyze_tool() -> dict[str, Any]:
```

W `_init_registry()` te narzedzia sa juz wpisane do registry:

```python
("rwgps_route_fetch", _load_rwgps_route_fetch_tool),
("route_stage_plan_analyze", _load_route_stage_plan_analyze_tool),
("stage_gpx_analyze", _load_stage_gpx_analyze_tool),
("rwgps_route_surface_analyze", _load_rwgps_route_surface_analyze_tool),
("rwgps_route_last", _load_rwgps_route_last_tool),
("route_poi_analyze", _load_route_poi_analyze_tool),
("artifact_search", _load_artifact_search_tool),
("artifacts_list", _load_artifacts_list_tool),
("artifact_save", _load_artifact_save_tool),
("planning_facts", _load_planning_facts_tool),
("planning_fact_lookup", _load_planning_fact_lookup_tool),
("weather_forecast", _load_weather_forecast_tool),
```

## 3) Klasyfikacja

### (a) Albert juz ma

- `route_poi_analyze`
- `stage_gpx_analyze`
- `rwgps_route_surface_analyze`
- `planning_facts`
- `planning_fact_lookup`
- `rwgps_route_fetch`
- `rwgps_route_last`
- `route_stage_plan_analyze`
- `artifact_search`
- `artifacts_list`
- `artifact_save`
- `weather_forecast`
- stage-invariant resolver: `_resolve_stage_from_planning_facts(...)`

### (b) Tylko w `core/planner.py`, a Albert nie ma

W aktualnym stanie repo nie znalazlem osobnych route-toolow z tej grupy jako brakujacych dla Alberta pod aktualnymi nazwami. `qbot3/tool_registry.py` juz zawiera wszystkie route-tooli, ktore sa wlaczane do `plan_routes()` przez manifest.

Jednoczesnie, po grepie po zadanych nazwach historycznych:

- `route_fetch_gpx` - brak jako exact name
- `route_profile` - brak jako exact name
- `planning_fact_get` - brak jako exact name
- `planning_fact_update` - brak jako exact name

### (c) Czy `core/planner.py` importuje cos z `qbot3/tool_registry.py`

Tak. `core/planner.py` importuje:

```python
from qbot3.tool_registry import tool_descriptions, lookup
```

To znaczy, ze `plan_routes()` juz wspoldzieli kod registry zamiast miec osobny, niezalezny zestaw definicji tooli.

## 4) Wniosek operacyjny

Krok 3 nie wymaga kopiowania route-tooli do Alberta pod aktualnymi nazwami. Na teraz problemem nie jest brak tooli w registry, tylko ewentualnie routing do Alberta vs osobny orchestrator oraz ewentualne aliasy historycznych nazw.

