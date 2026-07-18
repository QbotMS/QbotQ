# QBot — TODO

> Otwarte zadania. Najnowsze na gorze. To NIE jest CONTEXT.md (auto-gen) ani DECISIONS.md (decyzje).
> Ostatnie porzadki: 2026-07-16 (usunieto rzeczy zamkniete przy/po cutoverze ModelQ v2 08.07;
> pelna historia zamknietych pozycji w poprzedniej wersji: TODO.md.bak.* oraz DECISIONS.md).

---

# OTWARTE

## [KALENDARZ-WEB] Webowy kalendarz -- kontynuacja (dodane 2026-07-16)

BAZA GOTOWA (DECISIONS.md 2026-07-16 + CURRENT.md): siatka miesiaca z odczytem konca dnia
(CP/CTL/ATL/TSB) + jazdy + wysuwany przeglad dnia + dodawanie/usuwanie wpisow (event/feel/illness)
w qbot_v2.calendar_entry. Endpointy /api/calendar* w qbot_web.py (NIEZACOMMITOWANE).

DO ZROBIENIA (decyzja przed kodem, po jednym):
- Podlinkowanie kart jazd w panelu -> "Raport z jazdy" (sprawdzic deep-link po external_id).
- Nawigacja miedzy dniami wewnatrz panelu (bez zamykania).
- Edycja istniejacych wpisow (dzis tylko dodawanie/usuwanie).
- (po modelu kondycji) pokazanie wplywu samopoczucia/choroby w kalendarzu.
- Commit qbot_web.py jawnymi sciezkami (robi Michal).

## [KONDYCJA-DNIA] Model subiektywnej kondycji dnia -- L1/L2/L3 (dodane 2026-07-16)

Decyzja zatwierdzona (DECISIONS.md 2026-07-16). Robic PO kalendarzu (wejscie = wpisy feel/illness
z qbot_v2.calendar_entry). L1: subiektyw do LLM Analiza/Doradca (forma_analyze). L2: NOWA kolumna
readiness_effective (osobna, waga ~0.3, NIE rusza readiness_score ani bazy 60d). L3: ukryte
zmeczenie -> ATL (audytowalne, odwracalne). NIGDY nie rusza CP/FTP/W'. Wpiecie nocne:
fitmodel/daily_job.py. Decyzja przed kodem KAZDEGO etapu.

## [ZAORAJ-STARY-KALENDARZ] Usunac stary podsystem kalendarza (dodane 2026-07-16)

Decyzja: usunac (DECISIONS.md 2026-07-16). OSOBNA, ostrozna sesja: weryfikacja -> plan -> akceptacja
-> backup (kod -> _bak_archive, DB -> zrzut) -> usuniecie. Cel: qbot_calendar_core.py +
qbot_calendar_cli + qbot_qcal_cli (+ czesc kalendarzowa qcal_telegram) + tabele
public.calendar_events/calendar_days/reminders/calendar_daily_snapshots/qcal_write_audit
(+ sprawdzic sierote qbot_v2.calendar_events). ZOSTAWIC nowy webowy (qbot_v2.calendar_entry).
PULAPKI: qcal_telegram = transport POTWIERDZEN TRAS (nie ubijac); build_snapshot = agregator dnia
wolany przez MCP/Albert/daily_report/nutrition_cli; tool_registry -> _SYSTEM Alberta w tym samym commicie.

## [W-PRIME-KOTWICA-B] Kalibracja WARTOSCI W' z kotwicy z drogi (dodane 2026-07-16)

Wariant **a** (podniesienie PEWNOSCI z Wbal=0%) -- **ZROBIONE 2026-07-16**: modul
`fitmodel/wprime_anchor.py`, krok `wprime_anchor` w `daily_job` (po modelq2_v2). Czysta kotwica
(Wbal=0 >= 10 s, z `fitmodel_qext2_ride`) w oknie 42 dni -> `wprime_confidence='high'`; dzien z W'
bez kotwicy -> `'medium'`; bez W' -> bez zmian. NIE zmienia wartosci `wprime_modelq_kj`.

**DO ZROBIENIA -- wariant b (decyzja przed kodem):** z mocy i czasu trwania wysilku w momencie,
gdy W'bal zszedl do 0, wstecznie policzyc ILE W' naprawde musialo byc, i USTAWIC te wartosc
(dzis kotwica rusza tylko pewnosc, nie liczbe). Bezpieczniki konieczne: min. dlugosc/twardosc
wysilku, usrednianie z kilku kotwic (pojedyncze zdarzenie jest zaszumione) -- dlatego b dopiero,
gdy uzbiera sie kilka czystych kotwic. Dane wejsciowe: `fitmodel_qext2_ride.wbal_zero_first_offset_s`
-> moc z `activity_record` wokol tego offsetu.

