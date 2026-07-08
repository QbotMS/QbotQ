# ModelQ v1 -- ARCHIWUM (wycofane 2026-07-08)

Ten katalog zawiera silniki **poprzedniej generacji modelu (ModelQ v1)**, wycofane
po cutoverze na **ModelQ v2** (adapter `fitmodel/modelq2/publish.py`).

## Pliki
- `cp_v3.py` -- prog CP (+W') z krzywej mocy 1Hz: kotwica + zanik + dryf CTL. Zapisywal `cp_v3_w`.
- `cp_wprime.py` -- CP/W' z krzywych MMP (Garmin `training_sessions`). Zapisywal `cp_modelq_w`, `wprime_modelq_kj`, `ltp_modelq_w`.
- `training_load.py` -- CTL/ATL/TSB z XSS (raw + plus korygowany readiness). Zapisywal `ctl_xss`, `atl_raw`, `tsb_raw`, `atl_plus`, `tsb_plus`.

Dodatkowo logika FTP v1 (`run_weekly_job`, EF-anchored `ftp_est_w`) pozostaje w
`fitmodel/ftp_resolver.py` -- tego pliku NIE dalo sie przeniesc, bo zawiera
`_db_connect` uzywany przez caly system (w tym MQ2). `run_weekly_job` jest tam
martwym kodem (nie wywolywanym przez `daily_job`).

## Dlaczego wycofane
ModelQ v1 systematycznie zawyzal prog (ftp_est ~251-257 W vs realne TP ~240-245 W)
oraz forme (ctl_xss przeszacowany o ~16 pkt). ModelQ v2 liczy sygnature (TP/HIE/PP/LTP)
z wlasnego CTL wokol zamrozonych kotwic i jest zwalidowany vs Xert (TP ~2-4 W mediany).
Szczegoly: `docs/architecture/MODELQ_V2.md`.

## Jak przywrocic (awaryjny rollback kodu)
1. `git mv archive/modelq_v1/*.py fitmodel/`
2. W `fitmodel/daily_job.py` przywroc gowetke silnikow v1 (patrz historia git commita wycofania)
   oraz flage `MODELQ = os.environ.get("QBOT_MODELQ", "v1")`.
3. Odtworz dane z backupow: `qbot_v2.fitmodel_daily_v1_backup`, `fitmodel_wbal_ride_v1_backup`.

Kod jest zachowany w historii git -- ten katalog to wygodny punkt przywrocenia, nie jedyny.
