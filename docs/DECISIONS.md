# QBot — Decyzje architektoniczne

> Jeden punkt prawdy dla decyzji projektowych. Najnowsze na górze.
> Konwencja: przed każdą edycją tego pliku → kopia `DECISIONS.md.bak.RRRRMMDD_GGMMSS`.

---

## 2026-06-30 — DECYZJA: 2C store wiring — route_elevation_samples + route_climb_events

**Status:** WDROZONE (silnik + writer + DDL + testy + orchestrator disabled). Tabele utworzone na qbot_v2. Read-path 2C (raport) NIETKNIETY.

**Tabele (DDL: `sql/route_elevation_store_v1.sql`), dzieci `route_base` `ON DELETE CASCADE`, `route_version_key` niesiony jako kolumna; `route_base` BEZ zmian:**
- `route_elevation_samples` — gesty profil 50 m, 1 wiersz/wezel. Surowa wysokosc trzymana wiernie (`elevation_m` NULL przy dziurze DEM); `source` + `smoothing_version`. Wygladzanie/podjazdy sa POCHODNE, nie materializowane tu. `UNIQUE (route_base_id, sample_index)`.
- `route_climb_events` — naglowek podjazdu + segmenty 100 m jako `segments_json` JSONB (seg_index, start_m, end_m, length_m, gradient_pct, category). `UNIQUE (route_base_id, event_index)`.

**Segmenty jako JSON** (nie osobna tabela) — zgodne z idiomem store (`segment_geojson`, `*_meta_json` to jsonb) i decyzja uzytkownika. Segmenty zawsze czytane razem z naglowkiem, zmienna licznosc, brak potrzeby zapytan po segmencie.

**Writer `qbot3/routes/route_elevation_store.py`** (lustro `route_base_store`/`route_surface_store`): `_db_conn`, `ensure_route_elevation(route_base_id|route_id)`, geometria z `route_base.source_path` (GPX) -> SRTM30m -> silnik (`route_elevation_engine`). CLI z `--repeat`.
- Idempotencja: `route_elevation_samples` upsert `ON CONFLICT (route_base_id, sample_index)` (liczba stala dla wersji); `route_climb_events` delete+insert (liczba zmienna), wszystko w jednej `conn.transaction()`.
- `build_rows()` = czysta funkcja dataclasses->wiersze (testowalna offline). `content_hash` (odczyt z DB, posortowany) jako dowod idempotencji.

**Orchestrator `route_precompute_orchestrator.py`:** dodany `ELEVATION_JOB` za bramka `QBOT_ROUTE_ELEVATION_ENABLED` (default `0`) przez `_effective_job_sequence()`. Przy `0` zachowanie BAJT-IDENTYCZNE (job nie wchodzi do sekwencji). Bez zmian w writerach 2B.1–2B.4, `route_analysis_run`, webhooku 2B.6.

**Bramki (dowod, nie na slowo):**
- testy offline: `tests.test_route_elevation_engine` 8/8, `tests.test_route_elevation_store` 3/3,
- orchestrator: OFF=4 joby (bez `route_elevation`), ON=5 (`route_elevation` ostatni),
- zywy zapis 55798129: `route_base_id=1`, 1424 probki, 1 podjazd; dwa przebiegi -> identyczny `content_hash`; `ascent_smoothed` 426.7 m vs RWGPS 403.

**Granice:** tabele zasilane TYLKO przez writer (jawnie lub orchestrator po wlaczeniu bramki); brak publicznych MCP tooli; raport trasy bez zmian.


## 2026-06-30 — DECYZJA: 2C — silnik przewyższeń i podjazdów (elevation/climb)

**Status:** decyzja architektoniczna zamknięta. Kod 2C jeszcze nie wdrożony (decyzja przed kodem). Osobna faza po 2B.5; orchestrator 2B.5 obejmuje TYLKO base/surface/landcover/poi.

