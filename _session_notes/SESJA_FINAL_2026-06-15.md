# Sesja 2026-06-15 - podsumowanie finalne

## Branch: feature/router-v2-planner-v2-and-fixes
## Ostatni commit bazowy: c7a7cce

## ZREALIZOWANE I ZWERYFIKOWANE (bezpieczne, w produkcji)

- Krok 5 porządki: reminders, /help, fallback_policy (07ca7b7, b223d0e, 0dec288, e2afad2)
- Hotfix crashloop (0205f9a)
- Bootstrap `.env` (5c6dc3d) - Weather/Xert naprawione, 52->65 PASS
- Test truskawek (b68b45f) - 66/0/1
- `route_poi_analyze_readonly` (b1bb352) + permission fix (9e8cd03)
- TOP PRIORITY: tool_choice="required" petla read-only NAPRAWIONA (f5e28be) - zweryfikowane end-to-end przez `/mcp/`, xert/nutrition/POI dzialaja w 1-2 krokach
- Krok 10: "bilans tygodnia" -> `nutrition_range` (053bfef)
- Krok 11: multi_intent hijack guard dla `write_meal` (9167d6b)

## NOWE ODKRYCIA Z DZISIEJSZEJ DIAGNOZY

### Odkrycie A - mozliwy artefakt metodologii testu, nie potwierdzony bug produkcyjny

- W lokalnym wywolaniu `nutrition_write_resolve(fn({'description': ...}))` wynik byl taki sam dla `brokul sport` i `100g jablka`:
  - `template_id=8`
  - `meal_name="Białko / owsiane"`
  - `225 kcal`
- Ale prawdziwy Albert w logged runie uzywa `query`, nie `description`:
  - `{"query":"brokul sport","payload":{}}`
- Wcześniejsze testy przez prawdziwy `/mcp/` dla `100g jablka` i `50g banana` zwracały poprawne wartości, wiec to wyglada na falszywy alarm z blednej metodologii testu.
- Status na dzisiaj: DO WERYFIKACJI w nowej sesji jako pierwsze zadanie.

### Odkrycie B - niedeterminizm write flow dla `brokul sport`

- Dla tego samego inputu w tej samej sesji zobaczylem dwa rozne wyniki:
  - `status=partial`, 12 kroków, koncowka z 3x `nutrition_write_resolve`
  - `status=OK`, 4 kroki, sekwencja `nutrition_log_add -> nutrition_write_resolve -> nutrition_log_add`
- Drugi logged run pokazal, ze `nutrition_log_add` zostal wywolany z `kcal_total=0`.
- Uwaga: podczas diagnozy testowo powstaly wpisy w `qbot_v2.intake_logs`; usunalem tylko swoje rekordy z tej sesji (`117-122`, `126-127`). Rekord `123` zostawilem, bo mial inny `source`.

## DBA / cleanup po diagnozie

- Aktualny szybki check `qbot_v2.intake_items` dla `2026-06-15`, z filtrem na `brok` lub `kcal=0`, nie zwrocil zadnych wierszy.
- To oznacza, ze w `intake_items` nie zostaly dzisiaj oczywiste smieci do sprzatania po tej konkretnej diagnozie.

## NOWE TODO dla nastepnej sesji

1. **Odkrycie A** - zweryfikowac, czy `nutrition_write_resolve` ma bug z parametrem, czy to tylko artefakt testu. To jest pierwsze zadanie nowej sesji.
2. **Odkrycie B** - sprawdzic, czy w `intake_items` lub `intake_logs` zostal jakis ślad `brokul sport` / `kcal_total=0` z dzisiaj i ewentualnie wyczyscic go oraz przeliczyc `daily_summary`.
3. **Fix 2 (template_lookup)** - nadal otwarte; `meal_templates` lookup nieosiagalny z `qbot.query`, 14 testow w benchmarku czeka.
4. **Fix 3 (potencjalny)** - jesli po Fix 2 `brokul sport` dalej wpada w petle, dodac `_needs_forced_final_answer` po N nieudanych probach.
5. Krok 3b/1b - przełączenie Router v2 dla profilu etapu na Albert - gotowe, ale nie zrobione.
6. `core/planner.py` usuniecie - blokowane przez 5.
7. Drobne: niespojnosc intentu dla surface query, redundancja `route_poi_analyze_readonly`.

## Stan repo

- Branch: `feature/router-v2-planner-v2-and-fixes`
- Seria nadal nie jest zmergowana do `main`
- Acceptance: `66/0/1`
- Serwis: `active`, `NRestarts=0`

## Rekomendacja na start nastepnej sesji

- Zadanie 0 = Odkrycie A.
- Dopiero po tym decydowac, czy Fix 2 ma wyzszy priorytet, czy resolver jest juz poprawny a problem lezy tylko w braku template lookup.
