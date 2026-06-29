# QBot — Decyzje architektoniczne

> Jeden punkt prawdy dla decyzji projektowych. Najnowsze na górze.
> Konwencja: przed każdą edycją tego pliku → kopia `DECISIONS.md.bak.RRRRMMDD_GGMMSS`.

---

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
