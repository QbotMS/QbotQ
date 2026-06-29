# QBot — raport analizy trasy WEB

**Status:** WORKING CANON — robocze źródło prawdy przed implementacją  
**Zakres:** istniejąca architektura, decyzje projektowe i docelowy model raportu WEB  
**Trasa testowa:** RWGPS `55798129`  
**Cel:** na podstawie tego dokumentu aktualizować projekt, bez odtwarzania ustaleń z historii czatu.

---

## 0. Zasada dokumentu

Ten plik rozdziela pięć warstw:

```text
A. STAN ISTNIEJĄCY — makieta WEB
B. STAN ISTNIEJĄCY — obecny kod QBot
C. DECYZJE Z SESJI — zatwierdzone reguły produktu
D. ARCHITEKTURA DOCELOWA — jak ma działać nowy raport WEB
E. LUKI / DO WDROŻENIA — czego jeszcze brakuje
```

Nie mieszać tych warstw. Jeśli coś jest docelowe, nie oznacza to jeszcze, że działa w kodzie.

---

# A. STAN ISTNIEJĄCY — makieta WEB

## A1. Makieta ma pogodę i używa jej analitycznie

W makiecie WEB pogoda już jest widoczna w nagłówku i wpływa na interpretację raportu.

Widoczne dane testowe:

```text
Temp: 25°C
Wiatr: NNE 2 m/s
Opady: 0%
Zachmurzenie: 8%
Nasłonecznienie: pełne słońce
```

Opis testowy:

```text
Prognoza OWM na dziś 06:00, okolice startu.
Upalnie i sucho.
Wiatr słaby: 0–40 km lekko w twarz, 40–71 km w plecy.
```

Wniosek:

```text
Pogoda nie jest brakującym konceptem.
Do doprecyzowania pozostaje produkcyjny kontrakt danych i sposób zapisu w raportach.
```

Stała preferencja:

```text
Wiatr zawsze w m/s, nigdy w km/h.
```

## A2. Układ makiety WEB

Makieta ma układ:

```text
Header:
- nazwa trasy
- RWGPS route_id
- data utworzenia trasy
- data ostatniej modyfikacji trasy
- dystans
- przewyższenie
- max nachylenie / charakter profilu
- pogoda

Mapa:
- obraz offline, portrait
- większy niż pierwsza miniatura
- ponad sekcją 01
- trasa kolorowana wg kategorii nawierzchni
- alarmy zaznaczone wizualnie

01 Skład nawierzchni:
- pasek udziałów
- 6 kategorii
- krótki opis charakteru trasy

02 Alarmy:
- sortowane po km od–do
- km zaokrąglone do 0,5 km
- otoczenie pokazane przy alarmach

03 Narracja strategii:
- LLM łączy wiatr, ekspozycję, nawierzchnię, profil, pogodę i zmęczenie
```

## A3. WEB nie powinien być kompilowany z MD

Decyzja:

```text
DATA JSON = źródło prawdy dla renderu
HTML WEB = render z DATA
MD = mirror / roboczy zapis dla człowieka
metadata.json = techniczny audyt
```

Nie:

```text
MD → WEB
```

Tylko:

```text
DATA JSON → WEB
DATA JSON → MD
DATA JSON → metadata / artifact record
```

---

# B. STAN ISTNIEJĄCY — obecny kod QBot

## B1. Ścieżka obecnego route_report

Obecna ścieżka logiczna:

```text
użytkownik
→ qbot_query
→ qbot3.agent_runtime / Albert
→ qbot3.tool_registry
→ route_report
→ qbot_route_report_tool.py
```

`route_report` obecnie jest orkiestratorem istniejących narzędzi, nie nowego pipeline’u WEB.

## B2. Narzędzia obecnie składane przez route_report

Obecny `qbot_route_report_tool.py` korzysta m.in. z:

