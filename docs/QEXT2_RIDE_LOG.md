# QExt2 — dziennik jazdy w QBocie (20.10.2026, sesja karoolog-2010)

Decyzja Michała 20.10.2026: wariant A — Karoo samo wysyła dziennik po jeździe; dzienniki widać w **SETUP → QExt2**.

## Droga danych
1. **Karoo (QExt2 0.4.4+, `util/RideLogUpload.kt`)** — przy przejściu jazdy w stan Idle (`onRideState`) bierze z
   `ride_log(.1).txt` fragment od ostatniego `RIDE_START`, pakuje gzip + base64 (limit 700 000 znaków; za dużo →
   wszystkie wpisy bramy + końcówka dziennika) i zapisuje `pending_ride_log_<startMs>.json`.
2. Wysyłka: `POST https://qbot.cytr.us/ride-readiness` body `{"rideLog": {startMs, endMs, build, gz}}`, nagłówki
   `X-QExt2-Token` + `Authorization` (token urządzenia `QEXT_READINESS_TOKEN`), `waitForConnection=true`.
   Sukces 200 → plik usunięty; porażka → zostaje i idzie przy starcie usługi i końcu kolejnej jazdy. Kroki w dzienniku:
   `RIDE_LOG_QUEUED / SEND / SENT / FAIL`.
3. **QBot (`mcp_server.py _qext2_ride_log`, usługa `q-bot`)** — zapis do `qbot_v2.qext2_ride_log`
   (klucz `ride_start_ms`; ponowna wysyłka nadpisuje), wyniki pola BRAMA (`GATE_RESULT`) dopisywane do
   `/opt/qbot/artifacts/karoo_gate_events.jsonl`.
4. **Widok (`qbot_web.py /api/setup/qext2/logs`, `/api/setup/qext2/logs/{start_ms}[?gate=1]`, `setup.html q2Logs`)** —
   SETUP → QExt2 → „Dzienniki jazdy z Karoo”: jazda, build, wpisy, wyniki bramy po polsku, linki „pokaż” / „brama”.
5. **Status → Bramka (`qbot_status_checks.gate`)** — ostrzeżenie, gdy ostatni wynik z Karoo (NO_NET / ERROR) jest
   późniejszy niż ostatnie otwarcie w dzienniku serwera.

## Test 20.10.2026
Dziennik jazdy 18.10 (pobrany z Karoo przez USB) wysłany publicznym adresem jak z Karoo → 200, 1567 wpisów,
brama „13:05 brak sieci”; Status: „Ostatnia próba z Karoo 18.10 13:05: brak sieci na Karoo — prośba nie wyszła”.
Uwaga: publiczny most odrzuca (403) klienta z domyślnym User-Agent Pythona — testy wysyłać z `User-Agent: okhttp/...`.

## Tło
18.10 Karoo zgłosiło przy bramie brak internetu (`HTTP_FAIL ... NO_INTERNET`), więc prośba nie dotarła do serwera
i dziennik serwera bramy był pusty. Bez dziennika z Karoo nie dało się tego sprawdzić z QBota.
