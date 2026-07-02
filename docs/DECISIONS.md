# QBot — Decyzje architektoniczne

> Jeden punkt prawdy dla decyzji projektowych. Najnowsze na górze.
> Konwencja: przed każdą edycją tego pliku → kopia `DECISIONS.md.bak.RRRRMMDD_GGMMSS`.

---

## 2026-07-02 — DECYZJA: route_recompute z parametrem scope (all | poi)

**Status:** wdrozone. Testy zielone (test_route_precompute_orchestrator: 3 nowe routingu + 1 live skip; test_route_precompute_trigger 17). Okablowanie zweryfikowane na zywo (narzedzie ma arg scope, prompt Alberta zawiera scope='poi', sygnatura orkiestratora zaktualizowana).

**Problem/potrzeba (2 scenariusze uzytkownika):**
1. Pobralem trase z RWGPS, ale nie zdecydowalem sie jej przeliczyc — chce uruchomic pelny przelicz recznie.
2. Wracam do JUZ przeliczonej trasy po ~pol roku — chce odswiezyc TYLKO POI (sklepy/woda/godziny), bo reszta danych (osie, nawierzchnia, wysokosci) sie nie zmienia.

Dotychczas route_recompute robil ZAWSZE pelny przelicz (przebudowa route_base od GPX + cala sekwencja). Brak zawezania.

**Decyzja:** route_recompute dostaje opcjonalny scope. Pelny przelicz pozostaje DOMYSLNY (scenariusz 1); dokladamy tryb POI-only (scenariusz 2). NIE zawezamy calkowicie do POI — oba tryby potrzebne.

**Implementacja:**
- route_precompute_orchestrator.ensure_route_precompute(): nowy arg scope="all"|"poi" (walidacja ValueError dla innych). scope="all" = dotychczasowa sciezka (przebudowa base + _effective_job_sequence + pruning do 3 wersji). scope="poi" -> nowa funkcja _ensure_route_precompute_poi_only.
- _ensure_route_precompute_poi_only(): NIE wola ensure_route_base (nie parsuje GPX), odczytuje istniejacy aktywny route_base (_route_base_row); jesli brak -> LookupError z podpowiedzia "uruchom pelny przelicz scope='all'". Uruchamia WYLACZNIE job route_poi (ensure_route_poi, ktory od 2026-07-02 pobiera POI na zywo + zapisuje route_poi_meta). Rejestruje w route_precompute_jobs. NIE przycina wersji (POI-only nie tworzy nowej wersji). Zwrotka: scope="poi", retention=None.
- Zwrotka pelnego przeliczu dostala pole scope="all".
- tool_registry._load_route_recompute_tool: arg scope w args_schema + opis kiedy 'all' a kiedy 'poi'; wrapper mapuje warianty (poi/tylko_poi/...) na "poi", reszta -> "all"; note zalezny od scope.
- Prompt Alberta (qbot3/llm/albert.py _SYSTEM): zaktualizowany w TYM SAMYM commicie (twarda zasada: zmiana narzedzia = zmiana promptu razem) — opisuje kiedy scope='all' (trasa pobrana lecz nieprzeliczona / po odmowie w Telegramie), a kiedy scope='poi' (odswiezenie samego POI juz policzonej trasy).
- Testy: TestRoutePrecomputeScopeRouting (bez zywej bazy) — walidacja scope, scope='poi' omija ensure_route_base, scope='all' domyslnie do niej siega.

**Dowod na zywo (POI-only fetch) ODLOZONY:** sciezka POI-only wola ensure_route_poi = realny fetch Google Places/Overpass (koszt API). Nie uruchamiano automatycznie — to czesc osobno oczekujacego "finalnego przeliczenia trasy testowej", ktore przy okazji zapelni route_poi_meta.

**Nastepne (zatwierdzone, osobno):** ozywienie landcover w ocenie nawierzchni przez WorldCover (lokalne kafle zamiast Overpass) — wymaga osobnego doprecyzowania (mapowanie klas, weryfikacja na trasie); tylko dla odcinkow bez tagu OSM (tag wygrywa).

---

## 2026-07-02 — DECYZJA: nowa tabela route_poi_meta + raport czyta POI WYLACZNIE z bazy (przeciek nr 2)