**Audyt źródeł (zweryfikowany na żywo, nie z pamięci):**
- `tools/rwgps/climbs.py` = artefakt, błędny (trzy rozjeżdżające się logiki, martwy dla Alberta). NIE jest bazą. Do usunięcia po wejściu 2C.
- `route_brief`/`route_frames` 80 m = legacy/fallback (potwierdza decyzja 2026-06-28).
- `qbot3/artifacts/route_analyzer.analyze_stage_gpx` = dotąd najlepszy WŁASNY detektor (maszyna stanu z histerezą, max grade po oknie 100 m), ale próg ≥1 km/≥30 m → łapie tylko długie podjazdy. Baza algorytmu, nie gotowiec.
- **RWGPS API NIE zwraca podjazdów** (sprawdzone na 55798129): route detail (`/api/v1/routes/{id}.json`) bez pola `climb`; `/routes/{id}/climbs.json` i `/elevation.json` → 404; `?include=climbs`/`?climbs=true` ignorowane; `course_points` to wyłącznie nawigacja (Left/Right/Uturn…). Z RWGPS mamy tylko sumy `elevation_gain/loss`, gęsty ślad (1278 pkt) i nawierzchnię.
- Planowana trasa trafia na Karoo jako **GPX** — Hammerhead liczy Climbera sam na urządzeniu; nie ma gotowej listy do podebrania.
- Wysokość Karoo = otwarty stos DEM: **SRTM/GMTED2010/3DEP + Mapzen/Valhalla terrain** (atrybucja Hammerhead). Climber: progi **≥400 m i ≥3%** (tryb „All Climbs"), profil dzielony **co 100 m**, kolor wg gradientu.
- Valhalla `valhalla1.openstreetmap.de` `/height` = MARTWE (null wszędzie, też w Alpach) — to nie był błąd parsowania w poprzedniej sesji, instancja nie ma DEM. Nieużywalne.
- Działające otwarte DEM (z VPS): **opentopodata `srtm30m`** (rodzina Karoo — WYBRANE) oraz Open-Meteo GLO-90 (Copernicus 90 m — grubszy, limit/min, do profilu analitycznego co najwyżej).

**Źródło i metoda (przyjęte):**
- Siatka **50 m**, wspólna z nawierzchnią (decyzja 2026-06-30).
- `route_elevation_samples`: gęsty profil, źródło wysokości **SRTM30m (opentopodata)**. Surowe próbki trzymane wiernie + `source` + `smoothing_version`.
- Grade/ascent/podjazdy liczone z **LOKALNIE wygładzonego** profilu SRTM oknem **~200 m** (NIE globalnie — 400 m ścianki przeżywają). Okno wyznaczone EMPIRYCZNIE (kalibracja device-vs-SRTM, 3 górzyste jazdy — Castagneto/Suchedniów/Skarżysko: najbliżej barometru 250/150/250 → ~200 m). Surowy SRTM 50 m zawyża ascent +336..+652 m i rozdrabnia podjazdy na fantomy (do 22 zamiast 12) — nieużywalny bez wygładzenia.
- `route_climb_events` = **DWA POZIOMY**: (1) nagłówek podjazdu — start_m, end_m, length_m, elevation_gain_m, avg_gradient_pct, max_gradient_pct, severity, source, detection_version; (2) **segmenty 100 m z gradientem każdego** (profil ścianek, jak Climber) — liczone z WYGŁADZONEGO profilu (inaczej fantomowe ścianki z siatki 30 m). Sam `max_grade` nie mówi, czy ściana jest jedna czy pięć — dopiero rozkład 100 m to pokazuje.
- Detekcja progami Karoo: **≥400 m i ≥3%**. Precyzja do metra/0,1% świadomie nieistotna (120 vs 140 m, 4,5 vs 5% w jeździe bez znaczenia) — liczy się sygnatura podjazdu i profil ścianek.
- Idempotencja/wersjonowanie: `route_base_id + sample_index` / `route_base_id + event_index`, plus `route_version_key` (jak `route_base_store.py`). `smoothing_version`, `detection_version` jako stringi → wynik powtarzalny i wersjonowany.

**Rozdział warstw (kluczowy):**
- `route_elevation_samples` = fundament analityczny, budowany ZAWSZE (zasila ETA/wiatr/moc); może mieć własne wygładzanie.
- `route_climb_events` = warstwa pod sekcję raportu „Przewyższenia" (właściwa dla górzystego terenu), strojona pod ujęcie Climbera.

**Zastrzeżenia (uczciwie):**
- SRTM strojony pod barometr (fizyczna prawda przejazdu); Karoo używa SRTM, ale z własnym nieznanym wygładzaniem → zgodność BLISKA, nie co do metra. Pełna zgodność z Climberem wymagałaby porównania z eksportem z Karoo — poza naszą stroną.
- Pokrycie podjazdów device-vs-SRTM nigdy nie 100% w obie strony (inne źródło + barometr to faktyczna linia, SRTM to ślad GPS na siatce). Duże podjazdy zgadzają się zawsze; różnice na granicznych.
- opentopodata limity (1000/dobę, 1/s, 100 pkt/req): sporadyczny precompute jednej trasy OK (~7 req); przy backfillu wielu tras → cache albo własna instancja SRTM (miejsce na dysku jest).

**Granice 2C (czego NIE robi):** nie przepina raportu trasy; nie miesza elevation do `route_axis_segments`; nie używa 50 m jako jedynego kanonu dla podjazdów; nie rusza writerów 2B.1–2B.4; nie dodaje publicznych MCP tooli; nie zmienia `route_analysis_run`; nie odpala pełnych raportów. Orchestrator 2B.5 zostawia typowany, wyłączony punkt rozszerzenia na elevation/climb job.

**Pliki docelowe:** `qbot3/routes/route_elevation_store.py` + `tests/test_route_elevation_store.py` (lustro `route_base_store.py`: ten sam `_db_conn`, wejście `ensure_route_elevation(route_id)`, upsert z `route_version_key`, CLI). Writer: czyta DEM, zapisuje oba poziomy, idempotentny; nie dotyka raportu/POI/weather.

**Kalibracja jako powtarzalna metoda:** porównanie ramka-po-ramce device (`activity_record`, 1 Hz pozycja+wysokość, 335 jazd) vs SRTM na górzystych jazdach — stroi okno wygładzania i progi. Nie blokuje builda (okno ~200 m przyjęte).


## 2026-06-30 — DECYZJA: route_base, route_poi_layer i route_analysis_run jako rozdzielone warstwy trasy

**Status:** aktywna decyzja architektoniczna.

**Intencja:** QBot rozdziela fakty trasy, półstałe warstwy źródłowe i analizę konkretnego przejazdu. Nie mieszamy danych o trasie z overlayami zależnymi od `start_time`, prognozy i modelu ETA.

**route_base / route_axis_base:** zawiera tylko fakty i półstałe dane źródłowe trasy: `route_id`, `route_artifact_id`, `route_version_key`, `route_modified_at` / `route_updated_at`, `geometry_hash`, raw geometry reference, kanoniczną oś 50 m, `km_from`, `km_to`, `distance`, bazowe `elevation/slope`, oraz obiektywne dane źródłowe: `surface`, `highway`, `tracktype`, `landuse`, `natural`, `forest/wood`, `building/settlement context`, `water/river/lake context`, plus `quality/coverage/status` per source layer. Oś 50 m pozostaje warstwą pomocniczą do joinów, agregacji i raportowania przekrojowego, ale nie jest kanonicznym źródłem prawdy dla `elevation`, `climb` ani `gradient`.

**route_base nie zawiera gotowych ocen ani modeli pochodnych:** nie przechowuje `asphalt_heat_factor`, `sun/shade exposure factor`, `wind exposure factor`, `route risk factor`, `WBGT`, `cold-risk`, `weather`, `open_at_eta`, `recommended stops`, `nutrition/hydration` ani `resupply decision`. Te wartości są liczone później w `route_analysis_run` / `route_report_run` na podstawie `route_base`, `route_poi_layer`, `start_time`, prognozy, ETA i modeli.

**route_poi_layer:** może być półstałą warstwą przy `route_base`. Zawiera `poi_id` / `source_place_id`, `provider`, `name`, `category`, `lat/lon`, `km_on_route`, `distance_from_route_m`, `opening_hours`, `opening_hours_fetched_at`, `source_updated_at`, `confidence`, `validity_hint`, `stale_after`.

**route_poi_layer nie zawiera decyzji dla konkretnego przejazdu:** nie przechowuje `open_at_eta`, `selected_store_in_town`, `recommended_stop`, `refill_priority`, `detour_worth_it` ani `risk_of_closed_at_arrival`.

**route_analysis_run / route_report_run:** jest osobnym snapshotem analizy dla konkretnego `start_time`. Zawiera `route_id`, `route_artifact_id`, `route_version_key`, `start_time`, `assumed_speed_model`, `forecast_provider`, `forecast_fetched_at`, `report_generated_at`, `ETA` per segment, `weather_overlay` per segment, `WBGT_overlay` per segment, `cold_risk_overlay` per segment, `open_at_eta`, `selected POI stops`, `recommended_stop`, `refill_priority`, `enough_for_this_ride`, `selected_store_in_town`, `detour_worth_it`, `risk_of_closed_at_arrival`, `resupply plan` oraz ostrzeżenia o starych godzinach otwarcia.

**Wysokość i podjazdy jako osobna warstwa trasy:** dla przewyższeń nie opieramy się wyłącznie na 50 m axis. Potrzebne są dwie warstwy: `route_elevation_samples` jako gęstszy profil wysokości po oryginalnym GPX/RWGPS albo najgęstszym dostępnym profilu oraz `route_climb_events` jako wykryte podjazdy, krótkie ścianki i strome rampy. `route_analysis_run` ma te warstwy konsumować, nie być jedynym miejscem ich przechowywania.

**Pogoda i oceny czasowe jako overlay:** pogoda, WBGT i cold-risk nie są trwałymi cechami trasy. Są overlayem konkretnego uruchomienia raportu, zależnym od `start_time`, `forecast_fetched_at` i wybranego modelu ETA. Nie zapisujemy ich do `route_base` jako stałej prawdy.

**Półstałość i świeżość POI:** `route_poi_layer` i podstawowe `opening_hours` mogą być cache’owane przy wersji trasy, ale muszą mieć `fetched_at` i `stale_after`. Jeśli dane są stare, `route_analysis_run` ma pokazać `WARN` albo odświeżyć źródło przed użyciem.

**Webhook / web-book event:** gdy QBot dostaje informację o nowej trasie albo nowej wersji istniejącej trasy, powinien automatycznie uruchomić precompute tylko stałej i półstałej bazy trasy.

**Detekcja wersji:** nowa wersja trasy jest identyfikowana przez `route_id`, `route_modified_at` / `route_updated_at` ze źródła, `geometry_hash`, `route_artifact_id` oraz `route_version_key`.

**Automatyczny precompute:** webhook tworzy lub odświeża `route_base`, raw geometry reference, kanoniczną oś 50 m, `elevation_micro_profile`, `climb_events` / `steep_ramp_events`, surface source layer, land-cover / source context layer, `route_poi_layer`, `opening_hours` dla POI oraz `quality/coverage/status` per layer.

**Zakres precompute:** automatyczny precompute nie tworzy pełnego `route_analysis_run` zależnego od konkretnej daty i godziny. Nie tworzy `weather_overlay`, `WBGT_overlay`, `cold_risk_overlay`, `open_at_eta`, `selected_store_in_town`, `resupply plan`, `nutrition/hydration plan` ani final `route_report_run`, chyba że event jawnie zawiera `planned_start_time` i intencję przygotowania raportu dla konkretnego przejazdu.

**Kiedy powstaje run analityczny:** pełna analiza przejazdu powstaje jako osobny `route_analysis_run` / `route_report_run` na żądanie użytkownika, albo automatycznie tylko wtedy, gdy event zawiera `planned_start_time` i jawnie oznacza intencję przygotowania raportu dla konkretnego przejazdu.

**Idempotencja:** webhook dla tej samej `route_version_key` nie tworzy duplikatu. Może odświeżyć półstałe warstwy, jeśli są po terminie `stale_after`. Każdy przebieg zapisuje status: `pending`, `running`, `complete`, `failed`, `partial`.

**Separacja odpowiedzialności:** `route_base` jest trwałą bazą faktów i półstałych danych. `route_analysis_run` jest kasowalnym snapshotem analizy. Cleanup analiz będzie osobnym modułem później.

**Cel operacyjny:** pełny raport trasy składa `route_base`, `route_poi_layer` i `route_analysis_run`, zamiast mieszać dane stałe z czasowymi overlayami. Dzięki temu pogoda, WBGT, cold-risk i decyzje o POI są jednoznacznie przypięte do konkretnego startu, a nie do samej trasy.

## 2026-06-29 — Readiness diagnostics rozdzielają aktywne błędy od szumu

**Status:** wdrożone w diagnostyce, bez zmian runtime.

**Intencja:** `qbot_error_summary` rozdziela teraz `active_errors`, `historical_errors`, `expected_test_errors` i `malformed_legacy_records`. Readiness bazuje wyłącznie na `active_errors`, a nie na historycznych/testowych wpisach w `tool_calls`.

**Guard GATE:** `gate_hikconnect.py` pozostaje oczekiwaną zależnością legacy/QLab. Guard ma go raportować jako `INFO`/`expected_dependency`, nie jako warning blokujący readiness.

**Probe RWGPS:** `rwgps_storage_overview()` preferuje schemat `qbot_v2` dla tabel `route_artifacts`, `route_parse_results`, `route_surface_profiles` i `route_surface_segments`. Brak tabel w `public` sam w sobie nie oznacza missing schema.

**Cutover message:** `95%` w legacy cutover nadal oznacza, że legacy jest włączone. To nie jest błąd runtime, tylko stan przejściowy do pełnego cutoveru.

## 2026-06-29 — Route surface read-path passthrough dla raportu

**Status:** wdrożone w read-path, bez zmian schematu DB i bez zmian WEB.

**Intencja:** `qbot_route_tools.py` przekazuje dalej aktualny `surface_summary_json` shape do danych raportu, wraz z `surface_quality_status`, `tagged_surface_pct`, `inferred_surface_pct`, `unknown_surface_pct`, `geology_context`, `problem_segments`, `surface_percentages_raw` i `surface_percentages_refined`.

**Zgodność:** storage i schema DB pozostają bez zmian. HikConnect/GATE pozostają poza zakresem i nietknięte.

**Następny krok:** potwierdzić na publicznym `qbot.query`, że pełny raport używa `surface_summary_json`, pokazuje `geology_context` jako kontekst ryzyka i cache POI bez ciężkiego refreshu Overpass, a legacy segmenty zostają tylko fallbackiem.

**Regresja testowa:** `tests/test_route_report.py` pilnuje teraz, że full route report dla `55798129` renderuje `surface_summary_json` i `Geologia / podłoże`, nie wraca do legacy `33%`, a brak cache POI kończy się jawnym `PARTIAL` zamiast ciężkiego refreshu.

## 2026-06-29 — POI / zaopatrzenie w raporcie korzysta z cache i priorytetów PL

**Status:** wdrożone w read-path raportu, bez zmian schematu DB i bez ciężkiego refreshu w publicznym runtime.

**Intencja:** sekcja `POI / zaopatrzenie` w pełnym raporcie trasy ma czytać zapisany cache/artifact z punktami zaopatrzenia, pokazywać `km_on_route`, `distance_from_route_m`, `opening_hours`, `eta_at_poi` oraz status `OPEN_AT_ETA` / `UNKNOWN_HOURS` / `CLOSED_AT_ETA`, a nie odpalać publicznego Overpass refreshu.

**Priorytet produktu dla Polski:** sklepy spożywcze i stacje paliw są głównym źródłem zaopatrzenia, bary/restauracje/kawiarnie są pomocnicze, a publiczne `drinking_water` jest tylko bonusem. Brak fontann publicznych nie oznacza braku możliwości zakupu wody.

**Zachowanie awaryjne:** jeśli cache POI nie istnieje, raport pokazuje `UNAVAILABLE` albo `PARTIAL` z jawnym ostrzeżeniem. Legacy ścieżka pozostaje fallbackiem, ale nie może blokować całego raportu.

**Prezentacja A8 2026-06-29:** główna lista `POI / zaopatrzenie` pokazuje tylko punkty `hard_resupply` / `soft_food_stop` do 500 m od śladu. Punkty 500-1000 m mogą pojawić się wyłącznie jako `AWARYJNY_FALLBACK_1KM` przy checkpointach 25% / 50% / 75% trasy, jeśli w okolicy checkpointu nie ma żadnego `OPEN_AT_ETA` do 500 m. Punkty powyżej 1000 m nie trafiają do A8.

**ETA per raport 2026-06-29:** `eta_at_poi` i `OPEN_AT_ETA` / `CLOSED_AT_ETA` w A8 są liczone przy renderowaniu z `ride_start` raportu oraz `km_on_route`. Cache POI może zachować geometrię, godziny i kandydatów, ale nie może narzucać stałego ETA dla innego startu.

**Regresja testowa:** `tests/test_route_report.py` pilnuje, że raport pokazuje jawny status POI, kilometraż punktów, status godzin i klastrowanie, a brak cache nie wywołuje ciężkiej analizy.

## 2026-06-29 — Google Places jest primary dla hard_resupply

**Status:** wdrożone w route-poi analyzerze, bez zmian schematu DB i bez restartu usług.

**Intencja:** w analizie POI dla tras w Polsce `hard_resupply` ma pierwszeństwo z Google Places, a Overpass/OSM pełni rolę fallbacku lub uzupełnienia. Analiza działa po całej trasie w punktach/korytarzu, deduplikuje kandydatów po nazwie, dystansie, klastrze i kilometrze oraz ocenia godziny względem ETA.

**Zachowanie awaryjne:** jeśli Google nie daje kandydatów, Overpass nadal może podać punkt zaopatrzenia. Jeśli chunk się wywala, wynik ma jawne `PARTIAL` z technicznym powodem `analysis_timeout` / `overpass_timeout` / błędem providera.

**Regresja testowa:** dodano syntetyczne testy, które pilnują kolejności providerów, fallbacku Overpass oraz technicznego `PARTIAL` dla route-poi.

## 2026-06-29 — POI rozdziela supply_status od technical_completeness

**Status:** wdrożone w read-path raportu i analizie POI.

**Intencja:** `missing_chunks` z pomocniczego Overpass nie mogą same oznaczać, że zaopatrzenie jest `PARTIAL`, jeśli Google Places znalazł realne `hard_resupply` na trasie. Raport ma pokazywać osobno `supply_status` dla realnego zaopatrzenia oraz `technical_completeness` dla kompletności providerów pomocniczych.

**Reguła produktu:** `supply_status` opiera się na `hard_resupply`, `OPEN_AT_ETA` i długości luki między punktami, a `technical_completeness` wynika z `missing_chunks` i błędów providerów pomocniczych. W statusie zaopatrzenia wolno pokazać `RISK` dla realnej luki kilometrowej, ale nie `PARTIAL` tylko dlatego, że Overpass nie domknął wszystkich chunków.

**Regresja testowa:** testy pilnują, że Google Places primary może dać `supply_status=OK`, gdy techniczna kompletność pozostaje `PARTIAL`.

## 2026-06-29 — Route surface writer path zapisuje pełny aktualny engine output

**Status:** wdrożone w writer path, bez migracji DB i bez zmian WEB.

**Intencja:** `tools/rwgps/client.py` zapisuje teraz do `qbot_v2.route_surface_profiles.surface_summary_json` pełny aktualny engine output z `analyze_route_surface()`, przy zachowaniu kompatybilności przez merge legacy `surface_profile` + current result. Wykorzystywany jest istniejący `JSONB`, więc migracja schematu nie jest wymagana.

**Zapis segmentów:** `surface_segments_json` bierze segmenty z aktualnego wyniku engine, nie tylko z legacy payloadu. Testowo zapisano profile dla `55798129` i `55864231`.

**Następny krok:** sprawdzić, czy WEB/raport czyta nowe pola z `surface_summary_json` bez zmian w rendererze.

## 2026-06-28 — Overpass multi-endpoint fallback dla route_surface_engine

**Status:** wdrożone w kodzie, bez restartu usług i bez migracji DB.

**Intencja:** poprawić coverage dłuższych tras w `route_surface_engine_v1` bez podłączania Valhalli, przez fail-open fallback po globalnych publicznych instancjach Overpass.

**Default endpointy dla tras w Polsce:** `https://overpass-api.de/api/interpreter`, `https://overpass.private.coffee/api/interpreter`, `https://maps.mail.ru/osm/tools/overpass/api/interpreter`. Lista jest konfigurowalna przez `QBOT_OVERPASS_ENDPOINTS`. Regionalne instancje Swiss, Britain/Ireland, Virginia i Ethiopia nie są defaultem; `overpass.openstreetmap.ru` nie jest defaultem.

**Zachowanie produkcyjne:** tryb `first_success` jest domyślny; chunk zatrzymuje się na pierwszym endpointcie z HTTP 200. Timeout, HTTP 429 i HTTP 5xx przechodzą przez retry/backoff i następny endpoint. HTTP 400 kończy dany chunk bez retry, bo oznacza błąd query/syntax. Każdy chunk fail-open zostawia UNKNOWN/LOW_CONFIDENCE zamiast crasha.

**Metryki JSON:** `overpass_metrics` zawiera `endpoints_tried`, `endpoint_stats`, `chunks_total`, `chunks_ok`, `chunks_failed`, `timeout_count`, `http_error_count`, `cache_hit_count`, `selected_endpoint_per_chunk`. Wynik ma `quality_status` wg coverage, refined unknown i udziału inferencji.

**Diagnostyka mirrorów:** `QBOT_OVERPASS_PROBE_ALL=1` albo `analyze_route_surface(..., overpass_probe_all=True)` włącza `probe_all`, który odpytuje każdy default endpoint dla każdego chunka i zapisuje `overpass_probe.endpoint_comparison` z latencją, timeoutami, błędami HTTP oraz liczbą elements/ways/nodes/relations. Nie jest to default produkcyjny.

---

## 2026-06-28 — Geology context scaffold dla analizy nawierzchni

**Status:** wdrożone w kodzie, bez restartu usług i bez migracji DB.

**Intencja:** utrwalić `geology_context` jako stały etap produkcyjnego JSON analizy nawierzchni, ale bez ryzykownego podpinania zewnętrznych API w tej fazie. Geologia jest europejskim kontekstem interpretacyjnym dla całej trasy, nie źródłem prawdy surface.

**Kontrakt JSON:** top-level `geology_context` zawsze zawiera `enabled`, `status`, `provider`, `dominant_region`, `dominant_unit`, `units`, `sections`, `material_hint`, `confidence`, `source_resolution`, `sample_strategy`, `explanation`, `warnings`. Segmenty mogą mieć `geology_hint_applied`, `geology_material_hint` i `risk_flags`.

**Provider chain:** docelowo `EGDI` jest bazowym providerem dla całej Europy; krajowe providery są opcjonalnym enrichment/override dla obsługiwanych krajów, a `heuristic_region_v1` zostaje ostatnim fail-open fallbackiem. Docelowy porządek: 1) EGDI, 2) national provider enrichment tam, gdzie jest to sprawdzone, 3) `heuristic_region_v1`. Nie projektujemy `geology_context` jako listy ręcznych krajowych wyjątków. Włochy i Hiszpania były tylko testami konkretnych krajów, nie granicą systemu. Źródła do kolejnego audytu: Polska PIG-PIB/CBDG/GeoLOG/WMS/WFS, Europa EGDI/INSPIRE/OneGeology, Włochy ISPRA, Hiszpania IGME/REDIAM, a dla CZ/DE/AT/FR/SI/HR potrzebny jest osobny audyt.