```text
route_plan_analysis
route_profile_detail
route_time_estimate
tire_pressure
route_fuel_plan
route_poi_analyze_readonly
```

## B3. Obecna ścieżka planowanej trasy

```text
route_plan_analysis
→ qbot_route_tools.py
→ tools/rwgps/route_brief.py build()
→ tools/rwgps/route_weather.py build()
→ DB / artifacts / cache
```

Wniosek:

```text
OpenWeatherMap jest już w QBot przez route_weather.py.
```

## B4. Obecna ścieżka profilu trasy

```text
route_profile_detail
→ qbot_route_tools.py
→ tools/rwgps/route_brief.py build_detail()
```

## B5. Obecna ścieżka nawierzchni

Istnieje mechanika:

```text
mcp_server.py
└─ analyze_rwgps_artifact_surface(...)
```

oraz schemat:

```text
route_artifacts
route_parse_results
route_surface_profiles
route_surface_segments
```

Ograniczenie:

```text
To nie jest jeszcze docelowa ścieżka WEB:
Valhalla way_id → Overpass way(id) tags → landcover → frames → DATA JSON → WEB.
```

Aktualizacja 2026-06-29: writer path w `tools/rwgps/client.py` zapisuje teraz do `qbot_v2.route_surface_profiles.surface_summary_json` pełny aktualny engine output z `analyze_route_surface()`, zachowując kompatybilność przez merge legacy `surface_profile` + current result. Nie wymaga to migracji DB, bo używany jest istniejący `JSONB`. `surface_segments_json` bierze segmenty z aktualnego wyniku, a testowo zapisano profile dla `55798129` i `55864231`. WEB nie był jeszcze zmieniany; następny krok to sprawdzenie, czy renderer/raport czyta nowe pola z `surface_summary_json`.

Aktualizacja 2026-06-29: writer ma quality gate. Partial wynik Overpass lub `LOW_CONFIDENCE` nie nadpisuje dobrego profilu, jeśli dla tej samej trasy istnieje już profil `GOOD_TAGGED` albo `GOOD_INFERRED` z lepszą jakością. Bez lepszego istniejącego profilu zapis może przejść z warningiem w `surface_summary_json`, ale schemat DB pozostaje bez zmian. HikConnect/GATE pozostają poza zakresem i nietknięte.

## B6. Artifact Store istnieje

QBot ma dedykowany store:

```text
/opt/qbot/artifacts
qbot3/artifacts/store.py
qbot_v2.artifacts
```

Typy obejmują m.in.:

```text
route
poi
plan
report
export
database
import
document
```

Mutacje obejmują m.in.:

```text
source
analysis
generated
export
import
```

Wniosek:

```text
Raporty i snapshoty analiz powinny być zapisywane jako artefakty QBot, nie tylko w czacie.
```

---

# C. DECYZJE Z SESJI

## C1. Identyfikacja trasy

Samo `route_id` nie wystarcza, bo RWGPS może zmienić przebieg bez zmiany ID.

Klucz profilu trasy:

```text
route_id
rwgps_created_at
rwgps_updated_at
geometry_hash
profile_version
```

Zasada:

```text
Ten sam route_id + inny rwgps_updated_at albo geometry_hash = nowy route_profile, liczymy profil od zera.
Zmiana daty/godziny przejazdu = zostaje ten sam route_profile, liczymy nowy run_context.
```

W raporcie WEB obok numeru trasy pokazywać:

```text
RWGPS 55798129 · utworzona: ... · zmieniona: ...
```

## C2. Dwa byty: profil trasy i kontekst przejazdu

Profil trasy — zależny od geometrii:

```text
route_profile
- geometria
- Valhalla way_id
- OSM tags
- nawierzchnia
- landcover
- przewyższenia / climbs
- mapa bazowa
```

Kontekst przejazdu — zależny od daty/godziny:

```text
route_run_context
- pogoda
- wiatr względem kierunku
- ETA
- wpływ opadów / temperatury / słońca
- narracja strategii
```

