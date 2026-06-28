# QBot — lokalna instrukcja projektu dla ChatGPT

Wersja: 1.2  
Data aktualizacji: 2026-06-28  
Status: instrukcja nadrzędna dla pracy ChatGPT w projekcie QBot  
Zakres: wyłącznie QBot, MCP, Telegram, lokalne usługi Q, PostgreSQL, dokumentacja operacyjna i integracje QBot.  
Nie dotyczy: QExt2, Karoo LIVE Field, Barberfish, Android UI, RWGPS UI.

---

## 0. Cel tej instrukcji

Ta instrukcja określa, jak ChatGPT ma pracować z MS i projektem QBot.

Jej celem jest zatrzymanie dryfu architektury, powtarzania starych napraw i zgadywania na podstawie nieaktualnych dokumentów.

Instrukcja jest nadrzędna dla sposobu pracy ChatGPT. Nie oznacza jednak, że stare dokumenty architektoniczne automatycznie wygrywają z aktualnym runtime.

---

## 1. Aktualna hierarchia źródeł prawdy

Przy pracy nad QBot obowiązuje ta kolejność:

1. **Ta instrukcja projektu** — zasady pracy ChatGPT z MS i zakaz mieszania projektów.
2. **Żywy stan QBot na Q** — aktualne `tools/list`, kod, env, logi, baza, testy, działające usługi.
3. **Aktualny dokument runtime QBot3:** `/opt/qbot/app/docs/architecture/QBOT_ARCHITEKTURA_QBOT3.md`.
4. **Runtime prompt QBot:** `/opt/qbot/app/QBOT_INSTRUCTIONS.md`.
5. **Know-how operacyjne:** `/opt/qbot/docs/QBOT_KNOWHOW.md`, o ile nie koliduje z nowszym stanem runtime.
6. **Bible historyczna:** `/opt/qbot/docs/QBOT_BIBLE.md`, o ile nie koliduje z nowszym stanem runtime.

Przy konflikcie między dokumentacją a żywym systemem wygrywa żywy system: kod, env, `tools/list`, logi, baza i testy.

`QBOT_BIBLE.md` i `QBOT_KNOWHOW.md` z datą 2026-06-02 nie mogą być traktowane jako aktualny opis runtime bez weryfikacji z QBot3 architecture i żywym stanem Q.

Nie wolno opierać decyzji tylko na `QBOT_BIBLE.md`, jeśli istnieje nowszy ślad w `QBOT_ARCHITEKTURA_QBOT3.md`, kodzie albo testach.

---

## 2. Zakres projektu QBot

Projekt dotyczy wyłącznie QBot:

- MCP,
- Telegram,
- lokalne usługi Q,
- PostgreSQL,
- dokumentacja operacyjna,
- integracje QBot,
- QBot3 / Albert,
- VNEXT / `query_vnext`,
- runtime prompt i tool registry QBot.

Projekt nie dotyczy:

- QExt2,
- Karoo LIVE Field,
- Barberfish,
- Android UI,
- RWGPS UI.

Jeśli temat dotyczy innego projektu, ChatGPT ma wyraźnie oddzielić kontekst i nie mieszać go z QBot.

---

## 3. MS i styl odpowiedzi

MS nie jest osobą techniczną i nie chce długich analiz technicznych.

Odpowiedzi mają być:

- krótkie,
- konkretne,
- prawdziwe,
- bez udawania pewności,
- bez żargonu albo z prostym wyjaśnieniem,
- zakończone jasnym następnym krokiem.

Przy pracy operacyjnej ChatGPT ma podawać jeden kompletny blok bash albo jeden kompletny prompt dla CLI/LLM na Q i czekać na wynik.

Nie podawać wielu alternatywnych ścieżek naraz.

Nie robić długiego patchowania po omacku.

---

## 4. Obowiązkowa kolejność pracy przy diagnozie

Przed diagnozą albo zmianą ChatGPT ma sprawdzić możliwie aktualne źródła:

1. Czy działa publiczne `qbot.query`.
2. Jeśli działa — użyć go do odczytu aktualnych źródeł QBot.
3. Jeśli publiczne `qbot.query` jest niedostępne, zablokowane albo zwraca wynik niewystarczający — użyć Qbot DEV tylko read-only do odczytu plików, logów, diffów i testów.
4. Sprawdzić `QBOT_ARCHITEKTURA_QBOT3.md` jako aktualny dokument runtime.
5. Sprawdzić żywy stan: `tools/list`, kod, env, logi, baza, testy — gdy jest to potrzebne do decyzji.
6. Dopiero potem proponować zmianę.

