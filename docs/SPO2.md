# SpO2 nocne (2026-10-20, sesja spo2-2010)

## Dane
- Zrodlo: `qbot_v2.garmin_daily_raw` (kind='sleep'), pole `wellnessEpochSPO2DataDTOList` -- pelna odpowiedz
  `get_sleep_data`, zapisywana codziennie przez `qbot_garmin_extra` (wellness). Odczyt co 60 s w czasie snu,
  `epochTimestamp` w GMT, `spo2Reading`, `readingConfidence` (nieuzywane).
- Odczyty minutowe od 01.06.2026 (Garmin oddaje ok. 4,5 mies. wstecz -- historii dalej nie da sie pobrac).
- `qbot_v2.spo2_daily` (import_garmin_heart.import_spo2) trzyma tylko srednie/minimum dnia od 11.04.2026;
  importer celowo wycina listy z raw_json -- szczegoly sa w garmin_daily_raw, NIE dublowac.
- Data wiersza = dzien pobudki (jak qbot_sleep_daily).

## Algorytm (qbot_spo2.py)
- mediana nocy; minuty spadku = SpO2 <= mediana - 4 (DROP_PTS); spadek = ciag minut (przerwa <= 3 min).
- ocena vs 60 poprzednich nocy (min. 20): <= p75 spokojna (good), <= p90 do obserwacji (warn), wyzej niespokojna (bad).
- verdict: ostatnia noc + 7 ostatnich nocy vs mediana 30 wczesniejszych.
- factors: alkohol (FP.alcohol_days) i TSS >= 100 dzien wczesniej -> minuty spadku; niespokojna noc -> HRV i
  ocena snu rano (qbot_sleep_daily). Tylko wyrazne roznice, min. 8 nocy w grupie.

## Poranna wiadomosc (Telegram)
- qbot_spo2.morning_signal(today) wolane w qbot_trener_notify.py zaraz po sygnale temp. skory (body_signal).
- Warunek: >= 2 z 3 ostatnich nocy warn/bad ORAZ tetno spocz. dzis >= norma + 3 bpm (norma = srednia 60 nocy,
  min. 30, qbot_wellness_daily garmin -- ta sama co body_signal). Jedno zdanie z ikona 🫁, tylko gdy warunek.
- Historia 06-10.2026: 3 razy (13.08, 28.09, 12.10), nigdy razem z sygnalem temp. skory -> brak dublowania.
- Od 20.10 (pozniej): drugi warunek = tempo oddechu >= norma + 1/min (zamiast lub razem ze spadkami SpO2), zawsze z tetnem spocz. >= +3.
  Historia 06-10.2026: 7 razy (13.07, 03.08, 05.08, 13.08, 12.09, 28.09, 12.10); 28.09 i 12.10 = wszystkie trzy sygnaly naraz.
- Szczegoly nocy: tetno co 2 min (hr_series, przycisk 'Tętno'), niespokojne momenty / h, bb_text (BB <= p25 i stres >= p75 z 60 nocy;
  ok. co piata noc -> tylko w szczegolach, NIE w porannej wiadomosci).
- NIE wplywa na sleep_target ani gotowosc ModelQ (swiadomie -- tylko informacja).

## API
- `GET /api/jedzenie/spo2?days=120` -> {nights[], verdict, factors, params}
- `GET /api/jedzenie/spo2?day=RRRR-MM-DD` -> przebieg nocy (series [[HH:MM, %]], events_list, thr)
  (qbot_food_api.py; po zmianie qbot_spo2.py -> restart qbot-web).

## UI
- Zdrowie > Serce (nowy uklad od 20.10, web/public/zdrowie-serce2.js): kafel 'Oddech w nocy', panel nocy na wspolnej osi czasu,
  szczegoly = noc minuta po minucie (SpO2 + pasy wahan oddechu + tempo oddechu). Stare zdrowie-spo2.js / forma-serce.js / zdrowie-serce.js usuniete.
- Oddech w nocy (te same dane snu): bv_min (wahania oddechu, breathingDisruptionData poziom 1-2), resp (tempo oddechu) vs resp_norm (mediana 60 nocy),
  stress, bb_gain, hr_min, restless_h. verdict: breath_text (czy spadki potwierdza drugi czujnik), resp_text (RESP_UP = +1/min).
- qbot_heart.spo2_assess() zastapila spo2_status (najnizszy odczyt doby, falszywe 'ponizej 90% w 21 z 30 nocy') w punktach Serca,
  tekscie AI i raporcie PDF dla lekarza (qbot_heart_ai: spadki/h i niespokojne noce).

Wiki: docs/wiki/zdrowie/spo2.md