**EGDI audyt 2026-06-28:** prototyp opiera się na `https://geoserver.geo-zs.si/egdi-surface-geology/gsmlp/wms` i `GetFeatureInfo` z `INFO_FORMAT=application/json` na warstwie `GeologicUnitView_Lithology`. To działa dla wielu punktów europejskich i zwraca `lithology`, `representativeAge_uri`, `source`, `metadata_uri` oraz geometrię. Pan-europejny OGC API `.../ogc/features` istnieje, ale `collections/GeologicUnitView/items?bbox=...` zwracał w tym audycie `500`/`NullPointerException`, więc nie jest jeszcze bazą prototypu. OneGeology sprawdził się tylko jako techniczny fallback WMS/WFS bez praktycznego coverage dla punktów testowych w Europie Środkowej i Południowej.

**Integracja hook 2026-06-28:** `tools/rwgps/geology_context.py` używa teraz EGDI jako pierwszego realnego provider chain. Jeżeli EGDI zwraca `WARN` albo `UNAVAILABLE`, kod wraca do `heuristic_region_v1`. National provider enrichment nadal pozostaje tylko miejscem na przyszłą implementację.

**Próbkowanie:** geologia używa centroidu, bbox i punktów kontrolnych co 10 km; przy krótkich trasach minimum centroid + start + finish. Nigdy nie używa próbkowania 50 m, bo 50 m dotyczy wyłącznie nawierzchni.

