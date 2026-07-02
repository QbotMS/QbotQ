# AUDYT SILNIKA NAWIERZCHNI QBOT — raport i decyzje

_Data: 2026-07-02. Tryb: AUDYT (zero zmian w kodzie/bazie). Dowody: żywy kod + żywa baza qbot_v2, trasy 55798129 (base 1), 55864231 (base 55), 55918401 (base 43)._

Plik silnika: `tools/rwgps/route_surface_engine.py` (`ENGINE_VERSION="route_surface_engine_v1"`).

---

## Ustalenia (1–8)

### 1. Poprawność etykiet — na czym można polegać

Na jedynej trasie policzonej PEŁNĄ, aktualną ścieżką (55798129, base 1) prowieniencja jest kompletna:
- `osm_surface` (jawny tag OSM, `classification_source=tagged_surface`, confidence=high): **49/76 = 64%** — wiarygodne.
- `osm_contextual` (wnioskowane): **27/76 = 36%** — z tego `inferred_highway`=18 (confidence **low**), `inferred_tracktype`=9 (medium/low). To słabe etykiety z założenia.

Przykłady dobre (trasa 1): seg0 km0.0–0.55 asphalt (tag), seg2 km1.15–1.9 asphalt (tag).
Przykłady wątpliwe (trasa 1): seg3 km1.9–4.35 „ground" z `inferred_highway` conf=low (brak tagu, zgadnięte z typu drogi); seg4 km4.35–4.9 „grass" z `inferred_tracktype`.

Na trasach 55864231 i 55918401 udział `osm_surface` to 70% i 74%, ALE **`classification_source=None` dla WSZYSTKICH segmentów** — patrz ustalenie 8 (prowieniencja zepsuta, bo liczone starą ścieżką przed poprawką z 2026-07-02). Dodatkowo dużo `unknown`: trasa 55 = 20/66 (**30%**), trasa 43 = 8/31 (26%). To dokładnie te odcinki, gdzie „false certainty" byłaby błędem.

**Wniosek:** logika „tag wygrywa" działa poprawnie tam, gdzie ją widać. ~64% trasy ma twardą etykietę z tagu; reszta to uczciwie oznaczone wnioskowanie o niskiej pewności lub `unknown`.

### 2. Martwy kod — landcover w silniku: POTWIERDZONE martwe. Geologia: ŻYWA.

**Landcover w silniku = martwy (dowód w kodzie i w bazie).**
- `route_surface_engine.py:923` — `polygons: list = []`. Linia 924 przy `use_landcover=True` **tylko dopisuje ostrzeżenie** „landcover network refinement disabled in phase 1..."; `polygons` nigdy nie jest wypełniane.
- `:952` — `landcover = _landcover_label(...) if polygons else None` → skoro `polygons` zawsze puste, `landcover` zawsze `None`.
- W efekcie w `_refine_context` (`:619–634`) gałęzie las/pole/zabudowa (`landcover == "forest"/"farmland"/...`) **nigdy się nie odpalają**.
- Dowód z bazy: `segments_with_landcover_nonnull = 0` na WSZYSTKICH 3 trasach.

**Drugi martwy fragment (geologia w `_refine_context`, `:636–644`):** sprawdza dokładne tokeny `{"sand","alluvial"}`, `{"clay"}`, `{"limestone",...}`. Ale realny `material_hint` z `geology_context.py` to `sand_loose_ground_possible`, `rocky_stony_gravel_possible` itd. — te wartości **nigdy nie pasują** do tych tokenów. Ten fragment jest nieżywy (zastąpiony przez `risk_flags_for_segment`).

