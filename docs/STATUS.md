# STATUS funkcji QBota (2026-10-15)

Prosta informacja, czy dzialaja funkcje QBota. Jedno zrodlo prawdy dla strony i dla Alberta.

## Gdzie
- Strona: SETUP > Polaczenia > Status (`/opt/qbot/web/public/status.html`, ramka w `setup.html`; paleta UI2). Tylko wlasciciel (demo -> 403).
- API: `GET /api/setup/status` (`qbot_status_api.py`, montowany w `qbot_web.py`).
- Logika: `qbot_status_checks.py` -> `all_checks()`; kazdy check zwraca `{id, name, state, text, last, details}`,
  `state` = ok | warn | bad | off (off = swiadomie wylaczone). Teksty prostym jezykiem, daty DD.MM HH:MM.
- Albert: `qbot_status_overview` (wszystko), `hammerhead_sync_status`, `withings_sync_status`, `llm_status`, `gate_status`
  (capabilities w `qbot3/capabilities/system/`, opisane w prompcie Alberta).

## Co sprawdzamy (tylko odczyt)
| Funkcja | Zrodlo | Zle gdy |
|---|---|---|
| Uslugi QBota | systemctl is-active (api, web, mcp-bridge, qlab) | ktoras nieaktywna |
| Garmin -> QBot | state/garmin_watch.json (timer co 10 min) | brak importu > 1 h albo blad czesci danych |
| Hammerhead -> Garmin (TACX) | state/processed_hammerhead_activities.json + logs/hammerhead-garmin-sync.log (cron root co 10 min) | brak sprawdzenia > 1 h; 409 "Duplicate Activity" = OK (jazda juz jest w Garminie) |
| Withings -> Garmin | state/processed_withings_measures.json + state/withings_sync_alert_state.json | plik alarmu istnieje / brak pomiarow > 72 h |
| Komoot | systemd qbot-komoot-watch.service | blad / dawno nie uruchamiane |
| Kopia bazy | systemd qbot-backup.service | blad / > 60 h |
| Model AI Alberta | qbot3/llm/model_profiles.py (data/albert_model.json) | — |
| Bramka HikConnect | capability gate_status + /opt/qbot/artifacts/gate_log.jsonl | `warn` gdy usluga nie odpowiada, konfiguracja niepelna albo ostatnia proba po ostatnim otwarciu byla nieudana (http>=500 / stale); inaczej `ok` z data ostatniego otwarcia z dziennika (20.10.2026: wczesniej na sztywno `off` -- nieaktualne po przebudowie 16.10) |

## Decyzje (15.10.2026)
- Stary mechanizm Hammerhead per-profil (michal/user2/user3) zakonczyl prace 26.07 -- status NIE czyta jego plikow (resztki w /opt/qbot/_archiwum/2026-10-15/).
- `llm_status` czyta przelacznik modelu Alberta (wczesniej stara konfiguracje QGPT/OpenRouter -> sprzeczne odpowiedzi).
- Raport dzienny (`daily_report_status`) zaorany -- artefakt z poczatkow QBota.
- Nowa funkcja do statusu = nowy check w `qbot_status_checks.CHECKS` (strona i Albert dostaja ja automatycznie).

## Audyt tygodniowy (etap 5, 15.10.2026)
- `scripts/weekly_audit.py`, timer `qbot-weekly-audit` (pon 02:30, pliki: deploy/systemd/). Sprzata kopie .bak/_tmp_ starsze niz 7 dni
  (do _archiwum), puszcza wszystkie testy, liczy kandydatow na martwy kod, sprawdza status funkcji. Wynik: state/weekly_audit.json
  -> pozycja "Audyt tygodniowy" w Status. Telegram: jedna wiadomosc tylko przy NOWYM problemie.
- Instalacja (root): cp deploy/systemd/qbot-weekly-audit.* /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now qbot-weekly-audit.timer
- Inne bezpieczniki (testy): test_no_xert_basis (Xert nie jest podstawa), test_qdate_copies (kopie funkcji dat identyczne), test_tz_display.


## 2026-10-19 dodane (sesja aktualizacje-1910)
- Wiersz **Kopia poza serwerem (R2)**: czyta state/offsite_r2.json (publiczne podsumowanie pisane przez scripts/offsite_backup_r2.py; bez sekretow). Brak udanej kopii > 9 dni = zolty, blad = czerwony. Dok.: docs/BACKUP_OFFSITE_R2.md.
- Wiersz **Aktualizacje**: czyta state/updates.json (scripts/updates_check.py). Pozycje pilne = zolty. Obok zakladki Status: zakladka Aktualizacje. Dok.: docs/AKTUALIZACJE.md.
- Audyt tygodniowy: czas z weekly_audit.json (lokalny, bez strefy) czytany jako czas polski (wczesniej +2 h).