**Fail-open:** jeśli region nie pasuje albo provider zawiedzie, wynik zostaje `WARN`/`UNAVAILABLE`, material hint pozostaje `unknown`, a analiza nawierzchni działa dalej. Heurystyka może dodać tylko kontekst/ryzyka dla UNKNOWN, low confidence i inferowanych track/path/ground, bez nadpisywania `surface_raw`.

---

## 2026-06-28 — Metryki jakości klasyfikacji nawierzchni

**Status:** wdrożone w kodzie, bez restartu usług.

**Intencja:** odróżnić coverage OSM od jakości klasyfikacji surface. Wynik ma pokazywać, ile dystansu pochodzi z jawnego tagu `surface`, ile z inferencji (`highway`, `tracktype`, landcover/service defaults), a ile pozostaje UNKNOWN.

**Kontrakt JSON:** `route_surface_analysis_v1` dodaje `tagged_surface_pct`, `inferred_surface_pct`, `unknown_surface_pct`, `inference_sources_pct`, `inference_sources_m` oraz `problem_segments.top_unknown/top_inferred`. Segmenty mają `classification_source`.

**Quality status:** `GOOD_TAGGED` oznacza dobry coverage i niewielką inferencję; `GOOD_INFERRED` oznacza dobry coverage i niski UNKNOWN, ale istotna część wyniku jest inferowana. `PARTIAL` i `LOW_CONFIDENCE` zostają dla słabszego coverage/UNKNOWN. Stare pola `coverage_pct`, `unknown_pct_raw`, `unknown_pct_refined`, `quality_status` i `overpass_metrics` pozostają kompatybilne.

