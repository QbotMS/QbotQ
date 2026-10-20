---
tytul: Dziennik jazdy z Karoo
dzial: qext2
typ: polaczenie
opis: Karoo po każdej jeździe wysyła dziennik QExt2 do QBota; widać go w SETUP > QExt2, a wyniki pola BRAMA trafiają do Statusu.
tagi: [dziennik, karoo, qext2, brama, diagnostyka]
synonimy: [log karoo, ride log, dziennik qext2, logi jazdy, ride_log]
skroty: []
gdzie_widac: [SETUP, QExt2, Status]
liczby: [700 000 znaków]
zalezy_od: [brama]
wplywa_na: [brama, ../system/status]
zrodla_kodu: [mcp_server.py _qext2_ride_log ride_readiness, qbot_web.py setup_qext2_logs setup_qext2_log_text, web/public/setup.html q2Logs, qbot_status_checks.py gate, qbot_v2.qext2_ride_log, artifacts/karoo_gate_events.jsonl, qext2_deploy/app/src/main/kotlin/com/qext2/primary/util/RideLogUpload.kt]
aktualizacja: 20.10.2026
---

# Dziennik jazdy z Karoo

## Co to jest

QExt2 przez całą jazdę zapisuje na Karoo dziennik zdarzeń: pogodę, wiatr, komunikaty, połączenia z QBotem i każde dotknięcie pola BRAMA. Od wersji 0.4.4 po zakończeniu jazdy Karoo wysyła fragment tej jazdy do QBota.

## Po co

Żeby sprawdzić, co działo się na Karoo, bez podłączania go kablem. Przykład: 18.10.2026 brama z Karoo nie zadziałała, a serwer nie miał żadnego wpisu. Dopiero dziennik z Karoo pokazał, że o 13:05 Karoo nie miało internetu i prośba w ogóle nie wyszła.

## Skąd dane

Plik dziennika na Karoo (`ride_log.txt`). Karoo bierze z niego część od początku ostatniej jazdy, kompresuje i wysyła z tokenem urządzenia.

## Jak liczone

1. Koniec jazdy na Karoo: QExt2 przygotowuje paczkę i zapisuje ją na urządzeniu.
2. Karoo wysyła paczkę, gdy ma sieć. Bez sieci paczka czeka i idzie przy następnym uruchomieniu albo po kolejnej jeździe.
3. QBot zapisuje dziennik — jedna jazda to jeden wpis; ponowna wysyłka tej samej jazdy go zastępuje.
4. Z dziennika QBot wyciąga wyniki pola BRAMA (otwarta, brak sieci, błąd, za daleko, limit 15 s).

Bardzo długi dziennik (powyżej ok. 700 000 znaków po spakowaniu) jest skracany: zostają wszystkie wpisy bramy i końcówka jazdy.

## Gdzie to widać

SETUP → QExt2 → „Dzienniki jazdy z Karoo”: data i godzina jazdy, numer buildu, liczba wpisów, wyniki bramy oraz linki „pokaż” (cały dziennik) i „brama” (tylko wpisy bramy). Status → Bramka ostrzega, gdy ostatnia próba z Karoo skończyła się brakiem sieci albo błędem.

## Jak czytać

„13:05 brak sieci” oznacza, że Karoo nie wysłało prośby — brama nie mogła się otworzyć z Karoo. „otwarta” oznacza, że serwer potwierdził otwarcie.

## Decyzje i historia

- 20.10.2026: decyzja Michała — Karoo samo wysyła dziennik po jeździe (bez klikania), dzienniki w SETUP → QExt2. Pierwszy wpis: jazda 18.10 wgrana ręcznie z Karoo (test drogi przez publiczny adres).

## Ograniczenia i pułapki

Dziennik przychodzi dopiero po zakończeniu jazdy i gdy Karoo ma sieć. Jazdy na wersjach starszych niż 0.4.4 nie są wysyłane same.

## Powiązane hasła

- [Brama z Karoo](brama.md)
- [Status](../system/status.md)

## Zrodla

- `mcp_server.py` — `_qext2_ride_log` (odbiór, `POST /ride-readiness` z polem `rideLog`).
- `qbot_web.py` — `/api/setup/qext2/logs`, `/api/setup/qext2/logs/{start_ms}`.
- `web/public/setup.html` — `q2Logs`.
- `qbot_status_checks.py` — `gate` (wyniki z Karoo).
- QExt2: `util/RideLogUpload.kt`. Dok.: `docs/QEXT2_RIDE_LOG.md`.
