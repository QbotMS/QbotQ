# QBot — plan przebudowy architektury

Status: projekt do realizacji po powrocie do PL.
Cel nadrzędny: koniec z codziennymi zgrzytami i plasterkami. Domena tras ma działać tak niezawodnie jak rejestracja żywienia.

---

## 1. Diagnoza — dlaczego obecna architektura produkuje zgrzyty

1. **Router keywordowy z ~250 intentami to ręcznie pisany parser języka naturalnego.** Każda nowa fraza, odmiana polska, kolizja słów ("trasa" vs "profil" vs Garmin) wymaga ręcznej łatki. To praca, do której wymyślono LLM-y — robiona na sztywno.
2. **First-match = wyrok.** Dopasowany keyword kończy routing. Slot-gate (dodany 06.2026) łapie brak parametrów, ale NIE łapie pewnych-złych odpowiedzi: handler się wykonał, zwrócił liczby, nikt nie wie że ze złego źródła (stale artefakt, zła domena — Garmin zamiast RWGPS).
3. **Albert jest fallbackiem-na-błędzie, a większość problemów to nie błędy.** Stale profil E07 (66 km zamiast 57.6) wyglądał na sukces. Fallback z definicji nie widzi sukcesów. Do tego flash-lite to za słaby model na planowanie wielokrokowe.
4. **Zduplikowane źródła prawdy.** Mapa stage→route istniała w `qbot_planning_facts` ORAZ w hardcode `_TUSCANY_STAGE_ROUTE` — i rozjechała się (etap 5: tabela 55395124 vs kod 55554132). Hardcode per-trip łamie zasadę "narzędzia generyczne".
5. **Dedup bez świeżości = nigdy nie odświeżaj.** Reuse artefaktu po route_id/sha256 nie sprawdza `updated_at` w RWGPS. Trasa zaktualizowana 10.06, artefakt z 09.06 — system z przekonaniem serwuje starą geometrię.
6. **Patche bez pamięci.** Naprawy idą przez sesje agenta; wiedza o nich żyje w transkryptach i memories, nie w systemie. Brak rejestru zmian i przyczyn.

## 2. Zasady docelowe

- **Jedno źródło prawdy** dla każdej konfiguracji. Plan etapów = `qbot_planning_facts`. Zero literałów route_id w kodzie.
- **Niezmienniki w kodzie, nie w nadziei.** Świeżość artefaktu, zgodność dystansu z API, idempotencja — sprawdzane deterministycznie przed odpowiedzią.
- **Domeny zamknięte → szybka ścieżka deterministyczna.** Żywienie, kalendarz, przypomnienia działają i zostają na keywordach.
- **Domeny otwarte → LLM-first.** Trasy, analizy, planowanie tripów: model planuje sekwencję narzędzi, kod wykonuje i waliduje.
- **Każdy write idempotentny z kluczem deterministycznym** (semantyka żądania, nie timestamp).
- **Narzędzia generyczne.** Działają dla dowolnego projektu/tripu, parametryzowane project_id.

## 3. Architektura docelowa

```
zapytanie
   │
   ▼
Router v2 — klasyfikacja DOMENY (nie intentu)
   │
   ├─ domena zamknięta (nutrition, kalendarz, wellness)
   │     └─► keyword fast-path → handler  (jak dziś, bez zmian)
   │
   └─ domena otwarta (trasy, analizy, trip planning)
         └─► PLANNER (LLM, model klasy sonnet/gemini-pro, tool_choice=required)
               │  planuje: znajdź → sprawdź świeżość → pobierz → licz → odpowiedz
               ▼
             TOOLS (dzisiejsze handlery jako narzędzia z kontraktami)
               route_find / route_fetch_gpx / route_profile / poi_for_stage /
               planning_fact_get / artifact_get / artifact_put ...
               │
               ▼
             INVARIANTS (kod, nie LLM):
               - freshness: artefakt vs updated_at z RWGPS → refetch gdy starszy
               - sanity: dystans/przewyższenie z obliczeń vs metadane API (tolerancja %)
               - poi_stale: POI policzone dla innej wersji trasy → jawny komunikat
```

