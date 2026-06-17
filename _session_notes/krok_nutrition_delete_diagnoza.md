# Nutrition delete/correct diagnoza

Data: 2026-06-15

## 1) Istniejące funkcje DB do reużycia

W `qbot_nutrition_db.py` istnieją:

```python
def get_meal_log(meal_id: int) -> dict | None:
```

```python
def meal_log_list(date_str: str | None = None, limit: int = 20) -> list[dict]:
```

```python
def meal_log_delete(meal_id: int) -> dict | None:
```

```python
def daily_summary_compute(date_str: str) -> dict:
```

## 2) Main-track reference

W `qbot_mcp_adapter.py` istnieją gotowe wzorce:

```python
def _handle_nutrition_delete_preview(args: dict) -> dict[str, Any]:
```

```python
def _handle_nutrition_delete(args: dict) -> dict[str, Any]:
```

```python
def _action_exec_nutrition_delete(payload: dict, idem_key: str) -> dict:
```

```python
def _action_exec_nutrition_correct(payload: dict, idem_key: str) -> dict:
```

## 3) Proponowany payload schema

Delete:

```json
{"meal_id": int}
```

Correct:

```json
{
  "meal_id": int,
  "item_id": int,
  "meal_name": string,
  "kcal_total": number,
  "protein_g": number,
  "carbs_g": number,
  "fat_g": number
}
```

Uwagi:
- `meal_id` jest kluczem głównym.
- `meal_log_id` i `intake_log_id` są akceptowanymi aliasami backendu.
- `item_id` jest opcjonalny i pozwala skorygować konkretny element wpisu.

## 4) Czy Albert widzi ID wpisu

Tak.

`qbot3.tool_registry` ma:

```python
def _load_nutrition_day_summary_tool() -> dict[str, Any]:
```

```python
def _load_nutrition_meal_list_tool() -> dict[str, Any]:
```

`qbot_nutrition_tools._tool_qbot_nutrition_day_summary()` zwraca `meals`.
`qbot_nutrition_tools._tool_qbot_nutrition_meal_list()` zwraca:

- `meal_logs`
- `meal_log_items`
- `meal_log_id` dla pozycji w `meal_log_items`

`qbot_nutrition_db.meal_log_list()` zwraca dla każdej pozycji:

- `id`
- `date`
- `eaten_at`
- `items[]` z rekordami `qbot_v2.intake_items`

## 5) Wniosek

Schema jest jasna. Albert może najpierw użyć `nutrition_meal_list` albo `nutrition_day_summary`, odczytać `meal_id`, a potem wykonać `nutrition_log_delete` lub `nutrition_log_correct`.
