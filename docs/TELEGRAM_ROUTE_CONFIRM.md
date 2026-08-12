# QBot — Telegram: potwierdzenie analizy trasy i końcowe powiadomienie

_Utworzono 2026-07-01. Dokumentuje flow potwierdzeń RWGPS→Telegram oraz naprawę końcowego powiadomienia. Żywy system wygrywa — weryfikuj na kodzie._

## 1. Cel flow
Po zapisaniu/wykryciu nowej trasy w RWGPS:
1. RWGPS webhook materializuje artefakt trasy,
2. QBot wysyła Telegramem NUMEROWANE pytanie „uruchomić pełną analizę?",
3. użytkownik potwierdza numerowaną odpowiedzią (`NN TAK` / `NN NIE`),
4. po potwierdzeniu startuje precompute (w tle),
5. po zakończeniu QBot wysyła KOŃCOWE powiadomienie Telegram (z czasem liczenia).

## 2. Komponenty
- `qbot_qcal_telegram.py` — gateway Telegram:
  - `handle_message` → `_handle_pending_confirmation` (parsuje `NN TAK`, pilnuje numeru gdy jest wiele aktywnych próśb),
  - `_pending_execute` → `_execute_writer("confirm_route_analysis", ...)`: startuje worker precompute jako ODDZIELNY podproces (`route_precompute_trigger.py <id> --trigger-source telegram_confirm`) i zapisuje launch audit (intent `route_precompute_launch_audit`) w `telegram_conversation_turns`,
  - numerowanie pytań, TTL, idempotencja.
- `scripts/route_precompute_trigger.py` — worker:
  - `ensure_route_precompute_trigger(...)` — import artefaktu, surface/base/frames, sprawdzenie kompletności, precompute,
  - `_send_route_confirmation_final_notification(...)` — końcowe powiadomienie Telegram + audyt.

## 3. Zasady flow
- Numerowane pytania: `#NN Znalazłem nową trasę RWGPS: <nazwa>, <km>, <przewyższenie>. Odpowiedz: NN TAK albo NN NIE`.
- Gdy jest >1 aktywna prośba, samo „TAK" nic nie uruchamia — bot prosi o numer.
- TTL pytania: 30 min od REALNEJ wysyłki Telegram (nie od utworzenia pending_action).
- Idempotencja: jeden finalny komunikat na jedno uruchomienie (po `launch_audit_turn_id`).

## 4. Naprawa końcowego powiadomienia (2026-07-01)
**Objaw:** po `NN TAK` analiza kończyła się, dane były w DB, ale końcowe powiadomienie Telegram nie przychodziło (w `telegram_conversation_turns` brak `route_confirmation_final_notification_sent` i `_failed`).

**Przyczyna:** worker wysyłał końcowe powiadomienie TYLKO na ścieżce „faktycznie przeliczono". Gdy trasa była już policzona, `ensure_route_precompute_trigger` trafiał w gałąź „already complete → skipped" i wychodził PRZED krokiem wysyłki. Potwierdzone logiem workera, kodem i bazą.

