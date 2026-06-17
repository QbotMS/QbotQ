# Krok 9: redundancja `route_poi_analyze_readonly` po fixie read-only loop

## 1. Sekwencja testów

### 1.1 `/mcp/` real provider

Wywołanie:

`qbot.query("poi etapu 2")` przez `/mcp/`

Wynik:

- `status: OK`
- `steps: 2`
- `tool_calls: ["route_poi_analyze"]`
- `sources_used: ["route_poi_analyze"]`
- `router_v2: open_domain intent=route_poi_analyze conflict=False`
- odpowiedź tekstowa:
  - `Gotowe — analiza POI dla etapu 2 została zapisana.`

To oznacza, że service `/mcp/` wybrał wariant `route_poi_analyze` ze ścieżki write i zapisał raport.

### 1.2 direct `orchestrate_query`

Wywołanie:

`orchestrate_query(question="poi etapu 2", context="")`

Wynik:

- `status: OK`
- `steps: None`
- `tool_results`:
  - `route_poi_analyze_readonly -> OK`
  - `route_poi_analyze_readonly -> OK`
- odpowiedź tekstowa:
  - analiza POI z danymi, bez draftu i bez pętli

To oznacza, że direct runtime w tej sesji wybrał wariant readonly.

## 2. Artefakt POI

Po teście `/mcp/` pliki raportu mają timestamp z tej sesji:

- `poi_analysis_55444268_00_85.md` -> `2026-06-15 19:08:18.380659543 +0200`
- `poi_analysis_55444268_00_85.json` -> `2026-06-15 19:08:18.381740975 +0200`

Wniosek:

- write-path faktycznie wykonał side-effect i odświeżył artefakt
- readonly path nie zapisuje raportu do tych plików

## 3. Wniosek: A/B/C

**C**.

Powód:

- `route_poi_analyze_readonly` nadal jest użyteczne jako preferowany wariant dla zapytań informacyjnych, bo unika niepotrzebnego I/O i side-effectu zapisu.
- Fix Kroku 9 rozwiązuje problem poprawności odpowiedzi dla **obu** wariantów:
  - write-path finalizuje poprawnie
  - readonly-path finalizuje poprawnie
- Ale pozostaje różnica semantyczna:
  - `route_poi_analyze` zapisuje raport
  - `route_poi_analyze_readonly` nie zapisuje raportu

## 4. Rekomendacja

- Nie usuwać `route_poi_analyze_readonly` teraz.
- Trzymać go jako preferowany wariant dla zapytań informacyjnych o POI.
- Ewentualne przyszłe sprzątanie może go usunąć dopiero po ponownej ocenie, ale nie jest to konieczne.

## 5. Związek z Krokiem 9

Fix `f5e28be` naprawił finalizację read-only i write flow.
To znaczy:

- dla poprawności odpowiedzi `route_poi_analyze_readonly` nie jest już potrzebne
- dla efektywności i uniknięcia side-effectów nadal jest sensowne jako preferowany wariant
