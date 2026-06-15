# Krok 3c: diagnoza pętli 12x route_poi_analyze_readonly

**Status:** istniejący problem pętli Alberta, nie regresja samego `route_poi_analyze_readonly`.

## 1. Co się dzieje dla `poi etapu 2`

- `orchestrate_query("poi etapu 2")` kończy się `status: partial`.
- `steps` wraca jako `None` w końcowym wyniku runtime.
- `tool_results` zawiera 12 wpisów.
- Każdy wpis ma `reader: route_poi_analyze_readonly` i `status: OK`.
- W odpowiedzi tekstowej pojawia się tylko komunikat o limicie:
  - `Przekroczono limit 12 kroków. Ostatnie narzędzia: ['route_poi_analyze_readonly', 'route_poi_analyze_readonly', 'route_poi_analyze_readonly']`
- Nie ma śladu wywołania starego `route_poi_analyze` w tej sesji.

## 2. To nie wygląda na problem danych w tool_results

- Sam wrapper `route_poi_analyze_readonly` zwraca pełną analizę:
  - `status: OK`
  - `analysis` zawiera m.in. `summary`, `hard_resupply`, `soft_food_stop`, `water`, `attractions`, `chunks`, `missing_chunks`
- Rozmiar payloadu:
  - `result size (chars): 28185`
  - `result size (approx tokens): 7046`
- `analysis` jest dużym słownikiem:
  - `analysis size chars: 27720`
  - zawiera kluczowe pola na końcu struktury

## 3. Dlaczego Albert prawdopodobnie zapętla się

W `qbot3/llm/albert.py` wynik toola jest wkładany do wiadomości jako:

- `messages.append({"role": "tool", ..., "content": json.dumps(tool_content, ...)[:4000]})`

Czyli:

- pełny wynik jest zachowywany w `tool_results_log`
- ale do kontekstu LLM trafia tylko pierwsze 4000 znaków
- przy payloadzie ~28k znaków kluczowe dane z `analysis` są bardzo prawdopodobnie ucinane przed dostarczeniem modelowi

To dobrze tłumaczy, dlaczego model widzi, że narzędzie „zadziałało”, ale nie dochodzi do sensownej finalizacji odpowiedzi i ponawia to samo wywołanie aż do limitu kroków.

## 4. Porównanie z innymi zapytaniami

- Zapytanie `ile kcal dzis zjadlem` też dobiło do limitu 12 kroków.
- `tool_results` zawierało 12 wywołań `nutrition_day_summary`.
- To znaczy, że problem nie jest unikalny dla POI ani dla `route_poi_analyze_readonly`.

Wniosek: to wygląda na ogólny problem pętli/finalizacji w Albercie, który nowy wariant POI tylko ujawnił mocniej przez duży payload.

## 5. Rozstrzygnięcie

- To **nie** jest problem kompletności danych w `route_poi_analyze_readonly`.
- To **nie** wygląda też na nową regresję wyłącznie od tej zmiany.
- Najbardziej prawdopodobne źródło:
  - zbyt duży wynik toola
  - truncation `[:4000]` przed podaniem do LLM
  - brak skutecznego warunku finalizacji po otrzymaniu poprawnej analizy

## 6. Rekomendacja

- `route_poi_analyze_readonly` jest funkcjonalnie poprawny, ale **nie powinien być uznany za w pełni gotowy UX-owo** dopóki Albert nie przestanie zapętlać się na tych wynikach.
- Priorytet na kolejną sesję:
  1. zmniejszyć/skomprymować payload tool result przekazywany do `messages`
  2. albo dodać bardziej deterministyczny warunek finalizacji po `status=OK/PARTIAL`
  3. dopiero potem oceniać, czy README/description narzędzia jest wystarczające

## 7. Kontekst z tej sesji

- `qbot3/llm/albert.py`:
  - `_MAX_STEPS = int(os.getenv("ALBERT_MAX_STEPS", "5"))`
  - `for step in range(_MAX_STEPS):`
  - `messages.append(... )[:4000]`
- `qbot3/tool_registry.py`:
  - `route_poi_analyze_readonly` ma `safety: read`
  - `route_poi_analyze` zostaje na `safety: write`
