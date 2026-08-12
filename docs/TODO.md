# QBot — TODO

> Otwarte zadania. Najnowsze na gorze. To NIE jest CONTEXT.md (auto-gen) ani DECISIONS.md (decyzje).
> Ostatnie porzadki: 2026-07-16 (usunieto rzeczy zamkniete przy/po cutoverze ModelQ v2 08.07;
> pelna historia zamknietych pozycji w poprzedniej wersji: TODO.md.bak.* oraz DECISIONS.md).

---

# OTWARTE

## [WAGA-SYNC] Wlasny synchronizator Withings -> Garmin (zamiast SmartScaleSync) (dodane 2026-08-06)

CEL: zrezygnowac z platnej subskrypcji SmartScaleSync (18,5 EUR) i postawic synchronizacje
u siebie. Waga MUSI dalej isc przez Garmina -- QBot czyta body composition z Garmin Connect
(import_garmin_body.py -> qbot_v2.body_measurements, source_type=INDEX_SCALE), a konektor
Withings w QBocie jest DEPRECATED (qbot3/connectors/import_withings_body.py) i taki zostaje.

STAN FAKTYCZNY (sprawdzone 2026-08-06): ostatni pomiar 2026-08-06, 101.34 kg, source garmin /
INDEX_SCALE -- czyli droga Withings -> (SmartScaleSync) -> Garmin -> QBot dziala.
Withings NIE MA oficjalnej integracji z Garminem; kazde rozwiazanie to obejscie.

PLAN (decyzja przed kodem, po urlopie):
- withings-sync (pip, open source) albo wlasny odpowiednik na VPS, cron po porannym wazeniu.
- Sekrety Withings juz sa: /opt/q/secrets/withings/withings.env -- sprawdzic, czy refresh
  tokenu jeszcze dziala (to byl powod deprecacji konektora, wiec traktowac jako ryzyko nr 1).
- Garmin: login + haslo + 2FA, sesja do odnawiania. Ryzyko nr 2 -- upload idzie wewnetrznym
  API Garmina (plik FIT), potrafi sie zepsuc przy zmianach po stronie Garmina.
- Przeniesc pelny sklad ciala, nie sama wage (tluszcz, miesnie, kosci, nawodnienie, BMI).

DOWOD SUKCESU: po wazeniu nowy wiersz w qbot_v2.body_measurements z data biezaca --
BEZ aktywnej subskrypcji SmartScaleSync. Odpiac subskrypcje dopiero po 2-3 udanych dobach.

## [ZYWIENIE-ZAPIS] Regula cukrowa zerowala makra po podciagu w nazwie [ZAMKNIETE 2026-08-04]

WYKRYTE przy logowaniu jedzenia za 30.07-03.08. Pierwsza diagnoza (wpisana 2026-08-01)
byla BLEDNA -- twierdzila, ze "Albert gubi makra niedeterministycznie". Nieprawda.

PRAWDZIWA PRZYCZYNA: _validate_and_fix_meal_items (qbot_nutrition_db.py) dopasowywala
slowa cukrowe jako PODCIAG w dowolnym miejscu nazwy produktu:
    _sugar_keywords = ["miod", "miód", "cukier", "dzem", "jam", "konfitura", ...]
    if any(kw in name_l for kw in _sugar_keywords): -> protein_g=0, fat_g=0
Nazwa "Baton Slodzone Miodem" lapala sie na "miod" -> bialko 7->0, tluszcz 14.9->0,
przy nietknietych kcal i weglowodanach. Blad byl DETERMINISTYCZNY i CICHY -- bilans
kaloryczny sie zgadzal, wiec nic nie krzyczalo.

Dopasowanie po podciagu myli sie w obie strony:
  - za duzo: "Racuch z pistacjami" lapie "jam" (intake_items id=354)
  - za malo: "konfitura" nie lapie odmiany "konfitura" z ogonkiem (id=447 ocalal przypadkiem)

NAPRAWA (2026-08-04): zerowanie makr odpala sie tylko gdy produkt faktycznie JEST
glownie cukrem, tzn. same weglowodany pokrywaja >=80% deklarowanych kcal.
Miod (20 g W / 80 kcal = 100%) -> regula dziala. Baton (21.3 g W / 253 kcal = 34%)
-> pominieta, z ostrzezeniem w logu.
Test: 7/7 przypadkow + zapis kontrolny na zywo przez MCP (makra przezyly).

