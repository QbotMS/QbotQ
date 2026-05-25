#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${APP_DIR}/.env.local"
BACKUP_DIR="/opt/qbot/backups"
RETENTION_DAYS=14

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

mkdir -p "$BACKUP_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
OUTFILE="${BACKUP_DIR}/qbot_${TS}.sql.gz"

PGUSER="${PGUSER:-qbot}"
PGHOST="${PGHOST:-localhost}"
PGDATABASE="${PGDATABASE:-qbot}"

export PGPASSWORD="${PGPASSWORD:-}"

pg_dump -U "$PGUSER" -h "$PGHOST" "$PGDATABASE" | gzip > "$OUTFILE"

chmod 600 "$OUTFILE"

SIZE="$(du -h "$OUTFILE" | cut -f1)"

find "$BACKUP_DIR" -name 'qbot_*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true

echo "Backup created: $OUTFILE (${SIZE})"
echo "Old backups (>${RETENTION_DAYS} days) cleaned up"
