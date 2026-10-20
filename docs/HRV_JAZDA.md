# HRV z jazdy — pas Polar H10 → QExt2 → QBot

Stan: 2026-10-20 (sesja hrv-h10-2010). Plan i etapy: docs/TODO.md, sekcja [HRV-JAZDA].

## Po co
Niezależny pomiar progu tlenowego (LTP) i okolic progu (TP) z każdej zwykłej jazdy, metodą DFA α1 z odstępów
między uderzeniami serca (RR). Sprawdzian dla ModelQ, bez jazdy na maksa.

## Jak to działa (etapy 1–2, od QExt2 0.4.14)
- **W trakcie jazdy nie ma połączenia z pasem.** Pas Polar H10 zapisuje RR do własnej pamięci (jedno nagranie,
  ~95 tys. RR, ok. 20 h). Karoo dostaje zwykłe tętno przez ANT+, jak wcześniej.
- **Start jazdy** (QExt2 `hrv/H10Recorder.kt`, `onRideStart`): krótkie połączenie Bluetooth (SDK Polara 8.4.0-java17),
  stare nagranie w pasie: nasze (`QX...`) bez kopii na Karoo → pobierz i zapisz; potem usuń. Następnie
  „zacznij zapis RR” z identyfikatorem `QX<czas startu w ms, zegar Karoo>`. Pas nie odpowiada → próba co 30 s (4 razy).
  Komunikat na Karoo: „H10 zapis ✓” albo „H10: zapis nie ruszył”.
- **Koniec jazdy** (`onRideEnd`): stop zapisu, pobranie RR, paczka `pending_rr_<id>.json` na Karoo, wysyłka
  `POST /ride-readiness {"hrvRr": {...}}` (token urządzenia, Karoo samo czeka na sieć). Po odpowiedzi 200 paczka
  usunięta, zostaje znacznik `sent_rr_<id>` (60 dni). Komunikat: „H10 pobrane ✓ N uderzeń”.
- **Pamięć pasa czyszczona dopiero na starcie kolejnej jazdy**, gdy dane są już w QBocie albo w pliku na Karoo.
  Nie pobrano na końcu (pas zdjęty, brak zasięgu) → pobierze się na starcie następnej jazdy.
- **Ustawienia QExt2** (karta „Pas Polar H10”): zgoda na Bluetooth (Android 12 pyta raz), „Znajdź pas”
  (zapamiętuje pierwszy znaleziony H10), „Sprawdź połączenie” (stan zapisu, nagrania w pamięci, bateria pasa).
- Każdy krok trafia do dziennika jazdy (`H10_*`), widocznego w QBot SETUP > QExt2 > Dzienniki jazdy.

## QBot
- Odbiór: `mcp_server.py` `_qext2_hrv_rr` (usługa `q-bot`), gałąź `hrvRr` w `/ride-readiness`.
- Tabela `qbot_v2.qext2_hrv_rr` (`sql/hrv_rr_v1.sql`): `exercise_id`, `rec_start_ms`, `rec_end_ms`, `end_known`,
  `device_id`, `battery_pct`, `build`, `n_rr`, `sum_ms`, `rr_ms integer[]` (surowe RR w ms), `session_id`
  (wypełni etap 3), `received_at`. Surowe dane zachowane zawsze. Ponowna wysyłka nadpisuje.
- Test na żywo 20.10.2026: próbna paczka 4 RR → 200, wiersz zapisany, usunięty.

## Dalej
Etap 3: dopasowanie nagrania do jazdy (czas startu + porównanie tętna z Karoo), czyszczenie, odsetek błędnych
uderzeń, DFA α1 w oknach równej jazdy, LTP z HRV. Etap 4: raport jazdy, Forma > Trendy, Albert.

## Uwagi
- Aplikacje Polara (Flow, Beat) potrzebne tylko do rejestracji pasa i aktualizacji oprogramowania. Eksport RR
  z nagrań pamięci przez Beat/Flow nie działa, dlatego zapis steruje QExt2.
- SDK Polara 7.x–8.x w wersji domyślnej ma minSdk 33 albo wymaga JDK 21; wariant 8.4.0-java17 ma minSdk 26
  i pasuje do Karoo 3 (Android 12) i projektu (Java 17). QExt2 minSdk podniesiony z 23 do 26.