**Naprawa (scripts/route_precompute_trigger.py):**
1. Końcowe powiadomienie wysyłane TAKŻE na ścieżce „already complete/skipped" (sukces, tekst „była już kompletna…"). Ścieżki „ran" i „błąd" bez zmian.
2. **Czas liczenia** w komunikacie (opcja B — z metek jobów): `_route_precompute_compute_seconds()` liczy od min `started_at` do max `finished_at` warstw (`route_precompute_jobs.layer_status_json`); `_format_duration_pl()` formatuje (np. „2 min 2 s", „50 s", „1 h 2 min"). Wstrzykiwane do `_route_confirmation_final_text(..., duration_seconds=...)`.
3. **action_id** wpisu audytu: gdy wynik nie niesie `pending_action_id` (ścieżka „ran"/skipped z workera CLI), brany jest z wiersza launch audit — dzięki temu wpis finalny wiąże się z numerem akcji.

**Audyt:** `telegram_conversation_turns`, intenty `route_confirmation_final_notification_sent` / `route_confirmation_final_notification_failed`, w `qbot_response_json` m.in. `launch_audit_turn_id`, `telegram_send`, `message_text`.

## 5. Chat_id (do kogo idzie powiadomienie)
`_route_confirmation_chat_id`: env `QBOT_ROUTE_CONFIRMATION_CHAT_ID` / `TELEGRAM_CONFIRMATION_CHAT_ID`, inaczej `TELEGRAM_ALLOWED_CHAT_IDS` (jest w `/opt/qbot/app/.env.local`). Worker (podproces qbot-api) dziedziczy env z OBU plików (`.env.local` + `/etc/qbot/qbot-api.env`).

## 6. Testy
`tests/test_route_precompute_trigger.py` + `tests/test_qbot_qcal_telegram.py` (razem 28, zielone po naprawie).

## 7. Weryfikacja na żywo (2026-07-01)
- #21 (BIOM2 55918401): dosłane brakujące powiadomienie — „✅ …była już kompletna. Czas liczenia: 2 min 2 s…", msg_id 743, audyt turn 220. Drugie wywołanie → `already_notified` (bez duplikatu).
- #22 (55864231, „Poligon w piekle poranka"): PEŁNY przebieg — pytanie → „22 TAK" → precompute RAN (5 warstw, ~50 s) → „✅ …zakończona. Czas liczenia: 50 s…", msg_id 747, audyt turn 225.

## 8. Uwaga o wdrożeniu
Worker to świeży podproces uruchamiany przy każdym „TAK" — poprawka w `route_precompute_trigger.py` działa od zaraz, BEZ restartu qbot-api. Zmiany w gatewayu (`qbot_qcal_telegram.py`) wymagają restartu qbot-api.

## 9. Reczne przeliczenie trasy z Telegrama (2026-08-12)

**Problem:** gdy pytanie `NN TAK` wygaslo (TTL 30 min) albo odpowiedziano `NIE`, z Telegrama nie
bylo jak wrocic do przeliczenia. Telegram nie chodzi przez Alberta — `handle_message` ->
`qbot_tools._tool_qbot_query` -> `qbot_query_router` (legacy, same czytniki), a `route_recompute`
zyje wylacznie w rejestrze Alberta (`qbot3/tool_registry.py`). Nie bylo tam zadnego writera do tras.

**Rozwiazanie (bez podpinania Telegrama do Alberta):** deterministyczny przechwyt w gatewayu,
PRZED oddaniem tekstu do routera. Reuzywa istniejacy writer `confirm_route_analysis`, wiec
dostaje za darmo audyt, idempotencje i koncowe powiadomienie z czasem liczenia.

**Skladnia:** `przelicz trase 55918401`, `policz trase <id>`, `/przelicz <id>`,
`uruchom pelna analize trasy <id>`. Detektor: czasownik przeliczenia + (slowo "tras"/"route"
LUB numer 7+ cyfr). `analiza trasy X` i `raport trasy X` NIE lapia sie (to odczyty).

**Zachowanie (`_route_recompute_request`):**
1. **ID wprost w komendzie** -> start od razu, bez pytania (polecenie jest jawne).
2. **ID tylko z kontekstu rozmowy** (`context_json.last_route_id`) -> numerowane potwierdzenie
   `NN TAK` / `NN NIE`, zeby nie przeliczyc nie tej trasy.
3. **Brak ID i pustego kontekstu** -> prosba o numer, bez tworzenia akcji.

**Kontekst:** `handle_message` zapisuje `last_route_id` w `context_json` przy kazdej turze —
z numeru w tekscie, z `result.route_report.route_id`, albo przenosi poprzedni.

**Szczegoly:** `upsert_pending_action(action_type="confirm_route_analysis", expires_minutes=30)`,
`idem_key = telegram_manual_recompute:<route_id>:<YYYYMMDDHHMM>` (dedup w obrebie minuty —
chroni przed podwojnym tapnieciem). Payload niesie `trigger_source="telegram_manual"`, ale
`_execute_writer` i tak wymusza `telegram_confirm` (gate koncowego powiadomienia w workerze).

**Intenty audytu** (`telegram_conversation_turns`): `route_recompute_manual`,
`route_recompute_confirm_needed`, `route_recompute_needs_id`, `route_recompute_result`,
`route_recompute_failed`, `route_recompute_dryrun`.

**Testy:** `tests/test_qbot_qcal_telegram.py` — klasa `TestQbotQcalTelegramManualRecompute`
(5 testow: detekcja, brak porwania odczytow, start natychmiastowy, potwierdzenie z kontekstu,
prosba o numer). Razem 17 zielonych.

**Weryfikacja na zywo (2026-08-12):** dry-run dla trasy 55918401 na chat 358008451 -> pending #29
w `telegram_pending_actions` z payload `route_id=55918401`, TTL 30 min, `last_route_id` zapisany
w `context_json`; wpis testowy anulowany. Zmiana w gatewayu => wymaga restartu `qbot-api` (zrobiony).
