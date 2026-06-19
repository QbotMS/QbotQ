# QBot + QExt2 — PROJECT STATE / handoff migracyjny

Data: 2026-06-19. Autor: sesja Claude (Desktop Commander).
Cel: pojedynczy punkt wejścia dla świeżego asystenta/dewelopera na koncie
służbowym (TEAMS). Zbiera stan, który do tej pory żył wyłącznie w pamięci
konta Claude (account-bound, NIE migruje) i w transkryptach — a nie w repo.

> Zasada: ten plik opisuje STAN i WSKAZUJE źródła. Kanon architektury to
> `docs/architecture/QBOT_ARCHITEKTURA_V2.md`. Gdy ten plik i kanon się
> rozjeżdżają — wygrywa weryfikacja na żywym systemie, nie żaden z dokumentów.

---

## 0. Najpilniejsze (zrób przed/na starcie migracji)

1. **ROTACJA TOKENA — krytyczne.** Fine-grained GitHub PAT do repo QExt2 był
   zapisany DOSŁOWNIE w `.git/config` klonu `/opt/qext2` (remote URL) i został
   ujawniony 2026-06-19. Traktuj jako spalony: zrevokuj na GitHubie, wygeneruj
   nowy, i przekonfiguruj remote tak, by NIE trzymał tokena w configu
   (credential helper / `insteadOf` czytające z `/etc/qbot/qext2_push.token`).
   Wartości tokena NIE ma w tym pliku (celowo).
   > CZĘŚCIOWO 2026-06-19: `/opt/qext2/.git/config` NIE trzyma już literału —
   > używa credential helpera czytającego `/etc/qbot/qext2_push.token`.
   > POZOSTAJE: potwierdzić, że stary ujawniony token zrewokowany na GitHubie.
2. **Bearer MCP** (`/mcp/`) — jeśli był wklejany w transkrypty/konfig GPT,
   rozważ rotację przy zmianie konta. Wartość trzymana w `/etc/qbot/` na VPS.

---

## 1. Architektura — gdzie jest prawda

- Kanon: `docs/architecture/QBOT_ARCHITEKTURA_V2.md` (Albert-first).
- **WAŻNA KOREKTA (Krok 8):** plik V2 w tej wersji jest SPRZED korekty Kroku 8
  i NIE zawiera sekcji 13a. Realny routing domeny tras jest opisany w repo:
  `_session_notes/krok8_architektura_korekta.md`. Skrót: Albert-first jest
  faktem TYLKO dla domen zamkniętych (żywienie, kalendarz, przypomnienia).
  Dla domeny TRAS bramką wejściową jest Router v2 w `qbot_query_handler.py`,
  który dla `OPEN_DOMAIN_INTENTS` woła `core/planner.py` (Planner v2), a NIE
  Alberta. To trzeba zweryfikować na żywym systemie (patrz sekcja 3, konflikt).
- Specy modułów: `docs/architecture/SURFACE_INTEGRATION_SPEC.md` (nawierzchnia,
  QBot+QExt2, 2026-06-18), `docs/architecture/RIDEPHOTO_QBOT_MODUL_SPEC.md`
  (parkowany). Historyczne (zastąpione): `docs/architecture/archive/`.
- W repo był `QBOT_CURRENT_STATE.md` z 2026-05-26 (ostatni commit 05-28) —
  NIEAKTUALNY mimo autorytatywnej nazwy. Deploy dokłada do niego banner
  deprecacji wskazujący na ten plik i na V2.

## 2. Stan prac — QBot (Albert-first)

Zrealizowane (wg pamięci, do potwierdzenia na żywo):
- Krok 1: `QGPT_MODEL=gemini-2.5-flash`, `QBOT_ALBERT_MAX_STEPS=12`.
- Krok 2: realne single-step handlery `nutrition_log_add/delete/correct`
  z walidacją (`qbot3/safety.py`), dedup per-run, `tool_choice="auto"` po
  udanym zapisie.
- Krok 3: `should_use_albert_fallback()` zawsze True (poza
  `QBOT_ALBERT_HARD_KILL=1`); toolset routes dodany do registry Alberta.
- Krok 4 (Opcja B): 5 write-tools z realnym handlerem
  (`nutrition_log_*`, `calendar_event_add`, `reminder_add`); pozostałe na
  WRITE_DRAFT + two-step.
- Acceptance suite: 66/0/1 (Kroki 6-7).

## 3. KONFLIKTY pamięć ↔ dokumenty (zweryfikować przed działaniem)

Pamięć tego konta i dokumenty/notatki w repo miejscami się rozjeżdżają.
Świeży asystent MUSI to rozstrzygnąć żywym sprawdzeniem, nie ufać żadnej
stronie:

- **`core/planner.py`:** pamięć (po-Krok-4) mówi "usunięty po merge brancha";
  `krok8_architektura_korekta.md` (repo) mówi "ŻYWY dla domeny tras, NIE
  usuwać przed Krokiem 3b". Sprawdź: `ls -la /opt/qbot/app/core/planner.py`
  oraz realny routing zapytania "profil etapu 3".
  > ROZSTRZYGNIĘTE 2026-06-19 (sprawdzone na żywo): `core/planner.py` NIE
  > istnieje — planer usunięty. Wersja "z pamięci" była prawdziwa.
- **`action_execute` w `tools/list`:** pamięć w jednym miejscu mówi "usunięty
  (Opcja A, commity 93b1f6b / b20c855)", a opis Kroku 4 mówi "zostaje
  (Opcja B)". Sprawdź realny `tools/list` przez `/mcp/`.
- **Czyszczenie testowych reminders:** pamięć raz mówi "13→3 wyczyszczone
  (Krok 5)", a indziej "~10 starych zostało (ids 3,4,5,11,14,17,21,22,23,24)".
  Sprawdź `SELECT id FROM qbot_v2.reminders ORDER BY id;`.
- **Branch:** pamięć: `feature/router-v2-planner-v2-and-fixes` zmergowany do
  main. Repo na VPS był na branchu — sprawdź `git -C /opt/qbot/app branch`.
  > ROZSTRZYGNIĘTE 2026-06-19: repo na VPS na `main`, remote `QbotMS/QbotQ` (SSH).

## 4. FITMODEL

E0–E5 ukończone: 5 tabel DB, `fit_ingest.py`, `ftp_resolver.py`,
`glycogen.py`. E6–E9 do zrobienia.

## 5. QExt2 (Kotlin/Karoo — osobne repo QbotMS/QExt2)

- Build: push do `main` → GitHub Actions → Release → instalacja przez Karoo
  companion. Buduje się TYLKO z push na `main`.
- Otwarte: branch `feature/cassette-override` (override kasety 10-52,
  commit `bd4f131`) czeka na merge do main przez PR.
- PAT: `/etc/qbot/qext2_push.token` (root-only) — patrz sekcja 0 (rotacja).
  Fine-grained PAT ma max 366-dniowy expiry.
- Power meter: QUARQ (nie Assioma). Karoo nagrywa tylko kolarstwo; FIT bez
  mocy to nie błąd.

## 6. Nowy strumień: nawierzchnia (SURFACE_INTEGRATION_SPEC, 06-18)

Cross-system QBot+QExt2. Backend B1–B4 (Overpass around:20, REST
`/api/surface/{route_id}`, webhook RWGPS, prefetch athlete-data),
QExt2 E1–E7 (cache, fetch, fallback RouteGraph, mnożnik węgli/płynów,
advisory pacing, pole "szuter ahead"). W' bez mnożnika
nawierzchni (Quarq mierzy realną moc — mnożnik = double-count).

**STATUS 2026-06-19** (branch `feature/surface-overpass-resilience`, pushnięty):
- B1 ZROBIONE w części: Overpass `around:20m` per punkt, batchowanie,
  próbkowanie domyślnie 80 m, zdjęty limit próbek. Test vs RouteGraph — TODO.
- B2 ZROBIONE jako `GET /api/surface/by-name?name=` (wariant by-name, NIE
  `/{route_id}`): Bearer, cache w `route_surface_segments`, mapowanie 3-klasowe
  paved/gravel/loose, scalanie zakresów km, odpowiedź `not_ready`/`not_found` (202).
- Odporność Overpass: helpery `_overpass_post[/ _async]` z backoffem (429/5xx) +
  env `QBOT_OVERPASS_URLS/RETRIES/BACKOFF/SLEEP`; wszystkie wywołania przez nie.
- B3 (webhook RWGPS), B4 (prefetch), QExt2 E1–E7 — NIE rozpoczęte.
- Ograniczenia: mirrory kumi/private.coffee NIEOSIĄGALNE z VPS (został
  `overpass-api.de`); `by-name` niejednoznaczne przy substringach nazw etapów
  (pewny lookup po numerze stage); coverage ~25% przy sample 500 m.
- Bugfix: filtr `route_id` (segmenty per trasa) + diakrytyki w `SURFACE_MAP`
  (`gravel/żwir` itp. nie trafiały — leciały na default `paved`).

## 7. Infrastruktura (ścieżki — sekrety tylko WSKAZANE, nie zawarte)

- VPS: `olga181.mikrus.xyz`, port 10181, user root. Klucz SSH:
  `~/.ssh/mikrus_olga181` (PASSPHRASE-protected — wymaga agenta/hasła).