**Status:** wdrozone. DDL zaaplikowany na zywo (23 kolumny), writer/kanoniczny odczyt/raport podlaczone, testy zielone (test_route_report 64, test_route_poi_store, test_route_canonical_read, test_poi_open_window 5). Dowod na zywo (trasa 55864231): raport czyta 13+12+2+20 POI z route_poi_layer, version-guard=OK.

**Problem (przeciek nr 2 — krok 5 / raport):** qbot_route_report_tool czytal POI z DWOCH miejsc: licznik z bazy, ale TRESC (nazwy sklepow, godziny, luki, klastry) bezposrednio z plikow /opt/qbot/artifacts/reports/poi_analysis_<id>_*.json oraz poi_positions_<id>.json (funkcje _read_poi_analysis_cache i _read_poi_positions_cache globowaly dysk po numerze trasy). To ten sam typ przecieku co krok 3 — raport ma czytac z kanonicznej bazy, nie z przypadkowych artefaktow.

**Brakujace dane (opcja B, wybrana przez uzytkownika):** metadane JAKOSCI analizy POI sa liczone na poziomie CALEJ trasy (nie per-punkt) przez analyze_route_poi_artifact: supply_status, technical_completeness, najdluzsza luka, liczniki open/unknown/closed, poi_source_mode, google_supply_count, missing_chunks (ktore chunki nie pobraly sie z Overpass). Te nie mieszcza sie w per-punktowej route_poi_layer i nie da sie ich odtworzyc z zapisanych punktow (missing_chunks to artefakt momentu pobrania). Decyzja: nowa tabela.

**Nowa tabela qbot_v2.route_poi_meta** (sql/route_poi_meta_v1.sql): jeden wiersz na wersje trasy (UNIQUE route_base_id), dziecko route_base ON DELETE CASCADE (zero sierot, kasuje sie z trasa jak reszta warstw). Kolumny: analysis_status, supply_status, technical_completeness, supply_longest_gap_km/_from_km, supply_open/unknown/closed_count, poi_source_mode, google_supply_count, missing_chunks_count, km_from/km_to, avg_speed_kmh, fetched_at, missing_chunks_json, buffers_json.

**Zmiany:**
- route_poi_store.py: _build_poi_meta_row + _upsert_route_poi_meta; ensure_route_poi zapisuje meta w TEJ SAMEJ transakcji co punkty (fetched_at = moment pobrania). Zwrotka dostala supply_status/technical_completeness/missing_chunks_count/fetched_at.
- route_canonical_read.py: _poi_meta_row czyta route_poi_meta; read_canonical_route wystawia canonical_poi_meta.
- qbot_route_report_tool.py: _read_poi_analysis_cache i _read_poi_positions_cache przepisane — czytaja WYLACZNIE z bazy przez read_canonical_route (route_poi_layer + canonical_poi_meta), zero globowania dysku. Zwracaja ten sam ksztalt co dawny cache dyskowy (mapowanie km_on_route->route_km, distance_from_route_m->distance_to_track_m, opening_hours->opening_hours_osm, provider->open_source), wiec render POI bez zmian. generated_at = route_poi_meta.fetched_at. Dodano linie raportu "Dane POI z dnia: RRRR-MM-DD".

**Version-guard:** dane POI sa Z DEFINICJI z aktywnej wersji trasy (czytane z route_poi_layer pod aktywnym route_base), wiec kotwiczymy blok na route_artifact_id + sha256 z route_base (identyczne z aktywna wersja) -> guard OK. NIE kopiujemy created_at/updated_at (inne zrodlo dat -> falszywy mismatch).

**Do domkniecia przy finalnym przeliczaniu:** route_poi_meta zapelni sie dla istniejacych tras dopiero przy recompute (writer zweryfikowany testami + na zywo, ale realny wiersz meta powstanie przy pobraniu). Do 55864231 obecnie meta=NULL -> raport pokazuje POI z bazy, ale supply_status/generated_at puste do przeliczenia.

**Otwarte (pytanie uzytkownika):** czy route_recompute umie zawezic zakres do samego POI (bez pelnego przeliczania) — do zbadania osobno.

---

## 2026-07-02 — DECYZJA: zasilanie route_poi_layer ZAWSZE na zywo; usuniety przeciek czytania cudzych plikow z dysku + mechanizm 14-dni

**Status:** wdrozone i zweryfikowane (import OK, funkcja/stala usuniete, testy zielone: test_route_poi_store, test_poi_open_window, test_route_report 64).