Finalny raport:

```text
route_report_run = route_profile + route_run_context + render WEB
```

## C3. Odrzucenie tabeli 5 km jako produktu

Tabela 5 km została odrzucona jako główny raport dla człowieka.

Powody:

```text
- wymaga zapamiętywania przebiegu trasy,
- miesza rzeczy krytyczne i mało ważne,
- lepiej działa jako warstwa wewnętrzna niż jako produkt.
```

## C4. Docelowy produkt

Raport ma mieć trzy główne warstwy:

```text
1. SKŁAD — ile czego na trasie.
2. ALARMY — kilka krytycznych odcinków, po km.
3. NARRACJA STRATEGII — plan jazdy z danych.
```

Mapa jest warstwą wizualną.

## C5. Alarmy

Zasady:

```text
- sortować po km od–do,
- nie sortować po powadze,
- km zaokrąglać do 0,5 km,
- przy alarmie pokazywać otoczenie,
- alarm to iloczyn warstw, nie pojedynczy tag.
```

Przykłady alarmów:

```text
grade5 + las + sucho → ryzyko piachu / luźnego duktu
podjazd + piach → problem trakcji
zjazd + luźne → ryzyko kontroli
wiatr czołowy + otwarte → koszt energetyczny
końcówka + grade4/5 → ryzyko błędu na zmęczeniu
```

---

# D. ZWALIDOWANE TESTY DANYCH

## D1. Valhalla FOSSGIS

Endpoint:

```text
https://valhalla1.openstreetmap.de/trace_attributes
```

Rola:

```text
Używać do ustalenia właściwego OSM way_id dla odcinków trasy.
```

Test 55798129:

```text
292 odcinki
135 unikalnych way_id
confidence 1.0
snap mediana 0,23 m
p99 0,7 m
max 49,8 m
>50 m = 0%
```

Wniosek:

```text
Valhalla bardzo dobrze trafia w właściwą drogę.
```

## D2. Overpass po way_id

Preferowane zapytanie:

```text
way(id:...) out tags
```

Test 55798129, ważony długością:

```text
realny tag surface: 71,0%
brak tagu surface: 29,0%
way_not_found: 0%
```

Brak surface:

```text
track bez tracktype: 12,65 km
track / grade5: 4,80 km
track / grade3: 1,94 km
track / grade4: 0,89 km
path: 0,12 km
```

## D3. smoothness / mtb:scale

Test 55798129:

```text
smoothness: ok. 0,8% brakującej części
mtb:scale: 0%
```

Wniosek:

```text
Czytać warto, ale na trasach rural nie można zakładać, że te tagi uratują analizę.
```

## D4. Landcover

Potwierdzone wartości:

```text
wood
forest
meadow
```

Wniosek:

```text
Las/pole da się odczytać jako osobną warstwę, ale wymaga zapytań przestrzennych i cache.
```

## D5. Przewyższenia

Istniejący moduł:

```text
tools/rwgps/climbs.py
detect_climbs(track_points)
```

Test 55798129:

```text
2 lekkie podjazdy:
km 15,4–15,9 avg 4,0%
km 23,9–24,2 avg 3,8%
```

Wniosek:

```text
Trasa płaska.
Surowa elewacja RWGPS jest zaszumiona.
Nie liczyć grade na krótkim oknie.
```

---

# E. SYSTEMATYKA NAWIERZCHNI

## E1. Sześć kategorii raportu