---

## 2026-06-28 — Gravel surface engine po rzeczywistym śladzie

**Status:** faza 1 wdrożona w kodzie, bez migracji DB i bez restartu usług.

**Intencja:** migrujemy główną analizę nawierzchni gravelowej z `route_frames`/pudełek 80 m na analizę po rzeczywistym śladzie GPX/TCX/JSON/RWGPS. `route_frames` zostają jako legacy/fallback dla profilu, pogody, debug i agregacji, ale nie są źródłem prawdy nawierzchni.

**Parametry nawierzchni:** domyślne próbkowanie surface = 50 m; primary Overpass corridor = 50 m; fallback corridor = 80 m; confidence match distance: 0-25 m high, 25-50 m medium, 50-80 m low. Dystans 150 m nie jest normalnym matchem; może istnieć tylko jako awaryjny debug/fallback z `very_low` i ostrzeżeniem.

**Refinementy:** Valhalla jest fallback/refinement, nie zamiennik OSM. Landcover jest contextual refinement dla UNKNOWN/low/conflict, nie twarde źródło surface. `surface_raw` musi być zachowane, a inferencje mają method/confidence/explanation.

**Geology context:** geologia jest stałym etapem regionalnym, fail-open. Strategia: centroid + bbox + punkty kontrolne co 5-10 km, ewentualne sekcje tylko dla dużych jednostek; bez próbkowania geologii co 50 m. Wynik ma być cache'owany per route/artifact hash/bbox/provider. Provider chain: krajowy -> europejski/globalny fallback. W fazie 1 provider jest jawnie `UNAVAILABLE`, żeby nie dawać fałszywej precyzji.