**Problem (przeciek granicy):** ensure_route_poi (writer warstwy route_poi_layer, krok 3 — telegram_confirm/precompute) mial funkcje _cached_route_poi_analysis, ktora ZANIM zapytala Google/OSM, przeszukiwala /opt/qbot/artifacts/reports/ (i /old/reports/) po plikach poi_analysis_<route_id>_*.json i podnosila najnowszy pasujacy PO SAMYM NUMERZE TRASY. To lamie zasade granicy: writer bazy wolno zasilac WYLACZNIE z jego wlasciwego zrodla (tu: Google Places + Overpass na zywo, przez analyze_route_poi_artifact), nigdy z cudzych, niekontrolowanych artefaktow lezacych we wspolnym folderze raportow. Zbadano na zywo (trasa 55864231): job route_poi w precompute trwal 71 ms (odczyt pliku), nie kilka-kilkanascie s (realny fetch) — dowod, ze krok 3 recyklingowal plik z 2026-06-30 zamiast pobrac swieze dane. Plik mial nawet metke project_id="tuscany_2026" (inny projekt).

**Zasada (doprecyzowana wczesniej z uzytkownikiem):** autorytet zrodla jest PER WARSTWA. Kazde dziecko trasy wolno zasilac tylko z jego zadeklarowanego zrodla — zewnetrzne API (Overpass/Google/opentopodata) ALBO wewnetrzne narzedzie QBot na lokalnych kaflach (WorldCover). Lokalny cache Overpass w analyze_route_poi_artifact (_geofabrik_cache_candidates, /artifacts/overpass_cache) jest DOZWOLONY — to wewnetrzne zrodlo warstwy, nie cudzy raport. Zakazane bylo tylko podnoszenie gotowych poi_analysis_*.json z /artifacts/reports.

**Co zrobiono w qbot3/routes/route_poi_store.py:**
- Usunieto funkcje _cached_route_poi_analysis w calosci.
- ensure_route_poi ZAWSZE wola analyze_route_poi_artifact (zywe Google+Overpass) -> route_poi_layer. fetched_at = moment tego pobrania (uczciwe; wczesniej bywalo klamstwem "teraz" nad starym plikiem).
- Usunieto stala POI_CACHE_MAX_AGE_DAYS=14 i cala logike auto-refresh po 14 dniach (cofniete z commita 3ded59b). Powod: auto-odswiezanie po cichu generowaloby platne zapytania Google przy samym otwarciu starego raportu, bez wiedzy uzytkownika. Odswiezenie ma byc JAWNA decyzja uzytkownika (route_recompute), a raport ma pokazywac date danych POI.
- Zostawiono status="stale" per punkt (_stale_after_for_item, timedelta) jako uczciwy znacznik wieku pojedynczego POI.

**Zwiazane / do zrobienia:** (krok 5) raport route_report nadal czyta POI bezposrednio z pliku (_read_poi_analysis_cache) zamiast z route_poi_layer — osobny przeciek tej samej granicy, do naprawy w nastepnej kolejnosci. Pytanie otwarte: czy route_recompute umie zawezic zakres do samego POI.

---

## 2026-07-02 — DECYZJA: usuniecie warstwy route_landcover_layer (OSM land-cover) — zastapiona przez WorldCover/shade

**Status:** wdrozone. Kod usuniety, tabela qbot_v2.route_landcover_layer ZOSTAJE (usuniemy przy pelnym przeliczaniu wszystkich tras).

**Powod:** route_landcover_layer (OSM land-use przez Overpass) i route_shade_layer (ESA WorldCover, lewo/srodek/prawo od osi) opisuja to samo — otoczenie trasy. WorldCover wygral: dokladniejszy, aktualny, uzywany w raporcie (sekcja A0B). Legacy landcover trafial do raportu WYLACZNIE jako liczba w liczniku warstw, zadna jego tresc nie byla renderowana. Dodatkowo jego job pobieral z Overpass ~48 s przy kazdym przeliczeniu trasy (zbadano na zywo, trasa 55864231: landcover job 23:06:45->23:07:33). Decyzja uzytkownika: nie zostawiac martwych warstw ("za tydzien znow bedziemy analizowac co to jest").