| Kategoria | Źródła `surface` | `tracktype` | Sens użytkowy |
|---|---|---|---|
| **Asfalt** | `asphalt`, `concrete`, `paved` | — | szybko, przewidywalnie |
| **Słabe utwardzone** | `paving_stones`, `sett`, `cobblestone`, `concrete:plates` | — | utwardzone, ale trzęsie |
| **Szuter / ubite** | `compacted`, `fine_gravel`, `gravel`, `pebblestone` | `grade1`, `grade2` | dobry gravel |
| **Grunt / zmienne** | `dirt`, `ground`, `earth`, `unpaved` | `grade3` | sucho OK, mokro ryzyko |
| **Miękka** | `grass`, `mud` | `grade4` | miękko, wolniej, trakcja |
| **Piach / ryzyko** | `sand`, `grass`, `mud` | `grade5` + `track bez tracktype` | spodziewaj się najgorszego |

## E2. tracktype

```text
grade1 — lita / utwardzona
grade2 — głównie twarda, ubity żwir/kamień
grade3 — mieszana, częściowo miękka
grade4 — przeważnie miękka
grade5 — miękka niemal w całości, ryzyko piachu / gruntu / trawy
```

---

# F. ARCHITEKTURA DOCELOWA

## F1. Pipeline

Aktualizacja 2026-06-28: nawierzchnia ma być liczona w backendzie przez
`tools/rwgps/route_surface_engine.py` (`route_surface_engine_v1`) po realnym śladzie.
WEB konsumuje gotowy DATA JSON i renderuje wynik; nie liczy nawierzchni i nie jest
źródłem prawdy.

Aktualizacja 2026-06-29: publiczny `route_report` najpierw szuka najnowszego
dobrego profilu w `qbot_v2.route_surface_profiles.surface_summary_json` i dopiero
potem spada do legacy `route_frames` / `route_surface_segments`. Gdy profil jest
dobry, raport używa `surface_percentages_refined` jako głównego źródła skrótu
nawierzchni oraz pokazuje `surface_quality_status`, `tagged_surface_pct`,
`inferred_surface_pct`, `unknown_surface_pct`, `geology_context`,
`problem_segments`, `surface_percentages_raw` i `surface_percentages_refined`.
Sekcja POI preferuje istniejący cache/raport, a ciężki refresh Overpass jest
omijany w publicznym runtime, żeby nie blokować `qbot.query`. Publiczny raport
dodaje też jawny blok `Geologia / podłoże (geology_context)` z providerem,
status, material_hint i interpretacją ryzyka, ale nie nadpisuje OSM surface.
Storage i schema DB bez zmian; HikConnect/GATE poza zakresem i nietknięte.

Regresja testowa w `tests/test_route_report.py` pilnuje tego read-pathu dla
`55798129`, w tym brak powrotu do legacy `33%` i brak blokady całego raportu
przez nieobecny cache POI.

Aktualizacja 2026-06-28: Overpass ma multi-endpoint fallback przez globalne
instancje `overpass-api.de`, `overpass.private.coffee`, `maps.mail.ru`, z ENV
`QBOT_OVERPASS_ENDPOINTS`. Default runtime to `first_success`; diagnostyczny
`QBOT_OVERPASS_PROBE_ALL=1` / `overpass_probe_all=True` odpytuje wszystkie mirrory
i zapisuje `overpass_probe.endpoint_comparison`. WEB powinien pokazywać/uwzględniać
`quality_status` oraz `overpass_metrics`, szczególnie przy LOW_CONFIDENCE.

Aktualizacja 2026-06-28: WEB powinien renderować jakość klasyfikacji osobno od
coverage. DATA JSON zawiera `tagged_surface_pct`, `inferred_surface_pct`,
`unknown_surface_pct`, `inference_sources_pct`, `inference_sources_m` oraz
`problem_segments.top_unknown/top_inferred`. `GOOD_INFERRED` nie oznacza takiej
samej pewności jak `GOOD_TAGGED`; oznacza dobry coverage, ale wynik zależny od
inferencji.