**WEB:** WEB jest rendererem gotowego DATA JSON/route_surface_analysis_v1, nie źródłem prawdy ani miejscem liczenia nawierzchni.

---

## 2026-06-28 — Audyt i sprzątanie dokumentacji MD

**Status:** wykonane.

Przeprowadzono audyt 100% plików MD w repo i w `/opt/qbot/docs/`. Wynik:

- **29 plików wycofanych** → `docs/archive/retired_20260628/` (prefix `RETIRED_`), w tym 6 plików z `/opt/qbot/docs/` (QBOT_BIBLE, QBOT_KNOWHOW, QBOT_PROJECT_INSTRUCTION_LOCAL i inne).
- Oryginały w `/opt/qbot/docs/` zastąpione stub-ami z redirectem (plik `qbot_query_router.py` referencjonuje QBOT_BIBLE — stub zapobiega błędom przy odczycie).
- `docs/archive/README.md` zaktualizowany o nową sekcję `retired_20260628`.

**Aktywna mapa dokumentów po sprzątaniu:**
- `CLAUDE.md` + `AGENTS.md` — instrukcje pracy Claude/agentów
- `docs/CONTEXT.md` — auto-gen (aktualizuj przez `scripts/build_context.py`)
- `docs/architecture/QBOT_ARCHITEKTURA_QBOT3.md` — kanon architektury
- `QBOT_INSTRUCTIONS.md` — runtime prompt Alberta
- `docs/DECISIONS.md` — ten plik
- `docs/architecture/QBOT_TOOL_REGISTRY_MAP.md` — mapa narzędzi (54 narzędzia, 2026-06-28)
- `docs/architecture/MODELQ.md` — dokumentacja FitModel/ModelQ
- `docs/architecture/ROUTE_REPORT_WEB_ARCHITECTURE.md`, `SURFACE_INTEGRATION_SPEC.md`, `RIDEPHOTO_QBOT_MODUL_SPEC.md` — specs modułów
- `docs/RAMAT_WEB.md`, `docs/Qbot_Route_Logistics.md`, `docs/QBOT3_TELEGRAM_TRANSPARENT_UI.md`, `docs/qbot_mcp_connector.md` — operacyjne
- `governance/` — polityki

---

## 2026-06-22 — Przełącznik modeli Alberta + fixy (ucinanie wyników, loteria route_id) [dokumentacja wdrożonego]

**Status:** wdrożone i ZACOMMITOWANE. Wpis dokumentuje zmiany już obecne w kodzie (TASK 03 = tylko spisanie, bez zmian kodu).

### 1. Przełącznik modeli Alberta (gpt / gemini / claude)
- Moduł `qbot3/llm/model_profiles.py`: słownik `PROFILES` z 3 profilami; każdy ma jawny `base_url` + `model` + `key_env` (niezależne od QGPT_*):
  - `gpt` → base `QBOT_PLANNER_BASE_URL` (default `https://api.openai.com/v1`), model `QBOT_PLANNER_MODEL` (default `gpt-5.4-mini`), klucz `QBOT_PLANNER_API_KEY`
  - `gemini` → `https://generativelanguage.googleapis.com/v1beta/openai`, `gemini-2.5-flash`, klucz `GEMINI_API_KEY`
  - `claude` → `https://api.anthropic.com/v1/`, `claude-sonnet-4-6`, klucz `ANTHROPIC_API_KEY`
  - `DEFAULT = gemini`.