Kluczowe decyzje:
- **Planner widzi wynik i ground-truth.** Po obliczeniu profilu narzędzie zwraca też metadane API; rozjazd >5% = błąd walidacji, nie odpowiedź.
- **Eskalacja domenowa w fast-path:** jeśli keyword trafił, ale treść zapytania kłóci się z domeną handlera (zapytanie o RWGPS routuje do Garmina) → przekaż do Plannera zamiast ufać first-match.
- **Albert/Planner: upgrade modelu.** flash-lite zostaje co najwyżej do klasyfikacji domeny; planowanie wymaga mocniejszego modelu. Koszt kontrolowany tym, że domeny zamknięte (większość ruchu) nie dotykają LLM.

## 4. Pętla samonaprawy (błąd → ticket → agent → zgoda)

Dlaczego Albert nie naprawia sam: nie widzi kodu, logów ani historii i nie ma prawa zapisu. Naprawa wymaga kontekstu i rąk — to rola agenta kodującego, nie runtime'owego LLM.

Etapy wdrożenia:
1. **Ticket automatyczny (pierwszy krok, tani):** każdy ERROR / złamany niezmiennik pakuje kontekst do `qbot_v2.incident_tickets`: zapytanie, intent, traceback, ostatnie linie logów, env. Komenda `/incydenty` zwraca gotowy prompt do wklejenia w Terminus.
2. **Auto-propozycja:** agent (cron/webhook) czyta ticket, diagnozuje, przygotowuje patch + testy na branchu/backupie. NIE wdraża.
3. **Human-in-the-loop:** jedno potwierdzenie ("tak" w GPT/Terminus) = apply + restart + smoke. Bez zgody nic nie dotyka produkcji.

Granica autonomii (twarda): agent nigdy sam nie commituje do produkcji. Lekcje z czerwca 2026: agent potrafił złamać wcięcia, wymyślić `mutation_type="generated"`, zrandomizować klucz idempotencji. Pół-automat tak, czarna skrzynka nie.

Dodatkowo: **rejestr zmian** — każdy zaaplikowany patch zapisuje wpis (data, plik, przyczyna, ticket) do `qbot_v2.change_log`. Koniec z "patchami, o których nikt nie pamięta".

## 5. Co zostaje bez zmian

- Rejestracja żywienia i cały fast-path domen zamkniętych.
- Schemat bazy `qbot_v2` (rozszerzenia: incident_tickets, change_log).
- MCP bridge, endpoint Custom GPT, auth.
- QExt2 (osobny system).
- Magazyn artefaktów (dochodzi tylko warstwa świeżości).

## 6. Plan migracji (każdy etap zostawia system działający)

**Etap 0 — spłata znanych długów (przed przebudową):**
- [ ] Rozjazd etapu 5: rozstrzygnąć z RWGPS API która trasa (55554132 vs 55395124) jest aktualną E05.
- [ ] Resolver stage→route czyta z `planning_facts`; usunąć `_TUSCANY_STAGE_ROUTE`.
- [ ] E07 w planie → 55567991 (+ poi_stale=true dla zmienionych etapów).
- [ ] Klucz idempotencji route_import: deterministyczny (sprawdzić czy timestamp-key nie został).
- [ ] Sprzątanie: osierocony artefakt rwgps_55590078, trasa-śmieć 55590078 na koncie RWGPS, duplikaty wierszy 55567991 w qbot_v2.artifacts ("3 rows").
- [ ] `planning_fact_update` jako action_execute (edycja planu z GPT, bez SSH).

**Etap 1 — niezmiennik świeżości (największy zysk/koszt):**
- [ ] `route_fetch_gpx(route_id)`: porównaj `updated_at` artefaktu z API; starszy → refetch, nowy sha256, stary wiersz → status superseded.
- [ ] Sanity-check profilu: wynik vs metadane API, tolerancja 5%; rozjazd = błąd, nie odpowiedź.

**Etap 2 — Router v2 (klasyfikacja domeny + eskalacja domenowa):**
- [ ] Lekka klasyfikacja domeny przed keyword-matchem (może zostać keywordowa, ale na poziomie domen, nie 250 intentów).
- [ ] Eskalacja: konflikt domeny treści z domeną handlera → Planner.

**Etap 3 — Planner LLM-first dla domeny tras:**
- [ ] Upgrade modelu plannera; handlery tras opakowane w toole z kontraktami (wejście/wyjście/błędy).
- [ ] Scenariusze testowe: wszystkie tegoroczne zgrzyty (E07 stale, mis-route do Garmina, StageSpec hard-fail, multi_intent collisions) jako regresja.