Aktualizacja 2026-06-28: `geology_context` jest stałym elementem DATA JSON i musi działać dla całej Europy, nie tylko dla wybranych krajów testowych. Bazowym providerem jest `EGDI`, krajowe providery są opcjonalnym enrichment/override tam, gdzie są sprawdzone, a `heuristic_region_v1` pozostaje ostatnim fail-open fallbackiem. Audyt pokazał, że WMS `GeologicUnitView_Lithology` z `GetFeatureInfo` JSON zwraca litologię, wiek i źródło dla wielu punktów europejskich, natomiast pan-europejski OGC API `collections/GeologicUnitView/items` z `bbox` zwracał `500`, więc prototyp powinien startować od WMS JSON. `build_geology_context()` jest już hooked do EGDI first, a fallback do heurystyki uruchamia się tylko przy `WARN`/`UNAVAILABLE`. WEB może pokazać `dominant_region`, `material_hint`, `confidence`, `warnings` oraz segmentowe `risk_flags`, ale nie powinien prezentować heurystyki jako twardej klasyfikacji nawierzchni. Włochy i Hiszpania były tylko testami konkretnych krajów, nie docelową granicą systemu. Strategia geologii to centroid + bbox + punkty kontrolne co 10 km; próbkowanie 50 m dotyczy tylko nawierzchni.

```text
route_id + rwgps_created_at + rwgps_updated_at + geometry_hash
    ↓
RWGPS fetch/cache
    ↓
route_surface_engine_v1 (surface sample 50 m, OSM corridor 50/80 m, Overpass fallback)
    ↓
Valhalla trace_attributes → way_id / matched geometry / snap quality (fallback/refinement)
    ↓
Overpass way(id) → surface / highway / tracktype / smoothness / mtb:scale
    ↓
Landcover ingest/cache → forest / wood / meadow / farmland / sand (contextual refinement)
    ↓
Geology context → centroid+bbox+5-10 km control points, fail-open, cache
    ↓
Elevation / climbs → climbs.py / smoothed grade / optional Valhalla height
    ↓
Base map image
    ↓
route_run_context(planned_start_at)
    ↓
route_weather.py → OWM + fallback → temp / opady / wiatr / słońce
    ↓
Internal samples; route_frames only legacy/profile/weather/debug
    ↓
Surface composition
    ↓
Alarm detection
    ↓
Strategy narrative
    ↓
WEB DATA JSON
    ↓
HTML + MD mirror + metadata
```

## F2. DATA JSON jako źródło prawdy

Docelowo raport powinien zapisywać:

```text
route_report_data.json  ← źródło prawdy
route_report.html       ← render WEB
route_report.md         ← mirror czytelny dla człowieka
metadata.json           ← techniczny audyt
route_map.jpg/png       ← mapa offline
```

## F3. Artefakty

Proponowana struktura:

```text
/opt/qbot/artifacts/routes/<route_id>/
├─ profiles/<geometry_hash>/
│  ├─ source_route.json
│  ├─ valhalla_match.json
│  ├─ osm_way_tags.json
│  ├─ surface_segments.json
│  ├─ route_frames.json
│  ├─ climbs.json
│  ├─ landcover.json
│  ├─ base_map.jpg
│  └─ profile_metadata.json
└─ runs/<planned_start_at>/
   ├─ weather_frames.json
   ├─ run_context.json
   ├─ route_report_data.json
   ├─ route_report.html
   ├─ route_report.md
   ├─ route_map.jpg
   └─ report_metadata.json
```

## F4. Metadata raportu

W `metadata.json` i `route_report_data.json` musi być:

```json
{
  "route_id": "55798129",
  "rwgps_created_at": "...",
  "rwgps_updated_at": "...",
  "geometry_hash": "...",
  "profile_version": "...",
  "planned_start_at": "...",
  "report_generated_at": "..."
}
```

---

# G. ROLA ALBERTA / LLM

Docelowo Albert nie tworzy struktury raportu.

Albert powinien:

```text
- dostać gotowy kontrakt danych,
- użyć danych pośrednich,
- napisać kontrolowaną narrację strategii,
- nie zmieniać struktury raportu,
- nie zgadywać danych jako fakt.
```