**Co usunieto:**
- qbot3/routes/route_landcover_store.py (writer) + tests/test_route_landcover_store.py — pliki skasowane.
- route_precompute_orchestrator.py: route_landcover usuniety z JOB_SEQUENCE (+ import). Sekwencja bazowa: route_base, route_surface, route_poi (+ opcjonalnie route_shade, route_elevation za bramkami).
- route_canonical_read.py: route_landcover_layer usuniety z _CANONICAL_LAYER_ORDER (bramka kompletnosci) i z budowanego slownika layers; funkcja _landcover_rows skasowana.
- qbot_route_report_tool.py: route_landcover_layer usuniety z licznika warstw A0.
- Testy zaktualizowane: test_route_report, test_route_precompute_trigger, test_route_precompute_orchestrator, test_route_canonical_read, test_route_poi_store.

**Zmiana kontraktu land_cover_preferred_source:** wczesniej "worldcover_shade" gdy pokrycie shade, inaczej "osm_landcover_legacy". Po usunieciu legacy: "worldcover_shade" gdy pokrycie, inaczej "shade_none". Raport renderuje te wartosc verbatim (landscape_source: ...).

**Granica (wazne):** to NIE dotyczy landcover jako kontekstu WEWNATRZ silnika nawierzchni (route_surface_engine._refine_context uzywa landcover/geologii do wnioskowania surface na odcinkach bez tagu OSM). To osobna logika w pamieci, nietknieta. Usunieta zostala tylko osobna, materializowana warstwa-tabela route_landcover_layer.

---

## 2026-07-01 — DECYZJA: route store — wersjonowanie, retencja (keep=3), purge i narzedzia tras Alberta (list/recompute/delete)

**Status:** wdrozone i zweryfikowane na zywo. Pelna dok.: docs/ROUTE_STORE.md.

**Wersjonowanie:** aktywny plik GPX ma STALA nazwe `rwgps_<id>.gpx`; przy zmianie tresci poprzednia wersja archiwizowana jako `rwgps_<id>_<sha10>.gpx` (`tools/rwgps/client.py`). Nowy `route_version_key` = nowy `route_base` (stare zostaja), aktywna = najnowsza. Odrzucono zmiane nazw po sha (dotknelaby ~9 zywych plikow).

**Retencja:** `qbot3/routes/route_versions.py` (`prune_route_versions keep=3`, dry-run domyslnie, aktywna nigdy nie kasowana) + auto-hook po precompute w `route_precompute_orchestrator.py`. CLI: `scripts/route_versions_cli.py`.

**Purge:** `scripts/route_store_purge.py` `purge_route(route_id, confirm)` — dwustopniowo (podglad / realne kasowanie), kasuje route_base+artifacts (kaskady) + surowka + pliki. Kanal admin: `dev_route_store_purge` w `/root/qbot-dev-mcp/server.py` (poza repo).

**Narzedzia Alberta:** `route_list` (odczyt), `route_recompute` (write, aktywna wersja), `route_delete` (write, DWUSTOPNIOWO: podglad -> confirm=true po zgodzie). Rejestr `tool_registry.py`, prompt `albert.py`.

**Trzy warstwy bezpieczenstwa zapisow otwarte WASKO dla tras** (masowe kasowanie i inne destrukcje dalej blokowane): (1) straznik destrukcji `agent_runtime._is_destructive_query` + wyjatek `_looks_like_route_delete_request`; (2) whitelista realnych zapisow w `agent_runtime` (`_execute_single_tool` + `_execute_real_write_tool`); (3) allowlista walidatora `safety._ACTION_ALLOWLIST` (przez `_LEGACY_EXTRA_ACTIONS`). Zabezpieczenie kasowania trzyma dwustopniowy `route_delete`.

**Uzasadnienie kasowania z czatu:** trase zawsze mozna ponownie pobrac z RWGPS.

## 2026-07-01 — DECYZJA: Telegram — koncowe powiadomienie po potwierdzeniu rowniez dla "juz policzone", z czasem liczenia

