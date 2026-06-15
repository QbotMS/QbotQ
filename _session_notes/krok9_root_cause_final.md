# Krok 9 - root cause końcowy (2026-06-15)

## Potwierdzony root cause

Produkcję blokuje nie truncation, tylko logika finalizacji w `qbot3/llm/albert.py`:

- [`qbot3/llm/albert.py:258`](../qbot3/llm/albert.py#L258)
  - `kwargs["tool_choice"] = "auto" if _had_successful_write else "required"`

W read-only flow `_had_successful_write` pozostaje `False`, więc `tool_choice` jest stale `"required"`.

To wymusza narzędzia w każdej rundzie i uniemożliwia modelowi zakończenie odpowiedzi bez tool call. Skutek:

- 12x powtórka tego samego narzędzia
- `status="partial"`
- brak finalnego tekstu
- `answer` kończy się limitem kroków

## Zakres potwierdzony w tej sesji

Przetestowane i zapętlone read-only ścieżki:

- `route_poi_analyze_readonly`
  - wynik ~`28192` chars
  - `tool_results count: 12`
  - `status: partial`
- `nutrition_day_summary`
  - wynik `529` chars
  - `tool_results count: 12`
  - `status: partial`
- `xert_readiness`
  - wynik `304` chars
  - `tool_results count: 12`
  - `status: partial`

To oznacza, że problem jest **systemowy dla read-only**, a nie ograniczony do dużych wyników POI.

## Rola truncation `[:4000]`

W [`qbot3/llm/albert.py:394`](../qbot3/llm/albert.py#L394) nadal istnieje truncation `[:4000]` dla `role=tool` message.

To jest realny problem dla dużych wyników i należy go poprawić później, ale:

- nie tłumaczy samej pętli 12-step
- pętla występuje też dla małych payloadów

## Dlaczego acceptance suite nie ostrzegł

`tests/test_qbot3_acceptance.py` uruchamia `ALBERT_LLM_PROVIDER=mock`, a `qbot3/agent_runtime.py` ma dla tego trybu early-return do `_orchestrate_query_legacy(...)`.

Czyli acceptance suite nie przechodzi przez produkcyjną ścieżkę z `tool_choice="required"`.

## Wniosek operacyjny

- To jest **TOP_PRIORITY** i blokuje dalsze przełączanie Router v2.
- `route_poi_analyze_readonly` jest funkcjonalnie poprawne jako narzędzie, ale UX end-to-end jest zepsuty przez pętlę Alberta.
- Najpierw trzeba naprawić finalizację read-only, potem wracać do Kroku 3b/1b.
