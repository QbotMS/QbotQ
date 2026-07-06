# QBot — TODO

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
