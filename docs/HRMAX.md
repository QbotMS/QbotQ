# Tętno maksymalne (HRmax) — automat

Stan: 2026-10-20 (sesja hrmax-2010, decyzja Michała). Kod: `fitmodel/hrmax.py`, testy `tests/test_hrmax.py` (9).

## Po co
HRmax był wpisany ręcznie w kilku miejscach i się rozjechał: intervals.icu/Karoo 173 (poprawione 04.10),
QBot `fitmodel_param.hr_max_bpm` 184, QExt2 (`RIDER_MAX_HR_BPM` w env usługi q-bot) 184. Teraz jest JEDNA wartość
z automatu, którą czytają wszyscy.

## Jak liczy
- **Szczyt z jazdy** (`ride_peak`, tabela `qbot_v2.hrmax_peak`, każda jazda od 2025 raz): tętno utrzymane ≥10 s
  (minimum z 10 kolejnych sekund), 120–210; fizjologiczne tempo (20 s przed: najwyżej 40 ud. niżej, 30 s po: spadek
  najwyżej 40 ud.); realny wysiłek: średnia moc 120 s przed końcem ≥80% TP ModelQ z dnia jazdy (brak mocy = odrzut).
  Odrzuca artefakt starego paska z 02.05.2026 (93→181→115 przy ~70 W). Tętno z pliku jazdy Karoo (z pasem Polar na
  ANT+ = tętno z pasa).
- **Publikacja** (`qbot_v2.hrmax_daily`, krok `hrmax` na początku `daily_job`, przed ingestem):
  najwyższy wiarygodny szczyt z 365 dni; **w górę od razu**, **w dół** dopiero gdy przez 365 dni nic nie było bliżej
  niż 3 ud. od obecnej wartości.
- **Start 20.10.2026: 173** (wartość sprawdzona 04.10). Suchy przebieg: 376 jazd, 346 z wiarygodnym szczytem;
  najwyższe 172 (26.02.2025), 171 (24.01.2025), 170 (05.06.2026) — z 365 dni 170, mieści się w tolerancji, zostaje 173.

## Kto czyta (`get_hrmax()`)
- `fitmodel_param.hr_max_bpm` (zapis przy zmianie) → `fit_ingest` pasmo HR odcinków 0,60–0,85 HRmax.
  **Zmiana = przeliczenie odcinków**: kopia `qbot_v2.fitmodel_segment_bak_hrmax_<data>`, czyszczenie
  `fitmodel_segment` + `fitmodel_ingest_status`, ingest odbudowuje (w tym samym `daily_job` albo cron ingestu).
- `/ride-readiness` → QExt2 `maxHrBpm` (`mcp_server._maxhr_now`, źródło `qbot_auto`; env tylko awaryjnie).
- `threshold_sync.run_lthr` → intervals.icu `max_hr` i górna strefa tętna → Hammerhead/Karoo.
- Raport jazdy `%HRmax` (`ride_report_builder._hrmax_now`).
- Zmiana → jedna wiadomość na Telegramie.

## Przełączenie 20.10.2026
`hr_max_bpm` 184 → 173 (źródło `hrmax_auto`), odcinki 577 zarchiwizowane w `fitmodel_segment_bak_hrmax_20261020`
i do przeliczenia; QExt2 `maxHrBpm` = 173 (`qbot_auto`) sprawdzone na żywo po restarcie q-bot; intervals.icu już 173
(LTHR 153, strefy 124/136/142/151/156/162/173).