**Etap 4 — pętla ticketów (sekcja 4, etapy 1→3).**

**Etap 5 — porządki końcowe:**
- [ ] Audyt allowlisty action_execute vs schemat GPT.
- [ ] `rwgps_poi_fetch_google` jako action_execute + przeliczenie POI etapów z poi_stale.
- [ ] `artifact_move_shelf`, aktualizacja `/help`.

## 7. Modularyzacja — struktura repo

Cel: każdy moduł ma dedykowaną część przy wspólnym silniku; rozbudowa modułu nie miesza w reszcie projektu.

```
qbot/
  core/                  # SILNIK (wspólny, stabilny)
    router/              # Router v2: klasyfikacja domeny, dispatch do modułów
    planner/             # LLM planner dla domen otwartych
    invariants/          # świeżość, sanity-checks, idempotencja
    db/                  # dostęp do qbot_v2, migracje
    mcp/                 # bridge, schemat GPT, auth
    registry.py          # ładuje manifesty modułów
  modules/
    nutrition/           # domena zamknięta — fast-path (bez zmian logiki)
    routes/              # RWGPS, GPX, profile, POI, StageSpec — domena otwarta
    wellness/            # Garmin, Xert
    calendar/
    morning_report/
    ridephoto/           # moduł wg RIDEPHOTO_QBOT_MODUL_SPEC
  adapters/              # cienkie warstwy zewnętrzne
```

Kontrakt modułu — **manifest** (`modules/<nazwa>/manifest.py`):
- domena (zamknięta/otwarta) + keywordy modułu (router składa z nich globalną mapę; koniec jednej 250-pozycyjnej listy),
- toole eksponowane plannerowi (nazwa, schemat wejścia/wyjścia),
- akcje write → **allowlista `action_execute` generowana z manifestów**, nie utrzymywana ręcznie w dwóch plikach (likwiduje klasę błędów „BLOCKED bo druga lista"),
- testy regresyjne modułu.

Zasady:
- moduł nie importuje z innego modułu — tylko z `core/`; wymiana między domenami przez silnik,
- agent naprawiający moduł dostaje zakres plików tego modułu (granica blast-radius),
- `qbot_query_handler.py` znika docelowo: rozparcelowany na manifesty + `core/router`.

### QExt2 — decyzja o lokalizacji

Fakty: QExt2 (Kotlin/Gradle, Karoo) i QBot (Python) nie współdzielą kodu; integracja przez API/FIT. Deploy QExt2 zależy od GitHub Actions → Release → Karoo companion.

Rekomendacja: **workspace lokalny zamiast scalania repo** — `~/qbot-workspace/` z klonami `qbot/` i `QExt2/` obok siebie. Daje "wszystko w jednym miejscu" na dysku przy zerowym ryzyku dla pipeline'u releasów.

Jeśli jednak pełne monorepo: osobny etap migracji (nie przy okazji) — `git subtree` (zachowuje historię QExt2), workflowy z filtrami ścieżek (`paths: qext2/**` vs `paths-ignore`), tagi rozdzielone per moduł (`qext2-v*` dla releasów Karoo), weryfikacja że Karoo companion czyta Release z nowego repo.

## 8. Decyzje do podjęcia przed startem

1. Model plannera: Gemini Pro vs Claude (API w bridge już jest) — koszt vs jakość planowania.
2. Budżet latencji dla domeny tras (planner = 2-5 s więcej; akceptowalne dla analiz, sprawdzić dla prostych odczytów).
3. Czy klasyfikacja domeny w Routerze v2 keywordowa czy mini-LLM (koszt per query).
4. Zakres autonomii agenta w pętli ticketów (rekomendacja: stop na auto-propozycji).
5. ~~QExt2: workspace czy monorepo~~ **ROZSTRZYGNIĘTE (06.2026): dwa repa na GitHubie, QExt2 klonowane na Mikrusie jako `/opt/qext2` obok QBota.** Kopia robocza do edycji przez agenta; build i release nadal przez GitHub Actions → Karoo companion. Poza `/opt/qbot/`, żeby serwis qbot-api nie skanował katalogu Androida.

## 9. Kryterium sukcesu

Tydzień normalnego użycia domeny tras (nowa trasa, podmiana etapu, profil, POI, import) **bez jednej sesji naprawczej**. Każdy problem, który mimo to wystąpi, kończy się ticketem z pełnym kontekstem — nie wieczorem z grep-em.