**Geologia jako całość NIE jest uśpiona.** Działa realnie przez `risk_flags_for_segment` (`:972`). Dowód z bazy: segmenty z flagami ryzyka 51/21/16 na trzech trasach, flagi `sand_possible` + `loose_surface_possible` (heurystyka regionu Mazowsze). Bramkowanie jest sensowne (`geology_context.py:306–313`): pomija asfalt/beton/kostkę, odpala tylko na miękkich + niepewnych odcinkach. To jednak heurystyka REGIONALNA („w tym regionie możliwy piasek"), nie pomiar per odcinek — flagi mówią „możliwe", nie „potwierdzone".

### 3. Sprzężenia — pełny łańcuch zasilania `route_surface_layer`

Silnik NIE pisze wprost do warstwy kanonicznej. Łańcuch:

1. `precompute` → `_ensure_rwgps_surface_profile` (`scripts/route_precompute_trigger.py:636`) woła `_tool_qbot_route_artifact_enrich(enrich=["surface"])`.
2. enrich → silnik `analyze_route_surface` (`route_surface_engine.py:843`) — liczy segmenty na żywo (Overpass + tagi OSM + geologia).
3. `_persist_surface_profile_from_enrich_result` (`:540`) → tabela pośrednia **`route_surface_profiles`** (`surface_summary_json` + `surface_segments_json`).
4. writer `ensure_route_surface` (`qbot3/routes/route_surface_store.py`) czyta „najlepszy" profil przez `_fetch_best_route_surface_profile` (`qbot_route_tools.py:380`, warunek `coverage_pct>=90`) → **`route_surface_layer`**.

**Czy silnik jest jedynym źródłem?** Tak dla warstwy kanonicznej — `route_surface_profiles` to tylko bufor wyniku silnika, nie konkurencyjne źródło. Valhalla nie uczestniczy (ustalenie 5).

### 4. Rozdzielczość — jak uczciwie łączyć z WorldCover

Dowód z bazy (liczby węzłów):
| trasa | route_axis_segments | route_shade_layer | route_surface_layer |
|---|---|---|---|
| 55798129 | 1423 | 1423 | 76 |
| 55864231 | 1279 | 1279 | 66 |
| 55918401 | 441 | 441 | 31 |

`route_axis_segments` ma kolumny `km_from`, `km_to`. `route_shade_layer` jest 1:1 z osią (per węzeł ~50 m). `route_surface_layer` to scalone przebiegi z `km_from`/`km_to` w `surface_meta_json`.

**Uczciwe łączenie:** po kilometrażu. Dla węzła shade: `segment_index` → `route_axis_segments.km_from` → znajdź segment nawierzchni, którego zakres `[km_from, km_to]` obejmuje ten km. Zero interpolacji „na oko".

### 5. Dwa systemy klasyfikacji — czy Valhalla dotyka etykiety? NIE.

`_maybe_valhalla_refinement` (`:673`): domyślnie `use_valhalla=False`; nawet włączona zwraca `status="UNAVAILABLE"`, `used=False` i komunikat „Valhalla trace_attributes refinement not connected in phase 1; OSM/contextual result kept". W bazie `valhalla_snap_quality=None`. `grep` po „valhalla" w `route_canonical_read.py` i `client.py` (ścieżka odczytu/raportu) = **zero trafień**.

**Wniosek:** Valhalla NIE wpływa na etykietę nawierzchni w tym silniku ani w łańcuchu Route Store. „System B" (kubełki Valhalli) to problem GENERATORA tras (osobny projekt), nie tego silnika. Nic do usunięcia tutaj.

### 6. Testowalność poprawności — BRAK testów poprawności etykiet silnika.

`grep` po `route_surface_engine` / `_infer_from_tags` w całym `tests/` = **zero trafień**. Istniejące testy dotyczą:
- starej ścieżki frame'owej (`test_surface_inference.py`, `test_surface_enrich.py`),
- starego punktowego landcoveru Overpass (`test_highway_inference.py`),
- writera/kształtu (`test_route_surface_store.py`, `test_route_canonical_read.py`, `test_route_report.py`).

Żaden nie sprawdza: „tag=gravel → gravel", „tracktype=grade1 → nie ryzykowna", „highway=track bez tagu → ground/low". To realizacja lekcji projektu: testy przechodzą, a poprawność rdzenia nie jest pilnowana.

### 7. WorldCover — jak wpiąć (rekomendacja potwierdzona z zastrzeżeniem)

WorldCover mówi, co jest WOKÓŁ drogi (las/pole/łąka/zabudowa), a nie jaka jest nawierzchnia. Więc nie zamieni `unknown` w „gravel" — może jedynie **ożywić kontekst**, który dziś jest martwy (ustalenie 2), dając etykietę o NISKIEJ pewności na odcinkach bez tagu.

**Rekomendacja:** osobny przebieg **DB→DB**, czytający `route_surface_layer` + `route_shade_layer` złączone po km (ustalenie 4), **BEZ dotykania silnika i bez Overpass**. Reguły:
- działa WYŁĄCZNIE na `source=osm_contextual` (tag wygrywa — `osm_surface` nietykalne);
- mapa klas: drzewa(10)→las, uprawy(40)→pole, trawa(30)→łąka, zabudowa(50)→zabudowa;
- klasa dominująca z 5-punktowego przekroju + % zgodności; próg wstępnie ~70%;
- niska zgodność → „niepewne", NIE zgadywanie; wynik zawsze oznaczony jako pochodzący z WorldCover.

To zastępuje martwy, oparty na Overpass landcover w silniku (który i tak był wyłączony przez timeouty).

### 8. Prowieniencja — dziś NIEspójna, do naprawy przez przeliczenie.

Da się odtworzyć źródło etykiety TAM, gdzie `classification_source` jest wypełnione (`tagged_surface` / `inferred_highway` / `inferred_tracktype` / `unknown`) + `surface_raw`/`surface_inferred`/`surface_refined` w `surface_meta_json`. Tak jest na trasie 1.

ALE trasy 55 i 43 mają `classification_source=None` i `surface_inferred=None` dla wszystkich segmentów — bo były liczone starą funkcją `legacy_surface_shape`, która okrajała te pola (naprawione 2026-07-02, `route_surface_engine.py:1073+`, ale te trasy nie były od tego czasu przeliczone). **Naprawa = pełny recompute** (już zaplanowany), nie zmiana logiki. Oryginał (tag) nigdy nie jest nadpisywany — `surface_raw` zostaje osobno od `surface_refined`.

---

## WERDYKT: ZOSTAWIĆ RDZEŃ + posprzątać i domknąć (nie przebudowywać, nie zastępować)

Rdzeń klasyfikacji jest zdrowy: „tag wygrywa" działa, Valhalla poprawnie odcięta, geologia sensownie bramkowana, prowieniencja przewidziana w schemacie. Nie ma fundamentalnej wady uzasadniającej przebudowę czy zastąpienie.

Problemy to: (a) martwy kod landcoveru w silniku, (b) brak testów poprawności, (c) niespójna prowieniencja na starych trasach, (d) brak uszczelnienia odcinków bez tagu. Wszystko to naprawia się BEZ ruszania rdzenia.

- **Koszt/ryzyko ZOSTAWIĆ+sprzątać:** niski. Usuwamy nieżywe gałęzie, dokładamy testy i osobny przebieg WorldCover. Rdzeń nietknięty.
- **PRZEBUDOWAĆ:** wysokie ryzyko regresji „tag wygrywa" bez zysku — logika już poprawna. Odrzucone.
- **ZASTĄPIĆ:** brak lepszego źródła tagów niż OSM; Valhalla to nie autorytet. Odrzucone.

---

## Docelowy kształt klasyfikacji (fundament, nie łatka)

1. **Warstwa 1 — tag OSM (autorytet):** `_infer_from_tags` na jawnym `surface`/`tracktype`. `tag wygrywa` na odcinkach opisanych. Nietykalne.
2. **Warstwa 2 — wnioskowanie z typu drogi:** `inferred_highway`/`inferred_tracktype`, zawsze z niską pewnością, tylko dla `osm_contextual`.
3. **Warstwa 3 — kontekst WorldCover (nowe, DB→DB):** uszczelnia TYLKO `osm_contextual`, oznaczone, próg zgodności, niska pewność. Zastępuje martwy landcover Overpass.
4. **Warstwa 4 — ryzyko geologiczne (istnieje):** `risk_flags_for_segment`, flagi „możliwe", tylko na miękkich odcinkach. Bez zmian.
5. **Prowieniencja obowiązkowa:** każdy segment trzyma `surface_raw` + `surface_inferred` + `surface_refined` + `classification_source` + źródło każdej warstwy. Oryginał nigdy nadpisany.

---

## Martwy kod do usunięcia (dowody wyżej)

- W silniku: gałęzie landcover w `_refine_context` (`:619–634`) — nieosiągalne (`polygons` zawsze puste).
- W silniku: geologiczny fragment `_refine_context` (`:636–644`) — tokeny nie pasują do realnego `material_hint`; zastąpiony przez `risk_flags_for_segment`.
- W silniku: import i użycie `surface_landcover` (`_fetch_landuse`/`landcover_for_point`, `_landcover_label`, flaga `landcover_used`) — martwe w silniku. UWAGA: `surface_landcover.py` żyje jeszcze w STAREJ ścieżce frame'owej (`route_brief.py`, `scripts/surface_enrich_route.py`, testy) — pełne skasowanie modułu wymaga wygaszenia tej ścieżki (osobna migracja).
- Do rozważenia: stub `_maybe_valhalla_refinement` + param `use_valhalla` — nieszkodliwy, ale bezużyteczny; można zostawić jako jawne „off" albo usunąć.

---

## LISTA DECYZJI DO ZATWIERDZENIA

1. **Sprzątanie martwego landcoveru w silniku** — usunąć nieosiągalne gałęzie landcover w `_refine_context` + import/`_landcover_label`/flagę `landcover_used`. _Rekomendacja: TAK._
2. **Usunięcie martwego fragmentu geologicznego z `_refine_context` (`:636–644`)** — zostaje tylko `risk_flags_for_segment`. _Rekomendacja: TAK._
3. **Stub Valhalli** — usunąć czy zostawić jako jawne „off"? _Rekomendacja: zostawić (dokumentuje, że Valhalla świadomie nie jest źródłem)._
4. **Testy poprawności silnika** — dodać jednostkowe testy `_infer_from_tags`/`_canonical_surface`/tracktype/tag-wins na sztucznych tagach (bez sieci). _Rekomendacja: TAK, priorytet._
5. **Pełny recompute 3 tras testowych (potem wszystkich)** — ujednolici prowieniencję (`classification_source`) na 55/43 i zapełni `route_poi_meta`. _Rekomendacja: TAK._
6. **WorldCover uszczelnianie jako osobny przebieg DB→DB** — wg ustalenia 7 (tylko `osm_contextual`, próg ~70%, oznaczone). Zatwierdzić: (a) czy budujemy teraz, (b) próg zgodności. _Rekomendacja: budować po recompute; próg 70% do walidacji na trasie 1._
7. **`surface_landcover.py`** — nie kasować globalnie teraz (żyje w ścieżce frame'owej); zaplanować wygaszenie razem z migracją `route_frames`. _Rekomendacja: odłożyć._

---

## Podsumowanie po ludzku

Silnik nawierzchni jest w rdzeniu zdrowy: gdy droga ma w OSM opis nawierzchni, bierze go dosłownie (~2/3 trasy), a tam gdzie opisu brak — uczciwie zgaduje z niską pewnością i nie udaje, że wie. Valhalla nic nie psuje, bo w ogóle nie dotyka etykiet. Główne braki to trzy rzeczy do sprzątnięcia, nie do przebudowy: martwy kawałek „landcoveru" w silniku (nigdy się nie uruchamia), brak testów pilnujących poprawności etykiet, oraz dwie stare trasy, które trzeba przeliczyć, żeby wiedziały skąd wzięły etykietę. WorldCover warto dołożyć, ale tylko jako delikatną podpowiedź na odcinkach bez opisu — on mówi co jest wokół drogi, nie z czego jest zrobiona.