SKALA SZKOD w historii: przeskanowano wszystkie 337 pozycji intake_items.
Slowo cukrowe w nazwie mialy 4: id=41 (miod, zerowanie poprawne), id=324 (cukierek,
55 kcal), id=354 (pistacje, makra ocalaly -- inna sciezka zapisu), id=399 (baton,
juz poprawiony recznie). Realnie uszkodzony byl tylko id=399.

## [ZYWIENIE-BLONNIK] fiber_g nie dociera z LLM do bazy -- SWIADOMIE NIE NAPRAWIANE

args_schema toola nutrition_log_add (qbot3/tool_registry.py ~2087) nie ma pola fiber_g,
a albert.py (552-565) buduje z args_schema parametry funkcji dla LLM -- wiec model
fizycznie nie moze przekazac blonnika. Warstwy nizej (mcp_adapter 525/538,
qbot_nutrition_db 442) obsluguja fiber_g poprawnie.

DECYZJA (2026-08-04, Michal): NIE dodajemy pola. Blonnik nie zasila zadnego modelu
(ani ModelQ, ani glikogenu), a dane bylyby i tak szczatkowe -- podawany jest
sporadycznie, tylko gdy czytamy z etykiety. Srednia z rzadkich wpisow bylaby smieciem.

ZROBIONE ZAMIAST TEGO: fiber_total usuniete z publicznego podsumowania dnia
(_serialize_summary w qbot_nutrition_tools.py oraz _nutrition_summary_subset
w qbot3/adapters/mcp_adapter.py), zeby suma 0 nie czytala sie jak pomiar.
Kolumna w bazie i sumowanie w daily_summary_compute zostaja nietkniete --
jesli kiedys pole wroci, dane historyczne beda spojne.

## [DOK-CZAS-50M] docs/ROUTE_TIME_ESTIMATE_V2.md jest nieaktualny (dodane 2026-07-30)

Dokument mowi, ze resolver czasu czyta route_frames (80 m) i zostawia notke 'do weryfikacji'.
ZYWY KOD juz tego nie robi: qbot_route_time_tools._load_route_segments wola
route_segments_50m.load_canonical_segments_50m (os 50 m + route_elevation_samples +
route_surface_layer, nachylenie oknem 200 m) -- TASK 26. Poprawic dokument, zeby nie mylil
kolejnej sesji (ta pomylka juz raz wyprowadzila na manowce 2026-07-30).

## [PRECOMPUTE-80M] Pudelka 80 m nadal budowane w starej sciezce RWGPS (dodane 2026-07-30)

scripts/route_precompute_trigger._ensure_rwgps_route_frames buduje route_frames (80 m) jako
TWARDY warunek -- brak pudelek = caly trigger ERROR. Tymczasem Analiza Trasy (czas, pogoda,
profil, raport) czyta wylacznie kanon 50 m; route_frames sa legacy dla WYKONANYCH przejazdow
(ride_overlay). Sciezka Komoota (komoot_ingest.ingest_komoot_tour) pudelek NIE buduje.
Do rozwazenia: zdjac twardy warunek albo caly krok ze sciezki RWGPS. Sprawdzic wczesniej,
czy route_weather/route_brief nie sa jeszcze gdzies wolane produkcyjnie.

## [PROFIL-3D] Obracany profil 3D trasy (VeloViewer-style) (dodane 2026-07-18)

Pomysl Michala: obracany mysza model 3D profilu trasy jak w VeloViewer (bryla
wysokosci kolorowana nachyleniem; opcjonalnie mapa pod spodem). USTALONE: VeloViewer
NIE ma silnika do pozyczenia -- to autorski kod Ben Lowe; wersja z mapa pod spodem =
trik CSS3. Standard do tego efektu = biblioteka three.js (WebGL, darmowa, w przegladarce).

Dane JUZ SA: geometria trasy (/api/routes/{id}/geometry), wysokosci + nachylenia co 50 m
(route_profile_detail / route_axis_segments + route_elevation_samples). Brakuje tylko
warstwy rysujacej. Wzorzec UI: strona lab (forma.html / raport), statyki poza repo (zywe od razu).

