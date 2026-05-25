# Qbot Operational Readiness

## Architecture
- API: FastAPI on 127.0.0.1:8001
- Database: PostgreSQL (qbot)
- Backups: /opt/qbot/backups, daily timer at 03:20
- Restore drill: qbot_restore_drill (test DB for backup verification)

## What READY means
- `READY`: All subsystems OK, no blockers, no real errors
- `READY_WITH_WARNINGS`: System operational with informational warnings (e.g. old test errors, no restore drill)
- `NOT_READY`: Critical blockers (DB down, no backup, guard errors, service failures)

## Expected test errors
Expected test errors are historical tool_calls from testing (unknown tools, validation tests, bad names). They are classified by qbot_test_error_classification and do NOT affect readiness. Real errors are those that don't match known test patterns.

## Backup
- Timer: `systemctl status qbot-backup.timer`
- Manual: `systemctl start qbot-backup.service`
- Status via API: `qbot_backup_status`
- Location: `/opt/qbot/backups/qbot_YYYYmmdd_HHMMSS.sql.gz`
- Retention: 14 days

## Restore drill
- Test database: `qbot_restore_drill`
- NEVER restore over `qbot` production database
- Drill plan: `qbot_restore_drill_plan`
- Drill status: `qbot_restore_drill_status`
- See docs/qbot_backup_recovery.md for full recovery guide

## Using qbot_query
Natural language queries through the `/q` endpoint:
```bash
curl -s -X POST http://127.0.0.1:8001/q \
  -H "Content-Type: application/json" \
  -d '{"tool":"qbot_query","args":{"query":"czy qbot jest gotowy"}}'
```

Add `"execute": true` for runbook execution:
```bash
curl ... -d '{"tool":"qbot_query","args":{"query":"pełny przegląd","execute":true}}'
```

## Final smoke test
```bash
curl -s -X POST http://127.0.0.1:8001/q \
  -H "Content-Type: application/json" \
  -d '{"tool":"qbot_operator_final_smoke_test","args":{}}' | jq
```
Checks: API health, backup timer, backup files, restore drill, guard, git, readiness, error classification. Returns operational readiness percent.

## LLM rules (LLM boundary)
- **LLM role**: answer_synthesizer_only (summarize, explain, report)
- **LLM NEVER**: execute commands, access secrets, modify files, perform backup/restore
- **Source of truth**: Qbot tools and PostgreSQL logs
- **Integration is OPTIONAL** — system works without LLM
- Context is sanitized via qbot_answer_context before any LLM exposure

## Quick operator curl commands
```bash
# Health
curl http://127.0.0.1:8001/health

# Readiness
curl -s -X POST http://127.0.0.1:8001/q -H 'Content-Type: application/json' \
  -d '{"tool":"qbot_readiness_report","args":{}}' | jq

# Final smoke test
curl -s -X POST http://127.0.0.1:8001/q -H 'Content-Type: application/json' \
  -d '{"tool":"qbot_operator_final_smoke_test","args":{}}' | jq

# Backup status
curl -s -X POST http://127.0.0.1:8001/q -H 'Content-Type: application/json' \
  -d '{"tool":"qbot_backup_status","args":{}}' | jq

# Maintenance report
curl -s -X POST http://127.0.0.1:8001/q -H 'Content-Type: application/json' \
  -d '{"tool":"qbot_maintenance_report","args":{}}' | jq
```

## What NOT to do
- NEVER restore directly to production qbot database
- NEVER run DROP DATABASE qbot
- NEVER delete backup files younger than 14 days
- NEVER expose backup files over HTTP
- NEVER commit credentials
- NEVER restart production services without confirmation
- NEVER bypass LLM boundary rules
