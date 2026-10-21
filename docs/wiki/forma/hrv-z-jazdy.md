---
tytul: HRV z jazdy (próg tlenowy z DFA α1)
dzial: forma
typ: algorytm
opis: Z odstępów między uderzeniami serca z pasa Polar QBot wyznacza po jeździe moc i tętno progu tlenowego, zmęczenie i świeżość.
tagi: [hrv, dfa alfa1, próg tlenowy, ltp, polar, pas]
synonimy: [dfa a1, alfa1, alpha1, hrvt1, vt1, aerobic threshold, ltp z hrv, hrv z paska]
skroty: [DFA α1, LTP, TP, RR]
gdzie_widac: [Raport z jazdy, Telegram Nowa jazda, Forma Trendy, Albert]
liczby: [okno 120 s co 15 s, α1 0.75 = LTP, α1 0.5 = TP, ≤5% błędnych uderzeń w oknie]
zalezy_od: [qext2/pas-h10, modelq/tp]
wplywa_na: []
zrodla_kodu: [fitmodel/hrv_ride.py, qbot_v2.hrv_ride_result, qbot3/rides/ride_report_notify.py _hrv_line, tests/test_hrv_ride.py]
aktualizacja: 21.10.2026 (metoda v2)
---

# HRV z jazdy (próg tlenowy z DFA α1)

## Co to jest

Analiza nagrania z [pasa Polar H10](../qext2/pas-h10.md). Miara DFA α1 opisuje, jak „uporządkowany” jest rytm serca: na luzie ok. 1 i więcej, przy progu tlenowym ok. 0,75, przy progu beztlenowym ok. 0,5. QBot zestawia α1 z mocą z tej samej jazdy.

## Po co

- **Niezależny sprawdzian LTP ModelQ** (od niego zależą strefy w Trenerze, pułap pacingu w QExt2, szacunki czasu tras).
- **Postęp bazy tlenowej ze zwykłych jazd**, bez testów.
- **Zmęczenie w trakcie jazdy** (spadek α1 przy tej samej mocy) i **świeżość na rozgrzewce**.

## Skąd dane

Odstępy RR z pamięci pasa (QExt2 po jeździe) + moc, tętno i prędkość 1 Hz z pliku jazdy. Liczone automatycznie przy każdym przebiegu crona pytania o raport (`ride_report_ask`); nagrania z 7 dni są dopasowywane ponownie, jeśli jazda dotrze później.

## Jak liczone

1. **Dopasowanie do jazdy:** start jazdy ±15 min; korekta strefy czasowej zapisu sekundowego; przesunięcie zegara z najlepszej zgodności tętna pas↔Karoo (±180 s).
2. **Czyszczenie:** uderzenie poza 300–2000 ms albo odchylone >20% od mediany 11 sąsiednich = błędne; do obliczeń zastąpione. Odsetek błędnych = jakość sygnału.
3. **DFA α1** w oknach 120 s co 15 s (skale 4–16 uderzeń). Okno z >5% błędów odpada.
4. **Tylko równa jazda:** w oknie postój <5% czasu, toczenie bez mocy <15%, moc w miarę stała.
5. **α1 względem mocy** (linia prosta, raz odrzucone odstające): moc przy α1 = 0,75 → **próg tlenowy z HRV**, przy 0,5 → okolice **TP** (tylko gdy był mocny fragment). Ta sama metoda na tętnie → tętno progu tlenowego.
6. **Pewność:** wysoka (≥20 okien, próg objęty pomiarem z zapasem, wyraźna zależność), średnia (≥10 okien), niska (wynik wydłużony poza zmierzony zakres).

## Gdzie to widać

**Raport z jazdy (Etap 4, 21.10.2026, makieta zaakceptowana):** kafel **„HRV z jazdy”** zaraz po „Moc na uderzenie serca” (raport właściwy i strona testowa; `web/public/raport-jazdy-hrv.js`, dane `GET /api/ride-report/hrv?ride=` w `qbot_web.py`). Z progiem (pewność średnia/wysoka): moc i tętno progu tlenowego z HRV, porównanie z ModelQ, wynik z całej jazdy, zmęczenie, rozgrzewka wobec normy (od 10 jazd z pasem), sygnał, bateria pasa. Bez progu: „bez progu”, okolice progu z okien równej jazdy (α1 0,62–0,88) i dlaczego brak wyniku. Zwinięty wykres α1 w czasie na tle mocy. Jazda bez pasa = brak kafla. Zawsze dopisek: pomiar porównawczy, nie zmienia ModelQ.

