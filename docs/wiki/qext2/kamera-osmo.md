---
tytul: Kamera DJI Osmo (stan nagrywania na Karoo)
dzial: qext2
typ: funkcja
opis: QExt2 łączy się przez Bluetooth z kamerą DJI Osmo Nano na czas jazdy i odczytuje, czy kamera nagrywa. Etap 1 — tylko dziennik jazdy, kropka REC w KOKPIT 2 później.
tagi: [qext2, karoo, kamera, dji, osmo, nagrywanie, bluetooth]
synonimy: [osmo nano, kamera dji, kropka rec, sygnalizacja nagrywania, czy kamera nagrywa]
skroty: [BLE, R-SDK, REC]
gdzie_widac: [SETUP QExt2, Dzienniki jazdy, Karoo]
liczby: [30 s, 45 s, 60 s, 2 Hz]
zalezy_od: [dziennik-jazdy.md, autotest-karoo.md]
wplywa_na: [kokpit2.md]
zrodla_kodu: [qext2 osmo/OsmoLink.kt, qext2 osmo/OsmoProtocol.kt, qext2 setup/SetupActivity.kt osmoCard, qext2 QExt2PrimaryExtension.kt onRideState, qext2 health/FeatureGuard.kt OSMO]
aktualizacja: 21.10.2026
---

# Kamera DJI Osmo (stan nagrywania na Karoo)

## Co to jest

QExt2 rozmawia z kamerą DJI Osmo Nano przez Bluetooth (ten oszczędny, jak czujniki tętna) i odczytuje jej stan: czy nagrywa, baterię i tryb. Kamerą **nie steruje** — tylko patrzy (decyzja Michała 21.10.2026).

## Po co

Żeby na rowerze bez zaglądania w kamerę wiedzieć, że film się nagrywa. Docelowo w KOKPIT 2 w górnym wierszu, między opadem/niebem a wiatrem: czerwona kropka **REC** = nagrywa, szara = kamera połączona, nie nagrywa, pusto = kamery nie ma.

## Etapy

1. **Etap 1 (QExt2 0.4.23, 21.10.2026):** połączenie i zapis w dzienniku jazdy, bez kropki. Sprawdzamy, czy Karoo dogada się z kamerą i ile baterii kamery schodzi.
2. **Etap 2:** kropka REC w KOKPIT 2.
3. **Etap 3:** wyłącznik zdalny w QBot SETUP (bezpiecznik `osmo` już jest w QExt2).

## Jak działa

- **Pierwszy raz:** SETUP QExt2 → karta „Kamera DJI Osmo” → „Znajdź kamerę” (kamera włączona obok), potem „Połącz i sprawdź”. Kamera za pierwszym razem pokaże okno zgody — trzeba je zatwierdzić na kamerze. Kamera musiała być kiedyś aktywowana w aplikacji DJI Mimo (Michał to zrobił).
- **W jeździe:** start jazdy na Karoo → QExt2 łączy się z zapamiętaną kamerą (bez szukania — w tle szukanie na Karoo nie działa, lekcja z pasa H10). Połączenie trwa przez całą jazdę, także w pauzie. Koniec jazdy → rozłącza.
- **Kamera wyłączona albo daleko:** próba kończy się po 45 s i wraca co 30 s. QExt2 kamery nie budzi.
- Kamera wysyła stan ok. 2 razy na sekundę. Jeśli ucichnie, QExt2 ponawia prośbę o stan.

## Dziennik jazdy (SETUP QBota > QExt2 > Dzienniki jazdy)

- `OSMO_CONNECT`, `OSMO_LINKED` — łączenie i zgoda kamery.
- `OSMO_REC NAGRYWA / stop` — każda zmiana nagrywania (z baterią).
- `OSMO_STAT` co minutę — nagrywa czy nie, bateria i **spadek baterii od połączenia** (do oceny, ile kosztuje trzymanie łącza).
- `OSMO_NO_REC_INFO` — kamera łączy się, ale nie podaje, czy nagrywa (wtedy trzeba innej drogi).
- `OSMO_OTHER`, `OSMO_MODE_RAW` — wiadomości kamery, których jeszcze nie rozumiemy (do nauki protokołu).
- `OSMO_TIMEOUT`, `OSMO_GATT_DOWN`, `OSMO_ERR` — brak połączenia, rozłączenie, błąd.

## Ograniczenia i pułapki

- Protokół **nie jest oficjalnie udostępniony** przez DJI dla Nano. Sposób rozmowy pochodzi z otwartego projektu Osmosis (licencja MIT), który go rozpracował i sprawdził na Nano. Aktualizacja kamery może to zepsuć — wtedy znika tylko ten odczyt, reszta QExt2 działa (bezpiecznik `osmo`: 3 błędy z rzędu albo pętla padania wyłączają funkcję).
- Kamera prawdopodobnie przyjmuje jedno takie połączenie naraz — gdy trzyma ją telefon z Mimo, Karoo może się nie połączyć.
- Połączenie może nie pozwalać kamerze zasnąć na postoju — to sprawdza `OSMO_STAT`.

## Powiązane hasła

[KOKPIT 2](kokpit2.md) · [Dziennik jazdy](dziennik-jazdy.md) · [Autotest Karoo i bezpieczniki](autotest-karoo.md)
