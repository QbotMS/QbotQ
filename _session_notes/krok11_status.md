# Krok 11 - status

## Fix 1: multi_intent hijack guard

W `qbot_query_handler.py` multi-intent hijack został ograniczony do węższego zbioru write-intentów przez:

- `_MULTI_INTENT_HIJACK_EXEMPT = {"write_meal", "write_delete_meal", "write_planning_unsupported", "write_weight_unsupported"}`
- warunek:
  - `if len(domains) >= 2 and intent not in _MULTI_INTENT_HIJACK_EXEMPT:`

Efekt:

- write query `dodaj do dzis dieta brokul sport` nie wpada już w `multi_intent`
- `handle_query(...)` zwraca `write_meal`

## Walidacja regresji

- `jak mi idzie z dieta i treningiem`
  - `_resolve_intent` -> `training_recent`
  - final intent -> `multi_intent`
- `pokaz bilans i ostatnie treningi`
  - `_resolve_intent` -> `daily_balance`
  - final intent -> `multi_intent`

To oznacza, że prawdziwe multi-domain queries nadal trafiają do `_handle_multi_intent`.

## Acceptance

- `66 passed`
- `1 skipped`
- `0 failed`

## Restart / serwis

- `qbot-api`: `active`
- `NRestarts`: `0`
- po 10 s nadal `0`

## Smoke przez `/mcp/`

Oryginalne zapytanie:

- `dodaj do dzis dieta brokul sport`

Wynik przez `/mcp/`:

- `status: partial`
- `answer`: `Przekroczono limit 12 kroków...`
- `tool_results` pokazuje powtarzany `nutrition_write_resolve`
- to **nie** jest multi_intent hijack
- to osobny problem lookup/template, czyli `Fix 2` z TODO

## Commit

- Hash kodu: `9167d6b`

## Wniosek

Fix 1 działa: write-intent nie jest przechwytywany jako multi_intent, a prawdziwe multi-domain queries nadal trafiają do multi_intent.