- Aktywny profil w `data/albert_model.json` (`{"active": "..."}`) — zmiana BEZ restartu (plik czytany przy każdym `get_active()`/`resolve()`). Stan na 2026-06-22: `active=claude`.
- API modułu: `get_active()`, `set_active(name)`, `resolve()` (zwraca base_url/model/api_key/key_present z env), `public_status()`.
- `qbot3/agent_runtime.py` (l. 256–269): orkiestracja woła `resolve()` i przekazuje profil do `albert_run` jako `override_api_key` / `override_base_url` / `override_model`.
- Komendy (deterministyczne, `qbot_query_handler.py` l. 392–395 + `handle_query` l. 4865–4879):
  - „model gpt|gemini|claude" (+ synonimy „przełącz na…", „użyj…", „albert na…") → `set_active` + potwierdzenie; ostrzega, gdy brak klucza dla profilu.
  - „jaki model" / „aktywny model" / „który model" / „status modelu" → `public_status` (label, model, klucz jest/BRAK).
- `qbot3/llm/albert.py` `_gen_kwargs(model, base_url, max_n)` (l. 33–43): modele OpenAI gpt-5+/o-series → `max_completion_tokens`, bez `temperature`; pozostałe → `max_tokens` + `temperature=0`.
- Klucz `ANTHROPIC_API_KEY` skonsolidowany do autorytatywnego env `/etc/qbot/qbot-api.env`.

### 2. Fix ucinania długich wyników (profil km-po-km)
- Root cause: wynik KAŻDEGO narzędzia podawany modelowi był cięty do 4000 znaków → `route_profile_detail` urywał się ~km19.
- Fix: relay 4000 → 16000 (`albert.py` l. 441); `max_tokens` 1200 → 5000; `build_detail` w `tools/rwgps/route_brief.py` przepisany na zwięzły (~3,8 tys. znaków).
- Efekt: pełny profil 0→99,3 km w jednym wywołaniu.

### 3. Fix loterii `route_id` (nazwa zamiast numeru)
- Problem: narzędzia tras przy `route_id` = NAZWA zwracały cichy fail ze `status: OK`.
- Fix (`qbot_route_tools.py`): gdy `route_id` nie jest numeryczny → `_resolve_rwgps_route_hint(name)` zamienia nazwę na ID; gdy nierozwiązywalne → `None` (fallback na najnowszą).

### Stan w git
Zmiany zacommitowane: `2f5b62a` + `d8591c4`. HEAD na 2026-06-28: `9b44531`.

---

## 2026-06-21 — ZASADA: instrukcja Alberta zawsze zsynchronizowana z narzędziami (OBOWIĄZKOWE)

**Status:** obowiązujące, twarda reguła procesu.

**Problem:** narzędzia (`qbot3/tool_registry.py`) zmieniają się szybciej niż prompt Alberta (`_SYSTEM` w `qbot3/llm/albert.py`). Gdy dodasz/zmienisz/usuniesz narzędzie, a prompt zostaje w tyle, Albert nie wie że narzędzie istnieje albo do czego służy → myli intencje, wpada w złe narzędzie.

**Reguła:** KAŻDA zmiana narzędzi LUB domen/intencji MUSI być w tym samym kroku odzwierciedlona w prompcie Alberta. Definicja „gotowe" = kod + wpis w rejestrze + AKTUALNY prompt Alberta. Bez aktualizacji promptu zmiana jest NIEUKOŃCZONA.

**Wykryte przy okazji (dług do spłacenia w prompcie _SYSTEM):**
- Brak sekcji o trasach w prompcie → dopisać reguły doboru narzędzi tras: `route_plan_analysis` (podsumowanie planu), `route_profile_detail` (szczegóły z ramek), `ride_analysis` (wykonana jazda/FIT).
- „Styl odpowiedzi" każe streszczać → Albert ucina długie wyniki. Dopisać: gotowe analizy (pole analysis) pokazuj w całości, nie skracaj.
- `build_tools_spec` obcina opis narzędzia do 500 znaków → opisy < 500 znaków, rozróżnienie na początku.

---

## 2026-06-21 — Scalenie analizy tras w jeden pipeline (planowana + wykonana)

**Status:** zatwierdzone i ZAIMPLEMENTOWANE (Faza A + Faza B, rdzeń działa E2E). Stan: zacommitowane.

### Architektura — siatka pudełek 80 m

Trasa = rząd pudełek ~80 m (wspólna siatka geograficzna dla faz A i B).

**Faza A — trasa planowana:** pudełka PRAWDY O DRODZE (nawierzchnia, nachylenie, prognoza pogody + kierunek wiatru względem trasy, briefing ryzyka, forma, wellness, prognoza glikogenu).

**Faza B — trasa wykonana (FIT):** nakłada realny przejazd na te same pudełka. DIFF trasa-vs-plan (próg zboczenia 60 m), realna pogoda (Open-Meteo archive), wnioskowanie o wietrze (korelacja nadwyżki prędkości), werdykt przyłożony do formy+wellness.

### Tabele (qbot_v2) — dodane w tej sesji
`route_frames`, `route_frame_weather`, `ride_frames`.

### Moduły (tools/rwgps/) — dodane
`route_frames.py`, `route_weather.py`, `route_brief.py`, `ride_overlay.py`, `ride_verdict.py`.

### Wpięcie w bota (Albert)
Narzędzia w `qbot3/tool_registry.py`: `route_plan_analysis` (zaplanowana trasa/track), `ride_analysis` (FIT/wykonana jazda). Routing LLM-first przez Alberta — VNEXT nie przechwytuje tych zapytań.