## [WIADRA] Low/High/Peak strain na Karoo (dodane 2026-07-07)

Silnik serwerowy jest (`fitmodel/buckets.py`, wzor `i=moc/FTP`, `strain=i^4*(100/3600)`, progi
0.90/1.20, lekki przelew). UI Karoo ZATWIERDZONE (mockup `mockup_wiadra_stats.html`: 3 pionowe
slupki #4ADE80/#FACC15/#FF5252 w miejsce `tv_wprime`). **Blokada = definicja pojemnosci (100%)
slupka.** USTALENIE 2026-07-07 (niedokonczone): pojemnosc z MINIMALNEGO UZYTECZNEGO BUDZETU
TRENINGOWEGO dla konkretnej WGRANEJ trasy (wariant b zawezony). Reguła: brak wgranej trasy -> brak
budzetu -> brak pojemnosci; jest trasa -> jest pojemnosc. (Warianty a=% udzialu i c=budzet CTL
odrzucone -- patrz historia w TODO.md.bak.*)

NIEROZSTRZYGNIETE (do dogadania, potem kod):
- Wzor "minimalnego uzytecznego budzetu" z profilu trasy (dystans/przewyzszenie/czas) -- model
  jeszcze nie istnieje.
- Co pokazac, gdy brak wgranej trasy (ukryte pole / fallback (a) / placeholder)?
- Podzial budzetu na 3 osobne cele Low/High/Peak (nie tylko suma).
UWAGA: wyswietlacz jest na Karoo = **QExt2 (osobny projekt)**; serwerowa czesc (pojemnosc z trasy)
mozna zrobic w QBot, ale wyswietlanie to osobna sesja QExt2 (StrainBucketEngine + field_stats_3x3
+ SUROWA moc 1s, nie SMOOTHED_3S).

### Ustalenia 2026-07-16 (research, BEZ decyzji -- Michal nie decyduje dzis; pole Karoo tez jeszcze nie zaprojektowane)

PODSTAWA POJEMNOSCI (znaleziona): `_estimate_route_xss` w `qbot3/routes/route_report_canonical.py`
(:405) juz liczy zgrubne obciazenie PLANOWANEJ trasy -- tnie ja na segmenty (podjazdy z
`_climb_power`, reszta = IF_est*CP) i puszcza TEN SAM wzor W'bal/XSS co jazdy wykonane
(per-segment, tier B = estymata, nie pomiar). Plan: te sama per-segmentowa serie mocy przepuscic
przez `fitmodel/buckets.py` (progi 0.90/1.20 FTP) -> przewidywane Low/High/Peak trasy = trzy
POJEMNOSCI wiader. Reuse istniejacego kodu, drobny refactor (oddac serie mocy, nie tylko sume XSS).

KLUCZOWY HACZYK (przesadza architekture): **serwer NIE wie, ktora trase masz wgrana na Karoo.**
`komoot_watch.py` analizuje trasy (zapisuje `route_id` w `komoot_seen_tours`) ale SAM NIE pushuje --
trasa trafia na urzadzenie natywnym syncem Komoot->Karoo. "Ktora trasa zaladowana" wie tylko
QExt2 (Karoo SDK). WNIOSEK: #4 NIE jest czysto serwerowe -- wymaga kontraktu z QExt2: urzadzenie
musi podac `route_id` zaladowanej trasy do `/ride-readiness` (i schowac slupki, gdy go brak).

TIMING estymacji -- 2 opcje (NIEZDECYDOWANE):
  (1) przy analizie trasy (precompute): policz raz, zapisz per route_id. Prosto, ale uzywa FTP
      z dnia analizy (starzeje sie).
  (2) przy starcie jazdy w `/ride-readiness`: QExt2 podaje route_id, serwer bierze SWIEZE FTP/CP
      z ModelQ + zapisany profil trasy, liczy {cap_low,cap_high,cap_peak} na zywo. REKOMENDACJA
      -- bo klasyfikacja segmentu na L/H/P zalezy od progu FTP (i=moc/FTP), a `_estimate_route_xss`
      jest tani.

BRAK WGRANEJ TRASY (NIEZDECYDOWANE): rekomendacja = **chowac 3 slupki** (komorka wraca do W'bal /
`tv_wprime`), spojne z regula "brak trasy = brak pojemnosci". Alternatywy: fallback do trybu (a)
wzglednego / placeholder "brak trasy". UWAGA praktyczna: jesli duzo jazd jest BEZ wgranej trasy,
wiadra beda pokazywac sie rzadko -- do swiadomego zaakceptowania albo przemyslenia fallbacku.

POJEMNOSC = pelne przewidywane L/H/P trasy, czy UŁAMEK ("minimalny uzyteczny budzet", np. 70%)?
NIEZDECYDOWANE.

PODZIAL PRACY (gdy juz beda decyzje):
- QBot-core: funkcja `capacity(route_id, ModelQ) -> {cap_low,cap_high,cap_peak}` (reuse
  `_estimate_route_xss` + `buckets.py`) + wystawienie w `/ride-readiness`, gdy przyjdzie route_id.
- QExt2 (osobny projekt, osobna sesja): odczyt zaladowanej trasy z SDK, przekazanie route_id do
  `/ride-readiness`, akumulacja realnego L/H/P (SUROWA moc 1s), rysowanie slupkow.
  **UWAGA: pole/UI wiader na Karoo JESZCZE NIE ZAPROJEKTOWANE** -- to blokuje czesc QExt2
  niezaleznie od decyzji serwerowych.

3 DECYZJE DO PODJECIA (nie 2026-07-16): brak-trasy (chowac vs fallback) | timing (readiness vs
precompute) | pojemnosc (pelne L/H/P vs ulamek).

## [FORMA-WEB] Redesign strony Forma (dodane 2026-07-16)

Cel: wejscie -> szybka orientacja o stanie AKTUALNYM i ZMIANIE w okresie, dla formy ORAZ wellness.
Kierunek uzgodniony (mockup v2 zaakceptowany): hero-werdykt (kolor wg TSB), kafelki "stan + zmiana"
z przelacznikiem 1D/7D/30D/90D (Δ + sparkline, kolor wg kierunku dobrego per metryka), JEDEN wykres
z wlaczaniem serii (checkboxy). Dane juz sa w `/api/forma/data` (`series` -> Δ i sparkline licza sie
na froncie; backend prawie nietkniety). Do zrobienia: przepisac `forma.html` + `forma-render.js`
(bump `?v=`). Kafelek FTP/CP = jeden (CP=FTP w MQ2 z zalozenia). Rozstrzygniete: przelacznik Δ
wspolny czy per-kafelek; sparkline zostaje czy nie.

**Zrobione tej sesji (2026-07-16, czesciowo):** kafel+naglowek -> "Forma & Wellness"; wykres z interaktywnoscia (hover+tooltip, drag-zoom po X, klik=reset); LLM "Analiza" (interpretacja, nie opis) i "Doradca" (co robic) -- forma_analyze w qbot_web.py, tryby today/chart/coach; fix przestarzalego glikogenu. Do sprawdzenia: czy pelny redesign hero+kafelki-delta jest juz kompletny.

## [SPRZATANIE-MCP] Usunac martwy `qbot_mcp_adapter.py` (legacy) (dodane 2026-07-04)

Legacy `handle_mcp_request` (stary `meal_logs`) odpala sie tylko przy `QBOT3_ENABLED=0` -- dzis
martwy kod, ale `qbot_api.py` importuje go na starcie (galezie `else` w POST/GET `/mcp`,
`/mcp/health`, `/mcp/tools`). Kolejnosc (decyzja przed kodem): 1) usunac uzycia+importy w
`qbot_api.py` (albo twardy 4xx "legacy off"); 2) skasowac plik; 3) sprawdzic `meal_log_create`
gdzie indziej; 4) zaktualizowac CONTEXT.md + DECISIONS.md. Nie naprawia zawodnosci zapisu z ChatGPT
(to blokady konektora OpenAI) -- usuwa mylaca martwa sciezke.

