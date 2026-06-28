# QBot Universal Query Router

## Plik
`/opt/qbot/app/qbot_query_router.py`

## MCP Tool
```
qbot.query({
  query: string,             // dowolne pytanie NL
  scope?: "all" | "project" | "garage" | "nutrition" | "training" | "routes",
  max_rows?: number,         // default 500
  include_provenance?: bool, // default true
  include_missing?: bool     // default true
})
```

## Jak działa

```
User query → classify_intent() → wybierz readery → wykonaj → zbuduj odpowiedź
```

1. **Klasyfikacja intencji** — regex keyword matching na query → lista intencji
2. **Wybór readerów** — mapowanie intencja → lista allowlisted readerów
3. **Wykonanie** — każdy reader = istniejąca funkcja `_tool_qbot_*`, READ_ONLY
4. **Odpowiedź** — ustrukturyzowany JSON z provenance, confidence, missing

## 36 readerów w 13 kategoriach

| Kategoria | Readery |
|---|---|
| nutrition | nutrition_day, nutrition_range, nutrition_food_search, meal_list, nutrition_status |
| wellness | wellness_day, sleep_day, nutrition_day_legacy, wellness_range, wellness_db_status |
| xert | xert_readiness, xert_config |
| intervals | intervals_wellness, intervals_config |
| weather | weather_current, weather_forecast, weather_config |
| rwgps | rwgps_route_get, rwgps_route_list, rwgps_route_search, rwgps_export_links, rwgps_config, rwgps_legacy_status |
| routes | gpx_artifact_parse, route_artifact_enrich, artifact_store_status |
| garage | garage_list, garage_search, garage_status |
| reports | daily_report_status, daily_report_preview, ride_report_status, ride_report_latest, ride_report_preview |
| garmin | garmin_status, garmin_dry_run |
| cronometer | cronometer_status |
| artifacts | artifact_list, artifact_read |
| meta | status, tool_policy, readiness, capability_scan |

## Format odpowiedzi

```json
{
  "tool": "qbot.query",
  "safety_class": "READ_ONLY",
  "status": "ok" | "partial" | "no_data",
  "query": "oryginalne pytanie",
  "intents_detected": ["nutrition_daily", "nutrition_range"],
  "readers_called": ["nutrition_day", "meal_list", ...],
  "answers_count": 4,
  "answers": [
    {"reader": "nutrition_day", "category": "nutrition", "status": "OK", "data": {...}},
    ...
  ],
  "provenance": [
    {"reader": "nutrition_day", "tool": "qbot_nutrition_day_summary", "providers": ["nutrition_db"], "status": "OK"}
  ],
  "missing_fields": [],
  "confidence": "high" | "medium" | "low",
  "limitations": [],
  "suggested_next_actions": []
}
```

## Testowane zapytania (wszystkie OK)

| Pytanie | Intencje | Wynik |
|---|---|---|
| "Pokaż mój bilans kalorii z ostatnich 7 dni" | nutrition_daily, nutrition_range | 4 answers, high |
| "Jaka jest pogoda w Markach" | weather | 3 answers, ok |
| "Znajdź ostatnią trasę RWGPS" | rwgps_route | 1 answer, partial (brak route_id) |
| "Jaki mam status Xert?" | xert | 2 answers, ok |
| "Czy QBot ma dane do odpowiedzi na to pytanie?" | capability_check | 2 answers, ok |
| "Pokaż ostatni raport dzienny" | daily_report | 2 answers, ok |

## Bezpieczeństwo

- Zero zapisów do DB
- Zero arbitrary shell
- Każdy reader = istniejąca allowlisted funkcja `_tool_qbot_*`
- Tylko READ_ONLY operacje
- Parametry wyciągane regexem z query, nie z arbitralnego inputu
- Path validacja dla artifact_read

## Rozszerzanie

Dodaj nowy reader:
1. `_reader("nazwa", "kategoria", "qbot_nazwa_narzedzia", {"param": "typ"}, ["provider"])`
2. `_INTENT_TO_READERS["nowa_intencja"] = ["reader1", "reader2"]`
3. `_INTENT_PATTERNS.append(("nowa_intencja", ["slowo1", "slowo2"]))`
4. Jeśli narzędzie jeszcze nie jest w `_TOOL_DISPATCH`, dodaj import
