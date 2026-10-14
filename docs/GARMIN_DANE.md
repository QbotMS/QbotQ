# GARMIN-DANE — pelne dane snu/HRV z Garmina (od 2026-10-14)

## Po co
Importer wellness pobieral pelne odpowiedzi Garmina (`get_sleep_data`, `get_hrv_data`), ale zapisywal
tylko wycinek. Przepadaly: temperatura skory, potrzeba snu, status i norma HRV. Teraz zapisujemy calosc.

## Decyzje (2026-10-14)
- Status/norma HRV: liczy **QBot sam** z `hrv_ms`. Wartosci Garmina (`garmin_hrv_status`, `hrv_balanced_*`) tylko do porownan.
- VO2max: liczy **QBot sam**. VO2max Garmina zamrozony od 2025-03-08 (46) — jazdy z Karoo ida jako plik "Tacx",
  a Garmin liczy VO2max tylko na urzadzeniu w trakcie nagrania. Obciazenie/TE Garmin liczy dla plikow Tacx (340/342) -> walidacja ModelQ ma sens.
- Aklimatyzacja do upalu: liczy QBot sam (activity_record: temperatura + HR + moc).
- Potrzeba snu Garmina: uzywana jako zalecenie wieczorne + analiza wplywu (dlug snu -> nastepny dzien).
- Connect+: nie (brak nowych danych).

## Dane
- `qbot_v2.garmin_daily_raw (date, kind, payload jsonb, fetched_at)` — PELNA odpowiedz; kind = `sleep` | `hrv`. ~22 kB/dzien po kompresji.
- Nowe kolumny w `qbot_v2.qbot_wellness_daily` (wiersz `source='garmin'`):

| kolumna | zrodlo w odpowiedzi Garmina |
|---|---|
| skin_temp_dev_c | sleep.avgSkinTempDeviationC (odchylenie od normy; NULL gdy skinTempDataExists=false) |
| sleep_need_min / sleep_need_baseline_min / sleep_need_feedback | sleep.dailySleepDTO.sleepNeed.actual / baseline / feedback (potrzeba na TE noc) |
| next_sleep_need_min / next_sleep_need_feedback | sleep.dailySleepDTO.nextSleepNeed (potrzeba na NASTEPNA noc -> zalecenie wieczorne) |
| garmin_hrv_status | hrv.hrvSummary.status (fallback: sleep.hrvStatus) |
| hrv_weekly_avg | hrv.hrvSummary.weeklyAvg |
| hrv_balanced_low / hrv_balanced_high | hrv.hrvSummary.baseline.balancedLow / balancedUpper |

Powody zmian potrzeby snu (trainingFeedback, sleepHistoryAdjustment, hrvAdjustment, napAdjustment) i zalecana pora snu
(recommendedBedtimeStart/EndMins) sa w `garmin_daily_raw` (kind='sleep').
Uwaga: dla starszych dni Garmin zwraca mniej sekcji (brak epok oddechu/SpO2), pola kluczowe sa.

## Kod
- `qbot_garmin_extra.py` — `extract_extra()`, `save_extra()`, `ensure_schema()`.
- `qbot_wellness_store._garmin_fetch_wellness/_garmin_import_wellness` — przekazuja pelne odpowiedzi do `save_extra`
  w savepoincie (blad nie psuje importu podstawowego; trafia do `warnings`). Codzienny import bez zmian: `scripts/run_wellness_imports.py`.
- `sql/garmin_extra_v1.sql` — schemat (idempotentny).
- `scripts/garmin_extra_backfill.py` — migracja (`--migrate-only`) + historia; wznawialny, 2 zapytania/dzien, przerwa 1.5 s.
  DLUGIE -> tylko przez SSH w tle (patrz docstring).
- `scripts/debug_garmin_sleep_hrv_raw.py` — diagnostyka: pelna odpowiedz -> `/opt/qbot/artifacts/garmin_sleep_hrv_raw_<data>.json`.
- Testy: `tests/test_garmin_extra.py`.

## VO2max QBota (Etap 2, 2026-10-14)
- `fitmodel/vo2max.py`: moc 5 min z krzywej ModelQ `P5 = CP + W'/300 s`, wzor ACSM `VO2max = 10.8 * P5 / waga + 7` [ml/kg/min].
  Wartosc NA KG (decyzja uzytkownika: waga widoczna obok). Bez skalowania do Garmina (Garmin ~+5: luty 2025 QBot 40.6 vs Garmin 46).
- Odrzucone: regresja HR<->moc z jazd (test na 23 jazdach: -100..400, teren/dryf tetna); surowe MMP 5 min (zaszumione, np. 384 W przy CP 241 we wrzesniu 2026).
- Liczone w locie (bez kolumny w bazie): `add_vo2max()` w `/api/forma/data` (qbot_web: series + latest), przeniesienie CP/W'/wagi z ostatniego dnia.
- UI: Forma > Trendy, wykres mocy -> pigulka "VO2max" (niezalezna od CP/LTP, os po lewej do srodka), wartosc w podpisie i dymku. forma2-data.js v=64.
  UWAGA: strony zywe w /opt/qbot/web/public, `web_public/` w repo to lustro (scripts/web_mirror.py).
- Testy: `tests/test_vo2max.py`.

## Plan dalej
Etapy 2–7 w `docs/TODO.md` -> `[GARMIN-DANE]`.
