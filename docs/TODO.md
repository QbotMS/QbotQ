# QBot — TODO

> Rzeczy do zrobienia, żeby nie uciekły. Najnowsze na górze.
> To NIE jest CONTEXT.md (auto-gen) ani DECISIONS.md (decyzje). Tu leżą otwarte zadania.

---

## [MODELQ / KAROO / QExt2] Pozostale kroki odciecia Xerta i zapisu do FIT (dodane 2026-07-05)

Kontekst: Krok 1 zrobiony (CP z krotkich okien vs LTP z dlugich rozdzielone). Karoo przepiete
na ModelQ dla FTP+LTP przez endpoint `/ride-readiness` (W' na razie zostaje z Xerta ~22 kJ,
bo ModelQ W' jest jeszcze niewiarygodne). Ponizej co zostalo, w kolejnosci, z celem.

1. **Krok 2 — W' w ModelQ (null + range 13-22 kJ + confidence:low).**
   Po co: dzis `wprime_modelq_kj` = ~35 kJ to zawyzony artefakt (submaks). Potrzebne uczciwe W',
   zeby (a) raport nie klamal, (b) mozna bylo przepiac W' na Karoo z Xerta na ModelQ.
   Metoda: oportunistyczny harvest near-max z istniejacych MMP (mmp_30/60/120), plus kotwica
   z drogi (zdarzenie W'bal=0% na Karoo). Bez swiezego twardego momentu -> W'=null+range+low.

2. **Przepiac W' na Karoo z Xerta na ModelQ (PO Kroku 2).**
   Po co: domkniecie pelnego odciecia Xerta -> Karoo w 100% na ModelQ. Miejsce: override w
   `qbot_api.py` `_modelq_ftp_ltp` / `/ride-readiness` (dzis W' celowo omija ModelQ).
   Wtedy mozna tez wywalic zywe wywolanie Xerta z endpointu.

3. **WATEK 2 — QExt2 zapisuje swoje liczby do pliku FIT (developer data fields).**
   Po co: (a) domyka Krok 3 bez klonowania Kotlina, (b) daje etykietowane kotwice do harvestu W'.
   Pola: W'bal %, efektywne CP/W', wspolczynnik cf, znacznik zdarzenia 0%.
   Wymaga PO STRONIE QExt2: `fitFile="true"` w extension_info.xml + wypelnic pusty `startFit`
   (emisja FitEffect) -> przebudowa APK + wgranie na Karoo (fizyczny krok Michala).
   Wymaga PO STRONIE QBota: dopisac odczyt developer fields w `fitmodel/fit_ingest.py`
   (dzis czyta tylko standardowe pola: moc/tetno/kadencja/temp/predkosc/dystans/wysokosc;
   biblioteka fitparse te pola udostepnia). Wymaga przepustki (deploy key) do QExt2.

4. **Krok 3 — zrownanie W'bal w QBot (W1) z algorytmem QExt2 (dynamiczne tau + skalowanie readiness).**
   Po co: zeby liczby W'bal po stronie QBota zgadzaly sie z tym, co Karoo pokazuje na drodze
   (rozjazd 0% na Karoo vs 12% minimum w W1). Latwiejsze, gdy WATEK 2 dostarczy pola z FIT.

5. **Naprawic ingest `activity_record` 1Hz (stanal 2026-06-28) albo liczyc MMP z plikow FIT.**
   Po co: tick-po-ticku W'bal (Krok 3) tego potrzebuje. UWAGA: skalarne MMP (Krok 0/1/2)
   tego NIE potrzebuja -- to blokuje tylko Krok 3.

6. **Przepustka do zapisu QExt2 (deploy key) -- dokonczyc setup.**
   Po co: zeby Claude mogl sam pushowac zmiany do QExt2 (potrzebne do WATKU 2), bez tokena.
   Status: user wkleil czesc publiczna klucza (qext2-deploy). Zostalo: dodac na GitHub
   (repo QExt2 -> Settings -> Deploy keys -> Allow write access), alias `github-qext2` w
   ~/.ssh/config na `q`, test `ssh -T git@github-qext2`.

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
