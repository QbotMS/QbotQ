# Krok 4b diagnoza

Data: 2026-06-15

## Weryfikacja importu
- Import w kontekście `qbot` działa:
  - `runuser -u qbot -- env PYTHONPATH=/opt/qbot/app /opt/qbot/app/.venv/bin/python -c "from qbot_mcp_adapter import _action_exec_event, _action_exec_reminder; print('OK')"`
  - wynik: `OK`
- Import z mojego lokalnego kontekstu nie przeszedł przez odczyt `.env` (`PermissionError` na `/opt/qbot/app/.env`), ale to nie jest blocker dla procesu serwisowego.

## _action_exec_event / _action_exec_reminder
- `_action_exec_event(payload, idem_key, source)` woła `qcal_event_add_controlled(...)`.
- `qcal_event_add_controlled(...)` ma:
  - confirm/idempotency guard
  - duplicate check przez `qcal_write_audit`
  - natural-key duplicate fallback
  - create event + audit + snapshot rebuild
- `_action_exec_reminder(payload, idem_key, source)` robi prosty INSERT do `reminders`, audit i snapshot rebuild.
- Potwierdzenie: dla reminder nie ma duplicate-check na poziomie writer-a, więc per-run dedup w `agent_runtime.py` jest właściwą ochroną na duplikaty w jednej turze. Duplikaty między osobnymi `qbot.query` zostają known limitation, nie blocker.

## Args schema
- `calendar_event_add` zostało doprecyzowane do:
  - required: `date_start`, `title`
  - optional: `time_start`, `date_end`, `event_type`, `description`, `all_day`
- `reminder_add` zostało doprecyzowane do:
  - required: `date`, `title`
  - optional: `time`, `message`, `reminder_type`, `priority`, `channel`, `recurrence_rule`

## Decyzja zakresu
- Po diagnozie nadal zostaje 5 write tools na `WRITE_DRAFT`:
  - `memory_confirmed_fact_add`
  - `planning_fact_add`
  - `garmin_workout_create`
  - `route_poi_analyze`
  - `rwgps_route_import_gpx`
- To jest za dużo, żeby bezpiecznie usuwać `qbot.action_execute` z `tools/list` w tej sesji.
- Wybór: Opcja B, czyli zostawiam `qbot.action_execute` w `tools/list`, a pełna decyzja o wycięciu zostaje TODO.
