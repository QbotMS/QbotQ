---
tytul: Kamera DJI Osmo (stan nagrywania na Karoo)
dzial: qext2
typ: funkcja
opis: QExt2 łączy się przez Bluetooth z kamerą DJI Osmo Nano na czas jazdy i odczytuje, czy kamera nagrywa. Etap 1 — tylko dziennik jazdy, kropka REC w KOKPIT 2 później.
tagi: [qext2, karoo, kamera, dji, osmo, nagrywanie, bluetooth]
synonimy: [osmo nano, kamera dji, kropka rec, sygnalizacja nagrywania, czy kamera nagrywa]
skroty: [BLE, R-SDK, REC]
gdzie_widac: [KOKPIT 2, STATS v2, SETUP QExt2, Dzienniki jazdy, Karoo]
liczby: [30 s, 45 s, 60 s, 2 Hz]
zalezy_od: [dziennik-jazdy.md, autotest-karoo.md]
wplywa_na: [kokpit2.md]
zrodla_kodu: [qext2 osmo/OsmoLink.kt (DUML od 0.4.24), qext2 osmo/OsmoProtocol.kt, qext2 kokpit/Kokpit2.kt recDot, qext2 statsv2/StatsV2Renderer.kt drawCamBat drawPlan, qext2 setup/SetupActivity.kt osmoCard, qext2 QExt2PrimaryExtension.kt onRideState, qext2 health/FeatureGuard.kt OSMO]
aktualizacja: 21.10.2026
---

# Kamera DJI Osmo (stan nagrywania na Karoo)

## Co to jest

QExt2 rozmawia z kamerą DJI Osmo Nano przez Bluetooth (ten oszczędny, jak czujniki tętna) i odczytuje jej stan: czy nagrywa, baterię i tryb. Kamerą **nie steruje** — tylko patrzy (decyzja Michała 21.10.2026).

## Po co

Żeby na rowerze bez zaglądania w kamerę wiedzieć, że film się nagrywa. Docelowo w KOKPIT 2 w górnym wierszu, między opadem/niebem a wiatrem: czerwona kropka **REC** = nagrywa, szara = kamera połączona, nie nagrywa, pusto = kamery nie ma.

## Etapy

1. **Etap 1 (QExt2 0.4.23, 21.10.2026):** połączenie i zapis w dzienniku jazdy, bez kropki. Test 21.10: Karoo połączyło się z kamerą przez Bluetooth, ale Nano nie odpowiedziało na „język pilota DJI” (R-SDK) — pilot DJI też nie obsługuje Nano.
1. **Etap 1b (QExt2 0.4.24, 21.10.2026):** język aplikacji Mimo (DUML): parowanie ze zgodą na kamerze, podtrzymanie co 1 s, prośba o stan; dziennik zapisuje wszystko, co kamera przyśle. Sprawdzamy, czy stan „nagrywa” idzie przez Bluetooth.
2. **Etap 2 (QExt2 0.4.26, 21.10.2026):** kropka REC w KOKPIT 2 oraz w STATS v2 komórka **CAM BAT** (bateria kamery) obok zwężonego PLANU CZASU. Test 0.4.25: kamera po sparowaniu wysyła przez Bluetooth stan „nagrywa” (bajt 81, stop = 01), licznik czasu nagrania i baterię.
3. **Etap 3:** wyłącznik zdalny w QBot SETUP (bezpiecznik `osmo` już jest w QExt2).

## Jak działa

- **Pierwszy raz:** SETUP QExt2 → karta „Kamera DJI Osmo” → „Znajdź kamerę” (kamera włączona obok), potem „Połącz i sprawdź”. Kamera za pierwszym razem pokaże okno zgody — trzeba je zatwierdzić na kamerze. Kamera musiała być kiedyś aktywowana w aplikacji DJI Mimo (Michał to zrobił).
- **W jeździe:** start jazdy na Karoo → QExt2 łączy się z zapamiętaną kamerą (bez szukania — w tle szukanie na Karoo nie działa, lekcja z pasa H10). Połączenie trwa przez całą jazdę, także w pauzie. Koniec jazdy → rozłącza.
- **Kamera wyłączona albo daleko:** próba kończy się po 45 s i wraca co 30 s. QExt2 kamery nie budzi.
- Kamera wysyła stan ok. 2 razy na sekundę. Jeśli ucichnie, QExt2 ponawia prośbę o stan.

## Dziennik jazdy (SETUP QBota > QExt2 > Dzienniki jazdy)

- `OSMO_CONNECT`, `OSMO_PAIR_STATUS`, `OSMO_APPROVED`, `OSMO_LINKED` — łączenie, parowanie i zgoda kamery.
- `OSMO_MSG`, `OSMO_PARAM`, `OSMO_0280` — każdy rodzaj wiadomości kamery (pierwszy raz w całości) i zmiany stanu kamery (diagnostyka 0.4.24).
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
