# Krok 9 (TOP_PRIORITY): lokalizacja truncation w `albert.py` + reprodukcja POI/nutrition/xert

## 1. Truncation: gdzie dokładnie jest

Jedyny literalny limit `4000` znaleziony w badanym path:

- [`qbot3/llm/albert.py:394`](../qbot3/llm/albert.py#L394)
  - `messages.append({"role": "tool", ..., "content": json.dumps(tool_content, ensure_ascii=False, default=str)[:4000]})`

To jest **krytyczne**: cięcie dotyczy treści `role=tool` wkładanej do `messages` wysyłanych do LLM, a nie tylko logowania.

W `qbot3/agent_runtime.py` nie znaleziono podobnego limitu `4000`.

## 2. Co jeszcze jest ważne w `albert.py`

- [`qbot3/llm/albert.py:258`](../qbot3/llm/albert.py#L258)
  - `kwargs["tool_choice"] = "auto" if _had_successful_write else "required"`

To wygląda na główny mechanizm, który utrzymuje pętlę dla zapytań bez udanego write:

- read-only queries nie ustawiają `_had_successful_write`
- więc `tool_choice` pozostaje `"required"`
- model dostaje przymus kolejnego tool call zamiast swobody zakończenia odpowiedzi

W praktyce truncation `[:4000]` jest realne i szkodliwe, ale **sama nie tłumaczy 12-step loop**, bo pętla występuje również dla małych wyników.

## 3. Reprodukcja `poi etapu 2`

### Wynik runtime

- `status: partial`
- `steps: None`
- `tool_results count: 12`
- wszystkie `tool_results` mają `reader: route_poi_analyze_readonly` i `status: OK`
- answer kończy się komunikatem o limicie:
  - `Przekroczono limit 12 kroków...`

### Rozmiar wyniku narzędzia

Z bezpośredniego calla:

- `route_poi_analyze_readonly`:
  - `result size (chars): 28192`
  - `status: OK`

Z monkeypatcha `json.dumps` w `albert.py`:

- serializowany `tool_content` dla POI ma:
  - `TRACE dumps len: 28201`
  - czyli znacznie więcej niż `4000`

To potwierdza, że POI payload jest ucinany przed włożeniem do `messages`.

## 4. Reprodukcja `ile kcal dzis zjadlem`

To zgłasza się jako ten sam wzorzec pętli:

- `status: partial`
- `steps: None`
- `tool_results count: 12`
- wszystkie `tool_results` to `nutrition_day_summary -> OK`
- answer kończy się limitem 12 kroków

Rozmiar wyniku kontrolnego:

- `nutrition_day_summary`:
  - `result size (chars): 529`

To bardzo ważne: ten przypadek jest **mały**, a mimo to wpada w tę samą 12-step pętlę. Czyli problem nie jest wyjaśniony samym truncation dużych wyników.

## 5. Reprodukcja kontrolna `xert`

Kontrolny, mały wynik też wpada w pętlę:

- `status: partial`
- `steps: None`
- `tool_results count: 12`
- wszystkie `tool_results` to `xert_readiness -> OK`

Rozmiar wyniku kontrolnego:

- `xert_readiness`:
  - `result size (chars): 304`

To dodatkowo osłabia hipotezę, że sam rozmiar wyniku narzędzia jest główną przyczyną 12-step loop.

## 6. Wniosek końcowy

### Co jest potwierdzone

- Truncation `[:4000]` istnieje i jest **krytyczne**, bo dotyczy wiadomości przekazywanej do LLM.
- Payload POI jest duży (~28k chars), więc część danych analitycznych faktycznie wypada z kontekstu modelu.

### Co nie jest potwierdzone

- Nie da się obronić tezy, że **sam truncation** jest jedynym lub głównym źródłem 12-step loop.
- `nutrition_day_summary` i `xert_readiness` są dużo mniejsze, a mimo to kończą w tym samym limicie kroków.

### Najbardziej prawdopodobny root cause

- `tool_choice="required"` dla wszystkich tur bez `_had_successful_write`
- model jest więc zmuszany do kolejnego tool call zamiast do finalizacji odpowiedzi
- truncation `[:4000]` tylko pogarsza sytuację dla dużych wyników

## 7. Wstępna rekomendacja

- Nie uznawać truncation za samodzielną przyczynę.
- Następny fix powinien w pierwszej kolejności adresować:
  - politykę `tool_choice="required"` dla read-only flow
  - oraz dopiero wtórnie format/rozmiar `tool_content` w `messages`

## 8. Dane pomocnicze z tej sesji

- `poi etapu 2`
  - `status: partial`
  - `tool_results count: 12`
  - `route_poi_analyze_readonly` x12
  - payload size ~`28192` chars
- `ile kcal dzis zjadlem`
  - `status: partial`
  - `tool_results count: 12`
  - `nutrition_day_summary` x12
  - payload size `529` chars
- `jaka jest moja forma xert`
  - `status: partial`
  - `tool_results count: 12`
  - `xert_readiness` x12
  - payload size `304` chars