Poziomy (do decyzji, po jednym, decyzja przed kodem):
1) profil 2D kolorowany nachyleniem -- najprosciej, ~90% czytelnosci VeloViewera;
2) pseudo-3D scianka na mapie (jak zrzuty od Michala) -- ladne, wiecej dlubaniny (SVG/canvas);
3) pelne 3D three.js obracane mysza (marzenie Michala) -- osobny, cizszy kawalek.
Rekomendacja: prototyp poziomu 3 na jednej trasie (sama obracana bryla), potem rozbudowa.

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
- [KCAL-RYCZALT] pole "Ryczalt kcal/dzien" w PLANERZE WYPRAW -- swiadomie odlozone
  (decyzja 2026-08-11: zostawiamy). Dzis event z planera doedytowuje sie w kalendarzu.

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

**CZESCIOWO ZROBIONE 2026-07-26 -- zmierzony ZAKRES (nie wartosc).** Metoda: na kazdej jezdzie,
gdzie model doprowadzil Wbal do <=5%, szukamy najwiekszego CIAGLEGO wysilku powyzej TP wykonanego
juz przy pustym baku; jego praca = energia, ktorej modelowi zabraklo. Wymagane W' = HIE dnia +
niedomiar. Na 11 wyplukaniach z roku (6 z realnym niedomiarem) wyszlo **22-26 kJ, srodek ~24**:
22.0 / 22.3 / 22.8 / 24.3 / 25.4 / 26.1. Zapisane jako `WPRIME_MEASURED_LO/HI_KJ` w
`fitmodel/wprime_anchor.py`, ktory wypelnia teraz `wprime_lo_kj`/`wprime_hi_kj` (573 dni).
Zastapilo zalozeniowe "13-22, confidence low". Kazdy punkt mierzy DOLNY brzeg -- prawda moze
lezec wyzej niz 26, nigdy nizej niz 22. Biezace `wprime_modelq_kj` (~23.2) miesci sie w zakresie,
wiec wartosci NIE zmieniano.

**ZOSTAJE -- wariant b wlasciwy (decyzja przed kodem):** z mocy i czasu trwania wysilku w momencie,
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

- [PODJAZDY-SKALA] etap B: glikogen i punkt bomby w symulatorze trasy (zapas z ModelQ + jedzenie z fuel vs spalanie kJ); etap C: durability — krzywa osiągalna zależna od kj_before (po czystych jazdach z nową baterią); etap D: wiatr czołowy/boczny w fizyce symulatora + wykres W′/glikogenu pod profilem; ocena w trybie DZIEŃ planera; readiness dnia w CP. ZROBIONE: fazy 1-3 + łańcuch + etap A symulatora (50 m, przerwy kanonu, upał) 2026-08-10

