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

## Skąd wiadomo, czy dane z pasa doszły (od 20.10.2026, QExt2 0.4.16)
- **Telegram „Nowa jazda”** (`qbot3/rides/ride_report_notify.py` `_hrv_line`, 10 min po jeździe) ma linijkę:
  „💓 HRV z pasa: pobrane (N uderzeń)” albo „⚠️ … nie dotarło do QBota → Pobierz z pasa” (dziennik jazdy ma
  `H10_REC_START`, a nagrania brak) albo „⚠️ … zapis nie ruszył” (są wpisy `H10_` bez startu zapisu). Jazda bez pasa:
  brak linijki. Dopasowanie po czasie startu ±15 min. Sprawdzone na 3 jazdach z 20.10 (każdy wariant).
- **Ustawienia QExt2 → „Pobierz z pasa”** (`H10Recorder.pullNow`): bez nowej jazdy zatrzymuje zapis (o ile nie
  trwa jazda), pobiera nagrania `QX…` bez kopii na Karoo i wysyła do QBota. Pasa nie czyści (robi to start kolejnej jazdy).
- Typowy przypadek: Karoo wyłączone zaraz po zapisaniu jazdy. Nic nie przepada: nagranie zostaje w pasie
  albo w pliku na Karoo; najpóźniej pobierze się na starcie następnej jazdy.
- Czas pobrania nie rośnie z długością jazdy (3 h ≈ 13 tys. RR ≈ kilkadziesiąt kB); dłuższe bywa samo nawiązanie
  połączenia (test 20.10: start 2 s, koniec 58 s) — do obserwacji.

## Etap 3 — analiza (od 20.10.2026, `fitmodel/hrv_ride.py`, tabela `qbot_v2.hrv_ride_result`, `sql/hrv_rr_v2.sql`)
Uruchamiana automatycznie przy każdym przebiegu `scripts/ride_report_ask.py` (cron) przez `process_pending()`:
nagrania z 7 dni bez wyniku, bez dopasowanej jazdy albo ze starszą wersją metody (`VERSION`). Ręcznie:
`.venv/bin/python3 fitmodel/hrv_ride.py QX<id>`.
1. **Dopasowanie do jazdy:** `activity_fit_raw.started_at` ±15 min od startu zapisu w pasie.
   **Pułapka:** `activity_record.ts` bywa przesunięte o strefę czasową (20.10: 13:21+02 zamiast 15:21+02) —
   korekta = różnica do `started_at` zaokrąglona do 15 min (`tz_fix_s`). Reszta sekund: najlepsza zgodność tętna
   pas↔Karoo w ±180 s (`lag_s`, `hr_corr`; `lag_edge` = najlepsze na granicy, niepewne). Czas jazdy = czas pasa − lag.
2. **Czyszczenie:** RR poza 300–2000 ms albo >20% od mediany 11 sąsiednich = błędne uderzenie, do obliczeń
   interpolacja; oś czasu z surowych RR (zgubione uderzenie = dwa odstępy w jednym, czas się zgadza). `artifact_pct`.
3. **DFA α1:** okna 120 s co 15 s, skale 4–16 uderzeń; okno z >5% błędów odpada.
4. **Równa jazda:** postój <5% s, toczenie bez mocy <15% s, zmienność mocy (średnie 10 s) CV<0.20.
5. **α1 ~ moc** (regresja, raz odrzucone odstające >2,5 SD): moc przy α1=0,75 → `ltp_w` (LTP z HRV), przy 0,5 →
   `tp_w` (tylko gdy były okna z α1<0,6). Pewność: wysoka (≥20 okien, 0,75 objęte z zapasem, r≤−0,5), średnia
   (≥10, objęte, r≤−0,3), niska (ekstrapolacja). Ta sama metoda na tętnie → `ltp_hr`.
6. **Zmęczenie** `drift_a1`: α1 w paśmie mocy p25–p75, 2. połowa − 1. połowa (ujemne = zmęczenie).
   **Rozgrzewka** `warmup_a1`: średnie α1 z 15 min. Do porównania `ltp_modelq_w` / `tp_modelq_w` z dnia jazdy.
- **Telegram „Nowa jazda”:** pod „HRV z pasa: pobrane” linijka „próg tlenowy z HRV ≈ X W (pewność …) · ModelQ Y W”
  albo „progu nie dało się wyznaczyć (za mało równej jazdy)”; ostrzeżenia: >5% błędów (pasek/elektrody),
  bateria pasa ≤20% (CR2025).
- **Nie wpływa na ModelQ** (etap 5: walidacja 4–8 tyg., decyzja Michała).
- **Testy:** `tests/test_hrv_ride.py` (9): szum biały α1≈0,5, 1/f ≈1,0, błądzenie ≈1,5; czyszczenie; regresja
  (próg, brak rozrzutu, ekstrapolacja = niska); równa jazda. Test całości 20.10 na syntetycznym nagraniu z jazdy
  15:21 (zadane: zegar +15 s, 2% błędów, α1=0,75 przy 185 W) → lag 14 s, r=0,97, błędy 1,95%, LTP 180 W (średnia).
  Kanapa (2,5 min spoczynku): α1 1,27–1,52, 0% błędów — zgodnie z fizjologią.

**Metoda v2 (21.10.2026, Etap 3b, `VERSION = 2`; stare wyniki przeliczają się same):**
wygładzanie powolnego trendu RR przed α1 (smoothness priors λ=500, jak Kubios/badania Rogersa); korekta błędnych
uderzeń jak Kubios „medium” (25% od mediany sąsiadów); okno liczy się tylko przy stabilnym tętnie (początek vs koniec
okna ≤6 ud.) i nie w pierwszych 5 min; „równa jazda” obejmuje łagodnie narastającą moc (≤15 W/min); wynik główny
ze **świeżej części jazdy** (okna do 90 min), z całości w `ltp_all_w`; **test schodkowy** (≥4 stopnie ≥5 min,
+8–45 W) rozpoznawany sam — wtedy regresja tylko z okien wewnątrz stopni (`source = test_schodkowy`).
Telegram pokazuje próg tylko przy pewności średniej/wysokiej.
Powód: 1. prawdziwa jazda 21.10 (miasto, 81 min, 0,15% błędów, zgodność tętna 0,997) — okna z rosnącym tętnem po
starcie miały α1 1,0–1,6 przy 190–210 W, regresja dała 286 W (pewność niska) i trafiło to na Telegram.
v2: te okna odrzucone, zostały 4 wiarygodne (176–182 W → α1 0,68–0,81 przy 145–149 ud.) — za mało na wynik = „brak”.
Testy: 14 (doszło 5: wygładzanie usuwa trend i nie psuje szumu 1/f, rampa łagodna/stroma, test schodkowy jest/nie ma).

## Dalej
Etap 3: dopasowanie nagrania do jazdy (czas startu + porównanie tętna z Karoo), czyszczenie, odsetek błędnych
uderzeń, DFA α1 w oknach równej jazdy, LTP z HRV. Etap 4: raport jazdy, Forma > Trendy, Albert.

## Uwagi
- Aplikacje Polara (Flow, Beat) potrzebne tylko do rejestracji pasa i aktualizacji oprogramowania. Eksport RR
  z nagrań pamięci przez Beat/Flow nie działa, dlatego zapis steruje QExt2.
- SDK Polara 7.x–8.x w wersji domyślnej ma minSdk 33 albo wymaga JDK 21; wariant 8.4.0-java17 ma minSdk 26
  i pasuje do Karoo 3 (Android 12) i projektu (Java 17). QExt2 minSdk podniesiony z 23 do 26.
