# Kopia offsite olga181 -> Cloudflare R2

Stan od 2026-10-19 (sesja backup-r2-1910). Zastepuje tygodniowa kopie Mac/iCloud uruchamiana z Codex
(opis historyczny: docs/audit/sesja_aktualizacja_backup_mikrus_2026-10-19.md).

## Co i kiedy
- **Kiedy:** co niedziele ok. 04:30 (Europe/Warsaw), timer `qbot-offsite-r2.timer`, `Persistent=true`
  (gdy serwer byl wylaczony, kopia nadrabia sie po starcie). Nie zalezy od Maca ani od ChatGPT/Codex.
- **Gdzie:** Cloudflare R2, bucket `qbot-olga181-backup` (konto Mstawski@gmail.com, lokalizacja EEUR),
  repozytorium restic, szyfrowane.
- **Skrypt:** `scripts/offsite_backup_r2.py` (root), usluga `qbot-offsite-r2.service`.
- **Alert:** Telegram tylko przy bledzie. Sukces = brak wiadomosci.
- **Status:** `/var/lib/qbot-offsite-backup/r2-status.json` albo `python3 scripts/offsite_backup_r2.py --status`.
- **Retencja:** 8 ostatnich tygodniowych + 6 miesiecznych, `forget --prune` po kazdej kopii.
- **Kontrola:** po kazdej kopii `restic check --read-data-subset 3%` (losowe 3% danych pobierane i sprawdzane).
- **Koszt:** darmowy limit R2 = 10 GB/mies. Powyzej ok. 0,015 USD/GB/mies.

## Zakres (whitelist)
Kopiowane: `/etc`, `/root`, `/usr/local`, `/var/spool/cron`, `/var/www`, `/opt/qbot`, `/opt/q365`, `/opt/qext2`,
`/opt/q`, `/opt/noobs`, `/opt/qbot-offsite-backup` oraz eksporty z `/var/lib/qbot-offsite-backup/staging-r2`:
- wszystkie bazy PostgreSQL (`pg_dump -Fc`, kazdy sprawdzony `pg_restore --file=/dev/null`) + role,
- spojne kopie SQLite `garage.db`, `qbot_mcp_auth.db` (backup API + integrity_check),
- `pip freeze` kazdego venv, lista pakietow dpkg, lista unitow systemd, `manifest.json`.

Pominiete swiadomie (decyzja Michala 19.10.2026, do pobrania/odbudowy): mapy OSM `data/osm/*.pbf` i `roads.sqlite`
(`landmarks.sqlite` JEST w kopii), WorldCover, `.venv`/venv (zamiast nich pip freeze), przegladarki Playwright,
cache pip/npm/apt, `/opt/qbot/backups` (lokalne dzienne zrzuty), `_archiwum`, `artifacts/old`, historia Codex,
pipx/opencode, surowy `/var/lib/postgresql` (zamiast tego eksport).

Uwaga: pliki i eksporty baz nie sa jednym punktem w czasie. To nie jest obraz LXC.

## Sekrety (tylko root, 600)
- `/root/.config/qbot-offsite/r2.env` - klucz R2 (Object Read & Write, TYLKO bucket qbot-olga181-backup) + adres repo.
- `/root/.config/qbot-offsite/restic-password` - klucz szyfrowania. **Kopia tego pliku musi byc w menedzerze hasel.**
  Bez niego kopii nie da sie odszyfrowac. Wyswietlenie (tylko Michal, recznie): `ssh q cat /root/.config/qbot-offsite/restic-password`.

Klucz R2 lezy na serwerze. Przejecie serwera = mozliwosc odczytu i skasowania kopii w R2 (blokady usuwania nie ma,
bo koliduje z automatyczna retencja).

## Obsluga
```bash
ssh q systemctl start --no-block qbot-offsite-r2     # kopia teraz, w tle
ssh q python3 /opt/qbot/app/scripts/offsite_backup_r2.py --status
ssh q journalctl -u qbot-offsite-r2 -n 50 --no-pager
ssh q systemctl list-timers qbot-offsite-r2.timer
```
Lista kopii (root na serwerze):
```bash
set -a; . /root/.config/qbot-offsite/r2.env; set +a
export RESTIC_PASSWORD_FILE=/root/.config/qbot-offsite/restic-password
/opt/qbot-offsite-backup/restic snapshots
```

## Odtwarzanie (nowy serwer)
1. Zainstaluj restic, ustaw `r2.env` i `RESTIC_PASSWORD_FILE` (z menedzera hasel), `restic snapshots`.
2. `restic restore latest --target /restore` i przenies potrzebne katalogi (`/etc` selektywnie, `/opt/*`, `/root`).
3. PostgreSQL 16: odtworz role `postgres-roles.sql`, potem `pg_restore -C -d postgres postgres-qbot.dump`
   (pliki w `/restore/var/lib/qbot-offsite-backup/staging-r2/`).
4. SQLite: skopiuj `sqlite-opt_qbot_app_data_garage.db` -> `/opt/qbot/app/data/garage.db`,
   `sqlite-opt_qbot_app_qbot_mcp_auth.db` -> `/opt/qbot/app/qbot_mcp_auth.db`.
5. Venv: `python3 -m venv .venv && .venv/bin/pip install -r pip-freeze-qbot-app.txt` (analogicznie qbot-mcp, q365, cronometer).
6. Playwright: `.venv/bin/playwright install chromium`.
7. Mapy OSM: pobierz `poland-latest.osm.pbf` (Geofabrik) do `/opt/qbot/data/osm/` i odbuduj `roads.pbf`/`roads.sqlite`
   tym samym procesem co 5.10.2026 (`poland.poly` jest w kopii).
8. Unity systemd sa w `/etc/systemd/system` (z kopii) - `systemctl daemon-reload`, wlacz uslugi wg `systemd-units.txt`.