# ZROBIONE (skrot; szczegoly w DECISIONS.md i TODO.md.bak.*)
- [2026-08-12] ZROBIONE: TELEGRAM -- reczne, kontekstowe przeliczenie trasy. `przelicz trase <id>` / `policz trase <id>` / `/przelicz <id>` / `uruchom pelna analize trasy <id>` przechwytywane w `qbot_qcal_telegram.handle_message` PRZED routerem (Telegram nie chodzi przez Alberta, wiec `route_recompute` byl stamtad nieosiagalny). Reuzyty writer `confirm_route_analysis` -> audyt + koncowe powiadomienie z czasem liczenia. ID w komendzie = start od razu; ID z kontekstu (`context_json.last_route_id`) = numerowane potwierdzenie `NN TAK`; brak ID = prosba o numer. Testy 17 zielonych, dowod na zywo: pending #29 dla trasy 55918401 (dry-run, sprzatniete). Dok.: docs/TELEGRAM_ROUTE_CONFIRM.md rozdz. 9.
- [2026-08-11] ZROBIONE: [KCAL-RYCZALT] ryczalt kaloryczny przypiety do eventu kalendarza (`calendar_entry.kcal_planned`). Dni urlopu bez logowania dostaja szacunek X kcal + makra metoda presetow (`macros_for_kcal`, mediana realnych dni w pasmie +-250 kcal, fallback split). Nowy `qbot_event_intake.py`, nocny krok `event_intake` w daily_job (7 dni wstecz do wczoraj, idempotentny), pole w formularzu eventu (kalendarz-render.js v=26). Pierwszenstwo: realne jedzenie > reczny preset dnia > ryczalt; realny wpis kasuje ryczalt. Edycja eventu bez pola NIE zeruje ryczaltu (planer wypraw). Dowod na zywo: Sycylia 6-21.08 = 3200 kcal, dni 6-10.08 zapisane 340 g W / 135 g B / 116 g T (8 realnych dni, nie fallback). Szczegoly: DECISIONS 2026-08-11 + docs/PROJEKT_ODZYWIANIE.md.
- [2026-07-30] ZROBIONE: zestaw porownywanych modeli dobierany do horyzontu (0-2 dni: siatki do 7 km; 3-5 dni: 7-13 km + ECMWF; 6+ dni: same globalne) -- zestawianie siatki 2 km z 25 km na krotkim terminie mierzylo rozdzielczosc, nie pogode. Do rejestru doszedl HARMONIE 5.5 km. Grafika porownania (skale z kropkami) USUNIETA -- zastapiona czterema akapitami i ocena Alberta w 2-3 zdaniach prozy.
- [2026-07-30] NAPRAWIONE: pogoda wysypywala sie na dniu 2 bledem Postgresa o NaN. Przyczyna: zasieg modelu sprawdzany w DNIACH, a ICON-D2 mial 4 godziny z 24 (konczyl sie o 05:00) -- jazda od 09:00 trafiala w pustke i WBGT wychodzil NaN. Teraz model_reach zwraca ostatnia GODZINE, canonical_model wymaga pokrycia okna jazdy (start + 14 h), a _bez_nan() sanityzuje NaN/Inf na null z polem 'niepelne_dane'; json.dumps ma allow_nan=False. Payload zawiera tez pole 'model'. Zasada: 'model siega daty' to za gruba miara.
- [2026-07-30] ZROBIONE: panel zgodnosci modeli -- kazdy osrodek ma wlasny staly kolor (wczesniej wszystkie kropki byly identyczne, wiec legenda i uwagi Alberta o konkretnym modelu byly nieweryfikowalne), kanon rozpoznawany po rozmiarze i obwodce; instrukcja 'jak to czytac' nad panelem; rozdzielone pojecia 'rozstep miedzy modelami' (niezgoda miedzy osrodkami) i 'rozrzut zespolu' (niepewnosc 51 wariantow ECMWF) w UI i w prompcie Alberta. UWAGA na przyszlosc: zwroty, ktore LLM ma przepisac doslownie, trzeba podac w prompcie z polskimi znakami -- inaczej kopiuje je bez ogonkow.
- [2026-07-30] ZROBIONE: pogoda v3/v4 -- pas opadu pokazuje SZANSE jako tlo obok mm jako slupkow (alert deszczu powstaje juz przy 30% prawdopodobienstwa i 0 mm, wiec pusty pas przy plakietce DESZCZ wygladal na sprzecznosc); plakietka rozroznia 'deszcz' od 'ryzyko deszczu'; nowa skala barw temperatury dobrana do jazdy z legenda (stara malowala 29 C z alarmem upalu na zielono); 'brak danych' zastapione konkretnym powodem niepowodzenia.
- [2026-07-30] ZROBIONE: pogoda -- dlugie postoje w ETA (regula: 1 postoj 30 min na kazde pelne 75 km ETAPU; wczesniej silnik znal tylko mikroprzerwy i krotkie postoje co 9 km, wiec pogoda popoludniowa byla liczona o ~pol godziny za wczesnie -- szczyt WBGT wskazywal km 93.9 zamiast 86.2). Zachmurzenie dodane do silnika (cloud_cover), tabeli 30 min, podsumowania i serii wykresu. Podstrona v=2: pas chmur, pas opadu zawsze widoczny z podpisem, znaczniki postojow, interaktywny kursor z dymkiem (dziala tez dotykiem). DO OBEJRZENIA OKIEM.
- [2026-07-30] ZROBIONE (BEZ OGLEDZIN WIZUALNYCH): podstrona pogoda-wyprawy.html + pogoda-wyprawy-render.js -- os calej wyprawy, wykres dnia w SVG (temperatura/odczuwalna/WBGT, wstega rozrzutu zespolu, slupki opadu, strefy alertow, wschod/zachod, pasek wiatru wzdluz trasy), panel zgodnosci modeli z ocena Alberta, tabela 30 min, wariant klimatyczny. Przycisk wejscia w Planerze wyprawy (v=79). POST /api/pogoda/mail -- raport pogodowy mailem, niezalezny od PDF wyprawy, liczony tym samym endpointem co ekran. DO DOKONCZENIA: obejrzec strone w przegladarce (kanal chrome padl) i przetestowac realna wysylke maila.
- [2026-07-30] ZROBIONE: Pogoda wielomodelowa. Nowy qbot3/routes/route_weather_models.py: 6 modeli (ICON-D2 2.2 km / ICON-EU 7 / UKMO 10 / GFS 13 / ECMWF IFS 25 / ECMWF AIFS 25), zasieg sprawdzany na zywo (ICON-D2 tylko ~3 dni!), model kanoniczny wybierany REGULA (najdrobniejsza siatka siegajaca daty, ponizej 10 km; dalej ECMWF IFS), porownanie modeli w punktach kontrolnych jednym zapytaniem, rozrzut zespolu ECMWF (51 wariantow). run_meteo_engine przyjmuje model=. /api/planer/pogoda dokleja blok 'modele' z ocena Alberta (LLM interpretuje rozbieznosc, NIE wybiera modelu). Powod zgloszenia: rozjazd z Windy 4.6 C byl efektem cichego best_match, nie bledu. Koszt bloku: 2 zapytania na dzien.
- [2026-07-30] ZROBIONE: Planer wyprawy -- zakladka POGODA w lewym menu. Silnik METEO dostal zakres km (from_km/to_km) z przeliczeniem ETA od poczatku etapu, plus brakujace temp_c/rh_pct w wyniku i blok slonca (wschod/zachod/dlugosc dnia/UV). Nowy modul qbot3/routes/route_climate.py (ERA5, 10 lat, okno +-3 dni) jako UCZCIWY zamiennik prognozy dla dat dalszych niz ~16 dni -- oznaczony jako klimat, bez WBGT i burz. Endpoint GET /api/planer/pogoda (dzien po dniu, cache qbot_v2.planer_pogoda_cache, 3 h prognoza / 30 dni klimat). Front: karty dni z kaflami (temperatura, odczuwalna, wilgotnosc, opad, wiatr wzdluz/w poprzek/porywy, WBGT max, slonce, ETA), alerty upal/deszcz/burza/zimno i tabela co 30 min. Dowod: Oppelner Gravelzug 3 dni, wartosci potwierdzone niezaleznym strzalem do Open-Meteo.
- [2026-07-30] ZROBIONE: Raport z trasy -- SLONCE + WYKONALNOSC. (1) Silnik meteo liczyl 'slonce' (wschod/zachod/dlugosc dnia/UV) juz wczesniej, ale _build_report_data to gubilo -- teraz przepuszczone do DATA.details.weather.slonce. (2) WYKRES: pionowe linie przerywane wschodu (amber #c2871a) i zachodu (#5d6b96) + podpis, rysowane TYLKO gdy godzina wpada w okno start-finisz; km liczony z interpolacji C.eta (godzina -> km), z obsluga przejscia przez polnoc. (3) ZAKLADKA POGODA: linijka wschod/zachod/dlugosc dnia/ile minut jazdy po ciemku (sunHTML + darkMinutes w raport-render.js). (4) ZAKLADKA FORMA: wykonalnosc jazdy -- liczby z silnika fitmodel.expedition_feasibility.assess (model dwoch scian: XSS trasy vs rekord 1-dnia vs sciana metaboliczna, prognoza CTL na dzien jazdy, TSB po jezdzie), a OCENA pisana przez Alberta (nowa funkcja _report_feasibility w qbot_web.py, TRZECIE osobne wywolanie LLM -- doklejenie do istniejacych dwoch urywaloby odpowiedz przez budzet tokenow); fallback na tekstowy verdict silnika gdy LLM padnie. Wykonalnosc liczona wzgledem DATY z formularza raportu. DOWOD na komoot-3130742793 / 2026-08-05: slonce 05:02-20:20 (dzien 15.3 h), XSS trasy 106 vs rekord 342 i sciana 425 -> 'w normie', CTL prognoza 61.9, TSB po jezdzie -4.9, ocena Alberta 3 punkty. NIEZWERYFIKOWANE WIZUALNIE: kanal claude-in-chrome wisial 4 min -- linie na wykresie sprawdzone tylko arytmetycznie (zachod 20:20 w oknie 18:30-20:30 -> ~km 30), do obejrzenia okiem.
- [2026-07-30] ZROBIONE: Planer Wypraw -> Analiza Trasy, pelne dziedziczenie warstw kanonu 50 m. BYLO: 'parent surface coverage is insufficient for day 1: 669/2390' -- eksport dni padal, bo _inherit_parent_baseline laczylo nawierzchnie po segment_index z osia 50 m, a route_surface_layer ma odcinki ZMIENNEJ dlugosci z kilometrazem w surface_meta_json (rodzic: 6559 osi vs 669 nawierzchni; dopasowywalo sie tylko pierwsze ~33 km). Dziedziczono tez tylko 2 z 10 warstw. JEST: ciecie po kilometrach + komplet warstw -- route_surface_layer, route_elevation_samples, route_shade_layer, route_poi_layer, route_poi_meta, route_climb_events, route_surface_context, route_surface_profiles+route_surface_segments (nowe funkcje _inherit_*). Podjazd nalezy w CALOSCI do dnia, w ktorym sie ZACZYNA (flaga extends_past_day_end w meta). Joby zapisane jako complete/planer_inherit -> dzien od razu w /api/routes/ready, BEZ Telegrama (nie ma czego liczyc). Trasa z Komoota bez zmian: nadal Telegram + pelny precompute. Bezpiecznik w route_precompute_orchestrator (_inherited_stage_lineage/_layer_already_inherited): trasa z rodowodem i niepusta warstwa pomija job -- chroni przed platnym ponownym pobraniem POI. Atrakcje NIE sa kopiowane: route_attraction_store czyta publikacje rodzica przez route_stage_lineage. DOWOD na Oppelner Gravelzug (cuts 119.5/234.55): POI 575=575 (rodzic bez atrakcji), zacienienie 6559=6559, podjazdy 26=26, atrakcje 40=40 kandydatow (12+17+11) i 9=9 rekomendacji; nawierzchnia 670 vs 669, wysokosci 6562 vs 6560, kontekst 278 vs 277 (+1/+2 = odcinki przeciete granica dnia, poprawne). Dzien 1: 2390/2390 segmentow 50 m z nawierzchnia i nachyleniem, czas 6.32 h ruchu / 7.74 h calkowity. Zero zapytan zewnetrznych. Testy: tests/test_planer_stage_export.py 29 passed (+3 nowe testy regresji: komplet warstw, ciecie po km nie po segment_index, podjazd wg dnia startu).
- [2026-07-27] ZROBIONE: DZIS -> kafel 'Najblizszy cel' (pelna szerokosc, miedzy hero a kaflami). Endpoint GET /api/forma/event-prep (_event_prep_payload): 'event'=najblizszy wpis, 'target'=najblizszy event Z PLANOWANYM OBCIAZENIEM (delegacja/urlop = ograniczenie 'limits', NIE cel - inaczej kafel proponowal tapering do delegacji). Ocena silnikiem expedition_feasibility.assess (werdykt, sciany dnia/tygodnia, symulacja TSB) + deterministyczny taper _event_prep_taper. Tryb LLM mode='event' w /api/forma/analyze ('Do startu:' / 'Na imprezie:'), przycisk w kaflu -> prawy drawer. Front: #dzis-event + CSS .evp w forma.html; renderEventPrep/loadEventPrep + chip 'Najblizszy cel' w Dostosuj (klucz event_prep, domyslnie ON) w forma-render.js.
- [2026-07-27] ZROBIONE: Planowane obciazenie (XSS/dzien) z Planera Wypraw. Nowa tabela qbot_v2.planned_load_daily (day+source PK; osobno od fitmodel_daily). XSS/dzien liczony z podzialu Planera (dni_json) + fizyka trasy (_planer_stage_xss). Zapis auto przy /api/calendar/route (best-effort) + endpoint POST /api/planer/planned-load/recompute. Konsumenci: Doradca formy (_forma_planned_events dokleja XSS/dzien) + /api/calendar (days[d].planned_xss + lista planned) + badge w kalendarz-render.js (komorka + chip szuflady). Backfill wyprawy 1-3.08 (entry 13): 372/305/231 XSS.

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

- [2026-07-20] ZROBIONE: Scheduled -- scripts/verify_dupes.py (poranna weryfikacja duplikatow jazd, tylko zglasza; cron root 05:30; Telegram tylko o nowych grupach; stan data/verify_dupes_seen.json). Wykryto 9 starych par do ewentualnego recznego wyczyszczenia.


---

## [MIERNIK-MODELQ] Plan po sesji 2026-08-11 (Sycylia)

Kontekst i dowody: DECISIONS.md, wpis "2026-08-11 -- Miernik Quarq DUB-PWR".
Kolejnosc jest celowa: 1-2 to ryzyka wprowadzone dzisiaj, reszta wg wartosci.

### 1. [PILNE] Zabezpieczyc kotwice EF przed samonapedzaniem

RYZYKO: ef_anchor_step() wstawia kotwice KAZDEGO dnia, gdy TP_ef > TP_model+2 W.
Kotwica podnosi TP modelu -> nastepnego dnia TP_ef nadal moze byc wyzsze ->
kolejna kotwica. Mechanizm jednostronny (w dol tylko decay), wiec teoretycznie
moze wspinac sie w nieskonczonosc, jesli EF utrzyma sie wysoko.
Dzis: TP_ef 273.9, kotwica 262.9. Jutro model ~263 -> kotwica ~268 -> itd.
To moze byc POPRAWNE (nadrabianie zaleglosci po 3 tygodniach slepoty), ale
musi miec hamulec.

DO ZROBIENIA:
- twardy sufit dziennego przyrostu kotwicy (propozycja: max +3 W/dzien),
- sufit bezwzgledny sanity (propozycja: TP <= 1.35 * mediana TP z 90 dni),
- minimalna liczba segmentow w oknie EF (propozycja: >= 8) -- inaczej kotwica
  stoi na dwoch przypadkowych jazdach,
- czyscic stare auto-kotwice: zostawiac najwyzej jedna "kotwice EF" na 7 dni,
  zeby modelq2_anchor nie spuchl do setek wierszy (nearest-anchor zaczalby
  wybierac zawsze dzisiejsza i seria historyczna stracilaby sens).
- WERYFIKACJA: przebieg 7 kolejnych dni w symulacji, sprawdzic czy TP sie
  stabilizuje, czy rosnie liniowo.

### 2. [PILNE] Spojnosc XSS po rewizji TP w gore

PROBLEM: build_and_store przeliczyl TP dla 588 dni (20.07: 245 -> 256 W).
Ale XSS jazd w modelq2_ride policzono STARA, nizsza sygnatura -- zgodnie
z zasada kauzalnosci (sygnatura sprzed jazdy). Teraz wiemy, ze ta sygnatura
byla zanizona, wiec XSS tych jazd jest ZAWYZONY (nizszy prog = wiekszy stres).
Skutek: CTL/ATL z okresu 17.07-11.08 stoja na zawyzonym obciazeniu.

DECYZJA DO PODJECIA (nie przesadzac samemu):
  (a) zostawic -- kauzalnosc swieta, historia sie nie zmienia;
  (b) przeliczyc XSS dla 17.07-11.08 nowa sygnatura -- spojnosc wazniejsza
      niz kauzalnosc, bo to korekta bledu, nie zmiana wiedzy;
  (c) przeliczyc tylko od dnia wstawienia kotwicy EF.
Przed decyzja: policzyc RONICE (o ile spadnie CTL przy wariancie b).

### 3. Straznik v2 -- bilans energii calej jazdy

Zastapic/uzupelnic obecny straznik oparty na P@HR (stoi na optycznym HR
z zegarka Garmin, wahania +-10 uderzen dzien do dnia -- niepewna podstawa).

SPECYFIKACJA:
- praca zmierzona = suma power_w po sekundach;
- praca fizyczna = suma max(0, m*g*dh + Crr*m*g*v + 0.5*rho*CdA*v^3);
  clamp do zera obowiazkowy (na zjazdach placi grawitacja);
- wysokosc z barometru, wygladzona srednia ruchoma 15 s;
- masa: weight_kg z fitmodel_daily + 10.5 kg rower + flaga bagazu;
- WYNIK JAKO PRZEDZIAL, nie punkt: policzyc dla Crr 0.008 / 0.012 / 0.020 /
  0.030 i podac zakres. Werdykt tylko gdy CALY przedzial lezy po jednej
  stronie. To bezposrednia lekcja z 11.08 -- punktowy wynik przy zgadnietym
  Crr dal falszywe oskarzenie +50%.
- druga warstwa: podpis bledu (nadmiar w Nm w koszykach mocy) -> rozstrzyga
  offset vs wzmocnienie, czyli czy dane sa odzyskiwalne.
- FLAGA BAGAZU (automat): start != meta ORAZ start ~= meta jazdy poprzedniej
  -> tour A->B, masa nieznana -> nie wydawac werdyktu, tylko oznaczyc.
  Petla (start == meta, < 2 km) -> masa znana -> werdykt dozwolony.
- zapis do tabeli, nie do logow (lekcja: szukalem alertu w journalctl,
  a on lezal w power_meter_guard).

### 4. Rewizja 5 jazd w kwarantannie 22.07-02.08

Kwarantannowane na podstawie P@HR, czyli tej samej niepewnej metody.
Trzy z nich to prawdopodobnie toury z bagazem (sprawdzic topologia GPS).
Przepuscic przez straznika v2, zwolnic wszystkie bez jednoznacznego dowodu
zawyzania, przeliczyc. Zasada przyjeta 11.08: brak danych szkodzi bardziej
niz dane z bledem.

### 5. Test statyczny korby (po powrocie z wakacji)

Jedyny test rozdzielajacy offset od wzmocnienia bez jazdy.
- rower stabilnie, LEWE ramie korby POZIOMO (godzina 3), nic nie dotyka roweru;
- Set Zero, zapisac zero offset;
- obciazyc pedal znanym ciezarem (woda w butelkach: 1.5 l = 1.5 kg),
  DWA punkty: ~5 kg i ~10 kg;
- odczytac Torque w sekcji Crank Input w AXS (nie moc -- moment);
- oczekiwane T = m * 9.81 * L, gdzie L = dlugosc korby (POTWIERDZIC: 170
  czy 172.5 mm -- nie mam tego w danych);
- dopasowac prosta przez dwa punkty:
    przesuniecie (wyraz wolny) != 0  -> blad ZERA (nie trzyma pod obciazeniem),
    nachylenie != 1                  -> blad WZMOCNIENIA.
- wynik przesadza o reklamacji. Gwarancja SRAM 2 lata, zakup 19.05.2026,
  wysylka poza sezonem (listopad).

### 6. Bateria i procedura obslugi (biezace)

- AAA LITOWA (nie alkaliczna, nie cynkowo-weglowa). Alkaliczny Duracell
  tylko awaryjnie, na wakacje; wyjac po powrocie (ryzyko wycieku w osi).
- reset: przekrecic pierscien SLED o 90 stopni, wyjac sanki, odczekac kilka
  minut, wlozyc swieza, Set Zero.
- kalibracja przed KAZDA jazda (DUB-PWR nie ma Magic Zero) -- i zapisywac
  wartosc, docelowo automatycznie.
- POMYSL: pole na zero offset w /ride-readiness z QExt2, zeby straznik mial
  zero przed i po jezdzie bez recznego przepisywania z AXS.

### 7. Slaby punkt swiezo wdrozonej kotwicy EF (do przemyslenia)

EF liczy sie z ef_norm w fitmodel_segment, czyli z TETNA. To jest ten sam
optyczny HR z zegarka, do ktorego Michal ma uzasadnione zastrzezenia.
Czyli naprawilismy TP kotwica, ktora dziedziczy szum HR.
Kierunek: rozwazyc kotwice TP niezalezna od tetna -- np. z krzywej mocy
(MMP 300-1200 s z zaufanych jazd) albo z progu wyznaczonego bilansem energii.
Nie robic pochopnie -- najpierw obserwowac 2-3 tygodnie, czy kotwica EF
zachowuje sie sensownie po zalozeniu hamulcow z punktu 1.


### 8. [MIERNIK-MODELQ cd.] Tolerancja na zmeczenie -- do sprawdzenia we wrzesniu

- RHR po powrocie do Polski: czy zejdzie do 46 (baza roczna) czy zostanie 48.
  To rozstrzyga, czy sygnal "+48% reakcji RHR na jednostke XSS" jest prawdziwy,
  czy to byl upal sycylijski.
- Powtorzyc analize D+1 na 100 XSS na wrzesniowych danych (n bedzie wieksze).
- Jesli sygnal sie potwierdzi: konsekwencja NIE jest obnizanie intensywnosci
  (moc rosnie, wzorzec dziala), tylko pilnowanie dni wolnych -- Michal juz
  jest na 54% i to prawdopodobnie wlasnie dlatego moc rosnie.
- Rozwazyc dodanie RHR-per-XSS jako stalego wskaznika w raporcie Forma
  (obok CTL/ATL/TSB) -- to jedyny marker, ktory zlapal zmiane.
- L3 (feel/illness) ma 3 wpisy w calej historii. Albo zaczac logowac feel
  po jezdzie (1 klikniecie w QExt2/web), albo uznac L3 za martwe i oprzec
  sie wylacznie na L2-OBJ. Decyzja Michala.
