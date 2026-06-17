# Krok 10 - status końcowy

## A. `balance_kcal = null` dla dziś

Rozstrzygnięte jako **zamierzone**.

- Dane są liczone o 09:00 następnego dnia po pełnych danych Garmina.
- To nie jest problem tego zadania.
- Potwierdzone w DB dla wcześniejszych dni, gdzie `balance_kcal` jest już wypełnione.

## B. `bilans tygodnia` -> `nutrition_range`

Naprawione.

- Dodano bardziej precyzyjny wpis przed `daily_balance`:
  - `bilans tygodnia`
  - `bilans tygodniowy`
  - `tygodniowy bilans`
  - `bilans za tydzień`
  - `bilans za tydzien`
- Dzięki first-match routing trafia teraz do `nutrition_range`, a zwykłe:
  - `ile kcal dzis zjadlem`
  - `jaki jest bilans`
  - nadal trafiają do `daily_balance`

## Walidacja

- `_resolve_intent`:
  - `jaki jest moj bilans tygodnia` -> `nutrition_range`
  - `bilans tygodniowy` -> `nutrition_range`
  - `ile kcal dzis zjadlem` -> `daily_balance`
  - `jaki jest bilans` -> `daily_balance`
- `handle_query("jaki jest moj bilans tygodnia")`:
  - `intent: nutrition_range`
  - odpowiedź pokazuje zakres 7 dni, nie pojedynczy dzień
- acceptance:
  - `66 passed`
  - `1 skipped`
  - `0 failed`

## Stan serwisu

- `qbot-api`: `active`
- `NRestarts`: `0`
- po 10 s nadal `0`

## Commit

- Hash: `bdc18d7`

## Wniosek

Routing `bilans tygodnia` / `bilans tygodniowy` jest poprawny i nie psuje zwykłego `daily_balance`.