## [POI] Bramka walidacji tresci warstw + auto-wznawianie (odlozone 2026-07-03)

Telegram melduje "zapisane w DB" nawet gdy dane uciete/smieciowe (writer nie rzucil wyjatku !=
tresc OK). Do zbudowania: 1) bramka walidacji z odczytem zwrotnym z DB per warstwa (POI: zaopatrzenie
>=~90% dystansu, >=1 pkt/tercja; nawierzchnia ~100% wezlow, frames>0); 2) auto-wznawianie tylko dla
brakow transientnych (missing_chunks) -- gdy COMPLETE-ale-zly-content: eskalacja do czlowieka, NIE
retry; 3) uczciwy komunikat Telegram (realne liczby, nie "zapisane w DB"). Pliki:
`route_precompute_orchestrator.py`, `route_analyzer.py`, `scripts/route_precompute_trigger.py`.

## [ZYWIENIE] Drobiazgi po naprawie zapisu (dodane 2026-07-05)

1. Usunac walidacje sugar-type w `_validate_and_fix_meal_items` (`qbot_nutrition_db.py`) -- zeruje
   makra/kcal.
2. Sierota w starym `meal_logs` (id=16) -- do skasowania.
3. `_action_exec_nutrition_delete/correct` (`qbot_mcp_adapter.py`) robi UPDATE bez filtra `source`
   (tor martwy, ale moze nadpisac cudze wiersze) -- posprzatac razem z [SPRZATANIE-MCP].

