# Qbot Backup & Recovery Guide

## Backup location
```
/opt/qbot/backups/qbot_YYYYmmdd_HHMMSS.sql.gz
```

## Manual backup
```bash
bash /opt/qbot/app/scripts/qbot_backup.sh
```

## Check backup status via API
```bash
curl -s -X POST http://127.0.0.1:8001/q \
  -H "Content-Type: application/json" \
  -d '{"tool":"qbot_backup_status","args":{}}' | jq
```

## List all backups
```bash
ls -lh /opt/qbot/backups/
```

## Verify backup integrity
```bash
gzip -t /opt/qbot/backups/qbot_*.sql.gz
```

## Inspect backup content (first 20 lines)
```bash
zcat /opt/qbot/backups/qbot_*.sql.gz | head -20
```

## Restore to a TEST database (NEVER on production)
```bash
# 1. Create test database:
createdb -U qbot -h localhost qbot_test

# 2. Restore:
gunzip -c /opt/qbot/backups/qbot_YYYYmmdd_HHMMSS.sql.gz | psql -U qbot -h localhost qbot_test

# 3. Verify:
psql -U qbot -h localhost qbot_test -c "SELECT COUNT(*) FROM tool_calls;"

# 4. Clean up test db:
dropdb -U qbot -h localhost qbot_test
```

## Rollback/Restore checklist
- [ ] Stop qbot-api.service: `systemctl stop qbot-api.service`
- [ ] Verify backup file integrity: `gzip -t /opt/qbot/backups/<file>`
- [ ] Create test restore first (see above)
- [ ] Verify test restore data looks correct
- [ ] Drop current qbot database: `dropdb -U qbot -h localhost qbot`
- [ ] Create fresh qbot database: `createdb -U qbot -h localhost qbot`
- [ ] Restore: `gunzip -c <backup_file> | psql -U qbot -h localhost qbot`
- [ ] Restart API: `systemctl start qbot-api.service`
- [ ] Verify: `curl http://127.0.0.1:8001/health`

## What NOT to do
- NEVER restore directly to production qbot database without testing first
- NEVER run restore without stopping API services
- NEVER delete backup files unless they are older than retention period
- NEVER expose backup files over HTTP
- NEVER commit backup files to git
- NEVER run pg_restore or dropdb without explicit manual confirmation

## Retention
- Backups older than 14 days are auto-cleaned by the script
- Keep off-server copies (scp, rsync, rclone) for disaster recovery

## Systemd timer (optional — install only when ready)
```bash
cp /opt/qbot/app/systemd/qbot-backup.service.example /etc/systemd/system/qbot-backup.service
cp /opt/qbot/app/systemd/qbot-backup.timer.example /etc/systemd/system/qbot-backup.timer
systemctl daemon-reload
systemctl enable --now qbot-backup.timer
systemctl status qbot-backup.timer
```

## Sensitive data
- Passwords are read from /opt/qbot/app/.env.local
- No passwords are stored in the backup script
- No passwords are printed in logs
- Backup files are created with chmod 600