### Sprzątanie (wykonane 2026-06-21)
- `archive/route_legacy_2026-06/` — 22 skrypty starego stacku G (g1-g15, analyze_route_*, route_logistics_*) + `tools/rwgps/overpass_cache.py`. Zero importów w żywym kodzie.
- `scripts/build_context.py` przepisany (usunięto błędny opis „Router v2 → Planner v2 → core/planner.py"; `core/planner.py` NIE ISTNIEJE).
- `qbot_query_handler.py`: usunięty martwy keyword-hack (gałęzie + funkcje `_handle_route_plan_analysis`/`_handle_ride_analysis`).

### TODO (faza B, refinementy — NIE zrealizowane)
- Skojarzenie FIT ↔ plan: auto po starcie+dacie (zaakceptowane); próg zboczenia 60 m (zaakceptowane).
- Przeliczanie nawierzchni tylko dla off_plan > 200 m.
- Carry-forward FTP na dni odpoczynku.
- Pogoda wielopunktowa.
- Wygaszenie starego tagowania nawierzchni z FIT (obecnie fallback w `fitmodel/surface_tag.py`).

---

## 2026-06-21 — Rozstrzygnięcia przed Fazą B

**Pogoda — źródło:** OpenWeatherMap PRIMARY, Open-Meteo FALLBACK. OWM `/data/2.5/forecast` (3-godz., 5 dni); dla dat > 5 dni automatyczny fallback na Open-Meteo (16 dni).

**Bugfix loaderów .env:** pliki `tools/rwgps/*.py` nie zdejmowały cudzysłowów z wartości → klucz OWM leciał z apostrofami → 401. Poprawione w `route_weather`/`route_frames`/`route_brief`.

**Forma „na dziś":** `fitmodel_daily` cron (`daily_job`, 04:45) działa poprawnie. FTP liczony z danych jazdy, wypełnia tylko dni z przejazdem. `route_brief` bierze ostatni niepusty FTP — poprawnie.

---

_Uwaga (2026-06-28): ostatni wpis w tej sekcji zawierał notatkę „STAGED, niezacommitowane" — nieaktualne. Zmiany zostały zacommitowane w `2f5b62a` i `d8591c4`. HEAD: `9b44531`._

Aktualizacja 2026-06-29: route surface writer ma quality gate w `tools/rwgps/client.py`. Partial wynik Overpass lub `LOW_CONFIDENCE` nie nadpisuje dobrego profilu dla tej samej trasy, jeśli istnieje już profil `GOOD_TAGGED` albo `GOOD_INFERRED` z lepszą jakością. Schemat DB bez zmian. Słaby wynik bez lepszego istniejącego profilu może być zapisany z warningiem `LOW_QUALITY_PROFILE_NO_BETTER_EXISTING_PROFILE`. HikConnect/GATE pozostają poza zakresem i nietknięte.
## 2026-06-30 — DECYZJA: etapowanie DB route_base / route_axis / route_analysis_run

**Status:** aktywna decyzja architektoniczna.

**Intencja:** przed implementacją migracji QBot rozdziela docelowy schemat tras na etapy, żeby nie mieszać faktów trasy, półstałych warstw i snapshotów analiz przejazdu.

**Faza 2A — minimalny fundament DB:** wdrażamy tylko tabele wymagane do poprawnego rozdziału bazy trasy od analiz:
- `route_base`,
- `route_axis_segments`,
- `route_surface_layer`,
- `route_landcover_layer`,
- `route_poi_layer`,
- `route_precompute_jobs`,
- `route_analysis_run`.

**Zakres Fazy 2A:** `route_base` i `route_axis_segments` są trwałym fundamentem wersji trasy. `route_surface_layer`, `route_landcover_layer` i `route_poi_layer` są półstałymi warstwami źródłowymi. `route_precompute_jobs` kontroluje automatyczne przeliczenia po webhooku lub backfillu. `route_analysis_run` jest kasowalnym snapshotem konkretnej analizy przejazdu.

**Nie dublujemy bytów:** na tym etapie nie tworzymy osobnej tabeli `route_report_run`. Render raportu jest atrybutem `route_analysis_run` przez `rendered_report_artifact_id`.

**Faza 2B / 2C — później:** odkładamy na kolejne etapy:
- `elevation_micro_profile`,
- `route_climb_events`,
- znormalizowane segmentowe overlaye pogody / WBGT / cold-risk,
- osobny `route_report_run`, jeśli raport zacznie mieć własny cykl życia i wersjonowanie.

**Legacy:** `route_frames` i `route_frame_weather` pozostają legacy/fallbackiem. Nie są nowym modelem docelowym i nie mogą stać się drugą prawdą obok `route_axis_segments`.

**Idempotencja:** `route_base` jest unikalne po `route_id + route_version_key`. Joby precompute są idempotentne po `route_version_key + job_type` albo jawnej wartości `idempotency_key`. `route_analysis_run` może mieć wiele rekordów dla tej samej wersji trasy, bo zależy od `requested_start_time`, prognozy i modelu prędkości.

**Cleanup:** czyszczenie dotyczy tylko `route_analysis_run` i jego przyszłych child-overlayów. `route_base`, `route_axis_segments` i półstałe warstwy trasy nie są usuwane w ramach cleanupu analiz.

**Reuse istniejących analyzerów:** Faza 2A nie tworzy nowych kalkulatorów powierzchni, land-cover, POI, pogody ani raportu. Nowy kod ma być głównie kontraktem DB, writerem wyników i orkiestratorem precompute. Źródłem obliczeń pozostają istniejące narzędzia:
- `route_artifacts` i `route_parse_results` dla faktów trasy,
- parser RWGPS/GPX dla artefaktu i geometrii,
- `route_surface_engine` dla segmentacji 50 m i nawierzchni,
- `_persist_route_surface_profile` / `route_surface_profiles` jako obecny zapis legacy surface,
- `surface_landcover` oraz `route_brief.build_detail(..., land_cover=True)` dla land-cover/context,
- obecny POI analyzer, Google Places, Overpass fallback i `poi_open_window` dla POI oraz `opening_hours`,
- `qbot_route_report_tool`, `qbot_route_analysis_tool`, `route_weather`, WBGT toolchain, speed model i POI ETA/opening-hours evaluator dla `route_analysis_run`.

**Zakaz dublowania:** Nie wolno pisać równoległego analyzera surface, land-cover, POI, weather, ETA/opening-hours ani raportu, jeśli istniejące narzędzie może zostać użyte jako źródło danych. Wyjątkiem jest tylko adapter/writer/orchestrator, który zapisuje wynik istniejącego toola do nowych tabel i pilnuje `route_version_key`.
