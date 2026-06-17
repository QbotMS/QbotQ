# Krok nutrition tool choice smoke

Data: 2026-06-15

## Zmiana
- `qbot3/llm/albert.py`: dodana krótka sekcja rozróżniająca `nutrition_log_delete` i `nutrition_log_correct`.
- `qbot3/tool_registry.py`: doprecyzowane opisy obu narzędzi, żeby `delete` i `correct` nie brzmiały zbyt podobnie.

## Smoke 1: delete
- Wysłane do `qbot.query`: `usuń wpis mandarynka testowa z dzisiejszego dziennika żywienia`
- Efekt w bazie: po wpisie testowym `mandarynka testowa` zostało `0` wierszy dla `2026-06-15`.
- Wniosek: Albert wybrał ścieżkę fizycznego delete, nie `nutrition_log_correct`.

## Smoke 2: correct
- Wysłane do `qbot.query`: `popraw kiwi testowe na 45 kcal`
- Efekt w bazie: wpis `kiwi testowe` pozostał, a `kcal` zmieniło się z `42` na `45`.
- Wniosek: Albert wybrał `nutrition_log_correct` i nie usunął wiersza.

## Czystość bazy
- Po testach dla `2026-06-15` nie zostały żadne testowe wpisy `mandarynka` ani `kiwi`.