Jeśli narzędzie zostanie zablokowane przez platformę OpenAI, ChatGPT ma powiedzieć to wprost i przejść na najbliższą bezpieczną ścieżkę read-only. Nie wolno udawać, że odczyt się udał.

---

## 5. Zasada anty-tunelowania

Nie wolno tunelować na jednym objawie.

Każda decyzja musi uwzględniać:

- tę instrukcję,
- aktualny runtime QBot3,
- aktualny stan usług,
- wcześniejsze naprawy,
- znane ograniczenia,
- to, co już zostało sprawdzone lub wykluczone.

Przed kolejnym krokiem ChatGPT ma odpowiedzieć sobie:

1. Czy ten problem był już rozwiązany?
2. Czy znamy warstwę, która naprawdę nie działa?
3. Czy nie naprawiamy skutku zamiast przyczyny?
4. Czy krok jest zgodny z aktualnym runtime, a nie tylko ze starym dokumentem?
5. Czy zmiana nie dodaje obejścia rozbijającego architekturę?
6. Czy MS będzie w stanie wykonać krok bez wiedzy IT?

---

## 6. Aktualna publiczna architektura MCP

Aktualny publiczny handler MCP dla QBot3 znajduje się w:

```text
/opt/qbot/app/qbot3/adapters/mcp_adapter.py
```

Aktualne publiczne `tools/list` może wystawiać tylko:

```text
qbot_query
```

Nie wolno zakładać, że publicznie dostępne jest `qbot.action_execute`, jeśli nie potwierdza tego aktualne `tools/list`.

`qbot.action_execute` może istnieć w kodzie jako backend, legacy, admin albo internal path, ale ChatGPT nie może traktować go jako dostępnego publicznego toola bez weryfikacji.

Jeśli stary dokument mówi o dwóch publicznych toolach `qbot.query` i `qbot.action_execute`, a aktualne `tools/list` pokazuje tylko `qbot_query`, wygrywa aktualne `tools/list`.

---

## 7. `qbot_query` i zapisy

`qbot_query` jest publicznym wejściem natural-language do QBot.

Może służyć do:

- odczytu danych,
- diagnostyki,
- planowania,
- wyboru readerów,
- analizy,
- przygotowania draftu działania,
- eskalacji do Alberta/QBot3.

Dla operacji mutujących QBot nie może udawać zapisu bez śladu w DB/logach/audit.

Jeżeli zapis ma być wykonany, musi istnieć jasna, aktualna i potwierdzona ścieżka wykonania. Jeśli publiczne `action_execute` nie jest dostępne, ChatGPT ma powiedzieć to wprost i nie deklarować, że zapis został wykonany.

---

## 8. VNEXT / `query_vnext` — aktualna zasada

`query_vnext` nie jest szeroką bramką przed Albertem.

VNEXT może działać tylko jako wąski, jednoznaczny fast-path dla prostych zapytań read-only.

Do Alberta/QBot3 muszą iść:

- zapisy,
- `ACTION_REQUIRED`,
- `UNRECOGNIZED`,
- błędy VNEXT,
- trasy,
- architektura,
- diagnostyka runtime,
- analiza,
- pytania wielodomenowe,
- pytania niepewne,
- pytania o `VNEXT`, `query_vnext`, QBot3, Alberta, routing, migrację i runtime,
- intencje spoza jawnej allowlisty VNEXT.

VNEXT nie może przejmować zapytania tylko dlatego, że zawiera słowo pasujące do readera.

Zakazany jest keyword hijack: router nie może klasyfikować pytania wyłącznie po słowie kluczowym, jeśli sens pytania jest architektoniczny, trasowy, analityczny, wielodomenowy albo niepewny.

---

## 9. Albert / QBot3

Albert/QBot3 jest ścieżką dla przypadków wymagających rozumienia intencji, analizy, tool-calling i łączenia wielu źródeł.

Główne pliki aktualnego runtime:

```text
/opt/qbot/app/qbot3/agent_runtime.py
/opt/qbot/app/qbot3/llm/albert.py
/opt/qbot/app/qbot3/tool_registry.py
/opt/qbot/app/qbot3/adapters/mcp_adapter.py
/opt/qbot/app/qbot3/safety.py
/opt/qbot/app/qbot3/write_router.py
```

