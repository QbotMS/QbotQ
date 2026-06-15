# TOP_PRIORITY (2026-06-15, root cause potwierdzony w Kroku 9)

## `tool_choice="required"` w `qbot3/llm/albert.py` blokuje finalizację read-only i wywołuje pętlę 12-step

**Root cause:** w [`qbot3/llm/albert.py:258`](../qbot3/llm/albert.py#L258) mamy:
`kwargs["tool_choice"] = "auto" if _had_successful_write else "required"`

`_had_successful_write` przełącza się na `True` tylko po udanym realnym zapisie. Dla wszystkich przetestowanych read-only ścieżek:

- `xert_readiness`
- `nutrition_day_summary`
- `route_poi_analyze_readonly`

flaga pozostaje `False`, więc `tool_choice` jest stale `"required"`.

To wymusza kolejne tool call-e zamiast pozwolić modelowi zakończyć odpowiedź z `finish_reason="stop"`. Efekt:

- 12x identyczne wywołanie narzędzia
- `status="partial"`
- `answer` kończy się `Przekroczono limit kroków`
- dane są poprawnie policzone w `tool_results`, ale nie są syntetyzowane do odpowiedzi tekstowej

## `[:4000]` w `albert.py` jest realne, ale drugorzędne

W [`qbot3/llm/albert.py:394`](../qbot3/llm/albert.py#L394) nadal istnieje truncation:
`json.dumps(tool_content, ... )[:4000]`

To jest **krytyczne dla dużych wyników** jak `route_poi_analyze_readonly` (~28k chars), ale nie jest główną przyczyną 12-step pętli, bo tę samą pętlę reprodukujemy też dla małych wyników:

- `nutrition_day_summary` ~529 chars
- `xert_readiness` ~304 chars

## Dlaczego acceptance suite nie wykrył problemu

`tests/test_qbot3_acceptance.py` ustawia:

- `ALBERT_LLM_PROVIDER=mock`

W `qbot3/agent_runtime.py` ten tryb robi early-return do:

- `_orchestrate_query_legacy(...)`

czyli testy nie przechodzą przez produkcyjną ścieżkę `albert.py:run()/orchestrate_query()` z wymuszonym `tool_choice="required"`.

W efekcie acceptance `66/0/1` nie pokazało problemu, mimo że realny runtime przez `qbot.query` / MCP jest nim objęty.

## Wpływ

To dotyczy szeroko realnych zapytań read-only przez `orchestrate_query()`:

- nutrition
- wellness / xert
- routes / POI

czyli potencjalnie większości zwykłych zapytań użytkownika w sesji MCP.

## Co dalej

1. Naprawić politykę finalizacji w `qbot3/llm/albert.py` dla read-only flow.
2. Dopiero potem wrócić do przełączania Router v2 dla profilu etapu i pozostałych intencji OPEN_DOMAIN.
3. Po fixie ponownie sprawdzić:
   - `poi etapu 2`
   - `ile kcal dzis zjadlem`
   - kontrolnie `jaka jest moja forma xert`

**Pliki diagnozy:** `_session_notes/krok3c_pętla_diagnoza.md`, `_session_notes/krok9_truncation_lokalizacja.md`, `_session_notes/krok3c_status_final.md` (plus wcześniejsze notatki Kroku 3c).
