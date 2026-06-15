# TOP_PRIORITY (2026-06-15, odkryte podczas Kroku 3c)

## Truncation [:4000] w qbot3/llm/albert.py - możliwy systemowy bug pętli 12-step dla narzędzi z większym wynikiem

**Odkrycie:** orchestrate_query("poi etapu 2") wywołuje route_poi_analyze_readonly 12x (każdy status=OK, ~28185 chars wyniku), nigdy nie formułuje odpowiedzi, kończy na limicie kroków (QBOT_ALBERT_MAX_STEPS=12). Hipoteza: wynik toola jest wkładany do messages jako JSON ucięty do 4000 znaków (qbot3/llm/albert.py), kluczowe pola (hard_resupply/water/attractions) są "na końcu" struktury i wypadają po truncation - model nie widzi danych, ponawia tool call.

**DODATKOWO ZAOBSERWOWANE (niepotwierdzone, do weryfikacji jako pierwszy krok nowej sesji):** Q zgłosił że orchestrate_query("ile kcal dzis zjadlem") TEŻ wpada w 12 kroków i ponawia nutrition_day_summary. Jeśli to się potwierdzi - problem dotyczy WIELU/WSZYSTKICH narzędzi z wynikiem >4000 chars, nie tylko POI. To może wpływać na REALNE zapytania użytkownika przez qbot.query (Custom GPT / sesja MCP) NIEZALEŻNIE od acceptance suite (66/0/1 nie wykrywa tego - testy nutrition prawdopodobnie wołają _execute_nutrition_* bezpośrednio, nie orchestrate_query()).

**Koszt problemu (jeśli potwierdzony jako szeroki):** każde zapytanie trafiające w >4000-char wynik = do 12x wywołanie LLM + 12x wywołanie narzędzia (dla narzędzi z side-effects jak route_poi_analyze - 12x zapis artefaktu na dysk) + odpowiedź "Przekroczono limit kroków" bez danych dla użytkownika, mimo że dane ZOSTAŁY policzone (są w tool_results, ale orchestrate_query() ich nie syntetyzuje w odpowiedzi).

**ZAKRES NOWEJ SESJI (priorytet NAD Krokiem 3c i 3b/1b):**
1. Zlokalizować PRECYZYJNIE [:4000] (czy to literalnie ten kod) w qbot3/llm/albert.py - linia, kontekst, czy to dotyczy WSZYSTKICH tool_results czy konkretnego formatowania.
2. Zweryfikować zasięg: dla ilu narzędzi w tool_registry wynik REALISTYCZNIE przekracza 4000 chars (POI - tak, profile etapu z wieloma segmentami - prawdopodobnie, nutrition_day_summary - zweryfikować, inne route tools - audyt).
3. Zweryfikować czy "nutrition 12-step" jest reprodukowalne i czy to TEN SAM mechanizm (truncation) czy coś innego (osobny root cause).
4. Naprawić: opcje do rozważenia (NIE przesądzać teraz):
   - zwiększyć limit truncation (prosty fix, ale może tylko przesunąć problem dla jeszcze większych wyników)
   - zmienić co jest wkładane do messages - summary/skrót wyniku zamiast pełnego JSON, z mechanizmem "pobierz pełne dane" jeśli model potrzebuje
   - zmienić warunek finalizacji - jeśli tool_result.status=="OK" i to JEDYNE wywołanie tego narzędzia w tej turze, wymusić finalAnswer niezależnie od tego co model "widzi" (heurystyka: ufaj że narzędzie zwróciło wynik, nie pozwól pętli go ignorować)
5. PO fixie: re-test orchestrate_query("poi etapu 2") I "ile kcal dzis zjadlem" - oba powinny kończyć w 1-3 krokach ze status=OK/PARTIAL i realną odpowiedzią tekstową (nie "limit kroków").
6. Pełny acceptance suite - regresja vs 66/0/1.
7. DOPIERO POTEM: Krok 3b/1b (przełączenie Router v2 dla profilu etapu - już gotowe funkcjonalnie z 1a, ale jeśli profil etapu też ma wynik >4000 chars, może mieć TEN SAM problem pętli - sprawdzić PRZED przełączeniem, inaczej przełączenie "naprawi" routing ale wprowadzi 12-step pętlę dla każdego zapytania o profil).

**Pliki diagnozy:** _session_notes/krok3c_pętla_diagnoza.md, _session_notes/krok3c_status.md, _session_notes/krok3c_partial_diagnoza.md (jeśli istnieje).

- Krok 3c (NOWA SESJA): `route_poi_analyze_readonly` (opcja 1a) + audyt 4 pozostalych `WRITE_DRAFT`. START: [`_session_notes/krok3c_punkt_startowy.md`](/opt/qbot/app/_session_notes/krok3c_punkt_startowy.md), ZADANIE 1 (rozstrzygnij H1 vs H2 dla `WRITE_DRAFT` w `_tool_qbot_route_poi_analyze` PRZED implementacja).