## [RSRV] Ocena wzoru po realnych danych (dodane 2026-07-06)

Wejscie naprawione (todayFactor = readiness_score; RSRV na XSS). DO ZROBIENIA (po kilku jazdach z
realnym todayFactor): ocenic czy sam WZOR RSRV w QExt2 (tempo XSS-penalty, odbudowa 30 min, kara za
decoupling, budzet `CTL*5.4`) "czuje sie" jak Stamina, czy wymaga przestrojenia. Wymaga obserwacji
na zywych jazdach (nie zgadywania) + ew. push QExt2. Osobny projekt (QExt2).

## [DOK] MODELQ.md / dokumentacja (drobne)

- MODELQ.md nie opisuje `readiness_score/readiness_label/readiness_note` (kolumny sa w live DB i
  uzywane) -- dopisac.
- (opcjonalnie) usunac martwe kolumny `cp_v3_w`/`wprime_v3_kj` z samej tabeli `fitmodel_daily`
  (z payloadu Formy juz usuniete 2026-07-16). Usuniecie kolumn = decyzja przed kodem (destrukcja).

---

# ZROBIONE (skrot; szczegoly w DECISIONS.md i TODO.md.bak.*)

- **2026-07-16 (kalendarz WEB):** nowy modul kalendarza (qbot_v2.calendar_entry) -- siatka
  miesiaca z odczytem konca dnia (CP/CTL/ATL/TSB) + jazdy + wysuwany przeglad dnia +
  dodawanie/usuwanie wpisow (event/feel/illness); endpointy /api/calendar* (qbot_web.py).
  Forma: rename "Forma & Wellness" + interaktywny wykres + LLM Analiza/Doradca (forma_analyze).
- **2026-07-16:** #3a kotwica W' (pewnosc z Wbal=0%); sprzatanie `cp_v3_w`/`wprime_v3_kj` z
  `_FORMA_FIELDS`; auto-przeliczenie ModelQ po ingescie jazdy (`qbot_activity_ingest`); Albert +
  deterministyczny routing pytan o CP/FTP/W'/forme -> ModelQ (`fitness_status`), Xert = benchmark.
- **2026-07-14..16:** raport jazdy (W'bal z QExt2/ModelQ + realny pomiar z FIT, wind bar,
  decoupling, chipy readiness/TSB/CP_eff); FORMA wellness (writer sleep/hrv/rhr/weight w MQ2,
  reprocess 8 dni); glikogen NULL vs 0.
- **2026-07-08 (CUTOVER):** ModelQ v2 jedynym modelem (v1 -> archive/modelq_v1). Krok 1 (CP z
  krotkich okien, oddzielony od LTP), Krok 2 (W' harvest ~20 kJ), Krok 3 (W'bal = algorytm QExt2).
- **Karoo/raport na ModelQ:** `/ride-readiness` FTP+LTP+W' z ModelQ (Xert tylko fallback);
  wykres W'bal w raporcie jazdy na modelq2 + realny QExt2.
- **Komoot->Karoo** (wariant A + bramka Telegram, polling). **Ingest activity_record 1Hz** (cron 15 min).
- **XSS** policzony w QBot i on-device (QExt2); **RSRV** na XSS + todayFactor z readiness_score.
- **FORMA tile** + CTL/ATL/TSB (`_build_training_load_latest`). **Strefy HR** Coggan %LTHR=132 na Karoo.
- **QExt2 Strona A<->B**: 7 developer fields @1Hz do/z FIT (deploy key, CI, sideload).