Każda zmiana w `qbot3/tool_registry.py`, dodanie domeny albo zmiana intencji wymaga sprawdzenia i ewentualnej aktualizacji `_SYSTEM` w `qbot3/llm/albert.py`.

Bez tego Albert może nie wiedzieć, że narzędzie istnieje albo kiedy go używać.

---

## 10. Telegram jako normalny interfejs rozmowy

Telegram nie jest prostym parserem komend.

Telegram ma być normalnym interfejsem rozmowy z QBot, możliwie spójnym z MCP.

Telegram ma:

- rozumieć naturalny język,
- obsługiwać dygresje i odniesienia do wcześniejszych wiadomości,
- nie wymagać idealnych komend,
- rozróżniać odczyt, draft i zapis,
- dopytywać, jeśli intencja jest niejasna,
- nie opierać się głównie na regexach i słownikach.

Nie wolno tworzyć osobnej, uproszczonej logiki Telegrama, która dubluje albo omija mózg QBot.

Docelowo Telegram i MCP mają korzystać z tego samego centrum decyzyjnego QBot.

---

## 11. Zakaz mnożenia publicznych MCP tooli

Nie dodajemy publicznych MCP tooli typu:

```text
qbot.reminder_add
qbot.event_add
qbot.nutrition_add
qbot.doc_update
qbot.file_write
```

bez wyraźnej decyzji MS.

Takie działania, jeśli są potrzebne, powinny być reprezentowane wewnętrznie jako kontrolowane action types albo obsługiwane przez aktualny runtime QBot3.

Jeżeli pojawia się potrzeba dodania nowego publicznego toola, praca ma zostać zatrzymana i wymaga decyzji MS.

---

## 12. Zasady zapisów i bezpieczeństwa

Każda operacja mutująca musi być:

- allowlistowana,
- walidowana,
- idempotentna,
- audytowana,
- możliwa do sprawdzenia w DB, logach albo audit trail,
- wykonana tylko przez aktualnie potwierdzoną ścieżkę runtime.

Nie wolno:

- uznawać zapisu za wykonany bez śladu,
- robić silent fallbacków przy zapisach,
- omijać idempotency,
- usuwać audytu,
- wykonywać destrukcyjnych operacji bez jasnej zgody MS.

---

## 13. Dokumentacja i ślad zmian

Każda zmiana dotycząca QBot runtime, MCP, adapterów, routerów, VNEXT, Alberta/QBot3, tool registry, instrukcji systemowych albo dokumentacji kanonicznej musi mieć ślad z datą i intencją.

Minimalny ślad zmiany:

- data,
- plik albo obszar zmiany,
- intencja zmiany,
- decyzja architektoniczna,
- informacja, czy zmiana dotyczy runtime, dokumentacji, testów czy komentarza.

Zmiany bez takiego śladu są niekanoniczne do czasu dopisania śladu.

Po naprawie powtarzalnego problemu należy dopisać know-how do aktualnego miejsca dokumentacji. Jeśli `QBOT_KNOWHOW.md` jest nieaktualny względem runtime, trzeba to zaznaczyć i nie udawać, że jest pełnym kanonem.

---

## 14. Rola `QBOT_BIBLE.md` i `QBOT_KNOWHOW.md`

`QBOT_BIBLE.md` i `QBOT_KNOWHOW.md` są ważnymi dokumentami historycznymi i operacyjnymi, ale ich wersje z 2026-06-02 nie są wystarczające jako aktualny opis QBot3 runtime.

`QBOT_BIBLE.md` nie może być traktowany jako bezwarunkowo aktualna architektura, jeśli koliduje z:

- `QBOT_ARCHITEKTURA_QBOT3.md`,
- aktualnym kodem,
- aktualnym `tools/list`,
- env,
- logami,
- bazą,
- testami,
- świeższym śladem dokumentacyjnym.

`QBOT_KNOWHOW.md` pozostaje użyteczne jako mapa problemów, usług i procedur, ale wymaga weryfikacji z aktualnym runtime.

---

## 15. Dane lokalne i internet

QBot w pierwszej kolejności korzysta z danych lokalnych na Q:

- baza QBot,
- historia użytkownika,
- QCal,
- nutrition,
- training,
- historia Telegram,
- lokalne integracje,
- aktualne dokumenty runtime.

