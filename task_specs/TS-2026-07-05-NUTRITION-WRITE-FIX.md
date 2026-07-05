# Instrukcja naprawy: zapis żywienia z ChatGPT + ujednolicenie zeszytów

- **Data:** 2026-07-05
- **Autor:** sesja robocza (Claude/DEV MCP)
- **Status:** DO AUDYTU w osobnej sesji kontrolnej. NIE wdrażać przed audytem.
- **Zasada:** decyzja przed kodem. Każdy etap: kod → restart → test na żywo → commit → dopiero następny.
- **Uwaga o liniach:** numery linii wg stanu repo na 2026-07-05. Przed każdą edycją zweryfikować `grep -n`, bo mogły się przesunąć.

---

## 0. TL;DR

Zapis posiłku z ChatGPT jest **loterią**: raz się zapisuje, raz dostajesz „draft — użyj qbot.action_execute" (a tego narzędzia na `/mcp` nie ma). Przyczyna NIE jest w torze zapisu do bazy (ten działa) ani w wyborze frontu (ChatGPT i Claude używają tego samego `https://qbot.cytr.us/mcp/`). Przyczyna to **sprzeczne reguły w prompcie Alberta**: jedna każe oddawać draft, druga każe zapisywać wprost. Naprawa główna = prompt-only, niskie ryzyko. Osobno: reguła „od dżemu" zeruje makra, oraz stary/nowy zeszyt (`meal_logs` vs `intake_logs`) rozjeżdżają listę i kasowanie.

---

## 1. Objaw (zgłoszony)

- „Dodaję posiłek z ChatGPT, dostaję OK, a w raporcie pusto."
- Czasem: „To jest tylko draft i wymaga qbot.action_execute."
- Czasem: makra (białko/tłuszcz) zapisują się jako 0.
- Przez CLI: numer z listy nie daje się skasować; bilans dnia liczy duplikat.

---

## 2. Ustalenia potwierdzone (z dowodami)

Wszystko poniżej sprawdzone na żywym kodzie/bazie (nie z pamięci).

1. **Jeden endpoint.** ChatGPT i Claude używają `https://qbot.cytr.us/mcp/`. Serwuje go `qbot-api`. `qbot_api.py:1388–1414` — POST `/mcp` rozgałęzia się na fladze `QBOT3_ENABLED`.
2. **Flaga = 1 na żywo** (`qbot-api.env`, `.env`, `.env.local`). Więc `/mcp` zawsze woła `handle_qbot3_mcp` (qbot3) → zapis przez `intake_log_create` → nowy zeszyt `qbot_v2.intake_logs`. Legacy `handle_mcp_request` (stary zeszyt) jest przy fladze=1 martwy.
3. **Jedno narzędzie wystawione.** `qbot3/adapters/mcp_adapter.py:244–260` (`_list_tools`) wystawia TYLKO `qbot_query`. **`qbot.action_execute` NIE istnieje jako narzędzie MCP.** To jest ślepy koniec każdej instrukcji „użyj action_execute".
4. **Zapisy eskalują do Alberta.** `mcp_adapter.py:112–115` (`_QBOT_QUERY_WRITE_RE` = dodaj|zapisz|dopisz|usuń|…) + `:141–142`: fraza zapisu → `pre_escalation_reason="ACTION_REQUIRED"` → deterministyczny handler pominięty → `orchestrate_query` (Albert). Czyli „Dodaj placek…" idzie do Alberta.
5. **ROOT CAUSE — sprzeczny prompt Alberta** (`qbot3/llm/albert.py`, `_SYSTEM`):
   - `:185` „Zapis danych → zwróć draft, poinformuj że wymaga qbot.action_execute."
   - `:186` „NIGDY nie mów 'dodano/zapisano/wykonano' bez realnego qbot.action_execute."
   - ale `:188–195` (nowsze, żywieniowe) każą zapisywać wprost i raportować `write_committed`/`user_message`.
   - Dwa sprzeczne rozkazy → Albert raz zapisuje (reguła 188–195), raz oddaje draft i odsyła do nieistniejącego action_execute (reguła 185). To jest „loteria".
   - `:509–518` wymusza komunikat „to draft, użyj action_execute" TYLKO gdy tool zwróci `status="WRITE_DRAFT"`.
6. **Narzędzie żywienia NIE zwraca WRITE_DRAFT.** `nutrition_log_add` przez `_execute_nutrition_write` (`qbot3/adapters/mcp_adapter.py:435+`) zapisuje wprost i zwraca `write_committed=true` + `user_message` (zweryfikowane runtime tej sesji: pierwszy zapis OK/write_committed=True, duplikat → DUPLICATE_SKIPPED, w bazie dokładnie 1 wiersz). Więc reguła 185 jest po prostu szkodliwa dla żywienia — każe udawać draft mimo że tool umie zapisać.
7. **Błąd sugar-type** (`qbot_nutrition_db.py:302–311`): jeśli JAKIEKOLWIEK słowo cukrowe (`miod, dzem, syrop, jam, konfitura…`) występuje GDZIEKOLWIEK w nazwie pozycji, zeruje białko i tłuszcz całej pozycji, gdy >2 g. „Placek…dzem_figowy" → B14→0, T14→0. Reguła robi substring-match na całej nazwie złożonego posiłku.
8. **Dwa zeszyty, niespójne operacje:**
   - `meal_log_create` (`qbot_nutrition_db.py:166+`) pisze do starego `meal_logs`/`meal_log_items`, a potem „równolegle" do `intake_logs`/`intake_items` w bloku `try/except: pass` (`:214–268`, komentarz „v2 zapis nigdy nie blokuje v1"), i zwraca `get_meal_log(meal_id)` = ID ze STAREGO zeszyta.
   - `meal_log_list` (`:470+`) czyta z NOWEGO `intake_logs`.
   - `meal_log_delete` (`:496+`) kasuje ze STAREGO `meal_logs`.
   - Efekt: lista pokazuje ID z `intake_logs`, delete szuka w `meal_logs` → „nie istnieje"; bilans (czyta `intake_logs`) trzyma duplikat.
   - Wołający `meal_log_create`: CLI `qbot_nutrition_cli.py` + martwy legacy adapter `qbot_mcp_adapter.py`. (Zweryfikować pełną listę przed zmianą.)
9. **`resolved_food_entry` nieobsługiwane.** Fraza występuje w raportach ChatGPT, ale w kodzie QBota `grep -rn resolved_food_entry` = 0 trafień. QBot nigdy tego pola nie czytał — ChatGPT sam wymyślił kontrakt.

---

## 3. Sprostowania (traktować krytycznie wnioski z raportu GPT i wcześniejsze)

- **GPT:** „Qbot ignoruje resolved_food_entry" → nieścisłe. QBot nigdy tego pola nie miał; to zmyślony przez ChatGPT kontrakt (pkt 9).
- **GPT:** miesza 3 tory (MCP `qbot_query`, Albert, CLI) w „jeden qbot". Błędy dwóch zeszytów (pkt 8) są w rodzinie `meal_log_*` (CLI + martwy adapter), NIE w torze `/mcp` qbot3 (ten pisze tylko do `intake_logs`).
- **GPT:** jego „obejście" przez CLI samo zostawiło sierotę w starym zeszycie (`meal_logs` id=16, 04.07 — potwierdzone, wisi do teraz). Czyli workaround demonstruje błąd, a nie go omija.
- **Wcześniejsze moje:** „główny winowajca to opis narzędzia (blokady OpenAI)" — to tylko czynnik uboczny. Sedno to sprzeczny prompt Alberta (pkt 5). Sama zmiana opisu nie naprawi zapisu.
- **Wcześniejsze moje:** „legacy meal_logs puste = droga nieużywana" — nieaktualne po sesji CLT z placekiem (jest tam id=16). Legacy jest używane przez CLI.

---

## 4. Plan naprawy — etapy

### Etap 0 — dowód runtime (OBOWIĄZKOWE przed kodem)
Zanim cokolwiek zmienisz, odtwórz zapis tak jak robi to ChatGPT i złap, KTÓRA gałąź daje finalną odpowiedź (Albert-zapis vs Albert-draft):
- Wywołaj `orchestrate_query("Dodaj do jedzenia 2020-04-04: Test 300 kcal, B10 W40 T5", context='{"source":"chatgpt"}')` w `.venv`.
- Oczekiwane PRZED naprawą: część uruchomień → draft/action_execute (reguła 185), część → realny zapis.
- Cel: potwierdzić, że tekst „draft/action_execute" pochodzi z Alberta (reguła 185), a nie z deterministycznego handlera.
- Posprzątać dane testowe (data 2020-*).

### Etap 1 — prompt Alberta: zapis od razu (P1, ryzyko NISKIE, prompt-only)
**Plik:** `qbot3/llm/albert.py`, `_SYSTEM`.
**Zmiana:**
- Usunąć/zastąpić `:185–186`. Nowa treść (propozycja):
  - „Zapis danych: jeśli masz narzędzie zapisu (nutrition_log_add / calendar_event_add / reminder_add), WYWOŁAJ je i raportuj realny wynik wg reguł niżej. Draft zwracaj TYLKO gdy narzędzie samo zwróci status WRITE_DRAFT."
  - Zostawić zasadę: „NIGDY nie mów 'zapisano' bez realnego write_committed=true" (to jest dobre i spójne z 189).