- App: `/opt/qbot/app/` (repo QbotMS/QbotQ, remote SSH). venv `.venv/bin/python3`.
- QExt2 klon na VPS: `/opt/qext2`.
- Serwisy: `qbot-api` (8002), bridge `/root/qbot-mcp/server.py` (20181/public).
- Public MCP: `https://qbot.cytr.us/mcp/` (JSON-RPC 2.0, Bearer).
- DB: PostgreSQL, schemat `qbot_v2` (`qcal_write_audit` w schemacie `public`).
- **Sekrety (NIE w repo, zostają na VPS):** `/etc/qbot/qbot-api.env`
  (hasło DB, klucze API), `/etc/qbot/qext2_push.token` (PAT QExt2),
  `.env.local` (model, flagi). VPS się nie przenosi — sekrety zostają na miejscu.

## 8. Co NIE przenosi się na konto służbowe (checklist migracji)

- [ ] **Pamięć tego konta Claude** — account-bound. Skonsolidowana TUTAJ.
- [ ] **Pliki projektu Claude** (5 docs) — teraz w `docs/architecture/`.
      Na nowym koncie: wskaż projekt na repo QbotQ; docs są już w repo.
- [ ] **Custom GPT** (ChatGPT): instrukcje `QBOT_GPT_INSTRUKCJE_v3.md` +
      Bearer w akcji GPT — to po stronie ChatGPT, niezależne od konta Claude.
      Zostaje jak jest, chyba że migrujesz też GPT (wtedy re-wpisać Bearer).
- [ ] **Klucz SSH** `mikrus_olga181` (+ passphrase) — skopiuj na maszynę służbową.
- [ ] **Dostęp do repo** QbotMS/QbotQ i QbotMS/QExt2 z konta/org GitHub służbowego.
- [ ] **Desktop Commander** — wepnij na maszynie służbowej (allowedDirectories).
- [ ] **Rotacja PAT** (sekcja 0) — najlepiej przy okazji, pod nową org.

## 9. Kluczowe zasady pracy (learnings — z pamięci)

- Heredocs zawodne dla Pythona przez SSH: `write_file` lokalnie → `scp -P 10181`
  → wykonaj zdalnie. Nigdy heredoc z polskimi znakami / zagnieżdżonymi cudzysłowami.
- Po ręcznym DELETE z `intake_items`/`intake_logs`: ZAWSZE
  `daily_summary_compute(date)` — stale `nutrition_daily_summary` daje
  false-positive `WRITE_INCONSISTENT` przy następnym zapisie.
- `calendar_events.date_start` ma FK do `days(date)`: usuwając testy — najpierw
  `calendar_events`, potem `days` (odwrotnie = FK violation).
- Artefakty pisane jako root w `/opt/qbot/artifacts/projects/` blokują zapis
  procesowi `qbot`: po sesji `find ... -not -user qbot -exec chown qbot:qbot {} \;`.
- `_TODAY` musi być dynamiczne (stałe module-level zamrażają datę przy starcie).
- Standard patch loop: czytaj plik → patch lokalnie → `scp` do `/tmp/` →
  `ast.parse()` + backup `.bak.<ts>` do `_bak_archive/` → wykonaj →
  `systemctl restart qbot-api && sleep 4` → smoke.
- Crontab: `crontab -l | sed '...' | crontab -` (nie edycja pliku wprost).
- Commity wymagają jawnej zgody; agent nigdy nie deployuje na prod bez potwierdzenia.
- Q (Terminus) działa natywnie na olga181 — bez SSH/DC. Token podawaj jawnie
  w promptach Q; zawsze re-weryfikuj smoke testy niezależnie.
- Mock acceptance (`ALBERT_LLM_PROVIDER=mock`) NIE łapie bugów pętli realnego
  Alberta — weryfikuj na żywych `/mcp/` smoke testach.
- Przed usunięciem symbolu importowanego module-level przez `qbot_api.py` etc.:
  `grep -rn "from <module> import"` + realny `uvicorn` start PRZED restartem
  (lekcja z incydentu 0205f9a — crashloop).

## 10. Aktywne TODO (skonsolidowane)

QBot: (1) rozstrzygnąć konflikty z sekcji 3; (2) Krok 3b — Router v2 dla
`OPEN_DOMAIN_INTENTS` → Albert zamiast `core/planner.py`, potem bezpieczne
usunięcie planera; (3) Krok 5 cleanup (redukcja keyword routera, /help,
testowe reminders); (4) FITMODEL E6–E9; (5) `planning_fact_add/update` w
`tool_descriptions()` Alberta.
QExt2: merge `feature/cassette-override` → main.
Nawierzchnia: B1/B2 wstępnie ZROBIONE (06-19, branch
feature/surface-overpass-resilience — review/PR); dalej: doprecyzować `by-name`
(niejednoznaczność), test vs RouteGraph, potem E1/E2 → E3 → E5 → B3 → B4 → E6 → E7.
RidePhoto: parkowany (MVP 0 = tekstowy instagram_draft bez zależności).

---
*Źródła stanu: pamięć konta Claude (2026-06) + repo `_session_notes/`
(krok3..krok11, SESJA_FINAL_2026-06-15) + docs/architecture/. Przy rozbieżności
patrz sekcja 3 i weryfikuj na żywym systemie.*
