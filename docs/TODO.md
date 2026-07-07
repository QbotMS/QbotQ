# QBot — TODO


## [WIADRA] Low/High/Peak strain na Karoo (dodane 2026-07-07)

Kontekst: silnik juz istnieje po stronie serwera -- `fitmodel/buckets.py` (`compute_buckets`),
uzywany dzis tylko offline po jezdzie (`fitmodel/ride_buckets.py` -> tabela
`fitmodel_ride_buckets`). Wzor: `i = moc/FTP`, `strain = i^4 * (100/3600)` (1h@FTP=100),
progi `i<0.90` Low / `0.90-1.20` High / `i>=1.20` Peak, + lekki przelew w dol (10%/10%/5%).

Cel: to samo na zywo na Karoo (QExt2), w polu STATS. UI ZATWIERDZONE (mockup
mockup_wiadra_stats.html): dolny wiersz field_stats_3x3 -- BAT/h i BLEFT BEZ ZMIAN (to bateria
samego Karoo, nie AXS); trzecia komorka (dzis tv_wprime, etykieta "D BAT", pokazuje W' balance)
-> zamieniona na 3 pionowe kolumny-slupki, kolory z istniejacej palety (#4ADE80 Low / #FACC15
High / #FF5252 Peak).

OTWARTA DECYZJA (NIE rozstrzygnieta, zanim ruszymy z kodem) -- historia rozwazan 2026-07-07:

Pytanie: co oznacza "wypelnienie" slupka, tzn. skad bierze sie pojemnosc (100%) wiaderek?

  (a) PROSTY -- % udzialu danego wiadra w SUMIE strainu narastajacego w trakcie jazdy
      (Low+High+Peak = 100% caly czas, wzgledem samych siebie). Gotowe do wdrozenia od razu,
      zero modelowania. WADA (uwaga Michala): nie pokazuje nic o tym, czy jazda jest "duza" czy
      "mala" wzgledem realnej potrzeby -- tylko wewnetrzna proporcje.

  (b) ROUTE TARGET (pierwotny pomysl) -- % wykonania przewidzianego celu dla KONKRETNEJ
      zaplanowanej trasy z profilu wysokosci/dystansu. SPRAWDZONE: taki model nie istnieje w
      kodzie dzis (grep po predicted_tss/route_load -- zero wynikow).

  (c) BUDZET DZIENNY (CTL) -- rozwazono skalowanie pojemnosci wiaderek do tego samego dziennego
      budzetu, ktorego juz uzywa RSRV (`dailyBudgetTss = CTL*5.4`, patrz sekcja [MODELQ / QExt2]
      RSRV nizej). ODRZUCONE przez Michala 2026-07-07: "jesli wyskalujemy wiaderka pod RSRV to
      bez sensu -- nie pokaza uzytkowo wiecej niz RSRV". Redundancja z istniejacym polem, nie
      wnosi nowej informacji.

USTALENIE (2026-07-07, wciaz niedokonczone): pojemnosc wiaderek powinna pochodzic z MINIMALNEGO
UZYTECZNEGO BUDZETU TRENINGOWEGO dla KONKRETNEJ trasy (nie dziennego budzetu formy, nie prostego
% udzialu) -- czyli w praktyce zawezona, bardziej konkretna wersja (b). Kluczowa konsekwencja
wprost od Michala: JESLI trasa NIE jest wgrana na Karoo (brak zaplanowanej trasy) -> NIE MA
budzetu -> NIE MA pojemnosci wiaderek. JESLI trasa jest wgrana -> mamy pojemnosc.

NIEROZSTRZYGNIETE, do dogadania w kolejnej sesji:
- Jak dokladnie liczyc "minimalny uzyteczny budzet treningowy" z profilu trasy (dystans/
  przewyzszenie/spodziewany czas)? To wciaz niezbudowany model (jak w (b) wyzej), tylko teraz z
  jasniejsza definicja tego, co ma liczyc.
- Co pokazuje pole WIADRA, gdy trasa NIE jest wgrana (brak budzetu)? Warianty do przedyskutowania:
  ukryte pole / powrot do trybu (a) jako fallback / inny placeholder. Michal jeszcze tego nie
  zdecydowal.
- Zwiazane: potrzebny podzial dziennego/trasowego budzetu na 3 osobne cele Low/High/Peak (nie
  tylko jedna suma) -- patrz researchu nad Xert Adaptive Training Advisor (dzieli target XSS na
  Low/High/Peak indywidualnie, na podstawie improvement rate + deficyt/nadwyzka + dostepny czas,
  NIE na podstawie trasy -- to inny mechanizm niz to, czego szukamy tutaj, ale potwierdza, ze
  taki rozklad na 3 liczby ma sens i jest robiony gdzie indziej).

DO ZROBIENIA (dopiero po pelnej decyzji z powyzszego):
1. Zaprojektowac (osobna sesja, decyzja przed kodem) model "minimalny uzyteczny budzet
   treningowy" z profilu wgranej trasy + fallback dla braku trasy.
2. Kotlin `StrainBucketEngine` (nowy plik) -- mirror `fitmodel/buckets.py` 1:1 na liczenie
   surowego low/high/peak, zasilany moca 1s z Karoo SDK. UWAGA: potwierdzic dokladna nazwe pola
   raw-power w SDK (W'bal dzis uzywa SMOOTHED_3S_AVERAGE_POWER -- do wiader Michal chce SUROWEJ
   mocy 1s, to INNE pole, trzeba dopiac osobna subskrypcje). FTP juz dostepne on-device
   (AthleteDataStore).
3. UI: `field_stats_3x3.xml`, trzecia komorka ostatniego wiersza -> 3 kolumny (layout gotowy
   w mockupie mockup_wiadra_stats.html, do przeniesienia 1:1 na XML + RemoteViews w
   `StatsDataType.kt`).
4. Reset wiader na starcie kazdej nowej jazdy.
5. Build + CI + sideload (ta sama droga co Strona A / HR zones).

Powiazane, juz zrobione w tej samej sesji (patrz DECISIONS.md 2026-07-07):
- Strefy HR na Karoo przepiete z %maxHR na Coggan %LTHR (LTHR=132bpm) -- ZROBIONE, wypchniete,
  commit f13cd6b.

---

## [KOMOOT -> KAROO] Wariant A + bramka Telegram -- ZROBIONE (2026-07-06)

Pelny obieg dziala na zywo (test "TEST 18.05" #2963663831). Szczegoly: DECISIONS.md
2026-07-06 "Komoot -> Karoo (wariant A)". Commit 0e7bc29 + poprawka
telegram_reply_processor + handler webhooka qbot_api.py.

DOROBIONE 2026-07-06 (wszystkie 3, zweryfikowane):
1. Transport zablokowany na POLLING -- webhook jawnie usuniety (deleteWebhook, url puste);
   handler webhooka w qbot_api.py zostaje jako uspiony zapas.
2. Pytanie ponowne TYLKO przy zmianie geometrii -- kolumna komoot_geo_sig (hash
   wspolrzednych); edycja samej nazwy/meta = cicha aktualizacja bez powiadomienia.
3. created_date -- backfill 598/598 z listy tras (bez zapytan per-trasa).

---

## [XSS] Port XSS do QExt2 + wyswietlanie (dodane 2026-07-06)

**Zrobione w QBot 2026-07-06:** XSS (odpowiednik Xert Strain Score) liczony z
ModelQ (MPA/wBal), wzor `(moc/CP)*(1+1.0*fatigue)*(100/3600)`, kotwica 1h@CP=100,
BETA=1.0 skalibrowane do Xert training_load (EWMA-CTL 59.6 vs 62.4). Kolumny
xss/xss_per_h w fitmodel_wbal_ride, backfill 22 jazd, wpiete w daily_job (2d).
Patrz DECISIONS.md 2026-07-06.

**DO ZROBIENIA:**
1. **Port do QExt2** -- ten sam wzor jako funkcja obok tssValue()/rideReservePercent()
   w StatsCalculator.kt, karmiona CP_eff + wBal (juz sa on-device co sekunde).
   Zero dodatkowych zapytan do serwera w trakcie jazdy. Wymaga build+CI+sideload.
   Rekomendacja: dopiero gdy QBot XSS pochodzi kilka dni w produkcji ("zywy
   system wygrywa").
2. **Wyswietlanie XSS** w raporcie jazdy / Telegramie (dzis tylko kolumna w bazie).
3. **(Opcjonalnie) CTL/forma z XSS** -- gdy uzbiera sie wiecej danych (EWMA dopiero
   sie rozpedza na ~7 tyg danych).

---
> Rzeczy do zrobienia, żeby nie uciekły. Najnowsze na górze.
> To NIE jest CONTEXT.md (auto-gen) ani DECISIONS.md (decyzje). Tu leżą otwarte zadania.

---

## [MODELQ / KAROO / QExt2] Odciecie Xerta + zapis QExt2 do FIT (aktualizacja 2026-07-05)

Kontekst: budujemy odciecie Xerta (ModelQ jako jedyne zrodlo formy) i most QExt2<->QBot przez
plik FIT. Stan po sesji 2026-07-05 (szczegoly: DECISIONS.md wpisy 2026-07-05 (1)-(5)).

ZROBIONE:
- [x] Krok 1 -- CP z krotkich okien (120/300/600 s, ~242 W) rozdzielone od LTP z dlugich (~193 W).
- [x] Karoo /ride-readiness przepiete na ModelQ dla FTP+LTP (W' NADAL z Xerta ~22 kJ).
- [x] Krok 2 -- W' z harvestu near-max (koniec z artefaktem 34.8 kJ). Live: 20.3 kJ, confidence high.
      Bez swiezego twardego fragmentu -> NULL + przedzial 13-22 kJ + low.
- [x] Strona B -- QBot czyta 7 developer fields QExt2 z surowego FIT (tabela fitmodel_qext2_ride;
      no-op gdy plik ich nie ma).
- [x] Strona A -- QExt2 pisze te 7 pol @1Hz do FIT. Push przez deploy key, CI build #140 SUCCESS,
      APK build-140 (github.com/QbotMS/QExt2 Releases). Bez tokena w jawnej postaci (twarda granica).
- [x] Deploy key do QExt2 skonfigurowany i dziala (alias github-qext2, klon /opt/qbot/qext2_deploy).

POZOSTALO (kazdy krok osobno "decyzja przed kodem"):
1. [x] **[ZROBIONE 2026-07-06]** Przelaczono W' na Karoo /ride-readiness z Xerta na ModelQ
   (`_modelq_ftp_ltp`, commit 79e2fe4). Kazde pole (ftp/ltp/w') nadpisuje Xerta osobno, tylko
   gdy ModelQ ma wartosc. Zweryfikowane live: wPrimeKj=20.31 (bylo 22.4 z Xerta).
2. **Wykres W'bal w raporcie jazdy z Xerta na ModelQ.** Blok "forma" ma juz W' z ModelQ, ale sam WYKRES
   W'bal liczy sie na W' Xerta -- przelaczyc (byla razem z pkt 1, ale to osobny plik/miejsce
   w kodzie -- NIE zrobione jeszcze, sprawdzic ride_report_w2.py).
3. **Kosmetyczna etykieta zrodla w QExt2 (xertStatus -> ModelQ).** Wymaga kolejnego pushu QExt2 + CI
   (droga jak Strona A). Drobne -- nadal nie zrobione.
4. [x] **[ZROBIONE 2026-07-06]** Pierwszy realny test end-to-end Strona A<->B. Jazda 2026-07-06
   09:30-10:34 (build-140), external_id 23496824503 / plik hammerhead_44954.activity.e3cad43b...fit.
   Wszystkie 7 pol obecne w kazdym z 3783 rekordow od pierwszej sekundy. WAZNE: `ingest_all_new()`
   NIE odpala sie automatycznie -- trzeba go wywolac recznie/cronem na katalog
   outgoing/michal/hammerhead_originals (brak crona = fitmodel_qext2_ride zostaje pusta mimo
   gotowych danych w FIT). Uzupelniono recznie 2026-07-06 (17 plikow, w tym ta jazda) -- DO ZROBIENIA:
   dodac to do cyklicznego joba (daily_job.py?), zeby nie trzeba bylo robic tego recznie za kazdym razem.
5. **W' warstwa 1 -- kotwica z drogi.** Dane juz sa (fitmodel_qext2_ride.wbal_zero_seconds=82,
   wbal_zero_first_offset_s=3610 dla jazdy 2026-07-06) -- ZROBIC: wpiac to zdarzenie W'bal=0% jako
   realny pomiar wyczerpania do podniesienia pewnosci W' w Kroku 2.
6. [x] **[ZROBIONE 2026-07-06]** Krok 3 -- zrownanie W'bal w QBot z algorytmem QExt2. Nowy modul
   `fitmodel/wbal_replay.py`. Kluczowe dostrojenie: QExt2 karmi wzor moca SMOOTHED_3S_AVERAGE_POWER
   (SDK Karoo, nie surowa moc) -- z tym poprawiono srednia|diff| z 5.6pp do 0.49pp (izolowany test
   formuly) wzgledem prawdziwego qext2_wbal_pct z FIT-a. Walidacja end-to-end (pelny potok: baza +
   ModelQ FTP/W' + bramka postoj/dropout, BEZ podgladania urzadzenia): koncowe W'bal 33.5% (prawdziwe
   33%). [x] [ZROBIONE 2026-07-06] wpieto jako krok 2d w daily_job.py -> tabela
   fitmodel_wbal_ride (status/min/final/segments_json per jazda). Backfill 325
   kandydatow, 22 OK. Wyswietlanie w raporcie/Telegramie to OSOBNA, niezrobiona
   sprawa (na razie cichy backend zbierajacy dane).
7. **[ZROBIONE 2026-07-05, skorygowano 2026-07-06] Ingest activity_record 1Hz JUZ NIE STOI.**
   DECISIONS.md wpis 2026-07-05 (7): dopiety cron co 15 min (9-23), backfill przyrostowy
   (`backfill 20 0 2025-01-01 report`). Zweryfikowane na zywo 2026-07-06: `activity_record`/
   `activity_fit_raw` siegaja do 2026-07-04 (329 jazd, 2.35 mln rekordow 1Hz) -- TYLE SAMO co
   `training_sessions` (Garmin co 15 min) ma dla cyklingu; brak nowszych jazd = jeszcze nie ma ich
   w Garmincie (opoznienie Karoo->Garmin, NIE ingest QBota). Krok 3 (W'bal tick-po-ticku z QExt2)
   jest wiec ODBLOKOWANY danymi -- do zrobienia jak dojdzie czas.
   DROBNA ZASZLOSC (nieblokujaca): 9 plikow FIT z 30.06 w `/opt/qbot/artifacts/fit/` nie ma wiersza
   w `activity_fit_raw` (0 z nich ma parse_error) -- do wyjasnienia przy okazji, nie dzis.
   KANONICZNE ZRODLO SUROWEGO FIT dla wykonanych jazd (Garmin, 338 plikow na dysku, ~18 mies. wstecz)
   = `/opt/qbot/artifacts/fit/<external_id>.fit` + tabela `qbot_v2.activity_record`.
   `outgoing/michal/hammerhead_originals/` to INNY, WASKI katalog (bezposredni sync Hammerhead->dysk,
   ~9 tygodni wstecz, tylko do mostu QExt2 Strona B / fitmodel_qext2_ride) -- NIE uzywac go jako
   zamiennika activity_record/aktywnosci wykonanych jazd. Skalarne MMP (CP/W'/LTP/Peak Power,
   Warstwa 1) i tak nie potrzebuja zadnego z tych katalogow -- jada z training_sessions.mmp_*.


---

## [MODELQ / QExt2] RSRV -- ocena i mozliwe przestrojenie po realnych danych (dodane 2026-07-06)

**Kontekst:** RSRV mial byc odpowiednikiem Garmin Stamina ("ile baku zostalo na dzis").
Silnik w QExt2 (`rideReservePercent`) juz jest sensownie zaprojektowany pod ten cel:
start = `todayFactor*100`, odejmuje TSS (wzgledem budzetu z CTL) + kara za rozjazd
HR/moc, powolna odbudowa (tau=30min) na postojach. PROBLEM: nigdy nie dostawal
prawdziwego `todayFactor` (zawsze default 1.0 z `/ride-readiness`) -- wiec RSRV
zawsze "pelne" bez wzgledu na realna forme dnia.

**Zrobione 2026-07-06:** wpieto `readiness_score` (ModelQ, HRV+RHR+sen) jako
`todayFactor` w `/ride-readiness` (patrz DECISIONS.md). To naprawia WEJSCIE.

**DO ZROBIENIA (nie teraz -- po obejrzeniu kilku prawdziwych jazd z realnym
todayFactor):** ocenic czy sam WZOR RSRV w QExt2 (tempo TSS-penalty, tempo
odbudowy 30min, kara za decoupling) faktycznie "czuje sie" jak Stamina, czy
wymaga przestrojenia. To wymaga danych z obserwacji (nie zgadywania na sucho)
i prawdopodobnie kolejnego pushu QExt2 + CI, jesli cos trzeba zmienic w kodzie
kotlinowym (nie tylko w danych wejsciowych z serwera).

**[ZROBIONE 2026-07-07] Przepieto RSRV z TSS na XSS.** Odkryto na zywo, ze XSS
byl juz policzony on-device (`StatsCalculator.kt: xssAccum`/`xssValue()`) --
TODO nizej ([XSS] Port XSS do QExt2) bylo NIEAKTUALNE, port juz istnial.
Zmiana: `rideReservePercent` dostaje teraz `effectiveXss` (baza dzienna + sesja,
z `statsCalc.xssValue()`) zamiast `effectiveTss`. TSS/`tssValue()` NIETKNIETE --
zostaja wylacznie dla wlasnego pola statystyk "TSS", juz nie karmia RSRV.
Nowe klucze persystencji w `AthleteDataStore` (`ReserveDailyXssBase(Date)`) --
CELOWO nie nadpisano starych TSS-owych, zeby wczorajszy zapisany TSS nie zostal
pomylony z dzisiejszym XSS po aktualizacji. Ta sama logika resetu (nowy
dzien / sleep refresh / cleanup >500) zreplikowana 1:1 dla XSS. Budzet dzienny
w `rideReservePercent` (`CTL*5.4`) zostal BEZ ZMIAN -- to przyblizenie (TSS i
XSS maja te sama kotwice 1h@prog=100, ale to nie identyczna liczba dla tej
samej jazdy) -- do obejrzenia na zywych jazdach, czy RSRV "czuje sie" dobrze
w nowym tempie wyczerpywania (XSS mocniej kara zrywy przez zmeczenie niz TSS).
Pliki: `AthleteDataStore.kt`, `RideDataAggregator.kt`. Commit `406f9d4` w
`QbotMS/QExt2` main, push potwierdzony. Michal: build+CI+sideload jak zawsze.

---

## [SPRZATANIE] Usunac martwy `qbot_mcp_adapter.py` (legacy konektor) (dodane 2026-07-04)

**Kontekst (potwierdzone na zywo):** `/mcp` (qbot.cytr.us/mcp, serwuje `qbot-api`) rozgalezia sie na fladze `QBOT3_ENABLED`. Flaga **=1** we wszystkich aktywnych env (`qbot-api.env`, `.env`, `.env.local`) => `/mcp` zawsze wola `handle_qbot3_mcp` (qbot3 -> `intake_log_create`, nowy zeszyt `intake_logs`). Legacy `handle_mcp_request` z `qbot_mcp_adapter.py` (-> `meal_log_create` -> stary `meal_logs` + kopia do intake w `try/except: pass`) odpala sie TYLKO przy fladze =0 => obecnie **martwy kod**. Potwierdzone: ChatGPT i Claude uzywaja tego samego `https://qbot.cytr.us/mcp/`. W bazie 0 wpisow w starym `meal_logs` za ost. tydzien = legacy droga nieuzywana.

**Do zrobienia (decyzja przed kodem):**
1. UWAGA (sprawdzone 2026-07-04): `qbot_api.py` importuje z `qbot_mcp_adapter` NA STARCIE (`handle_mcp_request`, `_tool_qbot_mcp_status`, `_tool_qbot_mcp_tools_list`, `_validate_mcp_access`) i uzywa ich w gałęziach `else` (flaga=0) w: POST `/mcp` (1413), GET `/mcp` (mcp_root), `/mcp/health`, `/mcp/tools`. Samo skasowanie pliku => ImportError => CRASHLOOP qbot-api. Najpierw usunac WSZYSTKIE te uzycia/importy.
2. Usunac import + gałąź legacy w `qbot_api.py` (albo zostawic twardy 4xx "legacy off").
3. Usunac `qbot_mcp_adapter.py`; sprawdzic czy `meal_log_create` uzywane gdziekolwiek indziej zanim tkniemy.
4. Zaktualizowac `CONTEXT.md` (znika wzmianka o "oddzielnym adapterze ChatGPT") i `DECISIONS.md`.

**Uwaga:** to NIE naprawia zawodnosci zapisu z ChatGPT (ta jest po stronie blokad konektora OpenAI). To usuwa mylaca martwa sciezke i trwale kasuje ryzyko "dwoch zeszytow".

---

## Bramka walidacji treści POI/warstw + auto-wznawianie pobierania (odłożone 2026-07-03)

**Kontekst / dlaczego:** Telegram melduje „✅ Analiza zakończona. Dane zapisane w DB", nawet gdy dane są ucięte/śmieciowe. Przyczyna (potwierdzona na kodzie):
- `route_precompute_orchestrator._run_job` oznacza warstwę `complete`, jeśli writer NIE rzucił wyjątku — nie sprawdza treści.
- `route_precompute_trigger._precompute_complete` → ✅, gdy wszystkie warstwy `complete` (+ surface/frames OK). Zero walidacji zawartości.
- `technical_completeness=COMPLETE` mierzy tylko pokrycie fragmentów pobierania (missing_chunks), nie poprawność treści.
- Liczniki `summary` liczą listę PRZED obcięciem — mogą się rozjeżdżać z tym, co realnie w DB (był bug `[:15]/[:12]` w analizatorze, już podniesiony do `[:200]`).

**Do zbudowania:**
1. **Bramka walidacji z odczytem zwrotnym z DB** po każdej warstwie (progi per warstwa):
   - POI: zaopatrzenie sięga ~≥90% dystansu trasy; ≥1 punkt w każdej tercji; atrakcje po bramce jakości.
   - nawierzchnia: pokrycie ~100% węzłów osi; frames > 0.
2. **Auto-wznawianie (ograniczone) — tylko braki transientne:**
   - Jeśli `missing_chunks` obecne (sieć/timeout/throttle) → pętla celowanego retry (analizator MA już: retry ×3 + backoff, bisekcję, `retry_payload_json`, `merge`, wejście `retry_mode`/`retry_chunk_id`) + scalanie; limit np. 2–3 rundy.
   - Jeśli bramka nie przechodzi, a `missing_chunks` puste (COMPLETE-ale-zły-content = BŁĄD LOGIKI, jak dawny cap) → NIE wznawiać (odtworzy ten sam bubel); **eskalować do człowieka**.
3. **Uczciwy komunikat Telegram:** ✅ tylko po przejściu bramki; inaczej ⚠️ z konkretem („zaopatrzenie tylko do 48/106 km", „POI: brak w Q3"); pokazywać realne liczby (sklepy X, atrakcje Y, % nawierzchni), nie suche „Dane zapisane w DB".

**Zakres plików:** `qbot3/routes/route_precompute_orchestrator.py`, `qbot3/artifacts/route_analyzer.py` (retry/merge już są), `scripts/route_precompute_trigger.py` (komunikat + gating). Decyzja przed kodem: najpierw plan progów.


---

## [ZYWIENIE] Pozostale drobiazgi po naprawie zapisu (dodane 2026-07-05)

Kontekst: glowna naprawa "jedzenie znika" zrobiona i zweryfikowana (DECISIONS.md 2026-07-05 (6)).
Zostaly 3 drobne, NIEBLOKUJACE plasterki ze spec TS-2026-07-05-NUTRITION-WRITE-FIX.md:

1. Usunac walidacje sugar-type w `_validate_and_fix_meal_items` (qbot_nutrition_db.py) -- zeruje
   makra/kcal niezaleznie od reszty (trzecia, potwierdzona przyczyna objawu "zera w makrach").
2. Sierota w starym `meal_logs` (id=16) -- do sprzatniecia.
3. `_action_exec_nutrition_delete/correct` (qbot_mcp_adapter.py) robi UPDATE bez filtra `source`
   -- tor martwy, ale moze po cichu nadpisac cudze wiersze; posprzatac przy okazji.


## [FORMA] Kafelek WEB "Forma (ModelQ)" -- szkielet gotowy, czeka na CTL/ATL/TSB (dodane 2026-07-07)

**Zrobione:** `/forma.html` + `/forma-render.js` (poza repo, `/opt/qbot/web/public/`) + endpoint
`GET /api/forma/data?start=&end=` (`qbot_web.py`: `_build_forma_data`, `forma_data`). Karta "Dzis"
(FTP_est, CP, LTP, W'+pewnosc, W/kg, glikogen, HRV, RHR, sen, gotowosc z pelnym uzasadnieniem),
wykres 90 dni domyslnie (presety 7/30/90/365 + wlasny zakres), gestre serie jako linie, dziurawe
jako punkty. Kafelek w `index.html`. Zweryfikowane na zywych danych (patrz DECISIONS.md
2026-07-07 (2)).

**Otwarte / nastepny krok:**
- [x] **[ZROBIONE 2026-07-07]** Sekcja CTL/ATL/TSB podpieta -- `_build_training_load_latest()`
  w `qbot_web.py`, warianty "raw" jako glowne ctl/atl/tsb, "plus" jako dodatkowe pola w
  payloadzie (front ich jeszcze nie czyta). Szczegoly: DECISIONS.md 2026-07-07 (6).
- MODELQ.md nie opisuje `readiness_score/readiness_label/readiness_note` (kolumny sa w live
  DB i uzywane w tym kafelku) -- dopisac przy okazji do dokumentu.
- Do rozwazenia pozniej: normalizacja skal na wykresie (dzis dwie osie Y, W i "inne" -- przy
  wlaczeniu kilku serii z prawej osi jednoczesnie moze byc nieczytelnie, np. HRV (ms) i
  readiness_score (-1..1) na tej samej osi). Nie blokujace na start.


## [FORMA-MODEL] FTP tlumienie + CP/LTP ratchet-zanik + W' zanik -- WDROZONE 2026-07-07, patrz DECISIONS.md (4)

Pelna diagnoza i decyzja: `DECISIONS.md` 2026-07-07 (3). Skrot zadan do wdrozenia:

1. **FTP_est** (`fitmodel/ftp_resolver.py`): dopisac brakujace tlumienie z MODELQ.md 4.3
   (`zmiana_tyg = clip(+/-0.5*delta)`) -- dzis nie istnieje w kodzie mimo ze opisane w dokumencie.
2. **CP/LTP** (`fitmodel/cp_wprime.py`, `_envelope_curve`): dodac ratchet (rekord = wartosc+data,
   bez sztywnego okna 90d -- rozwazyc dlugie okno np. 365d albo osobna tabele) + liniowy zanik
   60->120 dni od daty rekordu do podlogi = biezacy FTP_est. Po 120 dniach trzyma podloge.
3. **W'** (`fitmodel/cp_wprime.py`, `_wprime_harvest`): dodac liniowy zanik 60->120 dni (dzis
   `WPRIME_FRESH_DAYS=60` skacze prosto na przedzial 13-22 kJ) do podlogi = 13 kJ (dolna granica,
   nie srodek -- zachowawczo, bo steruje pacingiem).
4. Do rozstrzygniecia PRZED kodem: gdzie trzymac (wartosc, data) rekordu per dlugosc -- nowe
   kolumny w `fitmodel_daily` czy osobna tabela `fitmodel_cp_records`. Sugestia: osobna tabela
   (per duration: 120/300/600/1200/1800s), bo `fitmodel_daily` jest per-dzien a rekord to
   per-dlugosc-wysilku, niezalezny od dnia.
5. **ZROBIONE (2026-07-07):** backfill `fitmodel_daily` wykonany -- 553/553 dni (2025-01-01..2026-07-07), 0 bledow. FTP tlumienie + CP/LTP/W' ratchet+zanik przeliczone na zywo (bez tabeli `fitmodel_cp_records`, ktora okazala sie psuc przeliczanie starych dni -- patrz DECISIONS.md 2026-07-07 (5)). Test 5->6 marca potwierdzony: +27,3W surowo -> +14,9W po tlumieniu.