Albert nie powinien:

```text
- wymyślać sekcji,
- ukrywać niepewności,
- przepisywać całej analizy 1:1,
- mieszać planowanej trasy z wykonaną jazdą.
```

---

# H. LUKI / DO WDROŻENIA

## H1. Brak jednego produkcyjnego pipeline’u WEB

Obecnie są:

```text
- stary route_report,
- makieta WEB,
- testy Valhalla / Overpass / OWM,
- decyzje projektowe.
```

Brakuje jednego pipeline’u:

```text
RWGPS route_id
→ route_identity
→ route_profile
→ route_run_context
→ DATA JSON
→ WEB HTML / MD / metadata
```

## H2. Valhalla /height

Do sprawdzenia:

```text
czy DEM z Valhalli daje lepszy profil niż RWGPS + wygładzanie
```

## H3. Landcover

Do wdrożenia:

```text
cache landcover / exposure dla całej trasy
```

## H4. Mapa offline

Do wdrożenia:

```text
stabilny generator mapy
cache po geometry_hash + style_version
większy obraz portrait nad sekcją 01
```

## H5. Artifact run

Brakuje formalnego bytu:

```text
route_report_run
```

który spina:

```text
route_profile
route_run_context
DATA JSON
HTML
MD
mapę
metadata
```

---

# I. Kryteria akceptacji — robocze

Raport jest dobry, jeśli:

```text
- po 30 sekundach wiadomo, ile jest asfaltu, szutru, gruntu i ryzyka piachu,
- alarmy są nieliczne i ułożone po km,
- alarm pokazuje powód złożony z warstw,
- trudne odcinki mają otoczenie i taktykę,
- pogoda wpływa na wnioski,
- profil nie kłamie przez szum elewacji,
- mapa pokazuje przebieg i miejsca ryzyka,
- niepewność nie jest maskowana,
- DATA JSON jest źródłem prawdy.
```

Raport jest zły, jeśli:

```text
- minimalizuje unknown kosztem prawdy,
- przypisuje drogę obok,
- mówi „asfalt” tam, gdzie dane są niepewne,
- każe zapamiętywać siatkę 5 km,
- sortuje alarmy po powadze,
- pokazuje fałszywe nachylenia z szumu GPS.
```

---

# J. Najważniejsza lekcja

Nie optymalizujemy procentu `unknown`.

Optymalizujemy:

```text
- trafienie w właściwą drogę,
- prawdziwość danych,
- uczciwą niepewność,
- alarmy bezpieczeństwa,
- użyteczną strategię jazdy.
```

Fałszywa pewność jest gorsza niż „nie wiem”.

## C9. Kontrakt czasu przejazdu: data startu + średnia prędkość

Raport route report musi jawnie pokazywać:

```text
planned_date
planned_start_time
timezone
```

Te pola muszą być widoczne obok pogody, bo kontekst czasu startu jest częścią interpretacji warunków na trasie.

Raport route report musi też jawnie pokazywać:

```text
assumed_avg_speed_kmh
```

Średnia prędkość nie jest detalem technicznym obok ETA. Ona zmienia:

```text
- ETA per km,
- czas dotarcia do stref pogody,
- ocenę wiatru na odcinkach,
- ekspozycję na słońce / temperaturę / opady,
- timing alarmów i okien ryzyka.
```

W produkcji `avg_speed_kmh` powinno być wyliczane z historii użytkownika, a nie zgadywane:

```text
- wcześniejsze przejazdy tego użytkownika,
- historia tras podobnych,
- dobór podobnych jazd po dystansie, przewyższeniu, typie trasy i tempie,
- agregacja przez medianę lub trimmed median.
```

Fallback `18.0 km/h` jest dopuszczalny tylko wtedy, gdy nie ma żadnej sensownej historii. Taki fallback musi być oznaczony jako `low confidence`.