**Status:** naprawione i zweryfikowane (28 testow zielonych; live #21 i #22). Pelna dok.: docs/TELEGRAM_ROUTE_CONFIRM.md.

**Przyczyna buga:** worker `route_precompute_trigger.py` wysylal koncowe powiadomienie tylko na sciezce "faktycznie przeliczono". Gdy trasa byla juz policzona, funkcja wychodzila w galezi "already complete -> skipped" PRZED wysylka -> brak powiadomienia (ani sent, ani failed).

**Naprawa:** koncowe powiadomienie wysylane TAKZE na sciezce skipped (sukces, tekst "byla juz kompletna"). Idempotencja po `launch_audit_turn_id`.

**Czas liczenia (wariant B):** z metek jobow (`route_precompute_jobs.layer_status_json`: min `started_at` -> max `finished_at`), formatowany `_format_duration_pl`, wstrzykiwany do tekstu ("Czas liczenia: X"). Odrzucono wariant A (czas od TAK) jako mylacy przy "juz policzone".

**action_id audytu:** gdy wynik nie niesie `pending_action_id` (worker CLI), brany z wiersza launch audit -> wpis finalny wiaze sie z numerem akcji.

**Wdrozenie:** worker to swiezy podproces przy kazdym TAK -> poprawka dziala bez restartu qbot-api.

## 2026-07-01 — DECYZJA: RWGPS nowej trasy najpierw pyta przez Telegram, a analiza startuje dopiero po potwierdzeniu

**Status:** wdrożone w webhooku RWGPS, workerze precompute i Telegram gateway.

**Decyzja:** po wykryciu nowej trasy RWGPS worker w trybie `--await-confirmation` materializuje tylko import i tworzy jawny `telegram_pending_actions` o `action_type=confirm_route_analysis`, a następnie wysyła pytanie do aktywnego `chat_id` przez Telegram. Dopiero odpowiedź `tak` uruchamia pełny canonical precompute tej konkretnej trasy.

**Zasada:** ten sam `route_id` / wersja artefaktu nie może spamować Telegrama wielokrotnie. Idempotencja jest oparta o `confirm_route_analysis` + `route_artifact_sha256` / `route_version_key`, a stan jest widoczny w `telegram_pending_actions`, `telegram_conversations` i `telegram_conversation_turns`.

**Naprawa runtime:** cache WorldCover / shade został przeniesiony na writable default `QBOT_WORLDCOVER_DIR=/opt/qbot/artifacts/worldcover`, bo stary `data/worldcover` był root-owned i wywracał `route_shade` podczas precompute.

**Aktualizacja:** pytanie Telegram teraz niesie jawny numer pending action (`#18 ...`), a odświeżenie `expires_at` dzieje się tuż przed realnym `sendMessage`, żeby użytkownik nie potwierdzał wygasłej akcji i żeby odpowiedzi `18 TAK` / `#18 NIE` były jednoznaczne.

**Doprecyzowanie runtime:** odpowiedzi Telegram i renderer kontekstu nie mogą zakładać, że `date_resolution` albo wynik writera zawsze jest słownikiem; `None` ma być traktowane jako brak danych, a nie wyjątek.

**Doprecyzowanie stanu:** `confirm_route_analysis` może przejść do `executed` dopiero po zapisaniu trwałego launch-audytu w DB. Samo `Popen()` bez audytu oznacza `failed`, a numerowane odpowiedzi Telegram nie mogą spadać do ogólnego `qbot.query` fallbacku.

**Doprecyzowanie logów:** log worker-a dla Telegram confirm nie może wskazywać na `/tmp`; używa katalogu kontrolowanego przez QBot pod `/opt/qbot/artifacts/logs/rwgps_confirmations/`, tworzonego bezpiecznie przy pierwszym użyciu.

**Doprecyzowanie uruchomienia:** worker po zakończeniu precompute czeka krótko na trwały `route_precompute_launch_audit`, bo zapis audytu i start procesu mogą się minąć o ułamek sekundy; finalny Telegram jest wysyłany dopiero po znalezieniu tego śladu.

## 2026-07-01 — DECYZJA: modul naprawy tras (naprawa-trasy.html) zaparkowany na zewnetrznej awarii Valhalli

**Status:** wdrozone i dziala na WEB (qbot-web, /naprawa-trasy.html + 4 nowe
endpointy w qbot_web.py). Zatrzymane na przejsciowej awarii publicznej Valhalli
(nginx 502) - do dokonczenia weryfikacji odcinka przy drodze S8 po powrocie uslugi.

**Decyzja:** pelne podsumowanie architektury, wszystkich decyzji (dopasowanie po
km nie po segment_index, kotwice cofniete w dobra nawierzchnie, progresywne
probkowanie promienia 0.3/1.0/2.0/3.0km, use_roads=0.7, brak limitu dlugosci
per-kandydat, regula "przyzwoity grade" dla tracktype, min. 200m na alert) oraz
otwartych problemow (dwa niezgodne systemy oceny nawierzchni A/B - do rozstrzygniecia
w sesji "generator tras", detekcja slepych zaulkow, cap na cala trase) jest w
docs/PROJEKT_NAPRAWA_TRAS.md - NIE duplikowac tutaj, czytac tamten plik jako
zrodlo prawdy dla tego modulu.

**Zasada:** modul to dzis czysty PODGLAD (Valhalla + trace_attributes), bez
zapisu/zszycia zaakceptowanego objazdu z powrotem do trasy - eksport zlozonej
trasy to niezbudowany, naturalny nastepny krok.

**Kontrakt:** kod w qbot_web.py jest w duzej czesci uncommitted (jak i inne pliki
z rownoleglej sesji Cowork - patrz `git status`) - przed commitem zweryfikowac
liste plikow, nie robic zbiorczego `git commit -a`.

---

## 2026-07-01 — DECYZJA: RWGPS webhook najpierw materializuje artefakt, a Telegram używa publicznego qbot.query wrappera

**Status:** wdrożone w workerze precompute i w Telegram gateway.

**Decyzja:** `scripts/route_precompute_trigger.py` ma najpierw upewnić się, że nowa trasa RWGPS ma zapisany `route_artifact` / `route_parse_result`, a dopiero potem uruchamiać canonical `route_base` i `route_precompute_jobs`. Telegramowy gateway ma natomiast korzystać z aktualnego `qbot.query` wrappera, żeby pełny route_report po imporcie widział ten sam publiczny route_report path co MCP / qbot.query.

**Zasada:** RWGPS import jest read-side materializacją canonical stores, a route_report pozostaje oddzielnym read-only renderem. Brak importu nie może wywrócić raportu, ale nowa trasa ma zostać przygotowana bez ręcznej operacji w legacy dumpach.

## 2026-06-30 — DECYZJA: route_report pokazuje canonical surface summary w A3

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** gdy `read_canonical_route(route_id)` zwraca `canonical_surface_summary`, route_report pokazuje w A3 canonical summary wyliczony z `qbot_v2.route_surface_layer`, zamiast opierać się wyłącznie na `surface_summary_json`.

**Zasada:** canonical summary ma pokazać `segment_count`, `total_distance_m`, `coverage_pct`, `by_surface`, `by_confidence` i `problem_segments_count`. Legacy `surface_summary_json` zostaje fallbackiem, jeśli canonical summary brak.

**Kontrakt:** A3 ma nie zmieniać A0/A0B/A0C ani A8. Brak canonical summary nie może wywrócić raportu.

## 2026-07-01 — DECYZJA: A3 rozdziela coverage surface od tagów OSM

**Status:** wdrożone w readerze canonical i renderze route_report.

**Decyzja:** A3 pokazuje jawnie `coverage_pct`, `tagged_surface_pct`, `inferred_surface_pct` oraz metryki Overpass chunks, aby nie mylić pokrycia warstwy surface z kompletnością tagów `surface=*` w OSM.

**Zasada:** `coverage_pct` oznacza pokrycie klasyfikacją nawierzchni dla trasy, a nie procent odcinków z bezpośrednim tagiem `surface=*`. `tagged_surface_pct` i `inferred_surface_pct` rozdzielają bezpośrednie odczyty z OSM od odcinków kontekstowych / inferowanych. Gdy dostępne są metryki Overpass, są one czytane z `qbot_v2.route_surface_profiles.surface_summary_json`; jeśli nie ma tego kontraktu, reader nie zgaduje.

**Kontrakt:** brak nowych pól nie wywraca raportu. Legacy fallback pozostaje, a A0/A0B/A0C/A8 nie zmieniają się.

## 2026-06-30 — DECYZJA: canonical reader wystawia surface summary z route_surface_layer

**Status:** wdrożone w `qbot3/routes/route_canonical_read.py`.

**Decyzja:** `read_canonical_route()` wystawia teraz `canonical_surface_summary` policzony z `qbot_v2.route_surface_layer`, aby kolejne przepięcie A3 mogło czytać canonical summary bez ruszania DB schema.

**Zasada:** summary jest wyprowadzany z canonical rows, bez zmiany `layers["route_surface_layer"]` i bez zmiany `layer_counts`. Legacy `surface_summary_json` pozostaje osobnym fallbackiem do czasu pełnego przepięcia A3.

**Kontrakt:** summary musi być bezpieczny przy brakujących `distance_m`, nie może rzucać wyjątkiem i ma pokazywać `segment_count`, `total_distance_m`, `coverage_pct`, `by_surface`, `by_source`, `by_confidence` oraz `problem_segments`.

## 2026-06-30 — DECYZJA: route_report pokazuje canonical marker POI w A8

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** jeśli `read_canonical_route(route_id)` zwraca canonical `route_poi_layer`, route_report pokazuje w A8 jawny marker źródła POI z liczbą punktów tej warstwy.

**Zasada:** canonical `route_poi_layer` jest pierwszym sygnałem w A8, a legacy cache / `route_poi_analyze_readonly` pozostają fallbackiem dla szczegółowej logistyki, godzin i listy kandydatów. Brak canonical POI nie wywraca raportu i nie zmienia A0, A0B, A0C ani A3.

**Kontrakt:** raport nie udaje jeszcze pełnej canonical listy logistycznej, jeśli helper zwraca tylko count; marker ma jedynie pokazać, że A8 czyta już canonical store.

## 2026-06-30 — DECYZJA: route_report pokazuje canonical marker nawierzchni w A3

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** jeśli `read_canonical_route(route_id)` zwraca canonical `route_surface_layer`, route_report pokazuje w A3 jawny marker źródła nawierzchni z liczbą segmentów tej warstwy.

**Zasada:** canonical `route_surface_layer` jest pierwszym sygnałem w A3, a legacy `surface_summary_json` pozostaje fallbackiem dla szczegółowej klasyfikacji. Brak canonical surface nie wywraca raportu i nie zmienia A0, A0B ani A0C.

**Kontrakt:** raport nie udaje pełnego canonical surface summary, jeśli helper zwraca tylko count; marker ma jedynie pokazać, że A3 czyta już canonical store.

## 2026-06-30 — DECYZJA: route_report pokazuje canonical profil wysokości i podjazdy

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** gdy `read_canonical_route(route_id)` zwraca niezerowe `route_elevation_samples` lub `route_climb_events`, route_report pokazuje osobną krótką sekcję o profilu wysokości i podjazdach opartą o canonical store.

**Zasada:** sekcja opisuje `profil wysokości` i `podjazdy / ścianki` jako warstwę canonical (`route_elevation_samples` + `route_climb_events`) i nie myli jej z legacy profilem raportowym. Brak canonical elevation nie wywraca raportu i nie zmienia A0/A0B ani A3/A8.

**Kontrakt:** raport pokazuje liczby próbek i climb events, ale nie przebudowuje jeszcze algorytmu oceny przewyższeń ani time estimate.

## 2026-07-01 — DECYZJA: A0C pokazuje canonical elevation summary i ograniczenie detekcji krótkich ramp

**Status:** wdrożone w `qbot3/routes/route_canonical_read.py` i `qbot_route_report_tool.py`.

**Decyzja:** sekcja A0C ma pokazywać canonical `elevation_summary` z `route_elevation_samples` i `route_climb_events`: `sample_count`, `climb_event_count`, `min_elevation_m`, `max_elevation_m`, `elevation_range_m`, `ascent_smoothed_m`, `descent_smoothed_m`, `smoothing_version`, `max_climb_event_gradient_pct`, `top_climb_events` oraz jawny limit detekcji krótkich ramp. Diagnostyka surowych próbek może zostać pokazana osobno, ale nie jako oficjalna ścianka.

**Zasada:** `route_elevation_samples` jest 50 m profilem, `route_elevation_engine.summarize()` daje smoothed ascent/descent, a `route_climb_events` są segmentowane w 100 m i dostarczają głównej metryki stromizny. Raport ma wprost mówić, że bardzo krótkie strome rampy mogą umknąć. Brak danych nie wywraca raportu i nie zmienia A0/A0B/A3/A8.

## 2026-07-01 — DECYZJA: route_report pokazuje końcowy werdykt trasy jako syntetyczny blok

**Status:** wdrożone w `qbot_route_report_tool.py`.

**Decyzja:** pełny `route_report` pokazuje dodatkową sekcję `WERDYKT TRASY / DECYZJA`, która syntetyzuje już dostępne dane z A0/A0B/A0C/A3/A4/A8 oraz B2/B5 w krótką decyzję dla rowerzysty gravelowego.

**Zasada:** werdykt nie liczy nowych danych i nie dubluje całych sekcji. Ma jawnie mówić, kiedy dane są ograniczone, kiedy nawierzchnia jest częściowo inferowana, kiedy METEO jest unavailable, i kiedy POI/godziny są niepełne. Brak dowolnej warstwy nie wywraca raportu, ale może obniżyć decyzję do `BRAK PEŁNYCH DANYCH`.

## 2026-06-30 — DECYZJA: route_report pokazuje sekcję otoczenia z route_shade_layer / WorldCover

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** gdy `read_canonical_route(route_id)` zwraca `land_cover_preferred_source=worldcover_shade` oraz niezerowy `route_shade_layer_count`, route_report pokazuje osobną krótką sekcję „otoczenie trasy" opartą o `route_shade_layer` / WorldCover.

**Zasada:** sekcja otoczenia mówi o przekroju lewo / środek / prawo względem osi trasy i używa nazwy produktu `otoczenie trasy`, a nie samego „landscape" bez wyjaśnienia. Jeśli canonical brak albo preferencja spada do `osm_landcover_legacy`, raport nie udaje WorldCover i zostaje przy legacy fallback bez regresji.

**Marker:** A0 canonical source pozostaje widoczny, ale sekcja otoczenia jest pierwszym merytorycznym przepięciem z canonical store do raportu.

## 2026-06-30 — DECYZJA: route_report pokazuje canonical read-path jako marker, bez przebudowy sekcji A/B

**Status:** wdrożone minimalnie w `qbot_route_report_tool.py`.

**Decyzja:** publiczny route_report najpierw próbuje `read_canonical_route(route_id)` i zapisuje marker źródła danych trasy: `read_path`, `fallback_reason`, `layer_counts`, `route_shade_layer_count`, `shade_coverage_pct` oraz `land_cover_preferred_source`.

**Zasada:** canonical store jest teraz widocznym źródłem diagnostycznym w raporcie, ale sekcje A3/A8/elevation nie zostały jeszcze przepięte na canonical read-path. Legacy fallback pozostaje bez zmian i brak canonical data nie może wywrócić raportu.

**Kontrakt źródła landscape:** gdy helper zwraca `land_cover_preferred_source=worldcover_shade`, raport ma to pokazać jawnie; gdy helper zwraca fallback do OSM, raport ma pokazać ten wybór bez zgadywania.

## 2026-06-30 — DECYZJA: kompletność RWGPS → precompute liczymy po aktywnych jobach orchestratora

**Status:** wdrożone w triggerze precompute.

**Decyzja:** `scripts/route_precompute_trigger.py` nie może już uznawać trasy za kompletną po stałych 4 jobach. Kompletność jest liczona dynamicznie zgodnie z aktywną sekwencją orchestratora (`route_base`, `route_surface`, `route_landcover`, `route_poi` plus opcjonalnie `route_shade` i `route_elevation`).

**Reguła runtime:** `route_shade` jest wymagany, gdy `QBOT_ROUTE_SHADE_ENABLED=1`. `route_elevation` jest wymagany tylko wtedy, gdy `QBOT_ROUTE_ELEVATION_ENABLED=1`. Jeśli flaga jest OFF, dany job nie wchodzi do definicji kompletności.

**Zasada:** precompute completion ma odzwierciedlać faktycznie aktywny canonical store, a nie starszą listę jobów. To domyka RWGPS → precompute → pełny canonical route store bez ruszania raportu, analizy ani promptów LLM.

## 2026-06-30 — DECYZJA: 2C.1 canonical read-helper dla warstw precompute

**Status:** wdrozone jako helper odczytu, bez zmian w raportowaniu.

**Decyzja:** `qbot3/routes/route_canonical_read.py` czyta kanoniczne warstwy trasy z DB i zwraca jawne `read_path="canonical"` albo `read_path="legacy_fallback"` z `fallback_reason`, gdy brakuje danych.

**Zakres odczytu:** helper korzysta z `qbot_v2.route_base`, `qbot_v2.route_axis_segments`, `qbot_v2.route_surface_layer`, `qbot_v2.route_landcover_layer`, `qbot_v2.route_poi_layer`, `qbot_v2.route_elevation_samples` i `qbot_v2.route_climb_events`. Nie renderuje raportu i nie uruchamia analyzers.

**Zasada:** canonical precompute jest primary read-path dla danych trasy, a legacy/cache/analyzers pozostają fallbackiem. `route_analysis_run` nadal jest snapshotem zależnym od `start_time`, nie trwałym magazynem faktów trasy.

**Test:** live smoke dla `55798129` ma potwierdzać obecność `route_base_id=1`, warstw surface/landcover/poi/elevation/climb oraz brak dodatkowych zapisów do `route_precompute_jobs`.

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