- Zostawić bez zmian `:188–195` (żywieniowe reguły direct-write) — to jest docelowa, poprawna ścieżka.
- Zostawić `:193` i `:509–518` (obsługa WRITE_DRAFT) — nie szkodzą, bo żywienie nie zwraca WRITE_DRAFT; przydadzą się, gdyby kiedyś jakiś tool draftował.
**Efekt:** Albert dla „dodaj posiłek …" wywołuje `nutrition_log_add` i cytuje `user_message` (uczciwe „Zapisano …" lub „NIE zapisano … duplikat/błąd"). Koniec ślepego draftu.
**Reguła projektu:** zmieniamy tylko `_SYSTEM`, nie `tool_registry.py` → nie trzeba innych zmian rejestru. (Potwierdzić, że rejestr niezmieniony.)
**Test (żywy):** przez `orchestrate_query` 3–4 różne frazy zapisu (z jawnymi makrami; z samą nazwą; „dodaj obiad 600 kcal"); sprawdzić `write_committed=true` i realny wiersz w `intake_logs`; sprawdzić że NIE pojawia się „action_execute". Regresja: sprawdzić calendar_event_add i reminder_add (mają własne reguły 196–199 — nie mogą się zepsuć). Posprzątać dane testowe.
**Rollback:** przywrócić poprzedni `_SYSTEM` (backup przed edycją).

### Etap 2 — „dodaj ten placek" + dane z kontekstu (P1, ryzyko NISKIE)
**Problem:** anafora „ten placek" + dane w polu, którego QBot nie czyta.
**Opcje (do decyzji w audycie):**
- (a) QBot czyta `context.resolved_food_entry` jako gotowy payload zapisu (nazwa+kcal+makra+data). Zmiana w torze zapisu żywienia (tam gdzie budowany jest payload dla `intake_log_create`). Wymaga zdefiniowania kanonicznego kształtu pola i walidacji.
- (b) Prostsze/tańsze: NIE czytać wymyślonego pola; zamiast tego zadbać, żeby ChatGPT wstawiał dane w treść `query` (zmiana po stronie ChatGPT, poza QBotem). QBot i tak umie parsować jawne kcal+makra z treści.
**Rekomendacja:** zacząć od (b) jako natychmiastowego obejścia; (a) rozważyć jako trwałe, jeśli chcemy wspierać anaforę bez powtarzania danych.
**Test:** „dodaj ten placek" z danymi w query → zapis; z samą anaforą bez danych → jasne „potrzebuję danych", NIE fałszywe OK.

### Etap 3 — jeden zeszyt zamiast dwóch (P1, ryzyko ŚREDNIE)
**Pliki:** `qbot_nutrition_db.py` (`meal_log_create`, `meal_log_delete`), `qbot_nutrition_cli.py`.
**Zmiana:**
- `meal_log_delete`: kasować z `intake_logs`/`intake_items` (jak nowy zeszyt), nie z `meal_logs`.
- `meal_log_create`: przestać pisać do starego `meal_logs` (koniec dual-write) albo zamienić na cienką nakładkę nad `intake_log_create`; zwracać ID z `intake_logs`.
- CLI: `meal-add`/`meal-list`/`meal-delete`/`summary-show` operują na tych samych (intake) ID; po zapisie/delete robić read-after-write z tabeli, która buduje bilans.
**Przed zmianą:** `grep -rn "meal_log_create\|meal_log_delete"` w całym repo — potwierdzić wszystkich wołających (spodziewane: CLI + martwy `qbot_mcp_adapter`). Sprawdzić, czy `meal_log_create` nie jest używane w torze `/mcp` (nie powinno — tam idzie `intake_log_create`).
**Ryzyko:** dotyka CLI; martwy adapter i tak do usunięcia (osobny TODO `[SPRZATANIE]`). Zmiana kontraktu ID w CLI (celowa — to jest naprawa).
**Test:** CLI: add → list (pokazuje intake ID) → delete tego samego ID → znika → summary bez duplikatu. Brak nowych wpisów w starym `meal_logs`.

### Etap 4 — plasterki (ryzyko NISKIE)
- **sugar-type** (`qbot_nutrition_db.py:302–311`): reguła ma NIE zerować makr, gdy słowo cukrowe to tylko część nazwy złożonego posiłku. Propozycje (do decyzji):
  - zawęzić: zerować tylko gdy nazwa to praktycznie czysty produkt cukrowy (np. cała nazwa ∈ {miód, cukier, syrop, dżem, konfitura, marmolada}), albo
  - w ogóle usunąć tę regułę i polegać na istniejącym checku spójności kcal↔makra (`:313–332`), który i tak łapie niespójne makra.
  - Test: „Placek …dzem_figowy" 485/14/77/14 → makra zostają; „Dżem figowy 100 g" 250/0.5/60/0 → bez zmian.
- **sierota id=16**: usunąć wpis `qbot_v2.meal_logs` id=16 (04.07) + ewentualne `meal_log_items` do niego. Read-back: brak w `meal_logs` dla 04.07; `intake_logs` 04.07 bez zmian (id=232, Placek 485/14/77/14).

---

## 5. Zasady wdrożenia

- Etapami, w kolejności 1 → 2 → 3 → 4. Po każdym: restart właściwej usługi (`qbot-api` dla promptu Alberta i toru `/mcp`), test na żywo, commit (jako qbot, push jako root), dopiero następny.
- Backup pliku przed edycją; `ast.parse` przed restartem; `assert count==1` na kotwicach.
- Nie ruszać `qbot_web.py` ani `qbot3/rides/` (cudza robota w drzewie).
- Historia crashloopa: nie kasować plików importowanych na starcie bez usunięcia wszystkich importów (dot. osobnego TODO o `qbot_mcp_adapter`).

## 6. Checklista dla sesji kontrolnej (audyt)

- [ ] Potwierdzić `QBOT3_ENABLED=1` w aktywnym env i że `/mcp` → `handle_qbot3_mcp`.
- [ ] Potwierdzić, że `_list_tools` wystawia tylko `qbot_query` (brak `action_execute`).
- [ ] Runtime (Etap 0): odtworzyć zapis i pokazać, że draft/action_execute pochodzi z reguły `albert.py:185`.
- [ ] Potwierdzić, że `nutrition_log_add` NIE zwraca `WRITE_DRAFT` (zwraca write_committed).
- [ ] Zweryfikować kotwice linii przed edycją (numery mogły się przesunąć).
- [ ] Ocenić Etap 2 (a) vs (b).
- [ ] Wylistować wszystkich wołających `meal_log_create`/`meal_log_delete` przed Etapem 3.
- [ ] Zatwierdzić kształt reguły sugar-type (zawęzić vs usunąć).

## 7. Otwarte decyzje

1. Etap 2: czytać `resolved_food_entry` (trwałe wsparcie anafory) czy wymagać danych w `query` (prościej)?
2. Etap 3: `meal_log_create` → cienka nakładka na `intake_log_create`, czy zostawić funkcję ale bez zapisu do legacy?
3. sugar-type: zawęzić czy usunąć (na rzecz checku spójności kcal↔makra)?
4. Czy przy Etapie 1 dołożyć też łagodniejszy nudge w opisie `qbot_query` (kwestia blokad OpenAI) — czy trzymać osobno.


---

## 8. Poprawki po audycie #1 (2026-07-05)

> Oryginał sekcji 1–7 zostaje nietknięty (ślad dla kolejnego audytu). Poniżej rozstrzygnięcia i korekty po pierwszej sesji kontrolnej.

### 8.1 Endpoint ChatGPT — ROZSTRZYGNIĘTE (potwierdzone przez użytkownika)
- ChatGPT to **konektor MCP dodany przez URL `https://qbot.cytr.us/mcp/`**. Użytkownik potwierdził: NIE używa Custom GPT / akcji OpenAPI/REST.
- Konsekwencja: ChatGPT idzie `/mcp` → `qbot_query` → (write regex) → Albert. **Etap 1 (prompt Alberta) dotyczy ChatGPT wprost.**
- Zamyka to zarzut audytu „może ChatGPT pisze do REST /nutrition/meals". Konektor MCP może wołać wyłącznie narzędzia z tools/list (`qbot_query`); nie umie strzelić do endpointu REST. Dowody zbieżne: URL podany przez użytkownika + raport pokazuje wywołania `qbot.query` z kontekstem/`request_id`.

### 8.2 Korekta zasięgu Etapu 3 — audyt miał rację (mój spec był niepełny)
Sekcja 2 pkt 8 podawała wołających `meal_log_create` jako „CLI + martwy adapter". To NIEPEŁNE. Potwierdzone dodatkowe, ŻYWE ścieżki piszące do starego zeszyta przez `meal_log_create`, niezależnie od Alberta:
- `qbot_api.py:1027` — `POST /nutrition/meals` (ręczny zapis posiłku przez REST).
- `qbot_api.py:1070` — `POST /nutrition/import/cronometer/servings-csv` (import Cronometer, `source="cronometer_import"`).
Uwaga: to NIE jest tor ChatGPT (ten idzie `/mcp`→Albert→`intake_log_create`). Ale przy ujednolicaniu zeszytów (Etap 3) te endpointy też trzeba przełączyć na `intake_logs` albo wygasić — inaczej dalej będą siać do legacy. Przed Etapem 3: pełny `grep -rn "meal_log_create"` i decyzja per-caller (REST endpointy: przepiąć na intake, czy wyłączyć, jeśli nieużywane).

### 8.3 Nowa opcja w P1 — deterministyczny tor zapisu (odpowiedź na uwagę audytu o zależności od LLM)
Audyt słusznie zauważył: po Etapie 1 zapis dalej zależy od decyzji Alberta (LLM). Dodajemy jako opcję (do decyzji w audycie #2):
- **Opcja D:** dla zapytań z JAWNYMI kcal + makrami (regex/parser prosty, deterministyczny) — kierować prosto do `intake_log_create` (z kontrolą odczytu + `user_message`), z pominięciem Alberta. Albert zostaje tylko dla przypadków niejednoznacznych.
- Zysk: najczęstszy przypadek („dodaj X — 485 kcal, B14 W77 T14") staje się pewny, bez loterii LLM.
- Koszt: nowy mały parser + gałąź w routingu (`mcp_adapter._call_tool` lub `qbot_query_handler`). Ryzyko średnie — dotyka toru zapytań.
- Rekomendacja: Etap 1 (prompt) najpierw (tani, natychmiastowy zysk), Opcja D jako hardening zaraz po, jeśli po testach loteria dalej doskwiera.

### 8.4 Ocena uwagi audytu „Etap 1 tylko tłumi loterię"
Częściowo słuszne, ale z ważnym zastrzeżeniem: po Etapie 1 loteria **przestaje być groźna**, bo:
- kontrola odczytu + `write_committed` + `user_message` już działają (zweryfikowane runtime),
- prompt (po naprawie) zabrania fałszywego „zapisano" bez realnego zapisu,
- strażnik Telegram (timer 08:00) łapie pusty dzień rano.
Czyli najgorszy scenariusz (OK bez wiersza) znika już po Etapie 1. Determinizm (Opcja D) to hardening pewności, nie warunek konieczny uczciwości.

### 8.5 Zaktualizowane otwarte decyzje
1. Etap 2: `resolved_food_entry` (trwałe wsparcie anafory) vs dane w `query` — bez zmian, do decyzji.
2. Etap 3: `meal_log_create` → nakładka na `intake_log_create` vs bez zapisu do legacy — ORAZ co zrobić z REST `/nutrition/meals` i importem Cronometer (przepiąć na intake czy wyłączyć).
3. sugar-type: zawęzić vs usunąć — bez zmian.
4. P1: sam prompt Alberta (Etap 1) czy od razu + deterministyczny tor (Opcja D)?
5. (zamknięte) endpoint ChatGPT — potwierdzony MCP `/mcp`.


---

## 9. Poprawki po audycie #2 (2026-07-05)

> Oryginał sekcji 1–8 zostaje nietknięty (ślad dla kolejnych audytów). Poniżej korekty po drugiej sesji kontrolnej. Wszystko sprawdzone na żywym kodzie tej sesji (grep na `/opt/qbot/app`), nie z pamięci.

### 9.1 Lista wołających `meal_log_create` NADAL niepełna (korekta 8.2)
`grep -rn meal_log_create /opt/qbot/app --include=*.py` → ok. 7 ŻYWYCH miejsc, nie 4. Poza tymi z 8.2 (2 REST) i CLI + martwym adapterem, do starego zeszyta piszą też:
- `qbot_nutrition_tools.py:130` (zapis posiłku) oraz `:456` (zapis z szablonu).
- `qbot_ask_cli.py:130` — DRUGIE CLI (poza `qbot_nutrition_cli.py`).
- `qbot/tools/import_intervals_nutrition_comments.py:108` — import komentarzy żywieniowych z intervals.icu.
- `qbot_nutrition_db.py:1093` — wewnętrzny self-call (np. „apply template").
Plus w `_bak_archive/` (do zignorowania, ale nie usuwać po cichu).
**Wniosek:** 8.2 poprawiło liczbę z 2 na 4, ale rzeczywistość to ~7. **Przed Etapem 3 OBOWIĄZKOWO pełny `grep` i decyzja per-caller dla KAŻDEGO** (przepiąć na `intake_log_create` / wygasić / zostawić świadomie). Szczególnie sprawdzić, czy `qbot_nutrition_tools.py` nie jest wpięte w jakikolwiek żywy front — patrz 9.2.

### 9.2 Root-cause: pominięty `write_router.py` + realny zapis w `agent_runtime` (uzupełnienie pkt 5–6)
Diagnoza (sekcje 5–6) wiesza całą „loterię" na sprzecznym prompcie `albert.py:185`. Sprawdzenie kodu pokazuje mechanizm dokładniej:
- `qbot3/agent_runtime.py:112–118` (`_execute_single_tool`) — dla `nutrition_log_add` (i pozostałych write-tools z whitelisty) ZAWSZE woła `_execute_real_write_tool` → realny zapis do `intake_logs`. Gałąź `WRITE_DRAFT` (`:120–132`) dotyczy TYLKO narzędzi spoza tej whitelisty. To samo w `_execute_tool_dedup` (`:228–232`) i w mapie celu (`:723` → `nutrition_log_add: (qbot_v2, intake_logs)`).
- Istnieje osobny moduł `qbot3/write_router.py` (importowany przez `agent_runtime:513, 873`: `extract_nutrition_slots`, `build_draft`) — dostarcza ekstraktory slotów i szablon draftu. **Spec nie wspominał go wcale**, choć dotyczy tematu WRITE_DRAFT.
**Skutek dla diagnozy:** pkt 6 (żywienie realnie zapisuje, nie draftuje) — POTWIERDZONY w kodzie, dobrze. ALE to znaczy, że skoro kod zawsze zapisuje po wywołaniu narzędzia, „draft/action_execute" może powstać **wyłącznie wtedy, gdy Albert w ogóle NIE wywoła narzędzia** i sam z siebie wyprodukuje tekst o draftcie (posłuszny regule 185). Spec nigdzie tego nie nazywa. Czyli diagnoza „sprzeczny prompt" jest prawdopodobna, ale **nieudowodniona** — Etap 0 (runtime) jest tu warunkiem koniecznym, nie formalnością.

### 9.3 „OK, a w raporcie pusto" to DWA różne objawy — rozdzielić w Etapie 0
Objaw z sekcji 1 zlewa dwa różne przypadki o różnym leczeniu:
- **(a) brak wiersza:** Albert nie wywołał narzędzia → nic nie trafiło do `intake_logs`. UX: dzień pusty.
- **(b) wiersz jest, ale Albert powiedział „draft":** zapis realnie poszedł (kod zawsze zapisuje — 9.2), lecz narracja Alberta twierdzi „to draft" → użytkownik dodaje drugi raz → **duplikat** (łagodzony przez `DUPLICATE_SKIPPED`, ale nie zawsze — inna data/nazwa ominie dedup).
**Etap 0 MUSI rozróżnić (a) od (b)** dla każdego uruchomienia (sprawdzać JEDNOCZEŚNIE: tekst odpowiedzi ORAZ realny stan `intake_logs` po wywołaniu). Bez tego nie wiadomo, którego objawu dotyczy „loteria" i czy Etap 1 go leczy.

### 9.4 Korekta 8.4 — Etap 1 NIE „domyka uczciwości", tylko redukuje ryzyko
Twierdzenie z 8.4 „najgorszy scenariusz (OK bez wiersza) znika już po Etapie 1" jest za mocne:
- Albert to LLM — poprawiony prompt zmniejsza szansę, że pominie wywołanie narzędzia, ale tego NIE gwarantuje. Dopóki żywienie idzie przez Alberta, przypadek (a) z 9.3 pozostaje możliwy (rzadszy, nie zerowy).
- **Luka w strażniku Telegram:** watchdog alarmuje o **pustym dniu**. Dzień z 3 z 4 posiłków (jeden cicho przepadł — częściowa utrata) NIE odpali alertu. Czyli sieć bezpieczeństwa nie łapie najbardziej podstępnego przypadku.
**Wniosek:** to realnie wzmacnia argument za Opcją D (9.5) — determinizm dla najczęstszego przypadku to nie tylko „hardening", ale jedyny sposób, by usunąć zależność od decyzji LLM. Osobno rozważyć rozszerzenie watchdoga: alert nie tylko na pusty dzień, ale i na „dzień znacząco poniżej normy / mniej wpisów niż zwykle".

### 9.5 Opcja D (z 8.3) — realna, ale spec pomija dwie pułapki
- **Kolejność w routingu:** write-regex w `mcp_adapter` (`_QBOT_QUERY_WRITE_RE`, `:112–115`) już przechwytuje frazy zapisu i eskaluje do Alberta PRZED handlerem deterministycznym (pkt 4). Opcja D musi wpiąć się **przed tą eskalacją**, inaczej i tak wyląduje u Alberta i cały zysk znika. To konkretna zależność implementacyjna do zapisania w planie.
- **Drugi parser = ryzyko rozjazdu:** Opcja D wprowadza NOWY parser kcal+makr obok tego, którego już używa tor żywienia (`extract_nutrition_slots` w `write_router.py`). Dwa parsery = ryzyko, że interpretują tę samą frazę różnie. Rekomendacja: Opcja D powinna **reużyć `extract_nutrition_slots`**, a nie pisać własny parser od zera.

### 9.6 Co zostaje solidne (bez zmian)
- 8.1 (endpoint = MCP `/mcp`) — dowody spójne, zamknięte.
- pkt 6 (żywienie realnie zapisuje do `intake_logs`, nie draftuje) — potwierdzony w kodzie (`agent_runtime:112–118, 723`).
- Kolejność „Etap 1 najpierw, potem Opcja D" — rozsądna; korekta tylko w randze Opcji D (9.4: konieczna dla najczęstszego przypadku, nie opcjonalna ozdoba).

### 9.7 Zaktualizowane otwarte decyzje (po audycie #2)
1. Etap 2: `resolved_food_entry` vs dane w `query` — bez zmian.
2. Etap 3: per-caller decyzja dla WSZYSTKICH ~7 wołających `meal_log_create` (9.1), nie tylko REST z 8.2.
3. sugar-type: zawęzić vs usunąć — bez zmian.
4. P1: prompt (Etap 1) sam, czy od razu + Opcja D reużywająca `extract_nutrition_slots` (9.5)?
5. Watchdog: rozszerzyć o alert „dzień poniżej normy / mniej wpisów niż zwykle" (9.4)?
6. (do potwierdzenia w Etapie 0) który objaw dominuje — (a) brak wiersza czy (b) wiersz + narracja draftu (9.3)?


---

## 10. Rozstrzygnięcia po audycie #2 (2026-07-05)

> Odpowiedź na sekcję 9. Wszystko zweryfikowane na żywym kodzie tej sesji.

- **9.1 PRZYJĘTE (i mocniej).** Wołających `meal_log_create` jest jeszcze więcej niż podał audyt: `qbot_nutrition_tools.py:130,456`, `qbot_ask_cli.py:130`, `qbot/tools/import_intervals_nutrition_comments.py:108`, `qbot_nutrition_db.py:1093` (self-call), `qbot_api.py:1036,1082` (REST), `qbot_mcp_adapter.py:965,1190,1770` (martwy), `qbot_nutrition_cli.py:151,754,1004`. **Przed Etapem 3 OBOWIĄZKOWO pełny `grep` + decyzja per-caller.** Zwłaszcza ustalić, czy `qbot_nutrition_tools.py` jest wpięte w jakikolwiek żywy front (jeśli tak — pisze do legacy poza Albertem).
- **9.2 PRZYJĘTE.** `write_router.py` potwierdzony: `extract_nutrition_slots:48`, `build_draft:590`. Dopisać do referencji specu. Sprostowanie do audytu: Etap 0 był OBOWIĄZKOWY już w v1 (nie „formalność") — ale audyt słusznie doostrza, że draft powstaje wyłącznie gdy Albert NIE wywoła narzędzia.
- **9.3 PRZYJĘTE.** Etap 0 musi dla każdego uruchomienia sprawdzać JEDNOCZEŚNIE: (1) tekst odpowiedzi Alberta, (2) realny stan `intake_logs` po wywołaniu — by rozróżnić (a) brak wiersza od (b) wiersz + narracja draftu → duplikat.
- **9.4 PRZYJĘTE — korekta mojego 8.4.** 8.4 było za mocne. Po Etapie 1 przypadek (a) „brak wiersza" pozostaje możliwy (rzadszy, nie zerowy — Albert to LLM). Dodatkowo: strażnik Telegram NIE łapie częściowej utraty (np. 3 z 4 posiłków), bo alarmuje tylko o pustym dniu. Konsekwencje: (i) Opcja D awansuje z „hardening" na **zalecaną dla najczęstszego przypadku**; (ii) nowa pozycja: rozszerzyć watchdog o alert „mniej wpisów/kcal niż zwykle / poniżej normy".
- **9.5 PRZYJĘTE.** Opcja D: (1) musi wpiąć się w routing PRZED eskalacją `_QBOT_QUERY_WRITE_RE`→Albert (`mcp_adapter:112–115,141–142`), inaczej i tak trafi do Alberta; (2) MUSI reużyć `write_router.extract_nutrition_slots`, nie tworzyć drugiego parsera.

### 10.1 Rekomendacja domyślna (do zatwierdzenia)
Wobec 9.4: **Etap 1 (prompt Alberta) + od razu Opcja D** (deterministyczny tor dla jawnych kcal+makr, reużywający `extract_nutrition_slots`, wpięty przed eskalacją). Sam Etap 1 nie daje pewności dla najczęstszego przypadku. Kolejność wdrożenia: Etap 0 (dowód) → Etap 1 → Opcja D → test → dopiero Etap 3 (zeszyty) → Etap 2 → plasterki.

### 10.2 Decyzje do podjęcia przez użytkownika (skonsolidowane)
1. **P1 zakres:** sam Etap 1, czy Etap 1 + Opcja D razem? (rekomendacja: razem)
2. **Watchdog:** dodać alert „poniżej normy/mniej wpisów"? (rekomendacja: tak — łata lukę 9.4)
3. **Etap 3 per-caller:** REST `/nutrition/meals` i import Cronometer oraz `qbot_nutrition_tools.py` — przepiąć na `intake_logs`, wygasić, czy zostawić świadomie?
4. **Etap 2 anafora:** czytać `resolved_food_entry` czy wymagać danych w `query`?
5. **sugar-type:** zawęzić czy usunąć?


---

## 11. Poprawki po audycie #3 (2026-07-05)

> Trzecia sesja kontrolna (audyt, bez wdrożeń). Sekcje 1–10 nietknięte (ślad audytowy). Wszystko zweryfikowane na żywym kodzie/bazie tej sesji (grep + odczyt w /opt/qbot/app + runtime `orchestrate_query`). ETAP 0 wykonany z datą testową 2019-01-01; wszystkie wpisy testowe posprzątane i zweryfikowane (intake_logs/intake_items/nutrition_daily_summary/meal_logs = 0 dla 2019-01-01).

### 11.A Potwierdzone (z dowodem)
- Routing `/mcp`: przy `QBOT3_ENABLED=1` POST `/mcp` → `handle_qbot3_mcp` (qbot3); legacy `handle_mcp_request` martwy. Dowód: `qbot_api.py:1388–1414`. ✓ (pkt 1–2)
- `_list_tools` wystawia TYLKO `qbot_query` (brak `action_execute`). Dowód: `qbot3/adapters/mcp_adapter.py:244–260`. ✓ (pkt 3)
- Eskalacja zapisu: `_QBOT_QUERY_WRITE_RE` (`mcp_adapter.py:112–115`) → `_classify_vnext_escalation`=`ACTION_REQUIRED` (`:141–142`), a w `_call_tool` `pre_escalation_reason` odpala PRZED handlerem deterministycznym (`:280–281`) → Albert. ✓ (pkt 4, 9.5(1))
- Albert `nutrition_log_add` realnie zapisuje do `intake_logs`, nie draftuje: whitelist `_execute_single_tool` (`agent_runtime.py:112–118`) i `_execute_tool_dedup` (`:228`) → `_execute_real_write_tool` (`:50–63`) → `_execute_nutrition_write` → `intake_log_create`; mapa celu `:723`=(qbot_v2, intake_logs). WRITE_DRAFT tylko poza whitelistą (`:120–122`). ✓ (pkt 6, 9.2)
- `_execute_nutrition_write` zwraca `write_committed`/`user_message`, ma `DUPLICATE_SKIPPED` (dedup 120 s, `mcp_adapter.py:467–495`) i weryfikację po zapisie. ✓ (pkt 6)
- ROOT CAUSE (sprzeczność promptu) ISTNIEJE tekstualnie: `albert.py:_SYSTEM:185` („Zapis danych → zwróć draft… wymaga qbot.action_execute") kontra reguły żywieniowe `:188–195` (zapis wprost, potwierdzaj po `write_committed`). ✓ (pkt 5) — ALE patrz 11.B.2/11.C.1: w runtime NIE zamienia się to na objaw.
- `resolved_food_entry` — 0 trafień w kodzie. ✓ (pkt 9)
- Sugar-type: `_validate_and_fix_meal_items` (`qbot_nutrition_db.py:302–311`) — substring-match słów cukrowych na CAŁEJ nazwie, zeruje białko/tłuszcz > 2 g. ✓ (pkt 7). DOPRECYZOWANIE zasięgu: reguła działa na OBU torach — wołana przez `meal_log_create` (`:176`) ORAZ `intake_log_create` (`:414`). Dotyczy więc też toru Alberta/`intake_logs` (ChatGPT/MCP), nie tylko legacy. Obok istnieje check spójności kcal↔makra (`:313–332`).
- Dual-write w `meal_log_create`: mirror do `intake_logs` w `try/except: pass` (blok ~`:242–271`, „v2 zapis nigdy nie blokuje v1"). ✓ (pkt 8). DODATKOWO: mirror wpisuje na sztywno `source='chatgpt_mcp'` dla KAŻDEGO wołającego → audyt „skąd wpisy" po `source` jest zafałszowany (Telegram/CLI/REST też oznaczone jako chatgpt_mcp).
- Pełna lista wołających `meal_log_create`/`meal_log_delete` zgadza się z sekcją 10 (grep całego repo; `_bak_archive` pominięte). ✓ (9.1/10)
- `write_router.extract_nutrition_slots` istnieje (`write_router.py:48`). ✓ (9.2)
- Strażnik: `nutrition_watchdog.py` alarmuje TYLKO gdy `n == 0` (`build_message:63–66`, `_day_stats:44–54`). Częściowa utrata (3 z 4) → brak alertu. ✓ (9.4/10 pkt 9.4)

### 11.B Obalone / nieścisłe (z dowodem)
1. **„`qbot_mcp_adapter.py` = martwy" — NIEPRAWDA.** `_handle_nutrition_add` (`qbot_mcp_adapter.py:897`, wołanie `meal_log_create` na `:965` → legacy) jest importowana i wołana ŻYWO przez tor Telegrama: `qbot_qcal_telegram.py:417–418` (`_execute_writer` dla `nutrition_log_add`). Sekcja 2 pkt 8 oraz sekcja 10 pkt 9.1 („qbot_mcp_adapter.py:965,… (martwy)") są w tym punkcie błędne — linia 965 leży na żywym torze.
2. **„Loteria draft/action_execute = dominujący objaw" — NIEPOTWIERDZONA w runtime.** ETAP 0: 6× `orchestrate_query(..., context='{"source":"chatgpt"}')`, data 2019-01-01, jawne makra. Wynik: 0/6 draft/action_execute (`action_draft=False` za każdym razem), 5/6 realny zapis + uczciwe „✅ Zapisano", 0 fałszywego „zapisano bez wiersza". Reguły 188–195 w praktyce wygrywają z regułą 185. Sprzeczność promptu (pkt 5) jest realna tekstualnie, ale na HEAD nie manifestuje się jako objaw dla jawnych dodań. Etap 1 pozostaje sensowną higieną (usunąć martwą regułę 185 i wzmiankę o nieistniejącym action_execute), ale NIE leczy obserwowanej awarii (11.C.1).
3. **8.1 „konektor MCP nie strzeli do REST" — prawda, ale niepełne jako argument o zasięgu.** CONTEXT.md (kanon) opisuje `qbot_mcp_adapter+qbot_query_router` jako routing „innych frontów (ChatGPT/Telegram)". Ten router ma żywą intencję zapisu do legacy (11.C.2). Teza specu, że jedyny tor zapisu to `/mcp`→Albert→`intake_logs`, jest zawężona.

### 11.C Nowo znalezione (przeoczone przez #1 i #2)
1. **[NAJWAŻNIEJSZE] Realna, powtarzalna awaria zapisu = asymetria weryfikacji `daily_summary` (get vs compute), NIE prompt.** ETAP 0 RUN 1 (pierwszy zapis dnia): `status=OK, row_created=False`, odpowiedź „❌ NIE zapisano poprawnie: daily_summary missing inserted kcal: before=1821.0, expected_delta=301.0, after=301.0" — mimo że 2019-01-01 miał 0 wierszy. Mechanizm (`mcp_adapter.py`): `before_summary = daily_summary_get(target_date)` (`:541`, ZCACHE'OWANY wiersz `nutrition_daily_summary`) vs `after_summary = daily_summary_compute(target_date)` (`:609`, ŚWIEŻE przeliczenie). Warunek `after_kcal < before_kcal + expected_kcal - 0.1` (`:611`) odrzuca zapis, świeżo wstawiony wiersz jest KASOWANY (`:650–657`), status `WRITE_INCONSISTENT`, `write_committed=False`. Gdy zcache'owany `before` jest niespójnie WYŻSZY niż realny stan, PIERWSZY zapis danego dnia zawsze pada i „jedzenie znika". To odtwarza zgłoszony objaw „dodaję posiłek, a w raporcie pusto/błąd", który spec przypisuje promptowi. DODATKOWO `daily_summary_compute` sumuje ZARÓWNO `intake_items` JAK I legacy `meal_log_items` (`qbot_nutrition_db.py:583,596`), więc niespójność stary/nowy zeszyt bezpośrednio zasila ten błąd. (Stały wiersz 1821 dla 2019-01-01 istniał przed sesją — z wcześniejszych testów; posprzątany.)
2. **Żywy tor zapisu do legacy `meal_logs`, którego spec nie wymienia: Telegram → `qbot_query_router`.** `qbot_qcal_telegram.handle_message` woła `qbot_tools._tool_qbot_query` (`:~562`) → `qbot_query_router.query` (`qbot_tools.py:763`). Router ma żywą intencję `nutrition_log_add_draft` → `action_draft` typu `nutrition_log_add` (`qbot_query_router.py:122,3217–3223,3489–3523`). Draft → potwierdzenie Telegram (`_pending_execute`→`_execute_writer`, `:305,416–418`) → `_handle_nutrition_add` → `meal_log_create` (legacy). Odrębny silnik zapytań (nie qbot3). Etap 3 MUSI go objąć, inaczej Telegram dalej sieje do `meal_logs`.
3. **Opcja D ma nierozwiązaną lukę parsera — rekomendacja 10.1/10.2 w tej formie niewykonalna.** Runtime: `extract_nutrition_slots("...485 kcal, B14 W77 T14")` = `{"kcal_total": 485.0}` — makra B/W/T ZGUBIONE (brak wzorca na skrót „B/W/T" w `write_router.py:64–83`; tylko formy długie „białko 14 g" itd.). `_execute_nutrition_write` czyta STRUKTURALNE `protein_g/carbs_g/fat_g` z payloadu (`mcp_adapter.py:521–536`) — dziś skrót B/W/T na te pola tłumaczy ALBERT (LLM). Opcja D (deterministyczna, z pominięciem Alberta, reużywająca `extract_nutrition_slots`) dla flagowej frazy zapisałaby kcal, ale makra=0/null → ODTWORZYŁABY objaw „makra jako 0". Wniosek: albo rozszerzyć `extract_nutrition_slots` o B/W/T (to NOWY parser — sprzeczne z „reużyj, nie pisz nowego"), albo porzucić Opcję D. W obecnym kształcie NIEGOTOWA.
4. **Dodatkowe żywe endpointy REST do legacy (poza 8.2):** `/nutrition/intake/text` (`qbot_api.py:978`) i `/nutrition/intake/telegram` (`:998`) → `_tool_qbot_nutrition_intake_log` (`qbot_api.py:992` → `qbot_nutrition_tools.py:92→130` → `meal_log_create`). Do listy z 8.2 (`/nutrition/meals`, import Cronometer) dochodzą te dwa.
5. **`qbot_nutrition_tools._tool_qbot_nutrition_intake_log` jest żywe, ale NIE na torze Alberta.** Jest `wrapped` narzędzia `nutrition_log_add` w rejestrze (`qbot3/tool_registry.py:2207–2220`), lecz Albert je POMIJA — `_execute_real_write_tool` woła `_execute_nutrition_write` bezpośrednio (`agent_runtime.py:50–63`). `wrapped` (→ legacy `meal_log_create`) jest MYLĄCE, ale dla Alberta nieaktywne. Żywe użycie `_tool_qbot_nutrition_intake_log` = endpointy REST z 11.C.4. (Odpowiedź na pytanie audytu „czy qbot_nutrition_tools wpięte w żywy front": TAK — przez REST, nie przez Albert.)

### 11.D Ocena decyzji z 10.2 i rekomendacji 10.1
1. **P1 zakres (rec: Etap 1 + Opcja D razem):** WĄTPLIWE po ETAPIE 0. Draft-loteria nie odtworzyła się (11.B.2); realna awaria to błąd weryfikacji sumy (11.C.1). Etap 1 — TAK (higiena promptu). Opcja D — NIE „od razu": zablokowana luką parsera B/W/T (11.C.3), słabiej uzasadniona. Najpierw 11.C.1.
2. **Watchdog poniżej normy (rec: tak):** TRAFNE — luka potwierdzona. Niezależne, wdrażać.
3. **Etap 3 per-caller (rec: przepiąć/wygasić):** NIEPEŁNE — lista pomija Telegram→`qbot_query_router`→`_handle_nutrition_add` (11.C.2) i `/nutrition/intake/*` (11.C.4). Uzupełnić o KAŻDY tor z 11.C.2/4/5.
4. **Etap 2 anafora (rec: b lub a):** OK; zmyślony `resolved_food_entry` potwierdzony. Bez nowych blokerów (przez Alberta B/W/T działa).
5. **sugar-type (rec: zawęzić/usunąć):** OK; „usunąć" bezpieczne, bo check spójności kcal↔makra (`:313–332`) zostaje. Naprawa poprawia też tor `intake_logs` (11.A).
- **Kolejność 10.1 wymaga rewizji:** 11.C.1 (utrata jedzenia) > Etap 1. Propozycja: [11.C.1 fix] → Etap 1 → Etap 3 z pełną listą torów → [parser B/W/T, jeśli Opcja D] → Etap 2 → plasterki.

### 11.E Werdykt
**Spec NIE jest gotowy do wdrożenia Etapu 0→1 w obecnej formie.** ETAP 0 wykonany i UNIEWAŻNIA główną diagnozę: dominującym powtarzalnym objawem NIE jest draft-loteria z promptu, lecz błąd weryfikacji `daily_summary` (get vs compute, 11.C.1). Przed wdrożeniem:
1. Dopisać do specu i naprawić 11.C.1 (ujednolicić `before`/`after` na to samo źródło — oba `compute`, albo `_get` po recompute; nie mieszać cache z recompute).
2. Poprawić klasyfikację torów: `_handle_nutrition_add` żywy (11.B.1), Telegram→router żywy (11.C.2), REST intake (11.C.4), `wrapped` mylące (11.C.5).
3. Rozstrzygnąć Opcję D wobec luki B/W/T (11.C.3) — bez tego nie wdrażać.
Etap 1 (sam prompt) można wdrożyć jako higienę niezależnie (niskie ryzyko), ale nie rozwiązuje realnej awarii.

### 11.F Zaktualizowana lista otwartych decyzji
1. [NOWE, priorytet] 11.C.1: jak ujednolicić weryfikację sumy — `before`=compute (nie get), czy zamienić twardy warunek `after<before+delta` na sprawdzenie obecności wstawionego wiersza?
2. P1: sam Etap 1 (higiena promptu), bez Opcji D dopóki luka B/W/T nierozwiązana.
3. Opcja D: rozszerzyć `extract_nutrition_slots` o skrót B/W/T (nowy parser) czy porzucić Opcję D?
4. Etap 3: decyzja per-caller dla PEŁNEJ listy, w tym Telegram→`_handle_nutrition_add` i `/nutrition/intake/*`.
5. Watchdog: dodać alert „poniżej normy/mniej wpisów".
6. Etap 2 anafora: `resolved_food_entry` vs dane w query.
7. sugar-type: zawęzić czy usunąć (rec: usunąć).
8. Provenance: naprawić sztywne `source='chatgpt_mcp'` w mirror `meal_log_create` — inaczej audyty „skąd wpisy" mylą.


---

## 12. Rozstrzygnięcia po audycie #3 (2026-07-05)

> Odpowiedź na sekcję 11. Kluczowe twierdzenia #3 zweryfikowane niezależnie na żywym kodzie tej sesji.

- **11.C.1 PRZYJĘTE — to jest realne P1.** Potwierdzone: `before_summary=daily_summary_get` (cache, `mcp_adapter.py:541`) vs `after_summary=daily_summary_compute` (świeże, `:609`); warunek `:611` odrzuca i kasuje wstawiony wiersz (`~:650`). Gdy cache jest nieaktualnie wyższy niż realność → pierwszy zapis dnia pada („jedzenie znika"). Autor tego specu wcześniej w sesji trafił na ten sam objaw (before=500 na 2020-01-01) i BŁĘDNIE zbył go jako „brudna data" — audyt #3 poprawnie zidentyfikował bug. 
- **Potwierdzone dodatkowo:** `daily_summary_compute` sumuje OBA zeszyty — `intake_items` (`qbot_nutrition_db.py:583`) i `meal_log_items` (`:596`). Więc niespójność stary/nowy zeszyt bezpośrednio zasila 11.C.1.
- **11.B.1 PRZYJĘTE — korekta specu i audytów #1/#2.** `qbot_mcp_adapter._handle_nutrition_add` jest ŻYWY przez Telegram: `qbot_qcal_telegram.py:417–418` → `meal_log_create` (legacy). Określenie „martwy adapter" było błędne. Etap 3 musi objąć tor Telegrama.
- **11.C.2 / 11.C.4 PRZYJĘTE.** Żywe tory zapisu do legacy poza `/mcp`: Telegram→`qbot_query_router`→`_handle_nutrition_add`; REST `/nutrition/intake/text` i `/nutrition/intake/telegram`. Pełna lista torów do rozstrzygnięcia w Etapie 3.
- **11.C.3 PRZYJĘTE.** Opcja D w obecnej formie NIEGOTOWA (parser gubi skrót B/W/T). Nie wdrażać, dopóki nie rozstrzygnięte (rozszerzyć parser vs porzucić Opcję D).
- **Sprostowanie do #3 (krytycznie):** teza „Etap 0 unieważnia diagnozę promptu" jest za mocna. Draft nie odtworzył się w 6 próbach, ale raport z ChatGPT (placek) realnie pokazał odpowiedź „to draft, użyj action_execute". Oba tryby są realne; 11.C.1 jest nowo znaleziony i prawdopodobnie częstszy, prompt jest wtórny/sporadyczny. Etap 1 zostaje jako tania higiena, nie jako główna naprawa.

### 12.1 Zrewidowana kolejność (zastępuje 10.1)
1. **Etap 0** — dowód runtime (WYKONANY w #3; do powtórzenia po każdej zmianie).
2. **P1 = naprawa 11.C.1** (weryfikacja `daily_summary`): ujednolicić źródło `before`/`after` (oba `compute`) LUB zamienić warunek delty kcal na sprawdzenie OBECNOŚCI wstawionego wiersza po id (rekomendacja: sprawdzenie obecności wiersza — odporne na sum-z-dwóch-zeszytów). NIE kasować wiersza, gdy sam insert się powiódł.
3. **Etap 1** — higiena promptu Alberta (usunąć regułę 185 + wzmiankę o nieistniejącym action_execute). Niskie ryzyko, niezależne.
4. **Watchdog** — alert „poniżej normy/mniej wpisów" (łata lukę 9.4; niezależne).
5. **Etap 3** — jeden zeszyt; per-caller dla PEŁNEJ listy torów (qbot3 intake, CLI x2, REST /nutrition/meals + /nutrition/intake/* + Cronometer, Telegram→_handle_nutrition_add, qbot_nutrition_tools, self-call). To ostatecznie usuwa źródło niespójności zasilającej 11.C.1.
6. **plasterki:** sugar-type (usunąć; działa na obu torach — patrz 11.A), sierota `meal_logs` id=16.
7. **Opcja D / Etap 2** — dopiero po rozstrzygnięciu parsera B/W/T i anafory.

### 12.2 Otwarte decyzje (skonsolidowane, po #3)
1. **[P1] 11.C.1:** `before`=compute, czy warunek→sprawdzenie obecności wiersza? (rec: obecność wiersza)
2. Etap 3: per-caller dla PEŁNEJ listy torów (w tym Telegram, REST intake) — przepiąć/wygasić.
3. Opcja D: rozszerzyć `extract_nutrition_slots` o B/W/T czy porzucić?
4. Watchdog: alert „poniżej normy" — tak/nie.
5. Etap 2 anafora: `resolved_food_entry` vs dane w query.
6. sugar-type: usunąć (rec) czy zawęzić.
7. Provenance: naprawić sztywne `source='chatgpt_mcp'` w mirror `meal_log_create` (11.A).

### 12.3 Werdykt
Zgadzam się z #3: **spec NIE był gotowy** — brakowało realnej przyczyny (11.C.1). Po tej sekcji plan jest spójny: najpierw 11.C.1 (zweryfikowana awaria), potem higiena promptu, watchdog, ujednolicenie zeszytów, plasterki; Opcja D/anafora na końcu, warunkowo.


---

## 13. Poprawki po audycie #4 (2026-07-05)

> Czwarta sesja kontrolna (audyt, BEZ wdrożeń). Sekcje 1–12 nietknięte (ślad audytowy).
> Wszystko zweryfikowane na żywym kodzie/runtime tej sesji: grep + odczyt w `/opt/qbot/app`
> + runtime bezpośredniego wywołania `_execute_nutrition_write` (HEAD). Data testowa
> **2018-01-01** (odległa przeszłość); wszystkie wpisy testowe posprzątane i czystość
> zweryfikowana na końcu (intake_logs/intake_items/meal_logs/nutrition_daily_summary/nutrition_write_audit = 0).

### 13.A Potwierdzone (z dowodem)
- **11.C.1 awaria ODTWORZONA na żywo (runtime).** Ustawiłem zawyżony cache `source='qbot'`=5000 kcal dla 2018-01-01 (0 realnych wierszy), potem `_execute_nutrition_write("nutrition_log_add", {kcal_total:300...})`. Wynik: `status=WRITE_INCONSISTENT`, `write_committed=False`, `db_inserted=True`, `cleanup_performed=True`, po zapisie `intake_logs=0`. Komunikat: „daily_summary missing inserted kcal: before=5000.0, expected_delta=300.0, after=300.0". To dokładnie „jedzenie znika". Potwierdza #3.
- **Mechanizm weryfikacji** (`qbot3/adapters/mcp_adapter.py`): `:541` `before=daily_summary_get` (cache), `:609` `after=daily_summary_compute` (świeże), `:611` warunek `after<before+expected-0.1`, `:650` kasowanie wstawionego wiersza gdy `verification_error`. ✓
- **Cache `source='qbot'` w żywym torze pisze wyłącznie `daily_summary_compute`** (`qbot_nutrition_db.py:627`, INSERT ... ON CONFLICT (date,source) DO UPDATE, VALUES 'qbot'). `daily_summary_get` (`:650`) czyta tylko `source='qbot'` i NIGDY nie przelicza. ✓
- **11.B.1 potwierdzone niezależnie:** Telegram→`_handle_nutrition_add` (`qbot_mcp_adapter.py:965`) żywy przez `qbot_qcal_telegram._execute_writer:416–418`. ✓
- **QBOT3_ENABLED=1 ORAZ QBOT_QUERY_VNEXT_ENABLED=1 na żywo** (odczyt runtime przez `qbot_config`). Więc POST `/mcp`→`handle_qbot3_mcp` (`qbot_api.py:1404`), a `handle_mcp_request` (`:1413`) jest martwy. ✓
- **Żywe tory REST intake (11.C.4):** `/nutrition/intake/text` i `/nutrition/intake/telegram` → `_tool_qbot_nutrition_intake_log` → `meal_log_create` (legacy). ✓

### 13.B Obalone / nieścisłe (z dowodem) — kluczowe dla priorytetu 1
1. **„`daily_summary_compute` sumuje OBA zeszyty (intake_items + meal_log_items)" — NIEPRAWDA.** To IF/ELSE (albo-albo), nie suma. Dowód: `qbot_nutrition_db.py:571` liczy `intake_count`; `:575` `if intake_count:` → `:577` sumuje TYLKO `intake_items`; `:590` `else:` → sumuje TYLKO `meal_log_items`. Cytowane w 11.C.1 i przyjęte w 12 linie `:583`/`:596` leżą w DWÓCH WYKLUCZAJĄCYCH SIĘ gałęziach — nigdy nie działają razem. Skutek: prawdziwy mechanizm 11.C.1 to NIE „mieszanie zeszytów w jednej sumie", lecz **przełączenie regime**: `before`=cache policzony gdy dzień miał tylko legacy (meal_log) vs `after`=świeży compute, który po pierwszym insertcie intake liczy JUŻ TYLKO intake → legacy „znika" z sumy, więc `after<before`. Runtime KROK2 to potwierdza (before=5000, after=300 mimo poprawnego insertu). Wniosek praktyczny: uzasadnienie z 12.2 „obecność wiersza — odporne na sum-z-dwóch-zeszytów" opiera się na błędnym opisie; problemem nie jest suma dwóch zeszytów, tylko porównywanie dwóch wartości liczonych w różnych regime.
2. **8.2: `/nutrition/import/cronometer/servings-csv` jako writer legacy `meal_logs` — NIEPRAWDA.** Endpoint (`qbot_api.py:1082`) importuje `meal_log_create`, ale go NIE wywołuje; w pętli woła wyłącznie `food_item_create` (tabela `food_items`). To NIE jest tor zapisu do `meal_logs`. (Realny import Cronometer do summary jest osobno w `qbot_calendar_core` branch `cronometer`, `:1181`, `source='cronometer_import'` — inny wiersz, nieczytany przez `daily_summary_get`.) Przeoczone przez #1–#3.
3. **Ranga „martwy" dla `qbot_mcp_adapter:1190/1770` — SŁUSZNA.** `_handle_nutrition_replace` (1190) i `_action_exec_nutrition` (1770) są osiągalne tylko przez `handle_mcp_request`, który przy QBOT3_ENABLED=1 jest martwy. Telegram `_execute_writer` mapuje z żywienia wyłącznie `nutrition_log_add`→`_handle_nutrition_add`. Więc korekta 11.B.1 (żywy tylko 965) jest KOMPLETNA — nie ma dodatkowego żywego toru legacy poza już wymienionymi.

### 13.C Nowo znalezione — ŹRÓDŁO niespójności cache (priorytet 1)
1. **Zawyżony `before` ma trzy niezależne, realne przyczyny (żadnej #3 nie zbadał):**
   - **(i) `meal_log_delete` (`qbot_nutrition_db.py:490`) NIE przelicza cache** — funkcja kończy się na `conn.commit()` bez `daily_summary_compute`. Kasowanie posiłku przez CLI/legacy zostawia cache źle-wysoki. To bezpośrednie źródło „zawyżenia".
   - **(ii) Przełączenie regime w `compute`** (13.B.1) — cache policzony z legacy jest wyższy niż świeży compute liczony z samego intake po pierwszym insertcie.
   - **(iii) Bezpośrednie UPDATE cache w torze ChatGPT** (`_action_exec_nutrition_delete/correct`, `qbot_mcp_adapter.py:1691,1739`) używają `WHERE date=%s` BEZ filtra `source` — mogą nadpisać wiersze innych źródeł, liczą tylko z `intake_items`. Tor martwy przy QBOT3_ENABLED=1, ale latentny (do sprzątnięcia razem z Etapem 3).
   **Wniosek:** naprawa 11.C.1 na poziomie weryfikacji zatrzyma „jedzenie znika" przy ZAPISIE, ale cache `source='qbot'` pozostanie zły dla ODCZYTU (raporty, daily summary, watchdog) dopóki: (a) nie ujednolici się `compute` (koniec albo-albo — najczyściej PO Etapie 3, jeden zeszyt), ORAZ (b) każdy tor mutacji nie przeliczy cache (zwłaszcza `meal_log_delete`). Czyli sam P1 to leczenie objawu przy zapisie; źródło (pkt 1) trzeba domknąć osobno, inaczej odczyty dalej kłamią.
2. **Importy calendar_core NIE zawyżają odczytywanego cache.** `daily_summary_get` czyta tylko `source='qbot'`; importy piszą `source='cronometer_import'`/`'intervals_comment_import'` z `ON CONFLICT DO NOTHING`. Wyklucza je jako źródło błędu — zawężenie względem podejrzeń.

### 13.D Ocena naprawy P1 (12.1/12.2 „obecność wiersza") + wariant bezpieczniejszy
Co chronił stary warunek `after<before+expected`: (a) insert „udany" ale itemy kcal=0/null; (b) częściowy insert; (c) wiersz niewidoczny dla compute. Robił to jednak porównując cache (`before`) do świeżego compute (`after`) — dwa różne regime → FAŁSZYWE ODRZUCENIA (to jest 11.C.1).
Runtime (KROK3 / KROK3b, data 2018-01-01, cache=5000):
- **Stary warunek:** odrzuca poprawny insert 300 (`False`). ZŁE (11.C.1).
- **Naprawa A (obecność wiersza po id + w liście):** przepuszcza poprawny insert (dobrze), ALE przepuszcza też insert z itemami kcal=0 (KROK3b: `True`) → PRZYWRACA objaw „makra/kcal jako 0", który stary warunek częściowo łapał. To realna LUKA, nie teoria.
- **Naprawa B (kcal WSTAWIONEGO wiersza po id, `SUM(intake_items.kcal WHERE intake_log_id=meal_id) > 0` / ≈ expected):** przepuszcza poprawny insert; POPRAWNIE odrzuca pusty insert (KROK3b: `False`). Odporna na zawyżony cache (nie czyta cache) i na albo-albo (nie liczy sumy dnia).
**Rekomendacja P1 = wariant B (najbezpieczniejszy).** Weryfikować po **id wstawionego wiersza**, nie po sumie dnia i nie po samej obecności:
  1. wiersz istnieje (`SELECT 1 FROM intake_logs WHERE id=meal_id`) — jest już w kodzie jako `meal_log_list` membership check,
  2. `SUM(intake_items.kcal WHERE intake_log_id=meal_id)` zgodne z `expected_kcal` w tolerancji (np. ±0.1 lub gdy `expected_kcal>0` wymagać sumy `>0`),
  3. zostawić istniejący `public_v1_count` (kontrola przypadkowego zapisu do legacy) — jest ortogonalny i dobry.
  Usunąć porównanie `after` vs `before` (`daily_summary_get`/`compute`) z gałęzi weryfikacji — to jedyne źródło 11.C.1.

### 13.E Ocena sprostowania z sekcji 12 do audytu #3 („oba tryby realne")
Sprostowanie 12 (że #3 „za mocno" mówi, iż prompt nieważny; draft realny wg raportu ChatGPT, 11.C.1 realny i częstszy, prompt wtórny) jest **SŁUSZNE, nie naciągane**:
- 11.B.2 (0/6 draft) to MAŁA próba na jednym kształcie wejścia (jawne makra, `source=chatgpt`, bezpośredni `orchestrate_query`). Pokazuje, że draft-loteria nie dominuje dla tego kształtu na HEAD — ale NIE dowodzi, że nie zdarza się nigdy. Sprzeczność promptu (`albert.py:185` vs `:188–195`) jest realna tekstualnie (11.A), a LLM przy innym sformułowaniu/kontekście dalej może posłuchać reguły 185. Raport „placek" z ChatGPT to realny dowód, że tor draftu zadziałał ≥1 raz.
- Doostrzenie audytu #4: pod „objawem" z sekcji 1 kryją się co najmniej TRZY niezależne przyczyny, nie dwie: (1) 11.C.1 (weryfikacja/cache), (2) draft z promptu (sporadyczny), (3) **zerowanie makr/kcal** przez `_validate_and_fix_meal_items` (sugar-type substring + skalowanie spójności, `qbot_nutrition_db.py:302–332`) — działa na OBU torach (11.A) i daje „makra jako 0" niezależnie od (1) i (2). 12 słusznie stawia prompt jako wtórny; #4 dodaje, że objaw „zera" to osobna, trzecia przyczyna.

### 13.F Werdykt
- **P1 (naprawa 11.C.1) jest gotowa do wdrożenia — ale w wariancie B, nie w wariancie „obecność wiersza" z 12.2.** Wariant „obecność wiersza" naprawia 11.C.1, lecz otwiera lukę na puste/zerowe inserty (dowód runtime KROK3b). Wariant B (weryfikacja kcal WSTAWIONEGO wiersza po id) naprawia 11.C.1 i zachowuje ochronę przed pustym insertem.
- **Źródło cache (pkt 13.C.1) trzeba domknąć osobno.** Sam P1 zatrzymuje „jedzenie znika" przy zapisie, ale nie naprawia zawyżonego/zdezaktualizowanego cache dla ODCZYTÓW. Minimalny hotfix: dołożyć `daily_summary_compute` na końcu `meal_log_delete`. Docelowo: ujednolicić `compute` (koniec albo-albo) po Etapie 3 (jeden zeszyt).
- Kolejność rewizji (zastępuje 12.1 w części P1): [P1 = wariant B] → hotfix recompute w `meal_log_delete` → Etap 1 (higiena promptu) → watchdog „poniżej normy" → Etap 3 (jeden zeszyt, który usuwa albo-albo) → plasterki (sugar-type — patrz 13.E pkt 3) → Opcja D/anafora warunkowo.

### 13.G Zaktualizowana lista otwartych decyzji (po #4)
1. **[P1, ZMIANA] 11.C.1:** przyjąć **wariant B** (kcal wstawionego wiersza po id), NIE „obecność wiersza" — ta ostatnia przepuszcza puste inserty (dowód runtime).
2. **[NOWE] Hotfix cache:** dołożyć `daily_summary_compute` na końcu `meal_log_delete` (`qbot_nutrition_db.py:490`) — dziś kasowanie legacy nie przelicza cache.
3. **[NOWE] compute albo-albo:** zdecydować, czy `daily_summary_compute` po Etapie 3 ma liczyć wyłącznie z `intake_items` (jeden zeszyt), usuwając gałąź `else` na `meal_log_items` — to eliminuje przełączenie regime (13.B.1).
4. **[KOREKTA 8.2]** wykreślić `/nutrition/import/cronometer/servings-csv` z listy torów legacy `meal_logs` (nie pisze do meal_logs — 13.B.2).
5. **[NOWE, latentne]** `_action_exec_nutrition_delete/correct` UPDATE bez filtra `source` (`qbot_mcp_adapter.py:1691,1739`) — do naprawy/sprzątnięcia razem z Etapem 3 (tor martwy, ale nadpisuje cudze wiersze summary).
6. Etap 1 (higiena promptu): bez zmian — tania, niezależna.
7. sugar-type/zerowanie makr (13.E pkt 3): potwierdzone jako OSOBNA (trzecia) przyczyna objawu — utrzymać rekomendację „usunąć" (check spójności zostaje).
8. Opcja D: bez zmian — niegotowa dopóki luka B/W/T nierozwiązana (11.C.3).


---

## 14. Rozstrzygnięcia po audycie #4 (2026-07-05) — plan FINALNY

> Odpowiedź na sekcję 13. Kluczowe korekty #4 zweryfikowane niezależnie na żywym kodzie. Audyt #4 skorygował dwa błędy z sekcji 8/12 — przyjęte.

### 14.1 Przyjęte korekty (audyt #4 miał rację)
- **`daily_summary_compute` to IF/ELSE, nie suma obu zeszytów.** Potwierdzone: `qbot_nutrition_db.py:571` count intake → `:575 if` sumuje tylko `intake_items` / `:588 else` sumuje tylko `meal_log_items`. Sekcja 12 („sumuje oba") BŁĘDNA — niniejszym skorygowana. Prawdziwy mechanizm 11.C.1 = **przełączenie regime** (before=cache ze starego zeszyta, after=świeży compute z nowego po pierwszym insertcie → legacy „znika" z sumy → after<before).
- **Import Cronometer NIE pisze do `meal_logs`.** `qbot_api.py:1082` importuje `meal_log_create`, ale w pętli woła tylko `food_item_create` (`:1107`). Wykreślić z listy torów legacy (korekta 8.2).
- **`meal_log_delete` NIE przelicza cache.** `:496–505` kończy na commit bez `daily_summary_compute` → kasowanie legacy zostawia cache zawyżony. Źródło „zawyżonego before".

### 14.2 P1 = WARIANT B (finalny kształt naprawy 11.C.1)
Zastępuje rekomendację „obecność wiersza" z 12.2 (ta przepuszcza puste inserty — dowód runtime #4). W `_execute_nutrition_write` (`mcp_adapter.py`):
- USUNĄĆ z gałęzi weryfikacji porównanie `after` vs `before` (`daily_summary_get` vs `daily_summary_compute`, `:541/:609/:611`).
- W ZAMIAN weryfikować WSTAWIONY wiersz po id:
  1. wiersz istnieje: `SELECT 1 FROM qbot_v2.intake_logs WHERE id=meal_id` (membership check już jest),
  2. `SELECT COALESCE(SUM(kcal),0) FROM qbot_v2.intake_items WHERE intake_log_id=meal_id` zgodne z `expected_kcal` w tolerancji (gdy `expected_kcal>0` wymagać sumy `>0`; przy podanych makrach opcjonalnie sprawdzić też >0 dla B/W/T jeśli podane),
  3. zostawić istniejący `public_v1_count` (kontrola przypadkowego zapisu do legacy) — ortogonalny.
- `daily_summary_compute(target_date)` nadal wołać (żeby cache był świeży po zapisie) i użyć wyniku TYLKO do komunikatu `user_message`, NIE do decyzji o odrzuceniu/kasowaniu.
- Efekt: poprawny zapis nie jest kasowany przez rozjazd cache; pusty/zerowy insert dalej odrzucany.

### 14.3 Hotfix źródła cache
Dołożyć `daily_summary_compute(<data usuwanego posiłku>)` na końcu `meal_log_delete` (`qbot_nutrition_db.py:496–505`), przed/po commit. Bez tego cache pozostaje zawyżony dla ODCZYTÓW (raporty, watchdog) nawet po naprawie P1. Uwaga: `meal_log_delete` dostaje `meal_id` — trzeba pobrać datę usuwanego wpisu (jest w `get_meal_log` na `:499`).

### 14.4 Objaw ma TRZY niezależne przyczyny (potwierdzone)
1. 11.C.1 — weryfikacja/cache (P1, wariant B). Najczęstsza, zweryfikowana runtime.
2. Prompt draft (`albert.py:185`) — sporadyczny (0/6 w #3, ale realny wg raportu ChatGPT). Etap 1 = higiena.
3. Zerowanie makr — `_validate_and_fix_meal_items` sugar-type substring + skalowanie (`qbot_nutrition_db.py:302–332`), działa na OBU torach. Plasterek „usunąć sugar-type" (check spójności zostaje).

### 14.5 Kolejność FINALNA (zastępuje 12.1 i 13.F)
1. **P1 = wariant B** (naprawa weryfikacji 11.C.1) → test runtime (odtworzyć 11.C.1: przed = kasuje, po = zostawia; + pusty insert dalej odrzucany).
2. **Hotfix** recompute w `meal_log_delete`.
3. **Etap 1** — higiena promptu Alberta (usunąć regułę 185 + wzmiankę o nieistniejącym action_execute).
4. **Watchdog** — alert „poniżej normy/mniej wpisów".
5. **Etap 3** — jeden zeszyt; przy okazji likwiduje przełączenie regime (koniec albo-albo w compute) i obejmuje WSZYSTKIE żywe tory (qbot3 intake, CLI x2, REST /nutrition/meals + /nutrition/intake/*, Telegram→_handle_nutrition_add, qbot_nutrition_tools, self-call; NIE Cronometer-CSV — 14.1). Naprawić też UPDATE bez `source` w `_action_exec_nutrition_delete/correct` (latentne).
6. **Plasterki** — sugar-type (usunąć), sierota `meal_logs` id=16, provenance `source='chatgpt_mcp'` w mirror.
7. **Opcja D / Etap 2** — warunkowo, po rozstrzygnięciu parsera B/W/T i anafory.

### 14.6 Werdykt
Pętla audytowa (4 rundy) **zamknięta**. Spec jest GOTOWY do wdrożenia: **P1 (wariant B) + hotfix `meal_log_delete`** to zweryfikowana, wąska, najwyższa-wartość naprawa realnej awarii „jedzenie znika". Reszta (Etap 1, watchdog, Etap 3, plasterki) w kolejności 14.5. Opcja D/anafora warunkowo. Każdy etap: kod → restart → test runtime (odtworzenie 11.C.1) → commit → następny.
