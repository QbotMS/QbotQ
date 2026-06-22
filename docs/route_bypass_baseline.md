# Baseline regresji — pytania o trasę (TASK 04, KROK 1)

_Wygenerowano: 2026-06-22. Cel: zmierzyć realny wskaźnik „loterii" dla pytań typu B
(profil/nawierzchnia odcinkami) ZANIM zapadnie decyzja o budowie deterministycznego bypassu.
Loteria `route_id` została już naprawiona innym fixem (`_resolve_rwgps_route_hint`), więc bypass
może być niepotrzebny — ten dokument służy pomiarowi, nie budowie._

## Zakres pomiaru (sign-off Michała, 2026-06-22)
- Bypass (gdyby budować) = WYŁĄCZNIE wiersz B. Teren (C) i podjazdy (E) zostają Albertowi.
- Twarde wykluczenia bez zmian: F feasibility, G porównania, H pacing/czas, I ride_analysis,
  J ciśnienie, K follow-up, L szukanie/import.
- Bypass = warstwa DANYCH (pole `analysis` 1:1 z route_profile_detail), NIE ocena.

## Trasowanie DZIŚ (fakt z żywego kodu)
`qbot.query` -> `qbot_query_handler.handle_query`. Pytania o trasę wpadają w `OPEN_DOMAIN_INTENTS`
i przy `QBOT_ROUTES_VIA_ALBERT=1` + `QBOT3_ENABLED=1` eskalują do Alberta (`orchestrate_query`);
handler keywordowy to fallback przy wyjątku. Albert (LLM) wybiera narzędzie wg `_SYSTEM`:
plan->route_plan_analysis, profil/nawierzchnia/podjazdy/teren->route_profile_detail,
jazda FIT->ride_analysis, sklepy/refill->route_poi_analyze_readonly, ciśnienie->tire_pressure.

## Kryterium oceny dla typu B (twarde, z treści odpowiedzi)
- SUKCES: odpowiedź zawiera tabelę „Nawierzchnia odcinkami" (wiersze km) ORAZ profil wysokości
  i/lub listę podjazdów dla właściwej trasy (dystans ~99,3 km dla 55734589).
- LOTERIA/BŁĄD: pusty wynik, „brak"/„nie mogę zidentyfikować trasy", status error/partial,
  przekroczenie limitu kroków, pominięty `rwgps_route_find` (pusty profil mimo braku id),
  albo zła klasyfikacja (np. odpowiedź planu/feasibility zamiast profilu odcinkami).

---

## Zestaw testowy (per kategoria)

### B — Profil / nawierzchnia odcinkami  [KANDYDAT BYPASSU — mierzony]
- B1 (z id): „Jaka jest nawierzchnia odcinkami (km po km) na trasie 55734589?"
- B2 (z id): „Pokaż profil wysokości i podjazdy trasy 55734589"
- B3 (z id, pełny): „Pokaż szczegółowy profil trasy 55734589 km po km: nawierzchnia odcinkami, wysokości i podjazdy"
- B4 (bez id -> najnowsza): „Pokaż szczegółowy profil nawierzchni odcinkami mojej najnowszej trasy"
- B5 (bez id -> najnowsza): „Gdzie na trasie są podjazdy i jaki jest profil wysokości km po km?"

### C — Teren / krajobraz  [zostaje Albertowi]
- C1: „Czy trasa 55734589 prowadzi przez las czy pola?"
- C2: „Co mam po bokach na trasie 55734589 — pokrycie terenu?"

### A — Plan / podsumowanie trasy  [Albert -> route_plan_analysis]
- A1: „Co mnie czeka na trasie 55734589? Podsumowanie."
- A2: „Przeanalizuj planowaną trasę 55734589."

### D — Sklepy / woda / refill  [Albert -> route_poi_analyze_readonly]
- D1: „Czy będę miał gdzie kupić wodę na trasie 55734589?"
- D2: „Czy sklepy po drodze będą otwarte, jak wyjadę o 8:00?"

### E — Podjazdy (dedykowane)  [zostaje Albertowi]
- E1: „Ile podjazdów ma trasa 55734589 i które są najtrudniejsze?"

### F — Feasibility / ocena  [WYKLUCZONE z bypassu]
- F1: „Czy dam radę na trasie 55734589?"

### G — Porównania  [WYKLUCZONE]
- G1: „Która trasa jest trudniejsza: 55734589 czy moja najnowsza?"

### H — Pacing / czas / taktyka  [WYKLUCZONE]
- H1: „Jak rozłożyć siły i ile zajmie mi przejazd trasy 55734589?"

### I — Analiza wykonanej jazdy / FIT  [WYKLUCZONE -> ride_analysis]
- I1: „Jak mi poszło na ostatniej jeździe?"

### J — Ciśnienie opon  [WYKLUCZONE -> tire_pressure]
- J1: „Na ile napompować opony na luźny szuter?"

### K — Follow-up / dopytanie kontekstowe  [WYKLUCZONE — bypass bezstanowy]
- K1: „A na tym odcinku jaka nawierzchnia?" (bez kontekstu poprzedniego pytania)

### L — Szukanie / import / generowanie trasy  [WYKLUCZONE — poza zakresem]
- L1: „Znajdź moją najnowszą trasę."

---

## Wyniki pomiaru
_Wypełniane po uruchomieniu zestawu przez qbot.query (request_id + outcome)._

---

## Wyniki pomiaru — KROK 1 (2026-06-22, qbot.query → Albert, model=claude)

Sukces = pełny profil km-po-km (nawierzchnia odcinkami + wysokości + podjazdy).

### TYP B — 11/11 SUKCES, 0 loterii (0%)
| Wariant | request_id | Wynik |
|---|---|---|
| B (z id) | 47ca99ff, 334d5624, 9539fb8c, b31bc5f9, a3bd28ae | 5/5 pełny profil |
| B (bez id → najnowsza) | 1f4d9760, ed47bca1, 790eb927, 8cd1d2cd, dedb92fe, 91589b14 | 6/6 pełny profil (rozwiązana najnowsza = 55734589) |

Wszystkie: router_v2 intent=rwgps_route_profile_sample → engine=albert. Brak pustek, brak pominięcia
rwgps_route_find, brak złej klasyfikacji.

### Kontrolne (po 1 — dokumentacja trasowania)
| Kat. | request_id | Trasowanie | OK? |
|---|---|---|---|
| A plan | 16aee047 | route_plan_analysis | ✓ |
| D woda/refill | 4553ac2f | POI (trip_attractions) | ✓ |
| E podjazdy | 25dd780b | route_climbs | ✓ |
| J ciśnienie | c20e8796 | tire_pressure | ✓ |
| I jazda | (NO_DATA) | garmin_last_activity (dziś joga) | ✓ |
| F feasibility | — | xert_status (NIE feasibility trasy) | ⚠ odstępstwo, poza zakresem B |

### Wniosek
Loteria typu B = 0/11. ZASTRZEŻENIE: N=11 → reguła trzech, 95% górna granica ~27%; „stabilnie"
obserwacyjne, nie dowiedzione <5%. Decyzja o budowie/zamknięciu bypassu = po stronie Michała (KROK 2).
