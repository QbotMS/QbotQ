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

## API
- `GET /api/jedzenie/spo2?days=120` -> {nights[], verdict, factors, params}
- `GET /api/jedzenie/spo2?day=RRRR-MM-DD` -> przebieg nocy (series [[HH:MM, %]], events_list, thr)
  (qbot_food_api.py; po zmianie qbot_spo2.py -> restart qbot-web).

## UI
- Strona testowa `/zdrowie-spo2-test.html` (POZA repo, kopia web_public/ przez web_mirror.py).
  Docelowo kafel w Zdrowie > Serce -- czeka na akceptacje Michala.

Wiki: docs/wiki/zdrowie/spo2.md