**Telegram „Nowa jazda”**, pod „HRV z pasa: pobrane”: „próg tlenowy z HRV ≈ X W (pewność …) · ModelQ Y W” albo „progu z HRV nie dało się wyznaczyć (za mało równej jazdy)”; ostrzeżenia „słaby sygnał” (>5% błędnych uderzeń) i „bateria pasa” (≤20%). **Forma → Trendy:** romby „LTP z HRV” przy linii LTP (pełny = pewność wysoka, jasny = średnia). **Albert:** pytania o pas / próg z HRV / zmęczenie z pasa (narzędzie `hrv_ride`).

## Jak czytać

- Do progu potrzeba kilku odcinków **5–8 min równej jazdy w różnym tempie** (np. ~150, ~180, ~210 W). Jazda po mieście zwykle nie wystarcza.
- To **nie jest LTHR**: LTHR (153) to tętno drugiego, wyższego progu; tętno progu tlenowego wyjdzie niżej.

## Decyzje i historia

- 20.10.2026: Etap 3 [HRV-JAZDA]. **Nie wpływa na ModelQ** — najpierw 4–8 tygodni porównań (Etap 5), decyzja Michała.
- Weryfikacja 20.10: 9 testów na sygnałach o znanym wyniku; test całości na sztucznym nagraniu z jazdy 15:21 (zadany próg 185 W → 180 W, zegar +15 s → 14 s, 2% błędów → 1,95%); kanapa: α1 1,27–1,52 w spoczynku.
- Znalezione przy okazji: zapis sekundowy jazd w bazie bywa przesunięty o strefę czasową względem startu jazdy — analiza to koryguje.

- **Metoda v2 (21.10.2026, Etap 3b, `VERSION = 2`; stare wyniki przeliczają się same):** wygładzanie powolnego trendu RR przed α1 (smoothness priors λ=500, jak Kubios/badania Rogersa); korekta błędnych uderzeń jak Kubios „medium” (25% od mediany sąsiadów); okno liczy się tylko przy stabilnym tętnie (początek vs koniec okna ≤6 ud.) i nie w pierwszych 5 min; „równa jazda” obejmuje łagodnie narastającą moc (≤15 W/min); wynik główny ze **świeżej części jazdy** (okna do 90 min), z całości w `ltp_all_w`; **test schodkowy** (≥4 stopnie ≥5 min, +8–45 W) rozpoznawany sam — wtedy regresja tylko z okien wewnątrz stopni (`source = test_schodkowy`). Telegram pokazuje próg tylko przy pewności średniej/wysokiej. Powód: 1. prawdziwa jazda 21.10 (miasto, 81 min, 0,15% błędów, zgodność tętna 0,997) — okna z rosnącym tętnem po starcie miały α1 1,0–1,6 przy 190–210 W, regresja dała 286 W (pewność niska) i trafiło to na Telegram. v2: te okna odrzucone, zostały 4 wiarygodne (176–182 W → α1 0,68–0,81 przy 145–149 ud.) — za mało na wynik = „brak”. Testy: 14 (doszło 5: wygładzanie usuwa trend i nie psuje szumu 1/f, rampa łagodna/stroma, test schodkowy jest/nie ma).

## Ograniczenia i pułapki

- α1 = 0,75 trafia w próg tlenowy u większości osób, nie u wszystkich idealnie.
- Mało równej jazdy (miasto, interwały, szuter z postojami) = brak wyniku albo niska pewność.
- Mokre elektrody i dobrze dopięty pasek = mniej błędnych uderzeń.

## Powiązane hasła

- [Pas Polar H10 na Karoo](../qext2/pas-h10.md)
- [HRV (nocne, Garmin)](hrv.md)
- [Tętno maksymalne](../modelq/tetno-maksymalne.md)

## Zrodla

- `fitmodel/hrv_ride.py` (`analyze`, `process_pending`, `result_for_ride`), tabela `qbot_v2.hrv_ride_result` (`sql/hrv_rr_v2.sql`)
- `qbot3/rides/ride_report_notify.py` `_hrv_line`
- `tests/test_hrv_ride.py`, `docs/HRV_JAZDA.md`
