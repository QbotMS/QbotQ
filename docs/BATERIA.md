# Bateria dnia — Body Battery, stres, drzemki (2026-10-20, sesja spo2-2010)

## Dane
- `garmin_daily_raw` kind='stress': `get_stress_data` (stres i Body Battery co 3 min, 480 pkt/dobe).
  Pobiera `qbot3/connectors/import_garmin_heart.py import_stress` (ostatnie 3 dni, w kazdym cyklu straznika Garmina).
  Historia od 01.06.2026 (Garmin oddaje ~4,5 mies.); backfill 141 dni zrobiony 20.10.
- Drzemki: `garmin_daily_raw` kind='sleep' -> `dailySleepDTO.dailyNapDTOS` (wykrywa zegarek). Dotad nieuzywane.
- Pora snu/pobudki: `qbot_sleep_daily`; TSS: `training_sessions`; kroki: `energy_daily` (juz byly, bilans kcal uzywa calego spalania Garmina).
- Dzien d = od pobudki d do zasniecia w noc d->d+1; po polnocy koncowka dnia lezy w pliku d+1 (laczone, godz. < 6).

## Wnioski z danych 06-10.2026 (141 dni)
- Dzien zuzywa ~70 pkt (rano ~83 -> do lozka ~9), noc laduje ~70 — bez zapasu.
- Rozladowanie: kroki 0,32; TSS 0,12; minuty stresu 0,03 (Spearman).
- 2 h przed snem: spokojnie (stres <= p25 ~32) -> noc +72, sen 82, HRV 82; nerwowo (>= p75 ~53) -> +62, 78, 75.
- Do lozka z BB <= p25 (~5) -> rano ~66; >= p75 (~16) -> rano ~95.
- Drzemki: 2 z krzywa (28.06 71 min: +3; 20.08 20 min: 0) — za malo, by ocenic wplyw.

## Kod
- `qbot_battery.py`: days(), insights() (progi p25/p75 z Twoich dni), verdict() (fakty dla ostatniego pelnego dnia + drzemka dzis), day_curve(), evening_hint().
- API: `GET /api/jedzenie/battery?days=` (dni + wnioski), `?day=` (krzywa dnia, jazdy, drzemki).
- Front: Zdrowie > Serce, kafel 'Bateria (Body Battery)', panel 'Bateria' na wspolnej osi (rano / do lozka / drzemki),
  szczegoly dnia z krzywa BB + stres + pasy jazd i drzemek; w szczegolach nocy: stres 2 h przed snem i bateria na dobranoc.
- Wieczorna linia snu (`fitmodel/sleep_target.evening_line`): '· dzis drzemka X min wliczona do snu doby'. Cel snu BEZ zmian
  (za malo drzemek, by zmierzyc wplyw; do ponownej oceny gdy bedzie >= 10 drzemek z krzywa).
- Bez nowych wiadomosci Telegram.

Wiki: docs/wiki/zdrowie/bateria.md
