---
tytul: Tętno maksymalne (automat)
dzial: modelq
typ: automat
opis: QBot sam wyznacza tętno maksymalne z wiarygodnych szczytów na jazdach i ustawia tę samą wartość w QBocie, QExt2 i na Karoo.
tagi: [tętno maksymalne, hrmax, strefy, automat, karoo, intervals]
synonimy: [max hr, hr max, maksymalne tętno, tętno max, maxhr, hfmax]
skroty: [HRmax, LTHR]
gdzie_widac: [Karoo, QExt2, Raport jazdy, Telegram]
liczby: [173 ud./min od 20.10.2026, 10 s utrzymania, 80% TP wysiłku, 365 dni, tolerancja 3 ud.]
zalezy_od: [modelq/tp]
wplywa_na: [forma/hrv-z-jazdy]
zrodla_kodu: [fitmodel/hrmax.py, qbot_v2.hrmax_peak, qbot_v2.hrmax_daily, fitmodel_param.hr_max_bpm, fitmodel/threshold_sync.py run_lthr, mcp_server.py _maxhr_now, qbot3/rides/ride_report_builder.py _hrmax_now]
aktualizacja: 21.10.2026
---

# Tętno maksymalne (automat)

## Co to jest

Jedna wartość tętna maksymalnego dla całego systemu, liczona codziennie z jazd. Od 20.10.2026: **173 ud./min**.

## Po co

Wcześniej była wpisywana ręcznie w kilku miejscach i się rozjechała (Karoo 173, QBot i QExt2 184). Od niej zależą strefy tętna na Karoo, kolory obciążenia w QExt2, %HRmax w raporcie jazdy i pasma tętna w odcinkach analizy ModelQ.

## Jak liczone

- **Szczyt z jazdy** (każda jazda raz): tętno **utrzymane ≥10 s**, w zakresie 120–210; **fizjologiczne tempo** (20 s wcześniej najwyżej 40 ud. niżej, 30 s później spadek najwyżej 40 ud.); **realny wysiłek**: średnia moc z 2 min przed ≥80% TP ModelQ z dnia jazdy. Odrzuca np. błąd starego paska z 02.05.2026 (93→181→115 przy ~70 W).
- **Wartość:** najwyższy wiarygodny szczyt z 365 dni. **W górę od razu**; **w dół** tylko gdy przez rok nic nie było bliżej niż 3 ud.
- Krok `hrmax` na początku codziennego przeliczenia (przed wczytaniem jazd).

## Gdzie to widać

- **Karoo** (strefy tętna — przez intervals.icu: `max_hr` i górna strefa), **QExt2** (`maxHrBpm`, źródło `qbot_auto`), **raport jazdy** (%HRmax), **odcinki analizy ModelQ** (pasmo 0,60–0,85 HRmax).
- **Telegram:** jedna wiadomość przy zmianie.

## Jak czytać

10 s utrzymanego tętna to dolna granica prawdziwego maksimum (chwilowy szczyt bywa o 1–2 ud. wyższy).

## Decyzje i historia

- 04.10.2026: ręcznie na Karoo 181 → 173 (181 = artefakt paska); QBot zostawiony na 184 (decyzja odłożona).
- 20.10.2026: decyzja Michała — automat zamiast ręcznych wpisów. Suchy przebieg: 376 jazd od 2025, 346 z wiarygodnym szczytem; najwyższe 172 (26.02.2025), 171 (24.01.2025), 170 (05.06.2026). Start od 173 (sprawdzone 04.10; 170 z ostatniego roku mieści się w tolerancji). Model QBota 184 → 173, odcinki analizy przeliczone od nowa (kopia `fitmodel_segment_bak_hrmax_20261020`).

## Ograniczenia i pułapki

- Szczyt liczy się tylko z jazd z pomiarem mocy (warunek wysiłku).
- Zmiana wartości uruchamia przeliczenie wszystkich odcinków analizy (kilkadziesiąt minut w tle).

## Powiązane hasła

- [TP ModelQ](tp.md)
- [HRV z jazdy](../forma/hrv-z-jazdy.md)

## Zrodla

- `fitmodel/hrmax.py` (`ride_peak`, `publish_value`, `run_daily`, `get_hrmax`), tabele `qbot_v2.hrmax_peak`, `qbot_v2.hrmax_daily`
- `fitmodel/daily_job.py` krok `hrmax`, `fitmodel/threshold_sync.py` `run_lthr`, `mcp_server.py` `_maxhr_now`, `qbot3/rides/ride_report_builder.py` `_hrmax_now`
- `tests/test_hrmax.py`, `docs/HRMAX.md`, `docs/DECISIONS.md` (2026-10-04, 2026-10-20)
