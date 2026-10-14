# QBot — progi i pochodne ModelQ (stan 2026-10-08)

_Dokument opisuje mechanizmy wdrozone 08.10.2026. Zywy system wygrywa — weryfikuj na kodzie i bazie.
Decyzje i liczby: docs/DECISIONS.md (wpisy 2026-10-08). Otwarte sprawy: docs/TODO.md._

## 1. CP / TP (prog mocy)
- **Model, nie pomiar:** TP = kotwice z `qbot_v2.modelq2_anchor` + dryf za CTL (`fitmodel/modelq2/progression.py`, `decay.py`).
- **08.10:** usunieta skazona auto-kotwica EF z 11.08 (TP 265.5, miernik +25 %) -> TP 255.4 -> **239.4 W**.
  Skrypt: `scripts/mq2_drop_anchor_20260811.py`; kopie `qbot_v2.bak_20261008_*`.
- Auto-kotwica EF wylaczona od 25.08 (`EF_ANCHOR_DISABLED`). Przeglad TP: `fitmodel/tp_recheck.py` (automat, tylko raport).
- **Uwaga:** "dolna granica TP z W'bal" (04.10) opiera sie na artefakcie regeneracji Skiby — do rewizji (TODO [MODELQ-TP-PRZEGLAD]).

## 2. Przelomy CP — `fitmodel/cp_breakthrough.py` (wariant B, z potwierdzeniem)
- Czysta jazda (bez kwarantanny, poza METER_BAD, `meter_phys` < 1.15): MMP 2/5/10/20 min > krzywa `TP + W'/d` o > 1 %
  -> kandydat w `qbot_v2.cp_breakthrough`; krotkie podnosza W', dlugie TP; limity +3 % TP, +15 % W'.
- Telegram: `#NN ... NN TAK / NN NIE` (48 h), akcja `confirm_cp_breakthrough` w `qbot_qcal_telegram.py`;
  TAK -> kotwica `przelom (zatwierdzony Telegram)` + `build_and_store` + `publish_to_daily`.
- Krok `daily_job`: `cp_breakthrough` (po `modelq2_v2`). Sprawdzone jazdy: `qbot_v2.cp_bt_checked`.
- Backtest 12.2025–10.2026: 0 przelomow (max 95 % krzywej). Detekcja z W'bal ODRZUCONA (falszywe przelomy).
- **TODO:** po >= 3 zatwierdzonych bez korekty -> automat (wariant A).

## 3. LTHR (tetno progowe) — `fitmodel/lthr.py`, dynamiczne
- Zastapilo kanon 132 bpm. Okna 8 min rownej jazdy, `HR + k*(1-%CP)`, k = mediana nachylen w obrebie jazd (start 80),
  mediana 120 dni, min. 12 okien / 4 jazdy; bez kwarantanny, METER_BAD i upalu (>= 26 C).
- Publikacja `qbot_v2.lthr_daily.lthr_bpm`: histereza 2 ud., max 3 ud./7 dni, start 150. **Dzis 148.**
- Krok `daily_job`: `lthr` (przed `modelq2_v2`), `lthr_sync` (po `threshold_sync`).
- Konsumenci (`get_lthr()`): XSS z tetna, raport jazdy (strefy HR Coggan 68/83/94/105 % LTHR), Trener, Albert,
  qbot-api `lthrBpm` (QExt2), intervals.icu `lthr` + `hr_zones` (Friel 81/89/93/99/102/106 % + max HR) -> Karoo.
- LTHR (bpm) prawie sie nie zmienia od treningu; rosnie moc przy nim (CP).

## 4. XSS z tetna — `fitmodel/modelq2/hr_xss.py`
- Dla jazd w kwarantannie miernika. LTHR na dzien jazdy + K_LOW/K_HIGH z `qbot_v2.hr_xss_calib`
  (`lthr.calibrate_hr_xss`, co 28 dni lub po zmianie LTHR). 08.10: K_LOW 0.924, K_HIGH 1.412.
- Korekta temperatury `temp_factor` (a + b*(T-15)), przycieta 0.80–1.25; dopasowanie slabe (+-5 %), zostawiona decyzja Michala.
- Kwarantanna rozszerzona 08.10: 01.08 Opole, 03.08 Prudnik; 22.07–02.08 przeliczone z HR (`scripts/mq2_quarantine_hr_20261008.py`).

## 5. Gotowosc TERAZ — `fitmodel/readiness_now.py`
- Poranna gotowosc (3 dni) minus kara za dzisiejsze jazdy `0.6 * XSS/CTL * 0.5^(h/5.5)`; liczona na zywo w `/api/forma/data`
  (`readiness_now`), nic nie zapisuje. Zegar Gotowosci w Dzienniku pokazuje wartosc teraz + wartosc poranna.

## 6. Glikogen — `fitmodel/glycogen.py`
- Jazdy z `activity_record` zamiast czytania wszystkich plikow FIT: 930 s -> 0.4 s, wyniki identyczne.

## 7. Wycofane 08.10
- **Trwalosc (durability):** zbadana i usunieta w calosci (kod, API, UI, pole dla Karoo, tabela `durability_ride`).
  Powod: do ~4 h brak spadku mocy (mediana 102 %), spadek dopiero po ~5 h — brak wartosci na co dzien.
- Wniosek, ktory zostaje: **RSRV na Karoo jest 3–5x za szybki** (po 2,4 h ~19 %) — kierunek dla QExt2 w TODO [RSRV].

## 8. CI
- `.github/workflows/smoke.yml`; `requirements.txt` przypina `mcp`/`pydantic` jak na serwerze.
- Odtworzenie CI lokalnie: `bash scripts/ci_smoke_repro.sh` -> `/opt/qbot/artifacts/ci_smoke_repro.txt`.
