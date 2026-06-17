# Krok 11 - diagnoza petli `brokul sport`

Data testu: 2026-06-15
Branch: `feature/router-v2-planner-v2-and-fixes`
Commit bazowy: `9167d6b`

## ZADANIE 1 - co zwraca `nutrition_write_resolve`

`nutrition_write_resolve` dla:

- `brokul sport`
- `dieta brokul sport`
- `100g jablka`

zwraca w obecnym stanie ten sam ksztalt wyniku:

- `status: "OK"`
- `resolved: true`
- `lookup_required: false`
- `source_kind: "template"`
- `payload.meal_name: "Białko / owsiane"`
- `payload.template_id: 8`
- `payload.kcal_total: 225.0`
- `payload.protein_g: 24.0`
- `payload.carbs_g: 20.0`
- `payload.fat_g: 3.5`
- `resolution_notes: ["template:Białko / owsiane", "direct_template"]`

Wniosek: resolver nie zwraca tu `not_found` ani pustego wyniku. Dla tego wejscia dziala twarde dopasowanie do `Białko / owsiane`, nawet dla `100g jablka`.

## ZADANIE 2 - `_tool_result_has_meaningful_data`

Dla wyniku `nutrition_write_resolve({'description': 'brokul sport'})`:

- `status: OK`
- `_tool_result_has_meaningful_data(...) == True`

Czyli hipoteza, ze ten wynik wyglada dla Alberta jak `brak danych`, nie potwierdzila sie.

## ZADANIE 3 - sekwencja `orchestrate_query`

Dwukrotnie sprawdzilem ten sam query:

1. Jeden run zakonczyl sie:
   - `status: partial`
   - odpowiedz: `Przekroczono limit 12 kroków...`
   - ostatnie tool-e: `['nutrition_write_resolve', 'nutrition_write_resolve', 'nutrition_write_resolve']`

2. Drugi run z logowaniem tool-call args zakonczyl sie:
   - `status: OK`
   - `steps: 4`
   - tool sequence:
     - `nutrition_log_add` args: `{"date":"2026-06-15","meal_name":"brokul sport"}`
     - `nutrition_write_resolve` args: `{"query":"brokul sport","payload":{}}`
     - `nutrition_log_add` args: `{"meal_name":"brokul sport","date":"2026-06-15","kcal_total":0}`
   - final answer: `Dodano "brokuł sport" do diety na dziś. Całkowita liczba kalorii na dziś to 2506.5 kcal.`

Wniosek: nie potwierdzilem stabilnego, deterministycznego `12x` identycznego zachowania w kazdym runie. Natomiast sam query potrafi wejsc w zla petle albo skonczyc sukcesem bez wariantow zapytania.

## ZADANIE 4 - porownanie z `100g jablka`

Nie ma strukturalnej roznicy typu `status/data`, ktora tlumaczylaby `has_meaningful_data=True` dla jablka i `False` dla brokula.

W obecnym stanie oba wejscia:

- zwracaja `status: OK`
- maja `payload` z danymi
- zawieraja `template_id`, `kcal_total`, `protein_g`, `carbs_g`, `fat_g`

Czyli problem nie wyglada na klasyczne `brak danych` po stronie `nutrition_write_resolve`.

## Wniosek glowny

Hipoteza z `has_meaningful_data=False` dla `brokul sport` nie jest potwierdzona.

Najbardziej prawdopodobny mechanizm:

- write flow nadal wchodzi w petle przy tym query,
- ale nie dlatego, ze resolver zwraca puste/niemozliwe dane,
- tylko dlatego, ze model/planowanie tooli dla tego wejscia jest niestabilne i czasem wraca do kolejnych krokow zamiast zakonczyc odpowiedzia.

## Relacja do Fix 2

To nadal wyglada na ten sam obszar co `template_lookup`:

- gdyby `nutrition_write_resolve` albo Albert mial lepszy fuzzy-match do `meal_templates`, to takie wejscie powinno od razu dostac meaningful data,
- wtedy petla moglaby zniknac bez dodatkowego Fix 3,
- ale obecny obserwowany przypadek nie jest dowodem, ze `has_meaningful_data` klasyfikuje to jako brak danych.

## Uwaga operacyjna

W trakcie diagnozy powstaly testowe zapisy w `qbot_v2.intake_logs`; usunalem tylko moje wpisy z tej sesji (`117-122`, `126-127`). Rekord `123` zostawilem, bo mial inny `source`.