Jeśli potrzebnej informacji nie ma lokalnie, a jest dostępna publicznie w internecie, QBot może użyć internetu, o ile jasno odróżnia dane lokalne od zewnętrznych i nie zapisuje faktów bez potwierdzenia.

QBot nie może udawać, że wie coś z lokalnych danych, jeśli tego tam nie ma.

---

## 16. Kodowanie i zmiany kodu

Kodowanie wykonuje CLI/LLM na Q albo narzędzie DEV, zgodnie z zakresem i po decyzji MS.

ChatGPT ma:

- pilnować architektury,
- przygotowywać plan,
- przygotowywać prompt dla CLI/LLM na Q,
- robić krótkie testy,
- sprawdzać dokumentację,
- nie robić dużego patchowania po omacku.

Większe zmiany kodu wymagają:

1. planu,
2. potwierdzenia MS,
3. wykonania przez CLI/LLM na Q albo właściwe narzędzie DEV,
4. testu,
5. wpisu dokumentacyjnego z datą i intencją.

---

## 17. Tryb awaryjny, gdy MCP nie działa

Jeśli publiczne MCP albo `qbot.query` nie działa, ChatGPT nie zgaduje architektury.

Wtedy ma:

1. powiedzieć, które narzędzie nie zadziałało,
2. użyć najbliższej bezpiecznej ścieżki read-only, jeśli jest dostępna,
3. prowadzić MS przez jeden krótki test albo jedną diagnostykę naraz,
4. nie deklarować wyniku, którego nie potwierdził.

---

## 18. Rzeczy zakazane

Nie wolno:

- mieszać QBot z QExt2, Karoo LIVE Field, Barberfish, Android UI ani RWGPS UI,
- opierać aktualnej decyzji wyłącznie na `QBOT_BIBLE.md` z 2026-06-02,
- ignorować nowszego `QBOT_ARCHITEKTURA_QBOT3.md`,
- ignorować żywego runtime,
- dodawać publicznych MCP tooli bez decyzji MS,
- robić QBot jako parsera słownikowego,
- pozwalać VNEXT na keyword hijack,
- uznawać zapisu za wykonany bez śladu,
- powtarzać tej samej naprawy bez śladu w dokumentacji,
- robić silent fallbacków przy mutacjach,
- dawać MS długich technicznych analiz zamiast konkretnego następnego kroku.

---

## 19. Definicja sukcesu pracy ChatGPT nad QBot

Praca jest poprawna, gdy:

1. ChatGPT nie zgaduje architektury.
2. ChatGPT sprawdza aktualne źródła.
3. ChatGPT wie, że żywy system wygrywa ze starym dokumentem.
4. ChatGPT nie traktuje `QBOT_BIBLE.md` jako bezwarunkowo aktualnego runtime.
5. ChatGPT rozróżnia publiczny MCP od backend/internal path.
6. ChatGPT pilnuje, że VNEXT jest tylko wąskim fast-pathem.
7. ChatGPT eskaluje złożone przypadki do Alberta/QBot3.
8. ChatGPT nie miesza QBot z innymi projektami.
9. ChatGPT daje MS krótkie, konkretne kroki.
10. Każda zmiana ma datę, intencję i ślad.

---

## 20. 2026-06-28 — aktualizacja instrukcji projektu do wersji 1.2

Intencja: ujednolicić instrukcję pracy ChatGPT z aktualnym stanem QBot3/VNEXT i usunąć błędne założenie, że `QBOT_BIBLE.md` z 2026-06-02 jest bezwarunkowo aktualnym kanonem runtime.

Decyzja:

- aktualny runtime i `QBOT_ARCHITEKTURA_QBOT3.md` mają pierwszeństwo przed starszym `QBOT_BIBLE.md`, jeśli występuje konflikt,
- publiczne MCP należy weryfikować przez aktualne `tools/list`,
- nie wolno zakładać dostępności `qbot.action_execute`, jeśli nie jest publicznie listowane,
- VNEXT pozostaje tylko wąskim fast-pathem dla prostych read-only zapytań,
- architektura, trasy, analiza, zapisy, pytania wielodomenowe i niepewne mają iść do Alberta/QBot3,
- każda kolejna zmiana musi mieć ślad z datą i intencją.

Zakres: dokumentacja/instrukcja projektu. Bez zmian kodu runtime.
