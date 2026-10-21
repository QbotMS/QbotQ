---
tytul: Group Ride (plan)
dzial: qext2
typ: przeglad
opis: Plan modułu jazdy grupowej — komunikaty i lista jeźdźców między licznikami Karoo, a na końcu także Garmin Edge. Jeszcze nie zbudowany.
tagi: [group ride, jazda grupowa, komunikator, karoo, garmin, connect iq, plan]
synonimy: [grouptrack, groupride, komunikator karoo, jazda w grupie, qext group ride]
skroty: [CIQ]
gdzie_widac: [nigdzie — moduł w fazie planu]
liczby: [24 h, 15 s, 5 min]
zalezy_od: [qext2/index]
wplywa_na: []
zrodla_kodu: [docs/TODO.md GROUP-RIDE]
aktualizacja: 21.10.2026
---

# Group Ride (plan)

## Co to jest

Planowany moduł jazdy grupowej: kilku rowerzystów, każdy ze swoim licznikiem, widzi kto jest ile przed nim lub za nim na trasie i może wysyłać gotowe komunikaty do reszty grupy. **Status: tylko plan, nic nie jest zbudowane.** Michał przemyśli decyzje przed startem prac.

## Po co

Żeby w grupie nie zgubić się na trasie, dać znać o postoju, gumie czy czekaniu bez wyciągania telefonu. Wzór: GroupRide w licznikach Garmin Edge, który działa tylko między Garminami. Cel QBota: wspólna centrala dla Karoo i (na końcu) Garmina, więc mieszane grupy.

## Jak ma działać

QBot jest centralą. Każdy licznik łączy się z nim przez internet z telefonu. Sesja ma kod, który rozsyła się uczestnikom; ważna 24 h od startu. Licznik wysyła pozycję, QBot liczy odległość po wspólnej trasie i rozsyła listę jeźdźców oraz komunikaty.

## Etapy

0. **Fundament — QBot i QExt2 dla innych osób.** Konta gości bez dostępu do danych Michała, QExt2 w trybie gościa (sam Group Ride), sposób wgrywania i aktualizacji u kolegów, zgoda na udostępnianie pozycji i kasowanie pozycji po jeździe. Łączy się z zaparkowanym pomysłem komercjalizacji (TODO: QBOT-KOMERCJA).
1. **Centrala w QBocie** — sesja z kodem, uczestnicy, pozycje, „kto ile przed/za”, rozsyłanie komunikatów.
2. **QExt2 Group Ride v1 (Karoo)** — dołączenie kodem, lista jeźdźców (dystans i czas po trasie), 8–10 gotowych komunikatów, alert z dźwiękiem, wyciszenie, wspólna trasa.
3. **Testy** — najpierw z „wirtualnym kolegą” symulowanym przez QBota, potem jazda z drugim Karoo.
4. **v2** — alarm „ktoś odpadł / stoi”, punkty spotkań z czasem dojazdu, mapa z kropkami, własne gotowce.
5. **v3** — podsumowanie grupowe po jeździe, podgląd na żywo w przeglądarce dla bliskich.
6. **Garmin (QExt Group Ride)** — dopiero gdy działa wersja Karoo. Pole danych Connect IQ łączące się z tą samą centralą.

## Garmin — co sprawdzono (21.10.2026, dokumentacja i forum programistów, bez testu na sprzęcie)

- **Edge 1040, 540, 840 (system Connect IQ 7) i nowsze:** pole danych może łączyć się z internetem na bieżąco, więc odświeżanie co kilkanaście sekund jest możliwe. Edge 1050, 550, 850 — do potwierdzenia na urządzeniu.
- **Starsze Edge (1030, 830, 530 i wcześniejsze):** pole danych łączy się tylko w tle, nie częściej niż co 5 min — za wolno; pomijamy.
- **Alert i dźwięk** z pola danych: działa (zgłaszano brak dźwięku po aktualizacji Edge 1050).
- **Wysyłanie komunikatów:** w polu danych tylko stuknięcie w ekran, przyciski nie działają. Edge dotykowe (840, 1040, 1050, 850) — pełna wersja; Edge bez dotyku (540, 550) — tylko odbiór.
- **Testy:** symulator Garmina → Fenix 8 Michała (łączność, alert) → pożyczony Edge wgrany kablem USB (konto właściciela niepotrzebne), jazda ze sparowanym telefonem właściciela.

## Decyzje do podjęcia

1. Czy dołączyć może ktoś tylko z telefonem (strona QBota)?
2. Co udostępniamy: tylko pozycję, czy też moc/tętno?
3. Goście: sam kod grupy czy konta w QBocie?
4. Odświeżanie: co 15 s czy rzadziej (bateria)?
5. Jak dystrybuujemy QExt2 kolegom?

## Ograniczenia i pułapki

- Bez zasięgu komórkowego komunikaty i pozycje docierają z opóźnieniem.
- Tylko gotowe komunikaty — Karoo i Edge nie nadają się do pisania tekstu.
- Bezpośrednie połączenie licznik–licznik bez internetu niesprawdzone; zasięg Bluetooth to kilkadziesiąt metrów.
- Alternatywne źródło pozycji: link Live Tracking z Karoo (TODO: LIVE-TRACK, pomysł B) — nieoficjalne, co 30 s, może przestać działać.

## Powiązane hasła

- QExt2 i Karoo (qext2/index).

## Zrodla

- `docs/TODO.md` — pozycja GROUP-RIDE, QBOT-KOMERCJA, LIVE-TRACK.
